"""Tab 6 -- Segment Viewer (spec 7): Excel-style Tier x Times Mailed selection and calculation
grids for one segment, CDE upload, segment-level inputs, Working | Final Version toggle."""

import io

import pandas as pd
import streamlit as st

from padm import formulas, repository, ui, validation
from padm.formulas import TIMES_MAILED_BUCKETS

SCOPE = "segment_viewer"
# Selection grid cell colors (priority: BLUE > GREEN > YELLOW -- an unsaved edit always wins over
# a saved or prior-matched state, since that's the most actionable thing to notice):
#   BLUE   = this cell differs from what's currently saved (DM_PADM_SELECTION_WORKING) -- unsaved.
#   GREEN  = this cell matches what's currently saved and is non-zero.
#   YELLOW = prior campaign's selection was non-zero here, but neither of the above applies.
YELLOW = "background-color: #fff3b0"
GREEN = "background-color: #c6f6c6"
BLUE = "background-color: #bfdbfe"
VERSIONS = ["Working Version", "Final Version"]

# ---------------------------------------------------------------------------------------------
# CDE file parsing (CSV or Excel, pivoted like Segment.xlsx)
# ---------------------------------------------------------------------------------------------

def _bucket(label):
    s = str(label).strip()
    if s.upper().replace(" ", "") in ("9+", "9PLUS", "9_PLUS"):
        return "9+"
    try:
        n = int(float(s))
    except ValueError:
        return s
    return "9+" if n >= 9 else str(n)


def _is_total(label):
    return str(label).strip().lower() in ("total", "grand total")


def parse_cde_file(raw_bytes, file_name):
    """First column = TRM10 tier (1-20); other headers = Times Mailed 0-8 / 9+; values = Count
    Distinct EPIN. Total rows/columns are ignored. Returns (valid cells, warnings, total cells)."""
    if file_name.lower().endswith((".xlsx", ".xls")):
        wide = pd.read_excel(io.BytesIO(raw_bytes))
    else:
        wide = pd.read_csv(io.BytesIO(raw_bytes))
    wide = wide.rename(columns={wide.columns[0]: "TRM10_TIER"})
    wide = wide[~wide["TRM10_TIER"].map(_is_total)]
    value_cols = [c for c in wide.columns if c != "TRM10_TIER" and not _is_total(c)]
    cells = wide.melt(id_vars=["TRM10_TIER"], value_vars=value_cols, var_name="TIMES_MAILED_BUCKET",
                       value_name="DISTINCT_EPIN_COUNT")
    cells["TIMES_MAILED_BUCKET"] = cells["TIMES_MAILED_BUCKET"].map(_bucket)
    cells["TRM10_TIER"] = pd.to_numeric(cells["TRM10_TIER"], errors="coerce")
    cells["DISTINCT_EPIN_COUNT"] = pd.to_numeric(
        cells["DISTINCT_EPIN_COUNT"].astype(str).str.replace(",", "", regex=False), errors="coerce").fillna(0)
    cells = cells.groupby(["TRM10_TIER", "TIMES_MAILED_BUCKET"], as_index=False)["DISTINCT_EPIN_COUNT"].sum()
    total = len(cells)
    ok_tier = cells["TRM10_TIER"].between(1, 20) & (cells["TRM10_TIER"] % 1 == 0)
    ok_bucket = cells["TIMES_MAILED_BUCKET"].isin(TIMES_MAILED_BUCKETS)
    ok_volume = cells["DISTINCT_EPIN_COUNT"] >= 0
    warnings = []
    if (~ok_tier).any():
        warnings.append(f"{int((~ok_tier).sum())} cell(s) with a tier outside 1-20 were dropped.")
    if (~ok_bucket).any():
        warnings.append(f"{int((~ok_bucket).sum())} cell(s) with an unknown Times Mailed column were dropped.")
    if (~ok_volume).any():
        warnings.append(f"{int((~ok_volume).sum())} cell(s) with a negative volume were dropped.")
    valid = cells[ok_tier & ok_bucket & ok_volume].copy()
    valid["TRM10_TIER"] = valid["TRM10_TIER"].astype(int)
    return valid, warnings, total

# ---------------------------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------------------------

def _segment_inputs(session, campaign, segment_id):
    """Rate Adjustment, Seasonality, Unwind Rate Adjustment, Unit Cost, CPP (spec 7.7).

    Prepopulated from the campaign's latest assumptions for any field that has a campaign-level
    counterpart (CPP, Unit Cost) -- shown as the starting value, still editable/overridable per
    segment. Fields with no campaign-level column at all
    (Rate Adjustment, Seasonality, Unwind Rate Adjustment -- segment-only by schema design) have
    nothing to inherit, so they still start blank."""
    definitions = repository.assumption_definitions(session)
    defs = definitions[definitions["SEGMENT_COLUMN"].notna() & definitions["ENTERED_ON"].isin(["SEGMENT_VIEWER", "BOTH"])
                        & (definitions["ASSUMPTION_LEVEL"] != "CAMPAIGN")]
    carried = definitions[definitions["SEGMENT_COLUMN"].notna() & ~definitions["ASSUMPTION_CODE"].isin(defs["ASSUMPTION_CODE"])]
    current = repository.segment_assumption_current(session, campaign["id"], segment_id)
    version = int(current.iloc[0]["VERSION_NUMBER"]) if not current.empty else 0
    stored = current.iloc[0].to_dict() if not current.empty else {}
    campaign_current = repository.campaign_assumption_current(session, campaign["id"])
    campaign_values = campaign_current.iloc[0].to_dict() if not campaign_current.empty else {}
    locked = campaign["locked"]

    with st.container(border=True):
        st.markdown("**Segment-level inputs**")
        st.caption("Prepopulated from the campaign's latest assumptions where a campaign-level value exists; "
                   "still editable here as a segment-specific override.")
        values, errors = {}, []
        for col, (_, d) in zip(st.columns(len(defs)), defs.iterrows()):
            code = d["ASSUMPTION_CODE"]
            suffix = validation.unit_suffix(d)
            segment_value = stored.get(d["SEGMENT_COLUMN"])
            campaign_column = d.get("CAMPAIGN_COLUMN")
            # validation.num() (not a bare `is not None` check) because a NULL segment override
            # comes back from stored.to_dict() as NaN, not None -- `NaN is not None` is True, so
            # the old check locked onto NaN and never fell back to the campaign value, confirmed
            # live: CPP went permanently blank here after the first segment-level save.
            default = segment_value if ui.num(segment_value) is not None else (
                campaign_values.get(campaign_column) if campaign_column else None)
            values[code] = col.number_input(
                f"{d['ASSUMPTION_LABEL']}{' (' + suffix + ')' if suffix else ''}",
                value=validation.to_display(d, default),
                step=validation.input_step(d), format=validation.input_format(d), placeholder="inherit / 0",
                help=f"{int(d['DECIMALS'])} decimals{', can be negative' if d['ALLOW_NEGATIVE'] else ', ≥ 0'}",
                disabled=locked, key=f"sv_in_{campaign['id']}_{segment_id}_{version}_{code}",
            )
            error = validation.validate(d, values[code])
            if error:
                errors.append(error)
        for error in errors:
            st.error(error)
        with st.container(horizontal=True, vertical_alignment="bottom"):
            reason = ui.reason_input(f"sv_in_reason_{campaign['id']}_{segment_id}", disabled=locked)
            if st.button("Save segment inputs", type="primary", icon=":material/save:", disabled=locked or bool(errors),
                          key=f"sv_in_save_{campaign['id']}_{segment_id}"):
                if ui.require_reason(reason):
                    payload = {d["ASSUMPTION_CODE"]: validation.to_stored(d, values[d["ASSUMPTION_CODE"]]) for _, d in defs.iterrows()}
                    payload.update({d["ASSUMPTION_CODE"]: ui.num(stored.get(d["SEGMENT_COLUMN"])) for _, d in carried.iterrows()})
                    ui.run_action(SCOPE, lambda: repository.save_segment_assumption(
                        session, campaign["id"], segment_id, payload, version, reason.strip()))


def _cde_section(session, campaign, segment):
    segment_id = segment["SEGMENT_ID"]
    active = repository.active_cde_batch(session, campaign["id"], segment_id)
    if not active.empty:
        row = active.iloc[0]
        st.success(f"CDE values are available -- version {row['VERSION_NUMBER']} ({row['SOURCE_FILE_NAME']}, "
                   f"{row['LOADED_ROW_COUNT']} cells), activated by {row['ACTIVATED_BY']} at {row['ACTIVATED_TS']}.",
                   icon=":material/check_circle:")
    with st.expander("Upload CDE volume (CSV / Excel)" if active.empty else "Load a new CDE version",
                      expanded=active.empty and not campaign["locked"]):
        st.caption("Stored in DM_PADM_CDE_LOAD_BATCH / DM_PADM_CDE_DETAIL (same tables for every campaign). "
                   "Layout: first column = TRM10 tier (1-20), other headers = Times Mailed 0-8 / 9+, values = Count Distinct EPIN.")
        uploaded = st.file_uploader("CDE file", type=["csv", "xlsx", "xls"], disabled=campaign["locked"],
                                     key=f"sv_cde_{campaign['id']}_{segment_id}")
        if uploaded is None:
            return
        raw = uploaded.getvalue()
        try:
            cells, warnings, total = parse_cde_file(raw, uploaded.name)
        except Exception as exc:
            st.error(f"Could not read this file: {exc}")
            return
        for warning in warnings:
            st.warning(warning)
        if cells.empty:
            st.error("No valid cells in this file.")
            return
        preview = cells.pivot_table(index="TRM10_TIER", columns="TIMES_MAILED_BUCKET", values="DISTINCT_EPIN_COUNT", aggfunc="sum", fill_value=0)
        st.dataframe(preview[[c for c in TIMES_MAILED_BUCKETS if c in preview.columns]], use_container_width=False)
        st.caption(f"{len(cells)} of {total} cell(s) valid · total volume {cells['DISTINCT_EPIN_COUNT'].sum():,.0f}")
        band = f"{int(segment['SCORE_MIN'])}_{int(segment['SCORE_MAX'])}"
        reason = ui.reason_input(f"sv_cde_reason_{campaign['id']}_{segment_id}")
        if st.button("Load and activate CDE version", type="primary", icon=":material/upload:",
                      key=f"sv_cde_go_{campaign['id']}_{segment_id}"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.load_cde_version(
                    session, campaign["id"], segment_id, raw, uploaded.name, band, cells, total, reason.strip()),
                    lambda result: f"{result[0]} {result[1]} selection cell(s) initialized.")


def _pivot_pct(frame, value_col="SELECTION_PERCENTAGE"):
    if frame.empty:
        return pd.DataFrame()
    frame = frame.copy()
    frame["TIMES_MAILED_BUCKET"] = frame["TIMES_MAILED_BUCKET"].astype(str)
    grid = frame.pivot_table(index="RESPONSE_MODEL_TIER", columns="TIMES_MAILED_BUCKET", values=value_col, aggfunc="max")
    grid = grid.reindex(columns=[c for c in TIMES_MAILED_BUCKETS if c in grid.columns]).sort_index() * 100
    grid.index = grid.index.astype(int)
    grid.index.name = "Tier"
    return grid.round(2)


def _selection_section(session, campaign, segment_id):
    """Selection % input grid (spec 7.3) + Save Selections (spec 7.4). Returns pending change count."""
    cid, locked = campaign["id"], campaign["locked"]
    working = repository.selection_working(session, cid, segment_id)
    st.markdown("**1. Selection % (input)**")
    st.caption(formulas.SELECTION_GRID_CAPTION)
    if working.empty:
        st.info("Upload CDE volume for this segment to create the selection grid.")
        return 0

    base = _pivot_pct(working)
    prior = repository.prior_selection(session, cid, segment_id)
    prior_grid = _pivot_pct(prior).reindex_like(base).fillna(0) if not prior.empty else base * 0
    if prior.empty:
        st.info("No prior month selection -- the grid starts at zero.", icon=":material/info:")
    else:
        st.caption(f"Prepopulated from {prior.iloc[0]['CAMPAIGN_DISPLAY_NAME']}.")
    st.caption("🟦 Blue = unsaved change · 🟩 Green = currently saved · 🟨 Yellow = prior campaign had a selection here")

    signature = int(working["ROW_VERSION"].sum())
    state_key = f"sv_sel_{cid}_{segment_id}"
    state = st.session_state.get(state_key)
    if state is None or state["signature"] != signature:
        state = {"signature": signature, "grid": base.fillna(0), "actions": [], "nonce": 0}
        st.session_state[state_key] = state

    edited = st.data_editor(
        state["grid"], key=f"sv_editor_{cid}_{segment_id}_{state['nonce']}", disabled=locked,
        height=ui.grid_height(state["grid"]), use_container_width=False,
        column_config={c: st.column_config.NumberColumn(c, min_value=0.0, max_value=100.0, step=0.01, format="%.2f%%")
                       for c in state["grid"].columns},
    )
    if not edited.fillna(0).equals(state["grid"]):
        changed = int((edited.fillna(0) != state["grid"]).values.sum())
        state["actions"].append({"ACTION_TYPE": "CELL_EDIT", "CHANGED_CELL_COUNT": changed})
        state["grid"] = edited.fillna(0)

    # Excel-like range tools (true click-drag fill is not available in st.data_editor).
    tiers, buckets = list(state["grid"].index), list(state["grid"].columns)
    with st.expander("Apply % to range / fill rows or columns / clear", expanded=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        tier_from = c1.selectbox("Tier from", tiers, key=f"sv_rt1_{cid}_{segment_id}", disabled=locked)
        tier_to = c2.selectbox("Tier to", tiers, index=len(tiers) - 1, key=f"sv_rt2_{cid}_{segment_id}", disabled=locked)
        tm_from = c3.selectbox("Times Mailed from", buckets, key=f"sv_rm1_{cid}_{segment_id}", disabled=locked)
        tm_to = c4.selectbox("Times Mailed to", buckets, index=len(buckets) - 1, key=f"sv_rm2_{cid}_{segment_id}", disabled=locked)
        pct = c5.number_input("Selection %", min_value=0.0, max_value=100.0, value=100.0, step=0.01,
                               key=f"sv_rp_{cid}_{segment_id}", disabled=locked)
        st.caption("Whole row(s): choose the tier range with Times Mailed from first to last column. Whole column(s): "
                   "the reverse. Multi-cell copy/paste works directly in the grid.")

        def apply(value, action):
            lo_t, hi_t = sorted((tiers.index(tier_from), tiers.index(tier_to)))
            lo_b, hi_b = sorted((buckets.index(tm_from), buckets.index(tm_to)))
            rows, cols = tiers[lo_t:hi_t + 1], buckets[lo_b:hi_b + 1]
            state["grid"].loc[rows, cols] = round(value, 2)
            state["actions"].append({"ACTION_TYPE": action, "TIER_FROM": int(rows[0]), "TIER_TO": int(rows[-1]),
                                       "TIMES_MAILED_FROM": cols[0], "TIMES_MAILED_TO": cols[-1],
                                       "ENTERED_PERCENTAGE": value / 100, "CHANGED_CELL_COUNT": len(rows) * len(cols)})
            state["nonce"] += 1
            st.rerun()

        b1, b2, b3 = st.columns(3)
        if b1.button("Apply % to range", disabled=locked, key=f"sv_apply_{cid}_{segment_id}"):
            apply(pct, "RANGE_APPLY")
        if b2.button("Clear range (set 0%)", disabled=locked, key=f"sv_clear_{cid}_{segment_id}"):
            apply(0.0, "RANGE_CLEAR")
        if b3.button("Discard unsaved edits", disabled=locked, key=f"sv_discard_{cid}_{segment_id}"):
            st.session_state.pop(state_key, None)
            st.rerun()

    # Styled read-only copy (cell styling isn't available in st.data_editor itself). Priority:
    # unsaved change (blue) > currently saved, non-zero (green) > prior campaign had a selection
    # here (yellow). base = what's actually saved right now; state["grid"] = the grid as shown,
    # including any not-yet-saved edits.
    base_aligned = base.reindex_like(state["grid"]).fillna(0)
    is_unsaved = (state["grid"] - base_aligned).abs() > 1e-9
    is_saved_nonzero = (~is_unsaved) & (base_aligned > 0)
    is_prior_only = (~is_unsaved) & (~is_saved_nonzero) & (prior_grid.reindex_like(state["grid"]).fillna(0) > 0)
    highlight = pd.DataFrame("", index=state["grid"].index, columns=state["grid"].columns)
    highlight[is_prior_only] = YELLOW
    highlight[is_saved_nonzero] = GREEN
    highlight[is_unsaved] = BLUE
    st.dataframe(state["grid"].style.format("{:.2f}%").apply(lambda _: highlight, axis=None),
                 height=ui.grid_height(state["grid"]), key=f"sv_sel_view_{cid}_{segment_id}", use_container_width=False)

    # Diff against the stored working grid.
    lookup = working.assign(TIMES_MAILED_BUCKET=working["TIMES_MAILED_BUCKET"].astype(str)) \
        .set_index(["RESPONSE_MODEL_TIER", "TIMES_MAILED_BUCKET"])
    changes = []
    for tier in state["grid"].index:
        for bucket in state["grid"].columns:
            if (tier, bucket) not in lookup.index:
                continue
            try:
                new = validation.selection_percent(state["grid"].loc[tier, bucket]) / 100
            except ValueError as exc:
                st.error(str(exc))
                return 0
            old = float(lookup.loc[(tier, bucket), "SELECTION_PERCENTAGE"])
            if abs(new - old) > 1e-9:
                changes.append((int(tier), bucket, new, int(lookup.loc[(tier, bucket), "ROW_VERSION"]), old))

    with st.container(horizontal=True, vertical_alignment="bottom"):
        reason = ui.reason_input(f"sv_sel_reason_{cid}_{segment_id}", disabled=locked)
        if st.button(f"Save Selections ({len(changes)} changed)", type="primary", icon=":material/save:",
                      disabled=locked or not changes, key=f"sv_sel_save_{cid}_{segment_id}"):
            if ui.require_reason(reason):
                ui.run_action(SCOPE, lambda: repository.save_selections(
                    session, cid, segment_id, changes, state["actions"], reason.strip()),
                    on_success=lambda _: st.session_state.pop(state_key, None))
    with st.expander("Selection audit log (one row per action)"):
        log = repository.selection_history(session, cid, segment_id)
        st.dataframe(log, hide_index=True) if not log.empty else st.caption("No selection events yet.")
    return len(changes)


def _calculated_grids(session, campaign, segment_id, version, pending):
    cells = repository.segment_calculation(session, campaign["id"], segment_id)
    if cells.empty:
        st.info("Calculated grids appear once CDE volume is loaded for this segment.")
        return
    if pending:
        st.caption(f":orange[{pending} unsaved selection change(s) are not in these grids yet -- Save Selections.]")

    selected_quantity = None
    if version == "Final Version":
        mail = repository.mailfile_cells(session, campaign["id"], segment_id)
        if mail.empty:
            st.warning("No mail-file selections (T_EXPERIAN_MAILFILE / T_TRANSUNION_MAILFILE via DM_PADM_MAILFILE_CELL) "
                       "are loaded for this segment yet -- showing the Working Version.")
        else:
            key = ["RESPONSE_MODEL_TIER", "TIMES_MAILED_BUCKET"]
            mail["TIMES_MAILED_BUCKET"] = mail["TIMES_MAILED_BUCKET"].astype(str)
            cells["TIMES_MAILED_BUCKET"] = cells["TIMES_MAILED_BUCKET"].astype(str)
            cells = cells.merge(mail[key + ["MAIL_QUANTITY"]], on=key, how="left")
            selected_quantity = cells["MAIL_QUANTITY"].fillna(0)
            st.caption(f"Final Version: Selections from the {mail['SOURCE_NAME'].iloc[0]} mail file; all other rows unchanged.")
    calc = formulas.calculate(cells, selected_quantity=selected_quantity)

    sources = ", ".join(f"{c.split('_')[0]}: {', '.join(sorted(cells[c].dropna().astype(str).unique())) or '–'}"
                         for c in ("NRR_SOURCE", "UNWIND_SOURCE", "EMS_SOURCE") if c in cells.columns)
    st.caption(f"Fallback sources used -- {sources}. Totals for rates and CPAs are weighted (Σ numerator / Σ denominator).")

    has_cpp = calc["EFFECTIVE_CPP"].notna().any() if "EFFECTIVE_CPP" in calc else False
    has_nrr = calc["BASE_NRR"].notna().any() if "BASE_NRR" in calc else False
    has_unit = calc["EFFECTIVE_UNIT_COST"].notna().any() if "EFFECTIVE_UNIT_COST" in calc else False
    has_hist_unwind = calc["HISTORICAL_UNWIND_RATE"].notna().any() if "HISTORICAL_UNWIND_RATE" in calc else False
    needs = {
        "base_nrr": (has_nrr, "No historical NRR and no NBR assumption."),
        "eff_nrr": (has_nrr, "Requires Base NRR."),
        "selected_nrr": (has_nrr, "Requires Effective NRR."),
        "hist_unwind": (has_hist_unwind, "No historical unwind rate and no Unwind Rate assumption."),
        "booked_pre": (has_nrr, "Requires Effective NRR."),
        "booked_pre_universe": (has_nrr, "Requires Effective NRR."),
        "eff_unwind": (has_hist_unwind, "No historical unwind rate and no Unwind Rate assumption."),
        "unwinds": (has_nrr, "Requires Booked Pre-Unwind."),
        "unwinds_universe": (has_nrr, "Requires Booked Pre-Unwind."),
        "booked_post": (has_nrr, "Requires Booked Pre-Unwind."),
        "booked_post_universe": (has_nrr, "Requires Booked Pre-Unwind."),
        "marketing": (has_cpp, "Requires CPP (Campaign Assumptions / Signature Page)."),
        "marketing_universe": (has_cpp, "Requires CPP (Campaign Assumptions / Signature Page)."),
        "booking": (has_nrr and has_unit, "Requires Booked Pre-Unwind and Unit Cost."),
        "booking_universe": (has_nrr and has_unit, "Requires Booked Pre-Unwind and Unit Cost."),
        "pre_cpa": (has_cpp and has_nrr, "Requires Marketing Cost and Booked Pre-Unwind."),
        "pre_cpa_universe": (has_cpp and has_nrr, "Requires Marketing Cost and Booked Pre-Unwind."),
        "post_cpa": (has_cpp and has_nrr and has_unit, "Requires Marketing Cost, Booking Cost and Booked Post-Unwind."),
        "post_cpa_universe": (has_cpp and has_nrr and has_unit, "Requires Marketing Cost, Booking Cost and Booked Post-Unwind."),
    }
    by_key = {g[0]: g for g in formulas.GRIDS}
    extra_rows = {
        "booked_post": ("EXPECTED_UNWINDS_SELECTED", "BOOKED_PRE_UNWIND_SELECTED"),
        "booked_post_universe": ("EXPECTED_UNWINDS_UNIVERSE", "BOOKED_PRE_UNWIND_UNIVERSE"),
    }
    # Side-by-side rows, matching the real Segment.xlsx alignment. Each grid renders at its
    # natural full width (no per-grid horizontal scrollbar); the CSS below lets the row's
    # st.columns block overflow instead of clipping each column to an equal share of the page,
    # so the whole row shares ONE horizontal scrollbar. Vertical scroll stays per-grid (fixed
    # height via ui.render_grid / grid_height, so it only ever triggers if a grid is unusually
    # tall).
    st.markdown("""
    <style>
    div[class*="st-key-grid_row_"] > div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden;
    }
    div[class*="st-key-grid_row_"] div[data-testid="column"] {
        width: auto !important; min-width: auto !important; flex: 0 0 auto !important;
    }
    </style>
    """, unsafe_allow_html=True)
    for row_number, row_keys in enumerate(formulas.GRID_ROWS, start=2):
        st.markdown(f"**{row_number}. {' / '.join(by_key[k][1] for k in row_keys)}**")
        row_container = st.container(key=f"grid_row_{row_number}")
        cols = row_container.columns(len(row_keys))
        for col, key in zip(cols, row_keys):
            _, title, column, fmt, caption, ratio = by_key[key]
            ok, why = needs.get(key, (True, ""))
            with col:
                if not ok:
                    with st.container(border=True):
                        st.markdown(f"**{title}**")
                        st.caption(caption)
                        st.caption(f":orange[Not calculated yet -- {why}]")
                    continue
                extra = None
                if key in extra_rows:
                    num_col, den_col = extra_rows[key]
                    unwinds = formulas.pivot_grid(calc, num_col).loc["Total"]
                    pre = formulas.pivot_grid(calc, den_col).loc["Total"]
                    extra = ("Unwind Rate", formulas.safe_div(unwinds, pre), "percent")
                ui.render_grid(calc, title, column, fmt, caption, ratio=ratio, extra_row=extra,
                                key=f"sv_grid_{key}_{campaign['id']}_{segment_id}")

    t = formulas.totals(calc)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected Quantity", f"{t['SELECTED_QUANTITY']:,.0f}", border=True)
    c2.metric("Booked Post-Unwind", f"{t['BOOKED_POST_UNWIND_SELECTED']:,.1f}", border=True)
    c3.metric("Pre-Unwind CPA", "–" if pd.isna(t["PRE_UNWIND_CPA"]) else f"${t['PRE_UNWIND_CPA']:,.2f}", border=True)
    c4.metric("Post-Unwind CPA", "–" if pd.isna(t["POST_UNWIND_CPA"]) else f"${t['POST_UNWIND_CPA']:,.2f}", border=True)


def render(session):
    st.header("Segment Viewer")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    segments = repository.campaign_segments(session, campaign["id"])
    if segments.empty:
        st.info("No segments on this campaign yet (Create Segment tab).")
        return
    by_id = segments.set_index("SEGMENT_ID")
    segment_id = st.selectbox("Segment", segments["SEGMENT_ID"].tolist(),
                               format_func=lambda s: by_id.loc[s, "SEGMENT_NAME"], key=f"sv_segment_{campaign['id']}")
    segment = by_id.loc[segment_id].to_dict() | {"SEGMENT_ID": segment_id}
    mla = " MLA" if str(segment.get("MLA_FLAG") or "").upper() in ("Y", "YES", "TRUE", "MLA") else ""
    tier_model = segment.get("TIER_MODEL") if isinstance(segment.get("TIER_MODEL"), str) else "TRM10"
    st.subheader(f"{segment['SEGMENT_NAME']}{mla} / {tier_model}")

    if not campaign["locked"] and not repository.active_cde_batch(session, campaign["id"], segment_id).empty:
        try:
            repository.ensure_working_grid(session, campaign["id"], segment_id)
        except Exception as exc:
            st.error(f"Could not initialize the selection grid: {exc}")

    version = st.segmented_control("Volume source", VERSIONS, default=VERSIONS[0], key=f"sv_version_{campaign['id']}",
                                    help="Working Version = MKU/CDE x selection %. Final Version = selections from the mail file.") \
        or VERSIONS[0]

    _segment_inputs(session, campaign, segment_id)
    _cde_section(session, campaign, segment)
    st.divider()
    # RESOLVED: _selection_section's own def (3 params, read directly above) never references
    # `version` in its body -- confirms the 5-arg call was this transcription's OCR error
    # (bled in from the next line's _calculated_grids call), not a bug in the real code.
    pending = _selection_section(session, campaign, segment_id)
    _calculated_grids(session, campaign, segment_id, version, pending)

    st.divider()
    latest = repository.latest_calculation_run(session, campaign["id"])
    if not latest.empty:
        st.caption(f"Latest run: {latest.iloc[0]['CALCULATION_STATUS']} at {latest.iloc[0]['CALCULATION_COMPLETED_TS']}")

