# PADM Dashboard — Build Specification

Single source of truth for the "PADM" (Portfolio/Prospect Acquisition Direct Mail) campaign
sign-off dashboard, replacing CreditOne Bank's manual Excel "Signature Page" sign-off process
for monthly direct-mail credit-card campaigns. Written from everything confirmed against the
real Snowflake schema (via `GET_DDL`/`DESC`), the sign-off proposal PDF, the handwritten scope
notes, and the real `Segment.xlsx`/`Signature page.xlsx` workbooks — not from assumption.

---

## 1. Platform & Architecture

- **Target**: Streamlit in Snowflake (Snowpark Python), multi-tab via `st.tabs`.
- **Database/schema**: `DB_RISK.RISK_SBX`.
- **Deployment type**: classic warehouse-backed Streamlit app (not SPCS/compute-pool-based —
  the compute-pool variant requires its own network/External Access Integration setup and adds
  no value here; a warehouse-backed app needs no `requirements.txt`, no compute pool, and uses
  the same connectivity as the rest of Snowsight).
- **Layered app structure** (`app/`):
  - `app/db.py` — session primitives only: `SCHEMA`, `df()`, `exec_sql()`, `call_proc()`.
  - `app/queries.py` — every read-only `SELECT`, one function per query, grouped by domain.
  - `app/repository.py` — every write: `INSERT`/`UPDATE`/`MERGE` and all `CALL <procedure>`
    invocations. May call into `queries.py` for read-before-write checks, never the reverse.
  - `app/ui.py` — pure visual layer: theme CSS injection, status pills, campaign banner,
    workflow stepper, chips. No DB or business logic.
  - `app/pages/*.py` — one file per tab, thin: Streamlit widgets calling `queries.*`/
    `repository.*`/`ui.*` only. **No inline SQL in any page file.**
  - `.streamlit/config.toml` — theme (primary color, background, font).
- **Why this structure**: separates reads from writes, keeps every page file reviewable at a
  glance, and avoids the duplication bug found in the user's own earlier
  `campaign_setup.py`/`campaign_queries.py` (a private `_discover()` reimplementing what
  `campaign_repository.discover_campaign()` already did via `MERGE`).

---

## 2. Database Objects

### 2a. Real, pre-existing objects (not created by this build — confirmed via `GET_DDL`)
- `DM_PADM_CAMPAIGN_1` — campaign master. Key columns: `CAMPAIGN_ID` (PK), `REPORTING_MONTH` +
  `CAMPAIGN_TYPE` (composite unique key; `CAMPAIGN_TYPE` constrained to `'MAIN'`/`'REMAIL'`),
  `STATUS` (constrained to `DISCOVERED`/`DRAFT`/`READY_FOR_REVIEW`/`COMPLETED`/`REOPENED`,
  default `'DISCOVERED'`), `CURRENT_SOURCE_VERSION_NUMBER` and `CURRENT_WORKING_VERSION_NUMBER`
  (two separate, both-real version counters — do not confuse them), `ACTIVE_FLAG`,
  `SOURCE_CHANGE_PENDING_FLAG`, `ROW_VERSION`, audit columns.
- `DM_PADM_CAMPAIGN_OFFER` — one row per offer per campaign-source-version. Originally had no
  `CREDIT_BUREAU_MODEL`/`SCORE`/`CRS_MODEL`/`NRM` columns (added by `sql/30_...`, see below).
- `VW_PADM_CAMPAIGN_OFFER_CURRENT` — thin passthrough view over `DM_PADM_CAMPAIGN_OFFER`
  joined to `DM_PADM_CAMPAIGN_SOURCE_VERSION` (`IS_CURRENT = TRUE` both sides).
- `VW_PADM_ACM_OFFER_SOURCE` — the real bridge view from the raw ACM tables
  (`CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS` joined to `T_ACM_PROGRAMS`) into PADM-shaped
  column names. **Already exposes** `CREDIT_BUREAU_MODEL`, `CREDIT_BUREAU_SCORE`, `CRS_MODEL`,
  `CRS_SCORE`, `NRM`, `ANNUAL_FEE`, `NETWORK`, `PROMO`, `IVR`, etc. — the gap was always
  downstream of this view, never in it.
- `VW_PADM_ACM_CAMPAIGN_CANDIDATE` — campaign discovery source (13 columns: year/month/
  reporting-month/sequence/type/display-name + source counters/dates).
- `SP_PADM_ACTIVATE_CAMPAIGN(P_CAMPAIGN_ID, P_CHANGE_REASON)` — moves `DISCOVERED`/`REOPENED`/
  incomplete `DRAFT` → `DRAFT`, snapshotting ACM offers into a new
  `DM_PADM_CAMPAIGN_SOURCE_VERSION`/`SOURCE_COMPONENT`/`DM_PADM_CAMPAIGN_OFFER`/
  `DM_PADM_CAMPAIGN_OFFER_PROFILE` set, validated and rolled back on mismatch.
- `SP_PADM_TRANSITION_CAMPAIGN(P_CAMPAIGN_ID, P_TO_STATUS, P_REASON, P_COMMENT)` — enforces the
  allowed workflow path only; readiness validation is the application's job.
- `SP_PADM_ACTIVATE_CDE_VERSION` — activates an uploaded CDE batch. **Signature not yet
  independently confirmed via `GET_DDL`** — `repository.load_cde_version` currently calls it as
  `(load_batch_id, reason)`; verify with `SHOW PROCEDURES LIKE 'SP_PADM_ACTIVATE_CDE_VERSION' IN
  SCHEMA DB_RISK.RISK_SBX;` before relying on it.
- `SP_PADM_SAVE_CAMPAIGN_ASSUMPTION` — pre-existing, campaign-level CPP/Unit Cost/adjustments.
- `VW_PADM_SEGMENT_CALCULATION_CURRENT` — the live (not snapshotted) per-segment calculation
  view. Confirmed columns: `CDE_VOLUME`, `EMS_REDUCTION_RATE`, `POST_EMS_VOLUME`,
  `SELECTION_PERCENTAGE`, `SELECTED_QUANTITY`, `BASE_NRR`, `EFFECTIVE_NRR`, `SELECTED_NRR`,
  `HISTORICAL_UNWIND_RATE`, `BOOKED_PRE_UNWIND_UNIVERSE/SELECTED`,
  `MARKETING_COST_UNIVERSE/SELECTED`, `BOOKING_COST_UNIVERSE/SELECTED`,
  `EXPECTED_UNWINDS_UNIVERSE/SELECTED`, `BOOKED_POST_UNWIND_UNIVERSE/SELECTED`,
  `PRE_UNWIND_CPA_UNIVERSE/SELECTED`, `POST_UNWIND_CPA_UNIVERSE/SELECTED`. Reads from CDE grid +
  selection working + assumptions — **this is why every downstream grid recalculates live** the
  moment an assumption or a selection % changes; nothing needs to be "re-run" except the final
  Signature Page 2 snapshot, which is a deliberate immutable freeze.
- `DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT` — 36-column immutable snapshot table; its column order is
  the correct, already-confirmed Signature Page field order (see §5).

### 2b. Gap-fill additions, this build (`sql/20_additional_procedures_and_views.sql`)
Confirmed genuinely missing (none of these 4 appear in the real procedure inventory):
1. `SP_PADM_SAVE_SEGMENT_ASSUMPTION` — segment-level override save, mirrors the campaign-level one.
2. `SP_PADM_SAVE_SELECTION_SET` — persists `DM_PADM_SELECTION_WORKING` into an immutable
   `DM_PADM_SELECTION_SET`/`SELECTION_SET_CELL` + `SELECTION_EVENT` audit row.
3. `SP_PADM_RUN_CALCULATION` — snapshots `VW_PADM_SEGMENT_CALCULATION_CURRENT` into
   `DM_PADM_CALCULATION_RUN`/`CALCULATION_CELL`. Required because nothing else populated these
   tables, and `signature_page_2_snapshot.sql`'s template requires a `COMPLETED` run to exist.
4. `SP_PADM_GENERATE_SIGNATURE_PAGE_2` — wraps the original bare
   `INSERT...SELECT` template (found with no version numbering, no completed-run guard) in a
   procedure that adds both.
5. `VW_PADM_SIGNATURE_PAGE_LIVE` — live (pre-snapshot) view, same grain/formulas as the Signature
   Page 2 snapshot insert, for the Signature Page tab and the pre-submission preview.

**Snowflake Scripting style note** (verified against the user's own working
`SP_PADM_ACTIVATE_CAMPAIGN`): every `IF (...)` condition and boolean assignment must be
**single-line**, even multi-clause ones. A multi-line `IF`/`OR` continuation is a real syntax
error in this environment — this caused the original reported bug.

### 2c. Gap-fill additions, this build (`sql/30_wire_credit_bureau_fields.sql`)
Wires `CREDIT_BUREAU_MODEL`, `CREDIT_BUREAU_SCORE`, `CRS_MODEL`, `NRM` end-to-end — all four are
real sign-off-proposal fields, all four already exposed by `VW_PADM_ACM_OFFER_SOURCE`, none of
them ever selected into `DM_PADM_CAMPAIGN_OFFER` by the real `SP_PADM_ACTIVATE_CAMPAIGN`:
1. `ALTER TABLE DM_PADM_CAMPAIGN_OFFER ADD COLUMN` all 4 (additive, non-breaking).
2. `CREATE OR REPLACE VIEW VW_PADM_CAMPAIGN_OFFER_CURRENT` — same passthrough, +4 columns.
3. `CREATE OR REPLACE PROCEDURE SP_PADM_ACTIVATE_CAMPAIGN` — reconstructed verbatim from the
   real procedure's `GET_DDL`, with only these 4 columns added to its `DM_PADM_CAMPAIGN_OFFER`
   insert. Nothing else in the procedure changed.
4. One-time backfill `UPDATE` for offers already activated before this change.

**Run order matters**: `30_...` must run before/with `20_...`, since `20_...`'s
`VW_PADM_SIGNATURE_PAGE_LIVE` and `SP_PADM_GENERATE_SIGNATURE_PAGE_2` reference these 4 columns.

**Not addressed, deliberately**: the sign-off proposal describes `Underwriting Flag` and
`Prospect Type` as derived/lookup values (a CASE expression, a named lookup), but
`VW_PADM_ACM_OFFER_SOURCE` passes them straight through from the ACM table under matching names.
Whether the ACM table's values already have that derivation applied upstream is unconfirmed —
left alone rather than guessed.

---

## 3. Page Specifications

Tab order: **Campaign Creation → Signature Page → Create Segment → Campaign Assumptions →
Population Description → Segment Viewer → Signature Page 2**.

Every page (except Campaign Creation, which has no single campaign context yet) opens with a
`ui.campaign_banner()`: campaign display name + a colored status pill
(`DRAFT`/`READY_FOR_REVIEW`/`COMPLETED`/`REOPENED`, consistent palette across the app).

### 3.1 Campaign Creation
- Table of all campaigns (`VW_PADM_CAMPAIGN_CURRENT`): id, display name, reporting month, type, status.
- Select one → **"Open this campaign"** sets `st.session_state["selected_campaign_id"]`, used by
  every other tab via `require_campaign()`.
- For `DISCOVERED`/`REOPENED` rows → **"Activate"** popover (reason required) →
  `SP_PADM_ACTIVATE_CAMPAIGN`.
- **"Discover new campaigns"** button → `MERGE` of `VW_PADM_ACM_CAMPAIGN_CANDIDATE` into
  `DM_PADM_CAMPAIGN_1` on `(REPORTING_MONTH, CAMPAIGN_TYPE)`; inserts new rows as `DISCOVERED`,
  flags `SOURCE_CHANGE_PENDING_FLAG` on existing rows whose source mail-date range moved.

### 3.2 Signature Page
Live view (`VW_PADM_SIGNATURE_PAGE_LIVE`), grouped by **Credit Bureau Model + Credit Bureau
Score** (expander per group). **Exact column order, confirmed from the real Excel sign-off
sheet** — do not reorder:

`Segment Description, AF, Test Type, Network, Credit Bureau Model, Credit Bureau Score, CRS
Model, CRS Score, NRM, Quantity, NBR, Boards, CPP, Marketing Expense, Unwind Rate, Pre-Unwind
CPA, Post-Unwind CPA, PROMO, IVR, Underwriting Flag, Prospect Type, Times Mailed 0%, Tiers,
Print Vendor, Post-Unwind Boards, Marketing + Booking Costs`

Per-group subtotal chips (Quantity, Boards, Marketing + Booking Costs) + a grand-total 3-tile
row at the bottom.

### 3.3 Create Segment
- Unallocated offers table (offers on this campaign not yet assigned to any segment).
- Assign selected offers → an existing governed segment, or create a new one (name, score
  type/min/max, prospect segment type, annual fee, network, MLA flag, mail/remail, response
  model type, risk score type) — change reason required, audited.
- Segments-in-this-campaign summary table (segment, offer count).

### 3.4 Campaign Assumptions
- **Campaign-level only** (CPP, Unit Cost, Rate Adjustment, Seasonality Reduction, Unwind Rate
  Adjustment) + version history expander. A negative Rate Adjustment or Unwind Adjustment warns
  that it needs assumptions-owner sign-off per PADM_CLARIFICATIONS, but is not blocked.
- Segment-level overrides are **not** here — moved to Segment Viewer (§3.6), so the override and
  its effect on the calculated grids live on one page.

### 3.5 Population Description
- Per (Offer, Credit Bureau Score... wait, per `(OFFER_RESERVATION_CODE, CRS_SCORE)` — grouped
  expander showing segment name + editable population description per allocated segment, with a
  Quantity/Boards subtotal. Change reason required to save a label.

### 3.6 Segment Viewer — the core calculation page
Order matters; this is the page where changing an input is meant to visibly cascade through
every grid below it, because every grid reads `VW_PADM_SEGMENT_CALCULATION_CURRENT`, a **live**
view — saving a new assumption or a new selection % recalculates it on the next read, no
separate "run" step needed (that's what `SP_PADM_RUN_CALCULATION` on Signature Page 2 is for —
freezing a point-in-time snapshot, not making the live numbers correct).

1. **Segment selector.**
2. **Segment Assumptions** (CPP/Unit Cost/Rate Adjustment/Seasonality Reduction/Unwind Rate
   Adjustment overrides for *this* segment) — at the top, so its effect on the grids below is
   visible on the same page without a tab switch.
3. **CDE upload** (pivoted CSV: col 0 = TRM10 tier 1–20, remaining headers = Times Mailed
   buckets 0–8/9+, values = Count Distinct EPIN; `Total`/`Grand Total` rows/cols ignored
   automatically). On load: new `DM_PADM_CDE_LOAD_BATCH` + `DM_PADM_CDE_DETAIL` rows →
   `SP_PADM_ACTIVATE_CDE_VERSION`. CDE Volume and Post-EMS Volume become visible immediately
   once this loads (the working selection grid auto-initializes per CDE cell, defaulting to the
   prior campaign's saved % where available, else 0).
4. **Selection % (editable grid)** — pivot table, Response Model Tier × Times Mailed Bucket,
   non-zero cells highlighted. **Known follow-up, not yet implemented**: PADM_NOTES specifies a
   3-tier color scheme (prior-matched = yellow, current-saved = green, unsaved change = blue);
   today only the single yellow highlight exists. Save → `SP_PADM_SAVE_SELECTION_SET`.
5. **Calculated Grids**, in this exact order — confirmed by a direct read of the real
   `Segment.xlsx` section headers, row by row (not a guess):
   `CDE Volume → Post-EMS Volume (Universe Post-EMS Rates) → Selected Quantity (Selections) →
   Effective NRR (Net Response Rate) → Unwind Rate → Booked Pre-Unwind → Pre-Unwind CPA →
   Post-Unwind CPA → Marketing Cost → Booking Cost → Expected Unwinds → Booked Post-Unwind`
   **Layout**: the first 6 render 3-per-row (2 rows of 3), the remaining 6 render 2-per-row (3
   rows of 2) — this specific grouping is a UI-layout choice, not a literal mapping of the real
   sheet's parallel multi-segment comparison columns (which is a different structure entirely);
   confirm with the user if the row-grouping itself (not just the metric order) needs to match
   something more specific.
   A caption under Booked Post-Unwind shows the aggregate unwind rate (total unwinds / total
   pre-unwind boards) — per the handwritten scope's explicit instruction to show it there.

### 3.7 Signature Page 2 — workflow + final sign-off
- Campaign banner + a 4-step workflow stepper (`DRAFT → READY_FOR_REVIEW → COMPLETED →
  REOPENED`), current step highlighted, done steps checked.
- Actions: **Run calculation** (`SP_PADM_RUN_CALCULATION`) → **Generate Signature Page 2
  snapshot** (`SP_PADM_GENERATE_SIGNATURE_PAGE_2`, needs a completed run) → **Submit for
  review**/**Approve-Complete**/**Reopen** (`SP_PADM_TRANSITION_CAMPAIGN`, 4 params including a
  free-text comment).
- While not `COMPLETED`: live preview (`VW_PADM_SIGNATURE_PAGE_LIVE`), same column order as §3.2.
- Once `COMPLETED`: version selector over `DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT`, immutable, locked
  — "generated at approval" chip, same field order (confirmed already correct in the original
  bare-INSERT template this build wrapped in a procedure).

---

## 4. Core Formulas

```
Post-EMS Volume        = CDE Volume × (1 − EMS Reduction Rate)
Selected Quantity       = ROUND(Post-EMS Volume × Selection %)
Effective NRR           = Base NRR × (1 + Rate Adjustment) × (1 − Seasonality Reduction)
Booked (Pre-Unwind)     = Selected Quantity × Effective NRR
Marketing Expense       = Selected Quantity × CPP           (or Universe Volume × CPP, Universe side)
Booking Cost            = Boards × Unit Cost
Expected Unwinds        = Booked (Pre-Unwind) × (Historical Unwind Rate × (1 + Unwind Rate Adjustment))
Booked (Post-Unwind)    = Booked (Pre-Unwind) − Expected Unwinds
Pre-Unwind CPA          = Marketing Expense / Booked (Pre-Unwind)
Post-Unwind CPA         = (Marketing Expense + Booking Cost) / Booked (Post-Unwind)
Marketing + Booking     = Marketing Expense + Booking Cost
```

Each of Universe (pre-selection) and Selected (post-selection) is computed in parallel; the
dashboard displays the Selected side throughout (the Universe side exists in the view for
comparison/audit, not surfaced as its own grid).

---

## 5. Workflow State Machine

```
DISCOVERED ──(SP_PADM_ACTIVATE_CAMPAIGN)──▶ DRAFT
REOPENED   ──(SP_PADM_ACTIVATE_CAMPAIGN)──▶ DRAFT
DRAFT             ──(SP_PADM_TRANSITION_CAMPAIGN)──▶ READY_FOR_REVIEW
READY_FOR_REVIEW  ──(SP_PADM_TRANSITION_CAMPAIGN)──▶ COMPLETED
READY_FOR_REVIEW  ──(SP_PADM_TRANSITION_CAMPAIGN)──▶ DRAFT        (send back)
COMPLETED         ──(SP_PADM_TRANSITION_CAMPAIGN)──▶ REOPENED
```
After `COMPLETED`, nothing downstream is edited directly — `REOPENED` creates a new working
version (`SP_PADM_TRANSITION_CAMPAIGN` increments `CURRENT_WORKING_VERSION_NUMBER`); the
procedure enforces the allowed path only, readiness checks before `READY_FOR_REVIEW` are the
application's responsibility, not enforced in SQL.

---

## 6. Known Open Items (as of this spec's writing)

1. `SP_PADM_ACTIVATE_CDE_VERSION`'s signature is unconfirmed — verify via `SHOW
   PROCEDURES`/`GET_DDL` before trusting the CDE-upload path end-to-end.
2. `discover_campaigns`'s one unverified column mapping: the candidate view's
   `SOURCE_CAMPAIGN_IDENTIFICATION_CODES` (plural) carried straight into
   `DM_PADM_CAMPAIGN_1.SOURCE_CAMPAIGN_IDENTIFICATION_CODE` (singular) — no exact name match
   exists; watch the first real discovery run for garbled values here.
3. Selection % grid's 3-tier color coding (yellow/green/blue) from PADM_NOTES — not implemented.
4. Segment Viewer's "first 6 / rest" grid-row grouping is a UI choice, not confirmed against the
   real sheet's parallel-segment column structure (see §3.6).
5. `Underwriting Flag`/`Prospect Type` derivation logic — unconfirmed whether already applied
   upstream in the ACM source table.

---

## 7. Deploying

1. Run `sql/30_wire_credit_bureau_fields.sql`, confirm its post-deployment check shows
   `FOUND = 1` for all 4 columns.
2. Run `sql/20_additional_procedures_and_views.sql`, confirm `FOUND = 1` for all 5 objects.
3. Deploy `app/` + `streamlit_app.py` + `.streamlit/config.toml` as a classic warehouse-backed
   Streamlit-in-Snowflake app (no compute pool, no `requirements.txt` needed — `streamlit`,
   `snowflake-snowpark-python`, and `pandas` are already provided by the runtime).
4. Test end to end: Campaign Creation (discover/activate) → Create Segment → Campaign
   Assumptions → Segment Viewer (assumptions → CDE → selections → all 12 grids) → Signature
   Page → Signature Page 2 (run calculation → generate snapshot → submit → approve).
