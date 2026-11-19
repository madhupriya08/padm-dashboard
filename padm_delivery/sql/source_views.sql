-- Merged from 2 transcription passes: Sql database queries 5-6.pdf (lines ~1-395, VW_PADM_ACM_CAMPAIGN_CANDIDATE
-- complete + VW_PADM_ACM_OFFER_SOURCE's start) and Sql database queries 7.pdf (lines ~396-498, the tail end
-- of VW_PADM_ACM_OFFER_SOURCE's WHERE clause + validation queries). A genuine gap exists where they meet:
-- neither pass fully captured lines ~397-426 (part of the WHERE clause) -- both passes independently flagged
-- this, it is not an artifact of this merge. Get a fresh screenshot of exactly that range if it matters.

-- TRANSCRIBED from "Sql database queries 6.pdf" photos of a local VS Code editor
-- (workspace "padm_phase1"), tab "source_views.sql".
-- PARTIAL: captured through line 436 (this PDF ends at page 24, mid-WHERE-clause of
-- VW_PADM_ACM_OFFER_SOURCE). Whatever follows (the rest of this view's WHERE clause, and
-- any further views after it) was NOT captured in this pass -- check later source files
-- (e.g. "Final sql database queries and documentation 1.pdf") for the rest.
USE DATABASE DB_RISK;
USE SCHEMA RISK_SBX;

CREATE OR REPLACE VIEW VW_PADM_ACM_CAMPAIGN_CANDIDATE
AS

WITH ELIGIBLE_OFFER AS
(
    SELECT
        YEAR(
            O.CAMPAIGN_GROUP_MAIL_DATE
        ) AS CAMPAIGN_YEAR

        , MONTH(
            O.CAMPAIGN_GROUP_MAIL_DATE
        ) AS CAMPAIGN_MONTH

        , DATE_TRUNC(
            'MONTH',
            O.CAMPAIGN_GROUP_MAIL_DATE
        )::DATE AS REPORTING_MONTH

        , CASE
            WHEN UPPER(
                TRIM(
                    O.CAMPAIGN_GROUP_CODE
                )
            ) = 'PADM'
            THEN 'MAIN'

            WHEN UPPER(
                TRIM(
                    O.CAMPAIGN_GROUP_CODE
                )
            ) IN (
                'MAP',
                'PAREMAIL'
            )
            THEN 'REMAIL'
        END AS CAMPAIGN_TYPE

        , O.CAMPAIGN_IDENTIFICATION_CODE
            AS SOURCE_CAMPAIGN_IDENTIFICATION_CODE

        , UPPER(
            TRIM(
                O.CAMPAIGN_GROUP_CODE
            )
        ) AS SOURCE_COMPONENT_CODE

        , O.CAMPAIGN_GROUP_MAIL_DATE::DATE
            AS SOURCE_MAIL_DATE

        , TRIM(
            O.CAMPAIGN_OFFER_RESERVATION_CODE
        ) AS OFFER_RESERVATION_CODE

    FROM CSTONE_BIZ.REFERENCE
        .T_ACM_CAMPAIGN_OFFERS AS O

    WHERE O.CAMPAIGN_IDENTIFICATION_CODE
        IS NOT NULL

      AND O.CAMPAIGN_GROUP_MAIL_DATE
        IS NOT NULL

      AND UPPER(
            TRIM(
                O.CAMPAIGN_TYPE_CHANNEL_TYPE
            )
        ) = 'MAIL'

      AND UPPER(
            TRIM(
                O.CAMPAIGN_OFFER_STATUS
            )
        ) = 'ACTIVE'

      AND COALESCE(
            O.CAMPAIGN_OFFER_REMOVED_FLAG,
            FALSE
        ) = FALSE

      AND UPPER(
            TRIM(
                O.CAMPAIGN_GROUP_CODE
            )
        ) IN (
            'PADM',
            'MAP',
            'PAREMAIL'
        )

      AND UPPER(
            TRIM(
                O.PROGRAM_CODE
            )
        ) NOT LIKE 'W%'

      AND LENGTH(
            TRIM(
                O.CAMPAIGN_OFFER_RESERVATION_CODE
            )
        ) <= 6
),

CAMPAIGN_GRAIN AS
(
    SELECT
        CAMPAIGN_YEAR
        , CAMPAIGN_MONTH
        , REPORTING_MONTH
        , CAMPAIGN_TYPE

        , (
            (
                CAMPAIGN_MONTH - 1
            ) * 2
        )
        + CASE
            WHEN CAMPAIGN_TYPE = 'MAIN'
                THEN 1
            WHEN CAMPAIGN_TYPE = 'REMAIL'
                THEN 2
        END AS CAMPAIGN_SEQUENCE

        , LISTAGG(
            DISTINCT
            SOURCE_CAMPAIGN_IDENTIFICATION_CODE,
            ', '
        ) WITHIN GROUP
        (
            ORDER BY
                SOURCE_CAMPAIGN_IDENTIFICATION_CODE
        ) AS SOURCE_CAMPAIGN_IDENTIFICATION_CODES

        , COUNT(
            DISTINCT
            SOURCE_CAMPAIGN_IDENTIFICATION_CODE
        ) AS SOURCE_IDENTIFICATION_CODE_COUNT

        , LISTAGG(
            DISTINCT
            SOURCE_COMPONENT_CODE,
            ', '
        ) WITHIN GROUP
        (
            ORDER BY
                SOURCE_COMPONENT_CODE
        ) AS SOURCE_COMPONENT_CODES

        , COUNT(
            DISTINCT
            SOURCE_COMPONENT_CODE
        ) AS SOURCE_COMPONENT_COUNT

        , MIN(
            SOURCE_MAIL_DATE
        ) AS SOURCE_MIN_MAIL_DATE

        , MAX(
            SOURCE_MAIL_DATE
        ) AS SOURCE_MAX_MAIL_DATE

        , COUNT(
            DISTINCT
            OFFER_RESERVATION_CODE
        ) AS SOURCE_OFFER_COUNT

    FROM ELIGIBLE_OFFER

    WHERE CAMPAIGN_TYPE IS NOT NULL

    GROUP BY
        CAMPAIGN_YEAR
        , CAMPAIGN_MONTH
        , REPORTING_MONTH
        , CAMPAIGN_TYPE
)
SELECT
    CAMPAIGN_YEAR
    , CAMPAIGN_MONTH
    , REPORTING_MONTH
    , CAMPAIGN_SEQUENCE
    , CAMPAIGN_TYPE

    , TO_CHAR(
        REPORTING_MONTH,
        'MMMM YYYY'
    )
    || ' '
    || CASE
        WHEN CAMPAIGN_TYPE = 'MAIN'
            THEN 'Main'
        WHEN CAMPAIGN_TYPE = 'REMAIL'
            THEN 'Remail'
    END
    || ' Campaign'
        AS CAMPAIGN_DISPLAY_NAME

    , SOURCE_CAMPAIGN_IDENTIFICATION_CODES
    , SOURCE_IDENTIFICATION_CODE_COUNT
    , SOURCE_COMPONENT_CODES
    , SOURCE_COMPONENT_COUNT
    , SOURCE_MIN_MAIL_DATE
    , SOURCE_MAX_MAIL_DATE
    , SOURCE_OFFER_COUNT

FROM CAMPAIGN_GRAIN;

CREATE OR REPLACE VIEW
    VW_PADM_ACM_OFFER_SOURCE
AS

SELECT
    O.CAMPAIGN_IDENTIFICATION_CODE
        AS SOURCE_CAMPAIGN_IDENTIFICATION_CODE

    , O.CAMPAIGN_GROUP_CODE
        AS SOURCE_CAMPAIGN_GROUP_CODE

    , O.CAMPAIGN_TYPE_CODE
        AS SOURCE_CAMPAIGN_TYPE_CODE

    , O.CAMPAIGN_TYPE_NAME
        AS SOURCE_CAMPAIGN_TYPE_NAME

    , O.CAMPAIGN_GROUP_DESCRIPTION
        AS SOURCE_CAMPAIGN_GROUP_DESCRIPTION

    , O.CAMPAIGN_GROUP_MAIL_DATE::DATE
        AS SOURCE_MAIL_DATE

    , O.CAMPAIGN_GROUP_START_DATE::DATE
        AS SOURCE_GROUP_START_DATE

    , O.CAMPAIGN_GROUP_END_DATE::DATE
        AS SOURCE_GROUP_END_DATE

    , O.CAMPAIGN_GROUP_RETIRE_DATE::DATE
        AS SOURCE_GROUP_RETIRE_DATE

    , O.CAMPAIGN_GROUP_EXPIRE_DATE::DATE
        AS SOURCE_GROUP_EXPIRE_DATE

    , O.CAMPAIGN_GROUP_LETTER_EXPIRE_DATE::DATE
        AS SOURCE_LETTER_EXPIRE_DATE

    , O.CAMPAIGN_COUNTER
        AS SOURCE_CAMPAIGN_COUNTER

    , O.CAMPAIGN_OFFER_RESERVATION_CODE
        AS OFFER_RESERVATION_CODE

    /*
    Use the offer table as the authoritative source for the
    Program Code and Program Version assigned to the offer.
    */
    , O.PROGRAM_CODE
        AS PROGRAM_CODE

    , O.PROGRAM_VERSION_NUMBER
        AS PROGRAM_VERSION_NUMBER

    , O.CAMPAIGN_CODE
        AS SOURCE_CAMPAIGN_CODE

    , O.CAMPAIGN_NAME
        AS SOURCE_CAMPAIGN_NAME

    , O.CAMPAIGN_DESCRIPTION
        AS SOURCE_CAMPAIGN_DESCRIPTION

    , COALESCE(
        NULLIF(
            TRIM(
                O.CAMPAIGN_OFFER_DESCRIPTION
            ),
            ''
        ),
        NULLIF(
            TRIM(
                O.CAMPAIGN_OFFER_SEGMENT_NAME
            ),
            ''
        )
    ) AS OFFER_DESCRIPTION

    , O.CAMPAIGN_OFFER_SEGMENT_NAME
        AS ACM_SEGMENT_NAME

    , O.CAMPAIGN_OFFER_CONTROL_TEST_DESCRIPTION
        AS TEST_TYPE

    , O.PROSPECT_CREDIT_BUREAU_MODEL
        AS CREDIT_BUREAU_MODEL

    , O.PROSPECT_CREDIT_BUREAU_SCORE
        AS CREDIT_BUREAU_SCORE

    , O.PROSPECT_CRS_MODEL
        AS CRS_MODEL

    , O.PROSPECT_CRS_SCORE
        AS CRS_SCORE

    , O.NET_RESPONSE_MODEL_CODE
        AS NRM

    , O.COST_PER_PIECE::NUMBER(18,6)
        AS SOURCE_CPP

    , O.RESERVATION_CODE_RISK
        AS PROMO

    , O.CAMPAIGN_OFFER_APPROVAL_CODE
        AS IVR

    , O.UNDERWRITING_FLAG
        AS UNDERWRITING_FLAG

    , O.PROSPECT_TYPE
        AS PROSPECT_TYPE

    , O.PRINT_VENDOR_ID
        AS PRINT_VENDOR_ID

    , CASE
        WHEN P.PROGRAM_CODE IS NOT NULL
            THEN 'EXACT_VERSION'

        ELSE 'NO_EXACT_PROGRAM_VERSION'
            END AS PROGRAM_MATCH_STATUS

    , P.PROGRAM_CODE
        AS MATCHED_PROGRAM_CODE

    , P.PROGRAM_VERSION_NUMBER
        AS MATCHED_PROGRAM_VERSION_NUMBER

    , P.ANNUAL_FEE_YR1
        AS ANNUAL_FEE_YR1

    , P.ANNUAL_FEE_YR2
        AS ANNUAL_FEE_YR2

    , CASE
        WHEN P.PROGRAM_CODE IS NOT NULL
            THEN CONCAT(
                TO_VARCHAR(
                    P.ANNUAL_FEE_YR1
                ),
                '/',
                TO_VARCHAR(
                    P.ANNUAL_FEE_YR2
                )
            )
        END AS ANNUAL_FEE

    , P.NETWORK
      AS NETWORK

    , O.CAMPAIGN_OFFER_STATUS
        AS SOURCE_OFFER_STATUS

    , O.CAMPAIGN_OFFER_REMOVED_FLAG
        AS SOURCE_REMOVED_FLAG

    , O.CAMPAIGN_OFFER_REMOVED_DATE::DATE
        AS SOURCE_REMOVED_DATE

    , O.RCD_UUID
        AS SOURCE_RECORD_ID

FROM CSTONE_BIZ.REFERENCE
    .T_ACM_CAMPAIGN_OFFERS AS O

LEFT JOIN CSTONE_BIZ.REFERENCE
        .T_ACM_PROGRAMS AS P

    ON O.PROGRAM_CODE =
        P.PROGRAM_CODE

    AND O.PROGRAM_VERSION_NUMBER =
        P.PROGRAM_VERSION_NUMBER

WHERE O.CAMPAIGN_GROUP_MAIL_DATE IS NOT NULL

  AND UPPER(
        TRIM(
            O.CAMPAIGN_TYPE_CHANNEL_TYPE
        )
    ) = 'MAIL'

  AND UPPER(
        TRIM(
            O.CAMPAIGN_OFFER_STATUS
        )
    ) = 'ACTIVE'

  AND COALESCE(
        O.CAMPAIGN_OFFER_REMOVED_FLAG,
        FALSE
    ) = FALSE

  AND O.CAMPAIGN_IDENTIFICATION_CODE IS NOT NULL

  AND UPPER(
        TRIM(
            O.CAMPAIGN_GROUP_CODE
        )
    ) IN (
        'PADM',
        'MAP',
        'PAREMAIL'
    )

  AND UPPER(
        TRIM(
            O.PROGRAM_CODE
        )
    ) NOT LIKE 'W%'

  AND LENGTH(
        TRIM(
            O.CAMPAIGN_OFFER_RESERVATION_CODE
        )
    )
-- TRANSCRIPTION CUT OFF HERE: "Sql database queries 6.pdf" ends at page 24 (this point),
-- mid-WHERE-clause of VW_PADM_ACM_OFFER_SOURCE (a length comparison, e.g. "<= 6", and
-- whatever FROM/JOIN/closing follows was not captured). Any further views after this one
-- were also not captured.

-- =============================================================
-- CONTINUATION from Sql database queries 7.pdf (see merge note above this file)
-- =============================================================
-- TRANSCRIBED from "Sql database queries 7.pdf" (14 pages, fully read).
-- This fragment shows the TAIL END of source_views.sql (validation queries at the bottom of
-- the file), lines ~396-498 per the editor's own line numbers in the screenshots. The rest of
-- source_views.sql (the actual CREATE VIEW statements for VW_PADM_ACM_CAMPAIGN_CANDIDATE,
-- VW_PADM_ACM_OFFER_SOURCE, etc., presumably lines 1-395) was NOT visible in this PDF.
--
-- TRANSCRIPTION UNCERTAIN: lines 396-426 (between "WHERE O.CAMPAIGN_GROUP_MAIL_DATE IS NOT
-- NULL" and "AND UPPER(...) NOT LIKE 'W%'") were not shown in the screenshots -- there's a
-- visible line-number gap (396 -> 427) in the source editor itself, meaning intervening lines
-- genuinely weren't captured in this pass, not merely cropped from view.

-- ~line 396
WHERE O.CAMPAIGN_GROUP_MAIL_DATE IS NOT NULL
-- TRANSCRIPTION CUT OFF HERE: lines 397-426 not captured in this PDF.
  AND UPPER(
      -- TRANSCRIPTION UNCERTAIN: inner expression of this UPPER(...) not clearly visible
  ) NOT LIKE 'W%'

  AND LENGTH(
      TRIM(
          O.CAMPAIGN_OFFER_RESERVATION_CODE
      )
  ) <= 6;

SELECT
      REPORTING_MONTH
    , CAMPAIGN_TYPE
    , COUNT(*) AS ROW_COUNT

FROM VW_PADM_ACM_CAMPAIGN_CANDIDATE

GROUP BY
      REPORTING_MONTH
    , CAMPAIGN_TYPE

HAVING COUNT(*) > 1;

SELECT
      SOURCE_CAMPAIGN_IDENTIFICATION_CODE
    , OFFER_RESERVATION_CODE
    , COUNT(*) AS ROW_COUNT

FROM VW_PADM_ACM_OFFER_SOURCE

GROUP BY
      SOURCE_CAMPAIGN_IDENTIFICATION_CODE
    , OFFER_RESERVATION_CODE

HAVING COUNT(*) > 1;

SELECT
      PROGRAM_MATCH_STATUS
    , COUNT(*) AS OFFER_ROW_COUNT
    , COUNT(
          DISTINCT PROGRAM_CODE
      ) AS PROGRAM_CODE_COUNT

FROM VW_PADM_ACM_OFFER_SOURCE

GROUP BY
    PROGRAM_MATCH_STATUS

ORDER BY
    PROGRAM_MATCH_STATUS;

SELECT
      REPORTING_MONTH
    , CAMPAIGN_TYPE
    , SOURCE_CAMPAIGN_IDENTIFICATION_CODES
    , SOURCE_IDENTIFICATION_CODE_COUNT
    , SOURCE_COMPONENT_CODES
    , SOURCE_COMPONENT_COUNT
    , SOURCE_MIN_MAIL_DATE
    , SOURCE_MAX_MAIL_DATE
    , SOURCE_OFFER_COUNT

FROM VW_PADM_ACM_CAMPAIGN_CANDIDATE

WHERE SOURCE_IDENTIFICATION_CODE_COUNT > 1

ORDER BY
      REPORTING_MONTH DESC
    , CAMPAIGN_TYPE;
