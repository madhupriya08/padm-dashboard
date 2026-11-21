USE DATABASE DB_RISK;
USE SCHEMA RISK_SBX;

-- -------------------------------------------------------------------------------------------
-- Pre Signature Page (2026-11-20): 3 tracking fields carried forward from the previous
-- campaign per offer (Total Available Volume, Quantity, Owner/Approver) -- mirrors the legacy
-- Matrix Creation Tool's merge of the same 3 columns from last month's matrix file, but as a
-- real versioned table joined on OFFER_RESERVATION_CODE instead of a network-share Excel file
-- matched on free-text description.
-- -------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DM_PADM_PRE_SIGNATURE_DETAIL
(
    PRE_SIGNATURE_DETAIL_ID VARCHAR NOT NULL,
    CAMPAIGN_ID VARCHAR NOT NULL,
    CAMPAIGN_OFFER_ID VARCHAR NOT NULL,
    TOTAL_AVAILABLE_VOLUME NUMBER(38,0),
    QUANTITY NUMBER(38,0),
    OWNER_APPROVER VARCHAR,
    IS_CURRENT BOOLEAN NOT NULL DEFAULT TRUE,
    CHANGE_REASON VARCHAR,
    CREATED_BY VARCHAR NOT NULL DEFAULT CURRENT_USER(),
    CREATED_TS TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    VALID_TO_TS TIMESTAMP_NTZ,
    CONSTRAINT PK_PADM_PRE_SIGNATURE_DETAIL PRIMARY KEY (PRE_SIGNATURE_DETAIL_ID)
);
