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

## 5. Working style that got results in the prior conversation (keep doing this)

- **Never guess at SQL object names, signatures, or column names.** The user has live Snowflake
  access; ask them to run `SHOW PROCEDURES`/`DESCRIBE TABLE`/`SELECT GET_DDL(...)` and paste the
  result back, rather than assuming. Guessed SQL caused real syntax errors earlier.
- When screenshots/photos are the only source, say plainly when something is uncertain rather
  than presenting a guess as confirmed fact. Mark it clearly if you do.
- The user is building this for a demo and wants things to actually work, not just look
  plausible — verify, don't assume.
