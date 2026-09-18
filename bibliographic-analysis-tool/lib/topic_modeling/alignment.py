import numpy as np

def calculate_jaccard(list1, list2):
    """Calculate Jaccard similarity between two lists of elements."""
    set1, set2 = set(list1), set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0

def align_topics(doc_bert_topics, doc_gsdmm_topics, bertopic_words, gsdmm_words, similarity_threshold=0.20, min_topic_size=2):
    """
    Align topics using a Consensus-Centric Many-to-One architecture where BERTopic is the leader.
    Every GSDMM topic is mapped to its best-matching BERTopic leader cluster using a hybrid metric:
    document overlap (60%) + keyword vocabulary overlap (40%).
    GSDMM acts as the lexical validation lens; no orphan GSDMM-only topics are created.
    """
    bert_ids = list(bertopic_words.keys())
    gsdmm_ids = list(gsdmm_words.keys())
    
    # Map topics to sets of document indices for overlap calculation
    bert_docs = {b_id: set() for b_id in bert_ids}
    gsdmm_docs = {g_id: set() for g_id in gsdmm_ids}
    
    for idx, b_topic in enumerate(doc_bert_topics):
        if b_topic in bert_docs:
            bert_docs[b_topic].add(idx)
            
    for idx, g_topic in enumerate(doc_gsdmm_topics):
        if g_topic in gsdmm_docs:
            gsdmm_docs[g_topic].add(idx)
            
    unified_mapping = {}
    bert_to_unified = {}
    gsdmm_to_unified = {}
    
    unified_id = 0
    
    # Step 1: Every BERTopic becomes a unified macro-topic (Leader)
    for b_id in bert_ids:
        bert_to_unified[b_id] = unified_id
        unified_mapping[unified_id] = {
            'bertopic_id': b_id,
            'gsdmm_ids': [],
            'gsdmm_id': None,
            'similarities': []
        }
        unified_id += 1
        
    # Step 2: Map every GSDMM cluster to its best-matching BERTopic leader cluster
    for g_id in gsdmm_ids:
        best_b_id = None
        best_sim = -1.0
        
        for b_id in bert_ids:
            doc_sim = calculate_jaccard(list(bert_docs[b_id]), list(gsdmm_docs[g_id]))
            word_sim = calculate_jaccard(bertopic_words.get(b_id, []), gsdmm_words.get(g_id, []))
            combined_sim = 0.6 * doc_sim + 0.4 * word_sim
            
            if combined_sim > best_sim:
                best_sim = combined_sim
                best_b_id = b_id
                
        # Consolidate into the best leader topic (never spawn orphan split topics)
        if best_b_id is not None:
            u_id = bert_to_unified[best_b_id]
            gsdmm_to_unified[g_id] = u_id
            unified_mapping[u_id]['gsdmm_ids'].append(g_id)
            if unified_mapping[u_id].get('gsdmm_id') is None:
                unified_mapping[u_id]['gsdmm_id'] = g_id
            unified_mapping[u_id]['similarities'].append(round(max(0.0, best_sim), 4))
        else:
            gsdmm_to_unified[g_id] = -1
            
    return bert_to_unified, gsdmm_to_unified, unified_mapping

def assign_unified_topics(
    doc_bert_topics, 
    doc_gsdmm_topics, 
    bert_to_unified, 
    gsdmm_to_unified, 
    unified_mapping=None, 
    doc_embeddings=None, 
    min_confidence=0.50, 
    min_topic_size=2
):
    """
    Two-Pass Consensus-Driven Topic Assignment & Refinement Pipeline:
      Pass 1: Detects pure Consensus Core documents (both models 100% agree).
      Pass 2: Constructs high-purity topic centroids from consensus cores and uses
              semantic embedding similarity to assertively resolve boundary and ambiguous documents.
    Returns: (unified_topics, confidences, secondary_topics, is_consensus_list)
    """
    n_docs = len(doc_bert_topics)
    unified_topics = [-1] * n_docs
    confidences = [0.0] * n_docs
    secondary_topics = [None] * n_docs
    is_consensus = [False] * n_docs
    
    # --- PASS 1: Identify Consensus Cores & Initial Assignments ---
    for i in range(n_docs):
        b_topic = doc_bert_topics[i]
        g_topic = doc_gsdmm_topics[i]
        b_uni = bert_to_unified.get(b_topic, -1)
        g_uni = gsdmm_to_unified.get(g_topic, -1)
        
        if b_uni == g_uni and b_uni != -1:
            # Full Consensus: Both models agree on this macro-theme
            unified_topics[i] = b_uni
            confidences[i] = 1.0
            secondary_topics[i] = None
            is_consensus[i] = True
        elif b_uni != -1 and g_uni != -1:
            # Divergence: Models placed document in different clusters
            unified_topics[i] = b_uni
            confidences[i] = 0.65
            secondary_topics[i] = g_uni
            is_consensus[i] = False
        elif b_uni != -1:
            # BERTopic-only valid
            unified_topics[i] = b_uni
            confidences[i] = 0.85
            secondary_topics[i] = None
            is_consensus[i] = False
        elif g_uni != -1:
            # GSDMM-only valid
            unified_topics[i] = g_uni
            confidences[i] = 0.75
            secondary_topics[i] = None
            is_consensus[i] = False
        else:
            unified_topics[i] = -1
            confidences[i] = 0.0
            secondary_topics[i] = None
            is_consensus[i] = False

    # --- PASS 2: Centroid-Based Boundary & Ambiguity Inference ---
    if doc_embeddings is not None and len(doc_embeddings) == n_docs:
        embeddings = np.array(doc_embeddings, dtype=np.float32)
        # Normalize document embeddings
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        norm_embeddings = embeddings / norms
        
        active_u_ids = sorted(list(set(t for t in unified_topics if t != -1)))
        
        # Build consensus centroid for each active topic
        centroids = {}
        for u_id in active_u_ids:
            # Prefer consensus core documents to build high-purity centroid
            core_indices = [idx for idx in range(n_docs) if is_consensus[idx] and unified_topics[idx] == u_id]
            if len(core_indices) >= 2:
                cent = np.mean(norm_embeddings[core_indices], axis=0)
            else:
                # Fallback to all documents assigned to this topic
                all_indices = [idx for idx in range(n_docs) if unified_topics[idx] == u_id]
                cent = np.mean(norm_embeddings[all_indices], axis=0) if all_indices else None
                
            if cent is not None:
                c_norm = np.linalg.norm(cent)
                if c_norm > 0:
                    centroids[u_id] = cent / c_norm
                    
        # Re-evaluate all non-consensus documents against consensus centroids
        if centroids:
            c_keys = list(centroids.keys())
            c_matrix = np.array([centroids[k] for k in c_keys], dtype=np.float32) # (K, dim)
            
            for idx in range(n_docs):
                if not is_consensus[idx] and unified_topics[idx] != -1:
                    doc_vec = norm_embeddings[idx] # (dim,)
                    sims = np.dot(c_matrix, doc_vec) # (K,)
                    
                    best_k_idx = int(np.argmax(sims))
                    best_sim = float(sims[best_k_idx])
                    best_target_u_id = c_keys[best_k_idx]
                    
                    cur_u_id = unified_topics[idx]
                    cur_k_idx = c_keys.index(cur_u_id) if cur_u_id in c_keys else -1
                    cur_sim = float(sims[cur_k_idx]) if cur_k_idx != -1 else 0.0
                    
                    # If document is well-aligned with leader assignment: boost confidence
                    if cur_sim >= 0.30:
                        confidences[idx] = round(min(0.92, max(0.70, float(0.50 + 0.50 * cur_sim))), 2)
                    elif best_sim > cur_sim + 0.15:
                        # Centroid shows much stronger alignment with alternative topic
                        secondary_topics[idx] = cur_u_id
                        unified_topics[idx] = best_target_u_id
                        confidences[idx] = round(min(0.85, max(0.65, float(0.40 + 0.50 * best_sim))), 2)
                    else:
                        # True interdisciplinary boundary document
                        confidences[idx] = 0.60
                        
    # --- ENFORCE MIN_CONFIDENCE THRESHOLD ---
    for i in range(n_docs):
        if confidences[i] < min_confidence:
            unified_topics[i] = -1
            confidences[i] = 0.0
            secondary_topics[i] = None
            is_consensus[i] = False
            
    # --- ENFORCE MIN_TOPIC_SIZE THRESHOLD ---
    if min_topic_size is not None and min_topic_size > 1:
        topic_counts = {}
        for u_id in unified_topics:
            if u_id != -1:
                topic_counts[u_id] = topic_counts.get(u_id, 0) + 1
                
        invalid_topics = {u_id for u_id, count in topic_counts.items() if count < min_topic_size}
        for i in range(n_docs):
            if unified_topics[i] in invalid_topics:
                unified_topics[i] = -1
                confidences[i] = 0.0
                secondary_topics[i] = None
                is_consensus[i] = False
                
    return unified_topics, confidences, secondary_topics, is_consensus
