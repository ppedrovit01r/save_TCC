import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import re

# Comprehensive dictionary for country extraction
# Mapping full country names, variants, and common academic names to standard names.
COUNTRY_FULL_NAMES = {
    # Americas
    "usa": "United States", "u.s.a.": "United States", "u.s.a": "United States", 
    "united states": "United States", "united states of america": "United States",
    "brazil": "Brazil", "brasil": "Brazil",
    "canada": "Canada",
    "mexico": "Mexico", "méxico": "Mexico",
    "argentina": "Argentina",
    "chile": "Chile",
    "colombia": "Colombia",
    "peru": "Peru", "perú": "Peru",
    "uruguay": "Uruguay",
    "venezuela": "Venezuela",
    "cuba": "Cuba",
    "ecuador": "Ecuador",
    "costa rica": "Costa Rica",
    "panama": "Panama", "panamá": "Panama",
    
    # Europe
    "uk": "United Kingdom", "u.k.": "United Kingdom", "united kingdom": "United Kingdom",
    "england": "United Kingdom", "scotland": "United Kingdom", "wales": "United Kingdom", "northern ireland": "United Kingdom",
    "germany": "Germany", "deutschland": "Germany",
    "france": "France",
    "spain": "Spain", "espana": "Spain", "españa": "Spain",
    "italy": "Italy", "italia": "Italy",
    "portugal": "Portugal",
    "netherlands": "Netherlands", "holland": "Netherlands", "the netherlands": "Netherlands",
    "sweden": "Sweden",
    "switzerland": "Switzerland", "suisse": "Switzerland", "schweiz": "Switzerland",
    "norway": "Norway",
    "denmark": "Denmark",
    "finland": "Finland",
    "belgium": "Belgium",
    "austria": "Austria", "österreich": "Austria",
    "poland": "Poland", "polska": "Poland",
    "greece": "Greece",
    "ireland": "Ireland",
    "czech republic": "Czech Republic", "czechia": "Czech Republic",
    "hungary": "Hungary",
    "romania": "Romania",
    "croatia": "Croatia",
    "slovakia": "Slovakia",
    "slovenia": "Slovenia",
    "bulgaria": "Bulgaria",
    "serbia": "Serbia",
    "ukraine": "Ukraine",
    "russia": "Russia", "russian federation": "Russia",
    "turkey": "Turkey", "turkiye": "Turkey", "türkiye": "Turkey",
    "cyprus": "Cyprus",
    "estonia": "Estonia",
    "latvia": "Latvia",
    "lithuania": "Lithuania",
    "luxembourg": "Luxembourg",
    "iceland": "Iceland",

    # Asia & Middle East
    "china": "China", "prc": "China", "peoples republic of china": "China", "people's republic of china": "China",
    "india": "India",
    "japan": "Japan", "nippon": "Japan",
    "south korea": "South Korea", "korea": "South Korea", "republic of korea": "South Korea",
    "taiwan": "Taiwan",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
    "indonesia": "Indonesia",
    "philippines": "Philippines",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "sri lanka": "Sri Lanka",
    "iran": "Iran",
    "israel": "Israel",
    "saudi arabia": "Saudi Arabia",
    "united arab emirates": "United Arab Emirates", "uae": "United Arab Emirates", "u.a.e.": "United Arab Emirates",
    "qatar": "Qatar",
    "kuwait": "Kuwait",
    "jordan": "Jordan",
    "lebanon": "Lebanon",
    "kazakhstan": "Kazakhstan",

    # Oceania
    "australia": "Australia",
    "new zealand": "New Zealand",

    # Africa
    "south africa": "South Africa",
    "egypt": "Egypt",
    "nigeria": "Nigeria",
    "kenya": "Kenya",
    "morocco": "Morocco",
    "tunisia": "Tunisia",
    "algeria": "Algeria",
    "ghana": "Ghana",
    "ethiopia": "Ethiopia"
}

# Ambiguous 2-letter ISO codes that collide with common prepositions/words (e.g. 'de', 'in', 'it', 'no', 'es', 'at', 'is', 'be', 'to')
# are removed so prepositions in affiliations (e.g., 'Universidade de ...') are never falsely identified as countries.
ISO2_CODES = {
    "br": "Brazil", "bra": "Brazil",
    "usa": "United States",
    "gbr": "United Kingdom",
    "prt": "Portugal",
    "esp": "Spain",
    "fra": "France",
    "deu": "Germany",
    "ita": "Italy",
    "can": "Canada",
    "aus": "Australia",
    "chn": "China",
    "ind": "India",
    "jpn": "Japan",
    "kor": "South Korea",
    "nld": "Netherlands",
    "che": "Switzerland",
    "swe": "Sweden",
    "nor": "Norway",
    "dnk": "Denmark",
    "fin": "Finland",
    "pol": "Poland",
    "aut": "Austria",
    "bel": "Belgium",
    "rus": "Russia",
    "mex": "Mexico",
    "arg": "Argentina",
    "chl": "Chile",
    "col": "Colombia"
}

# Regional cities, states, and prominent universities heuristics to detect countries when country name is omitted
CITY_STATE_FALLBACKS = [
    # Prominent Global Universities & Institutions
    (r'\b(mit|harvard|stanford|ucla|uc berkeley|carnegie mellon|caltech|columbia university|yale|princeton)\b', 'United States'),
    (r'\b(oxford|cambridge|imperial college|ucl|edinburgh)\b', 'United Kingdom'),
    (r'\b(usp|unicamp|unesp|ufrj|ufmg|ufrgs|ufsc|ufpr|ufpe|unb|ufba|ufc|ufscar|unifesp|puc-sp|puc-rio|pucrs|puc-pr|pucpr|pontifícia universidade católica|pontificia universidade catolica|fiocruz|inpe|embrapa|universidade federal|instituto federal|universidade estadual|univ federal|unifesp|utfpr|ufop|ufpel|ufg|ufms|ufmt|ufrpe|ufpb|ufma|ufpa|ufam|ufrr|unifal|unifei|ufs|ufv|ufvjm|ufrn|uema|uece|uerj|uel|uem|uemg)\b', 'Brazil'),
    
    # United States States & Major Metros
    (r'\b(california|new york|texas|massachusetts|illinois|washington|florida|pennsylvania|ohio|michigan|georgia|north carolina|virginia|colorado|maryland|arizona)\b', 'United States'),
    (r'\b(boston|berkeley|chicago|seattle|austin|pittsburgh|baltimore|atlanta|los angeles|san francisco)\b', 'United States'),
    # Require 5-digit US zip code when matching two-letter state abbreviations so 'ca' (Canada) is never falsely matched as California
    (r',?\s*\b(ma|ca|ny|tx|wa|il|fl|pa|nc|va)\s+[0-9]{5}\b', 'United States'),
    
    # Brazil States & Major Metros
    (r'\b(são paulo|sao paulo|rio de janeiro|belo horizonte|porto alegre|curitiba|recife|salvador|brasília|brasilia|fortaleza|campinas|florianópolis|florianopolis|vitória|vitoria|natal|joão pessoa|joao pessoa|manaus|belém|belem|ouro preto|pelotas|jataí|jatai|viçosa|vicosa|uberlândia|uberlandia|juiz de fora|maringá|maringa|londrina|campina grande|santa maria|ribeirão preto|ribeirao preto|são carlos|sao carlos)\b', 'Brazil'),
    (r',?\s*\b(ce|rs|sp|rj|mg|pr|sc|ba|pe|df|go|pa|rn|pb|es|ma|al|pi|mt|ms|se|ro|to|ac|ap|rr)\b\s*(?:,\s*brasil|,\s*brazil|[0-9]{5}-?[0-9]{3}|$)', 'Brazil'),
    
    # Canada Institutions & Locations
    (r'\b(école de technologie supérieure|ecole de technologie superieure|ets montreal|quebec|québec|montreal|montréal|toronto|vancouver|ottawa|waterloo)\b', 'Canada'),

    # United Kingdom
    (r'\b(london|edinburgh|manchester|birmingham|bristol|glasgow|leeds|sheffield)\b', 'United Kingdom'),
    # Others
    (r'\b(paris|lyon|marseille|toulouse)\b', 'France'),
    (r'\b(berlin|munich|münchen|heidelberg|frankfurt|hamburg|stuttgart)\b', 'Germany'),
    (r'\b(madrid|barcelona|valencia|seville|granada)\b', 'Spain'),
    (r'\b(rome|milan|bologna|florence|turin|padua)\b', 'Italy'),
    (r'\b(lisboa|lisbon|porto|coimbra|braga)\b', 'Portugal'),
    (r'\b(sydney|melbourne|brisbane|canberra|adelaide|perth)\b', 'Australia'),
    (r'\b(beijing|shanghai|tsinghua|peking|shenzhen|hangzhou|wuhan)\b', 'China'),
    (r'\b(tokyo|kyoto|osaka|tohoku|nagoya)\b', 'Japan'),
    (r'\b(seoul|kaist|yonsei|korea university)\b', 'South Korea'),
    (r'\b(amsterdam|rotterdam|utrecht|leiden|delft|eindhoven)\b', 'Netherlands'),
    (r'\b(zurich|zürich|geneva|lausanne|basel|eth zurich|epfl)\b', 'Switzerland')
]

# Standard ISO-2 and ISO-3 codes for explicit country code parsing (like 'ES; MX; US' or 'BR; CA')
ALL_ISO_CODES = {
    "br": "Brazil", "bra": "Brazil",
    "us": "United States", "usa": "United States",
    "ca": "Canada", "can": "Canada",
    "es": "Spain", "esp": "Spain",
    "mx": "Mexico", "mex": "Mexico",
    "ec": "Ecuador", "ecu": "Ecuador",
    "ar": "Argentina", "arg": "Argentina",
    "cl": "Chile", "chl": "Chile",
    "co": "Colombia", "col": "Colombia",
    "pe": "Peru", "per": "Peru",
    "uy": "Uruguay", "ury": "Uruguay",
    "ve": "Venezuela", "ven": "Venezuela",
    "gb": "United Kingdom", "gbr": "United Kingdom", "uk": "United Kingdom",
    "pt": "Portugal", "prt": "Portugal",
    "fr": "France", "fra": "France",
    "de": "Germany", "deu": "Germany",
    "it": "Italy", "ita": "Italy",
    "au": "Australia", "aus": "Australia",
    "cn": "China", "chn": "China",
    "in": "India", "ind": "India",
    "jp": "Japan", "jpn": "Japan",
    "kr": "South Korea", "kor": "South Korea",
    "nl": "Netherlands", "nld": "Netherlands",
    "ch": "Switzerland", "che": "Switzerland",
    "se": "Sweden", "swe": "Sweden",
    "no": "Norway", "nor": "Norway",
    "dk": "Denmark", "dnk": "Denmark",
    "fi": "Finland", "fin": "Finland",
    "pl": "Poland", "pol": "Poland",
    "at": "Austria", "aut": "Austria",
    "be": "Belgium", "bel": "Belgium",
    "ru": "Russia", "rus": "Russia",
    "ie": "Ireland", "irl": "Ireland",
    "nz": "New Zealand", "nzl": "New Zealand",
    "sg": "Singapore", "sgp": "Singapore",
    "za": "South Africa", "zaf": "South Africa"
}

COUNTRY_MAPPING = COUNTRY_FULL_NAMES

def _extract_single_country(segment_str: str) -> set:
    """Extract countries from an individual affiliation or country token/chunk."""
    seg = segment_str.strip().lower()
    if not seg:
        return set()
        
    found = set()
    clean_exact = seg.strip(' ,;.-')
    
    # 1. Exact ISO code match for token (e.g. 'es', 'mx', 'us', 'br', 'ca')
    if clean_exact in ALL_ISO_CODES:
        return {ALL_ISO_CODES[clean_exact]}
        
    # 2. Check full country names
    for key, standardized_name in COUNTRY_FULL_NAMES.items():
        pattern = r'\b' + re.escape(key) + r'\b'
        if re.search(pattern, seg):
            found.add(standardized_name)
            
    # 3. Check city, state, and academic institution fallbacks
    if not found:
        for pat, cname in CITY_STATE_FALLBACKS:
            if re.search(pat, seg):
                found.add(cname)
                break
                
    # 4. Strict 2/3-letter ISO match delimited at boundaries
    if not found:
        for iso_code, cname in ISO2_CODES.items():
            pattern = r'(?:^|[\s,;.-])' + re.escape(iso_code) + r'(?:$|[\s,;.-])'
            if re.search(pattern, seg):
                found.add(cname)
                break
                
    return found

def extract_countries(affiliation_str):
    if pd.isna(affiliation_str) or not str(affiliation_str).strip():
        return []
    
    aff_str = str(affiliation_str).strip()
    
    # If multiple values are delimited by semicolon, split and evaluate each segment
    if ';' in aff_str:
        segments = [s.strip() for s in aff_str.split(';') if s.strip()]
        found_countries = set()
        for seg in segments:
            found_countries.update(_extract_single_country(seg))
        return sorted(list(found_countries))
    
    # Otherwise evaluate string
    return sorted(list(_extract_single_country(aff_str)))

def show(df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-globe-americas' style='color: #697aa2;'></i> Global Demographics & Governance</h2>", unsafe_allow_html=True)
    
    if df is None or df.empty:
        st.warning("No data available.")
        return

    # Check gating: User must run Gender Mapping inference first
    if 'gender_analysis_results' not in st.session_state:
        st.markdown("""
        <div style="background-color: #F8FAFC; border: 2px dashed #CBD5E1; border-radius: 12px; padding: 40px 24px; text-align: center; margin-top: 20px;">
            <div style="font-size: 48px; margin-bottom: 12px;">🔒</div>
            <h3 style="font-size: 20px; font-weight: 700; color: #334155; margin-bottom: 8px;">
                Demographic & Geographic Data Locked
            </h3>
            <p style="font-size: 14px; color: #64748B; max-width: 620px; margin: 0 auto 20px auto; line-height: 1.6;">
                Global spatial autocorrelation, international author dispersion, and demographic governance require prior author-level extraction and country inference. 
                Please run the <b>Gender Mapping</b> pipeline first to unlock this comprehensive spatial intelligence suite.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        c_gate_l, c_gate_m, c_gate_r = st.columns([1, 1.2, 1])
        with c_gate_m:
            if st.button("👉 Run Gender Mapping to Unlock", type="primary", width="stretch"):
                st.session_state.current_page = "Gender Mapping"
                st.rerun()
        return

    gender_res = st.session_state.gender_analysis_results
    authors_df = gender_res.get('authors_df', pd.DataFrame())

    if 'Affiliations' not in df.columns and ('country' not in authors_df.columns if not authors_df.empty else True):
        st.error("The dataset does not have an 'Affiliations' column or inferred author countries required for demographic analysis.")
        return

    total_raw = len(df)
    
    # --- Data Cleaning and Extraction ---
    with st.spinner("Extracting geographic metadata from affiliations and author addresses..."):
        def extract_all_countries(row):
            found = set()
            # Strictly use author-bound fields: Affiliations, Address, and Country.
            # Conference 'Location' is excluded to avoid mistaking the event hosting venue for the author's origin.
            for col in ['Affiliations', 'Address', 'Country']:
                if col in row and pd.notna(row[col]):
                    found.update(extract_countries(row[col]))
            return list(found)
        df['Country_Extracted'] = df.apply(extract_all_countries, axis=1)
            
    # Calculate Data Quality Metrics
    df['Has_Country'] = df['Country_Extracted'].apply(lambda x: len(x) > 0)
    missing_count = total_raw - df['Has_Country'].sum()
    missing_pct = (missing_count / total_raw) * 100 if total_raw > 0 else 0

    if missing_count > 0:
        st.info(f"**Data Quality Notice:** **{missing_count}** out of {total_raw} articles (**{missing_pct:.1f}%**) do not have identifiable country data in their affiliations. Unlocked author-level inferences are also available below.")
    else:
        st.success(f"**Data Quality Notice:** All {total_raw} articles have identifiable country data.")

    df_valid = df[df['Has_Country']].copy()
    
    # Create Tabs for the unified module
    tab_geo, tab_network, tab_endo, tab_audit = st.tabs([
        "Geographic Distribution & Gender", 
        "Transnational Network", 
        "Editorial Endogeneity",
        "Geographic Metadata Audit"
    ])
    
    with tab_geo:
        st.markdown("""
        **Spatial Autocorrelation & Capillarity**
        Visualizing the global reach of publications and gender distribution across countries using choropleth heat maps.
        """)
        
        # Gender & Author filter for Geographic Map
        geo_mode = st.radio(
            "Spatial Map View:",
            ["All Author Affiliations", "Female Authors by Country", "Male Authors by Country", "Article Origin Countries"],
            horizontal=True
        )

        if geo_mode in ["Female Authors by Country", "Male Authors by Country"]:
            target_g = "female" if "Female" in geo_mode else "male"
            color_theme = "Purples" if target_g == "female" else "Blues"
            filtered_authors = authors_df[authors_df['gender'] == target_g]
            c_counts = filtered_authors[filtered_authors['country'] != 'Unknown']['country'].value_counts().reset_index()
            c_counts.columns = ['Country', f'{target_g.title()} Authors']
            
            if not c_counts.empty:
                c_g1, c_g2 = st.columns([1.5, 1], gap="medium")
                with c_g1:
                    fig_map = px.choropleth(
                        c_counts,
                        locations='Country',
                        locationmode='country names',
                        color=f'{target_g.title()} Authors',
                        color_continuous_scale=color_theme,
                        projection='equal earth',
                        title=f"Global Distribution of {target_g.title()} Authors by Country (Equal Earth Projection)"
                    )
                    fig_map.update_geos(showland=True, landcolor="#e2e8f0", showcountries=True, countrycolor="white")
                    fig_map.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=420)
                    st.plotly_chart(fig_map, width='stretch')
                with c_g2:
                    st.markdown(f"<div style='font-weight:700; margin-bottom:8px;'>Top Countries by {target_g.title()} Authors</div>", unsafe_allow_html=True)
                    st.dataframe(c_counts, hide_index=True, height=380, width="stretch")
            else:
                st.info(f"No country metadata identified for {target_g} authors yet.")
        elif geo_mode == "All Author Affiliations":
            c_counts = authors_df[authors_df['country'] != 'Unknown']['country'].value_counts().reset_index()
            c_counts.columns = ['Country', 'Total Inferred Authors']
            if not c_counts.empty:
                fig = px.choropleth(
                    c_counts,
                    locations="Country",
                    locationmode="country names",
                    color="Total Inferred Authors",
                    hover_name="Country",
                    projection='equal earth',
                    color_continuous_scale=['#3a2c58', '#414184', '#395e9c', '#357ca3', '#3498a9', '#3eb4ad', '#62cfac'],
                    title="Global Distribution of All Authors (Inferred - Equal Earth Projection)"
                )
                fig.update_geos(showland=True, landcolor="#e2e8f0", showcountries=True, countrycolor="white")
                fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
                st.plotly_chart(fig, width='stretch')
                with st.expander("View Raw Country Data"):
                    st.dataframe(c_counts, hide_index=True)
            else:
                st.info("No inferred author country data available.")
        else:
            if not df_valid.empty:
                all_countries = [country for sublist in df_valid['Country_Extracted'] for country in sublist]
                country_counts = pd.Series(all_countries).value_counts().reset_index()
                country_counts.columns = ['Country', 'Article Count']
                
                fig = px.choropleth(
                    country_counts, 
                    locations="Country", 
                    locationmode="country names",
                    color="Article Count", 
                    hover_name="Country",
                    projection='equal earth',
                    color_continuous_scale=['#3a2c58', '#414184', '#395e9c', '#357ca3', '#3498a9', '#3eb4ad', '#62cfac'],
                    title="Global Distribution of Publications (Article Affiliations - Equal Earth Projection)"
                )
                fig.update_geos(showland=True, landcolor="#e2e8f0", showcountries=True, countrycolor="white")
                fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
                st.plotly_chart(fig, width='stretch')
                
                with st.expander("View Raw Data"):
                    st.dataframe(country_counts, hide_index=True)
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
                    st.plotly_chart(fig, width='stretch')

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
                
                import difflib
                unique_lower = {a.lower(): a for a in unique_affiliations}
                matches = set(difflib.get_close_matches(pub_lower, list(unique_lower.keys()), n=10, cutoff=0.5))
                for a in unique_affiliations:
                    if pub_lower in a.lower() or a.lower() in pub_lower:
                        matches.add(a.lower())
                
                if pub_lower in matches:
                    matches.remove(pub_lower)
                    
                suggested_cognates = sorted(list(set([unique_lower[m] for m in matches if m in unique_lower])))
                
                selected_cognates = st.multiselect(
                    "Select Institutional Cognates (Aliases)", 
                    options=[a for a in unique_affiliations if a.lower() != pub_lower],
                    default=suggested_cognates,
                    help="Select other names that represent the same institution to include them in the endogeneity calculation."
                )

                search_terms = [pub_lower] + [c.lower().strip() for c in selected_cognates]
                df_endo_valid['is_endogenous'] = df_endo_valid['Affiliations'].astype(str).str.lower().apply(
                    lambda x: any(term in x for term in search_terms)
                )
                
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
                    st.dataframe(endogenous_df[display_cols], width='stretch')

    with tab_audit:
        st.markdown("<h3 style='font-size: 19px; font-weight: 700; color: #1E293B;'>Geographic Metadata & Country Extraction Quality Audit</h3>", unsafe_allow_html=True)
        st.markdown("""
        Audit the completeness, consistency, and extraction provenance across verified author-bound geographical fields in your bibliographic corpus:
        **Affiliations**, **Address**, and **Country**.
        
        *(Note: The conference `Location` field is explicitly excluded from author origin deduction to maintain scientific integrity and prevent mistaking conference venues for author provenance).*
        """)
        
        # Build audit dataframe
        audit_cols = [c for c in ['Title', 'Author', 'Publication Year', 'Country_Extracted', 'Country', 'Address', 'Location', 'Affiliations'] if c in df.columns]
        
        # Compute quality statistics per column
        total_records = len(df)
        has_aff = df['Affiliations'].apply(lambda x: pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan').sum() if 'Affiliations' in df.columns else 0
        has_addr = df['Address'].apply(lambda x: pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan').sum() if 'Address' in df.columns else 0
        has_orig_country = df['Country'].apply(lambda x: pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan').sum() if 'Country' in df.columns else 0
        has_extracted = df['Has_Country'].sum()
        
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Records", total_records)
        m2.metric("Affiliations Present", f"{has_aff} ({(has_aff/total_records)*100:.1f}%)" if total_records else "0")
        m3.metric("Author Address Present", f"{has_addr} ({(has_addr/total_records)*100:.1f}%)" if total_records else "0")
        m4.metric("Explicit Country Present", f"{has_orig_country} ({(has_orig_country/total_records)*100:.1f}%)" if total_records else "0")
        m5.metric("Author Country Identified", f"{has_extracted} ({(has_extracted/total_records)*100:.1f}%)" if total_records else "0", delta=f"{has_extracted - has_orig_country} deduced" if has_extracted >= has_orig_country else None)
        
        st.divider()
        
        # Filter options for the audit table
        filter_col1, filter_col2 = st.columns([1.5, 2])
        with filter_col1:
            audit_filter = st.radio(
                "Filter Audit Records:",
                ["All Records", "Successfully Extracted", "Missing Country Info"],
                horizontal=True
            )
        with filter_col2:
            search_query = st.text_input("Search in Geographic Fields or Title", placeholder="e.g. Brazil, USP, University, etc.")
            
        display_audit_df = df[audit_cols].copy()
        display_audit_df['Identified_Countries'] = display_audit_df['Country_Extracted'].apply(lambda lst: ", ".join(lst) if lst else "❌ None")
        display_audit_df['Status'] = display_audit_df['Country_Extracted'].apply(lambda lst: "✅ Identified" if lst else "⚠️ Missing")
        
        # Reorder columns for optimal inspection
        preferred_order = ['Status', 'Identified_Countries', 'Title', 'Affiliations', 'Address', 'Country', 'Location', 'Author', 'Publication Year']
        final_cols = [c for c in preferred_order if c in display_audit_df.columns]
        display_audit_df = display_audit_df[final_cols]
        
        if audit_filter == "Successfully Extracted":
            display_audit_df = display_audit_df[display_audit_df['Status'] == "✅ Identified"]
        elif audit_filter == "Missing Country Info":
            display_audit_df = display_audit_df[display_audit_df['Status'] == "⚠️ Missing"]
            
        if search_query.strip():
            sq = search_query.strip().lower()
            mask = display_audit_df.astype(str).apply(lambda row: row.str.lower().str.contains(sq, regex=False)).any(axis=1)
            display_audit_df = display_audit_df[mask]
            
        st.dataframe(
            display_audit_df,
            width='stretch',
            height=420,
            column_config={
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Identified_Countries": st.column_config.TextColumn("Author Country (Extracted)", width="medium"),
                "Title": st.column_config.TextColumn("Title", width="large"),
                "Affiliations": st.column_config.TextColumn("Author Affiliations", width="large"),
                "Address": st.column_config.TextColumn("Author Address", width="medium"),
                "Country": st.column_config.TextColumn("Explicit Country Column", width="small"),
                "Location": st.column_config.TextColumn("Conference Location (Excluded from Deduction)", width="medium")
            }
        )
        
        # Download audit log as CSV
        from utils.project_manager import format_timestamped_filename, save_project_file
        csv_data = display_audit_df.to_csv(index=False).encode('utf-8')
        fn_demo_log = format_timestamped_filename("geographic_metadata_audit_log.csv")
        try: save_project_file("exports", fn_demo_log, csv_data, mode="wb")
        except Exception: pass

        st.download_button(
            label="📥 Export Geographic Metadata Audit Log (CSV)",
            data=csv_data,
            file_name=fn_demo_log,
            mime="text/csv"
        )
