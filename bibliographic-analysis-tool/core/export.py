import pandas as pd
import io

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

def _get_val(row, key):
    """Safely extracts a scalar non-empty string value from a row, handling Series and duplicate columns."""
    val = row.get(key)
    if val is None:
        return None
    if isinstance(val, pd.Series):
        for v in val:
            if pd.notna(v) and str(v).strip() != '' and str(v).strip().lower() != 'nan':
                return str(v).strip()
        return None
    if isinstance(val, (list, tuple)):
        for v in val:
            if pd.notna(v) and str(v).strip() != '' and str(v).strip().lower() != 'nan':
                return str(v).strip()
        return None
    if pd.notna(val) and str(val).strip() != '' and str(val).strip().lower() != 'nan':
        return str(val).strip()
    return None

def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensures unique columns before exporting."""
    if not df.columns.is_unique:
        unique_cols = list(dict.fromkeys(df.columns))
        merged_data = {}
        for col in unique_cols:
            sub = df.loc[:, df.columns == col]
            if sub.ndim == 1 or sub.shape[1] == 1:
                merged_data[col] = sub.iloc[:, 0] if sub.ndim > 1 else sub
            else:
                sub_cleaned = sub.apply(lambda col_s: col_s.apply(
                    lambda val: pd.NA if _is_empty_val(val) else val
                ))
                combined = sub_cleaned.bfill(axis=1).iloc[:, 0]
                merged_data[col] = combined
        return pd.DataFrame(merged_data, index=df.index)
    return df

def df_to_csv(df: pd.DataFrame) -> bytes:
    df_clean = _clean_df(df)
    return df_clean.to_csv(index=False).encode("utf-8")

def df_to_excel(df: pd.DataFrame) -> bytes:
    df_clean = _clean_df(df)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_clean.to_excel(writer, index=False, sheet_name='Data')
    return output.getvalue()

def df_to_ris(df: pd.DataFrame) -> bytes:
    """Basic RIS generator from DataFrame with robust type handling."""
    df_clean = _clean_df(df)
    ris_content = []
    for _, row in df_clean.iterrows():
        ris_content.append("TY  - JOUR")
        
        title = _get_val(row, 'Title')
        if title:
            ris_content.append(f"T1  - {title}")
            
        author_str = _get_val(row, 'Author')
        if author_str:
            for author in author_str.split(','):
                if author.strip():
                    ris_content.append(f"AU  - {author.strip()}")
                    
        py_str = _get_val(row, 'Publication Year')
        if py_str:
            try:
                py_clean = str(int(float(py_str)))
                ris_content.append(f"PY  - {py_clean}")
            except (ValueError, TypeError):
                ris_content.append(f"PY  - {py_str}")
                
        doi = _get_val(row, 'DOI')
        if doi:
            ris_content.append(f"DO  - {doi}")
            
        abstract = _get_val(row, 'Abstract')
        if abstract:
            ris_content.append(f"AB  - {abstract}")
            
        ris_content.append("ER  - \n")
        
    return "\n".join(ris_content).encode("utf-8")

def df_to_bib(df: pd.DataFrame) -> bytes:
    """Basic BibTeX generator from DataFrame with robust type handling."""
    df_clean = _clean_df(df)
    bib_content = []
    for i, row in df_clean.iterrows():
        author_str = _get_val(row, 'Author')
        author = author_str.replace(',', ' and ') if author_str else 'Unknown'
        
        title = _get_val(row, 'Title') or 'Unknown'
        
        py_str = _get_val(row, 'Publication Year')
        if py_str:
            try:
                year = str(int(float(py_str)))
            except (ValueError, TypeError):
                year = py_str
        else:
            year = 'Unknown'
        
        entry = f"@article{{ref{i},\n"
        entry += f"  title={{ {title} }},\n"
        entry += f"  author={{ {author} }},\n"
        entry += f"  year={{ {year} }},\n"
        
        publisher = _get_val(row, 'Publisher') or _get_val(row, 'Journal')
        if publisher:
            entry += f"  journal={{ {publisher} }},\n"
            
        doi = _get_val(row, 'DOI')
        if doi:
            entry += f"  doi={{ {doi} }},\n"
            
        entry += "}\n"
        bib_content.append(entry)
        
    return "\n".join(bib_content).encode("utf-8")

def df_to_nbib(df: pd.DataFrame) -> bytes:
    """Basic NBIB generator from DataFrame with robust type handling."""
    df_clean = _clean_df(df)
    nbib_content = []
    for _, row in df_clean.iterrows():
        pmid = _get_val(row, 'PMID')
        if pmid:
            nbib_content.append(f"PMID- {pmid}")
            
        title = _get_val(row, 'Title')
        if title:
            nbib_content.append(f"TI  - {title}")
            
        author_str = _get_val(row, 'Author')
        if author_str:
            for author in author_str.split(','):
                if author.strip():
                    nbib_content.append(f"FAU - {author.strip()}")
                    
        py_str = _get_val(row, 'Publication Year')
        if py_str:
            try:
                py_clean = str(int(float(py_str)))
                nbib_content.append(f"DP  - {py_clean}")
            except (ValueError, TypeError):
                nbib_content.append(f"DP  - {py_str}")
                
        doi = _get_val(row, 'DOI')
        if doi:
            nbib_content.append(f"AID - {doi} [doi]")
            
        abstract = _get_val(row, 'Abstract')
        if abstract:
            nbib_content.append(f"AB  - {abstract}")
            
        journal = _get_val(row, 'Journal') or _get_val(row, 'Publisher')
        if journal:
            nbib_content.append(f"JT  - {journal}")
            
        keywords = _get_val(row, 'Keywords')
        if keywords:
            for kw in str(keywords).split(';'):
                if kw.strip():
                    nbib_content.append(f"OT  - {kw.strip()}")
                    
        nbib_content.append("")
        
    return "\n".join(nbib_content).encode("utf-8")