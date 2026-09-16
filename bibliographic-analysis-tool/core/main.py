import streamlit as st
import tempfile
import os
import time
import pandas as pd
from core.ingestion import parse_file, TARGET_COLUMNS, deduplicate_and_merge_columns, remove_blank_rows
from core.enrichment import enrich_dataset_openalex
from core.export import df_to_csv, df_to_excel, df_to_ris, df_to_bib, df_to_nbib
from dashboard.metrics_general import display_error_info
from utils.formatters import format_duration
from utils.project_manager import set_active_project, get_active_project_name, format_timestamped_filename, save_project_file, get_timestamp_str

MAX_ROWS = 50000

# --- CALLBACK FUNCTIONS ---
def add_to_memory(new_df, filename):
    """Appends new data to the master dataframe safely and records file provenance."""
    # Count raw imported rows for PRISMA
    raw_new_count = len(new_df)
    if 'prisma_imported_count' not in st.session_state:
        st.session_state.prisma_imported_count = 0
    st.session_state.prisma_imported_count += raw_new_count

    new_df = remove_blank_rows(deduplicate_and_merge_columns(new_df))
    
    # Tag rows with Source File metadata if not present
    if 'Source File' not in new_df.columns:
        new_df['Source File'] = filename
        
    if st.session_state.master_df is None:
        st.session_state.master_df = new_df
    else:
        st.session_state.master_df = pd.concat([st.session_state.master_df, new_df], ignore_index=True)
        st.session_state.master_df = remove_blank_rows(deduplicate_and_merge_columns(st.session_state.master_df))
        
    # Deduplicate rows based on DOI or Title
    dedup_subset = []
    if 'DOI' in st.session_state.master_df.columns:
        # Fill missing DOIs temporarily to avoid dropping all rows without DOI
        st.session_state.master_df['DOI_temp'] = st.session_state.master_df['DOI'].fillna(st.session_state.master_df.index.to_series().astype(str))
        dedup_subset.append('DOI_temp')
    if 'Title' in st.session_state.master_df.columns:
        st.session_state.master_df['Title_temp'] = st.session_state.master_df['Title'].str.lower().str.strip()
        dedup_subset.append('Title_temp')
        
    if dedup_subset:
        st.session_state.master_df = st.session_state.master_df.drop_duplicates(subset=dedup_subset, keep='first').reset_index(drop=True)
        # Drop temporary columns
        cols_to_drop = [c for c in ['DOI_temp', 'Title_temp'] if c in st.session_state.master_df.columns]
        if cols_to_drop:
            st.session_state.master_df = st.session_state.master_df.drop(columns=cols_to_drop)
            
    # Save a backup of the full deduplicated dataset before any PRISMA exclusions
    st.session_state.raw_df_backup = st.session_state.master_df.copy()
    
    if 'file_manifest' not in st.session_state:
        st.session_state.file_manifest = {}
    st.session_state.file_manifest[filename] = len(new_df)
    
    if filename not in st.session_state.loaded_files:
        st.session_state.loaded_files.append(filename)
    
    st.session_state.execution_logs.append(f"Auto-committed '{filename}' ({len(new_df)} valid rows out of {raw_new_count} raw) to memory. Total deduplicated rows: {len(st.session_state.master_df)}")

def inject_cluster_fields(fields, widget_key):
    """Callback: Forces the cluster fields into the multiselect's session state."""
    if widget_key not in st.session_state:
        st.session_state[widget_key] = []
    current_selection = set(st.session_state[widget_key])
    current_selection.update(fields)
    st.session_state[widget_key] = list(current_selection)

def clear_selection(widget_key):
    """Callback: Wipes the multiselect clean."""
    st.session_state[widget_key] = []


import base64

def show(is_sidebar=False):
    if not is_sidebar:
        logo_path = os.path.join("utils", "cropped-logo-300x86.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                encoded_logo = base64.b64encode(f.read()).decode("utf-8")
            st.markdown(
                f'''
                <div style="text-align: center; margin-bottom: 15px; padding-top: 5px;">
                    <a href="https://www.ufrgs.br/bpmlab/" target="_blank" rel="noopener noreferrer">
                        <img src="data:image/png;base64,{encoded_logo}" alt="BPM Research Lab Logo" style="max-width: 270px; height: auto; transition: transform 0.2s;" onmouseover="this.style.transform='scale(1.03)'" onmouseout="this.style.transform='scale(1.0)'" />
                    </a>
                </div>
                ''',
                unsafe_allow_html=True
            )
            st.title("Bibliometric Decision Support System")
        st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-database-gear' style='color: #697aa2;'></i> Data Preparation & Management</h2>", unsafe_allow_html=True)
    else:
        st.markdown("<h4 style='font-size: 17px; font-weight: 700; color: #1E293B;'><i class='bi bi-cloud-arrow-up-fill' style='color: #697aa2;'></i> Upload & Enrich</h4>", unsafe_allow_html=True)

    if "execution_logs" not in st.session_state: st.session_state.execution_logs = []
    if "loaded_files" not in st.session_state: st.session_state.loaded_files = []
    if "master_df" not in st.session_state: st.session_state.master_df = None
    if "file_manifest" not in st.session_state: st.session_state.file_manifest = {}

    num_loaded_files = len(st.session_state.loaded_files)
    num_master_rows = len(st.session_state.master_df) if st.session_state.master_df is not None else 0

    # 1. FILE UPLOADER (Auto-commits to memory & supports multi-file drag-and-drop)
    uploaded_files = st.file_uploader(
        "Add dataset file(s) (Excel, CSV, RIS, BibTeX, NBIB):",
        type=["csv", "xls", "xlsx", "bib", "ris", "nbib"],
        accept_multiple_files=True,
        key="uploader_sidebar" if is_sidebar else "uploader_main"
    )

    if uploaded_files:
        for u_file in uploaded_files:
            if u_file.name not in st.session_state.loaded_files:
                try:
                    start_time = time.time()
                    parsed_df = parse_file(u_file)
                    duration = time.time() - start_time
                    add_to_memory(parsed_df, u_file.name)
                    st.toast(f"Auto-committed `{u_file.name}` ({len(parsed_df)} rows) in {format_duration(duration)}!", icon="📂")
                except Exception as e:
                    st.error(f"Error parsing `{u_file.name}`: {e}")

    master_df = st.session_state.master_df
    num_loaded_files = len(st.session_state.loaded_files)
    num_master_rows = len(master_df) if master_df is not None else 0

    if master_df is None or num_master_rows == 0:
        st.info("Please upload one or more dataset files above to build your memory cluster.")
        return

    # Prominent Proceed to Analysis Button for users who don't want to enrich
    if not is_sidebar:
        st.markdown("""
        <div style="background-color: rgba(105, 122, 162, 0.06); border: 1px solid rgba(105, 122, 162, 0.2); border-left: 5px solid #697aa2; padding: 14px 18px; border-radius: 8px; margin-top: 10px; margin-bottom: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <strong style="color: #1E293B; font-size: 15px;"><i class="bi bi-check-circle-fill" style="color: #697aa2;"></i> Dataset Loaded & Memory Cluster Active!</strong>
                    <div style="color: #475569; font-size: 13.5px; margin-top: 2px;">You can proceed directly into the interactive analysis workspace (Dashboards, Science Mapping, Stratification) without running enrichment.</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if hasattr(st, "dialog"):
            @st.dialog("Name Your Project Workspace")
            def prompt_project_name_modal():
                st.markdown("""
                Give your project a descriptive title. A dedicated directory will be created under `Projects/<Project_Name>/` with separate subfolders for:
                - `logs/`: Enrichment, Stratification, and Gender audit reports.
                - `exports/`: Timestamped datasets and visual exports.
                - `sessions/`: Serialized flow models and progress checkpoints.
                """)
                default_name = st.session_state.get("active_project_name", f"Review_{get_timestamp_str()}")
                if default_name == "Default_Project":
                    default_name = f"Review_{get_timestamp_str()}"
                    
                p_name_input = st.text_input("Project Workspace Name:", value=default_name, placeholder="e.g. Healthcare_AI_Review")
                
                b_c1, b_c2 = st.columns(2)
                with b_c1:
                    if st.button("Create & Enter Workspace", type="primary", width="stretch", icon=":material/rocket_launch:"):
                        set_active_project(p_name_input)
                        st.session_state.fullscreen_core = False
                        st.session_state.last_enrich_completed = False
                        st.rerun()
                with b_c2:
                    if st.button("Use Default Name", width="stretch", icon=":material/check:"):
                        set_active_project(default_name)
                        st.session_state.fullscreen_core = False
                        st.session_state.last_enrich_completed = False
                        st.rerun()
        else:
            def prompt_project_name_modal():
                set_active_project(st.session_state.get("active_project_name", "Default_Project"))
                st.session_state.fullscreen_core = False
                st.rerun()

        if st.button("Proceed Directly to Analysis Workspace (Skip Enrichment)", type="primary", width="stretch", key="proceed_main_btn", icon=":material/arrow_forward:"):
            prompt_project_name_modal()
        st.divider()

    # 2. STREAMLIT TABS LAYOUT (De-cluttered UI)
    tab_diag, tab_memory = st.tabs(["Diagnostics & Smart Enrich", "Data Memory & Exports"])

    with tab_diag:
        st.caption(f"Target Context: Combined Cluster ({num_master_rows} total records across {num_loaded_files} files)")
        
        # Post-enrichment Success Banner (if just completed)
        if st.session_state.get('last_enrich_completed', False):
            st.markdown("""
            <div style="background-color: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.3); border-left: 5px solid #22c55e; padding: 14px 18px; border-radius: 8px; margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <strong style="color: #166534; font-size: 15px;"><i class="bi bi-check-circle-fill" style="color: #22c55e;"></i> Data Enrichment Succeeded!</strong>
                        <div style="color: #15803d; font-size: 13.5px; margin-top: 2px;">Your dataset was enhanced across all 5 tiers. You can inspect updated columns below or proceed to the analysis workspace.</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            p_col1, p_col2 = st.columns([1, 3])
            with p_col1:
                if st.button("Proceed to Analysis Workspace", type="primary", icon=":material/arrow_forward:", key="proceed_after_enrich"):
                    prompt_project_name_modal()
            with p_col2:
                if st.button("Dismiss Banner & Stay in Data Prep", icon=":material/close:", key="dismiss_enrich_banner"):
                    st.session_state.last_enrich_completed = False
                    st.rerun()
            st.divider()

        # Comprehensive Guide & Instructions Panel
        with st.expander("📖 Guide: How Data Enrichment & Multi-Tier Fallbacks Work", expanded=False):
            st.markdown("""
            ### What is Bibliographic Data Enrichment?
            When bibliographies are exported from academic databases (Scopus, Web of Science, PubMed, Google Scholar, etc.), records often have incomplete data: missing abstracts, incomplete affiliations, outdated citation counts, missing publication places, or unindexed keywords.
            The **5-Tier Enrichment Engine** connects to scientific open-access registries to automatically populate these gaps without manual work.

            ---
            ### The 5-Tier Fallback Hierarchy
            When enrichment runs, each record cascades through 5 specialized APIs:
            1. **Tier 1 (OpenAlex Batch API):** Fast bulk queries via DOIs that resolve author affiliations, publication years, fresh citation counts, abstracts, journal names, and concept maps.
            2. **Tier 2 (Crossref REST API):** Official DOI registration agency fallback to recover official publisher names, container journal titles, dates, volumes, and page numbers.
            3. **Tier 3 (PubMed / NLM eUtils):** Biomedical authority fallback using PMIDs to fetch authoritative MeSH terms and clinical abstracts.
            4. **Tier 4 (Semantic Scholar API):** AI-powered scholarly index fallback for retrieving missing paper abstracts and TLDR summaries.
            5. **Tier 5 (OpenAlex Fuzzy Title Matching):** For local or non-DOI records (e.g., conference papers or institutional preprints), searches by title to recover true DOIs and complete metadata.

            ---
            ### 1-Click Multi-Tier Profiles
            - **Smart Enrich (X Missing):** Dynamically inspects your current dataset and only queries the APIs for the specific columns that have empty/missing values in memory.
            - **Basic Enrich:** Quickly enriches foundational bibliographic publishing data (`Author`, `Publication Year`, `Times Cited`, `Publisher`, `Journal`, `Article References`).
            - **Smart + Basic Enrich:** Merges detected missing fields with the core publishing metadata.
            - **Smart + All (Ultimate Enrich):** The **ultimate button**. Evaluates all records across all 5 tiers for all 20+ fields (including resolving missing DOIs, live citation updates, full abstracts, author addresses, conference locations, and funding).

            *Note: All API queries are cached locally for 7 days, so re-running enrichment on the same dataset is instantaneous.*
            """)

        # Categorized Core Diagnostics (Only shows main mapping columns on core screen)
        display_error_info(master_df, key_prefix=f"prep_diag_{'side' if is_sidebar else 'main'}", is_core_screen=True, is_sidebar=is_sidebar)
        
        st.divider()

        # Missing Fields Auto-detection across all possible fields
        all_possible_enrich_fields = [
            'Title', 'Author', 'Publication Year', 'Times Cited', 'Publisher', 'Journal',
            'Article References', 'Affiliations', 'Country', 'Address', 'Location',
            'Abstract', 'Keywords', 'Concepts', 'Document Type', 'Language', 'Open Access',
            'Funding', 'DOI', 'OpenAlex ID', 'ISSN'
        ]
        basic_fields = ['Author', 'Publication Year', 'Times Cited', 'Publisher', 'Journal', 'Article References']
        
        field_stats = {}
        for field in all_possible_enrich_fields:
            if field in master_df.columns:
                is_nan = master_df[field].isna()
                is_empty = master_df[field].apply(lambda x: isinstance(x, str) and x.strip() == '') if master_df[field].dtype == object else False
                missing_count = int((is_nan | is_empty).sum())
            else:
                missing_count = num_master_rows
            if missing_count > 0:
                field_stats[field] = {
                    'count': missing_count,
                    'pct': (missing_count / num_master_rows) * 100 if num_master_rows > 0 else 0
                }
        missing_fields = list(field_stats.keys())

        # Live Smart Enrich Pre-Flight Card (Transparent Before-You-Click breakdown)
        st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B; margin-top: 10px;'><i class='bi bi-rocket-takeoff-fill' style='color: #697aa2;'></i> 1-Click Multi-Tier Enrichment Hub</h3>", unsafe_allow_html=True)
        
        with st.container():
            st.markdown(f"""
            <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #697aa2; padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;">
                <div style="font-weight: 700; color: #1E293B; font-size: 13.5px; margin-bottom: 4px;">
                    <i class="bi bi-search" style="color: #697aa2;"></i> Live Smart Enrich Pre-Flight Plan
                </div>
                <div style="color: #475569; font-size: 12.5px;">
                    Scanning current dataset detected <b>{len(missing_fields)} fields</b> with incomplete or missing records.
                </div>
            </div>
            """, unsafe_allow_html=True)

            if missing_fields:
                badges_html = []
                for f in missing_fields:
                    pct = field_stats[f]['pct']
                    cnt = field_stats[f]['count']
                    # Color coding based on severity of missingness
                    if pct >= 70:
                        bg_col = "#FEE2E2"
                        text_col = "#991B1B"
                        border_col = "#FCA5A5"
                    elif pct >= 30:
                        bg_col = "#FEF3C7"
                        text_col = "#92400E"
                        border_col = "#FCD34D"
                    else:
                        bg_col = "#E0F2FE"
                        text_col = "#075985"
                        border_col = "#BAE6FD"

                    badges_html.append(
                        f"<div style='display: inline-flex; align-items: center; background: {bg_col}; border: 1px solid {border_col}; "
                        f"border-radius: 6px; padding: 4px 8px; margin: 3px; font-size: 12px; color: {text_col};'>"
                        f"<strong style='margin-right: 4px;'>{f}</strong>"
                        f"<span style='opacity: 0.85;'>({pct:.0f}% • {cnt} missing)</span>"
                        f"</div>"
                    )

                st.markdown(
                    "<div style='margin-bottom: 12px;'>"
                    "<div style='font-size: 13px; font-weight: 700; color: #334155; margin-bottom: 6px;'>🎯 Smart Enrich Will Target:</div>"
                    f"<div style='display: flex; flex-wrap: wrap; gap: 4px;'>{''.join(badges_html)}</div>"
                    "</div>",
                    unsafe_allow_html=True
                )
            else:
                st.success("✨ All 20+ schema fields are currently 100% populated in memory!")

        enrich_target_fields = None
        is_ultimate_run = False
        
        # Primary Action Buttons: Stacked in sidebar, 4 columns in fullscreen
        if is_sidebar:
            b_c1, b_c2 = st.columns(2, gap="small")
            with b_c1:
                if st.button(f"Smart Enrich ({len(missing_fields)})", icon=":material/auto_fix_high:", width="stretch", type="primary", disabled=len(missing_fields) == 0, key="btn_side_smart", help="Targets only missing fields."):
                    enrich_target_fields = missing_fields.copy()
                    is_ultimate_run = False
                if st.button("Smart + Basic", icon=":material/auto_awesome:", width="stretch", key="btn_side_smart_basic", help="Missing fields + Basic 6."):
                    enrich_target_fields = list(set(missing_fields + basic_fields))
                    is_ultimate_run = False
            with b_c2:
                if st.button("Basic (Core 6)", icon=":material/bolt:", width="stretch", key="btn_side_basic", help="Author, Year, Citations, Publisher, Journal, References."):
                    enrich_target_fields = basic_fields.copy()
                    is_ultimate_run = False
                if st.button("Ultimate (All 21)", icon=":material/done_all:", width="stretch", key="btn_side_ultimate", help="Targets all fields across all 5 tiers."):
                    enrich_target_fields = all_possible_enrich_fields.copy()
                    is_ultimate_run = True
        else:
            c1, c2, c3, c4 = st.columns(4, gap="small")
            with c1:
                if st.button(f"Smart Enrich ({len(missing_fields)} Missing)", icon=":material/auto_fix_high:", width="stretch", type="primary", disabled=len(missing_fields) == 0, key="btn_main_smart", help="Targets only the fields detected as missing in the pre-flight plan above."):
                    enrich_target_fields = missing_fields.copy()
                    is_ultimate_run = False

            with c2:
                if st.button("Basic Enrich (Core 6)", icon=":material/bolt:", width="stretch", key="btn_main_basic", help="Enriches foundational publishing metadata: Author, Year, Times Cited, Publisher, Journal, and References."):
                    enrich_target_fields = basic_fields.copy()
                    is_ultimate_run = False

            with c3:
                smart_basic_combined = list(set(missing_fields + basic_fields))
                if st.button("Smart + Basic Enrich", icon=":material/auto_awesome:", width="stretch", key="btn_main_smart_basic", help="Combines your detected missing fields with core publishing metadata."):
                    enrich_target_fields = smart_basic_combined
                    is_ultimate_run = False

            with c4:
                if st.button("Smart + All (Ultimate)", icon=":material/done_all:", width="stretch", key="btn_main_ultimate", help="The ultimate button: targets all 21 fields across all 5 tiers, refreshes live citation counts, and resolves missing DOIs."):
                    enrich_target_fields = all_possible_enrich_fields.copy()
                    is_ultimate_run = True

        # Feature Clusters & Custom Selection
        st.markdown("<h4 style='font-size: 16px; font-weight: 700; color: #1E293B; margin-top: 20px;'><i class='bi bi-grid-3x3-gap-fill' style='color: #697aa2;'></i> Feature Clusters & Custom Field Selection</h4>", unsafe_allow_html=True)
        clusters = {
            "Basic Metadata": basic_fields,
            "English Normalization": ['Title', 'Abstract', 'Keywords', 'Concepts'],
            "Author Demographics": ['Affiliations', 'Country', 'Address'],
            "Conference & Venue": ['Location'],
            "Semantic Data": ['Abstract', 'Keywords', 'Concepts'],
            "Filters & Access": ['Document Type', 'Language', 'Open Access', 'ISSN'],
            "Funding Context": ['Funding']
        }
        
        multi_key = f"multi_{'side' if is_sidebar else 'main'}"
        if multi_key not in st.session_state:
            st.session_state[multi_key] = missing_fields.copy()

        # Quick cluster toggle buttons (responsive for sidebar vs fullscreen)
        if is_sidebar:
            st.caption("Quick Cluster Presets:")
            sb_r1_c1, sb_r1_c2 = st.columns(2, gap="small")
            with sb_r1_c1:
                if st.button("Select All", icon=":material/done_all:", width="stretch", key="sq_all"):
                    st.session_state[multi_key] = all_possible_enrich_fields.copy()
                    st.rerun()
                if st.button("Basic Metadata", icon=":material/add_circle:", width="stretch", key="sq_bas"):
                    st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Basic Metadata"]))
                    st.rerun()
                if st.button("Demographics", icon=":material/person_pin_circle:", width="stretch", key="sq_demo", help="Affiliations, Country, Address"):
                    st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Author Demographics"]))
                    st.rerun()
                if st.button("Semantic NLP", icon=":material/psychology:", width="stretch", key="sq_sem"):
                    st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Semantic Data"]))
                    st.rerun()

            with sb_r1_c2:
                if st.button("Clear All", icon=":material/delete_sweep:", width="stretch", key="sq_clr"):
                    st.session_state[multi_key] = []
                    st.rerun()
                if st.button("English Texts", icon=":material/translate:", width="stretch", key="sq_eng"):
                    st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["English Normalization"]))
                    st.rerun()
                if st.button("Conference Venue", icon=":material/place:", width="stretch", key="sq_venue", help="Location"):
                    st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Conference & Venue"]))
                    st.rerun()
                if st.button("Funding Context", icon=":material/payments:", width="stretch", key="sq_fund"):
                    st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Funding Context"]))
                    st.rerun()
        else:
            cl_cols = st.columns(8, gap="small")
            if cl_cols[0].button("+ All", icon=":material/done_all:", width="stretch", key="mq_all"):
                st.session_state[multi_key] = all_possible_enrich_fields.copy()
                st.rerun()
            if cl_cols[1].button("+ English", icon=":material/translate:", width="stretch", key="mq_eng"):
                st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["English Normalization"]))
                st.rerun()
            if cl_cols[2].button("+ Basic", icon=":material/add:", width="stretch", key="mq_bas"):
                st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Basic Metadata"]))
                st.rerun()
            if cl_cols[3].button("+ Demographics", icon=":material/person_pin_circle:", width="stretch", key="mq_demo", help="Author Demographics (Affiliations, Country, Address)"):
                st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Author Demographics"]))
                st.rerun()
            if cl_cols[4].button("+ Venue", icon=":material/place:", width="stretch", key="mq_venue", help="Conference & Venue Location"):
                st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Conference & Venue"]))
                st.rerun()
            if cl_cols[5].button("+ Semantic", icon=":material/psychology:", width="stretch", key="mq_sem"):
                st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Semantic Data"]))
                st.rerun()
            if cl_cols[6].button("+ Funding", icon=":material/payments:", width="stretch", key="mq_fund"):
                st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Funding Context"]))
                st.rerun()
            if cl_cols[7].button("Clear", icon=":material/delete_sweep:", width="stretch", key="mq_clr"):
                st.session_state[multi_key] = []
                st.rerun()

        all_available_fields = list(set([field for sublist in clusters.values() for field in sublist]))
        fields_custom = st.multiselect("Selected fields to enrich:", options=all_available_fields, key=multi_key)
        
        if st.button("Run Selected Custom Clusters", icon=":material/play_arrow:", width="stretch", disabled=len(fields_custom) == 0, key=f"run_clusters_{'side' if is_sidebar else 'main'}"):
            enrich_target_fields = fields_custom
            is_ultimate_run = False

        # Full-width Execution Container below buttons & custom cluster selector
        if enrich_target_fields is not None:
            st.markdown("<hr style='margin: 15px 0; border-color: #E2E8F0;'>", unsafe_allow_html=True)
            with st.spinner("Executing 5-Tier Multi-Tier Data Enrichment Engine..."):
                df_processed = enrich_dataset_openalex(
                    master_df.copy(), 
                    enrich_target_fields, 
                    st.session_state.execution_logs, 
                    file_manifest=st.session_state.file_manifest,
                    is_ultimate=is_ultimate_run
                )
                st.session_state.master_df = df_processed
                st.session_state.last_enrich_completed = True
                st.toast("Multi-Tier Data Enrichment Complete!", icon="🎉")
                st.rerun()

    with tab_memory:
        st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B;'><i class='bi bi-hdd-network-fill' style='color: #697aa2;'></i> Memory & Export Hub</h3>", unsafe_allow_html=True)
        
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Total Articles in Cluster", f"{num_master_rows:,}")
        m_col2.metric("Files Uploaded", num_loaded_files)
        m_col3.metric("Capacity Used", f"{(num_master_rows / MAX_ROWS):.1%}")

        if st.session_state.master_df is not None:
            # Display uploaded files log breakdown
            if st.session_state.file_manifest:
                st.markdown("<div style='font-weight:700; margin-top:10px;'><i class='bi bi-folder-fill' style='color:#697aa2;'></i> Uploaded Files Log</div>", unsafe_allow_html=True)
                manifest_df = pd.DataFrame([
                    {"File Name": fname, "Rows Contributed": rcount}
                    for fname, rcount in st.session_state.file_manifest.items()
                ])
                st.dataframe(manifest_df, width="stretch", hide_index=True, height=140)

            st.caption("Combined Dataset Preview:")
            st.dataframe(st.session_state.master_df.head(5), width="stretch", height=180)

            st.markdown("<div style='font-weight:700; margin-top:10px;'><i class='bi bi-download' style='color:#697aa2;'></i> Export Combined Cluster</div>", unsafe_allow_html=True)
            df_export = st.session_state.master_df
            ec1, ec2, ec3, ec4, ec5 = st.columns(5)
            
            fn_csv = format_timestamped_filename("exported_data.csv")
            data_csv = df_to_csv(df_export)
            try: save_project_file("exports", fn_csv, data_csv, mode="wb")
            except Exception: pass
            with ec1: st.download_button("CSV", data=data_csv, file_name=fn_csv, icon=":material/download:", width="stretch")
            
            fn_xlsx = format_timestamped_filename("exported_data.xlsx")
            data_xlsx = df_to_excel(df_export)
            try: save_project_file("exports", fn_xlsx, data_xlsx, mode="wb")
            except Exception: pass
            with ec2: st.download_button("Excel", data=data_xlsx, file_name=fn_xlsx, icon=":material/download:", width="stretch")
            
            fn_ris = format_timestamped_filename("exported_data.ris")
            data_ris = df_to_ris(df_export)
            try: save_project_file("exports", fn_ris, data_ris, mode="wb")
            except Exception: pass
            with ec3: st.download_button("RIS", data=data_ris, file_name=fn_ris, icon=":material/download:", width="stretch")
            
            fn_bib = format_timestamped_filename("exported_data.bib")
            data_bib = df_to_bib(df_export)
            try: save_project_file("exports", fn_bib, data_bib, mode="wb")
            except Exception: pass
            with ec4: st.download_button("BibTeX", data=data_bib, file_name=fn_bib, icon=":material/download:", width="stretch")
            
            fn_nbib = format_timestamped_filename("exported_data.nbib")
            data_nbib = df_to_nbib(df_export)
            try: save_project_file("exports", fn_nbib, data_nbib, mode="wb")
            except Exception: pass
            with ec5: st.download_button("NBIB", data=data_nbib, file_name=fn_nbib, icon=":material/download:", width="stretch")

            if st.button("Wipe Memory / Clear All Files", icon=":material/delete_forever:", type="primary", width="stretch"):
                st.session_state.master_df = None
                st.session_state.loaded_files = []
                st.session_state.file_manifest = {}
                st.session_state.fullscreen_core = True
                st.rerun()

        st.divider()
        with st.expander("Detailed Enrichment Execution Logs & Audit Trail", expanded=False):
            if "last_enrichment_report" in st.session_state and st.session_state.last_enrichment_report:
                fn_audit = format_timestamped_filename("enrichment_audit.log")
                st.download_button(
                    "Download Full Audit Log (.log)",
                    data=st.session_state.last_enrichment_report,
                    file_name=fn_audit,
                    mime="text/plain",
                    width="stretch"
                )
                st.code(st.session_state.last_enrichment_report, language="text")
            elif len(st.session_state.execution_logs) > 0:
                for log in st.session_state.execution_logs:
                    if isinstance(log, str) and "======" in log:
                        st.code(log, language="text")
                    else:
                        st.markdown(f"**>** `{log}`")
            else:
                st.caption("No enrichment execution logs recorded yet.")