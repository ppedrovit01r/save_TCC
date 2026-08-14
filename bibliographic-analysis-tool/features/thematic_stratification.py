import streamlit as st
import pandas as pd
import json
from lib.topic_modeling import (
    preprocess_for_gsdmm, run_bertopic, run_gsdmm,
    align_topics, assign_unified_topics,
    calculate_callon_metrics, calculate_temporal_trends,
    generate_topic_name
)

def show(df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-layers-half' style='color: #697aa2;'></i> Thematic Stratification</h2>", unsafe_allow_html=True)
    st.markdown("""
    A reproducible ensemble methodology integrating **semantic (BERTopic)** and 
    **probabilistic (GSDMM)** topic models through automatic topic alignment, 
    adaptive evaluation, and GenAI-assisted labeling.
    """)

    if df is None or df.empty:
        st.warning("Please load data in the Core Data Prep hub first.")
        return

    # Tabs definition
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Configuration", 
        "Topic Explorer", 
        "Strategic Map", 
        "Temporal Trends",
        "Quality Evaluation"
    ])

    with tab1:
        render_configuration_tab(df)
        
    with tab2:
        render_topic_explorer(df)
        
    with tab3:
        render_strategic_map(df)
        
    with tab4:
        render_temporal_trends(df)
        
    with tab5:
        render_quality(df)

def render_configuration_tab(df):
    st.subheader("Ensemble Pipeline Configuration")
    
    with st.expander("📥 Restore Previous Session"):
        st.write("Upload a previously exported Stratification Session JSON to restore your AI names, keywords, and cluster assignments without re-running the ML pipeline.")
        uploaded_file = st.file_uploader("Upload Stratification Session JSON", type=["json"])
        
        if uploaded_file is not None:
            if st.button("Restore Session", type="primary"):
                try:
                    data = json.load(uploaded_file)
                    
                    if len(data.get('topic_assignments', [])) != len(df):
                        st.error(f"🚨 Dataset length mismatch! Uploaded file has {len(data.get('topic_assignments', []))} rows, but current dataset has {len(df)} rows. You cannot restore this session onto a different dataset.")
                    else:
                        # Rehydrate dataframe
                        df['unified_topic'] = data['topic_assignments']
                        df['topic_confidence'] = data['topic_confidences']
                        df['secondary_topic'] = data['secondary_topics']
                        st.session_state.ts_df = df
                        
                        # Rehydrate metadata
                        # Ensure keys are integers where appropriate (JSON stringifies dictionary keys)
                        def to_int_keys(d):
                            return {int(k): v for k, v in d.items()}
                        
                        st.session_state.topic_names = to_int_keys(data.get('topic_names', {}))
                        st.session_state.topic_mapping = to_int_keys(data.get('topic_mapping', {}))
                        st.session_state.bert_words = to_int_keys(data.get('bert_words', {}))
                        st.session_state.gsdmm_words = to_int_keys(data.get('gsdmm_words', {}))
                            
                        st.success("Session Restored Successfully!")
                        import time
                        time.sleep(1)
                        st.rerun()
                except Exception as e:
                    st.error(f"Error restoring session: {e}")
    
    with st.expander("📐 Mathematical & Methodological Foundation"):
        st.markdown("""
        **Dual-Algorithm Ensemble Approach**
        This module employs a hybrid methodology to maximize topical coherence and diversity, specifically tailored for short or abstract texts.
        
        **1. BERTopic (Semantic Focus)**
        BERTopic [Grootendorst 2022] utilizes pre-trained transformer embeddings to capture deep semantic relationships. The algorithm operates in three main stages:
        *   **Embeddings**: Words are converted into high-dimensional vectors.
        *   **Dimensionality Reduction**: UMAP (Uniform Manifold Approximation and Projection) reduces the vector space while preserving local and global structures.
        *   **Clustering**: HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise) clusters the dense regions.
        *   **Representation**: A class-based TF-IDF (c-TF-IDF) extracts the most representative words per cluster:
        $$ W_{t,c} = tf_{t,c} \\times \\log \\left(1 + \\frac{A}{f_t} \\right) $$
        where $tf_{t,c}$ is the frequency of term $t$ in class $c$, $A$ is the average number of words per class, and $f_t$ is the term's frequency across all classes.
        
        **2. GSDMM (Probabilistic Focus)**
        The Gibbs Sampling Dirichlet Multinomial Mixture (GSDMM) [Yin and Wang 2014] is a probabilistic algorithm based on the Bag of Words paradigm, optimized for short texts. It operates under the assumption that one document is generated by exactly one topic. The probability of document $d$ belonging to topic $k$ is:
        $$ P(z=k | d) \\propto \\frac{m_{k, \\neg d} + \\alpha}{D - 1 + K\\alpha} \\times \\frac{\\prod_{w \\in d} (n_{k,w, \\neg d} + \\beta)}{ \\prod_{i=1}^{|d|} (N_{k, \\neg d} + V\\beta + i - 1) } $$
        where $\\alpha$ and $\\beta$ are Dirichlet priors, $m_k$ is the number of documents in topic $k$, $n_{k,w}$ is the frequency of word $w$ in topic $k$, and $V$ is the vocabulary size.
        """)
        
    st.divider()
    
    # Validation: Check for available text columns
    potential_cols = ["Title", "Abstract", "Keywords"]
    available_cols = [c for c in potential_cols if c in df.columns]
    
    if not available_cols:
        st.error("**No text data found.** The thematic stratification requires text to analyze (e.g. Title, Abstract). Please go back to the **Core Data Prep** hub and run the Data Enrichment pipeline before continuing.")
        return
        
    # Check data density to warn the user if enrichment is needed
    stats = []
    for c in available_cols:
        pct_present = (df[c].notna().sum() / len(df)) * 100
        stats.append(f"- **{c}**: {pct_present:.1f}% populated")
        
    st.info("**Available Text Data:**\n" + "\n".join(stats) + "\n\n*Tip: If these numbers are low, topic quality will be degraded. Consider enriching your dataset in the Data Prep tab.*")
    
    col1, col2 = st.columns(2)
    with col1:
        text_cols = st.multiselect(
            "Text Fields to Analyze",
            available_cols,
            default=[c for c in available_cols if c in ["Title", "Abstract"]]
        )
    with col2:
        if 'focus_topics' in st.session_state and len(st.session_state.focus_topics) > 0:
            st.warning("**Global Focus Mode Active.** You cannot run the Thematic Stratification pipeline while focused on a specific subset of topics. Please clear Focus Mode in the sidebar first.")
            st.button("Run Unified Ensemble", type="primary", disabled=True)
            return
        
        with st.expander("⚙️ Topic Alignment Strategy", expanded=True):
            strategy = st.radio(
                "How should the ensemble determine the number of topics?",
                ["Auto-Discovery (Recommended)", "Force Topic Size"]
            )
            
            target_k = None
            if strategy == "Force Topic Size":
                st.caption("Force both algorithms to compress or fragment the dataset into this exact number of topics.")
                target_k = st.slider("Target Number of Topics", min_value=2, max_value=50, value=7)
            else:
                st.caption("BERTopic mathematically discovers the optimal number of topics. GSDMM is then forced to align to that exact number.")
        
    if st.button("Run Unified Ensemble", type="primary"):
        if not text_cols:
            st.error("Please select at least one text column.")
            return
            
        import time
        import datetime
        import os
        
        start_time = time.time()
        start_timestamp = datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
            
        with st.spinner("Preprocessing texts..."):
            # Concatenate selected columns
            docs = df[text_cols].fillna("").agg(" ".join, axis=1)
            # Standard docs for BERTopic
            st.session_state.ts_docs = docs.tolist()
            # Tokenized docs for GSDMM
            st.session_state.ts_tokenized_docs = preprocess_for_gsdmm(st.session_state.ts_docs)
            
        with st.spinner("Running BERTopic..."):
            # If Auto-Discovery, nr_topics=None (or "auto") allows natural HDBSCAN discovery
            b_target = target_k if strategy == "Force Topic Size" else "auto"
            bert_model, bert_topics, bert_probs, bert_words = run_bertopic(st.session_state.ts_docs, nr_topics=b_target)
            st.session_state.bert_words = bert_words
            st.session_state.bert_topics = bert_topics
            
            # Sync GSDMM to BERTopic's output
            if strategy == "Auto-Discovery (Recommended)":
                target_k = len(bert_words)
            
        with st.spinner(f"Running GSDMM (k={target_k})"):
            gsdmm_model, gsdmm_topics, gsdmm_probs, gsdmm_words = run_gsdmm(st.session_state.ts_tokenized_docs, k=target_k)
            st.session_state.gsdmm_words = gsdmm_words
            st.session_state.gsdmm_topics = gsdmm_topics
            
        with st.spinner("4. Aligning Topics..."):
            b_to_u, g_to_u, mapping = align_topics(bert_topics, gsdmm_topics, bert_words, gsdmm_words)
            st.session_state.topic_mapping = mapping
            
            u_topics, confidences, secondary = assign_unified_topics(
                bert_topics, gsdmm_topics, b_to_u, g_to_u
            )
            
            # Save results back to session state dataframe
            df['unified_topic'] = u_topics
            df['topic_confidence'] = confidences
            df['secondary_topic'] = secondary
            st.session_state.ts_df = df
            
        # Logging
        end_time = time.time()
        end_timestamp = datetime.datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')
        duration = end_time - start_time
        
        outliers = u_topics.count(-1)
        total_docs = len(u_topics)
        
        log_lines = [
            "=" * 80,
            "             THEMATIC STRATIFICATION ENSEMBLE AUDIT REPORT",
            "=" * 80,
            f"Execution Timeframe: {start_timestamp}  -->  {end_timestamp} ({duration:.2f} seconds)",
            f"Fields Analyzed: {text_cols}",
            f"Alignment Strategy: {strategy}",
            f"Synchronized Topic Count (k): {target_k}",
            f"Total Documents Processed: {total_docs}",
            "",
            "--------------------------------------------------------------------------------",
            "MODEL STATISTICS",
            "--------------------------------------------------------------------------------",
            f"• Unified Topics Generated: {len(mapping)}",
            f"• Outlier Documents (-1): {outliers} ({(outliers/total_docs*100):.1f}%)",
            f"• Average Assignment Confidence: {(sum(confidences)/len(confidences)):.2f}",
            "",
            "--------------------------------------------------------------------------------",
            "ALIGNMENT MAPPING SUMMARY",
            "--------------------------------------------------------------------------------"
        ]
        
        for u_id, m in mapping.items():
            b_id = m['bertopic_id']
            g_id = m['gsdmm_id']
            sim = m['similarity']
            log_lines.append(f"• Unified Topic {u_id}: BERTopic [{b_id}] ↔ GSDMM [{g_id}] (Similarity: {sim:.2f})")
            
        log_lines.extend([
            "=" * 80,
            "PIPELINE COMPLETED SUCCESSFULLY",
            "=" * 80
        ])
        
        report_text = "\n".join(log_lines)
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_filename = os.path.join(log_dir, f"thematic_stratification_{datetime.datetime.fromtimestamp(end_time).strftime('%Y%m%d_%H%M%S')}.log")
        
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write(report_text + "\n")
            f.flush()
            
        st.session_state.ts_last_log = report_text
        st.session_state.ts_last_log_file = log_filename
            
        st.success(f"Ensemble pipeline completed in {duration:.2f}s! Log saved to `{log_filename}`.")

def render_topic_explorer(df):
    st.subheader("Topic Explorer & GenAI Naming")
    
    if 'ts_df' not in st.session_state or 'topic_mapping' not in st.session_state:
        st.info("Please run the ensemble pipeline in the Configuration tab first.")
        return
        
    # General Vision Table
    st.subheader("General Vision")
    unified_ids = list(st.session_state.topic_mapping.keys())
    
    if 'topic_names' not in st.session_state:
        st.session_state.topic_names = {}
        
    table_data = []
    for u_id in unified_ids:
        b_id = st.session_state.topic_mapping[u_id]['bertopic_id']
        g_id = st.session_state.topic_mapping[u_id]['gsdmm_id']
        
        b_words = ", ".join(st.session_state.bert_words.get(b_id, [])) if b_id is not None else "N/A"
        g_words = ", ".join(st.session_state.gsdmm_words.get(g_id, [])) if g_id is not None else "N/A"
        ai_name = st.session_state.topic_names.get(u_id, {}).get('name', '')
        
        table_data.append({
            "Unified Topic": u_id,
            "AI Name": ai_name,
            "BERTopic Keywords": b_words,
            "GSDMM Keywords": g_words
        })
        
    st.dataframe(pd.DataFrame(table_data), width="stretch")
    st.divider()

    # GenAI Config
    st.caption("GenAI Naming Engine")
    
    with st.expander("🔑 How to get a FREE API Key in 60 seconds"):
        st.markdown("""
        **Option A: Google Gemini (Recommended)**
        1. Go to [Google AI Studio](https://aistudio.google.com/).
        2. Sign in with your standard Google/Gmail account.
        3. Click the blue **"Get API key"** button on the left menu.
        4. Click **"Create API key"** and copy the long text string.
        5. Paste it in the box below!
        
        **Option B: Groq (Blazing Fast LLaMA 3)**
        1. Go to [GroqCloud](https://console.groq.com/keys).
        2. Sign in or create a quick account.
        3. Click **"Create API Key"** and copy the text string.
        4. Select "Groq (LLaMA 3)" from the provider list below and paste your key!
        """)
        
    g_col1, g_col2, g_col3 = st.columns([1, 2, 1])
    with g_col1:
        provider = st.selectbox("Provider", ["Gemini", "Groq (LLaMA 3)", "OpenAI", "Ollama (Local)", "None"])
    with g_col2:
        api_key = st.text_input("API Key (Stored locally only)", type="password")
        if provider == "Ollama (Local)":
            st.caption("Make sure Ollama is running on your machine.")
    with g_col3:
        if st.button("Generate Names for ALL Topics", width="stretch", type="primary"):
            if provider != "None":
                with st.spinner("Batch generating names..."):
                    for u_id in unified_ids:
                        b_id_all = st.session_state.topic_mapping[u_id]['bertopic_id']
                        g_id_all = st.session_state.topic_mapping[u_id]['gsdmm_id']
                        words_to_send = []
                        if b_id_all is not None: words_to_send.extend(st.session_state.bert_words.get(b_id_all, []))
                        if g_id_all is not None: words_to_send.extend(st.session_state.gsdmm_words.get(g_id_all, []))
                        
                        result = generate_topic_name(api_key, provider, list(set(words_to_send)))
                        st.session_state.topic_names[u_id] = result
                st.rerun()
            else:
                st.warning("Please select a valid provider.")
    
        
    # --- GLOBAL FOCUS MODE ACTIVATION ---
    st.subheader("🎯 Global Focus Mode")
    st.write("Isolate the entire application (Main Dashboard, Co-citation Networks, etc.) to analyze only specific topics.")
    
    # Get user friendly names for the multiselect
    focus_options = {u_id: get_topic_name(u_id) for u_id in unified_ids}
    
    selected_focus = st.multiselect(
        "Select Topic(s) to Focus:",
        options=unified_ids,
        format_func=lambda x: focus_options[x],
        default=st.session_state.get('focus_topics', [])
    )
    
    if st.button("Activate Focus Mode", type="primary"):
        st.session_state.focus_topics = selected_focus
        st.rerun()
        
    st.divider()
    
    # Topic Selector
    st.subheader("Explore Topic Keywords")
    unified_ids = list(st.session_state.topic_mapping.keys())
    selected_topic = st.selectbox("Select Topic to Explore", unified_ids, format_func=lambda x: f"Topic {x}")
    
    mapping_info = st.session_state.topic_mapping[selected_topic]
    b_id = mapping_info['bertopic_id']
    g_id = mapping_info['gsdmm_id']
    
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.write("**BERTopic Keywords:**")
        if b_id is not None:
            st.write(", ".join(st.session_state.bert_words.get(b_id, [])))
        else:
            st.write("N/A")
            
    with t_col2:
        st.write("**GSDMM Keywords:**")
        if g_id is not None:
            st.write(", ".join(st.session_state.gsdmm_words.get(g_id, [])))
        else:
            st.write("N/A")
            
    with g_col3:
        if st.button("Generate Name (Single)", width="stretch"):
            if provider != "None":
                words_to_send = []
                if b_id is not None: words_to_send.extend(st.session_state.bert_words.get(b_id, []))
                if g_id is not None: words_to_send.extend(st.session_state.gsdmm_words.get(g_id, []))
                
                with st.spinner("Generating..."):
                    result = generate_topic_name(api_key, provider, list(set(words_to_send)))
                    st.session_state.topic_names[selected_topic] = result
                st.rerun()
            else:
                st.warning("Please select a valid provider.")

    if selected_topic in st.session_state.topic_names:
        ai_data = st.session_state.topic_names[selected_topic]
        st.success(f"**Generated Name:** {ai_data.get('name')}")
        st.write(f"**Description:** {ai_data.get('description')}")
        
    # Representative documents
    st.subheader("Representative Documents")
    topic_docs = st.session_state.ts_df[st.session_state.ts_df['unified_topic'] == selected_topic]
    topic_docs = topic_docs.sort_values(by='topic_confidence', ascending=False).head(5)
    
    if not topic_docs.empty:
        for idx, row in topic_docs.iterrows():
            title = row.get('Title', 'No Title')
            conf = row.get('topic_confidence', 0)
            st.markdown(f"- **{title}** (Confidence: {conf:.2f})")
    else:
        st.write("No documents assigned to this topic.")

def get_topic_name(topic_id):
    if 'topic_names' in st.session_state and topic_id in st.session_state.topic_names:
        return st.session_state.topic_names[topic_id].get('name', f"Topic {topic_id}")
    return f"Topic {topic_id}"

def render_strategic_map(df):
    st.subheader("Strategic Map (Callon Diagram)")
    
    with st.expander("📐 Mathematical & Methodological Foundation"):
        st.markdown("""
        **Callon's Strategic Map**
        The Strategic Map visualizes the structural evolution of a research field by plotting themes based on two mathematical dimensions: Centrality and Density.
        
        *   **Centrality (External Relevance - X Axis)**: Measures the degree of interaction a network (topic) has with other networks. It represents the importance of a theme in the overall development of the field. Let $E_{ij}$ be the equivalence index between term $i$ and term $j$ (where $i$ belongs to topic $k$, and $j$ belongs to other topics):
        $$ C_k = 10 \\times \\sum_{i \\in k, j \\notin k} E_{ij} $$
        *   **Density (Internal Cohesion - Y Axis)**: Measures the internal strength of the network, quantifying how strongly the terms within a specific topic are linked to each other. It represents the theme's capacity to develop and sustain itself.
        $$ D_k = 100 \\times \\frac{\\sum_{i,j \\in k} E_{ij}}{N_k} $$
        
        **Quadrants Interpretation**:
        *   **Motor Themes (Top-Right)**: High Centrality, High Density. Well-developed and essential to the structure of the research field.
        *   **Specialized/Isolated Themes (Top-Left)**: Low Centrality, High Density. Highly developed internally but isolated from the broader field.
        *   **Emerging/Declining Themes (Bottom-Left)**: Low Centrality, Low Density. Weakly developed or marginalized themes.
        *   **Basic/Transversal Themes (Bottom-Right)**: High Centrality, Low Density. Important for the general field but not internally well-developed.
        """)
        
    if 'ts_df' not in st.session_state:
        st.info("Please run the ensemble pipeline first.")
        return
        
    metrics = calculate_callon_metrics(st.session_state.ts_df)
    if not metrics.empty:
        # Map to AI Names
        metrics['Topic Name'] = metrics['topic'].apply(get_topic_name)
        
        st.write("The Strategic Map visualizes topics based on their **Centrality** (external relevance) and **Density** (internal cohesion).")
        
        # Calculate medians for quadrants
        med_centrality = metrics['centrality'].median()
        med_density = metrics['density'].median()
        
        def get_quadrant(row):
            if row['centrality'] >= med_centrality and row['density'] >= med_density:
                return "Motor Themes"
            elif row['centrality'] < med_centrality and row['density'] >= med_density:
                return "Specialized/Isolated Themes"
            elif row['centrality'] < med_centrality and row['density'] < med_density:
                return "Emerging/Declining Themes"
            else:
                return "Basic/Transversal Themes"
                
        metrics['Quadrant'] = metrics.apply(get_quadrant, axis=1)
        
        import plotly.express as px
        
        fig = px.scatter(
            metrics,
            x='centrality',
            y='density',
            color='Topic Name',
            size='n_docs',
            hover_name='Topic Name',
            hover_data=['Quadrant'],
            title="Callon's Strategic Map"
        )
        
        # Auto-scale axes precisely to the data limits with 10% padding (avoids forcing 0)
        c_min, c_max = metrics['centrality'].min(), metrics['centrality'].max()
        d_min, d_max = metrics['density'].min(), metrics['density'].max()
        
        c_pad = (c_max - c_min) * 0.1 if c_max != c_min else 0.1
        d_pad = (d_max - d_min) * 0.1 if d_max != d_min else 0.1
        
        fig.update_xaxes(range=[c_min - c_pad, c_max + c_pad])
        fig.update_yaxes(range=[d_min - d_pad, d_max + d_pad])
        
        # Draw Quadrant lines
        fig.add_hline(y=med_density, line_dash="dash", line_color="gray", opacity=0.7)
        fig.add_vline(x=med_centrality, line_dash="dash", line_color="gray", opacity=0.7)
        
        # Quadrant Annotations
        fig.add_annotation(x=c_max, y=d_max, text="Motor", showarrow=False, font=dict(color="gray", size=14), xanchor="right", yanchor="top")
        fig.add_annotation(x=c_min, y=d_max, text="Specialized", showarrow=False, font=dict(color="gray", size=14), xanchor="left", yanchor="top")
        fig.add_annotation(x=c_min, y=d_min, text="Emerging/Declining", showarrow=False, font=dict(color="gray", size=14), xanchor="left", yanchor="bottom")
        fig.add_annotation(x=c_max, y=d_min, text="Basic/Transversal", showarrow=False, font=dict(color="gray", size=14), xanchor="right", yanchor="bottom")
        
        st.plotly_chart(fig, width="stretch")
        
        # Display the categorized table
        st.dataframe(metrics[['Topic Name', 'Quadrant', 'n_docs', 'centrality', 'density']], width="stretch")

def render_temporal_trends(df):
    st.subheader("Temporal Trends & Regression")
    if 'ts_df' not in st.session_state:
        st.info("Please run the ensemble pipeline first.")
        return
        
    ts_df = st.session_state.ts_df
    
    # Identify year column
    year_col = None
    for col in ['Year', 'year', 'Publication Year']:
        if col in ts_df.columns:
            year_col = col
            break
            
    if year_col is None:
        st.warning("No Year column found in dataset. Cannot calculate temporal trends.")
        return
        
    st.write(f"Analyzing trends over time using column: `{year_col}`")
    
    # Plotting prevalence over time
    topics = [t for t in ts_df['unified_topic'].unique() if t != -1]
    
    # Ensure year is formatted as a 4-digit integer
    ts_df[year_col] = ts_df[year_col].astype(str).str.extract(r'((?:18|19|20)\d{2})')[0]
    ts_df[year_col] = pd.to_numeric(ts_df[year_col], errors="coerce")
    
    yearly_counts = ts_df.groupby([year_col, 'unified_topic']).size().unstack(fill_value=0)
    
    # Rename columns to AI names
    yearly_counts.columns = [get_topic_name(c) for c in yearly_counts.columns]
    
    st.line_chart(yearly_counts, width="stretch")
        
    trends = calculate_temporal_trends(ts_df, year_col=year_col)
    if not trends.empty:
        trends['Topic Name'] = trends['topic'].apply(get_topic_name)
        st.dataframe(trends[['Topic Name', 'growth_coefficient', 'trend_status']], width="stretch")

def render_quality(df):
    st.subheader("Ensemble Quality Metrics")
    
    with st.expander("📐 Mathematical & Methodological Foundation"):
        st.markdown("""
        **Topic Model Evaluation Metrics**
        The quality of the generated topics is evaluated using established metrics for Coherence and Diversity, highlighting the trade-offs between semantic and probabilistic approaches [Amorim et al. 2022].
        
        **1. Coherence (Interpretability)**
        Measures how well the top words of a topic make semantic sense together. We utilize two metrics [Röder et al. 2015]:
        *   **NPMI (Normalized Pointwise Mutual Information)**: Evaluates the statistical co-occurrence of word pairs $(w_i, w_j)$ across the corpus.
        $$ NPMI(w_i, w_j) = \\frac{\\log \\frac{P(w_i, w_j)}{P(w_i)P(w_j)}}{-\\log P(w_i, w_j)} $$
        *   **$C_V$**: A composite metric combining NPMI with cosine similarity over word vectors. It is widely considered the most correlated with human interpretability.
        
        **2. Diversity (Uniqueness)**
        Measures how distinct the generated topics are from one another.
        *   **Inverted Rank-Biased Overlap (RBO)** [Webber et al. 2010]: Unlike simple intersection, RBO weights the rank of the overlapping words, heavily penalizing models that share the most frequent/important words across multiple topics.
        $$ RBO = (1 - p) \\sum_{d=1}^{d_{max}} p^{d-1} A_d $$
        where $A_d$ is the agreement at depth $d$, and $p$ is a parameter weighting the top of the ranking.
        """)
        
    if 'ts_df' not in st.session_state:
        st.info("Please run the ensemble pipeline first.")
        return
        
    ts_df = st.session_state.ts_df
    
    total_docs = len(ts_df)
    outliers = ts_df[ts_df['unified_topic'] == -1].shape[0]
    avg_conf = ts_df['topic_confidence'].mean()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Average Confidence", f"{avg_conf:.2f}")
    with col2:
        st.metric("Total Documents", total_docs)
    with col3:
        st.metric("Outliers (-1)", f"{outliers} ({(outliers/total_docs*100):.1f}%)")
        
    st.divider()
    st.write("### Data Export")
    st.write("You can download the full enriched dataset with unified topics, secondary topics, and confidence scores attached.")
    
    csv = ts_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Final Dataset as CSV",
        data=csv,
        file_name='bibliometric_stratified_results.csv',
        mime='text/csv',
    )
    
    st.divider()
    st.write("### Save Session")
    st.write("Export the current stratification session to a JSON file to easily restore it later.")
    
    session_data = {
        'topic_assignments': ts_df['unified_topic'].tolist() if 'unified_topic' in ts_df.columns else [],
        'topic_confidences': ts_df['topic_confidence'].tolist() if 'topic_confidence' in ts_df.columns else [],
        'secondary_topics': ts_df['secondary_topic'].tolist() if 'secondary_topic' in ts_df.columns else [],
        'topic_names': st.session_state.get('topic_names', {}),
        'topic_mapping': st.session_state.get('topic_mapping', {}),
        'bert_words': st.session_state.get('bert_words', {}),
        'gsdmm_words': st.session_state.get('gsdmm_words', {})
    }
    
    # Handle NaN in JSON by replacing with None
    import math
    def clean_floats(obj):
        if isinstance(obj, float):
            if math.isnan(obj): return None
            return obj
        elif isinstance(obj, dict):
            return {k: clean_floats(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean_floats(v) for v in obj]
        return obj
        
    json_bytes = json.dumps(clean_floats(session_data)).encode('utf-8')
    
    st.download_button(
        label="Export Session State (.json)",
        data=json_bytes,
        file_name='stratification_session.json',
        mime='application/json',
    )
