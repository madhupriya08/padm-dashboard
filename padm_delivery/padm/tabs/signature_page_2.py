"""Tab 7 -- Signature Page 2: calculated values + population description; Run Calculation ->
Generate (immutable snapshot) -> Approve / Reject; exports."""

import streamlit as st

from padm import exports, repository, ui

SCOPE = "signature_page_2"
STEPS = ["NEW", "DRAFT", "IN_PROGRESS", "PENDING_APPROVAL", "APPROVED"]


def _stepper(status):
    current = STEPS.index(status) if status in STEPS else -1
    for i, (col, step) in enumerate(zip(st.columns(len(STEPS)), STEPS)):
        label = f"{i + 1}. {step.replace('_', ' ').title()}"
        if i < current:
            col.markdown(f":green[:material/check_circle: {label}]")
        elif i == current:
            col.markdown(f":blue[:material/radio_button_checked: **{label}**]")
        else:
            col.markdown(f":gray[:material/radio_button_unchecked: {label}]")


def _actions(session, campaign):
    cid, status, locked = campaign["id"], campaign["status"], campaign["locked"]
    latest = repository.latest_calculation_run(session, cid)
    run = latest.iloc[0] if not latest.empty else None
    if run is not None:
        st.caption(f"Latest calculation run: **{run['CALCULATION_STATUS']}** at {run['CALCULATION_COMPLETED_TS']} "
                   f"by {run['CALCULATED_BY']} (working version v{run['CAMPAIGN_WORKING_VERSION_NUMBER']}).")

    with st.container(border=True):
        st.markdown("**1. Generate Signature Page 2**")
        st.caption("Runs the calculation, then creates an immutable snapshot of the result; status -> PENDING_APPROVAL.")
        if st.button("Generate Signature Page 2", type="primary", icon=":material/description:",
                      disabled=locked or status not in ("DRAFT", "IN_PROGRESS", "PENDING_APPROVAL"),
                      key="sp2_generate"):
            def generate():
                run_id, _ = repository.run_calculation(session, cid)
                return repository.generate_signature_page_2(session, cid, run_id)
            ui.run_action(SCOPE, generate)

    with st.container(border=True):
        st.markdown("**2. Approve or Reject**")
        st.caption("Approve copies the final state into the audit/snapshot tables and makes the whole campaign "
                   "read-only. Reject returns the campaign to DRAFT; prior versions are kept.")
        pending = status == "PENDING_APPROVAL"
        reason = ui.reason_input("sp2_decision_reason", disabled=not pending)
        comment = st.text_input("Comment (optional)", key="sp2_decision_comment", disabled=not pending)
        b1, b2 = st.columns(2)
        if b1.button("Approve", type="primary", icon=":material/verified:", disabled=not pending, key="sp2_approve"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.transition_status(session, cid, "APPROVED", reason.strip(), comment.strip() or None))
        if b2.button("Reject", icon=":material/undo:", disabled=not pending, key="sp2_reject"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.transition_status(session, cid, "REJECTED", reason.strip(), comment.strip() or None))


def _export_buttons(frame, campaign, label):
    title = f"PADM Sign-off -- {campaign['name']}"
    subtitle = f"{label} · Campaign type {ui.TYPE_LABELS.get(campaign['type'], campaign['type'])} · Status {campaign['status']}"
    base = f"padm_signature_page_2_{campaign['reporting_month']}_{campaign['type']}_{label.replace(' ', '_')}"
    c1, c2 = st.columns(2)
    try:
        c1.download_button("Export to Excel", exports.to_excel(frame, title, subtitle), f"{base}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            icon=":material/table_view:", key=f"sp2_xlsx_{label}")
    except ImportError:
        c1.caption("Excel export needs the openpyxl package.")
    pdf = exports.to_pdf(frame, title, subtitle)
    if pdf is not None:
        c2.download_button("Export to PDF", pdf, f"{base}.pdf", mime="application/pdf",
                            icon=":material/picture_as_pdf:", key=f"sp2_pdf_{label}")
    else:
        c2.download_button("Export to PDF (print-ready HTML)", exports.to_html(frame, title, subtitle), f"{base}.html",
                            mime="text/html", icon=":material/picture_as_pdf:", key=f"sp2_pdf_{label}",
                            help="reportlab is not installed: open the file and print to PDF.")


def render(session):
    st.header("Signature Page 2")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    _stepper(campaign["status"])
    _actions(session, campaign)
    st.divider()

    versions = repository.snapshot_versions(session, campaign["id"])
    options = ["Live preview"] + [f"Snapshot v{int(v)}" for v in versions["SIGNATURE_VERSION_NUMBER"]]
    choice = st.radio("Show", options, index=1 if campaign["status"] in ("PENDING_APPROVAL", "APPROVED") and len(options) > 1 else 0,
                       horizontal=True, key="sp2_view")
    if choice == "Live preview":
        rows = repository.signature_live(session, campaign["id"])
        st.caption("Live preview from VW_PADM_SIGNATURE_PAGE_LIVE -- Signature Page 1 columns with calculated values "
                   "and population description groups (Tab 5).")
    else:
        version = int(choice.split("v")[-1])
        meta = versions[versions["SIGNATURE_VERSION_NUMBER"] == version].iloc[0]
        rows = repository.snapshot_rows(session, campaign["id"], version)
        st.caption(f"Immutable snapshot v{version} · {meta['SNAPSHOT_STATUS']} · created by {meta['CREATED_BY']} "
                   f"at {meta['CREATED_TS']} · {meta['ROW_COUNT']} rows (read-only).")
    if rows.empty:
        st.info("Nothing to show yet.")
    else:
        ui.render_signature_page(rows, key=f"sp2_table_{choice}", group_by_population=True)
        _export_buttons(ui.signature_frame(rows, group_by_population=True), campaign, choice)

    st.divider()
    with st.expander("Actuals (after approval)"):
        st.caption("Placeholder -- once approved, actuals are created and worked on. Out of scope for this build.")
    with st.expander("Finance Extract"):
        st.caption("Placeholder -- Finance Extract requirements are TBD.")
