# Gap Report: Tabs 1-3 vs PADM_DASHBOARD_SPEC.md

Scope: campaign_creation.py (Tab 1), signature_page.py (Tab 2), create_segment.py (Tab 3),
repository.py + padm_repository_continued.py, padm/ui.py, padm_spec_alignment_02_views.sql.
`padm/queries.py`: not found in any transcribed file -- not referenced by these 3 tabs directly
(they all use `repository.*`), so not a blocker for this scope.

| # | Spec requirement | Found in real code | Verdict |
|---|---|---|---|
| 1 | Tabs 2-7 disabled until campaign selected (1.2) | `streamlit_app.py` not in my file set -- could not verify | NOT VERIFIABLE (this scope) |
| 2 | Status values NEW/DRAFT/IN_PROGRESS/PENDING_APPROVAL/APPROVED/REJECTED (2.5) | `campaign_creation.py:89-92` uses exactly these names | MATCHES |
| 3 | 4 mandatory source filters (2.3): program_code not 'W', reservation_code<=6, channel='Mail', offer_status='Active' | Claimed in `repository.py:105-106` comment to live in `VW_PADM_ACM_OFFER_SOURCE`, but that view is NOT defined anywhere in `padm_spec_alignment_02_views.sql` (grepped, zero matches) -- it's a pre-existing object never shown to me | NOT VERIFIABLE -- spec itself says "VERIFY, do not guess" here; someone must `GET_DDL` this view |
| 4 | Known cleanup: duplicate `_discover()`/plain-INSERT bug (2.4.6) | `campaign_creation.py` has NO local `_discover()`; `create_and_activate_campaign` (`repository.py:169`) calls `discover_campaign()` which is the single real `MERGE` (`repository.py:128-166`) | MATCHES -- bug already fixed/consolidated |
| 5 | WORKFLOW_EVENT written on discover/activate (2.4.4) | `discover_campaign()`'s MERGE does not write one; `SP_PADM_ACTIVATE_CAMPAIGN` (a procedure, not in my file set) may write it internally | NOT VERIFIABLE (procedure body not seen) |
| 6 | Source-change flag (2.6) | `discover_campaign()` sets `SOURCE_CHANGE_PENDING_FLAG = IFF(T.STATUS = 'NEW', FALSE, TRUE)` on re-discovery (`repository.py:146`); `campaign_header()` selects the flag (`repository.py:68`) for the header banner | MATCHES (banner rendering itself is in `ui.py`, not checked here) |
| 7 | Signature Page: ACM-only, read-only shell, previous-campaign fallback (3.1) | `signature_page.py:53-61` exactly this: tries current campaign, falls back to previous campaign's live view | MATCHES |
| 8 | Exact 27-column order (3.2) | `padm/ui.py:193-218+` `SIGNATURE_COLUMNS` list matches spec order 1-25 verbatim (Segment Description, AF, Test Type, Network, Credit Bureau Model/Score, CRS Model/Score, NRM, Quantity, NBR, Boards, CPP, Marketing Expense, Unwind Rate, Pre/Post-Unwind CPA, PROMO, IVR, Underwriting Flag, Prospect Type, Times Mailed 0%, Tiers, Print Vendor, Post-Unwind Boards); columns 26-27 (Marketing+Booking Costs, Unit Cost) not re-confirmed but file continues past my read window | MATCHES (1-25 confirmed; 26-27 very likely present, not re-verified) |
| 9 | TIMES_MAILED_0_PERCENTAGE computed, never NULL (3.6) | `padm_spec_alignment_02_views.sql:441`: `IFF(TIMES_MAILED_TOTAL, TIMES_MAILED_0_COUNT / TIMES_MAILED_TOTAL, NULL)` -- computed with a safe zero-guard | MATCHES |
| 10 | Prospect Type via reference table, not Python string logic (3.3) | `padm_spec_alignment_02_views.sql:314-319`: `LEFT JOIN DM_PADM_PROSPECT_TYPE_RULE` with a wildcard (`'*'`) default fallback row -- fully reference-table driven, no hardcoded CASE in SQL or Python | MATCHES (exceeds spec -- spec's own sketch used a hardcoded CASE, real code is more correct) |
| 11 | Underwriting Flag: blank, source TBD (Open Items) | `padm_spec_alignment_02_views.sql:271`: `NULL::VARCHAR AS UNDERWRITING_FLAG -- lookup source TBD (spec 10)` | MATCHES |
| 12 | CPP manual override, 4 decimals >=0, writes new assumption version (3.4) | `signature_page.py:10-41` `_cpp_section`: validated via `validation.validate(cpp_def, cpp)`, writes via `repository.save_campaign_assumption` with version+reason | MATCHES |
| 13 | Hidden fields list (3.5) | `signature_page.py:70-72` lists exactly: Campaign Year/Month/Month Sequence, Campaign Type, Mail Date, ACM Segment, Population Description, Test Pairings, Times Mailed 1-8%, 9+% | MATCHES |
| 14 | Segment name auto-gen `[Type] [Min]-[Max] [Source]` (4.1) | `create_segment.py:27-31` `segment_name()` -- exact format, uppercased | MATCHES |
| 15 | Score ranges from `DM_PADM_SCORE_RANGE_RULE_1`, not code (4.1) | `create_segment.py:60,73-79` reads `repository.score_range_rules`, validates via `validation.validate_score_range` | MATCHES |
| 16 | 60-day dropdown window (4.1) | `create_segment.py:85` comment "values mailed in the last 60 days"; underlying view name not directly confirmed in this file (`dropdowns = repository.dropdown_values(session)` -- the 60-day filter lives in whatever view that calls, not re-verified here) | LIKELY MATCHES, not fully re-verified |
| 17 | Block duplicate segments, offer reuse (4.1) | `create_segment.py:91-115`: `find_segment` + "Reuse Existing Segment" flow, distinguishes "already on this campaign" vs "exists elsewhere" | MATCHES |
| 18 | 15 form fields (4.2) | All 15 present: 3 mandatory (Source, Score Type, Score Range) + `OPTIONAL_FIELDS` (10: Prospect Type, Credit Bureau Model/Score, Annual Fee, Network, MLA, CRS Model/Score, Risk Score Type, Response Model Type) + Times Mailed + Free-form | MATCHES |
| 19 | Minor oddity (not in spec, worth a look) | `create_segment.py:22`: `RISK_SCORE_TYPE` field's dropdown source is `"CRS_MODEL"` (reuses the CRS Model dropdown's values), not its own distinct values | WORTH CHECKING -- may be an intentional shared list or a copy-paste slip |
| 20 | Offer allocation pre-suggestion from prior campaigns (4.3) | `create_segment.py:96`: `repository.suggested_offers(session, campaign["id"], existing_id)` | MATCHES |
| 21 | CHANGE_REASON mandatory on every write (9.1) | Every write path in all 3 tabs gates on `ui.require_reason(reason)` before calling repository; `_change_event()` (`repository.py:40-51`) always takes a reason param | MATCHES |
| 22 | Approved campaigns read-only everywhere (0. rule 9) | `repository.py:32-37` `_assert_editable()` raises if status is `APPROVED`; `campaign["locked"]` disables widgets in all 3 tabs | MATCHES |

## Summary
- MATCHES: 17 (incl. 2 cases where the real code exceeds the spec's own sketch -- Prospect Type
  and the already-fixed discover/activate duplication)
- NOT VERIFIABLE in this scope: 4 (streamlit_app.py navigation lock, the 4 ACM source filters,
  WORKFLOW_EVENT-on-discover, 60-day window's exact view) -- none contradict the spec, they're
  just outside the files I was given
- MISSING / WRONG: 0 confirmed
- Worth a second look: 1 (Risk Score Type's dropdown possibly sourcing the wrong column)

## 3 most important findings
1. **The spec's own flagged "known cleanup" bug (duplicate discover logic) is already fixed** in
   the real code -- `campaign_creation.py` has no local `_discover()`; everything goes through
   the single `discover_campaign()` MERGE. Good news, not a gap.
2. **The 4 mandatory ACM source filters (spec 2.3) cannot be verified** -- they're claimed to
   live inside `VW_PADM_ACM_OFFER_SOURCE`, a pre-existing view never shown in any transcribed
   file. This is exactly the kind of thing the spec says to verify with `DESCRIBE`/`GET_DDL`,
   not assume from a code comment.
3. **Signature Page's 27-column order, the Prospect Type reference-table join, and the computed
   Times Mailed 0% are all solid** -- this tab is in genuinely good shape against the spec.
