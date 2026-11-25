"""Snowflake access helpers. SQL uses named placeholders %(name)s; reads are cached and cleared on write."""

import re
from contextlib import contextmanager

import streamlit as st

SCHEMA = "DB_RISK.RISK_SBX"
ACM = "CSTONE_BIZ.REFERENCE"

_NAMED_PLACEHOLDER = re.compile(r"%\((\w+)\)s")
READ_CACHE_TTL_SECONDS = 30


class ProcedureError(RuntimeError):
    """A SP_PADM_* procedure refused the request (its message starts with 'ERROR: ')."""


def _to_python(value):
    """numpy/pandas scalars -> plain Python so the connector can bind them."""
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value


def _bind(sql, params):
    if not params:
        return sql, []
    if isinstance(params, (list, tuple)):
        return sql, [_to_python(v) for v in params]
    names = _NAMED_PLACEHOLDER.findall(sql)
    return _NAMED_PLACEHOLDER.sub("?", sql), [_to_python(params[n]) for n in names]


@st.cache_data(ttl=READ_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_df(_session, sql, binds):
    return _session.sql(sql, params=list(binds)).to_pandas()


def df(session, sql, params=None):
    sql, binds = _bind(sql, params)
    return _cached_df(session, sql, tuple(binds))


def clear_read_cache():
    _cached_df.clear()


def exec_sql(session, sql, params=None):
    sql, binds = _bind(sql, params)
    rows = session.sql(sql, params=binds).collect()
    clear_read_cache()
    return rows


def call_proc(session, proc_name, params):
    """CALL a procedure; raises ProcedureError when it returns an 'ERROR: ...' message."""
    placeholders = ", ".join(["?"] * len(params))
    rows = session.sql(
        f"CALL {SCHEMA}.{proc_name}({placeholders})", params=[_to_python(p) for p in params]
    ).collect()
    clear_read_cache()
    result = str(rows[0][0]) if rows and rows[0][0] is not None else ""
    if result.startswith("ERROR:"):
        raise ProcedureError(result[len("ERROR:"):].strip())
    return result


def rows_affected(rows, kind):
    """kind: 'inserted' / 'updated' / 'deleted'."""
    return int(rows[0].as_dict().get(f"number of rows {kind}", 0)) if rows else 0


@contextmanager
def transaction(session):
    """Explicit transaction for multi-statement writes -- not for CALLs, procedures manage their own."""
    session.sql("BEGIN").collect()
    try:
        yield
        session.sql("COMMIT").collect()
    except Exception:
        session.sql("ROLLBACK").collect()
        raise
    finally:
        clear_read_cache()
