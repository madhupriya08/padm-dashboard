# sql/ — folder guide

6 files, all flat in this folder, no comments in any of them (plain SQL only
— all notes below live here in this README instead).

## Run this

| File | What it does |
|------|---------------|
| `deploy_run_this.sql` | The complete PADM deployment script, run top to bottom. Schema (tables/columns/seed data), views, procedures, the `VW_PADM_SEGMENT_SOURCE_CANDIDATE` rebuild, one-time fixes/seeds, and the Pre Signature Page tracking table, in that order. Idempotent throughout (`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `CREATE OR REPLACE VIEW`/`PROCEDURE`), except the one-time-fixes portion (CPP override fix, segment sync), which should only be run once. |

## Do not run

| File | Why not |
|------|---------|
| `do_not_run_incomplete.sql` | Stops partway through `SP_PADM_ACTIVATE_CAMPAIGN` — missing the rest of the procedure body. Kept for reference only, not part of `deploy_run_this.sql`. |

## Reference only (captures of the real, pre-existing Snowflake schema)

Not deployment scripts — don't run these as part of a deploy. Each is a
combination of multiple real-schema captures, grouped by object type.

| File | Covers |
|------|--------|
| `reference_tables.sql` | All real `CREATE TABLE` captures (campaign/offer, segment/allocation, assumptions, selection, reference/audit, history, calculation/snapshot, CDE/EMS tables). |
| `reference_views.sql` | All real `CREATE VIEW` captures (calculation views, current-state views, CDE grid, ACM source views). |
| `reference_procedures.sql` | All real `CREATE PROCEDURE` captures (activate campaign, save campaign assumption, activate CDE version, save segment assumption, save selection set, run calculation, generate Signature Page 2). |
| `reference_other.sql` | Everything else: one-time `ALTER`/`UPDATE`/`DELETE` patches already applied live, campaign-load `MERGE` templates, debugging/exploration queries, and post-deployment validation checks. |

Known overlaps worth knowing about:

- **`VW_PADM_SIGNATURE_PAGE_LIVE`** is defined more than once across
  `reference_procedures.sql` and `reference_other.sql` (earlier/historical
  copies). **`deploy_run_this.sql`'s version is the canonical, confirmed-fixed
  one** — don't redeploy from the others.
- **`DM_PADM_CHANGE_EVENT`** in `reference_tables.sql` has already been
  corrected in place (`CHANGED_AT`, not `CHANGED_TS`) — this copy is current,
  not stale.
- `reference_tables.sql` has a `DM_PADM_CAMPAIGN_1` with a STATUS check
  constraint using the OLD status vocabulary
  (`DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED/REOPENED`) — pre-migration DDL;
  the real running app uses the newer vocabulary. Same caveat applies to the
  `discover_campaign()`-style `MERGE` template in `reference_other.sql`.
- `reference_other.sql` adds `CREDIT_BUREAU_MODEL` / `CREDIT_BUREAU_SCORE` /
  `CRS_MODEL` / `NRM` columns to `DM_PADM_CAMPAIGN_OFFER` that
  `reference_tables.sql`'s earlier snapshot of that same table doesn't have
  yet — the two are sequential snapshots, not conflicting definitions.
