import pandas as pd
import bibtexparser
import rispy
import io
import re
import urllib.parse

# ---------------------------------------------------------
# Robust DOI Extraction and Validation
# ---------------------------------------------------------
DOI_REGEX = re.compile(r'\b(10\.\d{4,9}/[^\s\"\'<>]+)', re.IGNORECASE)

def extract_valid_doi(val) -> str | None:
    """
    Extracts and standardizes a genuine DOI from arbitrary text, URLs, or link fields.
    Validates IDF standard DOI prefix (10.xxxx/...) and strips trailing punctuation,
    query parameters, and markdown/HTML wrappers.
    """
    if val is None or pd.isna(val):
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ('nan', '<na>', 'none', 'null', ''):
        return None
    
    if '%' in val_str:
        try:
            val_str = urllib.parse.unquote(val_str)
        except Exception:
            pass

    # Strip URL query parameters or hash anchors
    val_str = re.sub(r'[?#].*$', '', val_str)

    match = DOI_REGEX.search(val_str)
    if not match:
        return None

    candidate = match.group(1).strip()
    # Strip trailing punctuation commonly appended by citations, brackets, or sentence endings
    candidate = re.sub(r'[\.,;:\>\)\]\s]+$', '', candidate)
    if candidate.count('(') < candidate.count(')'):
        candidate = candidate.rstrip(')')

    parts = candidate.split('/', 1)
    if len(parts) == 2 and len(parts[1]) >= 2:
        return candidate.lower()
    return None

# Target standardized columns
TARGET_COLUMNS = [
    'Author', 'Title', 'OpenAlex ID', 'Abstract', 'Article References',
    'Times Cited', 'Publication Year', 'DOI', 'PMID', 'Publisher', 'Keywords',
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
        df['DOI'] = df['AID'].apply(extract_valid_doi)
    
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
            if col == 'Keywords':
                def combine_kw_row(row):
                    vals = [str(v).strip() for v in row if pd.notna(v) and str(v).strip() and str(v).strip().lower() not in ('nan', '<na>', 'none')]
                    seen = set()
                    unique_vals = []
                    for v in vals:
                        for part in re.split(r'[;,]', v):
                            cleaned_part = part.strip()
                            if cleaned_part and cleaned_part.lower() not in seen:
                                seen.add(cleaned_part.lower())
                                unique_vals.append(cleaned_part)
                    return "; ".join(unique_vals) if unique_vals else pd.NA
                combined = sub_cleaned.apply(combine_kw_row, axis=1)
            elif col == 'Author':
                def combine_author_row(row):
                    vals = [str(v).strip() for v in row if pd.notna(v) and str(v).strip() and str(v).strip().lower() not in ('nan', '<na>', 'none')]
                    if not vals:
                        return pd.NA
                    # Prefer longest author string (e.g. full names 'AF' over abbreviated initials 'AU')
                    return max(vals, key=len)
                combined = sub_cleaned.apply(combine_author_row, axis=1)
            elif col == 'Abstract':
                def combine_abs_row(row):
                    vals = [str(v).strip() for v in row if pd.notna(v) and str(v).strip() and str(v).strip().lower() not in ('nan', '<na>', 'none')]
                    return max(vals, key=len) if vals else pd.NA
                combined = sub_cleaned.apply(combine_abs_row, axis=1)
            else:
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
    
    # Check if input columns represent a Web of Science export
    is_wos = any(c in cols_lower for c in ['ut', 'pt', 'di', 'af'])
    
    column_mapping = {
        # 1. Identificadores Básicos (Chaves de Busca e Indexação)
        "doi": "DOI", "digital object identifier": "DOI", "doids": "DOI", "item doi": "DOI", "item_doi": "DOI",
        "di": "DOI", "do": "DOI",
        "aid": "AID",
        "pmid": "PMID", "pubmed id": "PMID", "pm": "PMID",
        "pmcid": "PMCID", "pubmed central id": "PMCID", "pmc": "PMCID",
        "eid": "Scopus ID", "scopus id": "Scopus ID",
        "submission id": "Local ID", "id": "Local ID", "an": "Local ID", "oid": "Local ID", "lid": "Local ID", "accession number": "Local ID", "ut": "Local ID",
        "openalex id": "OpenAlex ID", "openalex_id": "OpenAlex ID", "openalex": "OpenAlex ID",
        "issn": "ISSN", "issns": "ISSN", "journal issn (print version)": "ISSN", "journal eissn (online version)": "ISSN", "sn": "ISSN", "eissn": "ISSN", "pissn": "ISSN", "ei": "ISSN",
        "isbn": "ISBN", "isbns": "ISBN", "bn": "ISBN",
        "url": "URL", "fulltext url": "URL", "fulltext url ": "URL", "link": "URL", "plink": "URL", "journal url": "URL", "ur": "URL", "lk": "URL",
        "arxiv": "ArXiv ID", "arxiv id": "ArXiv ID", "eprint": "ArXiv ID", "archiveprefix": "ArXiv ID",

        # 2. Títulos e Conteúdo
        "title": "Title", "article title": "Title", "document title": "Title", "título": "Title", "titulo": "Title", 
        "documenttitle": "Title", "journal title": "Title", "ti": "Title", "t1": "Title",
        "primary_title": "Title", "primary title": "Title", "item title": "Title", "item_title": "Title",
        "short title": "Short Title", "shorttitle": "Short Title",

        # 3. Metadados de Autoria, Demografia, Endereço e Localização
        "authors": "Author", "author": "Author", "author(s)": "Author", "author full names": "Author", 
        "creators": "Author", "autores": "Author", "contributors": "Author", "au": "Author", "fau": "Author", "af": "Author", "first author": "First Author",
        "affiliations": "Affiliations", "author affiliations": "Affiliations", "authors with affiliations": "Affiliations", 
        "institutions": "Affiliations", "institution": "Affiliations", "organization": "Affiliations", "school": "Affiliations", 
        "department": "Affiliations", "affiliation": "Affiliations",
        "address": "Address", "addresses": "Address", "author address": "Address", "author addresses": "Address", 
        "correspondence address": "Address", "reprint address": "Address", "reprint addresses": "Address", "c1": "Address", "rp": "Address", "ad": "Address",
        "location": "Location", "conference location": "Location", "conference place": "Location", "conference venue": "Location", 
        "place": "Location", "city": "Location", "place of publication": "Location", "cl": "Location", "pl": "Location", "cy": "Location", 
        "event location": "Location", "venue": "Location", "place_published": "Location",
        "country": "Country", "countries": "Country", "country code": "Country", "country of publisher": "Country", "país": "Country", "pais": "Country",

        # 4. Inteligência Semântica e Modelagem de Tópicos
        "abstract": "Abstract", "abstract note": "Abstract", "abstracts": "Abstract", "abstract text": "Abstract", 
        "summary": "Abstract", "resumo": "Abstract", "resumen": "Abstract", "ab": "Abstract", "n2": "Abstract", 
        "description": "Abstract", "author abstract": "Abstract", "paper abstract": "Abstract", "article abstract": "Abstract",
        "keywords": "Keywords", "keyword": "Keywords", "author keywords": "Keywords", "index keywords": "Keywords", 
        "keywords plus": "Keywords", "keyword plus": "Keywords", "palavras-chave": "Keywords", "palavras chave": "Keywords", 
        "palabras clave": "Keywords", "palabras clave ": "Keywords", "descriptors": "Keywords", "subjects": "Keywords", 
        "subject terms": "Keywords", "subject headings": "Keywords", "all keywords": "Keywords",
        "ot": "Keywords", "kw": "Keywords", "de": "Keywords", "ak": "Keywords", "kp": "Keywords", "tags": "Keywords", "raw_keywords": "Keywords",
        "concepts": "Concepts", "mesh terms": "Concepts", "mesh": "Concepts", "categories": "Concepts", "subject areas": "Concepts", "mesh headings": "Concepts",
        "wc": "Concepts", "sc": "Concepts", "web of science categories": "Concepts", "web of science category": "Concepts", "research areas": "Concepts", "research area": "Concepts",

        # 5. Contexto de Publicação (Distinção de Journal vs Publisher vs Detalhes)
        "journal": "Journal", "journal name": "Journal", "source title": "Journal", "publicationname": "Journal", "publication name": "Journal", 
        "publication title": "Journal", "book series title": "Journal", "book_series_title": "Journal",
        "journal/book": "Journal", "source": "Journal", "booktitle": "Journal", "jt": "Journal", "jf": "Journal", "so": "Journal", 
        "j2": "Journal", "t2": "Journal", "j9": "Journal", "ji": "Journal", "abbreviated source title": "Journal", "conference": "Journal", "proceedings": "Journal", "series": "Journal",
        "publisher": "Publisher", "editor": "Publisher", "editors": "Publisher", "pb": "Publisher", "pu": "Publisher", "host organization": "Publisher", "publishing house": "Publisher",
        "volume": "Volume", "vol": "Volume", "vl": "Volume", "vi": "Volume", "journal volume": "Volume",
        "issue": "Issue", "is": "Issue", "ip": "Issue", "number": "Issue", "no": "Issue", "journal issue": "Issue",
        "pages": "Pages", "page": "Pages", "page start": "Pages", "page end": "Pages", "start page": "Pages", "end page": "Pages", "sp": "Pages", "ep": "Pages", "bp": "Pages", "pg": "Pages", 
        "pages count": "Pages", "article number": "Pages", "artno": "Pages", "art. no.": "Pages", "ar": "Pages",

        # 6. Métricas, Datas e Impacto
        "publication year": "Publication Year", "publicationyear": "Publication Year", "year": "Publication Year", "year published": "Publication Year",
        "py": "Publication Year", "ano": "Publication Year", "publicationdate": "Publication Year", "publication date": "Publication Year", 
        "coverdate": "Publication Year", "printedpublicationyear": "Publication Year", "dp": "Publication Year", "date": "Publication Year",
        "times cited": "Times Cited", "citations": "Times Cited", "citation count": "Times Cited", 
        "cited by count": "Times Cited", "cited by": "Times Cited", "citedbycount": "Times Cited", "tc": "Times Cited", "cites": "Times Cited",
        "z9": "Times Cited", "times cited, wos core": "Times Cited", "times cited (wos core)": "Times Cited", "times cited, all databases": "Times Cited", "times cited (all databases)": "Times Cited",

        # 7. Filtros de Exclusão Metodológica (PRISMA)
        "document type": "Document Type", "documenttype": "Document Type", "type": "Document Type", 
        "item type": "Document Type", "content type": "Document Type", "content_type": "Document Type", "tipo de documento": "Document Type", "doctypes": "Document Type", 
        "pubtypes": "Document Type", "publicationtype": "Document Type", "pt": "Document Type", "ty": "Document Type", "section title": "Document Type", "dt": "Document Type",
        "language": "Language", "languages": "Language", "language(s)": "Language", "language of original document": "Language", "idioma": "Language", "la": "Language", "lang": "Language",
        "open access": "Open Access", "oa status": "Open Access", "is_oa": "Open Access", "isopenaccess": "Open Access", "oa": "Open Access", "open access indicator": "Open Access",

        # 8. Redes de Fomento, Referências e Notas
        "funding": "Funding", "funding details": "Funding", "funding texts": "Funding", "sponsors": "Funding", "sponsor": "Funding", "fomento": "Funding", "gr": "Funding", "fu": "Funding", "fx": "Funding", "grant": "Funding",
        "funding orgs": "Funding", "funding name preferred": "Funding", "funding text": "Funding",
        "references": "Article References", "article references": "Article References", "cited references": "Article References", "cr": "Article References",
        "notes": "Notes", "note": "Notes", "annote": "Notes", "n1": "Notes", "comments": "Notes"
    }

    new_cols = []
    for col in cols_lower:
        if is_wos and col == 'id':
            new_cols.append("Keywords")
            continue
        mapped_name = column_mapping.get(col)
        if not mapped_name:
            col_normalized = col.replace('_', ' ').replace('-', ' ').strip()
            mapped_name = column_mapping.get(col_normalized)
        if mapped_name:
            new_cols.append(mapped_name)
        else:
            new_cols.append(str(col).title())
            
    df.columns = new_cols
    
    # Merge any duplicate columns generated by the mapping
    df = deduplicate_and_merge_columns(df)
    
    for col in TARGET_COLUMNS:
        if col not in df.columns:
            df[col] = pd.Series(pd.NA, index=df.index, dtype=object)
        elif col != 'Times Cited' and df[col].dtype != 'object':
            df[col] = df[col].astype(object)

    # Clean and validate existing DOIs
    if 'DOI' in df.columns:
        df['DOI'] = df['DOI'].apply(extract_valid_doi)
    else:
        df['DOI'] = pd.Series(pd.NA, index=df.index, dtype=object)

    # In-file DOI Extraction: If DOI is missing, scan URL, Link, Notes, Source, etc.
    doi_missing = df['DOI'].isna() | (df['DOI'].astype(str).str.strip() == '')
    if doi_missing.any():
        cand_cols = [
            c for c in df.columns 
            if c != 'DOI' and any(k in c.lower() for k in ['url', 'link', 'note', 'source', 'aid', 'local id', 'plink', 'ur', 'lk'])
        ]
        for col_cand in cand_cols:
            if not doi_missing.any():
                break
            extracted = df.loc[doi_missing, col_cand].apply(extract_valid_doi)
            found = extracted.notna()
            if found.any():
                df.loc[doi_missing & found, 'DOI'] = extracted[found]
                doi_missing = df['DOI'].isna() | (df['DOI'].astype(str).str.strip() == '')

    # Guard PMCID vs PMID: ensure PMCID values (e.g. PMC1234567) are quarantined into PMCID and not treated as PMIDs
    if 'PMID' in df.columns:
        pmid_str = df['PMID'].astype(str).str.strip()
        pmc_mask = pmid_str.str.upper().str.startswith('PMC')
        if pmc_mask.any():
            if 'PMCID' not in df.columns:
                df['PMCID'] = pd.Series(pd.NA, index=df.index, dtype=object)
            pmcid_empty = df['PMCID'].isna() | (df['PMCID'].astype(str).str.strip().isin(['', 'nan', '<NA>', 'None']))
            df.loc[pmc_mask & pmcid_empty, 'PMCID'] = df.loc[pmc_mask & pmcid_empty, 'PMID']
            df.loc[pmc_mask, 'PMID'] = pd.NA

    if 'Publication Year' in df.columns:
        from utils.formatters import clean_year_series
        df['Publication Year'] = clean_year_series(df['Publication Year'])

    if 'Pages' in df.columns:
        from utils.formatters import clean_pages_series
        df['Pages'] = clean_pages_series(df['Pages'])

    for meta_col in ['Volume', 'Issue', 'PMID', 'ISSN']:
        if meta_col in df.columns:
            from utils.formatters import clean_metadata_series
            df[meta_col] = clean_metadata_series(df[meta_col])

    # Cross-field deduction: Populate Affiliations from Address if Affiliations is missing
    if 'Affiliations' in df.columns and 'Address' in df.columns:
        if df['Affiliations'].dtype != 'object':
            df['Affiliations'] = df['Affiliations'].astype(object)
        aff_missing = df['Affiliations'].isna() | (df['Affiliations'].astype(str).str.strip() == '')
        addr_valid = df['Address'].notna() & (df['Address'].astype(str).str.strip() != '')
        mask = aff_missing & addr_valid
        if mask.any():
            df.loc[mask, 'Affiliations'] = df.loc[mask, 'Address']

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

    # Author Standardization: Ensure all author names are in Western format (First Name First) and academic degrees are stripped
    if 'Author' in df.columns:
        from features.gender import standardize_author_string
        def _std_author(val):
            if pd.notna(val) and str(val).strip() and str(val).strip().lower() not in ('nan', '<na>', 'none'):
                std = standardize_author_string(str(val))
                return std if std else val
            return val
        df['Author'] = df['Author'].apply(_std_author)

    return df

# [NOTE: Web of Science Plain Text (.txt) parsing disabled for this version]
# def parse_wos_plaintext(text: str) -> pd.DataFrame:
#     """Parses Web of Science plain text (.txt) exports with standard 2-letter tags (e.g. PT, AU, TI... ER)."""
#     entries = []
#     current_entry = {}
#     current_tag = None
#     
#     for line in text.splitlines():
#         line_clean = line.rstrip()
#         if not line_clean or line_clean in ('EF', 'VR 1.0') or line_clean.startswith('FN '):
#             continue
#         if line_clean == 'ER':
#             if current_entry:
#                 entries.append(current_entry)
#                 current_entry = {}
#             current_tag = None
#             continue
#             
#         if len(line_clean) >= 3 and line_clean[:2].isupper() and line_clean[2] == ' ':
#             tag = line_clean[:2]
#             val = line_clean[3:].strip()
#             current_tag = tag
#             if tag in current_entry:
#                 if isinstance(current_entry[tag], list):
#                     current_entry[tag].append(val)
#                 else:
#                     current_entry[tag] = [current_entry[tag], val]
#             else:
#                 current_entry[tag] = val
#         elif line_clean.startswith('   ') and current_tag:
#             val = line_clean.strip()
#             if isinstance(current_entry[current_tag], list):
#                 current_entry[current_tag][-1] += " " + val
#             else:
#                 current_entry[current_tag] += " " + val
#                 
#     if current_entry:
#         entries.append(current_entry)
#         
#     df = pd.DataFrame(entries)
#     for col in df.columns:
#         if df[col].apply(lambda x: isinstance(x, list)).any():
#             df[col] = df[col].apply(lambda x: "; ".join(map(str, x)) if isinstance(x, list) else x)
#     return df

def parse_file(uploaded_file) -> pd.DataFrame:
    ext = uploaded_file.name.split('.')[-1].lower()
    
    if ext in ['xlsx', 'xls']:
        df = pd.read_excel(uploaded_file)
    elif ext == 'csv':
        parsed_df = None
        encodings = ['utf-8-sig', 'utf-8', 'latin1', 'cp1252', 'iso-8859-1']
        raw_bytes = uploaded_file.getvalue()
        
        for enc in encodings:
            try:
                text_str = raw_bytes.decode(enc)
            except Exception:
                continue
                
            lines = [l for l in text_str.splitlines() if l.strip()]
            if not lines:
                parsed_df = pd.DataFrame()
                break

            # [NOTE: WoS Plain Text (.txt) and Tab-Delimited (.tsv) disabled for this version]
            # # 1. Check for Web of Science Plain Text tagged format (PT ..., AU ..., ER)
            # has_wos_pt = (
            #     any('FN Clarivate' in l or 'FN Thomson' in l for l in lines[:5]) or
            #     (re.match(r'^[A-Z]{2}\s', lines[0]) and any(l.strip() == 'ER' for l in lines))
            # )
            # if has_wos_pt and '\t' not in lines[0] and (len(lines) < 2 or '\t' not in lines[1]):
            #     try:
            #         pt_df = parse_wos_plaintext(text_str)
            #         if not pt_df.empty:
            #             parsed_df = pt_df
            #             break
            #     except Exception:
            #         pass
            #
            # # 2. Check for Tab-delimited file (Web of Science tab-delimited or generic TSV)
            # has_tabs = any('\t' in l for l in lines[:10])
            # if has_tabs or ext == 'tsv':
            #     start_idx = 0
            #     for i, l in enumerate(lines[:10]):
            #         if l.startswith('PT\t') or '\tTI\t' in l or '\tSO\t' in l or l.count('\t') >= 2:
            #             start_idx = i
            #             break
            #     clean_lines = [l for l in lines[start_idx:] if l.strip() and l.strip() != 'EF']
            #     try:
            #         tab_df = pd.read_csv(io.StringIO("\n".join(clean_lines)), sep='\t', skipinitialspace=True, low_memory=False)
            #         if not tab_df.empty:
            #             parsed_df = tab_df
            #             break
            #     except Exception:
            #         pass

            # Semicolon vs Comma delimited CSV
            first_data_line = lines[0]
            sep_order = [';', ','] if first_data_line.count(';') > first_data_line.count(',') else [',', ';']
            for s in sep_order:
                try:
                    test_df = pd.read_csv(io.StringIO(text_str), sep=s, skipinitialspace=True, low_memory=False)
                    if test_df.shape[1] > 1:
                        parsed_df = test_df
                        break
                except Exception:
                    continue
            if parsed_df is not None and not parsed_df.empty:
                break

            # Fallback python sniffer
            try:
                parsed_df = pd.read_csv(io.StringIO(text_str), sep=None, engine='python', skipinitialspace=True)
                if not parsed_df.empty:
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
        for tag in ['doi', 'do', 'di', 'DO', 'DI', 'url', 'ur', 'l3', 'm3']:
            if tag in df.columns:
                extracted = df[tag].apply(extract_valid_doi)
                if extracted.notna().any():
                    df['DOI'] = extracted if 'DOI' not in df.columns else df['DOI'].combine_first(extracted)
        for col in df.columns:
            if df[col].apply(lambda x: isinstance(x, (list, tuple))).any():
                df[col] = df[col].apply(lambda x: ", ".join(map(str, x)) if isinstance(x, (list, tuple)) else x)
    elif ext == 'bib':
        text = uploaded_file.getvalue().decode("utf-8", errors='ignore')
        bib_database = bibtexparser.loads(text)
        df = pd.DataFrame(bib_database.entries)
        for tag in ['doi', 'url', 'eprint', 'note', 'howpublished']:
            if tag in df.columns:
                extracted = df[tag].apply(extract_valid_doi)
                if extracted.notna().any():
                    df['DOI'] = extracted if 'DOI' not in df.columns else df['DOI'].combine_first(extracted)
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