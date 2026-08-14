import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Callable, Any, Optional, List, Union
from utils.exports import _download_button, safe_run

def h_index(citations: List[Union[int, float, None]]) -> int:
    try:
        citations = [int(c) for c in citations if pd.notna(c)]
    except Exception:
        return 0
    citations.sort(reverse=True)
    return sum(c >= i + 1 for i, c in enumerate(citations))

def g_index(citations: List[Union[int, float, None]]) -> int:
    try:
        citations = [int(c) for c in citations if pd.notna(c)]
    except Exception:
        return 0
    citations.sort(reverse=True)
    total = 0
    g = 0
    for i, c in enumerate(citations, start=1):
        total += c
        if total >= i**2:
            g = i
    return g

@safe_run
def calculate_metrics_per_author(df_authors: pd.DataFrame) -> pd.DataFrame:
    results = []
    for author, group in df_authors.groupby("Author"):
        citations = group["Times Cited"].fillna(0).astype(int).tolist()
        num_articles = len(citations)
        results.append(
            {
                "Author": author,
                "Number of Articles": num_articles,
                "Total Citations": sum(citations),
                "Average Citations": sum(citations) / num_articles if num_articles else 0,
                "h-index": h_index(citations),
                "g-index": g_index(citations),
            }
        )
    return pd.DataFrame(results)

@safe_run
def display_top_10_tables(df_results: pd.DataFrame):
    if df_results.empty:
        st.info("No author results to display.")
        return
    st.subheader("Top 10 Authors by Metric")
    col1, col2 = st.columns(2)
    _display_citations(col1, df_results)
    _display_number_and_index(col2, df_results)
    _display_g_index(df_results)

def _display_citations(col, df_results):
    with col:
        st.markdown("**Top 10 by Total Citations**")
        top_total = df_results.nlargest(10, "Total Citations")
        st.dataframe(top_total)
        _download_button(top_total, "Download CSV", "top10_total_citations.csv")

        st.markdown("**Top 10 by Average Citations**")
        top_avg = df_results.nlargest(10, "Average Citations")
        st.dataframe(top_avg)
        _download_button(top_avg, "Download CSV", "top10_avg_citations.csv")

def _display_number_and_index(col, df_results):
    with col:
        st.markdown("**Top 10 by Number of Articles**")
        top_articles = df_results.nlargest(10, "Number of Articles")
        st.dataframe(top_articles)
        _download_button(top_articles, "Download CSV", "top10_articles.csv")

        st.markdown("**Top 10 by h-index**")
        top_h = df_results.nlargest(10, "h-index")
        st.dataframe(top_h)
        _download_button(top_h, "Download CSV", "top10_h_index.csv")

def _display_g_index(df_results):
    st.markdown("**Top 10 by g-index**")
    top_g = df_results.nlargest(10, "g-index")
    st.dataframe(top_g)
    _download_button(top_g, "Download CSV", "top10_g_index.csv")

@safe_run
def display_gini_and_lorenz(df_results: pd.DataFrame):
    st.subheader("Lorenz Curve of Citations")
    if df_results.empty:
        st.info("No author data to compute the Gini coefficient.")
        return
    sorted_citations = np.sort(df_results["Total Citations"].values)
    if sorted_citations[-1] == 0:
        st.info("All authors have zero citations.")
        return

    cumulative_citations = np.cumsum(sorted_citations) / sorted_citations.sum()
    x_axis = np.arange(1, len(sorted_citations) + 1) / len(sorted_citations)
    
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_axis, y=cumulative_citations, mode='lines', name="Lorenz Curve", line=dict(color="#C69C55", width=2)))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode='lines', name="Equality Line", line=dict(color="gray", dash="dash")))
    
    fig.update_layout(
        title="Lorenz Curve of Citation Distribution",
        xaxis=dict(title="Cumulative Fraction of Authors", range=[0, 1.02]),
        yaxis=dict(title="Cumulative Fraction of Citations", range=[0, 1.02]),
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")

    n = len(sorted_citations)
    cumulative_sum = np.cumsum(sorted_citations)
    gini = (n + 1 - 2 * np.sum(cumulative_sum) / cumulative_sum[-1]) / n
    st.markdown(f"**Gini Coefficient (Citations):** {gini:.3f}")
