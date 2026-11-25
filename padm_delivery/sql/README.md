# sql/ — folder guide

13 files, run in numeric order against `DB_RISK.RISK_SBX`. Each file is self-contained (its own
`USE DATABASE`/`USE SCHEMA`) and says at the top whether it's idempotent or run-once.

| # | File | What it does | Re-run safe? |
|---|------|---------------|---------------|
| 01 | `01_legacy_cleanup_and_status_migration.sql` | Drops unused legacy NRR/Unwind scaffolding; migrates campaign STATUS to the current vocabulary. | Yes |
| 02 | `02_schema_alters.sql` | Adds new columns to assumption version, segment, campaign/offer-segment junction, and Signature Page 2 snapshot tables; adds `SEGMENT_KEY` / `CAMPAIGN_SEGMENT_KEY` and the segment natural-key constraint. | Yes |
| 03 | `03_reference_and_lookup_tables.sql` | Creates + seeds `DM_PADM_ASSUMPTION_DEFINITION` and `DM_PADM_PROSPECT_TYPE_RULE`; creates `DM_PADM_DASHBOARD_ACCESS` (empty) and `DM_PADM_MAILFILE_CELL`. | Yes |
| 04 | `04_views_assumptions.sql` | Campaign/segment "current assumption" views + the effective-assumption view. | Yes |
| 05 | `05_views_campaign_offer_and_acm_source.sql` | Current campaign offer view, CDE grid, selection view, ACM campaign-candidate and offer-source views (the mandatory-filter source for Campaign Creation / Pre Signature Page). | Yes |
| 06 | `06_ems_rate_table_and_segment_calculation_view.sql` | `DM_PADM_EMS_RATE_VERSION` table + the segment-level calculation view (quantity, CPA, booking cost, unwinds). | Yes |
| 07 | `07_views_signature_page.sql` | Signature Page's two main views (`VW_PADM_SIGNATURE_PAGE_ALL`, `VW_PADM_SIGNATURE_PAGE_LIVE`) and the 60-day dropdown-source view. | Yes |
| 08 | `08_procedures.sql` | All 8 stored procedures (activate campaign, save campaign/segment assumption, save selection set, activate CDE version, transition status, run calculation, generate Signature Page 2). | Yes |
| 09 | `09_segment_source_candidate_view.sql` | `VW_PADM_SEGMENT_SOURCE_CANDIDATE`: candidate segments derived from the raw Experian/TransUnion/MAP mailfile tables. | Yes |
| 10 | `10_one_time_fixes_run_once.sql` | CPP assumption-level fix; seeds `DM_PADM_SEGMENT_1` from the governed candidate pool; links every campaign to every active segment. | **No — run once** |
| 11 | `11_pre_signature_detail_table.sql` | `DM_PADM_PRE_SIGNATURE_DETAIL` table (Pre Signature Page's 3 tracking fields). | Yes |
| 12 | `12_seed_dashboard_access_run_once.sql` | Seeds the people allowed to open the dashboard into `DM_PADM_DASHBOARD_ACCESS`. | **No — run once** |
| 13 | `13_backfill_2026_segment_and_assumption_history_run_once.sql` | One-time 2026 historical backfill of mailfile cells and campaign CPP assumptions. | **No — run once** |

Superseded and removed from this folder (no longer needed): `deploy.sql`, `tables.sql`,
`views.sql`, `procedures.sql`, `others.sql`, `incomplete.sql`, `backfill_2026_segments_and_assumptions.sql`.
Everything in them that was actually live is now in files 01–11 and 13 above, reorganized and
with trimmed comments; nothing was dropped (see the delivery notes for how that was verified).

Full detail, kept up to date as a living doc: the Functional Specification doc —
https://claude.ai/artifact/EYMdLmed3ceKpaKrQUxuc4
