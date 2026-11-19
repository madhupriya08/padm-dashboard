"""Tab 3 -- Create Segment (spec 4): governed, reusable segments + offer allocation."""

import streamlit as st

from padm import repository, ui, validation
from padm.formulas import TIMES_MAILED_BUCKETS

SCOPE = "create_segment"
DEFAULT_SOURCES = ["EXPERIAN", "TRANSUNION"]
# LIFT shown for both bureaus per the user's explicit call (2026-11-19) -- note Credit One's own
# T_EXPERIAN_MAILFILE / T_TRANSUNION_MAILFILE data dictionaries show LIFT_SCORE existing only in
# T_EXPERIAN_MAILFILE (T_TRANSUNION_MAILFILE has no LIFT_SCORE column). Showing LIFT here for
# TransUnion is a UI-only choice for now -- no DM_PADM_SCORE_RANGE_RULE_1 bands exist for
# TRANSUNION + LIFT yet, so selecting it will hit the "no active score-range rules" warning until
# those rows are added.
SOURCE_SCORE_TYPES = {
    "EXPERIAN": ["VS3", "VS4", "LIFT"],
    "TRANSUNION": ["VS3", "VS4", "LIFT"],
}
NONE = "— none —"

# (form field, label, dropdown field in VW_PADM_SEGMENT_DROPDOWN_60D or fixed options)
# Trimmed to exactly the fields Sgn-off_proposal.pdf's "Segment Creation" section lists (Bureau
# Score Type / Range / Source are mandatory fields above, shown separately). PROSPECT_SEGMENT_TYPE,
# CREDIT_BUREAU_MODEL, CREDIT_BUREAU_SCORE, CRS_MODEL, CRS_SCORE were here before but aren't in
# that list -- they belong to Campaign Creation's separate offer-grouping dropdowns, not this tab.
OPTIONAL_FIELDS = [
    ("ANNUAL_FEE", "Annual Fee", "ANNUAL_FEE"),
    ("NETWORK", "Network", "NETWORK"),
    ("MLA_FLAG", "MLA", ["Y", "N"]),
    ("RISK_SCORE_TYPE", "Risk Score Type", "CRS_MODEL"),
    ("RESPONSE_MODEL_TYPE", "Response Model Type", "RESPONSE_MODEL_TYPE"),
]


def segment_name(score_type, score_min, score_max, source):
    """[Bureau Score Type] [Score Min]-[Score Max] [Source], e.g. VS3 550-600 EXPERIAN."""
    if not score_type or score_min is None or score_max is None or not source:
        return ""
    return f"{score_type} {int(score_min)}-{int(score_max)} {source}".upper()


def _text(value):
    return value if isinstance(value, str) and value else None


def _offer_label(offers, allocations=None):
    """An offer can belong to more than one segment (many-to-many) -- when `allocations` is given,
    appends how many segments it's already on, so picking it for one more is an informed choice."""
    lookup = offers.set_index("CAMPAIGN_OFFER_ID")
    counts = allocations["CAMPAIGN_OFFER_ID"].value_counts().to_dict() if allocations is not None else {}

    def label(oid):
        if oid not in lookup.index:
            return str(oid)
        base = f"{lookup.loc[oid, 'OFFER_RESERVATION_CODE']} · {lookup.loc[oid, 'OFFER_DESCRIPTION'] or ''}"
        n = counts.get(oid, 0)
        return f"{base} (on {n} segment{'s' if n != 1 else ''})" if n else base
    return label


def _optional_inputs(dropdowns, key, defaults=None, disabled=False):
    defaults = defaults or {}
    values = {}
    cols = st.columns(3)
    for i, (field, label, source) in enumerate(OPTIONAL_FIELDS):
        options = source if isinstance(source, list) else dropdowns.get(source, [])
        current = _text(defaults.get(field))
        options = [NONE] + sorted({str(o) for o in options} | ({current} if current else set()))
        choice = cols[i % 3].selectbox(label, options, index=options.index(current) if current in options else 0,
                                         key=f"{key}_{field}", disabled=disabled)
        values[field] = None if choice == NONE else choice
    return values


def _create_form(session, campaign, offers, allocations, dropdowns):
    locked = campaign["locked"]
    rules = repository.score_range_rules(session)
    # Union with DEFAULT_SOURCES, not `or` -- source_names() only reflects bureaus already used by
    # a governed segment or DM_PADM_POPULATION_GROUP_RULE, so a real source (e.g. TRANSUNION) with
    # no segments yet silently disappeared under the old `or` fallback (which only triggers on a
    # fully empty list). This guarantees both known sources always show.
    sources = sorted(set(repository.source_names(session)["SOURCE_NAME"].tolist()) | set(DEFAULT_SOURCES))
    all_score_types = sorted(rules["SCORE_TYPE"].dropna().unique().tolist())

    st.subheader("Create segment")
    if not all_score_types:
        st.warning("No active score-range rules in DM_PADM_SCORE_RANGE_RULE_1 -- add one before creating segments.")
        return
    with st.container(border=True):
        st.markdown("**Mandatory fields** (*)")
        c1, c2, c3, c4 = st.columns(4)
        source = c1.selectbox("Prospect Source Bureau *", sources, key="cs_source", disabled=locked)
        # Score Type options are scoped to the selected Source (SOURCE_SCORE_TYPES); falls back to
        # every active score type if the source isn't in that mapping. Key includes `source` so the
        # widget resets cleanly instead of keeping a selection that's no longer valid for this source.
        allowed = SOURCE_SCORE_TYPES.get(source)
        score_types = [t for t in all_score_types if t in allowed] if allowed else all_score_types
        if not score_types:
            st.warning(f"No active score-range rules for {source} yet in DM_PADM_SCORE_RANGE_RULE_1.")
            return
        score_type = c2.selectbox("Bureau Score Type *", score_types, key=f"cs_score_type_{source}", disabled=locked)
        type_rules = rules[rules["SCORE_TYPE"] == score_type]
        lo, hi = int(type_rules["SCORE_MIN"].min()), int(type_rules["SCORE_MAX"].max())
        score_min = c3.number_input("Score Min *", min_value=0, max_value=1000, value=lo, step=1, key="cs_min", disabled=locked)
        score_max = c4.number_input("Score Max *", min_value=0, max_value=1000, value=hi, step=1, key="cs_max", disabled=locked)
        st.caption("Valid ranges for this score type: " + ", ".join(
            f"{r.SCORE_RANGE_CODE} ({int(r.SCORE_MIN)}-{int(r.SCORE_MAX)})" for r in type_rules.itertuples()))
        range_error = validation.validate_score_range(score_min, score_max, type_rules)
        if range_error:
            st.error(range_error)
        name = segment_name(score_type, score_min, score_max, source)
        st.text_input("Segment name (auto-generated)", value=name, disabled=True, key=f"cs_name_{name}")

        st.markdown("**Optional fields** (values mailed in the last 60 days)")
        optional = _optional_inputs(dropdowns, "cs_opt", disabled=locked)
        times_mailed = st.multiselect("Times Mailed", TIMES_MAILED_BUCKETS, key="cs_tm", disabled=locked)

    existing = repository.find_segment(session, score_type, score_min, score_max, source) if not range_error else None
    existing_id = existing.iloc[0]["SEGMENT_ID"] if existing is not None and not existing.empty else None
    on_campaign = existing_id is not None and existing_id in set(repository.campaign_segments(session, campaign["id"])["SEGMENT_ID"])

    suggested = repository.suggested_offers(session, campaign["id"], existing_id)
    st.markdown("**Offer allocation** -- all offers of this campaign (an offer may belong to more than one segment)")
    if suggested:
        st.caption(f"{len(suggested)} offer(s) pre-suggested from earlier campaigns of this segment -- keep or change.")
    selected = st.multiselect(
        "Offers", offers["CAMPAIGN_OFFER_ID"].tolist(), default=[o for o in suggested if o in set(offers["CAMPAIGN_OFFER_ID"])],
        format_func=_offer_label(offers, allocations), key=f"cs_offers_{existing_id}", disabled=locked,
    )

    reason = ui.reason_input("cs_reason", disabled=locked)
    if existing_id is not None:
        if on_campaign:
            st.warning(f"Segment **{name}** already exists and is on this campaign -- use Edit below.")
            return
        st.warning(f"Segment **{name}** already exists (duplicate mandatory fields). Reuse it instead.")
        if st.button("Reuse Existing Segment", type="primary", icon=":material/recycling:", disabled=locked, key="cs_reuse"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.reuse_segment(session, campaign["id"], existing_id, selected, reason.strip()),
                              f"Segment {name} added to the campaign with {len(selected)} offer(s).")
        return
    if st.button("Create Segment", type="primary", icon=":material/add:", disabled=locked or bool(range_error), key="cs_create"):
        if ui.require_reason(reason):
            fields = {"SEGMENT_NAME": name, "SOURCE_NAME": source, "SCORE_TYPE": score_type,
                      "SCORE_MIN": score_min, "SCORE_MAX": score_max, "MAIL_REMAIL": campaign["type"],
                      "TIMES_MAILED_FILTER": times_mailed, **optional}
            ui.run_action(SCOPE, lambda: repository.create_segment(session, campaign["id"], fields, selected, reason.strip()),
                          f"Segment {name} created with {len(selected)} offer(s).")


def _reuse_any(session, campaign, offers, allocations, segments):
    """Reuse any governed segment not yet on this campaign."""
    master = repository.segments_master(session)
    candidates = master[~master["SEGMENT_ID"].isin(segments["SEGMENT_ID"])]
    with st.expander("Reuse an existing governed segment"):
        if candidates.empty:
            st.caption("Every governed segment is already on this campaign.")
            return
        segment_id = st.selectbox("Segment", candidates["SEGMENT_ID"].tolist(),
                                   format_func=lambda s: candidates.set_index("SEGMENT_ID").loc[s, "SEGMENT_NAME"],
                                   key="cs_reuse_any")
        suggested = [o for o in repository.suggested_offers(session, campaign["id"], segment_id)
                     if o in set(offers["CAMPAIGN_OFFER_ID"])]
        selected = st.multiselect("Offers", offers["CAMPAIGN_OFFER_ID"].tolist(), default=suggested,
                                   format_func=_offer_label(offers, allocations), key=f"cs_reuse_any_offers_{segment_id}",
                                   disabled=campaign["locked"])
        reason = ui.reason_input("cs_reuse_any_reason", disabled=campaign["locked"])
        if st.button("Reuse Existing Segment", disabled=campaign["locked"], key="cs_reuse_any_btn"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.reuse_segment(session, campaign["id"], segment_id, selected, reason.strip()),
                              "Segment added to the campaign.")


def _campaign_segments(session, campaign, offers, allocations, dropdowns):
    st.subheader("Segments on this campaign")
    segments = repository.campaign_segments(session, campaign["id"])
    _reuse_any(session, campaign, offers, allocations, segments)
    if segments.empty:
        st.caption("No segments yet.")
        return
    st.dataframe(segments[["SEGMENT_NAME", "SOURCE_NAME", "SCORE_TYPE", "SCORE_MIN", "SCORE_MAX", "PROSPECT_SEGMENT_TYPE",
                            "ANNUAL_FEE", "NETWORK", "OFFER_COUNT", "UPDATED_BY", "UPDATED_TS"]],
                 hide_index=True, key="cs_segment_table")

    locked = campaign["locked"]
    segment_id = st.selectbox("Edit / remove segment", segments["SEGMENT_ID"].tolist(),
                               format_func=lambda s: segments.set_index("SEGMENT_ID").loc[s, "SEGMENT_NAME"], key="cs_edit_pick")
    segment = segments.set_index("SEGMENT_ID").loc[segment_id]
    with st.container(border=True):
        st.caption("Mandatory fields define the governed segment and its name, so they are fixed. Optional fields "
                   "and offers can be edited. An offer may belong to more than one segment -- this list only "
                   "changes this segment's own links.")
        changes = _optional_inputs(dropdowns, f"cs_edit_{segment_id}_{segment['ROW_VERSION']}",
                                    defaults=segment.to_dict(), disabled=locked)
        changed = {k: v for k, v in changes.items() if _text(v) != _text(segment.get(k))}
        current = allocations[allocations["SEGMENT_ID"] == segment_id]["CAMPAIGN_OFFER_ID"].tolist()
        chosen = st.multiselect("Offers", offers["CAMPAIGN_OFFER_ID"].tolist(), default=current,
                                 format_func=_offer_label(offers, allocations),
                                 key=f"cs_edit_offers_{segment_id}", disabled=locked)
        reason = ui.reason_input(f"cs_edit_reason_{segment_id}", disabled=locked)
        c1, c2 = st.columns(2)
        if c1.button("Save edits", type="primary", icon=":material/edit:", disabled=locked, key=f"cs_edit_save_{segment_id}"):
            if ui.require_reason(reason):
                def save():
                    messages = []
                    if changed:
                        messages.append(repository.edit_segment(session, campaign["id"], segment_id,
                                                                  segment["ROW_VERSION"], changed, reason.strip()))
                    if set(chosen) != set(current):
                        messages.append(repository.set_segment_offers(session, campaign["id"], segment_id, chosen, reason.strip()))
                    return " ".join(messages) or "Nothing changed."
                ui.run_action(SCOPE, save)
        if c2.button("Remove from Campaign", icon=":material/remove_circle:", disabled=locked, key=f"cs_remove_{segment_id}"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.remove_segment_from_campaign(session, campaign["id"], segment_id, reason.strip()))


def render(session):
    st.header("Create Segment")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    st.caption("Segmentation rules are TBD; score ranges and group labels come from reference tables "
               "(DM_PADM_SCORE_RANGE_RULE_1, DM_PADM_POPULATION_GROUP_RULE).")
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("Sync governed segments from source", icon=":material/sync:",
                      help="Insert-only: adds any new segment found in VW_PADM_SEGMENT_SOURCE_CANDIDATE "
                           "(real ACM mailfile history) that doesn't already exist here. Never touches "
                           "or overwrites an existing segment's fields.", key="cs_discover"):
            ui.run_action(SCOPE, lambda: repository.discover_segments(session),
                          lambda n: f"{n} new governed segment(s) added from source." if n else
                                    "No new segments found -- everything in source already exists here.")
    offers = repository.campaign_offers(session, campaign["id"])
    allocations = repository.offer_segment_allocations(session, campaign["id"])
    dropdowns = repository.dropdown_values(session)
    _create_form(session, campaign, offers, allocations, dropdowns)
    st.divider()
    _campaign_segments(session, campaign, offers, allocations, dropdowns)
