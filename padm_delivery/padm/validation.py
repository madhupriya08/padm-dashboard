"""Input validation driven by DM_PADM_ASSUMPTION_DEFINITION. Values are entered in display units
(PERCENT = 0-100 style) and stored as fractions."""

import math

import pandas as pd


def _is_missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value)


def to_display(definition, stored):
    if _is_missing(stored):
        return None
    value = float(stored)
    return round(value * 100, 8) if definition["DISPLAY_UNIT"] == "PERCENT" else value


def to_stored(definition, display):
    if _is_missing(display):
        return None
    value = float(display)
    return value / 100 if definition["DISPLAY_UNIT"] == "PERCENT" else value


def validate(definition, display):
    """Returns an error message, or None when the display value is acceptable.
    Empty is always allowed (= not set / inherit)."""
    if _is_missing(display):
        return None
    label = definition["ASSUMPTION_LABEL"]
    decimals = int(definition["DECIMALS"])
    value = float(display)
    if round(value, decimals) != round(value, 10):
        return f"{label}: at most {decimals} decimal places."
    stored = to_stored(definition, value)
    if stored < 0 and not bool(definition["ALLOW_NEGATIVE"]):
        return f"{label}: cannot be negative."
    lo, hi = definition.get("MIN_VALUE"), definition.get("MAX_VALUE")
    if not _is_missing(lo) and stored < float(lo) - 1e-12:
        return f"{label}: must be >= {to_display(definition, lo)}{unit_suffix(definition)}."
    if not _is_missing(hi) and stored > float(hi) + 1e-12:
        return f"{label}: must be <= {to_display(definition, hi)}{unit_suffix(definition)}."
    return None


def unit_suffix(definition):
    return {"PERCENT": "%", "CURRENCY": "", "FRACTION": ""}.get(definition["DISPLAY_UNIT"], "")


def input_format(definition):
    return f"%.{int(definition['DECIMALS'])}f"


def input_step(definition):
    return 10 ** -int(definition["DECIMALS"])


def validate_score_range(score_min, score_max, rules):
    """rules: DM_PADM_SCORE_RANGE_RULE_1 rows for the selected score type."""
    if _is_missing(score_min) or _is_missing(score_max):
        return "Bureau Score Range min and max are required."
    if score_min > score_max:
        return "Score Min must be <= Score Max."
    if rules.empty:
        return "No score-range rule exists for this Bureau Score Type (DM_PADM_SCORE_RANGE_RULE_1)."
    inside = rules[(rules["SCORE_MIN"] <= score_min) & (rules["SCORE_MAX"] >= score_max)]
    if inside.empty:
        lo, hi = int(rules["SCORE_MIN"].min()), int(rules["SCORE_MAX"].max())
        return f"Range {score_min}-{score_max} is not within a valid range for this score type ({lo}-{hi})."
    return None


def selection_percent(value):
    """Selection % grid cell (0-100, 2 decimals)."""
    if _is_missing(value):
        return 0.0
    v = round(float(value), 2)
    if v < 0 or v > 100:
        raise ValueError("Selection % must be between 0 and 100.")
    return v
