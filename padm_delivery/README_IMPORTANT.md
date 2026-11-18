# What this zip actually is -- read before using

This is **not a verified, authoritative copy of your real `padm/` package.** It's a
reconstruction, transcribed from the 10 screenshot PDFs you shared, stitched back together by
multiple AI passes. Treat it as a **diff reference** -- a way to see exactly what was checked and
what was fixed -- not something to blindly copy over your real files in Snowsight.

## Fixes applied in this copy (both confirmed against your real spec + code)

1. **`padm/tabs/signature_page_2.py`** -- Reject was calling
   `repository.transition_status(session, cid, "REJECTED", ...)`. Your spec (sections 2.5 and
   8.2) and this same file's own on-screen caption both say Reject returns the campaign to
   `DRAFT`. `"REJECTED"` isn't even in this file's own `STEPS` list. Changed the literal to
   `"DRAFT"`.
2. **`padm/tabs/segment_viewer.py`** -- a transcription artifact, not a bug in your real code.
   An earlier OCR pass misread a call site as `_selection_section(session, campaign, segment_id,
   version, pending)` (5 args). The function's own definition (directly above, same file) takes
   only 3 params and never references `version` in its body, which also matches the spec (7.6:
   Selection % doesn't change between Working/Final version). Corrected the transcription to the
   3-arg call. **This fix is to our transcription, not necessarily to your real file** -- if your
   real file already has the 3-arg call, there was nothing to fix there in the first place.

## Known, real gaps in this reconstruction

- **`padm/queries.py` was never found in any of the 10 PDFs you shared.** It doesn't exist
  anywhere in this zip. If your tabs import from it, that import will fail if you ever tried to
  run this exact zip as-is.
- `padm/repository.py` here is **stitched from 3 separate screenshot-transcription passes**
  (lines 1-176, 9-745 of a second pass, and a 43-line fragment for `load_cde_version`'s body).
  The splice points were checked by hand and look clean, but this was never read end-to-end from
  your real, live file in one pass.
- `sql/03b_activate_INCOMPLETE_DO_NOT_RUN.sql` is exactly that -- incomplete (roughly lines 119+
  of a 300+-line script, the rest was never captured). Named so you don't run it by accident.
- Two full gap-report audits are in `docs/` (`GAP_REPORT_tabs1-3.md`, `GAP_REPORT_tabs4-7.md`)
  comparing this transcription against your spec (`docs/PADM_DASHBOARD_SPEC.md`). Summary:
  **~41 requirements matched, 2 confirmed real bugs (both fixed above), a handful flagged
  unverifiable rather than guessed at** (e.g. whether `SP_PADM_GENERATE_SIGNATURE_PAGE_2` refuses
  to run unless COMPLETED *inside the procedure itself*, vs. only in the Streamlit button's
  `disabled=` condition -- worth a direct look at your real `03_procedures.sql`).

## What's actually safe to do with this

- **Safe**: read the gap reports, apply the two specific one-line fixes above directly to your
  real files in Snowsight (both are tiny, exact edits -- see the diffs above).
- **Risky**: wholesale-replacing your real `padm/` folder with this zip's `padm/` folder, given
  the missing `queries.py` and the stitched `repository.py`.
