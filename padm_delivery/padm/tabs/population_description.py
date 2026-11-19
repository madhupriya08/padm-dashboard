"""Tab 5 -- Population Description (spec 6): pick a segment, edit its offers and its own
population-description label, save. An offer can belong to one segment only.

Redesigned (2026-11-19, user's explicit call) from the earlier Annual-Fee/Score-Band grouped
layout (called "overwhelming") to a single segment-first flow, matching Create Segment / Segment
Viewer / Campaign Assumptions' own pattern. The label is free text -- no dependency on
DM_PADM_POPULATION_GROUP_RULE (confirmed unnecessary; see the real Signature Page export's
"Sub-Total ..." rows, which are themselves just free text saved per allocation). A suggested
default is prefilled (Sub-Total <source> <band>, or Sub-Total MLA <band> for MLA segments,
matching the two patterns seen in that real export) -- it is a starting point to edit, not an
exact match, since no governed table exists anywhere for the "Core"/"Expansion"-style wording
seen in some of those real rows."""

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


def _is_mla(segment):
    return str(segment.get("MLA_FLAG") or "").strip().upper() in ("Y", "YES", "TRUE", "MLA")


def _suggested_label(segment):
    band = f"{int(segment['SCORE_MIN'])}-{int(segment['SCORE_MAX'])}"
    middle = "MLA" if _is_mla(segment) else str(segment.get("SOURCE_NAME") or "").upper()
    return f"Sub-Total {middle} {band}".strip()


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
    by_id = segments.set_index("SEGMENT_ID")

    segment_id = st.selectbox("Segment", segments["SEGMENT_ID"].tolist(),
                               format_func=lambda s: by_id.loc[s, "SEGMENT_NAME"], key=f"pd_segment_{campaign_id}")
    segment = by_id.loc[segment_id]

    current = offers[offers["SEGMENT_ID"] == segment_id]
    current_offer_ids = current["CAMPAIGN_OFFER_ID"].tolist()
    current_label = current["POPULATION_DESCRIPTION"].dropna().iloc[0] if current["POPULATION_DESCRIPTION"].notna().any() else None

    # "Reset to Previous Allocation" pre-loads this segment's widgets with the previous campaign's offers.
    reset_key = f"pd_reset_{campaign_id}_{segment_id}"
    previous = st.session_state.get(reset_key)
    reset_nonce = st.session_state.get(f"{reset_key}_nonce", 0)
    default_offers = previous if previous is not None else current_offer_ids

    with st.container(border=True):
        st.markdown(f"**{segment['SEGMENT_NAME']}**")
        options = offers[offers["SEGMENT_ID"].isna() | (offers["SEGMENT_ID"] == segment_id)]["CAMPAIGN_OFFER_ID"].tolist()
        chosen = st.multiselect(
            "Offers", options, default=[o for o in default_offers if o in options],
            format_func=lambda o: label_of.get(o, str(o)), disabled=locked,
            key=f"pd_offers_{campaign_id}_{segment_id}_{reset_nonce}",
        )
        label = st.text_input(
            "Population description (sign-off document)",
            value=current_label or _suggested_label(segment),
            help='Free text -- e.g. "Sub-Total Experian Core 550-600". Suggested default above is a '
                 "starting point (source + band, or MLA + band), not an exact match -- edit as needed.",
            disabled=locked, key=f"pd_label_{campaign_id}_{segment_id}_{reset_nonce}",
        )
        rows = live[live["SEGMENT_ID"] == segment_id]
        st.caption(_metrics_line(_sums(rows)) if not rows.empty else "No calculated figures yet for this segment.")

        with st.container(horizontal=True, vertical_alignment="bottom"):
            reason = ui.reason_input(f"pd_reason_{campaign_id}_{segment_id}", disabled=locked)
            if st.button("Save", type="primary", icon=":material/save:", disabled=locked, key=f"pd_save_{campaign_id}_{segment_id}"):
                if ui.require_reason(reason):
                    ui.run_action(
                        SCOPE,
                        lambda: repository.save_population_allocation(
                            session, campaign_id, {segment_id: chosen}, {segment_id: label}, reason.strip()),
                        on_success=lambda _: st.session_state.pop(reset_key, None),
                    )
            if st.button("Reset to Previous Allocation", icon=":material/history:", disabled=locked,
                          key=f"pd_reset_btn_{campaign_id}_{segment_id}"):
                prior = repository.previous_allocation(session, campaign_id).get(segment_id)
                if not prior:
                    st.warning("No previous campaign allocation for this segment.")
                else:
                    st.session_state[reset_key] = prior
                    st.session_state[f"{reset_key}_nonce"] = reset_nonce + 1
                    st.rerun()
        if previous is not None:
            st.info("Offers above show the previous campaign's allocation for this segment. Save to keep it.")

    seg_rows = live[live["SEGMENT_ID"].notna()]
    st.markdown(f"### Grand Total — {_metrics_line(_sums(seg_rows))}")
    unassigned = offers[offers["SEGMENT_ID"].isna()]
    if not unassigned.empty:
        st.caption(f"{len(unassigned)} offer(s) across the campaign are not assigned to any segment.")

    with st.expander("Allocation change history"):
        history = repository.change_history(session, campaign_id, ["OFFER_SEGMENT_ALLOCATION"])
        st.dataframe(history, hide_index=True) if not history.empty else st.caption("No allocation changes yet.")
