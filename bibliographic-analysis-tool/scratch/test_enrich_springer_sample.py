import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import io
from core.ingestion import normalize_columns
from core.enrichment import enrich_dataset_openalex

# Mock Streamlit to run outside browser
import streamlit as st

csv_data = """Item Title,Publication Title,Book Series Title,Journal Volume,Journal Issue,Item DOI,Authors,Publication Year,URL,Content Type
"Mapping the evolution of cloud computing, AI, and business process performance in SMEs: a bibliometric analysis",Humanities and Social Sciences Communications,,,,10.1057/s41599-026-07403-9,Chaudhry Saeed AhmadAnuar Shah Bali MahomedHaslinda Hashim,2026,https://link.springer.com/article/10.1057/s41599-026-07403-9,Article
Digital transformation and entrepreneurship in Vietnam: navigating challenges and policy impacts,Journal of Global Entrepreneurship Research,,,,10.1007/s40497-026-00530-2,Sean WattsMuhammad Saqib IqbalZulhasni Abdul Rahim,2026,https://link.springer.com/article/10.1007/s40497-026-00530-2,Article
Pathways to digital entrepreneurship adoption among Malaysian SMEs: Analysing the determinants and technology readiness dynamics,Journal of International Entrepreneurship,,,,10.1007/s10843-025-00403-x,Taofeek Adeyemi SangosanyaSri Sarah Maznah Mohd SallehUmmi Naiemah Saraih,2025,https://link.springer.com/article/10.1007/s10843-025-00403-x,Article
"""

df_raw = pd.read_csv(io.StringIO(csv_data))
print("Raw columns:", df_raw.columns.tolist())

df_clean = normalize_columns(df_raw)
print("Clean columns:", df_clean.columns.tolist())
print("Clean DOIs:", df_clean['DOI'].tolist())
print("Abstracts before enrichment:", df_clean['Abstract'].tolist())

logs = []
fields_to_enrich = ['Abstract', 'Keywords', 'Concepts', 'Times Cited', 'Open Access']
enriched_df = enrich_dataset_openalex(df_clean, fields_to_enrich=fields_to_enrich, log_list=logs)

print("\n--- RESULTS AFTER ENRICHMENT ---")
for idx, r in enriched_df.iterrows():
    abs_val = str(r['Abstract'])[:80] if pd.notna(r['Abstract']) else 'NONE'
    print(f"Row {idx}: DOI={r['DOI']} -> Abstract={abs_val}...")
