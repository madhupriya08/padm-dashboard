import streamlit as st
from snowflake.snowpark.context import get_active_session

from padm import ui
from padm.tabs import (
    campaign_assumptions,
    campaign_creation,
    create_segment,
    population_description,
    segment_viewer,
    signature_page,
    signature_page_2,
)

st.set_page_config(page_title="PADM Sign-Off Dashboard", layout="wide")

session = get_active_session()

with st.container(horizontal=True, vertical_alignment="center"):
    st.title("PADM Sign-Off Dashboard")
    ui.refresh_button()

# Tab order is part of the spec (1.1) -- do not reorder. Tabs 2-7 stay locked until a campaign
# is selected or created on Tab 1 (each tab gates itself through ui.require_campaign).
TABS = [
    ("Campaign Creation", campaign_creation),
    ("Signature Page", signature_page),
    ("Create Segment", create_segment),
    ("Campaign Assumptions", campaign_assumptions),
    ("Population Description", population_description),
    ("Segment Viewer", segment_viewer),
    ("Signature Page 2", signature_page_2),
]

has_campaign = bool(st.session_state.get(ui.CAMPAIGN_KEY))
labels = [label if i == 0 or has_campaign else f":material/lock: {label}" for i, (label, _) in enumerate(TABS)]

for tab, (_, page) in zip(st.tabs(labels), TABS):
    with tab:
        page.render(session)
