"""Pre Signature Page: live ACM-sourced offer data in the Matrix Creation Tool's column order
and sort, plus 4 tracking fields -- Total Available Volume, Quantity %, Quantity (units),
Owner/Approver. Carries forward from the previous campaign for a matching offer (by reservation
code) until saved here, and persists to a real table instead of an Excel file.

Two tables: a plain editable grid, and a read-only colored preview below it. Streamlit cannot show
live cell colors on an editable grid itself (the same limitation Segment Viewer hit) -- the preview
is the only way to show the Matrix tool's segment color-coding (and red for unsaved edits) without
losing the native toolbar (expand/search/download) on the editable grid.

Total Available Volume is one shared number per segment section, matching the Matrix tool's
merged-cell layout -- entering it on any row in a section applies it to the whole section.
Quantity % and Quantity (Units) are linked: enter either one (a clean number/percentage, not a
combined free-text note) and the other is calculated from the section's Total Available Volume."""

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
               "saved here. Total Available Volume is shared across every offer in the same colored "
               "section (as in the Matrix tool) -- type it once anywhere in a section. K/MM shorthand "
               "accepted (160k, 2.7mm, 165,000).")

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

    frame = pd.DataFrame(index=rows.index)
    for source, label in ui.MATRIX_COLUMNS:
        frame[label] = rows[source] if source in rows.columns else None
    vol_label = NEW_LABELS["TOTAL_AVAILABLE_VOLUME"]
    frame[vol_label] = saved["TOTAL_AVAILABLE_VOLUME"].map(ui.format_volume)
    for col in ("QUANTITY_PERCENTAGE", "QUANTITY_UNITS", "OWNER_APPROVER"):
        frame[NEW_LABELS[col]] = saved[col]

    segment_names = sorted({str(s).strip() for s in rows.get("ACM_SEGMENT", pd.Series(dtype=str)).dropna()
                             if str(s).strip()})
    if segment_names:
        st.caption("Segments in this campaign (each is one Total Available Volume section): " +
                   ", ".join(segment_names))

    locked = campaign["locked"]
    reason = ui.reason_input(f"psp_reason_{campaign['id']}", disabled=locked)
    editable_cols = set(NEW_LABELS.values())
    edited = st.data_editor(
        frame, hide_index=True, use_container_width=True,
        disabled=[c for c in frame.columns if c not in editable_cols],
        key=f"psp_editor_{campaign['id']}",
    )

    # Total Available Volume is one shared number per section (a merged cell in the real Matrix
    # tool) -- resolve each section to a single value from whatever was typed anywhere in it, then
    # propagate that value to the rest of the section.
    resolved_volume = edited[vol_label].map(ui.parse_volume)
    conflicts = 0
    for _, idx in rows.groupby("_SECTION").groups.items():
        values = resolved_volume.loc[idx].dropna().unique()
        if len(values) > 1:
            conflicts += 1
        if len(values):
            resolved_volume.loc[idx] = values[-1]
    if conflicts:
        st.warning(f"{conflicts} section(s) had more than one Total Available Volume typed -- "
                   "used the last one entered for the whole section.")

    # Quantity % and Quantity (Units) are linked through that section volume: whichever one is a
    # clean number, the other is calculated from it. Free-text/combined entries (not a single clean
    # number) are left exactly as typed on both sides -- no calculation applied.
    pct_label, units_label = NEW_LABELS["QUANTITY_PERCENTAGE"], NEW_LABELS["QUANTITY_UNITS"]
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

    # Read-only colored preview: the editable grid above can't show cell colors (same Streamlit
    # limitation Segment Viewer hit), so this mirrors it with the Matrix tool's section color as
    # the base and red wherever a value here hasn't been saved yet.
    RED_UNSAVED = "background-color: #fca5a5"
    owner_label = NEW_LABELS["OWNER_APPROVER"]

    def _changed(current, saved_values, parser=None):
        flags = []
        for i in rows.index:
            cur, base = current.loc[i], saved_values.loc[i]
            if parser is not None:
                cur_n, base_n = parser(cur), parser(base)
                if cur_n is not None or base_n is not None:
                    flags.append(cur_n != base_n)
                    continue
            cur_s = "" if cur is None or (isinstance(cur, float) and pd.isna(cur)) else str(cur).strip()
            base_s = "" if base is None or (isinstance(base, float) and pd.isna(base)) else str(base).strip()
            flags.append(cur_s != base_s)
        return pd.Series(flags, index=rows.index)

    unsaved = {
        vol_label: _changed(resolved_volume, saved["TOTAL_AVAILABLE_VOLUME"], ui.num),
        pct_label: _changed(final_pct, saved["QUANTITY_PERCENTAGE"], ui.parse_percent),
        units_label: _changed(final_units, saved["QUANTITY_UNITS"], ui.parse_volume),
        owner_label: _changed(edited[owner_label], saved["OWNER_APPROVER"]),
    }

    preview = frame.copy()
    preview[vol_label] = resolved_volume.map(ui.format_volume)
    preview[pct_label] = final_pct
    preview[units_label] = final_units
    preview[owner_label] = edited[owner_label]

    def style_row(row):
        base_hex = rows.loc[row.name, "_SECTION"]
        base_css = "" if base_hex == "none" else f"background-color: {base_hex}"
        styles = {col: base_css for col in preview.columns}
        for label, flags in unsaved.items():
            if flags.loc[row.name]:
                styles[label] = RED_UNSAVED
        return pd.Series(styles)

    st.caption("Preview (read-only) -- colored by Matrix segment section; red = entered here but not "
               "yet saved.")
    st.dataframe(preview.style.apply(style_row, axis=1), hide_index=True, use_container_width=True)

    if st.button("Save tracking fields", type="primary", icon=":material/save:",
                  disabled=locked, key=f"psp_save_{campaign['id']}"):
        if ui.require_reason(reason):
            payload = [
                {
                    "CAMPAIGN_OFFER_ID": rows.loc[i, "CAMPAIGN_OFFER_ID"],
                    "TOTAL_AVAILABLE_VOLUME": ui.num(resolved_volume.loc[i]),
                    "QUANTITY_PERCENTAGE": final_pct.loc[i],
                    "QUANTITY_UNITS": final_units.loc[i],
                    "OWNER_APPROVER": edited.loc[i, NEW_LABELS["OWNER_APPROVER"]],
                }
                for i in rows.index
            ]
            ui.run_action(SCOPE, lambda: repository.save_pre_signature_detail(
                session, campaign["id"], payload, reason.strip()))
