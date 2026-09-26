"""
Articles Explorer
=================
Comprehensive interactive exploration, sorting, filtering, and author standardization
inspection view for user-uploaded bibliographic datasets.
"""

import streamlit as st
import pandas as pd
import numpy as np
import html
import io
from features.gender import (
    split_authors_string,
    extract_name_parts,
    author_has_initials,
    clean_author_text,
    fetch_openalex_authorships_batch,
    fetch_semanticscholar_authors_for_doi,
    disambiguate_paper_authors
)
from core.enrichment import enrich_dataset_openalex
import utils.project_manager as pm
if not hasattr(pm, 'is_author_standardization_dismissed'):
    import importlib
    importlib.reload(pm)

from utils.project_manager import (
    save_master_dataset,
    is_author_standardization_dismissed,
    set_author_standardization_dismissed,
    get_manual_author_overrides,
    save_manual_author_override,
    delete_manual_author_override
)


def apply_author_override_to_df(df: pd.DataFrame, orig_name: str, new_name: str, row_idx: int = None) -> pd.DataFrame:
    """
    Replaces an author token in df['Author'] with new_name.
    If row_idx is specified, only replaces in that specific row.
    Otherwise, replaces across all rows where that author token appears.
    Uses tokenized author comparison to prevent substring collision errors.
    """
    if df is None or 'Author' not in df.columns or not orig_name or not new_name:
        return df
        
    orig_clean = clean_author_text(orig_name).strip().lower()
    indices = [row_idx] if row_idx is not None and row_idx in df.index else df.index
    
    for idx in indices:
        curr_val = df.at[idx, 'Author']
        if pd.isna(curr_val) or not str(curr_val).strip():
            continue
        tokens = split_authors_string(str(curr_val))
        modified = False
        new_tokens = []
        for t in tokens:
            t_clean = clean_author_text(t).strip().lower()
            if t.strip().lower() == orig_clean or t_clean == orig_clean:
                new_tokens.append(new_name.strip())
                modified = True
            else:
                new_tokens.append(t)
        if modified:
            df.at[idx, 'Author'] = "; ".join(new_tokens)
            
    return df



@st.cache_data
def _compute_articles_explorer_kpis(df_subset: pd.DataFrame):
    total = len(df_subset)
    if total == 0:
        return pd.Series(dtype=bool), 0, 0, 0.0, 0, 0.0, 0, 0.0, 0.0, "N/A"

    if "Author" in df_subset.columns:
        has_init_series = df_subset["Author"].apply(
            lambda x: author_has_initials(str(x)) if pd.notna(x) and str(x).strip() else True
        )
    else:
        has_init_series = pd.Series(False, index=df_subset.index)

    full_count = int((~has_init_series).sum())
    init_count = int(has_init_series.sum())
    pct_full = (full_count / total * 100) if total > 0 else 0

    if "Abstract" in df_subset.columns:
        has_abstract = int((df_subset["Abstract"].astype(str).str.strip().str.len() > 30).sum())
    else:
        has_abstract = 0
    pct_abstract = (has_abstract / total * 100) if total > 0 else 0

    if "DOI" in df_subset.columns:
        has_doi = int((df_subset["DOI"].astype(str).str.strip().str.len() > 4).sum())
    else:
        has_doi = 0
    pct_doi = (has_doi / total * 100) if total > 0 else 0

    avg_cit = float(df_subset["Times Cited"].mean()) if "Times Cited" in df_subset.columns else 0.0

    if "Publication Year" in df_subset.columns:
        _val_years = pd.to_numeric(df_subset["Publication Year"], errors="coerce").dropna()
        year_min = int(_val_years.min()) if not _val_years.empty else None
        year_max = int(_val_years.max()) if not _val_years.empty else None
    else:
        year_min = None
        year_max = None
    year_span = f"{year_min} – {year_max}" if year_min and year_max else "N/A"

    return has_init_series, full_count, init_count, pct_full, has_abstract, pct_abstract, has_doi, pct_doi, avg_cit, year_span

def _get_field(row, col_name, default=""):
    val = row.get(col_name, default)
    if pd.isna(val) or val is None:
        return default
    return str(val).strip()


def show(df_input: pd.DataFrame = None):
    # Header
    st.markdown(
        """
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <div>
                <h2 style="font-size: 24px; font-weight: 700; color: #1E293B; margin: 0;">
                    <i class="bi bi-collection" style="color: #697aa2; margin-right: 8px;"></i>Articles Explorer
                </h2>
                <div style="font-size: 13px; color: #64748B; margin-top: 4px;">
                    Full-corpus article catalog with interactive reordering, abstract reading, and author disambiguation inspection.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if 'master_df' not in st.session_state or st.session_state.master_df is None or st.session_state.master_df.empty:
        st.warning("⚠️ No dataset loaded yet. Please upload and parse your bibliographic files in the **Data Prep & Upload** tab.")
        return

    # Use provided df, or working_df (respecting Global Focus Mode), or fallback to master_df
    if df_input is not None and not df_input.empty:
        df = df_input.copy()
    elif 'working_df' in st.session_state and st.session_state.working_df is not None and not st.session_state.working_df.empty:
        df = st.session_state.working_df.copy()
    else:
        df = st.session_state.master_df.copy()

    total_articles = len(df)
    if total_articles == 0:
        st.warning("The current dataset view contains 0 articles.")
        return

    # Ensure standardized types for core columns
    if "Publication Year" in df.columns:
        from utils.formatters import clean_year_series
        df["Publication Year"] = clean_year_series(df["Publication Year"])

    if "Times Cited" in df.columns:
        df["Times Cited"] = pd.to_numeric(df["Times Cited"], errors="coerce").fillna(0).astype(int)

    # Compute KPI statistics via cached vectorized helper
    kpi_cols = [c for c in ["Author", "Abstract", "DOI", "Times Cited", "Publication Year"] if c in df.columns]
    (has_init_series, full_names_count, initials_count, pct_full_names,
     has_abstract, pct_abstract, has_doi, pct_doi, avg_citations, year_span_str) = _compute_articles_explorer_kpis(df[kpi_cols])

    if "Author" in df.columns:
        df["_has_initials"] = has_init_series
        df["_author_status"] = df["_has_initials"].apply(
            lambda x: "⚠️ Has Initials" if x else "✓ Full Names"
        )
    else:
        df["_has_initials"] = False
        df["_author_status"] = "No Author Data"

    # --- TOP KPI METRICS ROW ---
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    with kpi1:
        st.markdown(f"""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;">Total Articles</div>
            <div style="font-size: 24px; font-weight: 700; color: #1E293B; margin-top: 2px;">{total_articles:,}</div>
            <div style="font-size: 11px; color: #94A3B8;">Years: {year_span_str}</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi2:
        status_color = "#10B981" if pct_full_names > 80 else ("#F59E0B" if pct_full_names > 40 else "#EF4444")
        st.markdown(f"""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;">Full Author Names</div>
            <div style="font-size: 24px; font-weight: 700; color: {status_color}; margin-top: 2px;">{pct_full_names:.1f}%</div>
            <div style="font-size: 11px; color: #64748B;">{full_names_count:,} Full / {initials_count:,} Initials</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi3:
        st.markdown(f"""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;">Has Abstract</div>
            <div style="font-size: 24px; font-weight: 700; color: #1E293B; margin-top: 2px;">{pct_abstract:.1f}%</div>
            <div style="font-size: 11px; color: #64748B;">{has_abstract:,} of {total_articles:,}</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi4:
        st.markdown(f"""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;">Has DOI</div>
            <div style="font-size: 24px; font-weight: 700; color: #1E293B; margin-top: 2px;">{pct_doi:.1f}%</div>
            <div style="font-size: 11px; color: #64748B;">{has_doi:,} resolved DOIs</div>
        </div>
        """, unsafe_allow_html=True)
    with kpi5:
        st.markdown(f"""
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;">Avg. Citations</div>
            <div style="font-size: 24px; font-weight: 700; color: #1E293B; margin-top: 2px;">{avg_citations:.1f}</div>
            <div style="font-size: 11px; color: #64748B;">Max: {df['Times Cited'].max() if 'Times Cited' in df.columns else 0:,}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # --- AUTHOR INITIALS CALLOUT BANNER ---
    is_dismissed = is_author_standardization_dismissed()
    if initials_count > 0:
        if not is_dismissed:
            c_warn1, c_warn2, c_warn3 = st.columns([3.8, 1.8, 1.0])
            with c_warn1:
                st.markdown(f"""
                <div style="background-color: #FEF3C7; border: 1px solid #FDE68A; border-left: 5px solid #D97706; padding: 10px 14px; border-radius: 6px; font-size: 13px; color: #92400E;">
                    <b>⚠️ Author Initials or Non-Latin Names Detected ({initials_count:,} articles):</b><br>
                    Authors formatted with initials or non-Latin scripts can be standardized to Western full names via OpenAlex.
                </div>
                """, unsafe_allow_html=True)
            with c_warn2:
                st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                if st.button("Standardize", key="exp_btn_standardize", icon=":material/person_search:", type="primary", width="stretch", help="Standardizes author names: expands initials into verified full names via OpenAlex Knowledge Graph and romanizes non-Latin scripts into Western format."):
                    with st.spinner("Standardizing and disambiguating author names..."):
                        proc_df = enrich_dataset_openalex(
                            st.session_state.master_df.copy(),
                            ['Author'],
                            st.session_state.get('execution_logs', []),
                            file_manifest=st.session_state.get('file_manifest', {}),
                            is_ultimate=False
                        )
                        st.session_state.master_df = proc_df
                        save_master_dataset(st.session_state.master_df)
                        st.session_state.has_unstandardized_authors = False
                        set_author_standardization_dismissed(True)
                        st.toast("Author names standardized and romanized!", icon="🎉")
                        st.rerun()
            with c_warn3:
                st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                if st.button("Dismiss", key="exp_btn_dismiss", icon=":material/close:", width="stretch", help="Hide this warning banner for this project."):
                    set_author_standardization_dismissed(True)
                    st.session_state.has_unstandardized_authors = False
                    st.toast("Author standardization advisory dismissed.", icon="ℹ️")
                    st.rerun()
        else:
            c_dism1, c_dism2 = st.columns([4.2, 1.2])
            with c_dism1:
                st.markdown(f"<div style='font-size: 12px; color: #64748B; padding-top: 6px;'>✓ <i>Author standardization advisory dismissed ({initials_count:,} articles retain initials).</i></div>", unsafe_allow_html=True)
            with c_dism2:
                if st.button("Re-show Advisory", key="exp_btn_reshow", icon=":material/refresh:", width="stretch", help="Display the author standardization advisory banner again."):
                    set_author_standardization_dismissed(False)
                    st.rerun()

    # --- FILTERING & REORDERING CONTROLS BAR ---
    with st.expander("🔍 Filter, Search & Reorder Articles", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns([3, 2, 2, 2])

        with f_col1:
            search_query = st.text_input(
                "Search Corpus",
                placeholder="Search Title, Author, Abstract, Journal, DOI...",
                help="Case-insensitive text search across all major columns."
            ).strip()

        with f_col2:
            author_filter = st.selectbox(
                "Author Format",
                options=["All Articles", "Full Names (Standardized)", "Initials Detected (Needs Standardization)"],
                index=0
            )

        with f_col3:
            sort_by = st.selectbox(
                "Sort / Reorder By",
                options=[
                    "Publication Year (Newest First)",
                    "Publication Year (Oldest First)",
                    "Times Cited (Most Cited First)",
                    "Times Cited (Least Cited First)",
                    "Title (A → Z)",
                    "Author (A → Z)",
                    "Author Format (Initials First)",
                    "Author Format (Full Names First)"
                ],
                index=0
            )

        with f_col4:
            max_c = int(df["Times Cited"].max() if "Times Cited" in df.columns and len(df["Times Cited"]) > 0 else 1000)
            min_cit = st.number_input("Min. Citations", min_value=0, max_value=max(1, max_c), value=0, step=1)

    # --- APPLY FILTERS ---
    filtered_df = df.copy()

    # 1. Text Search Filter
    if search_query:
        q_lower = search_query.lower()
        match_mask = pd.Series(False, index=filtered_df.index)
        for col in ["Title", "Author", "Abstract", "Journal", "Source title", "DOI"]:
            if col in filtered_df.columns:
                match_mask = match_mask | filtered_df[col].astype(str).str.lower().str.contains(q_lower, regex=False, na=False)
        filtered_df = filtered_df[match_mask]

    # 2. Author Format Filter
    if author_filter == "Full Names (Standardized)":
        filtered_df = filtered_df[~filtered_df["_has_initials"]]
    elif author_filter == "Initials Detected (Needs Standardization)":
        filtered_df = filtered_df[filtered_df["_has_initials"]]

    # 3. Citation Filter
    if min_cit > 0 and "Times Cited" in filtered_df.columns:
        filtered_df = filtered_df[filtered_df["Times Cited"] >= min_cit]

    # --- APPLY SORTING / REORDERING ---
    if sort_by == "Publication Year (Newest First)" and "Publication Year" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by="Publication Year", ascending=False, na_position="last")
    elif sort_by == "Publication Year (Oldest First)" and "Publication Year" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by="Publication Year", ascending=True, na_position="last")
    elif sort_by == "Times Cited (Most Cited First)" and "Times Cited" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by="Times Cited", ascending=False, na_position="last")
    elif sort_by == "Times Cited (Least Cited First)" and "Times Cited" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by="Times Cited", ascending=True, na_position="last")
    elif sort_by == "Title (A → Z)" and "Title" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by="Title", ascending=True, na_position="last")
    elif sort_by == "Author (A → Z)" and "Author" in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by="Author", ascending=True, na_position="last")
    elif sort_by == "Author Format (Initials First)":
        filtered_df = filtered_df.sort_values(by="_has_initials", ascending=False)
    elif sort_by == "Author Format (Full Names First)":
        filtered_df = filtered_df.sort_values(by="_has_initials", ascending=True)

    # Status Bar
    count_filtered = len(filtered_df)
    st.caption(f"Showing **{count_filtered:,}** of **{total_articles:,}** articles (sorted by: *{sort_by}*)")

    # --- VIEW MODE TABS ---
    tab_table, tab_cards, tab_inspector, tab_export = st.tabs([
        "📋 Interactive Data Table",
        "📰 Article Cards & Abstract Reader",
        "🔍 Author Disambiguation Inspector",
        "💾 Export & Download"
    ])

    # =========================================================================
    # TAB 1: INTERACTIVE DATA TABLE
    # =========================================================================
    with tab_table:
        all_cols = [c for c in filtered_df.columns if not c.startswith("_")]
        
        # Determine default columns
        preferred_order = [
            "Title", "Author", "_author_status", "Publication Year", "Times Cited",
            "Journal", "Source title", "DOI", "Abstract"
        ]
        default_cols = [c for c in preferred_order if c in filtered_df.columns]

        col_select_col, height_col = st.columns([4, 1])
        with col_select_col:
            selected_cols = st.multiselect(
                "Columns to display",
                options=[c for c in filtered_df.columns if c != "_has_initials"],
                default=default_cols,
                help="Pick which columns to show in the interactive grid."
            )
        with height_col:
            grid_height = st.selectbox("Grid Height", options=[450, 650, 900], index=1)

        if not selected_cols:
            selected_cols = default_cols

        # Configure column formatting
        display_df = filtered_df[selected_cols].copy()
        
        col_cfg = {}
        if "DOI" in display_df.columns:
            col_cfg["DOI"] = st.column_config.LinkColumn(
                "DOI",
                help="Clickable DOI link",
                validate=r"^https?://.*|^10\.\d{4,9}/[-._;()/:A-Z0-9]+$",
                max_chars=100
            )
        if "_author_status" in display_df.columns:
            col_cfg["_author_status"] = st.column_config.TextColumn(
                "Author Format",
                help="Indicates whether all authors have full names or if initials were detected."
            )
        if "Times Cited" in display_df.columns:
            col_cfg["Times Cited"] = st.column_config.NumberColumn(
                "Citations",
                help="Total citations count",
                format="%d"
            )
        if "Publication Year" in display_df.columns:
            col_cfg["Publication Year"] = st.column_config.TextColumn(
                "Year",
                help="Publication Year"
            )
        if "Title" in display_df.columns:
            col_cfg["Title"] = st.column_config.TextColumn("Title", width="large")
        if "Abstract" in display_df.columns:
            col_cfg["Abstract"] = st.column_config.TextColumn("Abstract", width="large")

        st.dataframe(
            display_df,
            width="stretch",
            height=grid_height,
            column_config=col_cfg,
            hide_index=True
        )

    # =========================================================================
    # TAB 2: ARTICLE CARDS & ABSTRACT READER
    # =========================================================================
    with tab_cards:
        if count_filtered == 0:
            st.info("No articles match your search criteria.")
        else:
            card_col1, card_col2 = st.columns([2, 3])
            with card_col1:
                page_size = st.selectbox("Articles per page", options=[10, 25, 50, 100], index=0)
            
            total_pages = max(1, (count_filtered - 1) // page_size + 1)
            with card_col2:
                current_card_page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)

            start_idx = (current_card_page - 1) * page_size
            end_idx = min(start_idx + page_size, count_filtered)

            page_records = filtered_df.iloc[start_idx:end_idx]

            st.caption(f"Showing items **{start_idx + 1}** to **{end_idx}** of **{count_filtered}**")

            for row_idx, (_, row) in enumerate(page_records.iterrows(), start=start_idx + 1):
                raw_title = _get_field(row, 'Title', 'Untitled Article')
                authors = _get_field(row, 'Author', 'Unknown Authors')
                from utils.formatters import clean_year_value
                year = clean_year_value(_get_field(row, 'Publication Year', '')) or 'N/A'
                citations = row.get('Times Cited', 0)
                journal = _get_field(row, 'Journal', _get_field(row, 'Source title', ''))
                doi = _get_field(row, 'DOI', '')
                abstract = _get_field(row, 'Abstract', '')
                has_inits = row.get('_has_initials', False)

                # Format DOI link
                clean_doi_url = ""
                if doi:
                    if doi.startswith("http"):
                        clean_doi_url = doi
                    else:
                        clean_doi_url = f"https://doi.org/{doi}"

                # Author status badge
                if has_inits:
                    auth_badge = '<span style="background-color:#FEF3C7; color:#92400E; padding:3px 8px; border-radius:12px; font-size:11px; font-weight:600; border:1px solid #FDE68A;">⚠️ Initials Detected</span>'
                else:
                    auth_badge = '<span style="background-color:#D1FAE5; color:#065F46; padding:3px 8px; border-radius:12px; font-size:11px; font-weight:600; border:1px solid #A7F3D0;">✓ Full Names</span>'

                # Journal pill
                journal_html = f'<span style="background-color:#F1F5F9; color:#334155; padding:3px 8px; border-radius:6px; font-size:11px; margin-right:6px;">📖 {html.escape(journal[:45])}{"..." if len(journal) > 45 else ""}</span>' if journal else ""

                # DOI button/link
                doi_html = f'<a href="{clean_doi_url}" target="_blank" style="text-decoration:none; background-color:#EFF6FF; color:#1D4ED8; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:600; border:1px solid #BFDBFE;">🔗 DOI: {html.escape(doi)}</a>' if doi else ""

                st.html(
                    f"""
                    <div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                            <div style="font-size:16px; font-weight:700; color:#1E293B; line-height:1.3;">
                                <span style="color:#64748B; font-size:13px; font-weight:600; margin-right:6px;">#{row_idx}</span>
                                {html.escape(raw_title)}
                            </div>
                            <div style="white-space:nowrap; margin-left:12px;">
                                {auth_badge}
                            </div>
                        </div>
                        <div style="font-size: 13px; color: #475569; margin-bottom: 8px;">
                            <i class="bi bi-people" style="color:#697aa2; margin-right:4px;"></i> <b>Authors:</b> {html.escape(authors)}
                        </div>
                        <div style="display:flex; flex-wrap:wrap; gap:6px; align-items:center;">
                            <span style="background-color:#F1F5F9; color:#334155; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:600;">📅 {year}</span>
                            <span style="background-color:#F1F5F9; color:#334155; padding:3px 8px; border-radius:6px; font-size:11px; font-weight:600;">⭐ {citations:,} Citations</span>
                            {journal_html}
                            {doi_html}
                        </div>
                    </div>
                    """
                )

                # Abstract expander
                if abstract and len(abstract) > 10:
                    with st.expander(f"📄 Read Abstract (#{row_idx}: {raw_title[:40]}...)"):
                        st.markdown(
                            f"""
                            <div style="background-color: #F8FAFC; border-left: 3px solid #697aa2; padding: 12px 16px; border-radius: 4px; font-size: 13px; color: #334155; line-height: 1.6;">
                                {html.escape(abstract)}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                else:
                    st.caption(f"*No abstract available for article #{row_idx}*")

    # =========================================================================
    # TAB 3: AUTHOR DISAMBIGUATION INSPECTOR
    # =========================================================================
    with tab_inspector:
        st.markdown("""
        <div style="margin-bottom: 12px; font-size: 13px; color: #475569;">
            This inspector examines how the system parses author strings into <b>Given Names</b> and <b>Surnames</b>, and detects initials.
        </div>
        """, unsafe_allow_html=True)

        i_col1, i_col2 = st.columns([3, 2])
        with i_col1:
            inspector_scope = st.radio(
                "Filter Inspector View",
                options=["Show Articles Needing Disambiguation (Initials)", "Show All Filtered Articles"],
                horizontal=True
            )

        insp_df = filtered_df[filtered_df["_has_initials"]] if "Initials" in inspector_scope else filtered_df

        if len(insp_df) == 0:
            st.success("🎉 No articles in this selection have unstandardized author initials!")
        else:
            st.caption(f"Inspecting **{len(insp_df):,}** articles")

            # Article Selector for Single-Article Live Lookup
            st.markdown("##### ⚡ Single Article OpenAlex Test & Disambiguation")
            from utils.formatters import clean_year_value
            article_options = {
                idx: f"#{i+1} [{clean_year_value(row.get('Publication Year', '')) or 'N/A'}] {str(row.get('Title', ''))[:60]}... (DOI: {str(row.get('DOI', 'None'))[:25]})"
                for i, (idx, row) in enumerate(insp_df.head(100).iterrows())
            }

            selected_article_idx = st.selectbox(
                "Select an article to inspect and test live OpenAlex disambiguation:",
                options=list(article_options.keys()),
                format_func=lambda k: article_options[k]
            )

            if selected_article_idx is not None:
                sel_row = insp_df.loc[selected_article_idx]
                raw_authors_str = str(sel_row.get("Author", ""))
                sel_doi = str(sel_row.get("DOI", "")).strip()

                parsed_authors = split_authors_string(raw_authors_str)
                breakdown = []
                for a in parsed_authors:
                    fn, ln, is_init = extract_name_parts(a)
                    breakdown.append({
                        "Original Author Token": a,
                        "Parsed First Name": fn if fn else "-",
                        "Parsed Last Name": ln if ln else "-",
                        "Has Initials?": "⚠️ Yes (Initials)" if is_init else "✓ Full Name"
                    })

                st.markdown(f"**Article Title:** {sel_row.get('Title', 'Untitled')}")
                st.markdown(f"**Raw Author String:** `{raw_authors_str}`")

                st.dataframe(pd.DataFrame(breakdown), width="stretch", hide_index=True)

                c_lookup1, c_lookup2 = st.columns([2, 3])
                with c_lookup1:
                    if st.button("🔎 Test Multi-Tier Disambiguation (OpenAlex + ORCID + Semantic Scholar)", key="btn_test_single_oa", icon=":material/search:"):
                        if not sel_doi or sel_doi.lower() == 'nan':
                            st.warning("This article does not have a valid DOI. Disambiguation requires a valid DOI.")
                        else:
                            with st.spinner(f"Querying Multi-Tier Metadata for DOI: {sel_doi}..."):
                                clean_doi = sel_doi.replace("https://doi.org/", "").replace("doi:", "").lower()
                                fetched_map = fetch_openalex_authorships_batch([sel_doi])
                                work_data = fetched_map.get(clean_doi) or fetched_map.get(sel_doi)
                                oa_authorships = work_data.get('authorships', []) if work_data else []
                                ss_authors = fetch_semanticscholar_authors_for_doi(clean_doi)

                                resolved_list, was_enriched = disambiguate_paper_authors(
                                    parsed_authors,
                                    oa_authorships=oa_authorships,
                                    ss_authors=ss_authors
                                )

                                res_rows = []
                                for r in resolved_list:
                                    prov = r.get('provenance', 'None')
                                    if 'ORCID' in prov:
                                        badge = f"🟢 {prov}"
                                    elif 'Alternate' in prov:
                                        badge = f"🟣 {prov}"
                                    elif 'Semantic' in prov:
                                        badge = f"🔵 {prov}"
                                    elif 'OpenAlex' in prov:
                                        badge = f"🟡 {prov}"
                                    elif 'Original' in prov:
                                        badge = "⚪ Already Full Name"
                                    else:
                                        badge = "⚪ Unresolved (Kept Initial)"

                                    res_rows.append({
                                        "Original Token": [a for a in parsed_authors if r.get('last_name', '').lower() in a.lower()][0] if any(r.get('last_name', '').lower() in a.lower() for a in parsed_authors) else r.get('full_name'),
                                        "Resolved Given Name": r.get('first_name', ''),
                                        "Resolved Surname": r.get('last_name', ''),
                                        "Standardized Full Name": r.get('full_name', ''),
                                        "Resolution Source": badge,
                                        "Was Substituted?": "✨ YES" if r.get('was_enriched') else "Kept Original"
                                    })

                                st.markdown("###### Multi-Tier Disambiguation Result:")
                                st.dataframe(pd.DataFrame(res_rows), width="stretch", hide_index=True)

                                new_author_str = "; ".join(r['full_name'] for r in resolved_list)
                                st.info(f"**Proposed Standardized Author String:**\n`{new_author_str}`")

                                if st.button("Apply Standardized Authors to Dataset", key="btn_apply_single_oa", icon=":material/check:"):
                                    st.session_state.master_df.loc[selected_article_idx, "Author"] = new_author_str
                                    if 'working_df' in st.session_state:
                                        st.session_state.working_df.loc[selected_article_idx, "Author"] = new_author_str
                                    save_master_dataset(st.session_state.master_df)
                                    st.toast("Updated author names for this article!", icon="🎉")
                                    st.rerun()

                st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
                st.markdown("##### ✍️ Manual Author Name Correction & Override")
                st.caption("Recognize an author with initials (e.g. you know *Denton F* is *Fatima Denton*, or *O'Neill DW* is *Daniel W O'Neill*)? Rename them directly below.")
                
                token_choices = [a for a in parsed_authors] + ["(Custom / Other Author Name)"]
                c_man1, c_man2 = st.columns([1, 1])
                with c_man1:
                    chosen_token = st.selectbox("Author to Rename:", options=token_choices, key="man_sel_token")
                    if chosen_token == "(Custom / Other Author Name)":
                        orig_author_input = st.text_input("Original Author Name / Token:", key="man_custom_orig", placeholder="e.g. Denton F or DW O'Neill")
                    else:
                        orig_author_input = chosen_token
                with c_man2:
                    new_author_name = st.text_input("New Full Corrected Name:", key="man_new_name", placeholder="e.g. Fatima Denton")
                
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    if st.button("Apply to THIS Article Only", icon=":material/check:", width="stretch", key="btn_apply_man_single"):
                        if not orig_author_input or not new_author_name:
                            st.warning("Please provide both the author token and the new corrected name.")
                        else:
                            st.session_state.master_df = apply_author_override_to_df(
                                st.session_state.master_df,
                                orig_author_input,
                                new_author_name,
                                row_idx=selected_article_idx
                            )
                            if 'working_df' in st.session_state:
                                st.session_state.working_df = apply_author_override_to_df(
                                    st.session_state.working_df,
                                    orig_author_input,
                                    new_author_name,
                                    row_idx=selected_article_idx
                                )
                            save_master_dataset(st.session_state.master_df)
                            st.toast(f"Updated '{orig_author_input}' to '{new_author_name}' in this article!", icon="🎉")
                            st.rerun()
                with c_btn2:
                    if st.button("Apply to ALL Articles Across Corpus", icon=":material/done_all:", type="primary", width="stretch", key="btn_apply_man_global"):
                        if not orig_author_input or not new_author_name:
                            st.warning("Please provide both the author token and the new corrected name.")
                        else:
                            st.session_state.master_df = apply_author_override_to_df(
                                st.session_state.master_df,
                                orig_author_input,
                                new_author_name
                            )
                            if 'working_df' in st.session_state:
                                st.session_state.working_df = apply_author_override_to_df(
                                    st.session_state.working_df,
                                    orig_author_input,
                                    new_author_name
                                )
                            save_manual_author_override(orig_author_input, new_author_name)
                            save_master_dataset(st.session_state.master_df)
                            st.toast(f"Replaced '{orig_author_input}' with '{new_author_name}' across the entire corpus!", icon="🎉")
                            st.rerun()

            # Active Manual Overrides Manager (always visible in Tab 3)
            active_overrides = get_manual_author_overrides()
            if active_overrides:
                st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)
                st.markdown("###### 📋 Saved Corpus-Wide Manual Overrides")
                ov_rows = [{"Original Token": k, "Manual Replacement": v} for k, v in active_overrides.items()]
                st.dataframe(pd.DataFrame(ov_rows), width="stretch", hide_index=True)
                
                c_del_sel, c_del_btn = st.columns([3, 1])
                with c_del_sel:
                    to_remove = st.selectbox("Select override to delete:", options=list(active_overrides.keys()), key="man_sel_del")
                with c_del_btn:
                    st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                    if st.button("Delete Override", icon=":material/delete:", key="btn_del_override", width="stretch"):
                        delete_manual_author_override(to_remove)
                        st.toast(f"Removed override for '{to_remove}'.", icon="🗑️")
                        st.rerun()

    # =========================================================================
    # TAB 4: EXPORT & DOWNLOAD
    # =========================================================================
    with tab_export:
        st.markdown("##### 💾 Export Filtered Articles")
        st.markdown(f"Export the currently filtered and sorted subset (**{count_filtered:,}** articles) in your format of choice:")

        from core.export import df_to_csv, df_to_excel, df_to_bib, df_to_ris, df_to_nbib
        from utils.project_manager import format_timestamped_filename, save_project_file, get_active_project_name, open_project_folder

        def _save_filtered_export(subfolder, fname, data, mode="wb"):
            save_project_file(subfolder, fname, data, mode=mode)
            st.toast(f"Saved to Projects/{get_active_project_name()}/{subfolder}/{fname}", icon="💾")

        clean_export_df = filtered_df[[c for c in filtered_df.columns if not c.startswith("_")]].copy()

        ec1, ec2, ec3, ec4, ec5, ec6 = st.columns(6, gap="small")

        # 1. CSV Download
        fn_csv = format_timestamped_filename("filtered_articles.csv")
        data_csv = df_to_csv(clean_export_df)
        with ec1:
            st.download_button(
                label="CSV (.csv)",
                data=data_csv,
                file_name=fn_csv,
                mime="text/csv",
                width="stretch",
                icon=":material/download:",
                on_click=_save_filtered_export,
                args=("exports", fn_csv, data_csv, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )

        # 2. Excel Download
        fn_xlsx = format_timestamped_filename("filtered_articles.xlsx")
        data_xlsx = df_to_excel(clean_export_df)
        with ec2:
            st.download_button(
                label="Excel (.xlsx)",
                data=data_xlsx,
                file_name=fn_xlsx,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
                icon=":material/table_view:",
                on_click=_save_filtered_export,
                args=("exports", fn_xlsx, data_xlsx, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )

        # 3. BibTeX Download
        fn_bib = format_timestamped_filename("filtered_articles.bib")
        data_bib = df_to_bib(clean_export_df)
        with ec3:
            st.download_button(
                label="BibTeX (.bib)",
                data=data_bib,
                file_name=fn_bib,
                mime="text/plain",
                width="stretch",
                icon=":material/code:",
                on_click=_save_filtered_export,
                args=("exports", fn_bib, data_bib, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )

        # 4. RIS Download
        fn_ris = format_timestamped_filename("filtered_articles.ris")
        data_ris = df_to_ris(clean_export_df)
        with ec4:
            st.download_button(
                label="RIS (.ris)",
                data=data_ris,
                file_name=fn_ris,
                mime="application/x-research-info-systems",
                width="stretch",
                icon=":material/download:",
                on_click=_save_filtered_export,
                args=("exports", fn_ris, data_ris, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )

        # 5. NBIB Download
        fn_nbib = format_timestamped_filename("filtered_articles.nbib")
        data_nbib = df_to_nbib(clean_export_df)
        with ec5:
            st.download_button(
                label="NBIB (.nbib)",
                data=data_nbib,
                file_name=fn_nbib,
                mime="text/plain",
                width="stretch",
                icon=":material/download:",
                on_click=_save_filtered_export,
                args=("exports", fn_nbib, data_nbib, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )

        # 6. Open Exports Folder
        with ec6:
            if st.button("Open Folder", icon=":material/folder_open:", width="stretch", key="btn_open_articles_export_folder", help=f"Opens Projects/{get_active_project_name()}/exports in file explorer"):
                open_project_folder("exports")
