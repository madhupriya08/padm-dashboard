"""Pre Signature Page: live ACM offer data in Matrix Creation Tool column order, plus 3 tracking
fields -- Volume, Quantity, Owner/Approver -- carried forward from the previous campaign until
saved here. Shows Main and Remail together for the same month (a "Campaign" column tells rows
apart); saving routes each offer back to its own campaign, skipping one that's APPROVED. Quantity
is one combined field: a value ending in "%" is a percentage of that row's Volume, otherwise a flat
amount -- whichever isn't typed is derived from the other where possible."""

import streamlit as st
import pandas as pd

from padm import exports, repository, ui

SCOPE = "pre_signature_page"
NEW_COLUMNS = ["TOTAL_AVAILABLE_VOLUME", "QUANTITY_PERCENTAGE", "QUANTITY_UNITS", "OWNER_APPROVER"]
VOL_LABEL = "Volume"
QTY_LABEL = "Quantity"
OWNER_LABEL = "Owner/Approver"
CAMPAIGN_LABEL = "Campaign"
OVER_ALLOCATED_TOLERANCE = 1e-6


def _text(value):
    """None/NaN -> ""; everything else -> a plain stripped string."""
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


def _saved_quantity_display(saved_pct, saved_units):
    """Combined Quantity display from whichever saved column is set; % takes precedence."""
    pct_text = _display_text(saved_pct, ui.parse_percent, ui.format_percent)
    if pct_text:
        return pct_text
    return _display_text(saved_units, ui.parse_volume, ui.format_volume)


def render(session):
    st.header("Pre Signature Page")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)

    sibling = repository.sibling_campaign(session, campaign["id"])
    campaign_type_by_id = {campaign["id"]: "Main" if campaign.get("type", "MAIN") == "MAIN" else "Remail"}
    campaign_ids = [campaign["id"]]
    if not sibling.empty:
        sib = sibling.iloc[0]
        campaign_ids.append(sib["CAMPAIGN_ID"])
        campaign_type_by_id[sib["CAMPAIGN_ID"]] = "Main" if sib["CAMPAIGN_TYPE"] == "MAIN" else "Remail"
        st.caption(f"{campaign['name']} -- also showing {sib['CAMPAIGN_DISPLAY_NAME']} "
                   f"({sib['STATUS']}) for the same month.")
    else:
        st.caption(f"{campaign['name']} -- no Main/Remail sibling campaign exists for this month yet.")
    st.caption("ACM offer data in the Matrix Creation Tool's column order, plus Volume / Quantity / "
               "Owner-Approver -- carried forward from the previous campaign for a matching offer "
               "(by reservation code) until saved here. K/MM shorthand accepted (160k, 2.7mm, 165,000). "
               "Quantity: type a value ending in % for a percentage of that row's Volume, or a plain "
               "number/K/MM for a flat amount.")

    rows = repository.signature_live_for_month(session, campaign_ids)
    if rows.empty:
        st.info("No ACM offers are snapshotted for this campaign yet.")
        return
    rows = rows.copy()
    # VW_PADM_SIGNATURE_PAGE_LIVE groups by segment as well as offer -- collapse to one row per
    # offer, since these tracking fields are offer-grain, before anything keys off CAMPAIGN_OFFER_ID.
    if "CAMPAIGN_OFFER_ID" in rows.columns:
        rows = rows.drop_duplicates(subset="CAMPAIGN_OFFER_ID", keep="first")
    rows["_SORT"] = [ui.segment_sort_rank(s, d) for s, d in
                      zip(rows.get("ACM_SEGMENT", ""), rows.get("SEGMENT_DESCRIPTION", ""))]
    sort_cols = [c for c in ["_SORT", "CREDIT_BUREAU_SCORE", "TEST_TYPE"] if c in rows.columns]
    rows = rows.sort_values(sort_cols).drop(columns="_SORT").reset_index(drop=True)

    current = repository.pre_signature_detail(session, campaign_ids)
    if not current.empty:
        # A prior save may have already left more than one IS_CURRENT row for the same offer --
        # keep the most recent so a read never hands back a Series where a scalar is expected.
        current = current.sort_values("CREATED_TS").drop_duplicates(
            subset="CAMPAIGN_OFFER_ID", keep="last").drop(columns="CREATED_TS")
    current_by_offer = current.set_index("CAMPAIGN_OFFER_ID") if not current.empty else current

    # Each active campaign has its own "previous campaign" (same type, prior month) -- look each up
    # separately and combine, keyed by OFFER_RESERVATION_CODE.
    prior_frames = [repository.previous_pre_signature_detail(session, cid) for cid in campaign_ids]
    prior_frames = [p for p in prior_frames if not p.empty]
    prior = pd.concat(prior_frames, ignore_index=True) if prior_frames else pd.DataFrame()
    prior_by_code = (prior.drop_duplicates(subset="OFFER_RESERVATION_CODE", keep="last")
                      .set_index("OFFER_RESERVATION_CODE")) if not prior.empty else prior

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

    # PROGRAM_CODE's source column may come back as PROGRAM instead, depending on how the view's
    # alias was written in Snowsight -- check both names rather than assuming one.
    PROGRAM_ALIASES = {"PROGRAM_CODE": ("PROGRAM_CODE", "PROGRAM")}

    def _matrix_source(source):
        for candidate in PROGRAM_ALIASES.get(source, (source,)):
            if candidate in rows.columns:
                return rows[candidate]
        return None

    frame = pd.DataFrame(index=rows.index)
    frame[CAMPAIGN_LABEL] = [campaign_type_by_id.get(rows.loc[i, "CAMPAIGN_ID"], "") for i in rows.index]
    for source, label in ui.MATRIX_COLUMNS:
        frame[label] = _matrix_source(source)
    # Matrix segment color as an emoji square, since the editable grid can't show real cell colors.
    if "Segment" in frame.columns:
        def _segment_cell(s, d):
            emoji = ui.segment_color_emoji(s, d)
            return (f"{emoji} " if emoji else "") + _text(s)
        frame["Segment"] = [_segment_cell(s, d) for s, d in
                             zip(rows.get("ACM_SEGMENT", ""), rows.get("SEGMENT_DESCRIPTION", ""))]
    frame[VOL_LABEL] = saved["TOTAL_AVAILABLE_VOLUME"].map(ui.format_volume)
    frame[QTY_LABEL] = [_saved_quantity_display(saved.loc[i, "QUANTITY_PERCENTAGE"],
                                                 saved.loc[i, "QUANTITY_UNITS"]) for i in rows.index]
    frame[OWNER_LABEL] = saved["OWNER_APPROVER"].map(_text)

    st.subheader("Offers")
    locked = campaign["locked"]
    reason = ui.reason_input(f"psp_reason_{campaign['id']}", disabled=locked)
    editable_cols = {VOL_LABEL, QTY_LABEL, OWNER_LABEL}
    edited = st.data_editor(
        frame, hide_index=True, use_container_width=True,
        disabled=[c for c in frame.columns if c not in editable_cols],
        column_config={
            VOL_LABEL: st.column_config.TextColumn(
                VOL_LABEL, help="K/MM shorthand accepted (160k, 2.7mm, 165,000)."),
            QTY_LABEL: st.column_config.TextColumn(
                QTY_LABEL, help="A value ending in % for a percentage of this row's Volume (e.g. 45%), "
                "or a plain number/K/MM for a flat amount (e.g. 160k)."),
            OWNER_LABEL: st.column_config.TextColumn(OWNER_LABEL),
        },
        key=f"psp_editor_{campaign['id']}",
    )

    final_pct, final_units = pd.Series(index=rows.index, dtype=object), pd.Series(index=rows.index, dtype=object)
    over_allocated_errors = []
    for i in rows.index:
        volume = ui.num(edited.loc[i, VOL_LABEL])
        qty_text = _text(edited.loc[i, QTY_LABEL])
        if qty_text == "":
            continue
        is_percent = "%" in qty_text
        pct = ui.parse_percent(qty_text) if is_percent else None
        units = None if is_percent else ui.parse_volume(qty_text)
        if pct is None and units is None:
            continue  # free text -- doesn't consume any of the row's volume, left as typed
        if pct is not None:
            final_pct.loc[i] = ui.format_percent(pct)
            if volume is not None:
                row_units = volume * pct / 100
                final_units.loc[i] = ui.format_volume(row_units)
        else:
            final_units.loc[i] = ui.format_volume(units)
            if volume:
                final_pct.loc[i] = ui.format_percent(units / volume * 100)
        row_units = ui.parse_volume(final_units.loc[i]) if pd.notna(final_units.loc[i]) else None
        if volume is not None and row_units is not None and row_units - volume > OVER_ALLOCATED_TOLERANCE:
            code = rows.loc[i, "OFFER_RESERVATION_CODE"] if "OFFER_RESERVATION_CODE" in rows.columns else i
            over_units = ui.format_volume(row_units - volume)
            over_allocated_errors.append(
                f"**{code}**: Quantity exceeds this row's Volume by {over_units} units.")

    if over_allocated_errors:
        st.error("\n\n".join(over_allocated_errors))

    title = f"PADM Pre Signature Page -- {campaign['name']}"
    subtitle = "Main + Remail combined, as currently shown (includes any unsaved edits)."
    base = f"padm_pre_signature_page_{campaign['reporting_month']}"
    try:
        st.download_button(
            "Export to Excel", exports.to_excel(edited, title, subtitle), f"{base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/table_view:", key=f"psp_export_{campaign['id']}",
        )
    except ImportError:
        st.caption("Excel export needs the openpyxl package.")

    if st.button("Save tracking fields", type="primary", icon=":material/save:",
                  disabled=locked, key=f"psp_save_{campaign['id']}"):
        if ui.require_reason(reason):
            payload = [
                {
                    "CAMPAIGN_ID": rows.loc[i, "CAMPAIGN_ID"],
                    "CAMPAIGN_OFFER_ID": rows.loc[i, "CAMPAIGN_OFFER_ID"],
                    "TOTAL_AVAILABLE_VOLUME": ui.num(edited.loc[i, VOL_LABEL]),
                    "QUANTITY_PERCENTAGE": final_pct.loc[i] if pd.notna(final_pct.loc[i]) else None,
                    "QUANTITY_UNITS": final_units.loc[i] if pd.notna(final_units.loc[i]) else
                        (_text(edited.loc[i, QTY_LABEL]) or None),
                    "OWNER_APPROVER": edited.loc[i, OWNER_LABEL],
                }
                for i in rows.index
            ]
            ui.run_action(SCOPE, lambda: repository.save_pre_signature_detail(
                session, payload, reason.strip()))
