import numpy as np
from scipy.optimize import linear_sum_assignment

def calculate_jaccard(list1, list2):
    """Calculate Jaccard similarity between two lists of words."""
    set1, set2 = set(list1), set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0

def align_topics(doc_bert_topics, doc_gsdmm_topics, bertopic_words, gsdmm_words):
    """
    Align topics from BERTopic and GSDMM using the Hungarian Algorithm based on Document Overlap similarity.
    Returns a mapping from BERTopic ID to Unified Topic ID, and GSDMM ID to Unified Topic ID.
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
    
    n_bert = len(bert_ids)
    n_gsdmm = len(gsdmm_ids)
    
    # Pad to make square matrix if dimensions differ
    dim = max(n_bert, n_gsdmm)
    cost_matrix = np.zeros((dim, dim))
    
    for i in range(dim):
        for j in range(dim):
            if i < n_bert and j < n_gsdmm:
                # Calculate Jaccard similarity based on shared documents instead of words
                b_id = bert_ids[i]
                g_id = gsdmm_ids[j]
                sim = calculate_jaccard(list(bert_docs[b_id]), list(gsdmm_docs[g_id]))
                
                # We want to maximize similarity, so we minimize negative similarity
                cost_matrix[i, j] = -sim
            else:
                # High cost for dummy nodes
                cost_matrix[i, j] = 0.0
                
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    # Create the unified mapping
    unified_mapping = {}
    bert_to_unified = {}
    gsdmm_to_unified = {}
    
    unified_id = 0
    for r, c in zip(row_ind, col_ind):
        # Only map real topics
        if r < n_bert and c < n_gsdmm:
            b_id = bert_ids[r]
            g_id = gsdmm_ids[c]
            
            bert_to_unified[b_id] = unified_id
            gsdmm_to_unified[g_id] = unified_id
            
            unified_mapping[unified_id] = {
                'bertopic_id': b_id,
                'gsdmm_id': g_id,
                'similarity': -cost_matrix[r, c] # Convert back to positive similarity
            }
            unified_id += 1
            
    # Handle unaligned topics (if any)
    for b_id in bert_ids:
        if b_id not in bert_to_unified:
            bert_to_unified[b_id] = unified_id
            unified_mapping[unified_id] = {'bertopic_id': b_id, 'gsdmm_id': None, 'similarity': 0.0}
            unified_id += 1
            
    for g_id in gsdmm_ids:
        if g_id not in gsdmm_to_unified:
            gsdmm_to_unified[g_id] = unified_id
            unified_mapping[unified_id] = {'bertopic_id': None, 'gsdmm_id': g_id, 'similarity': 0.0}
            unified_id += 1

    return bert_to_unified, gsdmm_to_unified, unified_mapping

def assign_unified_topics(doc_bert_topics, doc_gsdmm_topics, bert_to_unified, gsdmm_to_unified):
    """
    Assign a unified topic to each document based on the alignment.
    Calculates assignment confidence.
    """
    unified_topics = []
    confidences = []
    secondary_topics = []
    
    for b_topic, g_topic in zip(doc_bert_topics, doc_gsdmm_topics):
        b_uni = bert_to_unified.get(b_topic, -1)
        g_uni = gsdmm_to_unified.get(g_topic, -1)
        
        if b_uni == g_uni and b_uni != -1:
            # Full consensus
            unified_topics.append(b_uni)
            confidences.append(1.0)
            secondary_topics.append(None)
        elif b_uni != -1 and g_uni != -1:
            # Conflict: default to BERTopic as primary, GSDMM as secondary, lower confidence
            unified_topics.append(b_uni)
            confidences.append(0.5)
            secondary_topics.append(g_uni)
        elif b_uni != -1:
            # Only BERTopic
            unified_topics.append(b_uni)
            confidences.append(0.8)
            secondary_topics.append(None)
        elif g_uni != -1:
            # Only GSDMM
            unified_topics.append(g_uni)
            confidences.append(0.8)
            secondary_topics.append(None)
        else:
            # Outlier
            unified_topics.append(-1)
            confidences.append(0.0)
            secondary_topics.append(None)
            
    return unified_topics, confidences, secondary_topics
