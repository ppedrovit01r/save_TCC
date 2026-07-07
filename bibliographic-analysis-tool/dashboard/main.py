import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Callable, Any, Optional, List, Union

import streamlit as st
import pandas as pd

from dashboard.metrics_general import display_header_data, display_most_cited_per_year_graph, display_authors_with_more_citations, display_error_info
from dashboard.metrics_impact import calculate_metrics_per_author, display_top_10_tables, display_gini_and_lorenz
from dashboard.metrics_aging import display_citation_data_per_year

def show():
    st.title("Main Dashboard")

    if 'master_df' not in st.session_state or st.session_state.master_df is None:
        st.warning("⚠️ Please upload or process a file in the 'Data Prep & Upload' tab first.")
        return

    # Fetch the dataset directly from memory
    df = st.session_state.master_df.copy()

    # Safety validation to ensure required columns exist
    expected = {"Author", "Title", "Times Cited", "Publication Year"}
    missing = expected - set(df.columns)
    if missing:
        st.error(f"Missing required columns for this analysis: {', '.join(missing)}")
        return

    numeric_cols = ["Times Cited", "Publication Year"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if df.empty:
        st.warning("The loaded dataset is empty.")
        return

    # Show visualizations and metrics
    display_header_data(df)

    if "Author" not in df.columns or df["Author"].dropna().empty:
        st.warning("No author information available.")
        return

    df_authors = (
        df.assign(Author=df["Author"].astype(str).str.split(","))
        .explode("Author")
    )
    df_authors["Author"] = df_authors["Author"].str.strip()
    df_results = calculate_metrics_per_author(df_authors)

    # Graphs and tables
    display_top_10_tables(df_results)
    display_most_cited_per_year_graph(df)
    display_authors_with_more_citations(df_results, df)
    display_gini_and_lorenz(df_results)
    display_citation_data_per_year(df)
    display_error_info(df)