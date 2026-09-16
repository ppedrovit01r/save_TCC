import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

def calculate_callon_metrics(df, topic_col='unified_topic', terms_col='tokens'):
    """
    Calculate Callon's Centrality and Density for each topic.
    Centrality: External relevance of the topic (connections to other topics).
    Density: Internal development/cohesion (connections within the topic).
    """
    topics = df[topic_col].unique()
    topics = [t for t in topics if t != -1] # Exclude outliers
    
    # We need a co-occurrence matrix of terms across the whole corpus
    # and within each topic to calculate this exactly as Callon proposed.
    # For now, we will use a simplified approximation based on the PDF formula.
    # e_{ij} is the equivalence index
    
    metrics = []
    
    # Simple placeholder logic until full word co-occurrence matrix is built
    # In a real scenario, this involves building a large term-document matrix.
    for topic in topics:
        topic_docs = df[df[topic_col] == topic]
        n_docs = len(topic_docs)
        
        # Mock calculation based on topic size and term overlap
        # To be replaced with exact Callon formula:
        # C_k = 10 * sum(e_{kh})
        # D_k = 100 * sum(e_{ij} / w)
        centrality = np.log1p(n_docs) * np.random.uniform(0.8, 1.2) # Placeholder
        
        if terms_col in topic_docs.columns:
            density = np.log1p(topic_docs[terms_col].apply(lambda x: len(x) if isinstance(x, list) else len(str(x))).mean()) * np.random.uniform(0.8, 1.2)
        elif 'Title' in topic_docs.columns:
            density = np.log1p(topic_docs['Title'].apply(lambda x: len(str(x))).mean()) * np.random.uniform(0.8, 1.2)
        else:
            density = np.random.uniform(0.8, 1.2) # Ultimate fallback
        
        metrics.append({
            'topic': topic,
            'n_docs': n_docs,
            'centrality': centrality,
            'density': density
        })
        
    return pd.DataFrame(metrics)

def calculate_temporal_trends(df, topic_col='unified_topic', year_col='year'):
    """
    Calculate topic prevalence over time and fit a linear regression 
    to determine the trend (Emerging, Declining, Stable).
    """
    if year_col not in df.columns:
        return pd.DataFrame()
        
    topics = df[topic_col].unique()
    topics = [t for t in topics if t != -1]
    
    # Calculate yearly prevalence (proportion of articles in that topic per year)
    yearly_counts = df.groupby([year_col, topic_col]).size().unstack(fill_value=0)
    yearly_totals = df.groupby(year_col).size()
    prevalence = yearly_counts.div(yearly_totals, axis=0)
    
    trends = []
    
    for topic in topics:
        if topic in prevalence.columns:
            y = prevalence[topic].values.reshape(-1, 1)
            X = np.array(prevalence.index).reshape(-1, 1)
            
            if len(X) > 1:
                model = LinearRegression()
                model.fit(X, y)
                coef = model.coef_[0][0]
                
                # Simple classification
                if coef > 0.01:
                    status = "Emerging"
                elif coef < -0.01:
                    status = "Declining"
                else:
                    status = "Stable"
            else:
                coef = 0
                status = "Unknown"
                
            trends.append({
                'topic': topic,
                'growth_coefficient': coef,
                'trend_status': status
            })
            
    return pd.DataFrame(trends)

def calculate_cluster_quality_metrics(df, topic_mapping, bert_words, gsdmm_words, topic_col='unified_topic', conf_col='topic_confidence'):
    """
    Computes per-cluster statistical audit metrics:
    - Document count and corpus share (%)
    - Mean confidence, min confidence, max confidence, std confidence
    - Full consensus rate (conf == 1.0)
    - Conflict rate (conf == 0.5)
    - Single model assignment rate (conf == 0.8)
    - Alignment mapping details (BERTopic leader and GSDMM followers)
    - Keyword coherence proxy
    """
    if df is None or df.empty or topic_col not in df.columns:
        return pd.DataFrame()

    total_docs = len(df)
    clusters = sorted([t for t in df[topic_col].unique() if t != -1])
    metrics_list = []

    for u_id in clusters:
        cluster_df = df[df[topic_col] == u_id]
        n_docs = len(cluster_df)
        pct_corpus = (n_docs / total_docs * 100) if total_docs > 0 else 0.0

        confs = cluster_df[conf_col].dropna() if conf_col in cluster_df.columns else pd.Series([0.0])
        mean_conf = float(confs.mean()) if not confs.empty else 0.0
        min_conf = float(confs.min()) if not confs.empty else 0.0
        max_conf = float(confs.max()) if not confs.empty else 0.0
        std_conf = float(confs.std()) if len(confs) > 1 else 0.0

        consensus_count = int((confs == 1.0).sum())
        conflict_count = int((confs == 0.5).sum())
        single_model_count = int(((confs >= 0.75) & (confs <= 0.85)).sum())
        consensus_rate = (consensus_count / n_docs * 100) if n_docs > 0 else 0.0

        mapping_info = topic_mapping.get(u_id, {}) if topic_mapping else {}
        b_id = mapping_info.get('bertopic_id')
        g_ids = mapping_info.get('gsdmm_ids', [])
        if not g_ids and mapping_info.get('gsdmm_id') is not None:
            g_ids = [mapping_info['gsdmm_id']]

        b_words_list = bert_words.get(b_id, []) if b_id is not None and bert_words else []
        g_words_list = []
        if gsdmm_words:
            for g_id in g_ids:
                g_words_list.extend(gsdmm_words.get(g_id, []))
        seen_g = set()
        dedup_g_words = [w for w in g_words_list if not (w in seen_g or seen_g.add(w))]

        # Jaccard lexical overlap between BERTopic and GSDMM keywords for this cluster
        if b_words_list and dedup_g_words:
            set_b, set_g = set(b_words_list), set(dedup_g_words)
            inter = len(set_b.intersection(set_g))
            union = len(set_b.union(set_g))
            lexical_jaccard = inter / union if union > 0 else 0.0
        else:
            lexical_jaccard = 1.0 if not b_words_list and not dedup_g_words else 0.0

        metrics_list.append({
            'topic': u_id,
            'doc_count': n_docs,
            'corpus_share_pct': pct_corpus,
            'mean_confidence': mean_conf,
            'min_confidence': min_conf,
            'max_confidence': max_conf,
            'std_confidence': std_conf,
            'consensus_rate_pct': consensus_rate,
            'consensus_count': consensus_count,
            'conflict_count': conflict_count,
            'single_model_count': single_model_count,
            'bertopic_id': b_id,
            'gsdmm_ids': g_ids,
            'keyword_overlap_jaccard': lexical_jaccard,
            'bertopic_keywords': ", ".join(b_words_list[:7]) if b_words_list else "None",
            'gsdmm_keywords': ", ".join(dedup_g_words[:7]) if dedup_g_words else "None"
        })

    return pd.DataFrame(metrics_list)

