import streamlit as st
import pandas as pd

from features.network_topology import (
    display_reference_summary,
    display_cocitation_analysis,
    display_bibliographic_coupling_analysis
)
from features.semantic_analysis import display_coword_analysis

def show():
    st.title("Auxiliary Features")

    if 'master_df' not in st.session_state or st.session_state.master_df is None:
        st.warning("⚠️ Please upload or process a file in the 'Data Prep & Upload' tab first.")
        return

    df = st.session_state.master_df.copy()

    expected = {"Title", "Article References", "Keywords", "Abstract"}
    missing = expected - set(df.columns)
    if missing:
        st.error(f"Missing required columns for mapping: {', '.join(missing)}")
        return

    display_reference_summary(df)
    st.markdown("---")
    display_cocitation_analysis(df)
    st.markdown("---")
    display_bibliographic_coupling_analysis(df)
    st.markdown("---")
    display_coword_analysis(df)