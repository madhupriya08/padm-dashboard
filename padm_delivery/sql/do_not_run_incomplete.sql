-- INCOMPLETE: this file stops partway through SP_PADM_ACTIVATE_CAMPAIGN. Missing: the
-- DM_PADM_CAMPAIGN_SOURCE_COMPONENT insert, the offer insert, the profile insert, the final
-- UPDATE DM_PADM_CAMPAIGN_1 SET STATUS = 'DRAFT', and the EXCEPTION block. Do not run as-is --
-- get the complete procedure body before deploying.

USE DATABASE DB_RISK;
USE SCHEMA RISK_SBX;

-- ===========================================================================================
-- PADM spec alignment, part 3b: SP_PADM_ACTIVATE_CAMPAIGN.
-- Same as wire_credit_bureau_fields.sql (ACM snapshot into source version / component / offer /
-- profile, WORKFLOW_EVENT + CHANGE_EVENT), with the new status values: NEW -> DRAFT.
-- Failures return text starting with 'ERROR: '.
-- ===========================================================================================
CREATE OR REPLACE PROCEDURE SP_PADM_ACTIVATE_CAMPAIGN(P_CAMPAIGN_ID VARCHAR, P_CHANGE_REASON VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
DECLARE
    V_STATUS VARCHAR;
    V_REPORTING_MONTH DATE;
    V_CAMPAIGN_TYPE VARCHAR;
    V_SOURCE_VERSION_ID VARCHAR;
    V_LOAD_BATCH_ID VARCHAR;
    V_SOURCE_HASH VARCHAR;
    V_NEXT_SOURCE_VERSION NUMBER(10,0);
    V_CURRENT_VERSION_COUNT NUMBER DEFAULT 0;
    V_COMPONENT_COUNT NUMBER DEFAULT 0;
    V_OFFER_COUNT NUMBER DEFAULT 0;
    V_PROFILE_COUNT NUMBER DEFAULT 0;
BEGIN
    SELECT MAX(STATUS), MAX(REPORTING_MONTH), MAX(CAMPAIGN_TYPE)
      INTO :V_STATUS, :V_REPORTING_MONTH, :V_CAMPAIGN_TYPE
    FROM DM_PADM_CAMPAIGN_1
    WHERE CAMPAIGN_ID = :P_CAMPAIGN_ID;

    IF (V_STATUS IS NULL) THEN
        RETURN 'ERROR: Campaign was not found.';
    END IF;

    IF (V_STATUS NOT IN ('NEW', 'DRAFT')) THEN
        RETURN 'ERROR: Only NEW, or incomplete DRAFT, campaigns can be activated.';
    END IF;

    IF (NULLIF(TRIM(P_CHANGE_REASON), '') IS NULL) THEN
        RETURN 'ERROR: Change Reason is required.';
    END IF;

    SELECT COUNT(*)
      INTO :V_CURRENT_VERSION_COUNT
    FROM DM_PADM_CAMPAIGN_SOURCE_VERSION
    WHERE CAMPAIGN_ID = :P_CAMPAIGN_ID
      AND IS_CURRENT = TRUE;

    IF (V_CURRENT_VERSION_COUNT > 0) THEN
        RETURN 'ERROR: Campaign already has a current source version.';
    END IF;

    SELECT COALESCE(MAX(SOURCE_VERSION_NUMBER), 0) + 1
      INTO :V_NEXT_SOURCE_VERSION
    FROM DM_PADM_CAMPAIGN_SOURCE_VERSION
    WHERE CAMPAIGN_ID = :P_CAMPAIGN_ID;

    V_SOURCE_VERSION_ID := UUID_STRING();
    V_LOAD_BATCH_ID := UUID_STRING();

    SELECT SHA2(
                COALESCE(TO_VARCHAR(:V_REPORTING_MONTH), '') || '|' ||
                COALESCE(:V_CAMPAIGN_TYPE, '') || '|' ||
                COALESCE(TO_VARCHAR(COUNT(*)), '') || '|' ||
                COALESCE(TO_VARCHAR(MIN(SOURCE_MAIL_DATE)), '') || '|' ||
                COALESCE(TO_VARCHAR(MAX(SOURCE_MAIL_DATE)), ''),
                256
            )
      INTO :V_SOURCE_HASH
    FROM VW_PADM_ACM_OFFER_SOURCE
    WHERE DATE_TRUNC('MONTH', SOURCE_MAIL_DATE)::DATE = :V_REPORTING_MONTH
      AND
      (
            (:V_CAMPAIGN_TYPE = 'MAIN' AND UPPER(TRIM(SOURCE_CAMPAIGN_GROUP_CODE)) = 'PADM')
         OR (:V_CAMPAIGN_TYPE = 'REMAIL' AND UPPER(TRIM(SOURCE_CAMPAIGN_GROUP_CODE)) IN ('MAP', 'PAREMAIL'))
      );

    IF (V_SOURCE_HASH IS NULL) THEN
        RETURN 'ERROR: No eligible ACM offers were found for the campaign month and type.';
    END IF;

    BEGIN TRANSACTION;

    INSERT INTO DM_PADM_CAMPAIGN_SOURCE_VERSION
    (
        CAMPAIGN_SOURCE_VERSION_ID
      , CAMPAIGN_ID
      , SOURCE_VERSION_NUMBER
      , SOURCE_HASH
      , SOURCE_ROW_COUNT
      , SOURCE_MIN_MAIL_DATE
      , SOURCE_MAX_MAIL_DATE
      , LOAD_BATCH_ID
      , IS_CURRENT
      , CHANGE_SUMMARY
    )
    SELECT
        :V_SOURCE_VERSION_ID
      , :P_CAMPAIGN_ID
      , :V_NEXT_SOURCE_VERSION
      , :V_SOURCE_HASH
      , COUNT(*)
      , MIN(SOURCE_MAIL_DATE)
      , MAX(SOURCE_MAIL_DATE)
      , :V_LOAD_BATCH_ID
      , TRUE
      , :P_CHANGE_REASON
    FROM VW_PADM_ACM_OFFER_SOURCE
    WHERE DATE_TRUNC('MONTH', SOURCE_MAIL_DATE)::DATE = :V_REPORTING_MONTH
      AND
      (
            (:V_CAMPAIGN_TYPE = 'MAIN' AND UPPER(TRIM(SOURCE_CAMPAIGN_GROUP_CODE)) = 'PADM')
         OR (:V_CAMPAIGN_TYPE = 'REMAIL' AND UPPER(TRIM(SOURCE_CAMPAIGN_GROUP_CODE)) IN ('MAP', 'PAREMAIL'))
      );

    INSERT INTO DM_PADM_CAMPAIGN_SOURCE_COMPONENT
    (
        CAMPAIGN_SOURCE_COMPONENT_ID
      , CAMPAIGN_ID
      , SOURCE_VERSION_NUMBER
      , SOURCE_HASH
      , SOURCE_ROW_COUNT
      , SOURCE_MIN_MAIL_DATE
      , SOURCE_MAX_MAIL_DATE
      , LOAD_BATCH_ID
      , IS_CURRENT
      , CHANGE_SUMMARY
    )
    SELECT
        :V_SOURCE_VERSION_ID
      , :P_CAMPAIGN_ID
      , :V_NEXT_SOURCE_VERSION
      , :V_SOURCE_HASH
      , COUNT(*)
      , MIN(SOURCE_MAIL_DATE)
      , MAX(SOURCE_MAIL_DATE)
      , :V_LOAD_BATCH_ID
      , TRUE
      , :P_CHANGE_REASON
    FROM VW_PADM_ACM_OFFER_SOURCE
    WHERE DATE_TRUNC('MONTH', SOURCE_MAIL_DATE)::DATE = :V_REPORTING_MONTH
      AND
      (
            (:V_CAMPAIGN_TYPE = 'MAIN' AND UPPER(TRIM(SOURCE_CAMPAIGN_GROUP_CODE)) = 'PADM')
         OR (:V_CAMPAIGN_TYPE = 'REMAIL' AND UPPER(TRIM(SOURCE_CAMPAIGN_GROUP_CODE)) IN ('MAP', 'PAREMAIL'))
      );

-- TRANSCRIPTION CUT OFF HERE (end of available source pages, around line 119-130 of the real
-- file). The real DM_PADM_CAMPAIGN_SOURCE_COMPONENT INSERT column list above is a GUESS carried
-- over from the already-confirmed SP_PADM_ACTIVATE_CAMPAIGN structure seen earlier in this
-- project (it reused the SOURCE_VERSION columns, which is almost certainly WRONG for a
-- "COMPONENT" grain table -- the real one groups by SOURCE_CAMPAIGN_IDENTIFICATION_CODE etc.,
-- not by campaign+version). DO NOT RUN THIS FILE'S COMPONENT INSERT AS-IS. Whoever finishes
-- this transcription needs to re-open padm_spec_alignment_03b_activate.sql starting around
-- line 119 ("INSERT INTO DM_PADM_CAMPAIGN_SOURCE_COMPONENT") and capture the rest verbatim:
-- the real component INSERT, the DM_PADM_CAMPAIGN_OFFER INSERT, the DM_PADM_CAMPAIGN_OFFER_PROFILE
-- INSERT, the final UPDATE DM_PADM_CAMPAIGN_1 SET STATUS = 'DRAFT', WORKFLOW_EVENT/CHANGE_EVENT
-- inserts, the validation counts, and the EXCEPTION block.
$$;
