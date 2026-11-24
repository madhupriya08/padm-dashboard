"""All SQL access for the PADM dashboard (reads and writes).

Writes either CALL a SP_PADM_* procedure (which owns its transaction) or run inside
``db.transaction``. Every user write carries a CHANGE_REASON and runs inside
(before/after values, CURRENT_USER(), timestamp). App-side writes refuse APPROVED campaigns.
"""

import hashlib
import json
import uuid

from padm.db import ACM, SCHEMA, ProcedureError, call_proc, df, exec_sql, rows_affected, transaction

READ_ONLY_STATUS = "APPROVED"
STALE_MESSAGE = "Record changed by another user -- reload."


def _values(row_count, column_count):
    row = "(" + ", ".join(["?"] * column_count) + ")"
    return ", ".join([row] * row_count)


def _assert_editable(session, campaign_id):
    status = campaign_status(session, campaign_id)
    if status is None:
        raise ProcedureError("Campaign was not found.")
    if status == READ_ONLY_STATUS:
        raise ProcedureError("Approved -- read only.")


def _change_event(session, campaign_id, entity_type, entity_id, change_type, before, after, reason):
    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_CHANGE_EVENT
            (CHANGE_EVENT_ID, CAMPAIGN_ID, ENTITY_TYPE, ENTITY_ID, CHANGE_TYPE, BEFORE_VALUE, AFTER_VALUE, CHANGE_REASON)
        SELECT UUID_STRING(), %(c)s, %(et)s, %(eid)s, %(ct)s, PARSE_JSON(%(b)s), PARSE_JSON(%(a)s), %(r)s
        """,
        {"c": campaign_id, "et": entity_type, "eid": str(entity_id), "ct": change_type,
         "b": json.dumps(before, default=str) if before is not None else None,
         "a": json.dumps(after, default=str) if after is not None else None, "r": reason},
    )

# ===============================================================================================
# Campaign (Tab 1) and header
# ===============================================================================================

def campaign_status(session, campaign_id):
    rows = session.sql(f"SELECT STATUS FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 WHERE CAMPAIGN_ID = ?",
                        params=[campaign_id]).collect()
    return rows[0][0] if rows else None


def campaign_header(session, campaign_id):
    return df(
        session,
        f"""
        SELECT CAMPAIGN_ID, CAMPAIGN_DISPLAY_NAME, REPORTING_MONTH, CAMPAIGN_TYPE, STATUS,
               SOURCE_MIN_MAIL_DATE, SOURCE_MAX_MAIL_DATE, SOURCE_CHANGE_PENDING_FLAG,
               CURRENT_WORKING_VERSION_NUMBER, ROW_VERSION
        FROM {SCHEMA}.VW_PADM_CAMPAIGN_CURRENT WHERE CAMPAIGN_ID = %(id)s
        """,
        {"id": campaign_id},
    )


def campaigns(session):
    return df(
        session,
        f"""
        SELECT CAMPAIGN_ID, CAMPAIGN_DISPLAY_NAME, REPORTING_MONTH, CAMPAIGN_TYPE, STATUS,
               CURRENT_WORKING_VERSION_NUMBER, SOURCE_MIN_MAIL_DATE, SOURCE_MAX_MAIL_DATE,
               SOURCE_CHANGE_PENDING_FLAG, UPDATED_BY, UPDATED_TS
        FROM {SCHEMA}.VW_PADM_CAMPAIGN_CURRENT
        ORDER BY REPORTING_MONTH DESC, CAMPAIGN_TYPE
        """,
    )


def campaign_candidate(session, reporting_month, campaign_type):
    """ACM candidate for month + type, LEFT JOIN the PADM campaign (if already created)."""
    return df(
        session,
        f"""
        SELECT C.*, T.CAMPAIGN_ID, T.STATUS, T.SOURCE_CHANGE_PENDING_FLAG
        FROM {SCHEMA}.VW_PADM_ACM_CAMPAIGN_CANDIDATE AS C
        LEFT JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 AS T
               ON T.REPORTING_MONTH = C.REPORTING_MONTH AND T.CAMPAIGN_TYPE = C.CAMPAIGN_TYPE
        WHERE C.REPORTING_MONTH = %(m)s AND C.CAMPAIGN_TYPE = %(t)s
        """,
        {"m": reporting_month, "t": campaign_type},
    )


def candidate_offers(session, reporting_month, campaign_type):
    """Discover: candidate ACM offers (mandatory filters applied in VW_PADM_ACM_OFFER_SOURCE),
    ACM LEFT JOIN campaign so every ACM offer shows even before PADM has a snapshot."""
    return df(
        session,
        f"""
        SELECT S.OFFER_RESERVATION_CODE, S.SOURCE_MAIL_DATE, S.SOURCE_CAMPAIGN_GROUP_CODE, S.PROGRAM_CODE,
               S.OFFER_DESCRIPTION, S.ACM_SEGMENT_NAME, S.CREDIT_BUREAU_MODEL, S.CREDIT_BUREAU_SCORE,
               S.ANNUAL_FEE, S.NETWORK, S.SOURCE_CPP,
               IFF(O.CAMPAIGN_OFFER_ID IS NULL, 'NOT SNAPSHOTTED', 'IN PADM') AS PADM_STATE
        FROM {SCHEMA}.VW_PADM_ACM_OFFER_SOURCE AS S
        LEFT JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 AS C
               ON C.REPORTING_MONTH = DATE_TRUNC('MONTH', S.SOURCE_MAIL_DATE)::DATE AND C.CAMPAIGN_TYPE = %(t)s
        LEFT JOIN {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT AS O
               ON O.CAMPAIGN_ID = C.CAMPAIGN_ID AND O.OFFER_RESERVATION_CODE = S.OFFER_RESERVATION_CODE
        WHERE DATE_TRUNC('MONTH', S.SOURCE_MAIL_DATE)::DATE = %(m)s
          AND ((%(t)s = 'MAIN' AND UPPER(TRIM(S.SOURCE_CAMPAIGN_GROUP_CODE)) = 'PADM')
            OR (%(t)s = 'REMAIL' AND UPPER(TRIM(S.SOURCE_CAMPAIGN_GROUP_CODE)) IN ('MAP', 'PAREMAIL')))
        ORDER BY S.OFFER_RESERVATION_CODE
        """,
        {"m": reporting_month, "t": campaign_type},
    )


def discover_campaign(session, reporting_month, campaign_type):
    """Single MERGE path from VW_PADM_ACM_CAMPAIGN_CANDIDATE into DM_PADM_CAMPAIGN_1.
    New -> STATUS 'NEW'. Existing campaign whose ACM range moved -> SOURCE_CHANGE_PENDING_FLAG
    (except while still NEW, where the row is simply refreshed). Returns CAMPAIGN_ID or None."""
    exec_sql(
        session,
        f"""
        MERGE INTO {SCHEMA}.DM_PADM_CAMPAIGN_1 AS T
        USING (SELECT * FROM {SCHEMA}.VW_PADM_ACM_CAMPAIGN_CANDIDATE
               WHERE REPORTING_MONTH = %(m)s AND CAMPAIGN_TYPE = %(t)s) AS S
            ON T.REPORTING_MONTH = S.REPORTING_MONTH AND T.CAMPAIGN_TYPE = S.CAMPAIGN_TYPE
        WHEN MATCHED AND (NOT EQUAL_NULL(T.SOURCE_MIN_MAIL_DATE, S.SOURCE_MIN_MAIL_DATE)
                        OR NOT EQUAL_NULL(T.SOURCE_MAX_MAIL_DATE, S.SOURCE_MAX_MAIL_DATE)
                        OR NOT EQUAL_NULL(T.CAMPAIGN_DISPLAY_NAME, S.CAMPAIGN_DISPLAY_NAME)) THEN UPDATE SET
            T.SOURCE_MIN_MAIL_DATE = S.SOURCE_MIN_MAIL_DATE
          , T.SOURCE_MAX_MAIL_DATE = S.SOURCE_MAX_MAIL_DATE
          , T.CAMPAIGN_DISPLAY_NAME = S.CAMPAIGN_DISPLAY_NAME
          , T.CAMPAIGN_SEQUENCE = S.CAMPAIGN_SEQUENCE
          , T.SOURCE_CHANGE_PENDING_FLAG = IFF(T.STATUS = 'NEW', FALSE, TRUE)
          , T.ROW_VERSION = COALESCE(T.ROW_VERSION, 0) + 1
          , T.UPDATED_BY = CURRENT_USER()
          , T.UPDATED_TS = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (CAMPAIGN_ID, SOURCE_CAMPAIGN_IDENTIFICATION_CODE, CAMPAIGN_YEAR, CAMPAIGN_MONTH, REPORTING_MONTH,
             CAMPAIGN_SEQUENCE, CAMPAIGN_TYPE, CAMPAIGN_DISPLAY_NAME, SOURCE_MIN_MAIL_DATE, SOURCE_MAX_MAIL_DATE,
             STATUS, ACTIVE_FLAG, SOURCE_CHANGE_PENDING_FLAG, CURRENT_SOURCE_VERSION_NUMBER,
             CURRENT_WORKING_VERSION_NUMBER, ROW_VERSION)
            VALUES
            (UUID_STRING(), S.SOURCE_CAMPAIGN_IDENTIFICATION_CODES, S.CAMPAIGN_YEAR, S.CAMPAIGN_MONTH, S.REPORTING_MONTH,
             S.CAMPAIGN_SEQUENCE, S.CAMPAIGN_TYPE, S.CAMPAIGN_DISPLAY_NAME, S.SOURCE_MIN_MAIL_DATE, S.SOURCE_MAX_MAIL_DATE,
             'NEW', FALSE, FALSE, 1, 1, 1)
        """,
        {"m": reporting_month, "t": campaign_type},
    )
    rows = session.sql(
        f"SELECT CAMPAIGN_ID FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 WHERE REPORTING_MONTH = ? AND CAMPAIGN_TYPE = ?",
        params=[reporting_month, campaign_type],
    ).collect()
    return str(rows[0][0]) if rows else None


def existing_campaign_for_month(session, reporting_month, campaign_type):
    """Looks up a PADM campaign for this month/type directly against DM_PADM_CAMPAIGN_1 --
    independent of whether ACM has any candidate data yet. Returns (campaign_id, status) or
    (None, None)."""
    rows = session.sql(
        f"SELECT CAMPAIGN_ID, STATUS FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 WHERE REPORTING_MONTH = ? AND CAMPAIGN_TYPE = ?",
        params=[reporting_month, campaign_type],
    ).collect()
    return (str(rows[0][0]), rows[0][1]) if rows else (None, None)


def create_manual_campaign(session, reporting_month, campaign_type):
    """Creates a placeholder campaign shell (STATUS 'NEW') for a month with no ACM candidate data
    yet. CAMPAIGN_SEQUENCE and CAMPAIGN_DISPLAY_NAME use the exact same formulas
    VW_PADM_ACM_CAMPAIGN_CANDIDATE does (sql/deploy.sql) so a campaign created this way looks
    identical to one discovered from ACM later. The ACM-sourced fields (SOURCE_CAMPAIGN_IDENTIFICATION_CODE,
    SOURCE_MIN_MAIL_DATE, SOURCE_MAX_MAIL_DATE) are left NULL -- discover_campaign() fills those in
    for real once ACM data exists and this campaign is refreshed/activated."""
    month_name = reporting_month.strftime("%B")
    type_label = "Main" if campaign_type == "MAIN" else "Remail"
    sequence = (reporting_month.month - 1) * 2 + (1 if campaign_type == "MAIN" else 2)
    display_name = f"{month_name} {reporting_month.year} {type_label} Campaign"
    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_CAMPAIGN_1
            (CAMPAIGN_ID, CAMPAIGN_YEAR, CAMPAIGN_MONTH, REPORTING_MONTH, CAMPAIGN_SEQUENCE,
             CAMPAIGN_TYPE, CAMPAIGN_DISPLAY_NAME, STATUS, ACTIVE_FLAG, SOURCE_CHANGE_PENDING_FLAG,
             CURRENT_SOURCE_VERSION_NUMBER, CURRENT_WORKING_VERSION_NUMBER, ROW_VERSION)
        SELECT UUID_STRING(), %(y)s, %(mo)s, %(m)s, %(seq)s, %(t)s, %(name)s, 'NEW', FALSE, FALSE, 1, 1, 1
        """,
        {"y": reporting_month.year, "mo": reporting_month.month, "m": reporting_month,
         "seq": sequence, "t": campaign_type, "name": display_name},
    )
    campaign_id, _ = existing_campaign_for_month(session, reporting_month, campaign_type)
    return campaign_id


def activate_campaign(session, campaign_id, reason):
    """Snapshot ACM via SP_PADM_ACTIVATE_CAMPAIGN (NEW -> DRAFT). Campaign must already exist --
    see discover_campaign()/create_and_activate_campaign() to create one first."""
    status = campaign_status(session, campaign_id)
    if status not in ("NEW", "DRAFT"):
        return campaign_id, f"Campaign already exists with status {status}."
    try:
        message = call_proc(session, "SP_PADM_ACTIVATE_CAMPAIGN", [campaign_id, reason])
    except ProcedureError as exc:
        if status == "DRAFT" and "current source version" in str(exc):
            return campaign_id, "Campaign is already active (DRAFT)."
        raise
    return campaign_id, message


def create_and_activate_campaign(session, reporting_month, campaign_type, reason):
    """Discover (MERGE) then snapshot ACM via SP_PADM_ACTIVATE_CAMPAIGN (NEW -> DRAFT). Convenience
    wrapper combining discover_campaign() + activate_campaign() for callers that want both at once."""
    campaign_id = discover_campaign(session, reporting_month, campaign_type)
    if campaign_id is None:
        raise ProcedureError("No eligible ACM offers exist for this month and campaign type.")
    return activate_campaign(session, campaign_id, reason)


def transition_status(session, campaign_id, to_status, reason, comment=None):
    return call_proc(session, "SP_PADM_TRANSITION_CAMPAIGN_STATUS", [campaign_id, to_status, reason, comment])


def workflow_history(session, campaign_id):
    return df(
        session,
        f"""
        SELECT EVENT_TS, FROM_STATUS, TO_STATUS, EVENT_REASON, EVENT_COMMENT, EVENT_BY
        FROM {SCHEMA}.DM_PADM_WORKFLOW_EVENT WHERE CAMPAIGN_ID = %(c)s ORDER BY EVENT_TS DESC
        """,
        {"c": campaign_id},
    )


def change_history(session, campaign_id, entity_types=None, limit=200):
    filter_sql = ""
    params = {"c": campaign_id, "n": limit}
    if entity_types:
        filter_sql = "AND ENTITY_TYPE IN (" + ", ".join(f"%(e{i})s" for i in range(len(entity_types))) + ")"
        params.update({f"e{i}": e for i, e in enumerate(entity_types)})
    return df(
        session,
        f"""
        SELECT CHANGED_AT, CHANGED_BY, ENTITY_TYPE, CHANGE_TYPE, CHANGE_REASON,
               TO_VARCHAR(BEFORE_VALUE) AS BEFORE_VALUE, TO_VARCHAR(AFTER_VALUE) AS AFTER_VALUE
        FROM {SCHEMA}.DM_PADM_CHANGE_EVENT
        WHERE CAMPAIGN_ID = %(c)s {filter_sql}
        ORDER BY CHANGED_AT DESC LIMIT %(n)s
        """,
        params,
    )


def previous_campaign(session, campaign_id):
    """Most recent earlier campaign (same type first, then any type). Empty frame if none."""
    return df(
        session,
        f"""
        SELECT P.CAMPAIGN_ID, P.CAMPAIGN_DISPLAY_NAME, P.REPORTING_MONTH, P.CAMPAIGN_TYPE
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 AS C
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 AS P
          ON P.REPORTING_MONTH < C.REPORTING_MONTH OR (P.REPORTING_MONTH = C.REPORTING_MONTH
             AND P.CAMPAIGN_SEQUENCE < C.CAMPAIGN_SEQUENCE)
        WHERE C.CAMPAIGN_ID = %(c)s AND P.STATUS <> 'NEW'
        ORDER BY IFF(P.CAMPAIGN_TYPE = C.CAMPAIGN_TYPE, 0, 1), P.REPORTING_MONTH DESC, P.CAMPAIGN_SEQUENCE DESC
        LIMIT 1
        """,
        {"c": campaign_id},
    )


# ===========================================================================
# Signature page (Tabs 2 and 7)
# ===========================================================================

def signature_live(session, campaign_id):
    # Order by columns VW_PADM_SIGNATURE_PAGE_LIVE actually outputs -- SCORE_MIN / SEGMENT_NAME
    # are not among them and would raise "invalid identifier".
    return df(
        session,
        f"""
        SELECT * FROM {SCHEMA}.VW_PADM_SIGNATURE_PAGE_LIVE WHERE CAMPAIGN_ID = %(c)s
        ORDER BY ANNUAL_FEE, POPULATION_DESCRIPTION NULLS LAST, SEGMENT_DESCRIPTION NULLS LAST, CAMPAIGN_OFFER_ID
        """,
        {"c": campaign_id},
    )


def pre_signature_detail(session, campaign_id):
    """Current Total Available Volume / Quantity % / Quantity (units) / Owner-Approver for this
    campaign's offers. CREATED_TS is included so a caller can pick the most recent row if more than
    one IS_CURRENT row ever exists for the same offer (padm/tabs/pre_signature_page.py guards
    against this)."""
    return df(
        session,
        f"""
        SELECT CAMPAIGN_OFFER_ID, TOTAL_AVAILABLE_VOLUME, QUANTITY_PERCENTAGE, QUANTITY_UNITS,
               OWNER_APPROVER, CREATED_TS
        FROM {SCHEMA}.DM_PADM_PRE_SIGNATURE_DETAIL WHERE CAMPAIGN_ID = %(c)s AND IS_CURRENT = TRUE
        """,
        {"c": campaign_id},
    )


def previous_pre_signature_detail(session, campaign_id):
    """Same fields from the previous campaign, keyed by OFFER_RESERVATION_CODE so they can be
    matched to this campaign's offers even though CAMPAIGN_OFFER_ID is a fresh snapshot each
    campaign. Empty frame if there's no previous campaign."""
    prior = previous_campaign(session, campaign_id)
    if prior.empty:
        return pd.DataFrame()
    return df(
        session,
        f"""
        SELECT O.OFFER_RESERVATION_CODE, D.TOTAL_AVAILABLE_VOLUME, D.QUANTITY_PERCENTAGE,
               D.QUANTITY_UNITS, D.OWNER_APPROVER
        FROM {SCHEMA}.DM_PADM_PRE_SIGNATURE_DETAIL AS D
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_OFFER AS O ON O.CAMPAIGN_OFFER_ID = D.CAMPAIGN_OFFER_ID
        WHERE D.CAMPAIGN_ID = %(p)s AND D.IS_CURRENT = TRUE
        """,
        {"p": prior.iloc[0]["CAMPAIGN_ID"]},
    )


def save_pre_signature_detail(session, campaign_id, rows, reason):
    """rows: [{CAMPAIGN_OFFER_ID, TOTAL_AVAILABLE_VOLUME, QUANTITY_PERCENTAGE, QUANTITY_UNITS,
    OWNER_APPROVER}, ...]. Soft-versions: retires the current row for each offer, inserts a new one.
    All new rows go in as one INSERT -- one row per offer in a Python loop meant one Snowflake
    round-trip per offer, which is what made Save slow for a campaign with many offers."""
    _assert_editable(session, campaign_id)
    if not rows:
        return "Nothing to save."
    with transaction(session):
        offer_ids = [str(r["CAMPAIGN_OFFER_ID"]) for r in rows]
        exec_sql(
            session,
            f"""
            UPDATE {SCHEMA}.DM_PADM_PRE_SIGNATURE_DETAIL
            SET IS_CURRENT = FALSE, VALID_TO_TS = CURRENT_TIMESTAMP()
            WHERE CAMPAIGN_ID = ? AND CAMPAIGN_OFFER_ID IN ({", ".join(["?"] * len(offer_ids))}) AND IS_CURRENT = TRUE
            """,
            [campaign_id, *offer_ids],
        )
        # UUID_STRING() is refused inside a VALUES(...) clause by Snowflake (a recurring issue in
        # this codebase, fixed the same way at other call sites) -- a SELECT list is fine, so each
        # row is its own SELECT, combined with UNION ALL into one INSERT.
        select_rows = " UNION ALL ".join(["SELECT UUID_STRING(), ?, ?, ?, ?, ?, ?, TRUE, ?"] * len(rows))
        binds = []
        for r in rows:
            binds += [campaign_id, r["CAMPAIGN_OFFER_ID"], r["TOTAL_AVAILABLE_VOLUME"],
                      r["QUANTITY_PERCENTAGE"], r["QUANTITY_UNITS"], r["OWNER_APPROVER"], reason]
        exec_sql(
            session,
            f"""
            INSERT INTO {SCHEMA}.DM_PADM_PRE_SIGNATURE_DETAIL
                (PRE_SIGNATURE_DETAIL_ID, CAMPAIGN_ID, CAMPAIGN_OFFER_ID, TOTAL_AVAILABLE_VOLUME,
                 QUANTITY_PERCENTAGE, QUANTITY_UNITS, OWNER_APPROVER, IS_CURRENT, CHANGE_REASON)
            {select_rows}
            """,
            binds,
        )
    return f"Saved tracking fields for {len(rows)} offer(s)."


def snapshot_versions(session, campaign_id):
    return df(
        session,
        f"""
        SELECT SIGNATURE_VERSION_NUMBER, MAX(CALCULATION_RUN_ID) AS CALCULATION_RUN_ID,
               MAX(SNAPSHOT_STATUS) AS SNAPSHOT_STATUS, MAX(CREATED_BY) AS CREATED_BY,
               MAX(CREATED_TS) AS CREATED_TS, COUNT(*) AS ROW_COUNT
        FROM {SCHEMA}.DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT WHERE CAMPAIGN_ID = %(c)s
        GROUP BY SIGNATURE_VERSION_NUMBER ORDER BY SIGNATURE_VERSION_NUMBER DESC
        """,
        {"c": campaign_id},
    )


def snapshot_rows(session, campaign_id, version):
    return df(
        session,
        f"""
        SELECT * FROM {SCHEMA}.DM_PADM_SIGNATURE_PAGE_2_SNAPSHOT
        WHERE CAMPAIGN_ID = %(c)s AND SIGNATURE_VERSION_NUMBER = %(v)s
        ORDER BY ANNUAL_FEE, POPULATION_GROUP_KEY, SEGMENT_DESCRIPTION, OFFER_RESERVATION_CODE
        """,
        {"c": campaign_id, "v": int(version)},
    )


def latest_calculation_run(session, campaign_id):
    return df(
        session,
        f"""
        SELECT CALCULATION_RUN_ID, CALCULATION_STATUS, CALCULATION_STARTED_TS, CALCULATION_COMPLETED_TS,
               CAMPAIGN_WORKING_VERSION_NUMBER, CALCULATED_BY
        FROM {SCHEMA}.DM_PADM_CALCULATION_RUN WHERE CAMPAIGN_ID = %(c)s
        ORDER BY CALCULATION_STARTED_TS DESC LIMIT 1
        """,
        {"c": campaign_id},
    )


def run_calculation(session, campaign_id):
    result = call_proc(session, "SP_PADM_RUN_CALCULATION", [campaign_id])
    run_id, cells = result.split("|", 1)
    return run_id, int(cells)


def generate_signature_page_2(session, campaign_id, calculation_run_id):
    return call_proc(session, "SP_PADM_GENERATE_SIGNATURE_PAGE_2", [campaign_id, calculation_run_id])


# ===========================================================================
# Assumptions (Tabs 2, 4, 6)
# ===========================================================================

def assumption_definitions(session):
    return df(
        session,
        f"""
        SELECT * FROM {SCHEMA}.DM_PADM_ASSUMPTION_DEFINITION
        WHERE ACTIVE_FLAG = TRUE ORDER BY DISPLAY_SEQUENCE, ASSUMPTION_CODE
        """,
    )


def campaign_assumption_current(session, campaign_id):
    return df(session, f"SELECT * FROM {SCHEMA}.VW_PADM_CAMPAIGN_ASSUMPTION_CURRENT WHERE CAMPAIGN_ID = %(c)s",
               {"c": campaign_id})


def campaign_assumption_history(session, campaign_id):
    return df(
        session,
        f"""
        SELECT VERSION_NUMBER, CPP, UNIT_COST, NBR, UNWIND_RATE, CHANGE_REASON, CREATED_BY, CREATED_TS, IS_CURRENT
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_ASSUMPTION_VERSION WHERE CAMPAIGN_ID = %(c)s ORDER BY VERSION_NUMBER
        """,
        {"c": campaign_id},
    )


def default_campaign_assumption(session, campaign_id):
    """Defaults for a campaign without assumptions: the previous campaign's current version,
    else the same month of the previous year. Returns (frame, source description)."""
    prior = previous_campaign(session, campaign_id)
    if not prior.empty:
        values = campaign_assumption_current(session, prior.iloc[0]["CAMPAIGN_ID"])
        if not values.empty:
            return values, f"previous campaign ({prior.iloc[0]['CAMPAIGN_DISPLAY_NAME']})"
    last_year = df(
        session,
        f"""
        SELECT A.*, P.CAMPAIGN_DISPLAY_NAME
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 AS C
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 AS P
          ON P.REPORTING_MONTH = DATEADD(YEAR, -1, C.REPORTING_MONTH) AND P.CAMPAIGN_TYPE = C.CAMPAIGN_TYPE
        JOIN {SCHEMA}.VW_PADM_CAMPAIGN_ASSUMPTION_CURRENT AS A ON A.CAMPAIGN_ID = P.CAMPAIGN_ID
        WHERE C.CAMPAIGN_ID = %(c)s
        """,
        {"c": campaign_id},
    )
    if not last_year.empty:
        return last_year, f"previous year ({last_year.iloc[0]['CAMPAIGN_DISPLAY_NAME']})"
    return last_year, None


def segment_assumption_current(session, campaign_id, segment_id):
    return df(
        session,
        f"SELECT * FROM {SCHEMA}.VW_PADM_SEGMENT_ASSUMPTION_CURRENT WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s",
        {"c": campaign_id, "s": segment_id},
    )


def default_segment_assumption(session, campaign_id, segment_id):
    """Same segment's current overrides on the previous campaign, if any."""
    prior = previous_campaign(session, campaign_id)
    if prior.empty:
        return segment_assumption_current(session, "", segment_id), None
    values = segment_assumption_current(session, prior.iloc[0]["CAMPAIGN_ID"], segment_id)
    return values, (f"previous campaign ({prior.iloc[0]['CAMPAIGN_DISPLAY_NAME']})" if not values.empty else None)


def segment_assumption_history(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT VERSION_NUMBER, UNIT_COST_OVERRIDE AS UNIT_COST, NBR_OVERRIDE AS NBR, UNWIND_RATE_OVERRIDE AS UNWIND_RATE,
               RATE_ADJUSTMENT_OVERRIDE AS RATE_ADJUSTMENT, SEASONALITY_REDUCTION_OVERRIDE AS SEASONALITY_REDUCTION,
               UNWIND_RATE_ADJUSTMENT_OVERRIDE AS UNWIND_RATE_ADJUSTMENT,
               CHANGE_REASON, CREATED_BY, CREATED_TS, IS_CURRENT
        FROM {SCHEMA}.DM_PADM_SEGMENT_ASSUMPTION_VERSION
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s ORDER BY VERSION_NUMBER
        """,
        {"c": campaign_id, "s": segment_id},
    )


def save_campaign_assumption(session, campaign_id, values, expected_version, reason):
    """values: stored-unit dict keyed CPP / UNIT_COST / NBR / UNWIND_RATE."""
    return call_proc(
        session, "SP_PADM_SAVE_CAMPAIGN_ASSUMPTION",
        [campaign_id, values.get("CPP"), values.get("UNIT_COST"), values.get("NBR"), values.get("UNWIND_RATE"),
         expected_version, reason],
    )


def save_segment_assumption(session, campaign_id, segment_id, values, expected_version, reason):
    """values: stored-unit dict keyed by assumption code; missing/None = inherit."""
    return call_proc(
        session, "SP_PADM_SAVE_SEGMENT_ASSUMPTION",
        [campaign_id, segment_id, values.get("CPP"), values.get("UNIT_COST"), values.get("NBR"),
         values.get("UNWIND_RATE"), values.get("RATE_ADJUSTMENT"), values.get("SEASONALITY_REDUCTION"),
         values.get("UNWIND_RATE_ADJUSTMENT"), expected_version, reason],
    )


# ===========================================================================
# Segments (Tab 3)
# ===========================================================================

def score_range_rules(session):
    return df(
        session,
        f"""
        SELECT SCORE_TYPE, SCORE_RANGE_CODE, SCORE_MIN, SCORE_MAX, DISPLAY_SEQUENCE
        FROM {SCHEMA}.DM_PADM_SCORE_RANGE_RULE_1
        WHERE ACTIVE_FLAG = TRUE AND CURRENT_DATE() >= VALID_FROM AND (VALID_TO IS NULL OR CURRENT_DATE() < VALID_TO)
        ORDER BY SCORE_TYPE, DISPLAY_SEQUENCE, SCORE_MIN
        """,
    )


def source_names(session):
    return df(
        session,
        f"""
        SELECT DISTINCT UPPER(SOURCE_NAME) AS SOURCE_NAME FROM (
            SELECT SOURCE_NAME FROM {SCHEMA}.DM_PADM_POPULATION_GROUP_RULE WHERE ACTIVE_FLAG = TRUE
            UNION ALL SELECT SOURCE_NAME FROM {SCHEMA}.DM_PADM_SEGMENT_1 WHERE ACTIVE_FLAG = TRUE
        ) WHERE SOURCE_NAME IS NOT NULL ORDER BY 1
        """,
    )


def dropdown_values(session):
    """Distinct ACM values mailed in the last 60 days, as {FIELD_NAME: [values]}."""
    frame = df(session, f"SELECT FIELD_NAME, FIELD_VALUE FROM {SCHEMA}.VW_PADM_SEGMENT_DROPDOWN_60D ORDER BY 1, 2")
    return {name: group["FIELD_VALUE"].tolist() for name, group in frame.groupby("FIELD_NAME")}


def segments_master(session):
    return df(session, f"SELECT * FROM {SCHEMA}.DM_PADM_SEGMENT_1 WHERE ACTIVE_FLAG = TRUE ORDER BY SEGMENT_NAME")


def segment_key(source_name, score_type, score_min, score_max):
    """The natural key that identifies a segment regardless of which campaign it's on --
    SOURCE_NAME/SCORE_TYPE/SCORE_MIN/SCORE_MAX, the same 4 fields create_segment.py calls
    "mandatory fields". Matches DM_PADM_SEGMENT_1.SEGMENT_KEY (sql/deploy.sql) exactly."""
    return f"{(source_name or '').upper()}|{score_type.upper()}|{int(score_min)}|{int(score_max)}"


def campaign_segment_key(campaign_id, segment_id):
    """Identifies one campaign's copy of one segment. Matches
    DM_PADM_CAMPAIGN_SEGMENT_1.CAMPAIGN_SEGMENT_KEY (sql/deploy.sql) exactly."""
    return f"{campaign_id}|{segment_id}"


def find_segment(session, score_type, score_min, score_max, source_name):
    return df(
        session,
        f"SELECT * FROM {SCHEMA}.DM_PADM_SEGMENT_1 WHERE ACTIVE_FLAG = TRUE AND SEGMENT_KEY = %(k)s",
        {"k": segment_key(source_name, score_type, score_min, score_max)},
    )


def discover_segments(session):
    """Bulk insert-only MERGE from VW_PADM_SEGMENT_SOURCE_CANDIDATE (real ACM mailfile history)
    into DM_PADM_SEGMENT_1 -- the same source-candidate view bkp_files/load_campaigns_segments_
    from_source.sql reads, but targeting the table the app actually uses. Matched on the same
    4-field natural key find_segment() uses (SOURCE_NAME, SCORE_TYPE, SCORE_MIN, SCORE_MAX),
    since DM_PADM_SEGMENT_1 has no SEGMENT_KEY column. Never updates an existing segment --
    DM_PADM_SEGMENT_1 also has no USER_CREATED_FLAG to distinguish a dashboard-curated row from a
    source-derived one, so insert-only (new governed segments only) is the safe choice, unlike
    discover_campaign()'s MATCHED/update branches. Returns the number of new segments inserted."""
    rows = exec_sql(
        session,
        f"""
        MERGE INTO {SCHEMA}.DM_PADM_SEGMENT_1 AS T
        USING (
            SELECT SUGGESTED_SEGMENT_NAME AS SEGMENT_NAME, SOURCE AS SOURCE_NAME,
                   BUREAU_SCORE_TYPE AS SCORE_TYPE, SCORE_MIN, SCORE_MAX,
                   COALESCE(PROSPECT_SEGMENT_TYPE, 'ALL') AS PROSPECT_SEGMENT_TYPE,
                   ANNUAL_FEE, NETWORK, MLA_FLAG, RESPONSE_MODEL_TYPE, RISK_SCORE_TYPE, MAIL_REMAIL,
                   UPPER(SOURCE) || '|' || UPPER(BUREAU_SCORE_TYPE) || '|' || SCORE_MIN || '|' || SCORE_MAX
                       AS SEGMENT_KEY
            FROM {SCHEMA}.VW_PADM_SEGMENT_SOURCE_CANDIDATE
            WHERE SCORE_MIN IS NOT NULL AND SCORE_MAX IS NOT NULL AND SOURCE IS NOT NULL
              AND BUREAU_SCORE_TYPE IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY SOURCE, BUREAU_SCORE_TYPE, SCORE_MIN, SCORE_MAX
                ORDER BY LAST_MAIL_DATE DESC, SOURCE_RECORD_COUNT DESC
            ) = 1
        ) AS S
        ON T.SEGMENT_KEY = S.SEGMENT_KEY
        WHEN NOT MATCHED THEN INSERT (
            SEGMENT_ID, SEGMENT_NAME, SOURCE_NAME, SCORE_TYPE, SCORE_MIN, SCORE_MAX,
            PROSPECT_SEGMENT_TYPE, ANNUAL_FEE, NETWORK, MLA_FLAG, RESPONSE_MODEL_TYPE,
            RISK_SCORE_TYPE, MAIL_REMAIL, SEGMENT_KEY, ACTIVE_FLAG, VALID_FROM, ROW_VERSION
        ) VALUES (
            UUID_STRING(), S.SEGMENT_NAME, S.SOURCE_NAME, S.SCORE_TYPE, S.SCORE_MIN, S.SCORE_MAX,
            S.PROSPECT_SEGMENT_TYPE, S.ANNUAL_FEE, S.NETWORK, S.MLA_FLAG, S.RESPONSE_MODEL_TYPE,
            S.RISK_SCORE_TYPE, S.MAIL_REMAIL, S.SEGMENT_KEY, TRUE, CURRENT_DATE(), 1
        )
        """,
    )
    return rows_affected(rows, "inserted")


def campaign_segments(session, campaign_id):
    return df(
        session,
        f"""
        SELECT CS.CAMPAIGN_SEGMENT_ID, CS.ROW_VERSION AS CAMPAIGN_SEGMENT_ROW_VERSION, S.*,
               (SELECT COUNT(*) FROM {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION A
                WHERE A.CAMPAIGN_ID = CS.CAMPAIGN_ID AND A.SEGMENT_ID = CS.SEGMENT_ID AND A.IS_CURRENT = TRUE) AS OFFER_COUNT
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1 AS CS
        JOIN {SCHEMA}.DM_PADM_SEGMENT_1 AS S ON CS.SEGMENT_ID = S.SEGMENT_ID
        WHERE CS.CAMPAIGN_ID = %(c)s AND CS.IS_CURRENT = TRUE
        ORDER BY S.SOURCE_NAME, S.SCORE_TYPE, S.SCORE_MIN
        """,
        {"c": campaign_id},
    )


def campaign_offers(session, campaign_id):
    """Every current offer for this campaign -- one row per offer, no segment join. An offer can
    belong to any number of segments (many-to-many -- its full Quantity/Boards/$ count
    independently in EACH segment's totals, by design); use offer_segment_allocations() for
    the offer<->segment links."""
    return df(
        session,
        f"""
        SELECT O.CAMPAIGN_OFFER_ID, O.OFFER_RESERVATION_CODE, O.OFFER_DESCRIPTION, O.OFFER_SEGMENT_NAME,
               O.CREDIT_BUREAU_MODEL, O.CREDIT_BUREAU_SCORE, O.CRS_SCORE, O.PROSPECT_TYPE
        FROM {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT AS O
        WHERE O.CAMPAIGN_ID = %(c)s
        ORDER BY O.OFFER_RESERVATION_CODE
        """,
        {"c": campaign_id},
    )


def offer_segment_allocations(session, campaign_id):
    """Current offer<->segment links for this campaign (many-to-many: an offer may have several
    rows, one per segment it belongs to)."""
    return df(
        session,
        f"""
        SELECT A.OFFER_SEGMENT_ALLOCATION_ID, A.CAMPAIGN_OFFER_ID, A.SEGMENT_ID,
               A.POPULATION_DESCRIPTION, A.ROW_VERSION AS ALLOCATION_ROW_VERSION
        FROM {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION AS A
        WHERE A.CAMPAIGN_ID = %(c)s AND A.IS_CURRENT = TRUE
        """,
        {"c": campaign_id},
    )


def suggested_offers(session, campaign_id, segment_id):
    """Offers (by reservation code) this segment used on earlier campaigns, mapped onto the
    current campaign's unallocated offers."""
    if not segment_id:
        return []
    frame = df(
        session,
        f"""
        SELECT DISTINCT CUR.CAMPAIGN_OFFER_ID
        FROM {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION AS A
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_OFFER AS PO ON A.CAMPAIGN_OFFER_ID = PO.CAMPAIGN_OFFER_ID
        JOIN {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT AS CUR
          ON CUR.CAMPAIGN_ID = %(c)s AND CUR.OFFER_RESERVATION_CODE = PO.OFFER_RESERVATION_CODE
        LEFT JOIN {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION AS CA
                ON CA.CAMPAIGN_OFFER_ID = CUR.CAMPAIGN_OFFER_ID AND CA.IS_CURRENT = TRUE
        WHERE A.SEGMENT_ID = %(s)s AND A.CAMPAIGN_ID <> %(c)s AND CA.CAMPAIGN_OFFER_ID IS NULL
        """,
        {"c": campaign_id, "s": segment_id},
    )
    return frame["CAMPAIGN_OFFER_ID"].tolist()


def _working_version(session, campaign_id):
    return int(session.sql(
        f"SELECT CURRENT_WORKING_VERSION_NUMBER FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 WHERE CAMPAIGN_ID = ?",
        params=[campaign_id]).collect()[0][0])


def _insert_allocations(session, campaign_id, segment_id, offer_ids, reason, method, label=None):
    """An offer may belong to any number of segments (many-to-many) -- this only guards against
    a duplicate *(offer, segment)* row, not against the offer having other current allocations
    to different segments."""
    if not offer_ids:
        return 0
    rows = exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION
            (OFFER_SEGMENT_ALLOCATION_ID, CAMPAIGN_ID, CAMPAIGN_OFFER_ID, SEGMENT_ID, WORKING_VERSION_NUMBER,
             POPULATION_DESCRIPTION, ALLOCATION_STATUS, INITIALIZATION_METHOD, IS_CURRENT, CHANGE_REASON, ROW_VERSION)
        SELECT UUID_STRING(), C.CAMPAIGN_ID, V.OFFER_ID, ?, C.CURRENT_WORKING_VERSION_NUMBER,
               ?, 'ACTIVE', ?, TRUE, ?, 1
        FROM (VALUES {_values(len(offer_ids), 1)}) AS V(OFFER_ID)
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 C ON C.CAMPAIGN_ID = ?
        WHERE NOT EXISTS (SELECT 1 FROM {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION A
                           WHERE A.CAMPAIGN_OFFER_ID = V.OFFER_ID AND A.SEGMENT_ID = ? AND A.IS_CURRENT = TRUE)
        """,
        [segment_id, label, method, reason, *[str(o) for o in offer_ids], campaign_id, segment_id],
    )
    inserted = rows_affected(rows, "inserted")
    if inserted != len(offer_ids):
        raise ProcedureError(f"{len(offer_ids) - inserted} offer(s) are already on this segment and were skipped. "
                              "Reload to see current state.")
    for offer_id in offer_ids:
        _change_event(session, campaign_id, "OFFER_SEGMENT_ALLOCATION", offer_id, "ALLOCATED",
                      None, {"SEGMENT_ID": segment_id, "POPULATION_DESCRIPTION": label}, reason)
    return inserted


def _retire_allocations(session, campaign_id, allocation_ids, reason):
    """Soft-version: flip IS_CURRENT on the given allocations (optimistic: must still be current)."""
    if not allocation_ids:
        return
    rows = exec_sql(
        session,
        f"""
        UPDATE {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION
        SET IS_CURRENT = FALSE, VALID_TO_TS = CURRENT_TIMESTAMP(),
            CHANGE_REASON = ?, ROW_VERSION = COALESCE(ROW_VERSION, 1) + 1,
            UPDATED_BY = CURRENT_USER(), UPDATED_TS = CURRENT_TIMESTAMP()
        WHERE IS_CURRENT = TRUE AND OFFER_SEGMENT_ALLOCATION_ID IN ({", ".join(["?"] * len(allocation_ids))})
        """,
        [reason, *[str(a) for a in allocation_ids]],
    )
    if rows_affected(rows, "updated") != len(allocation_ids):
        raise ProcedureError(STALE_MESSAGE)
    for allocation_id in allocation_ids:
        _change_event(session, campaign_id, "OFFER_SEGMENT_ALLOCATION", allocation_id, "RETIRED",
                      {"IS_CURRENT": True}, {"IS_CURRENT": False}, reason)


def _ensure_campaign_segment(session, campaign_id, segment_id, reason, method):
    exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1
            (CAMPAIGN_SEGMENT_ID, CAMPAIGN_ID, SEGMENT_ID, CAMPAIGN_SEGMENT_KEY, WORKING_VERSION_NUMBER,
             SEGMENT_STATUS, INITIALIZATION_METHOD, IS_CURRENT, CHANGE_REASON, ROW_VERSION)
        SELECT UUID_STRING(), C.CAMPAIGN_ID, %(s)s, %(k)s, C.CURRENT_WORKING_VERSION_NUMBER, 'ACTIVE', %(m)s, TRUE, %(r)s, 1
        FROM {SCHEMA}.DM_PADM_CAMPAIGN_1 C
        WHERE C.CAMPAIGN_ID = %(c)s
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1 CS
                           WHERE CS.CAMPAIGN_ID = %(c)s AND CS.SEGMENT_ID = %(s)s AND CS.IS_CURRENT = TRUE)
        """,
        {"c": campaign_id, "s": segment_id, "k": campaign_segment_key(campaign_id, segment_id),
         "m": method, "r": reason},
    )


SEGMENT_OPTIONAL_FIELDS = [
    "PROSPECT_SEGMENT_TYPE", "CREDIT_BUREAU_MODEL", "CREDIT_BUREAU_SCORE", "ANNUAL_FEE", "NETWORK", "MLA_FLAG",
    "CRS_MODEL", "CRS_SCORE", "RISK_SCORE_TYPE", "RESPONSE_MODEL_TYPE", "FREE_FORM_NOTE",
]


def create_segment(session, campaign_id, fields, offer_ids, reason):
    """New governed segment + campaign working copy + offer allocation, in one transaction."""
    _assert_editable(session, campaign_id)
    if not find_segment(session, fields["SCORE_TYPE"], fields["SCORE_MIN"], fields["SCORE_MAX"],
                         fields["SOURCE_NAME"]).empty:
        raise ProcedureError("A segment with these mandatory fields already exists -- reuse it instead.")
    segment_id = str(uuid.uuid4())
    record = {
        "SEGMENT_ID": segment_id, "SEGMENT_NAME": fields["SEGMENT_NAME"], "SOURCE_NAME": fields["SOURCE_NAME"],
        "SCORE_TYPE": fields["SCORE_TYPE"], "SCORE_MIN": int(fields["SCORE_MIN"]), "SCORE_MAX": int(fields["SCORE_MAX"]),
        "MAIL_REMAIL": fields.get("MAIL_REMAIL"),
        "TIMES_MAILED_FILTER": json.dumps(fields.get("TIMES_MAILED_FILTER") or []),
        **{f: (fields.get(f) or None) for f in SEGMENT_OPTIONAL_FIELDS},
    }
    record["PROSPECT_SEGMENT_TYPE"] = record["PROSPECT_SEGMENT_TYPE"] or "ALL"
    record["SEGMENT_KEY"] = segment_key(fields["SOURCE_NAME"], fields["SCORE_TYPE"],
                                         fields["SCORE_MIN"], fields["SCORE_MAX"])
    columns = list(record)
    select_list = ", ".join("PARSE_JSON(?)" if c == "TIMES_MAILED_FILTER" else "?" for c in columns)
    with transaction(session):
        exec_sql(
            session,
            f"""
            INSERT INTO {SCHEMA}.DM_PADM_SEGMENT_1 ({", ".join(columns)}, ACTIVE_FLAG, VALID_FROM, ROW_VERSION)
            SELECT {select_list}, TRUE, CURRENT_DATE(), 1
            """,
            [record[c] for c in columns],
        )
        _change_event(session, campaign_id, "SEGMENT", segment_id, "CREATED", None, record, reason)
        _ensure_campaign_segment(session, campaign_id, segment_id, reason, "MANUAL_CREATE")
        _insert_allocations(session, campaign_id, segment_id, offer_ids, reason, "MANUAL_CREATE")
    return segment_id


def reuse_segment(session, campaign_id, segment_id, offer_ids, reason):
    _assert_editable(session, campaign_id)
    with transaction(session):
        _ensure_campaign_segment(session, campaign_id, segment_id, reason, "REUSED")
        _change_event(session, campaign_id, "CAMPAIGN_SEGMENT", segment_id, "REUSED", None,
                      {"SEGMENT_ID": segment_id, "OFFERS": list(offer_ids)}, reason)
        _insert_allocations(session, campaign_id, segment_id, offer_ids, reason, "REUSED")


def reuse_all_segments(session, campaign_id, segment_ids, reason):
    """Bulk-link every given governed segment onto this campaign (no offer allocation -- that
    stays a per-segment step afterward, via Create Segment's edit panel or Population
    Description). Safe to call with segments already on the campaign: _ensure_campaign_segment()
    is a NOT-EXISTS-guarded insert, so duplicates are silently skipped, not double-added."""
    _assert_editable(session, campaign_id)
    if not segment_ids:
        return 0
    with transaction(session):
        for segment_id in segment_ids:
            _ensure_campaign_segment(session, campaign_id, segment_id, reason, "BULK_REUSE")
            _change_event(session, campaign_id, "CAMPAIGN_SEGMENT", segment_id, "REUSED", None,
                          {"SEGMENT_ID": segment_id}, reason)
    return len(segment_ids)


def edit_segment(session, campaign_id, segment_id, expected_row_version, changes, reason):
    """changes: {column: new value} for optional attributes only (mandatory fields define the
    governed segment and its name)."""
    _assert_editable(session, campaign_id)
    changes = {k: (v or None) for k, v in changes.items() if k in SEGMENT_OPTIONAL_FIELDS}
    if not changes:
        return "Nothing changed."
    before = df(session, f"SELECT * FROM {SCHEMA}.DM_PADM_SEGMENT_1 WHERE SEGMENT_ID = %(s)s", {"s": segment_id})
    set_sql = ", ".join(f"{c} = ?" for c in changes)
    with transaction(session):
        rows = exec_sql(
            session,
            f"""
            UPDATE {SCHEMA}.DM_PADM_SEGMENT_1
            SET {set_sql}, ROW_VERSION = ROW_VERSION + 1, UPDATED_BY = CURRENT_USER(), UPDATED_TS = CURRENT_TIMESTAMP()
            WHERE SEGMENT_ID = ? AND ROW_VERSION = ?
            """,
            [*changes.values(), segment_id, int(expected_row_version)],
        )
        if rows_affected(rows, "updated") != 1:
            raise ProcedureError(STALE_MESSAGE)
        _change_event(session, campaign_id, "SEGMENT", segment_id, "UPDATED",
                      {c: (before.iloc[0][c] if not before.empty else None) for c in changes}, changes, reason)
    return "Segment updated."


def set_segment_offers(session, campaign_id, segment_id, offer_ids, reason):
    """Replace this segment's current offer set (new allocation versions; old ones retired). Only
    touches this segment's own links -- an offer kept here that's also on another segment is
    untouched there (many-to-many)."""
    _assert_editable(session, campaign_id)
    allocations = offer_segment_allocations(session, campaign_id)
    current = allocations[allocations["SEGMENT_ID"] == segment_id]
    wanted = set(map(str, offer_ids))
    retire = current[~current["CAMPAIGN_OFFER_ID"].astype(str).isin(wanted)]["OFFER_SEGMENT_ALLOCATION_ID"].tolist()
    add = sorted(wanted - set(current["CAMPAIGN_OFFER_ID"].astype(str)))
    with transaction(session):
        _retire_allocations(session, campaign_id, retire, reason)
        _insert_allocations(session, campaign_id, segment_id, add, reason, "MANUAL_EDIT")
    return f"{len(add)} offer(s) added, {len(retire)} removed."


def remove_segment_from_campaign(session, campaign_id, segment_id, reason):
    _assert_editable(session, campaign_id)
    allocations = offer_segment_allocations(session, campaign_id)
    allocation_ids = allocations[allocations["SEGMENT_ID"] == segment_id]["OFFER_SEGMENT_ALLOCATION_ID"].tolist()
    with transaction(session):
        _retire_allocations(session, campaign_id, allocation_ids, reason)
        rows = exec_sql(
            session,
            f"""
            UPDATE {SCHEMA}.DM_PADM_CAMPAIGN_SEGMENT_1
            SET IS_CURRENT = FALSE, SEGMENT_STATUS = 'REMOVED', VALID_TO_TS = CURRENT_TIMESTAMP(),
                CHANGE_REASON = %(r)s, ROW_VERSION = COALESCE(ROW_VERSION, 1) + 1,
                UPDATED_BY = CURRENT_USER(), UPDATED_TS = CURRENT_TIMESTAMP()
            WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s AND IS_CURRENT = TRUE
            """,
            {"c": campaign_id, "s": segment_id, "r": reason},
        )
        if rows_affected(rows, "updated") != 1:
            raise ProcedureError(STALE_MESSAGE)
        _change_event(session, campaign_id, "CAMPAIGN_SEGMENT", segment_id, "REMOVED",
                      {"IS_CURRENT": True, "OFFERS": len(allocation_ids)}, {"IS_CURRENT": False}, reason)
    return "Segment removed from campaign."


# ===========================================================================
# Population description (Tab 5)
# ===========================================================================

def previous_allocation(session, campaign_id):
    """{segment_id: [current campaign offer ids]} from the previous campaign's allocation,
    matched by offer reservation code."""
    prior = previous_campaign(session, campaign_id)
    if prior.empty:
        return {}
    frame = df(
        session,
        f"""
        SELECT A.SEGMENT_ID, CUR.CAMPAIGN_OFFER_ID
        FROM {SCHEMA}.DM_PADM_OFFER_SEGMENT_ALLOCATION AS A
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_OFFER AS PO ON A.CAMPAIGN_OFFER_ID = PO.CAMPAIGN_OFFER_ID
        JOIN {SCHEMA}.VW_PADM_CAMPAIGN_OFFER_CURRENT AS CUR
          ON CUR.CAMPAIGN_ID = %(c)s AND CUR.OFFER_RESERVATION_CODE = PO.OFFER_RESERVATION_CODE
        WHERE A.CAMPAIGN_ID = %(p)s AND A.IS_CURRENT = TRUE
        """,
        {"c": campaign_id, "p": prior.iloc[0]["CAMPAIGN_ID"]},
    )
    return {seg: group["CAMPAIGN_OFFER_ID"].tolist() for seg, group in frame.groupby("SEGMENT_ID")}


def save_population_allocation(session, campaign_id, segment_offers, segment_labels, reason):
    """segment_offers: {segment_id: [offer ids]}; segment_labels: {segment_id: label}.
    Any segment whose offers or label changed gets new allocation versions (old ones retired).
    An offer may appear under more than one segment_id -- many-to-many is intentional: its full
    Quantity/Boards/$ then count independently in each of those segments' totals."""
    _assert_editable(session, campaign_id)
    allocations = offer_segment_allocations(session, campaign_id)
    changed = 0
    with transaction(session):
        # Retire first (offers may move between segments), then insert.
        plans = []
        for segment_id, wanted in segment_offers.items():
            current = allocations[allocations["SEGMENT_ID"] == segment_id]
            label = (segment_labels.get(segment_id) or "").strip() or None
            current_label = current["POPULATION_DESCRIPTION"].dropna().iloc[0] if current["POPULATION_DESCRIPTION"].notna().any() else None
            same_offers = set(map(str, wanted)) == set(current["CAMPAIGN_OFFER_ID"].astype(str))
            if same_offers and label == current_label:
                continue
            _retire_allocations(session, campaign_id, current["OFFER_SEGMENT_ALLOCATION_ID"].tolist(), reason)
            plans.append((segment_id, wanted, label))
        for segment_id, wanted, label in plans:
            _ensure_campaign_segment(session, campaign_id, segment_id, reason, "POPULATION_DESCRIPTION")
            _insert_allocations(session, campaign_id, segment_id, list(wanted), reason, "POPULATION_DESCRIPTION", label)
            changed += 1
    return f"Allocation saved for {changed} segment(s)." if changed else "Nothing changed."


# ===========================================================================
# Segment Viewer (Tab 6)
# ===========================================================================

def active_cde_batch(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT CDE_LOAD_BATCH_ID, VERSION_NUMBER, SOURCE_FILE_NAME, LOADED_ROW_COUNT, ACTIVATED_BY, ACTIVATED_TS
        FROM {SCHEMA}.DM_PADM_CDE_LOAD_BATCH
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s AND ACTIVE_FLAG = TRUE
        """,
        {"c": campaign_id, "s": segment_id},
    )


def ensure_working_grid(session, campaign_id, segment_id):
    """Seeds DM_PADM_SELECTION_WORKING for every active CDE cell lacking a row, with the most
    recent prior campaign's saved % for this segment, else 0."""
    rows = exec_sql(
        session,
        f"""
        INSERT INTO {SCHEMA}.DM_PADM_SELECTION_WORKING
            (CAMPAIGN_ID, SEGMENT_ID, RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET, SELECTION_PERCENTAGE,
             SOURCE_CAMPAIGN_ID, SOURCE_SEGMENT_ID, INITIALIZATION_METHOD, IS_DIRTY)
        SELECT G.CAMPAIGN_ID, G.SEGMENT_ID, G.RESPONSE_MODEL_TIER, G.TIMES_MAILED_BUCKET,
               COALESCE(PC.SELECTION_PERCENTAGE, 0),
               P.CAMPAIGN_ID, IFF(P.CAMPAIGN_ID IS NULL, NULL, G.SEGMENT_ID),
               IFF(PC.SELECTION_PERCENTAGE IS NULL, 'DEFAULT_ZERO', 'PRIOR_MONTH_COPY'), FALSE
        FROM {SCHEMA}.VW_PADM_CDE_GRID_CURRENT G
        LEFT JOIN (
            SELECT SS.SELECTION_SET_ID, SS.CAMPAIGN_ID
            FROM {SCHEMA}.DM_PADM_SELECTION_SET SS
            JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 PRIOR_C ON SS.CAMPAIGN_ID = PRIOR_C.CAMPAIGN_ID
            JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 CUR ON CUR.CAMPAIGN_ID = %(c)s
            WHERE SS.SEGMENT_ID = %(s)s AND SS.IS_CURRENT = TRUE AND SS.CAMPAIGN_ID <> %(c)s
              AND PRIOR_C.REPORTING_MONTH <= CUR.REPORTING_MONTH
            QUALIFY ROW_NUMBER() OVER (ORDER BY PRIOR_C.REPORTING_MONTH DESC, SS.CREATED_TS DESC) = 1
        ) P ON TRUE
        LEFT JOIN {SCHEMA}.DM_PADM_SELECTION_SET_CELL PC
            ON PC.SELECTION_SET_ID = P.SELECTION_SET_ID
           AND PC.RESPONSE_MODEL_TIER = G.RESPONSE_MODEL_TIER AND PC.TIMES_MAILED_BUCKET = G.TIMES_MAILED_BUCKET
        LEFT JOIN {SCHEMA}.DM_PADM_SELECTION_WORKING W
            ON W.CAMPAIGN_ID = G.CAMPAIGN_ID AND W.SEGMENT_ID = G.SEGMENT_ID
           AND W.RESPONSE_MODEL_TIER = G.RESPONSE_MODEL_TIER AND W.TIMES_MAILED_BUCKET = G.TIMES_MAILED_BUCKET
        WHERE G.CAMPAIGN_ID = %(c)s AND G.SEGMENT_ID = %(s)s AND W.CAMPAIGN_ID IS NULL
        """,
        {"c": campaign_id, "s": segment_id},
    )
    return rows_affected(rows, "inserted")


def selection_working(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET, SELECTION_PERCENTAGE, IS_DIRTY, INITIALIZATION_METHOD,
               SOURCE_CAMPAIGN_ID, ROW_VERSION
        FROM {SCHEMA}.DM_PADM_SELECTION_WORKING WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
        """,
        {"c": campaign_id, "s": segment_id},
    )


def prior_selection(session, campaign_id, segment_id):
    """Prior month's saved selection cells for this segment (drives the yellow highlight)."""
    return df(
        session,
        f"""
        SELECT PC.RESPONSE_MODEL_TIER, PC.TIMES_MAILED_BUCKET, PC.SELECTION_PERCENTAGE, PRIOR_C.CAMPAIGN_DISPLAY_NAME
        FROM {SCHEMA}.DM_PADM_SELECTION_SET SS
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 PRIOR_C ON SS.CAMPAIGN_ID = PRIOR_C.CAMPAIGN_ID
        JOIN {SCHEMA}.DM_PADM_CAMPAIGN_1 CUR ON CUR.CAMPAIGN_ID = %(c)s
        JOIN {SCHEMA}.DM_PADM_SELECTION_SET_CELL PC ON PC.SELECTION_SET_ID = SS.SELECTION_SET_ID
        WHERE SS.SEGMENT_ID = %(s)s AND SS.IS_CURRENT = TRUE AND SS.CAMPAIGN_ID <> %(c)s
          AND PRIOR_C.REPORTING_MONTH <= CUR.REPORTING_MONTH
        QUALIFY DENSE_RANK() OVER (ORDER BY PRIOR_C.REPORTING_MONTH DESC, SS.CREATED_TS DESC) = 1
        """,
        {"c": campaign_id, "s": segment_id},
    )


def selection_history(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT CHANGED_TS, CHANGED_BY, ACTION_TYPE, TIER_FROM, TIER_TO, TIMES_MAILED_FROM, TIMES_MAILED_TO,
               ENTERED_PERCENTAGE, CHANGED_CELL_COUNT, CHANGE_REASON, SELECTION_SET_ID
        FROM {SCHEMA}.DM_PADM_SELECTION_EVENT
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s ORDER BY CHANGED_TS DESC LIMIT 200
        """,
        {"c": campaign_id, "s": segment_id},
    )


def save_selections(session, campaign_id, segment_id, changes, actions, reason):
    """changes: [(tier, bucket, new_fraction, expected_row_version, old_fraction)].
    actions: user actions since the last save, logged one row each in DM_PADM_SELECTION_EVENT
    (like Excel change tracking). Then SP_PADM_SAVE_SELECTION_SET creates the immutable set."""
    _assert_editable(session, campaign_id)
    if not changes:
        raise ProcedureError("No selection changes to save.")
    binds = [v for tier, bucket, pct, rv, _ in changes for v in (int(tier), str(bucket), float(pct), int(rv))]
    with transaction(session):
        rows = exec_sql(
            session,
            f"""
            UPDATE {SCHEMA}.DM_PADM_SELECTION_WORKING W
            SET SELECTION_PERCENTAGE = V.PCT, IS_DIRTY = TRUE, INITIALIZATION_METHOD = 'USER_EDIT',
                ROW_VERSION = W.ROW_VERSION + 1, UPDATED_BY = CURRENT_USER(), UPDATED_TS = CURRENT_TIMESTAMP()
            FROM (VALUES {_values(len(changes), 4)}) AS V(TIER, BUCKET, PCT, RV)
            WHERE W.CAMPAIGN_ID = ? AND W.SEGMENT_ID = ?
              AND W.RESPONSE_MODEL_TIER = V.TIER AND W.TIMES_MAILED_BUCKET = V.BUCKET AND W.ROW_VERSION = V.RV
            """,
            [*binds, campaign_id, segment_id],
        )
        if rows_affected(rows, "updated") != len(changes):
            raise ProcedureError(STALE_MESSAGE)
        for action in actions or [{"ACTION_TYPE": "CELL_EDIT"}]:
            exec_sql(
                session,
                f"""
                INSERT INTO {SCHEMA}.DM_PADM_SELECTION_EVENT
                    (SELECTION_EVENT_ID, CAMPAIGN_ID, SEGMENT_ID, ACTION_TYPE, TIER_FROM, TIER_TO,
                     TIMES_MAILED_FROM, TIMES_MAILED_TO, ENTERED_PERCENTAGE, CHANGED_CELL_COUNT,
                     PRIOR_VALUE_SUMMARY, CHANGE_REASON)
                SELECT UUID_STRING(), %(c)s, %(s)s, %(a)s, %(tf)s, %(tt)s, %(mf)s, %(mt)s, %(p)s, %(n)s,
                       PARSE_JSON(%(prior)s), %(r)s
                """,
                {
                    "c": campaign_id, "s": segment_id, "a": action.get("ACTION_TYPE", "CELL_EDIT"),
                    "tf": action.get("TIER_FROM"), "tt": action.get("TIER_TO"),
                    "mf": action.get("TIMES_MAILED_FROM"), "mt": action.get("TIMES_MAILED_TO"),
                    "p": action.get("ENTERED_PERCENTAGE"), "n": action.get("CHANGED_CELL_COUNT"),
                    "prior": json.dumps([{"tier": t, "tm": b, "before": o, "after": p}
                                         for t, b, p, _, o in changes][:500]),
                    "r": reason,
                },
            )
        return call_proc(session, "SP_PADM_SAVE_SELECTION_SET", [campaign_id, segment_id, reason])


def segment_calculation(session, campaign_id, segment_id):
    return df(
        session,
        f"SELECT * FROM {SCHEMA}.VW_PADM_SEGMENT_CALCULATION_CURRENT WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s",
        {"c": campaign_id, "s": segment_id},
    )


def mailfile_cells(session, campaign_id, segment_id):
    return df(
        session,
        f"""
        SELECT RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET, SUM(MAIL_QUANTITY) AS MAIL_QUANTITY, MAX(SOURCE_NAME) AS SOURCE_NAME
        FROM {SCHEMA}.DM_PADM_MAILFILE_CELL
        WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s AND IS_CURRENT = TRUE
        GROUP BY RESPONSE_MODEL_TIER, TIMES_MAILED_BUCKET
        """,
        {"c": campaign_id, "s": segment_id},
    )


def load_cde_version(session, campaign_id, segment_id, raw_bytes, file_name, score_band, cells, total_rows, reason):
    """New DM_PADM_CDE_LOAD_BATCH + DM_PADM_CDE_DETAIL cells, activated through
    SP_PADM_ACTIVATE_CDE_VERSION, then the selection working grid is seeded.
    cells: DataFrame with TRM10_TIER, TIMES_MAILED_BUCKET, DISTINCT_EPIN_COUNT."""
    _assert_editable(session, campaign_id)
    batch_id = str(uuid.uuid4())
    with transaction(session):
        exec_sql(
            session,
            f"""
            INSERT INTO {SCHEMA}.DM_PADM_CDE_LOAD_BATCH
                (CDE_LOAD_BATCH_ID, CAMPAIGN_ID, SEGMENT_ID, VERSION_NUMBER, SOURCE_FILE_NAME, SOURCE_FILE_HASH,
                 LOAD_STATUS, VALIDATION_STATUS, ACTIVE_FLAG, SOURCE_ROW_COUNT, LOADED_ROW_COUNT, REJECTED_ROW_COUNT,
                 SOURCE_TOTAL_VOLUME, CHANGE_REASON, VALIDATED_BY, VALIDATED_TS)
            SELECT %(id)s, %(c)s, %(s)s, COALESCE(MAX(VERSION_NUMBER), 0) + 1, %(f)s, %(h)s,
                   'LOADED', 'VALID', FALSE, %(total)s, %(loaded)s, %(rejected)s,
                   %(vol)s, %(r)s, CURRENT_USER(), CURRENT_TIMESTAMP()
            FROM {SCHEMA}.DM_PADM_CDE_LOAD_BATCH WHERE CAMPAIGN_ID = %(c)s AND SEGMENT_ID = %(s)s
            """,
            {"id": batch_id, "c": campaign_id, "s": segment_id, "f": file_name,
             "h": hashlib.sha256(raw_bytes).hexdigest(), "total": int(total_rows), "loaded": int(len(cells)),
             "rejected": int(total_rows - len(cells)), "vol": int(cells["DISTINCT_EPIN_COUNT"].sum()), "r": reason},
        )
        values = [(str(r.TIMES_MAILED_BUCKET), int(r.TRM10_TIER), int(round(r.DISTINCT_EPIN_COUNT)), i + 1)
                  for i, r in enumerate(cells.itertuples())]
        exec_sql(
            session,
            f"""
            INSERT INTO {SCHEMA}.DM_PADM_CDE_DETAIL
                (CDE_DETAIL_ID, CDE_LOAD_BATCH_ID, CAMPAIGN_ID, SEGMENT_ID, VANTAGE_SCORE_BAND,
                 TIMES_MAILED_BUCKET, TRM10_TIER, DISTINCT_EPIN_COUNT, SOURCE_ROW_NUMBER)
            SELECT UUID_STRING(), ?, ?, ?, ?, V.BUCKET, V.TIER, V.VOLUME, V.ROW_NUM
            FROM (VALUES {_values(len(values), 4)}) AS V(BUCKET, TIER, VOLUME, ROW_NUM)
            """,
            [batch_id, campaign_id, segment_id, score_band, *[v for row in values for v in row]],
        )
    message = call_proc(session, "SP_PADM_ACTIVATE_CDE_VERSION", [batch_id, reason])
    seeded = ensure_working_grid(session, campaign_id, segment_id)
    return message, seeded
