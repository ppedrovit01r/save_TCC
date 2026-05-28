import streamlit as st
import pandas as pd

from data.data_preparation import show as show_data
from analysis.performance_analysis import show as show_performance
from analysis.science_mapping import show as show_science_mapping

def show_trend_spotting(): #placeholder for now
    st.title("📈 Trend Spotting")
    st.info("Coming soon: Longitudinal analysis of keywords to spot rising and falling research trends.")

def show_slr_assistant():
    st.title("📚 SLR Assistant")
    st.info("Coming soon: Reading priority matrix and search string optimization.")

def show_academic_export():
    st.title("💾 Academic Export")
    st.info("Coming soon: Export your cleaned dataset directly to .bib or .ris formats.")

st.set_page_config(page_title="Editorial Decision Support", layout="wide")

st.title("Editorial Decision Support System")

# --- INITIALIZE GLOBAL MEMORY (SESSION STATE) ---
if 'master_df' not in st.session_state:
    st.session_state.master_df = None

tabs = st.tabs([
    "Data Prep & Upload", 
    "Performance Analysis", 
    "Science Mapping", 
    "Trend Spotting", 
    "SLR Assistant", 
    "Academic Export"
])

with tabs[0]:
    st.markdown("### Step 1: Upload or Prepare your Dataset")
    st.markdown("Upload a raw file to enrich it with OpenAlex, or upload an already processed file to begin analysis.")
    show_data()

with tabs[1]:
    show_performance()

with tabs[2]:
    show_science_mapping()

with tabs[3]:
    show_trend_spotting()

with tabs[4]:
    show_slr_assistant()

with tabs[5]:
    show_academic_export()