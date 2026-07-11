import streamlit as st
import tempfile
import os
import pandas as pd
from core.ingestion import parse_file, TARGET_COLUMNS
from core.enrichment import enrich_dataset_openalex
from core.export import df_to_csv, df_to_excel, df_to_ris, df_to_bib

def show(is_sidebar=False):
    # Adjust titles based on context
    if not is_sidebar:
        st.header("Data Preparation & Upload")
    else:
        st.subheader("Upload & Enrich")

    if "execution_logs" not in st.session_state:
        st.session_state.execution_logs = []

    uploaded_file = st.file_uploader(
        "Upload dataset (Excel, CSV, RIS, BibTeX):",
        type=["csv", "xls", "xlsx", "bib", "ris"],
        key="uploader_sidebar" if is_sidebar else "uploader_main"
    )

    if uploaded_file is None:
        if not is_sidebar:
            st.info("Please upload a file to begin.")
        return

    # Read and Normalize Immediately
    try:
        if 'raw_df' not in st.session_state or st.session_state.get('last_uploaded') != uploaded_file.name:
            start_time = pd.Timestamp.now()
            df_normalized = parse_file(uploaded_file)
            duration = pd.Timestamp.now() - start_time

            st.session_state.raw_df = df_normalized
            st.session_state.last_uploaded = uploaded_file.name
            st.session_state.execution_logs.append(f"File '{uploaded_file.name}' ingested and normalized in {duration:.2f} seconds.")
    except Exception as e:
        st.error(f"Error parsing file: {e}")
        return

    if not is_sidebar:
        st.write("### Data Preview")
        st.dataframe(st.session_state.raw_df.head(4))
        st.divider()

    # --- ACTION BUTTONS ---
    st.markdown("**Process Options**")
    
    # If in main screen, use columns. If in sidebar, stack vertically.
    if not is_sidebar:
        col1, col2 = st.columns(2)
    else:
        col1, col2 = st.container(), st.container()

    with col1:
        if st.button("Load Directly to Memory", use_container_width=True, type="primary" if is_sidebar else "secondary"):
            st.session_state.master_df = st.session_state.raw_df.copy()
            st.session_state.execution_logs.append("Data loaded directly into memory.")
            st.session_state.fullscreen_core = False # Auto-collapse fullscreen
            st.rerun()

    with col2:
        with st.expander("Enrich with OpenAlex", expanded=not is_sidebar):
            fields_to_enrich = st.multiselect(
                "Select missing fields:",
                options=['Author', 'Publication Year', 'Times Cited', 'Publisher', 'Article References'],
                default=['Times Cited', 'Article References']
            )
            if st.button("Process & Load", use_container_width=True, disabled=len(fields_to_enrich)==0):
                with st.spinner("Querying OpenAlex..."):
                    df_processed = enrich_dataset_openalex(
                        st.session_state.raw_df.copy(), 
                        fields_to_enrich, 
                        st.session_state.execution_logs
                    )
                    st.session_state.master_df = df_processed
                    st.session_state.fullscreen_core = False # Auto-collapse fullscreen
                    st.rerun()

    # --- EXPORT ---
    if st.session_state.get('master_df') is not None:
        st.divider()
        st.markdown("**Export Processed Data**")
        df_export = st.session_state.master_df
        
        if not is_sidebar:
            ec1, ec2, ec3, ec4 = st.columns(4)
        else:
            ec1, ec2, ec3, ec4 = st.container(), st.container(), st.container(), st.container()
            
        with ec1: st.download_button("CSV", data=df_to_csv(df_export), file_name="processed_data.csv", use_container_width=True)
        with ec2: st.download_button("Excel", data=df_to_excel(df_export), file_name="processed_data.xlsx", use_container_width=True)
        with ec3: st.download_button("RIS", data=df_to_ris(df_export), file_name="processed_data.ris", use_container_width=True)
        with ec4: st.download_button("BibTeX", data=df_to_bib(df_export), file_name="processed_data.bib", use_container_width=True)

    # Logs
    if not is_sidebar:
        st.divider()
        with st.expander("System Execution Logs"):
            for log in st.session_state.execution_logs:
                st.text(f"> {log}")