import streamlit as st
import pandas as pd

from core.main import show as show_data_prep
from dashboard.main import show as show_dashboard
from features.main import show as show_features


st.set_page_config(page_title="Editorial Decision Support", layout="wide")

st.title("Editorial Decision Support System")

# --- INITIALIZE GLOBAL MEMORY (SESSION STATE) ---
if 'master_df' not in st.session_state:
    st.session_state.master_df = None

tabs = st.tabs([
    "1. Data Preparation", 
    "2. Main Dashboard", 
    "3. Auxiliary Features"
])

with tabs[0]:
    st.markdown("### Step 1: Upload or Prepare your Dataset")
    st.markdown("Upload a raw file to enrich it with OpenAlex, or upload an already processed file to begin analysis.")
    show_data_prep()

with tabs[1]:
    show_dashboard()

with tabs[2]:
    show_features()
