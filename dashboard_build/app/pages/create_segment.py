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
            subtitle="Create Segment -- allocate offers to governed segments",
        )

    ui.section_title("Unallocated offers")
    unallocated = queries.unallocated_offers(session, campaign_id)
    if unallocated.empty:
        st.success("All offers in this campaign are allocated to a segment.")
    else:
        st.dataframe(unallocated, use_container_width=True, hide_index=True)

    st.divider()
    ui.section_title("Assign selected offers to a segment")

    if unallocated.empty:
        st.caption("No unallocated offers to assign.")
    else:
        selected_offer_ids = st.multiselect(
            "Offers to assign",
            options=unallocated["CAMPAIGN_OFFER_ID"].tolist(),
            format_func=lambda oid: unallocated.loc[unallocated["CAMPAIGN_OFFER_ID"] == oid, "OFFER_RESERVATION_CODE"].iloc[0],
        )

        segments = queries.existing_segments(session)
        mode = st.radio("Segment", ["Use an existing governed segment", "Create a new governed segment"], horizontal=True)

        if mode == "Use an existing governed segment" and not segments.empty:
            segment_id = st.selectbox(
                "Existing segment",
                options=segments["SEGMENT_ID"].tolist(),
                format_func=lambda sid: segments.loc[segments["SEGMENT_ID"] == sid, "SEGMENT_NAME"].iloc[0],
            )
            new_segment_fields = None
        else:
            segment_id = None
            with st.form("new_segment_form"):
                segment_name = st.text_input("Segment name")
                col1, col2 = st.columns(2)
                score_type = col1.text_input("Bureau Score Type")
                prospect_type = col2.text_input("Prospect Type")
                score_min = col1.number_input("Score Min", min_value=0, max_value=1000, value=0)
                score_max = col2.number_input("Score Max", min_value=0, max_value=1000, value=850)
                annual_fee = col1.text_input("Annual Fee")
                network = col2.text_input("Network")
                mla_flag = col1.checkbox("MLA")
                mail_remail = col2.selectbox("Mail/Remail", ["MAIL", "REMAIL"])
                response_model_type = col1.text_input("Response Model Type")
                risk_score_type = col2.text_input("Risk Score Type")
                create_segment_submitted = st.form_submit_button("Create new segment")
            new_segment_fields = dict(
                segment_name=segment_name, score_type=score_type, prospect_type=prospect_type,
                score_min=score_min, score_max=score_max, annual_fee=annual_fee, network=network,
                mla_flag=mla_flag, mail_remail=mail_remail, response_model_type=response_model_type,
                risk_score_type=risk_score_type,
            )
            if create_segment_submitted:
                if not segment_name.strip():
                    st.error("Segment name is required.")
                else:
                    repository.create_segment(session, new_segment_fields)
                    st.success(f"Segment '{new_segment_fields['segment_name']}' created. Select it above to continue.")
                    st.rerun()

        change_reason = st.text_input("Reason for this allocation", key="allocate_reason")
        if st.button("Assign offers to segment", disabled=not selected_offer_ids or not segment_id):
            if not change_reason.strip():
                st.error("A change reason is required.")
            else:
                repository.ensure_campaign_segment(session, campaign_id, segment_id, change_reason)
                for offer_id in selected_offer_ids:
                    repository.allocate_offer_to_segment(session, campaign_id, offer_id, segment_id, change_reason)
                st.success(f"Assigned {len(selected_offer_ids)} offer(s) to the segment.")
                st.rerun()

    st.divider()
    ui.section_title("Segments in this campaign")
    campaign_segments = queries.campaign_segments_with_offer_counts(session, campaign_id)
    if campaign_segments.empty:
        st.caption("No segments created yet for this campaign.")
    else:
        st.dataframe(campaign_segments, use_container_width=True, hide_index=True)
        st.caption(
            "To move an offer to a different segment, set its current allocation to inactive and create a new "
            "allocation row (preserves the audit trail) -- not yet wired to a button here; do it via a short "
            "UPDATE + INSERT following the same CHANGE_REASON pattern as above if you need this in the UI."
        )
