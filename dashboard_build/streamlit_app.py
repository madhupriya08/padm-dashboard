import streamlit as st
from snowflake.snowpark.context import get_active_session

from app import ui
from app.pages import campaign_setup, signature_page, create_segment, campaign_assumptions, population_description, segment_viewer, signature_page_2

st.set_page_config(page_title="PADM Campaign Sign-Off", layout="wide")
ui.inject_theme()

session = get_active_session()

tabs = st.tabs([
    "Campaign Creation",
    "Signature Page",
    "Create Segment",
    "Campaign Assumptions",
    "Population Description",
    "Segment Viewer",
    "Signature Page 2",
])

with tabs[0]:
    campaign_setup.render(session)
with tabs[1]:
    signature_page.render(session)
with tabs[2]:
    create_segment.render(session)
with tabs[3]:
    campaign_assumptions.render(session)
with tabs[4]:
    population_description.render(session)
with tabs[5]:
    segment_viewer.render(session)
with tabs[6]:
    signature_page_2.render(session)
