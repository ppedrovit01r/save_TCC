import numpy as np

def calculate_jaccard(list1, list2):
    """Calculate Jaccard similarity between two lists of elements."""
    set1, set2 = set(list1), set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0

def align_topics(doc_bert_topics, doc_gsdmm_topics, bertopic_words, gsdmm_words, similarity_threshold=0.20, min_topic_size=2):
    """
    Align topics using a Many-to-Many logic where BERTopic is the leader.
    GSDMM topics map to the BERTopic they share the most documents with.
    If they do not meet the similarity_threshold with ANY BERTopic, they become their own unified topic
    only if they meet the min_topic_size threshold; otherwise, they merge into the nearest BERTopic.
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
            
    unified_mapping = {}
    bert_to_unified = {}
    gsdmm_to_unified = {}
    
    unified_id = 0
    
    # Step 1: Every BERTopic becomes a unified topic (Leader)
    for b_id in bert_ids:
        bert_to_unified[b_id] = unified_id
        unified_mapping[unified_id] = {
            'bertopic_id': b_id,
            'gsdmm_ids': [], # Now a list to support many-to-one
            'gsdmm_id': None, # For backwards compatibility
            'similarities': []
        }
        unified_id += 1
        
    # Step 2: For each GSDMM topic, find the best matching BERTopic
    for g_id in gsdmm_ids:
        best_b_id = None
        best_sim = -1
        
        for b_id in bert_ids:
            sim = calculate_jaccard(list(bert_docs[b_id]), list(gsdmm_docs[g_id]))
            if sim > best_sim:
                best_sim = sim
                best_b_id = b_id
                
        g_size = len(gsdmm_docs[g_id])
        
        # If the best match meets the threshold, merge it into that Unified Topic
        if best_sim >= similarity_threshold and best_b_id is not None:
            u_id = bert_to_unified[best_b_id]
            gsdmm_to_unified[g_id] = u_id
            unified_mapping[u_id]['gsdmm_ids'].append(g_id)
            if unified_mapping[u_id].get('gsdmm_id') is None:
                unified_mapping[u_id]['gsdmm_id'] = g_id
            unified_mapping[u_id]['similarities'].append(best_sim)
        elif g_size < min_topic_size and best_b_id is not None:
            # Prevent micro-topics: if GSDMM cluster is smaller than min_topic_size,
            # merge it into the closest BERTopic cluster rather than creating a micro-topic
            u_id = bert_to_unified[best_b_id]
            gsdmm_to_unified[g_id] = u_id
            unified_mapping[u_id]['gsdmm_ids'].append(g_id)
            if unified_mapping[u_id].get('gsdmm_id') is None:
                unified_mapping[u_id]['gsdmm_id'] = g_id
            unified_mapping[u_id]['similarities'].append(max(0.0, best_sim))
        else:
            # If it doesn't match any BERTopic well
            if g_size >= min_topic_size:
                # Becomes its own independent unified topic
                gsdmm_to_unified[g_id] = unified_id
                unified_mapping[unified_id] = {
                    'bertopic_id': None,
                    'gsdmm_ids': [g_id],
                    'gsdmm_id': g_id,
                    'similarities': [1.0] # It is itself
                }
                unified_id += 1
            else:
                # It is too small and matches nothing, so it becomes an outlier
                gsdmm_to_unified[g_id] = -1
            
    return bert_to_unified, gsdmm_to_unified, unified_mapping

def assign_unified_topics(doc_bert_topics, doc_gsdmm_topics, bert_to_unified, gsdmm_to_unified, min_confidence=0.70, min_topic_size=2):
    """
    Assign a unified topic to each document based on the many-to-many alignment.
    Calculates assignment confidence.
    Enforces min_confidence (documents below this become outliers).
    Enforces min_topic_size (topics with fewer documents become outliers).
    """
    unified_topics = []
    confidences = []
    secondary_topics = []
    
    for b_topic, g_topic in zip(doc_bert_topics, doc_gsdmm_topics):
        b_uni = bert_to_unified.get(b_topic, -1)
        g_uni = gsdmm_to_unified.get(g_topic, -1)
        
        if b_uni == g_uni and b_uni != -1:
            # Full consensus! Both models placed the document in sub-topics that belong to the same unified topic
            u_id = b_uni
            conf = 1.0
            sec = None
        elif b_uni != -1 and g_uni != -1:
            # Conflict: they mapped to different unified topics.
            # BERTopic leads, so it's the primary assignment. GSDMM is secondary.
            u_id = b_uni
            conf = 0.5
            sec = g_uni
        elif b_uni != -1:
            # Only BERTopic is valid
            u_id = b_uni
            conf = 0.8
            sec = None
        elif g_uni != -1:
            # Only GSDMM is valid (e.g. BERTopic was -1 outlier, but GSDMM found a cluster)
            u_id = g_uni
            conf = 0.8
            sec = None
        else:
            # Complete outlier
            u_id = -1
            conf = 0.0
            sec = None
            
        # Enforce minimum confidence
        if conf < min_confidence:
            u_id = -1
            conf = 0.0
            sec = None
            
        unified_topics.append(u_id)
        confidences.append(conf)
        secondary_topics.append(sec)
        
    # Post-process to enforce min_topic_size
    if min_topic_size is not None and min_topic_size > 1:
        topic_counts = {}
        for u_id in unified_topics:
            if u_id != -1:
                topic_counts[u_id] = topic_counts.get(u_id, 0) + 1
                
        # Find which topics fail the size check
        invalid_topics = {u_id for u_id, count in topic_counts.items() if count < min_topic_size}
        
        for i in range(len(unified_topics)):
            if unified_topics[i] in invalid_topics:
                unified_topics[i] = -1
                confidences[i] = 0.0
                secondary_topics[i] = None
                
    return unified_topics, confidences, secondary_topics
