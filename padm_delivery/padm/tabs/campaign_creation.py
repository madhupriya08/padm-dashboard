"""Tab 1 -- Campaign Creation: discover ACM offers, create/activate, select, status flow. Main and
Remail for one chosen month are created together in a single action -- no separate Type selector."""

import datetime as dt

import streamlit as st

from padm import repository, ui

SCOPE = "campaign_creation"
TYPE_LABELS = {"MAIN": "Main", "REMAIL": "Remail"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def _picker():
    today = dt.date.today()
    c1, c2 = st.columns(2)
    month = c1.selectbox("Campaign Month", range(1, 13), index=today.month - 1,
                          format_func=lambda m: MONTHS[m - 1], key="cc_month")
    year = c2.selectbox("Campaign Year", range(today.year, today.year + 4), key="cc_year")
    return dt.date(year, month, 1)


def _discover_section(session):
    st.subheader("Search for a campaign")
    st.caption("Mandatory ACM filters: program code not starting with W, reservation code ≤ 6 characters, "
               "channel = Mail, offer status = Active. Month/year come from CAMPAIGN_GROUP_MAIL_DATE. "
               "Main and Remail for the chosen month are searched and created together.")
    reporting_month = _picker()

    if st.button("Search", icon=":material/search:", key="cc_discover"):
        st.session_state["cc_discovered"] = reporting_month

    discovered = st.session_state.get("cc_discovered")
    if discovered != reporting_month:
        return

    existing, candidates, offers_by_type = {}, {}, {}
    for campaign_type in ("MAIN", "REMAIL"):
        existing_id, existing_status = repository.existing_campaign_for_month(session, reporting_month, campaign_type)
        if existing_id is not None:
            existing[campaign_type] = existing_status
            continue
        candidates[campaign_type] = repository.campaign_candidate(session, reporting_month, campaign_type)
        offers_by_type[campaign_type] = repository.candidate_offers(session, reporting_month, campaign_type)

    for campaign_type, status in existing.items():
        st.info(f"{TYPE_LABELS[campaign_type]} campaign for this month already exists with status "
                f"{status}. Select it below to continue.")

    to_create = [t for t in ("MAIN", "REMAIL") if t not in existing]
    if not to_create:
        return

    for campaign_type in to_create:
        candidate, offers = candidates[campaign_type], offers_by_type[campaign_type]
        st.markdown(f"**{TYPE_LABELS[campaign_type]}**")
        if candidate.empty or offers.empty:
            st.caption("No ACM data has landed for this month/type yet -- a placeholder campaign will "
                       "be created instead, to Activate later once ACM data exists.")
        else:
            row = candidate.iloc[0]
            c1, c2 = st.columns(2)
            c1.metric("Candidate", row["CAMPAIGN_DISPLAY_NAME"], border=True)
            c2.metric("ACM offers", f"{len(offers):,}", border=True)
            st.dataframe(offers, hide_index=True, height=250, key=f"cc_offers_{campaign_type}")

    def _create():
        created = []
        for campaign_type in to_create:
            candidate, offers = candidates[campaign_type], offers_by_type[campaign_type]
            if candidate.empty or offers.empty:
                campaign_id = repository.create_manual_campaign(session, reporting_month, campaign_type)
            else:
                campaign_id = repository.discover_campaign(session, reporting_month, campaign_type)
            if campaign_id is not None:
                created.append((campaign_type, campaign_id))
        return created

    st.subheader("Create campaign(s)")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        reason = ui.reason_input("cc_create_reason")
        if st.button("Create Campaign(s)", type="primary", icon=":material/add_box:", key="cc_create"):
            if ui.require_reason(reason):
                ui.run_action(
                    SCOPE, _create,
                    lambda result: ("Created " + " and ".join(TYPE_LABELS[t] for t, _ in result) + ".")
                        if result else "Nothing to create -- both already exist for this month.",
                    on_success=lambda result: st.session_state.update({ui.CAMPAIGN_KEY: result[0][1]}) if result else None,
                )


def _campaign_list(session):
    st.subheader("Existing campaigns")
    campaigns = repository.campaigns(session)
    if campaigns.empty:
        st.caption("No campaigns yet.")
        return
    shown = campaigns.drop(columns=["CAMPAIGN_ID", "SOURCE_MIN_MAIL_DATE", "SOURCE_MAX_MAIL_DATE"]) \
        .rename(columns={"CURRENT_WORKING_VERSION_NUMBER": "VERSION"})
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
                    ui.run_action(SCOPE, lambda: repository.activate_campaign(
                        session, campaign["id"], reason.strip()),
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
