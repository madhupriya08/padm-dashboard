# PADM Source-of-Truth Requirements (extracted 2026-11-19)

Extracted from 5 PDFs the user uploaded as ground truth for the 7 dashboard tabs, read in full. Every
requirement below is tagged with its source file (and page/section where identifiable) so it can be
traced back. Nothing here is guessed -- where a PDF was unclear or cut off, it is flagged in "Open
conflicts / ambiguities" at the end rather than filled in.

## Source documents, in order of authority

1. **`Sgn-off_proposal.pdf`** (23 pages) -- **THE primary requirements document.** A formal sign-off
   proposal with Purpose/Summary/Business Objectives/Scope/Solution Overview/Functional
   Components/Technical Architecture/Data Layer Requirements, then **exact field-by-field
   `Sign-off Field -> Source` mapping tables** for the Signature Page, a Segment Tab
   Working-Version-vs-Final-Version table, Non-Functional Requirements, an **Open Items & Decisions
   Required** table (several items explicitly TBD -- not yet decided by the business, don't invent
   answers for these), and a Create Campaign / Grouping-Segmentation-Creation section. This is the
   single most authoritative, most precise source -- when it conflicts with anything else, trust this.
2. **`PADM_CLARIFICATIONS.pdf`** (8 pages) -- a Q&A/clarifications doc layered on top of an earlier
   proposal. Treat as overriding older docs where it conflicts, but note it uses a **third, different
   status vocabulary** (see conflicts section) -- don't assume it's the final word on status naming.
3. **`Signature_page.pdf`** (4 pages) -- not a requirements doc; a real populated example/export of a
   Signature Page. Valuable as **ground truth for the exact column order and header names** the real
   output must match.
4. **`NRR_all_optimized_-_vivian_s_code.pdf`** (24 pages) + **`NRR-all_optimized_vivians_code_2.pdf`**
   (12 pages) -- **two sequential parts of one continuous legacy SQL ETL script** (not two competing
   revisions -- confirmed by reading both: file 4 starts from `-- Define Campaigns` / mailfile pull and
   runs through Experian + TransUnion campaign/prospect_type/campaign_segment classification into
   `Prior Decline`/`Prior Closure`/`Charge-Off` sections; file 3 picks up mid-stream at `REMAIL TU
   PROSPECTING`/`RETARGETING` and continues into a `main` table that joins applications/accounts, VS4/
   FICO rules, and Experian Prescreen Macro logic). This is the **reference implementation for how
   `prospect_type`, `campaign_segment`, and score-band labels are built** -- it's what Population
   Description / segment classification should match, not itself a tab-by-tab spec.

## Per-tab requirements

### Campaign Creation
- Allow creation of a campaign based on **month and year of `campaign_group_mail_date`**.
  [`Sgn-off_proposal.pdf`, "Create Campaign" section, step 1]
- Always apply these filters when pulling eligible campaign offers (**matches the already-confirmed
  spec 2.3 filters in this repo verbatim** -- cross-confirmed, not new):
  - `SUBSTR(program_code, 1, 1) <> 'W'`
  - `LENGTH(CAMPAIGN_OFFER_RESERVATION_CODE) <= 6`
  - `campaign_type_channel_type = 'Mail'`
  - `campaign_offer_Status = 'Active'`
  [`Sgn-off_proposal.pdf`, "Create Campaign" step 2a-2d]
- "Group offers based on" -- **the grouping key itself was cut off / not captured** in this read; see
  conflicts section.
- Grouping/Segmentation Creation dropdowns, all **sourced from distinct values where
  `campaign_group_mail_date >= today() - 60`**:
  1. Prospect Source Bureau (Experian, TransUnion) -- dropdown
  2. Prospect Type (Prospecting, Retargeting) -- dropdown
  3. Credit Bureau Model -- dropdown
  4. Credit Bureau Score -- dropdown
  5. Annual Fee -- dropdown
  6. CRS Model -- dropdown
  7. CRS Score -- dropdown
  8. Times Mailed -- **multi-select**
  9. Free form field -- flagged in red/as new in the source, i.e. a newer addition the user called out
  [`Sgn-off_proposal.pdf`, "Grouping/Segmentation Creation"]
- Manual inserts: **1. CPP (per campaign date)** -- list is cut off after this one item in the source
  (see conflicts).
- Segment Creation: "Strategy users shall be able to create segments using configurable criteria
  including:" Bureau Score Type, Bureau Score Range, Source, Annual Fee, Network, MLA, Times Mailed
  (TM), Risk Score Type, Response Model Type. [`Sgn-off_proposal.pdf`, p.3-4, "Segment Creation"]

### Signature Page
Exact `Sign-off Field -> Source` mapping table (the authoritative field list and lineage --
**[`Sgn-off_proposal.pdf`], "Signature Page" / "(Existing Fields)"**):

| Field | Source |
|---|---|
| Segment Description | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_DESCRIPTION` |
| AF (Annual Fee) | `CSTONE_BIZ.REFERENCE.T_ACM_PROGRAMS.ANNUAL_FEE_YR1` / `ANNUAL_FEE_YR2` |
| Test Type | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_CONTROL_TEST_DESCRIPTION` |
| Network | `CSTONE_BIZ.REFERENCE.T_ACM_PROGRAMS.NETWORK` |
| Credit Bureau Model | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.PROSPECT_CREDIT_BUREAU_MODEL` |
| Credit Bureau Score | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.PROSPECT_CREDIT_BUREAU_SCORE` |
| CRS Model | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.PROSPECT_CRS_MODEL` |
| CRS Score | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.PROSPECT_CRS_SCORE` |
| NRM | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.NET_RESPONSE_MODEL_CODE` |
| Quantity | MKU, 105, `CSTONE_BIZ.REFERENCE.T_EXPERIAN_MAILFILE`, `CSTONE_BIZ.REFERENCE.T_TRANSUNION_MAILFILE` |
| NBR | ASSUMPTIONS (manual/assumption input) |
| Boards | Calculation: `QUANTITY x NBR` |
| CPP | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.COST_PER_PIECE` |
| Marketing Expense | Calculation: `Quantity x CPP` |
| Unwind Rate | ASSUMPTIONS |
| Pre Unwind CPA | Calculation: `Marketing Expense / Boards` |
| Post Unwind CPA | Calculation: `(Marketing + Booking Cost) / Post Unwind Boards` |
| PROMO | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.RESERVATION_CODE_RISK` |
| IVR | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_APPROVAL_CODE` |
| Underwriting Flag | "Underwriting_Flag_Lookup" (a lookup, not inline -- exact source TBD, matches this repo's existing `-- lookup source TBD (spec 10)` note) |
| Prospect Type | `WHEN CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_SEGMENT_NAME IN (PQ ABANDON, PQ DECLINE, PRIOR CHARGE OFF, PRIOR CLOSURE, PRIOR DECLINE, REMARKET, TU PRIOR CHARGE OFF, TU PRIOR CLOSURE, TU PRIOR DECLINE) THEN 'RETARGETING' ELSE 'PROSPECTING'` |
| Times Mailed 0% | Calculation: `quantity TM0 / total quantity` |
| Times Mailed 1%-9+% | Calculation: `quantity TM{n} / total quantity` (same pattern for each bucket 1 through 9+) |
| TIERS | `MKU/105/MAILFILES (Min tier || '-' || max tier)` |
| Print Vendor | `CSTONE_BIZ.REFERENCE.T_ACM_CAMPAIGN_OFFERS.PRINT_VENDOR_ID` |
| Post Unwind Boards | Calculation: `Boards x (1 - Unwind Rate)` |
| Marketing + Booking Costs | Calculation: `Marketing Expense + (Boards x Unit Cost)` |
| Unit Cost | **Manual Input** |
| Campaign Name and Date (Header) | (source not given in table -- header-level, not a row field) |

"Additions -- table only, not to be displayed" (fields computed/stored but not shown on the page itself):

| Field | Source |
|---|---|
| Campaign Year | Derived from `CAMPAIGN_OFFERS.CAMPAIGN_GROUP_MAIL_DATE` |
| Campaign Month | Derived from `CAMPAIGN_OFFERS.CAMPAIGN_GROUP_MAIL_DATE` |
| Campaign Month Sequence | Derived from `CAMPAIGN_OFFERS.CAMPAIGN_GROUP_MAIL_DATE` |
| Campaign Type | **(Primary/Remail)** -- flagged red/new; derivation logic itself is an open TBD item (see below) |
| Mail Date | Derived from `CAMPAIGN_OFFERS.CAMPAIGN_GROUP_MAIL_DATE` |
| ACM Segment | `CAMPAIGN_OFFERS.CAMPAIGN_OFFER_SEGMENT_NAME` |
| Population Description | **Subtotal groups** -- flagged red/new |
| Test Pairings | `CAMPAIGN_OFFERS.CAMPAIGN_OFFER_CONTROL_TEST_NAME` |

Unwind calculation detail, Working Version vs Final Version (note a real difference between the two!):

| Field | Working Version | Final Version |
|---|---|---|
| Unwinds 1 | `Booked pre-unwind 1 * unwind rate * (1+unwind rate adjustment)` | No changes from WV |
| Unwinds 2 | `Booked pre-unwind 2 * unwind rate * (1+unwind rate adjustment)` | `Booked pre-unwind 2 * unwind rate * (1+unwind rate adjustment)` -- same formula restated, not actually different despite being in the "differs" column |
| Booked - Post Unwind 1 | `'Booked - Pre Unwind 1' - unwinds 1` | No changes from WV |
| Booked - Post Unwind 2 | `'Booked - Pre Unwind 2' - unwinds 2` | `'Booked - Pre Unwind 2' - unwinds 2` |
| CPP | Manual input in signature page | No changes from WV |
| Unit cost | Manual input in segment tab | No changes from WV |
| Seasonality Adjustment | Manual input in segment tab | No changes from WV |

[all of the above: `Sgn-off_proposal.pdf`, "Signature Page" section tables]

Ground-truth column order/headers from a real populated export (**[`Signature_page.pdf`]**, all 4
pages): Segment Description, AF, Test Type, Network, Credit Bureau Model, Credit Bureau Score, CRS
Model, CRS Score, NRM, Quantity, NBR, Boards, CPP, Marketing Expense, Unwind Rate, Pre Unwind CPA,
Post Unwind CPA, PROMO, IVR, Underwriting Flag, Prospect Type, Times Mailed 0%, TIERS, PRINT VENDOR,
Post Unwind Boards, Marketing + Booking Costs. **This matches the field list/order above closely --
use this as the exact column sequence for the real page.**

### Signature Page 2
- Generate Signature Pages automatically.
- Allow authorized users to update applicable fields.
- **Dynamically refresh calculations when assumptions or selections change.**
- Summarize Signature Page 2 information (on Signature Page 1, see below).
[`Sgn-off_proposal.pdf`, "Functional Components -> Signature Page 2"]

### (Overview / landing -- called "Signature Page 1" in this doc, maps to this app's Campaign landing/header)
- Summarize Signature Page 2 information.
- Generate executive approval documentation.
- Allow updates before finalization.
- Support PDF and Excel export functionality.
[`Sgn-off_proposal.pdf`, "Functional Components -> Signature Page 1"]

### Create Segment
- "Strategy users shall be able to create segments using configurable criteria including:" Bureau
  Score Type, Bureau Score Range, Source, Annual Fee, Network, **MLA**, Times Mailed (TM), Risk Score
  Type, Response Model Type. [`Sgn-off_proposal.pdf`, p.3-4]
  - Note: this repo's HANDOFF.md already has an open item "MLA field removal in Create Segment" from
    the mobile debugging session -- **this directly conflicts**: the sign-off proposal explicitly
    lists MLA as a required segment-creation criterion, so removing it needs to be re-confirmed with
    the user rather than assumed correct. Flagged in conflicts below.

### Campaign Assumptions
- Segment Management: display segment-level assumptions; support **Tier x Times Mailed** selections;
  recalculate campaign impacts dynamically; **preserve and prepopulate previously selected values for
  existing segments**. [`Sgn-off_proposal.pdf`, "Functional Components -> Segment Management"]
- Manual inserts include at least: CPP (per campaign date), Unit Cost (manual input in segment tab),
  Seasonality Adjustment (manual input in segment tab).
- Segment Tab "Selections %  - NEW" (flagged red/new in the source): **pre-populated with prior
  month's selection; an additional table that allows users to select a percentage for each cell.**
  This directly corresponds to the open "Selection % no-prior-month check" item already tracked in
  HANDOFF.md -- the proposal confirms prior-month prepopulation IS a real, explicit requirement, not
  a guess.
- Net Response Rate 1: **"From Vivian's script"** (i.e. the NRR_all_optimized files above).
- Net Response Rate 2: `Net Response Rate 1 x seasonality adjustment`.

### Population Description
- Segment Tab fields, Working Version source:
  - MKU Volume: Excel report at `\\fnbmcorp\share\Risk\Acquisitions\Current
    Projects\Pre-Approved\Campaigns\2026\0426\Orion\Marketable Universe Counts` -- **Final Version: no
    changes from WV** (i.e. this manual Excel-report dependency is NOT eliminated by the new app,
    at least not yet decided otherwise).
  - Universe Post-EMS Rates: `MKU Volume x EMS adjustment -- for POC, apply blanket 5%` -- matches
    this repo's existing POC 5% EMS fallback exactly. No changes from WV.
  - Selections: `Selection % x universe post-EMS` (Working Version) vs. **Final Version: from Mail
    file (`t_experian_mailfile` or `t_transunion_mailfile`)** -- a real, explicit difference between
    the two versions, not a typo.
- Population description logic should be grouped/labeled by the real `campaign_segment` /
  `prospect_type` classification logic in the Vivian's-code NRR files (score bands like VS550-600,
  VS601-639, VS640-700, VS701-730, 731+, per bureau and prospect_type: Experian Vantage, Experian
  Vantage MLA, Nascar, VS4, PDCL/PCL/PCO/ABDN [prior decline/closure/charge-off/abandon], TransUnion
  equivalents, Emerging Consumer) -- **not built with ad hoc Python string logic**, matching this
  repo's existing spec requirement.

### Segment Viewer
- Support Tier x Times Mailed selections (same requirement as Campaign Assumptions' Segment
  Management bullet above -- these two tabs share this requirement in the source doc).
- "Selections % - NEW" prior-month prepopulation + per-cell percentage table (see Campaign
  Assumptions above -- same feature, shared across both tabs per the proposal's wording).

## Technical / architectural requirements (apply across all tabs)
- **Two-schema architecture**: Working Schema (active business operations, read/write access, user
  updates, assumption maintenance, campaign preparation) and Archive Schema (finalized versions,
  read-only access, historical retention, audit and compliance support).
  [`Sgn-off_proposal.pdf`, "Technical Architecture"]
- Audit Trail: record changes, capture timestamp of changes, capture user identification, track
  before/after values where applicable, maintain historical records for review.
- Non-Functional Requirements:
  - Performance: campaign generation within acceptable business SLA targets (**exact SLA = open TBD
    item**); recalculations should execute **in near real-time** following user updates.
  - Security: enforce role-based access controls; maintain audit logging for all updates; restrict
    archived data to read-only access.
  - Maintainability: support future expansion of assumptions and segment attributes; minimize
    hard-coded business rules.
  - Usability: intuitive multi-tab navigation; consistent formatting across generated outputs;
    executive-friendly presentation of Signature Pages.
- Data Layer Requirements (data sources the app integrates with): Assumptions (campaign planning
  assumptions), MKU (population and segmentation volumes), Mail Files (mailing quantities and tier
  info), ACM Offers (offer attributes and campaign configuration), 105 Reports (campaign population
  metrics), Audit Trail (change tracking), Signature Page Calculations (aggregations and derived
  metrics).

## Open Items & Decisions Required (explicitly marked TBD/undecided in the source -- do not guess these)
From `Sgn-off_proposal.pdf`'s own "Open Items & Decisions Required" table:
- Finance Extract requirements -- **TBD**
- Campaign Type derivation logic -- **TBD** (directly relevant: this repo doesn't yet know exactly how
  `CAMPAIGN_TYPE` = Primary/Remail is derived)
- Segmentation rules -- **TBD**
- Underwriting Flag lookup source -- **TBD** (matches this repo's existing `-- lookup source TBD
  (spec 10)` note -- independently confirmed as genuinely undecided, not just missing from our
  reconstruction)
- Final role matrix -- **TBD**
- Performance SLAs -- **TBD**
- Change-highlighting methodology -- **TBD**

## Additional source: Unwinds_optimized files (read 2026-11-19)

**`Unwinds_optimized-_vivians_code.pdf`** (24 pages) + **`Unwinds_optimized-_vivians_code_continuation.pdf`**
(24 pages) -- one continuous legacy SQL script (not two revisions), a **different pipeline from the
NRR_all_optimized files** above. Where NRR files build `prospect_type`/`campaign_segment` labels for
*pre-mail* segmentation, these Unwinds files are a **post-booking unwind-rate validation/ETL script**:
pull mailfiles -> classify `prospect_type`/`campaign_segment`/`score_range` (same VS3/VS4 CASE WHEN
pattern as the NRR files, extended with `ASSUMPTION_STATUS`/campaign-code-exclusion logic and Experian/
TransUnion Prescreen Macro back-calculation) -> join to applications/boards (`FACT_APPLICATION`,
`DIM_APPLICATION_STATUS`) -> join to `FACT_CARD_MONTHLY` to pull accounts that boarded and later
unwound (`UNWIND_INDICATOR = 1`, specific `STATUS_REASON_CODE`s) -> produce `unwinds_validation` /
`unwinds_output` tables (one row per campaign/segment/tier with boards, unwinds, association,
score range). This is the reference implementation for how **historical unwind rates get computed
per tier**, not a dashboard spec -- relevant background for Campaign Assumptions' Unwind Rate
assumption and Segment Viewer's Unwind Rate grid, but not itself a UI requirement.

## LIFT score type search result

**Searched all 4 PDFs for "LIFT"/"Lift". Found real content, but it does NOT support treating LIFT
as a peer "Bureau Score Type" alongside VS3/VS4 the way DM_PADM_SCORE_RANGE_RULE_1 currently models
VS3/VS4 (symmetric score bands like 300-499/500-529/.../731+). Concretely:**

1. `e.LIFT_SCORE` is a real raw column pulled from `CSTONE_BIZ.REFERENCE.T_EXPERIAN_MAILFILE`
   (TransUnion's mailfile has no equivalent -- `NULL AS LIFT_SCORE` in that branch). It sits
   alongside `RISK_SCORE_TYPE`/`RISK_SCORE` (PRE_SCREEN), not alongside `PRESCREEN_VANTAGE_V3`/`V4`.
2. **LIFT maps to the existing `Emerging Consumer` prospect type, not a new one.** A commented-out
   (confirmed unused -- "-- unnecessary as it is not part of final output") branch in the
   continuation file reads: `CASE WHEN campaign_segment = 'Emerging Consumer' THEN 'LIFT' ELSE
   response_model_type END` -- i.e. the script's own author used "LIFT" and "Emerging Consumer"
   interchangeably as labels for the same population. `Emerging Consumer` is already a real,
   confirmed `prospect_type` value in the NRR files (`WHEN e.campaign_source = 'E' THEN 'Emerging
   Consumer'`).
3. **A real, explicit business rule involving LIFT_SCORE exists**: `-- Exclude Emerging consumers
   with a liftscore of < 566` -> `CASE WHEN CAMPAIGN_SEGMENT = 'Emerging Consumer' AND LIFT_SCORE <
   566 THEN 'EXCLUDE' ELSE NULL END AS ASSUMPTION_STATUS_EC`.
4. **LIFT_SCORE does get bucketed, but into `RESPONSE_MODEL_TIER` boundary values for post-booking
   unwind-rate analysis**, not into VS3/VS4-style score-range codes. The exact, real tier boundaries
   (`a.LIFT_SCORE` -> `RESPONSE_MODEL_TIER_recalc`, Unwinds file, continuation pages ~17-18):
   `566` (566-585), `586` (586-601), `602` (=602), `603` (603-610), `611` (611-620), `621`
   (621-630), `631` (631-640), `641` (641-651), `652` (652-662), `663` (663-676), `677` (677-692),
   `693` (693-702), `703` (703-708), `709` (709-729), `730` (730-806). These are fine-grained
   ~10-20-point tier cutpoints, not the ~30-70-point bands VS3/VS4 use.

**Recommendation (for the user, not auto-applied)**: don't manually insert `DM_PADM_SCORE_RANGE_RULE_1`
rows for `BUREAU_SCORE_TYPE = 'LIFT'` shaped like the existing VS3/VS4 rows (e.g. a guessed "LIFT
550-600") -- that would misrepresent what LIFT actually is in the real system. If "LIFT" is meant to
be selectable as a Bureau Score Type in Create Segment, the real semantics confirmed here are: LIFT
*is* the Emerging Consumer population, scored via `LIFT_SCORE` (not Vantage V3/V4), with its own
566-806 exclude-below-566 range and the 15 tier cutpoints above -- a decision on how (or whether) to
expose that in Create Segment's dropdown is the user's call, not something to guess into the schema.

## Open conflicts / ambiguities

1. **Status vocabulary, a THIRD variant found.** `PADM_CLARIFICATIONS.pdf` uses yet another status
   set distinct from both the "real" one (`NEW/DRAFT/IN_PROGRESS/PENDING_APPROVAL/APPROVED/REJECTED`,
   confirmed directly from `padm/tabs/campaign_creation.py`) and the "old DDL" one
   (`DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED/REOPENED`, confirmed live in
   `SP_PADM_ACTIVATE_CAMPAIGN`). Treat the clarifications doc's vocabulary as a draft/proposal
   iteration, not current truth -- the two already-confirmed vocabularies above remain authoritative.
2. **MLA in Create Segment**: the sign-off proposal explicitly lists MLA as a configurable
   segment-creation criterion, but HANDOFF.md (from the mobile debugging session) has an open item
   about *removing* MLA from Create Segment. This is a direct conflict -- needs the user's
   confirmation on which is current intent before any code change, not an assumption either way.
3. **"Group offers based on" (Create Campaign, step 3)**: the grouping key was not captured in this
   read -- either cut off in the source photo/scan or genuinely incomplete in the document itself.
   Don't guess the grouping key; ask the user or re-check the source.
4. **"Manual inserts" list (Create Campaign)**: only one item ("1. CPP (per campaign date)") was
   visible before the document's content ran out at page 23 -- unclear whether this list is genuinely
   a single item or was cut off. Flag as possibly incomplete rather than assuming CPP is the only
   manual insert.
5. **Unwinds 2 / Booked-Post-Unwind-2 Working-vs-Final table**: the "Final Version" column restates
   the exact same formula as "Working Version" rather than showing an actual difference, unlike the
   Selections row (which does show a real WV-vs-Final difference). This might mean these two rows
   genuinely don't change between versions (consistent with how most other rows in the same table say
   "No changes from WV" instead) -- i.e. not a real conflict, just an inconsistent way of writing "no
   change." Noting it in case it turns out to matter.
6. **Underwriting Flag**: proposal says source is `"Underwriting_Flag_Lookup"` and separately lists it
   as an open TBD ("Underwriting Flag lookup source -- TBD") -- i.e. the proposal itself acknowledges
   the lookup exists conceptually but its actual source/table is undecided. Don't invent a lookup
   table/view name for this.
7. **NRR/Vivian's-code files are reference ETL, not a tab spec.** They define exactly how
   `prospect_type`/`campaign_segment` labels and score-band buckets are built, but say nothing
   directly about Streamlit UI layout, so they inform Population Description's labeling logic and
   Campaign Assumptions' "From Vivian's script" NRR formula, but shouldn't be read as dashboard
   field-order requirements the way the Sgn-off proposal's tables are.
