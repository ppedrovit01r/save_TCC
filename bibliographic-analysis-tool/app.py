import streamlit as st
import pandas as pd

from core.main import show as show_data_prep
from dashboard.main import show as show_dashboard
# --- FEATURE IMPORTS ---
# from features.network_topology import show_cocitation
# from features.semantic_analysis import show_thematic_stratification, show_thematic_flow
# from features.metrics_advanced import show_endogeneity
# from features.mapping import show_geographic, show_gender
# from features.assistants import show_prisma, show_review_matcher

from utils.style import apply_custom_css

st.set_page_config(page_title="Editorial Decision Support", layout="wide", initial_sidebar_state="expanded")
apply_custom_css()

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
        if st.button("← Return to Analysis Workspace"):
            st.session_state.fullscreen_core = False
            st.rerun()
            
    st.title("Bibliometric Decision Support System")
    st.caption("Journal Analysis Hub") #not necessary
    show_data_prep(is_sidebar=False)

else:
    # 2. LOADED STATE: Retractable Sidebar (Core) & Persistent Menu
    with st.sidebar:
        st.header("🗄️ Data Management")
        if st.button("⛶ Expand to Fullscreen", use_container_width=True):
            st.session_state.fullscreen_core = True
            st.rerun()
        st.divider()
        # Render the core module inside the sidebar
        show_data_prep(is_sidebar=True)

    # Main Area: Split into Persistent Menu and Features Window
    nav_col, content_col = st.columns([2, 8], gap="large")
    
    with nav_col:
        st.markdown('<div class="persistent-menu">', unsafe_allow_html=True)

        # --- PERSONA TOGGLE ---
        st.subheader("Profile Mode")
        profile = st.select_slider(
            "Select Features Context",
            options=["RESEARCHER", "ALL", "EDITORIAL"],
            value="ALL",
            label_visibility="collapsed"
        )

        st.divider
        st.subheader("Data Overview")
        num_articles = len(st.session_state.master_df)
        st.metric("Articles in Memory", f"{num_articles:,}")
        # You can add more brief metrics here (e.g., total authors, years span)
        
        # --- DYNAMIC MENU LOGIC ---
        st.divider()
        st.subheader("Navigation")
        # Base feature available to everyone
        menu_options = ["Main Dashboard"]
        # Features for Researchers
        if profile in ["ALL", "RESEARCHER"]:
            menu_options.extend(["Co-citation Networks", "PRISMA Assistant"])
        # Features for Editorials
        if profile in ["ALL", "EDITORIAL"]:
            menu_options.extend(["Endogeneity Index", "Review Matcher"])
        # Shared Auxiliary Features
        menu_options.extend([
            "Thematic Stratification", 
            "Thematic Flow", 
            "Geographic Mapping", 
            "Gender Mapping"
        ])
        # The Radio Menu
        page = st.radio("Select Feature:", menu_options, label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)

    # --- CONTENT ROUTING ---
    with content_col:
        if page == "Main Dashboard":
            # Pass the profile to the dashboard so it knows what to hide
            show_dashboard(profile)
        
        # --- FEATURE ROUTING (Uncomment when files are ready) ---
        # elif page == "Co-citation Networks":
        #     show_cocitation(st.session_state.master_df)
        # elif page == "PRISMA Assistant":
        #     show_prisma(st.session_state.master_df)
        # elif page == "Endogeneity Index":
        #     show_endogeneity(st.session_state.master_df)
        # elif page == "Review Matcher":
        #     show_review_matcher(st.session_state.master_df)
        # elif page == "Thematic Stratification":
        #     show_thematic_stratification(st.session_state.master_df)
        # elif page == "Thematic Flow":
        #     show_thematic_flow(st.session_state.master_df)
        # elif page == "Geographic Mapping":
        #     show_geographic(st.session_state.master_df)
        # elif page == "Gender Mapping":
        #     show_gender(st.session_state.master_df)
        else:
            st.info(f"🏗️ The module for **{page}** is currently under construction.")