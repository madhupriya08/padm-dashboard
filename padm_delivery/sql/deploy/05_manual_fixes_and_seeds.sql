-- One-time fixes and data seeds. Run each section once, in order.
-- Run AFTER 04_segment_source_candidate_rebuild.sql (that file rebuilds the view this one reads).

USE DATABASE DB_RISK;
USE SCHEMA RISK_SBX;

-- ===========================================================================================
-- 1. CPP fix: make it a real segment-level override, not campaign-only.
--    The seed in 01_schema.sql now has the right value for a fresh deploy, but that MERGE
--    only inserts new rows -- it won't touch the CPP row that already exists. Run this instead.
-- ===========================================================================================
UPDATE DM_PADM_ASSUMPTION_DEFINITION
SET ASSUMPTION_LEVEL = 'CAMPAIGN_SEGMENT', UPDATED_BY = CURRENT_USER(), UPDATED_TS = CURRENT_TIMESTAMP()
WHERE ASSUMPTION_CODE = 'CPP';

-- ===========================================================================================
-- 2. Sync governed segments from real ACM/mailfile history into DM_PADM_SEGMENT_1.
--    Same MERGE the "Sync governed segments from source" button on Create Segment runs --
--    use this instead if you'd rather not touch the dashboard. Insert-only, safe to re-run.
-- ===========================================================================================
MERGE INTO DM_PADM_SEGMENT_1 AS T
USING (
    SELECT SUGGESTED_SEGMENT_NAME AS SEGMENT_NAME, SOURCE AS SOURCE_NAME,
           BUREAU_SCORE_TYPE AS SCORE_TYPE, SCORE_MIN, SCORE_MAX,
           COALESCE(PROSPECT_SEGMENT_TYPE, 'ALL') AS PROSPECT_SEGMENT_TYPE,
           ANNUAL_FEE, NETWORK, MLA_FLAG, RESPONSE_MODEL_TYPE, RISK_SCORE_TYPE, MAIL_REMAIL
    FROM VW_PADM_SEGMENT_SOURCE_CANDIDATE
    WHERE SCORE_MIN IS NOT NULL AND SCORE_MAX IS NOT NULL AND SOURCE IS NOT NULL
      AND BUREAU_SCORE_TYPE IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY SOURCE, BUREAU_SCORE_TYPE, SCORE_MIN, SCORE_MAX
        ORDER BY LAST_MAIL_DATE DESC, SOURCE_RECORD_COUNT DESC
    ) = 1
) AS S
ON UPPER(T.SOURCE_NAME) = UPPER(S.SOURCE_NAME) AND UPPER(T.SCORE_TYPE) = UPPER(S.SCORE_TYPE)
   AND T.SCORE_MIN = S.SCORE_MIN AND T.SCORE_MAX = S.SCORE_MAX
WHEN NOT MATCHED THEN INSERT (
    SEGMENT_ID, SEGMENT_NAME, SOURCE_NAME, SCORE_TYPE, SCORE_MIN, SCORE_MAX,
    PROSPECT_SEGMENT_TYPE, ANNUAL_FEE, NETWORK, MLA_FLAG, RESPONSE_MODEL_TYPE,
    RISK_SCORE_TYPE, MAIL_REMAIL, ACTIVE_FLAG, VALID_FROM, ROW_VERSION
) VALUES (
    UUID_STRING(), S.SEGMENT_NAME, S.SOURCE_NAME, S.SCORE_TYPE, S.SCORE_MIN, S.SCORE_MAX,
    S.PROSPECT_SEGMENT_TYPE, S.ANNUAL_FEE, S.NETWORK, S.MLA_FLAG, S.RESPONSE_MODEL_TYPE,
    S.RISK_SCORE_TYPE, S.MAIL_REMAIL, TRUE, CURRENT_DATE(), 1
);

SELECT COUNT(*) AS segment_master_rows FROM DM_PADM_SEGMENT_1 WHERE ACTIVE_FLAG = TRUE;

-- ===========================================================================================
-- 3. Link every active governed segment to every campaign that already exists.
--    Demo convenience, not a production pattern -- idempotent, safe to re-run after step 2
--    finds more segments. Remove segments you don't want from a given campaign via "Remove
--    from Campaign" in Create Segment afterward.
-- ===========================================================================================
INSERT INTO DM_PADM_CAMPAIGN_SEGMENT_1
    (CAMPAIGN_SEGMENT_ID, CAMPAIGN_ID, SEGMENT_ID, WORKING_VERSION_NUMBER, SEGMENT_STATUS,
     INITIALIZATION_METHOD, IS_CURRENT, CHANGE_REASON, ROW_VERSION)
SELECT UUID_STRING(), C.CAMPAIGN_ID, S.SEGMENT_ID, C.CURRENT_WORKING_VERSION_NUMBER, 'ACTIVE',
       'SQL_SEED', TRUE, 'Seeded from governed segment pool for demo', 1
FROM DM_PADM_CAMPAIGN_1 C
CROSS JOIN DM_PADM_SEGMENT_1 S
WHERE S.ACTIVE_FLAG = TRUE
  AND NOT EXISTS (SELECT 1 FROM DM_PADM_CAMPAIGN_SEGMENT_1 CS
                  WHERE CS.CAMPAIGN_ID = C.CAMPAIGN_ID AND CS.SEGMENT_ID = S.SEGMENT_ID AND CS.IS_CURRENT = TRUE);

SELECT COUNT(*) AS campaign_segment_links FROM DM_PADM_CAMPAIGN_SEGMENT_1 WHERE IS_CURRENT = TRUE;
