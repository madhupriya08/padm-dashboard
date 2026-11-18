import streamlit as st

from app import queries, repository, ui

ACTIVATABLE_STATUSES = ("DISCOVERED", "REOPENED")


def render(session):
    st.header("Campaign Creation")

    campaigns = queries.all_campaigns(session)
    if campaigns.empty:
        st.info(
            "No campaigns exist yet in DM_PADM_CAMPAIGN_1. This page can open or activate an "
            "existing campaign row, but cannot yet discover brand-new ones from the ACM source "
            "-- see the note below."
        )
    else:
        st.dataframe(campaigns, use_container_width=True, hide_index=True)

        campaign_id = st.selectbox(
            "Campaign",
            options=campaigns["CAMPAIGN_ID"].tolist(),
            format_func=lambda cid: campaigns.loc[campaigns["CAMPAIGN_ID"] == cid, "CAMPAIGN_DISPLAY_NAME"].iloc[0],
        )
        row = campaigns.loc[campaigns["CAMPAIGN_ID"] == campaign_id].iloc[0]
        status = row["STATUS"]

        col1, col2 = st.columns(2)
        if col1.button("Open this campaign", type="primary"):
            st.session_state["selected_campaign_id"] = campaign_id
            st.success(f"'{row['CAMPAIGN_DISPLAY_NAME']}' is now the active campaign on every other tab.")
            st.rerun()

        if status in ACTIVATABLE_STATUSES:
            with col2.popover("Activate"):
                st.caption(f"Moves this campaign from {status} to DRAFT and snapshots its offers from the ACM source.")
                reason = st.text_input("Reason (required)", key=f"activate_reason_{campaign_id}")
                if st.button("Confirm activation", key=f"activate_confirm_{campaign_id}"):
                    if not reason.strip():
                        st.error("A reason is required.")
                    else:
                        result = repository.activate_campaign(session, campaign_id, reason)
                        st.success(result)
                        st.rerun()
        else:
            col2.caption(f"Status is {status} -- only DISCOVERED/REOPENED campaigns can be (re)activated.")

    st.divider()
    ui.section_title("Discover new campaigns from the ACM source")
    st.caption(
        "Syncs VW_PADM_ACM_CAMPAIGN_CANDIDATE into DM_PADM_CAMPAIGN_1: any (Reporting Month, "
        "Campaign Type) combo not yet present is inserted as DISCOVERED; existing rows whose source "
        "mail-date range has moved get SOURCE_CHANGE_PENDING_FLAG set so Draft knows to refresh."
    )
    if st.button("Discover new campaigns"):
        repository.discover_campaigns(session)
        st.success("Discovery sync complete.")
        st.rerun()
