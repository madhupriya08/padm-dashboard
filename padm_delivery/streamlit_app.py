"""PADM Sign-Off Dashboard — entry point.

Renders the 8-tab workflow: Campaign Creation, Pre Signature Page, Signature Page,
Create Segment, Campaign Assumptions, Population Description, Segment Viewer,
Signature Page 2. The selected campaign lives in st.session_state["campaign_id"]
and is shared by every tab.

Campaign data goes through ui.campaign_context() (not repository.campaign_header() directly --
that returns a raw DataFrame with real column names like CAMPAIGN_DISPLAY_NAME and
CURRENT_WORKING_VERSION_NUMBER, not a dict with keys like "name"/"mail_date"/"version").
This file renders no header of its own -- each tab's own header (via ui.require_campaign() ->
ui.header_bar()) stays the single source of truth for campaign status/version/lock state.
What's here is purely the page shell, branding bar, and the landing screen.
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session

from padm import ui
from padm.db import SCHEMA
from padm.tabs import (
    campaign_assumptions,
    campaign_creation,
    create_segment,
    population_description,
    pre_signature_page,
    segment_viewer,
    signature_page,
    signature_page_2,
)

st.set_page_config(page_title="PADM Sign-Off Dashboard", page_icon=":material/fact_check:", layout="wide")

TABS = [
    ("Campaign Creation", ":material/add_box:", campaign_creation),
    ("Pre Signature Page", ":material/checklist:", pre_signature_page),
    ("Signature Page", ":material/description:", signature_page),
    ("Create Segment", ":material/group_add:", create_segment),
    ("Campaign Assumptions", ":material/tune:", campaign_assumptions),
    ("Population Description", ":material/pie_chart:", population_description),
    ("Segment Viewer", ":material/table_view:", segment_viewer),
    ("Signature Page 2", ":material/task_alt:", signature_page_2),
]

st.markdown("""
<style>
:root {
    --padm-navy: #0b1f3a; --padm-blue: #103a63; --padm-teal: #0e5a7a;
    --padm-teal-light: #e6f3f7; --padm-ink: #1a2b3c; --padm-muted: #5a6b7a;
    --padm-border: #dde5ec;
}
.padm-brand { padding: 1.1rem 1.5rem; border-radius: 14px; margin-bottom: 1rem;
    background: linear-gradient(120deg, var(--padm-navy) 0%, var(--padm-blue) 55%, var(--padm-teal) 100%);
    box-shadow: 0 4px 18px rgba(10, 30, 60, 0.25); color: #fff; }
.padm-brand h1 { margin: 0; font-size: 1.55rem; font-weight: 700; color: #fff; letter-spacing: 0.2px; }
.padm-brand .sub { opacity: 0.82; font-size: 0.92rem; margin-top: 0.2rem; }
.padm-steps { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.85rem; }
.padm-step { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.18);
    border-radius: 999px; padding: 0.3rem 0.8rem; font-size: 0.82rem; color: #fff; }
.padm-step b { opacity: 0.6; margin-right: 0.3rem; }

/* Campaign header card (padm/ui.py header_bar) */
.padm-header-card { background: linear-gradient(180deg, #ffffff 0%, var(--padm-teal-light) 130%);
    border: 1px solid var(--padm-border); border-radius: 12px; padding: 0.9rem 1.2rem;
    margin-bottom: 0.7rem; box-shadow: 0 2px 10px rgba(10, 30, 60, 0.06); }
.padm-header-grid { display: flex; flex-wrap: wrap; gap: 1.6rem; }
.padm-header-grid > div { min-width: 7.5rem; }
.padm-header-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em;
    color: var(--padm-muted); text-transform: uppercase; }
.padm-header-value { font-size: 0.98rem; color: var(--padm-ink); font-weight: 600; }

/* Tabs */
div[data-testid="stTabs"] button[role="tab"] p { font-weight: 600; }
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    border-bottom: 3px solid var(--padm-teal); }
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p { color: var(--padm-teal); }

/* Sidebar */
section[data-testid="stSidebar"] { background: #f4f8fa; border-right: 1px solid var(--padm-border); }

/* Buttons */
button[kind="primary"], button[kind="primaryFormSubmit"] {
    background-color: var(--padm-teal) !important; border-color: var(--padm-teal) !important; }
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
    background-color: var(--padm-blue) !important; border-color: var(--padm-blue) !important; }

/* Section headers within tabs (st.header()) */
div[data-testid="stMarkdownContainer"] h2 { color: var(--padm-navy); }
</style>
""", unsafe_allow_html=True)


def _brand_bar() -> None:
    steps = "".join(f'<span class="padm-step"><b>{i}</b>{label}</span>' for i, (label, _, _) in enumerate(TABS, start=1))
    st.markdown(
        f"""<div class="padm-brand">
            <h1>PADM Sign-Off Dashboard</h1>
            <div class="sub">Direct-mail credit-card campaign sign-off — replaces the manual Excel process.</div>
            <div class="padm-steps">{steps}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def _landing(session) -> None:
    _brand_bar()
    st.info("Select or create a campaign below to unlock Signature Page, Create Segment, and the rest of the workflow.",
            icon=":material/arrow_forward:")
    campaign_creation.render(session)


def _authorized(session) -> bool:
    """Who can open this dashboard in the shared workspace -- everyone else sees a plain
    "work in progress" page instead. Checks CURRENT_USER() (the person's email on this account)
    against DM_PADM_DASHBOARD_ACCESS rather than a hardcoded list, so granting or revoking access
    is a plain INSERT/UPDATE in Snowsight, with no redeploy of this file needed."""
    rows = session.sql(
        f"""
        SELECT COUNT(*) FROM {SCHEMA}.DM_PADM_DASHBOARD_ACCESS
        WHERE ACTIVE_FLAG = TRUE AND UPPER(EMAIL) = UPPER(CURRENT_USER())
        """
    ).collect()
    return rows[0][0] > 0


def main() -> None:
    session = get_active_session()
    if not _authorized(session):
        st.info("This dashboard is a work in progress and isn't available here yet.")
        return

    st.sidebar.checkbox("Debug mode", key="debug_mode",
                         help="Show full Python tracebacks alongside error messages, for diagnosing issues live.")
    campaign = ui.campaign_context(session)

    if campaign is None:
        _landing(session)
        return

    _brand_bar()
    tabs = st.tabs([f"{icon} {label}" for label, icon, _ in TABS])
    for tab, (label, _, module) in zip(tabs, TABS):
        with tab:
            module.render(session)


if __name__ == "__main__":
    main()
