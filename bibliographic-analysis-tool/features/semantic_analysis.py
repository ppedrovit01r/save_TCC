import streamlit as st
import pandas as pd
import networkx as nx
import nltk
from collections import Counter
from nltk.corpus import stopwords
from pyvis.network import Network
from pathlib import Path
import streamlit.components.v1 as components

from utils.exports import safe_download

DARK_BG = "#222222"
DARK_FONT = "#ffffff"

def display_metrics_summary(df):
    fields = ["Title", "Keywords", "Abstract"]
    summary = []
    total_articles = len(df)
    for fld in fields:
        present = df[fld].notna().sum() if fld in df.columns else 0
        missing = total_articles - present
        summary.append({
            "Field": fld, 
            "Total Present": present, 
            "Missing": missing, 
            "% Missing": f"{missing/total_articles*100:.2f}%"
        })
    
    st.dataframe(pd.DataFrame(summary).style.set_table_styles([
        {"selector": "thead", "props": [("background-color", "#111111"), ("color", DARK_FONT)]}, 
        {"selector": "td", "props": [("background-color", "#222222"), ("color", DARK_FONT)]}
    ]))

def display_coword_analysis(df):
    st.subheader("Co-Word Analysis (Focus Word)")
    display_metrics_summary(df)
    
    focus_word = st.text_input("Focus Word", value="future").lower()
    fields = st.multiselect(
        "Select fields to include", 
        ["Title", "Keywords", "Abstract"], 
        default=["Title", "Keywords", "Abstract"]
    )
    top_n = st.slider("Top N co-words", 5, 100, 20, step=5)

    if not focus_word:
        st.info("Enter a focus word to start the analysis.")
        return
    if not fields:
        st.warning("Select at least one field.")
        return
        
    display_coword_graph(focus_word, fields, df, top_n)

def display_coword_graph(focus_word, fields, df, top_n):
    try:
        nltk.data.find("corpora/stopwords")
    except LookupError:
        with st.spinner("Downloading NLTK stopwords..."):
            nltk.download("stopwords")
            
    stop_words = set(stopwords.words("english"))
    text_series = df[fields].fillna("").agg(" ".join, axis=1).str.lower()
    subset = text_series[text_series.str.contains(focus_word, regex=False)]
    
    if subset.empty:
        st.info(f"No occurrences of '{focus_word}' found in the selected fields.")
        return

    token_lists = [[w for w in txt.split() if w.isalpha() and w not in stop_words] for txt in subset]
    co_counter = Counter()
    for tokens in token_lists:
        co_counter.update(set(tokens) - {focus_word})
        
    if not co_counter:
        st.info("No co-words found with current parameters.")
        return

    top_words = dict(co_counter.most_common(top_n))
    G = nx.Graph()
    G.add_node(focus_word, size=30)
    for w, cnt in top_words.items():
        G.add_node(w, size=10 + cnt)
        G.add_edge(focus_word, w, weight=cnt)

    G_vis = Network(height="600px", width="100%", bgcolor=DARK_BG, font_color=DARK_FONT)
    for node in G.nodes():
        G_vis.add_node(
            node, 
            label=node, 
            title=node if node == focus_word else f"{node} ({co_counter[node]}x)", 
            size=G.nodes[node]["size"]
        )
    for u, v, data in G.edges(data=True):
        G_vis.add_edge(u, v, value=data["weight"])

    html_path = Path("co_word_graph.html")
    G_vis.save_graph(str(html_path))
    with html_path.open("r", encoding="utf-8") as f:
        html = f.read()

    components.html(html, height=600)
    safe_download(
        st.download_button, 
        "Download Graph", 
        html, 
        "co_word_graph.html", 
        "text/html", 
        key="coword_download"
    )