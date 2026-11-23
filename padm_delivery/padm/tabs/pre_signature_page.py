"""Pre Signature Page: live ACM-sourced offer data in the Matrix Creation Tool's column order
and sort, color-coded the same way, plus 4 tracking fields -- Total Available Volume, Quantity %,
Quantity (units), Owner/Approver. Carries forward from the previous campaign for a matching offer
(by reservation code) until saved here, and persists to a real table instead of an Excel file."""

import pandas as pd
import streamlit as st

from padm import repository, ui

SCOPE = "pre_signature_page"
NEW_COLUMNS = ["TOTAL_AVAILABLE_VOLUME", "QUANTITY_PERCENTAGE", "QUANTITY_UNITS", "OWNER_APPROVER"]
NEW_LABELS = {
    "TOTAL_AVAILABLE_VOLUME": "Total Available Volume",
    "QUANTITY_PERCENTAGE": "Quantity %",
    "QUANTITY_UNITS": "Quantity (Units)",
    "OWNER_APPROVER": "Owner/Approver",
}


def render(session):
    st.header("Pre Signature Page")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    st.caption(f"{campaign['name']} · ACM offer data in the Matrix Creation Tool's column order, plus "
               "Total Available Volume / Quantity % / Quantity (Units) / Owner-Approver -- carried "
               "forward from the previous campaign for a matching offer (by reservation code) until "
               "saved here.")

    rows = repository.signature_live(session, campaign["id"])
    if rows.empty:
        st.info("No ACM offers are snapshotted for this campaign yet.")
        return
    rows = rows.copy()
    rows["_SORT"] = [ui.segment_sort_rank(s, d) for s, d in
                      zip(rows.get("ACM_SEGMENT", ""), rows.get("SEGMENT_DESCRIPTION", ""))]
    sort_cols = [c for c in ["_SORT", "CREDIT_BUREAU_SCORE", "TEST_TYPE"] if c in rows.columns]
    rows = rows.sort_values(sort_cols).drop(columns="_SORT").reset_index(drop=True)

    current = repository.pre_signature_detail(session, campaign["id"])
    current_by_offer = current.set_index("CAMPAIGN_OFFER_ID") if not current.empty else current

    prior = repository.previous_pre_signature_detail(session, campaign["id"])
    prior_by_code = prior.set_index("OFFER_RESERVATION_CODE") if not prior.empty else prior

    frame = pd.DataFrame(index=rows.index)
    for source, label in ui.MATRIX_COLUMNS:
        frame[label] = rows[source] if source in rows.columns else None

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

    def color_rows(row):
        color = ui.segment_color(rows.loc[row.name, "ACM_SEGMENT"] if "ACM_SEGMENT" in rows.columns else None,
                                  rows.loc[row.name, "SEGMENT_DESCRIPTION"] if "SEGMENT_DESCRIPTION" in rows.columns else None)
        return [f"background-color: {color}" if color else ""] * len(row)

    locked = campaign["locked"]
    reason = ui.reason_input(f"psp_reason_{campaign['id']}", disabled=locked)
    editable_cols = set(NEW_LABELS.values())
    edited = st.data_editor(
        frame.style.apply(color_rows, axis=1), hide_index=True, use_container_width=False,
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
                    "QUANTITY_PERCENTAGE": edited.loc[i, NEW_LABELS["QUANTITY_PERCENTAGE"]],
                    "QUANTITY_UNITS": edited.loc[i, NEW_LABELS["QUANTITY_UNITS"]],
                    "OWNER_APPROVER": edited.loc[i, NEW_LABELS["OWNER_APPROVER"]],
                }
                for i in edited.index
            ]
            ui.run_action(SCOPE, lambda: repository.save_pre_signature_detail(
                session, campaign["id"], payload, reason.strip()))
