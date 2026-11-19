"""Every PADM formula, in calculation order (spec 7.8).

Mirrors VW_PADM_SEGMENT_CALCULATION_CURRENT -- keep the two in sync. The Segment Viewer uses
``calculate`` for the Final Version (mail-file quantities replace Selected Quantity) and the
grid definitions below for display, captions and weighted totals.
"""

import numpy as np
import pandas as pd

TIMES_MAILED_BUCKETS = [str(i) for i in range(9)] + ["9+"]
EMS_POC_BLANKET_RATE = 0.05


def safe_div(numerator, denominator):
    """Division where a zero/NULL denominator gives NULL (displayed as '-')."""
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    if np.isscalar(den):
        return np.nan if (pd.isna(den) or den == 0) else num / den
    return num / den.where(den != 0)


def sql_round(values):
    """Snowflake ROUND(x, 0): half away from zero."""
    v = pd.to_numeric(values, errors="coerce")
    return np.sign(v) * np.floor(np.abs(v) + 0.5)


def _col(cells, name, default=0.0):
    if name not in cells.columns:
        return pd.Series(default, index=cells.index, dtype="float64")
    return pd.to_numeric(cells[name], errors="coerce")


def calculate(cells, selected_quantity=None):
    """Recomputes every derived column from the input columns.

    Inputs: CDE_VOLUME, EMS_REDUCTION_RATE, SELECTION_PERCENTAGE, BASE_NRR, HISTORICAL_UNWIND_RATE,
    EFFECTIVE_RATE_ADJUSTMENT, EFFECTIVE_SEASONALITY_REDUCTION, EFFECTIVE_UNWIND_RATE_ADJUSTMENT,
    EFFECTIVE_CPP, EFFECTIVE_UNIT_COST.
    ``selected_quantity`` (Series aligned to ``cells``) overrides step 4 -- the Final Version.
    """
    out = cells.copy()
    ems = _col(out, "EMS_REDUCTION_RATE", np.nan).fillna(EMS_POC_BLANKET_RATE)
    selection = _col(out, "SELECTION_PERCENTAGE").fillna(0)
    rate_adj = _col(out, "EFFECTIVE_RATE_ADJUSTMENT").fillna(0)
    seasonality = _col(out, "EFFECTIVE_SEASONALITY_REDUCTION").fillna(0)
    unwind_adj = _col(out, "EFFECTIVE_UNWIND_RATE_ADJUSTMENT").fillna(0)
    cpp = _col(out, "EFFECTIVE_CPP", np.nan)
    unit_cost = _col(out, "EFFECTIVE_UNIT_COST", np.nan)

    # 2-3 volume
    out["EMS_REDUCTION_RATE"] = ems
    out["POST_EMS_VOLUME"] = _col(out, "CDE_VOLUME") * (1 - ems)
    # 4 selected quantity
    if selected_quantity is None:
        out["SELECTED_QUANTITY"] = sql_round(out["POST_EMS_VOLUME"] * selection)
    else:
        out["SELECTED_QUANTITY"] = pd.to_numeric(selected_quantity, errors="coerce").fillna(0)
    # 5-6 NRR
    out["EFFECTIVE_NRR"] = _col(out, "BASE_NRR", np.nan) * (1 + rate_adj) * (1 - seasonality)
    # 7 booked pre-unwind (universe + selected)
    out["BOOKED_PRE_UNWIND_UNIVERSE"] = out["POST_EMS_VOLUME"] * out["EFFECTIVE_NRR"]
    out["BOOKED_PRE_UNWIND_SELECTED"] = out["SELECTED_QUANTITY"] * out["EFFECTIVE_NRR"]
    # 8 effective unwind rate
    out["EFFECTIVE_UNWIND_RATE"] = _col(out, "HISTORICAL_UNWIND_RATE", np.nan) * (1 + unwind_adj)
    # 9-10 unwinds / post-unwind
    for scope in ("UNIVERSE", "SELECTED"):
        pre = out[f"BOOKED_PRE_UNWIND_{scope}"]
        out[f"EXPECTED_UNWINDS_{scope}"] = pre * out["EFFECTIVE_UNWIND_RATE"]
        out[f"BOOKED_POST_UNWIND_{scope}"] = pre * (1 - out["EFFECTIVE_UNWIND_RATE"])
    # 11-12 costs
    out["MARKETING_COST_UNIVERSE"] = out["POST_EMS_VOLUME"] * cpp
    out["MARKETING_COST_SELECTED"] = out["SELECTED_QUANTITY"] * cpp
    out["BOOKING_COST_UNIVERSE"] = out["BOOKED_PRE_UNWIND_UNIVERSE"] * unit_cost
    out["BOOKING_COST_SELECTED"] = out["BOOKED_PRE_UNWIND_SELECTED"] * unit_cost
    # 13-14 CPA (only after marketing cost and booked pre-unwind exist)
    for scope in ("UNIVERSE", "SELECTED"):
        out[f"PRE_UNWIND_CPA_{scope}"] = safe_div(out[f"MARKETING_COST_{scope}"], out[f"BOOKED_PRE_UNWIND_{scope}"])
        out[f"POST_UNWIND_CPA_{scope}"] = safe_div(
            out[f"MARKETING_COST_{scope}"] + out[f"BOOKING_COST_{scope}"], out[f"BOOKED_POST_UNWIND_{scope}"]
        )
    out["SELECTED_NRR"] = out["EFFECTIVE_NRR"].where(out["SELECTED_QUANTITY"] > 0)
    out["_BASE_NRR_WEIGHT"] = _col(out, "BASE_NRR", np.nan) * out["POST_EMS_VOLUME"]
    out["_SELECTION_WEIGHT"] = selection * out["POST_EMS_VOLUME"]
    out["_HIST_UNWIND_WEIGHT"] = _col(out, "HISTORICAL_UNWIND_RATE", np.nan) * out["BOOKED_PRE_UNWIND_UNIVERSE"]
    return out


# ---------------------------------------------------------------------------------------------
# Grid definitions, in calculation order.
#   key, title, value column, display format, formula caption,
#   ratio=(numerator columns, denominator columns) for weighted totals, or None (sum)
# ---------------------------------------------------------------------------------------------
GRIDS = [
    ("mku", "CDE Volume", "CDE_VOLUME", "localized",
     "CDE Volume = loaded CDE volume (Count Distinct EPIN)", None),
    ("post_ems", "Universe Post-EMS", "POST_EMS_VOLUME", "localized",
     "Universe Post-EMS = CDE_VOLUME x (1 - EMS_REDUCTION_RATE)  [blanket 5% when no EMS rate]", None),
    ("selected", "Selections", "SELECTED_QUANTITY", "localized",
     "Selections = ROUND(Universe Post-EMS x Selection %, 0)", None),
    ("base_nrr", "Base NRR", "BASE_NRR", "percent",
     "Base NRR = Boarded Count / Mail Quantity (historical; fallback segment -> campaign NBR)",
     (["_BASE_NRR_WEIGHT"], ["POST_EMS_VOLUME"])),
    ("eff_nrr", "Effective NRR", "EFFECTIVE_NRR", "percent",
     "Effective NRR = Base NRR x (1 + Rate Adjustment) x (1 - Seasonality Reduction)",
     (["BOOKED_PRE_UNWIND_UNIVERSE"], ["POST_EMS_VOLUME"])),
    ("selected_nrr", "Selected NRR", "SELECTED_NRR", "percent",
     "Selected NRR = Effective NRR, for cells with a non-zero Selected Quantity",
     (["BOOKED_PRE_UNWIND_SELECTED"], ["SELECTED_QUANTITY"])),
    ("hist_unwind", "Historical Unwind Rate", "HISTORICAL_UNWIND_RATE", "percent",
     "Historical Unwind Rate = input (exact cell -> segment fallback -> campaign default)",
     (["_HIST_UNWIND_WEIGHT"], ["BOOKED_PRE_UNWIND_UNIVERSE"])),
    ("booked_pre", "Booked Pre-Unwind (Selected)", "BOOKED_PRE_UNWIND_SELECTED", "%.1f",
     "Booked Pre-Unwind = Selected Quantity x Effective NRR", None),
    ("booked_pre_universe", "Universe Booked Pre-Unwind", "BOOKED_PRE_UNWIND_UNIVERSE", "%.1f",
     "Universe Booked Pre-Unwind = Universe Post-EMS x Effective NRR", None),
    ("eff_unwind", "Effective Unwind Rate", "EFFECTIVE_UNWIND_RATE", "percent",
     "Effective Unwind Rate = Historical Unwind Rate x (1 + Unwind Rate Adjustment)",
     (["EXPECTED_UNWINDS_UNIVERSE"], ["BOOKED_PRE_UNWIND_UNIVERSE"])),
    ("pre_cpa_universe", "Pre-Unwind CPA Universe", "PRE_UNWIND_CPA_UNIVERSE", "dollar",
     "Pre-Unwind CPA Universe = Universe Marketing Cost / Universe Booked Pre-Unwind",
     (["MARKETING_COST_UNIVERSE"], ["BOOKED_PRE_UNWIND_UNIVERSE"])),
    ("pre_cpa", "Pre-Unwind CPA (Selected)", "PRE_UNWIND_CPA_SELECTED", "dollar",
     "Pre-Unwind CPA = Marketing Cost / Booked Pre-Unwind",
     (["MARKETING_COST_SELECTED"], ["BOOKED_PRE_UNWIND_SELECTED"])),
    ("post_cpa_universe", "Post-Unwind CPA Universe", "POST_UNWIND_CPA_UNIVERSE", "dollar",
     "Post-Unwind CPA Universe = (Universe Marketing + Booking Cost) / Universe Booked Post-Unwind",
     (["MARKETING_COST_UNIVERSE", "BOOKING_COST_UNIVERSE"], ["BOOKED_POST_UNWIND_UNIVERSE"])),
    ("post_cpa", "Post-Unwind CPA Selected", "POST_UNWIND_CPA_SELECTED", "dollar",
     "Post-Unwind CPA = (Marketing Cost + Booking Cost) / Booked Post-Unwind",
     (["MARKETING_COST_SELECTED", "BOOKING_COST_SELECTED"], ["BOOKED_POST_UNWIND_SELECTED"])),
    ("marketing_universe", "Universe Marketing Cost", "MARKETING_COST_UNIVERSE", "dollar",
     "Universe Marketing Cost = Universe Post-EMS x CPP", None),
    ("marketing", "Selected Marketing Cost", "MARKETING_COST_SELECTED", "dollar",
     "Selected Marketing Cost = Selected Quantity x CPP", None),
    ("booking_universe", "Universe Booking Cost", "BOOKING_COST_UNIVERSE", "dollar",
     "Universe Booking Cost = Universe Booked Pre-Unwind x Unit Cost", None),
    ("booking", "Selected Booking Cost", "BOOKING_COST_SELECTED", "dollar",
     "Selected Booking Cost = Booked Pre-Unwind x Unit Cost", None),
    ("unwinds_universe", "Universe Expected Unwinds", "EXPECTED_UNWINDS_UNIVERSE", "%.1f",
     "Universe Expected Unwinds = Universe Booked Pre-Unwind x Effective Unwind Rate", None),
    ("unwinds", "Selected Expected Unwinds", "EXPECTED_UNWINDS_SELECTED", "%.1f",
     "Selected Expected Unwinds = Booked Pre-Unwind x Effective Unwind Rate", None),
    ("booked_post_universe", "Universe Booked Post-Unwind", "BOOKED_POST_UNWIND_UNIVERSE", "%.1f",
     "Universe Booked Post-Unwind = Universe Booked Pre-Unwind x (1 - Effective Unwind Rate)", None),
    ("booked_post", "Selected Booked Post-Unwind", "BOOKED_POST_UNWIND_SELECTED", "%.1f",
     "Selected Booked Post-Unwind = Booked Pre-Unwind x (1 - Effective Unwind Rate)", None),
]

# Row groups for the side-by-side layout (user's explicit call, matching the real Segment.xlsx
# alignment): each inner list is a set of grid keys (from GRIDS above) shown side by side in one
# horizontally-scrollable row, in this exact order top to bottom.
GRID_ROWS = [
    ["mku", "post_ems", "selected"],
    ["base_nrr", "eff_nrr", "selected_nrr"],
    ["hist_unwind", "booked_pre_universe", "booked_pre"],
    ["pre_cpa_universe", "pre_cpa"],
    ["post_cpa_universe", "post_cpa"],
    ["marketing_universe", "marketing"],
    ["booking_universe", "booking"],
    ["unwinds_universe", "unwinds"],
    ["booked_post_universe", "booked_post"],
]

SELECTION_GRID_CAPTION = "Selection % = user input (0-100), prepopulated from the prior month's saved selection"


def _ordered(pivoted):
    return pivoted[[c for c in TIMES_MAILED_BUCKETS if c in pivoted.columns]].sort_index()


def pivot_grid(cells, value_col, ratio=None):
    """Tier x Times Mailed grid with Total row and Total column.

    Sums for additive metrics. For rates/CPAs the totals are weighted:
    sum(numerators) / sum(denominators). Division by zero -> NaN (rendered '-').
    """
    if cells.empty:
        return pd.DataFrame()
    cells = cells.copy()
    cells["TIMES_MAILED_BUCKET"] = cells["TIMES_MAILED_BUCKET"].astype(str)

    def pivot(col, agg="sum"):
        return _ordered(cells.pivot_table(index="RESPONSE_MODEL_TIER", columns="TIMES_MAILED_BUCKET",
                                           values=col, aggfunc=agg, dropna=False))

    if ratio is None:
        grid = pivot(value_col).fillna(0)
        grid["Total"] = grid.sum(axis=1)
        grid.loc["Total"] = grid.sum(axis=0)
    else:
        numerators, denominators = ratio
        cells["_NUM"] = sum(pd.to_numeric(cells[c], errors="coerce").fillna(0) for c in numerators)
        cells["_DEN"] = sum(pd.to_numeric(cells[c], errors="coerce").fillna(0) for c in denominators)
        grid = pivot(value_col, "mean")
        num, den = pivot("_NUM").fillna(0), pivot("_DEN").fillna(0)
        grid["Total"] = safe_div(num.sum(axis=1), den.sum(axis=1))
        total_row = safe_div(num.sum(axis=0), den.sum(axis=0))
        total_row["Total"] = safe_div(num.values.sum(), den.values.sum())
        grid.loc["Total"] = total_row
    grid.index = grid.index.map(lambda v: v if isinstance(v, str) else str(int(v)))
    grid.index.name = "Tier"
    return grid


def totals(cells):
    """Headline totals for a segment (weighted rates)."""
    s = {c: pd.to_numeric(cells[c], errors="coerce").fillna(0).sum() for c in (
        "SELECTED_QUANTITY", "BOOKED_PRE_UNWIND_SELECTED", "EXPECTED_UNWINDS_SELECTED",
        "BOOKED_POST_UNWIND_SELECTED", "MARKETING_COST_SELECTED", "BOOKING_COST_SELECTED")}
    return {
        **s,
        "UNWIND_RATE": safe_div(s["EXPECTED_UNWINDS_SELECTED"], s["BOOKED_PRE_UNWIND_SELECTED"]),
        "PRE_UNWIND_CPA": safe_div(s["MARKETING_COST_SELECTED"], s["BOOKED_PRE_UNWIND_SELECTED"]),
        "POST_UNWIND_CPA": safe_div(s["MARKETING_COST_SELECTED"] + s["BOOKING_COST_SELECTED"],
                                     s["BOOKED_POST_UNWIND_SELECTED"]),
    }
