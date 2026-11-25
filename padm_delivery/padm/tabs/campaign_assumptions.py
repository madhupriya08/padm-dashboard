"""Tab 4 -- Campaign Assumptions: campaign-level, versioned, validated from
DM_PADM_ASSUMPTION_DEFINITION, prefilled from the previous campaign / previous year."""

import pandas as pd
import streamlit as st

from padm import repository, ui, validation

SCOPE = "campaign_assumptions"


def _inputs(definitions, stored_values, key, locked, read_only_codes=(), column="CAMPAIGN_COLUMN"):
    """One number_input per definition, in display units. Returns ({code: display}, [errors])."""
    values, errors = {}, []
    cols = st.columns(max(len(definitions), 1))
    for col, (_, d) in zip(cols, definitions.iterrows()):
        code = d["ASSUMPTION_CODE"]
        current = validation.to_display(d, stored_values.get(d[column])) if stored_values is not None else None
        suffix = validation.unit_suffix(d)
        values[code] = col.number_input(
            f"{d['ASSUMPTION_LABEL']}{' (' + suffix + ')' if suffix else ''}",
            value=current, step=validation.input_step(d), format=validation.input_format(d),
            placeholder="not set" if column == "CAMPAIGN_COLUMN" else "inherit campaign",
            help=f"{d['DATA_TYPE']}, {int(d['DECIMALS'])} decimals"
                 f"{', can be negative' if d['ALLOW_NEGATIVE'] else ', ≥ 0'}. Entered on: {d['ENTERED_ON']}.",
            disabled=locked or code in read_only_codes, key=f"{key}_{code}",
        )
        error = validation.validate(d, values[code])
        if error:
            errors.append(error)
    return values, errors


def _history_with_diffs(history, codes):
    """Version history panel: version, changed by, timestamp, reason, old -> new values."""
    if history.empty:
        return history
    rows, previous = [], None
    for _, row in history.iterrows():
        diffs = []
        for code in codes:
            if code not in history.columns:
                continue
            old = None if previous is None else ui.num(previous[code])
            new = ui.num(row[code])
            if old != new:
                diffs.append(f"{code}: {'–' if old is None else old} → {'–' if new is None else new}")
        rows.append({"Version": int(row["VERSION_NUMBER"]), "Changed by": row["CREATED_BY"], "Timestamp": row["CREATED_TS"],
                      "Change reason": row["CHANGE_REASON"], "Old → New": "; ".join(diffs) or "(no value change)",
                      "Current": bool(row["IS_CURRENT"])})
        previous = row
    return pd.DataFrame(rows).sort_values("Version", ascending=False)


def _campaign_level(session, campaign, definitions):
    st.subheader("Campaign-level assumptions")
    # NBR is the fallback for Base NRR when no historical NRR cell exists -- without it, Base NRR
    # (and everything downstream) has no value at all, since historical NRR isn't loaded yet.
    defs = definitions[definitions["CAMPAIGN_COLUMN"].notna()]
    current = repository.campaign_assumption_current(session, campaign["id"])
    version = int(current.iloc[0]["VERSION_NUMBER"]) if not current.empty else 0
    source = None
    if current.empty:
        current, source = repository.default_campaign_assumption(session, campaign["id"])
    stored = current.iloc[0].to_dict() if not current.empty else None
    if source:
        st.info(f"No assumptions saved for this campaign yet -- prefilled from the {source}. Review and save.",
                icon=":material/history:")
    elif stored is None:
        st.caption("No assumptions saved yet and no previous campaign to default from.")
    else:
        st.caption(f"Current version v{version}.")

    with st.container(border=True):
        values, errors = _inputs(defs, stored, f"ca_{campaign['id']}_{version}", campaign["locked"])
        for error in errors:
            st.error(error)
        with st.container(horizontal=True, vertical_alignment="bottom"):
            reason = ui.reason_input(f"ca_reason_{campaign['id']}", disabled=campaign["locked"])
            if st.button("Save campaign assumptions", type="primary", icon=":material/save:",
                          disabled=campaign["locked"] or bool(errors), key=f"ca_save_{campaign['id']}"):
                if ui.require_reason(reason):
                    stored_values = {d["ASSUMPTION_CODE"]: validation.to_stored(d, values[d["ASSUMPTION_CODE"]])
                                      for _, d in defs.iterrows()}
                    ui.run_action(SCOPE, lambda: repository.save_campaign_assumption(
                        session, campaign["id"], stored_values, version, reason.strip()))

    with st.expander("Version history -- campaign level"):
        history = _history_with_diffs(repository.campaign_assumption_history(session, campaign["id"]),
                                        defs["ASSUMPTION_CODE"].tolist())
        st.dataframe(history, hide_index=True) if not history.empty else st.caption("No versions yet.")


# Segment-level assumptions are edited on Segment Viewer instead, not here.


def render(session):
    st.header("Campaign Assumptions")
    campaign = ui.require_campaign(session)
    if campaign is None:
        return
    ui.show_flash(SCOPE)
    definitions = repository.assumption_definitions(session)
    if definitions.empty:
        st.error("DM_PADM_ASSUMPTION_DEFINITION is empty -- run sql/padm_spec_alignment_01_schema.sql.")
        return
    with st.expander("Assumption definitions (validation rules)"):
        st.dataframe(definitions[["ASSUMPTION_LABEL", "ASSUMPTION_LEVEL", "DATA_TYPE", "DISPLAY_UNIT", "DECIMALS",
                                   "MIN_VALUE", "MAX_VALUE", "ALLOW_NEGATIVE", "ENTERED_ON"]], hide_index=True)
    _campaign_level(session, campaign, definitions)
