import streamlit as st
import tempfile
import os
import time
import pandas as pd
from core.ingestion import parse_file, TARGET_COLUMNS, deduplicate_and_merge_columns, remove_blank_rows
from core.enrichment import enrich_dataset_openalex
from core.export import df_to_csv, df_to_excel, df_to_ris, df_to_bib, df_to_nbib
from dashboard.metrics_general import display_error_info

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
                    st.toast(f"Auto-committed `{u_file.name}` ({len(parsed_df)} rows) to memory!", icon="📂")
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
        if st.button("Proceed Directly to Analysis Workspace (Skip Enrichment)", type="primary", width="stretch", key="proceed_main_btn", icon=":material/arrow_forward:"):
            st.session_state.fullscreen_core = False
            st.rerun()
        st.divider()

    # 2. STREAMLIT TABS LAYOUT (De-cluttered UI)
    tab_diag, tab_memory = st.tabs(["Diagnostics & Smart Enrich", "Data Memory & Exports"])

    with tab_diag:
        st.caption(f"Target Context: Combined Cluster ({num_master_rows} total records across {num_loaded_files} files)")
        
        # Categorized Core Diagnostics (Only shows main mapping columns on core screen)
        display_error_info(master_df, key_prefix="prep_diag", is_core_screen=True)
        
        st.divider()

        # Missing Fields Auto-detection
        all_possible_enrich_fields = [
            'Title', 'Author', 'Publication Year', 'Times Cited', 'Publisher', 'Article References',
            'Affiliations', 'Country', 'Abstract', 'Keywords', 'Concepts',
            'Document Type', 'Language', 'Open Access', 'Funding'
        ]
        basic_fields = ['Author', 'Publication Year', 'Times Cited', 'Publisher', 'Article References']
        
        missing_fields = []
        for field in all_possible_enrich_fields:
            if field in master_df.columns:
                is_nan = master_df[field].isna()
                is_empty = master_df[field].apply(lambda x: isinstance(x, str) and x.strip() == '') if master_df[field].dtype == object else False
                if (is_nan | is_empty).any():
                    missing_fields.append(field)
            else:
                missing_fields.append(field)

        enrich_target_fields = None

        st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B; margin-top: 15px;'><i class='bi bi-rocket-takeoff-fill' style='color: #697aa2;'></i> 1-Click Multi-Tier Enrichment Hub</h3>", unsafe_allow_html=True)
        
        # 4 Primary Action Buttons on the same line
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            if st.button(f"Smart Enrich ({len(missing_fields)} Missing)", icon=":material/auto_fix_high:", width="stretch", type="primary", disabled=len(missing_fields) == 0):
                enrich_target_fields = missing_fields.copy()

        with c2:
            if st.button("Basic Enrich", icon=":material/bolt:", width="stretch"):
                enrich_target_fields = basic_fields.copy()

        with c3:
            smart_basic_combined = list(set(missing_fields + basic_fields))
            if st.button("Smart + Basic Enrich", icon=":material/auto_awesome:", width="stretch"):
                enrich_target_fields = smart_basic_combined

        with c4:
            if st.button("Smart + All", icon=":material/done_all:", width="stretch"):
                enrich_target_fields = all_possible_enrich_fields.copy()

        # Feature Clusters & Custom Selection
        st.markdown("<h4 style='font-size: 16px; font-weight: 700; color: #1E293B; margin-top: 15px;'><i class='bi bi-grid-3x3-gap-fill' style='color: #697aa2;'></i> Feature Clusters & Custom Field Selection</h4>", unsafe_allow_html=True)
        clusters = {
            "Basic Metadata": basic_fields,
            "English Normalization": ['Title', 'Abstract', 'Keywords', 'Concepts'],
            "Demographics": ['Affiliations', 'Country'],
            "Semantic Data": ['Abstract', 'Keywords', 'Concepts'],
            "Filters": ['Document Type', 'Language', 'Open Access'],
            "Funding Context": ['Funding']
        }
        
        multi_key = f"multi_{'side' if is_sidebar else 'main'}"
        if multi_key not in st.session_state:
            st.session_state[multi_key] = missing_fields.copy()

        # Quick cluster toggle buttons
        cl_cols = st.columns(8, gap="small")
        if cl_cols[0].button("+ All", icon=":material/done_all:", width="stretch"):
            st.session_state[multi_key] = all_possible_enrich_fields.copy()
            st.rerun()
        if cl_cols[1].button("+ English", icon=":material/translate:", width="stretch"):
            st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["English Normalization"]))
            st.rerun()
        if cl_cols[2].button("+ Basic", icon=":material/add:", width="stretch"):
            st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Basic Metadata"]))
            st.rerun()
        if cl_cols[3].button("+ Demo", icon=":material/public:", width="stretch"):
            st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Demographics"]))
            st.rerun()
        if cl_cols[4].button("+ Semantic", icon=":material/psychology:", width="stretch"):
            st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Semantic Data"]))
            st.rerun()
        if cl_cols[5].button("+ Filters", icon=":material/filter_alt:", width="stretch"):
            st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Filters"]))
            st.rerun()
        if cl_cols[6].button("+ Funding", icon=":material/payments:", width="stretch"):
            st.session_state[multi_key] = list(set(st.session_state[multi_key] + clusters["Funding Context"]))
            st.rerun()
        if cl_cols[7].button("Clear", icon=":material/delete_sweep:", width="stretch"):
            st.session_state[multi_key] = []
            st.rerun()

        all_available_fields = list(set([field for sublist in clusters.values() for field in sublist]))
        fields_custom = st.multiselect("Selected fields to enrich:", options=all_available_fields, key=multi_key)
        
        if st.button("Run Selected Custom Clusters", icon=":material/play_arrow:", width="stretch", disabled=len(fields_custom) == 0):
            enrich_target_fields = fields_custom

        # Full-width Execution Container below buttons & custom cluster selector
        if enrich_target_fields is not None:
            st.markdown("<hr style='margin: 15px 0; border-color: #E2E8F0;'>", unsafe_allow_html=True)
            with st.spinner("Executing 5-Tier Multi-Tier Data Enrichment Engine..."):
                df_processed = enrich_dataset_openalex(master_df.copy(), enrich_target_fields, st.session_state.execution_logs, file_manifest=st.session_state.file_manifest)
                st.session_state.master_df = df_processed
                st.toast("Multi-Tier Data Enrichment Complete!")
                st.session_state.fullscreen_core = False
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
            with ec1: st.download_button("CSV", data=df_to_csv(df_export), file_name="exported_data.csv", icon=":material/download:", width="stretch")
            with ec2: st.download_button("Excel", data=df_to_excel(df_export), file_name="exported_data.xlsx", icon=":material/download:", width="stretch")
            with ec3: st.download_button("RIS", data=df_to_ris(df_export), file_name="exported_data.ris", icon=":material/download:", width="stretch")
            with ec4: st.download_button("BibTeX", data=df_to_bib(df_export), file_name="exported_data.bib", icon=":material/download:", width="stretch")
            with ec5: st.download_button("NBIB", data=df_to_nbib(df_export), file_name="exported_data.nbib", icon=":material/download:", width="stretch")

            if st.button("Wipe Memory / Clear All Files", icon=":material/delete_forever:", type="primary", width="stretch"):
                st.session_state.master_df = None
                st.session_state.loaded_files = []
                st.session_state.file_manifest = {}
                st.session_state.fullscreen_core = True
                st.rerun()

        st.divider()
        with st.expander("Detailed Enrichment Execution Logs & Audit Trail", expanded=False):
            if "last_enrichment_report" in st.session_state and st.session_state.last_enrichment_report:
                st.download_button(
                    "Download Full Audit Log (.log)",
                    data=st.session_state.last_enrichment_report,
                    file_name="enrichment_audit.log",
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