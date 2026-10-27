import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from core.ingestion import normalize_columns
import io

csv_data = """Item Title,Publication Title,Book Series Title,Journal Volume,Journal Issue,Item DOI,Authors,Publication Year,URL,Content Type
"Mapping the evolution of cloud computing, AI, and business process performance in SMEs: a bibliometric analysis",Humanities and Social Sciences Communications,,,,10.1057/s41599-026-07403-9,Chaudhry Saeed AhmadAnuar Shah Bali MahomedHaslinda Hashim,2026,https://link.springer.com/article/10.1057/s41599-026-07403-9,Article
Digital transformation and entrepreneurship in Vietnam: navigating challenges and policy impacts,Journal of Global Entrepreneurship Research,,,,10.1007/s40497-026-00530-2,Sean WattsMuhammad Saqib IqbalZulhasni Abdul Rahim,2026,https://link.springer.com/article/10.1007/s40497-026-00530-2,Article
Pathways to digital entrepreneurship adoption among Malaysian SMEs: Analysing the determinants and technology readiness dynamics,Journal of International Entrepreneurship,,,,10.1007/s10843-025-00403-x,Taofeek Adeyemi SangosanyaSri Sarah Maznah Mohd SallehUmmi Naiemah Saraih,2025,https://link.springer.com/article/10.1007/s10843-025-00403-x,Article
"""

df = pd.read_csv(io.StringIO(csv_data))
print('Original columns:', df.columns.tolist())
norm_df = normalize_columns(df)
print('Normalized columns:', norm_df.columns.tolist())
print('DOI column:', norm_df['DOI'].tolist())
print('Abstract column:', norm_df['Abstract'].tolist())
if 'Item Doi' in norm_df.columns:
    print('Item Doi column:', norm_df['Item Doi'].tolist())
