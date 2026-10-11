import pandas as pd
import numpy as np
import re
from typing import Tuple

def normalize_doi(val) -> str:
    """Standardizes a DOI string: strips URL prefixes, doi: label, whitespace, and lowercases."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip().lower()
    s = re.sub(r'^https?://(dx\.)?doi\.org/', '', s)
    s = re.sub(r'^doi:\s*', '', s)
    s = s.strip().rstrip('/')
    return s if s and s not in ('nan', '<na>', 'none', 'null', '') else None

def normalize_openalex_id(val) -> str:
    """Standardizes an OpenAlex ID (e.g. 'https://openalex.org/W2122410182' -> 'W2122410182')."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    s = re.sub(r'^https?://openalex\.org/', '', s).strip()
    return s.upper() if s and s.lower() not in ('nan', '<na>', 'none', 'null', '') else None

def normalize_pmid(val) -> str:
    """Standardizes a PubMed ID string."""
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if s.endswith('.0'):
        s = s[:-2]
    # Digits only check
    digits = re.sub(r'\D', '', s)
    return digits if digits and digits not in ('0', '') else None

def normalize_title(val) -> str:
    """
    Standardizes a title for deduplication:
    Strips translated bracket notation like '[ON ARTIFICIAL INTELLIGENCE]' -> 'on artificial intelligence',
    removes punctuation, collapses whitespace, and lowercases.
    """
    if val is None or pd.isna(val):
        return None
    s = str(val).strip().lower()
    # Strip enclosing square brackets or parentheses commonly added by NLM / Medline for translations
    s = re.sub(r'^[\[\(]\s*|\s*[\]\)]$', '', s)
    # Remove punctuation
    s = re.sub(r'[^\w\s]', '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s if s and s not in ('nan', '<na>', 'none', 'null', '') else None

def deduplicate_dataset(df: pd.DataFrame, return_duplicates: bool = False, phase_name: str = "Ingestion") -> Tuple[pd.DataFrame, int] | Tuple[pd.DataFrame, int, list]:
    """
    Multi-stage hierarchical deduplication for bibliographic datasets:
    1. DOI deduplication (exact normalized DOI match)
    2. OpenAlex ID deduplication (exact canonical OpenAlex ID match)
    3. PMID deduplication (exact PubMed ID match)
    4. Normalized Title + Authors deduplication (preventing merges if DOIs/PMIDs conflict)

    When duplicates are found, records are sorted by metadata completeness (number of non-null fields
    and Times Cited) so the richest record is preserved. Any unique missing fields are backfilled.

    Returns:
        If return_duplicates is False: (deduplicated_df, total_duplicates_removed)
        If return_duplicates is True:  (deduplicated_df, total_duplicates_removed, duplicates_list)
    """
    if df is None or df.empty:
        return (df, 0, []) if return_duplicates else (df, 0)

    initial_count = len(df)
    df_clean = df.copy()

    # Pre-calculate metadata richness for intelligent record preservation
    # Priority: higher non-null column count, then higher Times Cited
    cit_numeric = pd.to_numeric(df_clean.get("Times Cited", 0), errors="coerce").fillna(0)
    non_null_counts = df_clean.notna().sum(axis=1)
    df_clean["_richness"] = non_null_counts * 1000000 + cit_numeric

    duplicates_list = []
    
    def _apply_dedup(df_subset, subset_col, stage_name):
        df_subset = df_subset.sort_values("_richness", ascending=False)
        if return_duplicates:
            dup_mask = df_subset.duplicated(subset=[subset_col], keep=False)
            if dup_mask.any():
                for _, group in df_subset[dup_mask].groupby(subset_col):
                    kept = group.iloc[0]
                    for i in range(1, len(group)):
                        duplicates_list.append({
                            'phase': phase_name,
                            'stage': stage_name,
                            'kept': kept,
                            'removed': group.iloc[i]
                        })
        return df_subset.drop_duplicates(subset=[subset_col], keep="first")

    # Stage 1: DOI Deduplication
    if "DOI" in df_clean.columns:
        norm_doi = df_clean["DOI"].apply(normalize_doi)
        has_doi = norm_doi.notna()
        if has_doi.any():
            df_doi = df_clean[has_doi].copy()
            df_doi["_norm_doi"] = norm_doi[has_doi]
            df_doi = df_doi.sort_values("_richness", ascending=False)
            
            # NOTE / SPECIAL HANDLING:
            # Certain medical and scientific journals (e.g., NEJM, The Lancet, JAMA) assign a single
            # shared DOI to an entire Correspondence / Letters to the Editor section (e.g., '10.1056/NEJMc2408971').
            # However, the National Library of Medicine (PubMed / NLM) indexes each individual letter
            # and the authors' reply as distinct publications with unique PMIDs (e.g., PMID 39321378 vs PMID 39321381).
            # Because these represent distinct dialogue contributions (e.g. Letter vs. Reply) written by
            # different authors rather than duplicate versions of the same article, records sharing a DOI
            # but bearing conflicting non-null PMIDs must NOT be merged and must be preserved as distinct records.
            kept_doi_indices = []
            
            for doi_val, group in df_doi.groupby("_norm_doi", sort=False):
                if len(group) == 1:
                    kept_doi_indices.append(group.index[0])
                    continue
                
                clusters = []
                for idx, row in group.iterrows():
                    row_pmid = normalize_pmid(row.get('PMID')) if 'PMID' in row else None
                    
                    merged = False
                    for c in clusters:
                        conflict = False
                        if row_pmid and c['pmid'] and row_pmid != c['pmid']:
                            conflict = True
                            
                        if not conflict:
                            if return_duplicates:
                                duplicates_list.append({
                                    'phase': phase_name,
                                    'stage': 'DOI',
                                    'kept': c['row'],
                                    'removed': row
                                })
                            if not c['pmid'] and row_pmid:
                                c['pmid'] = row_pmid
                            merged = True
                            break
                    
                    if not merged:
                        clusters.append({
                            'row': row,
                            'pmid': row_pmid
                        })
                        kept_doi_indices.append(idx)
                        
            df_doi = df_doi.loc[kept_doi_indices].drop(columns=["_norm_doi"])
            df_no_doi = df_clean[~has_doi]
            df_clean = pd.concat([df_doi, df_no_doi], ignore_index=True)

    # Stage 2: OpenAlex ID Deduplication
    if "OpenAlex ID" in df_clean.columns:
        norm_oa = df_clean["OpenAlex ID"].apply(normalize_openalex_id)
        has_oa = norm_oa.notna()
        if has_oa.any():
            df_oa = df_clean[has_oa].copy()
            df_oa["_norm_oa"] = norm_oa[has_oa]
            df_oa = _apply_dedup(df_oa, "_norm_oa", "OpenAlex ID").drop(columns=["_norm_oa"])
            df_no_oa = df_clean[~has_oa]
            df_clean = pd.concat([df_oa, df_no_oa], ignore_index=True)

    # Stage 3: PMID Deduplication
    if "PMID" in df_clean.columns:
        norm_pmid = df_clean["PMID"].apply(normalize_pmid)
        has_pmid = norm_pmid.notna()
        if has_pmid.any():
            df_pm = df_clean[has_pmid].copy()
            df_pm["_norm_pm"] = norm_pmid[has_pmid]
            df_pm = _apply_dedup(df_pm, "_norm_pm", "PMID").drop(columns=["_norm_pm"])
            df_no_pm = df_clean[~has_pmid]
            df_clean = pd.concat([df_pm, df_no_pm], ignore_index=True)

    # Stage 4: Normalized Title + Authors Deduplication
    if "Title" in df_clean.columns and "Author" in df_clean.columns:
        norm_title = df_clean["Title"].apply(normalize_title)
        
        def normalize_author(val):
            if pd.isna(val):
                return ""
            s = str(val).strip().lower()
            s = re.sub(r'[^\w\s]', '', s)
            s = re.sub(r'\s+', ' ', s).strip()
            return s
            
        norm_author = df_clean["Author"].apply(normalize_author)
        
        has_title = norm_title.notna() & (norm_title.str.len() >= 10)
        
        if has_title.any():
            df_t = df_clean[has_title].copy()
            df_t["_norm_t"] = norm_title[has_title]
            df_t["_norm_a"] = norm_author[has_title]
            
            df_t["_dedup_t_key"] = df_t["_norm_t"] + " | " + df_t["_norm_a"]
            df_t = df_t.sort_values("_richness", ascending=False)
            
            kept_indices = []
            
            for key, group in df_t.groupby("_dedup_t_key"):
                if len(group) == 1:
                    kept_indices.append(group.index[0])
                    continue
                
                clusters = []
                for idx, row in group.iterrows():
                    row_doi = normalize_doi(row.get('DOI')) if 'DOI' in row else None
                    row_pmid = normalize_pmid(row.get('PMID')) if 'PMID' in row else None
                    
                    merged = False
                    for c in clusters:
                        conflict = False
                        if row_doi and c['doi'] and row_doi != c['doi']:
                            conflict = True
                        if row_pmid and c['pmid'] and row_pmid != c['pmid']:
                            conflict = True
                            
                        if not conflict:
                            if return_duplicates:
                                duplicates_list.append({
                                    'phase': phase_name,
                                    'stage': 'Title + Authors',
                                    'kept': c['row'],
                                    'removed': row
                                })
                            if not c['doi'] and row_doi: c['doi'] = row_doi
                            if not c['pmid'] and row_pmid: c['pmid'] = row_pmid
                            merged = True
                            break
                    
                    if not merged:
                        clusters.append({
                            'row': row,
                            'doi': row_doi,
                            'pmid': row_pmid
                        })
                        kept_indices.append(idx)
            
            df_t = df_t.loc[kept_indices]
            df_t = df_t.drop(columns=["_norm_t", "_norm_a", "_dedup_t_key"])
            
            df_no_t = df_clean[~has_title]
            df_clean = pd.concat([df_t, df_no_t], ignore_index=True)

    # Clean up temporary ranking column
    if "_richness" in df_clean.columns:
        df_clean = df_clean.drop(columns=["_richness"])

    df_clean = df_clean.reset_index(drop=True)
    duplicates_removed = initial_count - len(df_clean)
    if return_duplicates:
        return df_clean, duplicates_removed, duplicates_list
    return df_clean, duplicates_removed
