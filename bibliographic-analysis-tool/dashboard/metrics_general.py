import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from typing import Callable, Any, Optional, List, Union
from utils.exports import _download_button, safe_run

@safe_run
def display_header_data(df: pd.DataFrame):
    all_authors = df["Author"].astype(str).str.split(",").explode().str.strip().unique()
    num_authors = len(all_authors)
    total_citations = df["Times Cited"].sum(skipna=True)
    avg_citations = df["Times Cited"].mean(skipna=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("Unique Authors", num_authors)
    col2.metric("Total Citations", int(total_citations))
    col3.metric("Average Citations", round(avg_citations, 2))

@safe_run
def display_most_cited_per_year_graph(df: pd.DataFrame, min_cit: int = 100):
    if df.empty:
        st.info("The dataset is empty.")
        return
    needed = {"Times Cited", "Publication Year", "Title"}
    if needed - set(df.columns):
        st.warning("Missing columns for this chart.")
        return

    st.subheader(f"Most Cited Articles per Year (Citations > {min_cit})")
    high_cited = df[df["Times Cited"] > min_cit][["Title", "Publication Year", "Times Cited"]]

    if high_cited.empty:
        st.info(f"No articles with more than {min_cit} citations were found.")
        return

    high_cited = high_cited.sort_values(["Publication Year", "Times Cited"], ascending=[True, False])
    fig, ax = plt.subplots(figsize=(10, 6))
    for year, group in high_cited.groupby("Publication Year"):
        ax.bar(group["Title"], group["Times Cited"], label=year)

    ax.set_xlabel("Article Title")
    ax.set_ylabel("Citations")
    ax.set_title(f"Most Cited Articles per Year (Citations > {min_cit})")
    ax.legend(title="Publication Year")
    plt.xticks(rotation=90)
    st.pyplot(fig)
    _download_button(high_cited, f"Download Most Cited Articles (>{min_cit})", "most_cited_articles_per_year.csv")

@safe_run
def display_authors_with_more_citations(df_results: pd.DataFrame, df: pd.DataFrame):
    st.subheader("Authors with More Than 100 Total Citations")
    authors_over_100 = df_results[df_results["Total Citations"] > 100].sort_values("Total Citations", ascending=False)
    if authors_over_100.empty:
        st.info("No authors with more than 100 citations were found.")
    else:
        st.dataframe(authors_over_100)
        _download_button(authors_over_100, "Download CSV", "authors_over_100.csv")

    st.subheader("Number of Articles by Year")
    if "Publication Year" not in df.columns:
        st.warning("No 'Publication Year' column in the dataset.")
        return
    articles_per_year = df["Publication Year"].dropna().astype(int).value_counts().sort_index()
    if articles_per_year.empty:
        st.info("No year information available.")
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    articles_per_year.plot(kind="bar", ax=ax)
    ax.set_xlabel("Publication Year")
    ax.set_ylabel("Number of Articles")
    ax.set_title("Number of Articles by Year")
    st.pyplot(fig)

    year_table = articles_per_year.reset_index()
    year_table.columns = ["Publication Year", "Number of Articles"]
    st.dataframe(year_table)
    _download_button(year_table, "Download CSV", "articles_per_year.csv")

@safe_run
def display_error_info(df: pd.DataFrame):
    st.header("Error Information (Missing Data)")
    st.subheader("Articles Missing Citation Information")
    missing_citations = df[df["Times Cited"].isna()][["Title", "Publication Year"]]
    total_articles = len(df)
    count_missing = len(missing_citations)
    perc = (count_missing / total_articles * 100) if total_articles else 0.0

    st.markdown(f"**{count_missing} articles** do not have citation information ({perc:.2f}% of {total_articles}).")
    if not missing_citations.empty:
        st.dataframe(missing_citations)
        _download_button(missing_citations, "Download Missing Data", "missing_citations.csv")

    st.subheader("📊 Articles with Zero or Missing Citations by Year")
    uncited_or_missing = (
        df[df["Times Cited"].isna() | (df["Times Cited"] == 0)]
        .groupby("Publication Year").size().reset_index(name="Uncited or Missing")
    )
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(uncited_or_missing["Publication Year"].astype(str), uncited_or_missing["Uncited or Missing"], alpha=0.8)
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, height, f"{int(height)}", ha="center", va="bottom", fontsize=9)
    ax.set_xlabel("Publication Year")
    ax.set_ylabel("Number of Articles")
    ax.set_title("Articles with Zero or Missing Citations by Year")
    ax.set_xticks(range(len(uncited_or_missing)))
    ax.set_xticklabels(uncited_or_missing["Publication Year"].astype(str), rotation=90)
    st.pyplot(fig)
