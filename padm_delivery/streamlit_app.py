"""PADM Sign-Off Dashboard — entry point.

Renders the 7-tab workflow (spec sections 1.1 through 1.3): Campaign Creation,
Signature Page, Create Segment, Campaign Assumptions, Population Description,
Segment Viewer, Signature Page 2. The selected campaign lives in
st.session_state["campaign_id"] and is shared by every tab.

STATUS (2026-11-19): this is the mobile session's PROPOSED rewrite of streamlit_app.py --
sent as a file, NOT YET CONFIRMED applied/working against the real project. Flagged caveats
from the mobile session itself, not yet resolved:
  - Assumes repository.campaign_header() returns a dict with keys name/mail_date/type/version/
    status/source_change_pending -- unverified against the real function's actual return shape.
  - Uses get_active_session() for the Snowpark session -- assumed, not confirmed, to match the
    real file.
  - Uses `:material/...:` icon syntax, which needs a recent-enough Streamlit version.
  - RESOLVED: checked padm/ui.py directly -- it defines CAMPAIGN_KEY = "campaign_id", so this
    file's hardcoded "campaign_id" string matches exactly. No key-name mismatch.
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session

from padm import repository, ui
from padm.tabs import (
    campaign_assumptions,
    campaign_creation,
    create_segment,
    population_description,
    segment_viewer,
    signature_page,
    signature_page_2,
)

st.set_page_config(page_title="PADM Sign-Off Dashboard", page_icon=":material/fact_check:", layout="wide")

TABS = [
    ("Campaign Creation", ":material/add_box:", campaign_creation),
    ("Signature Page", ":material/description:", signature_page),
    ("Create Segment", ":material/group_add:", create_segment),
    ("Campaign Assumptions", ":material/tune:", campaign_assumptions),
    ("Population Description", ":material/pie_chart:", population_description),
    ("Segment Viewer", ":material/table_view:", segment_viewer),
    ("Signature Page 2", ":material/task_alt:", signature_page_2),
]

STATUS_COLOR = {
    "NEW": "grey", "DRAFT": "grey", "IN_PROGRESS": "blue",
    "PENDING_APPROVAL": "orange", "APPROVED": "green", "REJECTED": "red",
}

st.markdown("""
<style>
.padm-header { padding: 0.9rem 1.3rem; border-radius: 10px;
    background: linear-gradient(135deg, #0f2744 0%, #15395e 100%); color: #fff; margin-bottom: 0.6rem; }
.padm-header h2 { margin: 0; color: #fff; font-size: 1.35rem; }
.padm-header .meta { opacity: 0.85; font-size: 0.9rem; margin-top: 0.15rem; }
.padm-readonly { padding: 0.55rem 1rem; border-radius: 8px; background: #e8f5e9;
    border: 1px solid #66bb6a; color: #1b5e20; font-weight: 600; margin-bottom: 0.6rem; }
div[data-testid="stTabs"] button[role="tab"] p { font-weight: 600; }
</style>
""", unsafe_allow_html=True)


def _header(campaign: dict) -> None:
    status = campaign["status"]
    badge = f":{STATUS_COLOR.get(status, 'grey')}-background[{status}]"
    st.markdown(
        f"""<div class="padm-header">
            <h2>{campaign['name']}</h2>
            <div class="meta">Mail Date: {campaign['mail_date']} &nbsp;·&nbsp;
            Type: {campaign['type']} &nbsp;·&nbsp; Working Version: v{campaign['version']}</div>
        </div>""",
        unsafe_allow_html=True,
    )
    left, right = st.columns([5, 1])
    with left:
        st.markdown(f"**Status:** {badge}")
    with right:
        if st.button(":material/refresh: Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    if status == "APPROVED":
        st.markdown('<div class="padm-readonly">:material/lock: Approved — read only. No further edits are allowed.</div>',
                     unsafe_allow_html=True)
    if campaign.get("source_change_pending"):
        st.warning("Source ACM data has changed since this campaign was activated. Review before proceeding.",
                    icon=":material/sync_problem:")


def _landing(session) -> None:
    st.title(":material/fact_check: PADM Sign-Off Dashboard")
    st.caption("Replaces the manual Excel sign-off process for monthly direct-mail credit-card campaigns.")
    st.info("Select or create a campaign in **Campaign Creation** to unlock the rest of the workflow.",
            icon=":material/arrow_forward:")
    st.markdown("##### Workflow")
    steps = " → ".join(label for label, _, _ in TABS)
    st.caption(steps)
    campaign_creation.render(session)


def main() -> None:
    session = get_active_session()
    campaign_id = st.session_state.get("campaign_id")
    campaign = repository.campaign_header(session, campaign_id) if campaign_id else None

    if campaign is None:
        _landing(session)
        return

    _header(campaign)

    tabs = st.tabs([f"{icon} {label}" for label, icon, _ in TABS])
    for tab, (label, _, module) in zip(tabs, TABS):
        with tab:
            module.render(session)


if __name__ == "__main__":
    main()
