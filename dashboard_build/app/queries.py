"""Read-only SELECTs for the PADM dashboard. No writes happen here."""

from app.db import SCHEMA, df

# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

def campaign_header(session, campaign_id):
    return df(
        session,
        f"SELECT CAMPAIGN_DISPLAY_NAME, STATUS FROM {SCHEMA}.VW_PADM_CAMPAIGN_CURRENT WHERE CAMPAIGN_ID = %(id)s",
        {"id": campaign_id},
    )


def campaign_current(session, campaign_id):
    return df(
        session,
        f"SELECT * FROM {SCHEMA}.VW_PADM_CAMPAIGN_CURRENT WHERE CAMPAIGN_ID = %(id)s",
        {"id": campaign_id},
    )


def all_campaigns(session):
    return df(
        session,
        f"""
        SELECT CAMPAIGN_ID, CAMPAIGN_DISPLAY_NAME, REPORTING_MONTH, CAMPAIGN_TYPE, STATUS
        FROM {SCHEMA}.VW_PADM_CAMPAIGN_CURRENT
        ORDER BY REPORTING_MONTH DESC, CAMPAIGN_TYPE
        """,
    )


# ---------------------------------------------------------------------------
# Segments (governed master list + per-campaign allocation)
# ---------------------------------------------------------------------------

def existing_segments(session):
    return df(
        session,
        f"""
        SELECT SEGMENT_ID, SEGMENT_NAME, SCORE_TYPE, SCORE_MIN, SCORE_MAX, PROSPECT_SEGMENT_TYPE,
               ANNUAL_FEE, NETWORK, MLA_FLAG, MAIL_REMAIL, RESPONSE_MODEL_TYPE, RISK_SCORE_TYPE
        FROM {SCHEMA}.DM_PADM_SEGMENT_1
        WHERE ACTIVE_FLAG = TRUE
        ORDER BY SEGMENT_NAME
        """,
    )


def segment_score_band(session, segment_id):
    return df(
        session,
        f"SELECT SCORE_MIN, SCORE_MAX FROM {SCHEMA}.DM_PADM_SEGMENT_1 WHERE SEGMENT_ID = %(s)s",
        {"s": segment_id},
    )


def campaign_segments(session, campaign_id):
    """Segments currently active on a campaign (id + name only)."""
    return df(
        session,
        f"""
        SELECT CS.SEGMENT_ID, S.SEGMENT_NAME FROM {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1 CS
        JOIN {SCHEMA}.DM_PADM_SEGMENT_1 S ON CS.SEGMENT_ID = S.SEGMENT_ID
        WHERE CS.CAMPAIGN_ID = %(c)s AND CS.IS_CURRENT = TRUE
        ORDER BY S.SEGMENT_NAME
        """,
        {"c": campaign_id},
    )


def campaign_segments_with_offer_counts(session, campaign_id):
    return df(
        session,
        f"""
        SELECT CS.CAMPAIGN_SEGMENT_ID, CS.SEGMENT_ID, S.SEGMENT_NAME, COUNT(A.CAMPAIGN_OFFER_ID) AS OFFER_COUNT
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1 CS
        JOIN {SCHEMA}.DM_PADM_SEGMENT_1 S ON CS.SEGMENT_ID = S.SEGMENT_ID
        LEFT JOIN {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION A
               ON CS.CAMPAIGN_ID = A.CAMPAIGN_ID AND CS.SEGMENT_ID = A.SEGMENT_ID AND A.IS_CURRENT = TRUE
        WHERE CS.CAMPAIGN_ID = %(campaign_id)s AND CS.IS_CURRENT = TRUE
        GROUP BY CS.CAMPAIGN_SEGMENT_ID, CS.SEGMENT_ID, S.SEGMENT_NAME
        ORDER BY S.SEGMENT_NAME
        """,
        {"campaign_id": campaign_id},
    )


def campaign_segment_id(session, campaign_id, segment_id):
    """Existing DM_PADM_CAMPAIGN_SEGMENT_1 row for this (campaign, segment), if any."""
    return df(
        session,
        f"""
        SELECT CAMPAIGN_SEGMENT_ID, WORKING_VERSION_NUMBER FROM {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s AND IS_CURRENT = TRUE
        """,
        {"c": campaign_id, "s": segment_id},
    )


# ---------------------------------------------------------------------------
# Offer <-> Segment allocation / population description
# ---------------------------------------------------------------------------

def unallocated_offers(session, campaign_id):
    # NOTE: CRS_SCORE only -- confirmed verbatim that VW_PADM_CAMPAIGN_OFFER_CURRENT (and
    # DM_PADM_CAMPAIGN_OFFER itself) never carries a bureau-model/bureau-score field.
    return df(
        session,
        f"""
        SELECT O.CAMPAIGN_OFFER_ID, O.OFFER_RESERVATION_CODE, O.OFFER_DESCRIPTION,
               O.PROSPECT_TYPE, O.CRS_SCORE
        FROM {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT O
        LEFT JOIN {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION A
               ON O.CAMPAIGN_OFFER_ID = A.CAMPAIGN_OFFER_ID AND A.IS_CURRENT = TRUE
        WHERE O.CAMPAIGN_ID = %(campaign_id)s AND A.CAMPAIGN_OFFER_ID IS NULL
        ORDER BY O.OFFER_RESERVATION_CODE
        """,
        {"campaign_id": campaign_id},
    )


def population_allocation_groups(session, campaign_id):
    return df(
        session,
        f"""
        SELECT A.OFFER_SEGMENT_ALLOCATION_ID, O.OFFER_RESERVATION_CODE, O.CRS_SCORE,
               A.SEGMENT_ID, S.SEGMENT_NAME, A.POPULATION_DESCRIPTION
        FROM {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION A
        JOIN {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT O ON A.CAMPAIGN_OFFER_ID = O.CAMPAIGN_OFFER_ID
        JOIN {SCHEMA}.DM_PADM_SEGMENT_1 S ON A.SEGMENT_ID = S.SEGMENT_ID
        WHERE A.CAMPAIGN_ID = %(c)s AND A.IS_CURRENT = TRUE
        ORDER BY O.OFFER_RESERVATION_CODE, O.CRS_SCORE
        """,
        {"c": campaign_id},
    )


def population_subtotal(session, campaign_id, offer_code, score):
    result = df(
        session,
        f"""
        SELECT SUM(QUANTITY) AS QUANTITY, SUM(BOARDS) AS BOARDS
        FROM {SCHEMA}.VW_PADM_SIGNATURE_PAGE_LIVE L
        JOIN {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT O ON L.CAMPAIGN_OFFER_ID = O.CAMPAIGN_OFFER_ID
        WHERE L.CAMPAIGN_ID = %(c)s AND O.OFFER_RESERVATION_CODE = %(code)s
          AND EQUAL_NULL(O.CRS_SCORE, %(score)s)
        """,
        {"c": campaign_id, "code": offer_code, "score": score},
    )
    return result.iloc[0] if not result.empty else None


# ---------------------------------------------------------------------------
# Assumptions (campaign-level + segment-level overrides)
# ---------------------------------------------------------------------------

def campaign_assumption_current(session, campaign_id):
    return df(
        session,
        f"SELECT * FROM {SCHEMA}.VW_PADM_CAMPAIGN_ASSUMPTION_CURRENT WHERE CAMPAIGN_ID = %(c)s",
        {"c": campaign_id},
    )


def campaign_assumption_history(session, campaign_id):
    return df(
        session,
        f"""
        SELECT VERSION_NUMBER, CPP, UNIT_COST, RATE_ADJUSTMENT, SEASONALITY_REDUCTION,
               UNWIND_RATE_ADJUSTMENT, CHANGE_REASON, CREATED_BY, CREATED_TS
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_ASSUMPTION_VERSION
        WHERE CAMPAIGN_ID = %(c)s ORDER BY VERSION_NUMBER DESC
        """,
        {"c": campaign_id},
    )


def segment_assumption_current(session, campaign_id):
    return df(
        session,
        f"""
        SELECT SA.*, S.SEGMENT_NAME FROM {SCHEMA}.VW_PADM_SEGMENT_ASSUMPTION_CURRENT SA
        JOIN {SCHEMA}.DM_PADM_SEGMENT_1 S ON SA.SEGMENT_ID = S.SEGMENT_ID
        WHERE SA.CAMPAIGN_ID = %(c)s
        """,
        {"c": campaign_id},
    )


# ---------------------------------------------------------------------------
# CDE grid (per segment, per campaign)
# ---------------------------------------------------------------------------

def cde_tiers_and_buckets(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT DISTINCT RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET
        FROM {SCHEMA}.VW_PADM_CDE_GRID_CURRENT
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
        """,
        {"c": campaign_id, "s": segment_id},
    )


def active_cde_batch(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT VERSION_NUMBER, SOURCE_FILE_NAME, SOURCE_ROW_COUNT, ACTIVATED_BY, ACTIVATED_TS
        FROM {SCHEMA}.DM_PADM_CDE_LOAD_BATCH
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s AND ACTIVE_FLAG = TRUE
        """,
        {"c": campaign_id, "s": segment_id},
    )


def next_cde_version(session, campaign_id, segment_id):
    result = df(
        session,
        f"""
        SELECT COALESCE(MAX(VERSION_NUMBER), 0) + 1 AS NEXT_VERSION
        FROM {SCHEMA}.DM_PADM_CDE_LOAD_BATCH WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
        """,
        {"c": campaign_id, "s": segment_id},
    )
    return int(result.iloc[0]["NEXT_VERSION"])


# ---------------------------------------------------------------------------
# Selection working grid / prior selections
# ---------------------------------------------------------------------------

def selection_working_grid(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET, SELECTION_PERCENTAGE, IS_DIRTY
        FROM {SCHEMA}.DM_PADM_SELECTION_WORKING
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
        """,
        {"c": campaign_id, "s": segment_id},
    )


def prior_selection_cells(session, segment_id, exclude_campaign_id):
    return df(
        session,
        f"""
        SELECT SC.RESPONSE_MODEL_TIER, SC.TIMES_MAILED_BUCKET, SC.SELECTION_PERCENTAGE
        FROM {SCHEMA}.DM_PADM_SELECTION_SET SS
        JOIN {SCHEMA}.DM_PADM_SELECTION_SET_CELL SC ON SS.SELECTION_SET_ID = SC.SELECTION_SET_ID
        JOIN {SCHEMA}.VW_PADM_CAMPAIGN_CURRENT C ON SS.CAMPAIGN_ID = C.CAMPAIGN_ID
        WHERE SS.SEGMENT_ID = %(seg)s AND SS.CAMPAIGN_ID != %(exclude)s AND SS.IS_CURRENT = TRUE
        ORDER BY C.REPORTING_MONTH DESC
        """,
        {"seg": segment_id, "exclude": exclude_campaign_id},
    )


# ---------------------------------------------------------------------------
# Calculation results / Signature Page
# ---------------------------------------------------------------------------

def segment_calculation_cells(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT * FROM {SCHEMA}.VW_PADM_SEGMENT_CALCULATION_CURRENT
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
        """,
        {"c": campaign_id, "s": segment_id},
    )


def signature_live_grid(session, campaign_id):
    return df(
        session,
        f"""
        SELECT * FROM {SCHEMA}.VW_PADM_SIGNATURE_PAGE_LIVE
        WHERE CAMPAIGN_ID = %(campaign_id)s
        ORDER BY CREDIT_BUREAU_MODEL, CREDIT_BUREAU_SCORE
        """,
        {"campaign_id": campaign_id},
    )


def latest_completed_calculation_run(session, campaign_id):
    return df(
        session,
        f"""
        SELECT CALCULATION_RUN_ID, CALCULATION_STATUS, CALCULATION_COMPLETED_TS
        FROM {SCHEMA}.DM_PADM_CALCULATION_RUN
        WHERE CAMPAIGN_ID = %(c)s AND CALCULATION_STATUS = 'COMPLETED'
        ORDER BY CALCULATION_COMPLETED_TS DESC LIMIT 1
        """,
        {"c": campaign_id},
    )


def signature_page_2_snapshot_versions(session, campaign_id):
    return df(
        session,
        f"""
        SELECT DISTINCT SIGNATURE_VERSION_NUMBER, SNAPSHOT_STATUS, MAX(CREATED_TS) AS CREATED_TS
        FROM {SCHEMA}.DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT
        WHERE CAMPAIGN_ID = %(c)s
        GROUP BY SIGNATURE_VERSION_NUMBER, SNAPSHOT_STATUS
        ORDER BY SIGNATURE_VERSION_NUMBER DESC
        """,
        {"c": campaign_id},
    )


def signature_page_2_snapshot_rows(session, campaign_id, version):
    return df(
        session,
        f"""
        SELECT * FROM {SCHEMA}.DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT
        WHERE CAMPAIGN_ID = %(c)s AND SIGNATURE_VERSION_NUMBER = %(v)s
        ORDER BY CREDIT_BUREAU_MODEL, CREDIT_BUREAU_SCORE
        """,
        {"c": campaign_id, "v": version},
    )
