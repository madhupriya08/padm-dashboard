# Notes from "Sql database queries 7.pdf" (14 pages, fully read)

This PDF was NOT fresh SQL DDL as its filename implies -- it was a workspace walkthrough of the
OLD, dead `app/` tree (already captured elsewhere in padm_delivery as app_pages/campaign_setup.py
etc.) plus a fragment of `source_views.sql` (captured in source_views.sql in this same staging
folder) plus a file-tree/requirements.txt view.

## Confirmed file tree (sql/ folder), as shown in the editor sidebar
00_context.sql, activation_and_validations.sql, assumption_tables.sql,
calculation_and_snapshot_tables.sql, calculation_views.sql, campaign_and_offer_tables.sql,
campaign_load_templates.sql, cde_ems_tables.sql, cde_final.sql, changes.sql,
current_state_views.sql, history_tables.sql, operational_procedures.sql,
post_deployment_validations.sql, reference_and_audit_tables.sql,
segment_and_allocation_tables.sql, selection_tables.sql, signature_page_2_snapshot.sql,
source_views.sql, validations (3).sql, requirements.txt, streamlit_app.py

Note: `00_context.sql` is a file not previously known about -- likely just `USE DATABASE
DB_RISK; USE SCHEMA RISK_SBX;` boilerplate, but unconfirmed, never seen its actual content.

## requirements.txt (full, confirmed)
```
streamlit
snowflake-snowpark-python
pandas
openpyxl
```

## DM_PADM_CAMPAIGN_1 column list (cross-reference only, from dead app/campaign_repository.py's
discover_campaign() MERGE -- NOT from this file's own DDL, so treat as corroborating evidence,
not authoritative)
CAMPAIGN_ID, CAMPAIGN_YEAR, CAMPAIGN_MONTH, REPORTING_MONTH, CAMPAIGN_SEQUENCE, CAMPAIGN_TYPE,
CAMPAIGN_DISPLAY_NAME, SOURCE_MIN_MAIL_DATE, SOURCE_MAX_MAIL_DATE, STATUS, ACTIVE_FLAG,
SOURCE_CHANGE_PENDING_FLAG, CURRENT_SOURCE_VERSION_NUMBER, CURRENT_WORKING_VERSION_NUMBER,
ROW_VERSION, CREATED_BY, CREATED_TS, UPDATED_BY, UPDATED_TS.

This CONFIRMS both CURRENT_SOURCE_VERSION_NUMBER and CURRENT_WORKING_VERSION_NUMBER exist as
separate real columns (matches a DESC TABLE result confirmed earlier in the project).

Dead-tree STATUS values used in this old MERGE: 'DISCOVERED', 'DRAFT', 'REOPENED' (3-way IN
check on match) -- this is the OLD status vocabulary from the dead app/ tree, NOT the real
padm/ package's vocabulary (NEW/DRAFT/IN_PROGRESS/PENDING_APPROVAL/APPROVED/REJECTED, per the
user's own spec and the real padm/tabs/campaign_creation.py). Do not confuse the two.

## Nothing else actionable for the 23 target SQL files was found in this PDF.
