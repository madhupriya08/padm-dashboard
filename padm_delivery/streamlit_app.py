"""PADM Sign-Off Dashboard — entry point.

Renders the 7-tab workflow (spec sections 1.1 through 1.3): Campaign Creation,
Signature Page, Create Segment, Campaign Assumptions, Population Description,
Segment Viewer, Signature Page 2. The selected campaign lives in
st.session_state["campaign_id"] and is shared by every tab.

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
    ("Signature Page", ":material/description:", signature_page),
    ("Pre Signature Page", ":material/checklist:", pre_signature_page),
    ("Create Segment", ":material/group_add:", create_segment),
    ("Campaign Assumptions", ":material/tune:", campaign_assumptions),
    ("Population Description", ":material/pie_chart:", population_description),
    ("Segment Viewer", ":material/table_view:", segment_viewer),
    ("Signature Page 2", ":material/task_alt:", signature_page_2),
]

st.markdown("""
<style>
.padm-brand { padding: 1.1rem 1.5rem; border-radius: 14px; margin-bottom: 1rem;
    background: linear-gradient(120deg, #0b1f3a 0%, #103a63 55%, #0e5a7a 100%);
    box-shadow: 0 4px 18px rgba(10, 30, 60, 0.25); color: #fff; }
.padm-brand h1 { margin: 0; font-size: 1.55rem; font-weight: 700; color: #fff; letter-spacing: 0.2px; }
.padm-brand .sub { opacity: 0.82; font-size: 0.92rem; margin-top: 0.2rem; }
.padm-steps { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.85rem; }
.padm-step { background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.18);
    border-radius: 999px; padding: 0.3rem 0.8rem; font-size: 0.82rem; color: #fff; }
.padm-step b { opacity: 0.6; margin-right: 0.3rem; }
div[data-testid="stTabs"] button[role="tab"] p { font-weight: 600; }
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    border-bottom: 3px solid #0e5a7a; }
</style>
""", unsafe_allow_html=True)


def _brand_bar() -> None:
    steps = "".join(f'<span class="padm-step"><b>{i}</b>{label}</span>' for i, (label, _, _) in enumerate(TABS, start=1))
    st.markdown(
        f"""<div class="padm-brand">
            <h1>:material/fact_check: PADM Sign-Off Dashboard</h1>
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


def main() -> None:
    session = get_active_session()
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
