import pandas as pd
import streamlit as st


def require_campaign():
    campaign_id = st.session_state.get("selected_campaign_id")
    if not campaign_id:
        st.warning("Open or create a campaign first on the Campaign Creation tab.")
        st.stop()
    return campaign_id


def pivot_grid(cells: pd.DataFrame, value_col: str, agg="sum"):
    if cells.empty:
        return pd.DataFrame()
    pivoted = cells.pivot_table(
        index="RESPONSE_MODEL_TIER",
        columns="TIMES_MAILED_BUCKET",
        values=value_col,
        aggfunc=agg,
        fill_value=0,
    )
    bucket_order = [str(i) for i in range(9)] + ["9+"]
    ordered_cols = [c for c in bucket_order if c in pivoted.columns]
    pivoted = pivoted[ordered_cols]
    pivoted.loc["Total"] = pivoted.sum(numeric_only=True)
    pivoted["Total"] = pivoted.sum(axis=1, numeric_only=True)
    return pivoted


def highlight_nonzero_yellow(val):
    try:
        return "background-color: #fff3b0" if float(val) > 0 else ""
    except (TypeError, ValueError):
        return ""
