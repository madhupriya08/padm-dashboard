"""Pre Signature Page: live ACM-sourced offer data in the Matrix Creation Tool's column order
and sort, plus 4 tracking fields -- Total Available Volume, Quantity %, Quantity (units),
Owner/Approver. Carries forward from the previous campaign for a matching offer (by reservation
code) until saved here, and persists to a real table instead of an Excel file.

Total Available Volume is one shared number per segment section, matching the Matrix tool's
merged-cell layout. Since st.data_editor can't merge cells, it gets its own small editor with
exactly one row per section (so there is exactly one place to enter it, no per-offer-row
duplication/conflicts); the main offer grid shows that section's resolved volume read-only.

Offers are shown in ONE table, colored by Matrix segment (whole row, real hex colors, everything
except the 4 tracking columns on the right) -- the tradeoff for that is this table is read-only.
Streamlit's st.data_editor cannot show per-cell or per-row background colors while editable, for
any column combination -- there is no supported way around that, so a colored table and an inline-
editable table are mutually exclusive in Streamlit. Editing therefore happens by selecting a row
(st.dataframe's on_select, same pattern used elsewhere in this app, e.g. the campaign list) and
filling in a small form below the table with just that row's Quantity %, Quantity (Units) and
Owner/Approver, then saving that one row. The colored table itself is built the same proven way
Segment Viewer's own colored grid is: a same-shape DataFrame of CSS strings applied via
Styler.apply(fn, axis=None).

Quantity % and Quantity (Units) are linked: enter either one (a clean number/percentage, not a
combined free-text note) in the form and the other is calculated from the section's Total
Available Volume before saving. A clean value on either side is also re-displayed in its canonical
format (a typed "80" becomes "80%"). A section with exactly one row always represents 100% of that
section (and the full Units) regardless of what's typed into it, the same way one offer alone IS
its whole available volume in the Matrix tool. A "Remaining % by section" readout above the table
shows each section's % allocated and what's left, computed from what's currently saved. Skipped
for a section containing free text (e.g. a cutoff-tiered note like "100% (605-645) & 25% BAU
volume (646+)"), since the true remaining total can't be known for sure then -- that same kind of
row (needing two different percentages for two score sub-bands) stays free text, typed exactly as
the source shows it: PADM has no data source giving the population split between those sub-bands,
so that specific split isn't calculated, only flagged."""

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

    # Total Available Volume is entered once per section (above) and is read-only here -- show it
    # on only the first row of each section (like the Matrix tool's merged cell), blank on the
    # rest of the section, instead of repeating the same number on every row.
    first_row_of_section = {key: section_rows[key][0] for key in section_keys}
    pct_label, units_label = NEW_LABELS["QUANTITY_PERCENTAGE"], NEW_LABELS["QUANTITY_UNITS"]
    owner_label = NEW_LABELS["OWNER_APPROVER"]

    def row_display(i):
        pct = _display_text(saved.loc[i, "QUANTITY_PERCENTAGE"], ui.parse_percent, ui.format_percent)
        units = _display_text(saved.loc[i, "QUANTITY_UNITS"], ui.parse_volume, ui.format_volume)
        owner = _text(saved.loc[i, "OWNER_APPROVER"])
        return pct, units, owner

    frame = pd.DataFrame(index=rows.index)
    for source, label in ui.MATRIX_COLUMNS:
        frame[label] = rows[source] if source in rows.columns else None
    frame[vol_label] = [ui.format_volume(resolved_volume.loc[i])
                         if i == first_row_of_section[rows.loc[i, "_SECTION"]] else ""
                         for i in rows.index]
    display_rows = [row_display(i) for i in rows.index]
    frame[pct_label] = [d[0] for d in display_rows]
    frame[units_label] = [d[1] for d in display_rows]
    frame[owner_label] = [d[2] for d in display_rows]

    # Section-level allocation (from what's actually saved): how much % is accounted for in each
    # section, and what's left of its 100%. Skipped for a section containing free text (e.g. a
    # cutoff-tiered note like "100% (605-645) & 25% BAU volume (646+)"), since the true remaining
    # % can't be known for sure then.
    remaining_lines = []
    for key in section_keys:
        idx = section_rows[key]
        clean_total, skip, any_value = 0.0, False, False
        for i in idx:
            raw_pct, raw_units = frame.loc[i, pct_label], frame.loc[i, units_label]
            if raw_pct == "" and raw_units == "":
                continue
            any_value = True
            pct = ui.parse_percent(raw_pct)
            units = ui.parse_volume(raw_units)
            volume = ui.num(resolved_volume.loc[i])
            if pct is not None:
                clean_total += pct
            elif units is not None and volume:
                clean_total += units / volume * 100
            else:
                skip = True
        if not any_value:
            continue
        if skip:
            remaining_lines.append(f"- {section_label(key)}: can't total (contains free-text entries).")
        else:
            remaining_lines.append(f"- {section_label(key)}: {clean_total:g}% allocated, "
                                    f"{100 - clean_total:g}% remaining.")
    if remaining_lines:
        st.markdown("**Remaining % by section (as currently saved):**\n\n" + "\n".join(remaining_lines))

    # The one colored table: read-only (st.dataframe can show real cell/row colors; an editable
    # st.data_editor categorically cannot, for a single cell or a whole row alike -- there is no
    # supported way around that). Styled the same proven way Segment Viewer's own colored grid is:
    # a same-shape DataFrame of CSS strings applied via Styler.apply(fn, axis=None). Every column
    # gets the row's real Matrix segment hex color EXCEPT the 4 tracking columns on the right
    # (Volume/Quantity %/Quantity Units/Owner-Approver), left plain, as asked. Editing happens by
    # selecting a row below, not inline in this table.
    uncolored = {vol_label, pct_label, units_label, owner_label}
    highlight = pd.DataFrame("", index=frame.index, columns=frame.columns)
    for i in rows.index:
        base_hex = rows.loc[i, "_SECTION"]
        if base_hex != "none":
            for col in frame.columns:
                if col not in uncolored:
                    highlight.loc[i, col] = f"background-color: {base_hex}"

    st.subheader("Offers")
    st.caption("Whole row colored by Matrix segment, except the 4 tracking columns on the right. "
               "Click a row to edit its Quantity % / Quantity (Units) / Owner-Approver below.")
    event = st.dataframe(
        frame.style.apply(lambda _: highlight, axis=None),
        hide_index=True, use_container_width=True, on_select="rerun",
        selection_mode="single-row", key=f"psp_offers_{campaign['id']}",
    )
    selected = event.selection.rows if event and event.selection else []
    if not selected:
        st.info("Select a row above to edit its tracking fields.")
        return
    i = selected[0]
    offer_id = rows.loc[i, "CAMPAIGN_OFFER_ID"]
    volume = ui.num(resolved_volume.loc[i])
    current_pct, current_units, current_owner = row_display(i)
    label = frame.loc[i, "Segment"] if "Segment" in frame.columns else str(offer_id)
    code = rows.loc[i, "OFFER_RESERVATION_CODE"] if "OFFER_RESERVATION_CODE" in rows.columns else None

    st.markdown(f"**Editing:** {label}" + (f" · {code}" if pd.notna(code) else ""))
    c1, c2, c3 = st.columns(3)
    pct_input = c1.text_input(pct_label, value=current_pct, disabled=locked,
                               key=f"psp_edit_pct_{campaign['id']}_{offer_id}")
    units_input = c2.text_input(units_label, value=current_units, disabled=locked,
                                 key=f"psp_edit_units_{campaign['id']}_{offer_id}")
    owner_input = c3.text_input(owner_label, value=current_owner, disabled=locked,
                                 key=f"psp_edit_owner_{campaign['id']}_{offer_id}")
    reason = ui.reason_input(f"psp_reason_{campaign['id']}_{offer_id}", disabled=locked)

    if st.button("Save this row", type="primary", icon=":material/save:",
                  disabled=locked, key=f"psp_save_{campaign['id']}_{offer_id}"):
        if ui.require_reason(reason):
            pct = ui.parse_percent(pct_input)
            units = ui.parse_volume(units_input)
            final_pct_val, final_units_val = pct_input, units_input
            if pct is not None:
                final_pct_val = ui.format_percent(pct)
            if units is not None:
                final_units_val = ui.format_volume(units)
            if volume:
                if pct is not None and units is None:
                    final_units_val = ui.format_volume(volume * pct / 100)
                elif units is not None and pct is None:
                    final_pct_val = ui.format_percent(units / volume * 100)
            # A section with exactly one row IS that section -- it always represents 100% of that
            # section's volume, regardless of what's typed, the same way the Matrix tool treats a
            # single-offer section as the whole available volume.
            if volume and len(section_rows[rows.loc[i, "_SECTION"]]) == 1:
                final_pct_val = ui.format_percent(100)
                final_units_val = ui.format_volume(volume)
            payload = [{
                "CAMPAIGN_OFFER_ID": offer_id,
                "TOTAL_AVAILABLE_VOLUME": volume,
                "QUANTITY_PERCENTAGE": final_pct_val,
                "QUANTITY_UNITS": final_units_val,
                "OWNER_APPROVER": owner_input,
            }]
            ui.run_action(SCOPE, lambda: repository.save_pre_signature_detail(
                session, campaign["id"], payload, reason.strip()))
