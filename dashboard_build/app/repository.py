"""Writes (INSERT/UPDATE) and stored-procedure calls for the PADM dashboard.

Every mutation goes through here. Reads needed to decide what to write (e.g. "does this
campaign/segment row already exist") come from app.queries, never from inline SQL here.
"""

import hashlib
import uuid

from app.db import SCHEMA, call_proc, exec_sql
from app import queries

# ---------------------------------------------------------------------------
# Segments / allocation
# ---------------------------------------------------------------------------

def create_segment(session, fields):
    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_SEGMENT_1
            (SEGMENT_ID, SEGMENT_NAME, SCORE_TYPE, SCORE_MIN, SCORE_MAX, PROSPECT_SEGMENT_TYPE,
             ANNUAL_FEE, NETWORK, MLA_FLAG, MAIL_REMAIL, RESPONSE_MODEL_TYPE, RISK_SCORE_TYPE,
             ACTIVE_FLAG)
        VALUES (UUID_STRING(), %(name)s, %(score_type)s, %(score_min)s, %(score_max)s, %(prospect_type)s,
                %(annual_fee)s, %(network)s, %(mla)s, %(mail_remail)s, %(rmt)s, %(rst)s, TRUE)
        """,
        {
            "name": fields["segment_name"],
            "score_type": fields["score_type"],
            "score_min": fields["score_min"],
            "score_max": fields["score_max"],
            "prospect_type": fields["prospect_type"],
            "annual_fee": fields["annual_fee"],
            "network": fields["network"],
            "mla": fields["mla_flag"],
            "mail_remail": fields["mail_remail"],
            "rmt": fields["response_model_type"],
            "rst": fields["risk_score_type"],
        },
    )


def ensure_campaign_segment(session, campaign_id, segment_id, change_reason):
    """Returns the CAMPAIGN_SEGMENT_ID for (campaign, segment), creating it if needed."""
    existing = queries.campaign_segment_id(session, campaign_id, segment_id)
    if not existing.empty:
        return existing.iloc[0]["CAMPAIGN_SEGMENT_ID"]

    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1
            (CAMPAIGN_SEGMENT_ID, CAMPAIGN_ID, SEGMENT_ID, WORKING_VERSION_NUMBER, SEGMENT_STATUS,
             INITIALIZATION_METHOD, IS_CURRENT, CHANGE_REASON)
        VALUES (UUID_STRING(), %(c)s, %(s)s, 1, 'ACTIVE', 'MANUAL_CREATE', TRUE, %(reason)s)
        """,
        {"c": campaign_id, "s": segment_id, "reason": change_reason},
    )


def allocate_offer_to_segment(session, campaign_id, offer_id, segment_id, change_reason):
    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION
            (OFFER_SEGMENT_ALLOCATION_ID, CAMPAIGN_ID, CAMPAIGN_OFFER_ID, SEGMENT_ID,
             WORKING_VERSION_NUMBER, ALLOCATION_STATUS, INITIALIZATION_METHOD, IS_CURRENT, CHANGE_REASON)
        VALUES (UUID_STRING(), %(c)s, %(offer)s, %(seg)s, 1, 'ACTIVE', 'MANUAL_CREATE', TRUE, %(reason)s)
        """,
        {"c": campaign_id, "offer": offer_id, "seg": segment_id, "reason": change_reason},
    )


def set_population_description(session, allocation_id, label, change_reason):
    exec_sql(
        session,
        f"""
        UPDATE {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION
        SET POPULATION_DESCRIPTION = %(label)s, CHANGE_REASON = %(reason)s
        WHERE OFFER_SEGMENT_ALLOCATION_ID = %(id)s
        """,
        {"label": label, "reason": change_reason, "id": allocation_id},
    )


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------

def save_campaign_assumption(session, campaign_id, cpp, unit_cost, rate_adjustment, seasonality, unwind_adj, reason):
    return call_proc(
        session, f"{SCHEMA}.SP_PADM_SAVE_CAMPAIGN_ASSUMPTION",
        [campaign_id, cpp, unit_cost, rate_adjustment, seasonality, unwind_adj, reason],
    )


def save_segment_assumption(session, campaign_id, segment_id, cpp, unit_cost, rate_adjustment, seasonality, unwind_adj, reason):
    return call_proc(
        session, f"{SCHEMA}.SP_PADM_SAVE_SEGMENT_ASSUMPTION",
        [campaign_id, segment_id, cpp, unit_cost, rate_adjustment, seasonality, unwind_adj, reason],
    )


# ---------------------------------------------------------------------------
# CDE grid load
# ---------------------------------------------------------------------------

def ensure_working_grid_initialized(session, campaign_id, segment_id):
    """Seeds DM_PADM_SELECTION_WORKING for every CDE cell the first time a segment is opened."""
    existing = queries.selection_working_grid(session, campaign_id, segment_id)
    if not existing.empty:
        return existing

    cde_cells = queries.cde_tiers_and_buckets(session, campaign_id, segment_id)
    if cde_cells.empty:
        return existing

    prior = queries.prior_selection_cells(session, segment_id, campaign_id)
    prior_lookup = {
        (r.RESPONSE_MODEL_TIER, r.TIMES_MAILED_BUCKET): r.SELECTION_PERCENTAGE for r in prior.itertuples()
    } if not prior.empty else {}
    init_method = "PRIOR_MONTH_COPY" if prior_lookup else "DEFAULT_ZERO"

    for _, cell in cde_cells.iterrows():
        pct = prior_lookup.get((cell["RESPONSE_MODEL_TIER"], cell["TIMES_MAILED_BUCKET"]), 0)
        exec_sql(
            session,
            f"""
            INSERT INTO {SCHEMA}.DM_PADM_SELECTION_WORKING
                (CAMPAIGN_ID, SEGMENT_ID, RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET, SELECTION_PERCENTAGE,
                 INITIALIZATION_METHOD, IS_DIRTY)
            VALUES (%(c)s, %(s)s, %(tier)s, %(bucket)s, %(pct)s, %(method)s, FALSE)
            """,
            {
                "c": campaign_id, "s": segment_id, "tier": int(cell["RESPONSE_MODEL_TIER"]),
                "bucket": cell["TIMES_MAILED_BUCKET"], "pct": float(pct), "method": init_method,
            },
        )
    return queries.selection_working_grid(session, campaign_id, segment_id)


def load_cde_version(session, campaign_id, segment_id, raw_bytes, file_name, score_band, valid_cells, total_rows, reason):
    """Creates a new CDE_LOAD_BATCH + its CDE_DETAIL cells, then activates it. Returns the proc's message."""
    next_version = queries.next_cde_version(session, campaign_id, segment_id)
    load_batch_id = str(uuid.uuid4())
    file_hash = hashlib.sha256(raw_bytes).hexdigest()

    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_CDE_LOAD_BATCH
            (CDE_LOAD_BATCH_ID, CAMPAIGN_ID, SEGMENT_ID, VERSION_NUMBER, SOURCE_FILE_NAME, SOURCE_FILE_HASH,
             LOAD_STATUS, VALIDATION_STATUS, ACTIVE_FLAG, SOURCE_ROW_COUNT, LOADED_ROW_COUNT, REJECTED_ROW_COUNT,
             CHANGE_REASON, VALIDATED_BY, VALIDATED_TS)
        VALUES (%(id)s, %(c)s, %(s)s, %(v)s, %(fname)s, %(fhash)s,
                'LOADED', 'VALID', FALSE, %(total)s, %(loaded)s, %(rejected)s,
                %(reason)s, CURRENT_USER(), CURRENT_TIMESTAMP())
        """,
        {
            "id": load_batch_id, "c": campaign_id, "s": segment_id, "v": next_version,
            "fname": file_name, "fhash": file_hash, "total": int(total_rows),
            "loaded": int(len(valid_cells)), "rejected": int(total_rows - len(valid_cells)), "reason": reason,
        },
    )

    for _, cell in valid_cells.iterrows():
        exec_sql(
            session,
            f"""
            INSERT INTO {SCHEMA}.DM_PADM_CDE_DETAIL
                (CDE_LOAD_BATCH_ID, CAMPAIGN_ID, SEGMENT_ID, VANTAGE_SCORE_BAND, TIMES_MAILED_BUCKET,
                 TRM10_TIER, DISTINCT_EPIN_COUNT)
            VALUES (%(batch)s, %(c)s, %(s)s, %(band)s, %(bucket)s, %(tier)s, %(volume)s)
            """,
            {
                "batch": load_batch_id, "c": campaign_id, "s": segment_id, "band": score_band,
                "bucket": cell["TIMES_MAILED_BUCKET"], "tier": int(cell["TRM10_TIER"]),
                "volume": int(round(cell["DISTINCT_EPIN_COUNT"])),
            },
        )

    result = call_proc(session, f"{SCHEMA}.SP_PADM_ACTIVATE_CDE_VERSION", [load_batch_id, reason])
    return next_version, result


# ---------------------------------------------------------------------------
# Selection grid
# ---------------------------------------------------------------------------

def update_selection_cell(session, campaign_id, segment_id, tier, bucket, new_percentage):
    exec_sql(
        session,
        f"""
        UPDATE {SCHEMA}.DM_PADM_SELECTION_WORKING
        SET SELECTION_PERCENTAGE = %(pct)s, IS_DIRTY = TRUE
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
          AND RESPONSE_MODEL_TIER = %(tier)s AND TIMES_MAILED_BUCKET = %(bucket)s
        """,
        {"pct": new_percentage, "c": campaign_id, "s": segment_id, "tier": int(tier), "bucket": bucket},
    )


def save_selection_set(session, campaign_id, segment_id, change_reason):
    return call_proc(session, f"{SCHEMA}.SP_PADM_SAVE_SELECTION_SET", [campaign_id, segment_id, change_reason])


# ---------------------------------------------------------------------------
# Calculation / workflow / Signature Page 2
# ---------------------------------------------------------------------------

def run_calculation(session, campaign_id):
    """Returns (run_id, cell_count)."""
    result = call_proc(session, f"{SCHEMA}.SP_PADM_RUN_CALCULATION", [campaign_id])
    run_id, cell_count = result.split("|")
    return run_id, cell_count


def generate_signature_page_2(session, campaign_id, calculation_run_id):
    return call_proc(session, f"{SCHEMA}.SP_PADM_GENERATE_SIGNATURE_PAGE_2", [campaign_id, calculation_run_id])


def transition_campaign(session, campaign_id, to_status, reason, comment=""):
    """Calls your pre-existing SP_PADM_TRANSITION_CAMPAIGN (Campaign ID, target status, reason, comment)."""
    return call_proc(session, f"{SCHEMA}.SP_PADM_TRANSITION_CAMPAIGN", [campaign_id, to_status, reason, comment])


def activate_campaign(session, campaign_id, reason):
    """Calls your pre-existing SP_PADM_ACTIVATE_CAMPAIGN (Campaign ID, reason): DISCOVERED/REOPENED -> DRAFT."""
    return call_proc(session, f"{SCHEMA}.SP_PADM_ACTIVATE_CAMPAIGN", [campaign_id, reason])


def discover_campaigns(session):
    """Syncs VW_PADM_ACM_CAMPAIGN_CANDIDATE into DM_PADM_CAMPAIGN_1: inserts new (REPORTING_MONTH,
    CAMPAIGN_TYPE) combos as STATUS='DISCOVERED', and flags SOURCE_CHANGE_PENDING_FLAG on existing
    rows whose source mail-date range has moved since they were discovered.

    Column mapping confirmed from DESC VIEW/DESC TABLE (2026-11-16):
      - VW_PADM_ACM_CAMPAIGN_CANDIDATE.SOURCE_CAMPAIGN_IDENTIFICATION_CODES (plural) is the closest
        match for DM_PADM_CAMPAIGN_1.SOURCE_CAMPAIGN_IDENTIFICATION_CODE (singular) -- no 1:1 name
        match exists, so the delimited list is carried through as-is.
      - SOURCE_IDENTIFICATION_CODE_COUNT / SOURCE_COMPONENT_CODES / SOURCE_COMPONENT_COUNT /
        SOURCE_OFFER_COUNT on the candidate view have no corresponding column on DM_PADM_CAMPAIGN_1
        and are intentionally not persisted here.
      - SOURCE_CAMPAIGN_COUNTER_MIN/MAX exist only on DM_PADM_CAMPAIGN_1, not on the candidate view;
        left NULL at discovery (both columns are nullable).
    """
    exec_sql(
        session,
        f"""
        MERGE INTO {SCHEMA}.DM_PADM_CAMPAIGN_1 AS T
        USING {SCHEMA}.VW_PADM_ACM_CAMPAIGN_CANDIDATE AS S
        ON T.REPORTING_MONTH = S.REPORTING_MONTH AND T.CAMPAIGN_TYPE = S.CAMPAIGN_TYPE
        WHEN MATCHED AND (T.SOURCE_MIN_MAIL_DATE != S.SOURCE_MIN_MAIL_DATE OR T.SOURCE_MAX_MAIL_DATE != S.SOURCE_MAX_MAIL_DATE) THEN
            UPDATE SET T.SOURCE_CHANGE_PENDING_FLAG = TRUE, T.SOURCE_MIN_MAIL_DATE = S.SOURCE_MIN_MAIL_DATE,
                       T.SOURCE_MAX_MAIL_DATE = S.SOURCE_MAX_MAIL_DATE, T.UPDATED_BY = CURRENT_USER(), T.UPDATED_TS = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
            INSERT (CAMPAIGN_ID, SOURCE_CAMPAIGN_IDENTIFICATION_CODE, CAMPAIGN_YEAR, CAMPAIGN_MONTH, REPORTING_MONTH,
                    CAMPAIGN_SEQUENCE, CAMPAIGN_TYPE, CAMPAIGN_DISPLAY_NAME, SOURCE_MIN_MAIL_DATE, SOURCE_MAX_MAIL_DATE,
                    STATUS, ACTIVE_FLAG)
            VALUES (UUID_STRING(), S.SOURCE_CAMPAIGN_IDENTIFICATION_CODES, S.CAMPAIGN_YEAR, S.CAMPAIGN_MONTH, S.REPORTING_MONTH,
                    S.CAMPAIGN_SEQUENCE, S.CAMPAIGN_TYPE, S.CAMPAIGN_DISPLAY_NAME, S.SOURCE_MIN_MAIL_DATE, S.SOURCE_MAX_MAIL_DATE,
                    'DISCOVERED', TRUE)
        """,
    )
