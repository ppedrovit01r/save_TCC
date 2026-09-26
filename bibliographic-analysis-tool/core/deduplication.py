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

def deduplicate_dataset(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    Multi-stage hierarchical deduplication for bibliographic datasets:
    1. DOI deduplication (exact normalized DOI match)
    2. OpenAlex ID deduplication (exact canonical OpenAlex ID match)
    3. PMID deduplication (exact PubMed ID match)
    4. Normalized Title deduplication (exact title match of length >= 10, considering publication year)

    When duplicates are found, records are sorted by metadata completeness (number of non-null fields
    and Times Cited) so the richest record is preserved. Any unique missing fields are backfilled.

    Returns:
        (deduplicated_df, total_duplicates_removed)
    """
    if df is None or df.empty:
        return df, 0

    initial_count = len(df)
    df_clean = df.copy()

    # Pre-calculate metadata richness for intelligent record preservation
    # Priority: higher non-null column count, then higher Times Cited
    cit_numeric = pd.to_numeric(df_clean.get("Times Cited", 0), errors="coerce").fillna(0)
    non_null_counts = df_clean.notna().sum(axis=1)
    df_clean["_richness"] = non_null_counts * 1000000 + cit_numeric

    # Stage 1: DOI Deduplication
    if "DOI" in df_clean.columns:
        norm_doi = df_clean["DOI"].apply(normalize_doi)
        has_doi = norm_doi.notna()
        if has_doi.any():
            df_doi = df_clean[has_doi].copy()
            df_doi["_norm_doi"] = norm_doi[has_doi]
            # Sort by richness descending so richest duplicate is first
            df_doi = df_doi.sort_values("_richness", ascending=False)
            df_doi = df_doi.drop_duplicates(subset=["_norm_doi"], keep="first").drop(columns=["_norm_doi"])
            
            df_no_doi = df_clean[~has_doi]
            df_clean = pd.concat([df_doi, df_no_doi], ignore_index=True)

    # Stage 2: OpenAlex ID Deduplication
    if "OpenAlex ID" in df_clean.columns:
        norm_oa = df_clean["OpenAlex ID"].apply(normalize_openalex_id)
        has_oa = norm_oa.notna()
        if has_oa.any():
            df_oa = df_clean[has_oa].copy()
            df_oa["_norm_oa"] = norm_oa[has_oa]
            df_oa = df_oa.sort_values("_richness", ascending=False)
            df_oa = df_oa.drop_duplicates(subset=["_norm_oa"], keep="first").drop(columns=["_norm_oa"])
            
            df_no_oa = df_clean[~has_oa]
            df_clean = pd.concat([df_oa, df_no_oa], ignore_index=True)

    # Stage 3: PMID Deduplication
    if "PMID" in df_clean.columns:
        norm_pmid = df_clean["PMID"].apply(normalize_pmid)
        has_pmid = norm_pmid.notna()
        if has_pmid.any():
            df_pm = df_clean[has_pmid].copy()
            df_pm["_norm_pm"] = norm_pmid[has_pmid]
            df_pm = df_pm.sort_values("_richness", ascending=False)
            df_pm = df_pm.drop_duplicates(subset=["_norm_pm"], keep="first").drop(columns=["_norm_pm"])
            
            df_no_pm = df_clean[~has_pmid]
            df_clean = pd.concat([df_pm, df_no_pm], ignore_index=True)

    # Stage 4: Normalized Title Deduplication (with Year consistency)
    if "Title" in df_clean.columns:
        norm_title = df_clean["Title"].apply(normalize_title)
        # Require meaningful title length (>= 10 chars) to prevent dropping distinct papers with generic 1-word titles
        has_title = norm_title.notna() & (norm_title.str.len() >= 10)
        if has_title.any():
            df_t = df_clean[has_title].copy()
            df_t["_norm_t"] = norm_title[has_title]
            
            # Use Publication Year if available, otherwise match on title
            if "Publication Year" in df_t.columns:
                from utils.formatters import clean_year_value
                df_t["_clean_yr"] = df_t["Publication Year"].apply(clean_year_value)
                # When year is present, match on (Title, Year). If year is empty, match on Title.
                # Treat empty year as matching or create composite subset
                df_t["_dedup_t_key"] = df_t.apply(
                    lambda r: f"{r['_norm_t']}_{r['_clean_yr']}" if r['_clean_yr'] else r['_norm_t'],
                    axis=1
                )
                df_t = df_t.sort_values("_richness", ascending=False)
                df_t = df_t.drop_duplicates(subset=["_dedup_t_key"], keep="first").drop(columns=["_norm_t", "_clean_yr", "_dedup_t_key"])
            else:
                df_t = df_t.sort_values("_richness", ascending=False)
                df_t = df_t.drop_duplicates(subset=["_norm_t"], keep="first").drop(columns=["_norm_t"])

            df_no_t = df_clean[~has_title]
            df_clean = pd.concat([df_t, df_no_t], ignore_index=True)

    # Clean up temporary ranking column
    if "_richness" in df_clean.columns:
        df_clean = df_clean.drop(columns=["_richness"])

    df_clean = df_clean.reset_index(drop=True)
    duplicates_removed = initial_count - len(df_clean)
    return df_clean, duplicates_removed
