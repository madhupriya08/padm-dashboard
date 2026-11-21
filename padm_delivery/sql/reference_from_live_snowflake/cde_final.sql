-- NOTE: this file's VW_PADM_CDE_GRID_CURRENT definition reads from VW_PADM_CDE_DETAIL_CURRENT.
-- A SECOND, DIFFERENT definition of the same view name appears in current_state_views.sql
-- (reading directly from DM_PADM_CDE_DETAIL + DM_PADM_CDE_LOAD_BATCH instead). Since
-- CREATE OR REPLACE means whichever runs last wins, confirm the real execution order between
-- these two files before assuming either is "the" definition.
USE DATABASE DB_RISK;
USE SCHEMA RISK_SBX;

-- It retains the active CDE batch and version used by each grid cell.

CREATE OR REPLACE VIEW VW_PADM_CDE_GRID_CURRENT
AS
SELECT
      D.CDE_LOAD_BATCH_ID
    , D.CDE_VERSION_NUMBER
    , D.CAMPAIGN_ID
    , D.SEGMENT_ID
    , D.TRM10_TIER AS RESPONSE_MODEL_TIER
    , D.TIMES_MAILED_BUCKET
    , SUM(D.DISTINCT_EPIN_COUNT)::NUMBER(38,6) AS CDE_VOLUME
FROM VW_PADM_CDE_DETAIL_CURRENT AS D
GROUP BY
      D.CDE_LOAD_BATCH_ID
    , D.CDE_VERSION_NUMBER
    , D.CAMPAIGN_ID
    , D.SEGMENT_ID
    , D.TRM10_TIER
    , D.TIMES_MAILED_BUCKET;

-- Confirm the final view contract.

SELECT
      ORDINAL_POSITION
    , COLUMN_NAME
    , DATA_TYPE
FROM DB_RISK.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'RISK_SBX'
  AND TABLE_NAME = 'VW_PADM_CDE_GRID_CURRENT'
ORDER BY ORDINAL_POSITION;

-- Confirm one active grid lineage per Campaign and Segment.
-- Expected: no rows.
SELECT
      CAMPAIGN_ID
    , SEGMENT_ID
    , COUNT(DISTINCT CDE_LOAD_BATCH_ID) AS ACTIVE_BATCH_COUNT
FROM VW_PADM_CDE_GRID_CURRENT
GROUP BY
      CAMPAIGN_ID
    , SEGMENT_ID
HAVING COUNT(DISTINCT CDE_LOAD_BATCH_ID) > 1;
