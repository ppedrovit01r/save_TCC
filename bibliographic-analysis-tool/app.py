import streamlit as st
import pandas as pd
import base64
import os

from core.main import show as show_data_prep
from dashboard.main import show as show_dashboard
from utils.style import apply_custom_css

st.set_page_config(page_title="Editorial Decision Support", layout="wide", initial_sidebar_state="expanded")
apply_custom_css()

def get_sidebar_logo_html():
    logo_path = os.path.join("utils", "cropped-logo-300x86.png")
    logo2_path = os.path.join("utils", "Logo_UFRGS.png")
    
    encoded_bpm = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            encoded_bpm = base64.b64encode(f.read()).decode("utf-8")
            
    encoded_ufrgs = ""
    if os.path.exists(logo2_path):
        with open(logo2_path, "rb") as f:
            encoded_ufrgs = base64.b64encode(f.read()).decode("utf-8")
            
    if encoded_bpm and encoded_ufrgs:
        return f'''
        <div style="display: flex; justify-content: center; align-items: center; gap: 20px; padding: 10px 0 16px 0;">
            <a href="https://www.ufrgs.br/bpmlab/" target="_blank" rel="noopener noreferrer" style="display: flex; align-items: center; justify-content: center; text-decoration: none;">
                <img src="data:image/png;base64,{encoded_bpm}" alt="BPM Research Lab Logo" style="max-height: 54px; max-width: 190px; width: auto; object-fit: contain; cursor: pointer; transition: transform 0.2s ease-in-out;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1.0)'" />
            </a>
            <a href="https://www.ufrgs.br/site/" target="_blank" rel="noopener noreferrer" style="display: flex; align-items: center; justify-content: center; text-decoration: none;">
                <img src="data:image/png;base64,{encoded_ufrgs}" alt="UFRGS Logo" style="max-height: 94px; max-width: 125px; width: auto; object-fit: contain; cursor: pointer; transition: transform 0.2s ease-in-out;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1.0)'" />
            </a>
        </div>
        '''
    elif encoded_bpm:
        return f'''
        <div style="text-align: center; padding: 5px 0 12px 0;">
            <a href="https://www.ufrgs.br/bpmlab/" target="_blank" rel="noopener noreferrer" style="text-decoration: none; display: inline-block;">
                <img src="data:image/png;base64,{encoded_bpm}" alt="BPM Research Lab Logo" style="max-width: 230px; width: 85%; height: auto; cursor: pointer; transition: transform 0.2s ease-in-out;" onmouseover="this.style.transform='scale(1.04)'" onmouseout="this.style.transform='scale(1.0)'" />
            </a>
        </div>
        '''
    return '''
    <div style="text-align: center; padding: 5px 0 12px 0;">
        <a href="https://www.ufrgs.br/bpmlab/" target="_blank" rel="noopener noreferrer" style="text-decoration: none; font-size: 18px; font-weight: 700; color: #697aa2;">
            ⚙️ BPM Research Lab
        </a>
    </div>
    '''

# --- STATE MANAGEMENT ---
if 'master_df' not in st.session_state:
    st.session_state.master_df = None
if 'fullscreen_core' not in st.session_state:
    st.session_state.fullscreen_core = True

has_data = st.session_state.master_df is not None

# --- ROUTING LOGIC ---
if not has_data or st.session_state.fullscreen_core:
    # 1. INITIAL STATE: Fullscreen Data Prep
    if has_data:
        # If they have data but forced fullscreen, let them return
        if st.button("Return to Analysis Workspace", icon=":material/arrow_back:"):
            st.session_state.fullscreen_core = False
            st.rerun()
            
    show_data_prep(is_sidebar=False)

else:
    # 2. LOADED STATE: Unified Professional Sidebar
    with st.sidebar:
        # --- RESEARCH GROUP LOGO ---
        st.markdown(get_sidebar_logo_html(), unsafe_allow_html=True)
        
        # --- ACTIVE PROJECT WORKSPACE BADGE ---
        from utils.project_manager import get_active_project_name, open_project_folder
        current_proj = get_active_project_name()
        st.markdown(f"""
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #697aa2; border-radius: 6px; padding: 8px 12px; margin-bottom: 8px;">
            <div style="font-size: 10.5px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px;">Active Project</div>
            <div style="font-size: 13.5px; font-weight: 700; color: #1E293B; margin-top: 1px; word-break: break-all;">📁 {current_proj}</div>
            <div style="font-size: 10.5px; color: #94A3B8; margin-top: 1px;">Projects/{current_proj}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Open Project Folder Quick Action
        if st.button("Open Project Folder", icon=":material/folder:", width="stretch", key="sidebar_open_proj_folder_btn", help="Opens the project folder in your local file explorer"):
            open_project_folder()
        st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

        # --- PROFILE MODE BUTTONS ---
        st.markdown('<div style="font-size:12px; color:#64748B; font-weight:600; margin-bottom:6px;"><i class="bi bi-person-badge"></i> PROFILE CONTEXT</div>', unsafe_allow_html=True)
        if "profile" not in st.session_state:
            st.session_state.profile = "ALL"
            
        p_c1, p_c2, p_c3 = st.columns(3, gap="small")
        if p_c1.button("All", icon=":material/public:", type="primary" if st.session_state.profile == "ALL" else "secondary", width="stretch"):
            st.session_state.profile = "ALL"
            st.rerun()
        if p_c2.button("Research", icon=":material/science:", type="primary" if st.session_state.profile == "RESEARCHER" else "secondary", width="stretch"):
            st.session_state.profile = "RESEARCHER"
            st.rerun()
        if p_c3.button("Editorial", icon=":material/newspaper:", type="primary" if st.session_state.profile == "EDITORIAL" else "secondary", width="stretch"):
            st.session_state.profile = "EDITORIAL"
            st.rerun()

        profile = st.session_state.profile
        st.divider()

        # --- 2-COLUMN NAVIGATION GRID ---
        st.markdown('<div style="font-size:12px; color:#64748B; font-weight:600; margin-bottom:6px;"><i class="bi bi-compass"></i> NAVIGATION MENU</div>', unsafe_allow_html=True)
        if "current_page" not in st.session_state: 
            st.session_state.current_page = "Main Dashboard"

        # Collect all valid pages based on user profile permissions
        all_allowed_pages = ["Main Dashboard"]

        if profile in ["ALL", "RESEARCHER"]:
            all_allowed_pages.extend(["Co-citation Networks", "PRISMA Assistant"])

        all_allowed_pages.extend([
            "Thematic Stratification", 
            "Thematic Flow", 
            "Demographics", 
            "Gender Mapping"
        ])

        # Mathematically split the list exactly in half
        midpoint = (len_pages := len(all_allowed_pages)) // 2 + (len_pages % 2)

        pages_left = all_allowed_pages[:midpoint]
        pages_right = all_allowed_pages[midpoint:]

        n_col1, n_col2 = st.columns(2, gap="small")
        with n_col1:
            for p_name in pages_left:
                is_active = st.session_state.current_page == p_name
                if st.button(
                    p_name, 
                    key=f"nav_l_{p_name}", 
                    type="primary" if is_active else "secondary", 
                    width="stretch"
                ):
                    st.session_state.current_page = p_name
                    st.rerun()

        with n_col2:
            for p_name in pages_right:
                is_active = st.session_state.current_page == p_name
                if st.button(
                    p_name, 
                    key=f"nav_r_{p_name}", 
                    type="primary" if is_active else "secondary", 
                    width="stretch"
                ):
                    st.session_state.current_page = p_name
                    st.rerun()

        page = st.session_state.current_page
        st.divider()

        # --- CORE DATA PREP & CLUSTER HUB ---
        with st.expander("Core Data Prep & Cluster Memory", expanded=False, icon=":material/database:"):
            show_data_prep(is_sidebar=True)

        st.divider()

        # --- FULLSCREEN BUTTON AT THE VERY END ---
        if st.button("Expand Data Prep Fullscreen", icon=":material/fullscreen:", width="stretch"):
            st.session_state.fullscreen_core = True
            st.rerun()

    # --- FOCUS MODE DATA INTERCEPTION ---
    if 'focus_topics' not in st.session_state:
        st.session_state.focus_topics = []

    working_df = st.session_state.master_df
    is_focused = len(st.session_state.focus_topics) > 0

    if is_focused and 'unified_topic' in working_df.columns:
        working_df = working_df[working_df['unified_topic'].isin(st.session_state.focus_topics)]

    # Make working_df available in session state for modules that hardcode session_state calls
    st.session_state.working_df = working_df

    # --- FOCUS MODE UI BANNER ---
    if is_focused:
        with st.sidebar:
            st.error("GLOBAL FOCUS MODE ACTIVE")
            
            # Fetch AI Names for the banner
            topic_names = []
            for t in st.session_state.focus_topics:
                name = st.session_state.topic_names.get(t, {}).get('name', f'Topic {t}') if 'topic_names' in st.session_state else f'Topic {t}'
                topic_names.append(name)
                
            st.caption(f"Isolating analysis to: **{', '.join(topic_names)}**")
            if st.button("Clear Focus (Return to Full Data)", icon=":material/close:", width="stretch", type="primary"):
                st.session_state.focus_topics = []
                st.rerun()

    # --- MAIN WORKSPACE CONTENT ROUTING ---
    if page == "Main Dashboard":
        show_dashboard(profile)
    elif page == "Co-citation Networks":
        from features.network_topology import show as show_net
        show_net(working_df)
    elif page == "Thematic Stratification":
        from features.thematic_stratification import show as show_stratification
        # CRITICAL: Always pass raw_df_backup (or master_df) to stratification so they can see all topics!
        df_to_use = st.session_state.get('raw_df_backup', st.session_state.master_df)
        show_stratification(df_to_use)
    elif page == "Thematic Flow":
        from features.thematic_flow import show as show_flow
        show_flow(st.session_state.master_df)
    elif page == "PRISMA Assistant":
        from features.prisma_assistant import show as show_prisma
        show_prisma(st.session_state.master_df)
    elif page == "Demographics":
        from features.demographics import show as show_demographics
        show_demographics(st.session_state.master_df)
    elif page == "Gender Mapping":
        from features.gender import show as show_gender
        show_gender(working_df)
    else:
        st.info(f"🏗️ The module for **{page}** is currently under construction.")
        
        # Add Placeholder Mathematical Foundation Expanders
        with st.expander("📐 Mathematical & Methodological Foundation"):
            if page == "Endogeneity Index":
                st.markdown("""
                **Endogeneity in Bibliometric Citations**
                Measures systemic bias (e.g., self-citation cartels, institutional incest).
                *   Utilizes econometric techniques like **Instrumental Variables (IV)** or **Two-Stage Least Squares (2SLS)**.
                *   $$ Y_i = \\beta_0 + \\beta_1 X_i + \\beta_2 W_i + u_i $$ where $X_i$ is potentially endogenous.
                """)
            elif page in ["Geographic Mapping", "Gender Mapping"]:
                st.markdown("""
                **Spatial Autocorrelation & Demographic Inference**
                *   **Moran's I** for spatial clustering: $$ I = \\frac{N}{W} \\frac{\\sum_i \\sum_j w_{ij}(x_i - \\bar{x})(x_j - \\bar{x})}{\\sum_i (x_i - \\bar{x})^2} $$
                *   **Gender Inference Confidence Scoring**: Probabilistic name matching algorithms (e.g. naive Bayes on historical census data).
                """)
            elif page == "PRISMA Assistant":
                st.markdown("""
                **Vector Space Matching**
                Uses **Cosine Similarity** on TF-IDF or BM25 vector representations to match abstracts with appropriate peer reviewers or to automate PRISMA screening steps.
                *   $$ \\text{sim}(A, B) = \\cos(\\theta) = \\frac{A \\cdot B}{\\|A\\| \\|B\\|} $$
                """)
            else:
                st.markdown("Mathematical specifications for this module are still being formalized.")