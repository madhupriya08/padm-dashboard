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
            subtitle="Population Description -- label allocated segments per offer",
        )

    groups = queries.population_allocation_groups(session, campaign_id)
    if groups.empty:
        st.info("No offer-to-segment allocations yet. Create segments first on the Create Segment tab.")
        return

    for (offer_code, score), group in groups.groupby(["OFFER_RESERVATION_CODE", "CRS_SCORE"], dropna=False):
        with st.expander(f"Offer {offer_code}  |  Score {score}", expanded=False):
            st.dataframe(
                group[["SEGMENT_NAME", "POPULATION_DESCRIPTION"]],
                use_container_width=True, hide_index=True,
            )
            subtotal = queries.population_subtotal(session, campaign_id, offer_code, score)
            if subtotal is not None:
                ui.chips(
                    f"Quantity {subtotal.get('QUANTITY') or 0:,.0f}",
                    f"Boards {subtotal.get('BOARDS') or 0:,.0f}",
                )

            selected_segment_names = st.multiselect(
                "Segments to label",
                options=group["SEGMENT_ID"].tolist(),
                format_func=lambda sid: group.loc[group["SEGMENT_ID"] == sid, "SEGMENT_NAME"].iloc[0],
                key=f"ms_{offer_code}_{score}",
            )
            label = st.text_input("Population description", key=f"label_{offer_code}_{score}")
            reason = st.text_input("Change reason (required)", key=f"reason_{offer_code}_{score}")

            if st.button("Apply label", key=f"apply_{offer_code}_{score}", disabled=not selected_segment_names):
                if not reason.strip():
                    st.error("A change reason is required.")
                else:
                    for segment_id in selected_segment_names:
                        allocation_id = group.loc[group["SEGMENT_ID"] == segment_id, "OFFER_SEGMENT_ALLOCATION_ID"].iloc[0]
                        repository.set_population_description(session, allocation_id, label, reason)
                    st.success(f"Updated population description for {len(selected_segment_names)} segment(s).")
                    st.rerun()
