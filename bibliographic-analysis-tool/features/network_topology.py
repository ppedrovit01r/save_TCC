import itertools
import json
import requests
from typing import Any, Union, List, Optional, Dict
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

OA_CACHE_FILE = Path("utils/cache/openalex_works_cache.json")

def _load_oa_works_cache() -> dict:
    if "oa_works_cache" in st.session_state and isinstance(st.session_state.oa_works_cache, dict):
        return st.session_state.oa_works_cache
    cache = {}
    if OA_CACHE_FILE.exists():
        try:
            with open(OA_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    st.session_state.oa_works_cache = cache
    return cache

def _save_oa_works_cache(cache: dict):
    st.session_state.oa_works_cache = cache
    try:
        OA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OA_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def extract_surname(name: str) -> str:
    name = str(name).strip()
    if not name:
        return ""
    if "," in name:
        return name.split(",")[0].strip()
    parts = name.split()
    return parts[-1].strip() if parts else name

def format_citation_label(authors: Any, year: Any, title: str) -> str:
    """
    Bibliographic rule:
    - 1 author: Last Name (year) - Title
    - 2 authors: Last Name 1 & Last Name 2 (year) - Title
    - >2 authors: Last Name 1, et al., (year) - Title
    """
    year_str = str(year).strip() if (year and pd.notna(year) and str(year).strip().lower() not in ["nan", "none", ""]) else ""
    title_str = str(title).strip() if (title and pd.notna(title) and str(title).strip().lower() not in ["nan", "none", ""]) else "Untitled"
    if len(title_str) > 52:
        title_str = f"{title_str[:49]}..."

    if isinstance(authors, str):
        if ";" in authors:
            auth_list = [a.strip() for a in authors.split(";") if a.strip()]
        elif "," in authors and not any(part.strip().endswith(".") for part in authors.split(",")):
            auth_list = [a.strip() for a in authors.split(",") if a.strip()]
        else:
            auth_list = [authors.strip()]
    elif isinstance(authors, list):
        auth_list = [str(a).strip() for a in authors if a and str(a).strip()]
    else:
        auth_list = []

    surnames = [extract_surname(a) for a in auth_list if extract_surname(a)]
    
    if len(surnames) == 0:
        author_prefix = ""
    elif len(surnames) == 1:
        author_prefix = f"{surnames[0]} "
    elif len(surnames) == 2:
        author_prefix = f"{surnames[0]} & {surnames[1]} "
    else:
        author_prefix = f"{surnames[0]}, et al., "

    if author_prefix and year_str:
        return f"{author_prefix}({year_str}) - {title_str}"
    elif author_prefix:
        return f"{author_prefix}- {title_str}"
    elif year_str:
        return f"({year_str}) - {title_str}"
    else:
        return title_str

def batch_resolve_openalex_ids(ids: list) -> dict:
    """Batch-resolves OpenAlex work IDs (e.g. W123456789) to authors, year, and title."""
    cache = _load_oa_works_cache()
    to_fetch = set()
    for raw_id in ids:
        if not raw_id or pd.isna(raw_id):
            continue
        clean = str(raw_id).strip().replace("https://openalex.org/", "").upper()
        if clean.startswith("W") and clean[1:].isdigit():
            # If not in cache or cached without title/authors
            if clean not in cache or not cache[clean].get("title"):
                to_fetch.add(clean)

    if to_fetch:
        fetch_list = list(to_fetch)
        chunk_size = 25
        updated = False
        headers = {"User-Agent": "mailto:pedro.alexandre@inf.ufrgs.br"}
        for i in range(0, len(fetch_list), chunk_size):
            chunk = fetch_list[i : i + chunk_size]
            filter_str = "|".join(chunk)
            url = f"https://api.openalex.org/works?filter=openalex:{filter_str}&per-page=50&select=id,title,publication_year,authorships"
            try:
                resp = requests.get(url, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    found_ids = set()
                    for item in results:
                        oa_id = str(item.get("id", "")).replace("https://openalex.org/", "").upper()
                        title = item.get("title") or ""
                        year = item.get("publication_year") or ""
                        authors = []
                        for auth in item.get("authorships", []):
                            dn = auth.get("author", {}).get("display_name", "")
                            if dn:
                                authors.append(dn.strip())
                        cache[oa_id] = {
                            "title": title,
                            "year": year,
                            "authors": authors,
                            "author": authors[0] if authors else ""
                        }
                        found_ids.add(oa_id)
                        updated = True
                    for cid in chunk:
                        if cid not in found_ids and cid not in cache:
                            cache[cid] = {"title": "", "year": "", "authors": [], "author": ""}
                            updated = True
            except Exception:
                pass
        if updated:
            _save_oa_works_cache(cache)
    return cache

def format_ref_label(ref_raw: str, df: pd.DataFrame = None, cache: dict = None) -> str:
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
                    return format_citation_label(row.get('Author', ''), row.get('Publication Year', ''), row.get('Title', ''))
                
        # Check OpenAlex ID match
        if 'OpenAlex ID' in df.columns:
            clean_oa = ref_clean.replace("https://openalex.org/", "").upper()
            if clean_oa:
                oa_match = df[df['OpenAlex ID'].astype(str).str.upper() == clean_oa]
                if not oa_match.empty:
                    row = oa_match.iloc[0]
                    return format_citation_label(row.get('Author', ''), row.get('Publication Year', ''), row.get('Title', ''))

    # 2. Check OpenAlex ID resolution via cache or query
    clean_oa = ref_clean.replace("https://openalex.org/", "").upper()
    if clean_oa.startswith("W") and clean_oa[1:].isdigit():
        if cache is None:
            cache = _load_oa_works_cache()
        if clean_oa in cache and cache[clean_oa].get("title"):
            meta = cache[clean_oa]
            authors = meta.get("authors") or ([meta.get("author")] if meta.get("author") else [])
            year = meta.get("year", "")
            title = meta.get("title", "")
            return format_citation_label(authors, year, title)
            
        # Fallback single fetch if missed by batch query
        try:
            headers = {"User-Agent": "mailto:pedro.alexandre@inf.ufrgs.br"}
            single_url = f"https://api.openalex.org/works/{clean_oa}?select=id,title,publication_year,authorships"
            resp = requests.get(single_url, headers=headers, timeout=3.0)
            if resp.status_code == 200:
                item = resp.json()
                title = item.get("title") or ""
                year = item.get("publication_year") or ""
                authors = [a.get("author", {}).get("display_name", "").strip() for a in item.get("authorships", []) if a.get("author", {}).get("display_name")]
                cache[clean_oa] = {"title": title, "year": year, "authors": authors, "author": authors[0] if authors else ""}
                _save_oa_works_cache(cache)
                return format_citation_label(authors, year, title)
        except Exception:
            pass

        return f"OpenAlex Work ({clean_oa})"
        
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

CLUSTER_PALETTE = [
    "#2563EB", # Cobalt Royal Blue
    "#D92D20", # Crimson Red
    "#059669", # Emerald Green
    "#D97706", # Amber / Warm Gold
    "#7C3AED", # Deep Violet
    "#0284C7", # Cerulean Sky Blue
    "#EA580C", # Vivid Tangerine
    "#4F46E5", # Indigo
    "#C026D3", # Fuchsia / Magenta
    "#0D9488", # Teal
    "#15803D", # Forest Green
    "#9333EA", # Bright Purple
]

def get_blue_color(value: float, max_value: float) -> str:
    norm = value / max_value if max_value else 0
    # High-contrast blue gradient: Sky Blue (70, 130, 240) to Deep Midnight Navy (15, 23, 42)
    r = int(70 - (70 - 15) * norm)
    g = int(130 - (130 - 23) * norm)
    b = int(240 - (240 - 42) * norm)
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
        df,
        key_prefix="cocitation"
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
    
    # Pre-resolve OpenAlex IDs for top 20 references so researchers see author, year & title
    all_refs = list(top20["Ref1"].unique()) + list(top20["Ref2"].unique())
    oa_cache = batch_resolve_openalex_ids(all_refs)

    top20["Reference 1"] = top20["Ref1"].apply(lambda r: format_ref_label(r, df, oa_cache))
    top20["Reference 2"] = top20["Ref2"].apply(lambda r: format_ref_label(r, df, oa_cache))
    top20["Co-Citation Frequency"] = top20["Count"]
    
    display_df = top20[["Reference 1", "Reference 2", "Co-Citation Frequency"]]
    
    col1, col2 = st.columns([0.7, 0.3], vertical_alignment="center")
    with col1:
        st.markdown("<h4 style='margin: 0; font-size: 16px; font-weight: 600;'>Top 20 Co-cited Reference Pairs</h4>", unsafe_allow_html=True)
    with col2:
        safe_download(st.download_button, "Download Top 20 CSV", display_df.to_csv(index=False).encode("utf-8-sig"), "top20_co_citation.csv", "text/csv", key="top20_co_citation")

    st.dataframe(display_df, width="stretch", height=240, hide_index=True)

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
        df,
        key_prefix="bc"
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
    top20_bc["Article 1 Title"] = top20_bc["Article1"]
    top20_bc["Article 2 Title"] = top20_bc["Article2"]
    top20_bc["Shared References Overlap"] = top20_bc["Shared_Refs"]
    
    display_df = top20_bc[["Article 1 Title", "Article 2 Title", "Shared References Overlap"]]
    
    col1, col2 = st.columns([0.7, 0.3], vertical_alignment="center")
    with col1:
        st.markdown("<h4 style='margin: 0; font-size: 16px; font-weight: 600;'>Top 20 Coupling Article Pairs</h4>", unsafe_allow_html=True)
    with col2:
        safe_download(st.download_button, "Download Top 20 CSV", display_df.to_csv(index=False).encode("utf-8-sig"), "top20_bibliographic_coupling.csv", "text/csv", key="top20_bc")

    st.dataframe(display_df, width="stretch", height=240, hide_index=True)

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
    sum_df = pd.DataFrame(summary)
    
    col1, col2 = st.columns([0.7, 0.3], vertical_alignment="center")
    with col1:
        st.markdown("<h4 style='margin: 0; font-size: 16px; font-weight: 600;'>Corpus Text Completeness</h4>", unsafe_allow_html=True)
    with col2:
        safe_download(st.download_button, "Download Summary CSV", sum_df.to_csv(index=False).encode("utf-8-sig"), "coword_corpus_summary.csv", "text/csv", key="coword_summary_csv")

    st.dataframe(sum_df, width="stretch", hide_index=True)

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
        theme_choice = st.radio("Graph Theme:", ["Light Mode", "Dark Mode"], index=0, horizontal=True, key="coword_theme")

    bg_color = "#F3F4F6" if theme_choice == "Light Mode" else "#181E29"
    font_color = "#0F172A" if theme_choice == "Light Mode" else "#F8FAFC"
    stroke_color = "#F3F4F6" if theme_choice == "Light Mode" else "#181E29"
    edge_color = "rgba(71, 85, 105, 0.45)" if theme_choice == "Light Mode" else "rgba(203, 213, 225, 0.45)"

    G_vis = Network(height="600px", width="100%", bgcolor=bg_color, font_color=font_color)
    for node in G.nodes():
        node_bg = "#1D4ED8" if node == focus_word else "#0284C7"
        node_border = "#0F172A" if theme_choice == "Light Mode" else "#FFFFFF"
        G_vis.add_node(
            node, 
            label=node, 
            title=node if node == focus_word else f"{node} ({co_counter[node]}×)", 
            size=G.nodes[node]["size"],
            color={
                "background": node_bg,
                "border": node_border,
                "highlight": {"background": "#F59E0B", "border": "#D97706"}
            },
            borderWidth=2,
            borderWidthSelected=3,
            font={"color": font_color, "size": 13, "strokeWidth": 3, "strokeColor": stroke_color}
        )
    for u, v, data in G.edges(data=True):
        G_vis.add_edge(u, v, value=data["weight"], color=edge_color)

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
        theme_choice = st.radio("Graph Theme:", ["Light Mode", "Dark Mode"], index=0, horizontal=True, key=f"{key_prefix}_theme")
        
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

def display_selected_cluster(selected_cluster, cluster_dict, G, metric_choice="Degree", theme_choice="Light Mode", df=None, key_prefix: str = ""):
    metrics = calculate_all_metrics(G)
    values = metrics[metric_choice]
    
    bg_color = "#F3F4F6" if theme_choice == "Light Mode" else "#181E29"
    font_color = "#0F172A" if theme_choice == "Light Mode" else "#F8FAFC"
    stroke_color = "#F3F4F6" if theme_choice == "Light Mode" else "#181E29"
    edge_color = "rgba(71, 85, 105, 0.45)" if theme_choice == "Light Mode" else "rgba(203, 213, 225, 0.45)"

    G_vis = Network(height="600px", width="100%", notebook=False, bgcolor=bg_color, font_color=font_color)
    nodes_to_show = G.nodes() if selected_cluster == "All" else cluster_dict[int(selected_cluster.split()[1])]
    
    # Pre-resolve OpenAlex IDs for all displayed nodes
    oa_cache = batch_resolve_openalex_ids(list(nodes_to_show))
    
    max_value = max((values.get(n, 0) for n in nodes_to_show), default=1)
    legend_data = []

    for cluster_id, cluster_nodes in cluster_dict.items():
        if selected_cluster != "All" and cluster_id != int(selected_cluster.split()[1]):
            continue
        cluster_color = CLUSTER_PALETTE[(cluster_id - 1) % len(CLUSTER_PALETTE)]
        border_color = "#0F172A" if theme_choice == "Light Mode" else "#FFFFFF"
        node_color_dict = {
            "background": cluster_color,
            "border": border_color,
            "highlight": {"background": "#F59E0B", "border": "#D97706"}
        }
        for idx, node in enumerate(sorted(cluster_nodes, key=lambda n: values.get(n, 0), reverse=True), 1):
            node_number = f"{cluster_id}-{idx}"
            readable_ref = format_ref_label(node, df, oa_cache)
            legend_data.append({"Node": node_number, "Reference / Paper": readable_ref, "Cluster": cluster_id, f"{metric_choice}": round(values.get(node, 0), 4)})
            val = values.get(node, 0)
            G_vis.add_node(
                node, 
                label=node_number, 
                title=f"{readable_ref}\n{metric_choice}: {val:.4f}\nCluster: {cluster_id}", 
                size=16 + 40 * (val / max_value if max_value else 0), 
                color=node_color_dict, 
                borderWidth=2,
                borderWidthSelected=3,
                font={"color": font_color, "size": 13, "strokeWidth": 3, "strokeColor": stroke_color},
                group=cluster_id
            )

    for u, v, data in G.edges(data=True):
        if u in nodes_to_show and v in nodes_to_show:
            G_vis.add_edge(u, v, value=data["weight"], color=edge_color)

    html_file = f"{key_prefix}_cluster_graph.html" if key_prefix else "cluster_graph.html"
    html_path = Path(html_file)
    G_vis.save_graph(str(html_path))
    with html_path.open("r", encoding="utf-8") as f:
        html = f.read()

    components.html(html, height=600)
    display_cluster_table(legend_data, key_prefix=key_prefix)
    return html

def display_cluster_table(legend_data, key_prefix: str = ""):
    df_legend = pd.DataFrame(legend_data)
    col1, col2 = st.columns([0.7, 0.3], vertical_alignment="center")
    with col1:
        st.markdown("<h4 style='margin: 0; font-size: 16px; font-weight: 600;'>Legend: Node → Reference Mapping</h4>", unsafe_allow_html=True)
    with col2:
        if not df_legend.empty:
            btn_key = f"{key_prefix}_cluster_legend_csv" if key_prefix else "cluster_legend_csv"
            fn = f"{key_prefix}_cluster_legend.csv" if key_prefix else "cluster_legend.csv"
            safe_download(st.download_button, "Download Legend CSV", df_legend.to_csv(index=False).encode("utf-8-sig"), fn, "text/csv", key=btn_key)

    st.dataframe(df_legend, width="stretch", height=240, hide_index=True)
