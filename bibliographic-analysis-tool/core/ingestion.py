import pandas as pd
import bibtexparser
import rispy
import io
import re

# Target standardized columns
TARGET_COLUMNS = [
    'Author', 'Title', 'OpenAlex ID', 'Abstract', 'Article References',
    'Times Cited', 'Publication Year', 'DOI', 'Publisher', 'Keywords',
    'Affiliations', 'Country', 'Document Type', 'Language', 'Open Access',
    'Funding', 'Concepts', 'Journal', 'Location', 'Address', 'Volume', 'Issue', 'Pages', 'ISSN'
]

# ---------------------------------------------------------
# Blank Row Identification & Filtration
# ---------------------------------------------------------
def remove_blank_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Identifies and drops completely empty lines and blank records to guarantee true item counts."""
    if df is None or df.empty:
        return df

    df_cleaned = df.copy()

    def is_empty_cell(val):
        if val is None:
            return True
        if isinstance(val, (list, tuple)):
            for v in val:
                if pd.notna(v) and str(v).strip() != '' and str(v).strip().lower() not in ('nan', '<na>', 'none'):
                    return False
            return True
        if isinstance(val, pd.Series):
            for v in val:
                if pd.notna(v) and str(v).strip() != '' and str(v).strip().lower() not in ('nan', '<na>', 'none'):
                    return False
            return True
        try:
            if pd.isna(val):
                return True
        except Exception:
            pass
        v_str = str(val).strip().lower()
        return v_str == '' or v_str == 'nan' or v_str == '<na>' or v_str == 'none'

    if hasattr(df_cleaned, 'map'):
        empty_mask = df_cleaned.map(is_empty_cell)
    else:
        empty_mask = df_cleaned.applymap(is_empty_cell)

    # 1. Row is completely blank if ALL columns are empty
    all_blank = empty_mask.all(axis=1)

    # 2. Row is an invalid empty record if ALL core fields (Title, Author, DOI, Abstract) are empty
    core_cols = [c for c in ['Title', 'Author', 'DOI', 'Abstract'] if c in df_cleaned.columns]
    if core_cols:
        core_blank = empty_mask[core_cols].all(axis=1)
        drop_mask = all_blank | core_blank
    else:
        drop_mask = all_blank

    df_valid = df_cleaned[~drop_mask].reset_index(drop=True)
    return df_valid

# ---------------------------------------------------------
# NBIB Parsing Logic
# ---------------------------------------------------------
def parse_nbib(text: str) -> pd.DataFrame:
    entries = []
    current_entry = {}
    current_tag = None
    
    for line in text.splitlines():
        if not line.strip():
            if current_entry:
                entries.append(current_entry)
                current_entry = {}
            current_tag = None
            continue
            
        # Match NLM tags like 'PMID- ', 'TI  - '
        if len(line) >= 4 and (line[:4].isupper() or line[:4].strip().isupper()) and (len(line) == 4 or line[4] == '-'):
            tag = line[:4].strip()
            value = line[6:].strip() if len(line) >= 6 else ""
            current_tag = tag
            
            if tag in current_entry:
                if isinstance(current_entry[tag], list):
                    current_entry[tag].append(value)
                else:
                    current_entry[tag] = [current_entry[tag], value]
            else:
                current_entry[tag] = value
        elif line.startswith(" ") and current_tag:
            # Continuation line
            val = line.strip()
            if isinstance(current_entry[current_tag], list):
                current_entry[current_tag][-1] += " " + val
            else:
                current_entry[current_tag] += " " + val
                
    if current_entry:
        entries.append(current_entry)
        
    df = pd.DataFrame(entries)
    
    nbib_mapping = {
        'PMID': 'PMID',
        'TI': 'Title',
        'AB': 'Abstract',
        'FAU': 'Author',
        'AU': 'Author',
        'TA': 'Journal',
        'JT': 'Journal',
        'MH': 'Keywords',
        'OT': 'Keywords',
        'LA': 'Language',
        'PT': 'Document Type',
        'AD': 'Address',
        'PL': 'Location',
        'VI': 'Volume',
        'IP': 'Issue',
        'PG': 'Pages',
        'GR': 'Funding',
        'PMC': 'PMCID'
    }
    
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, list)).any():
            df[col] = df[col].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x)
            
    if 'AID' in df.columns:
        def extract_doi(val):
            if pd.isna(val): return val
            for item in str(val).split(', '):
                if '[doi]' in item:
                    return item.replace(' [doi]', '').strip()
            return val
        df['DOI'] = df['AID'].apply(extract_doi)
    
    if 'DP' in df.columns:
        df['Publication Year'] = df['DP'].astype(str).str.extract(r'^(\d{4})')[0]
        
    df = df.rename(columns=nbib_mapping)
    return df

# ---------------------------------------------------------
# Normalization Logic
# ---------------------------------------------------------
def _is_empty_val(val):
    if val is None:
        return True
    if isinstance(val, (list, tuple, set)):
        for item in val:
            if pd.notna(item) and str(item).strip() != '' and str(item).strip().lower() not in ('nan', '<na>', 'none'):
                return False
        return True
    if isinstance(val, pd.Series):
        for item in val:
            if pd.notna(item) and str(item).strip() != '' and str(item).strip().lower() not in ('nan', '<na>', 'none'):
                return False
        return True
    try:
        if pd.isna(val):
            return True
    except Exception:
        pass
    v_str = str(val).strip().lower()
    return v_str == '' or v_str == 'nan' or v_str == '<na>' or v_str == 'none'

def deduplicate_and_merge_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Consolidates duplicate column names by keeping non-null values."""
    if df.columns.is_unique:
        return df

    unique_cols = list(dict.fromkeys(df.columns))
    merged_data = {}

    for col in unique_cols:
        sub = df.loc[:, df.columns == col]
        if sub.ndim == 1 or sub.shape[1] == 1:
            merged_data[col] = sub.iloc[:, 0] if sub.ndim > 1 else sub
        else:
            # Clean empty/whitespace strings to pd.NA for horizontal fill safely
            sub_cleaned = sub.apply(lambda col_s: col_s.apply(
                lambda val: pd.NA if _is_empty_val(val) else val
            ))
            combined = sub_cleaned.bfill(axis=1).iloc[:, 0]
            merged_data[col] = combined

    return pd.DataFrame(merged_data, index=df.index)

def extract_country_from_text(text: str) -> str:
    """Extracts country name or ISO code from address, affiliation, or location text."""
    if not text or pd.isna(text) or not isinstance(text, str):
        return None
    text_lower = text.lower()
    
    # Brazil and Brazilian states / major cities
    br_states = [r'\bce\b', r'\brs\b', r'\bsp\b', r'\brj\b', r'\bmg\b', r'\bpr\b', r'\bsc\b', r'\bba\b', r'\bpe\b', r'\bdf\b', r'\bgo\b', r'\bpa\b', r'\brn\b', r'\bpb\b', r'\bes\b', r'\bma\b', r'\bal\b', r'\bpi\b', r'\bmt\b', r'\bms\b', r'\bse\b', r'\bro\b', r'\bto\b', r'\bac\b', r'\bap\b', r'\brr\b']
    br_cities = ['fortaleza', 'porto alegre', 'são paulo', 'sao paulo', 'rio de janeiro', 'curitiba', 'belo horizonte', 'recife', 'salvador', 'brasília', 'brasilia', 'florianópolis', 'florianopolis', 'campinas']
    
    if any(k in text_lower for k in ['brasil', 'brazil']) or any(c in text_lower for c in br_cities):
        return 'Brazil'
    for st_pat in br_states:
        if re.search(st_pat, text_lower):
            return 'Brazil'
            
    # Major countries mapping
    country_patterns = [
        (r'\b(united states|usa|u\.s\.a\.|u\.s\.)\b', 'United States'),
        (r'\b(united kingdom|uk|u\.k\.|england|scotland|wales)\b', 'United Kingdom'),
        (r'\b(portugal|lisboa|porto|coimbra)\b', 'Portugal'),
        (r'\b(spain|españa|espana|madrid|barcelona)\b', 'Spain'),
        (r'\b(france|paris)\b', 'France'),
        (r'\b(germany|deutschland|berlin|munich)\b', 'Germany'),
        (r'\b(italy|italia|rome|milan)\b', 'Italy'),
        (r'\b(canada|toronto|montreal|vancouver)\b', 'Canada'),
        (r'\b(australia|sydney|melbourne)\b', 'Australia'),
        (r'\b(china|beijing|shanghai)\b', 'China'),
        (r'\b(india|delhi|mumbai|bangalore)\b', 'India'),
        (r'\b(japan|tokyo)\b', 'Japan'),
        (r'\b(netherlands|holland|amsterdam)\b', 'Netherlands'),
        (r'\b(switzerland|zurich|geneva)\b', 'Switzerland'),
        (r'\b(sweden|stockholm)\b', 'Sweden'),
        (r'\b(mexico|méxico)\b', 'Mexico'),
        (r'\b(argentina|buenos aires)\b', 'Argentina'),
        (r'\b(chile|santiago)\b', 'Chile'),
        (r'\b(colombia|bogota|bogotá)\b', 'Colombia'),
    ]
    for pat, cname in country_patterns:
        if re.search(pat, text_lower):
            return cname
    return None

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    cols_lower = df.columns.str.lower()
    
    column_mapping = {
        # 1. Identificadores Básicos (Chaves de Busca e Indexação)
        "doi": "DOI", "digital object identifier": "DOI", "doids": "DOI",
        "aid": "AID",
        "pmid": "PMID", "pubmed id": "PMID",
        "pmcid": "PMCID", "pubmed central id": "PMCID", "pmc": "PMCID",
        "eid": "Scopus ID", "scopus id": "Scopus ID",
        "submission id": "Local ID", "id": "Local ID", "an": "Local ID", "oid": "Local ID", "lid": "Local ID", "accession number": "Local ID", "ut": "Local ID",
        "openalex id": "OpenAlex ID", "openalex_id": "OpenAlex ID", "openalex": "OpenAlex ID",
        "issn": "ISSN", "issns": "ISSN", "journal issn (print version)": "ISSN", "journal eissn (online version)": "ISSN", "sn": "ISSN", "eissn": "ISSN", "pissn": "ISSN",
        "isbn": "ISBN", "isbns": "ISBN", "bn": "ISBN",
        "url": "URL", "fulltext url": "URL", "fulltext url ": "URL", "link": "URL", "plink": "URL", "journal url": "URL", "ur": "URL", "lk": "URL",
        "arxiv": "ArXiv ID", "arxiv id": "ArXiv ID", "eprint": "ArXiv ID", "archiveprefix": "ArXiv ID",

        # 2. Títulos e Conteúdo
        "title": "Title", "article title": "Title", "document title": "Title", "título": "Title", "titulo": "Title", 
        "documenttitle": "Title", "journal title": "Title", "ti": "Title", "t1": "Title",
        "primary_title": "Title", "primary title": "Title", "item title": "Title",
        "short title": "Short Title", "shorttitle": "Short Title",

        # 3. Metadados de Autoria, Demografia, Endereço e Localização
        "authors": "Author", "author": "Author", "author(s)": "Author", "author full names": "Author", 
        "creators": "Author", "autores": "Author", "contributors": "Author", "au": "Author", "fau": "Author", "first author": "First Author",
        "affiliations": "Affiliations", "author affiliations": "Affiliations", "authors with affiliations": "Affiliations", 
        "institutions": "Affiliations", "institution": "Affiliations", "organization": "Affiliations", "school": "Affiliations", 
        "department": "Affiliations", "affiliation": "Affiliations",
        "address": "Address", "addresses": "Address", "author address": "Address", "author addresses": "Address", 
        "correspondence address": "Address", "reprint address": "Address", "c1": "Address", "rp": "Address", "ad": "Address",
        "location": "Location", "conference location": "Location", "conference place": "Location", "conference venue": "Location", 
        "place": "Location", "city": "Location", "place of publication": "Location", "cl": "Location", "pl": "Location", "cy": "Location", 
        "event location": "Location", "venue": "Location", "place_published": "Location",
        "country": "Country", "countries": "Country", "country code": "Country", "country of publisher": "Country", "país": "Country", "pais": "Country",

        # 4. Inteligência Semântica e Modelagem de Tópicos
        "abstract": "Abstract", "abstract note": "Abstract", "summary": "Abstract", "resumo": "Abstract", "ab": "Abstract", "n2": "Abstract", "description": "Abstract",
        "keywords": "Keywords", "author keywords": "Keywords", "index keywords": "Keywords", "palavras-chave": "Keywords", "palavras chave": "Keywords", 
        "descriptors": "Keywords", "subjects": "Keywords", "ot": "Keywords", "kw": "Keywords", "de": "Keywords", "tags": "Keywords", "raw_keywords": "Keywords",
        "concepts": "Concepts", "mesh terms": "Concepts", "mesh": "Concepts", "categories": "Concepts", "subject areas": "Concepts",

        # 5. Contexto de Publicação (Distinção de Journal vs Publisher vs Detalhes)
        "journal": "Journal", "journal name": "Journal", "source title": "Journal", "publicationname": "Journal", "publication name": "Journal", 
        "journal/book": "Journal", "source": "Journal", "booktitle": "Journal", "jt": "Journal", "jf": "Journal", "so": "Journal", 
        "j2": "Journal", "t2": "Journal", "abbreviated source title": "Journal", "conference": "Journal", "proceedings": "Journal", "series": "Journal",
        "publisher": "Publisher", "editor": "Publisher", "editors": "Publisher", "pb": "Publisher", "pu": "Publisher", "host organization": "Publisher", "publishing house": "Publisher",
        "volume": "Volume", "vol": "Volume", "vl": "Volume", "vi": "Volume",
        "issue": "Issue", "is": "Issue", "ip": "Issue", "number": "Issue", "no": "Issue",
        "pages": "Pages", "page": "Pages", "page start": "Pages", "page end": "Pages", "sp": "Pages", "ep": "Pages", "pg": "Pages", 
        "pages count": "Pages", "article number": "Pages", "artno": "Pages", "art. no.": "Pages",

        # 6. Métricas, Datas e Impacto
        "publication year": "Publication Year", "publicationyear": "Publication Year", "year": "Publication Year", 
        "py": "Publication Year", "ano": "Publication Year", "publicationdate": "Publication Year", "publication date": "Publication Year", 
        "coverdate": "Publication Year", "printedpublicationyear": "Publication Year", "dp": "Publication Year", "date": "Publication Year",
        "times cited": "Times Cited", "citations": "Times Cited", "citation count": "Times Cited", 
        "cited by count": "Times Cited", "cited by": "Times Cited", "citedbycount": "Times Cited", "tc": "Times Cited", "cites": "Times Cited",

        # 7. Filtros de Exclusão Metodológica (PRISMA)
        "document type": "Document Type", "documenttype": "Document Type", "type": "Document Type", 
        "item type": "Document Type", "tipo de documento": "Document Type", "doctypes": "Document Type", 
        "pubtypes": "Document Type", "publicationtype": "Document Type", "pt": "Document Type", "ty": "Document Type", "section title": "Document Type", "dt": "Document Type",
        "language": "Language", "languages": "Language", "language(s)": "Language", "language of original document": "Language", "idioma": "Language", "la": "Language", "lang": "Language",
        "open access": "Open Access", "oa status": "Open Access", "is_oa": "Open Access", "isopenaccess": "Open Access",

        # 8. Redes de Fomento, Referências e Notas
        "funding": "Funding", "funding details": "Funding", "funding texts": "Funding", "sponsors": "Funding", "sponsor": "Funding", "fomento": "Funding", "gr": "Funding", "fu": "Funding", "fx": "Funding", "grant": "Funding",
        "references": "Article References", "article references": "Article References", "cited references": "Article References", "cr": "Article References",
        "notes": "Notes", "note": "Notes", "annote": "Notes", "n1": "Notes", "comments": "Notes"
    }

    new_cols = []
    for col in cols_lower:
        mapped_name = column_mapping.get(col)
        if mapped_name:
            new_cols.append(mapped_name)
        else:
            new_cols.append(str(col).title())
            
    df.columns = new_cols
    
    # Merge any duplicate columns generated by the mapping
    df = deduplicate_and_merge_columns(df)
    
    for col in TARGET_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    # Cross-field deduction: Populate Affiliations from Address if Affiliations is missing
    if 'Affiliations' in df.columns and 'Address' in df.columns:
        aff_missing = df['Affiliations'].isna() | (df['Affiliations'].astype(str).str.strip() == '')
        addr_valid = df['Address'].notna() & (df['Address'].astype(str).str.strip() != '')
        df.loc[aff_missing & addr_valid, 'Affiliations'] = df.loc[aff_missing & addr_valid, 'Address']

    # Cross-field deduction: Deduce Country strictly from author-bound fields (Address or Affiliations) if Country is missing.
    # Note: 'Location' is explicitly excluded because it typically represents the conference/event hosting venue rather than author place.
    if 'Country' in df.columns:
        cnt_missing = df['Country'].isna() | (df['Country'].astype(str).str.strip() == '')
        for idx in df[cnt_missing].index:
            deduced = None
            for col_candidate in ['Address', 'Affiliations']:
                if col_candidate in df.columns:
                    val_c = df.at[idx, col_candidate]
                    if pd.notna(val_c):
                        deduced = extract_country_from_text(str(val_c))
                        if deduced:
                            break
            if deduced:
                df.at[idx, 'Country'] = deduced

    return df

def parse_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.split('.')[-1].lower()
    
    if ext in ['xlsx', 'xls']:
        df = pd.read_excel(uploaded_file)
    elif ext == 'csv':
        parsed_df = None
        encodings = ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']
        
        for enc in encodings:
            uploaded_file.seek(0)
            try:
                parsed_df = pd.read_csv(uploaded_file, sep=',', encoding=enc, skipinitialspace=True)
                break
            except Exception:
                uploaded_file.seek(0)
                try:
                    parsed_df = pd.read_csv(uploaded_file, sep=';', encoding=enc, skipinitialspace=True)
                    break
                except Exception:
                    uploaded_file.seek(0)
                    try:
                        parsed_df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding=enc, skipinitialspace=True)
                        break
                    except Exception:
                        continue

        if parsed_df is None:
            uploaded_file.seek(0)
            raw_bytes = uploaded_file.getvalue()
            for enc in encodings:
                try:
                    text_str = raw_bytes.decode(enc, errors='ignore')
                    clean_lines = [re.sub(r'^\s+"', '"', l.strip()) for l in text_str.splitlines() if l.strip()]
                    parsed_df = pd.read_csv(io.StringIO("\n".join(clean_lines)), sep=',', skipinitialspace=True)
                    break
                except Exception:
                    continue

        if parsed_df is None:
            raise ValueError(f"Could not parse CSV file '{uploaded_file.name}'. Please verify formatting.")

        df = parsed_df
    elif ext == 'ris':
        text = uploaded_file.getvalue().decode("utf-8", errors='ignore')
        entries = rispy.loads(text)
        df = pd.DataFrame(entries)
        if 'authors' in df.columns: df.rename(columns={'authors': 'Author'}, inplace=True)
        if 'year' in df.columns: df.rename(columns={'year': 'Publication Year'}, inplace=True)
        for col in df.columns:
            if df[col].apply(lambda x: isinstance(x, (list, tuple))).any():
                df[col] = df[col].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
    elif ext == 'bib':
        text = uploaded_file.getvalue().decode("utf-8", errors='ignore')
        bib_database = bibtexparser.loads(text)
        df = pd.DataFrame(bib_database.entries)
        for col in df.columns:
            if df[col].apply(lambda x: isinstance(x, (list, tuple))).any():
                df[col] = df[col].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
    elif ext == 'nbib':
        text = uploaded_file.getvalue().decode("utf-8", errors='ignore')
        df = parse_nbib(text)
    else:
        raise ValueError(f"Unsupported file format: {ext}")
        
    normalized_df = normalize_columns(df)
    return remove_blank_rows(normalized_df)