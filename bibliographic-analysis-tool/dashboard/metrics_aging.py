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
    
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pubs_per_year.index, y=pubs_per_year.values, mode='lines+markers', name="Publications", line=dict(color="#C69C55")))
    fig.add_trace(go.Scatter(x=citations_per_year.index, y=citations_per_year.values, mode='lines+markers', name="Citations", line=dict(color="#64B5F6")))
    
    fig.update_layout(
        title="Publications and Citations by Year",
        xaxis=dict(title="Year"),
        yaxis=dict(title="Count"),
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")
    _display_average_citation_year(citations_per_year, pubs_per_year)

@safe_run
def _display_average_citation_year(citations_per_year, pubs_per_year):
    st.subheader("Average Citations per Article by Year")
    with np.errstate(divide="ignore", invalid="ignore"):
        avg_citations_per_year = citations_per_year / pubs_per_year
        avg_citations_per_year.replace([np.inf, -np.inf], np.nan, inplace=True)
        
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=avg_citations_per_year.index, y=avg_citations_per_year.values, mode='lines+markers', name="Avg Citations", line=dict(color="purple")))
    fig.update_layout(
        title="Average Citations per Article by Year",
        xaxis=dict(title="Publication Year"),
        yaxis=dict(title="Average Citations"),
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")
    avg_table = avg_citations_per_year.reset_index()
    avg_table.columns = ["Publication Year", "Average Citations per Paper"]
    st.dataframe(avg_table, width="stretch", height=180)
    _download_button(avg_table, "Download CSV", "avg_citations_per_paper.csv")