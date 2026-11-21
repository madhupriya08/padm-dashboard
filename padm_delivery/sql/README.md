# sql/ — folder guide

6 files, all flat in this folder, no comments in any of them (plain SQL only
— all notes below live here in this README instead).

## Run this

| File | What it does |
|------|---------------|
| `deploy.sql` | The complete PADM deployment script, run top to bottom. Schema (tables/columns/seed data), views, procedures, the `VW_PADM_SEGMENT_SOURCE_CANDIDATE` rebuild, one-time fixes/seeds, and the Pre Signature Page tracking table, in that order. Idempotent throughout (`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `CREATE OR REPLACE VIEW`/`PROCEDURE`), except the one-time-fixes portion (CPP override fix, segment sync), which should only be run once. |

## Do not run

| File | Why not |
|------|---------|
| `incomplete.sql` | Stops partway through `SP_PADM_ACTIVATE_CAMPAIGN` — missing the rest of the procedure body. Kept for reference only, not part of `deploy.sql`. |

## Reference only (captures of the real, pre-existing Snowflake schema)

Not deployment scripts — don't run these as part of a deploy. Each is a
combination of multiple real-schema captures, grouped by object type.

| File | Covers |
|------|--------|
| `tables.sql` | All real `CREATE TABLE` captures (campaign/offer, segment/allocation, assumptions, selection, reference/audit, history, calculation/snapshot, CDE/EMS tables). |
| `views.sql` | All real `CREATE VIEW` captures (calculation views, current-state views, CDE grid, ACM source views). |
| `procedures.sql` | All real `CREATE PROCEDURE` captures (activate campaign, save campaign assumption, activate CDE version, save segment assumption, save selection set, run calculation, generate Signature Page 2). |
| `others.sql` | Everything else: one-time `ALTER`/`UPDATE`/`DELETE` patches already applied live, campaign-load `MERGE` templates, debugging/exploration queries, and post-deployment validation checks. |

Known overlaps worth knowing about:

- **`VW_PADM_SIGNATURE_PAGE_LIVE`** is defined more than once across
  `procedures.sql` and `others.sql` (earlier/historical copies).
  **`deploy.sql`'s version is the canonical, confirmed-fixed one** — don't
  redeploy from the others.
- **`DM_PADM_CHANGE_EVENT`** in `tables.sql` has already been corrected in
  place (`CHANGED_AT`, not `CHANGED_TS`) — this copy is current, not stale.
- `tables.sql` has a `DM_PADM_CAMPAIGN_1` with a STATUS check constraint
  using the OLD status vocabulary
  (`DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED/REOPENED`) — pre-migration DDL;
  the real running app uses the newer vocabulary. Same caveat applies to the
  `discover_campaign()`-style `MERGE` template in `others.sql`.
- `others.sql` adds `CREDIT_BUREAU_MODEL` / `CREDIT_BUREAU_SCORE` /
  `CRS_MODEL` / `NRM` columns to `DM_PADM_CAMPAIGN_OFFER` that `tables.sql`'s
  earlier snapshot of that same table doesn't have yet — the two are
  sequential snapshots, not conflicting definitions.
