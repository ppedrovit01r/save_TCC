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
