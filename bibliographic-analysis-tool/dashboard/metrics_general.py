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
    st.write("Overview of missing information across all loaded columns.")

    total_articles = len(df)
    if total_articles == 0:
        st.info("No data available.")
        return

    # 1. Calculate missing data across all columns
    missing_counts = df.isna().sum()
    
    # Safely count empty/whitespace strings across all columns without using the .str accessor
    for col in df.columns:
        empty_str_count = df[col].apply(lambda x: isinstance(x, str) and x.strip() == '').sum()
        missing_counts[col] += empty_str_count

    missing_df = pd.DataFrame({
        "Column": missing_counts.index,
        "Missing Count": missing_counts.values,
        "Missing Percentage": (missing_counts.values / total_articles) * 100
    }).sort_values(by="Missing Percentage", ascending=False)

    # Filter out columns with 100% completeness for the chart
    missing_filtered = missing_df[missing_df["Missing Count"] > 0]

    # 2. Visual Overview (Horizontal Bar Chart)
    if not missing_filtered.empty:
        # Dynamically adjust height based on the number of columns missing data
        chart_height = max(5, len(missing_filtered) * 0.5)
        fig, ax = plt.subplots(figsize=(10, chart_height))
        
        # Using the sepia/gold tone to fit your theme
        bars = ax.barh(missing_filtered["Column"], missing_filtered["Missing Percentage"], color="#C69C55")
        
        ax.set_xlabel("% Missing")
        ax.set_title("Percentage of Missing Data by Column")
        ax.set_xlim(0, 100)
        ax.invert_yaxis() # Highest missing percentage on top

        # Add percentage labels directly onto the bars for quick scanning
        for bar in bars:
            width = bar.get_width()
            ax.text(width + 1, bar.get_y() + bar.get_height()/2, f'{width:.1f}%', va='center', fontsize=10)

        # Remove border spines for a cleaner, modern look
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        st.pyplot(fig)
    else:
        st.success("🎉 100% Data Completeness! No missing values detected in the current dataset.")

    # 3. Tabular Overview
    st.subheader("Detailed Breakdown")
    st.dataframe(
        missing_df.style.format({"Missing Percentage": "{:.2f}%"}),
        use_container_width=True,
        hide_index=True
    )

    # 4. Targeted Sub-setting & Download
    if not missing_filtered.empty:
        st.markdown("---")
        st.subheader("Extract Incomplete Records")
        st.write("Select a specific column to isolate and download the records missing that information.")

        col_to_check = st.selectbox(
            "Select column to inspect:", 
            missing_filtered["Column"].tolist()
        )

        if col_to_check:
            # Catch both NaNs and empty strings
            is_nan = df[col_to_check].isna()
            is_empty = df[col_to_check].apply(lambda x: isinstance(x, str) and x.strip() == '') if df[col_to_check].dtype == object else False

            incomplete_records = df[is_nan | is_empty]
            
            st.warning(f"Found **{len(incomplete_records)}** records missing **{col_to_check}**.")
            st.dataframe(incomplete_records.head(5)) # Only show preview to save memory
            
            _download_button(
                incomplete_records, 
                f"Download Records Missing {col_to_check}", 
                f"missing_{col_to_check.lower().replace(' ', '_')}.csv"
            )
