# sql/ — folder guide

This folder has two very different kinds of files in it, split into two
folders so they don't get confused with each other:

- **`deploy/`** — the actual PADM deliverable. Run these, in order, against
  `DB_RISK.RISK_SBX`.
- **`reference_from_live_snowflake/`** — captures of the real, pre-existing
  Snowflake schema. These are a reference/verification corpus, **not a
  deploy script** — several are partial captures, scratch/debugging files,
  or already-applied one-time patches. Each file keeps its own note at the
  top on what's confirmed vs. uncertain — don't strip those.

No SQL content was changed in this reorganization — files were only moved and,
inside `deploy/`, given sequential number prefixes for run order.

## `deploy/` — run order

| # | File | What it does |
|---|------|---------------|
| 1 | `01_schema.sql` | Additive schema changes + reference data (idempotent: `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / seed `MERGE`s). |
| 2 | `02_views.sql` | All PADM views, including the fixed `VW_PADM_SIGNATURE_PAGE_LIVE` (offer-driven `LEFT JOIN`) — this is the canonical version; see note below. |
| 3 | `03_procedures.sql` | Core stored procedures (save assumptions, save selections, activate CDE version, transition campaign status, run calculation, generate Signature Page 2). |
| 3b | `03b_activate_INCOMPLETE_DO_NOT_RUN.sql` | **Do not run.** Marked incomplete in its own filename — kept for reference only. |
| 4 | `04_segment_source_candidate_rebuild.sql` | Rebuilds `VW_PADM_SEGMENT_SOURCE_CANDIDATE` from the real Experian/TransUnion mailfile tables. |
| 5 | `05_manual_fixes_and_seeds.sql` | One-time fixes/seeds (CPP override fix, etc.). **Must run after** `04_segment_source_candidate_rebuild.sql` — the file says so explicitly. |
| 6 | `06_pre_signature_detail.sql` | New table for the Pre Signature Page feature (Total Available Volume / Quantity / Owner-Approver tracking). Independent of the others — can run any time after `01_schema.sql`. |

## `reference_from_live_snowflake/` — what's in here

Flat and unrenamed on purpose — several of these filenames (`changes.sql`,
`updates.sql`, `signature_page_2_snapshot.sql`, etc.) are the **real tab names
from the Snowsight/VS Code tree**, kept as-is so they still match what you'd
see live, rather than renamed to something that describes their content.

Known overlaps with `deploy/` worth knowing about:

- **`VW_PADM_SIGNATURE_PAGE_LIVE`** also appears in
  `additional_procedures_and_views.sql` and `new_validations.sql` here — both
  are earlier/historical captures. `new_validations.sql`'s own note already
  says its copy matches `02_views.sql` verbatim. **`deploy/02_views.sql` is
  the canonical, confirmed-fixed version** — don't redeploy from these two.
- **`DM_PADM_CHANGE_EVENT`** in `reference_and_audit_tables.sql` has already
  been corrected in place (`CHANGED_AT`, not `CHANGED_TS`) — this copy is
  current, not stale.
- **`campaign_and_offer_tables.sql`** documents that it's *pre-migration* DDL
  (old `DISCOVERED/DRAFT/READY_FOR_REVIEW/COMPLETED/REOPENED` status
  vocabulary) — the real running app uses the newer vocabulary; see that
  file's own header note. Same caveat applies to `campaign_load_templates.sql`.
- **`wire_credit_bureau_fields.sql`** adds the `CREDIT_BUREAU_MODEL` /
  `CREDIT_BUREAU_SCORE` / `CRS_MODEL` / `NRM` columns that
  `campaign_and_offer_tables.sql`'s snapshot of `DM_PADM_CAMPAIGN_OFFER`
  doesn't have yet — the two are sequential snapshots of the same table, not
  conflicting definitions.

Several files here (`new_validations.sql`, `post_deployment_validations.sql`,
`activation_and_validations.sql`) are debugging/validation scripts, not
deployment DDL — don't run them as part of a deploy.
