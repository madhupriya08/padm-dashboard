# PADM Sign-Off Dashboard

A Streamlit-in-Snowflake app that replaces the manual Excel-based Signature Page sign-off process
for monthly direct-mail credit-card acquisition campaigns. Full background and page-by-page
behavior: the Functional Specification doc — https://claude.ai/artifact/EYMdLmed3ceKpaKrQUxuc4

## What's in this folder

```
streamlit_app.py       entry point
padm/                  app code
  db.py, exports.py, formulas.py, repository.py, ui.py, validation.py
  tabs/                 one file per tab (8 tabs)
sql/                    deployment scripts, run in numeric order (see sql/README.md)
docs/                   data dictionary, lineage notes, reference material
```

## Deploying from scratch

### 1. Run the SQL

In Snowsight, run every file in `sql/` **in numeric order**, `01_...` through `13_...`, against
`DB_RISK.RISK_SBX`. Each file is self-contained (its own `USE DATABASE`/`USE SCHEMA`) and says at
the top whether it's safe to re-run or run-once only — see `sql/README.md` for the full list.
Three of the thirteen are one-time operations (`10_one_time_fixes_run_once.sql`,
`12_seed_dashboard_access_run_once.sql`, `13_backfill_..._run_once.sql`) — skip any of those
you've already run on this schema.

Before running `12_seed_dashboard_access_run_once.sql`, edit it to list the real people who should
have access (see Access Control below) — it ships with the 6 names from this engagement's own
setup as an example.

### 2. Create the Streamlit app

In Snowsight, create a plain Streamlit app (not a CLI-managed "Project" — one created with
`snowflake.yml`/`requirements.txt`/`pyproject.toml` needs outbound network access to pip-install
packages, which most accounts don't have enabled, and will fail with a "Failed to retrieve
packages... External Access Integration" error). Paste `streamlit_app.py` and the whole `padm/`
folder (keeping the exact nesting: `padm/db.py` etc. at the top level, `padm/tabs/*.py` one level
down) into the app's folder.

### 3. Add packages

In the Streamlit app editor, open **Packages** (in the toolbar, not the file tree) and add:

- `pandas`
- `openpyxl` — used by `padm/exports.py`'s Excel export and `padm/tabs/segment_viewer.py`'s CDE
  file upload

`snowflake-snowpark-python` is available by default and doesn't need adding. All three come from
Snowflake's own Anaconda channel, so no outbound network access is required.

### 4. Point the app at the right schema

`padm/db.py`'s `SCHEMA` constant and every SQL script assume `DB_RISK.RISK_SBX`. If you're
deploying against a different database/schema, update both before running anything.

## Access control

Only people listed in `DM_PADM_DASHBOARD_ACCESS` (with `ACTIVE_FLAG = TRUE`) see the real
dashboard; everyone else gets a plain "work in progress" message. This is checked against
`CURRENT_USER()`, which on this account is the person's email address.

Grant or revoke access with a plain `UPDATE`/`INSERT` — no redeploy needed:

```sql
-- Revoke
UPDATE DM_PADM_DASHBOARD_ACCESS SET ACTIVE_FLAG = FALSE WHERE EMAIL = 'name@creditone.com';

-- Restore
UPDATE DM_PADM_DASHBOARD_ACCESS SET ACTIVE_FLAG = TRUE WHERE EMAIL = 'name@creditone.com';

-- Add someone new
INSERT INTO DM_PADM_DASHBOARD_ACCESS (EMAIL) VALUES ('new.person@creditone.com');
```

This only controls what renders once the app is opened. Who can even *see* the app's source files
in Snowsight is a separate, folder-level sharing setting, set from the workspace folder's own
Share button — not something controlled from code.

## Known open items

A handful of business decisions are still open (Campaign Type derivation logic, a few reference
tables not yet wired in, the final role/permission matrix, and others) — see Section 7 of the
Functional Specification for the full, current list.
