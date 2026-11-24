"""Pre Signature Page: live ACM-sourced offer data in the Matrix Creation Tool's column order
and sort, plus 4 tracking fields -- Total Available Volume, Quantity %, Quantity (units),
Owner/Approver. Carries forward from the previous campaign for a matching offer (by reservation
code) until saved here, and persists to a real table instead of an Excel file.

Total Available Volume is one shared number per segment section, matching the Matrix tool's
merged-cell layout. Since st.data_editor can't merge cells, it gets its own small editor with
exactly one row per section (so there is exactly one place to enter it, no per-offer-row
duplication/conflicts); the main offer grid shows that section's resolved volume read-only.

Quantity % and Quantity (Units) are linked: enter either one (a clean number/percentage, not a
combined free-text note) and the other is calculated from the section's Total Available Volume.

Two tables below the editors: a plain editable grid, and a read-only colored preview. Streamlit
cannot show live cell colors on an editable grid itself (the same limitation Segment Viewer hit)
-- the preview mirrors Segment Viewer's own proven styling pattern (a same-shape DataFrame of CSS
strings applied with Styler.apply(..., axis=None)). Non-tracking (Matrix) columns are colored by
Matrix segment section; the 4 tracking columns instead show save state -- green once a value is
saved, red while it's typed but not yet saved (flips to green on the next run after Save)."""

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
RED_UNSAVED = "background-color: #fca5a5"
GREEN_SAVED = "background-color: #86efac"


def _text(value):
    """None/NaN -> "" ; everything else -> a plain stripped string. Keeps a column's pandas dtype
    as plain text (object) from the start, so Streamlit can't infer a numeric column type for it
    and reject free-text entries like '100% (605-645) & 25% BAU volume (646+)'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _display_text(value, parser, formatter):
    """Like _text(), but if the value parses as a clean number, show it formatted (so a raw DB
    number like 25.0 displays as '25%' / '25,000') -- otherwise falls back to the raw text as-is
    (a free-text note is never reformatted or dropped)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    parsed = parser(value)
    return formatter(parsed) if parsed is not None else str(value).strip()


def render(session):
    st.header("Pre Signature Page")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    st.caption(f"{campaign['name']} · ACM offer data in the Matrix Creation Tool's column order, plus "
               "Total Available Volume / Quantity % / Quantity (Units) / Owner-Approver -- carried "
               "forward from the previous campaign for a matching offer (by reservation code) until "
               "saved here. K/MM shorthand accepted (160k, 2.7mm, 165,000).")

    rows = repository.signature_live(session, campaign["id"])
    if rows.empty:
        st.info("No ACM offers are snapshotted for this campaign yet.")
        return
    rows = rows.copy()
    rows["_SORT"] = [ui.segment_sort_rank(s, d) for s, d in
                      zip(rows.get("ACM_SEGMENT", ""), rows.get("SEGMENT_DESCRIPTION", ""))]
    sort_cols = [c for c in ["_SORT", "CREDIT_BUREAU_SCORE", "TEST_TYPE"] if c in rows.columns]
    rows = rows.sort_values(sort_cols).drop(columns="_SORT").reset_index(drop=True)
    rows["_SECTION"] = [ui.segment_color(s, d) or "none" for s, d in
                         zip(rows.get("ACM_SEGMENT", ""), rows.get("SEGMENT_DESCRIPTION", ""))]

    current = repository.pre_signature_detail(session, campaign["id"])
    current_by_offer = current.set_index("CAMPAIGN_OFFER_ID") if not current.empty else current

    prior = repository.previous_pre_signature_detail(session, campaign["id"])
    prior_by_code = prior.set_index("OFFER_RESERVATION_CODE") if not prior.empty else prior

    def value_for(i, col):
        offer_id = rows.loc[i, "CAMPAIGN_OFFER_ID"]
        code = rows.loc[i, "OFFER_RESERVATION_CODE"] if "OFFER_RESERVATION_CODE" in rows.columns else None
        if not current_by_offer.empty and offer_id in current_by_offer.index:
            return current_by_offer.loc[offer_id, col]
        if pd.notna(code) and not prior_by_code.empty and code in prior_by_code.index:
            return prior_by_code.loc[code, col]
        return None

    saved = pd.DataFrame(index=rows.index)
    for col in NEW_COLUMNS:
        saved[col] = [value_for(i, col) for i in rows.index]

    # Sections in display order (first occurrence), each a group of offer rows sharing one Matrix
    # segment color -- exactly where the Matrix tool shows one merged Available Volume cell.
    section_keys = list(dict.fromkeys(rows["_SECTION"]))
    section_rows = {key: rows.index[rows["_SECTION"] == key] for key in section_keys}

    def section_label(key):
        names = sorted({str(s).strip() for s in rows.loc[section_rows[key], "ACM_SEGMENT"].dropna()
                         if str(s).strip()})
        return ", ".join(names) if names else "(uncategorized)"

    def section_saved_volume(key):
        for i in section_rows[key]:
            value = ui.num(saved.loc[i, "TOTAL_AVAILABLE_VOLUME"])
            if value is not None:
                return value
        return None

    vol_label = NEW_LABELS["TOTAL_AVAILABLE_VOLUME"]
    locked = campaign["locked"]

    st.subheader("Total Available Volume by section")
    st.caption("One row per segment section (as in the Matrix tool's merged Available Volume cell) -- "
               "enter it once here and it applies to every offer in that section below.")
    section_frame = pd.DataFrame(
        {"Segment Section": [section_label(k) for k in section_keys],
         vol_label: [ui.format_volume(section_saved_volume(k)) for k in section_keys]},
        index=section_keys,
    )
    section_edited = st.data_editor(
        section_frame, hide_index=True, use_container_width=True,
        disabled=["Segment Section"],
        column_config={vol_label: st.column_config.TextColumn(
            vol_label, help="K/MM shorthand accepted (160k, 2.7mm, 165,000).")},
        key=f"psp_section_editor_{campaign['id']}",
    )
    section_volume = {k: ui.parse_volume(section_edited.loc[k, vol_label]) for k in section_keys}
    resolved_volume = rows["_SECTION"].map(section_volume)

    frame = pd.DataFrame(index=rows.index)
    for source, label in ui.MATRIX_COLUMNS:
        frame[label] = rows[source] if source in rows.columns else None
    frame[vol_label] = resolved_volume.map(ui.format_volume)
    frame[NEW_LABELS["QUANTITY_PERCENTAGE"]] = saved["QUANTITY_PERCENTAGE"].map(
        lambda v: _display_text(v, ui.parse_percent, ui.format_percent))
    frame[NEW_LABELS["QUANTITY_UNITS"]] = saved["QUANTITY_UNITS"].map(
        lambda v: _display_text(v, ui.parse_volume, ui.format_volume))
    frame[NEW_LABELS["OWNER_APPROVER"]] = saved["OWNER_APPROVER"].map(_text)

    st.subheader("Offers")
    locked = campaign["locked"]
    reason = ui.reason_input(f"psp_reason_{campaign['id']}", disabled=locked)
    pct_label, units_label = NEW_LABELS["QUANTITY_PERCENTAGE"], NEW_LABELS["QUANTITY_UNITS"]
    owner_label = NEW_LABELS["OWNER_APPROVER"]
    editable_cols = {pct_label, units_label, owner_label}
    edited = st.data_editor(
        frame, hide_index=True, use_container_width=True,
        disabled=[c for c in frame.columns if c not in editable_cols],
        column_config={
            vol_label: st.column_config.TextColumn(vol_label, help="Set above, one per section."),
            pct_label: st.column_config.TextColumn(pct_label),
            units_label: st.column_config.TextColumn(units_label),
            owner_label: st.column_config.TextColumn(owner_label),
        },
        key=f"psp_editor_{campaign['id']}",
    )

    # Quantity % and Quantity (Units) are linked through the section's resolved volume: whichever
    # one is a clean number, the other is calculated from it. Free-text/combined entries (not a
    # single clean number) are left exactly as typed on both sides -- no calculation applied.
    final_pct, final_units = edited[pct_label].copy(), edited[units_label].copy()
    for i in rows.index:
        volume = ui.num(resolved_volume.loc[i])
        pct = ui.parse_percent(edited.loc[i, pct_label])
        units = ui.parse_volume(edited.loc[i, units_label])
        if volume:
            if pct is not None and units is None:
                final_units.loc[i] = ui.format_volume(volume * pct / 100)
            elif units is not None and pct is None:
                final_pct.loc[i] = ui.format_percent(units / volume * 100)

    # Read-only colored preview, built the same way Segment Viewer's own (confirmed-working)
    # colored grid is: a same-shape DataFrame of CSS strings applied via Styler.apply(fn, axis=None).
    # Base color = the row's Matrix segment section; red overrides it on any of the 4 tracking
    # cells whose current value differs from what's actually saved.
    preview = frame.copy()
    preview[vol_label] = resolved_volume.map(ui.format_volume)
    preview[pct_label] = final_pct
    preview[units_label] = final_units
    preview[owner_label] = edited[owner_label]

    def changed(current, saved_values, parser=None):
        flags = []
        for i in rows.index:
            cur, base = current.loc[i], saved_values.loc[i]
            if parser is not None:
                cur_n, base_n = parser(cur), parser(base)
                if cur_n is not None or base_n is not None:
                    flags.append(cur_n != base_n)
                    continue
            flags.append(_text(cur) != _text(base))
        return pd.Series(flags, index=rows.index)

    # Tracking columns: current value + the parser that tells a "real value" from blank, used both
    # for the unsaved-diff check and for deciding whether a saved cell is non-empty (-> green).
    tracking = {
        vol_label: (resolved_volume.map(ui.format_volume), saved["TOTAL_AVAILABLE_VOLUME"], ui.num),
        pct_label: (final_pct, saved["QUANTITY_PERCENTAGE"], ui.parse_percent),
        units_label: (final_units, saved["QUANTITY_UNITS"], ui.parse_volume),
        owner_label: (edited[owner_label], saved["OWNER_APPROVER"], None),
    }
    unsaved = {label: changed(current, base, parser) for label, (current, base, parser) in tracking.items()}

    highlight = pd.DataFrame("", index=preview.index, columns=preview.columns)
    for i in rows.index:
        base_hex = rows.loc[i, "_SECTION"]
        if base_hex != "none":
            highlight.loc[i, :] = f"background-color: {base_hex}"
    # Tracking columns show save state instead of section color: red = typed here but not saved
    # yet, green = saved (matches the database) and not blank. Saving flips red -> green because
    # the rerun after a save re-reads `saved` from the database, so nothing is "unsaved" any more.
    for label, (current, _base, parser) in tracking.items():
        for i in rows.index:
            if unsaved[label].loc[i]:
                highlight.loc[i, label] = RED_UNSAVED
            else:
                value = current.loc[i]
                present = (parser(value) is not None) if parser is not None else (_text(value) != "")
                if present:
                    highlight.loc[i, label] = GREEN_SAVED

    st.caption("Preview (read-only) -- non-tracking columns colored by Matrix segment section. "
               "Tracking columns (Volume / Quantity % / Quantity Units / Owner-Approver): green = "
               "saved, red = entered here but not yet saved.")
    st.dataframe(preview.style.apply(lambda _: highlight, axis=None),
                 hide_index=True, use_container_width=True, key=f"psp_preview_{campaign['id']}")

    if st.button("Save tracking fields", type="primary", icon=":material/save:",
                  disabled=locked, key=f"psp_save_{campaign['id']}"):
        if ui.require_reason(reason):
            payload = [
                {
                    "CAMPAIGN_OFFER_ID": rows.loc[i, "CAMPAIGN_OFFER_ID"],
                    "TOTAL_AVAILABLE_VOLUME": ui.num(resolved_volume.loc[i]),
                    "QUANTITY_PERCENTAGE": final_pct.loc[i],
                    "QUANTITY_UNITS": final_units.loc[i],
                    "OWNER_APPROVER": edited.loc[i, owner_label],
                }
                for i in rows.index
            ]
            ui.run_action(SCOPE, lambda: repository.save_pre_signature_detail(
                session, campaign["id"], payload, reason.strip()))
