"""UI pieces shared by every tab: header bar, read-only lock, actions/flash messages, change
reason boxes, Tier x Times Mailed grids and the signature-page table."""

import math

import pandas as pd
import streamlit as st

from padm import repository
from padm.db import ProcedureError, clear_read_cache
from padm.formulas import pivot_grid

CAMPAIGN_KEY = "campaign_id"
TYPE_LABELS = {"MAIN": "PRIMARY (MAIN)", "REMAIL": "REMAIL"}

# ---------------------------------------------------------------------------
# Campaign context + header (spec 1.2)
# ---------------------------------------------------------------------------


def campaign_context(session):
    """The campaign selected on Tab 1 as a dict, or None."""
    campaign_id = st.session_state.get(CAMPAIGN_KEY)
    if not campaign_id:
        return None
    header = repository.campaign_header(session, campaign_id)
    if header.empty:
        st.session_state.pop(CAMPAIGN_KEY, None)
        return None
    row = header.iloc[0]
    return {
        "id": campaign_id,
        "name": row["CAMPAIGN_DISPLAY_NAME"],
        "status": row["STATUS"],
        "type": row["CAMPAIGN_TYPE"],
        "reporting_month": row["REPORTING_MONTH"],
        "mail_date_min": row["SOURCE_MIN_MAIL_DATE"],
        "mail_date_max": row["SOURCE_MAX_MAIL_DATE"],
        "working_version": int(row["CURRENT_WORKING_VERSION_NUMBER"] or 1),
        "row_version": int(row["ROW_VERSION"] or 1),
        "source_change_pending": bool(row["SOURCE_CHANGE_PENDING_FLAG"]),
        "locked": row["STATUS"] == repository.READ_ONLY_STATUS,
        "activated": row["STATUS"] != "NEW",
    }


def _mail_date(campaign):
    lo, hi = campaign["mail_date_min"], campaign["mail_date_max"]
    if lo is None or (isinstance(lo, float) and math.isnan(lo)):
        return "-"
    return str(lo) if lo == hi else f"{lo} - {hi}"


def header_bar(campaign):
    with st.container(border=True):
        cols = st.columns([3, 2, 2, 2, 1])
        cols[0].markdown(f"**Campaign**  \n{campaign['name']}")
        cols[1].markdown(f"**Mail Date**  \n{_mail_date(campaign)}")
        cols[2].markdown(f"**Campaign Type**  \n{TYPE_LABELS.get(campaign['type'], campaign['type'])}")
        cols[3].markdown(f"**Status**  \n:blue-badge[{campaign['status']}]")
        cols[4].markdown(f"**Version**  \n{campaign['working_version']}")
    if campaign["locked"]:
        st.info("Approved - read only", icon=":material/lock:")
    if campaign["source_change_pending"]:
        st.warning("ACM source data changed after this campaign was activated. Review the offers on the "
                    "Campaign Creation tab.", icon=":material/sync_problem:")


def require_campaign(session, need_activation=True):
    """Gate for Tabs 2-7: returns the campaign (after drawing the header) or None."""
    campaign = campaign_context(session)
    if campaign is None:
        st.info("Select or create a campaign on the **Campaign Creation** tab to unlock this tab.",
                icon=":material/lock:")
        return None
    header_bar(campaign)
    if need_activation and not campaign["activated"]:
        st.warning("This campaign is NEW: activate it on the Campaign Creation tab to snapshot its ACM offers.")
        return None
    return campaign


# ---------------------------------------------------------------------------
# Actions + flash messages (messages survive the st.rerun() after a write)
# ---------------------------------------------------------------------------


def flash(scope, message, kind="success"):
    st.session_state.setdefault("_flash", []).append((scope, kind, str(message)))


def show_flash(scope):
    keep = []
    for item_scope, kind, message in st.session_state.get("_flash", []):
        if item_scope == scope:
            getattr(st, kind)(message)
        else:
            keep.append((item_scope, kind, message))
    st.session_state["_flash"] = keep


def run_action(scope, action, success_message=None, on_success=None):
    """Runs a write; on success flashes the message and reruns so every tab re-reads.
    Procedure refusals / Snowflake errors are shown inline and the user's inputs are kept."""
    try:
        result = action()
    except ProcedureError as exc:
        st.error(str(exc))
        return
    except Exception as exc:  # Snowflake error text is the most useful thing to show
        st.error(f"{exc}")
        return
    if on_success:
        on_success(result)
    message = success_message(result) if callable(success_message) else (success_message or result)
    flash(scope, message)
    st.rerun()


def reason_input(key, disabled=False, label="Change reason (required)"):
    return st.text_input(label, key=key, disabled=disabled, placeholder="Why is this change being made?")


def require_reason(reason):
    if not reason or not reason.strip():
        st.error("A change reason is required.")
        return False
    return True


def refresh_button():
    if st.button("Refresh data", icon=":material/refresh:", help="Re-read everything from Snowflake"):
        clear_read_cache()
        st.rerun()


def num(value):
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Tier x Times Mailed grids (spec 7.2)
# ---------------------------------------------------------------------------

_FORMATS = {
    "localized": "{:,.0f}",
    "percent": "{:.2%}",
    "dollar": "${:,.2f}",
    "%.1f": "{:,.1f}",
    "%.2f": "{:,.2f}",
}


def grid_height(grid, extra_rows=0):
    return (len(grid) + 1 + extra_rows) * 35 + 3


def _grid_cell_text(value, fmt):
    """Only non-zero values are shown (user's explicit call, matching the real Segment.xlsx) --
    NULL and exact-zero cells render blank, not '0' / '0.00%' / '-'."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v == 0:
        return ""
    return _FORMATS.get(fmt, "{:,.2f}").format(v)


def styled(grid, fmt, highlight=None):
    """Styler: blank for NULL/zero cells (see _grid_cell_text), optional per-cell background
    (DataFrame of CSS)."""
    styler = grid.style.format(lambda v: _grid_cell_text(v, fmt))
    if highlight is not None:
        styler = styler.apply(lambda _: highlight.reindex_like(grid).fillna(""), axis=None)
    return styler.set_properties(subset=pd.IndexSlice[["Total"], :], **{"font-weight": "bold"}) \
        if "Total" in grid.index else styler


def render_grid(cells, title, value_col, fmt, caption, ratio=None, extra_row=None, key=None):
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(caption)
        if cells.empty or value_col not in cells.columns:
            st.caption("No data.")
            return None
        grid = pivot_grid(cells, value_col, ratio=ratio)
        if extra_row is not None:
            label, values, row_fmt = extra_row
            shown = grid.copy().astype(object)
            shown = shown.apply(lambda col: col.map(lambda v: _grid_cell_text(v, fmt)))
            shown.loc[label] = [_grid_cell_text(v, row_fmt) for v in values.reindex(grid.columns)]
            st.dataframe(shown, height=grid_height(shown), key=key)
        else:
            st.dataframe(styled(grid, fmt), height=grid_height(grid), key=key)
        return grid


# ---------------------------------------------------------------------------
# Signature page table (spec 3.2 column order) -- Tabs 2 and 7
# ---------------------------------------------------------------------------

# (source column, label, format, calculated?)
SIGNATURE_COLUMNS = [
    ("SEGMENT_DESCRIPTION", "Segment Description", None, False),
    ("ANNUAL_FEE", "AF", None, False),
    ("TEST_TYPE", "Test Type", None, False),
    ("NETWORK", "Network", None, False),
    ("CREDIT_BUREAU_MODEL", "Credit Bureau Model", None, False),
    ("CREDIT_BUREAU_SCORE", "Credit Bureau Score", None, False),
    ("CRS_MODEL", "CRS Model", None, False),
    ("CRS_SCORE", "CRS Score", None, False),
    ("NRM", "NRM", None, False),
    ("QUANTITY", "Quantity", "localized", False),
    ("NBR", "NBR", "percent", True),
    ("BOARDS", "Boards", "%.1f", True),
    ("CPP", "CPP", "dollar4", False),
    ("MARKETING_EXPENSE", "Marketing Expense", "dollar", True),
    ("UNWIND_RATE", "Unwind Rate", "percent", True),
    ("PRE_UNWIND_CPA", "Pre-Unwind CPA", "dollar", True),
    ("POST_UNWIND_CPA", "Post-Unwind CPA", "dollar", True),
    ("PROMO", "PROMO", None, False),
    ("IVR", "IVR", None, False),
    ("UNDERWRITING_FLAG", "Underwriting Flag", None, False),
    ("PROSPECT_TYPE", "Prospect Type", None, False),
    ("TIMES_MAILED_0_PERCENTAGE", "Times Mailed 0%", "percent", False),
    ("TIERS", "Tiers", None, False),
    ("PRINT_VENDOR", "Print Vendor", None, False),
    ("POST_UNWIND_BOARDS", "Post-Unwind Boards", "%.1f", True),
    ("MARKETING_PLUS_BOOKING_COSTS", "Marketing + Booking Costs", "dollar", True),
    ("UNIT_COST", "Unit Cost", "dollar", False),
]
SUM_COLUMNS = ["QUANTITY", "BOARDS", "MARKETING_EXPENSE", "POST_UNWIND_BOARDS", "MARKETING_PLUS_BOOKING_COSTS"]
_CELL_FORMATS = {**_FORMATS, "dollar4": "${:,.4f}"}


def _fmt(value, fmt):
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return "-"
    if fmt is None:
        return str(value)
    try:
        return _CELL_FORMATS[fmt].format(float(value))
    except (TypeError, ValueError):
        return str(value)


def signature_totals(rows):
    """Subtotal row: sums for volumes/costs, weighted ratios for rates and CPAs."""
    def s(col):
        return pd.to_numeric(rows[col], errors="coerce").fillna(0).sum() if col in rows.columns else 0.0

    qty, boards, mkt = s("QUANTITY"), s("BOARDS"), s("MARKETING_EXPENSE")
    post, mkt_book = s("POST_UNWIND_BOARDS"), s("MARKETING_PLUS_BOOKING_COSTS")
    weighted_unwind = (pd.to_numeric(rows.get("UNWIND_RATE"), errors="coerce").fillna(0)
                        * pd.to_numeric(rows.get("BOARDS"), errors="coerce").fillna(0)).sum() if "UNWIND_RATE" in rows else 0
    return {
        "QUANTITY": qty, "BOARDS": boards, "MARKETING_EXPENSE": mkt, "POST_UNWIND_BOARDS": post,
        "MARKETING_PLUS_BOOKING_COSTS": mkt_book,
        "NBR": boards / qty if qty else None,
        "CPP": mkt / qty if qty else None,
        "UNWIND_RATE": weighted_unwind / boards if boards else None,
        "PRE_UNWIND_CPA": mkt / boards if boards else None,
        "POST_UNWIND_CPA": mkt_book / post if post else None,
    }


def signature_display(rows, mask_calculated=False):
    """rows -> display frame with spec labels/order. mask_calculated shows 'pending' (Tab 2)."""
    out = pd.DataFrame(index=rows.index)
    for source, label, fmt, calculated in SIGNATURE_COLUMNS:
        if mask_calculated and calculated:
            out[label] = "pending"
        elif source in rows.columns:
            out[label] = [_fmt(v, fmt) for v in rows[source]]
        else:
            out[label] = "-"
    return out


def totals_display(totals, label, mask_calculated=False):
    row = {}
    for source, col_label, fmt, calculated in SIGNATURE_COLUMNS:
        if source == "SEGMENT_DESCRIPTION":
            row[col_label] = label
        elif mask_calculated and calculated:
            row[col_label] = "pending"
        elif source in totals:
            row[col_label] = _fmt(totals[source], fmt)
        else:
            row[col_label] = ""
    return pd.DataFrame([row])


# Columns whose real value is per-SEGMENT, not per-offer: VW_PADM_SIGNATURE_PAGE_LIVE's
# calculation join is on (CAMPAIGN_ID, SEGMENT_ID) only, with no offer dimension, so these are
# already identical across every offer row within the same segment (confirmed from the view's own
# SQL). Everything else in SIGNATURE_COLUMNS is a real per-offer attribute (Test Type, Promo, IVR,
# etc.) that can legitimately differ between offers in the same segment.
SEGMENT_LEVEL_COLUMNS = {
    "QUANTITY", "NBR", "BOARDS", "CPP", "MARKETING_EXPENSE", "UNWIND_RATE", "PRE_UNWIND_CPA",
    "POST_UNWIND_CPA", "TIMES_MAILED_0_PERCENTAGE", "TIERS", "POST_UNWIND_BOARDS",
    "MARKETING_PLUS_BOOKING_COSTS",
}


def collapse_to_segment(rows):
    """Signature Page (Tab 2) shows one row per segment, not one per offer (user's explicit call,
    2026-11-19). Also fixes a real pre-existing issue, not just a cosmetic one: because the
    segment-level calculated columns above are repeated identically across every offer row in a
    segment, summing them per-offer (the old flat display) inflated GRAND TOTAL by that segment's
    offer count. Collapsing first means each segment's numbers are only counted once.

    Offer-level columns that vary between offers in the same segment are shown as a distinct-value
    summary rather than silently picking one and discarding the rest."""
    if rows.empty or "SEGMENT_ID" not in rows.columns:
        return rows
    with_segment = rows[rows["SEGMENT_ID"].notna()].copy()
    without_segment = rows[rows["SEGMENT_ID"].isna()]
    if with_segment.empty:
        return rows
    collapsed_rows = []
    for segment_id, group in with_segment.groupby("SEGMENT_ID", sort=False):
        row = {"SEGMENT_ID": segment_id, "OFFER_COUNT": len(group)}
        for col in group.columns:
            if col in ("SEGMENT_ID", "CAMPAIGN_OFFER_ID"):
                continue
            if col in SEGMENT_LEVEL_COLUMNS:
                row[col] = group[col].iloc[0]
                continue
            distinct = sorted(group[col].dropna().astype(str).unique())
            if len(distinct) == 0:
                row[col] = None
            elif len(distinct) == 1:
                row[col] = distinct[0]
            else:
                shown = ", ".join(distinct[:3]) + (", ..." if len(distinct) > 3 else "")
                row[col] = f"{len(distinct)} distinct ({shown})"
        collapsed_rows.append(row)
    collapsed = pd.DataFrame(collapsed_rows)
    return pd.concat([collapsed, without_segment], ignore_index=True) if not without_segment.empty else collapsed


def signature_frame(rows, mask_calculated=False, group_by_population=False):
    """Display frame: flat + grand total, or population groups with sub-totals + grand total."""
    if not group_by_population:
        return pd.concat([signature_display(rows, mask_calculated),
                           totals_display(signature_totals(rows), "GRAND TOTAL", mask_calculated)], ignore_index=True)
    rows = rows.copy()
    rows["_GROUP"] = rows["POPULATION_DESCRIPTION"].fillna("UNASSIGNED").astype(str)
    parts = []
    for group, group_rows in rows.groupby("_GROUP", sort=False):
        parts += [totals_display({}, f"> {group}"), signature_display(group_rows, mask_calculated),
                  totals_display(signature_totals(group_rows), f"Sub-total - {group}", mask_calculated)]
    parts.append(totals_display(signature_totals(rows), "GRAND TOTAL", mask_calculated))
    return pd.concat(parts, ignore_index=True)


def is_total_label(text):
    return str(text).startswith(("Sub-total", "GRAND TOTAL", ">"))


def render_signature_page(rows, key, mask_calculated=False, group_by_population=False):
    """Flat table (Tab 2) or grouped by population description with sub-totals (Tab 7)."""
    config = {"Segment Description": st.column_config.TextColumn("Segment Description", pinned=True)}
    frame = signature_frame(rows, mask_calculated, group_by_population)

    def bold(row):
        text = str(row["Segment Description"])
        weight = "font-weight: bold" if text.startswith(("Sub-total", "GRAND TOTAL", ">")) else ""
        return [weight] * len(row)

    st.dataframe(frame.style.apply(bold, axis=1), hide_index=True, column_config=config, key=key)
