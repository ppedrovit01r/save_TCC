import numpy as np
import pandas as pd
from bertopic import BERTopic
import tomotopy as tp
import nltk
from nltk.corpus import stopwords
import string

def preprocess_for_gsdmm(texts):
    """
    Preprocess texts specifically for GSDMM (Bag of Words).
    Requires tokenization and stopword removal.
    """
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)
        
    stop_words = set(stopwords.words("english")).union(set(stopwords.words("portuguese")))
    custom_stopwords = {"sobre", "estudo", "uso", "artigo", "paper", "study", "using", "results", "analysis"}
    stop_words = stop_words.union(custom_stopwords)
    tokenized_docs = []
    for text in texts:
        if pd.isna(text):
            tokenized_docs.append([])
            continue
            
        # Lowercase and remove punctuation
        text = text.lower().translate(str.maketrans('', '', string.punctuation))
        tokens = [w for w in text.split() if w.isalpha() and w not in stop_words and len(w) > 2]
        tokenized_docs.append(tokens)
        
    return tokenized_docs

from sklearn.feature_extraction.text import CountVectorizer

def run_bertopic(docs, min_topic_size=15, nr_topics=None):
    """
    Run BERTopic on the provided documents.
    """
    # Fill NAs
    docs = [str(d) if pd.notna(d) else "" for d in docs]
    
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        nltk.download("stopwords", quiet=True)
        
    stop_words = list(stopwords.words("english")) + list(stopwords.words("portuguese"))
    
    # Optional: also remove very common generic academic words if they still show up
    custom_stopwords = ["sobre", "estudo", "uso", "artigo", "paper", "study", "using", "results", "analysis"]
    stop_words.extend(custom_stopwords)
    
    vectorizer_model = CountVectorizer(stop_words=stop_words)
    
    if nr_topics is not None:
        # Lower minimum topic size to allow enough initial fragmentation for reduce_topics to work
        min_topic_size = 5
        topic_model = BERTopic(min_topic_size=min_topic_size, nr_topics=nr_topics, vectorizer_model=vectorizer_model)
    else:
        topic_model = BERTopic(min_topic_size=min_topic_size, vectorizer_model=vectorizer_model)
        
    topics, probs = topic_model.fit_transform(docs)
    
    # Extract top words for each topic
    topic_info = topic_model.get_topic_info()
    topic_words = {}
    for topic_id in topic_info['Topic']:
        if topic_id != -1:
            words = [word for word, _ in topic_model.get_topic(topic_id)]
            topic_words[topic_id] = words
            
    return topic_model, topics, probs, topic_words

from .gsdmm_mgp import MovieGroupProcess

def run_gsdmm(tokenized_docs, k=15, alpha=0.1, beta=0.1, iter=30):
    """
    Run GSDMM using the local MovieGroupProcess implementation.
    """
    # Filter empty docs
    valid_doc_indices = []
    valid_docs = []
    for i, doc in enumerate(tokenized_docs):
        if len(doc) > 0:
            valid_docs.append(doc)
            valid_doc_indices.append(i)
            
    # Build vocabulary
    vocab = set(x for doc in valid_docs for x in doc)
    n_terms = len(vocab)
            
    model = MovieGroupProcess(K=k, alpha=alpha, beta=beta, n_iters=iter)
    doc_assignments = model.fit(valid_docs, n_terms)
    
    # Retrieve topic assignments
    doc_topics = [-1] * len(tokenized_docs)
    doc_probs = [0.0] * len(tokenized_docs)
    
    for i, topic_id in enumerate(doc_assignments):
        original_idx = valid_doc_indices[i]
        doc_topics[original_idx] = topic_id
        
        # Calculate pseudo-probability based on score
        score = model.score(valid_docs[i])
        # Find best topic probability (rough approximation)
        best_prob = np.exp(score[topic_id]) / sum(np.exp(score))
        doc_probs[original_idx] = best_prob
        
    # Extract top words for each topic, skip empty ones
    topic_words = {}
    for k_id in range(k):
        # Sort words in topic by frequency
        word_counts = model.cluster_word_distribution[k_id]
        if not word_counts:
            continue # Completely skip empty clusters
        sorted_words = sorted(word_counts.keys(), key=lambda w: word_counts[w], reverse=True)
        topic_words[k_id] = sorted_words[:10]
        
    return model, doc_topics, doc_probs, topic_words
