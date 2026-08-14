import streamlit as st
import pandas as pd
import numpy as np

def show(df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-bank' style='color: #697aa2;'></i> Editorial Governance & Endogeneity Indicators</h2>", unsafe_allow_html=True)
    
    # Display the mathematical foundation
    with st.expander("📐 Mathematical & Methodological Foundation"):
        st.markdown("""
        The ethical governance and sustainability of a scientific journal require constant analytical monitoring of its academic independence. As discussed by experts, the main risk factor for a journal's isolation or de-indexing is **Editorial Endogeneity**, characterized by a disproportionate concentration of publications originating from authors linked to the journal's own publisher institution.

        Strict guidelines established by indexers, such as *SciELO*, stipulate strict percentage limits for the acceptance of endogenous articles. To audit a journal's compliance with these rules, the **Institutional Endogeneity Index ($E_{inst}$)** is mathematically formalized as:
        
        $$ E_{inst} = \\frac{\\sum_{a=1}^{A} \\delta(I_a, I_{pub})}{A} $$
        
        where $A$ represents the total number of analyzed articles, $I_a$ denotes the set of affiliations of the co-authors of article $a$, and $I_{pub}$ is the reference publisher institution. 
        The indicator function $\\delta = 1$ if $I_a \\cap I_{pub} \\neq \\emptyset$ (an intersection exists), otherwise $0$.
        """)
    st.divider()

    if df is None or df.empty:
        st.warning("No data available.")
        return

    if 'Affiliations' not in df.columns:
        st.error("The dataset does not have an 'Affiliations' column. Please enrich the dataset or provide one with affiliations to use this module.")
        return

    # Total rows before filtering
    total_raw = len(df)
    
    # Check for missing affiliations
    df_missing = df[df['Affiliations'].isna() | (df['Affiliations'].astype(str).str.strip() == '') | (df['Affiliations'].astype(str).str.lower() == 'nan')]
    missing_count = len(df_missing)
    missing_pct = (missing_count / total_raw) * 100 if total_raw > 0 else 0
    
    # Show missing info as requested
    if missing_count > 0:
        st.info(f"**Data Quality Notice:** **{missing_count}** out of {total_raw} articles (**{missing_pct:.1f}%**) do not have affiliation data. These have been filtered out for the endogeneity analysis.")
    else:
        st.success(f"**Data Quality Notice:** All {total_raw} articles have affiliation data.")

    # Filter out missing affiliations
    df_valid = df.drop(df_missing.index).copy()
    total_analyzed = len(df_valid)

    if total_analyzed == 0:
        st.warning("No articles with affiliations available to analyze.")
        return

    st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B;'>Audit Configuration</h3>", unsafe_allow_html=True)
    
    # Extract unique affiliations for the dropdown
    all_affiliations = set()
    for aff_str in df_valid['Affiliations'].dropna():
        # Usually separated by semicolons or commas. Let's try semicolon first, fallback to comma if needed. 
        # But semicolon is standard in many bibliometric exports.
        for inst in str(aff_str).replace(',', ';').split(';'):
            cleaned = inst.strip()
            if cleaned:
                all_affiliations.add(cleaned)
    unique_affiliations = sorted(list(all_affiliations))
    
    col1, col2 = st.columns(2)
    with col1:
        selected_inst = st.selectbox("Select Publisher Institution ($I_{pub}$)", options=["-- Type Custom Institution --"] + unique_affiliations, help="Select the institution from the dataset, or choose to type a custom one.")
        if selected_inst == "-- Type Custom Institution --":
            publisher_inst = st.text_input("Custom Publisher Institution", placeholder="e.g. University of Sao Paulo")
        else:
            publisher_inst = selected_inst
            
    with col2:
        threshold_pct = st.slider("Regulatory Indexer Threshold (e.g., SciELO Limit) %", min_value=0, max_value=100, value=20, step=1, help="Maximum allowed percentage of endogenous articles for compliance.")

    if not publisher_inst:
        st.info("👆 Please provide the **Publisher Institution ($I_{pub}$)** above to calculate the Endogeneity Index.")
        return

    # Logic to compute E_inst
    pub_lower = publisher_inst.lower().strip()
    
    # Vectorized boolean cross logic
    df_valid['is_endogenous'] = df_valid['Affiliations'].astype(str).str.lower().apply(lambda x: pub_lower in x)
    
    endogenous_count = df_valid['is_endogenous'].sum()
    e_inst = (endogenous_count / total_analyzed) * 100

    st.divider()
    st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B;'>Audit Results</h3>", unsafe_allow_html=True)
    
    r_col1, r_col2, r_col3 = st.columns(3)
    r_col1.metric("Analyzed Articles ($A$)", f"{total_analyzed}")
    r_col2.metric("Endogenous Articles ($\\sum\\delta$)", f"{endogenous_count}")
    
    # Formatting metric color based on threshold
    delta_color = "normal" if e_inst <= threshold_pct else "inverse"
    r_col3.metric("Endogeneity Index ($E_{inst}$)", f"{e_inst:.1f}%", delta=f"{threshold_pct - e_inst:.1f}% limit margin", delta_color=delta_color)

    if e_inst > threshold_pct:
        st.error(f"🚨 **NON-COMPLIANCE ALERT:** The Endogeneity Index of **{e_inst:.1f}%** exceeds the stipulated regulatory threshold of **{threshold_pct}%**. The journal operates above the acceptable limit of institutional concentration, presenting a risk of de-indexing or academic isolation.")
    else:
        st.success(f"✅ **COMPLIANT:** The Endogeneity Index of **{e_inst:.1f}%** is within the stipulated regulatory threshold of **{threshold_pct}%**.")

    # Progress bar visualization (scaled to 1.0)
    st.progress(min(e_inst / 100.0, 1.0))
    
    # Data table of endogenous articles
    if endogenous_count > 0:
        st.markdown("<h4 style='font-size: 16px; font-weight: 700; color: #1E293B; margin-top: 20px;'>Identified Endogenous Articles</h4>", unsafe_allow_html=True)
        endogenous_df = df_valid[df_valid['is_endogenous']].drop(columns=['is_endogenous'])
        display_cols = [c for c in ['Title', 'Author', 'Publication Year', 'Affiliations', 'DOI'] if c in endogenous_df.columns]
        if not display_cols:
            display_cols = endogenous_df.columns
        st.dataframe(endogenous_df[display_cols], use_container_width=True)
