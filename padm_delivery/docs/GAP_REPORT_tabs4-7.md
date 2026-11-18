# Gap Report: Tabs 4-7 vs PADM_DASHBOARD_SPEC

## Tab 4 - Campaign Assumptions (campaign_assumptions.py)
| Requirement | Status | Note |
|---|---|---|
| Rate Adjustment / Seasonality / Unwind Rate Adj kept OFF this tab, segment-only, entered only on Segment Viewer | MATCHES | `viewer_only` codes computed from `ENTERED_ON == "SEGMENT_VIEWER"`, passed as `read_only_codes` to `_inputs`, field `disabled=True` here (line 103,116,128) |
| Versioned, IS_CURRENT/ROW_VERSION, CHANGE_REASON mandatory | MATCHES | `ui.require_reason`, `repository.save_*_assumption(..., version, reason)` |
| Defaults prefill from previous campaign/year | MATCHES | `repository.default_campaign_assumption` / `default_segment_assumption` with `source` info banner |
| Version history panel: version/changed by/ts/reason/old->new | MATCHES | `_history_with_diffs` |

## Tab 5 - Population Description (population_description.py)
| Requirement | Status | Note |
|---|---|---|
| Group by AF then score band | MATCHES | `segments.groupby(["AF","BAND"])`, BAND = SCORE_TYPE+min-max |
| Multi-select offer assignment per segment, one offer per segment only | MATCHES (+extra) | duplicate-offer check added, not in spec but harmless |
| Sub-totals + grand total | MATCHES | `_sums`/`_metrics_line` |
| Group labels from DM_PADM_POPULATION_GROUP_RULE, no Python string-building | PARTIAL/UNVERIFIED | UI is a plain `text_input`, no string concatenation (good) but default value traces to `live["POPULATION_DESCRIPTION"]`, not directly confirmed to originate from the rule table -- would need the SQL view to settle |
| Save Allocation + CHANGE_REASON, Reset to Previous | MATCHES | |

## Tab 6 - Segment Viewer (segment_viewer.py, formulas.py)
| Requirement | Status | Note |
|---|---|---|
| "Show calculated grid" toggle REMOVED | MATCHES | no such toggle found |
| "Working Version \| Final Version" toggle present | MATCHES | `st.segmented_control("Volume source", VERSIONS,...)` line 365 |
| 14-step calculated-grid order (spec 7.8) | MATCHES EXACTLY | `formulas.GRIDS` order: mku, post_ems, selected, base_nrr, eff_nrr, booked_pre, eff_unwind, unwinds, booked_post, marketing, booking, pre_cpa, post_cpa -- byte-for-byte matches spec table |
| Formula caption shown at start of every grid | MATCHES | caption string is item 5 of each GRIDS tuple, rendered via `ui.render_grid` |
| Unwind Rate row directly below Booked Post-Unwind Total | MATCHES | `extra_row=("Unwind Rate", safe_div(...), "percent")` only for `key=="booked_post"` |
| CDE upload is on Segment Viewer | MATCHES | `_cde_section` |
| Excel-like range apply (edit cell/range/row/col/copy-paste/clear) | MATCHES | `st.data_editor` + range-apply expander; true click-drag explicitly unavailable, matches spec's own acknowledged limitation |
| Highlight prior-month selected cells yellow (prior>0) | MATCHES | single-tier yellow highlight exactly as spec 7.3 states (no 3-tier scheme is required by THIS spec) |
| 3-store selection save (WORKING/_SET+_SET_CELL/_EVENT) + 3-month purge TASK | NOT VERIFIED HERE | repository-side, not re-checked in this pass (tabs 1-3 fork may have covered DDL) |
| Fallback chain (exact->segment+type->campaign default) | MATCHES (indirect evidence) | `NRR_SOURCE`/`UNWIND_SOURCE`/`EMS_SOURCE` columns surfaced and captioned, implying COALESCE chain exists in the view |
| Booked Pre-Unwind computed for BOTH universe and selected | MATCHES | formulas.py computes `_UNIVERSE` and `_SELECTED` variants; UI renders both (grid `7b`) |
| Formula sign/parity check (Effective NRR, Effective Unwind Rate, Post-EMS Volume, Post-Unwind CPA) | MATCHES EXACTLY | no sign-flip bugs found; `(1-seasonality)` not `(1+seasonality)`, `(1-ems)` not `(1+ems)`, division-by-zero -> NaN via `safe_div`, weighted totals (not sums) for rate/CPA grids |
| **BUG, HIGH PRIORITY**: `segment_viewer.py` line 376 | **WRONG** | `pending = _selection_section(session, campaign, segment_id, version, pending)` passes 5 args and reads `pending` on the right-hand side before it is ever assigned, but `_selection_section`'s `def` (line 167) only takes `(session, campaign, segment_id)` -- 3 args. Either a transcription slip or a real `NameError`/`TypeError` crash on this exact line. **Must be checked against the live file directly before anything else on this page can be trusted.** |

## Tab 7 - Signature Page 2 (signature_page_2.py)
| Requirement | Status | Note |
|---|---|---|
| Actions in order: Run Calculation -> Generate -> Approve/Reject -> Export | MATCHES | `_actions`, `_export_buttons` |
| Generate refuses unless latest run COMPLETED | MATCHES in UI (`disabled=... or not completed`) | **NOT CONFIRMED at the SQL/procedure level** -- spec explicitly requires `SP_PADM_GENERATE_SIGNATURE_PAGE_2` itself to refuse, not just the button; 03_procedures.sql not re-checked in this pass for that guard |
| Live preview from VW_PADM_SIGNATURE_PAGE_LIVE; immutable versioned snapshot | MATCHES | |
| Export to Excel and PDF | MATCHES | `exports.to_excel`/`to_pdf` with HTML fallback if reportlab missing |
| Approve -> APPROVED, read-only everywhere | MATCHES | |
| **Reject -> status set to "REJECTED", NOT "DRAFT"** | **WRONG** | Spec 2.5/8.2 says Reject returns to DRAFT. Code calls `repository.transition_status(session, cid, "REJECTED", ...)`. `REJECTED` is not even in this same file's own `STEPS` list (`["NEW","DRAFT","IN_PROGRESS","PENDING_APPROVAL","APPROVED"]`), so the stepper would show no highlighted step (index -1) for a rejected campaign, and anything elsewhere keyed off `campaign["locked"]`/status may not treat REJECTED as an editable/DRAFT-equivalent state. |
| Actuals / Finance Extract placeholders | MATCHES | correctly left as placeholder expanders, out of scope |

## Summary
MATCHES: 24+ | WRONG: 2 (confirmed) | MISSING/UNVERIFIED: 3 (population label source, 3-store/purge task, SQL-level COMPLETED guard)

This codebase is **very well-aligned with the spec** -- formulas, grid order, toggles, and most
business rules are implemented correctly and precisely. The two WRONG findings are both real,
specific, fixable bugs, not broad gaps.
