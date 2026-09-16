import streamlit as st
import pandas as pd
import json
import os
import time
import datetime
from utils.formatters import format_duration
from lib.topic_modeling import (
    preprocess_for_gsdmm, run_bertopic, run_gsdmm,
    align_topics, assign_unified_topics,
    calculate_callon_metrics, calculate_temporal_trends, calculate_cluster_quality_metrics,
    generate_topic_name, generate_batch_topic_names
)
import re
import hashlib
import string
import nltk
from utils.project_manager import get_global_cache_dir, save_project_file, format_timestamped_filename, get_timestamp_str

TRANSLATION_CACHE_FILE = os.path.join("utils", "cache", "translation_cache.json")

def load_translation_cache() -> dict:
    """Loads previously translated texts from disk."""
    if os.path.exists(TRANSLATION_CACHE_FILE):
        try:
            with open(TRANSLATION_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Filter out any accidental error boilerplate that might have slipped into cache previously
                    return {k: v for k, v in data.items() if v and not is_error_boilerplate(v)}
        except Exception:
            pass
    return {}

def save_translation_cache(cache: dict):
    """Saves translation cache safely to disk."""
    try:
        os.makedirs(os.path.dirname(TRANSLATION_CACHE_FILE), exist_ok=True)
        # Final sanity check: ensure no error boilerplate is ever saved to disk
        clean_cache = {k: v for k, v in cache.items() if v and not is_error_boilerplate(v)}
        with open(TRANSLATION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def is_error_boilerplate(text: str) -> bool:
    """Detects HTTP 500 error pages, quota limits, or scraping failure responses stored in document text."""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    patterns = [
        "error 500", "500. that", "that's an error", "thats an error", "internal server error",
        "server error", "please try again later", "that's all we know", "thats all we know",
        "error1500thats", "errorthere", "laterthats", "429 too many requests", "rate limit exceeded",
        "service unavailable", "bad gateway"
    ]
    return any(p in lower for p in patterns)

def is_likely_english(text: str, lang_meta: str = "") -> bool:
    """
    Determines if text is already English using metadata and offline NLTK stopword analysis.
    Returns True if English (no translation needed), False if non-English.
    """
    if lang_meta and str(lang_meta).strip().lower() in ["en", "eng", "english"]:
        return True
    if not text or len(str(text).strip()) < 15:
        return True
        
    try:
        en_stops = set(stopwords.words('english'))
        pt_stops = set(stopwords.words('portuguese'))
        es_stops = set(stopwords.words('spanish'))
        fr_stops = set(stopwords.words('french'))
    except Exception:
        nltk.download('stopwords', quiet=True)
        en_stops = set(stopwords.words('english'))
        pt_stops = set(stopwords.words('portuguese'))
        es_stops = set(stopwords.words('spanish'))
        fr_stops = set(stopwords.words('french'))

    clean = str(text).lower()
    words = [w.strip(string.punctuation) for w in clean.split()]
    words = [w for w in words if w.isalpha() and len(w) > 1]
    if not words:
        return True

    en_count = sum(1 for w in words if w in en_stops)
    foreign_stops = pt_stops.union(es_stops).union(fr_stops) - en_stops
    foreign_count = sum(1 for w in words if w in foreign_stops)

    # Distinct Romance language functional n-grams / markers
    romance_markers = ['ção', 'ções', ' da ', ' do ', ' das ', ' dos ', ' de ', ' na ', ' no ', ' para ', ' com ', ' em ', ' el ', ' la ', ' los ', ' las ']
    marker_hits = sum(1 for m in romance_markers if m in clean)

    if marker_hits >= 2 and en_count < 3:
        return False

    if foreign_count > en_count and foreign_count >= 2:
        return False

    return True

def show(df):
    st.markdown("<h2 style='font-size: 24px; font-weight: 700; color: #1E293B;'><i class='bi bi-layers-half' style='color: #697aa2;'></i> Thematic Stratification</h2>", unsafe_allow_html=True)
    st.markdown("""
    A reproducible ensemble methodology integrating **semantic (BERTopic)** and 
    **probabilistic (GSDMM)** topic models through automatic topic alignment, 
    adaptive evaluation, and GenAI-assisted labeling.
    """)

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
                ["Auto-Discovery (Recommended)", "Force Topic Size"],
                help="Auto-Discovery allows BERTopic to naturally find the optimal number of clusters based on density, and then forces GSDMM to match that exact number. Force Topic Size lets you manually dictate the granularity."
            )
            target_k = 5
            if strategy == "Force Topic Size":
                target_k = st.slider("Target Number of Topics", 2, 50, 5)
                
            n_corpus = len(df)
            default_min_docs = min(12, max(2, int(0.025 * n_corpus)))
            max_allowed_min = max(20, int(0.10 * n_corpus))
            min_cluster_docs = st.number_input(
                "Minimum Cluster Size (Documents)",
                min_value=2,
                max_value=max_allowed_min,
                value=default_min_docs,
                help=f"Topics/clusters with fewer documents than this threshold will be absorbed or pruned, preventing micro-topics (< 2.5% of corpus). Default is min(12, 2.5% of corpus) = {default_min_docs} for {n_corpus} documents."
            )
            
            min_confidence = st.slider(
                "Minimum Topic Confidence",
                min_value=0.0,
                max_value=1.0,
                value=0.70,
                step=0.05,
                help="Documents with an alignment confidence below this threshold will be marked as outliers (-1). A higher value ensures tighter, more coherent clusters."
            )
                
        with st.expander("🌐 Text Translation Pipeline"):
            translation_mode = st.radio(
                "Translation Strategy",
                ["Disabled", "Selective (Non-English Only - Recommended)", "Force All Documents"],
                index=1,
                help="Selective mode automatically identifies non-English documents via metadata ('Language' column) and fast offline heuristics. English texts require 0 network calls, preventing Google rate-limits (HTTP 500 errors) and preserving quota."
            )
            enable_translation = translation_mode != "Disabled"
            force_all_translation = translation_mode == "Force All Documents"
            
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
            
            if enable_translation:
                import urllib.request
                import urllib.parse
                import time
                from deep_translator import GoogleTranslator
                
                cache = load_translation_cache()
                cache_updates = 0
                translator = GoogleTranslator(source='auto', target='en')
                translated_docs = []
                
                def get_cache_key(txt: str) -> str:
                    return hashlib.md5(txt.strip().encode('utf-8')).hexdigest()

                def translate_single_text(txt: str) -> str:
                    nonlocal cache_updates
                    txt_clean = txt.strip()
                    if not txt_clean:
                        return txt_clean

                    key = get_cache_key(txt_clean)
                    # Check persistent cache first
                    if key in cache:
                        cached_val = cache[key]
                        if cached_val and not is_error_boilerplate(cached_val):
                            return cached_val

                    # Truncate clean text to 2500 chars to avoid payload limits
                    payload = txt_clean[:2500]

                    # Attempt 1: GoogleTranslator
                    try:
                        res = translator.translate(payload)
                        if res and not is_error_boilerplate(res):
                            cache[key] = res
                            cache_updates += 1
                            time.sleep(0.35)
                            return res
                    except Exception:
                        pass

                    # Attempt 2: Direct Google GTX endpoint with retry
                    try:
                        time.sleep(0.4)
                        encoded = urllib.parse.quote(payload)
                        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={encoded}"
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read().decode('utf-8'))
                            trans = ''.join([part[0] for part in data[0] if part and part[0]])
                            if trans and not is_error_boilerplate(trans):
                                cache[key] = trans
                                cache_updates += 1
                                return trans
                    except Exception:
                        pass

                    # Safe fallback: return original text (never save errors to cache)
                    return txt_clean

                progress_text = "Analyzing language & translating non-English documents..."
                my_bar = st.progress(0, text=progress_text)
                
                doc_list = docs.tolist()
                lang_series = df['Language'] if 'Language' in df.columns else [None] * len(df)
                total_docs = len(doc_list)
                translated_count = 0
                english_skipped = 0
                cached_count = 0

                for i, doc in enumerate(doc_list):
                    raw_text = str(doc).strip()
                    if not raw_text:
                        translated_docs.append(raw_text)
                        continue

                    # Check if metadata or heuristics confirm it is English
                    lang_meta = lang_series.iloc[i] if hasattr(lang_series, 'iloc') else (lang_series[i] if i < len(lang_series) else None)
                    key = get_cache_key(raw_text)

                    if not force_all_translation and is_likely_english(raw_text, lang_meta):
                        # It is already English: 0 network requests needed
                        translated_docs.append(raw_text)
                        english_skipped += 1
                    elif key in cache and not is_error_boilerplate(cache[key]):
                        # Cached non-English translation: 0 network requests
                        translated_docs.append(cache[key])
                        cached_count += 1
                    else:
                        # Non-English: translate and update cache
                        trans = translate_single_text(raw_text)
                        translated_docs.append(trans)
                        translated_count += 1

                    if i % 5 == 0 or i == total_docs - 1:
                        status_msg = f"Preprocessing texts... {i+1}/{total_docs} (English/Skipped: {english_skipped}, Cached: {cached_count}, Translated: {translated_count})"
                        my_bar.progress((i + 1) / total_docs, text=status_msg)

                my_bar.empty()
                if cache_updates > 0:
                    save_translation_cache(cache)

                if translated_count > 0 or cached_count > 0:
                    st.toast(f"Translation complete: {translated_count} translated, {cached_count} from cache, {english_skipped} skipped as English.", icon="🌐")

                docs = pd.Series(translated_docs)
                
            # Final Sanitize: scrub any existing web error boilerplate from text before sending to BERTopic/GSDMM
            def clean_document_text(text: str) -> str:
                if not text or pd.isna(text):
                    return ""
                s = str(text)
                # If the entire text or majority is just an HTTP 500 error page dump
                if is_error_boilerplate(s):
                    # Strip out error boilerplate
                    s = re.sub(r'500\s*\.?\s*(?:That\'?s\s*an\s*error\.?)?', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'There\s*was\s*an\s*error\.?', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'Please\s*try\s*again\s*later\.?', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'That\'?s\s*all\s*we\s*know\.?', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'(?:internal\s*)?server\s*error\s*500', '', s, flags=re.IGNORECASE)
                    s = re.sub(r'error1500thats|errorthere|laterthats', '', s, flags=re.IGNORECASE)
                return s.strip()

            sanitized_docs = [clean_document_text(d) for d in docs.tolist()]

            # Standard docs for BERTopic
            st.session_state.ts_docs = sanitized_docs
            # Tokenized docs for GSDMM
            st.session_state.ts_tokenized_docs = preprocess_for_gsdmm(st.session_state.ts_docs)
            
        with st.spinner("Running BERTopic..."):
            # If Auto-Discovery, nr_topics=None (or "auto") allows natural HDBSCAN discovery
            b_target = target_k if strategy == "Force Topic Size" else "auto"
            bert_model, bert_topics, bert_probs, bert_words = run_bertopic(
                st.session_state.ts_docs,
                min_topic_size=int(min_cluster_docs),
                nr_topics=b_target
            )
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
            b_to_u, g_to_u, mapping = align_topics(
                bert_topics,
                gsdmm_topics,
                bert_words,
                gsdmm_words,
                min_topic_size=int(min_cluster_docs)
            )
            st.session_state.topic_mapping = mapping
            
            u_topics, confidences, secondary = assign_unified_topics(
                bert_topics, gsdmm_topics, b_to_u, g_to_u,
                min_confidence=float(min_confidence),
                min_topic_size=int(min_cluster_docs)
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
        
        formatted_duration = format_duration(duration)
        
        log_lines = [
            "=" * 80,
            "             THEMATIC STRATIFICATION ENSEMBLE AUDIT REPORT",
            "=" * 80,
            f"Execution Timeframe: {start_timestamp}  -->  {end_timestamp} ({formatted_duration})",
            f"Fields Analyzed: {text_cols}",
            f"Alignment Strategy: {strategy}",
            f"Minimum Cluster Size: {min_cluster_docs} documents",
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
            b_id = m.get('bertopic_id')
            g_ids = m.get('gsdmm_ids', [])
            if not g_ids and m.get('gsdmm_id') is not None:
                g_ids = [m['gsdmm_id']]
            sims = m.get('similarities', [])
            
            b_str = f"[{b_id}]" if b_id is not None else "[None]"
            g_str = "[" + ", ".join([str(g) for g in g_ids]) + "]" if g_ids else "[None]"
            sim_str = "[" + ", ".join([f"{s:.2f}" for s in sims]) + "]" if sims else "[0.00]"
            
            log_lines.append(f"• Unified Topic {u_id}: BERTopic {b_str} ↔ GSDMM {g_str} (Similarities: {sim_str})")
            
        log_lines.extend([
            "",
            "--------------------------------------------------------------------------------",
            "PER-CLUSTER STATISTICAL & CONFIDENCE AUDIT",
            "--------------------------------------------------------------------------------"
        ])
        
        # Calculate cluster audit metrics for the log
        clusters = sorted([t for t in set(u_topics) if t != -1])
        for c_id in clusters:
            c_indices = [i for i, t in enumerate(u_topics) if t == c_id]
            c_confs = [confidences[i] for i in c_indices]
            c_count = len(c_indices)
            c_share = (c_count / total_docs * 100) if total_docs > 0 else 0
            c_mean_conf = (sum(c_confs) / c_count) if c_count > 0 else 0
            c_consensus = sum(1 for c in c_confs if c == 1.0)
            c_conflict = sum(1 for c in c_confs if c == 0.5)
            
            m_info = mapping.get(c_id, {})
            b_kws = ", ".join(bert_words.get(m_info.get('bertopic_id'), [])[:6]) if m_info.get('bertopic_id') is not None else "None"
            g_list = []
            for g_k in m_info.get('gsdmm_ids', []):
                g_list.extend(gsdmm_words.get(g_k, []))
            g_kws = ", ".join(list(dict.fromkeys(g_list))[:6]) if g_list else "None"
            
            log_lines.append(
                f"Cluster {c_id:02d} | Docs: {c_count:4d} ({c_share:4.1f}%) | "
                f"Mean Conf: {c_mean_conf:.2f} | Consensus: {c_consensus:3d} | Conflicts: {c_conflict:3d}\n"
                f"   • BERTopic Top Keywords: {b_kws}\n"
                f"   • GSDMM Top Keywords:    {g_kws}"
            )
            
        log_lines.extend([
            "=" * 80,
            "PIPELINE COMPLETED SUCCESSFULLY",
            "=" * 80
        ])
        
        report_text = "\n".join(log_lines)
        log_filename_base = f"thematic_stratification_{get_timestamp_str()}.log"
        log_filename = save_project_file("logs", log_filename_base, report_text)
            
        st.session_state.ts_last_log = report_text
        st.session_state.ts_last_log_file = log_filename
            
        st.success(f"Ensemble pipeline completed in {formatted_duration}! Log saved to `{log_filename}`.")

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
        mapping_entry = st.session_state.topic_mapping.get(u_id, {})
        b_id = mapping_entry.get('bertopic_id')
        g_ids = mapping_entry.get('gsdmm_ids', [])
        if not g_ids and mapping_entry.get('gsdmm_id') is not None:
            g_ids = [mapping_entry['gsdmm_id']]
        
        b_words = ", ".join(st.session_state.bert_words.get(b_id, [])) if b_id is not None else "N/A"
        
        g_words_list = []
        for g_id in g_ids:
            g_words_list.extend(st.session_state.gsdmm_words.get(g_id, []))
        seen = set()
        dedup_g_words = [w for w in g_words_list if not (w in seen or seen.add(w))]
        g_words = ", ".join(dedup_g_words) if dedup_g_words else "N/A"
        
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
        provider = st.selectbox("Provider", ["Gemini", "Groq (LLaMA 3)", "Anthropic (Claude)", "OpenAI", "Ollama (Local)", "None"])
    with g_col2:
        api_key = st.text_input("API Key (Stored locally only)", type="password")
        if provider == "Ollama (Local)":
            st.caption("Make sure Ollama is running on your machine.")
    with g_col3:
        if st.button("Generate Names for ALL Topics", width="stretch", type="primary"):
            if provider != "None" and api_key:
                with st.spinner("Batch generating all topic labels..."):
                    # Collect all topic keyword sets into a single dictionary
                    batch_payload = {}
                    for u_id in unified_ids:
                        mapping_entry = st.session_state.topic_mapping.get(u_id, {})
                        b_id_all = mapping_entry.get('bertopic_id')
                        g_ids_all = mapping_entry.get('gsdmm_ids', [])
                        if not g_ids_all and mapping_entry.get('gsdmm_id') is not None:
                            g_ids_all = [mapping_entry['gsdmm_id']]
                        
                        words_to_send = []
                        if b_id_all is not None: 
                            words_to_send.extend(st.session_state.bert_words.get(b_id_all, []))
                        for g_id in g_ids_all:
                            words_to_send.extend(st.session_state.gsdmm_words.get(g_id, []))
                        batch_payload[u_id] = list(set(words_to_send))
                    
                    # Make 1 single API call for all topics
                    batch_results = generate_batch_topic_names(api_key, provider, batch_payload)
                    
                    for u_id, res in batch_results.items():
                        st.session_state.topic_names[int(u_id)] = res
                        
                st.rerun()
            else:
                st.warning("Please provide an API key and select a provider.")
    
        
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
    
    mapping_info = st.session_state.topic_mapping.get(selected_topic, {})
    b_id = mapping_info.get('bertopic_id')
    g_ids = mapping_info.get('gsdmm_ids', [])
    if not g_ids and mapping_info.get('gsdmm_id') is not None:
        g_ids = [mapping_info['gsdmm_id']]
    
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        st.write("**BERTopic Keywords:**")
        if b_id is not None:
            st.write(", ".join(st.session_state.bert_words.get(b_id, [])))
        else:
            st.write("N/A")
            
    with t_col2:
        st.write("**GSDMM Keywords:**")
        g_words_list = []
        for g_id in g_ids:
            g_words_list.extend(st.session_state.gsdmm_words.get(g_id, []))
        seen = set()
        dedup_g_words = [w for w in g_words_list if not (w in seen or seen.add(w))]
        if dedup_g_words:
            st.write(", ".join(dedup_g_words))
        else:
            st.write("N/A")
            
    with g_col3:
        if st.button("Generate Name (Single)", width="stretch"):
            if provider != "None":
                words_to_send = []
                if b_id is not None: words_to_send.extend(st.session_state.bert_words.get(b_id, []))
                for g_id in g_ids:
                    words_to_send.extend(st.session_state.gsdmm_words.get(g_id, []))
                
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
        
    # Document Representatives & Borderline Audit
    st.subheader("📄 Cluster Document Audit: Most vs. Least Representative")
    st.caption("Inspect central documents (high confidence) versus boundary/borderline documents (lowest confidence) to assess cluster coherence.")
    
    topic_docs = st.session_state.ts_df[st.session_state.ts_df['unified_topic'] == selected_topic]
    
    if not topic_docs.empty:
        n_total_in_topic = len(topic_docs)
        sample_size = min(5, n_total_in_topic)
        most_rep = topic_docs.sort_values(by='topic_confidence', ascending=False).head(sample_size)
        least_rep = topic_docs.sort_values(by='topic_confidence', ascending=True).head(sample_size)
        
        rep_col1, rep_col2 = st.columns(2, gap="large")
        
        with rep_col1:
            st.markdown(f"##### 🎯 Most Representative (Core Documents - Top {sample_size})")
            for _, r in most_rep.iterrows():
                r_title = r.get('Title', 'Untitled Document')
                r_conf = r.get('topic_confidence', 0.0)
                r_year = r.get('Publication Year', r.get('Year', 'N/A'))
                r_doi = r.get('DOI', '')
                r_abstract = str(r.get('Abstract', 'No abstract available.'))
                if len(r_abstract) > 280:
                    r_abstract = r_abstract[:280] + "..."
                
                doi_link = f" • [DOI](https://doi.org/{r_doi})" if r_doi and str(r_doi).lower() != 'nan' else ""
                
                with st.container(border=True):
                    st.markdown(f"**{r_title}** ({r_year}){doi_link}")
                    st.caption(f"**Confidence:** `{r_conf:.2f}` | **Secondary Topic:** `{r.get('secondary_topic', 'None')}`")
                    st.markdown(f"<span style='color: #475569; font-size: 13px;'>{r_abstract}</span>", unsafe_allow_html=True)
                    
        with rep_col2:
            st.markdown(f"##### ⚠️ Least Representative (Boundary / Outlier Candidates - Bottom {sample_size})")
            for _, r in least_rep.iterrows():
                r_title = r.get('Title', 'Untitled Document')
                r_conf = r.get('topic_confidence', 0.0)
                r_year = r.get('Publication Year', r.get('Year', 'N/A'))
                r_doi = r.get('DOI', '')
                r_abstract = str(r.get('Abstract', 'No abstract available.'))
                if len(r_abstract) > 280:
                    r_abstract = r_abstract[:280] + "..."
                
                doi_link = f" • [DOI](https://doi.org/{r_doi})" if r_doi and str(r_doi).lower() != 'nan' else ""
                
                with st.container(border=True):
                    st.markdown(f"**{r_title}** ({r_year}){doi_link}")
                    st.caption(f"**Confidence:** `{r_conf:.2f}` | **Secondary Topic:** `{r.get('secondary_topic', 'None')}`")
                    st.markdown(f"<span style='color: #475569; font-size: 13px;'>{r_abstract}</span>", unsafe_allow_html=True)
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
    
    with st.expander("🔬 How BERTopic & GSDMM Discover Topics (Algorithmic Deep Dive)"):
        st.markdown("""
        ### 1. BERTopic (Semantic Density Clustering)
        * **Step 1 - Transformer Embeddings:** Documents (Title, Abstract, Keywords) are embedded into high-dimensional semantic vector spaces using Sentence-Transformers (`all-MiniLM-L6-v2`). Semantically related documents lie close to each other even if they share zero identical words.
        * **Step 2 - Manifold Dimensionality Reduction (UMAP):** Reduces high-dimensional embeddings down to low-dimensional manifolds while strictly preserving local neighborhoods and semantic clusters.
        * **Step 3 - Density-Based Clustering (HDBSCAN):** Groups dense regions into topic clusters. Documents in sparse, unclustered regions are labeled as **outliers (-1)** rather than forced into unnatural topics.
        * **Step 4 - Class-based TF-IDF (c-TF-IDF):** Treats all documents in cluster $c$ as a single long text and extracts the top distinguishing keywords:
        $$ W_{t,c} = tf_{t,c} \\times \\log \\left(1 + \\frac{A}{f_t} \\right) $$

        ---

        ### 2. GSDMM (Probabilistic Short-Text Dirichlet Mixture Model)
        * **The Movie-Group Metaphor:** Envisions $D$ students (documents) choosing among $K$ tables (topics). A student joins a table based on two probabilities:
          1. **Popularity (Rich-get-richer):** Tables with more students attract new students ($\alpha$ parameter).
          2. **Word Affinity:** Tables whose existing students share words with the new student's document attract that student ($\beta$ parameter).
        * **Collapsed Gibbs Sampling:** Iterates through documents, re-assigning each document to the table with maximum posterior probability until convergence.
        * **Why GSDMM?** Unlike classical LDA (which assumes each document is a blend of multiple topics), GSDMM assumes **one document $\\approx$ one primary topic**, making it mathematically optimal for short academic abstracts and conference titles.

        ---

        ### 3. Topic Alignment & Ensemble Consensus Scoring
        * **Consensus (Confidence = 1.00):** Both BERTopic (semantic) and GSDMM (word co-occurrence) independently assign the document to the same unified topic cluster. Highest reliability.
        * **Single-Model Valid (Confidence = 0.80):** One model clustered the document while the other flagged it as an outlier or novel sub-cluster. High confidence.
        * **Cross-Model Conflict (Confidence = 0.50):** The two models placed the document into different unified clusters. BERTopic serves as primary assignment, while GSDMM is captured as `secondary_topic` for audit.
        * **Complete Outlier (Confidence = 0.00):** Neither model found sufficient topical density (assigned to Topic -1).
        """)
        
    if 'ts_df' not in st.session_state:
        st.info("Please run the ensemble pipeline first.")
        return
        
    ts_df = st.session_state.ts_df
    
    total_docs = len(ts_df)
    outliers = ts_df[ts_df['unified_topic'] == -1].shape[0]
    avg_conf = ts_df['topic_confidence'].mean()
    
    # 1. Macro KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Average Confidence", f"{avg_conf:.2f}")
    with col2:
        st.metric("Total Documents", f"{total_docs:,}")
    with col3:
        st.metric("Outliers (-1)", f"{outliers:,}", f"{(outliers/total_docs*100):.1f}%", delta_color="inverse")
    with col4:
        n_clusters = len([t for t in ts_df['unified_topic'].unique() if t != -1])
        st.metric("Active Clusters", f"{n_clusters}")

    st.divider()

    # 2. Per-Cluster Statistical & Confidence Audit Table
    st.subheader("🔍 Per-Cluster Quality & Confidence Audit")
    st.caption("Detailed statistical evaluation of assignment reliability, consensus between BERTopic and GSDMM, and lexical overlap.")

    t_map = st.session_state.get('topic_mapping', {})
    b_words = st.session_state.get('bert_words', {})
    g_words = st.session_state.get('gsdmm_words', {})
    
    cluster_metrics_df = calculate_cluster_quality_metrics(ts_df, t_map, b_words, g_words)
    
    if not cluster_metrics_df.empty:
        # Add human-friendly AI Topic Name
        cluster_metrics_df['Topic Name'] = cluster_metrics_df['topic'].apply(get_topic_name)
        
        # Format table for high-readability audit
        display_audit_df = cluster_metrics_df[[
            'topic', 'Topic Name', 'doc_count', 'corpus_share_pct', 
            'mean_confidence', 'min_confidence', 'max_confidence',
            'consensus_rate_pct', 'keyword_overlap_jaccard',
            'bertopic_keywords', 'gsdmm_keywords'
        ]].copy()
        
        display_audit_df.columns = [
            'Cluster ID', 'Topic Name', 'Docs', 'Corpus %', 
            'Mean Conf', 'Min Conf', 'Max Conf', 
            'Consensus %', 'Keyword Jaccard',
            'BERTopic Top Keywords', 'GSDMM Top Keywords'
        ]
        
        # Color styling for confidence
        st.dataframe(
            display_audit_df.style.format({
                'Corpus %': '{:.1f}%',
                'Mean Conf': '{:.2f}',
                'Min Conf': '{:.2f}',
                'Max Conf': '{:.2f}',
                'Consensus %': '{:.1f}%',
                'Keyword Jaccard': '{:.2f}'
            }),
            width="stretch",
            hide_index=True
        )

        # Visual confidence bar chart
        import plotly.express as px
        fig_conf = px.bar(
            cluster_metrics_df,
            x='Topic Name',
            y='mean_confidence',
            color='mean_confidence',
            color_continuous_scale='Blues',
            text='mean_confidence',
            labels={'mean_confidence': 'Mean Confidence', 'Topic Name': 'Topic Cluster'},
            title="Cluster Assignment Reliability (Mean Confidence per Cluster)"
        )
        fig_conf.update_traces(texttemplate='%{text:.2f}', textposition='outside')
        fig_conf.update_layout(yaxis=dict(range=[0, 1.1]), height=380, margin=dict(t=40, b=40, l=20, r=20))
        st.plotly_chart(fig_conf, width="stretch")

    st.divider()

    # 3. View and Download Auditable Execution Log
    st.subheader("📋 Auditable Execution Log")
    st.caption("Complete timestamped ledger of preprocessing parameters, model convergence, topic alignment pairs, and per-cluster distributions.")
    
    last_log = st.session_state.get('ts_last_log', '')
    log_file_path = st.session_state.get('ts_last_log_file', '')
    
    if last_log:
        with st.expander("📄 View Full Audit Log Text", expanded=False):
            st.code(last_log, language="text")
            
        c_dl1, c_dl2 = st.columns([1.5, 2])
        with c_dl1:
            st.download_button(
                label="📥 Download Audit Log (.log)",
                data=last_log.encode('utf-8'),
                file_name=os.path.basename(log_file_path) if log_file_path else "thematic_stratification_audit.log",
                mime="text/plain",
                type="secondary",
                width="stretch"
            )
    else:
        st.info("Audit log will appear here once the ensemble stratification pipeline has been executed.")
    st.write("### Data Export")
    st.write("You can download the full enriched dataset with unified topics, secondary topics, and confidence scores attached.")
    
    csv = ts_df.to_csv(index=False).encode('utf-8')
    fn_strat_csv = format_timestamped_filename('bibliometric_stratified_results.csv')
    try: save_project_file("exports", fn_strat_csv, csv, mode="wb")
    except Exception: pass
    
    st.download_button(
        label="Download Final Dataset as CSV",
        data=csv,
        file_name=fn_strat_csv,
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
    fn_strat_sess = format_timestamped_filename('stratification_session.json')
    try: save_project_file("sessions", fn_strat_sess, json_bytes, mode="wb")
    except Exception: pass
    
    st.download_button(
        label="Export Session State (.json)",
        data=json_bytes,
        file_name=fn_strat_sess,
        mime='application/json',
    )
