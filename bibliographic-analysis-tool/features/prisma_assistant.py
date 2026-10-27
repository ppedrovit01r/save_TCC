import streamlit as st
import pandas as pd
import html
from utils.formatters import clean_year_value
from utils.project_manager import format_timestamped_filename, get_active_project_name
from utils.exports import _save_export_on_click

# --- DEFAULT PEDAGOGICAL EXEMPLAR CRITERIA (Kitchenham 2007 & Petersen 2008/2015) ---
DEFAULT_INCLUSION_CRITERIA = [
    {
        'id': 'IC 1',
        'title': 'Domain Relevance',
        'desc': 'The study must propose, evaluate, or survey data deduplication techniques, frameworks, algorithms, or architectures.'
    },
    {
        'id': 'IC 2',
        'title': 'Specific Context',
        'desc': 'The study must focus on chunk-level deduplication, entity resolution, or sequence deduplication in empirical settings.'
    },
    {
        'id': 'IC 3',
        'title': 'Contribution Type',
        'desc': 'The study must present a primary contribution, such as a new algorithm, an empirical evaluation, a taxonomic framework, or a comprehensive review.'
    },
    {
        'id': 'IC 4',
        'title': 'Language',
        'desc': 'The study must be written entirely in English.'
    },
    {
        'id': 'IC 5',
        'title': 'Publication Type',
        'desc': 'The study must be peer-reviewed and published in a conference proceeding, journal, or book chapter.'
    }
]

DEFAULT_EXCLUSION_CRITERIA = [
    {
        'id': 'EC 1',
        'title': 'Out of Scope',
        'desc': 'The study focuses on deduplication in an unrelated domain (e.g., excluding record linkage if focus is hardware storage deduplication).',
        'stage': 'Title_Abstract'
    },
    {
        'id': 'EC 2',
        'title': 'Secondary Focus',
        'desc': 'The study mentions deduplication only as a passing example or minor pre-processing step without detailing the underlying mechanism.',
        'stage': 'Title_Abstract'
    },
    {
        'id': 'EC 3',
        'title': 'Data Limits',
        'desc': 'The study lacks sufficient technical details, evaluation metrics, or empirical data to assess its validity.',
        'stage': 'Full_Text'
    },
    {
        'id': 'EC 4',
        'title': 'Grey Literature',
        'desc': 'The study is an extended abstract, preprint (e.g., arXiv papers without peer review), editorial, white paper, or presentation slide deck.',
        'stage': 'Title_Abstract'
    }
]

def infer_default_database_name(filename: str) -> str:
    """Infers an intelligent default digital library name from filename heuristics."""
    s = filename.lower()
    if 'scopus' in s:
        return 'Scopus'
    elif 'ieee' in s:
        return 'IEEE Xplore'
    elif 'acm' in s:
        return 'ACM Digital Library'
    elif 'wos' in s or 'webofscience' in s or 'web_of_science' in s:
        return 'Web of Science'
    elif 'pubmed' in s or 'medline' in s or s.endswith('.nbib'):
        return 'PubMed'
    elif 'springer' in s:
        return 'SpringerLink'
    elif 'sciencedirect' in s or 'elsevier' in s:
        return 'ScienceDirect'
    else:
        clean = filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
        return clean if clean else 'Generic Database'

def _clean_html_label(text: str) -> str:
    """Escapes special characters (&, <, >, quotes) for safe inclusion in Graphviz HTML-like labels."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)

def _render_html(html_str: str):
    """Renders HTML in Streamlit ensuring all leading indentation is dedented so Markdown never interprets it as a code block."""
    import textwrap
    st.markdown(textwrap.dedent(html_str).strip(), unsafe_allow_html=True)


def is_missing_abstract(val) -> bool:
    """Returns True if the abstract is None, NaN, empty, or a generic placeholder."""
    if val is None:
        return True
    if isinstance(val, (pd.Series, dict)):
        abstract_val = val.get('Abstract')
        if abstract_val is None:
            abstract_val = val.get('abstract', '')
        val = abstract_val
    elif isinstance(val, pd.DataFrame):
        if 'Abstract' in val.columns:
            val = val['Abstract'].iloc[0] if len(val) > 0 else ''
        else:
            val = ''
            
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except (ValueError, TypeError):
        pass

    s = str(val).strip()
    if not s:
        return True
    clean_lower = s.lower().strip(" .[]")
    if clean_lower in ('', 'no abstract', 'no abstract available', '[no abstract]', '[no abstract available]', 'none', 'nan', 'null', 'abstract unavailable', 'not available', 'n/a', 'na'):
        return True
    if len(s) < 10 and clean_lower in ('-', '.', 'na', 'n/a'):
        return True
    return False

def auto_save_prisma_state(prisma_state):
    """Safely auto-saves the active PRISMA state to disk in the active project directory."""
    try:
        from utils.project_manager import save_project_prisma_state, get_active_project_name
        proj_name = prisma_state.get('project_name') or get_active_project_name()
        prisma_state['project_name'] = proj_name
        return save_project_prisma_state(prisma_state, project_name=proj_name)
    except Exception as e:
        print(f"Auto-save PRISMA state notice: {e}")
        return ""

def get_raw_retrieved_audit_stats(loaded_files, file_manifest, raw_df, prisma_duplicates=None):
    """
    Computes rigorous raw audit statistics ensuring mathematical consistency:
    total_raw_retrieved - total_duplicates == total_screened_pool
    where total_screened_pool matches len(raw_df).
    """
    file_raw_counts = {}
    dups_list = prisma_duplicates or []
    if not isinstance(dups_list, list):
        dups_list = []
        
    dup_file_counts = {}
    for d in dups_list:
        if isinstance(d, dict) and 'removed' in d:
            rem = d['removed']
            fname = None
            if isinstance(rem, dict):
                fname = rem.get('Source File')
            elif hasattr(rem, 'get'):
                fname = rem.get('Source File')
            if fname:
                dup_file_counts[fname] = dup_file_counts.get(fname, 0) + 1

    for fname in loaded_files:
        cnt = 0
        if file_manifest and fname in file_manifest and file_manifest[fname] > 0:
            cnt = int(file_manifest[fname])
        elif raw_df is not None and 'Source File' in raw_df.columns:
            surv = int((raw_df['Source File'] == fname).sum())
            dups_for_f = int(dup_file_counts.get(fname, 0))
            cnt = surv + dups_for_f
        elif raw_df is not None:
            cnt = len(raw_df)
        file_raw_counts[fname] = max(1, cnt) if (cnt > 0 or not loaded_files) else 0

    total_raw = sum(file_raw_counts.values())
    total_dups = len(dups_list)
    raw_df_len = len(raw_df) if raw_df is not None else 0

    if total_raw < raw_df_len + total_dups:
        total_raw = raw_df_len + total_dups

    total_screen_pool = max(0, total_raw - total_dups)
    if raw_df_len > 0 and total_screen_pool != raw_df_len:
        if total_dups == 0:
            total_raw = raw_df_len
            total_screen_pool = raw_df_len
        else:
            total_screen_pool = raw_df_len
            total_raw = raw_df_len + total_dups

    return file_raw_counts, total_raw, total_dups, total_screen_pool

def reconcile_screening_queue(prisma_state, raw_df):
    """
    Ensures that every valid study in raw_df that has not been explicitly included
    (screened_ok) or excluded (exclusions) is present in screening_queue, maintaining
    any existing queue ordering while appending any missing un-evaluated studies.
    Guarantees len(screening_queue) == total_records - len(exclusions) - len(screened_ok).
    """
    if raw_df is None or raw_df.empty or prisma_state is None:
        return
        
    valid_indices = list(raw_df.index)
    valid_set = set(valid_indices)
    
    # 1. Sanitize screened_ok
    prisma_state['screened_ok'] = [
        int(i) if str(i).isdigit() else i
        for i in prisma_state.get('screened_ok', [])
        if (int(i) if str(i).isdigit() else i) in valid_set
    ]
    
    # 2. Sanitize exclusions
    sanitized_exclusions = {}
    for k, v in prisma_state.get('exclusions', {}).items():
        clean_k = int(k) if str(k).isdigit() else k
        if clean_k in valid_set:
            sanitized_exclusions[clean_k] = v
    prisma_state['exclusions'] = sanitized_exclusions
    
    evaluated_set = set(prisma_state['exclusions'].keys()) | set(prisma_state['screened_ok'])
    
    # 3. Filter existing queue to valid, un-evaluated studies only
    existing_queue = [
        int(i) if str(i).isdigit() else i
        for i in prisma_state.get('screening_queue', [])
        if (int(i) if str(i).isdigit() else i) in valid_set and (int(i) if str(i).isdigit() else i) not in evaluated_set
    ]
    existing_queue_set = set(existing_queue)
    
    # 4. Append any un-evaluated studies that were missing from the queue
    for idx in valid_indices:
        if idx not in evaluated_set and idx not in existing_queue_set:
            existing_queue.append(idx)
            existing_queue_set.add(idx)
            
    # Did the queue change? If so, persist changes to state and disk
    if existing_queue != prisma_state.get('screening_queue', []):
        prisma_state['screening_queue'] = existing_queue
        auto_save_prisma_state(prisma_state)
    else:
        prisma_state['screening_queue'] = existing_queue

def execute_auto_exclude_missing_abstracts(raw_df, prisma_state, custom_ec_id=None, custom_ec_title=None):
    """
    Finds all candidate studies with missing or empty abstracts,
    records them under Pre-Screening Exclusions alongside duplicates,
    removes them from the screening queue, and ensures Phase 2 Exclusion Criteria
    remain purely thematic/methodological.
    Returns (num_excluded, 'Pre_Screening').
    """
    queue = prisma_state.get('screening_queue', list(raw_df.index))
    missing_indices = []
    for idx in queue:
        if idx in raw_df.index:
            try:
                row = raw_df.loc[idx]
                if is_missing_abstract(row):
                    missing_indices.append(idx)
            except Exception:
                pass

    for idx in missing_indices:
        if prisma_state.get('mode') == 'basic':
            if "Missing Abstract" not in prisma_state.get('custom_reasons', []):
                prisma_state['custom_reasons'].append("Missing Abstract")
            prisma_state['exclusions'][idx] = "Missing Abstract"
        else:
            prisma_state['exclusions'][idx] = {
                'code': 'PRE_NO_ABS',
                'reason': 'Missing Abstract',
                'full_text': 'Missing Abstract: Excluded before screening due to lack of text.',
                'stage': 'Pre_Screening'
            }

    missing_set = set(missing_indices)
    prisma_state['screening_queue'] = [i for i in queue if i not in missing_set]
    prisma_state['screened_ok'] = [i for i in prisma_state.get('screened_ok', []) if i not in missing_set]
    
    # Track missing abstracts count under pre-screening
    current_cnt = prisma_state.get('missing_abstracts_count', 0)
    prisma_state['missing_abstracts_count'] = current_cnt + len(missing_indices)
    prisma_state['auto_exclude_missing_abstracts'] = True

    # Ensure no duplicate EC for missing abstracts remains in Phase 2 exclusion_criteria
    ecs = prisma_state.get('exclusion_criteria', [])
    prisma_state['exclusion_criteria'] = [
        ec for ec in ecs if 'abstract' not in ec.get('title', '').lower() and 'abstract' not in ec.get('id', '').lower()
    ]
    prisma_state['missing_abstracts_override'] = None
    prisma_state['db_final_overrides'] = {}
    st.session_state.pop('ov_missing_abstracts_cnt', None)

    reconcile_screening_queue(prisma_state, raw_df)
    auto_save_prisma_state(prisma_state)

    return len(missing_indices), 'Pre_Screening'


def execute_restore_missing_abstracts(raw_df, prisma_state):
    """
    Restores studies that were excluded due to missing abstracts back into the screening queue.
    """
    restored = 0
    to_delete = []
    for idx, ex in list(prisma_state.get('exclusions', {}).items()):
        if isinstance(ex, dict) and (ex.get('stage') == 'Pre_Screening' or ex.get('code') == 'PRE_NO_ABS' or 'abstract' in ex.get('reason', '').lower()):
            to_delete.append(idx)
        elif isinstance(ex, str) and 'abstract' in ex.lower():
            to_delete.append(idx)
            
    for idx in to_delete:
        if idx in prisma_state['exclusions']:
            del prisma_state['exclusions'][idx]
            restored += 1
            
    prisma_state['missing_abstracts_count'] = 0
    prisma_state['auto_exclude_missing_abstracts'] = False
    prisma_state['missing_abstracts_override'] = None
    prisma_state['db_final_overrides'] = {}
    st.session_state.pop('ov_missing_abstracts_cnt', None)
    reconcile_screening_queue(prisma_state, raw_df)
    auto_save_prisma_state(prisma_state)
    return restored


def show(master_df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-diagram-3-fill' style='color: #697aa2;'></i> PRISMA Assistant</h2>", unsafe_allow_html=True)
    st.caption("Standard & Advanced Systematic Literature Review (SLR) Protocol Engine (Kitchenham et al., 2007; Petersen et al., 2008/2015)")

    if master_df is None or master_df.empty:
        st.warning("No dataset loaded. Please go to Data Preparation to load your articles.")
        return

    from utils.project_manager import get_active_project_name, load_project_prisma_state, save_project_prisma_state, get_project_root
    active_proj_name = get_active_project_name()

    # Resolve candidate studies pool entering Phase 2:
    # 1. Use session-cached candidate DataFrame if present
    # 2. Or load uploaded_candidates.csv from project directory
    # 3. Or use raw_df_backup / master_df and persist candidate pool
    raw_df = None
    import os
    proj_root = get_project_root(active_proj_name)
    candidates_csv = os.path.join(proj_root, "uploaded_candidates.csv")

    if 'prisma_raw_df' in st.session_state and st.session_state.prisma_raw_df is not None and not st.session_state.prisma_raw_df.empty:
        raw_df = st.session_state.prisma_raw_df
    elif os.path.exists(candidates_csv):
        try:
            raw_df = pd.read_csv(candidates_csv)
            st.session_state.prisma_raw_df = raw_df
        except Exception:
            raw_df = None

    if raw_df is None or raw_df.empty:
        if 'raw_df_backup' in st.session_state and st.session_state.raw_df_backup is not None and not st.session_state.raw_df_backup.empty:
            raw_df = st.session_state.raw_df_backup
        else:
            raw_df = master_df
        st.session_state.prisma_raw_df = raw_df
        try:
            raw_df.to_csv(candidates_csv, index=False)
        except Exception:
            pass

    needs_load = (
        'prisma_state' not in st.session_state
        or st.session_state.prisma_state is None
        or st.session_state.prisma_state.get('project_name') != active_proj_name
    )

    if needs_load:
        saved_disk_state = load_project_prisma_state(project_name=active_proj_name, valid_indices=raw_df.index)
        if saved_disk_state:
            saved_disk_state['project_name'] = active_proj_name
            st.session_state.prisma_state = saved_disk_state
        else:
            st.session_state.prisma_state = {
                'project_name': active_proj_name,
                'mode': 'advanced', # 'basic' or 'advanced'
                'exclusions': {}, # row_index -> reason string (basic) or dict (advanced)
                'custom_reasons': ["Off-topic", "Wrong Language", "Not Peer-Reviewed", "Wrong Population", "Wrong Outcome"],
                'screening_queue': list(raw_df.index),
                'screened_ok': [],
                'file_db_mapping': {}, # filename -> db_name
                'db_initial_query_hits': {}, # db_name -> int (manual entry)
                'db_ic_progression': {}, # db_name -> {ic_id: int} (manual entry)
                'db_uploaded_overrides': {}, # db_name -> int (optional manual override for uploaded file count)
                'inclusion_criteria': [dict(c) for c in DEFAULT_INCLUSION_CRITERIA],
                'exclusion_criteria': [dict(c) for c in DEFAULT_EXCLUSION_CRITERIA],
                'ec_overrides': {},
                'db_final_overrides': {}
            }
            # Auto-save immediately so the project file is established on disk
            save_project_prisma_state(st.session_state.prisma_state, project_name=active_proj_name)
    
    prisma_state = st.session_state.prisma_state
    prisma_state['project_name'] = active_proj_name

    if 'db_ic_progression' not in prisma_state:
        prisma_state['db_ic_progression'] = {}
    if 'db_uploaded_overrides' not in prisma_state:
        prisma_state['db_uploaded_overrides'] = {}

    # Self-heal stale zero overrides from legacy sessions so live screening exclusions always appear in diagrams
    live_ec_tally = {}
    for ex_v in prisma_state.get('exclusions', {}).values():
        if isinstance(ex_v, dict):
            c_code = ex_v.get('code', '')
            if c_code and c_code != 'PRE_NO_ABS' and ex_v.get('stage') != 'Pre_Screening':
                live_ec_tally[c_code] = live_ec_tally.get(c_code, 0) + 1
    if 'ec_overrides' in prisma_state and isinstance(prisma_state['ec_overrides'], dict):
        stale_zero_keys = [
            k for k, v in prisma_state['ec_overrides'].items()
            if v == 0 and (live_ec_tally.get(k, 0) > 0 or all(val == 0 for val in prisma_state['ec_overrides'].values()))
        ]
        if stale_zero_keys:
            for k in stale_zero_keys:
                prisma_state['ec_overrides'].pop(k, None)
                st.session_state.pop(f"ov_ec_{k}", None)
            auto_save_prisma_state(prisma_state)

    if prisma_state.get('duplicates_override') == 0:
        prisma_state['duplicates_override'] = None
    if prisma_state.get('missing_abstracts_override') == 0:
        prisma_state['missing_abstracts_override'] = None

    # Clean up legacy "Missing Abstract" ECs: move to Pre_Screening and remove from Phase 2 ECs
    ecs = prisma_state.get('exclusion_criteria', [])
    legacy_abs_ec = next((ec for ec in ecs if 'abstract' in ec.get('title', '').lower() or 'abstract' in ec.get('id', '').lower()), None)
    if legacy_abs_ec:
        legacy_id = legacy_abs_ec.get('id')
        migrated_cnt = 0
        for idx, ex in list(prisma_state.get('exclusions', {}).items()):
            if isinstance(ex, dict) and ex.get('code') == legacy_id:
                ex['stage'] = 'Pre_Screening'
                ex['code'] = 'PRE_NO_ABS'
                migrated_cnt += 1
        if migrated_cnt > 0:
            prisma_state['missing_abstracts_count'] = max(prisma_state.get('missing_abstracts_count', 0), migrated_cnt)
            prisma_state['auto_exclude_missing_abstracts'] = True
        prisma_state['exclusion_criteria'] = [ec for ec in ecs if ec.get('id') != legacy_id]
        auto_save_prisma_state(prisma_state)

    # Self-healing queue reconciliation: guarantees all un-evaluated studies are present in screening queue
    reconcile_screening_queue(prisma_state, raw_df)

    # Initialize file_db_mapping with any loaded files not yet registered
    loaded_files = st.session_state.get('loaded_files', [])
    if not loaded_files and 'Source File' in raw_df.columns:
        loaded_files = [f for f in raw_df['Source File'].dropna().unique()]
    
    for fname in loaded_files:
        if fname not in prisma_state['file_db_mapping']:
            if 'Source Database' in raw_df.columns and 'Source File' in raw_df.columns:
                match_db = raw_df.loc[raw_df['Source File'] == fname, 'Source Database'].dropna()
                if not match_db.empty and str(match_db.iloc[0]).strip() not in ('', 'Unspecified', 'nan'):
                    prisma_state['file_db_mapping'][fname] = str(match_db.iloc[0]).strip()
                    continue
            prisma_state['file_db_mapping'][fname] = infer_default_database_name(fname)

    # --- PROJECT PERSISTENCE HEADER BAR ---
    c_head_info, c_head_btn = st.columns([2.8, 1.2])
    with c_head_info:
        st.caption(f"<i class='bi bi-folder2-open'></i> **Project Storage:** `Projects/{active_proj_name}/prisma_state.json` — all protocol criteria, custom hits, IC funnel counts, and screening logs are automatically preserved.", unsafe_allow_html=True)
    with c_head_btn:
        if st.button("Save SLR Progress", icon=":material/save:", key="btn_save_prisma_header", width="stretch", help="Persists your SLR screening decisions and custom audit counts to disk."):
            saved_p = auto_save_prisma_state(prisma_state)
            if saved_p:
                st.toast(f"SLR protocol & progress saved successfully to Projects/{active_proj_name}!", icon=":material/check_circle:")
            else:
                st.error(f"Error saving SLR progress to Projects/{active_proj_name}.")

    # --- WORKFLOW MODE SELECTOR ---
    col_mode_sel, col_mode_info = st.columns([1.4, 2.6])
    with col_mode_sel:
        current_mode = prisma_state.get('mode', 'advanced')
        selected_mode = st.radio(
            "Workflow Mode:",
            ["Basic PRISMA (Single Stream)", "Advanced SLR (Kitchenham & Petersen)"],
            index=1 if current_mode == 'advanced' else 0,
            horizontal=True,
            key="radio_prisma_mode"
        )
        new_mode = 'basic' if selected_mode.startswith("Basic") else 'advanced'
        if new_mode != current_mode:
            prisma_state['mode'] = new_mode
            auto_save_prisma_state(prisma_state)
            st.rerun()

    with col_mode_info:
        if prisma_state['mode'] == 'advanced':
            _render_html("""
            <div style="background-color: #F0FDF4; border-left: 4px solid #16A34A; padding: 8px 12px; border-radius: 4px; font-size: 13px; color: #166534; margin-top: 15px;">
                <i class="bi bi-shield-check"></i> <strong>Advanced SLR Protocol Active:</strong> Multi-database provenance, customized Inclusion & Exclusion Criteria (IC/EC), and Petersen Systematic Mapping diagramming.
            </div>
            """)
        else:
            _render_html("""
            <div style="background-color: #F8FAFC; border-left: 4px solid #64748B; padding: 8px 12px; border-radius: 4px; font-size: 13px; color: #475569; margin-top: 15px;">
                <i class="bi bi-lightning-charge"></i> <strong>Basic PRISMA Active:</strong> Fast single-pool screening with preset exclusion tags and standard PRISMA 2020 diagramming.
            </div>
            """)

    st.divider()

    # =========================================================================
    # RENDER TABS BASED ON ACTIVE WORKFLOW MODE
    # =========================================================================

    if prisma_state['mode'] == 'basic':
        # -----------------------------
        # BASIC PRISMA MODE (3 TABS)
        # -----------------------------
        tab_screening, tab_duplicates, tab_flowchart = st.tabs([
            "Screening & Exclusion", 
            "Excluded Duplicates", 
            "PRISMA Flowchart Generator"
        ])

        with tab_screening:
            _render_basic_screening_tab(raw_df, prisma_state)

        with tab_duplicates:
            _render_duplicates_tab()

        with tab_flowchart:
            _render_basic_flowchart_tab(raw_df, prisma_state)

    else:
        # ---------------------------------------------------
        # ADVANCED SLR MODE (KITCHENHAM & PETERSEN) (5 TABS)
        # ---------------------------------------------------
        tab_db_map, tab_protocol, tab_screening, tab_duplicates, tab_flowchart = st.tabs([
            "1. Database Provenance & Grouping",
            "2. Protocol & Criteria (IC / EC)",
            "3. Assisted Screening & Evaluation",
            "4. Excluded Duplicates",
            "5. PRISMA & Petersen Flowchart"
        ])

        with tab_db_map:
            _render_database_mapping_tab(raw_df, prisma_state, loaded_files)

        with tab_protocol:
            _render_protocol_criteria_tab(raw_df, prisma_state)

        with tab_screening:
            _render_advanced_screening_tab(raw_df, prisma_state)

        with tab_duplicates:
            _render_duplicates_tab()

        with tab_flowchart:
            _render_advanced_flowchart_tab(raw_df, prisma_state)


# =============================================================================
# TAB IMPLEMENTATIONS: ADVANCED SLR MODE
# =============================================================================

def _render_database_mapping_tab(raw_df, prisma_state, loaded_files):
    st.markdown("### <i class='bi bi-hdd-network-fill' style='color:#697aa2;'></i> Multi-Database Provenance & Phase 1 Manual Audit", unsafe_allow_html=True)
    st.markdown("""
    In a Systematic Literature Review, **Phase 1 (Search Execution & Inclusion Criteria)** takes place in the external digital libraries (e.g., Scopus, IEEE Xplore, PubMed) *before* articles are exported and uploaded into this tool.
    **After Phase 1** and **before Phase 2 (Exclusion Criteria)**, the resulting articles are uploaded to this tool, where **deduplication** is automatically performed.
    """)

    if not loaded_files:
        st.info("No individual source files registered. Using entire dataset as a single database source.")
        return

    file_manifest = st.session_state.get('file_manifest', {})
    prisma_dups = st.session_state.get('prisma_duplicates', [])
    file_raw_counts, total_raw, total_dups, total_screen_pool = get_raw_retrieved_audit_stats(loaded_files, file_manifest, raw_df, prisma_dups)

    # Global Audit Baseline Banner (Post-Phase 1 Upload & Deduplication Bridge)
    _render_html(f"""
    <div style="background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 12px 16px; border-radius: 6px; font-size: 13.5px; color: #0F172A; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">
        <div style="margin-bottom: 4px;">
            <i class="bi bi-cloud-arrow-up-fill" style="color:#0284C7;"></i> <strong>Phase 1 Intake &amp; Pre-Phase 2 Deduplication:</strong>
        </div>
        <strong>{total_raw:,}</strong> candidate studies retrieved across <strong>{len(loaded_files)}</strong> file(s) (post-Phase 1 ICs) &nbsp;|&nbsp; 
        <span style="color:#DC2626;"><strong>- {total_dups:,}</strong> duplicate records removed</span> &nbsp;|&nbsp; 
        <span style="color:#166534;"><strong>{total_screen_pool:,}</strong> unique candidate studies entering Phase 2 (EC Screening)</span>
    </div>
    """)

    st.markdown("#### <i class='bi bi-1-circle-fill' style='color:#0284C7;'></i> Step 1: Map Uploaded Files to Source Digital Libraries", unsafe_allow_html=True)
    
    col_files, col_summary = st.columns([1.6, 1.4], gap="large")

    with col_files:
        st.caption("Assign each uploaded file to its digital library of origin (multiple files can share the same database name):")
        changed = False
        for idx, fname in enumerate(loaded_files):
            file_rows = file_raw_counts.get(fname, 0)
            
            c_f1, c_f2 = st.columns([1.3, 1.7])
            with c_f1:
                st.markdown(f"**`{fname}`**<br><span style='color:#64748B; font-size:12px;'>{file_rows:,} candidate records retrieved</span>", unsafe_allow_html=True)
            with c_f2:
                old_db = prisma_state['file_db_mapping'].get(fname, infer_default_database_name(fname))
                new_db = st.text_input(
                    f"Database for {fname}",
                    value=old_db,
                    key=f"db_in_{idx}_{fname}",
                    label_visibility="collapsed",
                    placeholder="e.g. Scopus, IEEE Xplore, ACM DL"
                ).strip()
                if new_db and new_db != old_db:
                    prisma_state['file_db_mapping'][fname] = new_db
                    # Carry over manual Phase 1 numbers if renaming a database
                    if old_db in prisma_state.get('db_initial_query_hits', {}) and new_db not in prisma_state['db_initial_query_hits']:
                        prisma_state['db_initial_query_hits'][new_db] = prisma_state['db_initial_query_hits'].pop(old_db)
                    if old_db in prisma_state.get('db_ic_progression', {}) and new_db not in prisma_state['db_ic_progression']:
                        prisma_state['db_ic_progression'][new_db] = prisma_state['db_ic_progression'].pop(old_db)
                    auto_save_prisma_state(prisma_state)
                    changed = True
        if changed:
            st.rerun()

    # Compute grouping
    db_groups = {}
    for fname in loaded_files:
        assigned_db = prisma_state['file_db_mapping'].get(fname, 'Unspecified Database').strip()
        if not assigned_db:
            assigned_db = 'Unspecified Database'
        if assigned_db not in db_groups:
            db_groups[assigned_db] = {'files': [], 'imported_count': 0}
        db_groups[assigned_db]['files'].append(fname)
        db_groups[assigned_db]['imported_count'] += file_raw_counts.get(fname, 0)

    with col_summary:
        st.caption("Aggregated candidate studies retrieved per digital library (post-Phase 1):")
        for db_name, grp in db_groups.items():
            _render_html(f"""
            <div style="background-color:#FFFFFF; border:1px solid #E2E8F0; border-left:4px solid #697aa2; padding:10px 14px; border-radius:6px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <strong style="color:#1E293B; font-size:14px;"><i class="bi bi-database"></i> {db_name}</strong><br>
                    <span style="color:#64748B; font-size:12px;">Files: {', '.join(grp['files'])}</span>
                </div>
                <div style="background-color:#E0F2FE; color:#0369A1; font-weight:700; font-size:13px; padding:4px 10px; border-radius:999px;">
                    {grp['imported_count']:,} retrieved studies
                </div>
            </div>
            """)

    st.divider()

    # =========================================================================
    # STEP 2: PHASE 1 MANUAL NUMBERS (INITIAL HITS & INCLUSION CRITERIA)
    # =========================================================================
    c_p1_hdr, c_p1_rst = st.columns([3.0, 1.0])
    with c_p1_hdr:
        st.markdown("#### <i class='bi bi-2-circle-fill' style='color:#0284C7;'></i> Step 2: Phase 1 Manual Numbers — Search Execution & Inclusion Criteria (Pre-Upload)", unsafe_allow_html=True)
        st.caption("Every number in Phase 1 (Initial Search Hits and surviving articles after each Inclusion Criterion) is manually entered by you based on your external digital library queries. Changes saved here automatically update the entire PRISMA module and flowcharts.")
    with c_p1_rst:
        if st.button("Reset Phase 1 to 0", icon=":material/restart_alt:", key="btn_reset_p1_zeros", width="stretch", help="Clears all Phase 1 numbers back to 0 so you can enter them fresh."):
            for db_n in db_groups.keys():
                prisma_state['db_initial_query_hits'][db_n] = 0
                st.session_state[f"hits_{db_n}"] = 0
                st.session_state[f"ov_p1_init_{db_n}"] = 0
                prisma_state['db_ic_progression'][db_n] = {}
                for ic_item in prisma_state.get('inclusion_criteria', []):
                    iid = ic_item['id']
                    prisma_state['db_ic_progression'][db_n][iid] = 0
                    st.session_state[f"ic_funnel_{db_n}_{iid}"] = 0
                    st.session_state[f"ov_p1_ic_{db_n}_{iid}"] = 0
            auto_save_prisma_state(prisma_state)
            st.toast("Reset all Phase 1 numbers to 0!", icon=":material/restart_alt:")
            st.rerun()

    ics = prisma_state.get('inclusion_criteria', [])

    for idx_db, (db_name, grp) in enumerate(db_groups.items()):
        imported_cnt = grp['imported_count']
        if db_name not in prisma_state['db_initial_query_hits']:
            prisma_state['db_initial_query_hits'][db_name] = 0
        if db_name not in prisma_state['db_ic_progression']:
            prisma_state['db_ic_progression'][db_name] = {}

        with st.container(border=True):
            _render_html(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                <div>
                    <span style="font-size:15px; font-weight:700; color:#0F172A;"><i class="bi bi-funnel-fill" style="color:#0284C7;"></i> Phase 1 Funnel for Digital Library: <code style="color:#0369A1;">{db_name}</code></span>
                </div>
                <div style="background-color:#F0FDF4; border:1px solid #BBF7D0; color:#166534; font-size:12.5px; font-weight:600; padding:4px 12px; border-radius:6px;">
                    <i class="bi bi-box-arrow-in-right"></i> Retrieved Candidate Studies (Phase 1 Intake): <strong>{imported_cnt:,} studies</strong>
                </div>
            </div>
            """)

            num_cols = 1 + len(ics)
            funnel_cols = st.columns([1.2] + [1.0] * len(ics)) if ics else [st.container()]

            # 1. Initial Search Hits (Manual)
            hit_key_t1 = f"hits_{db_name}"
            hit_key_t5 = f"ov_p1_init_{db_name}"
            saved_hits = int(prisma_state['db_initial_query_hits'].get(db_name, 0))
            st.session_state[hit_key_t1] = saved_hits

            def _on_hits_change(db=db_name, k1=hit_key_t1, k5=hit_key_t5):
                val = int(st.session_state[k1])
                prisma_state['db_initial_query_hits'][db] = val
                st.session_state[k5] = val
                auto_save_prisma_state(prisma_state)

            with funnel_cols[0]:
                st.number_input(
                    f"Initial Hits ({db_name})",
                    min_value=0,
                    step=1,
                    key=hit_key_t1,
                    on_change=_on_hits_change,
                    help="Manually enter the initial number of search query hits returned by this digital library before applying Inclusion Criteria."
                )

            # 2. Sequential Inclusion Criteria (Manual)
            for idx_ic, ic in enumerate(ics):
                ic_id = ic['id']
                ic_title = ic.get('title', '')
                ic_key_t1 = f"ic_funnel_{db_name}_{ic_id}"
                ic_key_t5 = f"ov_p1_ic_{db_name}_{ic_id}"

                if ic_id not in prisma_state['db_ic_progression'][db_name]:
                    prisma_state['db_ic_progression'][db_name][ic_id] = 0
                saved_ic_val = int(prisma_state['db_ic_progression'][db_name].get(ic_id, 0))
                st.session_state[ic_key_t1] = saved_ic_val

                def _on_ic_change(db=db_name, iid=ic_id, k1=ic_key_t1, k5=ic_key_t5):
                    val = int(st.session_state[k1])
                    prisma_state['db_ic_progression'].setdefault(db, {})[iid] = val
                    st.session_state[k5] = val
                    auto_save_prisma_state(prisma_state)

                with funnel_cols[idx_ic + 1]:
                    short_title = ic_title if len(ic_title) <= 18 else ic_title[:16] + ".."
                    st.number_input(
                        f"After {ic_id} ({short_title})",
                        min_value=0,
                        step=1,
                        key=ic_key_t1,
                        on_change=_on_ic_change,
                        help=f"{ic_id}: {ic_title} — Manually enter the number of studies remaining after applying this Inclusion Criterion."
                    )

    # Synchronize database provenance into the actual dataframe
    db_lookup = {fname: prisma_state['file_db_mapping'].get(fname, 'Unspecified').strip() for fname in loaded_files}
    if 'Source File' in raw_df.columns:
        raw_df['Source Database'] = raw_df['Source File'].map(db_lookup).fillna('Unspecified')
        if st.session_state.master_df is not None and 'Source File' in st.session_state.master_df.columns:
            st.session_state.master_df['Source Database'] = st.session_state.master_df['Source File'].map(db_lookup).fillna('Unspecified')

    st.success("Database mappings and Phase 1 manual audit numbers are synchronized across the entire PRISMA module.", icon=":material/check_circle:")


def renumber_inclusion_criteria(prisma_state):
    """
    Renumbers all inclusion criteria sequentially as 'IC 1', 'IC 2', ..., 'IC N'.
    Safely synchronizes any progression numbers tracked in 'db_ic_progression'.
    """
    ics = prisma_state.get('inclusion_criteria', [])
    id_mapping = {}
    for idx, ic in enumerate(ics):
        old_id = ic['id']
        new_id = f"IC {idx + 1}"
        ic['id'] = new_id
        if old_id != new_id:
            id_mapping[old_id] = new_id

    # Safely rebuild db_ic_progression to avoid dictionary key collision overwrites
    for db_name, db_dict in list(prisma_state.get('db_ic_progression', {}).items()):
        if isinstance(db_dict, dict):
            new_prog = {}
            for k, val in db_dict.items():
                mapped_k = id_mapping.get(k, k)
                new_prog[mapped_k] = val
            prisma_state['db_ic_progression'][db_name] = new_prog
    auto_save_prisma_state(prisma_state)


def renumber_exclusion_criteria(prisma_state):
    """
    Renumbers all exclusion criteria sequentially as 'EC 1', 'EC 2', ..., 'EC N'.
    Safely synchronizes any recorded study exclusions in 'exclusions'.
    """
    ecs = prisma_state.get('exclusion_criteria', [])
    id_mapping = {}
    for idx, ec in enumerate(ecs):
        old_id = ec['id']
        new_id = f"EC {idx + 1}"
        ec['id'] = new_id
        if old_id != new_id:
            id_mapping[old_id] = new_id

    # Safely update recorded study exclusions
    for ex_data in prisma_state.get('exclusions', {}).values():
        if isinstance(ex_data, dict):
            old_code = ex_data.get('code')
            if old_code in id_mapping:
                ex_data['code'] = id_mapping[old_code]
    auto_save_prisma_state(prisma_state)


def renumber_all_criteria(prisma_state):
    """Renumbers both ICs and ECs sequentially."""
    renumber_inclusion_criteria(prisma_state)
    renumber_exclusion_criteria(prisma_state)


def _render_protocol_criteria_tab(raw_df, prisma_state):
    from utils.project_manager import get_active_project_name
    active_proj_name = prisma_state.get('project_name') or get_active_project_name()

    st.markdown("### <i class='bi bi-clipboard2-check-fill' style='color:#697aa2;'></i> SLR Protocol: Inclusion & Exclusion Criteria (IC & EC)", unsafe_allow_html=True)
    
    # Methodological Guide Accordion
    with st.expander("Methodological Guide: Formulating IC & EC (Kitchenham & Petersen Guidelines)", expanded=False, icon=":material/menu_book:"):
        st.markdown("""
        #### How to Define SLR Criteria Properly:
        In Systematic Literature Reviews (Kitchenham et al., 2007) and Systematic Mapping Studies (Petersen et al., 2008/2015), the review protocol establishes boundaries to ensure replicability and prevent researcher bias:

        *   **Inclusion Criteria (IC)**: Define what **MUST** be true for a study to enter the candidate pool. They guide search string formulation and initial retrieval scope (e.g., Domain Relevance, Contribution Type, Specific Context, Language, Publication Type).
        *   **Exclusion Criteria (EC)**: Define explicit disqualifiers applied sequentially during Title/Abstract and Full-Text screening (e.g., Out of Scope, Secondary Focus, Data Limits, Grey Literature, Duplicates).
        
        > [!NOTE]
        > **Methodological Flexibility**: Language, Document Type, or Duplication can be framed as an Inclusion Criterion (e.g. *IC 4: Written entirely in English*) or an Exclusion Criterion (e.g. *EC 1: Exclude non-English*). Neither is wrong—it depends on your formal research protocol. You can reorder, convert, and reassign any criterion freely below!
        """)
        
        if st.button("Load Pedagogical Exemplar Protocol Template", icon=":material/auto_stories:", type="secondary", help="Resets criteria in this project to the textbook Kitchenham & Petersen exemplar template."):
            prisma_state['inclusion_criteria'] = [dict(c) for c in DEFAULT_INCLUSION_CRITERIA]
            prisma_state['exclusion_criteria'] = [dict(c) for c in DEFAULT_EXCLUSION_CRITERIA]
            auto_save_prisma_state(prisma_state)
            st.toast(f"Pedagogical exemplar template loaded and saved for project '{active_proj_name}'!", icon=":material/check_circle:")
            st.rerun()

    # Toolbar for Global Actions & Dedicated Project Storage
    c_tool_info, c_tool_renum, c_tool_save = st.columns([2.0, 1.2, 1.3])
    with c_tool_info:
        st.markdown(f"**Project Workspace:** <span style='background:#F1F5F9; color:#1E293B; padding:2px 8px; border-radius:4px; font-weight:600; font-family: monospace;'>Projects/{active_proj_name}/prisma_state.json</span>", unsafe_allow_html=True)
        st.caption(f"All criteria edits, reordering, and renumbering are permanently saved to project **{active_proj_name}**.")
    with c_tool_renum:
        if st.button("Auto-Renumber All", icon=":material/format_list_numbered:", type="secondary", width="stretch", help="Renumber all ICs and ECs sequentially (IC 1..N and EC 1..N)"):
            renumber_all_criteria(prisma_state)
            st.toast("Renumbered all Inclusion and Exclusion Criteria sequentially!", icon=":material/check_circle:")
            st.rerun()
    with c_tool_save:
        if st.button("Save Protocol Criteria", icon=":material/save:", type="primary", width="stretch", help=f"Explicitly writes all Inclusion and Exclusion criteria to Projects/{active_proj_name}/prisma_state.json"):
            saved_p = auto_save_prisma_state(prisma_state)
            if saved_p:
                st.toast(f"All criteria successfully saved to Projects/{active_proj_name}!", icon=":material/check_circle:")
            else:
                st.error(f"Error saving criteria to Projects/{active_proj_name}.")

    st.divider()

    col_ic, col_ec = st.columns(2, gap="large")

    # 1. INCLUSION CRITERIA (IC) COLUMN
    with col_ic:
        c_ic_title, c_ic_renum = st.columns([2, 1.2])
        with c_ic_title:
            st.markdown("#### <i class='bi bi-check2-circle' style='color:#16A34A;'></i> Inclusion Criteria (IC)", unsafe_allow_html=True)
        with c_ic_renum:
            if st.button("Renumber ICs", icon=":material/format_list_numbered:", key="btn_renum_ics", help="Renumber all ICs sequentially as IC 1, IC 2, ..., IC N"):
                renumber_inclusion_criteria(prisma_state)
                st.toast("Renumbered Inclusion Criteria sequentially!", icon=":material/check_circle:")
                st.rerun()

        st.caption("Criteria that justify including a study in the review scope:")

        ics = prisma_state.get('inclusion_criteria', [])
        
        for i, ic in enumerate(ics):
            with st.container(border=True):
                c_top1, c_acts = st.columns([1.7, 2.3])
                with c_top1:
                    st.markdown(f"**<span style='background:#DCFCE7; color:#166534; padding:2px 8px; border-radius:4px;'>{ic['id']}</span> {ic['title']}**", unsafe_allow_html=True)
                
                edit_key = f"edit_ic_active_{i}"
                is_editing = st.session_state.get(edit_key, False)
                
                with c_acts:
                    b_up, b_down, b_to_ec, b_edit, b_del = st.columns([1, 1, 1.6, 1.3, 1.1])
                    with b_up:
                        if st.button("", key=f"up_ic_{i}", icon=":material/arrow_upward:", help=f"Move {ic['id']} up", disabled=(i == 0)):
                            ics[i], ics[i - 1] = ics[i - 1], ics[i]
                            auto_save_prisma_state(prisma_state)
                            st.rerun()
                    with b_down:
                        if st.button("", key=f"down_ic_{i}", icon=":material/arrow_downward:", help=f"Move {ic['id']} down", disabled=(i == len(ics) - 1)):
                            ics[i], ics[i + 1] = ics[i + 1], ics[i]
                            auto_save_prisma_state(prisma_state)
                            st.rerun()
                    with b_to_ec:
                        if st.button("To EC", key=f"conv_ic_{i}", icon=":material/swap_horiz:", help=f"Convert {ic['id']} to Exclusion Criterion"):
                            ic_to_move = ics.pop(i)
                            existing_ec_ids = {c['id'] for c in prisma_state.get('exclusion_criteria', [])}
                            next_num = len(prisma_state.get('exclusion_criteria', [])) + 1
                            while f"EC {next_num}" in existing_ec_ids:
                                next_num += 1
                            new_ec_id = f"EC {next_num}"
                            prisma_state.setdefault('exclusion_criteria', []).append({
                                'id': new_ec_id,
                                'title': ic_to_move.get('title', ''),
                                'stage': 'Title_Abstract',
                                'desc': ic_to_move.get('desc', '')
                            })
                            auto_save_prisma_state(prisma_state)
                            st.toast(f"Converted '{ic_to_move.get('title', '')}' to Exclusion Criterion ({new_ec_id})!", icon=":material/check_circle:")
                            st.rerun()
                    with b_edit:
                        btn_label = "Cancel" if is_editing else "Edit"
                        btn_icon = ":material/close:" if is_editing else ":material/edit:"
                        if st.button(btn_label, key=f"btn_toggle_edit_ic_{i}", icon=btn_icon, help=f"Edit {ic['id']}"):
                            st.session_state[edit_key] = not is_editing
                            st.rerun()
                    with b_del:
                        if st.button("Del", key=f"del_ic_{i}", icon=":material/delete:", help=f"Delete {ic['id']}"):
                            ics.pop(i)
                            auto_save_prisma_state(prisma_state)
                            st.rerun()
                
                if is_editing:
                    st.divider()
                    edit_id = st.text_input("Criterion ID", value=ic['id'], key=f"input_id_ic_{i}")
                    edit_title = st.text_input("Criterion Title", value=ic['title'], key=f"input_title_ic_{i}")
                    edit_desc = st.text_area("Criterion Description", value=ic.get('desc', ''), key=f"input_desc_ic_{i}")
                    if st.button("Save Changes", key=f"save_ic_{i}", type="primary", icon=":material/save:"):
                        old_ic_id = ic['id']
                        new_ic_id = edit_id.strip()
                        if not new_ic_id:
                            st.error("Criterion ID cannot be empty.")
                        elif new_ic_id != old_ic_id and any(c['id'] == new_ic_id for idx_c, c in enumerate(ics) if idx_c != i):
                            st.error(f"Duplicate ID '{new_ic_id}' already exists. Criteria IDs must be unique. Or use 'Renumber ICs'.")
                        else:
                            ics[i] = {
                                'id': new_ic_id,
                                'title': edit_title.strip(),
                                'desc': edit_desc.strip()
                            }
                            if new_ic_id != old_ic_id:
                                for db_p in prisma_state.get('db_ic_progression', {}).values():
                                     if isinstance(db_p, dict) and old_ic_id in db_p:
                                         db_p[new_ic_id] = db_p.pop(old_ic_id)
                            auto_save_prisma_state(prisma_state)
                            st.session_state[edit_key] = False
                            st.toast(f"Updated {new_ic_id} successfully!", icon=":material/check_circle:")
                            st.rerun()
                else:
                    st.markdown(f"<span style='color:#475569; font-size:13px;'>{ic['desc']}</span>", unsafe_allow_html=True)

        with st.expander("+ Add New Inclusion Criterion", expanded=False):
            new_ic_id = st.text_input("Criterion ID", value=f"IC {len(ics) + 1}", key="add_ic_id")
            new_ic_title = st.text_input("Criterion Title", placeholder="e.g. Domain Relevance", key="add_ic_title")
            new_ic_desc = st.text_area("Criterion Description", placeholder="e.g. The study must propose or evaluate...", key="add_ic_desc")
            if st.button("Add Inclusion Criterion", type="primary", icon=":material/add:"):
                clean_id = new_ic_id.strip()
                clean_title = new_ic_title.strip()
                if not clean_id or not clean_title:
                    st.warning("Please provide both an ID and a Title for the criterion.")
                elif any(c['id'] == clean_id for c in ics):
                    st.error(f"Criterion ID '{clean_id}' already exists. Please choose a unique ID or use Auto-Renumber.")
                else:
                    ics.append({
                        'id': clean_id,
                        'title': clean_title,
                        'desc': new_ic_desc.strip()
                    })
                    auto_save_prisma_state(prisma_state)
                    st.toast(f"Added {clean_id}!", icon=":material/check_circle:")
                    st.rerun()

    # 2. EXCLUSION CRITERIA (EC) COLUMN
    with col_ec:
        c_ec_title, c_ec_renum = st.columns([2, 1.2])
        with c_ec_title:
            st.markdown("#### <i class='bi bi-x-circle' style='color:#DC2626;'></i> Exclusion Criteria (EC)", unsafe_allow_html=True)
        with c_ec_renum:
            if st.button("Renumber ECs", icon=":material/format_list_numbered:", key="btn_renum_ecs", help="Renumber all ECs sequentially as EC 1, EC 2, ..., EC N"):
                renumber_exclusion_criteria(prisma_state)
                st.toast("Renumbered Exclusion Criteria sequentially!", icon=":material/check_circle:")
                st.rerun()

        st.caption("Criteria used to disqualify studies during screening phases:")

        ecs = prisma_state.get('exclusion_criteria', [])

        for j, ec in enumerate(ecs):
            with st.container(border=True):
                c_ec1, c_ec_acts = st.columns([1.7, 2.3])
                stage_label = "Title & Abstract" if ec.get('stage') == 'Title_Abstract' else "Full-Text"
                stage_color = "#E0F2FE" if ec.get('stage') == 'Title_Abstract' else "#FEF3C7"
                stage_text_col = "#0369A1" if ec.get('stage') == 'Title_Abstract' else "#92400E"

                with c_ec1:
                    st.markdown(f"**<span style='background:#FEE2E2; color:#991B1B; padding:2px 8px; border-radius:4px;'>{ec['id']}</span> {ec['title']}** &nbsp; <span style='background:{stage_color}; color:{stage_text_col}; font-size:11px; padding:2px 6px; border-radius:4px;'>{stage_label}</span>", unsafe_allow_html=True)
                
                edit_ec_key = f"edit_ec_active_{j}"
                is_ec_editing = st.session_state.get(edit_ec_key, False)
                
                with c_ec_acts:
                    b_ec_up, b_ec_down, b_to_ic, b_ec_edit, b_ec_del = st.columns([1, 1, 1.6, 1.3, 1.1])
                    with b_ec_up:
                        if st.button("", key=f"up_ec_{j}", icon=":material/arrow_upward:", help=f"Move {ec['id']} up", disabled=(j == 0)):
                            ecs[j], ecs[j - 1] = ecs[j - 1], ecs[j]
                            auto_save_prisma_state(prisma_state)
                            st.rerun()
                    with b_ec_down:
                        if st.button("", key=f"down_ec_{j}", icon=":material/arrow_downward:", help=f"Move {ec['id']} down", disabled=(j == len(ecs) - 1)):
                            ecs[j], ecs[j + 1] = ecs[j + 1], ecs[j]
                            auto_save_prisma_state(prisma_state)
                            st.rerun()
                    with b_to_ic:
                        if st.button("To IC", key=f"conv_ec_{j}", icon=":material/swap_horiz:", help=f"Convert {ec['id']} to Inclusion Criterion"):
                            ec_to_move = ecs.pop(j)
                            existing_ic_ids = {c['id'] for c in prisma_state.get('inclusion_criteria', [])}
                            next_num = len(prisma_state.get('inclusion_criteria', [])) + 1
                            while f"IC {next_num}" in existing_ic_ids:
                                next_num += 1
                            new_ic_id = f"IC {next_num}"
                            prisma_state.setdefault('inclusion_criteria', []).append({
                                'id': new_ic_id,
                                'title': ec_to_move.get('title', ''),
                                'desc': ec_to_move.get('desc', '')
                            })
                            auto_save_prisma_state(prisma_state)
                            st.toast(f"Converted '{ec_to_move.get('title', '')}' to Inclusion Criterion ({new_ic_id})!", icon=":material/check_circle:")
                            st.rerun()
                    with b_ec_edit:
                        btn_label = "Cancel" if is_ec_editing else "Edit"
                        btn_icon = ":material/close:" if is_ec_editing else ":material/edit:"
                        if st.button(btn_label, key=f"btn_toggle_edit_ec_{j}", icon=btn_icon, help=f"Edit {ec['id']}"):
                            st.session_state[edit_ec_key] = not is_ec_editing
                            st.rerun()
                    with b_ec_del:
                        if st.button("Del", key=f"del_ec_{j}", icon=":material/delete:", help=f"Delete {ec['id']}"):
                            ecs.pop(j)
                            auto_save_prisma_state(prisma_state)
                            st.rerun()

                if is_ec_editing:
                    st.divider()
                    edit_ec_id = st.text_input("Criterion ID", value=ec['id'], key=f"input_id_ec_{j}")
                    edit_ec_title = st.text_input("Criterion Title", value=ec['title'], key=f"input_title_ec_{j}")
                    stage_options = ["Title & Abstract Screening", "Full-Text Eligibility Assessment"]
                    default_stage_idx = 0 if ec.get('stage') == 'Title_Abstract' else 1
                    edit_ec_stage = st.selectbox("Stage", stage_options, index=default_stage_idx, key=f"input_stage_ec_{j}")
                    edit_ec_desc = st.text_area("Criterion Description", value=ec.get('desc', ''), key=f"input_desc_ec_{j}")
                    if st.button("Save Changes", key=f"save_ec_{j}", type="primary", icon=":material/save:"):
                        old_ec_id = ec['id']
                        new_ec_id = edit_ec_id.strip()
                        if not new_ec_id:
                            st.error("Criterion ID cannot be empty.")
                        elif new_ec_id != old_ec_id and any(c['id'] == new_ec_id for idx_c, c in enumerate(ecs) if idx_c != j):
                            st.error(f"Duplicate ID '{new_ec_id}' already exists. Criteria IDs must be unique. Or use 'Renumber ECs'.")
                        else:
                            ecs[j] = {
                                'id': new_ec_id,
                                'title': edit_ec_title.strip(),
                                'stage': 'Title_Abstract' if 'Title' in edit_ec_stage else 'Full_Text',
                                'desc': edit_ec_desc.strip()
                            }
                            if new_ec_id != old_ec_id:
                                for ex_data in prisma_state.get('exclusions', {}).values():
                                    if isinstance(ex_data, dict) and ex_data.get('code') == old_ec_id:
                                        ex_data['code'] = new_ec_id
                            auto_save_prisma_state(prisma_state)
                            st.session_state[edit_ec_key] = False
                            st.toast(f"Updated {new_ec_id} successfully!", icon=":material/check_circle:")
                            st.rerun()
                else:
                    st.markdown(f"<span style='color:#475569; font-size:13px;'>{ec['desc']}</span>", unsafe_allow_html=True)

        with st.expander("+ Add New Exclusion Criterion", expanded=False):
            new_ec_id = st.text_input("Criterion ID", value=f"EC {len(ecs) + 1}", key="add_ec_id")
            new_ec_title = st.text_input("Criterion Title", placeholder="e.g. Out of Scope", key="add_ec_title")
            new_ec_stage = st.selectbox("Application Stage", ["Title & Abstract Screening", "Full-Text Eligibility Assessment"], key="add_ec_stage")
            new_ec_desc = st.text_area("Criterion Description", placeholder="e.g. The study focuses on unrelated domain...", key="add_ec_desc")
            if st.button("Add Exclusion Criterion", type="primary", icon=":material/add:"):
                clean_id = new_ec_id.strip()
                clean_title = new_ec_title.strip()
                if not clean_id or not clean_title:
                    st.warning("Please provide both an ID and a Title for the criterion.")
                elif any(c['id'] == clean_id for c in ecs):
                    st.error(f"Criterion ID '{clean_id}' already exists. Please choose a unique ID or use Auto-Renumber.")
                else:
                    ecs.append({
                        'id': clean_id,
                        'title': clean_title,
                        'stage': 'Title_Abstract' if 'Title' in new_ec_stage else 'Full_Text',
                        'desc': new_ec_desc.strip()
                    })
                    auto_save_prisma_state(prisma_state)
                    st.toast(f"Added {clean_id}!", icon=":material/check_circle:")
                    st.rerun()

        # Pre-Screening Filtration Card for Missing Abstracts
        st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("##### <i class='bi bi-funnel-fill' style='color:#0284C7;'></i> Pre-Screening Filtration: Articles with No Abstract", unsafe_allow_html=True)
            st.caption("Automatically purges publications lacking abstracts before Phase 2 screening begins. In your auditable PRISMA flowchart, these are positioned in the middle transition alongside Duplicates, keeping Phase 2 exclusively focused on your thematic/methodological Exclusion Criteria.")

            total_missing_in_dataset = sum(1 for idx in raw_df.index if is_missing_abstract(raw_df.loc[idx]))
            pending_missing_in_queue = sum(1 for idx in prisma_state.get('screening_queue', []) if idx in raw_df.index and is_missing_abstract(raw_df.loc[idx]))
            already_excluded_noabs = sum(1 for ex in prisma_state.get('exclusions', {}).values() if (isinstance(ex, dict) and (ex.get('stage') == 'Pre_Screening' or ex.get('code') == 'PRE_NO_ABS' or 'abstract' in ex.get('reason', '').lower())) or (isinstance(ex, str) and 'abstract' in ex.lower()))

            col_stat1, col_stat2, col_stat3 = st.columns(3)
            col_stat1.metric("Pending in Queue", f"{pending_missing_in_queue:,}")
            col_stat2.metric("Excluded (Pre-Screening)", f"{already_excluded_noabs:,}")
            col_stat3.metric("Total in Dataset", f"{total_missing_in_dataset:,}")

            if pending_missing_in_queue > 0:
                if st.button(
                    f"Auto-Exclude All {pending_missing_in_queue:,} Studies with No Abstract",
                    icon=":material/auto_delete:",
                    type="primary",
                    key="btn_auto_exclude_missing_abstracts_tab2",
                    help="Excludes all candidate studies lacking abstracts before Phase 2 screening (placed alongside Duplicates in flowchart)."
                ):
                    count_ex, _ = execute_auto_exclude_missing_abstracts(raw_df, prisma_state)
                    st.toast(f"Successfully auto-excluded {count_ex} studies without abstracts before screening!", icon=":material/auto_delete:")
                    st.rerun()
            elif already_excluded_noabs > 0:
                c_info, c_undo = st.columns([2.8, 1.2])
                with c_info:
                    st.success(f"{already_excluded_noabs:,} studies without abstracts are excluded before screening (recorded in pre-screening audit block).", icon=":material/check_circle:")
                with c_undo:
                    if st.button("Restore to Queue", icon=":material/undo:", key="btn_restore_missing_abstracts"):
                        cnt_rest = execute_restore_missing_abstracts(raw_df, prisma_state)
                        st.toast(f"Restored {cnt_rest} studies back to the screening queue!", icon=":material/undo:")
                        st.rerun()
            else:
                st.info("No studies with missing abstracts detected in this dataset.", icon=":material/check_circle:")


def _render_advanced_screening_tab(raw_df, prisma_state):
    # Ensure queue is fully synchronized with un-evaluated studies
    reconcile_screening_queue(prisma_state, raw_df)

    st.markdown("### <i class='bi bi-person-check-fill' style='color:#697aa2;'></i> Phase 2: Protocol-Guided Screening & Evaluation (Exclusion Criteria)", unsafe_allow_html=True)
    st.write("Screen the unique candidate studies (post-Phase 1 & post-deduplication) against your Exclusion Criteria. Every evaluation immediately updates the PRISMA flowchart, even while screening is still in progress.")

    loaded_files = st.session_state.get('loaded_files', [])
    if not loaded_files and 'Source File' in raw_df.columns:
        loaded_files = [f for f in raw_df['Source File'].dropna().unique()]
    file_manifest = st.session_state.get('file_manifest', {})
    prisma_dups = st.session_state.get('prisma_duplicates', [])
    _, total_raw_up, total_dups_up, _ = get_raw_retrieved_audit_stats(loaded_files, file_manifest, raw_df, prisma_dups)

    total_records = len(raw_df)
    total_excluded = len(prisma_state['exclusions'])
    total_included = len(prisma_state['screened_ok'])
    pending = total_records - total_excluded - total_included

    surviving_cnt = max(0, total_records - total_excluded)
    _render_html(f"""
    <div style="background-color:#F8FAFC; border-left:4px solid #0284C7; padding:10px 14px; border-radius:6px; font-size:13px; color:#0F172A; margin-bottom:14px;">
        <i class="bi bi-arrow-right-circle-fill" style="color:#0284C7;"></i> <strong>Pipeline Continuity (Post-Phase 1 &rarr; Phase 2):</strong>
        <strong>{total_raw_up:,}</strong> retrieved candidate records &nbsp;|&nbsp;
        <span style="color:#DC2626;"><strong>- {total_dups_up:,}</strong> duplicates removed</span> &nbsp;|&nbsp;
        <span style="color:#0369A1;"><strong>{total_records:,}</strong> unique studies in Phase 2 pool</span> &nbsp;|&nbsp;
        <span style="color:#166534;"><strong>{surviving_cnt:,}</strong> currently surviving ({total_included:,} verified included, {pending:,} pending evaluation)</span>
    </div>
    """)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Retrieved Candidate Pool", f"{total_records:,}")
    m2.metric("Pending Screening", f"{pending:,}")
    m3.metric("Verified Included", f"{total_included:,}")
    m4.metric("Excluded So Far", f"{total_excluded:,}")

    # Active IC Checklist Quick-Reference
    ics = prisma_state.get('inclusion_criteria', [])
    if ics:
        with st.expander("Review Protocol Checklist: Active Inclusion Criteria (IC)", expanded=False, icon=":material/checklist:"):
            for ic in ics:
                st.markdown(f"- **{ic['id']} ({ic['title']}):** {ic['desc']}")

    st.divider()

    # Check for missing abstracts in current screening queue
    pending_missing_in_queue = [idx for idx in prisma_state.get('screening_queue', []) if idx in raw_df.index and is_missing_abstract(raw_df.loc[idx])]
    if pending_missing_in_queue:
        with st.container(border=True):
            c_auto_info, c_auto_btn = st.columns([3, 1.2])
            with c_auto_info:
                st.markdown("<i class='bi bi-funnel-fill' style='color:#0284c7;'></i> **Pre-Screening Filter: Missing Abstracts Detected**", unsafe_allow_html=True)
                st.caption(f"Found **{len(pending_missing_in_queue):,}** candidate studies in your screening queue without an abstract. You can exclude them before Phase 2 screening (placed alongside Duplicates in the pre-screening audit block).")
            with c_auto_btn:
                if st.button(
                    f"Exclude All ({len(pending_missing_in_queue):,})",
                    icon=":material/auto_delete:",
                    type="primary",
                    key="adv_btn_auto_missing_abstract",
                    width="stretch"
                ):
                    count_ex, _ = execute_auto_exclude_missing_abstracts(raw_df, prisma_state)
                    st.toast(f"Excluded {count_ex} studies without abstracts before screening!", icon=":material/auto_delete:")
                    st.rerun()
        st.divider()

    if len(prisma_state['screening_queue']) > 0:
        current_idx = prisma_state['screening_queue'][0]
        current_article = raw_df.loc[current_idx]

        title = current_article.get('Title', 'No Title')
        abstract = current_article.get('Abstract', 'No Abstract')
        authors = current_article.get('Author', 'Unknown Authors')
        year = clean_year_value(current_article.get('Publication Year', '')) or 'Unknown Year'
        keywords = current_article.get('Keywords', 'None')
        journal = current_article.get('Journal', current_article.get('Publisher', 'Unknown Venue'))
        doc_type = current_article.get('Document Type', 'Unknown')
        source_file = current_article.get('Source File', 'Unknown File')
        
        # Source Database Provenance
        source_db = prisma_state['file_db_mapping'].get(source_file, current_article.get('Source Database', 'Unknown Database'))

        curr_missing = is_missing_abstract(current_article)
        missing_badge = '<span style="background:#FEE2E2; color:#991B1B; font-size:12px; font-weight:600; padding:3px 8px; border-radius:4px; white-space:nowrap;"><i class="bi bi-exclamation-triangle-fill"></i> No Abstract</span>' if curr_missing else ''

        st.markdown('#### <i class="bi bi-search"></i> Next Candidate Study to Screen', unsafe_allow_html=True)
        import html as _html
        safe_title = _html.escape(str(title))
        safe_authors = _html.escape(str(authors))
        safe_year = _html.escape(str(year))
        safe_journal = _html.escape(str(journal))
        safe_doc_type = _html.escape(str(doc_type))
        safe_keywords = _html.escape(str(keywords))
        safe_source_db = _html.escape(str(source_db))
        safe_source_file = _html.escape(str(source_file))

        card_html = (
            f"<div style='background-color: #f8fafc; border-left: 5px solid #697aa2; padding: 18px; border-radius: 6px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.04);'>"
            f"<div style='display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 6px;'>"
            f"<h4 style='margin: 0; color: #1E293B; font-size: 18px; font-weight: 600; line-height: 1.4;'>{safe_title}</h4>"
            f"<div style='display:flex; gap:6px;'>"
            f"{missing_badge}"
            f"<span style='background:#E0F2FE; color:#0369A1; font-size:12px; font-weight:600; padding:3px 8px; border-radius:4px; white-space:nowrap;'><i class='bi bi-database'></i> {safe_source_db}</span>"
            f"<span style='background:#F1F5F9; color:#475569; font-size:12px; padding:3px 8px; border-radius:4px; white-space:nowrap;'><i class='bi bi-file-earmark-text'></i> {safe_source_file}</span>"
            f"</div></div>"
            f"<div style='color: #64748b; font-size: 13.5px; margin-top: 8px; line-height: 1.6;'>"
            f"<i class='bi bi-people-fill' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Authors:</span> {safe_authors} <br>"
            f"<i class='bi bi-calendar3' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Year:</span> {safe_year} &nbsp;|&nbsp; "
            f"<i class='bi bi-journal-text' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Venue:</span> {safe_journal} &nbsp;|&nbsp; "
            f"<i class='bi bi-file-earmark-text' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Type:</span> {safe_doc_type} <br>"
            f"<i class='bi bi-tags-fill' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Keywords:</span> {safe_keywords}"
            f"</div></div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)

        with st.expander("Show Abstract", expanded=True):
            if is_missing_abstract(abstract):
                st.markdown("<span style='color:#DC2626; font-style:italic;'><i class='bi bi-exclamation-circle'></i> No abstract text available for this publication in the dataset.</span>", unsafe_allow_html=True)
            else:
                st.write(abstract)

        st.markdown("##### <i class='bi bi-lightning-charge-fill' style='color: #F59E0B;'></i> Screening Evaluation", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 1.8, 1])
        
        with col1:
            if st.button("Include (Keep)", icon=":material/check_circle:", type="primary", width="stretch", key="adv_btn_include"):
                prisma_state['screened_ok'].append(current_idx)
                prisma_state['screening_queue'].pop(0)
                prisma_state['db_final_overrides'] = {}
                for k in list(st.session_state.keys()):
                    if k.startswith("ov_final_"):
                        del st.session_state[k]
                auto_save_prisma_state(prisma_state)
                st.rerun()

        with col2:
            ecs = prisma_state.get('exclusion_criteria', DEFAULT_EXCLUSION_CRITERIA)
            ec_options = [f"{ec['id']}: {ec['title']} - {ec['desc']}" for ec in ecs]
            if not ec_options:
                ec_options = ["EC 1: Excluded study"]

            selected_ec_str = st.selectbox("Select Applicable Exclusion Criterion:", ec_options, label_visibility="collapsed")
            
            # Select stage
            c_stage, c_btn = st.columns([1.2, 1])
            with c_stage:
                screen_stage = st.selectbox("Stage", ["Title & Abstract", "Full-Text"], label_visibility="collapsed", key="stage_sel")
            with c_btn:
                if st.button("Exclude (Reject)", icon=":material/cancel:", width="stretch", key="adv_btn_exclude"):
                    ec_code = selected_ec_str.split(':')[0].strip()
                    ec_title = selected_ec_str.split(':')[1].split(' - ')[0].strip() if ':' in selected_ec_str else selected_ec_str
                    
                    prisma_state['exclusions'][current_idx] = {
                        'code': ec_code,
                        'reason': ec_title,
                        'full_text': selected_ec_str,
                        'stage': 'Title_Abstract' if screen_stage == "Title & Abstract" else 'Full_Text'
                    }
                    prisma_state['screening_queue'].pop(0)
                    # Clear any manual override for this EC so live screening results immediately update the diagram
                    if 'ec_overrides' in prisma_state and ec_code in prisma_state['ec_overrides']:
                        del prisma_state['ec_overrides'][ec_code]
                    st.session_state.pop(f"ov_ec_{ec_code}", None)
                    prisma_state['db_final_overrides'] = {}
                    for k in list(st.session_state.keys()):
                        if k.startswith("ov_final_"):
                            del st.session_state[k]
                    auto_save_prisma_state(prisma_state)
                    st.rerun()

        with col3:
            if st.button("Skip for now", icon=":material/skip_next:", width="stretch", key="adv_btn_skip"):
                idx = prisma_state['screening_queue'].pop(0)
                prisma_state['screening_queue'].append(idx)
                auto_save_prisma_state(prisma_state)
                st.rerun()

    else:
        st.success("All candidate studies have been evaluated!", icon=":material/task_alt:")

    # Live Exclusion Breakdown Tally
    if prisma_state['exclusions']:
        st.divider()
        st.markdown("#### <i class='bi bi-pie-chart-fill' style='color:#697aa2;'></i> Exclusion Breakdown by Criterion", unsafe_allow_html=True)
        
        ec_counts = {}
        for ex in prisma_state['exclusions'].values():
            if isinstance(ex, dict):
                key = f"{ex.get('code', 'EC')}: {ex.get('reason', 'Excluded')} ({ex.get('stage', 'General')})"
            else:
                key = str(ex)
            ec_counts[key] = ec_counts.get(key, 0) + 1
        
        breakdown_cols = st.columns(min(len(ec_counts), 4))
        for idx, (ec_lbl, cnt) in enumerate(ec_counts.items()):
            col_target = breakdown_cols[idx % len(breakdown_cols)]
            col_target.metric(ec_lbl, f"{cnt} studies")

    st.divider()
    st.markdown("#### <i class='bi bi-floppy-fill' style='color:#697aa2;'></i> Commit Clean Dataset to Workspace", unsafe_allow_html=True)
    st.caption("Synchronizes downstream modules (Thematic Stratification, Network Topology, Dashboard) with the curated, included studies.")
    
    if st.button("Commit Final Included Dataset to Workspace", type="primary", icon=":material/save:"):
        st.session_state.master_df = raw_df.drop(index=list(prisma_state['exclusions'].keys())).reset_index(drop=True)
        auto_save_prisma_state(prisma_state)
        from utils.project_manager import save_master_dataset
        save_master_dataset(st.session_state.master_df)
        st.success(f"Successfully committed {len(st.session_state.master_df)} articles to the main workspace!")
        st.rerun()


def compute_balanced_database_survival(db_progressions, total_screen_in, total_excluded, tracked_ex_by_db=None, manual_finals=None):
    """
    Computes final included studies per digital library ensuring mathematical integrity:
    1. sum(Final Included per DB) == total_final == (total_screen_in - total_excluded).
    2. Final Included for each DB does not exceed that DB's uploaded intake or post-deduplication screening intake.
    3. Respects manual overrides if they balance to total_final, else allocates proportionally.
    """
    total_final = max(0, total_screen_in - total_excluded)
    db_names = list(db_progressions.keys())
    
    if not db_names:
        return {}

    # If manual overrides exist and sum to total_final, respect them!
    if manual_finals and len(manual_finals) == len(db_names):
        if sum(manual_finals.get(db, 0) for db in db_names) == total_final:
            return {db: int(manual_finals[db]) for db in db_names}

    raw_intakes = {
        db: db_progressions[db].get('uploaded', db_progressions[db]['ics'][-1][1] if db_progressions[db].get('ics') else db_progressions[db].get('initial', 0))
        for db in db_names
    }
    total_raw = sum(raw_intakes.values())

    # Step 1: Allocate total_screen_in across databases (accounting for pre-screening duplicates & missing abstracts)
    if total_screen_in <= 0:
        screen_intakes = {db: 0 for db in db_names}
    elif total_screen_in >= total_raw or total_raw == 0:
        screen_intakes = {db: raw_intakes[db] for db in db_names}
    else:
        # Proportionally reduce raw_intakes to total_screen_in using largest-remainder integer allocation
        screen_intakes = {}
        allocated = 0
        remainders = []
        for db in db_names:
            exact = total_screen_in * (raw_intakes[db] / total_raw)
            base = min(raw_intakes[db], int(exact))
            screen_intakes[db] = base
            allocated += base
            remainders.append((exact - base, raw_intakes[db] - base, db))
        diff = total_screen_in - allocated
        remainders.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for rem, room, db in remainders:
            if diff <= 0:
                break
            if room > 0:
                add = min(diff, room)
                screen_intakes[db] += add
                diff -= add
        if diff > 0:
            for db in db_names:
                room = raw_intakes[db] - screen_intakes[db]
                if room > 0:
                    add = min(diff, room)
                    screen_intakes[db] += add
                    diff -= add
                if diff <= 0:
                    break

    # Step 2: Allocate Phase 2 exclusions from screen_intakes to reach total_final
    if total_final <= 0:
        return {db: 0 for db in db_names}
    if total_excluded == 0:
        return screen_intakes

    if tracked_ex_by_db is None:
        tracked_ex_by_db = {db: 0 for db in db_names}

    total_tracked = sum(tracked_ex_by_db.get(db, 0) for db in db_names)
    weights = {}
    for db in db_names:
        if total_tracked > 0:
            weights[db] = tracked_ex_by_db.get(db, 0) / total_tracked
        elif total_screen_in > 0:
            weights[db] = screen_intakes[db] / total_screen_in
        else:
            weights[db] = 1.0 / len(db_names)

    ex_allocated = {}
    allocated_sum = 0
    for db in db_names[:-1]:
        e = min(screen_intakes[db], round(total_excluded * weights[db]))
        ex_allocated[db] = e
        allocated_sum += e
    last_db = db_names[-1]
    rem_ex = total_excluded - allocated_sum
    rem_ex = max(0, min(screen_intakes[last_db], rem_ex))
    ex_allocated[last_db] = rem_ex

    finals = {db: max(0, screen_intakes[db] - ex_allocated[db]) for db in db_names}
    diff = total_final - sum(finals.values())
    if diff != 0:
        for db in db_names:
            if diff > 0 and finals[db] < screen_intakes[db]:
                add = min(diff, screen_intakes[db] - finals[db])
                finals[db] += add
                diff -= add
            elif diff < 0 and finals[db] > 0:
                sub = min(abs(diff), finals[db])
                finals[db] -= sub
                diff += sub
            if diff == 0:
                break
    return finals


def _build_horizontal_slr_diagram(
    db_progressions,   # dict: { 'Scopus': { 'initial': 0, 'ics': [('IC 1', 0, '...')], 'uploaded': 483, 'final': 473 }, ... }
    ec_data,           # list of dicts: [ { 'id': 'EC 1', 'title': 'Out of Scope', 'count': 4, 'remaining': 7 }, ... ]
    total_duplicates=0,
    total_missing_abstracts=0,
    search_exec_title="PHASE 1: SEARCH EXECUTION (MANUAL)",
    search_exec_subtitle="Using Inclusion Criteria",
    selection_title="PHASE 2: SELECTION OF PUBLICATIONS",
    selection_subtitle="Using Exclusion Criteria"
):
    """
    Constructs an auditable Graphviz DOT diagram matching Kitchenham (2007) and Petersen (2008/2015) guidelines:
    Phase 1 (Manual): Database (Initial Hits) -> IC 1 -> IC 2 -> IC 3
    Post-Phase 1 Upload & Deduplication: Uploaded to Tool (Post-IC) -> Deduplication (- N) & Missing Abstracts (- M) -> Candidate Screening Pool
    Phase 2 (In-Tool Screening): Candidate Screening Pool -> EC 1 -> EC 2 -> EC 3 (strictly in sequential order, live results) -> Final Included
    Phase 3: Final Included -> Breakdown by Digital Library
    Sized for academic publication.
    """
    total_raw_hits = sum(d.get('initial', 0) for d in db_progressions.values())
    total_post_ic = sum(d['ics'][-1][1] if d.get('ics') else d.get('initial', 0) for d in db_progressions.values())
    total_uploaded = sum(
        d.get('uploaded', d['ics'][-1][1] if d.get('ics') else d.get('initial', 0))
        for d in db_progressions.values()
    )
    total_screen_in = max(0, total_uploaded - total_duplicates - total_missing_abstracts)
    total_excluded = sum(ec.get('count', 0) for ec in ec_data)
    total_final = max(0, total_screen_in - total_excluded)

    # Reconcile database final numbers so sum(finals) == total_final strictly
    finals_sum = sum(d.get('final', 0) for d in db_progressions.values())
    if finals_sum != total_final and total_final >= 0:
        balanced_finals = compute_balanced_database_survival(
            db_progressions, total_screen_in, total_excluded
        )
        for db_name, b_cnt in balanced_finals.items():
            if db_name in db_progressions:
                db_progressions[db_name]['final'] = b_cnt

    safe_search_title = _clean_html_label(search_exec_title)
    safe_search_sub = _clean_html_label(search_exec_subtitle)
    safe_sel_title = _clean_html_label(selection_title)
    safe_sel_sub = _clean_html_label(selection_subtitle)

    p1_parts = [
        f"Initial Hits (Manual): {total_raw_hits:,}",
        f"Post-IC (Manual): {total_post_ic:,}",
        f"Retrieved Studies: {total_uploaded:,}"
    ]
    p1_sub_html = f'<br/><font point-size="9" color="#0369A1"><b>{" &nbsp;|&nbsp; ".join(p1_parts)}</b></font>'

    dot = [
        "digraph Auditable_SLR_Pipeline {",
        "    rankdir=LR;",
        '    size="9.4,4.6!";',
        '    ratio="compress";',
        '    margin="0.06,0.06";',
        "    nodesep=0.18;",
        "    ranksep=0.25;",
        '    fontname="Segoe UI, Helvetica, Arial, sans-serif";',
        '    node [fontname="Segoe UI, Helvetica, Arial, sans-serif", fontsize=9, height=0.32, margin="0.10,0.05"];',
        '    edge [fontname="Segoe UI, Helvetica, Arial, sans-serif", fontsize=8, color="#0F172A", penwidth=1.1, arrowsize=0.65];',
        "",
        "    # ========================================================",
        "    # PHASE 1: SEARCH EXECUTION & INCLUSION CRITERIA FUNNEL",
        "    # ========================================================",
        "    subgraph cluster_search {",
        f'        label = <<b>{safe_search_title}</b><br/><font point-size="9">({safe_search_sub})</font><br/>{p1_sub_html}>;',
        '        labeljust = "c";',
        "        fontsize = 11;",
        '        fontcolor = "#0369A1";',
        '        color = "#0284C7";',
        '        style = "solid";',
        "        penwidth = 1.2;",
        "        margin = 10;",
        ""
    ]

    # Find unique IC steps across databases for header titles
    max_ic_steps = 0
    ic_headers = []
    for pdata in db_progressions.values():
        ics = pdata.get('ics', [])
        if len(ics) > max_ic_steps:
            max_ic_steps = len(ics)
            ic_headers = [(code, title) for code, _, title in ics]

    # Add IC Header Title Nodes (outside at top of each IC column)
    header_nodes = []
    for step_idx, (ic_code, ic_title) in enumerate(ic_headers):
        h_id = f"header_ic_{step_idx}"
        header_nodes.append(h_id)
        safe_h_code = _clean_html_label(ic_code)
        raw_title = ic_title
        if len(raw_title) > 24:
            raw_title = raw_title[:22] + "..."
        safe_h_title = _clean_html_label(raw_title)
        dot.append(f'        {h_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>{safe_h_code}</b></td></tr><tr><td align="center"><font point-size="8" color="#0369A1"><b>{safe_h_title}&emsp;&emsp;</b></font></td></tr></table>>, shape=box, style="filled,rounded", fillcolor="#F0F9FF", color="#0284C7", penwidth=1.2, fontsize=9, margin="0.15,0.05"];')

    if len(header_nodes) > 1:
        dot.append("        " + " -> ".join(header_nodes) + " [style=invis, weight=5];")

    db_exit_nodes = []
    step_db_nodes = {s: [] for s in range(max_ic_steps)}
    db_init_nodes = []

    for i, (db_name, pdata) in enumerate(db_progressions.items()):
        safe_name = _clean_html_label(db_name)
        init_cnt = pdata.get('initial', 0)
        ics = pdata.get('ics', [])
        
        in_node_id = f"db_init_{i}"
        db_init_nodes.append(in_node_id)
        dot.append(f'        {in_node_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{safe_name}</td></tr><tr><td align="center"><b>{init_cnt:,} hits</b></td></tr></table>>, shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0F172A", penwidth=1.3, fontsize=9, margin="0.12,0.06"];')
        
        if ics:
            prev_node = in_node_id
            for step_idx, (ic_code, ic_cnt, _) in enumerate(ics):
                ic_node_id = f"db_{i}_ic_{step_idx}"
                step_db_nodes[step_idx].append(ic_node_id)
                safe_code = _clean_html_label(ic_code)
                dot.append(f'        {ic_node_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{safe_code}: <b>{ic_cnt:,}</b></td></tr></table>>, shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#0284C7", penwidth=1.1, fontsize=9, margin="0.10,0.05"];')
                dot.append(f'        {prev_node} -> {ic_node_id} [color="#0284C7", penwidth=1.1];')
                prev_node = ic_node_id
            db_exit_nodes.append(prev_node)
        else:
            cnt_node = f"db_cnt_{i}"
            dot.append(f'        {cnt_node} [label="{init_cnt:,}", shape=box, style="solid", color="#0F172A", penwidth=1.1, fillcolor="#FFFFFF", fontsize=9, width=0.5, height=0.3];')
            dot.append(f"        {in_node_id} -> {cnt_node};")
            db_exit_nodes.append(cnt_node)

    for step_idx, h_id in enumerate(header_nodes):
        nodes_in_col = [h_id] + step_db_nodes[step_idx]
        dot.append("        {rank=same; " + "; ".join(nodes_in_col) + ";}")
        if step_db_nodes[step_idx]:
            dot.append(f'        {h_id} -> {step_db_nodes[step_idx][0]} [style=invis, weight=10];')

    if db_init_nodes:
        dot.append("        {rank=same; " + "; ".join(db_init_nodes) + ";}")

    dot.append("    }")
    dot.append("")

    # ========================================================
    # POST-PHASE 1 INTAKE, DEDUPLICATION & SCREENING POOL
    # (Omit duplicate bubble if zero; professional academic terms)
    # ========================================================
    pre_screen_ex = (total_duplicates > 0) or (total_missing_abstracts > 0)
    if pre_screen_ex:
        dot.append(f'    total_retrieved_pool [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>{total_uploaded:,}</b></td></tr><tr><td align="center"><font point-size="7" color="#0F172A"><b>RETRIEVED STUDIES</b></font></td></tr><tr><td align="center"><font point-size="7" color="#64748B">(Identification Intake)</font></td></tr></table>>, shape=box, style="rounded,filled,bold", color="#0F172A", penwidth=1.4, fillcolor="#F8FAFC", fontsize=9, width=1.0, height=0.42];')
        for exit_node in db_exit_nodes:
            dot.append(f"    {exit_node} -> total_retrieved_pool;")

        pre_tags = []
        if total_duplicates > 0:
            dot.append(f'    dedup_tag [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>- {total_duplicates:,}</b></td></tr><tr><td align="center"><font point-size="7" color="#DC2626"><b>DUPLICATES</b></font></td></tr></table>>, shape=box, style="filled", color="#DC2626", penwidth=1.0, fillcolor="#FEF2F2", fontsize=8, width=0.75, height=0.32];')
            dot.append('    total_retrieved_pool -> dedup_tag [color="#DC2626", penwidth=1.0, style=dashed];')
            pre_tags.append("dedup_tag")

        if total_missing_abstracts > 0:
            dot.append(f'    noabs_tag [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>- {total_missing_abstracts:,}</b></td></tr><tr><td align="center"><font point-size="7" color="#DC2626"><b>NO ABSTRACT</b></font></td></tr></table>>, shape=box, style="filled", color="#DC2626", penwidth=1.0, fillcolor="#FEF2F2", fontsize=8, width=0.75, height=0.32];')
            dot.append('    total_retrieved_pool -> noabs_tag [color="#DC2626", penwidth=1.0, style=dashed];')
            pre_tags.append("noabs_tag")

        dot.append(f'    total_screen_pool [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>{total_screen_in:,}</b></td></tr><tr><td align="center"><font point-size="7" color="#0369A1"><b>ENTERED SCREENING</b></font></td></tr><tr><td align="center"><font point-size="7" color="#0284C7">(Unique Candidate Pool)</font></td></tr></table>>, shape=box, style="rounded,filled,bold", color="#0369A1", penwidth=1.6, fillcolor="#E0F2FE", fontsize=10, width=1.0, height=0.42];')
        dot.append('    total_retrieved_pool -> total_screen_pool [color="#0284C7", penwidth=1.5];')

        if len(pre_tags) > 1:
            dot.append("    {rank=same; " + "; ".join(pre_tags) + ";}")
            dot.append(f"    {pre_tags[0]} -> {pre_tags[1]} [style=invis];")
        elif len(pre_tags) == 1:
            dot.append(f"    {{rank=same; total_retrieved_pool; {pre_tags[0]};}}")
    else:
        # When duplicates and missing abstracts are zero, show single candidate screening intake pool
        dot.append(f'    total_screen_pool [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>{total_screen_in:,}</b></td></tr><tr><td align="center"><font point-size="7" color="#0369A1"><b>STUDIES</b></font></td></tr></table>>, shape=box, style="rounded,filled,bold", color="#0369A1", penwidth=1.6, fillcolor="#E0F2FE", fontsize=10, width=1.0, height=0.42];')
        for exit_node in db_exit_nodes:
            dot.append(f"    {exit_node} -> total_screen_pool;")
    dot.append("")

    # ========================================================
    # PHASE 2: SELECTION OF PUBLICATIONS (EXCLUSION CRITERIA)
    # Sequential in-order flow from left to right
    # (Omit exclusion bubble when count is zero)
    # ========================================================
    dot.append("    subgraph cluster_selection {")
    dot.append(f'        label = <<b>{safe_sel_title}</b><br/><font point-size="9">({safe_sel_sub})</font><br/><br/><font point-size="9" color="#DC2626"><b>Total Excluded: {total_excluded:,}</b></font> &nbsp;&emsp;&emsp;|&nbsp; <font point-size="9" color="#166534"><b>Current / Final Yield: {total_final:,}</b></font>>;')
    dot.append('        labeljust = "c";')
    dot.append("        fontsize = 11;")
    dot.append('        fontcolor = "#0369A1";')
    dot.append('        color = "#0369A1";')
    dot.append('        style = "dashed";')
    dot.append("        penwidth = 1.2;")
    dot.append("        margin = 10;")
    dot.append("")

    ec_box_ids = []
    
    for j, ec in enumerate(ec_data):
        ec_id = f"ec_box_{j}"
        ec_cnt_id = f"ec_cnt_{j}"
        ec_box_ids.append(ec_id)
        
        safe_ec_code = _clean_html_label(ec.get('id', f'EC {j+1}'))
        raw_ec_title = ec.get('title', 'Excluded')
        if len(raw_ec_title) > 22:
            raw_ec_title = raw_ec_title[:20] + "..."
        safe_title = _clean_html_label(raw_ec_title)
        ex_count = ec.get('count', 0)
        rem_count = ec.get('remaining', None)
        
        rem_row = f'<tr><td align="center"><font point-size="8" color="#166534">Passed: {rem_count:,}</font></td></tr>' if rem_count is not None else ""

        dot.append(f'        {ec_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{safe_ec_code}:</td></tr><tr><td align="center"><b>{safe_title}&emsp;</b></td></tr>{rem_row}</table>>, shape=box, style="rounded,filled", fillcolor="#E0F2FE", color="#0284C7", penwidth=1.3, fontsize=9, margin="0.10,0.06"];')
        
        # Only render the exclusion bubble when count is greater than zero
        if ex_count > 0:
            dot.append(f'        {ec_cnt_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>- {ex_count:,}</b></td></tr><tr><td align="center"><font point-size="7" color="#DC2626"><b>EXCLUDED</b></font></td></tr></table>>, shape=box, style="filled", color="#DC2626", penwidth=1.0, fillcolor="#FEF2F2", fontsize=8, width=0.7, height=0.3];')
            dot.append(f'        {ec_id} -> {ec_cnt_id} [color="#DC2626", penwidth=1.0, style=dashed];')
            dot.append(f'        {{rank=same; {ec_id}; {ec_cnt_id};}}')

    if ec_box_ids:
        # Sequential progression strictly in order across the EC funnel
        for j in range(len(ec_box_ids) - 1):
            dot.append(f'        {ec_box_ids[j]} -> {ec_box_ids[j+1]} [color="#0284C7", penwidth=1.2];')

    dot.append("    }")
    dot.append("")

    # Connect pool into Phase 2 first EC strictly in order
    if ec_box_ids:
        dot.append(f"    total_screen_pool -> {ec_box_ids[0]} [color=\"#0284C7\", penwidth=1.4];")
        last_phase2_exit = ec_box_ids[-1]
    else:
        last_phase2_exit = "total_screen_pool"

    # Final Selected Total
    dot.append(f'    final_selected [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center"><b>{total_final:,}</b></td></tr><tr><td align="center"><font point-size="8" color="#166534"><b>FINAL INCLUDED</b></font></td></tr></table>>, shape=box, style="rounded,filled,bold", color="#16A34A", penwidth=1.8, fillcolor="#DCFCE7", fontsize=10, width=0.9, height=0.4];')
    dot.append(f"    {last_phase2_exit} -> final_selected [penwidth=1.5, color=\"#16A34A\"];")
    dot.append("")

    # Right pills: Database Final Breakdown (only render if more than 1 digital library)
    if len(db_progressions) > 1:
        right_pill_ids = []
        for k, (db_name, pdata) in enumerate(db_progressions.items()):
            safe_name = _clean_html_label(db_name)
            final_cnt = pdata.get('final', 0)
            out_id = f"db_out_{k}"
            right_pill_ids.append(out_id)
            dot.append(f'    {out_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{safe_name}:</td></tr><tr><td align="center"><b>{final_cnt:,} included</b></td></tr></table>>, shape=box, style="rounded,filled", fillcolor="#FFFFFF", color="#16A34A", penwidth=1.2, fontsize=9, margin="0.10,0.05"];')
            dot.append(f"    final_selected -> {out_id} [color=\"#16A34A\", penwidth=1.0];")

        if right_pill_ids:
            dot.append("    {rank=same; " + "; ".join(right_pill_ids) + ";}")
    dot.append("}")
    return "\n".join(dot)


def _build_vertical_slr_diagram(
    db_progressions: dict,
    ec_data: list,
    user_ics: list,
    total_duplicates: int = 0,
    total_missing_abstracts: int = 0
) -> str:
    """
    Constructs a vertical PRISMA/SLR audit diagram with distinct separate nodes for every IC,
    explicit Post-Phase 1 Upload & Deduplication nodes, and every EC.
    Sized for academic publication (<= 50% of an A4 page).
    """
    total_raw_hits = sum(d.get('initial', 0) for d in db_progressions.values())
    total_uploaded = sum(
        d.get('uploaded', d['ics'][-1][1] if d.get('ics') else d.get('initial', 0))
        for d in db_progressions.values()
    )
    total_screen_in = max(0, total_uploaded - total_duplicates - total_missing_abstracts)
    total_excluded = sum(ec.get('count', 0) for ec in ec_data)
    total_final = max(0, total_screen_in - total_excluded)

    # Reconcile database final numbers so sum(finals) == total_final strictly
    finals_sum = sum(d.get('final', 0) for d in db_progressions.values())
    if finals_sum != total_final and total_final >= 0:
        balanced_finals = compute_balanced_database_survival(
            db_progressions, total_screen_in, total_excluded
        )
        for db_name, b_cnt in balanced_finals.items():
            if db_name in db_progressions:
                db_progressions[db_name]['final'] = b_cnt

    dot = [
        "digraph Vertical_Auditable_PRISMA {",
        "    rankdir=TB;",
        '    size="6.8,5.0!";',
        '    ratio="compress";',
        '    margin="0.06,0.06";',
        "    nodesep=0.18;",
        "    ranksep=0.22;",
        '    node [shape=rect, style="rounded,filled", fontname="Segoe UI, Helvetica, Arial, sans-serif", fontsize=9, color="#94A3B8", fontcolor="#1E293B", margin="0.12,0.06"];',
        '    edge [fontname="Segoe UI, Helvetica, Arial, sans-serif", fontsize=8, color="#64748B", penwidth=1.1, arrowsize=0.65];',
        "",
        "    # --- 1. DIGITAL LIBRARIES IDENTIFICATION ROW (MANUAL PHASE 1) ---"
    ]

    db_nodes = []
    for i, (db_name, pdata) in enumerate(db_progressions.items()):
        safe_name = _clean_html_label(db_name)
        hits = pdata.get('initial', 0)
        db_id = f"DB_{i}"
        db_nodes.append(db_id)
        dot.append(f'    {db_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{safe_name}</td></tr><tr><td align="center"><b>{hits:,} hits (Manual)</b></td></tr></table>>, fillcolor="#F8FAFC", color="#94A3B8"];')

    if db_nodes:
        dot.append("    {rank=same; " + " ".join(db_nodes) + "}")
    dot.append(f'    TotalID [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Phase 1: Total Initial Records Identified (Manual)</td></tr><tr><td align="center"><b>n = {total_raw_hits:,}</b></td></tr></table>>, fillcolor="#F1F5F9", color="#64748B", style="rounded,filled,bold"];')
    for db_id in db_nodes:
        dot.append(f"    {db_id} -> TotalID;")

    dot.append("")
    dot.append("    # --- 2. SEPARATE INCLUSION CRITERIA (IC) SEQUENTIAL NODES (MANUAL) ---")
    prev_ic = "TotalID"
    for idx_ic, ic in enumerate(user_ics):
        ic_code = _clean_html_label(ic.get('id', f'IC {idx_ic + 1}'))
        ic_title = _clean_html_label(ic.get('title', 'Criteria'))
        ic_node = f"IC_node_{idx_ic}"
        
        # Calculate survival count across all DBs for this IC step
        surv_cnt = 0
        for pdata in db_progressions.values():
            if pdata.get('ics') and idx_ic < len(pdata['ics']):
                surv_cnt += pdata['ics'][idx_ic][1]
            else:
                surv_cnt += pdata.get('initial', 0)

        dot.append(f'    {ic_node} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{ic_code}: <b>{ic_title}</b></td></tr><tr><td align="center"><font color="#0284C7">Surviving Records (Manual): n = {surv_cnt:,}</font></td></tr></table>>, fillcolor="#E0F2FE", color="#0284C7", penwidth=1.3];')
        dot.append(f"    {prev_ic} -> {ic_node};")
        prev_ic = ic_node

    # --- 3. RETRIEVED STUDIES, DEDUPLICATION & SCREENING INTAKE POOL ---
    pre_screen_ex = (total_duplicates > 0) or (total_missing_abstracts > 0)
    if pre_screen_ex:
        dot.append(f'    RetrievedPool [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Retrieved Candidate Studies (Phase 1 Intake)</td></tr><tr><td align="center"><b>n = {total_uploaded:,}</b></td></tr></table>>, fillcolor="#F8FAFC", color="#0F172A", style="rounded,filled,bold", penwidth=1.4];')
        dot.append(f"    {prev_ic} -> RetrievedPool [penwidth=1.3];")

        rank_nodes = ["RetrievedPool"]
        if total_duplicates > 0:
            dot.append(f'    Dups [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Deduplication:</td></tr><tr><td align="center"><font color="#DC2626"><b>Duplicates Removed: - {total_duplicates:,}</b></font></td></tr></table>>, fillcolor="#FEF2F2", color="#DC2626", penwidth=1.1];')
            dot.append('    RetrievedPool -> Dups [style=dashed, color="#DC2626", penwidth=1.0];')
            rank_nodes.append("Dups")

        if total_missing_abstracts > 0:
            dot.append(f'    NoAbs [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Pre-Screening Filter:</td></tr><tr><td align="center"><font color="#DC2626"><b>Missing Abstracts: - {total_missing_abstracts:,}</b></font></td></tr></table>>, fillcolor="#FEF2F2", color="#DC2626", penwidth=1.1];')
            dot.append('    RetrievedPool -> NoAbs [style=dashed, color="#DC2626", penwidth=1.0];')
            rank_nodes.append("NoAbs")

        if len(rank_nodes) > 1:
            dot.append("    {rank=same; " + " ".join(rank_nodes) + "}")

        dot.append(f'    Screen [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Candidate Studies Entering Phase 2 Screening</td></tr><tr><td align="center"><b>n = {total_screen_in:,}</b></td></tr></table>>, fillcolor="#E0F2FE", color="#0369A1", style="rounded,filled,bold", penwidth=1.6];')
        dot.append("    RetrievedPool -> Screen [penwidth=1.4, color=\"#0284C7\"];")
    else:
        # When duplicates and missing abstracts are zero, show single candidate screening intake node
        dot.append(f'    Screen [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Retrieved Candidate Studies Entering Screening</td></tr><tr><td align="center"><b>n = {total_screen_in:,}</b></td></tr></table>>, fillcolor="#E0F2FE", color="#0369A1", style="rounded,filled,bold", penwidth=1.6];')
        dot.append(f"    {prev_ic} -> Screen [penwidth=1.4, color=\"#0284C7\"];")
    dot.append("")

    dot.append("    # --- 4. SEPARATE EXCLUSION CRITERIA (EC) NODES ---")
    prev_ec = "Screen"
    for idx_ec, ec in enumerate(ec_data):
        ec_code = _clean_html_label(ec.get('id', f'EC {idx_ec + 1}'))
        ec_title = _clean_html_label(ec.get('title', 'Excluded'))
        ex_cnt = ec.get('count', 0)
        rem_cnt = ec.get('remaining', 0)
        
        ec_pass_node = f"EC_pass_{idx_ec}"
        ec_ex_node = f"EC_ex_{idx_ec}"
        
        dot.append(f'    {ec_pass_node} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{ec_code} Passed: <b>{ec_title}</b></td></tr><tr><td align="center"><font color="#166534">Retained: n = {rem_cnt:,}</font></td></tr></table>>, fillcolor="#F0FDF4", color="#16A34A", penwidth=1.2];')
        dot.append(f"    {prev_ec} -> {ec_pass_node};")
        
        # Only render the exclusion bubble when count is greater than zero
        if ex_cnt > 0:
            dot.append(f'    {ec_ex_node} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{ec_code} Excluded:</td></tr><tr><td align="center"><font color="#DC2626"><b>- {ex_cnt:,} studies</b></font></td></tr></table>>, fillcolor="#FEF2F2", color="#DC2626", penwidth=1.0];')
            dot.append(f'    {prev_ec} -> {ec_ex_node} [style=dashed, color="#DC2626"];')
            dot.append(f"    {{rank=same; {ec_pass_node} {ec_ex_node}}}")
        prev_ec = ec_pass_node

    dot.append("")
    dot.append("    # --- 5. FINAL INCLUDED STUDIES NODE ---")
    dot.append(f'    FinalIncluded [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">Final Studies Included in Systematic Literature Review</td></tr><tr><td align="center"><b>n = {total_final:,}</b></td></tr></table>>, fillcolor="#DCFCE7", color="#16A34A", fontcolor="#166534", style="rounded,filled,bold", penwidth=1.8];')
    dot.append(f"    {prev_ec} -> FinalIncluded;")
    dot.append("")

    # --- 6. FINAL BREAKDOWN BY DATABASE (Render only if > 1 source) ---
    if len(db_progressions) > 1:
        final_db_nodes = []
        for k, (db_name, pdata) in enumerate(db_progressions.items()):
            safe_name = _clean_html_label(db_name)
            fin_cnt = pdata.get('final', 0)
            out_id = f"final_db_{k}"
            final_db_nodes.append(out_id)
            dot.append(f'    {out_id} [label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0"><tr><td align="center">{safe_name}:</td></tr><tr><td align="center"><b>{fin_cnt:,} studies</b></td></tr></table>>, fillcolor="#FFFFFF", color="#16A34A", penwidth=1.3];')
            dot.append(f'    FinalIncluded -> {out_id} [color="#16A34A"];')

        if final_db_nodes:
            dot.append("    {rank=same; " + " ".join(final_db_nodes) + "}")
    dot.append("}")
    return "\n".join(dot)


def _render_advanced_flowchart_tab(raw_df, prisma_state):
    st.markdown("### <i class='bi bi-diagram-3-fill' style='color:#697aa2;'></i> SLR & PRISMA Auditable Flowchart Generator", unsafe_allow_html=True)
    st.caption("Complete methodological audit trail tracking manual Phase 1 Inclusion Criteria, Post-Phase 1 Uploaded Articles & Deduplication, and live Phase 2 Exclusion Criteria evaluation (Kitchenham, 2007; Petersen, 2008/2015).")

    # Flowchart Architecture Selector
    c_arch1, c_arch2 = st.columns([1.6, 2.4])
    with c_arch1:
        diagram_style = st.radio(
            "Flowchart Architecture Style:",
            [
                "Auditable Horizontal SLR Pipeline (By Database & Criteria Funnel)",
                "Auditable Vertical SLR Pipeline (Sequential IC & EC Nodes)"
            ],
            index=0,
            key="slr_diagram_style_radio"
        )
    with c_arch2:
        if "Horizontal" in diagram_style:
            _render_html("""
            <div style="background-color: #F0FDF4; border-left: 4px solid #16A34A; padding: 10px 14px; border-radius: 4px; font-size: 13px; color: #166534; margin-top: 15px;">
                <i class="bi bi-shield-check"></i> <strong>Auditable SLR Funnel (Horizontal):</strong> Displays manual Phase 1 Inclusion Criteria filtration per database, followed by the Phase 1 Intake &amp; Deduplication bridge, live Phase 2 Exclusion Criteria evaluation in the center, and final included studies by database on the right.
            </div>
            """)
        else:
            _render_html("""
            <div style="background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 10px 14px; border-radius: 4px; font-size: 13px; color: #0369A1; margin-top: 15px;">
                <i class="bi bi-diagram-3"></i> <strong>Auditable SLR Pipeline (Vertical):</strong> Displays each manual Inclusion Criterion (IC), the Retrieved Studies Intake &amp; Deduplication step, and each live Exclusion Criterion (EC) as separate boxes in a top-to-bottom PRISMA flow.
            </div>
            """)

    st.divider()

    loaded_files = st.session_state.get('loaded_files', [])
    if not loaded_files and 'Source File' in raw_df.columns:
        loaded_files = [f for f in raw_df['Source File'].dropna().unique()]

    file_manifest = st.session_state.get('file_manifest', {})
    prisma_dups = st.session_state.get('prisma_duplicates', [])
    file_raw_counts, total_raw_intake, total_dups_tracked, total_screen_pool_base = get_raw_retrieved_audit_stats(loaded_files, file_manifest, raw_df, prisma_dups)

    # Compute database groups
    db_groups = {}
    for fname in loaded_files:
        assigned_db = prisma_state['file_db_mapping'].get(fname, 'Unspecified Database').strip()
        if not assigned_db:
            assigned_db = 'Unspecified Database'
        if assigned_db not in db_groups:
            db_groups[assigned_db] = {'files': [], 'imported_count': 0}
        db_groups[assigned_db]['files'].append(fname)
        db_groups[assigned_db]['imported_count'] += file_raw_counts.get(fname, 0)

    if not db_groups:
        db_groups['Combined Cluster'] = {'files': ['All'], 'imported_count': total_raw_intake}

    user_ecs = [
        ec for ec in prisma_state.get('exclusion_criteria', DEFAULT_EXCLUSION_CRITERIA)
        if 'abstract' not in ec.get('title', '').lower() and 'abstract' not in ec.get('id', '').lower()
    ]
    user_ics = prisma_state.get('inclusion_criteria', DEFAULT_INCLUSION_CRITERIA)

    # Pre-screening Missing Abstracts tracking
    tracked_noabs = 0
    for ex in prisma_state.get('exclusions', {}).values():
        if isinstance(ex, dict):
            if ex.get('stage') == 'Pre_Screening' or ex.get('code') == 'PRE_NO_ABS' or 'abstract' in ex.get('reason', '').lower():
                tracked_noabs += 1
        elif isinstance(ex, str) and 'abstract' in ex.lower():
            tracked_noabs += 1
    if tracked_noabs == 0 and prisma_state.get('missing_abstracts_count'):
        tracked_noabs = int(prisma_state['missing_abstracts_count'])

    user_noabs_override = prisma_state.get('missing_abstracts_override', None)
    total_missing_abstracts = int(user_noabs_override) if user_noabs_override is not None else int(tracked_noabs)

    # Compute Included Studies per Database (all articles not yet excluded)
    included_indices = [idx for idx in raw_df.index if idx not in prisma_state['exclusions']]
    included_df = raw_df.loc[included_indices] if included_indices else pd.DataFrame(columns=raw_df.columns)

    computed_final_counts = {}
    for db_name, grp in db_groups.items():
        if 'Source Database' in included_df.columns:
            fin_c = (included_df['Source Database'] == db_name).sum()
        elif 'Source File' in included_df.columns:
            fin_c = included_df['Source File'].isin(grp['files']).sum()
        else:
            fin_c = len(included_df) // len(db_groups)
        computed_final_counts[db_name] = int(fin_c)

    # Compute Live Exclusion Counts per EC from Tab 3 Screening
    ec_counts = {}
    for ex in prisma_state['exclusions'].values():
        if isinstance(ex, dict):
            if ex.get('stage') == 'Pre_Screening' or ex.get('code') == 'PRE_NO_ABS':
                continue
            code = ex.get('code', 'EC')
            ec_counts[code] = ec_counts.get(code, 0) + 1
        else:
            ec_counts[str(ex)] = ec_counts.get(str(ex), 0) + 1

    # Compute Phase 1 manual progression & Post-Phase 1 uploaded count per database
    db_progressions = {}
    for db_name, grp in db_groups.items():
        # Every number for Phase 1 is manually entered by the user (defaults to 0)
        init_val = int(prisma_state.get('db_initial_query_hits', {}).get(db_name, 0))
        uploaded_val = int(prisma_state.get('db_uploaded_overrides', {}).get(db_name, grp['imported_count']))
        fin_val = computed_final_counts.get(db_name, 0)
        
        ic_steps = []
        saved_ic_dict = prisma_state.get('db_ic_progression', {}).get(db_name, {})
        
        for idx_ic, ic in enumerate(user_ics):
            ic_id = ic['id']
            ic_title = ic.get('title', '')
            step_cnt = int(saved_ic_dict.get(ic_id, 0))
            ic_steps.append((ic_id, step_cnt, ic_title))
            
        db_progressions[db_name] = {
            'initial': init_val,
            'ics': ic_steps,
            'uploaded': uploaded_val,
            'final': int(fin_val)
        }

    # Deduplication, Missing Abstracts, and Candidate Pool Entering Phase 2
    user_dup_override = prisma_state.get('duplicates_override', None)
    total_duplicates = int(user_dup_override) if user_dup_override is not None else int(total_dups_tracked)
    total_uploaded_all = sum(d.get('uploaded', 0) for d in db_progressions.values())
    total_screen_in = max(0, total_uploaded_all - total_duplicates - total_missing_abstracts)
    running_pool = total_screen_in
    computed_ec_data = []
    ec_overrides_map = prisma_state.get('ec_overrides', {})
    for ec in user_ecs:
        ec_id = ec.get('id', 'EC')
        ec_title = ec.get('title', 'Excluded')
        cnt = int(ec_overrides_map[ec_id]) if ec_id in ec_overrides_map else int(ec_counts.get(ec_id, 0))
        running_pool = max(0, running_pool - cnt)
        computed_ec_data.append({
            'id': ec_id,
            'title': ec_title,
            'count': cnt,
            'remaining': running_pool
        })

    # Manual Overrides Expander (Bidirectionally synced with Tab 1 and Tab 3 Live Screening)
    with st.expander("Fine-Tune & Override Diagram Numbers (Audit Numbers)", expanded=False, icon=":material/tune:"):
        st.markdown("##### <i class='bi bi-funnel'></i> Phase 1: Manual Search Hits & Inclusion Criteria Progression (Synchronized with Tab 1)", unsafe_allow_html=True)
        st.caption("Every Phase 1 number (Initial Hits and IC 1..N survival) is manually entered by you and automatically synchronized with Tab 1. 'Retrieved Studies (Phase 1 Intake)' reflects candidate studies retrieved post-IC entering deduplication and Phase 2:")
        
        overridden_progressions = {}
        for idx_db, (db_name, pdata) in enumerate(db_progressions.items()):
            st.markdown(f"**Database: `{db_name}`**")
            c_init, *c_ic_cols, c_up = st.columns([1.2] + [1] * len(pdata['ics']) + [1.2])
            with c_init:
                hit_key_t1 = f"hits_{db_name}"
                hit_key_t5 = f"ov_p1_init_{db_name}"
                current_hits = int(prisma_state.get('db_initial_query_hits', {}).get(db_name, pdata['initial']))
                st.session_state[hit_key_t5] = current_hits

                def _on_tab5_hits_change(db=db_name, k1=hit_key_t1, k5=hit_key_t5):
                    val = int(st.session_state[k5])
                    prisma_state['db_initial_query_hits'][db] = val
                    st.session_state[k1] = val
                    auto_save_prisma_state(prisma_state)

                ov_init = st.number_input(
                    f"Initial Hits ({db_name})",
                    min_value=0,
                    key=hit_key_t5,
                    on_change=_on_tab5_hits_change
                )
            
            ov_ics = []
            for idx_s, (s_code, s_cnt, s_title) in enumerate(pdata['ics']):
                col_ic_target = c_ic_cols[idx_s]
                lbl = f"After {s_code} (Manual)"
                
                ic_key_t1 = f"ic_funnel_{db_name}_{s_code}"
                ic_key_t5 = f"ov_p1_ic_{db_name}_{s_code}"
                current_ic_val = int(prisma_state.get('db_ic_progression', {}).get(db_name, {}).get(s_code, s_cnt))
                st.session_state[ic_key_t5] = current_ic_val

                def _on_tab5_ic_change(db=db_name, iid=s_code, k1=ic_key_t1, k5=ic_key_t5):
                    val = int(st.session_state[k5])
                    prisma_state['db_ic_progression'].setdefault(db, {})[iid] = val
                    st.session_state[k1] = val
                    auto_save_prisma_state(prisma_state)

                with col_ic_target:
                    new_s_cnt = st.number_input(
                        lbl,
                        min_value=0,
                        key=ic_key_t5,
                        on_change=_on_tab5_ic_change
                    )
                    ov_ics.append((s_code, int(new_s_cnt), s_title))

            with c_up:
                up_key_t5 = f"ov_uploaded_{db_name}"
                current_up_val = int(prisma_state.get('db_uploaded_overrides', {}).get(db_name, pdata['uploaded']))
                st.session_state[up_key_t5] = current_up_val

                def _on_tab5_up_change(db=db_name, ku=up_key_t5):
                    prisma_state.setdefault('db_uploaded_overrides', {})[db] = int(st.session_state[ku])
                    auto_save_prisma_state(prisma_state)

                ov_up = st.number_input(
                    "Retrieved Studies (Phase 1 Intake)",
                    min_value=0,
                    key=up_key_t5,
                    on_change=_on_tab5_up_change,
                    help="Candidate studies retrieved from this database after Phase 1 (ICs) and before Phase 2 (ECs)."
                )
                    
            overridden_progressions[db_name] = {
                'initial': int(ov_init),
                'ics': ov_ics,
                'uploaded': int(ov_up),
                'final': pdata['final']
            }

        ov_total_uploaded = sum(d.get('uploaded', 0) for d in overridden_progressions.values())

        st.divider()
        st.markdown("##### <i class='bi bi-intersect'></i> Phase 1 Intake & Deduplication (Pre-Phase 2)", unsafe_allow_html=True)
        c_dup_info, c_dup_input = st.columns([2.5, 1.5])
        with c_dup_info:
            st.caption(f"Number of duplicate records removed from retrieved candidate studies before Phase 2 screening. Retrieved Studies ({ov_total_uploaded:,}) &minus; Duplicates = Screening Pool:")
        with c_dup_input:
            dup_ov_key = "ov_duplicates_removed_cnt"
            st.session_state[dup_ov_key] = int(total_duplicates)

            def _on_dup_ov_change():
                prisma_state['duplicates_override'] = int(st.session_state[dup_ov_key])
                auto_save_prisma_state(prisma_state)

            ov_dups = st.number_input(
                "Duplicates Removed:",
                min_value=0,
                key=dup_ov_key,
                on_change=_on_dup_ov_change,
                help="Audit count of duplicates removed from retrieved candidate studies before Phase 2 screening."
            )
            total_duplicates = int(ov_dups)

        st.divider()
        st.markdown("##### <i class='bi bi-file-earmark-x'></i> Pre-Screening: Excluded Records with No Abstract", unsafe_allow_html=True)
        c_noabs_info, c_noabs_input = st.columns([2.5, 1.5])
        with c_noabs_info:
            st.caption(f"Number of publications lacking an abstract excluded prior to Phase 2 screening. Retrieved Studies ({ov_total_uploaded:,}) &minus; Duplicates ({total_duplicates:,}) &minus; No Abstract:")
        with c_noabs_input:
            noabs_ov_key = "ov_missing_abstracts_cnt"
            st.session_state[noabs_ov_key] = int(total_missing_abstracts)

            def _on_noabs_ov_change():
                prisma_state['missing_abstracts_override'] = int(st.session_state[noabs_ov_key])
                auto_save_prisma_state(prisma_state)

            ov_noabs = st.number_input(
                "Missing Abstracts Removed:",
                min_value=0,
                key=noabs_ov_key,
                on_change=_on_noabs_ov_change,
                help="Audit count of articles without abstracts removed before Phase 2 screening."
            )
            total_missing_abstracts = int(ov_noabs)

        st.divider()
        c_ec_hdr, c_ec_rst = st.columns([3, 1.2])
        with c_ec_hdr:
            st.markdown("##### <i class='bi bi-x-circle'></i> Phase 2: Exclusion Criteria Counts (Live from Tab 3 Screening)", unsafe_allow_html=True)
            st.caption("Automatically populated in real time as you evaluate articles in Tab 3 (even when screening is partially complete). You can also override any number below:")
        with c_ec_rst:
            if st.button("Sync to Live Screening", icon=":material/sync:", key="btn_sync_live_screening_tab5", width="stretch", help="Clear manual overrides and restore live counts from Tab 3 Screening & Deduplication."):
                prisma_state['ec_overrides'] = {}
                prisma_state['duplicates_override'] = None
                prisma_state['missing_abstracts_override'] = None
                prisma_state['db_uploaded_overrides'] = {}
                prisma_state['db_final_overrides'] = {}
                for k_del in list(st.session_state.keys()):
                    if k_del.startswith(("ov_ec_", "ov_final_", "ov_uploaded_", "ov_duplicates_", "ov_missing_")):
                        del st.session_state[k_del]
                auto_save_prisma_state(prisma_state)
                st.toast("Synchronized flowchart with live screening and upload counts!", icon=":material/check_circle:")
                st.rerun()

        col_ov_ec = st.columns(min(len(computed_ec_data), 4)) if computed_ec_data else [st]
        overridden_ec_data = []
        ov_running_pool = max(0, ov_total_uploaded - total_duplicates - total_missing_abstracts)
        
        for idx, ec_item in enumerate(computed_ec_data):
            target_col = col_ov_ec[idx % len(col_ov_ec)]
            ec_id = ec_item['id']
            ec_key = f"ov_ec_{ec_id}"
            ec_ov_dict = prisma_state.get('ec_overrides', {})
            current_ec_cnt = int(ec_ov_dict[ec_id]) if ec_id in ec_ov_dict else int(ec_item['count'])
            st.session_state[ec_key] = current_ec_cnt

            def _on_ec_change(eid=ec_id, k=ec_key):
                prisma_state.setdefault('ec_overrides', {})[eid] = int(st.session_state[k])
                auto_save_prisma_state(prisma_state)

            with target_col:
                new_c = st.number_input(
                    f"{ec_item['id']} ({ec_item['title']})",
                    min_value=0,
                    key=ec_key,
                    on_change=_on_ec_change
                )
                ov_running_pool = max(0, ov_running_pool - int(new_c))
                overridden_ec_data.append({
                    'id': ec_item['id'],
                    'title': ec_item['title'],
                    'count': int(new_c),
                    'remaining': ov_running_pool
                })

        st.divider()
        st.markdown("##### <i class='bi bi-check2-all'></i> Phase 3: Digital Library Final Yield Breakdown", unsafe_allow_html=True)
        st.caption("Distribution of surviving studies across digital libraries (matches Final Included in flowchart):")

        total_intake = max(0, ov_total_uploaded - total_duplicates - total_missing_abstracts)
        total_ex = sum(ec['count'] for ec in overridden_ec_data)
        target_final_yield = max(0, total_intake - total_ex)

        # Tracked exclusions per database from raw screening
        tracked_ex_by_db = {}
        for ex_idx in prisma_state['exclusions'].keys():
            if ex_idx in raw_df.index:
                row_db = raw_df.loc[ex_idx, 'Source Database'] if 'Source Database' in raw_df.columns else 'Unspecified Database'
                tracked_ex_by_db[row_db] = tracked_ex_by_db.get(row_db, 0) + 1

        manual_finals = prisma_state.get('db_final_overrides', {})
        balanced_db_finals = compute_balanced_database_survival(
            overridden_progressions,
            total_intake,
            total_ex,
            tracked_ex_by_db,
            manual_finals
        )

        # Check if existing session state values have a stale discrepancy without valid user manual overrides
        stale_sum = sum(st.session_state.get(f"ov_final_{k}", -1) for k in db_groups.keys())
        manual_has_valid_sum = bool(manual_finals and sum(manual_finals.get(k, 0) for k in db_groups.keys()) == target_final_yield)

        col_fin_dbs = st.columns(len(db_groups))
        for idx_db, db_k in enumerate(db_groups.keys()):
            with col_fin_dbs[idx_db]:
                fin_key = f"ov_final_{db_k}"
                expected_fin = int(balanced_db_finals.get(db_k, 0))
                if fin_key not in st.session_state or (stale_sum != target_final_yield and not manual_has_valid_sum):
                    st.session_state[fin_key] = expected_fin

                def _on_final_change(db=db_k, k=fin_key):
                    prisma_state.setdefault('db_final_overrides', {})[db] = int(st.session_state[k])
                    auto_save_prisma_state(prisma_state)

                ov_fin = st.number_input(
                    f"Final Included: {db_k}",
                    min_value=0,
                    key=fin_key,
                    on_change=_on_final_change
                )
                overridden_progressions[db_k]['final'] = int(ov_fin)

        sum_finals = sum(overridden_progressions[db_k]['final'] for db_k in db_groups.keys())
        if sum_finals == target_final_yield:
            st.caption(f"<span style='color:#16A34A; font-weight:600;'><i class='bi bi-check-circle-fill'></i> Audit Balance:</span> Sum of database yields ({sum_finals:,}) equals Final Included studies ({target_final_yield:,}).", unsafe_allow_html=True)
        else:
            diff = sum_finals - target_final_yield
            st.caption(f"<span style='color:#D97706; font-weight:600;'><i class='bi bi-exclamation-triangle-fill'></i> Audit Discrepancy:</span> Sum of database yields ({sum_finals:,}) differs from Final Yield ({target_final_yield:,}) by {diff:+d}. Flowchart and tables auto-balance to {target_final_yield:,}.", unsafe_allow_html=True)
            for db_k, b_val in balanced_db_finals.items():
                overridden_progressions[db_k]['final'] = b_val

    # -------------------------------------------------------------------------
    # LIVE PIPELINE & SCREENING SUMMARY BANNER ABOVE DIAGRAM
    # -------------------------------------------------------------------------
    p1_manual_init_sum = sum(d.get('initial', 0) for d in overridden_progressions.values())
    p1_manual_last_ic_sum = sum(d['ics'][-1][1] if d.get('ics') else d.get('initial', 0) for d in overridden_progressions.values())
    uploaded_sum = sum(d.get('uploaded', 0) for d in overridden_progressions.values())
    screen_pool_sum = max(0, uploaded_sum - total_duplicates - total_missing_abstracts)
    ec_excluded_sum = sum(ec.get('count', 0) for ec in overridden_ec_data)
    final_yield_sum = max(0, screen_pool_sum - ec_excluded_sum)

    live_kept_cnt = len(prisma_state.get('screened_ok', []))
    live_pending_cnt = len(prisma_state.get('screening_queue', []))
    live_eval_cnt = live_kept_cnt + len(prisma_state.get('exclusions', {}))

    p1_warn_badge = ""
    if p1_manual_init_sum == 0 and p1_manual_last_ic_sum == 0:
        p1_warn_badge = ' &nbsp;<span style="background:#FEF3C7; color:#92400E; padding:2px 7px; border-radius:4px; font-weight:600; font-size:11.5px;"><i class="bi bi-pencil-square"></i> Enter Phase 1 manual numbers in Tab 1</span>'

    _render_html(f"""
    <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 4px solid #0284C7; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; font-size: 13px; color: #1E293B; line-height: 1.6;">
        <div><strong><i class="bi bi-funnel-fill" style="color:#0284C7;"></i> Phase 1 (Manual IC Funnel):</strong> Initial Hits: <strong>{p1_manual_init_sum:,}</strong> &rarr; Post-IC Survival: <strong>{p1_manual_last_ic_sum:,}</strong>{p1_warn_badge}</div>
        <div><strong><i class="bi bi-cloud-upload-fill" style="color:#0F172A;"></i> Phase 1 Intake &amp; Deduplication:</strong> Retrieved Studies (Phase 1 Intake): <strong>{uploaded_sum:,}</strong> &nbsp;|&nbsp; <span style="color:#DC2626;">Duplicates: <strong>- {total_duplicates:,}</strong></span>{f' &nbsp;|&nbsp; <span style="color:#DC2626;">No Abstract: <strong>- {total_missing_abstracts:,}</strong></span>' if total_missing_abstracts > 0 else ''} &rarr; <span style="color:#0369A1;"><strong>{screen_pool_sum:,}</strong> Entering Phase 2</span></div>
        <div><strong><i class="bi bi-clipboard2-check-fill" style="color:#16A34A;"></i> Phase 2 Live Screening Status:</strong> Evaluated so far: <strong>{live_eval_cnt:,}</strong> (Explicitly Kept: <span style="color:#16A34A;"><strong>{live_kept_cnt:,}</strong></span> &nbsp;|&nbsp; Excluded via ECs: <span style="color:#DC2626;"><strong>- {ec_excluded_sum:,}</strong></span> &nbsp;|&nbsp; Pending Queue: <strong>{live_pending_cnt:,}</strong>) &rarr; <span style="color:#166534;"><strong>{final_yield_sum:,}</strong> Currently Surviving / Final Included</span></div>
    </div>
    """)

    # -------------------------------------------------------------------------
    # RENDER SELECTED DIAGRAM
    # -------------------------------------------------------------------------
    if "Auditable Horizontal" in diagram_style:
        dot_string = _build_horizontal_slr_diagram(
            db_progressions=overridden_progressions,
            ec_data=overridden_ec_data,
            total_duplicates=total_duplicates,
            total_missing_abstracts=total_missing_abstracts
        )

        st.graphviz_chart(dot_string)

        fn_dot = format_timestamped_filename("auditable_slr_pipeline_flowchart.dot")
        st.download_button(
            "Download DOT format (Import to WebGraphviz / Visio / LaTeX)",
            data=dot_string,
            file_name=fn_dot,
            mime="text/plain",
            on_click=_save_export_on_click,
            args=("exports", "auditable_slr_pipeline_flowchart.dot", dot_string, "w"),
            help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
        )

    else:
        # Build Vertical Auditable PRISMA SLR Flowchart (Separate IC and EC nodes)
        dot_string = _build_vertical_slr_diagram(
            db_progressions=overridden_progressions,
            ec_data=overridden_ec_data,
            user_ics=user_ics,
            total_duplicates=total_duplicates,
            total_missing_abstracts=total_missing_abstracts
        )

        st.graphviz_chart(dot_string)

        fn_dot = format_timestamped_filename("prisma_slr_flowchart.dot")
        st.download_button(
            "Download DOT format (Import to WebGraphviz / Visio / LaTeX)",
            data=dot_string,
            file_name=fn_dot,
            mime="text/plain",
            on_click=_save_export_on_click,
            args=("exports", "prisma_slr_flowchart.dot", dot_string, "w"),
            help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
        )

    # -------------------------------------------------------------------------
    # AUDIT TRAIL DATA MATRICES (TABULAR REPORTING)
    # -------------------------------------------------------------------------
    st.divider()
    st.markdown("### <i class='bi bi-table' style='color:#697aa2;'></i> Methodological Audit Matrices (Tabular Traceability)", unsafe_allow_html=True)
    st.caption("Complete tabular documentation ready for direct inclusion in SLR papers, dissertations, and peer-review audits.")

    tab_mat1, tab_mat2, tab_mat3 = st.tabs([
        "Phase 1 & Upload Transition",
        "Phase 2: Exclusion Criteria Funnel (Live)",
        "Phase 3: Digital Library Yield & Survival"
    ])

    with tab_mat1:
        st.markdown("#### Phase 1: Manual Search Execution, Inclusion Criteria Funnel & Phase 1 Intake")
        # Build Phase 1 dataframe
        p1_rows = []
        for db_name, pdata in overridden_progressions.items():
            row = {
                "Digital Library": db_name,
                "Initial Query Hits (Manual)": f"{pdata['initial']:,}"
            }
            for step_idx, (ic_code, ic_cnt, ic_title) in enumerate(pdata['ics']):
                row[f"{ic_code} ({ic_title}) [Manual]"] = f"{ic_cnt:,}"
            row["Post-IC Survival (Manual)"] = f"{pdata['ics'][-1][1] if pdata['ics'] else pdata['initial']:,}"
            row["Retrieved Studies (Phase 1 Intake)"] = f"{pdata.get('uploaded', 0):,}"
            p1_rows.append(row)
        
        if p1_rows:
            st.dataframe(pd.DataFrame(p1_rows), width="stretch", hide_index=True)
            p1_tot_post_ic = sum(pdata['ics'][-1][1] if pdata['ics'] else pdata['initial'] for pdata in overridden_progressions.values())
            p1_tot_uploaded = sum(pdata.get('uploaded', 0) for pdata in overridden_progressions.values())
            p1_tot_screen = max(0, p1_tot_uploaded - total_duplicates - total_missing_abstracts)
            trans_parts = [
                f"<strong><i class='bi bi-arrow-right-circle-fill'></i> Post-Phase 1 Transition to Phase 2:</strong> <strong>{p1_tot_post_ic:,}</strong> manual Post-IC survival",
                f"<strong>{p1_tot_uploaded:,}</strong> candidate studies retrieved (post-IC intake)"
            ]
            if total_duplicates > 0:
                trans_parts.append(f'<span style="color:#DC2626;"><strong>- {total_duplicates:,}</strong> cross-database duplicates removed</span>')
            else:
                trans_parts.append('<span style="color:#64748B;"><strong>- 0</strong> cross-database duplicates removed</span>')

            if total_missing_abstracts > 0:
                trans_parts.append(f'<span style="color:#DC2626;"><strong>- {total_missing_abstracts:,}</strong> missing abstracts removed</span>')

            trans_parts.append(f'<span style="color:#166534;"><strong>{p1_tot_screen:,}</strong> unique candidate studies entering Phase 2 Screening</span>')

            trans_html = " &nbsp;|&nbsp; ".join(trans_parts)
            _render_html(f'<div style="background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 10px 14px; border-radius: 4px; font-size: 13px; color: #0369A1; margin-top: 10px;">{trans_html}</div>')

    with tab_mat2:
        st.markdown("#### Phase 2: Selection of Publications (Live Exclusion Criteria Evaluation)")
        st.caption(f"Reflects live exclusions recorded in Tab 3 (Currently evaluated: **{live_eval_cnt:,}** | Explicitly included: **{live_kept_cnt:,}** | Pending evaluation: **{live_pending_cnt:,}**).")
        p2_rows = []
        for idx, ec_item in enumerate(overridden_ec_data):
            p2_rows.append({
                "Evaluation Step": f"Step {idx + 1}",
                "Criterion Code": ec_item['id'],
                "Criterion Title": ec_item['title'],
                "Excluded Studies": f"- {ec_item['count']:,}",
                "Remaining Candidate Pool": f"{ec_item['remaining']:,}"
            })
        if p2_rows:
            st.dataframe(pd.DataFrame(p2_rows), width="stretch", hide_index=True)

    with tab_mat3:
        st.markdown("#### Phase 3: Final Digital Library Retention & Yield Rates")
        p3_rows = []
        for db_name, pdata in overridden_progressions.items():
            init_c = pdata['initial']
            post_ic = pdata['ics'][-1][1] if pdata['ics'] else init_c
            up_c = pdata.get('uploaded', 0)
            fin_c = pdata['final']
            ex_tot = max(0, up_c - fin_c)
            retention_rate = (fin_c / up_c * 100) if up_c > 0 else 0
            
            p3_rows.append({
                "Digital Library": db_name,
                "Initial Query Hits (Manual)": f"{init_c:,}",
                "Post-IC Survival (Manual)": f"{post_ic:,}",
                "Retrieved Studies (Phase 1 Intake)": f"{up_c:,}",
                "Dedup & Phase 2 Exclusions": f"- {ex_tot:,}",
                "Final Included (Phase 3)": f"{fin_c:,}",
                "Retention Rate (vs. Retrieved)": f"{retention_rate:.1f}%"
            })
        if p3_rows:
            st.dataframe(pd.DataFrame(p3_rows), width="stretch", hide_index=True)
            tot_p3_final = sum(pdata['final'] for pdata in overridden_progressions.values())
            st.caption(f"Total Final Included Studies across all digital libraries: **{tot_p3_final:,}**.")


# =============================================================================
# TAB IMPLEMENTATIONS: BASIC PRISMA MODE
# =============================================================================

def _render_basic_screening_tab(raw_df, prisma_state):
    # Ensure queue is fully synchronized with un-evaluated studies
    reconcile_screening_queue(prisma_state, raw_df)

    st.markdown("### Manual Screening & Exclusion (Quick Mode)")
    st.write("Review the candidate articles and exclude those that don't match your criteria.")
    
    total_records = len(raw_df)
    total_excluded = len(prisma_state['exclusions'])
    total_included = len(prisma_state['screened_ok'])
    pending = total_records - total_excluded - total_included

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Pending Screening", pending)
    col_m2.metric("Included", total_included)
    col_m3.metric("Excluded", total_excluded)

    st.divider()

    pending_missing = [idx for idx in prisma_state.get('screening_queue', []) if idx in raw_df.index and is_missing_abstract(raw_df.loc[idx])]
    if pending_missing:
        with st.container(border=True):
            c_b1, c_b2 = st.columns([3, 1.2])
            with c_b1:
                st.markdown("<i class='bi bi-robot' style='color:#0284c7;'></i> **Auto-Exclude Rule: Missing Abstracts Detected**", unsafe_allow_html=True)
                st.caption(f"Detected **{len(pending_missing):,}** articles with no abstract in your screening queue.")
            with c_b2:
                if st.button(f"Auto-Exclude All ({len(pending_missing)})", icon=":material/auto_delete:", key="basic_btn_auto_no_abstract", type="primary", width="stretch"):
                    count_ex, _ = execute_auto_exclude_missing_abstracts(raw_df, prisma_state)
                    st.toast(f"Auto-excluded {count_ex} articles without abstract!", icon=":material/auto_delete:")
                    st.rerun()
        st.divider()

    if len(prisma_state['screening_queue']) > 0:
        current_idx = prisma_state['screening_queue'][0]
        current_article = raw_df.loc[current_idx]

        title = current_article.get('Title', 'No Title')
        abstract = current_article.get('Abstract', 'No Abstract')
        authors = current_article.get('Author', 'Unknown Authors')
        year = clean_year_value(current_article.get('Publication Year', '')) or 'Unknown Year'
        keywords = current_article.get('Keywords', 'None')
        journal = current_article.get('Journal', current_article.get('Publisher', 'Unknown Venue'))
        doc_type = current_article.get('Document Type', 'Unknown')

        curr_missing = is_missing_abstract(current_article)
        missing_badge = '<span style="background:#FEE2E2; color:#991B1B; font-size:12px; font-weight:600; padding:3px 8px; border-radius:4px; white-space:nowrap;"><i class="bi bi-exclamation-triangle-fill"></i> No Abstract</span>' if curr_missing else ''

        st.markdown('#### <i class="bi bi-search"></i> Next Article to Screen', unsafe_allow_html=True)
        import html as _html
        safe_title = _html.escape(str(title))
        safe_authors = _html.escape(str(authors))
        safe_year = _html.escape(str(year))
        safe_journal = _html.escape(str(journal))
        safe_doc_type = _html.escape(str(doc_type))
        safe_keywords = _html.escape(str(keywords))

        card_html = (
            f"<div style='background-color: #f8fafc; border-left: 5px solid #697aa2; padding: 18px; border-radius: 6px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.04);'>"
            f"<div style='display:flex; justify-content:space-between; align-items:flex-start;'>"
            f"<h4 style='margin: 0; color: #1E293B; font-size: 18px; font-weight: 600;'>{safe_title}</h4>"
            f"{missing_badge}"
            f"</div>"
            f"<div style='color: #64748b; font-size: 13.5px; margin-top: 8px; line-height: 1.6;'>"
            f"<i class='bi bi-people-fill' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Authors:</span> {safe_authors} <br>"
            f"<i class='bi bi-calendar3' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Year:</span> {safe_year} &nbsp;|&nbsp; "
            f"<i class='bi bi-journal-text' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Venue:</span> {safe_journal} &nbsp;|&nbsp; "
            f"<i class='bi bi-file-earmark-text' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Type:</span> {safe_doc_type} <br>"
            f"<i class='bi bi-tags-fill' style='color: #697aa2;'></i> <span style='font-weight: 600;'>Keywords:</span> {safe_keywords}"
            f"</div></div>"
        )
        st.markdown(card_html, unsafe_allow_html=True)
        with st.expander("Show Abstract", expanded=True):
            if is_missing_abstract(abstract):
                st.markdown("<span style='color:#DC2626; font-style:italic;'><i class='bi bi-exclamation-circle'></i> No abstract text available for this publication in the dataset.</span>", unsafe_allow_html=True)
            else:
                st.write(abstract)

        st.markdown("##### <i class='bi bi-lightning-charge-fill' style='color: #F59E0B;'></i> Action Decision", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Include (Keep)", icon=":material/check_circle:", type="primary", width="stretch", key="basic_btn_include"):
                prisma_state['screened_ok'].append(current_idx)
                prisma_state['screening_queue'].pop(0)
                auto_save_prisma_state(prisma_state)
                st.rerun()

        with col2:
            reason = st.selectbox("Reason for exclusion:", prisma_state.get('custom_reasons', ["Off-topic", "Wrong Language"]), label_visibility="collapsed")
            if st.button("Exclude (Reject)", icon=":material/cancel:", width="stretch", key="basic_btn_exclude"):
                prisma_state['exclusions'][current_idx] = reason
                prisma_state['screening_queue'].pop(0)
                auto_save_prisma_state(prisma_state)
                st.rerun()
                
        with col3:
            if st.button("Skip for now", icon=":material/skip_next:", width="stretch", key="basic_btn_skip"):
                idx = prisma_state['screening_queue'].pop(0)
                prisma_state['screening_queue'].append(idx)
                auto_save_prisma_state(prisma_state)
                st.rerun()
    else:
        st.success("All articles have been screened!", icon=":material/task_alt:")

    st.divider()
    st.markdown("#### Apply Filters to Workspace")
    st.write("Commit the final dataset to the workspace so other modules use the clean data.")
    if st.button("Commit Final Included Dataset to Workspace", type="primary", icon=":material/save:", key="basic_btn_commit"):
        st.session_state.master_df = raw_df.drop(index=list(prisma_state['exclusions'].keys())).reset_index(drop=True)
        auto_save_prisma_state(prisma_state)
        from utils.project_manager import save_master_dataset
        save_master_dataset(st.session_state.master_df)
        st.success(f"Successfully committed {len(st.session_state.master_df)} articles to the main workspace!")
        st.rerun()


def _render_basic_flowchart_tab(raw_df, prisma_state):
    st.markdown("### PRISMA 2020 Flow Diagram")
    
    imported = st.session_state.get('prisma_imported_count', len(raw_df))
    duplicates = len(st.session_state.get('prisma_duplicates', []))
    screened = len(raw_df)
    
    exclusions_list = []
    for ex in prisma_state['exclusions'].values():
        if isinstance(ex, dict):
            exclusions_list.append(ex.get('reason', 'Excluded'))
        else:
            exclusions_list.append(str(ex))
            
    total_excluded_chart = len(exclusions_list)
    included_chart = screened - total_excluded_chart

    reason_counts = {}
    for r in exclusions_list:
        reason_counts[r] = reason_counts.get(r, 0) + 1
    
    reasons_text = "\\n".join([f"- {r}: {c}" for r, c in reason_counts.items()]) if reason_counts else "None"

    with st.expander("Adjust PRISMA Numbers Manually", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            mod_imported = st.number_input("Records identified from databases", value=imported)
            mod_duplicates = st.number_input("Duplicate records removed", value=duplicates)
            mod_screened = st.number_input("Records screened", value=screened)
        with col_b:
            mod_excluded = st.number_input("Records excluded", value=total_excluded_chart)
            mod_reasons = st.text_area("Exclusion Reasons (for box)", value=reasons_text.replace('\\n', '\n')).replace('\n', '\\n')
            mod_included = st.number_input("New studies included", value=included_chart)

    dot_string = f"""
    digraph PRISMA_SMS {{
        rankdir=TB;
        node [shape=rect, style="rounded,filled", fontname="Segoe UI, Helvetica, sans-serif", fontsize=11, color="#94A3B8", fontcolor="#1E293B", margin="0.25,0.15"];
        edge [fontname="Segoe UI, Helvetica, sans-serif", fontsize=10, color="#64748B", penwidth=1.2, arrowsize=0.8];
        
        # Nodes
        ID [label="Initial Search & Identification\\nDatabases & Snowballing\\n(n = {mod_imported})", fillcolor="#F1F5F9"];
        Dups [label="Excluded:\\nDuplicates Removed\\n(n = {mod_duplicates})", fillcolor="#FEE2E2", color="#FCA5A5"];
        Screen [label="Title & Abstract Screening\\n(n = {mod_screened})", fillcolor="#E0F2FE", color="#7DD3FC"];
        Excluded [label="Excluded based on\\nTitle & Abstract\\n(n = {mod_excluded})", fillcolor="#FEE2E2", color="#FCA5A5"];
        FullText [label="Full-Text Eligibility &\\nClassification Scheme\\n(n = {mod_screened - mod_excluded})", fillcolor="#E0F2FE", color="#7DD3FC"];
        ExcludedReasons [label="Excluded based on Full-Text:\\n{mod_reasons}", fillcolor="#FEE2E2", color="#FCA5A5"];
        Included [label="Final Studies Included\\nin Systematic Mapping\\n(n = {mod_included})", fillcolor="#DCFCE7", color="#86EFAC", fontcolor="#166534", style="rounded,filled,bold"];
        
        # Edges
        ID -> Screen;
        ID -> Dups [style=dashed];
        Screen -> FullText;
        Screen -> Excluded [style=dashed];
        FullText -> Included;
        FullText -> ExcludedReasons [style=dashed];
        
        {{rank=same; ID Dups}}
        {{rank=same; Screen Excluded}}
        {{rank=same; FullText ExcludedReasons}}
    }}
    """

    st.graphviz_chart(dot_string)

    fn_dot = format_timestamped_filename("prisma_flowchart.dot")
    st.download_button(
        "Download DOT format (Import to WebGraphviz/Visio)",
        data=dot_string,
        file_name=fn_dot,
        mime="text/plain",
        on_click=_save_export_on_click,
        args=("exports", "prisma_flowchart.dot", dot_string, "w"),
        help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
    )


# =============================================================================
# SHARED TAB: EXCLUDED DUPLICATES
# =============================================================================

def _render_duplicates_tab():
    st.markdown("### Excluded Duplicates Verification")
    st.write("Review articles that were automatically excluded during the data ingestion and enrichment phases due to being identified as duplicates.")
    
    duplicates_list = st.session_state.get('prisma_duplicates', [])
    if not duplicates_list:
        ps = st.session_state.get('prisma_state')
        if ps and 'prisma_duplicates' in ps and ps['prisma_duplicates']:
            duplicates_list = ps['prisma_duplicates']
            st.session_state.prisma_duplicates = duplicates_list

    # Check for manual audit override if user explicitly configured one in Tab 5
    ps = st.session_state.get('prisma_state', {})
    dup_override = ps.get('duplicates_override', None) if isinstance(ps, dict) else None

    if not duplicates_list and dup_override is None:
        st.metric("Total Duplicates Removed", 0)
        st.info("No duplicate records were detected or removed during data ingestion or enrichment.")
        return
    elif not duplicates_list and dup_override is not None:
        st.metric("Total Duplicates Removed (Manual Audit Override)", int(dup_override))
        _render_html(f"""
        <div style="background-color: #FEF2F2; border-left: 4px solid #EF4444; padding: 12px 16px; border-radius: 6px; margin-top: 10px; color: #991B1B; font-size: 13.5px;">
            <i class="bi bi-info-circle-fill"></i> <strong>Audit Override Active:</strong> 
            Flowchart diagrams reflect a manually entered count of <strong>{int(dup_override):,}</strong> duplicates removed. No automatic duplicate pairs were recorded in memory.
        </div>
        """)
        return
    else:
        st.metric("Total Duplicates Removed", len(duplicates_list))
        st.divider()
        
        phases = {}
        for dup in duplicates_list:
            p = dup.get('phase', 'Ingestion')
            if p not in phases:
                phases[p] = []
            phases[p].append(dup)
            
        for phase, ph_dups in phases.items():
            st.markdown(f"#### Phase: {phase} ({len(ph_dups)} duplicates)")
            for i, dup in enumerate(ph_dups):
                kept = dup['kept']
                removed = dup['removed']
                stage = dup['stage']
                
                def _get_val(row, col):
                    return row[col] if col in row and pd.notna(row[col]) and str(row[col]).strip() else 'N/A'
                
                with st.expander(f"Pair {i+1} - Matched on {stage} (Kept: {_get_val(kept, 'Title')})", expanded=False):
                    st.markdown("<i class='bi bi-check-circle-fill' style='color:#16a34a;'></i> **Kept Version**", unsafe_allow_html=True)
                    _render_html(f"""
                    <div style="background-color: #f0fdf4; border-left: 4px solid #22c55e; padding: 12px; border-radius: 4px; margin-bottom: 15px; color: #166534;">
                        <strong>Title:</strong> {_get_val(kept, 'Title')}<br>
                        <strong>Authors:</strong> {_get_val(kept, 'Author')}<br>
                        <strong>Year:</strong> {_get_val(kept, 'Publication Year')} | 
                        <strong>Venue:</strong> {_get_val(kept, 'Journal')}<br>
                        <strong>DOI:</strong> {_get_val(kept, 'DOI')} | 
                        <strong>PMID:</strong> {_get_val(kept, 'PMID')} | 
                        <strong>OpenAlex ID:</strong> {_get_val(kept, 'OpenAlex ID')}
                    </div>
                    """)
                    
                    st.markdown("<i class='bi bi-x-circle-fill' style='color:#dc2626;'></i> **Excluded Version**", unsafe_allow_html=True)
                    _render_html(f"""
                    <div style="background-color: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; border-radius: 4px; margin-bottom: 5px; color: #991b1b;">
                        <strong>Title:</strong> {_get_val(removed, 'Title')}<br>
                        <strong>Authors:</strong> {_get_val(removed, 'Author')}<br>
                        <strong>Year:</strong> {_get_val(removed, 'Publication Year')} | 
                        <strong>Venue:</strong> {_get_val(removed, 'Journal')}<br>
                        <strong>DOI:</strong> {_get_val(removed, 'DOI')} | 
                        <strong>PMID:</strong> {_get_val(removed, 'PMID')} | 
                        <strong>OpenAlex ID:</strong> {_get_val(removed, 'OpenAlex ID')}
                    </div>
                    """)
