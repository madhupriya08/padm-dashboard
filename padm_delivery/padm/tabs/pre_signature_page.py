"""Pre Signature Page: live ACM-sourced offer data in the Matrix Creation Tool's column order
and sort, plus 4 tracking fields -- Total Available Volume, Quantity %, Quantity (units),
Owner/Approver. Carries forward from the previous campaign for a matching offer (by reservation
code) until saved here, and persists to a real table instead of an Excel file.

Total Available Volume is one shared number per segment section, matching the Matrix tool's
merged-cell layout. st.data_editor can't merge cells, so it gets its own small editor with exactly
one row per section; the main offer grid shows that section's resolved volume read-only.

Quantity % and Quantity (Units) are linked as a waterfall down each section, in row order, matching
the Matrix tool's own layout (its "BALANCE" rows and approximate "~228K"-style remainders are
calculated leftovers, not typed numbers). Each row's % applies to whatever volume is left after the
rows above it, not to the section's original total, so percentages on different rows aren't
comparable to one another. Units are the primary input (a straight subtraction from what's left); a
clean % resolves to units the same way, against the current remaining amount. Whichever cell was
just edited wins and recalculates its counterpart, even when a row already has both filled in.
Free text (e.g. a cutoff-tiered note like "100% (605-645) & 25% BAU volume (646+)") is left as
typed and doesn't consume any of the running total -- PADM has no population-split data for that
kind of entry, so it's flagged rather than calculated. The one remaining blank row in a section
absorbs whatever's left, matching the sheet's own BALANCE row. Entries that already exceed a
section's volume are flagged as a validation error rather than accepted silently.

Two tables: a plain editable grid, and a read-only colored preview below it. st.data_editor can't
show per-cell or per-row background colors while editable, so the grid carries a Status column
(green/red per row, lagging one rerun behind the latest edit) and an emoji square approximating
each row's Matrix segment color; the preview colors the whole row with the real segment hex color,
using the same Styler pattern as Segment Viewer."""

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
STATUS_COL = "Status"
STATUS_SAVED = "\U0001F7E2"     # green circle
STATUS_UNSAVED = "\U0001F534"   # red circle


def _text(value):
    """None/NaN -> "" ; everything else -> a plain stripped string. Keeps the column's dtype as
    plain text so Streamlit doesn't infer a numeric column and reject free-text entries."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _display_text(value, parser, formatter):
    """Like _text(), but formats a clean number through `formatter`; a free-text value is left
    exactly as typed."""
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
    # segment color -- where the Matrix tool shows one merged Available Volume cell.
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

    # Status column seeded from the save-state computed on the previous rerun -- a value computed
    # from this grid's own edits can't be redrawn into it within the same run.
    status_key = f"psp_status_{campaign['id']}"
    status_state = st.session_state.get(status_key, {})
    offer_ids = [str(rows.loc[i, "CAMPAIGN_OFFER_ID"]) for i in rows.index]

    # Quantity %/Units auto-fill is seeded back in from session_state too, so the cell you didn't
    # type into shows the calculated value right away instead of only after a Save.
    calc_key = f"psp_calc_{campaign['id']}"
    calc_state = st.session_state.get(calc_key, {})

    # What the %/Units cells held last run, used below to detect which one was just edited.
    # Comparing against `frame` (what we're about to display) doesn't work: st.data_editor keeps
    # re-asserting whatever was last typed into a cell on every rerun regardless of the new data
    # passed in, so once both % and Units have been typed into at different times, both would look
    # permanently "changed" against any recalculated frame. Comparing against the widget's own
    # previous output avoids that.
    prev_key = f"psp_prev_values_{campaign['id']}"
    prev_values = st.session_state.get(prev_key, {})

    def initial_status(i):
        """Status for a row session_state has no computed value for yet (before the first edit
        this session) -- falls back to what's actually saved, so existing data shows green
        immediately instead of waiting for an edit."""
        for col, parser in (("TOTAL_AVAILABLE_VOLUME", ui.num), ("QUANTITY_PERCENTAGE", ui.parse_percent),
                            ("QUANTITY_UNITS", ui.parse_volume), ("OWNER_APPROVER", None)):
            value = saved.loc[i, col]
            present = (parser(value) is not None) if parser is not None else (_text(value) != "")
            if present:
                return STATUS_SAVED
        return ""

    # Total Available Volume is entered once per section (above) and read-only here -- shown on
    # only the first row of each section (like the Matrix tool's merged cell).
    first_row_of_section = {key: section_rows[key][0] for key in section_keys}

    frame = pd.DataFrame(index=rows.index)
    frame[STATUS_COL] = [status_state.get(oid, initial_status(i)) for i, oid in zip(rows.index, offer_ids)]
    for source, label in ui.MATRIX_COLUMNS:
        frame[label] = rows[source] if source in rows.columns else None
    # Matrix segment color as an emoji square, since the editable grid can't show real cell colors.
    if "Segment" in frame.columns:
        def _segment_cell(s, d):
            emoji = ui.segment_color_emoji(s, d)
            return (f"{emoji} " if emoji else "") + _text(s)
        frame["Segment"] = [_segment_cell(s, d) for s, d in
                             zip(rows.get("ACM_SEGMENT", ""), rows.get("SEGMENT_DESCRIPTION", ""))]
    frame[vol_label] = [ui.format_volume(resolved_volume.loc[i])
                         if i == first_row_of_section[rows.loc[i, "_SECTION"]] else ""
                         for i in rows.index]
    frame[NEW_LABELS["QUANTITY_PERCENTAGE"]] = [
        calc_state.get(oid, {}).get("pct", _display_text(saved.loc[i, "QUANTITY_PERCENTAGE"],
                                                           ui.parse_percent, ui.format_percent))
        for i, oid in zip(rows.index, offer_ids)]
    frame[NEW_LABELS["QUANTITY_UNITS"]] = [
        calc_state.get(oid, {}).get("units", _display_text(saved.loc[i, "QUANTITY_UNITS"],
                                                             ui.parse_volume, ui.format_volume))
        for i, oid in zip(rows.index, offer_ids)]
    frame[NEW_LABELS["OWNER_APPROVER"]] = saved["OWNER_APPROVER"].map(_text)

    st.subheader("Offers")
    locked = campaign["locked"]
    reason = ui.reason_input(f"psp_reason_{campaign['id']}", disabled=locked)
    pct_label, units_label = NEW_LABELS["QUANTITY_PERCENTAGE"], NEW_LABELS["QUANTITY_UNITS"]
    owner_label = NEW_LABELS["OWNER_APPROVER"]
    editable_cols = {pct_label, units_label, owner_label}
    st.caption(f"{STATUS_SAVED} = every entered value here matches what's saved. {STATUS_UNSAVED} = "
               "something here hasn't been saved yet. Updates shortly after you act (e.g. edit another "
               "cell), not on the very keystroke that changed it.")
    edited = st.data_editor(
        frame, hide_index=True, use_container_width=True,
        disabled=[c for c in frame.columns if c not in editable_cols],
        column_config={
            STATUS_COL: st.column_config.TextColumn(STATUS_COL, width="small"),
            vol_label: st.column_config.TextColumn(vol_label, help="Set above, one per section."),
            pct_label: st.column_config.TextColumn(
                pct_label, help="Waterfall: % of what's left in this section after the rows above it, "
                "not of the section's original total."),
            units_label: st.column_config.TextColumn(units_label),
            owner_label: st.column_config.TextColumn(owner_label),
        },
        key=f"psp_editor_{campaign['id']}",
    )

    # Quantity % and Quantity (Units) waterfall down each section in row order: each row's % is
    # relative to whatever volume is left after the rows above it, not the section's original
    # total. Units are the primary input (a straight subtraction from what's left); a clean %
    # resolves to units against the current remaining amount. Whichever cell was just edited wins
    # when a row already has both filled in.
    final_pct, final_units = edited[pct_label].copy(), edited[units_label].copy()
    new_prev_values = {}
    OVER_ALLOCATED_TOLERANCE = 1e-6
    remaining_lines = []
    over_allocated_errors = []
    for key in section_keys:
        idx = section_rows[key]
        volume = ui.num(section_volume.get(key))
        remaining = volume
        skip = False
        blanks = []
        for i in idx:
            oid = offer_ids[i]
            pct_text, units_text = _text(edited.loc[i, pct_label]), _text(edited.loc[i, units_label])
            pct = ui.parse_percent(pct_text)
            units = ui.parse_volume(units_text)
            prev = prev_values.get(oid, {})
            pct_changed = pct_text != prev.get("pct", _text(frame.loc[i, pct_label]))
            units_changed = units_text != prev.get("units", _text(frame.loc[i, units_label]))
            new_prev_values[oid] = {"pct": pct_text, "units": units_text}

            if pct_text == "" and units_text == "":
                blanks.append(i)
                continue
            if pct is None and units is None:
                skip = True  # free text -- doesn't consume any of the running total
                continue
            if remaining is None:
                # No section volume set yet -- canonical-format what's typed, no waterfall math.
                if pct is not None:
                    final_pct.loc[i] = ui.format_percent(pct)
                if units is not None:
                    final_units.loc[i] = ui.format_volume(units)
                continue

            if units_changed and not pct_changed and units is not None:
                row_units = units
            elif pct_changed and not units_changed and pct is not None:
                row_units = remaining * pct / 100
            elif units is not None:
                row_units = units
            else:
                row_units = remaining * pct / 100
            final_units.loc[i] = ui.format_volume(row_units)
            final_pct.loc[i] = ui.format_percent(row_units / remaining * 100) if remaining else ui.format_percent(0)
            remaining -= row_units

        if not skip and len(blanks) == 1 and remaining is not None:
            # The one remaining blank row absorbs whatever's left of the section (the sheet's own
            # BALANCE row).
            i = blanks[0]
            final_units.loc[i] = ui.format_volume(remaining)
            final_pct.loc[i] = ui.format_percent(100)
            remaining = 0.0

        if volume is None:
            remaining_lines.append(f"- {section_label(key)}: set a Total Available Volume above to allocate.")
        elif skip:
            remaining_lines.append(f"- {section_label(key)}: can't total (contains free-text entries).")
        elif remaining is not None and remaining < -OVER_ALLOCATED_TOLERANCE:
            over_units = ui.format_volume(-remaining)
            remaining_lines.append(f"- ⚠️ {section_label(key)}: OVER-ALLOCATED by {over_units} units "
                                    f"(of {ui.format_volume(volume)} available).")
            over_allocated_errors.append(
                f"**{section_label(key)}**: entries exceed this section's Total Available Volume "
                f"by {over_units} units. Reduce one or more entries.")
        else:
            allocated = volume - remaining
            remaining_lines.append(f"- {section_label(key)}: {ui.format_volume(allocated)} of "
                                    f"{ui.format_volume(volume)} allocated, {ui.format_volume(remaining)} remaining.")
    if over_allocated_errors:
        st.error("\n\n".join(over_allocated_errors))
    st.markdown("**Allocation by section (waterfall -- each row from what's left after the rows "
                "above it):**\n\n" + "\n".join(remaining_lines))

    # Read-only colored preview: st.data_editor can't paint a cell's background while editable, so
    # real per-row color lives in a second, read-only table, built the same way as Segment Viewer's
    # own colored grid (a same-shape DataFrame of CSS strings via Styler.apply(fn, axis=None)).
    # Every column gets the row's segment color except the 4 tracking columns, left plain.
    preview = frame.copy()
    preview[pct_label] = final_pct
    preview[units_label] = final_units
    preview[owner_label] = edited[owner_label]
    uncolored = {vol_label, pct_label, units_label, owner_label}
    highlight = pd.DataFrame("", index=preview.index, columns=preview.columns)
    for i in rows.index:
        base_hex = rows.loc[i, "_SECTION"]
        if base_hex != "none":
            for col in preview.columns:
                if col not in uncolored:
                    highlight.loc[i, col] = f"background-color: {base_hex}"
    st.caption("Preview (read-only) -- whole row colored by Matrix segment, except the 4 tracking "
               "columns on the right.")
    st.dataframe(preview.style.apply(lambda _: highlight, axis=None),
                 hide_index=True, use_container_width=True, key=f"psp_preview_{campaign['id']}")

    # Persist this run's calculated %/Units and raw widget values for the next rerun.
    st.session_state[calc_key] = {
        offer_ids[i]: {"pct": final_pct.loc[i], "units": final_units.loc[i]} for i in rows.index
    }
    st.session_state[prev_key] = new_prev_values

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

    tracking = {
        vol_label: (resolved_volume.map(ui.format_volume), saved["TOTAL_AVAILABLE_VOLUME"], ui.num),
        pct_label: (final_pct, saved["QUANTITY_PERCENTAGE"], ui.parse_percent),
        units_label: (final_units, saved["QUANTITY_UNITS"], ui.parse_volume),
        owner_label: (edited[owner_label], saved["OWNER_APPROVER"], None),
    }
    unsaved = {label: changed(current, base, parser) for label, (current, base, parser) in tracking.items()}

    def row_has_value(i):
        for label, (current, _base, parser) in tracking.items():
            value = current.loc[i]
            if (parser(value) is not None) if parser is not None else (_text(value) != ""):
                return True
        return False

    new_status_state = {}
    for i in rows.index:
        if any(unsaved[label].loc[i] for label in tracking):
            new_status_state[offer_ids[i]] = STATUS_UNSAVED
        elif row_has_value(i):
            new_status_state[offer_ids[i]] = STATUS_SAVED
        else:
            new_status_state[offer_ids[i]] = ""
    st.session_state[status_key] = new_status_state

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
