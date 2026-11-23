"""Tab 2 -- Signature Page (spec 3): ACM-only, read-only starting shell.

CPP is edited on Campaign Assumptions (campaign-level) and Segment Viewer (segment-level
override) -- not here. See DM_PADM_ASSUMPTION_DEFINITION's CPP row (ASSUMPTION_LEVEL =
'CAMPAIGN_SEGMENT', ENTERED_ON = 'BOTH')."""

import streamlit as st

from padm import repository, ui

SCOPE = "signature_page"


def render(session):
    st.header("Signature Page")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    st.caption(f"{campaign['name']} · data from ACM only (CSTONE_BIZ.REFERENCE) · one row per offer, as snapshotted. "
               "Calculated fields stay *pending* until assumptions and selections exist; they fill in on Signature Page 2.")

    rows = repository.signature_live(session, campaign["id"])
    if rows.empty:
        prior = repository.previous_campaign(session, campaign["id"])
        if prior.empty:
            st.info("No ACM offers are snapshotted for this campaign and no previous campaign exists.")
        else:
            st.info(f"No offers on this campaign yet -- showing the previous campaign's ACM values "
                   f"({prior.iloc[0]['CAMPAIGN_DISPLAY_NAME']}).")
            rows = repository.signature_live(session, prior.iloc[0]["CAMPAIGN_ID"])

    if not rows.empty:
        pre_sig = repository.pre_signature_detail(session, campaign["id"])
        if not pre_sig.empty and "CAMPAIGN_OFFER_ID" in rows.columns and "QUANTITY" in rows.columns:
            pre_sig_units = pre_sig.set_index("CAMPAIGN_OFFER_ID")["QUANTITY_UNITS"].map(ui.parse_volume)
            rows = rows.copy()
            estimate = rows["CAMPAIGN_OFFER_ID"].map(pre_sig_units)
            rows["QUANTITY"] = rows["QUANTITY"].where(rows["QUANTITY"].notna(), estimate)
        ui.render_signature_page(rows, key=f"sp_table_{campaign['id']}", mask_calculated=True)
        with st.expander("Hidden fields (stored, not part of the sign-off sheet)"):
            hidden = ["OFFER_RESERVATION_CODE", "CAMPAIGN_YEAR", "CAMPAIGN_MONTH", "CAMPAIGN_MONTH_SEQUENCE",
                      "CAMPAIGN_TYPE", "MAIL_DATE", "ACM_SEGMENT", "POPULATION_DESCRIPTION", "TEST_PAIRINGS",
                      *[f"TIMES_MAILED_{i}_PERCENTAGE" for i in range(1, 9)], "TIMES_MAILED_9_PLUS_PERCENTAGE"]
            st.dataframe(rows[[c for c in hidden if c in rows.columns]], hide_index=True)
