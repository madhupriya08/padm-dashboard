import streamlit as st

from app import queries, repository, ui
from app.pages._shared import require_campaign


def render(session):
    campaign_id = require_campaign()
    campaign = queries.campaign_header(session, campaign_id)
    if not campaign.empty:
        ui.campaign_banner(
            campaign.iloc[0]["CAMPAIGN_DISPLAY_NAME"],
            campaign.iloc[0]["STATUS"],
            subtitle="Campaign Assumptions -- CPP, unit cost, and rate adjustments",
        )

    ui.section_title("Campaign-level")
    current = queries.campaign_assumption_current(session, campaign_id)
    row = current.iloc[0] if not current.empty else None

    with st.form("campaign_assumption_form"):
        c1, c2, c3 = st.columns(3)
        cpp = c1.number_input("CPP", value=float(row["CPP"]) if row is not None and row["CPP"] is not None else 0.0, step=0.01, format="%.4f")
        unit_cost = c2.number_input("Unit Cost", value=float(row["UNIT_COST"]) if row is not None and row["UNIT_COST"] is not None else 0.0, step=0.01, format="%.4f")
        rate_adjustment = c3.number_input("Rate Adjustment", value=float(row["RATE_ADJUSTMENT"]) if row is not None and row["RATE_ADJUSTMENT"] is not None else 0.0, step=0.01, format="%.4f")
        c4, c5 = st.columns(2)
        seasonality = c4.slider("Seasonality Reduction", 0.0, 1.0, float(row["SEASONALITY_REDUCTION"]) if row is not None and row["SEASONALITY_REDUCTION"] is not None else 0.0)
        unwind_adj = c5.number_input("Unwind Rate Adjustment", value=float(row["UNWIND_RATE_ADJUSTMENT"]) if row is not None and row["UNWIND_RATE_ADJUSTMENT"] is not None else 0.0, step=0.01, format="%.4f")
        reason = st.text_input("Change reason (required)")
        submitted = st.form_submit_button("Save campaign assumptions")

    if rate_adjustment < 0 or unwind_adj < 0:
        st.warning(
            "A negative rate adjustment is mathematically allowed here, but per PADM_CLARIFICATIONS this needs "
            "sign-off from the assumptions owner before it's used -- confirm before saving."
        )

    if submitted:
        if not reason.strip():
            st.error("A change reason is required.")
        else:
            result = repository.save_campaign_assumption(session, campaign_id, cpp, unit_cost, rate_adjustment, seasonality, unwind_adj, reason)
            st.success(result)
            st.rerun()

    with st.expander("Campaign assumption version history"):
        st.dataframe(queries.campaign_assumption_history(session, campaign_id), use_container_width=True, hide_index=True)

    st.divider()
    st.caption(
        "Segment-level overrides moved to the Segment Viewer tab -- set them there, right before the CDE "
        "upload and the grids they feed, so the change and its effect on the calculated grids stay on one page."
    )
