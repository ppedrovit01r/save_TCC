import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
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
            
        run_btn = st.button("Generate Thematic Flow", type="primary")
        
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
        node_labels = []
        node_customdata = []
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
                    nodes.append({"era_idx": era_idx, "topic_idx": i, "words": t_words[i], "vol": t_vols[i]})
                    
                    lbl = f"Era {era_idx+1} (T{i+1})"
                    node_labels.append(lbl)
                    
                    hover_text = f"<b>{era_name} - Topic {i+1}</b><br>Documents: {t_vols[i]}<br><br><b>Keywords:</b><br>" + "<br>".join(t_words[i][:7])
                    node_customdata.append(hover_text)
                    
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
                            links_source.append(start_idx_1 + t1)
                            links_target.append(start_idx_2 + t2)
                            val = max(1, int(sim * era1["vols"][t1] * 10)) # Multiplied by 10 for visual thickness
                            links_value.append(val)
                            
                            # Make link color match source node color with transparency
                            base_color = node_colors[start_idx_1 + t1]
                            # Convert hex to rgba
                            h = base_color.lstrip('#')
                            rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
                            links_color.append(f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, 0.4)")
                            
        if not links_source:
            st.warning("No connections found between eras at this similarity threshold. Try lowering the threshold or changing the cutoff years.")
            return
            
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=20,
                thickness=40,
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
            font=dict(size=14, color="#000000"),
            height=600,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        st.plotly_chart(fig, width="stretch")
        
