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

def show(profile="ALL"):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-bar-chart-line-fill' style='color: #697aa2;'></i> Main Dashboard</h2>", unsafe_allow_html=True)

    if 'master_df' not in st.session_state or st.session_state.master_df is None:
        st.warning("Please upload or process a file in the 'Data Prep & Upload' tab first.")
        return

    # Fetch the dataset directly from memory (use working_df for Focus Mode support)
    if 'working_df' in st.session_state:
        df = st.session_state.working_df.copy()
    else:
        df = st.session_state.master_df.copy()

    # Safety validation to ensure required columns exist
    expected = {"Author", "Title", "Times Cited", "Publication Year"}
    missing = expected - set(df.columns)
    if missing:
        st.error(f"Missing required columns for this analysis: {', '.join(missing)}")
        return

    if "Publication Year" in df.columns:
        from utils.formatters import clean_year_series
        df["Publication Year"] = clean_year_series(df["Publication Year"])

    if "Times Cited" in df.columns:
        df["Times Cited"] = pd.to_numeric(df["Times Cited"], errors="coerce").fillna(0).astype(int)

    if df.empty:
        st.warning("The loaded dataset is empty.")
        return

    # Show visualizations and metrics
    display_header_data(df)

    if "Author" not in df.columns or df["Author"].dropna().empty:
        st.warning("No author information available.")
        return

    from features.gender import split_authors_string

    # Robustly split multiple authors per article (delimited by ;, and, or ,) and deduplicate per article
    parsed_authors = df["Author"].apply(lambda x: split_authors_string(str(x)) if pd.notna(x) else [])
    df_authors = df.assign(Author=parsed_authors).explode("Author")

    # Filter out empty, NaN, and invalid placeholder tokens (<NA>, nan, unknown, etc.)
    df_authors = df_authors[df_authors["Author"].notna()].copy()
    df_authors["Author"] = df_authors["Author"].astype(str).str.strip()
    invalid_tokens = {'', 'nan', '<na>', 'none', 'null', 'n/a', 'unknown', 'et al', 'et al.', 'anonymous'}
    df_authors = df_authors[~df_authors["Author"].str.lower().isin(invalid_tokens)]
    df_results = calculate_metrics_per_author(df_authors)

    # Graphs and tables
    display_top_10_tables(df_results)
    display_most_cited_per_year_graph(df)
    display_authors_with_more_citations(df_results, df)
    display_gini_and_lorenz(df_results)
    display_citation_data_per_year(df)
    display_error_info(df, key_prefix="dash_main")