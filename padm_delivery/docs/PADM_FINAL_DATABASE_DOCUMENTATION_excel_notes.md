# Notes from "Final sql database queries and documentation 1.pdf" (24 pages, fully read)

This PDF contains NO raw CREATE TABLE/CREATE VIEW SQL syntax. It is entirely screenshots of a
read-only Excel workbook titled **"PADM_Final_Database_Documentation"** (tabs: Index, Overview,
Run Order, Tables, Column Dictionary, Views, Join Map, Calculations, Page Data Flow, Workflow,
Procedures, Validations, Source Mapping, Open Config, Legend — only Index/Overview/Run
Order/Tables/Column Dictionary/Views were actually visible in the screenshots; Join Map/
Calculations/etc. tabs exist per the Index but their content was NOT shown), plus 2 screenshots of
the OLD dead `app/campaign_queries.py` file (already-known dead tree, cross-reference only).

Per the fork directive, this is documentation/reference material, not executable SQL — it must
NOT be used to fabricate CREATE TABLE/VIEW statements. It is captured here for the merge step to
cross-check against whatever real DDL the other 3 parallel forks captured from their PDFs.

## Index tab (sheet list)
Overview=Executive summary; Run Order=Deployment and load sequence; Tables=Table-level data
dictionary; Column Dictionary=Column-level data dictionary; Views=View contracts; Join Map=Join
keys and risks; Calculations=Formula definitions; Page Data Flow=Application page contracts;
Workflow=Status movement; Procedures=Transactional write procedures; Validations=Post-deployment
and post-load checks; Source Mapping=Source-to-target mapping; Open Config=Remaining
configuration and implementation items; Legend=Workbook terminology.

## Overview tab (design topics, condensed)
Scope: Final Snowflake database layer from ACM campaign discovery through live and snapshotted
Signature Page 2. Campaign model: PADM source component maps to MAIN; MAP and PAREMAIL combine
into one REMAIL campaign. Campaign business grain: REPORTING_MONTH + CAMPAIGN_TYPE; CAMPAIGN_ID
is the immutable internal key. Offer grain: CAMPAIGN_SOURCE_VERSION_ID + OFFER_RESERVATION_CODE.
Offer-Segment model: many-to-many through DM_PADM_OFFER_SEGMENT_ALLOCATION. Population
Description: stored and versioned on Campaign + Offer + Segment allocation. CDE design: raw
Vantage band, Times Mailed, TRM10 Tier, CRS23 and distinct EPIN count retained; grid is derived.
Selection design: mutable working cells plus immutable version headers, immutable cells and
action audit events. Assumption design: every save creates a new Campaign or Segment assumption
version. Calculation design: current values are views; completed results are stored in calculation
and Signature Page 2 snapshot tables. Main risk controlled: source, user input, history,
calculations and final snapshots kept in separate objects. First deployment: run in a development
schema and execute post-deployment validations before loading real campaigns.

## Run Order tab (27-step deployment sequence — AUTHORITATIVE file names/order)
| # | Phase | File or Procedure | Action | Expected Result |
|---|---|---|---|---|
|1|Set context|00_context.sql|Confirm development database and schema.|No data changed.|
|2|Reference and audit tables|01_reference_and_audit_tables.sql|Create load, audit and rule tables.|All statements succeed.|
|3|Campaign and offer tables|02_campaign_and_offer_tables.sql|Create campaign, source version, component, offer and profile tables.|All statements succeed.|
|4|Segment and allocations|03_segment_and_allocation_tables.sql|Create governed Segment and many-to-many allocation tables.|All statements succeed.|
|5|Assumptions|04_assumption_tables.sql|Create versioned campaign and Segment assumptions.|All statements succeed.|
|6|CDE and EMS|05_cde_ems_tables.sql|Create raw CDE versions and versioned EMS rates.|All statements succeed.|
|7|Selections|06_selection_tables.sql|Create working, versioned and event tables.|All statements succeed.|
|8|History|07_history_tables.sql|Create NRR, unwind and explicit history mapping tables.|All statements succeed.|
|9|Calculations and snapshots|08_calculation_and_snapshot_tables.sql|Create calculation-run, cell and Signature Page 2 snapshot tables.|Views compile; no duplicate offers.|
|10|Source views|09_source_views.sql|Create eligible ACM campaign and offer source views.|Views compile.|
|11|Current state views|10_current_state_views.sql|Create current campaign, assumption, CDE and selection views.|Views compile; can be empty.|
|12|Calculation views|11_calculation_views.sql|Create NRR, unwind and Segment calculation views.|Procedures compile.|
|13|Procedures|16_operational_procedures.sql|Create controlled activation, version save and status transition procedures.|Failure queries return no rows.|
|14|Structural validation|17_post_deployment_validations.sql|Check required objects and source uniqueness.|Campaigns are DISCOVERED and inactive.|
|15|Campaign discovery|12_campaign_load_templates.sql|Merge source candidates into campaign master.|Status DRAFT, Active TRUE.|
|16|Campaign activation|SP_PADM_ACTIVATE_CAMPAIGN|Activate one test campaign with a reason.|One current source version; no offer duplicates.|
|17|Source snapshot load|Application transaction|Create source version, components, offers and profiles.|No duplicate current allocations.|
|18|Segments and allocations|Application transaction|Create Campaign Segments and Offer-Segment allocations.|Exactly one current version.|
|19|Assumptions|SP_PADM_SAVE_CAMPAIGN_ASSUMPTION|Create current Campaign assumption version.|One active CDE version per Campaign + Segment.|
|20|CDE load|13_cde_load_template.sql|Stage, validate, insert and activate raw CDE detail.|No overlapping mappings.|
|21|EMS and history|Governed loads|Load EMS, NRR, unwind and approved history mappings.|Working cells unique and percentages 0 to 1.|
|22|Selections|Application transaction|Initialize and save complete selection sets.|Formula validations return no rows.|
|23|Calculation review|VW_PADM_SEGMENT_CALCULATION_CURRENT|Review cell-level calculations.|(blank in source)|
|24|Ready for review|SP_PADM_TRANSITION_CAMPAIGN|Transition after Signature Page 2 completion.|Status READY_FOR_REVIEW.|
|25|Complete|SP_PADM_TRANSITION_CAMPAIGN|Transition after approval.|Status COMPLETED and read-only.|
|26|Final snapshot|14_signature_page_2_snapshot.sql|Create immutable final output after profile-source adjustment.|Snapshot row counts reconcile.|
|27|Final validation|15_validations.sql and 17_post_deployment_validations.sql|Run complete duplicate, grain, range and formula checks.|All failure queries return no rows.|

NOTE: this Run Order's file-numbering scheme (00_context.sql ... 17_post_deployment_validations.sql)
and status vocabulary (DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED) do NOT match the 23 real
target filenames given in this fork's directive (bare names like `activation_and_validations.sql`,
no numeric prefixes) nor the real padm/ status vocabulary from the user's spec
(NEW/DRAFT/IN_PROGRESS/PENDING_APPROVAL/APPROVED/REJECTED). This appears to be an EARLIER/DRAFT
design iteration's documentation, not necessarily the final deployed schema — flag this
discrepancy for the merge step rather than assuming either naming scheme is current.

## Tables tab (Table / Family / Grain / Primary Key / Purpose) — full list seen
DM_PADM_SOURCE_LOAD_BATCH | Source control | One row per source load batch | LOAD_BATCH_ID | Tracks file/object loads, counts and statuses.
DM_PADM_CHANGE_EVENT | Audit | One row per data-change event | CHANGE_EVENT_ID | Stores before/after JSON and business reason.
DM_PADM_WORKFLOW_EVENT | Workflow | One row per campaign status transition | WORKFLOW_EVENT_ID | Stores status movement, user, reason and timestamp.
DM_PADM_SCORE_RANGE_RULE | Reference | Score type + score range + effective period | SCORE_RANGE_RULE_ID | Governed score ranges; removes reusable-view hardcoding.
DM_PADM_POPULATION_GROUP_RULE | Reference | Population rule + effective period | POPULATION_GROUP_RULE_ID | Suggests editable population grouping labels.
DM_PADM_LIFT_TIER_RULE | Reference | Lift score range + effective period | LIFT_TIER_RULE_ID | Maps LIFT score to response tier.
DM_PADM_CAMPAIGN | Campaign | Reporting month + campaign type | CAMPAIGN_ID | Immutable campaign identity, workflow and source-change state.
DM_PADM_CAMPAIGN_SOURCE_VERSION | Campaign source | Campaign + source version | CAMPAIGN_SOURCE_VERSION_ID | Preserves each refreshed ACM source snapshot.
DM_PADM_CAMPAIGN_SOURCE_COMPONENT | Campaign source | Source version + component + mail date | CAMPAIGN_SOURCE_COMPONENT_ID | Preserves PADM, MAP and PAREMAIL components.
DM_PADM_CAMPAIGN_OFFER | Campaign source | Source version + offer code | CAMPAIGN_OFFER_ID | Immutable offer-level ACM snapshot.
DM_PADM_CAMPAIGN_OFFER_PROFILE | Campaign source | Offer + profile version | CAMPAIGN_OFFER_PROFILE_ID | Stores MKU, Report 105, actual quantity and TM distributions.
DM_PADM_SEGMENT | Governance | One row per governed Segment | SEGMENT_ID | Reusable Segment definition.
DM_PADM_CAMPAIGN_SEGMENT | Working | Campaign + Segment + working version | CAMPAIGN_SEGMENT_ID | Defines Segments in a campaign and prior-source lineage.
DM_PADM_OFFER_SEGMENT_ALLOCATION | Working | Campaign + Offer + Segment + version | OFFER_SEGMENT_ALLOCATION_ID | Many-to-many offer allocation and Population Description.
DM_PADM_CAMPAIGN_ASSUMPTION_VERSION | Input | Campaign + assumption version | CAMPAIGN_ASSUMPTION_VERSION_ID | Versioned CPP, Unit Cost and adjustments.
DM_PADM_SEGMENT_ASSUMPTION_VERSION | Input | Campaign + Segment + version | SEGMENT_ASSUMPTION_VERSION_ID | Versioned Segment overrides.
DM_PADM_CDE_LOAD_BATCH | CDE | Campaign + Segment + CDE version | CDE_LOAD_BATCH_ID | Tracks raw CDE file versions and activation.
DM_PADM_CDE_DETAIL | CDE | CDE batch + raw score/tier/TM/CRS cell | CDE_DETAIL_ID | Preserves raw pivot dimensions and distinct EPIN count.
DM_PADM_EMS_RATE_VERSION | Input | Campaign/Segment/Tier/TM + version | EMS_RATE_VERSION_ID | Versioned positive EMS reduction.
DM_PADM_SELECTION_WORKING | Input | Campaign + Segment + Tier + TM | (composite) | Mutable current selection matrix.
DM_PADM_SELECTION_SET | Input history | Campaign + Segment + version | SELECTION_SET_ID | Immutable selection save header.
DM_PADM_SELECTION_SET_CELL | Input history | Selection set + Tier + TM | (composite) | Complete reproducible matrix for each save.
DM_PADM_SELECTION_EVENT | Audit | One row per selection action | SELECTION_EVENT_ID | Human-readable rectangle action audit.
DM_PADM_HISTORY_LOAD_BATCH | History | One row per NRR or unwind load | HISTORY_LOAD_BATCH_ID | Stores observation windows and rule versions.
DM_PADM_HISTORY_SEGMENT_KEY | History | One row per historical natural key | HISTORY_SEGMENT_KEY_ID | Normalizes Vivian [sic, likely "the"] historical Segment definitions.
DM_PADM_HISTORY_SEGMENT_MAP | History governance | Historical key + Segment + effective period | HISTORY_SEGMENT_MAP_ID | Explicit approved mapping to governed Segment.
DM_PADM_NRR_HISTORY_CELL | History | Batch + historical key + type + Tier + TM + date | NRR_HISTORY_CELL_ID | Stores mail, applied and boarded counts.
DM_PADM_UNWIND_HISTORY_CELL | History | Batch + historical key + type + Tier + TM + date | UNWIND_HISTORY_CELL_ID | Stores boards and unwinds.
DM_PADM_CALCULATION_RUN | Calculation | One row per campaign calculation run | CALCULATION_RUN_ID | Pins source data and calculation status.
DM_PADM_CALCULATION_CELL | Calculation snapshot | Run + Segment + Tier + TM | CALCULATION_CELL_ID | Immutable final cell calculations.
DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT | Final output | Campaign + version + offer + Segment | SIGNATURE_PAGE_2_SNAPSHOT_ID | Immutable completed Signature Page 2 output.

## Column Dictionary tab (Table / Position / Column / Type / Nullable / Default / Meaning)
Full column-level detail was captured for every table above EXCEPT: most of DM_PADM_CAMPAIGN's
later columns (17 ROW_VERSION onward — only cross-referenced via dead-tree code, see
NOTES_from_queries7.md) and ALL of DM_PADM_CAMPAIGN_SOURCE_VERSION were skipped between two
consecutive screenshots (a genuine capture gap, not a redaction — the screenshooter scrolled past
them). Do not fabricate these two tables' full column lists.

Captured in full (transcribed faithfully, NUMBER(n) truncated as shown in source — e.g. "NUMBER(38"
means the screenshot's visible digits, precision/scale not fully confirmed):

**DM_PADM_SOURCE_LOAD_BATCH**: 1 LOAD_BATCH_ID VARCHAR not null; 2 SOURCE_NAME VARCHAR not null;
3 SOURCE_OBJECT_NAME VARCHAR null; 4 SOURCE_FILE_NAME VARCHAR null; 5 SOURCE_AS_OF_TS
TIMESTAMP_NTZ null; 6 LOAD_STARTED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP();
7 LOAD_COMPLETED_TS TIMESTAMP_NTZ null; 8 LOAD_STATUS VARCHAR not null default 'STARTED';
9 SOURCE_ROW_COUNT NUMBER(38 null; 10 LOADED_ROW_COUNT NUMBER(38 null; 11 REJECTED_ROW_COUNT
NUMBER(38 null; 12 ERROR_MESSAGE VARCHAR null; 13 CREATED_BY VARCHAR not null default
CURRENT_USER().

**DM_PADM_CHANGE_EVENT**: 1 CHANGE_EVENT_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR null;
3 ENTITY_TYPE VARCHAR not null; 4 ENTITY_ID VARCHAR not null; 5 CHANGE_TYPE VARCHAR not null;
6 BEFORE_VALUE VARIANT null; 7 AFTER_VALUE VARIANT null; 8 CHANGE_REASON VARCHAR null;
9 CHANGED_BY VARCHAR not null default CURRENT_USER(); 10 CHANGED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

**DM_PADM_WORKFLOW_EVENT**: 1 WORKFLOW_EVENT_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not null;
3 FROM_STATUS VARCHAR null; 4 TO_STATUS VARCHAR not null; 5 EVENT_REASON VARCHAR null;
6 EVENT_COMMENT VARCHAR null; 7 EVENT_BY VARCHAR not null default CURRENT_USER();
8 EVENT_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_SCORE_RANGE_RULE**: 1 SCORE_RANGE_RULE_ID VARCHAR not null; 2 SCORE_TYPE VARCHAR not
null; 3 SCORE_RANGE_CODE VARCHAR not null; 4 SCORE_MIN NUMBER(10 not null; 5 SCORE_MAX
NUMBER(10 not null; 6 DISPLAY_SEQUENCE NUMBER(10 null; 7 VALID_FROM DATE not null; 8 VALID_TO
DATE null; 9 ACTIVE_FLAG BOOLEAN not null default TRUE; 10 CREATED_BY VARCHAR not null default
CURRENT_USER(); 11 CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP();
12 UPDATED_BY VARCHAR not null default CURRENT_USER(); 13 UPDATED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

**DM_PADM_POPULATION_GROUP_RULE**: 1 POPULATION_GROUP_RULE_ID VARCHAR not null; 2 SOURCE_NAME
VARCHAR not null; 3 SCORE_TYPE VARCHAR null; 4 SCORE_MIN NUMBER(10 null; 5 SCORE_MAX NUMBER(10
null; 6 PROSPECT_SEGMENT_TYPE VARCHAR null; 7 POPULATION_GROUP_CODE VARCHAR not null;
8 POPULATION_GROUP_LABEL VARCHAR not null; 9 DISPLAY_SEQUENCE NUMBER(10 null; 10 VALID_FROM DATE
not null; 11 VALID_TO DATE null; 12 ACTIVE_FLAG BOOLEAN not null default TRUE; 13 CREATED_BY
VARCHAR not null default CURRENT_USER(); 14 CREATED_TS TIMESTAMP_NTZ not null default
CURRENT_TIMESTAMP(); 15 UPDATED_BY VARCHAR not null default CURRENT_USER(); 16 UPDATED_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_LIFT_TIER_RULE**: 1 LIFT_TIER_RULE_ID VARCHAR not null; 2 LIFT_SCORE_MIN NUMBER(10
not null; 3 LIFT_SCORE_MAX NUMBER(10 not null; 4 RESPONSE_MODEL_TIER NUMBER(10 not null (meaning:
"Segment Viewer row dimension"); 5 VALID_FROM DATE not null; 6 VALID_TO DATE null; 7 ACTIVE_FLAG
BOOLEAN not null default TRUE; 8 CREATED_BY VARCHAR not null default CURRENT_USER();
9 CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_CAMPAIGN** (PARTIAL — gap after column 16, see note above): 1 CAMPAIGN_ID VARCHAR not
null; 2 SOURCE_CAMPAIGN_IDENTIFICATION_CODE VARCHAR null; 3 CAMPAIGN_YEAR NUMBER(4 not null;
4 CAMPAIGN_MONTH NUMBER(2 not null; 5 REPORTING_MONTH DATE not null; 6 CAMPAIGN_SEQUENCE
NUMBER(3 not null; 7 CAMPAIGN_TYPE VARCHAR not null; 8 CAMPAIGN_DISPLAY_NAME VARCHAR not null;
9 SOURCE_CAMPAIGN_COUNTER_MIN NUMBER(10 null; 10 SOURCE_CAMPAIGN_COUNTER_MAX NUMBER(10 null;
11 SOURCE_MIN_MAIL_DATE DATE null; 12 SOURCE_MAX_MAIL_DATE DATE null; 13 STATUS VARCHAR not null
default 'DISCOVERED'; 14 ACTIVE_FLAG BOOLEAN not null default FALSE; 15
SOURCE_CHANGE_PENDING_FLAG BOOLEAN not null default FALSE; 16 CURRENT_SOURCE_VERSION_NUMBER
NUMBER(10 not null default 1. [columns 17+ not captured in this PDF — see
NOTES_from_queries7.md's dead-tree cross-reference for likely remaining column names:
CURRENT_WORKING_VERSION_NUMBER, ROW_VERSION, CREATED_BY, CREATED_TS, UPDATED_BY, UPDATED_TS —
unconfirmed from this source].

**DM_PADM_CAMPAIGN_SOURCE_VERSION**: TRANSCRIPTION CUT OFF — no columns of this table were shown
in any screenshot in this PDF.

**DM_PADM_CAMPAIGN_SOURCE_COMPONENT** (column 1 not captured, screenshots start at column 2):
2 CAMPAIGN_SOURCE_VERSION_ID VARCHAR not null; 3 CAMPAIGN_ID VARCHAR not null;
4 SOURCE_CAMPAIGN_IDENTIFICATION_CODE VARCHAR null; 5 SOURCE_CAMPAIGN_GROUP_CODE VARCHAR not
null; 6 SOURCE_CAMPAIGN_GROUP_DESCRIPTION VARCHAR null; 7 SOURCE_CAMPAIGN_TYPE_CODE VARCHAR
null; 8 SOURCE_CAMPAIGN_TYPE_NAME VARCHAR null; 9 SOURCE_MAIL_DATE DATE not null;
10 SOURCE_GROUP_START_DATE DATE null; 11 SOURCE_GROUP_END_DATE DATE null;
12 SOURCE_GROUP_RETIRE_DATE DATE null; 13 SOURCE_GROUP_EXPIRE_DATE DATE null;
14 SOURCE_LETTER_EXPIRE_DATE DATE null; 15 SOURCE_OFFER_COUNT NUMBER(38 not null; 16 CREATED_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_CAMPAIGN_OFFER**: 1 CAMPAIGN_OFFER_ID VARCHAR not null; 2 CAMPAIGN_SOURCE_VERSION_ID
VARCHAR not null; 3 CAMPAIGN_ID VARCHAR not null; 4 CAMPAIGN_SOURCE_COMPONENT_ID VARCHAR not
null; 5 OFFER_RESERVATION_CODE VARCHAR not null; 6 PROGRAM_CODE VARCHAR not null;
7 PROGRAM_VERSION_NUMBER NUMBER(10 not null; 8 SOURCE_CAMPAIGN_CODE VARCHAR null;
9 SOURCE_CAMPAIGN_NAME VARCHAR null; 10 SOURCE_CAMPAIGN_DESCRIPTION VARCHAR null;
11 SOURCE_MAIL_DATE DATE not null; 12 OFFER_DESCRIPTION VARCHAR null; 13 OFFER_SEGMENT_NAME
VARCHAR null; 14 TEST_TYPE VARCHAR null; 15 SOURCE_CPP NUMBER(18 null; 16 PROMO_CODE VARCHAR
null; 17 APPROVAL_CODE VARCHAR null; 18 UNDERWRITING_FLAG VARCHAR null (boolean indicator);
19 PROSPECT_TYPE VARCHAR null; 20 PRINT_VENDOR_ID VARCHAR null; 21 CRS_SCORE VARCHAR null;
22 OFFER_NOTE VARCHAR null; 23 MAIL_CLASS VARCHAR null; 24 REMOVED_FLAG BOOLEAN not null default
FALSE; 25 REMOVED_DATE DATE null; 26 SEED_DESCRIPTION VARCHAR null; 27 DUPLEX_FLAG BOOLEAN null;
28 UP_TO_AMOUNT NUMBER(18 null; 29 USER_DEFINED_CAMPAIGN_FIELD VARCHAR null; 30 OFFER_STATUS
VARCHAR null; 31 SOURCE_RECORD_ID VARCHAR null; 32 SOURCE_ROW_HASH VARCHAR not null;
33 IS_CURRENT BOOLEAN not null default TRUE; 34 CREATED_TS TIMESTAMP_NTZ not null default
CURRENT_TIMESTAMP().

**DM_PADM_CAMPAIGN_OFFER_PROFILE**: 1 CAMPAIGN_OFFER_PROFILE_ID VARCHAR not null; 2 CAMPAIGN_ID
VARCHAR not null; 3 CAMPAIGN_OFFER_ID VARCHAR not null; 4 PROFILE_VERSION_NUMBER NUMBER(10 not
null; 5 PROFILE_SOURCE_TYPE VARCHAR not null; 6 MKU_VOLUME NUMBER(38 null; 7 REPORT_105_VOLUME
NUMBER(38 null; 8 ACTUAL_MAIL_QUANTITY NUMBER(38 null; 9 ANNUAL_FEE VARCHAR null; 10 NETWORK
VARCHAR null; 11 BUREAU_SCORE_TYPE VARCHAR null; 12 BUREAU_SCORE_RANGE VARCHAR null;
13 RISK_SCORE_TYPE VARCHAR null; 14 CRS_SCORE_MIN NUMBER(18 null; 15 CRS_SCORE_MAX NUMBER(18
null; 16 TIMES_MAILED_0_COUNT NUMBER(38 null; 17 TIMES_MAILED_1_COUNT NUMBER(38 null;
18 TIMES_MAILED_2_COUNT NUMBER(38 null; 19 TIMES_MAILED_3_COUNT NUMBER(38 null;
20 TIMES_MAILED_4_COUNT NUMBER(38 null; 21 TIMES_MAILED_5_COUNT NUMBER(38 null;
22 TIMES_MAILED_6_COUNT NUMBER(38 null; 23 TIMES_MAILED_7_COUNT NUMBER(38 null;
24 TIMES_MAILED_8_COUNT NUMBER(38 null; 25 TIMES_MAILED_9_PLUS_COUNT NUMBER(38 null;
26 AVAILABLE_TIERS ARRAY null; 27 PROFILED_RECORD_COUNT NUMBER(38 null; 28 SOURCE_LOAD_BATCH_ID
VARCHAR null; 29 IS_CURRENT BOOLEAN not null default TRUE; 30 PROFILED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

**DM_PADM_SEGMENT**: 1 SEGMENT_ID VARCHAR not null; 2 SEGMENT_NAME VARCHAR not null;
3 SOURCE_NAME VARCHAR null; 4 SCORE_TYPE VARCHAR not null; 5 SCORE_MIN NUMBER(10 not null;
6 SCORE_MAX NUMBER(10 not null; 7 PROSPECT_SEGMENT_TYPE VARCHAR not null; 8 ANNUAL_FEE VARCHAR
null; 9 NETWORK VARCHAR null; 10 MLA_FLAG VARCHAR null (boolean indicator); 11 MAIL_REMAIL
VARCHAR null; 12 RESPONSE_MODEL_TYPE VARCHAR null; 13 RISK_SCORE_TYPE VARCHAR null;
14 ACTIVE_FLAG BOOLEAN not null default TRUE; 15 VALID_FROM DATE not null; 16 VALID_TO DATE
null; 17 ROW_VERSION NUMBER(38 not null default 1; 18 CREATED_BY VARCHAR not null default
CURRENT_USER(); 19 CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP();
20 UPDATED_BY VARCHAR not null default CURRENT_USER(); 21 UPDATED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

**DM_PADM_CAMPAIGN_SEGMENT**: 1 CAMPAIGN_SEGMENT_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not
null; 3 SEGMENT_ID VARCHAR not null; 4 WORKING_VERSION_NUMBER NUMBER(10 not null; 5
SEGMENT_STATUS VARCHAR not null default 'ACTIVE'; 6 SOURCE_CAMPAIGN_ID VARCHAR null;
7 SOURCE_SEGMENT_ID VARCHAR null; 8 INITIALIZATION_METHOD VARCHAR not null; 9 VALID_FROM_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP(); 10 VALID_TO_TS TIMESTAMP_NTZ null;
11 IS_CURRENT BOOLEAN not null default TRUE; 12 CHANGE_REASON VARCHAR null; 13 CREATED_BY
VARCHAR not null default CURRENT_USER(); 14 CREATED_TS TIMESTAMP_NTZ not null default
CURRENT_TIMESTAMP(); 15 UPDATED_BY VARCHAR not null default CURRENT_USER(); 16 UPDATED_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_OFFER_SEGMENT_ALLOCATION**: 1 OFFER_SEGMENT_ALLOCATION_ID VARCHAR not null;
2 CAMPAIGN_ID VARCHAR not null; 3 CAMPAIGN_OFFER_ID VARCHAR not null; 4 SEGMENT_ID VARCHAR not
null; 5 WORKING_VERSION_NUMBER NUMBER(10 not null; 6 POPULATION_GROUP_RULE_ID VARCHAR null;
7 POPULATION_DESCRIPTION VARCHAR null; 8 ALLOCATION_STATUS VARCHAR not null default 'ACTIVE';
[9 SOURCE_CAMPAIGN_... cut off at screenshot boundary] 11 INITIALIZATION_METHOD VARCHAR not
null; 12 VALID_FROM_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP(); 13 VALID_TO_TS
TIMESTAMP_NTZ null; 14 IS_CURRENT BOOLEAN not null default TRUE; 15 CHANGE_REASON VARCHAR not
null; 16 CREATED_BY VARCHAR not null default CURRENT_USER(); 17 CREATED_TS TIMESTAMP_NTZ not
null default CURRENT_TIMESTAMP(); 18 UPDATED_BY VARCHAR not null default CURRENT_USER();
19 UPDATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP(). (TRANSCRIPTION UNCERTAIN:
column 9/10 names not visible, screenshot cut.)

**DM_PADM_CAMPAIGN_ASSUMPTION_VERSION**: 1 CAMPAIGN_ASSUMPTION_VERSION_ID VARCHAR not null;
2 CAMPAIGN_ID VARCHAR not null; 3 VERSION_NUMBER NUMBER(10 not null; 4 CPP NUMBER(18 null;
5 UNIT_COST NUMBER(18 null; 6 RATE_ADJUSTMENT NUMBER(18 null; 7 SEASONALITY_REDUCTION NUMBER(18
null; 8 UNWIND_RATE_ADJUSTMENT NUMBER(18 null; 9 EFFECTIVE_FROM_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP(); 10 EFFECTIVE_TO_TS TIMESTAMP_NTZ null; 11 IS_CURRENT BOOLEAN not
null default TRUE; 12 CHANGE_REASON VARCHAR not null; 13 CREATED_BY VARCHAR not null default
CURRENT_USER(); 14 CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_SEGMENT_ASSUMPTION_VERSION**: 1 SEGMENT_ASSUMPTION_VERSION_ID VARCHAR not null;
2 CAMPAIGN_ID VARCHAR not null; 3 SEGMENT_ID VARCHAR not null; 4 VERSION_NUMBER NUMBER(10 not
null; 5 CPP_OVERRIDE NUMBER(18 null; 6 UNIT_COST_OVERRIDE NUMBER(18 null;
7 RATE_ADJUSTMENT_OVERRIDE NUMBER(18 null; 8 SEASONALITY_REDUCTION_OVERRIDE NUMBER(18 null;
9 UNWIND_RATE_ADJUSTMENT_OVERRIDE NUMBER(18 null; 10 EFFECTIVE_FROM_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP(); 11 EFFECTIVE_TO_TS TIMESTAMP_NTZ null; 12 IS_CURRENT BOOLEAN not
null default TRUE; 13 CHANGE_REASON VARCHAR not null; 14 CREATED_BY VARCHAR not null default
CURRENT_USER(); 15 CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_CDE_LOAD_BATCH**: 1 CDE_LOAD_BATCH_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not
null; 3 SEGMENT_ID VARCHAR not null; 4 SOURCE_FILE_NAME VARCHAR not null; 5 SOURCE_FILE_HASH
VARCHAR not null; 6 VERSION_NUMBER NUMBER(10 not null; 7 LOAD_STATUS VARCHAR not null default
'LOADED'; 8 VALIDATION_STATUS VARCHAR not null default 'PENDING'; 9 ACTIVE_FLAG BOOLEAN not null
default FALSE; 10 SOURCE_ROW_COUNT NUMBER(38 null; 11 LOADED_ROW_COUNT NUMBER(38 null;
12 REJECTED_ROW_COUNT NUMBER(38 null; 13 SOURCE_AS_OF_DATE DATE null; 14 CHANGE_REASON VARCHAR
not null; 15 CREATED_BY VARCHAR not null default CURRENT_USER(); 16 CREATED_TS TIMESTAMP_NTZ
not null default CURRENT_TIMESTAMP(); 17 ACTIVATED_BY VARCHAR null; 18 ACTIVATED_TS
TIMESTAMP_NTZ null.

**DM_PADM_CDE_DETAIL**: 1 CDE_DETAIL_ID VARCHAR not null; 2 CDE_LOAD_BATCH_ID VARCHAR not null;
3 CAMPAIGN_ID VARCHAR not null; 4 SEGMENT_ID VARCHAR not null; 5 VANTAGE_SCORE_BAND VARCHAR not
null; 6 TIMES_MAILED_BUCKET VARCHAR not null (meaning: Segment Viewer column dimension 0-9+);
7 TRM10_TIER NUMBER(10 not null; 8 CRS23_SCORE NUMBER(18 null; 9 DISTINCT_EPIN_COUNT NUMBER(38
not null (meaning: raw CDE measure retained from the upload); 10 CREATED_TS TIMESTAMP_NTZ not
null default CURRENT_TIMESTAMP().

**DM_PADM_EMS_RATE_VERSION**: 1 EMS_RATE_VERSION_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not
null; 3 SEGMENT_ID VARCHAR null; 4 RESPONSE_MODEL_TIER NUMBER(10 null (Segment Viewer row dim);
5 TIMES_MAILED_BUCKET VARCHAR null (Segment Viewer column dim 0-9+); 6 VERSION_NUMBER NUMBER(10
not null; 7 EMS_REDUCTION_RATE NUMBER(18 not null (meaning: positive decimal reduction, 0.05 =
reduce by 5 percent); 8 RATE_SOURCE VARCHAR not null; 9 VALID_FROM_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP(); 10 VALID_TO_TS TIMESTAMP_NTZ null; 11 IS_CURRENT BOOLEAN not null
default TRUE; 12 CHANGE_REASON VARCHAR null; 13 CREATED_BY VARCHAR not null default
CURRENT_USER(); 14 CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_SELECTION_WORKING**: 1 CAMPAIGN_ID VARCHAR not null; 2 SEGMENT_ID VARCHAR not null;
3 RESPONSE_MODEL_TIER NUMBER(10 not null; 4 TIMES_MAILED_BUCKET VARCHAR not null; 5
SELECTION_PERCENTAGE NUMBER(18 not null default 0 (stored decimal 0-1); 6 SOURCE_CAMPAIGN_ID
VARCHAR null; 7 SOURCE_SEGMENT_ID VARCHAR null; 8 INITIALIZATION_METHOD VARCHAR not null;
9 IS_DIRTY BOOLEAN not null default FALSE; 10 ROW_VERSION NUMBER(38 not null default 1;
11 UPDATED_BY VARCHAR not null default CURRENT_USER(); 12 UPDATED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

**DM_PADM_SELECTION_SET**: 1 SELECTION_SET_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not null;
3 SEGMENT_ID VARCHAR not null; 4 VERSION_NUMBER NUMBER(10 not null; 5 STATUS VARCHAR not null;
6 SOURCE_CAMPAIGN_ID VARCHAR null; 7 SOURCE_SEGMENT_ID VARCHAR null; 8 IS_CURRENT BOOLEAN not
null default TRUE; 9 IS_FINAL BOOLEAN not null default FALSE; 10 CHANGE_REASON VARCHAR
[remainder not captured].

**DM_PADM_SELECTION_SET_CELL** (only tail columns visible): 3 TIMES_MAILED_BUCKET VARCHAR not
null; 4 SELECTION_PERCENTAGE NUMBER(18 not null (stored decimal 0-1). [columns 1-2 and remainder
not captured in this PDF.]

**DM_PADM_SELECTION_EVENT**: 1 SELECTION_EVENT_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not
null; 3 SEGMENT_ID VARCHAR not null; 4 SELECTION_SET_ID VARCHAR null; 5 ACTION_TYPE VARCHAR not
null; 6 TIER_FROM NUMBER(10 null; 7 TIER_TO NUMBER(10 null; 8 TIMES_MAILED_FROM VARCHAR null;
9 TIMES_MAILED_TO VARCHAR null; 10 ENTERED_PERCENTAGE NUMBER(18 null; 11 CHANGED_CELL_COUNT
NUMBER(38 null; 12 PRIOR_VALUE_SUMMARY VARIANT null; 13 CHANGE_REASON VARCHAR not null;
14 CHANGED_BY VARCHAR not null default CURRENT_USER(); 15 CHANGED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

**DM_PADM_HISTORY_LOAD_BATCH**: 1 HISTORY_LOAD_BATCH_ID VARCHAR not null; 2 HISTORY_TYPE VARCHAR
not null; 3 AS_OF_DATE DATE not null; 4 OBSERVATION_START_DATE DATE not null;
5 OBSERVATION_END_DATE DATE not null; 6 APPLICATION_LOOKBACK_DATE DATE null;
7 PROSPECTING_CUTOFF_DATE DATE null; 8 MAX_MONTHS_ON_BOOK NUMBER(10 null; 9 SOURCE_CODE_VERSION
VARCHAR null; 10 SEGMENT_RULE_VERSION VARCHAR null; 11 UNDERWRITING_RULE_VERSION VARCHAR null;
12 LOAD_STATUS VARCHAR not null default 'LOADED'; 13 SOURCE_ROW_COUNT NUMBER(38 null;
14 LOADED_ROW_COUNT NUMBER(38 [remainder not captured].

**DM_PADM_HISTORY_SEGMENT_MAP** (tail visible, columns 1-2 not captured): 3 SEGMENT_ID VARCHAR
not null; 4 VALID_FROM DATE not null; 5 VALID_TO DATE null; 6 ACTIVE_FLAG BOOLEAN not null
default TRUE; 7 CHANGE_REASON VARCHAR not null; 8 APPROVED_BY VARCHAR null; 9 APPROVED_TS
TIMESTAMP_NTZ null; 10 CREATED_BY VARCHAR not null default CURRENT_USER(); 11 CREATED_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_NRR_HISTORY_CELL**: 1 NRR_HISTORY_CELL_ID VARCHAR not null; 2 HISTORY_LOAD_BATCH_ID
VARCHAR not null; 3 HISTORY_SEGMENT_KEY_ID VARCHAR not null; 4 CAMPAIGN_TYPE VARCHAR not null;
5 RESPONSE_MODEL_TIER NUMBER(10 not null; 6 TIMES_MAILED_BUCKET VARCHAR not null;
7 OBSERVATION_CAMPAIGN_DATE DATE null; 8 OFFER_CODE VARCHAR null; 9 MAIL_QUANTITY NUMBER(38 not
null; 10 APPLIED_COUNT NUMBER(38 not null; 11 BOARDED_COUNT NUMBER(38 not null; 12 CREATED_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_UNWIND_HISTORY_CELL**: 1 UNWIND_HISTORY_CELL_ID VARCHAR not null; 2
HISTORY_LOAD_BATCH_ID VARCHAR not null; 3 HISTORY_SEGMENT_KEY_ID VARCHAR not null;
4 CAMPAIGN_TYPE VARCHAR not null; 5 RESPONSE_MODEL_TIER NUMBER(10 not null; 6
TIMES_MAILED_BUCKET VARCHAR not null; 7 OBSERVATION_CAMPAIGN_DATE DATE null; 8 OFFER_CODE
VARCHAR null; 9 BOARD_COUNT NUMBER(38 not null; 10 UNWIND_COUNT NUMBER(38 not null; 11
CREATED_TS TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP().

**DM_PADM_CALCULATION_RUN**: 1 CALCULATION_RUN_ID VARCHAR not null; 2 CAMPAIGN_ID VARCHAR not
null; 3 CAMPAIGN_WORKING_VERSION_NUMBER NUMBER(10 not null; 4 CAMPAIGN_ASSUMPTION_VERSION_ID
VARCHAR null; 5 CALCULATION_STATUS VARCHAR not null default 'STARTED'; 6 SOURCE_DATA_AS_OF_TS
TIMESTAMP_NTZ not null default CURRENT_TIMESTAMP(); 7 CALCULATION_STARTED_TS TIMESTAMP_NTZ not
null default CURRENT_TIMESTAMP(); 8 CALCULATION_COMPLETED_TS TIMESTAMP_NTZ null; 9
CALCULATED_BY VARCHAR not null default CURRENT_USER().

**DM_PADM_CALCULATION_CELL**: 1 CALCULATION_CELL_ID VARCHAR not null; 2 CALCULATION_RUN_ID
VARCHAR not null; 3 CAMPAIGN_ID VARCHAR not null; 4 SEGMENT_ID VARCHAR not null;
5 RESPONSE_MODEL_TIER NUMBER(10 not null; 6 TIMES_MAILED_BUCKET VARCHAR not null;
7 CDE_VOLUME NUMBER(38 null; 8 EMS_REDUCTION_RATE NUMBER(18 null (0.05 = reduce by 5%);
9 POST_EMS_VOLUME NUMBER(38 null; 10 SELECTION_PERCENTAGE NUMBER(18 null (stored decimal 0-1);
11 SELECTED_QUANTITY NUMBER(38 null; 12 BASE_NRR NUMBER(18 null; 13 EFFECTIVE_NRR NUMBER(18
null; 14 SELECTED_NRR NUMBER(18 null; 15 HISTORICAL_UNWIND_RATE NUMBER(18 null;
16 BOOKED_PRE_UNWIND_UNIVERSE NUMBER(38 null; 17 BOOKED_PRE_UNWIND_SELECTED NUMBER(38 null;
18 MARKETING_COST_UNIVERSE NUMBER(38 null [exact col 18 name partially obscured by cursor in
screenshot, TRANSCRIPTION UNCERTAIN]; ...; 22 EXPECTED_UNWINDS_UNIVERSE NUMBER(38 null;
23 EXPECTED_UNWINDS_SELECTED NUMBER(38 null; 24 BOOKED_POST_UNWIND_UNIVERSE NUMBER(38 null;
25 BOOKED_POST_UNWIND_SELECTED NUMBER(38 null; 26 PRE_UNWIND_CPA_UNIVERSE NUMBER(38 null;
27 PRE_UNWIND_CPA_SELECTED NUMBER(38 null; 28 POST_UNWIND_CPA_UNIVERSE NUMBER(38 null;
29 POST_UNWIND_CPA_SELECTED NUMBER(38 null; 30 CREATED_TS TIMESTAMP_NTZ not null default
CURRENT_TIMESTAMP(). (TRANSCRIPTION UNCERTAIN: columns 19-21 between
MARKETING_COST_UNIVERSE and EXPECTED_UNWINDS_UNIVERSE were not clearly legible — likely
MARKETING_COST_SELECTED, BOOKING_COST_UNIVERSE/SELECTED per the spec's formula names, but not
confirmed from this screenshot, do not assume.)

**DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT**: 1 SIGNATURE_PAGE_2_SNAPSHOT_ID VARCHAR not null;
2 CAMPAIGN_ID VARCHAR not null; 3 CALCULATION_RUN_ID VARCHAR not null; 4
SIGNATURE_VERSION_NUMBER NUMBER(10 not null; 5 CAMPAIGN_OFFER_ID VARCHAR not null; 6 SEGMENT_ID
VARCHAR not null; 7 POPULATION_DESCRIPTION VARCHAR null; 8 SEGMENT_DESCRIPTION VARCHAR null;
9 ANNUAL_FEE VARCHAR null; 10 TEST_TYPE VARCHAR null; 11 NETWORK VARCHAR null;
12 CREDIT_BUREAU_MODEL VARCHAR null; 13 CREDIT_BUREAU_SCORE VARCHAR null; 14 CRS_MODEL VARCHAR
null; 15 CRS_SCORE VARCHAR null; 16 NRM VARCHAR null; 17 QUANTITY NUMBER(38 null; 18 NBR
NUMBER(18 null; 19 BOARDS NUMBER(38 null; 20 CPP NUMBER(18 null; 21 MARKETING_EXPENSE NUMBER(38
null; 22 UNWIND_RATE NUMBER(18 null; 23 PRE_UNWIND_CPA NUMBER(38 null; 24 POST_UNWIND_CPA
NUMBER(38 null; 25 PROMO VARCHAR null; 26 IVR VARCHAR null; 27 UNDERWRITING_FLAG VARCHAR null
(boolean indicator); 28 PROSPECT_TYPE VARCHAR null; 29 TIMES_MAILED_0_PERCENTAGE NUMBER(18 null;
30 TIERS VARCHAR null; 31 PRINT_VENDOR VARCHAR null; 32 POST_UNWIND_BOARDS NUMBER(38 null;
33 MARKETING_PLUS_BOOKING_COSTS NUMBER(38 null; 34 SNAPSHOT_STATUS VARCHAR not null;
35 CREATED_BY VARCHAR not null default CURRENT_USER(); 36 CREATED_TS TIMESTAMP_NTZ not null
default CURRENT_TIMESTAMP().

## Views tab (View / Inputs / Output Grain / Logic / Consumer) — full list, 12 views
VW_PADM_ACM_CAMPAIGN_CANDIDATE | T_ACM_CAMPAIGN_OFFERS | Reporting month + MAIN/REMAIL |
Discovers eligible modern ACM campaigns; PADM maps to MAIN, MAP/PAREMAIL map to REMAIL | Campaign
discovery MERGE.
VW_PADM_ACM_OFFER_SOURCE | T_ACM_CAMPAIGN_OFFERS + T_ACM_PROGRAMS | Source campaign
identification code + offer code | Filters active Mail offers and joins Program by Program Code
+ Program Version | Source snapshot loader.
VW_PADM_CAMPAIGN_CURRENT | DM_PADM_CAMPAIGN | Campaign ID | Current campaign contract |
Application campaign list and details.
VW_PADM_CAMPAIGN_OFFER_CURRENT | Offer + current source version | Campaign + offer | Returns
only current source-version offers | Signature Page source.
VW_PADM_CAMPAIGN_ASSUMPTION_CURRENT | Campaign assumption versions | Campaign | Returns the one
current Campaign assumption | Effective assumptions.
VW_PADM_SEGMENT_ASSUMPTION_CURRENT | Segment assumption versions | Campaign + Segment | Returns
the one current Segment override | Effective assumptions.
VW_PADM_EFFECTIVE_ASSUMPTION | Campaign Segment + current assumptions | Campaign + Segment |
Segment override then Campaign default | Calculation view.
VW_PADM_CDE_GRID_CURRENT | Raw CDE detail + active batch | Campaign + Segment + Tier + TM |
Aggregates raw score and CRS detail to the displayed grid | Segment Viewer.
VW_PADM_SELECTION_CURRENT | Selection working | Campaign + Segment + Tier + TM | Current
editable selection matrix and lineage | Calculation view.
VW_PADM_NRR_CURRENT | NRR history + approved maps | Segment + type + Tier + TM plus fallback |
Exact NRR plus Segment/type fallback | Calculation view.
VW_PADM_UNWIND_CURRENT | Unwind history + approved maps | Segment + type + Tier + TM plus
fallback | Exact unwind plus Segment/type fallback | Calculation view.
VW_PADM_SEGMENT_CALCULATION_CURRENT | CDE + EMS + selection + assumption + history | Campaign +
Segment + Tier + TM | Canonical live Universe and Selected calculations | Segment Viewer and
Signature Page 2.

NOTE: this view-name list is DIFFERENT from (does not include) several real confirmed views named
elsewhere in this project, e.g. VW_PADM_SIGNATURE_PAGE_LIVE, VW_PADM_SIGNATURE_PAGE_ALL,
VW_PADM_ACM_CAMPAIGN_CANDIDATE (matches). As with the Run Order's naming scheme, treat this as
possibly an earlier design draft rather than assuming it supersedes already-confirmed real view
names -- flag for cross-check, don't let it silently overwrite already-verified definitions.

## campaign_queries.py (dead app/ tree) — 2 more functions seen, cross-reference only
`campaigns(session)`: `SELECT CAMPAIGN_ID, CAMPAIGN_YEAR, CAMPAIGN_MONTH, REPORTING_MONTH,
CAMPAIGN_SEQUENCE, CAMPAIGN_TYPE, CAMPAIGN_DISPLAY_NAME, SOURCE_MIN_MAIL_DATE,
SOURCE_MAX_MAIL_DATE, STATUS, ACTIVE_FLAG, SOURCE_CHANGE_PENDING_FLAG,
CURRENT_SOURCE_VERSION_NUMBER, CURRENT_WORKING_VERSION_NUMBER, ROW_VERSION, UPDATED_BY,
UPDATED_TS FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 ORDER BY REPORTING_MONTH DESC, CAMPAIGN_TYPE`
(matches/confirms the column list already in NOTES_from_queries7.md; note dead-tree table name is
`DM_PADM_CAMPAIGN_1`, trailing `_1`, vs. this PDF's Column Dictionary which names it
`DM_PADM_CAMPAIGN` with no suffix — likely the same object at different project stages, flag for
cross-check).

`campaign_source_summary(session, campaign_id)`: counts current source version/component/offer/
profile rows for one campaign —
```sql
SELECT C.CAMPAIGN_ID, C.REPORTING_MONTH, C.CAMPAIGN_TYPE,
       COUNT(DISTINCT V.CAMPAIGN_SOURCE_VERSION_ID) AS CURRENT_SOURCE_VERSION_COUNT,
       COUNT(DISTINCT SC.CAMPAIGN_SOURCE_COMPONENT_ID) AS SOURCE_COMPONENT_COUNT,
       COUNT(DISTINCT O.CAMPAIGN_OFFER_ID) AS OFFER_COUNT,
       COUNT(DISTINCT P.CAMPAIGN_OFFER_PROFILE_ID) AS OFFER_PROFILE_COUNT
FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 AS C
LEFT JOIN {SCHEMA}.DM_PADM_CAMPAIGN_SOURCE_VERSION AS V
    ON C.CAMPAIGN_ID = V.CAMPAIGN_ID AND V.IS_CURRENT = TRUE
LEFT JOIN {SCHEMA}.DM_PADM_CAMPAIGN_SOURCE_COMPONENT AS SC
    ON V.CAMPAIGN_SOURCE_VERSION_ID = SC.CAMPAIGN_SOURCE_VERSION_ID
LEFT JOIN {SCHEMA}.DM_PADM_CAMPAIGN_OFFER AS O
    ON V.CAMPAIGN_SOURCE_VERSION_ID = O.CAMPAIGN_SOURCE_VERSION_ID AND O.IS_CURRENT = TRUE
LEFT JOIN {SCHEMA}.DM_PADM_CAMPAIGN_OFFER_PROFILE AS P
    ON O.CAMPAIGN_OFFER_ID = P.CAMPAIGN_OFFER_ID AND P.IS_CURRENT = TRUE
WHERE C.CAMPAIGN_ID = ?
GROUP BY C.CAMPAIGN_ID, C.REPORTING_MONTH, C.CAMPAIGN_TYPE
```
This confirms the join keys: SOURCE_VERSION joins CAMPAIGN on CAMPAIGN_ID (+IS_CURRENT);
SOURCE_COMPONENT joins SOURCE_VERSION on CAMPAIGN_SOURCE_VERSION_ID; OFFER joins SOURCE_VERSION
on CAMPAIGN_SOURCE_VERSION_ID (+IS_CURRENT); OFFER_PROFILE joins OFFER on CAMPAIGN_OFFER_ID
(+IS_CURRENT). This is corroborating evidence (from dead code), not authoritative DDL.
