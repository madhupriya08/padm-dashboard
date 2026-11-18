import streamlit as st

from app import queries, repository, ui
from app.pages._shared import require_campaign


def render(session):
    campaign_id = require_campaign()

    campaign = queries.campaign_header(session, campaign_id)
    if campaign.empty:
        st.error("Campaign not found.")
        return
    status = campaign.iloc[0]["STATUS"]
    ui.campaign_banner(
        campaign.iloc[0]["CAMPAIGN_DISPLAY_NAME"],
        status,
        subtitle="Signature Page 2 -- calculation, snapshot, and workflow sign-off",
    )
    ui.workflow_stepper(status)

    ui.section_title("Workflow Actions")
    col1, col2, col3 = st.columns(3)

    if col1.button("Run calculation"):
        run_id, cell_count = repository.run_calculation(session, campaign_id)
        st.success(f"Calculation run complete -- {cell_count} cells calculated.")
        st.session_state["latest_calculation_run_id"] = run_id
        st.rerun()

    latest_run = queries.latest_completed_calculation_run(session, campaign_id)
    run_id = st.session_state.get("latest_calculation_run_id") or (latest_run.iloc[0]["CALCULATION_RUN_ID"] if not latest_run.empty else None)

    if col2.button("Generate Signature Page 2 snapshot", disabled=run_id is None):
        result = repository.generate_signature_page_2(session, campaign_id, run_id)
        st.success(result)
        st.rerun()

    if col3.button("Submit for review", disabled=status != "DRAFT"):
        result = repository.transition_campaign(session, campaign_id, "READY_FOR_REVIEW", "Submitted via Signature Page 2")
        st.success(result)
        st.rerun()

    col4, col5 = st.columns(2)
    if col4.button("Approve / Complete", disabled=status != "READY_FOR_REVIEW"):
        result = repository.transition_campaign(session, campaign_id, "COMPLETED", "Approved via Signature Page 2")
        st.success(result)
        st.rerun()
    if col5.button("Reopen", disabled=status != "COMPLETED"):
        result = repository.transition_campaign(session, campaign_id, "REOPENED", "Reopened via Signature Page 2")
        st.success(result)
        st.rerun()

    st.divider()

    if status == "COMPLETED":
        versions = queries.signature_page_2_snapshot_versions(session, campaign_id)
        if versions.empty:
            st.info("No snapshot generated yet for this completed campaign.")
            return
        version = st.selectbox("Signature Page 2 version", options=versions["SIGNATURE_VERSION_NUMBER"].tolist())
        ui.section_title(f"Immutable Snapshot -- v{version}")
        ui.chips("Locked -- generated at approval time")
        st.dataframe(queries.signature_page_2_snapshot_rows(session, campaign_id, version), use_container_width=True, hide_index=True)
    else:
        ui.section_title("Live Preview")
        ui.chips("Recalculates as assumptions / allocations / selections change, until submission")
        st.dataframe(queries.signature_live_grid(session, campaign_id), use_container_width=True, hide_index=True)
