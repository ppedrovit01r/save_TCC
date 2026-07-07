import pandas as pd
import bibtexparser
import rispy

# Target standardized columns
TARGET_COLUMNS = [
    'Author', 'Title', 'Abstract', 'Article References',
    'Times Cited', 'Publication Year', 'DOI', 'Publisher', 'Keywords'
]

# ---------------------------------------------------------
# Normalization Logic
# ---------------------------------------------------------
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    cols_lower = df.columns.str.lower()
    
    column_mapping = {
        "authors": "Author", "author": "Author",
        "title": "Title", "article title": "Title",
        "abstract note": "Abstract", "abstract": "Abstract",
        "references": "Article References", "article references": "Article References", "cited references": "Article References",
        "publication year": "Publication Year", "year": "Publication Year",
        "times cited": "Times Cited", "citations": "Times Cited", "citation count": "Times Cited",
        "doi": "DOI",
        "publisher": "Publisher", "journal": "Publisher", "journal name": "Publisher",
        "keywords": "Keywords", "author keywords": "Keywords"
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