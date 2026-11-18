import streamlit as st

from app import queries, ui
from app.pages._shared import require_campaign

DISPLAY_COLUMNS = {
    "SEGMENT_DESCRIPTION": "Segment Description",
    "ANNUAL_FEE": "AF",
    "TEST_TYPE": "Test Type",
    "NETWORK": "Network",
    "CREDIT_BUREAU_MODEL": "Credit Bureau Model",
    "CREDIT_BUREAU_SCORE": "Credit Bureau Score",
    "CRS_MODEL": "CRS Model",
    "CRS_SCORE": "CRS Score",
    "NRM": "NRM",
    "QUANTITY": "Quantity",
    "NBR": "NBR",
    "BOARDS": "Boards",
    "CPP": "CPP",
    "MARKETING_EXPENSE": "Marketing Expense",
    "UNWIND_RATE": "Unwind Rate",
    "PRE_UNWIND_CPA": "Pre-Unwind CPA",
    "POST_UNWIND_CPA": "Post-Unwind CPA",
    "PROMO": "PROMO",
    "IVR": "IVR",
    "UNDERWRITING_FLAG": "Underwriting Flag",
    "PROSPECT_TYPE": "Prospect Type",
    "TIMES_MAILED_0_PERCENTAGE": "Times Mailed 0%",
    "TIERS": "Tiers",
    "PRINT_VENDOR": "Print Vendor",
    "POST_UNWIND_BOARDS": "Post-Unwind Boards",
    "MARKETING_PLUS_BOOKING_COSTS": "Marketing + Booking Costs",
}


def render(session):
    campaign_id = require_campaign()

    campaign = queries.campaign_header(session, campaign_id)
    if campaign.empty:
        st.error("Selected campaign not found.")
        st.stop()
    ui.campaign_banner(
        campaign.iloc[0]["CAMPAIGN_DISPLAY_NAME"],
        campaign.iloc[0]["STATUS"],
        subtitle="Signature Page -- live values, recalculates as assumptions/allocations/selections change",
    )

    grid = queries.signature_live_grid(session, campaign_id)
    if grid.empty:
        st.info(
            "No segments/offers allocated yet for this campaign. "
            "Go to Create Segment to allocate offers before this page has values."
        )
        return

    # Grouped by Credit Bureau Model + Score, per the sign-off proposal's Signature Page field
    # mapping. Requires sql/30_wire_credit_bureau_fields.sql to have been run -- otherwise these
    # are NULL for any offer activated before that script.
    for (model, score), group in grid.groupby(["CREDIT_BUREAU_MODEL", "CREDIT_BUREAU_SCORE"], dropna=False):
        with st.expander(f"Credit Bureau Model {model or 'Unknown'} / Score {score or 'Unknown'} ({len(group)} segments)", expanded=True):
            shown = group.rename(columns=DISPLAY_COLUMNS)[[v for v in DISPLAY_COLUMNS.values() if v in group.rename(columns=DISPLAY_COLUMNS).columns]]
            st.dataframe(shown, use_container_width=True, hide_index=True)
            numeric_cols = group.select_dtypes("number").columns
            subtotal = group[numeric_cols].sum(numeric_only=True)
            ui.chips(
                f"Quantity {subtotal.get('QUANTITY', 0):,.0f}",
                f"Boards {subtotal.get('BOARDS', 0):,.0f}",
                f"Marketing + Booking ${subtotal.get('MARKETING_PLUS_BOOKING_COSTS', 0):,.2f}",
            )

    st.divider()
    numeric_cols = grid.select_dtypes("number").columns
    grand_total = grid[numeric_cols].sum(numeric_only=True)
    ui.section_title("Grand Total")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Quantity", f"{grand_total.get('QUANTITY', 0):,.0f}")
    c2.metric("Total Boards", f"{grand_total.get('BOARDS', 0):,.0f}")
    c3.metric("Total Marketing + Booking Costs", f"${grand_total.get('MARKETING_PLUS_BOOKING_COSTS', 0):,.2f}")
