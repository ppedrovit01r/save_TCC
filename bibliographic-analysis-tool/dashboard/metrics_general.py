import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import Callable, Any, Optional, List, Union
from utils.exports import _download_button, safe_run
from core.ingestion import normalize_columns, TARGET_COLUMNS

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
    high_cited = df[df["Times Cited"] > min_cit][["Title", "Publication Year", "Times Cited"]].copy()

    if high_cited.empty:
        st.info(f"No articles with more than {min_cit} citations were found.")
        return

    high_cited = high_cited.sort_values(["Publication Year", "Times Cited"], ascending=[True, False])
    
    fig = px.bar(
        high_cited, 
        x="Title", 
        y="Times Cited", 
        color="Publication Year",
        title=f"Most Cited Articles per Year (Citations > {min_cit})",
        labels={"Times Cited": "Citations", "Title": "Article Title"},
        hover_data=["Publication Year"]
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=80),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")
    _download_button(high_cited, f"Download Most Cited Articles (>{min_cit})", "most_cited_articles_per_year.csv")

@safe_run
def display_authors_with_more_citations(df_results: pd.DataFrame, df: pd.DataFrame):
    st.subheader("Authors with More Than 100 Total Citations")
    authors_over_100 = df_results[df_results["Total Citations"] > 100].sort_values("Total Citations", ascending=False)
    if authors_over_100.empty:
        st.info("No authors with more than 100 citations were found.")
    else:
        st.dataframe(authors_over_100, width="stretch", height=220)
        _download_button(authors_over_100, "Download CSV", "authors_over_100.csv")

    st.subheader("Number of Articles by Year")
    if "Publication Year" not in df.columns:
        st.warning("No 'Publication Year' column in the dataset.")
        return
    articles_per_year = df["Publication Year"].dropna().astype(int).value_counts().sort_index()
    if articles_per_year.empty:
        st.info("No year information available.")
        return

    year_df = articles_per_year.reset_index()
    year_df.columns = ["Publication Year", "Number of Articles"]
    
    fig = px.bar(
        year_df, 
        x="Publication Year", 
        y="Number of Articles",
        title="Number of Articles by Year",
        text="Number of Articles",
        color_discrete_sequence=["#C69C55"]
    )
    fig.update_layout(
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")

    st.dataframe(year_df, width="stretch", height=180)
    _download_button(year_df, "Download CSV", "articles_per_year.csv")

@safe_run
def display_error_info(df: pd.DataFrame, key_prefix: str = "err_info", is_core_screen: bool = False):
    st.subheader("Error Information (Missing Data Diagnostics)")
    st.caption("Overview of missing information across mapped schema columns.")

    total_articles = len(df)
    if total_articles == 0:
        st.info("No data available.")
        return

    # 1. Normalize columns first so raw synonymous fields merge
    df_norm = normalize_columns(df.copy())

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from typing import Callable, Any, Optional, List, Union
from utils.exports import _download_button, safe_run
from core.ingestion import normalize_columns, TARGET_COLUMNS

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
    high_cited = df[df["Times Cited"] > min_cit][["Title", "Publication Year", "Times Cited"]].copy()

    if high_cited.empty:
        st.info(f"No articles with more than {min_cit} citations were found.")
        return

    high_cited = high_cited.sort_values(["Publication Year", "Times Cited"], ascending=[True, False])
    
    fig = px.bar(
        high_cited, 
        x="Title", 
        y="Times Cited", 
        color="Publication Year",
        title=f"Most Cited Articles per Year (Citations > {min_cit})",
        labels={"Times Cited": "Citations", "Title": "Article Title"},
        hover_data=["Publication Year"]
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        margin=dict(l=20, r=20, t=40, b=80),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")
    _download_button(high_cited, f"Download Most Cited Articles (>{min_cit})", "most_cited_articles_per_year.csv")

@safe_run
def display_authors_with_more_citations(df_results: pd.DataFrame, df: pd.DataFrame):
    st.subheader("Authors with More Than 100 Total Citations")
    authors_over_100 = df_results[df_results["Total Citations"] > 100].sort_values("Total Citations", ascending=False)
    if authors_over_100.empty:
        st.info("No authors with more than 100 citations were found.")
    else:
        st.dataframe(authors_over_100, width="stretch", height=220)
        _download_button(authors_over_100, "Download CSV", "authors_over_100.csv")

    st.subheader("Number of Articles by Year")
    if "Publication Year" not in df.columns:
        st.warning("No 'Publication Year' column in the dataset.")
        return
    articles_per_year = df["Publication Year"].dropna().astype(int).value_counts().sort_index()
    if articles_per_year.empty:
        st.info("No year information available.")
        return

    year_df = articles_per_year.reset_index()
    year_df.columns = ["Publication Year", "Number of Articles"]
    
    fig = px.bar(
        year_df, 
        x="Publication Year", 
        y="Number of Articles",
        title="Number of Articles by Year",
        text="Number of Articles",
        color_discrete_sequence=["#C69C55"]
    )
    fig.update_layout(
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, width="stretch")

    st.dataframe(year_df, width="stretch", height=180)
    _download_button(year_df, "Download CSV", "articles_per_year.csv")

@safe_run
def display_error_info(df: pd.DataFrame, key_prefix: str = "err_info", is_core_screen: bool = False):
    st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B; margin-top: 15px;'><i class='bi bi-exclamation-triangle-fill' style='color: #697aa2;'></i> Error Information (Missing Data Diagnostics)</h3>", unsafe_allow_html=True)
    st.caption("Overview of missing information across mapped schema columns.")

    total_articles = len(df)
    if total_articles == 0:
        st.info("No data available.")
        return

    # 1. Normalize columns first so raw synonymous fields merge
    df_norm = normalize_columns(df.copy())

    # 2. Calculate missing counts
    missing_counts = df_norm.isna().sum()
    for col in df_norm.columns:
        empty_str_count = df_norm[col].apply(lambda x: isinstance(x, str) and x.strip() == '').sum()
        missing_counts[col] += empty_str_count

    missing_df = pd.DataFrame({
        "Column": missing_counts.index,
        "Missing Count": missing_counts.values,
        "Missing Percentage": (missing_counts.values / total_articles) * 100
    }).sort_values(by="Missing Percentage", ascending=False)

    # 3. Categorize errors into Main Mapping Columns vs Additional Columns
    main_missing = missing_df[missing_df["Column"].isin(TARGET_COLUMNS) & (missing_df["Missing Count"] > 0)]
    additional_missing = missing_df[(~missing_df["Column"].isin(TARGET_COLUMNS)) & (missing_df["Missing Count"] > 0)]

    if main_missing.empty and (is_core_screen or additional_missing.empty):
        st.success("100% Data Completeness! No missing values detected across main schema fields.")
        return

    # Render Main Mapping Columns (Core Focus)
    if not main_missing.empty:
        col_chart, col_table = st.columns([1, 1], gap="medium")

        with col_chart:
            fig = go.Figure(go.Bar(
                x=main_missing["Missing Percentage"],
                y=main_missing["Column"],
                orientation='h',
                marker=dict(color='#C69C55'),
                text=main_missing["Missing Percentage"].apply(lambda v: f"{v:.1f}%"),
                textposition='outside',
                hovertemplate="<b>%{y}</b><br>Missing: %{x:.2f}% (%{customdata} records)<extra></extra>",
                customdata=main_missing["Missing Count"]
            ))
            
            fig.update_layout(
                title=dict(text="Main Schema Missing % by Column", font=dict(size=12)),
                xaxis=dict(title="% Missing", range=[0, 112]),
                yaxis=dict(autorange="reversed"),
                margin=dict(l=10, r=20, t=30, b=20),
                height=max(250, min(480, len(main_missing) * 22)),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, width="stretch")

        with col_table:
            st.caption("Main Schema Breakdown")
            st.dataframe(
                main_missing.style.format({"Missing Percentage": "{:.2f}%"}),
                width="stretch",
                hide_index=True,
                height=250
            )

    # Secondary Additional Columns (Only on Dashboard screen, not Core screen)
    if not is_core_screen and not additional_missing.empty:
        with st.expander("Additional Dataset Columns Diagnostics (Non-Schema)", expanded=False):
            st.caption("Secondary raw columns present in the input file that fall outside the core schema.")
            st.dataframe(
                additional_missing.style.format({"Missing Percentage": "{:.2f}%"}),
                width="stretch",
                hide_index=True,
                height=180
            )

    # Incomplete records inspection
    active_missing = main_missing if not main_missing.empty else additional_missing
    if not active_missing.empty:
        with st.expander("Inspect & Download Records Missing Specific Fields", expanded=False):
            col_to_check = st.selectbox(
                "Select column to inspect:", 
                active_missing["Column"].tolist(),
                key=f"{key_prefix}_col_select"
            )

            if col_to_check:
                is_nan = df_norm[col_to_check].isna()
                is_empty = df_norm[col_to_check].apply(lambda x: isinstance(x, str) and x.strip() == '') if df_norm[col_to_check].dtype == object else False
                incomplete_records = df_norm[is_nan | is_empty]
                
                st.warning(f"Found **{len(incomplete_records)}** records missing **{col_to_check}**.")
                st.dataframe(incomplete_records.head(5), width="stretch", height=180)
                
                _download_button(
                    incomplete_records, 
                    f"Download Records Missing {col_to_check}", 
                    f"missing_{col_to_check.lower().replace(' ', '_')}.csv"
                )
