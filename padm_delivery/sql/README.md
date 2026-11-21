# sql/ — folder guide

Two folders, two different purposes:

- **`deploy/`** — the actual PADM deliverable.
- **`reference_from_live_snowflake/`** — captures of the real, pre-existing
  Snowflake schema. Reference/verification material, **not a deploy script**.

## `deploy/`

| File | What it does |
|------|---------------|
| `padm_deploy.sql` | The complete deployment script, run top to bottom. Combines schema (tables/columns/seed data), views, procedures, the `VW_PADM_SEGMENT_SOURCE_CANDIDATE` rebuild, one-time fixes/seeds, and the Pre Signature Page tracking table, in that run order, each section divided with its own header. Idempotent throughout (`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `CREATE OR REPLACE VIEW`/`PROCEDURE`), except the one-time-fixes section, which should only be run once. |
| `03b_activate_INCOMPLETE_DO_NOT_RUN.sql` | **Do not run.** Marked incomplete in its own filename — kept for reference only, not part of `padm_deploy.sql`. |

## `reference_from_live_snowflake/`

Four files, grouped by object type, each a combination of multiple real-schema
captures (every section keeps its own divider naming which capture it came
from, and any completeness/uncertainty notes that capture had):

| File | Covers |
|------|--------|
| `reference_tables.sql` | All real `CREATE TABLE` captures (campaign/offer, segment/allocation, assumptions, selection, reference/audit, history, calculation/snapshot, CDE/EMS tables). |
| `reference_views.sql` | All real `CREATE VIEW` captures (calculation views, current-state views, CDE grid, ACM source views). |
| `reference_procedures.sql` | All real `CREATE PROCEDURE` captures (activate campaign, save campaign assumption, activate CDE version, save segment assumption, save selection set, run calculation, generate Signature Page 2). |
| `reference_patches_and_validations.sql` | Everything else: one-time `ALTER`/`UPDATE`/`DELETE` patches already applied live, campaign-load `MERGE` templates, debugging/exploration queries, and post-deployment validation checks. Not deployment DDL — nothing here should be re-run as part of a deploy. |

Known overlaps worth knowing about:

- **`VW_PADM_SIGNATURE_PAGE_LIVE`** appears in `reference_views.sql`-adjacent
  captures too (inside `reference_procedures.sql`'s and
  `reference_patches_and_validations.sql`'s sections) as earlier/historical
  copies. **`deploy/padm_deploy.sql`'s version (section 2, Views) is the
  canonical, confirmed-fixed one** — don't redeploy from the others.
- **`DM_PADM_CHANGE_EVENT`** in `reference_tables.sql`'s
  `reference_and_audit_tables.sql` section has already been corrected in
  place (`CHANGED_AT`, not `CHANGED_TS`) — this copy is current, not stale.
- **`campaign_and_offer_tables.sql`**'s section documents *pre-migration* DDL
  (old `DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED/REOPENED` status
  vocabulary) — the real running app uses the newer vocabulary. Same caveat
  applies to the `campaign_load_templates.sql` section in
  `reference_patches_and_validations.sql`.
- The `wire_credit_bureau_fields.sql` section adds the `CREDIT_BUREAU_MODEL` /
  `CREDIT_BUREAU_SCORE` / `CRS_MODEL` / `NRM` columns that
  `campaign_and_offer_tables.sql`'s snapshot of `DM_PADM_CAMPAIGN_OFFER`
  doesn't have yet — the two are sequential snapshots of the same table, not
  conflicting definitions.
