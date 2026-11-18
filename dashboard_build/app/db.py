SCHEMA = "DB_RISK.RISK_SBX"


def df(session, sql, params=None):
    return session.sql(sql, params=params or []).to_pandas()


def exec_sql(session, sql, params=None):
    session.sql(sql, params=params or []).collect()


def call_proc(session, proc_name, params):
    placeholders = ", ".join(["%s"] * len(params))
    rows = session.sql(f"CALL {proc_name}({placeholders})", params=params).collect()
    return rows[0][0] if rows else None
