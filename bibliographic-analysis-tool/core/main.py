import streamlit as st
import tempfile
import os
import pandas as pd
from core.ingestion import parse_file, TARGET_COLUMNS
from core.enrichment import enrich_dataset_openalex
from core.export import df_to_csv, df_to_excel, df_to_ris, df_to_bib

def show():
    st.title("Data Preparation & Upload")

    if "execution_logs" not in st.session_state:
        st.session_state.execution_logs = []

    uploaded_file = st.file_uploader(
        "Upload your dataset (Excel, CSV, RIS, or BibTeX format):",
        type=["csv", "xls", "xlsx", "bib", "ris"]
    )

    if uploaded_file is None:
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

    st.write("### Data Preview")
    st.dataframe(st.session_state.raw_df.head(7))

    st.markdown("---")
    st.subheader("What do you want to do with this file?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Direct Usage")
        st.write("Load data directly into memory without querying external APIs.")
        if st.button("Load to Memory", use_container_width=True):
            st.session_state.master_df = st.session_state.raw_df.copy()
            st.session_state.execution_logs.append("Data loaded directly into memory for analysis.")
            st.success("Data loaded successfully! Proceed to analysis tabs.")

    with col2:
        st.markdown("#### Enrichment (using OpenAlex API)")
        fields_to_enrich = st.multiselect(
            "Select which missing fields to fetch:",
            options=['Author', 'Publication Year', 'Times Cited', 'Publisher', 'Article References'],
            default=['Times Cited', 'Article References']
        )

        can_process = len(fields_to_enrich) > 0
        
        if st.button("Process and Load", use_container_width=True, disabled=not can_process):
            with st.spinner("Querying OpenAlex..."):
                df_processed = enrich_dataset_openalex(
                    st.session_state.raw_df.copy(), 
                    fields_to_enrich, 
                    st.session_state.execution_logs
                )
                st.session_state.master_df = df_processed
                st.success("Enrichment complete! Data loaded into memory.")

    #Logs
    st.markdown("---")
    with st.expander("System Execution Logs", expanded=True):
        for log in st.session_state.execution_logs:
            st.text(f"> {log}")
        if st.button("Clear Logs"):
            st.session_state.execution_logs = []
            st.rerun()

    # Export
    if st.session_state.get('master_df') is not None:
        st.markdown("---")
        st.subheader("Export Processed Data")
        
        df_export = st.session_state.master_df
        
        exp_col1, exp_col2, exp_col3, exp_col4 = st.columns(4)
        with exp_col1:
            st.download_button("Export as CSV", data=df_to_csv(df_export), file_name="processed_data.csv", mime="text/csv", use_container_width=True)
        with exp_col2:
            st.download_button("Export as Excel", data=df_to_excel(df_export), file_name="processed_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with exp_col3:
            st.download_button("Export as RIS", data=df_to_ris(df_export), file_name="processed_data.ris", mime="application/x-research-info-systems", use_container_width=True)
        with exp_col4:
            st.download_button("Export as BibTeX", data=df_to_bib(df_export), file_name="processed_data.bib", mime="application/x-bibtex", use_container_width=True)