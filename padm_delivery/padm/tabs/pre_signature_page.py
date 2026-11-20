"""Pre Signature Page: live signature data (same source as Signature Page) plus 3 tracking
fields carried forward from the previous campaign -- Total Available Volume, Quantity,
Owner/Approver. Mirrors the legacy Matrix Creation Tool's merge of those 3 columns from last
month's matrix, but joins on OFFER_RESERVATION_CODE (a stable key we already have) instead of
matching on free-text description, and persists to a real table instead of an Excel file."""

import pandas as pd
import streamlit as st

from padm import repository, ui

SCOPE = "pre_signature_page"
NEW_COLUMNS = ["TOTAL_AVAILABLE_VOLUME", "QUANTITY", "OWNER_APPROVER"]
NEW_LABELS = {
    "TOTAL_AVAILABLE_VOLUME": "Total Available Volume",
    "QUANTITY": "Quantity",
    "OWNER_APPROVER": "Owner/Approver",
}


def render(session):
    st.header("Pre Signature Page")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    st.caption(f"{campaign['name']} · same data as Signature Page, plus Total Available Volume / "
               "Quantity / Owner-Approver -- carried forward from the previous campaign for a "
               "matching offer (by reservation code) until saved here.")

    rows = repository.signature_live(session, campaign["id"])
    if rows.empty:
        st.info("No ACM offers are snapshotted for this campaign yet.")
        return
    rows = rows.reset_index(drop=True)

    current = repository.pre_signature_detail(session, campaign["id"])
    current_by_offer = current.set_index("CAMPAIGN_OFFER_ID") if not current.empty else current

    prior = repository.previous_pre_signature_detail(session, campaign["id"])
    prior_by_code = prior.set_index("OFFER_RESERVATION_CODE") if not prior.empty else prior

    frame = ui.signature_frame(rows, mask_calculated=True)
    frame = frame.reset_index(drop=True)

    def value_for(i, col):
        offer_id = rows.loc[i, "CAMPAIGN_OFFER_ID"]
        code = rows.loc[i, "OFFER_RESERVATION_CODE"] if "OFFER_RESERVATION_CODE" in rows.columns else None
        if not current_by_offer.empty and offer_id in current_by_offer.index:
            return current_by_offer.loc[offer_id, col]
        if code is not None and not prior_by_code.empty and code in prior_by_code.index:
            return prior_by_code.loc[code, col]
        return None

    for col in NEW_COLUMNS:
        frame[NEW_LABELS[col]] = [value_for(i, col) for i in frame.index]

    locked = campaign["locked"]
    reason = ui.reason_input(f"psp_reason_{campaign['id']}", disabled=locked)
    editable_cols = set(NEW_LABELS.values())
    edited = st.data_editor(
        frame, hide_index=True, use_container_width=False,
        disabled=[c for c in frame.columns if c not in editable_cols],
        key=f"psp_editor_{campaign['id']}",
    )

    if st.button("Save tracking fields", type="primary", icon=":material/save:",
                  disabled=locked, key=f"psp_save_{campaign['id']}"):
        if ui.require_reason(reason):
            payload = [
                {
                    "CAMPAIGN_OFFER_ID": rows.loc[i, "CAMPAIGN_OFFER_ID"],
                    "TOTAL_AVAILABLE_VOLUME": edited.loc[i, NEW_LABELS["TOTAL_AVAILABLE_VOLUME"]],
                    "QUANTITY": edited.loc[i, NEW_LABELS["QUANTITY"]],
                    "OWNER_APPROVER": edited.loc[i, NEW_LABELS["OWNER_APPROVER"]],
                }
                for i in edited.index
            ]
            ui.run_action(SCOPE, lambda: repository.save_pre_signature_detail(
                session, campaign["id"], payload, reason.strip()))
