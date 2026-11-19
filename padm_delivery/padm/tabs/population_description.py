"""Tab 5 -- Population Description (spec 6): pick one or more segments, give them a shared
population-description label, and set each segment's own offers. An offer can belong to any
number of segments -- many-to-many is intentional (confirmed with the user 2026-11-19): a shared
offer's full Quantity/Boards/$ counts independently in each segment it's allocated to, so the
Grand Total below can be larger than the sum of distinct offers mailed.

Redesigned from the earlier Annual-Fee/Score-Band grouped layout (called "overwhelming") to a
segment-first flow: pick which segments this population description covers (one or several --
"a set of segments", per the user), then edit each one's own offers below. The label is free
text -- no dependency on DM_PADM_POPULATION_GROUP_RULE (confirmed unnecessary; the real
Signature Page export's "Sub-Total ..." rows are themselves just free text saved per allocation).
A suggested default is prefilled per the first selected segment (Sub-Total <source> <band>, or
Sub-Total MLA <band>, matching the two patterns seen in that export) -- a starting point to edit,
not an exact match, since no governed table exists for "Core"/"Expansion"-style wording."""

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


def _offer_label(offers, allocations):
    lookup = offers.set_index("CAMPAIGN_OFFER_ID")
    counts = allocations["CAMPAIGN_OFFER_ID"].value_counts().to_dict()

    def label(oid):
        if oid not in lookup.index:
            return str(oid)
        base = str(lookup.loc[oid, "OFFER_RESERVATION_CODE"])
        n = counts.get(oid, 0)
        return f"{base} (on {n} segment{'s' if n != 1 else ''})" if n else base
    return label


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
    allocations = repository.offer_segment_allocations(session, campaign_id)
    live = repository.signature_live(session, campaign_id)
    by_id = segments.set_index("SEGMENT_ID")

    segment_ids = st.multiselect(
        "Segment(s) -- this description applies to all selected", segments["SEGMENT_ID"].tolist(),
        format_func=lambda s: by_id.loc[s, "SEGMENT_NAME"], key=f"pd_segments_{campaign_id}",
    )
    if not segment_ids:
        st.caption("Pick one or more segments above to edit their offers and population description.")
    else:
        first = by_id.loc[segment_ids[0]]
        existing_labels = {allocations.loc[allocations["SEGMENT_ID"] == sid, "POPULATION_DESCRIPTION"].dropna().iloc[0]
                            for sid in segment_ids
                            if (allocations["SEGMENT_ID"] == sid).any()
                            and allocations.loc[allocations["SEGMENT_ID"] == sid, "POPULATION_DESCRIPTION"].notna().any()}
        default_label = next(iter(existing_labels)) if len(existing_labels) == 1 else _suggested_label(first)

        label = st.text_input(
            "Population description (sign-off document)", value=default_label,
            help='Free text -- e.g. "Sub-Total Experian Core 550-600". Applies to every segment selected above. '
                 "Suggested default is a starting point (source + band, or MLA + band), not an exact match.",
            disabled=locked, key=f"pd_label_{campaign_id}_{'_'.join(sorted(segment_ids))}",
        )

        segment_offers = {}
        for sid in segment_ids:
            seg = by_id.loc[sid]
            current = allocations.loc[allocations["SEGMENT_ID"] == sid, "CAMPAIGN_OFFER_ID"].tolist()
            with st.container(border=True):
                st.markdown(f"**{seg['SEGMENT_NAME']}**")
                chosen = st.multiselect(
                    "Offers", offers["CAMPAIGN_OFFER_ID"].tolist(), default=current,
                    format_func=_offer_label(offers, allocations), disabled=locked,
                    key=f"pd_offers_{campaign_id}_{sid}",
                )
                segment_offers[sid] = chosen
                rows = live[live["SEGMENT_ID"] == sid]
                st.caption(_metrics_line(_sums(rows)) if not rows.empty else "No calculated figures yet for this segment.")

        with st.container(horizontal=True, vertical_alignment="bottom"):
            reason = ui.reason_input(f"pd_reason_{campaign_id}", disabled=locked)
            if st.button("Save", type="primary", icon=":material/save:", disabled=locked, key=f"pd_save_{campaign_id}"):
                if ui.require_reason(reason):
                    labels = {sid: label for sid in segment_ids}
                    ui.run_action(SCOPE, lambda: repository.save_population_allocation(
                        session, campaign_id, segment_offers, labels, reason.strip()))
            if st.button("Reset to Previous Allocation", icon=":material/history:", disabled=locked,
                          key=f"pd_reset_btn_{campaign_id}"):
                prior = repository.previous_allocation(session, campaign_id)
                missing = [sid for sid in segment_ids if sid not in prior]
                if missing:
                    st.warning(f"No previous allocation for {len(missing)} of the selected segment(s) -- "
                               "unaffected segments were left as-is above.")
                for sid in segment_ids:
                    if sid in prior:
                        st.session_state[f"pd_offers_{campaign_id}_{sid}"] = prior[sid]
                st.rerun()

    st.divider()
    seg_rows = live[live["SEGMENT_ID"].notna()]
    st.markdown(f"### Grand Total — {_metrics_line(_sums(seg_rows))}")
    st.caption("An offer shared across segments counts in each of them, so this can exceed the total distinct offers mailed.")
    unassigned = offers[~offers["CAMPAIGN_OFFER_ID"].isin(allocations["CAMPAIGN_OFFER_ID"])]
    if not unassigned.empty:
        st.caption(f"{len(unassigned)} offer(s) across the campaign are not assigned to any segment.")

    with st.expander("Allocation change history"):
        history = repository.change_history(session, campaign_id, ["OFFER_SEGMENT_ALLOCATION"])
        st.dataframe(history, hide_index=True) if not history.empty else st.caption("No allocation changes yet.")
