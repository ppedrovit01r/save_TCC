import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import re

# Comprehensive dictionary for country extraction
# Mapping both full names and common abbreviations to ISO standard names.
COUNTRY_MAPPING = {
    "usa": "United States", "u.s.a.": "United States", "u.s.a": "United States", 
    "united states": "United States", "united states of america": "United States", "us": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "united kingdom": "United Kingdom",
    "england": "United Kingdom", "scotland": "United Kingdom", "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "brazil": "Brazil", "brasil": "Brazil",
    "germany": "Germany", "deutschland": "Germany",
    "france": "France",
    "spain": "Spain", "espana": "Spain", "españa": "Spain",
    "italy": "Italy", "italia": "Italy",
    "china": "China", "prc": "China", "peoples republic of china": "China",
    "india": "India",
    "canada": "Canada",
    "australia": "Australia",
    "japan": "Japan", "nippon": "Japan",
    "south korea": "South Korea", "korea": "South Korea", "republic of korea": "South Korea",
    "russia": "Russia", "russian federation": "Russia",
    "netherlands": "Netherlands", "holland": "Netherlands", "the netherlands": "Netherlands",
    "sweden": "Sweden",
    "switzerland": "Switzerland", "suisse": "Switzerland",
    "portugal": "Portugal",
    "mexico": "Mexico",
    "argentina": "Argentina",
    "chile": "Chile",
    "colombia": "Colombia",
    "south africa": "South Africa",
    "new zealand": "New Zealand",
    "ireland": "Ireland",
    "denmark": "Denmark",
    "norway": "Norway",
    "finland": "Finland",
    "belgium": "Belgium",
    "austria": "Austria",
    "poland": "Poland",
    "greece": "Greece",
    "turkey": "Turkey", "turkiye": "Turkey",
    "iran": "Iran",
    "saudi arabia": "Saudi Arabia",
    "egypt": "Egypt",
    "israel": "Israel",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
    "indonesia": "Indonesia",
    "taiwan": "Taiwan",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh"
}

def extract_countries(affiliation_str):
    if pd.isna(affiliation_str) or not str(affiliation_str).strip():
        return []
    
    aff_lower = str(affiliation_str).lower()
    found_countries = set()
    
    # We use regex word boundaries to avoid matching "us" inside "australia", etc.
    for key, standardized_name in COUNTRY_MAPPING.items():
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, aff_lower):
            found_countries.add(standardized_name)
            
    return list(found_countries)

def show(df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-globe-americas' style='color: #697aa2;'></i> Global Demographics & Governance</h2>", unsafe_allow_html=True)
    
    if df is None or df.empty:
        st.warning("No data available.")
        return

    if 'Affiliations' not in df.columns:
        st.error("The dataset does not have an 'Affiliations' column required for demographic analysis.")
        return

    total_raw = len(df)
    
    # --- Data Cleaning and Extraction ---
    with st.spinner("Extracting geographic metadata from affiliations..."):
        df['Country_Extracted'] = df['Affiliations'].apply(extract_countries)
            
    # Calculate Data Quality Metrics
    df['Has_Country'] = df['Country_Extracted'].apply(lambda x: len(x) > 0)
    missing_count = total_raw - df['Has_Country'].sum()
    missing_pct = (missing_count / total_raw) * 100 if total_raw > 0 else 0

    if missing_count > 0:
        st.info(f"**Data Quality Notice:** **{missing_count}** out of {total_raw} articles (**{missing_pct:.1f}%**) do not have identifiable country data in their affiliations. They are excluded from spatial mapping.")
    else:
        st.success(f"**Data Quality Notice:** All {total_raw} articles have identifiable country data.")

    df_valid = df[df['Has_Country']].copy()
    
    # Create Tabs for the unified module
    tab_geo, tab_network, tab_endo = st.tabs(["Geographic Distribution", "Transnational Network", "Editorial Endogeneity"])
    
    with tab_geo:
        st.markdown("""
        **Spatial Autocorrelation & Capillarity**
        Visualizing the global reach of the publication using choropleth heat maps. This answers whether the journal is truly international or localized.
        """)
        
        if not df_valid.empty:
            # Flatten the list of countries to count occurrences
            all_countries = [country for sublist in df_valid['Country_Extracted'] for country in sublist]
            country_counts = pd.Series(all_countries).value_counts().reset_index()
            country_counts.columns = ['Country', 'Article Count']
            
            fig = px.choropleth(
                country_counts, 
                locations="Country", 
                locationmode="country names",
                color="Article Count", 
                hover_name="Country",
                color_continuous_scale=['#3a2c58', '#414184', '#395e9c', '#357ca3', '#3498a9', '#3eb4ad', '#62cfac'],
                title="Global Distribution of Publications"
            )
            fig.update_geos(showland=True, landcolor="#e2e8f0", showcountries=True, countrycolor="white")
            fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("View Raw Data"):
                st.dataframe(country_counts)
        else:
            st.warning("No geographic data available for mapping.")

    with tab_network:
        st.markdown("""
        **Transnational Co-authorship Graph $G = (V, E)$**
        The edge weight $w_{ij} = \\sum X_a(i, j)$ expresses the intensity of cooperation between country $i$ and country $j$.
        """)
        
        if not df_valid.empty:
            # Build edges
            edges = {}
            node_weights = {}
            for countries in df_valid['Country_Extracted']:
                countries = sorted(countries) # Sort to avoid (A,B) and (B,A) duplicates
                for c in countries:
                    node_weights[c] = node_weights.get(c, 0) + 1
                    
                if len(countries) > 1:
                    for i in range(len(countries)):
                        for j in range(i+1, len(countries)):
                            pair = (countries[i], countries[j])
                            edges[pair] = edges.get(pair, 0) + 1
            
            if not edges:
                st.info("No international co-authorships found in this dataset.")
            else:
                # Options for filtering
                st.markdown("<h4 style='font-size: 15px;'>Graph Filters</h4>", unsafe_allow_html=True)
                
                filter_option = st.radio("Display Mode:", ["Show Top N Nodes", "Show All Nodes"], horizontal=True)
                
                nodes_to_keep = set(node_weights.keys())
                
                if filter_option == "Show Top N Nodes":
                    top_n = st.slider("Select N:", min_value=2, max_value=len(node_weights), value=min(20, len(node_weights)))
                    # Sort nodes by weight descending
                    sorted_nodes = sorted(node_weights.items(), key=lambda x: x[1], reverse=True)
                    nodes_to_keep = {k for k, v in sorted_nodes[:top_n]}
                    
                # Filter edges based on nodes_to_keep
                filtered_edges = {pair: weight for pair, weight in edges.items() if pair[0] in nodes_to_keep and pair[1] in nodes_to_keep}
                
                # Build NetworkX graph
                G = nx.Graph()
                for (u, v), w in filtered_edges.items():
                    G.add_edge(u, v, weight=w)
                
                # Ensure all kept nodes are in graph even if no edges (isolated)
                for n in nodes_to_keep:
                    G.add_node(n, weight=node_weights.get(n, 1))
                
                if G.number_of_nodes() == 0:
                    st.warning("No data matches the selected filter.")
                else:
                    pos = nx.spring_layout(G, k=0.5, seed=42)
                    
                    edge_x = []
                    edge_y = []
                    for edge in G.edges():
                        x0, y0 = pos[edge[0]]
                        x1, y1 = pos[edge[1]]
                        edge_x.extend([x0, x1, None])
                        edge_y.extend([y0, y1, None])
                        
                    edge_trace = go.Scatter(
                        x=edge_x, y=edge_y,
                        line=dict(width=1, color='#888'),
                        hoverinfo='none',
                        mode='lines')
                        
                    node_x = []
                    node_y = []
                    node_text = []
                    node_size = []
                    
                    for node in G.nodes():
                        x, y = pos[node]
                        node_x.append(x)
                        node_y.append(y)
                        count = node_weights.get(node, 0)
                        node_text.append(f"{node} (Articles: {count})")
                        # Scale size non-linearly to avoid massive overlapping nodes
                        node_size.append(10 + (count ** 0.5) * 2)
                        
                    node_trace = go.Scatter(
                        x=node_x, y=node_y,
                        mode='markers+text',
                        hoverinfo='text',
                        text=[n for n in G.nodes()],
                        textposition="top center",
                        hovertext=node_text,
                        marker=dict(
                            showscale=False,
                            color='#697aa2',
                            size=node_size,
                            line_width=2))
                            
                    fig = go.Figure(data=[edge_trace, node_trace],
                                 layout=go.Layout(
                                    title=dict(text='Transnational Co-authorship Network', font=dict(size=16)),
                                    showlegend=False,
                                    hovermode='closest',
                                    margin=dict(b=20,l=5,r=5,t=40),
                                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                                    )
                    st.plotly_chart(fig, use_container_width=True)

    with tab_endo:
        st.markdown("""
        The ethical governance and sustainability of a scientific journal require constant analytical monitoring of its academic independence. As discussed by experts, the main risk factor for a journal's isolation or de-indexing is **Editorial Endogeneity**, characterized by a disproportionate concentration of publications originating from authors linked to the journal's own publisher institution.

        Strict guidelines established by indexers, such as *SciELO*, stipulate strict percentage limits for the acceptance of endogenous articles. To audit a journal's compliance with these rules, the **Institutional Endogeneity Index ($E_{inst}$)** is mathematically formalized as:
        
        $$ E_{inst} = \\frac{\\sum_{a=1}^{A} \\delta(I_a, I_{pub})}{A} $$
        """)
        st.divider()

        st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B;'>Audit Configuration</h3>", unsafe_allow_html=True)
        
        # Check for missing affiliations specifically for Endogeneity (uses raw strings)
        df_endo_missing = df[df['Affiliations'].isna() | (df['Affiliations'].astype(str).str.strip() == '') | (df['Affiliations'].astype(str).str.lower() == 'nan')]
        endo_missing_count = len(df_endo_missing)
        endo_missing_pct = (endo_missing_count / total_raw) * 100 if total_raw > 0 else 0
        
        if endo_missing_count > 0:
            st.info(f"**Data Quality Notice:** **{endo_missing_count}** out of {total_raw} articles (**{endo_missing_pct:.1f}%**) do not have affiliation data. These have been filtered out for the endogeneity analysis.")
        
        df_endo_valid = df.drop(df_endo_missing.index).copy()
        total_endo_analyzed = len(df_endo_valid)

        if total_endo_analyzed == 0:
            st.warning("No articles with affiliations available to analyze.")
        else:
            # Extract unique affiliations for the dropdown
            all_affiliations = set()
            for aff_str in df_endo_valid['Affiliations'].dropna():
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
            else:
                pub_lower = publisher_inst.lower().strip()
                df_endo_valid['is_endogenous'] = df_endo_valid['Affiliations'].astype(str).str.lower().apply(lambda x: pub_lower in x)
                
                endogenous_count = df_endo_valid['is_endogenous'].sum()
                e_inst = (endogenous_count / total_endo_analyzed) * 100

                st.divider()
                st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B;'>Audit Results</h3>", unsafe_allow_html=True)
                
                r_col1, r_col2, r_col3 = st.columns(3)
                r_col1.metric("Analyzed Articles ($A$)", f"{total_endo_analyzed}")
                r_col2.metric("Endogenous Articles ($\\sum\\delta$)", f"{endogenous_count}")
                
                delta_color = "normal" if e_inst <= threshold_pct else "inverse"
                r_col3.metric("Endogeneity Index ($E_{inst}$)", f"{e_inst:.1f}%", delta=f"{threshold_pct - e_inst:.1f}% limit margin", delta_color=delta_color)

                if e_inst > threshold_pct:
                    st.error(f"🚨 **NON-COMPLIANCE ALERT:** The Endogeneity Index of **{e_inst:.1f}%** exceeds the stipulated regulatory threshold of **{threshold_pct}%**. Risk of de-indexing.")
                else:
                    st.success(f"✅ **COMPLIANT:** The Endogeneity Index of **{e_inst:.1f}%** is within the stipulated regulatory threshold of **{threshold_pct}%**.")

                st.progress(min(e_inst / 100.0, 1.0))
                
                if endogenous_count > 0:
                    st.markdown("<h4 style='font-size: 16px; font-weight: 700; color: #1E293B; margin-top: 20px;'>Identified Endogenous Articles</h4>", unsafe_allow_html=True)
                    endogenous_df = df_endo_valid[df_endo_valid['is_endogenous']].drop(columns=['is_endogenous'])
                    display_cols = [c for c in ['Title', 'Author', 'Publication Year', 'Affiliations', 'DOI'] if c in endogenous_df.columns]
                    if not display_cols:
                        display_cols = endogenous_df.columns
                    st.dataframe(endogenous_df[display_cols], use_container_width=True)
