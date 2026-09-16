import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import NMF
import nltk
from nltk.corpus import stopwords
import string

def preprocess_text(texts):
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)
        
    stop_words = set(stopwords.words("english")).union(set(stopwords.words("portuguese")))
    custom_stopwords = {"sobre", "estudo", "uso", "artigo", "paper", "study", "using", "results", "analysis"}
    stop_words = stop_words.union(custom_stopwords)
    
    processed = []
    for text in texts:
        if pd.isna(text):
            processed.append("")
            continue
        text = str(text).lower().translate(str.maketrans('', '', string.punctuation))
        tokens = [w for w in text.split() if w.isalpha() and w not in stop_words and len(w) > 2]
        processed.append(" ".join(tokens))
    return processed

def run_nmf(docs, n_topics=5, n_top_words=15):
    # Ensure min_df is not larger than the number of documents
    min_df = 2 if len(docs) > 2 else 1
    max_df = 0.95 if len(docs) > 5 else 1.0
    vectorizer = TfidfVectorizer(max_df=max_df, min_df=min_df)
    tfidf = vectorizer.fit_transform(docs)
    
    nmf = NMF(n_components=n_topics, random_state=42, init='nndsvda', max_iter=200)
    nmf.fit(tfidf)
    
    feature_names = vectorizer.get_feature_names_out()
    
    topics_words = []
    for topic_idx, topic in enumerate(nmf.components_):
        top_features_ind = topic.argsort()[:-n_top_words - 1:-1]
        top_features = [feature_names[i] for i in top_features_ind]
        topics_words.append(top_features)
        
    # Get document assignments and volumes
    doc_topic_matrix = nmf.transform(tfidf)
    doc_assignments = doc_topic_matrix.argmax(axis=1)
    
    topic_volumes = [0] * n_topics
    for t in doc_assignments:
        topic_volumes[t] += 1
        
    return topics_words, topic_volumes

def calculate_jaccard(list1, list2):
    set1, set2 = set(list1), set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0

from lib.topic_modeling.genai import generate_batch_topic_names
from utils.exports import _download_button
from utils.project_manager import format_timestamped_filename, save_project_file

def show(df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-bezier2' style='color: #697aa2;'></i> Thematic Flow (Trend Spotting)</h2>", unsafe_allow_html=True)
    st.markdown("Map how topics are born, merge, split, or decline across specific time eras using a Sankey diagram.")

    # Display the mathematical foundation
    with st.expander("📐 Mathematical & Methodological Foundation"):
        st.markdown("""
        **Thematic Evolution (Sankey Diagram)**
        This module tracks the evolution of topics across temporal eras by performing independent clustering on temporal slices of the corpus.
        
        *   **Time Slicing & Clustering**: The corpus is divided into sequential periods based on user-defined cutoff years. Within each period, **Non-Negative Matrix Factorization (NMF)** is applied to the TF-IDF representation of the documents to extract a fixed number of topics. NMF is highly efficient and naturally extracts parts-based semantic representations.
        *   **Evolution Tracking (Links)**: To map how topics split, merge, or continue, we calculate the **Jaccard Similarity** between the top 15 keywords of every topic in Era $T$ and Era $T+1$.
        $$ J(A, B) = \\frac{|A \\cap B|}{|A \\cup B|} $$
        If the similarity exceeds the user-defined threshold, a directed link is drawn. The thickness of the link is proportional to the similarity multiplied by the document volume of the source topic.
        *   **Interpretation**: 
            *   **Merges**: Multiple topics in Era $T$ linking to a single topic in Era $T+1$.
            *   **Splits**: A single topic in Era $T$ linking to multiple topics in Era $T+1$.
            *   **Declines**: A topic in Era $T$ with no links to Era $T+1$ (dies out).
        """)

    if df is None or df.empty:
        st.warning("Please load data in the Core Data Prep hub first.")
        return
        
    if "Publication Year" not in df.columns:
        st.error("Missing 'Publication Year' column required for temporal analysis.")
        return

    # --- Flow Resume / Upload Section ---
    with st.expander("📂 Resume Work: Upload Saved Flow Project (.json)", expanded=False):
        uploaded_flow_file = st.file_uploader(
            "Upload a previously exported Flow Project JSON file", 
            type=["json"], 
            key="upload_thematic_flow_json",
            help="Restores eras, topics, keywords, connection links, and GenAI labels without needing to re-run clustering."
        )
        if uploaded_flow_file is not None:
            try:
                flow_payload = json.loads(uploaded_flow_file.read().decode("utf-8"))
                required_keys = ['nodes', 'links_source', 'links_target', 'links_value', 'links_color', 'links_records']
                if all(k in flow_payload for k in required_keys):
                    st.session_state.thematic_flow_data = flow_payload
                    st.success(f"Successfully restored flow project with {len(flow_payload['nodes'])} topics across {len(set(n['era_name'] for n in flow_payload['nodes']))} eras!")
                    st.rerun()
                else:
                    st.error("Invalid Flow Project JSON: missing required node/link structures.")
            except Exception as e:
                st.error(f"Error parsing Flow Project file: {e}")
        
    df = df.copy()
    # Extract 4-digit year starting with 18, 19, or 20 from strings like "20260721" or "2026-07-21"
    df["Publication Year"] = df["Publication Year"].astype(str).str.extract(r'((?:18|19|20)\d{2})')[0]
    df["Publication Year"] = pd.to_numeric(df["Publication Year"], errors="coerce")
    df = df.dropna(subset=["Publication Year"])
    
    if df.empty:
        st.error("No valid publication years found in dataset.")
        return
        
    min_year = int(df["Publication Year"].min())
    max_year = int(df["Publication Year"].max())

    potential_cols = ["Title", "Abstract", "Keywords"]
    available_cols = [c for c in potential_cols if c in df.columns]

    with st.expander("⚙️ Configuration", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            text_cols = st.multiselect(
                "Text Fields to Analyze",
                available_cols,
                default=[c for c in available_cols if c in ["Title", "Abstract"]]
            )
            
            topic_strategy = st.radio(
                "Number of Topics per Era", 
                ["Automatic (Based on volume)", "Fixed Number"]
            )
            
            if topic_strategy == "Fixed Number":
                n_topics_fixed = st.slider("Topics per Era", 3, 20, 5)
            else:
                n_topics_fixed = "auto"
                st.caption("Automatically determines the optimal number of topics based on the density and volume of documents in each era.")
        with col2:
            st.write(f"Data spans **{min_year}** to **{max_year}**.")
            slicing_strategy = st.radio(
                "Time Slicing Strategy", 
                ["Automatic (Balanced Document Volume)", "Automatic (Equal Time Intervals)", "Custom Cutoffs"]
            )
            
            if slicing_strategy == "Custom Cutoffs":
                default_cutoff = str(min_year + (max_year - min_year) // 2) if max_year > min_year else ""
                cutoffs_str = st.text_input("Enter Cutoff Years (comma-separated)", value=default_cutoff, help="Example: 1970, 1980 will create 3 eras")
            else:
                era_strategy = st.radio("Number of Eras", ["Automatic (Based on timespan)", "Fixed Number"])
                if era_strategy == "Fixed Number":
                    n_eras_fixed = st.slider("Number of Eras", 2, 10, 3)
                else:
                    n_eras_fixed = "auto"
                    st.caption("Automatically determines the optimal number of eras based on the total timespan of the dataset.")
                
            similarity_threshold = st.slider("Link Similarity Threshold", 0.0, 1.0, 0.03, 0.01, help="Minimum keyword overlap required to draw a line between eras.")
            
        run_btn = st.button("Generate Thematic Flow", type="primary", icon=":material/play_arrow:")
        
    if run_btn:
        if not text_cols:
            st.error("Select text columns.")
            return
            
        eras = []
        if slicing_strategy != "Custom Cutoffs":
            if n_eras_fixed == "auto":
                span = max_year - min_year
                if span <= 5: n_eras = 2
                elif span <= 15: n_eras = 3
                elif span <= 30: n_eras = 4
                else: n_eras = 5
            else:
                n_eras = n_eras_fixed
                
        if slicing_strategy == "Custom Cutoffs":
            try:
                cutoffs = []
                if cutoffs_str.strip():
                    cutoffs = sorted([int(x.strip()) for x in cutoffs_str.split(",") if x.strip()])
                cutoffs = [y for y in cutoffs if min_year <= y < max_year]
            except:
                st.error("Invalid cutoff years. Please enter numbers separated by commas.")
                return
                
            start = min_year
            for c in cutoffs:
                eras.append((start, c))
                start = c + 1
            eras.append((start, max_year))
            
        elif slicing_strategy == "Automatic (Equal Time Intervals)":
            interval = (max_year - min_year + 1) / n_eras
            start = min_year
            for i in range(n_eras - 1):
                end = int(start + interval - 1)
                eras.append((start, end))
                start = end + 1
            eras.append((start, max_year))
            
        elif slicing_strategy == "Automatic (Balanced Document Volume)":
            df_sorted = df[["Publication Year"]].copy().sort_values("Publication Year")
            df_sorted["era_bin"] = pd.qcut(np.arange(len(df_sorted)), q=n_eras, labels=False)
            
            start = min_year
            for i in range(n_eras):
                era_data = df_sorted[df_sorted["era_bin"] == i]
                if not era_data.empty:
                    e_max = int(era_data["Publication Year"].max())
                    if i == n_eras - 1:
                        e_max = max_year
                    if start <= e_max:
                        eras.append((start, e_max))
                        start = e_max + 1
            if start <= max_year and eras:
                # If there's leftover years due to skewed data, just append to last era
                last = eras.pop()
                eras.append((last[0], max_year))
        
        era_topics = []
        nodes = []
        node_colors = []
        
        # Light pastel color palette for nodes so black text is highly readable
        colors = ['#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5', '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5']
        
        with st.spinner("Processing Time Eras..."):
            docs = df[text_cols].fillna("").agg(" ".join, axis=1)
            df['combined_text'] = preprocess_text(docs)
            
            for era_idx, (start_y, end_y) in enumerate(eras):
                mask = (df["Publication Year"] >= start_y) & (df["Publication Year"] <= end_y)
                era_df = df[mask]
                
                era_name = f"{start_y}-{end_y}"
                if start_y == end_y:
                    era_name = f"{start_y}"
                    
                if len(era_df) < 1:
                    st.warning(f"Era {era_name} has 0 documents. Skipping.")
                    era_topics.append({"words": [], "vols": [], "name": era_name, "node_start_idx": len(nodes), "num_topics": 0})
                    continue
                    
                if n_topics_fixed == "auto":
                    # Heuristic: 1 topic per ~35 documents, bounded between 3 and 12
                    current_n_topics = max(3, min(12, len(era_df) // 35))
                else:
                    current_n_topics = n_topics_fixed
                    
                # Ensure we don't ask for more topics than we have documents
                current_n_topics = min(current_n_topics, len(era_df))
                if current_n_topics < 1:
                    current_n_topics = 1
                    
                t_words, t_vols = run_nmf(era_df['combined_text'].tolist(), n_topics=current_n_topics)
                
                era_node_start = len(nodes)
                for i in range(current_n_topics):
                    node_id = f"E{era_idx+1}_T{i+1}"
                    nodes.append({
                        "id": node_id,
                        "global_idx": len(nodes),
                        "era_idx": era_idx,
                        "era_name": era_name,
                        "topic_idx": i,
                        "words": t_words[i],
                        "vol": t_vols[i],
                        "default_label": f"{era_name}: T{i+1}"
                    })
                    node_colors.append(colors[i % len(colors)])
                    
                era_topics.append({
                    "words": t_words, 
                    "vols": t_vols, 
                    "name": era_name, 
                    "node_start_idx": era_node_start,
                    "num_topics": current_n_topics
                })
                
        if len([e for e in era_topics if e["num_topics"] > 0]) < 2:
            st.error("Need at least 2 valid eras with data to show flow.")
            return
            
        with st.spinner("Calculating Flows..."):
            links_source = []
            links_target = []
            links_value = []
            links_color = []
            links_records = []
            
            for e in range(len(eras) - 1):
                era1 = era_topics[e]
                era2 = era_topics[e+1]
                
                if era1["num_topics"] == 0 or era2["num_topics"] == 0: continue
                
                start_idx_1 = era1["node_start_idx"]
                start_idx_2 = era2["node_start_idx"]
                
                for t1 in range(era1["num_topics"]):
                    for t2 in range(era2["num_topics"]):
                        w1 = era1["words"][t1]
                        w2 = era2["words"][t2]
                        sim = calculate_jaccard(w1, w2)
                        
                        if sim >= similarity_threshold:
                            s_idx = start_idx_1 + t1
                            t_idx = start_idx_2 + t2
                            val = max(1, int(sim * era1["vols"][t1] * 10)) # Multiplied by 10 for visual thickness
                            links_source.append(s_idx)
                            links_target.append(t_idx)
                            links_value.append(val)
                            
                            # Make link color match source node color with transparency
                            base_color = node_colors[s_idx]
                            h = base_color.lstrip('#')
                            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                            links_color.append(f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.4)")

                            links_records.append({
                                "Source Era": era1["name"],
                                "Source Topic": f"Topic {t1+1}",
                                "Target Era": era2["name"],
                                "Target Topic": f"Topic {t2+1}",
                                "Jaccard Similarity": round(sim, 4),
                                "Flow Weight": val
                            })
                            
        if not links_source:
            st.warning("No connections found between eras at this similarity threshold. Try lowering the threshold or changing the cutoff years.")
            return

        # Save flow results in session state to allow GenAI labeling without re-computing NMF
        st.session_state.thematic_flow_data = {
            'nodes': nodes,
            'node_colors': node_colors,
            'links_source': links_source,
            'links_target': links_target,
            'links_value': links_value,
            'links_color': links_color,
            'links_records': links_records,
            'genai_labels': {}
        }

    # Render Diagram & GenAI Controls if flow data exists in memory
    if 'thematic_flow_data' in st.session_state:
        flow_data = st.session_state.thematic_flow_data
        nodes = flow_data['nodes']
        node_colors = flow_data['node_colors']
        links_source = flow_data['links_source']
        links_target = flow_data['links_target']
        links_value = flow_data['links_value']
        links_color = flow_data['links_color']
        links_records = flow_data['links_records']
        genai_labels = flow_data.get('genai_labels', {})

        # --- GenAI Naming Expander ---
        with st.expander("✨ GenAI Era Topic Naming (Single-Batch Quota Protected)", expanded=False):
            st.markdown("""
            Automatically name every topic across all eras using an LLM. 
            To strictly protect your quota and avoid prompt overflow, all topics are batched in a single efficient JSON call (chunked at 25 topics max).
            The generated names are embedded directly into the Sankey diagram node labels!
            """)
            
            g_col1, g_col2, g_col3 = st.columns([1.2, 2, 1.2])
            with g_col1:
                genai_provider = st.selectbox(
                    "LLM Provider", 
                    ["Gemini", "Groq (LLaMA 3)", "Anthropic (Claude)", "OpenAI", "Ollama (Local)"],
                    key="flow_genai_provider"
                )
            with g_col2:
                genai_api_key = st.text_input(
                    "API Key", 
                    type="password", 
                    placeholder="Enter API key...",
                    key="flow_genai_key"
                )
            with g_col3:
                st.write("")
                st.write("")
                run_genai_naming = st.button("Label All Eras with AI", type="primary", icon=":material/auto_awesome:", width="stretch")

            if run_genai_naming:
                if not genai_api_key and genai_provider != "Ollama (Local)":
                    st.warning("Please provide an API Key.")
                else:
                    with st.spinner(f"Batch labeling {len(nodes)} era topics in 1 quota-protected call..."):
                        batch_dict = {
                            n["id"]: n["words"]
                            for n in nodes
                        }
                        # Generates all names in one batch call with maximum 25 topics per chunk
                        res_labels = generate_batch_topic_names(
                            api_key=genai_api_key,
                            provider=genai_provider,
                            topics_dict=batch_dict,
                            chunk_size=25
                        )
                        st.session_state.thematic_flow_data['genai_labels'] = res_labels
                        st.toast(f"Labeled {len(res_labels)} topics across all eras!", icon="🎉")
                        st.rerun()

        # Build dynamic node labels and hover texts
        node_labels = []
        node_customdata = []
        node_rows_for_export = []

        for n in nodes:
            n_id = n["id"]
            ai_info = genai_labels.get(n_id, {})
            ai_name = ai_info.get("name") if isinstance(ai_info, dict) else None

            era_bold = f"<b>{n['era_name']}</b>"
            if ai_name and ai_name.strip() and not ai_name.startswith("Topic E"):
                # Embed AI name directly inside node label with bold era date
                display_label = f"{era_bold}: {ai_name}"
                plain_label = f"{n['era_name']}: {ai_name}"
            else:
                display_label = f"{era_bold}: T{n['topic_idx']+1}"
                plain_label = f"{n['era_name']}: T{n['topic_idx']+1}"

            node_labels.append(display_label)
            
            kw_list = ", ".join(n["words"][:7])
            hover = (
                f"{display_label}<br>"
                f"Era: {n['era_name']}<br>"
                f"Documents: {n['vol']}<br><br>"
                f"<b>Keywords:</b><br>{kw_list}"
            )
            node_customdata.append(hover)

            node_rows_for_export.append({
                "Node ID": n["id"],
                "Era": n["era_name"],
                "Topic Index": n["topic_idx"] + 1,
                "Display Label": plain_label,
                "GenAI Name": ai_name or "",
                "Document Count": n["vol"],
                "Top Keywords": ", ".join(n["words"])
            })

        # Inject CSS override to completely eliminate Plotly Sankey SVG text-shadow and enforce crisp dark text
        st.markdown("""
        <style>
        .sankey-node text, text.node-label {
            text-shadow: none !important;
            fill: #111827 !important;
            font-weight: 500 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # Render Interactive Sankey Diagram
        fig = go.Figure(data=[go.Sankey(
            textfont=dict(
                color="#111827",
                size=13,
                family="Source Sans Pro, sans-serif",
                shadow="none"
            ),
            node=dict(
                pad=20,
                thickness=35,
                line=dict(color="black", width=0.5),
                label=node_labels,
                color=node_colors,
                customdata=node_customdata,
                hovertemplate="%{customdata}<extra></extra>"
            ),
            link=dict(
                source=links_source,
                target=links_target,
                value=links_value,
                color=links_color
            )
        )])
        
        fig.update_layout(
            title_text="Thematic Flow Across Eras",
            font=dict(size=13, color="#111827"),
            height=620,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        
        st.plotly_chart(fig, width="stretch")

        # --- Export Hub ---
        st.markdown("<h4 style='font-size: 16px; font-weight: 700; color: #1E293B; margin-top: 15px;'><i class='bi bi-download' style='color: #697aa2;'></i> Export Thematic Flow Data</h4>", unsafe_allow_html=True)
        exp_c1, exp_c2, exp_c3, exp_c4 = st.columns(4, gap="small")
        
        nodes_export_df = pd.DataFrame(node_rows_for_export)
        links_export_df = pd.DataFrame(links_records)
        
        with exp_c1:
            _download_button(
                nodes_export_df,
                label="Download Nodes (CSV)",
                file_name="thematic_flow_nodes.csv",
                key="dl_flow_nodes"
            )
        with exp_c2:
            _download_button(
                links_export_df,
                label="Download Links (CSV)",
                file_name="thematic_flow_links.csv",
                key="dl_flow_links"
            )
        with exp_c3:
            # Inject style block inside exported standalone HTML to ensure shadow is removed there as well
            raw_html = fig.to_html(include_plotlyjs="cdn")
            clean_html = raw_html.replace(
                "</head>",
                "<style>.sankey-node text, text.node-label { text-shadow: none !important; fill: #111827 !important; font-weight: 500 !important; }</style></head>"
            )
            fn_flow_html = format_timestamped_filename("thematic_flow_sankey.html")
            html_encoded = clean_html.encode("utf-8")
            try: save_project_file("exports", fn_flow_html, html_encoded, mode="wb")
            except Exception: pass
            
            st.download_button(
                label="Download HTML Chart",
                data=html_encoded,
                file_name=fn_flow_html,
                mime="text/html",
                key="dl_flow_html"
            )
        with exp_c4:
            flow_export_json = json.dumps(st.session_state.thematic_flow_data, indent=2).encode("utf-8")
            fn_flow_proj = format_timestamped_filename("thematic_flow_project.json")
            try: save_project_file("sessions", fn_flow_proj, flow_export_json, mode="wb")
            except Exception: pass

            st.download_button(
                label="Save Flow Project (.json)",
                data=flow_export_json,
                file_name=fn_flow_proj,
                mime="application/json",
                key="dl_flow_project_json",
                help="Download entire flow state so you can re-upload and continue later without re-running."
            )
        
