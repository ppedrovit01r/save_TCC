import streamlit as st
import pandas as pd

def show(master_df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-diagram-3-fill' style='color: #697aa2;'></i> PRISMA Assistant</h2>", unsafe_allow_html=True)
    st.caption("Automated System for Systematic Literature Reviews (Kitchenham Guidelines)")

    if master_df is None or master_df.empty:
        st.warning("No dataset loaded. Please go to Data Preparation to load your articles.")
        return

    # Ensure state initialization
    if 'raw_df_backup' not in st.session_state:
        st.error("Raw data backup not found. Please re-upload your files in the Data Prep module.")
        return

    raw_df = st.session_state.raw_df_backup

    if 'prisma_state' not in st.session_state:
        st.session_state.prisma_state = {
            'exclusions': {}, # row_index -> reason
            'custom_reasons': ["Off-topic", "Wrong Language", "Not Peer-Reviewed", "Wrong Population", "Wrong Outcome"],
            'screening_queue': list(raw_df.index),
            'screened_ok': []
        }
    
    prisma_state = st.session_state.prisma_state

    # Ensure queue only contains valid indices
    prisma_state['screening_queue'] = [idx for idx in prisma_state['screening_queue'] if idx in raw_df.index]

    # Layout: Tabs
    tab_screening, tab_flowchart = st.tabs(["Screening & Exclusion", "PRISMA Flowchart Generator"])

    with tab_screening:
        st.markdown("### Manual Screening & Exclusion")
        st.write("Review the articles and exclude those that don't match your PICOC criteria.")
        
        total_records = len(raw_df)
        total_excluded = len(prisma_state['exclusions'])
        total_included = len(prisma_state['screened_ok'])
        pending = total_records - total_excluded - total_included

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Pending Screening", pending)
        col_m2.metric("Included", total_included)
        col_m3.metric("Excluded", total_excluded)

        st.divider()

        if len(prisma_state['screening_queue']) > 0:
            current_idx = prisma_state['screening_queue'][0]
            current_article = raw_df.loc[current_idx]

            title = current_article.get('Title', 'No Title')
            abstract = current_article.get('Abstract', 'No Abstract')
            authors = current_article.get('Author', 'Unknown Authors')
            
            # Safely format year as integer
            raw_year = current_article.get('Publication Year', 'Unknown Year')
            try:
                year = str(int(float(raw_year)))
            except (ValueError, TypeError):
                year = str(raw_year)
                
            keywords = current_article.get('Keywords', 'None')
            journal = current_article.get('Journal', current_article.get('Publisher', 'Unknown Venue'))
            doc_type = current_article.get('Document Type', 'Unknown')

            st.markdown('#### <i class="bi bi-search"></i> Next Article to Screen', unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background-color: #f8fafc; border-left: 5px solid #697aa2; padding: 18px; border-radius: 6px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.04);">
                <h4 style="margin-top: 0; color: #1E293B; font-size: 18px; font-weight: 600;">{title}</h4>
                <div style="color: #64748b; font-size: 13.5px; margin-top: 8px; line-height: 1.6;">
                    <i class="bi bi-people-fill" style="color: #697aa2;"></i> <span style="font-weight: 600;">Authors:</span> {authors} <br>
                    <i class="bi bi-calendar3" style="color: #697aa2;"></i> <span style="font-weight: 600;">Year:</span> {year} &nbsp;|&nbsp; 
                    <i class="bi bi-journal-text" style="color: #697aa2;"></i> <span style="font-weight: 600;">Venue:</span> {journal} &nbsp;|&nbsp; 
                    <i class="bi bi-file-earmark-text" style="color: #697aa2;"></i> <span style="font-weight: 600;">Type:</span> {doc_type} <br>
                    <i class="bi bi-tags-fill" style="color: #697aa2;"></i> <span style="font-weight: 600;">Keywords:</span> {keywords}
                </div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander("Show Abstract", expanded=True):
                st.write(abstract)

            st.markdown("##### <i class='bi bi-lightning-charge-fill' style='color: #F59E0B;'></i> Action Decision", unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Include (Keep)", icon=":material/check_circle:", type="primary", width="stretch", key="btn_include"):
                    prisma_state['screened_ok'].append(current_idx)
                    prisma_state['screening_queue'].pop(0)
                    st.rerun()

            with col2:
                reason = st.selectbox("Reason for exclusion:", prisma_state['custom_reasons'], label_visibility="collapsed")
                if st.button("Exclude (Reject)", icon=":material/cancel:", width="stretch", key="btn_exclude"):
                    prisma_state['exclusions'][current_idx] = reason
                    prisma_state['screening_queue'].pop(0)
                    st.rerun()
                    
            with col3:
                if st.button("Skip for now", icon=":material/skip_next:", width="stretch", key="btn_skip"):
                    # Move to end of queue
                    idx = prisma_state['screening_queue'].pop(0)
                    prisma_state['screening_queue'].append(idx)
                    st.rerun()
        else:
            st.success("All articles have been screened!", icon=":material/task_alt:")

        st.divider()
        st.markdown("#### Apply Filters to Workspace")
        st.write("Commit the final dataset to the workspace so other modules (like Thematic Stratification) use the clean data.")
        if st.button("Commit Final Included Dataset to Workspace", type="primary", icon=":material/save:"):
            # The master_df should only contain rows that are NOT excluded
            st.session_state.master_df = raw_df.drop(index=list(prisma_state['exclusions'].keys())).reset_index(drop=True)
            st.success(f"Successfully committed {len(st.session_state.master_df)} articles to the main workspace!")
            
            # Update the thematic flow with the new master_df
            st.rerun()

    with tab_flowchart:
        st.markdown("### PRISMA 2020 Flow Diagram")
        
        # Calculate counts
        imported = st.session_state.get('prisma_imported_count', len(raw_df))
        duplicates = imported - len(raw_df)
        screened = len(raw_df)
        exclusions_list = list(prisma_state['exclusions'].values())
        total_excluded_chart = len(exclusions_list)
        included_chart = screened - total_excluded_chart

        # Group exclusions by reason
        reason_counts = {}
        for r in exclusions_list:
            reason_counts[r] = reason_counts.get(r, 0) + 1
        
        reasons_text = "\\n".join([f"- {r}: {c}" for r, c in reason_counts.items()]) if reason_counts else "None"

        # Allow user to override counts for final export
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

        # Graphviz DOT string adapted to Petersen et al. Systematic Mapping Studies
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

        st.download_button(
            "Download DOT format (Import to WebGraphviz/Visio)",
            data=dot_string,
            file_name="prisma_petersen_flowchart.dot",
            mime="text/plain"
        )
