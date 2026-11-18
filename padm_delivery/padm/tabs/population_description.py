"""Tab 5 -- Population Description (spec 6): group segments by AF -> score band, assign offers
per segment (multi-select), editable group labels, sub-totals and grand total."""

import pandas as pd
import streamlit as st

from padm import repository, ui

SCOPE = "population_description"
NUMERIC = [("QUANTITY", "Qty", "{:,.0f}"), ("BOARDS", "Boards", "{:,.1f}"), ("MARKETING_EXPENSE", "Marketing", "${:,.2f}"),
           ("POST_UNWIND_BOARDS", "Post-Unwind Boards", "{:,.1f}"),
           ("MARKETING_PLUS_BOOKING_COSTS", "Marketing + Booking", "${:,.2f}")]


def _sums(rows):
    return {col: pd.to_numeric(rows[col], errors="coerce").fillna(0).sum() for col, _, _ in NUMERIC}


def _metrics_line(values, prefix=""):
    return prefix + " · ".join(f"{label} {fmt.format(values[col])}" for col, label, fmt in NUMERIC)


def render(session):
    st.header("Population Description")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    campaign_id, locked = campaign["id"], campaign["locked"]

    segments = repository.campaign_segments(session, campaign_id)
    if segments.empty:
        st.info("No segments on this campaign yet (Create Segment tab).")
        return
    offers = repository.campaign_offers(session, campaign_id)
    live = repository.signature_live(session, campaign_id)
    label_of = offers.set_index("CAMPAIGN_OFFER_ID")["OFFER_RESERVATION_CODE"].to_dict()

    # "Reset to Previous Allocation" pre-loads the widgets with the previous campaign's links.
    reset_key = f"pd_reset_{campaign_id}"
    previous = st.session_state.get(reset_key)
    reset_nonce = st.session_state.get(f"{reset_key}_nonce", 0)

    # Group: Annual Fee, then score band (segment attributes; labels default from the rule table).
    seg_rows = live[live["SEGMENT_ID"].notna()]
    segments = segments.copy()
    af = seg_rows.groupby("SEGMENT_ID")["ANNUAL_FEE"].first()
    default_label = seg_rows.groupby("SEGMENT_ID")["POPULATION_DESCRIPTION"].first()
    segments["AF"] = segments["SEGMENT_ID"].map(af).fillna(segments["ANNUAL_FEE"]).fillna("–")
    segments["BAND"] = segments["SCORE_TYPE"] + " " + segments["SCORE_MIN"].astype(int).astype(str) + "-" + \
        segments["SCORE_MAX"].astype(int).astype(str)
    segments = segments.sort_values(["AF", "SCORE_MIN", "SEGMENT_NAME"])

    assignments, labels = {}, {}
    st.caption("Offers ideally stay the same across campaigns: each segment defaults to its current (or previous) "
               "offers. An offer can belong to one segment only.")
    for (af_value, band), group in segments.groupby(["AF", "BAND"], sort=False):
        with st.container(border=True):
            c1, c2 = st.columns([2, 3])
            c1.markdown(f"**GROUP: {af_value} | {band}**")
            first = group.iloc[0]["SEGMENT_ID"]
            group_label = c2.text_input(
                "Group label (sign-off document)", value=default_label.get(first) or "",
                placeholder="from DM_PADM_POPULATION_GROUP_RULE", disabled=locked,
                key=f"pd_label_{campaign_id}_{af_value}_{band}_{reset_nonce}",
            )
            group_rows = []
            for _, seg in group.iterrows():
                sid = seg["SEGMENT_ID"]
                current = offers[offers["SEGMENT_ID"] == sid]["CAMPAIGN_OFFER_ID"].tolist()
                default = previous.get(sid, []) if previous is not None else current
                options = sorted(set(offers["CAMPAIGN_OFFER_ID"]), key=lambda o: label_of.get(o, ""))
                s1, s2 = st.columns([2, 5])
                s1.markdown(f"{seg['SEGMENT_NAME']}")
                assignments[sid] = s2.multiselect(
                    "Offers", options, default=[o for o in default if o in options],
                    format_func=lambda o: label_of.get(o, str(o)), label_visibility="collapsed", disabled=locked,
                    key=f"pd_offers_{campaign_id}_{sid}_{reset_nonce}",
                )
                labels[sid] = group_label
                rows = live[live["SEGMENT_ID"] == sid]
                group_rows.append(rows)
                s2.caption(_metrics_line(_sums(rows)))
            st.markdown(f"**— Sub-total** {_metrics_line(_sums(pd.concat(group_rows)))}")

    st.markdown(f"### —— Grand Total\n{_metrics_line(_sums(seg_rows))}")
    unassigned = offers[offers["SEGMENT_ID"].isna()]
    if not unassigned.empty:
        st.caption(f"{len(unassigned)} offer(s) are not assigned to any segment.")

    chosen = [o for ids in assignments.values() for o in ids]
    duplicates = sorted({label_of.get(o, o) for o in chosen if chosen.count(o) > 1})
    if duplicates:
        st.error(f"Assigned to more than one segment: {', '.join(duplicates)}")

    with st.container(horizontal=True, vertical_alignment="bottom"):
        reason = ui.reason_input(f"pd_reason_{campaign_id}", disabled=locked)
        if st.button("Save Allocation", type="primary", icon=":material/save:", disabled=locked or bool(duplicates),
                      key=f"pd_save_{campaign_id}"):
            if ui.require_reason(reason):
                ui.run_action(
                    SCOPE,
                    lambda: repository.save_population_allocation(session, campaign_id, assignments, labels, reason.strip()),
                    on_success=lambda _: st.session_state.pop(reset_key, None),
                )
        if st.button("Reset to Previous Allocation", icon=":material/history:", disabled=locked, key=f"pd_reset_btn_{campaign_id}"):
            prior = repository.previous_allocation(session, campaign_id)
            if not prior:
                st.warning("No previous campaign allocation to reset to.")
            else:
                st.session_state[reset_key] = prior
                st.session_state[f"{reset_key}_nonce"] = reset_nonce + 1
                st.rerun()
    if previous is not None:
        st.info("Widgets show the previous campaign's allocation. Save Allocation to keep it.")

    with st.expander("Allocation change history"):
        history = repository.change_history(session, campaign_id, ["OFFER_SEGMENT_ALLOCATION"])
        st.dataframe(history, hide_index=True) if not history.empty else st.caption("No allocation changes yet.")
