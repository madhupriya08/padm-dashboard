# PADM Sign-Off Dashboard — Reference

*Built 2026-11-19. Paste this into Confluence and edit freely — nothing here is generated or locked.*

A Streamlit-in-Snowflake app that replaces the manual Excel sign-off process for monthly
direct-mail credit-card campaigns — 7 tabs, one campaign at a time, every write versioned and
audited.

**Quick facts**: 7 workflow tabs · 26 of 27 real SQL files captured · 12 files changed this
session · 1 crash bug found and fixed (`streamlit_app.py`).

The real, running code is the `padm/` package (`padm/tabs/*.py`, `padm/repository.py`,
`padm/ui.py`, `padm/formulas.py`). A separate `app/` tree exists in the project but is **dead
code** — not imported by `streamlit_app.py` — kept only for historical reference.

---

## Architecture

Two source systems feed PADM's own tables, which the dashboard reads — the dashboard itself
never queries the source systems directly except through governed views.

```
CSTONE_BIZ.REFERENCE                 PADM governed views                PADM's own tables           7 tabs
(not owned by PADM)
─────────────────────                ────────────────────                ──────────────────           ─────
T_ACM_CAMPAIGN_OFFERS,  ────────▶    VW_PADM_ACM_OFFER_SOURCE
T_ACM_PROGRAMS          ────────▶    VW_PADM_ACM_CAMPAIGN_CANDIDATE ───▶  DM_PADM_CAMPAIGN_1    ───▶  read +
                                                                          + CAMPAIGN_OFFER,            write,
T_EXPERIAN_MAILFILE,    ────────▶    VW_PADM_SEGMENT_SOURCE_CANDIDATE    OFFER_PROFILE                this
T_TRANSUNION_MAILFILE                (rebuilt this session —        ───▶ DM_PADM_SEGMENT_1,           column
                                       real score bands)                 CAMPAIGN_SEGMENT_1,           only
                                                                          OFFER_SEGMENT_ALLOCATION

                                                                          Assumptions, Selections,
                                                                          CDE — all versioned,
                                                                          never overwritten
```

Key properties:
- **Two-schema design** — Working Schema (`DB_RISK.RISK_SBX`) is where every tab reads and
  writes. An Archive Schema concept exists for finalized, read-only history per the sign-off
  proposal.
- **Versioned, never overwritten** — assumptions, selections, allocations and segments are all
  append-only version tables; a save retires the prior row, never deletes it.
- **One audit trail** — `DM_PADM_CHANGE_EVENT` is written to by every write-path across every
  tab, the single place to answer "who changed what, and why."

### Tab order

```
1. Campaign Creation → 2. Signature Page → 3. Create Segment → 4. Campaign Assumptions
→ 5. Population Description → 6. Segment Viewer → 7. Signature Page 2
```

### Campaign status flow

```
NEW → DRAFT → IN_PROGRESS → PENDING_APPROVAL → APPROVED  (terminal — no path back)
                   ▲                 │
                   └── REJECTED ◀────┘
```

Tab order mirrors the physical sign-off sheet's own structure. Approval is a deliberate dead
end: only Reject has a return path, confirmed from the real procedure's own transition rules.

---

## What changed this session

Grouped by what was asked for, in the order it happened. Every item below is committed and
pushed to `main` on GitHub (see **Resources** below).

### CPP relocation
> *"I want to remove cpp from signature page... ideally it should be in both campaign
> assumptions and segment viewer page"*

Root cause: CPP already had a segment-override column and was marked `ENTERED_ON='BOTH'`, but
its `ASSUMPTION_LEVEL` was `'CAMPAIGN'` instead of `'CAMPAIGN_SEGMENT'` — the one value stopping
the generic, definitions-driven UI from showing it as a segment override. Fixed the data,
removed the redundant manual-override section (and the 3 Offers/Quantity/Segmented-offers
metric tiles) from Signature Page.

**Files**: `sql/deploy/01_schema.sql`, a live `UPDATE` on `DM_PADM_ASSUMPTION_DEFINITION`,
`padm/tabs/signature_page.py`

### Signature Page: one row per segment
> *"no need to show offer details in signature page"*

Collapsed the page to one row per segment. Along the way, found and fixed a real pre-existing
bug, not just a cosmetic one: `VW_PADM_SIGNATURE_PAGE_LIVE`'s calculated columns are already
segment-level (its calculation join has no offer dimension), so a segment with 5 offers
repeated the same numbers 5 times — the old flat display's GRAND TOTAL was inflated by each
segment's offer count. Offer-level fields that genuinely vary between offers in a segment (Test
Type, Promo, IVR) now show as a distinct-value summary instead of silently picking one.

**Files**: `padm/ui.py` (new `collapse_to_segment()`), `padm/tabs/signature_page.py`

### Create Segment: trimmed to spec, bug fixes, real historical segments
> Multiple asks: mandatory-field asterisks, TransUnion missing from the bureau dropdown, LIFT
> missing from score type, *"only the fields mentioned under segment creation in sign-off
> proposal doc is needed"*, and *"all these campaigns until Nov are already completed so there
> should be segments available."*

- Asterisks added; `source_names()` fixed — was silently dropping a bureau with zero segments
  created yet.
- Optional fields trimmed to exactly the sign-off proposal's Segment Creation list; Free-form
  field removed (belongs to a different section of that document).
- Bureau Score Type now cascades on the selected Source; LIFT shown for both bureaus per
  explicit choice (real data dictionary confirms `LIFT_SCORE` exists only in
  `T_EXPERIAN_MAILFILE` — flagged, not hidden).
- **Root cause of the "no segments" question**: campaigns already had a real
  discover-from-source mechanism (`discover_campaign()`); segments never did. Added
  `discover_segments()` + a "Sync governed segments from source" button, and rebuilt
  `VW_PADM_SEGMENT_SOURCE_CANDIDATE` after its source table (`DM_PADM_TR_MAILFILE_NORMALIZED`)
  turned out not to be part of this project — now reads directly from `T_EXPERIAN_MAILFILE` /
  `T_TRANSUNION_MAILFILE`, banding the raw Vantage/LIFT scores against
  `DM_PADM_SCORE_RANGE_RULE_1`.

**Files**: `padm/tabs/create_segment.py`, `padm/repository.py`,
`sql/deploy/04_segment_source_candidate_rebuild.sql`, `sql/deploy/05_manual_fixes_and_seeds.sql`

### Many-to-many offer ↔ segment allocation
> *"it is many to many... let's not fix the score range for this but ... population description
> is given to a set of segments not just one"*

Explicit decision confirmed: a shared offer's full numbers count in **each** segment it belongs
to (Grand Total can exceed distinct offers mailed — by design, not a bug). The old hard block
("An offer can only be assigned to one segment") is gone; the uniqueness guard moved from
per-offer to per-(offer, segment) pair.

**Files**: `padm/repository.py`, `padm/tabs/create_segment.py`,
`padm/tabs/population_description.py`

### Campaign Assumptions simplified to campaign-level only
> *"cpp, unitcost, rate adjustment is needed as campaign level assumptions thats it for this
> page... remove segment assumptions in this page"*

Removed the Segment-level assumptions section — Segment Viewer is now the single place to edit
segment-level overrides. Flagged, not silently dropped: `NBR`'s segment override has nowhere
left to be edited (its definition row is marked `ENTERED_ON='ASSUMPTIONS'`, not Segment Viewer)
— open question if that's still needed.

**Files**: `padm/tabs/campaign_assumptions.py`

### Population Description rebuilt to segment-first
> *"the current page looks overwhelming... many to many links between segment to offer should
> be done here... select segment first and edit or save offers and give a population
> description to set of segments"*

Replaced the Annual-Fee/Score-Band grouped layout with: pick a **set** of segments, give them
one shared label, each still gets its own offer multiselect below. Label pre-fills a suggested
default (`Sub-Total <source or MLA> <band>`) built from the segment's own fields — matches the
real Signature Page export's naming pattern, not an exact copy (no governed table exists for
the "Core"/"Expansion" wording seen there).

**Files**: `padm/tabs/population_description.py`

### Segment Viewer: prepopulation, 3-color grid, Excel-aligned layout
> A long list, including *"segment level assumptions should be prepopulated with campaign
> latest assumptions"*, *"previous campaign's selections should get populated... with non-zero
> values highlighted in yellow"*, *"I need the alignment of the grids same as shown in segment
> excel"*, and *"only highlighted non-zero values should be shown."*

- CPP/Unit Cost now prefill from the campaign's current assumption when no segment override
  exists.
- Selection grid highlighting extended from 1 color to 3: **blue** = unsaved edit, **green** =
  currently saved, **yellow** = prior campaign had a value.
- Rebuilt the 22-grid calculated section into side-by-side rows matching the real
  `Segment.xlsx` provided — Universe-vs-Selected pairs that were already being calculated but
  never displayed are now visible.
- Every calculated grid now shows only non-zero values — zero/null cells render blank, matching
  the Excel convention.

**Files**: `padm/tabs/segment_viewer.py`, `padm/formulas.py`, `padm/ui.py`

### streamlit_app.py — found a real crash bug while polishing it
> *"give the streamlit_app.py file in a creative and professional way without changing the main
> functionalities"*

`main()` read campaign data as a dict with made-up keys (`campaign["name"]`,
`campaign["mail_date"]`) — the real function returns a DataFrame with different column names,
so this would have thrown a `KeyError` the moment a campaign was selected. It also rendered a
second header above the tabs while every tab already renders its own. Both fixed by routing
through the already-correct `ui.campaign_context()`; cosmetic polish (branding bar, workflow
pills, landing screen) is additive only.

**Files**: `streamlit_app.py`

---

## Demo Q&A prep

The questions asked directly, plus the ones most likely to come up alongside them.

**Q: Did we fetch any data from Vivian's code, and from where exactly?**
Not as a live data source — her NRR/Unwinds SQL scripts are legacy ETL reference, not tables the
app queries. What's confirmed: `VW_PADM_SEGMENT_SOURCE_CANDIDATE`'s segment-naming logic (the
MLA / PCO / PCL / PDCL / ABDN / REMAIL suffixes) matches her classification scheme conceptually
— but the actual score-band/prospect-type classification happens upstream, in whatever already
populates `T_EXPERIAN_MAILFILE` / `T_TRANSUNION_MAILFILE`'s `PROSPECT_TYPE`/
`PRESCREEN_VANTAGE_*` columns, not inline in her script. Her Unwinds_optimized scripts are
background for the Unwind Rate assumption only.

**Q: Where did all the campaign and segment information come from?**
Campaigns: `discover_campaign()` merges `VW_PADM_ACM_CAMPAIGN_CANDIDATE` (ACM offer data,
eligibility-filtered) into `DM_PADM_CAMPAIGN_1` — this already existed. Segments: historically
only ever created by hand through the Create Segment form. This session added the equivalent
sync for segments — `discover_segments()`, sourced from `VW_PADM_SEGMENT_SOURCE_CANDIDATE`,
which reads the real Experian/TransUnion mailfile tables directly.

**Q: Are segment-level assumptions stored anywhere for completed campaigns?**
Yes — `DM_PADM_SEGMENT_ASSUMPTION_VERSION` is fully versioned and append-only; nothing is ever
deleted. A completed campaign's segment assumptions stay queryable forever via "Version
history." Once a campaign reaches `APPROVED`, the whole app goes read-only
(`campaign["locked"]`), but the underlying data isn't purged — only editing is blocked.

**Q: What happens once a campaign is approved — can it still be changed?**
No, by design. The confirmed real status flow only allows `REJECTED → DRAFT` — there's no
procedure path from `APPROVED` back to editable. Every input across every tab already disables
itself automatically (`disabled=locked`), and the header shows a lock banner. A "reopen an
approved campaign as a new version" workflow doesn't exist today — it would be new scope, not a
toggle.

**Q: Can the same offer really belong to two different segments?**
Yes, as of this session, by explicit decision. Its full Quantity/Boards/Marketing Expense etc.
count independently in each segment — so a campaign's Grand Total can be larger than the true
count of distinct offers mailed. That's expected, not a double-counting bug.

**Q: Is LIFT a real option for both Experian and TransUnion?**
It shows in the dropdown for both, per an explicit UI decision. Technically, Credit One's own
data dictionary confirms `LIFT_SCORE` exists only in `T_EXPERIAN_MAILFILE` — TransUnion has no
real score-band data behind it yet, so creating a TransUnion + LIFT segment will correctly show
"no active score-range rules" until real data is added.

**Q: Why do some Signature Page / Segment Viewer cells show blank instead of 0?**
Intentional, matching the real `Segment.xlsx` convention — only non-zero values are shown on
calculated grids. The Selection % input grid is unchanged (it never did this).

**Q: What's the difference between Working Version and Final Version on Segment Viewer?**
Real, confirmed difference, not a redundant toggle — the sign-off proposal's own
Working-vs-Final table says so. Working Version = Selection % × Universe Post-EMS (your
estimate). Final Version swaps in actual mailed quantities from `DM_PADM_MAILFILE_CELL`
(sourced from the real Experian/TransUnion mail files) once they exist.

---

## Still open

| Item | Status | Notes |
|---|---|---|
| 3-month purge for `DM_PADM_SELECTION_WORKING` | Deferred | Needs a scheduled Snowflake `TASK`. `DM_PADM_SELECTION_SET`/`_EVENT` (the real audit trail) must never be touched by it. |
| `validations.sql` | Skipped | Explicitly skipped at your request — the one file of ~27 real ones never captured. |
| Offer-to-segment auto-match from offer attributes | Not pursued | Would need confirming what `CREDIT_BUREAU_MODEL`/`SCORE` mean on a real offer row. Manual/SQL seeding used instead for the demo. |
| Reopen an approved campaign as a new version | Needs confirmation | No path exists in the real procedure today — flagged as new scope, not yet confirmed wanted. |

---

## Resources

- **GitHub repository** — every file, table definition, and this page's source are committed
  and pushed to `main`: [github.com/madhupriya08/padm-dashboard](https://github.com/madhupriya08/padm-dashboard)
- **Data lineage workbook** — field-by-field source tracing for all 7 tabs — one sheet each,
  every element mapped to its real table/view/procedure and join logic:
  `padm_delivery/docs/PADM_Data_Lineage.xlsx`
- **Build spec (updated)** — the original build specification, revised section-by-section to
  match this session's decisions: `padm_delivery/docs/PADM_DASHBOARD_SPEC.md`
