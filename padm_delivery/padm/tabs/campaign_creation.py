"""Tab 1 -- Campaign Creation (spec 2): discover ACM offers, create/activate, select, status flow."""

import datetime as dt

import streamlit as st

from padm import repository, ui

SCOPE = "campaign_creation"
TYPE_OPTIONS = {"PRIMARY (MAIN)": "MAIN", "REMAIL": "REMAIL"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def _picker():
    today = dt.date.today()
    c1, c2, c3 = st.columns(3)
    month = c1.selectbox("Campaign Month", range(1, 13), index=today.month - 1,
                          format_func=lambda m: MONTHS[m - 1], key="cc_month")
    year = c2.selectbox("Campaign Year", range(today.year - 3, today.year + 2), index=3, key="cc_year")
    type_label = c3.selectbox("Campaign Type", list(TYPE_OPTIONS), key="cc_type",
                               help="Derivation logic is TBD -- selected manually and stored on the campaign.")
    return dt.date(year, month, 1), TYPE_OPTIONS[type_label]


def _discover_section(session):
    st.subheader("Discover / create a campaign")
    st.caption("Mandatory ACM filters: program code not starting with W, reservation code ≤ 6 characters, "
               "channel = Mail, offer status = Active. Month/year come from CAMPAIGN_GROUP_MAIL_DATE.")
    reporting_month, campaign_type = _picker()

    if st.button("Discover", icon=":material/search:", key="cc_discover"):
        st.session_state["cc_discovered"] = (reporting_month, campaign_type)

    discovered = st.session_state.get("cc_discovered")
    if discovered != (reporting_month, campaign_type):
        return

    candidate = repository.campaign_candidate(session, reporting_month, campaign_type)
    offers = repository.candidate_offers(session, reporting_month, campaign_type)
    if candidate.empty or offers.empty:
        st.warning("No eligible ACM offers for this month and campaign type.")
        return

    row = candidate.iloc[0]
    status = row["STATUS"] if isinstance(row["STATUS"], str) else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Candidate", row["CAMPAIGN_DISPLAY_NAME"], border=True)
    c2.metric("ACM offers", f"{len(offers):,}", border=True)
    c3.metric("Mail dates", f"{row['SOURCE_MIN_MAIL_DATE']} - {row['SOURCE_MAX_MAIL_DATE']}", border=True)
    c4.metric("PADM status", status or "not created", border=True)
    st.dataframe(offers, hide_index=True, height=300, key="cc_offers")

    if status not in (None, "NEW", "DRAFT"):
        st.info(f"This campaign already exists with status {status}. Select it below.")
        return
    with st.container(horizontal=True, vertical_alignment="bottom"):
        reason = ui.reason_input("cc_create_reason")
        if st.button("Create / Activate Campaign", type="primary", icon=":material/rocket_launch:", key="cc_create"):
            if ui.require_reason(reason):
                ui.run_action(
                    SCOPE,
                    lambda: repository.create_and_activate_campaign(session, reporting_month, campaign_type, reason.strip()),
                    lambda result: result[1],
                    on_success=lambda result: st.session_state.update({ui.CAMPAIGN_KEY: result[0]}),
                )


def _campaign_list(session):
    st.subheader("Existing campaigns")
    campaigns = repository.campaigns(session)
    if campaigns.empty:
        st.caption("No campaigns yet.")
        return
    shown = campaigns.drop(columns=["CAMPAIGN_ID"]).rename(columns={"CURRENT_WORKING_VERSION_NUMBER": "VERSION"})
    event = st.dataframe(ui.style_status_column(shown), hide_index=True, on_select="rerun",
                          selection_mode="single-row", key="cc_campaigns")
    selected = event.selection.rows if event and event.selection else []
    if selected:
        campaign_id = campaigns.iloc[selected[0]]["CAMPAIGN_ID"]
        if st.session_state.get(ui.CAMPAIGN_KEY) != campaign_id:
            st.session_state[ui.CAMPAIGN_KEY] = campaign_id
            st.rerun()
    if st.session_state.get(ui.CAMPAIGN_KEY):
        st.caption("Click a row to switch the active campaign for all tabs.")


def _status_section(session, campaign):
    st.subheader("Status workflow")
    st.caption("NEW → DRAFT → IN_PROGRESS (v1, v2, …) → PENDING_APPROVAL (Signature Page 2) → APPROVED, "
               "or REJECTED → back to DRAFT. Approve / Reject are on the Signature Page 2 tab.")
    status = campaign["status"]
    if status == "NEW":
        with st.container(horizontal=True, vertical_alignment="bottom"):
            reason = ui.reason_input("cc_activate_reason")
            if st.button("Activate (snapshot ACM)", type="primary", key="cc_activate"):
                if ui.require_reason(reason):
                    ui.run_action(SCOPE, lambda: repository.create_and_activate_campaign(
                        session, campaign["reporting_month"], campaign["type"], reason.strip()),
                        lambda result: result[1])
    elif status in ("DRAFT", "IN_PROGRESS"):
        label = "Start working version" if status == "DRAFT" else f"Save as new working version (v{campaign['working_version'] + 1})"
        with st.container(horizontal=True, vertical_alignment="bottom"):
            reason = ui.reason_input("cc_version_reason")
            comment = st.text_input("Comment (optional)", key="cc_version_comment")
            if st.button(label, type="primary", icon=":material/save:", key="cc_version"):
                if ui.require_reason(reason):
                    ui.run_action(SCOPE, lambda: repository.transition_status(
                        session, campaign["id"], "IN_PROGRESS", reason.strip(), comment.strip() or None))

    with st.expander("Workflow history (who worked on the campaign, and when)"):
        history = repository.workflow_history(session, campaign["id"])
        st.dataframe(history, hide_index=True) if not history.empty else st.caption("No workflow events yet.")
    with st.expander("Change audit (all data changes)"):
        changes = repository.change_history(session, campaign["id"])
        st.dataframe(changes, hide_index=True) if not changes.empty else st.caption("No changes recorded yet.")


def render(session):
    st.header("Campaign Creation")
    ui.show_flash(SCOPE)
    _discover_section(session)
    st.divider()
    _campaign_list(session)
    campaign = ui.campaign_context(session)
    if campaign is not None:
        st.divider()
        ui.header_bar(campaign)
        _status_section(session, campaign)
