# PADM Dashboard - Build Specification (transcribed from user's real PADM DASHBOARD SPEC.md)

Goal: Build the complete, working PADM sign-off dashboard as a Streamlit in Snowflake app with
7 tabs, backed by Snowflake tables, views and stored procedures. Replace the manual Excel
sign-off process with a versioned, auditable, multi-tab application.

> **Revised 2026-11-19** against the real, running app (not just the original build intent).
> Sections below marked **[UPDATED]** reflect decisions made and code shipped this session;
> the original wording is kept struck through context where it helps explain what changed and
> why. Treat this file, not the untouched original, as current truth going forward.

Sources of truth (priority order): 1. Handwritten scope notes. 2. Requirement notepad. 3. PADM
Sign-off Proposal. Where spec says VERIFY, do not guess -- query the database and confirm.

## 0. Rules for the Agent
1. Introspect before you create: SHOW TABLES/VIEWS/PROCEDURES in DB_RISK.RISK_SBX, DESCRIBE
   TABLE on every DM_PADM_* object. Reuse existing objects, never duplicate under a new name.
2. Document where each value is stored/comes from -> docs/DATA_LINEAGE.md before new code.
3. Naming: tables DM_PADM_*, views VW_PADM_*, procedures SP_PADM_*. Schema DB_RISK.RISK_SBX.
4. Every table holding working state has: IS_CURRENT, ROW_VERSION, CHANGE_REASON (mandatory on
   writes), CREATED_BY/CREATED_TS/UPDATED_BY/UPDATED_TS.
5. Never overwrite history -- every save inserts a new version and flips IS_CURRENT.
6. Keep tables clean and generic -- same tables serve every future campaign/segment. No
   hardcoded campaign/segment/score-band/tier anywhere.
7. Loosely coupled code: one Python module per tab, a shared repository/data-access layer, a
   shared formula module. New assumptions/segment attributes addable without rewriting tabs.
8. Minimize hardcoded business rules: score ranges, population group labels, prospect-type
   lists, filters all live in reference tables.
9. **Approved campaigns are READ-ONLY.** Every write procedure must reject edits when campaign
   status is APPROVED.

### 0.1 Existing objects to VERIFY and reuse
| Area | Objects |
|---|---|
| Campaign | DM_PADM_CAMPAIGN_1, DM_PADM_CAMPAIGN_SOURCE_VERSION, DM_PADM_CAMPAIGN_SOURCE_COMPONENT, DM_PADM_CAMPAIGN_OFFER, DM_PADM_CAMPAIGN_OFFER_PROFILE |
| Segmentation | DM_PADM_SEGMENT_1, DM_PADM_CAMPAIGN_SEGMENT_1, DM_PADM_OFFER_SEGMENT_ALLOCATION |
| Assumptions | DM_PADM_CAMPAIGN_ASSUMPTION_VERSION, DM_PADM_SEGMENT_ASSUMPTION_VERSION |
| Mail universe | DM_PADM_CDE_LOAD_BATCH, DM_PADM_CDE_DETAIL, DM_PADM_EMS_RATE_VERSION |
| Selection | DM_PADM_SELECTION_WORKING, DM_PADM_SELECTION_SET, DM_PADM_SELECTION_SET_CELL, DM_PADM_SELECTION_EVENT |
| History | DM_PADM_HISTORY_LOAD_BATCH, DM_PADM_HISTORY_SEGMENT_KEY, DM_PADM_HISTORY_SEGMENT_MAP, DM_PADM_NRR_HISTORY_CELL, DM_PADM_UNWIND_HISTORY_CELL |
| Output | DM_PADM_CALCULATION_RUN, DM_PADM_CALCULATION_CELL, DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT |
| Reference/audit | DM_PADM_SCORE_RANGE_RULE_1, DM_PADM_POPULATION_GROUP_RULE, DM_PADM_LIFT_TIER_RULE, DM_PADM_CHANGE_EVENT, DM_PADM_WORKFLOW_EVENT, DM_PADM_SOURCE_LOAD_BATCH |
| Views | VW_PADM_SEGMENT_CALCULATION_CURRENT, VW_PADM_SIGNATURE_PAGE_LIVE |
| Procedures | SP_PADM_ACTIVATE_CAMPAIGN, SP_PADM_SAVE_CAMPAIGN_ASSUMPTION, SP_PADM_SAVE_SEGMENT_ASSUMPTION, SP_PADM_ACTIVATE_CDE_VERSION, SP_PADM_SAVE_SELECTION_SET, **SP_PADM_TRANSITION_CAMPAIGN** (CONFIRMED real name -- 4 params incl. comment; ~~SP_PADM_TRANSITION_CAMPAIGN_STATUS~~ was an earlier invented duplicate, removed), SP_PADM_RUN_CALCULATION, SP_PADM_GENERATE_SIGNATURE_PAGE_2 |
| **[NEW, confirmed real]** | VW_PADM_SEGMENT_SOURCE_CANDIDATE (rebuilt 2026-11-19 off T_EXPERIAN_MAILFILE/T_TRANSUNION_MAILFILE -- see 4.5), DM_PADM_CAMPAIGN_SEGMENT_1, DM_PADM_OFFER_SEGMENT_ALLOCATION (many-to-many as of 2026-11-19) |

VERIFY specifically: column names PROSPECT_CREDIT_BUREAU_MODEL/SCORE on offer source/current
view; full column lists of DM_PADM_HISTORY_SEGMENT_KEY and DM_PADM_HISTORY_SEGMENT_MAP.

### 0.2 Source (ACM) objects -- all in CSTONE_BIZ.REFERENCE
T_ACM_CAMPAIGN_OFFERS, T_ACM_PROGRAMS, T_EXPERIAN_MAILFILE, T_TRANSUNION_MAILFILE.

## 1. Application Structure

### 1.1 Tabs (exact order)
1 Campaign Creation -- create/discover/activate a campaign, manage status
2 Signature Page -- ACM-only, read-only starting shell for the campaign
3 Create Segment -- build governed segments, allocate offers
4 Campaign Assumptions -- campaign + segment-level assumptions, versioned
5 Population Description -- group segments, assign offers, show subtotals
6 Segment Viewer -- Excel-style Tier x Times Mailed selection/calculation grids
7 Signature Page 2 -- Signature Page + calculated values + population description, then approval

### 1.2 Navigation rules
- Tabs 2-7 disabled until a campaign is selected/created in Tab 1.
- Selected campaign held in st.session_state["campaign_id"], shared by all tabs.
- Header bar on EVERY tab shows: Campaign Name, Mail Date, Campaign Type, Status, Working
  Version number.
- When status is APPROVED, every input widget on every tab is disabled, banner "Approved -- read
  only".

### 1.3 End-to-end flow
Campaign Creation -> Signature Page -> Create Segment -> Campaign Assumptions -> Population
Description -> Segment Viewer -> Signature Page 2 -> Approval -> Actuals

## 2. Tab 1 - Campaign Creation

### 2.1 Purpose
Create a campaign from ACM data, snapshot that data into PADM tables (so later ACM changes
don't silently change an in-flight campaign), manage status.

### 2.2 Inputs
| Control | Type | Rule |
|---|---|---|
| Campaign Month/Year | Month+year picker | Based on month/year of CAMPAIGN_GROUP_MAIL_DATE |
| Campaign Type | Dropdown: PRIMARY (MAIN), REMAIL | Derivation TBD. Manual selection for now, store it. |
| Discover button | Button | Lists candidate ACM offers for chosen month+type |
| Create/Activate Campaign button | Button | Calls SP_PADM_ACTIVATE_CAMPAIGN |
| Existing campaigns list | Table + select | Selecting a row sets the active campaign for all tabs |

### 2.3 Mandatory source filters (always applied)
```sql
SUBSTR(program_code, 1, 1) <> 'W'
AND LENGTH(CAMPAIGN_OFFER_RESERVATION_CODE) <= 6
AND campaign_type_channel_type = 'Mail'
AND campaign_offer_status = 'Active'
```

### 2.4 Activation behaviour
1. Discover candidate offers using filters above.
2. Snapshot ACM offer data into PADM's campaign/offer tables, with a source version + load batch.
3. Join as ACM LEFT JOIN campaign, so every ACM offer appears even before PADM data exists.
4. Write a WORKFLOW_EVENT row.
5. Document: what "Discover New Campaigns" does + full activation process -> docs/CAMPAIGN_ACTIVATION.md
6. **Known cleanup**: campaign_setup.py's `_discover()` duplicates the MERGE in
   campaign_repository.discover_campaign() but uses a plain INSERT. Consolidate both into the
   single MERGE path.

### 2.5 Campaign status workflow
```
NEW -> DRAFT -> IN_PROGRESS (v1, v2, ... incremental)
    -> PENDING_APPROVAL   (after Signature Page 2 is generated)
    -> APPROVED           (store in audit tables, READ-ONLY)
    or REJECTED           (returns to DRAFT)
```
| Rule | Detail |
|---|---|
| Versioning | Each save in IN_PROGRESS creates a new working version (v1,v2,...) with timestamp+user |
| History | Keep full history of who worked on campaign and when (WORKFLOW_EVENT) |
| Approve | Copy final state into audit/snapshot tables, set status APPROVED. No further edits. |
| Reject | Set status back to DRAFT. Prior versions kept. |
| Enforcement | All transitions go through SP_PADM_TRANSITION_CAMPAIGN only (confirmed real name, see 0.1). **Confirmed: no transition path exists from APPROVED back to any editable status** -- only REJECTED -> DRAFT. Treat APPROVED as a deliberate, terminal lock; a "reopen an approved campaign" feature does not exist today. |

VERIFY: if the existing CHECK constraint on DM_PADM_CAMPAIGN_1.STATUS uses different values
(e.g. DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED/REOPENED), migrate to the statuses above.
Write the old->new mapping in docs/STATUS_MIGRATION.md.

### 2.6 Source-change flag
If ACM data changes after a campaign is activated, set SOURCE_CHANGE_PENDING_FLAG on the
campaign. Show a warning banner in the header when the flag is set.

## 3. Tab 2 - Signature Page

### 3.1 Rules
- Signature page data comes ONLY from the ACM tables.
- It is the FIRST STEP of each campaign.
- Show as a READ-ONLY SHELL before segments exist, all columns populated.
- For a new campaign, load the previous campaign's ACM values.
- Keep the previous year's and previous campaigns' assumptions in a table (defaults for Tab 4).
- Join as ACM LEFT JOIN campaign.
- Show calculated fields (Boards, CPA etc) as blank/"pending" until assumptions+selections
  exist. They fill in on Signature Page 2.
- Grain: one row per CAMPAIGN_ID + CAMPAIGN_OFFER_RESERVATION_CODE.

### 3.2 Displayed columns (in this order) -- all sources in CSTONE_BIZ.REFERENCE
1. Segment Description - T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_DESCRIPTION
2. AF (Annual Fee) - T_ACM_PROGRAMS.ANNUAL_FEE_YR1 / ANNUAL_FEE_YR2
3. Test Type - T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_CONTROL_TEST_DESCRIPTION
4. Network - T_ACM_PROGRAMS.NETWORK
5. Credit Bureau Model - T_ACM_CAMPAIGN_OFFERS.PROSPECT_CREDIT_BUREAU_MODEL
6. Credit Bureau Score - T_ACM_CAMPAIGN_OFFERS.PROSPECT_CREDIT_BUREAU_SCORE
7. CRS Model - T_ACM_CAMPAIGN_OFFERS.PROSPECT_CRS_MODEL
8. CRS Score - T_ACM_CAMPAIGN_OFFERS.PROSPECT_CRS_SCORE
9. NRM - T_ACM_CAMPAIGN_OFFERS.NET_RESPONSE_MODEL_CODE
10. Quantity - MKU/105/T_EXPERIAN_MAILFILE/T_TRANSUNION_MAILFILE
11. NBR - Assumptions (Tab 4)
12. Boards - Quantity x NBR
13. CPP - T_ACM_CAMPAIGN_OFFERS.COST_PER_PIECE. Manual override allowed (3.4)
14. Marketing Expense - Quantity x CPP
15. Unwind Rate - Assumptions (Tab 4)
16. Pre-Unwind CPA - Marketing Expense / Boards
17. Post-Unwind CPA - (Marketing + Booking Cost) / Post-Unwind Boards
18. PROMO - T_ACM_CAMPAIGN_OFFERS.RESERVATION_CODE_RISK
19. IVR - T_ACM_CAMPAIGN_OFFERS.CAMPAIGN_OFFER_APPROVAL_CODE
20. Underwriting Flag - lookup, **source TBD**, show blank, keep column
21. Prospect Type - rule in 3.3
22. Times Mailed 0% - Quantity TM0 / total quantity
23. Tiers - MKU/105/mailfiles: min tier || '-' || max tier
24. Print Vendor - T_ACM_CAMPAIGN_OFFERS.PRINT_VENDOR_ID
25. Post-Unwind Boards - Boards x (1 - Unwind Rate)
26. Marketing + Booking Costs - Marketing Expense + (Boards x Unit Cost)
27. Unit Cost - Manual input (Tab 4 / Segment Viewer)
-- Header: Campaign Name and Date (source not given; VERIFY)

### 3.3 Prospect Type rule (keep in a reference table, not code)
```sql
CASE WHEN CAMPAIGN_OFFER_SEGMENT_NAME IN (
  'PQ ABANDON','PQ DECLINE','PRIOR CHARGE OFF','PRIOR CLOSURE','PRIOR DECLINE',
  'REMARKET','TU PRIOR CHARGE OFF','TU PRIOR CLOSURE','TU PRIOR DECLINE')
THEN 'RETARGETING' ELSE 'PROSPECTING' END
```

### 3.4 Manual inserts **[UPDATED 2026-11-19 -- removed from this tab]**
- ~~CPP (per campaign date): editable field on this page.~~ **Removed from Signature Page.**
  CPP is now entered on Campaign Assumptions (campaign-level) and Segment Viewer (segment-level
  override) only. Root cause of the original design gap: CPP's `DM_PADM_ASSUMPTION_DEFINITION`
  row had `ASSUMPTION_LEVEL='CAMPAIGN'` instead of `'CAMPAIGN_SEGMENT'` even though it already had
  a segment-override column -- fixing that one value was enough for the generic,
  definitions-driven assumption UI to pick it up correctly in both other places. No manual insert
  remains on Signature Page.
- Also removed: the "Offers / Quantity / Segmented offers" metric tiles that used to sit above
  the table -- not part of the sign-off proposal's field list, and redundant with the per-segment
  numbers now shown directly in the table (see 3.6).

### 3.5 Hidden fields (stored, not displayed)
Campaign Year, Campaign Month, Campaign Month Sequence (all derived from CAMPAIGN_GROUP_MAIL_DATE),
Campaign Type (Primary/Remail), Mail Date, ACM Segment (CAMPAIGN_OFFER_SEGMENT_NAME), Population
Description (from Tab 5), Test Pairings (CAMPAIGN_OFFER_CONTROL_TEST_NAME), Times Mailed 1%...8%,
Times Mailed 9+%.

### 3.6 Implementation
- Read from VW_PADM_SIGNATURE_PAGE_LIVE -- a pre-snapshot view, same shape/formulas as the
  Signature Page 2 snapshot.
- TIMES_MAILED_0_PERCENTAGE must be COMPUTED from the times-mailed count columns, never NULL.
- **[UPDATED 2026-11-19] Grain changed from one row per offer to one row per segment.** The
  view's calculated columns (Quantity, Boards, NBR, CPP, etc.) have no offer dimension on the
  calculation side (joined only on CAMPAIGN_ID + SEGMENT_ID), so they were already identical
  across every offer in a segment -- the old one-row-per-offer display silently inflated GRAND
  TOTAL by each segment's offer count when summed. Fixed by collapsing to one row per segment in
  the Python layer (`ui.collapse_to_segment()`), not in the view: the view itself is unchanged.
  Offer-level fields that genuinely differ between offers sharing a segment (Test Type, Promo,
  IVR, etc.) show as a distinct-value summary rather than picking one and discarding the rest.
- **[UPDATED 2026-11-19] Only non-zero values are shown.** Zero and NULL cells in every
  calculated grid render blank, matching the real Segment.xlsx convention -- see 7.8.

## 4. Tab 3 - Create Segment

### 4.1 Rules
- Check the score logic based on Type (score ranges must be valid for selected bureau score
  type). Keep score ranges in DM_PADM_SCORE_RANGE_RULE_1, not in code.
- Mandatory fields: Bureau Score Type, Bureau Score Range (min-max), Source.
- Segment name auto-generated: `[Bureau Score Type] [Score Min]-[Score Max] [Source]`, e.g.
  `VS3 550-600 EXPERIAN`. Read-only, regenerates when fields change.
- Show already-available values as dropdowns. Dropdown values = distinct values from all rows
  where campaign_group_mail_date >= CURRENT_DATE() - 60.
- A segment is governed/reusable across campaigns (SEGMENT_1), with a campaign working copy
  (CAMPAIGN_SEGMENT_1).
- Block duplicates: same mandatory-field combo can't be created twice. Offer to reuse existing.

### 4.2 Form fields **[UPDATED 2026-11-19 -- trimmed to the sign-off proposal's actual list]**
1 Prospect Source Bureau (Experian, TransUnion) - Dropdown - Required (Source) -- marked `*` in UI
2 Bureau Score Type - Dropdown - Required -- marked `*`; **cascades on Source** (see below)
3 Bureau Score Range (min-max) - Two number inputs, validated against score-range rule - Required -- marked `*`
4 Annual Fee - Dropdown - No
5 Network - Dropdown - No
6 MLA - Dropdown - No
7 Risk Score Type - Dropdown - No
8 Response Model Type - Dropdown - No
9 Times Mailed - Multi-select (0-9+) - No (stored, not yet used to filter anything -- open item)

~~Prospect Type, Credit Bureau Model, Credit Bureau Score, CRS Model, CRS Score, Free-form
field~~ **removed** -- confirmed these belong to a different section of the sign-off proposal
(Campaign Creation's offer-grouping dropdowns), not Segment Creation's own field list.

**Bureau Score Type cascades on the selected Source**: Experian offers VS3/VS4/LIFT; TransUnion
offers VS3/VS4/LIFT (LIFT shown for both per explicit product decision, though Credit One's own
`T_EXPERIAN_MAILFILE`/`T_TRANSUNION_MAILFILE` data dictionaries confirm `LIFT_SCORE` exists only
in the Experian table -- a TransUnion+LIFT segment will correctly show "no active score-range
rules" until real TransUnion LIFT band data exists).

### 4.3 Offer allocation at creation **[UPDATED 2026-11-19 -- many-to-many]**
- ~~List available (unallocated) offers~~ **List ALL offers of the current campaign** -- an
  offer can belong to more than one segment (explicit decision: its full Quantity/Boards/$ then
  count independently in each segment it's on; Grand Total can exceed distinct offers mailed by
  design). Each offer in the picker is tagged `(on N segments)` when it already has allocations.
- Pre-suggest offers that the previously recorded matching segment used in earlier campaigns.
  User can keep/change.
- Save to DM_PADM_OFFER_SEGMENT_ALLOCATION. Uniqueness is enforced per *(offer, segment)* pair,
  not per offer.
- Actions: Create Segment, Reuse Existing Segment, Edit, Remove from Campaign.

### 4.4 Open item
Segmentation rules are TBD. Keep rule logic in reference tables, addable without code changes.

### 4.5 Governed segment pool, synced from source **[NEW 2026-11-19]**
- DM_PADM_SEGMENT_1 (the governed segment table every tab reads) historically only ever got rows
  through this manual Create Segment form -- unlike campaigns, which already had a real
  discover-from-source mechanism (`discover_campaign()`). This meant completed historical
  campaigns showed zero reusable segments even though real segment data existed in source
  systems.
- Added `discover_segments()`: an insert-only MERGE (never overwrites an existing governed
  segment) from `VW_PADM_SEGMENT_SOURCE_CANDIDATE` into DM_PADM_SEGMENT_1, matched on the same
  4-field key (Source, Score Type, Score Min, Score Max) `find_segment()` already uses. Exposed
  as a "Sync governed segments from source" button on this tab.
- `VW_PADM_SEGMENT_SOURCE_CANDIDATE` itself had to be rebuilt this session: its original
  definition read from `DM_PADM_TR_MAILFILE_NORMALIZED`, confirmed **not part of this project**
  and dropped. It now reads directly from `CSTONE_BIZ.REFERENCE.T_EXPERIAN_MAILFILE` /
  `T_TRANSUNION_MAILFILE`, banding the raw `PRESCREEN_VANTAGE_V3`/`V4`/`LIFT_SCORE` columns
  against `DM_PADM_SCORE_RANGE_RULE_1`.

## 5. Tab 4 - Campaign Assumptions

### 5.1 Rules **[UPDATED 2026-11-19 -- campaign-level only]**
- ~~Keep assumptions at BOTH campaign level and segment level~~. **Segment-level assumptions
  removed from this tab entirely** -- Segment Viewer is now the single place to view/edit
  segment-level overrides, which also prepopulate from this tab's campaign-level values (see
  7.7). This tab shows CPP, Unit Cost and whatever else has a real campaign-level column --
  generic/data-driven (any `DM_PADM_ASSUMPTION_DEFINITION` row with a non-null `CAMPAIGN_COLUMN`
  shows automatically), not a hardcoded field list.
- **Flagged, not resolved**: `NBR`'s segment-level override (`NBR_OVERRIDE`) has nowhere left to
  be edited -- its definition row is marked `ENTERED_ON='ASSUMPTIONS'` (meant for this tab), not
  `'SEGMENT_VIEWER'`/`'BOTH'`. If a segment-level NBR override is still needed, change its
  `ENTERED_ON` to `'BOTH'` (same fix already applied to CPP) so Segment Viewer picks it up.
- Store the data so far along with new inserts: every save creates a new version, old versions
  kept, via IS_CURRENT and ROW_VERSION.
- Add validation + type for each assumption (assumption-definition reference table: name, data
  type, decimals, min, max, allow-negative, level).
- Defaults: prefill from the previous campaign's and previous year's assumptions table.
- Show a version history panel: version, changed by, timestamp, change reason, old -> new value.

### 5.2 Assumptions and validation
| Assumption | Level | Type | Decimals | Rule | Entered on |
|---|---|---|---|---|---|
| CPP | Campaign | Number | 4 | >=0 | This tab or Signature Page |
| Unit Cost | Campaign/Segment | Number | 2 | >=0 | This tab or Segment Viewer |
| NBR | Campaign/Segment | Number | 4 | >=0 | This tab |
| Unwind Rate | Campaign/Segment | Number | 2 | >=0 (non-negative) | This tab |
| Unwind Rate Adjustment | Segment | Number | 2 | Allowed range VERIFY | Segment Viewer |
| Rate Adjustment | **Segment only** | Number | 2 | Sign rule VERIFY | **Segment Viewer only** |
| Seasonality Rate Adjustment | **Segment only** | Percentage | 2 | **Can be negative** | **Segment Viewer only** |

- Rate Adjustment and Seasonality are **segment-specific, not campaign-level**. Entered **only
  on Segment Viewer**. This tab shows them read-only.
- Write campaign-level via SP_PADM_SAVE_CAMPAIGN_ASSUMPTION, segment-level via
  SP_PADM_SAVE_SEGMENT_ASSUMPTION.

## 6. Tab 5 - Population Description

### 6.1 Rules **[UPDATED 2026-11-19 -- rebuilt segment-first, per the user's explicit call: the
original AF/score-band grouped layout was reported as "overwhelming"]**
- ~~Group segments by AF-to-score data: Annual Fee, then score band~~. **Segment-first instead**:
  pick a *set* of segments (multiselect -- "a population description is given to a set of
  segments, not just one"), they share one label, each still keeps its own offer multiselect.
  Many-to-many: the same offer can be picked into more than one selected segment's list in one
  save.
- Below each segment, provide a dropdown (multi-select) to assign one or more offers to that
  segment.
- Show the population description with sub-totals per group (quantity + other numeric cols) --
  implemented as per-segment figures plus one campaign-wide Grand Total; because of many-to-many
  this total can exceed the true count of distinct offers mailed (a shared offer's numbers count
  once per segment it's on), by design.
- Let the user label each group (used on sign-off doc). ~~Default labels from
  DM_PADM_POPULATION_GROUP_RULE~~ -- **confirmed unnecessary**: the real Signature Page export's
  "Sub-Total ..." rows are themselves just free text saved per allocation, not driven by a rule
  table. The label field is plain free text, pre-filled with a best-effort suggestion (`Sub-Total
  <source or MLA> <band>`) built from the segment's own fields -- a starting point to edit, not an
  exact match (no governed table exists for "Core"/"Expansion"-style wording seen in some real
  rows). **Do not build labels with Python string logic beyond this simple suggestion** -- the
  user always has final say via the editable text field.
- Offers ideally remain the same across campaign segments. Default each segment's offers to the
  previous allocation, let user change.
- Maintain allocation table: DM_PADM_OFFER_SEGMENT_ALLOCATION (Campaign+Offer Reservation
  Code+Segment). Versioned, each change audited. An offer may have more than one current row
  (one per segment it's allocated to) -- this table is many-to-many by design now, not 1:1.
- Allow changes to segment-to-offer links for existing segments on this page.

### 6.2 Layout **[UPDATED 2026-11-19]**
```
Segment(s) multiselect: [ Segment A ] [ Segment B ] ...   <- a set, shares one label below
Population description (free text, suggested default):  [Sub-Total EXPERIAN 550-600        ]

  Segment A   [Offers v multi-select]   Qty  ...
  Segment B   [Offers v multi-select]   Qty  ...

== Grand Total (campaign-wide) ======================   Qty  ...
```

### 6.3 Actions
Save (new version + CHANGE_REASON, applies to every segment currently selected) and Reset to
Previous Allocation (per segment).

## 7. Tab 6 - Segment Viewer (Excel-style grids)

### 7.1 General rules
- Keep all tables/data clean so the same process works for every campaign/segment.
- **Track the segment selections of every campaign.** Find/use/create one table for it.
- Pick a segment from a dropdown. Grids load for that segment.
- Segment header shows segment name + tier model, e.g. `VS3 550-600 MLA / TRM10`.
- **Remove the "Show calculated grid" toggle.** Calculated grids always visible.
- First campaign, no prior data: show zeros + note "No prior month selection".

### 7.2 Grid shape (same as Excel)
```
              Times Mailed
Tier   0  1  2  3 ... 9+   Total
1
2
...
N (e.g. 20 for TRM10)
Total
```
Rows = tiers (TRM10 tier 1...N) + Total row. Columns = Times Mailed buckets 0...9+ + Total
column. Show Total row AND Total column on EVERY grid.

### 7.3 Selection % grid (the editable input grid) **[UPDATED 2026-11-19 -- 3-color highlight]**
- Prepopulate with the previous month's selections, matched on the segment filters of the new
  campaign.
- ~~Highlight prior-month selected cells in yellow (prior value > 0)~~. **Extended to 3 colors,
  priority blue > green > yellow**: blue = cell differs from what's currently saved (unsaved
  edit -- most actionable, shown first); green = cell matches what's currently saved and is
  non-zero; yellow = prior campaign had a selection here, but neither of the above applies.
- Users can add/remove additional selections (edit any cell, 0 = remove).
- Applying % must work like Excel: edit a single cell; select a range (rows/cols/block) and
  apply one % to all of it; fill a whole row/column; copy/paste multiple cells; clear a range.
- Use st.data_editor with percentage formatting (0-100, 2 decimals).
- If cell styling isn't supported in the deployed Streamlit version, render a styled read-only
  copy directly below with the yellow highlights.
- Known limitation: true Excel click-drag fill isn't available -- provide "Apply % to range"
  controls instead.
- Percentages applied ON TOP OF post-EMS rate values.

### 7.4 Saving selections
- "Save Selections" button calls SP_PADM_SAVE_SELECTION_SET with mandatory change reason.
- Store all selections across THREE permanent stores:
| Store | Table | Retention |
|---|---|---|
| Working selections (live edits) | DM_PADM_SELECTION_WORKING | Cleared every 3 months (scheduled task) |
| Saved selection history (immutable versions) | DM_PADM_SELECTION_SET / _SET_CELL | Never cleared |
| Audit log (one row per user action) | DM_PADM_SELECTION_EVENT | Never cleared, audit purpose |
- Create a Snowflake TASK that purges working rows older than 3 months for campaigns not in
  progress. Must never touch saved history or audit rows.

### 7.5 CDE, MKU and EMS data
- CDE: load/save CDE volume for all of the previous year's campaigns, use same table for all
  future campaigns (DM_PADM_CDE_LOAD_BATCH / DM_PADM_CDE_DETAIL). Activate a CDE version per
  campaign+segment via SP_PADM_ACTIVATE_CDE_VERSION. Provide CSV/Excel upload in the UI for new
  segments -- **this happens on the Segment Viewer page**; once uploaded, show CDE values.
- MKU (Marketable Universe) is volume before suppression. Source: Excel report "Marketable
  Universe Counts" on the Risk Acquisitions share. VERIFY the load path, document in
  docs/DATA_LINEAGE.md.
- EMS: check EMS calculation. Post-EMS = MKU/CDE Volume x (1 - EMS reduction). **For the POC,
  apply a blanket 5% when no EMS rate exists.**

### 7.6 Working version vs final version
- Working Version (WV): estimate built from MKU/CDE volume and selection %.
- Final Version (FV): selections come from the actual mail file (T_EXPERIAN_MAILFILE or
  T_TRANSUNION_MAILFILE). All other rows unchanged from WV.
- Show a toggle "Working Version | Final Version" at top of the grids (switches volume source;
  NOT the removed "calculated grid" toggle).
| Field | Working Version | Final Version |
|---|---|---|
| MKU Volume | Excel report | No change |
| Universe Post-EMS Rates | MKU Volume x EMS adj (blanket 5% for POC) | No change |
| Selections | Selection % x universe post-EMS | From mail file (Experian/TransUnion) |
| Selections % (new) | Prepopulated prior month; user selects % per cell | No change |
| Net Response Rate 1 | From Vivian's script (historical NRR) | No change |
| Net Response Rate 2 | NRR1 x seasonality adjustment | No change |
| Booked Pre-Unwind 1/2 | Quantity x NRR1/NRR2 | No change |
| Unwinds 1 | Booked Pre-Unwind1 x unwind rate x (1+unwind rate adj) | No change |
| Unwinds 2 | Booked Pre-Unwind2 x unwind rate x (1+unwind rate adj) | Same formula |
| Booked Post-Unwind 1 | Booked Pre-Unwind1 - Unwinds1 | No change |
| Booked Post-Unwind 2 | Booked Pre-Unwind2 - Unwinds2 | Same formula |
| CPP | Manual input on signature page | No change |
| Unit Cost | Manual input on segment tab | No change |
| Seasonality Adjustment | Manual input on segment tab | No change |

### 7.7 Segment-level inputs on this tab **[UPDATED 2026-11-19 -- prepopulation + CPP added]**
These sit above the grids, segment-specific. Save via SP_PADM_SAVE_SEGMENT_ASSUMPTION.
- CPP: prepopulates from the campaign's current/latest assumption when no segment override
  exists yet; still editable/overridable per segment here. (This is the field that moved off
  Signature Page -- see 3.4.)
- Unit Cost: 2 decimals, >= 0. Also prepopulates from the campaign's current value.
- Rate Adjustment: 2 decimals. No campaign-level counterpart -- nothing to prepopulate from.
- Seasonality Rate Adjustment: percentage, 2 decimals, CAN BE NEGATIVE. No campaign-level
  counterpart.
- Unwind Rate Adjustment: 2 decimals. No campaign-level counterpart.

### 7.8 Calculated grids - order of calculation **[UPDATED 2026-11-19 -- side-by-side layout
matching the real Segment.xlsx the user provided; 14 grids -> 22]**
~~Display the grids IN CALCULATION ORDER, top to bottom~~ -- **still in calculation order, but
grouped into rows of 2-3 grids shown side by side**, each with its own horizontal + vertical
scrollbar, matching the real Excel alignment. Universe-vs-Selected pairs were already being
calculated in Python before this session (`formulas.calculate()`) -- only their side-by-side
display is new, except for 2 genuinely new grid definitions (Selected NRR, Historical Unwind
Rate) that reuse values already computed. **Only non-zero values are shown** -- zero/NULL cells
render blank, matching the Excel convention (also applied to Signature Page -- see 3.6).
| Row | Grids shown side by side |
|---|---|
| 1 | Selection % (input) -- *separate section above, own save button, unaffected by this change* |
| 2 | CDE Volume · Universe Post-EMS · Selections |
| 3 | Base NRR · Effective NRR · Selected NRR |
| 4 | Historical Unwind Rate · Effective Unwind Rate · Booked Pre-Unwind (Selected) · Universe Booked Pre-Unwind |
| 5 | Pre-Unwind CPA Universe · Pre-Unwind CPA (Selected) |
| 6 | Post-Unwind CPA Universe · Post-Unwind CPA Selected |
| 7 | Universe Marketing Cost · Selected Marketing Cost |
| 8 | Universe Booking Cost · Selected Booking Cost |
| 9 | Universe Expected Unwinds · Selected Expected Unwinds |
| 10 | Universe Booked Post-Unwind · Selected Booked Post-Unwind |

Formulas are unchanged from the original spec (see below) -- this was a display/layout change,
not a calculation change.

Rules for calculated grids:
- A CPA grid can't be calculated before Marketing Cost and Booked Pre-Unwind exist. Enforce the
  dependency order in BOTH code and procedure.
- On the Booked Post-Unwind grid, show an Unwind Rate row directly below the Total row.
- Totals for rate and CPA grids are WEIGHTED (total numerator/total denominator), not sums.
- Division by zero returns NULL and displays "-".
- Compute Booked Pre-Unwind for BOTH universe volume and selected volume.
- Fallback logic when a historical NRR/unwind/EMS cell is missing, in this order: 1. exact cell
  (segment+tier+times mailed) 2. segment+campaign type 3. campaign-level default. Implement with
  chained LEFT JOIN...COALESCE in VW_PADM_SEGMENT_CALCULATION_CURRENT.
- "Run Calculation" button calls SP_PADM_RUN_CALCULATION, writes DM_PADM_CALCULATION_RUN
  (status COMPLETED) and DM_PADM_CALCULATION_CELL.

### 7.9 Shared formula module
Keep every formula above in ONE Python module (padm/formulas.py) AND mirror it in the SQL view.
Add a unit test confirming Python and SQL results match for a sample segment.

## 8. Tab 7 - Signature Page 2

### 8.1 Rules
- It is Signature Page 1 (same 27 columns, section 3.2) loaded with calculated values and
  population description (groups, labels, sub-totals from Tab 5).
- Before submission: LIVE PREVIEW, read from VW_PADM_SIGNATURE_PAGE_LIVE.
- On generation/submission: IMMUTABLE SNAPSHOT in DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT, grain
  Campaign + Signature Version + output row.
- SP_PADM_GENERATE_SIGNATURE_PAGE_2 must REFUSE to run unless latest calculation run is
  COMPLETED. It assigns version numbers.
- Prior snapshot versions can be paged through, read-only.

### 8.2 Actions (in order)
1. Run Calculation
2. Generate Signature Page 2 (snapshot; status -> PENDING_APPROVAL)
3. Approve (status -> APPROVED; copy to audit tables; whole campaign read-only) or Reject
   (status -> DRAFT)
4. Export to Excel and Export to PDF (executive-friendly formatting)

### 8.3 After approval
Values go for approval, then actuals are created/worked on. Actuals are OUT OF SCOPE for this
build -- leave a placeholder section.

## 9. Audit & Non-Functional Requirements

### 9.1 Audit trail (all tabs)
- Record every change with timestamp, user (CURRENT_USER() for now; roles decided later),
  before/after values.
- DM_PADM_CHANGE_EVENT for data changes, DM_PADM_WORKFLOW_EVENT for status changes.
- Keep historical records for review.
- CHANGE_REASON mandatory on every write. Show a text box next to every Save button.

### 9.2 Architecture
- Working schema: active operations, read/write, user updates, assumption maintenance,
  campaign preparation.
- Archive: finalized versions, read-only, historical retention, audit/compliance.

### 9.3 Non-functional requirements
| Area | Requirement |
|---|---|
| Performance | Campaign generation within business SLA (TBD); recalculation near real-time after user edits |
| Security | Role-based access; audit logging on all updates; archived data read-only |
| Maintainability | Easy to add new assumptions/segment attributes; minimal hardcoded rules |
| Usability | Intuitive tab navigation; consistent formatting; executive-friendly signature pages |
| Concurrency | Optimistic locking via ROW_VERSION. Stale save shows "Record changed by another user -- reload". |

## 10. Open Items (build placeholders; do not invent logic)
| Item | Status | Build action |
|---|---|---|
| Finance Extract requirements | TBD | Placeholder tab section only |
| Campaign Type derivation logic | TBD | Manual dropdown for now |
| Segmentation rules | TBD | Reference-table driven |
| Underwriting Flag lookup source | TBD | Blank column kept |
| Final role matrix | TBD | Use CURRENT_USER(); no role gates yet |
| Performance SLAs | TBD | -- |
| Change-highlighting method | TBD | Yellow = prior-month selection (as specified) |
| Campaign Name and Date header source | TBD | VERIFY |

## 11. Deliverables
1. streamlit_app.py plus one module per tab under padm/tabs/
2. padm/repository.py (all SQL access), padm/formulas.py, padm/validation.py
3. sql/ with idempotent DDL (CREATE...IF NOT EXISTS / ALTER), views, procedures, 3-month purge task
4. docs/DATA_LINEAGE.md, docs/CAMPAIGN_ACTIVATION.md, docs/STATUS_MIGRATION.md
5. tests/: formula unit tests, Python-vs-SQL parity test, status-transition test (approved
   campaign can't be edited)
6. Seed script: create one campaign + one segment, activate one CDE version, so Segment Viewer
   and Signature Page 2 have data to show

## 12. Acceptance Checklist
- [ ] All 7 tabs load in order. Tabs 2-7 locked until a campaign is selected.
- [ ] Campaign creation applies the 4 filters and snapshots ACM data.
- [ ] Status flow works end to end. Approved means read-only everywhere. Rejected -> Draft.
- [ ] Signature Page shows all 27 columns from ACM only, as read-only shell. Hidden fields stored.
- [ ] Segment name auto-generates from mandatory fields. Dropdowns use the 60-day window.
- [ ] Assumptions versioned; no overwrite. Precision and sign rules enforced.
- [ ] Population Description groups by AF->score, assigns offers by multi-select, shows sub-totals.
- [ ] Selection % grid prefilled from prior month with yellow highlights. Excel-like range apply works.
- [ ] Save Selections writes working, history, audit stores. 3-month purge task exists.
- [ ] Calculated grids appear in calculation order, each with formula caption. Unwind rate shown
      under Booked Post-Unwind total.
- [ ] Signature Page 2 = Signature Page 1 + calculated values + population description. Snapshot
      immutable. Excel/PDF export works.
- [ ] Every write has a user, timestamp, before/after values, a change reason.
