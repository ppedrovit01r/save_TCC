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
def display_most_cited_per_year_graph(df: pd.DataFrame, min_cit: Optional[int] = None):
    if df.empty:
        st.info("The dataset is empty.")
        return
    needed = {"Times Cited", "Publication Year", "Title"}
    if needed - set(df.columns):
        st.warning("Missing columns for this chart.")
        return

    # Calculate smart default citation threshold based on the dataset
    max_cit = int(df["Times Cited"].max()) if ("Times Cited" in df.columns and not df["Times Cited"].isna().all()) else 0
    if min_cit is None:
        min_cit = 100 if max_cit >= 100 else (50 if max_cit >= 50 else (10 if max_cit >= 10 else 0))

    # --- SINGLE CONTROL LINE: Header, Dynamic Input, Display Limit, and Download Button ---
    col1, col2, col3, col4 = st.columns([0.42, 0.18, 0.18, 0.22], vertical_alignment="center")
    with col1:
        st.subheader("Most Cited Articles per Year")
    with col2:
        # Dynamically changes the threshold number
        min_cit = st.number_input(
            "Min Citations", value=int(min_cit), step=10, min_value=0, key="graph_cit_threshold"
        )
    with col3:
        display_limit = st.selectbox(
            "Display Limit", 
            options=[15, 25, 50, "All"], 
            index=1, 
            key="graph_display_limit",
            help="Limits bars shown in graph for readability; CSV export contains all matching records."
        )

    # Columns to include
    cols = ["Title", "Publication Year", "Times Cited"]
    if "Author" in df.columns:
        cols.append("Author")
    
    # Filter data based on the chosen threshold
    if min_cit == 0:
        high_cited = df[df["Times Cited"] >= 0][cols].copy()
    else:
        high_cited = df[df["Times Cited"] > min_cit][cols].copy()

    with col4:
        # Button is visible immediately, disabled if no data is found
        _download_button(
            high_cited, 
            f"Download CSV (>{min_cit})", 
            "most_cited_articles_per_year.csv", 
            disabled=high_cited.empty
        )

    # Empty handling displays nicely below the controls
    if high_cited.empty:
        st.info(f"No articles with more than {min_cit} citations were found.")
    else:
        high_cited = high_cited.sort_values(["Publication Year", "Times Cited"], ascending=[True, False]).reset_index(drop=True)
        high_cited["Article ID"] = [f"A{i+1}" for i in range(len(high_cited))]
        
        # Apply display limit to chart if dataset is large
        if display_limit != "All" and len(high_cited) > int(display_limit):
            chart_df = high_cited.head(int(display_limit)).copy()
            sub_title_extra = f" · Showing Top {len(chart_df)} of {len(high_cited)}"
        else:
            chart_df = high_cited.copy()
            sub_title_extra = ""

        # Format clean hover tooltip with wrapped title and authors
        hover_notes = []
        for _, r in chart_df.iterrows():
            raw_title = str(r["Title"]).strip()
            words = raw_title.split()
            lines, cur_line, cur_len = [], [], 0
            for w in words:
                if cur_len + len(w) > 52:
                    lines.append(" ".join(cur_line))
                    cur_line = [w]
                    cur_len = len(w)
                else:
                    cur_line.append(w)
                    cur_len += len(w) + 1
            if cur_line:
                lines.append(" ".join(cur_line))
            wrapped_title = "<br>".join(lines[:4])
            if len(lines) > 4:
                wrapped_title += "..."
                
            author_info = f"<br><b>Authors:</b> {str(r['Author']).split(',')[0]} et al." if ("Author" in r and pd.notna(r["Author"])) else ""
            hover_notes.append(f"<b>{r['Article ID']}</b>: {wrapped_title}<br><b>Year:</b> {r['Publication Year']}<br><b>Citations:</b> {r['Times Cited']}{author_info}")

        chart_df["hover_text"] = hover_notes

        fig = px.bar(
            chart_df, 
            x="Article ID", 
            y="Times Cited", 
            color="Publication Year",
            title=f"Most Cited Articles per Year (Citations > {min_cit}){sub_title_extra}",
            labels={"Times Cited": "Citations", "Article ID": "Article ID"}
        )
        fig.update_traces(
            hovertemplate="%{customdata}<extra></extra>", 
            customdata=chart_df["hover_text"]
        )
        fig.update_layout(
            xaxis=dict(tickangle=0, title="Article ID (see Legend below)"),
            margin=dict(l=20, r=20, t=45, b=40),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig, width="stretch")

        # --- ARTICLE LEGEND & MAPPING TABLE ---
        st.markdown("<h4 style='font-size: 15px; font-weight: 600; color: #1E293B; margin-top: 10px; margin-bottom: 2px;'><i class='bi bi-list-columns-reverse' style='color: #697aa2;'></i> Legend: Article ID → Full Reference Details</h4>", unsafe_allow_html=True)
        st.caption("Interactive reference mapping for chart labels (A1, A2, ...). Use table search and sorting to inspect specific papers.")
        
        legend_cols = ["Article ID", "Publication Year", "Times Cited", "Title"]
        if "Author" in high_cited.columns:
            legend_cols.append("Author")
        legend_display = high_cited[legend_cols]
        
        st.dataframe(
            legend_display, 
            width="stretch", 
            height=min(280, max(120, len(legend_display) * 35 + 38)),
            hide_index=True
        )


@safe_run
def display_authors_with_more_citations(df_results: pd.DataFrame, df: pd.DataFrame):
    max_author_cit = 0
    if not df_results.empty and "Total Citations" in df_results.columns:
        valid_cits = df_results["Total Citations"].dropna()
        if not valid_cits.empty:
            max_author_cit = int(valid_cits.max())
    default_thresh = 100 if max_author_cit >= 100 else (50 if max_author_cit >= 50 else (10 if max_author_cit >= 10 else 0))

    # --- SINGLE CONTROL LINE: Header, Dynamic Input, and Download Button ---
    col1, col2, col3 = st.columns([0.5, 0.2, 0.3], vertical_alignment="center")
    with col1:
        st.subheader("Authors by Citation Threshold")
    with col2:
        # Dynamically changes the threshold number
        author_threshold = st.number_input(
            "Min Citations", value=int(default_thresh), step=10, min_value=0, key="author_cit_threshold"
        )
        
    if author_threshold == 0:
        authors_over_thresh = df_results[df_results["Total Citations"] >= 0].sort_values("Total Citations", ascending=False)
    else:
        authors_over_thresh = df_results[df_results["Total Citations"] > author_threshold].sort_values("Total Citations", ascending=False)
    
    with col3:
        _download_button(
            authors_over_thresh, 
            "Download CSV", 
            f"authors_over_{author_threshold}.csv", 
            disabled=authors_over_thresh.empty
        )

    if authors_over_thresh.empty:
        st.info(f"No authors with more than {author_threshold} citations were found.")
    else:
        st.dataframe(authors_over_thresh, width="stretch", height=220)

    # --- ARTICLE COUNT BY YEAR SECTION ---
    st.write("") # Layout breathing room
    
    if "Publication Year" not in df.columns:
        st.warning("No 'Publication Year' column in the dataset.")
        return
        
    articles_per_year = df["Publication Year"].dropna().astype(int).value_counts().sort_index()
    if articles_per_year.empty:
        st.info("No year information available.")
        return

    year_df = articles_per_year.reset_index()
    year_df.columns = ["Publication Year", "Number of Articles"]
    
    # Header Line with Download Button for the table
    y_col1, y_col2 = st.columns([0.7, 0.3], vertical_alignment="center")
    with y_col1:
        st.subheader("Number of Articles by Year")
    with y_col2:
        _download_button(year_df, "Download CSV", "articles_per_year.csv")
    
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

@safe_run
def display_error_info(df: pd.DataFrame, key_prefix: str = "err_info", is_core_screen: bool = False, is_sidebar: bool = False):
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
        def render_chart():
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

        def render_table():
            st.caption("Main Schema Breakdown")
            st.dataframe(
                main_missing.style.format({"Missing Percentage": "{:.2f}%"}),
                width="stretch",
                hide_index=True,
                height=min(280, max(140, len(main_missing) * 35 + 38))
            )

        if is_sidebar:
            # In sidebar mode: Avoid 2 squished columns; use compact tabbed view
            t_chart, t_table = st.tabs(["📊 Missing % Chart", "📋 Data Breakdown"])
            with t_chart:
                render_chart()
            with t_table:
                render_table()
        else:
            # Fullscreen / main area: spacious 2-column view
            col_chart, col_table = st.columns([1, 1], gap="medium")
            with col_chart:
                render_chart()
            with col_table:
                render_table()

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
