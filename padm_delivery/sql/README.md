# sql/ — folder guide

13 files against `DB_RISK.RISK_SBX`. **Run them in the order below, not alphabetically** — these
names don't sort into run order. Each file is self-contained (its own `USE DATABASE`/`USE SCHEMA`)
and says at the top whether it's safe to re-run or run-once only.

| Run order | File | What it does | Re-run safe? |
|---|------|---------------|---------------|
| 1 | `cleanup.sql` | Drops unused legacy NRR/Unwind scaffolding; migrates campaign STATUS to the current vocabulary. | Yes |
| 2 | `schema_alters.sql` | Adds new columns to assumption version, segment, campaign/offer-segment junction, and Signature Page 2 snapshot tables; adds `SEGMENT_KEY` / `CAMPAIGN_SEGMENT_KEY` and the segment natural-key constraint. | Yes |
| 3 | `reference_and_lookup_tables.sql` | Creates + seeds `DM_PADM_ASSUMPTION_DEFINITION` and `DM_PADM_PROSPECT_TYPE_RULE`; creates `DM_PADM_DASHBOARD_ACCESS` (empty) and `DM_PADM_MAILFILE_CELL`. | Yes |
| 4 | `views_assumptions.sql` | Campaign/segment "current assumption" views + the effective-assumption view. | Yes |
| 5 | `views_campaign_offer_and_acm_source.sql` | Current campaign offer view, CDE grid, selection view, ACM campaign-candidate and offer-source views (the mandatory-filter source for Campaign Creation / Pre Signature Page). | Yes |
| 6 | `ems_rate_table_and_segment_calculation_view.sql` | `DM_PADM_EMS_RATE_VERSION` table + the segment-level calculation view (quantity, CPA, booking cost, unwinds). | Yes |
| 7 | `views_signature_page.sql` | Signature Page's two main views (`VW_PADM_SIGNATURE_PAGE_ALL`, `VW_PADM_SIGNATURE_PAGE_LIVE`) and the 60-day dropdown-source view. | Yes |
| 8 | `procedures.sql` | All 8 stored procedures (activate campaign, save campaign/segment assumption, save selection set, activate CDE version, transition status, run calculation, generate Signature Page 2). | Yes |
| 9 | `segment_source_candidate_view.sql` | `VW_PADM_SEGMENT_SOURCE_CANDIDATE`: candidate segments derived from the raw Experian/TransUnion/MAP mailfile tables. | Yes |
| 10 | `fixes.sql` | CPP assumption-level fix; seeds `DM_PADM_SEGMENT_1` from the governed candidate pool; links every campaign to every active segment. | **No — run once** |
| 11 | `pre_signature_detail_table.sql` | `DM_PADM_PRE_SIGNATURE_DETAIL` table (Pre Signature Page's 3 tracking fields). | Yes |
| 12 | `dashboard_access.sql` | Seeds the people allowed to open the dashboard into `DM_PADM_DASHBOARD_ACCESS`. | **No — run once** |
| 13 | `segment_and_assumption_history.sql` | One-time 2026 historical backfill of mailfile cells and campaign CPP assumptions. | **No — run once** |

Superseded and removed from this folder (no longer needed): the old `deploy.sql`, `tables.sql`,
`views.sql`, an earlier `procedures.sql` (a different, now-deleted file — not the current one
above, which happens to share its name), `others.sql`, `incomplete.sql`, and an earlier
`backfill_2026_segments_and_assumptions.sql`. Everything in them that was actually live is now in
the 13 files above, reorganized and with trimmed comments; nothing was dropped (verified by diffing
the old scripts against the new files with comments stripped — identical).

Full detail, kept up to date as a living doc: the Functional Specification doc —
https://claude.ai/artifact/EYMdLmed3ceKpaKrQUxuc4
