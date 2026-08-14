import itertools
from collections import Counter
from pathlib import Path
import networkx as nx
import nltk
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from networkx.algorithms import community
from pyvis.network import Network
from networkx.exception import PowerIterationFailedConvergence
from utils.exports import safe_download

def format_ref_label(ref_raw: str, df: pd.DataFrame = None) -> str:
    """Converts cryptic reference strings (DOIs, OpenAlex IDs like 'W...') or long raw strings into human-readable citation labels."""
    if not ref_raw or pd.isna(ref_raw):
        return "Unknown Reference"
    ref_clean = str(ref_raw).strip()
    
    # 1. Look up in master dataset if DOI or OpenAlex ID matches a known record in memory
    if df is not None and not df.empty:
        # Check DOI match
        if 'DOI' in df.columns:
            clean_doi = ref_clean.replace("https://doi.org/", "").replace("doi:", "").lower()
            if clean_doi:
                doi_match = df[df['DOI'].astype(str).str.lower().str.contains(clean_doi, na=False, regex=False)]
                if not doi_match.empty:
                    row = doi_match.iloc[0]
                    author = str(row.get('Author', '')).split(',')[0]
                    year = str(row.get('Publication Year', ''))
                    title = str(row.get('Title', ''))[:35]
                    return f"{author} ({year}) - {title}..." if author and year else f"{title[:40]}..."
                
        # Check OpenAlex ID match
        if 'OpenAlex ID' in df.columns:
            clean_oa = ref_clean.replace("https://openalex.org/", "").upper()
            if clean_oa:
                oa_match = df[df['OpenAlex ID'].astype(str).str.upper() == clean_oa]
                if not oa_match.empty:
                    row = oa_match.iloc[0]
                    author = str(row.get('Author', '')).split(',')[0]
                    year = str(row.get('Publication Year', ''))
                    title = str(row.get('Title', ''))[:35]
                    return f"{author} ({year}) - {title}..." if author and year else f"{title[:40]}..."

    # 2. Handle OpenAlex IDs ('W...')
    if ref_clean.upper().startswith("W") and ref_clean[1:].isdigit():
        return f"OpenAlex Work ({ref_clean.upper()})"
        
    # 3. Handle DOIs
    if ref_clean.lower().startswith("10.") or "doi.org" in ref_clean.lower():
        doi_short = ref_clean.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")
        return f"DOI: {doi_short}"
        
    # 4. Truncate long raw textual citations
    if len(ref_clean) > 55:
        return f"{ref_clean[:52]}..."
        
    return ref_clean

def show(df: pd.DataFrame = None):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-diagram-3-fill' style='color: #697aa2;'></i> Science Mapping & Network Topology Dashboard</h2>", unsafe_allow_html=True)
    st.caption("Interactive Topological Analysis: Co-citation, Bibliographic Coupling, and Co-word Networks.")

    # Fetch from session state if df not directly passed
    if df is None:
        if 'master_df' not in st.session_state or st.session_state.master_df is None:
            st.warning("Please upload or process a dataset in the 'Data Prep & Upload' tab first.")
            return
        df = st.session_state.master_df.copy()
    else:
        df = df.copy()

    # Column safety check
    expected = {"Title", "Article References", "Keywords", "Abstract"}
    missing = expected - set(df.columns)
    if missing:
        st.error(f"Missing required columns for network mapping: {', '.join(missing)}")
        return

    # Mathematical formulation callout box
    with st.expander("Mathematical Foundation: Modularity & Community Detection", expanded=False):
        st.markdown(
            r"""
            Adjacency matrices are constructed using **NetworkX** and structured based on the **Louvain community detection algorithm**. 
            Modularity optimization measures the density of links inside communities as compared to links between communities:
            
            $$Q = \frac{1}{2m} \sum_{ij} \left[ A_{ij} - \frac{k_i k_j}{2m} \right] \delta(c_i, c_j)$$
            
            *Where $A_{ij}$ is the weight of the edge between nodes $i$ and $j$, $k_i$ is the sum of weights of edges attached to node $i$, $c_i$ is the community to which node $i$ is assigned, and $m = \frac{1}{2} \sum_{ij} A_{ij}$.*
            """
        )

    # Sub-tabs for Network Features
    net_tab1, net_tab2, net_tab3 = st.tabs([
        "Co-Citation Networks", 
        "Bibliographic Coupling", 
        "Co-Word Analysis"
    ])

    with net_tab1:
        display_reference_summary(df)
        st.divider()
        display_cocitation_analysis(df)

    with net_tab2:
        display_bibliographic_coupling_analysis(df)

    with net_tab3:
        display_coword_analysis(df)

def get_blue_color(value: float, max_value: float) -> str:
    norm = value / max_value if max_value else 0
    # Academic blue gradient: sky blue (147, 197, 253) to royal blue (37, 99, 235)
    r = int(147 - (147 - 37) * norm)
    g = int(197 - (197 - 99) * norm)
    b = int(253 - (253 - 235) * norm)
    return f"rgb({r},{g},{b})"

def clean_refs(refs) -> list:
    """Supports standard citations, DOIs, and OpenAlex IDs ('W...')"""
    try:
        if pd.isna(refs):
            return []
        refs_list = [r.strip() for r in str(refs).split(";") if r.strip()]
        valid = []
        for r in refs_list:
            if (
                (any(c.isalpha() for c in r) and " " in r) or 
                r.lower().startswith("10.") or 
                "doi.org" in r.lower() or
                r.upper().startswith("W") 
            ):
                valid.append(r)
        return valid
    except Exception as exc:
        st.warning(f"Could not process references: {exc}")
        return []

def display_reference_summary(df):
    if "Article References" not in df.columns:
        st.warning("Column 'Article References' is missing – skipping summary.")
        return
    st.subheader("Reference Summary")
    total_refs = sum(len(clean_refs(r)) for r in df["Article References"].dropna())
    articles_with_refs = df["Article References"].notna().sum()
    articles_missing_refs = df["Article References"].isna().sum()
    total_articles = len(df)

    cols = st.columns(4)
    cols[0].metric("Total References", total_refs)
    cols[1].metric("Articles with References", articles_with_refs)
    cols[2].metric("Articles without References", articles_missing_refs)
    cols[3].metric("% Articles without References", f"{articles_missing_refs/total_articles*100:.2f}%" if total_articles else "0%")

def display_cocitation_analysis(df):
    if df["Article References"].dropna().empty:
        st.info("No reference data – co-citation analysis skipped.")
        return
    pairs_df = co_citation_pairs_df(df)
    co_citation_counts = pairs_df.value_counts().reset_index(name="Count")
    if co_citation_counts.empty:
        st.info("Insufficient data to build co-citation pairs.")
        return

    st.subheader("Co-Citation Analysis")
    display_top_20_cocitation_pairs_table(co_citation_counts, df)
    G = co_citation_graph(co_citation_counts)
    if G.number_of_nodes() == 0:
        st.warning("The co-citation graph is empty.")
        return

    cluster_dict, metric_choice, theme_choice = cluster_and_metric_selection(G, "cocitation")
    html_graph = display_selected_cluster(
        select_cluster_option(cluster_dict, "cocitation"), 
        cluster_dict, 
        G, 
        metric_choice, 
        theme_choice,
        df
    )
    if html_graph:
        safe_download(st.download_button, "Download Co-citation Graph (HTML)", html_graph, "co_citation_graph.html", "text/html", key="cocitation_download", icon=":material/download:")

def co_citation_pairs_df(df):
    all_pairs = []
    for refs in df["Article References"].dropna():
        rlist = list(set(clean_refs(refs)))
        for combo in itertools.combinations(sorted(rlist), 2):
            all_pairs.append(combo)
    return pd.DataFrame(all_pairs, columns=["Ref1", "Ref2"])

def co_citation_graph(co_citation_counts):
    top_pairs = co_citation_counts.sort_values("Count", ascending=False).head(100)
    G = nx.Graph()
    for _, row in top_pairs.iterrows():
        G.add_edge(row["Ref1"], row["Ref2"], weight=row["Count"])
    return G

def display_top_20_cocitation_pairs_table(co_citation_counts, df=None):
    top20 = co_citation_counts.sort_values("Count", ascending=False).head(20).copy()
    st.markdown("**Top 20 Co-cited Reference Pairs**")
    
    top20["Reference 1"] = top20["Ref1"].apply(lambda r: format_ref_label(r, df))
    top20["Reference 2"] = top20["Ref2"].apply(lambda r: format_ref_label(r, df))
    top20["Co-Citation Frequency"] = top20["Count"]
    
    display_df = top20[["Reference 1", "Reference 2", "Co-Citation Frequency"]]
    st.dataframe(display_df, width="stretch", height=240, hide_index=True)
    safe_download(st.download_button, "Download Top 20 CSV", display_df.to_csv(index=False).encode("utf-8"), "top20_co_citation.csv", "text/csv", key="top20_co_citation")

def display_bibliographic_coupling_analysis(df):
    if df["Article References"].dropna().empty:
        st.info("No reference data – bibliographic coupling skipped.")
        return
    bc_pairs_df = bibliographic_coupling_pairs(df)
    if bc_pairs_df.empty:
        st.info("Insufficient overlap to build coupling networks.")
        return
    st.subheader("Bibliographic Coupling Analysis")
    display_top_20_bc_pairs_table(bc_pairs_df)

    G = bc_graph(bc_pairs_df)
    if G.number_of_nodes() == 0:
        st.warning("The coupling graph is empty.")
        return

    cluster_dict, metric_choice, theme_choice = cluster_and_metric_selection(G, "bc")
    html_graph = display_selected_cluster(
        select_cluster_option(cluster_dict, "bc"), 
        cluster_dict, 
        G, 
        metric_choice,
        theme_choice,
        df
    )
    if html_graph:
        safe_download(st.download_button, "Download Coupling Graph (HTML)", html_graph, "bibliographic_coupling_graph.html", "text/html", key="bc_download", icon=":material/download:")

def bibliographic_coupling_pairs(df):
    pairs_bc = []
    refs_list = df["Article References"].dropna().tolist()
    titles_list = df["Title"].fillna("Untitled").tolist()
    for idx1, refs1 in enumerate(refs_list):
        refs1_set = set(clean_refs(refs1))
        for idx2 in range(idx1 + 1, len(refs_list)):
            shared_refs = refs1_set & set(clean_refs(refs_list[idx2]))
            if shared_refs:
                pairs_bc.append({"Article1": titles_list[idx1], "Article2": titles_list[idx2], "Shared_Refs": len(shared_refs)})
                
    if not pairs_bc:
        return pd.DataFrame(columns=["Article1", "Article2", "Shared_Refs"])
        
    return pd.DataFrame(pairs_bc).sort_values("Shared_Refs", ascending=False)

def bc_graph(bc_df):
    top_bc = bc_df.head(100)
    G = nx.Graph()
    for _, row in top_bc.iterrows():
        G.add_edge(row["Article1"], row["Article2"], weight=row["Shared_Refs"])
    return G

def display_top_20_bc_pairs_table(bc_df):
    top20_bc = bc_df.head(20).copy()
    st.markdown("**Top 20 Coupling Article Pairs**")
    
    top20_bc["Article 1 Title"] = top20_bc["Article1"]
    top20_bc["Article 2 Title"] = top20_bc["Article2"]
    top20_bc["Shared References Overlap"] = top20_bc["Shared_Refs"]
    
    display_df = top20_bc[["Article 1 Title", "Article 2 Title", "Shared References Overlap"]]
    st.dataframe(display_df, width="stretch", height=240, hide_index=True)
    safe_download(st.download_button, "Download Top 20 CSV", display_df.to_csv(index=False).encode("utf-8"), "top20_bibliographic_coupling.csv", "text/csv", key="top20_bc")

def display_coword_analysis(df):
    st.subheader("Co-Word Analysis (Focus Word Network)")
    display_metrics_summary(df)
    
    col_w, col_f, col_n = st.columns([2, 3, 2])
    with col_w:
        focus_word = st.text_input("Focus Word", value="journal").lower()
    with col_f:
        fields = st.multiselect("Select fields to include", ["Title", "Keywords", "Abstract"], default=["Title", "Keywords", "Abstract"])
    with col_n:
        top_n = st.slider("Top N co-words", 5, 100, 20, step=5)

    if not focus_word:
        st.info("Enter a focus word to start the analysis.")
        return
    if not fields:
        st.warning("Select at least one field.")
        return
    display_coword_graph(focus_word, fields, df, top_n)

def display_metrics_summary(df):
    fields = ["Title", "Keywords", "Abstract"]
    summary = []
    total_articles = len(df)
    for fld in fields:
        present = df[fld].notna().sum() if fld in df.columns else 0
        missing = total_articles - present
        summary.append({"Field": fld, "Total Present": present, "Missing": missing, "% Missing": f"{missing/total_articles*100:.2f}%" if total_articles else "0%"})
    st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

def display_coword_graph(focus_word, fields, df, top_n):
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        with st.spinner("Downloading NLTK stopwords…"):
            try:
                nltk.download("stopwords")
            except Exception:
                pass
    try:
        from nltk.corpus import stopwords
        stop_words = set(stopwords.words("english"))
    except Exception:
        stop_words = {"the", "a", "an", "in", "on", "of", "for", "and", "or", "to", "with", "is", "by"}

    text_series = df[fields].fillna("").agg(" ".join, axis=1).str.lower()
    subset = text_series[text_series.str.contains(focus_word, regex=False)]
    if subset.empty:
        st.info(f"No occurrences of '{focus_word}' found in the selected fields.")
        return

    token_lists = [[w for w in txt.split() if w.isalpha() and w not in stop_words] for txt in subset]
    co_counter = Counter()
    for tokens in token_lists:
        co_counter.update(set(tokens) - {focus_word})
    if not co_counter:
        st.info("No co-words found with current parameters.")
        return

    top_words = dict(co_counter.most_common(top_n))
    G = nx.Graph()
    G.add_node(focus_word, size=30)
    for w, cnt in top_words.items():
        G.add_node(w, size=10 + cnt)
        G.add_edge(focus_word, w, weight=cnt)

    col_theme, _ = st.columns([1, 1])
    with col_theme:
        theme_choice = st.radio("Graph Theme:", ["Dark Mode", "Light Mode"], horizontal=True, key="coword_theme")

    bg_color = "#222222" if theme_choice == "Dark Mode" else "#F8F9FA"
    font_color = "#ffffff" if theme_choice == "🌙 Dark Mode" else "#222222"

    G_vis = Network(height="600px", width="100%", bgcolor=bg_color, font_color=font_color)
    for node in G.nodes():
        G_vis.add_node(node, label=node, title=node if node == focus_word else f"{node} ({co_counter[node]}×)", size=G.nodes[node]["size"])
    for u, v, data in G.edges(data=True):
        G_vis.add_edge(u, v, value=data["weight"])

    html_path = Path("co_word_graph.html")
    G_vis.save_graph(str(html_path))
    with html_path.open("r", encoding="utf-8") as f:
        html = f.read()

    components.html(html, height=600)
    safe_download(st.download_button, "Download Co-word Graph (HTML)", html, "co_word_graph.html", "text/html", key="coword_download", icon=":material/download:")

def cluster_and_metric_selection(G, key_prefix=""):
    col_a, col_m, col_t = st.columns([1, 1, 1])
    with col_a:
        algo = st.selectbox("Clustering Algorithm", ["Louvain", "Greedy", "Label Propagation"], key=f"{key_prefix}_algo")
    with col_m:
        metric_choice = st.selectbox("Centrality Metric", ["Degree", "Betweenness", "Eigenvector", "Closeness", "PageRank"], key=f"{key_prefix}_metric")
    with col_t:
        theme_choice = st.radio("Graph Theme:", ["Dark Mode", "Light Mode"], horizontal=True, key=f"{key_prefix}_theme")
        
    clusters = run_clustering(G, algo)
    cluster_dict = {i + 1: list(c) for i, c in enumerate(clusters)}
    return cluster_dict, metric_choice, theme_choice

def run_clustering(G, algo="Louvain"):
    if G.number_of_nodes() == 0:
        return []
    if algo == "Louvain":
        try:
            import community as community_louvain
            partition = community_louvain.best_partition(G)
            clusters = {}
            for node, cid in partition.items():
                clusters.setdefault(cid, []).append(node)
            return [set(c) for c in clusters.values()]
        except ImportError:
            st.info("Falling back to Greedy modularity clustering (python-louvain package recommended).")
            return community.greedy_modularity_communities(G)
    if algo == "Greedy":
        return community.greedy_modularity_communities(G)
    if algo == "Label Propagation":
        return community.asyn_lpa_communities(G)
    return community.greedy_modularity_communities(G)

def calculate_all_metrics(G):
    with st.spinner("Calculating centrality metrics…"):
        try:
            degree = dict(G.degree())
            betweenness = nx.betweenness_centrality(G, weight="weight", normalized=True)
            eigenvector = nx.eigenvector_centrality(G, weight="weight", max_iter=1000)
            closeness = nx.closeness_centrality(G)
            pagerank = nx.pagerank(G, weight="weight")
        except PowerIterationFailedConvergence:
            st.warning("Eigenvector calculation did not converge. Set to 0.")
            eigenvector = {n: 0 for n in G.nodes()}
            pagerank = nx.pagerank(G, weight="weight")
            degree = dict(G.degree())
            betweenness = nx.betweenness_centrality(G, weight="weight", normalized=True)
            closeness = nx.closeness_centrality(G)
    return {"Degree": degree, "Betweenness": betweenness, "Eigenvector": eigenvector, "Closeness": closeness, "PageRank": pagerank}

def select_cluster_option(cluster_dict, key_prefix=""):
    options = ["All"] + [f"Cluster {i}" for i in cluster_dict.keys()]
    return st.selectbox("Select Cluster Focus", options, key=f"{key_prefix}_cluster")

def display_selected_cluster(selected_cluster, cluster_dict, G, metric_choice="Degree", theme_choice="Dark Mode", df=None):
    metrics = calculate_all_metrics(G)
    values = metrics[metric_choice]
    
    bg_color = "#222222" if theme_choice == "Dark Mode" else "#F8F9FA"
    font_color = "#ffffff" if theme_choice == "Dark Mode" else "#222222"

    G_vis = Network(height="600px", width="100%", notebook=False, bgcolor=bg_color, font_color=font_color)
    nodes_to_show = G.nodes() if selected_cluster == "All" else cluster_dict[int(selected_cluster.split()[1])]
    max_value = max((values.get(n, 0) for n in nodes_to_show), default=1)
    legend_data = []

    for cluster_id, cluster_nodes in cluster_dict.items():
        if selected_cluster != "All" and cluster_id != int(selected_cluster.split()[1]):
            continue
        for idx, node in enumerate(sorted(cluster_nodes, key=lambda n: values.get(n, 0), reverse=True), 1):
            node_number = f"{cluster_id}-{idx}"
            readable_ref = format_ref_label(node, df)
            legend_data.append({"Node": node_number, "Reference / Paper": readable_ref, "Cluster": cluster_id, f"{metric_choice}": round(values.get(node, 0), 4)})
            val = values.get(node, 0)
            G_vis.add_node(
                node, 
                label=node_number, 
                title=f"{readable_ref}\n{metric_choice}: {val:.4f}", 
                size=15 + 40 * (val / max_value if max_value else 0), 
                color=get_blue_color(val, max_value), 
                group=cluster_id
            )

    for u, v, data in G.edges(data=True):
        if u in nodes_to_show and v in nodes_to_show:
            G_vis.add_edge(u, v, value=data["weight"])

    html_path = Path("cluster_graph.html")
    G_vis.save_graph(str(html_path))
    with html_path.open("r", encoding="utf-8") as f:
        html = f.read()

    components.html(html, height=600)
    display_cluster_table(legend_data)
    return html

def display_cluster_table(legend_data):
    st.markdown("**Legend: Node → Reference Mapping**")
    st.dataframe(pd.DataFrame(legend_data), width="stretch", height=240, hide_index=True)
