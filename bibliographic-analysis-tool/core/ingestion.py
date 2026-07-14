import pandas as pd
import bibtexparser
import rispy

# Target standardized columns
TARGET_COLUMNS = [
    'Author', 'Title', 'OpenAlex ID', 'Abstract', 'Article References',
    'Times Cited', 'Publication Year', 'DOI', 'Publisher', 'Keywords',
    'Affiliations', 'Country', 'Document Type', 'Language', 'Open Access',
    'Funding', 'Concepts' 
]

# ---------------------------------------------------------
# Normalization Logic
# ---------------------------------------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    cols_lower = df.columns.str.lower()
    
    column_mapping = {
        # 1. Identificadores Básicos (Chaves de Busca)
        "doi": "DOI", "digital object identifier": "DOI",
        "title": "Title", "article title": "Title", "document title": "Title", "título": "Title",
        "openalex id": "OpenAlex ID", # O identificador nativo e unívoco do OpenAlex

        # 2. Metadados de Autoria (Demografia, Impacto e Endogenia)
        "authors": "Author", "author": "Author", "author full names": "Author", "creators": "Author", "autores": "Author",
        "affiliations": "Affiliations", "author affiliations": "Affiliations", "institutions": "Affiliations", "addresses": "Affiliations",
        "country": "Country", "countries": "Country", "country code": "Country", "país": "Country", # Geocodificação extraída do ROR

        # 3. Inteligência Semântica (Modelagem de Tópicos e Recomendação)
        "abstract": "Abstract", "abstract note": "Abstract", "summary": "Abstract", "resumo": "Abstract",
        "keywords": "Keywords", "author keywords": "Keywords", "index keywords": "Keywords", "palavras-chave": "Keywords",
        "concepts": "Concepts", "mesh terms": "Concepts", "subjects": "Concepts", "categories": "Concepts", # Tags semânticas automatizadas do OpenAlex

        # 4. Topologia de Redes (Co-citação e Acoplamento)
        "references": "Article References", "article references": "Article References", "cited references": "Article References", "bibliography": "Article References",
        "referenced works": "Article References", # Formato de retorno em lista de IDs do OpenAlex

        # 5. Métricas de Envelhecimento, Impacto e Desigualdade
        "publication year": "Publication Year", "year": "Publication Year", "py": "Publication Year", "ano": "Publication Year",
        "times cited": "Times Cited", "citations": "Times Cited", "citation count": "Times Cited", "cited by count": "Times Cited",

        # 6. Filtros de Exclusão Metodológica (Crucial para o Assistente PRISMA)
        "document type": "Document Type", "type": "Document Type", "item type": "Document Type", "tipo de documento": "Document Type",
        "language": "Language", "idioma": "Language",
        "open access": "Open Access", "oa status": "Open Access", "is_oa": "Open Access",

        # 7. Contexto de Publicação e Governança
        "publisher": "Publisher", "journal": "Publisher", "journal name": "Publisher", "source title": "Publisher",
        "funding": "Funding", "sponsor": "Funding", "funding details": "Funding", "fomento": "Funding" # Redes globais de fomento
    }

    
    new_cols = []
    for col in cols_lower:
        mapped_name = column_mapping.get(col)
        if mapped_name:
            new_cols.append(mapped_name)
        else:
            new_cols.append(str(col).title())
            
    df.columns = new_cols
    
    for col in TARGET_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
            
    return df

def parse_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.split('.')[-1].lower()
    
    if ext in ['xlsx', 'xls']:
        df = pd.read_excel(uploaded_file)
    elif ext == 'csv':
        # Includes encoding fallback (UTF-8 to Latin1) common in academic exports
        try:
            df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='utf-8')
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding='latin1')
    elif ext == 'ris':
        text = uploaded_file.getvalue().decode("utf-8")
        entries = rispy.loads(text)
        df = pd.DataFrame(entries)
        # Standardize basic RIS keys if needed before normalization
        if 'authors' in df.columns: df.rename(columns={'authors': 'Author'}, inplace=True)
        if 'year' in df.columns: df.rename(columns={'year': 'Publication Year'}, inplace=True)
    elif ext == 'bib':
        text = uploaded_file.getvalue().decode("utf-8", errors='ignore')
        bib_database = bibtexparser.loads(text)
        df = pd.DataFrame(bib_database.entries)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
        
    return normalize_columns(df)