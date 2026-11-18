import io

import pandas as pd
import streamlit as st

from app import queries, repository, ui
from app.pages._shared import highlight_nonzero_yellow, pivot_grid, require_campaign

TIMES_MAILED_BUCKETS = [str(i) for i in range(9)] + ["9+"]


def _normalize_bucket(label):
    s = str(label).strip()
    if s.upper().replace(" ", "") in ("9+", "9PLUS", "9_PLUS"):
        return "9+"
    try:
        n = int(float(s))
    except ValueError:
        return s
    return "9+" if n >= 9 else str(n)


def _parse_cde_csv(raw_bytes):
    """Pivoted CSV: col 0 is TRM10 tier (1-20), remaining headers are Times Mailed buckets."""
    wide = pd.read_csv(io.BytesIO(raw_bytes))
    index_col = wide.columns[0]
    wide = wide.rename(columns={index_col: "TRM10_TIER"})
    wide = wide[~wide["TRM10_TIER"].astype(str).str.strip().str.lower().isin(["total", "grand total"])]

    value_cols = [c for c in wide.columns if c != "TRM10_TIER" and str(c).strip().lower() not in ("total", "grand total")]
    long_df = wide.melt(id_vars=["TRM10_TIER"], value_vars=value_cols, var_name="TIMES_MAILED_BUCKET", value_name="DISTINCT_EPIN_COUNT")
    long_df["TIMES_MAILED_BUCKET"] = long_df["TIMES_MAILED_BUCKET"].apply(_normalize_bucket)
    long_df["TRM10_TIER"] = pd.to_numeric(long_df["TRM10_TIER"], errors="coerce")
    long_df["DISTINCT_EPIN_COUNT"] = pd.to_numeric(long_df["DISTINCT_EPIN_COUNT"], errors="coerce").fillna(0)
    long_df = long_df.groupby(["TRM10_TIER", "TIMES_MAILED_BUCKET"], as_index=False)["DISTINCT_EPIN_COUNT"].sum()

    total_rows = len(long_df)
    errors = []
    bad_tier = long_df[~long_df["TRM10_TIER"].between(1, 20)]
    if not bad_tier.empty:
        errors.append(f"{len(bad_tier)} row(s) have a TRM10 tier outside 1-20 and were dropped.")
    bad_bucket = long_df[~long_df["TIMES_MAILED_BUCKET"].isin(TIMES_MAILED_BUCKETS)]
    if not bad_bucket.empty:
        errors.append(
            f"{len(bad_bucket)} row(s) have an unrecognized Times Mailed column "
            f"({sorted(bad_bucket['TIMES_MAILED_BUCKET'].unique())}) and were dropped."
        )
    bad_volume = long_df[long_df["DISTINCT_EPIN_COUNT"] < 0]
    if not bad_volume.empty:
        errors.append(f"{len(bad_volume)} row(s) have a negative volume and were dropped.")

    valid = long_df[
        long_df["TRM10_TIER"].between(1, 20)
        & long_df["TIMES_MAILED_BUCKET"].isin(TIMES_MAILED_BUCKETS)
        & (long_df["DISTINCT_EPIN_COUNT"] >= 0)
    ]
    return valid, errors, total_rows


def _segment_assumptions_section(session, campaign_id, segment_id):
    """Segment-level assumption overrides, at the top of the page: changing these (or the
    selection % grid below) is what drives every calculated grid further down, since they all
    read VW_PADM_SEGMENT_CALCULATION_CURRENT, a live view, not a snapshot."""
    ui.section_title("Segment Assumptions")
    st.caption("Overrides the campaign-level assumption for this segment only. Leave a field at 0 to inherit it.")

    seg_current = queries.segment_assumption_current(session, campaign_id)
    seg_row = seg_current[seg_current["SEGMENT_ID"] == segment_id]
    seg_row = seg_row.iloc[0] if not seg_row.empty else None

    with st.form(f"segment_assumption_form_{segment_id}"):
        c1, c2, c3 = st.columns(3)
        s_cpp = c1.number_input("CPP Override", value=float(seg_row["CPP_OVERRIDE"]) if seg_row is not None and seg_row["CPP_OVERRIDE"] is not None else 0.0, step=0.01, format="%.4f")
        s_unit_cost = c2.number_input("Unit Cost Override", value=float(seg_row["UNIT_COST_OVERRIDE"]) if seg_row is not None and seg_row["UNIT_COST_OVERRIDE"] is not None else 0.0, step=0.01, format="%.4f")
        s_rate = c3.number_input("Rate Adjustment Override", value=float(seg_row["RATE_ADJUSTMENT_OVERRIDE"]) if seg_row is not None and seg_row["RATE_ADJUSTMENT_OVERRIDE"] is not None else 0.0, step=0.01, format="%.4f")
        c4, c5 = st.columns(2)
        s_season = c4.slider("Seasonality Reduction Override", 0.0, 1.0, float(seg_row["SEASONALITY_REDUCTION_OVERRIDE"]) if seg_row is not None and seg_row["SEASONALITY_REDUCTION_OVERRIDE"] is not None else 0.0)
        s_unwind = c5.number_input("Unwind Rate Adjustment Override", value=float(seg_row["UNWIND_RATE_ADJUSTMENT_OVERRIDE"]) if seg_row is not None and seg_row["UNWIND_RATE_ADJUSTMENT_OVERRIDE"] is not None else 0.0, step=0.01, format="%.4f")
        seg_reason = st.text_input("Change reason (required)", key=f"segment_reason_{segment_id}")
        seg_submitted = st.form_submit_button("Save segment assumptions")

    if seg_submitted:
        if not seg_reason.strip():
            st.error("A change reason is required.")
        else:
            result = repository.save_segment_assumption(
                session, campaign_id, segment_id,
                s_cpp or None, s_unit_cost or None, s_rate or None, s_season or None, s_unwind or None,
                seg_reason,
            )
            st.success(result)
            st.rerun()


def _upload_cde_section(session, campaign_id, segment_id):
    with st.expander("Upload CDE grid (CSV)", expanded=False):
        active = queries.active_cde_batch(session, campaign_id, segment_id)
        if not active.empty:
            row = active.iloc[0]
            ui.chips(
                f"Active v{row['VERSION_NUMBER']}",
                f"{row['SOURCE_FILE_NAME']}",
                f"{row['SOURCE_ROW_COUNT']} rows",
                f"by {row['ACTIVATED_BY']} at {row['ACTIVATED_TS']}",
            )
        else:
            st.caption("No active CDE version for this segment yet.")

        st.caption(
            "CSV pivoted the same way as the Segment.xlsx workbook: first column is the TRM10 tier (1-20), "
            "remaining column headers are Times Mailed buckets (0-8, 9+), values are Count Distinct of EPIN. "
            "'Total'/'Grand Total' rows or columns are ignored automatically."
        )
        uploaded = st.file_uploader("CDE grid CSV", type=["csv"], key=f"cde_upload_{segment_id}")
        if uploaded is None:
            return

        raw_bytes = uploaded.getvalue()
        valid, errors, total_rows = _parse_cde_csv(raw_bytes)
        for message in errors:
            st.warning(message)
        if valid.empty:
            st.error("No valid rows parsed from this file.")
            return

        preview = valid.pivot_table(index="TRM10_TIER", columns="TIMES_MAILED_BUCKET", values="DISTINCT_EPIN_COUNT", fill_value=0)
        ordered_cols = [c for c in TIMES_MAILED_BUCKETS if c in preview.columns]
        st.dataframe(preview[ordered_cols], use_container_width=True)
        st.caption(f"Parsed {len(valid)} of {total_rows} cell(s). Total volume: {valid['DISTINCT_EPIN_COUNT'].sum():,.0f}")

        score_band_df = queries.segment_score_band(session, segment_id)
        default_band = ""
        if not score_band_df.empty and score_band_df.iloc[0]["SCORE_MIN"] is not None and score_band_df.iloc[0]["SCORE_MAX"] is not None:
            row = score_band_df.iloc[0]
            default_band = f"{int(row['SCORE_MIN'])}_{int(row['SCORE_MAX'])}"
        score_band = st.text_input(
            "Vantage score band for this segment (e.g. 550_600)",
            value=default_band,
            key=f"cde_band_{segment_id}",
        )
        reason = st.text_input("Reason for this CDE load (required)", key=f"cde_reason_{segment_id}")

        if st.button("Load & activate this CDE version", key=f"cde_commit_{segment_id}"):
            if not reason.strip():
                st.error("A change reason is required.")
            elif not score_band.strip():
                st.error("A Vantage score band is required.")
            else:
                next_version, result = repository.load_cde_version(
                    session, campaign_id, segment_id, raw_bytes, uploaded.name, score_band, valid, total_rows, reason,
                )
                st.success(result or f"CDE version {next_version} loaded and activated ({len(valid)} cells).")
                st.caption(
                    "Note: if selections were already saved against a prior CDE version for this segment, "
                    "review the Selection grid below -- new tiers/buckets get added but existing selection "
                    "cells are not automatically reconciled against the new volume."
                )
                st.rerun()


def render(session):
    campaign_id = require_campaign()

    campaign = queries.campaign_header(session, campaign_id)
    if not campaign.empty:
        ui.campaign_banner(
            campaign.iloc[0]["CAMPAIGN_DISPLAY_NAME"],
            campaign.iloc[0]["STATUS"],
            subtitle="Segment Viewer -- CDE volume, selection %, and downstream calculation grids",
        )

    segments = queries.campaign_segments(session, campaign_id)
    if segments.empty:
        st.info("No segments created yet for this campaign. Create one on the Create Segment tab.")
        return

    segment_id = st.selectbox(
        "Segment",
        options=segments["SEGMENT_ID"].tolist(),
        format_func=lambda sid: segments.loc[segments["SEGMENT_ID"] == sid, "SEGMENT_NAME"].iloc[0],
    )

    _segment_assumptions_section(session, campaign_id, segment_id)
    st.divider()
    _upload_cde_section(session, campaign_id, segment_id)

    working = repository.ensure_working_grid_initialized(session, campaign_id, segment_id)
    if working.empty:
        st.warning("No CDE volume loaded yet for this campaign/segment -- upload a CDE grid above first.")
        return

    ui.section_title("1. Selection % (editable)")
    st.caption("Pre-populated from the prior campaign's saved selection where available. Only non-zero cells are highlighted.")
    selection_pivot = working.pivot_table(
        index="RESPONSE_MODEL_TIER", columns="TIMES_MAILED_BUCKET", values="SELECTION_PERCENTAGE", fill_value=0
    )
    ordered_cols = [c for c in TIMES_MAILED_BUCKETS if c in selection_pivot.columns]
    selection_pivot = selection_pivot[ordered_cols]

    edited = st.data_editor(
        selection_pivot,
        use_container_width=True,
        key="selection_editor",
        column_config={c: st.column_config.NumberColumn(c, min_value=0.0, max_value=1.0, step=0.01, format="%.4f") for c in ordered_cols},
    )

    st.dataframe(selection_pivot.style.applymap(highlight_nonzero_yellow), use_container_width=True)

    change_reason = st.text_input("Reason for this selection change (required to save)")
    if st.button("Save Selections"):
        if not change_reason.strip():
            st.error("A change reason is required.")
        else:
            changed = 0
            for tier in edited.index:
                for bucket in edited.columns:
                    new_val = float(edited.loc[tier, bucket])
                    old_val = float(selection_pivot.loc[tier, bucket]) if tier in selection_pivot.index and bucket in selection_pivot.columns else 0.0
                    if abs(new_val - old_val) > 1e-9:
                        repository.update_selection_cell(session, campaign_id, segment_id, tier, bucket, new_val)
                        changed += 1
            if changed == 0:
                st.info("No cells changed.")
            else:
                result = repository.save_selection_set(session, campaign_id, segment_id, change_reason)
                st.success(result)
                st.rerun()

    cells = queries.segment_calculation_cells(session, campaign_id, segment_id)
    if cells.empty:
        st.caption("No calculated grid available yet -- save a selection above to see downstream grids.")
        return

    st.divider()
    ui.section_title("Calculated Grids")
    # Order and 3-per-row / 2-per-row layout per the real Segment.xlsx workbook: the first 6
    # grids (volume + rate progression) render 3-wide, the remaining cost/CPA grids 2-wide.
    first_six = [
        ("1. CDE Volume", "CDE_VOLUME", "{:,.0f}"),
        ("2. Post-EMS Volume (Universe Post-EMS Rates)", "POST_EMS_VOLUME", "${:,.0f}"),
        ("3. Selected Quantity (Selections)", "SELECTED_QUANTITY", "{:,.0f}"),
        ("4. Effective NRR (Net Response Rate)", "EFFECTIVE_NRR", "{:.4f}"),
        ("5. Unwind Rate", "HISTORICAL_UNWIND_RATE", "{:.4f}"),
        ("6. Booked Pre-Unwind (Selected)", "BOOKED_PRE_UNWIND_SELECTED", "{:,.0f}"),
    ]
    rest = [
        ("7. Pre-Unwind CPA (Selected)", "PRE_UNWIND_CPA_SELECTED", "${:,.2f}"),
        ("8. Post-Unwind CPA (Selected)", "POST_UNWIND_CPA_SELECTED", "${:,.2f}"),
        ("9. Marketing Cost (Selected)", "MARKETING_COST_SELECTED", "${:,.0f}"),
        ("10. Booking Cost (Selected)", "BOOKING_COST_SELECTED", "${:,.0f}"),
        ("11. Expected Unwinds (Selected)", "EXPECTED_UNWINDS_SELECTED", "{:,.0f}"),
        ("12. Booked Post-Unwind (Selected)", "BOOKED_POST_UNWIND_SELECTED", "{:,.0f}"),
    ]

    def _render_grid_row(row_grids, per_row):
        available = [g for g in row_grids if g[1] in cells.columns]
        for chunk_start in range(0, len(available), per_row):
            chunk = available[chunk_start:chunk_start + per_row]
            row_cols = st.columns(per_row)
            for col_widget, (title, col, fmt) in zip(row_cols, chunk):
                with col_widget:
                    with st.expander(title):
                        grid = pivot_grid(cells, col)
                        st.dataframe(grid.style.format(fmt), use_container_width=True)
                        if col == "BOOKED_POST_UNWIND_SELECTED" and "HISTORICAL_UNWIND_RATE" in cells.columns:
                            total_booked_pre = cells["BOOKED_PRE_UNWIND_SELECTED"].sum()
                            total_unwinds = cells["EXPECTED_UNWINDS_SELECTED"].sum() if "EXPECTED_UNWINDS_SELECTED" in cells.columns else 0
                            overall_unwind_rate = (total_unwinds / total_booked_pre) if total_booked_pre else 0
                            ui.chips(f"Unwind rate (total) {overall_unwind_rate:.4f}")

    _render_grid_row(first_six, 3)
    _render_grid_row(rest, 2)
