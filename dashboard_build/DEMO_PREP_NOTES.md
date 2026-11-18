# PADM Demo Prep — Everything You Need to Know

## 1. The 30-second pitch

PADM replaces a manual Excel "Signature Page" sign-off process for CreditOne Bank's monthly
direct-mail credit-card campaigns. Each month, Risk/RTM has to review and approve every
campaign's segments, volumes, and economics (response rate, cost, unwind risk) before it mails.
Today that's done by hand in Excel. PADM automates it end-to-end in Snowflake: pull the campaign
from the upstream ACM system, segment it, set assumptions, let the user pick mail-selection
percentages, calculate the economics, and produce an auditable, versioned sign-off page.

## 2. End-to-end data flow (say this out loud, in order)

1. **ACM** (an upstream campaign system) publishes campaign/offer data into
   `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS` / `T_ACM_PROGRAMS`.
2. **Campaign Creation** tab discovers a candidate campaign for a given month + type
   (MAIN/REMAIL) and lets the user activate it — this snapshots the ACM data into PADM's own
   tables (`DM_PADM_CAMPAIGN_OFFER`, `DM_PADM_CAMPAIGN_OFFER_PROFILE`) so later ACM changes don't
   silently move the ground under an in-flight campaign.
3. **Signature Page** (tab 1) shows that ACM-sourced data as a read-only shell, before segments exist.
4. **Create Segment** groups offers into governed, reusable Segments (bureau, score band, product,
   prospect type) and allocates offers to them.
5. **Campaign Assumptions** sets the economic knobs: CPP, Unit Cost, Rate Adjustment, Seasonality
   Reduction, Unwind Rate Adjustment — at campaign level, with optional per-segment overrides.
6. **CDE** (credit-bureau mail universe, scored by Vantage/CRS and tiered 1–20) gets loaded and
   "activated" per campaign+segment — this is the raw mailable volume before any selection.
7. **Population Description** groups allocations by offer+score and lets the user label each
   group for the sign-off document.
8. **Segment Viewer** is the Tier × Times-Mailed selection grid — the user picks what % of each
   cell actually gets mailed (pre-populated from last month's saved selection). Saving snapshots
   it immutably for audit.
9. **Run calculation** replays the whole formula chain (below) and snapshots it.
10. **Signature Page 2** is the final artifact: a live preview until submission, then an immutable
    snapshot once the campaign is submitted/approved.

## 3. Core formulas — know these cold, they get asked

```
Post-EMS Volume        = CDE_VOLUME × (1 − EMS_REDUCTION_RATE)
Selected Quantity       = ROUND(Post-EMS Volume × Selection%)
Base NRR                = Boarded Count / Mail Quantity        (from historical "Vivian" data)
Effective NRR           = Base NRR × (1 + Rate Adjustment) × (1 − Seasonality Reduction)
Effective Unwind Rate   = Historical Unwind Rate × (1 + Unwind Rate Adjustment)
Booked Pre-Unwind       = Volume × Effective NRR                (computed for Universe AND Selected volume)
Booked Post-Unwind      = Booked Pre-Unwind × (1 − Effective Unwind Rate)
Marketing Cost          = Volume × CPP
Booking Cost            = Volume × Effective NRR × Unit Cost
Expected Unwinds        = Volume × Effective NRR × Effective Unwind Rate
Pre-Unwind CPA          = Marketing Cost / Booked Pre-Unwind
Post-Unwind CPA         = (Marketing Cost + Booking Cost) / Booked Post-Unwind
```

**Fallback logic (3 levels)** when an exact historical/EMS cell is missing:
`exact cell (segment+tier+times-mailed) → segment+campaign-type only → campaign-level default`.
This is implemented as 3 chained `LEFT JOIN`s with `COALESCE` in `VW_PADM_SEGMENT_CALCULATION_CURRENT`.

**"NRR"** = Net Response Rate / booking rate. **"Unwind"** = an account that boarded and later
cancelled/was rescinded. **"EMS"** = suppression applied to the raw mail universe before
selection. **"CDE"** = the raw scored mail universe (Vantage/CRS score band × TRM10 tier ×
times-mailed-in-12-months bucket). **"MKU"** = Marketable Universe (the volume number quoted
before any suppression).

## 4. The schema, condensed (33 tables, 12 views, now 8 stored procs)

Everything lives in **`DB_RISK.RISK_SBX`**, prefix `DM_PADM_*` for tables, `VW_PADM_*` for views.
Every table that holds working state has `IS_CURRENT` (soft versioning) and most have
`ROW_VERSION` (optimistic locking) + mandatory `CHANGE_REASON` on writes — this is the audit
backbone; don't skip populating `CHANGE_REASON` in the demo or writes will fail.

- **Campaign chain**: `CAMPAIGN_1` → `CAMPAIGN_SOURCE_VERSION` → `CAMPAIGN_SOURCE_COMPONENT` →
  `CAMPAIGN_OFFER` → `CAMPAIGN_OFFER_PROFILE`.
- **Segmentation**: `SEGMENT_1` (governed/reusable) ↔ `CAMPAIGN_SEGMENT_1` (campaign working copy)
  ↔ `OFFER_SEGMENT_ALLOCATION` (offer↔segment bridge, carries `POPULATION_DESCRIPTION`).
- **Assumptions**: `CAMPAIGN_ASSUMPTION_VERSION` / `SEGMENT_ASSUMPTION_VERSION`.
- **Mail universe**: `CDE_LOAD_BATCH` / `CDE_DETAIL` → `EMS_RATE_VERSION`.
- **Selection**: `SELECTION_WORKING` (live edits) → `SELECTION_SET` / `SELECTION_SET_CELL`
  (immutable saves) + `SELECTION_EVENT` (audit).
- **History (feeds NRR/Unwind formulas)**: `HISTORY_LOAD_BATCH`, `HISTORY_SEGMENT_KEY`,
  `HISTORY_SEGMENT_MAP`, `NRR_HISTORY_CELL`, `UNWIND_HISTORY_CELL`.
- **Output**: `CALCULATION_RUN` / `CALCULATION_CELL` → `SIGNATURE_PAGE_2_SNAPSHOT`.
- **Reference/audit**: `SCORE_RANGE_RULE_1`, `POPULATION_GROUP_RULE`, `LIFT_TIER_RULE`,
  `CHANGE_EVENT`, `WORKFLOW_EVENT`, `SOURCE_LOAD_BATCH`.

**Stored procs that already existed**: `SP_PADM_ACTIVATE_CAMPAIGN`, `SP_PADM_SAVE_CAMPAIGN_ASSUMPTION`,
`SP_PADM_ACTIVATE_CDE_VERSION`.

**Stored procs/view I added** (in `dashboard_build/sql/20_additional_procedures_and_views.sql`) —
these close real gaps, be ready to explain *why* each exists:
- `SP_PADM_SAVE_SEGMENT_ASSUMPTION` — there was no way to save a segment-level override; only
  campaign-level assumptions had a save procedure.
- `SP_PADM_SAVE_SELECTION_SET` — nothing persisted the Segment Viewer's working grid into an
  immutable, audited selection set; it would have stayed mutable forever.
- `SP_PADM_TRANSITION_CAMPAIGN_STATUS` — enforces the workflow rule from the clarifications doc:
  after approval, nothing is edited directly; Reopen bumps the working version instead.
- `SP_PADM_RUN_CALCULATION` — **this was the biggest gap**: nothing populated
  `DM_PADM_CALCULATION_RUN`/`CALCULATION_CELL` at all, even though Signature Page 2 generation
  requires a `COMPLETED` calculation run to join against. Without this, Signature Page 2 could
  never actually be generated.
- `SP_PADM_GENERATE_SIGNATURE_PAGE_2` — wraps the existing bare `INSERT...SELECT` template with
  version numbering and a guard that blocks it unless the calculation run is `COMPLETED`.
- `VW_PADM_SIGNATURE_PAGE_LIVE` — a pre-snapshot view with the same shape/formulas as the
  snapshot, used for the live Signature Page (tab 1) and the pre-submission preview on
  Signature Page 2.

## 5. Workflow states

`DISCOVERED → DRAFT → READY_FOR_REVIEW → COMPLETED (read-only) → REOPENED → DRAFT`

This 5-state model is what's actually built (confirmed in two independent places — the database
documentation and the live `CHECK` constraint on `DM_PADM_CAMPAIGN_1.STATUS`). The clarifications
doc brainstormed a longer list (`SUBMITTED`/`APPROVED`/`REJECTED`/`SUPERSEDED`) during Q&A, but
that was never adopted into the schema — **if asked why there's no explicit "Approved" status,
say it's folded into `COMPLETED`, and `REJECTED` is just staying in `DRAFT`/being `REOPENED`.**

## 6. What to click through, in demo order

1. **Campaign Creation** tab → pick a Reporting Month + MAIN/REMAIL → "Create Campaign" (this
   calls `SP_PADM_ACTIVATE_CAMPAIGN` under the hood, snapshotting ACM data).
2. **Signature Page** → show the raw ACM-sourced shell (will be mostly empty until segments
   exist — say "this is the starting point, auto-pulled from ACM, nothing hand-typed yet").
3. **Create Segment** → pick unallocated offers, either reuse a governed Segment or create one,
   assign offers to it.
4. **Campaign Assumptions** → set CPP/Unit Cost/Rate Adjustment/Seasonality/Unwind Adjustment at
   campaign level; optionally override at segment level.
5. **Population Description** → group by offer+score, label each group.
6. **Segment Viewer** → pick a segment, show the Selection % grid pre-filled from last month
   (if any prior data exists — if this is the very first campaign, it'll be zeros, say so),
   edit a few cells, hit **Save Selections**, then show the calculated grids underneath
   (Post-EMS Volume → Selected Quantity → NRR → Booked → Costs → CPA) in that exact order,
   explaining "we can't calculate CPA without Marketing Cost and Booked Pre-Unwind first."
7. **Signature Page 2** → **Run calculation** → **Generate Signature Page 2 snapshot** →
   **Submit for review** → **Approve/Complete**. Show that pre-completion it's a live preview
   and post-completion it's an immutable version you can page back through.

## 7. Be upfront about what's new / not yet battle-tested

- **Only the Campaign Creation tab existed before this work.** The other five tabs
  (Signature Page, Create Segment, Campaign Assumptions, Population Description, Segment Viewer,
  Signature Page 2) are a first-pass build against the documented schema — say "built from the
  schema and the sign-off proposal, not yet run against live data" if asked how long it's been
  tested.
- **I don't have a live Snowflake connection in this session** — the SQL and column names were
  reverse-engineered from screenshots of your VS Code project, not from live schema
  introspection. Two spots are explicitly flagged in the SQL/code comments as needing a quick
  verification against your real `source_views.sql`:
  - `CREDIT_BUREAU_MODEL` / `CREDIT_BUREAU_SCORE` column names on the offer-current view.
  - Exact column list on `DM_PADM_HISTORY_SEGMENT_KEY` / `HISTORY_SEGMENT_MAP` (referenced but
    not fully captured).
- **The Excel-style drag-fill on the selection grid isn't replicated** — I used Streamlit's
  native `st.data_editor`, which supports multi-cell copy/paste but not true click-drag.
  Mention this is a known simplification if someone compares it to the Excel workbook.
- **A pre-existing code smell, not something I introduced**: `campaign_setup.py`'s `_discover()`
  function duplicates `campaign_repository.discover_campaign()`'s `MERGE` logic with a plain
  `INSERT` instead — worth consolidating, didn't touch it since it wasn't broken, just redundant.
- **`TIMES_MAILED_0_PERCENTAGE`** was a hardcoded `NULL` placeholder in your existing
  `signature_page_2_snapshot.sql` template — I actually computed it properly (from
  `CAMPAIGN_OFFER_PROFILE`'s times-mailed count columns) in both the new procedure and the new
  live view. Worth mentioning as a fix, not just a gap-fill.

## 8. How to actually deploy before the demo

1. Run `dashboard_build/sql/20_additional_procedures_and_views.sql` against `DB_RISK.RISK_SBX`
   (it's idempotent — safe to re-run). The last `SELECT` in it confirms all 6 new objects exist.
2. Copy `dashboard_build/app/pages/*.py` into your real project's `app/pages/` folder, and
   `dashboard_build/streamlit_app.py` over your existing entry point (it adds the 6 new tabs
   alongside your existing Campaign Creation tab — double check the import path matches your
   actual package layout, e.g. if your pages aren't under `app.pages`, adjust the imports).
3. Create at least one campaign, one segment, and activate a CDE version *before* the demo so
   Segment Viewer and Signature Page 2 have something to show — an empty grid is a weak demo
   moment. Do a full dry run tonight if you can.

## 9. Likely questions and short answers

- **"Why only one page existed before?"** — Campaign Creation (discovery + activation) is the
  natural first slice to build since everything else depends on an activated campaign; the rest
  was scoped but not started.
- **"What's the difference between Signature Page and Signature Page 2?"** — Same shape of data;
  Signature Page (tab 1) is the ACM-sourced starting shell before segmentation, Signature Page 2
  is the fully-calculated, population-labeled version that becomes the immutable approval record.
- **"How do you handle a campaign that gets reopened after approval?"** — `REOPENED` bumps
  `CURRENT_WORKING_VERSION_NUMBER`; nothing from the completed version is mutated, a new working
  version is what gets edited, preserving the original for audit.
- **"What happens if ACM data changes after a campaign is activated?"** — flagged via
  `SOURCE_CHANGE_PENDING_FLAG` on `DM_PADM_CAMPAIGN_1`; the existing `campaign_load_templates.sql`
  MERGE already sets this, including specifically flagging it if it happens to a `COMPLETED`
  campaign — the dashboard doesn't yet surface this flag anywhere, worth calling out as a
  follow-up, not a missed requirement.
