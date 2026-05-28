import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Callable, Any, Optional, List, Union

st.set_option("client.showErrorDetails", False)
plt.style.use("dark_background")

def show():
    st.title("Performance Analysis")

    # --- GLOBAL MEMORY INTEGRATION ---
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

    # Ensure numeric columns are in the correct format
    numeric_cols = ["Times Cited", "Publication Year"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    display(df)

def safe_run(func: Callable[..., Any]) -> Callable[..., Any]:
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyError as err:
            st.error(f"[{func.__name__}] Missing column: {err}")
        except ZeroDivisionError:
            st.error(f"[{func.__name__}] Division by zero.")
        except ValueError as err:
            st.error(f"[{func.__name__}] Value error: {err}")
        except Exception as err:
            st.error(f"[{func.__name__}] Unexpected error:")
            st.exception(err)
    return wrapper

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
def display(df: pd.DataFrame):
    if df.empty:
        st.warning("The loaded dataset is empty.")
        return

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

    display_top_10_tables(df_results)
    display_most_cited_per_year_graph(df)
    display_authors_with_more_citations(df_results, df)
    display_gini_and_lorenz(df_results)
    display_citation_data_per_year(df)
    display_error_info(df)

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

def _download_button(df: pd.DataFrame, label: str, file_name: str):
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), file_name, "text/csv")

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
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(x_axis, cumulative_citations, label="Lorenz Curve", color="blue")
    ax.plot([0, 1], [0, 1], "--", color="black", label="Equality Line")
    ax.set_xlabel("Cumulative Fraction of Authors")
    ax.set_ylabel("Cumulative Fraction of Citations")
    ax.set_title("Lorenz Curve")
    st.pyplot(fig)

    n = len(sorted_citations)
    cumulative_sum = np.cumsum(sorted_citations)
    gini = (n + 1 - 2 * np.sum(cumulative_sum) / cumulative_sum[-1]) / n
    st.markdown(f"**Gini Coefficient (Citations):** {gini:.3f}")

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