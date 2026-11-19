# PADM Dashboard — Handoff to new session

Read this whole file first. It replaces a very long prior conversation (the person you're
helping, Madhupriya, has been building a Streamlit-in-Snowflake dashboard for CreditOne Bank's
PADM direct-mail sign-off process, and this is the distilled context from that work).

## 1. The project, in one paragraph

PADM replaces a manual Excel "Signature Page" sign-off process for monthly direct-mail
credit-card campaigns with a Streamlit-in-Snowflake app (DB_RISK.RISK_SBX schema). The real
source of truth for what the app must do is `padm_delivery/docs/PADM_DASHBOARD_SPEC.md` in this
repo — a 560-line spec the user wrote themselves, with an explicit 7-tab structure, exact
formulas, exact column orders, and an explicit rule: **"Where this spec says VERIFY, do not
guess. Query the database and confirm before you build."** Treat that spec as authoritative
over anything else, including this handoff.

## 2. Critical: there are TWO code trees in this repo. Only one is real.

- **`padm_delivery/`** — a reconstruction of the user's REAL, currently-running `padm/` package
  (`padm/tabs/*.py`, `padm/repository.py`, `padm/db.py`, `padm/ui.py`, `padm/validation.py`,
  `padm/formulas.py`, `padm/exports.py`, `streamlit_app.py`). This is what matters. **Read
  `padm_delivery/README_IMPORTANT.md` before touching anything** — it explains this
  reconstruction's known gaps in detail (most importantly: **`padm/queries.py` was never
  captured in any screenshot and does not exist anywhere in this repo** — if you need it, ask
  the user for a fresh screenshot of that file).
- **`dashboard_build/`** — a separate, parallel app (`app/` package) built earlier in the prior
  conversation, based on a wrong assumption about which code was live. **It is not wired into
  anything the user actually runs.** Don't spend time on it unless the user explicitly asks;
  it's kept only for reference.

## 3. How we got here (so you don't redo work)

1. Early work (in the prior conversation, not in this repo in detail) diagnosed and fixed real
   SQL bugs in the user's Snowflake objects via `GET_DDL`/`DESC TABLE` confirmation — never
   guessing. Key confirmed facts from that work (still true, not yet re-verified against a live
   `SHOW TABLES`/`DESCRIBE` pass — do that early if you have DB access):
   - `VW_PADM_ACM_OFFER_SOURCE` (a real, pre-existing bridge view) already exposes
     `CREDIT_BUREAU_MODEL`, `CREDIT_BUREAU_SCORE`, `CRS_MODEL`, `CRS_SCORE`, `NRM` — these were
     wired through to `DM_PADM_CAMPAIGN_OFFER` and `SP_PADM_ACTIVATE_CAMPAIGN`.
   - The real procedure is `SP_PADM_TRANSITION_CAMPAIGN_STATUS` per the user's spec section
     0.1 (an earlier guess that it was named without `_STATUS` was wrong; the spec's own existing
     objects list confirms the longer name — but ALSO cross check against whatever
     `padm/repository.py`'s `transition_status()` actually calls, since that's more current than
     either guess).
   - The user's own confirmed campaign-offer source filters (spec 2.3):
     `SUBSTR(program_code,1,1)<>'W' AND LENGTH(reservation_code)<=6 AND channel_type='Mail' AND
     offer_status='Active'`.
2. A huge batch of screenshots (10 PDFs) of the user's real Snowsight workspace were transcribed
   (via multiple sub-agent passes) into `padm_delivery/`. Two real bugs were found this way and
   fixed (see README_IMPORTANT.md for exact detail):
   - `signature_page_2.py`: Reject was setting status to `"REJECTED"` instead of `"DRAFT"` — now
     fixed.
   - `segment_viewer.py`: a 5-arg vs 3-arg call-site mismatch turned out to be a transcription
     OCR error, not a real bug — the fix applied was to the transcription, not necessarily to
     the user's live file (worth a 10-second glance at the real file to confirm it already
     looks like the fix, not the error).
3. Two structured gap-report audits exist comparing the transcription against the spec:
   `padm_delivery/docs/GAP_REPORT_tabs1-3.md` and `GAP_REPORT_tabs4-7.md`. Summary: ~41
   requirements matched the spec correctly, only the 2 bugs above were wrong, a handful of items
   were flagged as "unverifiable from screenshots alone" rather than guessed at (see below).

## 4. Open items — things to verify or finish, not yet done

- **`padm/queries.py` is completely missing.** Get it from the user (ask for a screenshot/photo,
  or if they have live DB/file access now, have them paste its contents directly).
- Whether `SP_PADM_GENERATE_SIGNATURE_PAGE_2` refuses to run unless the latest calculation run is
  `COMPLETED` **inside the procedure itself** (spec requires this) — currently this is only
  confirmed enforced via the Streamlit button's `disabled=` condition, not inside the SQL.
- Whether a 3-month purge `TASK` exists for `DM_PADM_SELECTION_WORKING` (spec 7.4 requires one,
  that must never touch `DM_PADM_SELECTION_SET`/`_EVENT`).
- Whether population-group labels (Tab 5) are pulled from `DM_PADM_POPULATION_GROUP_RULE` or
  built with Python string logic (spec explicitly forbids the latter).
- `sql/03b_activate_INCOMPLETE_DO_NOT_RUN.sql` in `padm_delivery/` is exactly that — incomplete,
  do not run as-is. If you need the full `SP_PADM_ACTIVATE_CAMPAIGN`/related script, get a fresh
  complete copy from the user rather than trusting this file.
- The user previously reported **a timestamp-rendering error happening across multiple tabs**,
  not yet confirmed with an exact error message/traceback. Likely cause candidates investigated
  but not confirmed: (a) `padm/db.py`'s `@st.cache_data`-wrapped `_cached_df()` returning
  `TIMESTAMP_NTZ` columns that don't survive Arrow serialization cleanly in `st.dataframe()`, or
  (b) specific tabs rebuilding a "history" table via `rows.append({...}); pd.DataFrame(rows)`
  with a raw timestamp value inside the dict (loses clean dtype). **Get the exact error text
  from the user before attempting a fix** — guessing here previously went back and forth.
- Campaign status naming has been a recurring source of confusion across different sources in
  the prior conversation. **The spec (section 2.5) is authoritative**:
  `NEW → DRAFT → IN_PROGRESS (v1, v2, ...) → PENDING_APPROVAL → APPROVED` or `REJECTED → DRAFT`.
  If you see any other status vocabulary anywhere (e.g. `DISCOVERED`/`READY_FOR_REVIEW`/
  `COMPLETED`/`REOPENED` — that's from the unrelated `dashboard_build/app/` dead code, ignore
  it), treat the spec's names as correct and flag the mismatch rather than silently guessing
  which is right.

## 4a. Update from mobile debugging session (2026-11-19)

Got full real `padm/` package via screenshots (previously only had the unverified
`padm_delivery/` reconstruction). Confirmed real, and applied to `padm_delivery/` in this repo:

1. **`VW_PADM_SIGNATURE_PAGE_LIVE`** (`padm_delivery/sql/02_views.sql`) was missing
   `CRS_MODEL`/`NRM` entirely and didn't join `VW_PADM_ACM_OFFER_SOURCE` at all -- the
   reconstruction's version was a wrong guess (a thin wrapper over `VW_PADM_SIGNATURE_PAGE_ALL`
   that doesn't match the real object). Replaced with the real, standalone view definition,
   confirmed applied and run by the user directly in Snowsight.
2. **`padm/repository.py`'s `signature_live()`** had a broken `ORDER BY` referencing
   `SCORE_MIN`/`SEGMENT_NAME`/`OFFER_RESERVATION_CODE` -- none of which the view actually
   outputs (`invalid identifier`). Fixed to order by real output columns. Confirmed applied.
3. **`streamlit_app.py`** rewrite (header bar, status badge, landing screen) -- applied to
   `padm_delivery/` but **NOT yet confirmed working against the real project**. One caveat
   already resolved (checked `padm/ui.py` directly: `CAMPAIGN_KEY = "campaign_id"` matches the
   new file's hardcoded string, no mismatch). Still unconfirmed: whether
   `repository.campaign_header()` actually returns a dict with keys
   `name`/`mail_date`/`type`/`version`/`status`/`source_change_pending`, and whether the
   deployed Streamlit version supports `:material/...:` icons.

Still open, unchanged from before: Selection % "no prior month" check (query given, not yet
run), `MLA` field removal in Create Segment, offer-allocation defaulting to previous offers
(`repository.suggested_offers()` already exists for this), a Campaign Assumptions
segment-lookup complaint (unconfirmed root cause), the 3-month purge `TASK` (still not found
anywhere in any SQL file shared so far). `app/` in the real Snowsight project is confirmed dead
code -- not imported by `streamlit_app.py` -- same pattern as `dashboard_build/` in this repo.

**Current working mode**: the user is debugging reactively from mobile (no DB access there) --
run the app, report the exact error, get the exact fix, nothing broader unless asked.

## 4b. Major SQL update (2026-11-19, later same day)

`padm_delivery/sql/` went from 4 files to 22 (of the ~27 real files shown in the user's actual
Snowsight file tree). Extracted via parallel transcription of the original 7 "Sql database
queries N.pdf" + "Sql_database_queries_1.pdf" PDFs (the project's original source documents).
Two real cross-PDF splices were done carefully (not guessed): `operational_procedures.sql`
(now has complete `SP_PADM_ACTIVATE_CAMPAIGN`, `SP_PADM_SAVE_CAMPAIGN_ASSUMPTION`,
`SP_PADM_ACTIVATE_CDE_VERSION`) and `calculation_views.sql` (now has the COMPLETE
`VW_PADM_SEGMENT_CALCULATION_CURRENT`, including the MEASURES CTE and final SELECT that were
previously cut off -- a bogus 2-line stub that a transcription fork had left in its place was
found and replaced, not just appended to).

**Still fully missing**: `validations.sql` -- the user explicitly chose to skip capturing this one
(2026-11-19), not a gap. It's the only one of the ~27 real files with zero content in this repo.

**`DM_PADM_EMS_RATE_VERSION`** (an EMS rate table referenced by the filename `cde_ems_tables.sql`)
was never found in any source despite being in that file -- flagged, not fabricated.

## 4c. Two more real files captured (2026-11-19, later same day)

- **`additional_procedures_and_views.sql`** -- turned out to be the user's own copy, already
  uploaded to their real workspace, of this project's own `dashboard_build/sql/20_additional_procedures_and_views.sql`
  (confirmed via distinctive comment text only this conversation wrote -- the Section 3 removal
  note about the redundant `SP_PADM_TRANSITION_CAMPAIGN_STATUS`, and the Section 6 credit-bureau
  note). Copied verbatim into `padm_delivery/sql/additional_procedures_and_views.sql` -- no
  re-transcription needed, already verbatim-known content.
- **`new_validations.sql`** -- a real debugging/scratch file (not a deployment script), captured
  via 3 photos. Contains ad hoc exploration SELECTs/DESCs against the live schema, 3 one-time
  `DROP TABLE`s for legacy tables (`DM_PADM_TR_BOARDED_ACCOUNT`, `DM_PADM_TR_APPLICATION_OUTCOME`,
  `DM_PADM_TR_MAILFILE_NORMALIZED`), and -- important -- direct evidence that the user flagged
  `VW_PADM_SIGNATURE_PAGE_ALL` and the pre-fix `VW_PADM_SIGNATURE_PAGE_LIVE` as **"WRONG JOINS"**,
  followed by the corrected `CREATE OR REPLACE VIEW` they wrote. That corrected view matches
  `padm_delivery/sql/02_views.sql`'s current `VW_PADM_SIGNATURE_PAGE_LIVE` verbatim (the fix from
  section 4a above is confirmed to be this same, real, applied fix -- not superseded by anything
  newer). Saved to `padm_delivery/sql/new_validations.sql` with a transcription-confidence note at
  the top (lines 1-42, from a rotated photo, have a couple of TRANSCRIPTION UNCERTAIN inline
  comments; lines 43-94, the view DDL, are high-confidence, read from clear photos).

## 4d. Final 2 real SQL files captured (2026-11-19, later same day) -- 26 of ~27 done

- **`updates.sql`** -- 5 `ALTER TABLE ADD COLUMN IF NOT EXISTS` statements (2 on
  `DM_PADM_CHANGE_EVENT` for `BEFORE_VALUE`/`AFTER_VALUE` VARIANT audit columns, 3 on
  `DM_PADM_CAMPAIGN_OFFER`/`DM_PADM_CAMPAIGN_SOURCE_COMPONENT` for program-matching columns), a
  verification SELECT, then an idempotent repeat of the same 3 ALTERs, then 2 cleanup `DELETE`s
  removing orphaned `DM_PADM_CAMPAIGN_SOURCE_COMPONENT`/`_VERSION` rows with no offers attached.
- **`wire_credit_bureau_fields.sql`** -- the file HANDOFF.md previously flagged as likely
  overlapping the `VW_PADM_SIGNATURE_PAGE_LIVE` fix. It does NOT touch that view at all --
  it's scoped to `DM_PADM_CAMPAIGN_OFFER` / `VW_PADM_CAMPAIGN_OFFER_CURRENT` /
  `SP_PADM_ACTIVATE_CAMPAIGN` only (adds `CREDIT_BUREAU_MODEL`/`CREDIT_BUREAU_SCORE` columns,
  rebuilds the view with them added after `CRS_SCORE`, updates the activate procedure to
  populate them from `VW_PADM_ACM_OFFER_SOURCE`, backfills existing rows once, verifies).
  **Important correction to section 4b above**: this real, currently-running procedure's code
  (`SP_PADM_ACTIVATE_CAMPAIGN`) contains `IF (V_STATUS NOT IN ('DISCOVERED', 'REOPENED',
  'DRAFT')) THEN` -- the OLD status vocabulary is confirmed LIVE in real procedure logic, not
  merely in stale DDL/docs as previously assumed. Don't treat `DISCOVERED`/`REOPENED` as dead;
  cross-check against `padm/repository.py`'s actual status-handling code before assuming the
  spec's newer vocabulary (`NEW`/`IN_PROGRESS`/`PENDING_APPROVAL`) is what's really enforced at
  the DB layer for activation.

**`validations.sql` was explicitly skipped** at the user's request -- not pursued further unless
they bring it up again.

**Confirmed, not guessed**: `DM_PADM_CAMPAIGN_1`'s real DDL uses the OLD status vocabulary
(`DISCOVERED`/`DRAFT`/`READY_FOR_REVIEW`/`COMPLETED`/`REOPENED`) in its `CHECK` constraint --
`padm_spec_alignment_01_schema.sql` (already in this repo) is presumably the migration script
that bridges old DDL to the real running vocabulary (`NEW`/`DRAFT`/`IN_PROGRESS`/
`PENDING_APPROVAL`/`APPROVED`/`REJECTED`). Also confirmed: a "Final sql database queries and
documentation 1.pdf" turned out to be a documentation Excel workbook, not SQL -- its Run Order
tab and Table dictionary are saved at `padm_delivery/docs/PADM_FINAL_DATABASE_DOCUMENTATION_excel_notes.md`,
but that workbook itself uses the OLD status vocabulary and an unrelated file-numbering scheme --
treat it as a useful but stale cross-reference, not current truth.

## 5. Working style that got results in the prior conversation (keep doing this)

- **Never guess at SQL object names, signatures, or column names.** The user has live Snowflake
  access; ask them to run `SHOW PROCEDURES`/`DESCRIBE TABLE`/`SELECT GET_DDL(...)` and paste the
  result back, rather than assuming. Guessed SQL caused real syntax errors earlier.
- When screenshots/photos are the only source, say plainly when something is uncertain rather
  than presenting a guess as confirmed fact. Mark it clearly if you do.
- The user is building this for a demo and wants things to actually work, not just look
  plausible — verify, don't assume.
