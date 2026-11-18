"""Tab 2 -- Signature Page (spec 3): ACM-only, read-only starting shell + CPP manual insert."""

import streamlit as st

from padm import repository, ui, validation

SCOPE = "signature_page"


def _cpp_section(session, campaign):
    definitions = repository.assumption_definitions(session)
    cpp_def = definitions[definitions["ASSUMPTION_CODE"] == "CPP"]
    if cpp_def.empty:
        st.caption("CPP is not defined in DM_PADM_ASSUMPTION_DEFINITION.")
        return
    cpp_def = cpp_def.iloc[0]
    current = repository.campaign_assumption_current(session, campaign["id"])
    row = current.iloc[0] if not current.empty else None
    version = int(row["VERSION_NUMBER"]) if row is not None else 0

    with st.container(border=True):
        st.markdown("**CPP (per campaign date) -- manual override**")
        st.caption("Blank uses the ACM COST_PER_PIECE per offer. Saving writes a new campaign-assumption version. "
                   "4 decimal places, ≥ 0.")
        with st.container(horizontal=True, vertical_alignment="bottom"):
            cpp = st.number_input(
                "CPP", min_value=0.0, value=ui.num(row["CPP"]) if row is not None else None,
                step=validation.input_step(cpp_def), format=validation.input_format(cpp_def),
                placeholder="ACM value", disabled=campaign["locked"], key=f"sp_cpp_{campaign['id']}_{version}",
            )
            reason = ui.reason_input(f"sp_cpp_reason_{campaign['id']}", disabled=campaign["locked"])
            if st.button("Save CPP", type="primary", icon=":material/save:", disabled=campaign["locked"],
                          key=f"sp_cpp_save_{campaign['id']}"):
                error = validation.validate(cpp_def, cpp)
                if error:
                    st.error(error)
                elif ui.require_reason(reason):
                    values = {c: (ui.num(row[c]) if row is not None else None) for c in ("UNIT_COST", "NBR", "UNWIND_RATE")}
                    values["CPP"] = cpp
                    ui.run_action(SCOPE, lambda: repository.save_campaign_assumption(
                        session, campaign["id"], values, version, reason.strip()))


def render(session):
    st.header("Signature Page")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    st.caption(f"{campaign['name']} · data from ACM only (CSTONE_BIZ.REFERENCE) · one row per offer reservation code. "
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
        c1, c2, c3 = st.columns(3)
        c1.metric("Offers", f"{len(rows):,}", border=True)
        c2.metric("Quantity", f"{rows['QUANTITY'].fillna(0).sum():,.0f}", border=True)
        c3.metric("Segmented offers", f"{rows['SEGMENT_ID'].notna().sum():,}", border=True)
        ui.render_signature_page(rows, key=f"sp_table_{campaign['id']}", mask_calculated=True)
        with st.expander("Hidden fields (stored, not part of the sign-off sheet)"):
            hidden = ["OFFER_RESERVATION_CODE", "CAMPAIGN_YEAR", "CAMPAIGN_MONTH", "CAMPAIGN_MONTH_SEQUENCE",
                      "CAMPAIGN_TYPE", "MAIL_DATE", "ACM_SEGMENT", "POPULATION_DESCRIPTION", "TEST_PAIRINGS",
                      *[f"TIMES_MAILED_{i}_PERCENTAGE" for i in range(1, 9)], "TIMES_MAILED_9_PLUS_PERCENTAGE"]
            st.dataframe(rows[[c for c in hidden if c in rows.columns]], hide_index=True)

    st.divider()
    _cpp_section(session, campaign)
