import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Callable, Any, Optional, List, Union
from utils.exports import _download_button, safe_run

@safe_run
def display_citation_data_per_year(df: pd.DataFrame):
    st.subheader("Publications vs Citations by Year")
    if "Publication Year" not in df.columns:
        st.warning("'Publication Year' column not found.")
        return
    df_year = df.dropna(subset=["Publication Year"]).copy()
    df_year["Publication Year"] = df_year["Publication Year"].astype(int)
    if df_year.empty:
        st.info("No valid year data.")
        return

    pubs_per_year = df_year.groupby("Publication Year").size()
    citations_per_year = df_year.groupby("Publication Year")["Times Cited"].sum()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(pubs_per_year.index, pubs_per_year.values, marker="o", label="Publications")
    ax.plot(citations_per_year.index, citations_per_year.values, marker="s", label="Citations")
    ax.set_xlabel("Year")
    ax.set_ylabel("Count")
    ax.set_title("Publications and Citations by Year")
    ax.legend()
    st.pyplot(fig)
    _display_average_citation_year(citations_per_year, pubs_per_year)

@safe_run
def _display_average_citation_year(citations_per_year, pubs_per_year):
    st.subheader("Average Citations per Article by Year")
    with np.errstate(divide="ignore", invalid="ignore"):
        avg_citations_per_year = citations_per_year / pubs_per_year
        avg_citations_per_year.replace([np.inf, -np.inf], np.nan, inplace=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(avg_citations_per_year.index, avg_citations_per_year.values, marker="o", color="purple")
    ax.set_xlabel("Publication Year")
    ax.set_ylabel("Average Citations")
    ax.set_title("Average Citations per Article by Year")
    st.pyplot(fig)
    avg_table = avg_citations_per_year.reset_index()
    avg_table.columns = ["Publication Year", "Average Citations per Paper"]
    st.dataframe(avg_table)
    _download_button(avg_table, "Download CSV", "avg_citations_per_paper.csv")