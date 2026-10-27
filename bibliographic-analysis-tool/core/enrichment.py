import streamlit as st
import tempfile
import os
import time
import datetime
import urllib.parse
import pandas as pd
import requests
import requests_cache
import re
import json
import xml.etree.ElementTree as ET
import difflib
import numpy as np
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from core.ingestion import deduplicate_and_merge_columns, extract_valid_doi
from utils.formatters import format_duration
from features.gender import author_has_initials, split_authors_string, disambiguate_paper_authors, clean_author_text

CACHE_DIR = "/tmp" if os.name == 'posix' else tempfile.gettempdir()
requests_cache.install_cache(os.path.join(CACHE_DIR, 'openalex_cache'), expire_after=604800)
SS_CACHE_FILE = os.path.join(CACHE_DIR, 'semanticscholar_cache.json')
DOI_SEARCH_CACHE_FILE = os.path.join(CACHE_DIR, 'doi_search_cache.json')
CR_CACHE_FILE = os.path.join(CACHE_DIR, 'crossref_works_cache.json')

# Polite Pool Header (Replace with your actual email in production)
HEADERS = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}

# ---------------------------------------------------------
# Thread-safe API Rate Limiters & Local Caches
# ---------------------------------------------------------
class RateLimiter:
    """Thread-safe rate limiter to strictly respect API politeness and prevent HTTP 429."""
    def __init__(self, min_interval_seconds: float):
        self.min_interval = min_interval_seconds
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()

# Crossref polite pool: ~8-10 req/s
_cr_limiter = RateLimiter(0.12)
# OpenAlex polite pool: ~6.6 req/s
_oa_limiter = RateLimiter(0.15)
# NCBI PubMed polite rate: <= 3 req/s
_pm_limiter = RateLimiter(0.35)
# Semantic Scholar unauthenticated: strictly <= 1 req/s
_ss_limiter = RateLimiter(1.05)

_DOI_SEARCH_CACHE = None
_DOI_CACHE_LOCK = threading.Lock()

def _load_doi_search_cache() -> dict:
    global _DOI_SEARCH_CACHE
    if _DOI_SEARCH_CACHE is not None:
        return _DOI_SEARCH_CACHE
    with _DOI_CACHE_LOCK:
        if os.path.exists(DOI_SEARCH_CACHE_FILE):
            try:
                with open(DOI_SEARCH_CACHE_FILE, "r", encoding="utf-8") as f:
                    _DOI_SEARCH_CACHE = json.load(f)
                    return _DOI_SEARCH_CACHE
            except Exception:
                _DOI_SEARCH_CACHE = {}
        else:
            _DOI_SEARCH_CACHE = {}
    return _DOI_SEARCH_CACHE

def _save_doi_search_cache(cache: dict):
    global _DOI_SEARCH_CACHE
    with _DOI_CACHE_LOCK:
        _DOI_SEARCH_CACHE = cache
        try:
            with open(DOI_SEARCH_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

_CR_CACHE = None
_CR_CACHE_LOCK = threading.Lock()

def _load_cr_cache() -> dict:
    global _CR_CACHE
    if _CR_CACHE is not None:
        return _CR_CACHE
    with _CR_CACHE_LOCK:
        if os.path.exists(CR_CACHE_FILE):
            try:
                with open(CR_CACHE_FILE, "r", encoding="utf-8") as f:
                    _CR_CACHE = json.load(f)
                    return _CR_CACHE
            except Exception:
                _CR_CACHE = {}
        else:
            _CR_CACHE = {}
    return _CR_CACHE

def _save_cr_cache(cache: dict):
    global _CR_CACHE
    with _CR_CACHE_LOCK:
        _CR_CACHE = cache
        try:
            with open(CR_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

# ---------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------
def format_authors(authorships: list) -> str:
    if not authorships: return pd.NA
    author_names = []
    for auth in authorships:
        if 'author' in auth and 'display_name' in auth['author']:
            name = clean_author_text(auth['author']['display_name'])
            if name:
                author_names.append(name)
    return ", ".join(author_names) if author_names else pd.NA

def format_references(referenced_works: list) -> str:
    if not referenced_works: return pd.NA
    ref_ids = [str(rw).replace("https://openalex.org/", "") for rw in referenced_works]
    return "; ".join(ref_ids)

def reconstruct_abstract(inverted_index: dict) -> str:
    if not inverted_index: return pd.NA
    try:
        max_idx = max([idx for positions in inverted_index.values() for idx in positions])
        words = [""] * (max_idx + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(words).strip()
    except Exception:
        return pd.NA

def format_affiliations_and_countries(authorships: list) -> tuple:
    if not authorships: return pd.NA, pd.NA
    affiliations, countries = [], []
    for auth in authorships:
        for inst in auth.get('institutions', []):
            if inst.get('display_name'): affiliations.append(inst['display_name'])
            if inst.get('country_code'): countries.append(inst['country_code'])
            
    aff_str = "; ".join(sorted(set(affiliations))) if affiliations else pd.NA
    cnt_str = "; ".join(sorted(set(countries))) if countries else pd.NA
    return aff_str, cnt_str

def format_addresses(authorships: list) -> str:
    if not authorships: return pd.NA
    addresses = []
    for auth in authorships:
        for raw_aff in auth.get('raw_affiliation_strings', []):
            if raw_aff and str(raw_aff).strip():
                addresses.append(str(raw_aff).strip())
    return "; ".join(sorted(set(addresses))) if addresses else pd.NA

def format_location_from_oa(oa_data: dict) -> str:
    primary_loc = oa_data.get('primary_location') or {}
    source = primary_loc.get('source') or {}
    venue_name = source.get('display_name')
    host_org = source.get('host_organization_name')
    loc_parts = [p for p in [venue_name, host_org] if p and str(p).strip()]
    return " - ".join(loc_parts) if loc_parts else pd.NA

def format_list_of_dicts(data: list, key: str = 'display_name') -> str:
    if not data: return pd.NA
    items = [item.get(key) for item in data if item.get(key)]
    return "; ".join(items) if items else pd.NA

def _get_field(row: pd.Series, field_name: str):
    """Safely extracts a scalar non-null non-empty string value from a row, handling duplicate column names."""
    val = row.get(field_name)
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

def needs_enrichment(row: pd.Series, fields_to_enrich: list, is_ultimate: bool = False) -> bool:
    if is_ultimate:
        return True
    doi_val = _get_field(row, 'DOI')
    title_val = _get_field(row, 'Title')
    if not doi_val and title_val:
        return True
    # Mandatory author standardization: always enrich if authors contain initials
    author_val = _get_field(row, 'Author')
    if author_has_initials(author_val):
        return True
    for field in fields_to_enrich:
        val = _get_field(row, field)
        if val is None:
            return True
    return False

# ---------------------------------------------------------
# API Fetchers (Tiers)
# ---------------------------------------------------------

# Tier 1: OpenAlex Batch
def fetch_openalex_batch(dois: list, log_list: list = None) -> dict:
    if not dois: return {}
    clean_dois = [str(doi).strip().replace("https://doi.org/", "").replace("doi:", "").lower() for doi in dois if pd.notna(doi) and str(doi).strip()]
    if not clean_dois: return {}
    
    results = {}
    batch_size = 50
    for i in range(0, len(clean_dois), batch_size):
        batch = clean_dois[i:i+batch_size]
        filter_str = "doi:" + "|".join(batch)
        url = f"https://api.openalex.org/works?filter={filter_str}&per-page={batch_size}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(0.15 * (attempt + 1))  # Respect OpenAlex polite pool and backoff
                response = requests.get(url, headers=HEADERS, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    for work in data.get('results', []):
                        work_doi = work.get('doi')
                        if work_doi:
                            work_doi_clean = str(work_doi).replace("https://doi.org/", "").lower()
                            results[work_doi_clean] = work
                    break
                elif response.status_code in [429, 500, 502, 503, 504]:
                    if log_list is not None:
                        log_list.append(f"[API WARN] OpenAlex batch failed (HTTP {response.status_code}). Retry {attempt+1}/{max_retries}...")
                    time.sleep(1.0 * (attempt + 1))
                else:
                    break
            except Exception as e:
                if attempt == max_retries - 1 and log_list is not None:
                    log_list.append(f"[API ERROR] OpenAlex batch dropped after {max_retries} retries: {str(e)}")
                elif log_list is not None:
                    log_list.append(f"[API WARN] OpenAlex batch timeout. Retry {attempt+1}/{max_retries}...")
    return results

def fetch_openalex_batch_by_pmids(pmids: list, log_list: list = None) -> dict:
    if not pmids:
        return {}
    clean_pmids = []
    for p in pmids:
        if pd.notna(p):
            p_str = str(p).strip()
            # Guard: PubMed Central IDs (PMCID) must not be confused with PubMed IDs (PMID)
            if p_str.upper().startswith('PMC'):
                continue
            digits = re.sub(r'\D', '', p_str.rstrip('.0'))
            if digits:
                clean_pmids.append(digits)
    if not clean_pmids:
        return {}
    
    seen = set()
    unique_pmids = [p for p in clean_pmids if not (p in seen or seen.add(p))]
    
    results = {}
    batch_size = 50
    for i in range(0, len(unique_pmids), batch_size):
        batch = unique_pmids[i:i+batch_size]
        filter_str = "pmid:" + "|".join(batch)
        url = f"https://api.openalex.org/works?filter={filter_str}&per-page={batch_size}"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(0.15 * (attempt + 1))
                response = requests.get(url, headers=HEADERS, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    for work in data.get('results', []):
                        pmid_url = work.get('ids', {}).get('pmid', '')
                        if pmid_url:
                            pmid_val = str(pmid_url).rstrip('/').split('/')[-1]
                            results[pmid_val] = work
                    break
                elif response.status_code in [429, 500, 502, 503, 504]:
                    if log_list is not None:
                        log_list.append(f"[API WARN] OpenAlex PMID batch failed (HTTP {response.status_code}). Retry {attempt+1}/{max_retries}...")
                    time.sleep(1.0 * (attempt + 1))
                else:
                    break
            except Exception as e:
                if attempt == max_retries - 1 and log_list is not None:
                    log_list.append(f"[API ERROR] OpenAlex PMID batch dropped after {max_retries} retries: {str(e)}")
                elif log_list is not None:
                    log_list.append(f"[API WARN] OpenAlex PMID batch timeout. Retry {attempt+1}/{max_retries}...")
    return results

# Tier 2: Crossref
def fetch_crossref_by_doi(doi: str, log_list: list = None) -> dict:
    if pd.isna(doi) or not str(doi).strip(): return None
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "")
    
    cache = _load_cr_cache()
    if clean_doi in cache:
        return cache[clean_doi]

    _cr_limiter.wait()
    url = f"https://api.crossref.org/works/{clean_doi}"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=12)
            if response.status_code == 200:
                data = response.json().get('message')
                if data:
                    cache[clean_doi] = data
                    _save_cr_cache(cache)
                    return data
                break
            elif response.status_code in [429, 500, 502, 503, 504]:
                time.sleep(0.5 * (attempt + 1))
            else:
                break
        except Exception as e:
            if attempt == max_retries - 1 and log_list is not None:
                log_list.append(f"[API ERROR] Crossref dropped for DOI {clean_doi}: {str(e)[:100]}")
            time.sleep(0.5)
    return None

# Tier 3: PubMed (Batched up to 100 PMIDs per call, <= 3 req/sec)
def fetch_pubmed_batch(pmids: list) -> dict:
    if not pmids:
        return {}
    clean_pmids = [str(p).strip() for p in pmids if pd.notna(p) and str(p).strip().isdigit()]
    if not clean_pmids:
        return {}

    seen = set()
    unique_pmids = [p for p in clean_pmids if not (p in seen or seen.add(p))]

    results = {}
    batch_size = 100
    for i in range(0, len(unique_pmids), batch_size):
        chunk = unique_pmids[i:i+batch_size]
        id_str = ",".join(chunk)
        efetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={id_str}&retmode=xml"
        try:
            time.sleep(0.35)  # Strictly <= 3 req/sec NCBI polite rate limit
            response = requests.get(efetch_url, headers=HEADERS, timeout=20)
            if response.status_code == 200:
                try:
                    root = ET.fromstring(response.content)
                    for article in root.findall(".//PubmedArticle"):
                        pmid_node = article.find(".//MedlineCitation/PMID")
                        if pmid_node is None or not pmid_node.text:
                            continue
                        p_id = pmid_node.text.strip()
                        mesh_matches = [
                            desc.text.strip()
                            for desc in article.findall(".//MeshHeading/DescriptorName")
                            if desc.text
                        ]
                        abstract_parts = [
                            ab.text.strip()
                            for ab in article.findall(".//Abstract/AbstractText")
                            if ab.text
                        ]
                        abstract = " ".join(abstract_parts) if abstract_parts else None
                        results[p_id] = {
                            'mesh': mesh_matches,
                            'abstract': abstract
                        }
                except Exception:
                    # Regex fallback if malformed XML chunk
                    articles_raw = response.text.split("<PubmedArticle>")
                    for raw in articles_raw[1:]:
                        pmid_m = re.search(r'<PMID[^>]*>(.*?)</PMID>', raw)
                        if not pmid_m:
                            continue
                        p_id = pmid_m.group(1).strip()
                        mesh_matches = re.findall(r'<DescriptorName[^>]*>(.*?)</DescriptorName>', raw)
                        abstract_matches = re.findall(r'<AbstractText[^>]*>(.*?)</AbstractText>', raw)
                        results[p_id] = {
                            'mesh': mesh_matches,
                            'abstract': " ".join(abstract_matches) if abstract_matches else None
                        }
        except Exception:
            pass
    return results

def fetch_pubmed_by_pmid(pmid: str) -> dict:
    if pd.isna(pmid) or not str(pmid).strip(): return None
    res = fetch_pubmed_batch([str(pmid).strip()])
    return res.get(str(pmid).strip())

# Tier 4: Semantic Scholar (Batched up to 500 DOIs per call, <= 1 req/sec)
_SS_CACHE = None

def _load_ss_cache() -> dict:
    global _SS_CACHE
    if _SS_CACHE is not None:
        return _SS_CACHE
    if os.path.exists(SS_CACHE_FILE):
        try:
            with open(SS_CACHE_FILE, "r", encoding="utf-8") as f:
                _SS_CACHE = json.load(f)
                return _SS_CACHE
        except Exception:
            _SS_CACHE = {}
    else:
        _SS_CACHE = {}
    return _SS_CACHE

def _save_ss_cache(cache: dict):
    global _SS_CACHE
    _SS_CACHE = cache
    try:
        with open(SS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def fetch_semanticscholar_batch(dois: list, log_list: list = None) -> dict:
    if not dois:
        return {}
    clean_dois = [
        str(doi).strip().replace("https://doi.org/", "").replace("doi:", "").lower()
        for doi in dois
        if pd.notna(doi) and str(doi).strip()
    ]
    if not clean_dois:
        return {}

    seen = set()
    unique_dois = [d for d in clean_dois if not (d in seen or seen.add(d))]

    cache = _load_ss_cache()
    results = {}
    missing_dois = []

    for d in unique_dois:
        if d in cache:
            results[d] = cache[d]
        else:
            missing_dois.append(d)

    if not missing_dois:
        return results

    batch_size = 500
    cache_dirty = False
    for i in range(0, len(missing_dois), batch_size):
        chunk = missing_dois[i:i+batch_size]
        ids_payload = [f"DOI:{c}" for c in chunk]
        url = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,abstract,tldr,authors,authors.name,authors.authorId"
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(1.0 * (attempt + 1))  # Strictly <= 1 req/sec Semantic Scholar rate limit
                resp = requests.post(url, json={"ids": ids_payload}, headers=HEADERS, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for doi_key, paper in zip(chunk, data):
                            if paper and isinstance(paper, dict) and not paper.get('error'):
                                results[doi_key] = paper
                                cache[doi_key] = paper
                                cache_dirty = True
                    break
                elif resp.status_code in [429, 500, 502, 503, 504]:
                    if log_list is not None:
                        log_list.append(f"[API WARN] Semantic Scholar batch failed (HTTP {resp.status_code}). Retry {attempt+1}/{max_retries}...")
                    time.sleep(2.0 * (attempt + 1))
                else:
                    break
            except Exception as e:
                if attempt == max_retries - 1 and log_list is not None:
                    log_list.append(f"[API ERROR] Semantic Scholar batch dropped after {max_retries} retries: {str(e)}")
                elif log_list is not None:
                    log_list.append(f"[API WARN] Semantic Scholar batch timeout. Retry {attempt+1}/{max_retries}...")

    if cache_dirty:
        _save_ss_cache(cache)

    return results

def fetch_semanticscholar_by_doi(doi: str, log_list: list = None) -> dict:
    if pd.isna(doi) or not str(doi).strip(): return None
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "").lower()
    batch_res = fetch_semanticscholar_batch([clean_doi], log_list=log_list)
    return batch_res.get(clean_doi)

# ---------------------------------------------------------
# Title Normalization & Multi-Signal Triangulation
# ---------------------------------------------------------
def normalize_title_for_matching(title: str) -> str:
    if not title or pd.isna(title):
        return ""
    t = str(title).strip().lower()
    t = re.sub(r'^[\[\(]\s*|\s*[\]\)]$', '', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def token_sort_similarity(s1: str, s2: str) -> float:
    w1 = " ".join(sorted(s1.split()))
    w2 = " ".join(sorted(s2.split()))
    if not w1 or not w2:
        return 0.0
    return difflib.SequenceMatcher(None, w1, w2).ratio()

def extract_author_surnames(author_str: str) -> list[str]:
    if not author_str or pd.isna(author_str):
        return []
    surnames = []
    authors = re.split(r';|\band\b', str(author_str), flags=re.IGNORECASE)
    for auth in authors:
        cleaned = re.sub(r'[^\w\s]', '', auth).strip()
        tokens = [tok.lower() for tok in cleaned.split() if len(tok) >= 2]
        if tokens:
            surnames.extend([t for t in tokens if len(t) >= 3])
    return list(set(surnames))

def verify_candidate_match(query_title: str, query_author: str, query_year: str,
                           cand_title: str, cand_authors: list | str, cand_year: str) -> tuple[bool, float]:
    """
    Triangulates candidate bibliographic match across Title similarity,
    Author overlap, and Publication Year proximity to eliminate false positives.
    """
    if not query_title or not cand_title:
        return False, 0.0

    q_norm = normalize_title_for_matching(query_title)
    c_norm = normalize_title_for_matching(cand_title)
    if not q_norm or not c_norm:
        return False, 0.0

    if q_norm == c_norm:
        title_sim = 1.0
    else:
        seq_sim = difflib.SequenceMatcher(None, q_norm, c_norm).ratio()
        tok_sim = token_sort_similarity(q_norm, c_norm)
        title_sim = max(seq_sim, tok_sim)
        
        # Subtitle handling (prefix containment or colon/dash split)
        prefix_match = False
        min_len = min(len(q_norm), len(c_norm))
        if min_len >= 18 and (q_norm.startswith(c_norm) or c_norm.startswith(q_norm)):
            prefix_match = True
        else:
            q_main = normalize_title_for_matching(re.split(r'[:\-\u2013\u2014]', str(query_title))[0])
            c_main = normalize_title_for_matching(re.split(r'[:\-\u2013\u2014]', str(cand_title))[0])
            if (len(q_main) >= 18 and q_main == c_norm) or (len(c_main) >= 18 and c_main == q_norm):
                prefix_match = True
        
        if prefix_match:
            title_sim = max(title_sim, 0.84)

    author_matched = False
    author_bonus = 0.0
    if query_author:
        q_surnames = set(extract_author_surnames(query_author))
        if q_surnames:
            c_author_text = ""
            if isinstance(cand_authors, list):
                for a in cand_authors:
                    if isinstance(a, dict):
                        c_author_text += " " + str(a.get('family', '')) + " " + str(a.get('name', '')) + " " + str(a.get('author', {}).get('display_name', ''))
                    else:
                        c_author_text += " " + str(a)
            else:
                c_author_text = str(cand_authors)
            c_surnames = set(extract_author_surnames(c_author_text))
            
            overlap = q_surnames & c_surnames
            if overlap:
                author_matched = True
                author_bonus = 0.08
            elif len(q_surnames) >= 2 and len(c_surnames) >= 2 and title_sim < 0.90:
                author_bonus = -0.15

    year_bonus = 0.0
    if query_year and cand_year:
        try:
            m_qy = re.search(r'\b(19\d\d|20\d\d)\b', str(query_year))
            m_cy = re.search(r'\b(19\d\d|20\d\d)\b', str(cand_year))
            if m_qy and m_cy:
                diff = abs(int(m_qy.group(1)) - int(m_cy.group(1)))
                if diff == 0:
                    year_bonus = 0.05
                elif diff == 1:
                    year_bonus = 0.02
                elif diff > 3 and title_sim < 0.92:
                    year_bonus = -0.12
        except Exception:
            pass

    confidence = min(1.0, max(0.0, title_sim + author_bonus + year_bonus))

    if title_sim >= 0.85:
        return True, confidence
    if author_matched and title_sim >= 0.76 and confidence >= 0.78:
        return True, confidence
    if confidence >= 0.82:
        return True, confidence

    return False, confidence

# ---------------------------------------------------------
# Multi-Engine DOI Search Functions
# ---------------------------------------------------------
def fetch_doi_from_crossref(title: str, author: str = None, year: str = None, log_list: list = None) -> tuple[str | None, dict | None, float]:
    """Queries Crossref Works Search for a matching paper and returns (doi, item_data, confidence)."""
    if not title or pd.isna(title):
        return None, None, 0.0
    clean_title = normalize_title_for_matching(title)
    if not clean_title:
        return None, None, 0.0

    params = {'query.title': clean_title, 'rows': 3}
    if author:
        surnames = extract_author_surnames(author)
        if surnames:
            params['query.author'] = surnames[0]

    _cr_limiter.wait()
    try:
        resp = requests.get("https://api.crossref.org/works", params=params, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            items = resp.json().get('message', {}).get('items', [])
            for item in items:
                cand_doi = extract_valid_doi(item.get('DOI'))
                if not cand_doi:
                    continue
                cand_titles = item.get('title', [])
                cand_title = cand_titles[0] if cand_titles else ""
                cand_authors = item.get('author', [])
                
                cand_year = None
                for date_key in ['published-print', 'published-online', 'issued', 'created']:
                    parts = item.get(date_key, {}).get('date-parts', [])
                    if parts and parts[0] and parts[0][0]:
                        cand_year = str(parts[0][0])
                        break

                is_match, conf = verify_candidate_match(title, author, year, cand_title, cand_authors, cand_year)
                if is_match:
                    return cand_doi, item, conf
    except Exception as e:
        if log_list is not None:
            log_list.append(f"[DOI Crossref WARN] Search exception: {str(e)[:100]}")
    return None, None, 0.0

def fetch_doi_from_openalex(title: str, author: str = None, year: str = None, log_list: list = None) -> tuple[str | None, dict | None, float]:
    """Queries OpenAlex BM25 search for a matching work and returns (doi, work_data, confidence)."""
    if not title or pd.isna(title):
        return None, None, 0.0
    clean_title = normalize_title_for_matching(title)
    if not clean_title:
        return None, None, 0.0

    params = {'search': clean_title, 'per-page': 3}
    _oa_limiter.wait()
    try:
        resp = requests.get("https://api.openalex.org/works", params=params, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            for cand in results:
                cand_doi = extract_valid_doi(cand.get('doi'))
                cand_title = cand.get('title') or ""
                cand_authors = cand.get('authorships', [])
                cand_year = str(cand.get('publication_year', ''))

                is_match, conf = verify_candidate_match(title, author, year, cand_title, cand_authors, cand_year)
                if is_match:
                    return cand_doi, cand, conf
    except Exception as e:
        if log_list is not None:
            log_list.append(f"[DOI OpenAlex WARN] Search exception: {str(e)[:100]}")
    return None, None, 0.0

def fetch_doi_from_pubmed(title: str, author: str = None, year: str = None, log_list: list = None) -> tuple[str | None, dict | None, float]:
    """Queries PubMed eSearch & eFetch to recover a biomedical paper's DOI."""
    if not title or pd.isna(title):
        return None, None, 0.0
    clean_title = normalize_title_for_matching(title)
    if not clean_title or len(clean_title) < 10:
        return None, None, 0.0

    params = {
        'db': 'pubmed',
        'term': f"{clean_title}[Title]",
        'retmode': 'json',
        'retmax': 2
    }
    _pm_limiter.wait()
    try:
        resp = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            idlist = resp.json().get('esearchresult', {}).get('idlist', [])
            if idlist:
                cand_pmid = idlist[0]
                _pm_limiter.wait()
                efetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={cand_pmid}&retmode=xml"
                ef_resp = requests.get(efetch_url, headers=HEADERS, timeout=12)
                if ef_resp.status_code == 200:
                    try:
                        root = ET.fromstring(ef_resp.content)
                        article = root.find(".//PubmedArticle")
                        if article is not None:
                            cand_t_node = article.find(".//ArticleTitle")
                            cand_title = cand_t_node.text if cand_t_node is not None else ""
                            cand_doi = None
                            for aid in article.findall(".//ArticleId"):
                                if aid.get('IdType') == 'doi' and aid.text:
                                    cand_doi = extract_valid_doi(aid.text)
                                    break
                            cand_year = None
                            y_node = article.find(".//JournalIssue/PubDate/Year")
                            if y_node is not None:
                                cand_year = y_node.text

                            cand_authors = [
                                (a.find("LastName").text if a.find("LastName") is not None else "")
                                for a in article.findall(".//Author")
                            ]
                            is_match, conf = verify_candidate_match(title, author, year, cand_title, cand_authors, cand_year)
                            if is_match and cand_doi:
                                return cand_doi, {'pmid': cand_pmid, 'title': cand_title}, conf
                    except Exception:
                        pass
    except Exception as e:
        if log_list is not None:
            log_list.append(f"[DOI PubMed WARN] Search exception: {str(e)[:100]}")
    return None, None, 0.0

def fetch_doi_from_semanticscholar(title: str, author: str = None, year: str = None, log_list: list = None) -> tuple[str | None, dict | None, float]:
    """Queries Semantic Scholar Match API as a fallback to locate paper IDs and DOIs."""
    if not title or pd.isna(title):
        return None, None, 0.0
    clean_title = normalize_title_for_matching(title)
    if not clean_title or len(clean_title) < 10:
        return None, None, 0.0

    _ss_limiter.wait()
    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search/match",
            params={'query': clean_title},
            headers=HEADERS,
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            if data:
                item = data[0]
                cand_doi = extract_valid_doi(item.get('externalIds', {}).get('DOI'))
                cand_title = item.get('title') or ""
                cand_authors = item.get('authors', [])
                cand_year = str(item.get('year', ''))

                is_match, conf = verify_candidate_match(title, author, year, cand_title, cand_authors, cand_year)
                if is_match and cand_doi:
                    return cand_doi, item, conf
    except Exception as e:
        if log_list is not None:
            log_list.append(f"[DOI SemanticScholar WARN] Search exception: {str(e)[:100]}")
    return None, None, 0.0

def resolve_single_record_doi(rec: dict, log_list: list = None) -> dict:
    """Attempts to discover a DOI for a single record across Crossref, OpenAlex, PubMed, and Semantic Scholar."""
    row_idx = rec['row_idx']
    title = rec.get('title')
    author = rec.get('author')
    year = rec.get('year')

    cache = _load_doi_search_cache()
    norm_t = normalize_title_for_matching(title) if title else ""
    if norm_t and norm_t in cache:
        cached_entry = cache[norm_t]
        return {
            'row_idx': row_idx,
            'doi': cached_entry.get('doi'),
            'engine': cached_entry.get('engine', 'Cache'),
            'conf': cached_entry.get('conf', 1.0),
            'meta': None
        }

    # 1. Primary Engine: Crossref Works Search
    doi, cr_meta, conf = fetch_doi_from_crossref(title, author, year, log_list=log_list)
    if doi:
        cache[norm_t] = {'doi': doi, 'engine': 'Crossref', 'conf': conf}
        _save_doi_search_cache(cache)
        return {'row_idx': row_idx, 'doi': doi, 'engine': 'Crossref', 'conf': conf, 'meta': cr_meta}

    # 2. Secondary Engine: OpenAlex BM25 Search
    doi, oa_meta, conf = fetch_doi_from_openalex(title, author, year, log_list=log_list)
    if doi:
        cache[norm_t] = {'doi': doi, 'engine': 'OpenAlex', 'conf': conf}
        _save_doi_search_cache(cache)
        return {'row_idx': row_idx, 'doi': doi, 'engine': 'OpenAlex', 'conf': conf, 'meta': oa_meta}

    # 3. Tertiary Engine: PubMed eSearch (Biomedical)
    doi, pm_meta, conf = fetch_doi_from_pubmed(title, author, year, log_list=log_list)
    if doi:
        cache[norm_t] = {'doi': doi, 'engine': 'PubMed', 'conf': conf}
        _save_doi_search_cache(cache)
        return {'row_idx': row_idx, 'doi': doi, 'engine': 'PubMed', 'conf': conf, 'meta': pm_meta}

    # 4. Final Fallback: Semantic Scholar Match API
    doi, ss_meta, conf = fetch_doi_from_semanticscholar(title, author, year, log_list=log_list)
    if doi:
        cache[norm_t] = {'doi': doi, 'engine': 'Semantic Scholar', 'conf': conf}
        _save_doi_search_cache(cache)
        return {'row_idx': row_idx, 'doi': doi, 'engine': 'Semantic Scholar', 'conf': conf, 'meta': ss_meta}

    return {'row_idx': row_idx, 'doi': None, 'engine': None, 'conf': 0.0, 'meta': None}

def resolve_missing_dois_concurrent(records_to_resolve: list, log_list: list = None, max_workers: int = 4, on_progress: callable = None) -> dict:
    """Concurrently discovers DOIs for records using ThreadPoolExecutor with politeness rate limiters."""
    if not records_to_resolve:
        return {}

    results = {}
    completed_count = 0
    total_count = len(records_to_resolve)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(resolve_single_record_doi, rec, log_list): rec for rec in records_to_resolve}
        for future in as_completed(futures):
            completed_count += 1
            rec = futures[future]
            try:
                res = future.result()
                if res and res.get('doi'):
                    results[res['row_idx']] = res
                    if log_list is not None:
                        t_disp = str(rec.get('title') or '')[:60]
                        log_list.append(
                            f"[DOI Discovery] Row {res['row_idx']}: Found DOI '{res['doi']}' via {res.get('engine')} "
                            f"(conf: {res.get('conf', 1.0):.2f}) for Title: '{t_disp}'"
                        )
                else:
                    if log_list is not None:
                        t_disp = str(rec.get('title') or '')[:60]
                        log_list.append(
                            f"[DOI Discovery - No Match] Row {rec['row_idx']}: No matching DOI found across engines for Title: '{t_disp}'"
                        )
            except Exception as e:
                if log_list is not None:
                    log_list.append(f"[DOI Resolver Exception] Row {rec['row_idx']}: {str(e)[:100]}")
            
            if on_progress:
                try:
                    on_progress(completed_count, total_count, len(results))
                except Exception:
                    pass

    return results

def fetch_openalex_data_by_title(title: str, author: str = None, year: str = None) -> dict:
    """Residual helper for unindexed non-DOI records, using BM25 search with metadata triangulation."""
    doi, oa_cand, conf = fetch_doi_from_openalex(title, author=author, year=year)
    return oa_cand if conf >= 0.82 else None

# ---------------------------------------------------------
# Updates Applicator
# ---------------------------------------------------------
def apply_openalex_data(oa_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list, is_ultimate: bool = False):
    needs_update = lambda f: f in fields_to_enrich and (_get_field(row, f) is None or is_ultimate)
    has_doi = _get_field(row, 'DOI') is not None
    
    updates['enriched'] = True
    
    if not has_doi:
        new_doi = oa_data.get('doi')
        if new_doi: updates['DOI'] = str(new_doi).replace("https://doi.org/", "")
        else: missed.append('DOI')
        
    updates['OpenAlex ID'] = str(oa_data.get('id')).replace("https://openalex.org/", "")

    # Fetch canonical English title if requested or missing
    if 'Title' in fields_to_enrich or needs_update('Title'):
        oa_title = oa_data.get('title')
        if oa_title and str(oa_title).strip():
            updates['Title'] = str(oa_title).strip()

    author_curr = _get_field(row, 'Author')
    if 'Author' in fields_to_enrich or needs_update('Author') or (author_curr and author_has_initials(str(author_curr))):
        oa_authorships = oa_data.get('authorships', [])
        if oa_authorships:
            if author_curr and pd.notna(author_curr) and str(author_curr).strip():
                raw_list = split_authors_string(str(author_curr))
                resolved, was_enr = disambiguate_paper_authors(raw_list, oa_authorships=oa_authorships)
                if was_enr:
                    updates['Author'] = "; ".join(a['full_name'] for a in resolved)
                else:
                    new_auth_str = "; ".join(a['full_name'] for a in resolved)
                    if new_auth_str and new_auth_str != str(author_curr).strip():
                        updates['Author'] = new_auth_str
                    else:
                        val = format_authors(oa_authorships)
                        if pd.notna(val) and str(val).strip():
                            from features.gender import standardize_author_string
                            updates['Author'] = standardize_author_string(str(val))
            else:
                val = format_authors(oa_authorships)
                if pd.notna(val) and str(val).strip():
                    from features.gender import standardize_author_string
                    updates['Author'] = standardize_author_string(str(val))
        elif pd.isna(author_curr):
            missed.append('Author')

    if needs_update('Affiliations') or needs_update('Country'):
        aff_val, cnt_val = format_affiliations_and_countries(oa_data.get('authorships'))
        if needs_update('Affiliations'):
            if pd.isna(aff_val): missed.append('Affiliations')
            else: updates['Affiliations'] = aff_val
        if needs_update('Country'):
            if pd.isna(cnt_val): missed.append('Country')
            else: updates['Country'] = cnt_val

    if needs_update('Address'):
        addr_val = format_addresses(oa_data.get('authorships'))
        if pd.notna(addr_val): updates['Address'] = addr_val
        else: missed.append('Address')

    if needs_update('Location'):
        loc_val = format_location_from_oa(oa_data)
        if pd.notna(loc_val): updates['Location'] = loc_val
        else: missed.append('Location')

    # Fetch canonical English abstract if requested or missing
    if 'Abstract' in fields_to_enrich or needs_update('Abstract'):
        val = reconstruct_abstract(oa_data.get('abstract_inverted_index'))
        if pd.notna(val) and str(val).strip():
            updates['Abstract'] = str(val).strip()
        else:
            missed.append('Abstract (OA)')
        
    if 'Keywords' in fields_to_enrich or needs_update('Keywords'):
        val = format_list_of_dicts(oa_data.get('keywords'))
        if pd.notna(val): updates['Keywords'] = val
        else: missed.append('Keywords')
        
    if 'Concepts' in fields_to_enrich or needs_update('Concepts'):
        val = format_list_of_dicts(oa_data.get('concepts'))
        if pd.notna(val): updates['Concepts'] = val
        else: missed.append('Concepts')

    if needs_update('Article References'):
        val = format_references(oa_data.get('referenced_works'))
        if pd.isna(val): missed.append('Article References')
        else: updates['Article References'] = val
         
    if needs_update('Publication Year'):
        val = oa_data.get('publication_year')
        from utils.formatters import clean_year_value
        val_clean = clean_year_value(val)
        if not val_clean: missed.append('Publication Year')
        else: updates['Publication Year'] = val_clean
        
    # In ultimate mode or if Times Cited requested, always refresh citation count
    if 'Times Cited' in fields_to_enrich or needs_update('Times Cited') or is_ultimate:
        val = oa_data.get('cited_by_count')
        if pd.isna(val): missed.append('Times Cited')
        else: updates['Times Cited'] = val

    if needs_update('Publisher'):
        primary_loc = oa_data.get('primary_location') or {}
        val = primary_loc.get('source', {}).get('host_organization_name') if primary_loc and primary_loc.get('source') else pd.NA
        if pd.isna(val): missed.append('Publisher')
        else: updates['Publisher'] = val

    if needs_update('Journal'):
        primary_loc = oa_data.get('primary_location') or {}
        val = primary_loc.get('source', {}).get('display_name') if primary_loc and primary_loc.get('source') else pd.NA
        if pd.isna(val): missed.append('Journal')
        else: updates['Journal'] = str(val).strip()

    if needs_update('ISSN'):
        primary_loc = oa_data.get('primary_location') or {}
        source = primary_loc.get('source') or {}
        issn_val = source.get('issn_l') or (source.get('issn') and ", ".join(source.get('issn')))
        if issn_val and str(issn_val).strip(): updates['ISSN'] = str(issn_val).strip()
        else: missed.append('ISSN')
        
    if needs_update('Document Type'):
        val = oa_data.get('type')
        if pd.isna(val): missed.append('Document Type')
        else: updates['Document Type'] = str(val).title()
        
    if needs_update('Language'):
        val = oa_data.get('language')
        if pd.isna(val): missed.append('Language')
        else: updates['Language'] = str(val).upper()
        
    if needs_update('Open Access'):
        oa_status = oa_data.get('open_access', {}).get('is_oa')
        if oa_status is None: missed.append('Open Access')
        else: updates['Open Access'] = bool(oa_status)
        
    if needs_update('Funding'):
        val = format_list_of_dicts(oa_data.get('grants'), key='funder_display_name')
        if pd.isna(val): missed.append('Funding')
        else: updates['Funding'] = val

def extract_crossref_publication_year(cr_data: dict) -> tuple[str | None, str | None, dict]:
    """
    Extracts publication year from Crossref metadata with date intelligence:
    - Collects date-parts from published-online, published-print, issued, created.
    - If published-print is in the future (> current_year) and published-online or issued is present,
      prefers the actual publication date (online/issued).
    - If published-online is earlier than or equal to published-print (Early View / Advance Article),
      prefers published-online as the true public availability date.
    - Returns (cleaned_year, source_date_key, all_dates_dict).
    """
    from datetime import datetime
    current_year = datetime.now().year
    
    dates_found = {}
    for k in ['published-online', 'published-print', 'issued', 'created']:
        parts = cr_data.get(k, {}).get('date-parts', [])
        if parts and parts[0] and parts[0][0]:
            try:
                p_strs = [str(x) for x in parts[0] if x is not None]
                dates_found[k] = '-'.join(p_strs)
            except (ValueError, TypeError):
                pass

    if not dates_found:
        return None, None, {}

    year_map = {}
    for k, d_str in dates_found.items():
        try:
            year_map[k] = int(d_str.split('-')[0])
        except (ValueError, IndexError):
            pass

    y_online = year_map.get('published-online')
    y_print = year_map.get('published-print')
    y_issued = year_map.get('issued')
    y_created = year_map.get('created')

    chosen_year = None
    chosen_key = None

    if y_print and y_print > current_year:
        if y_online and y_online <= current_year:
            chosen_year = y_online
            chosen_key = f"published-online ({dates_found.get('published-online')}; avoided future print date {dates_found.get('published-print')})"
        elif y_issued and y_issued <= current_year:
            chosen_year = y_issued
            chosen_key = f"issued ({dates_found.get('issued')}; avoided future print date {dates_found.get('published-print')})"
        elif y_created and y_created <= current_year:
            chosen_year = y_created
            chosen_key = f"created ({dates_found.get('created')}; avoided future print date {dates_found.get('published-print')})"
        else:
            chosen_year = y_print
            chosen_key = f"published-print ({dates_found.get('published-print')})"
    elif y_online:
        chosen_year = y_online
        chosen_key = f"published-online ({dates_found.get('published-online')})"
    elif y_issued:
        chosen_year = y_issued
        chosen_key = f"issued ({dates_found.get('issued')})"
    elif y_print:
        chosen_year = y_print
        chosen_key = f"published-print ({dates_found.get('published-print')})"
    elif y_created:
        chosen_year = y_created
        chosen_key = f"created ({dates_found.get('created')})"

    from utils.formatters import clean_year_value
    val_clean = clean_year_value(chosen_year) if chosen_year else None
    return val_clean, chosen_key, dates_found

def apply_crossref_data(cr_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list, existing_updates: dict = None, log_context: dict = None):
    needs_update = lambda f: (
        f in fields_to_enrich 
        and _get_field(row, f) is None 
        and (existing_updates is None or f not in existing_updates or _get_field(existing_updates, f) is None) 
        and f not in updates
    )
    
    if ('Title' in fields_to_enrich or needs_update('Title')) and needs_update('Title') and 'Title' not in updates:
        cr_title = cr_data.get('title')
        if cr_title and isinstance(cr_title, list) and len(cr_title) > 0 and str(cr_title[0]).strip():
            updates['Title'] = str(cr_title[0]).strip()

    if ('Abstract' in fields_to_enrich or needs_update('Abstract')) and needs_update('Abstract') and 'Abstract' not in updates:
        cr_abs = cr_data.get('abstract')
        if cr_abs and str(cr_abs).strip():
            clean_abs = re.sub(r'<[^>]+>', '', str(cr_abs)).strip()
            if clean_abs:
                updates['Abstract'] = clean_abs

    if needs_update('Journal'):
        c_title = cr_data.get('container-title')
        if c_title and isinstance(c_title, list) and len(c_title) > 0 and str(c_title[0]).strip():
            updates['Journal'] = str(c_title[0]).strip()
        elif isinstance(c_title, str) and c_title.strip():
            updates['Journal'] = c_title.strip()

    if needs_update('Publisher'):
        val = cr_data.get('publisher')
        if val:
            if isinstance(val, list):
                val = val[0] if len(val) > 0 else None
            if val and str(val).strip():
                updates['Publisher'] = str(val).strip()
        
    # Publication Year extraction with date intelligence
    cr_year, cr_year_reason, cr_dates = extract_crossref_publication_year(cr_data)
    if log_context is not None:
        log_context['crossref_dates'] = cr_dates
        log_context['crossref_year_reason'] = cr_year_reason
        log_context['crossref_year'] = cr_year

    if needs_update('Publication Year'):
        if cr_year:
            updates['Publication Year'] = cr_year
            
    author_curr = updates.get('Author') or (existing_updates.get('Author') if existing_updates else None) or _get_field(row, 'Author')
    if 'Author' in fields_to_enrich or needs_update('Author') or (author_curr and author_has_initials(str(author_curr))):
        authors = cr_data.get('author', [])
        if authors:
            if author_curr and pd.notna(author_curr) and str(author_curr).strip():
                raw_list = split_authors_string(str(author_curr))
                resolved, was_enr = disambiguate_paper_authors(raw_list, cr_authors=authors)
                if was_enr:
                    updates['Author'] = "; ".join(a['full_name'] for a in resolved)
                else:
                    new_auth_str = "; ".join(a['full_name'] for a in resolved)
                    if new_auth_str and new_auth_str != str(author_curr).strip():
                        updates['Author'] = new_auth_str
            elif 'Author' not in updates and (existing_updates is None or 'Author' not in existing_updates):
                from features.gender import standardize_author_name
                author_names = [standardize_author_name(f"{a.get('given', '')} {a.get('family', '')}".strip()) for a in authors if a.get('family')]
                author_names = [a for a in author_names if a]
                if author_names: updates['Author'] = "; ".join(author_names)

    if needs_update('Volume') and cr_data.get('volume'):
        updates['Volume'] = str(cr_data.get('volume'))
    if needs_update('Issue') and cr_data.get('issue'):
        updates['Issue'] = str(cr_data.get('issue'))
    if needs_update('Pages') and cr_data.get('page'):
        updates['Pages'] = str(cr_data.get('page'))
    if needs_update('ISSN') and cr_data.get('ISSN'):
        issn_list = cr_data.get('ISSN')
        updates['ISSN'] = ", ".join(issn_list) if isinstance(issn_list, list) else str(issn_list)

    # Document Type mapping from Crossref type
    if needs_update('Document Type'):
        cr_type = cr_data.get('type')
        if cr_type:
            type_map = {
                'journal-article': 'Journal Article',
                'proceedings-article': 'Conference Paper',
                'book-chapter': 'Book Chapter',
                'book': 'Book',
                'posted-content': 'Preprint',
                'dataset': 'Dataset',
                'report': 'Report',
                'dissertation': 'Dissertation'
            }
            updates['Document Type'] = type_map.get(str(cr_type).lower(), str(cr_type).title())

    # Language from Crossref language
    if needs_update('Language'):
        lang = cr_data.get('language')
        if lang:
            updates['Language'] = str(lang).upper()

    # Funding from Crossref funder list
    if needs_update('Funding'):
        funders = cr_data.get('funder', [])
        if funders and isinstance(funders, list):
            f_names = [f.get('name') for f in funders if isinstance(f, dict) and f.get('name')]
            if f_names:
                updates['Funding'] = "; ".join(f_names)

    # Open Access from Crossref license
    if needs_update('Open Access'):
        licenses = cr_data.get('license', [])
        if licenses and isinstance(licenses, list):
            is_oa = any(
                ('creativecommons.org' in str(lic.get('URL', '')).lower() or 'open' in str(lic.get('URL', '')).lower())
                for lic in licenses if isinstance(lic, dict)
            )
            updates['Open Access'] = is_oa

    # Article References from Crossref reference list
    if needs_update('Article References'):
        refs = cr_data.get('reference', [])
        if refs and isinstance(refs, list):
            ref_dois = [str(r.get('DOI')).strip() for r in refs if isinstance(r, dict) and r.get('DOI')]
            if ref_dois:
                updates['Article References'] = "; ".join(ref_dois)

    # Times Cited from is-referenced-by-count
    if ('Times Cited' in fields_to_enrich or needs_update('Times Cited')) and needs_update('Times Cited') and 'Times Cited' not in updates:
        cit_count = cr_data.get('is-referenced-by-count')
        if cit_count is not None and pd.notna(cit_count):
            try:
                updates['Times Cited'] = int(cit_count)
            except Exception:
                pass

    # Affiliations & Country from Crossref author affiliations
    if needs_update('Affiliations') or needs_update('Country'):
        cr_authors = cr_data.get('author', [])
        affs = []
        for a in cr_authors:
            if isinstance(a, dict):
                for aff in a.get('affiliation', []):
                    if isinstance(aff, dict) and aff.get('name'):
                        affs.append(str(aff['name']).strip())
                    elif isinstance(aff, str) and aff.strip():
                        affs.append(aff.strip())
        if affs:
            unique_affs = "; ".join(sorted(set(affs)))
            if needs_update('Affiliations') and 'Affiliations' not in updates:
                updates['Affiliations'] = unique_affs
            if needs_update('Country') and 'Country' not in updates:
                from core.ingestion import extract_country_from_text
                c_found = extract_country_from_text(unique_affs)
                if c_found:
                    updates['Country'] = c_found

    # Keywords from Crossref subject
    if needs_update('Keywords') and 'Keywords' not in updates:
        subjects = cr_data.get('subject', [])
        if subjects and isinstance(subjects, list):
            updates['Keywords'] = "; ".join(str(s).strip() for s in subjects if str(s).strip())

def apply_pubmed_data(pm_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list, existing_updates: dict = None):
    needs_update = lambda f: (
        f in fields_to_enrich 
        and _get_field(row, f) is None 
        and (existing_updates is None or f not in existing_updates or _get_field(existing_updates, f) is None) 
        and f not in updates
    )
    if ('Abstract' in fields_to_enrich or needs_update('Abstract')) and needs_update('Abstract') and pm_data.get('abstract'):
        updates['Abstract'] = pm_data['abstract']
    if ('Concepts' in fields_to_enrich or needs_update('Concepts')) and needs_update('Concepts') and pm_data.get('mesh'):
        updates['Concepts'] = "; ".join(pm_data['mesh'])

def apply_semanticscholar_data(ss_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list, existing_updates: dict = None):
    needs_update = lambda f: (
        f in fields_to_enrich 
        and _get_field(row, f) is None 
        and (existing_updates is None or f not in existing_updates or _get_field(existing_updates, f) is None) 
        and f not in updates
    )
    
    if needs_update('Title') and 'Title' not in updates:
        ss_title = ss_data.get('title')
        if ss_title and str(ss_title).strip():
            updates['Title'] = str(ss_title).strip()

    if needs_update('Abstract') and 'Abstract' not in updates:
        val = ss_data.get('abstract') or (ss_data.get('tldr') or {}).get('text')
        if val and str(val).strip():
            updates['Abstract'] = str(val).strip()

    # Author Disambiguation via Semantic Scholar AER
    author_curr = updates.get('Author') or (existing_updates.get('Author') if existing_updates else None) or _get_field(row, 'Author')
    if author_curr and pd.notna(author_curr) and str(author_curr).strip() and author_has_initials(str(author_curr)):
        ss_authors = ss_data.get('authors', [])
        if ss_authors:
            raw_list = split_authors_string(str(author_curr))
            resolved, was_enr = disambiguate_paper_authors(raw_list, ss_authors=ss_authors)
            if was_enr:
                updates['Author'] = "; ".join(a['full_name'] for a in resolved)
            else:
                new_auth_str = "; ".join(a['full_name'] for a in resolved)
                if new_auth_str and new_auth_str != str(author_curr).strip():
                    updates['Author'] = new_auth_str

# ---------------------------------------------------------
# Main Enrichment Engine
# ---------------------------------------------------------
def enrich_dataset_openalex(df: pd.DataFrame, fields_to_enrich: list, log_list: list, file_manifest: dict = None, is_ultimate: bool = False) -> pd.DataFrame:
    df = deduplicate_and_merge_columns(df).reset_index(drop=True)
    # Ensure author standardization is mandatory across all enrichment runs
    if 'Author' not in fields_to_enrich:
        fields_to_enrich = list(fields_to_enrich) + ['Author']

    # Ensure text/metadata columns are object dtype to prevent float64 dtype FutureWarnings
    text_cols = [
        'Title', 'Author', 'DOI', 'OpenAlex ID', 'Abstract', 'Journal', 
        'Publisher', 'Country', 'Affiliations', 'Address', 'Location', 
        'Keywords', 'Concepts', 'Article References', 'Document Type', 
        'Language', 'ISSN', 'Volume', 'Issue', 'Pages', 'Funding', 'Open Access'
    ]
    for col in text_cols:
        if col in df.columns:
            if df[col].dtype != 'object':
                df[col] = df[col].astype(object)
        else:
            df[col] = pd.Series(pd.NA, index=df.index, dtype=object)

    st.write("Starting Data Enrichment Pipeline...")
    start_time = time.time()
    
    # 1. Pre-filter tasks
    tasks = []
    dois_to_fetch = []
    for idx, row in df.iterrows():
        if needs_enrichment(row, fields_to_enrich, is_ultimate=is_ultimate):
            tasks.append((idx, row))
            doi_val = _get_field(row, 'DOI')
            if doi_val:
                dois_to_fetch.append(doi_val)
                
    tasks_count = len(tasks)
    progress_bar = st.progress(0)
    
    if tasks_count == 0:
        if log_list is not None:
            log_list.append("Optimization: No API calls made. All selected fields are already populated in the dataset.")
        progress_bar.progress(1.0)
        return df

    # Baseline DOI Inventory
    initial_doi_mask = df['DOI'].notna() & (df['DOI'].astype(str).str.strip() != '') & (df['DOI'].astype(str).str.lower() != 'nan')
    initial_doi_count = int(initial_doi_mask.sum())
    total_records = len(df)
    t15_dois_discovered = 0
    doi_by_engine = Counter()

    if log_list is not None:
        log_list.append("=" * 75)
        log_list.append(f"STARTING ENRICHMENT PIPELINE: {total_records:,} total records ({initial_doi_count:,} with initial DOIs, {total_records - initial_doi_count:,} lacking DOIs)")
        log_list.append(f"Target fields requested ({len(fields_to_enrich)} fields): {fields_to_enrich}")
        log_list.append(f"DOI Baseline: {initial_doi_count:,} / {total_records:,} records ({(initial_doi_count/total_records*100 if total_records else 0):.1f}% coverage) already indexed.")
        log_list.append("=" * 75)

    # Granular Metric Counters
    t1_queried = len(dois_to_fetch)
    t1_resolved = 0
    t2_passed = 0
    t2_resolved = 0
    t3_passed = 0
    t3_resolved = 0
    t4_passed = 0
    t4_resolved = 0
    t5_passed = 0
    t5_resolved = 0

    t1_fields_cnt = Counter()
    t2_fields_cnt = Counter()
    t3_fields_cnt = Counter()
    t4_fields_cnt = Counter()
    t5_fields_cnt = Counter()

    failed_records_audit = []

    # Main Status Container
    status_box = st.container()
    with status_box:
        st.markdown("<h4 style='font-size: 16px; font-weight: 700; color: #1E293B; margin-bottom: 8px;'><i class='bi bi-activity' style='color: #697aa2;'></i> Live Multi-Tier Enrichment Execution</h4>", unsafe_allow_html=True)
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Dataset Records", f"{total_records:,}")
        m2.metric("Records Evaluated", f"{tasks_count:,}")
        m3.metric("DOIs Available", f"{t1_queried:,}")
        m4.metric("No DOIs (Discovery Target)", f"{tasks_count - t1_queried:,}")
        
        doi_tracker_line = st.empty()
        status_text = st.empty()
        progress_bar = st.progress(0)

    def render_doi_tracker_line(discovered_p0=0, discovered_fallback=0, current_phase=""):
        total_now = initial_doi_count + discovered_p0 + discovered_fallback
        pct_now = (total_now / total_records * 100) if total_records > 0 else 0
        new_now = discovered_p0 + discovered_fallback
        
        badge_text = f"🎯 DOIs Found Up to Now: {total_now:,} / {total_records:,} records ({pct_now:.1f}% coverage)"
        sub_text = f"Initial at Ingestion: {initial_doi_count:,} | Newly Discovered: +{new_now:,}"
        if current_phase:
            sub_text += f" | {current_phase}"
            
        doi_tracker_line.markdown(
            f"""
            <div style="background-color: #F0FDF4; border: 1px solid #BBF7D0; border-left: 5px solid #16A34A; padding: 10px 16px; border-radius: 6px; margin: 8px 0; font-family: inherit;">
                <div style="font-weight: 700; color: #15803D; font-size: 14.5px;">
                    <i class="bi bi-fingerprint" style="margin-right: 5px;"></i> {badge_text}
                </div>
                <div style="color: #166534; font-size: 12.5px; margin-top: 3px;">
                    Initial at Ingestion: <b>{initial_doi_count:,}</b> | Newly Discovered: <b>+{new_now:,}</b> {f'| <em>{current_phase}</em>' if current_phase else ''}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        return badge_text

    # Render initial DOI baseline immediately
    render_doi_tracker_line(0, 0, "Enrichment Initialized")

    # ---------------------------------------------------------
    # PHASE 0: CONCURRENT MULTI-ENGINE DOI DISCOVERY
    # (PubMed PMID -> Crossref Search -> OpenAlex Search -> PubMed Search -> Semantic Scholar)
    # ---------------------------------------------------------
    missing_doi_tasks = [
        (idx, row) for idx, row in tasks
        if not _get_field(row, 'DOI') and _get_field(row, 'Title')
    ]

    t0_discovered = 0
    prefetched_meta = {}

    if missing_doi_tasks:
        status_text.markdown(f"**Phase 0 (DOI Discovery Engine):** Investigating **{len(missing_doi_tasks):,} records missing DOIs** across Crossref, OpenAlex, PubMed, and Semantic Scholar...")
        if log_list is not None:
            log_list.append(f"[Phase 0 Start] Initiating concurrent DOI discovery for {len(missing_doi_tasks):,} records lacking DOIs...")
        
        # Step 0A: Fast batch resolution for records having PMIDs
        pmids_for_oa = [
            _get_field(r, 'PMID') for _, r in missing_doi_tasks
            if _get_field(r, 'PMID')
        ]
        oa_pmid_batch_results = fetch_openalex_batch_by_pmids(pmids_for_oa, log_list=log_list) if pmids_for_oa else {}

        records_for_search = []
        for idx, row in missing_doi_tasks:
            pmid = _get_field(row, 'PMID')
            p_str = str(pmid).strip() if pmid else ""
            clean_pm = "" if p_str.upper().startswith('PMC') else re.sub(r'\D', '', p_str.rstrip('.0'))
            found_via_pmid = False
            if clean_pm and clean_pm in oa_pmid_batch_results:
                work = oa_pmid_batch_results[clean_pm]
                work_doi = extract_valid_doi(work.get('doi'))
                if work_doi:
                    df.at[idx, 'DOI'] = work_doi
                    dois_to_fetch.append(work_doi)
                    prefetched_meta[work_doi] = work
                    t0_discovered += 1
                    doi_by_engine['PMID Batch'] += 1
                    found_via_pmid = True
                    if log_list is not None:
                        t_disp = str(_get_field(row, 'Title') or '')[:55]
                        log_list.append(f"[DOI Discovery - PMID] Row {idx}: Discovered DOI '{work_doi}' via PMID {clean_pm} for Title: '{t_disp}'")
                    render_doi_tracker_line(discovered_p0=t0_discovered, current_phase=f"Phase 0: PMID Resolution (+{t0_discovered})")
            
            if not found_via_pmid:
                records_for_search.append({
                    'row_idx': idx,
                    'title': _get_field(row, 'Title'),
                    'author': _get_field(row, 'Author'),
                    'year': _get_field(row, 'Publication Year'),
                    'pmid': clean_pm
                })

        # Step 0B: Concurrent Multi-Engine Search for remaining title records
        if records_for_search:
            status_text.markdown(f"**Phase 0 (DOI Discovery Engine):** Concurrently querying Crossref, OpenAlex, PubMed, and Semantic Scholar for **{len(records_for_search):,} records**...")
            
            def _on_search_progress(comp, tot, disc):
                render_doi_tracker_line(
                    discovered_p0=t0_discovered + disc, 
                    current_phase=f"Phase 0 Search: {comp}/{tot} records checked (+{t0_discovered + disc} discovered)"
                )
                status_text.markdown(
                    f"**Phase 0 (DOI Discovery Engine):** Checked **{comp:,}/{tot:,} records** | "
                    f"Discovered **{disc:,} new DOIs** across Crossref, OpenAlex, PubMed & Semantic Scholar..."
                )

            discovered_dois = resolve_missing_dois_concurrent(
                records_for_search, 
                log_list=log_list, 
                max_workers=4,
                on_progress=_on_search_progress
            )
            for row_idx, res in discovered_dois.items():
                found_doi = res.get('doi')
                if found_doi:
                    df.at[row_idx, 'DOI'] = found_doi
                    dois_to_fetch.append(found_doi)
                    if res.get('meta'):
                        prefetched_meta[found_doi] = res['meta']
                    t0_discovered += 1
                    eng_name = res.get('engine', 'Multi-Engine')
                    doi_by_engine[eng_name] += 1

        render_doi_tracker_line(discovered_p0=t0_discovered, current_phase="Phase 0 Complete")
        if t0_discovered > 0:
            st.toast(f"🎯 Discovered {t0_discovered} missing DOIs!", icon="🔍")
            if log_list is not None:
                log_list.append(
                    f"[Phase 0 Summary] Successfully discovered {t0_discovered}/{len(missing_doi_tasks)} missing DOIs "
                    f"({(t0_discovered/len(missing_doi_tasks)*100 if missing_doi_tasks else 0):.1f}% success). "
                    f"Breakdown by Engine: {dict(doi_by_engine)}"
                )
                log_list.append(
                    f"[DOI Tracking] Total DOIs identified up to now: {initial_doi_count + t0_discovered:,} / {total_records:,} records "
                    f"({((initial_doi_count + t0_discovered)/total_records*100):.1f}% coverage) (+{t0_discovered:,} newly discovered)."
                )

    # Deduplicate clean DOIs
    dois_to_fetch = list(dict.fromkeys([
        str(d).replace("https://doi.org/", "").replace("doi:", "").lower().strip()
        for d in dois_to_fetch if d and str(d).strip()
    ]))
    t1_queried = len(dois_to_fetch)

    # TIER 1: OpenAlex Batch API (The bulk)
    status_text.markdown(f"**Tier 1:** Querying OpenAlex Batch API for **{t1_queried:,} DOIs** (including {t0_discovered} newly discovered) in batches of 50...")
    oa_batch_results = fetch_openalex_batch(dois_to_fetch, log_list=log_list)
    status_text.markdown(f"**Tier 1 Complete:** Fetched metadata for **{len(oa_batch_results):,} / {t1_queried:,} DOIs**. Now processing fallbacks (Tiers 2-5)...")

    # Pre-fetch candidate PMIDs for Tier 3 in fast polite batches
    pmids_to_fetch = [
        _get_field(r, 'PMID') for _, r in tasks
        if _get_field(r, 'PMID') and (_get_field(r, 'Abstract') is None or _get_field(r, 'Concepts') is None or is_ultimate)
    ]
    pm_batch_results = fetch_pubmed_batch(pmids_to_fetch) if pmids_to_fetch else {}

    # Pre-fetch candidate PMIDs for OpenAlex lookup when DOI is missing (Identifier-first resolution)
    pmids_for_oa = [
        _get_field(r, 'PMID') for _, r in tasks
        if not _get_field(r, 'DOI') and _get_field(r, 'PMID')
    ]
    oa_pmid_batch_results = fetch_openalex_batch_by_pmids(pmids_for_oa, log_list=log_list) if pmids_for_oa else {}
    
    completed = 0
    records_audit_trail = []
    for idx, _task_row in tasks:
        # Use latest record state from df (contains Phase 0 discovered DOI)
        row = df.loc[idx]
        doi = _get_field(row, 'DOI')
        title = _get_field(row, 'Title')
        pmid = _get_field(row, 'PMID')
        p_str = str(pmid).strip() if pmid else ""
        clean_pm = "" if p_str.upper().startswith('PMC') else re.sub(r'\D', '', p_str.rstrip('.0'))
        has_doi = doi is not None and str(doi).strip() != ''
        clean_doi = str(doi).replace("https://doi.org/", "").lower().strip() if has_doi else ""
        
        all_updates = {}
        missed = []
        
        rec_audit = {
            'row': idx,
            'source_file': str(_get_field(row, 'Source File') or 'Unknown File'),
            'title': str(title) if title else 'Untitled Record',
            'doi': clean_doi if clean_doi else None,
            'doi_url': f"https://doi.org/{clean_doi}" if clean_doi else None,
            'pmid': clean_pm if clean_pm else None,
            'pubmed_url': f"https://pubmed.ncbi.nlm.nih.gov/{clean_pm}/" if clean_pm else None,
            'openalex_id': None,
            'openalex_url': None,
            'openalex_api': None,
            'crossref_id': clean_doi if (has_doi or clean_doi) else None,
            'crossref_api': f"https://api.crossref.org/works/{clean_doi}" if (has_doi or clean_doi) else None,
            'semanticscholar_id': None,
            'tier_actions': [],
            'field_values_assigned': {},
            'cr_dates_info': None,
            'failed_columns': []
        }
        
        needs_update = lambda f: f in fields_to_enrich and (_get_field(row, f) is None or is_ultimate) and f not in all_updates
        
        # Tier 1 Apply (by DOI)
        oa_data = oa_batch_results.get(clean_doi)
        if not oa_data and clean_doi in prefetched_meta:
            pref = prefetched_meta[clean_doi]
            if isinstance(pref, dict) and ('authorships' in pref or 'abstract_inverted_index' in pref):
                oa_data = pref

        if oa_data:
            up_t1 = {}
            apply_openalex_data(oa_data, row, fields_to_enrich, up_t1, missed, is_ultimate=is_ultimate)
            if up_t1.get('enriched'):
                t1_resolved += 1
                fields_p = []
                for k, v in up_t1.items():
                    if k != 'enriched':
                        t1_fields_cnt[k] += 1
                        all_updates[k] = v
                        fields_p.append(k)
                        rec_audit['field_values_assigned'][k] = (v, "Tier 1 OpenAlex")
                
                oa_id_val = up_t1.get('OpenAlex ID') or oa_data.get('id')
                if oa_id_val:
                    clean_oa = str(oa_id_val).replace("https://openalex.org/", "").replace("works/", "").strip()
                    rec_audit['openalex_id'] = clean_oa
                    rec_audit['openalex_url'] = f"https://openalex.org/works/{clean_oa}"
                    rec_audit['openalex_api'] = f"https://api.openalex.org/works/{clean_oa}"

                oa_disp = rec_audit['openalex_id'] or 'Found'
                oa_url_disp = rec_audit['openalex_url'] or ''
                tier1_msg = f"Tier 1 (OpenAlex): Matched Work {oa_disp} (Web Link: {oa_url_disp}). Populated {len(fields_p)} field(s): {', '.join(fields_p)}"
                rec_audit['tier_actions'].append(tier1_msg)
                if fields_p and log_list is not None:
                    log_list.append(f"[Tier 1 OpenAlex] Row {idx} ({clean_doi}): Work {oa_disp} ({oa_url_disp}) → Populated {len(fields_p)} field(s) ({', '.join(fields_p)})")

        # Tier 1.5: If record has NO DOI, but HAS a valid PMID: query OpenAlex by PMID directly!
        if not has_doi and clean_pm:
            oa_pm_data = oa_pmid_batch_results.get(clean_pm)
            if oa_pm_data:
                up_pm = {}
                apply_openalex_data(oa_pm_data, row, fields_to_enrich, up_pm, missed, is_ultimate=is_ultimate)
                if up_pm.get('enriched'):
                    t1_resolved += 1
                    fields_p = []
                    for k, v in up_pm.items():
                        if k != 'enriched':
                            t1_fields_cnt[k] += 1
                            all_updates[k] = v
                            fields_p.append(k)
                            rec_audit['field_values_assigned'][k] = (v, "Tier 1.5 OpenAlex PMID")
                    if 'DOI' in up_pm:
                        clean_doi = str(up_pm['DOI']).replace("https://doi.org/", "").lower().strip()
                        has_doi = True
                        t15_dois_discovered += 1
                        doi_by_engine['Tier 1.5 PMID'] += 1
                        rec_audit['doi'] = clean_doi
                        rec_audit['doi_url'] = f"https://doi.org/{clean_doi}"
                        rec_audit['crossref_id'] = clean_doi
                        rec_audit['crossref_api'] = f"https://api.crossref.org/works/{clean_doi}"
                    
                    oa_id_val = up_pm.get('OpenAlex ID') or oa_pm_data.get('id')
                    if oa_id_val:
                        clean_oa = str(oa_id_val).replace("https://openalex.org/", "").replace("works/", "").strip()
                        rec_audit['openalex_id'] = clean_oa
                        rec_audit['openalex_url'] = f"https://openalex.org/works/{clean_oa}"
                        rec_audit['openalex_api'] = f"https://api.openalex.org/works/{clean_oa}"
                    
                    oa_disp = rec_audit['openalex_id'] or 'Found'
                    oa_url_disp = rec_audit['openalex_url'] or ''
                    tier15_msg = f"Tier 1.5 (OpenAlex via PMID {clean_pm}): Matched Work {oa_disp} ({oa_url_disp}). Populated {len(fields_p)} field(s): {', '.join(fields_p)}"
                    rec_audit['tier_actions'].append(tier15_msg)
                    if fields_p and log_list is not None:
                        log_list.append(f"[Tier 1.5 PMID Match] Row {idx} (PMID {clean_pm}): Work {oa_disp} ({oa_url_disp}) → Populated {len(fields_p)} field(s) ({', '.join(fields_p)})")
            
        # Tier 2: Crossref (if unresolved DOI, missing OpenAlex data, or any missing metadata field)
        needs_cr = (
            not oa_data 
            or needs_update('Publisher') 
            or needs_update('Publication Year') 
            or needs_update('Journal') 
            or needs_update('Abstract') 
            or needs_update('Author')
            or needs_update('Document Type')
            or needs_update('Language')
            or needs_update('Funding')
            or needs_update('Open Access')
            or needs_update('Article References')
            or needs_update('Times Cited')
            or needs_update('Affiliations')
            or needs_update('Country')
            or needs_update('Keywords')
        )
        if has_doi and needs_cr:
            t2_passed += 1
            cr_data = None
            if clean_doi in prefetched_meta:
                pref = prefetched_meta[clean_doi]
                if isinstance(pref, dict) and ('author' in pref or 'container-title' in pref):
                    cr_data = pref
            if not cr_data:
                cr_data = fetch_crossref_by_doi(doi or clean_doi, log_list=log_list)
            if cr_data:
                up_t2 = {}
                cr_log_ctx = {}
                apply_crossref_data(cr_data, row, fields_to_enrich, up_t2, missed, existing_updates=all_updates, log_context=cr_log_ctx)
                
                cr_dates_found = cr_log_ctx.get('crossref_dates', {})
                cr_dates_str = ", ".join(f"{k}={v}" for k, v in cr_dates_found.items()) if cr_dates_found else "None"
                cr_reason = cr_log_ctx.get('crossref_year_reason') or "Standard date extraction"
                rec_audit['cr_dates_info'] = f"Dates found: [{cr_dates_str}]. Date Resolution: {cr_reason}"
                
                if up_t2:
                    t2_resolved += 1
                    for k, v in up_t2.items():
                        t2_fields_cnt[k] += 1
                        all_updates[k] = v
                        rec_audit['field_values_assigned'][k] = (v, "Tier 2 Crossref")
                        
                tier2_msg = (
                    f"Tier 2 (Crossref): API endpoint https://api.crossref.org/works/{clean_doi} "
                    f"| Dates: [{cr_dates_str}] | Date Resolution: {cr_reason} "
                    f"| Populated {len(up_t2)} field(s): {', '.join(up_t2.keys()) if up_t2 else 'None (preserved earlier tier values)'}"
                )
                rec_audit['tier_actions'].append(tier2_msg)
                if log_list is not None:
                    log_list.append(
                        f"[Tier 2 Crossref] Row {idx} ({clean_doi}): API https://api.crossref.org/works/{clean_doi} "
                        f"| Dates: [{cr_dates_str}] → {len(up_t2)} field(s) populated ({', '.join(up_t2.keys()) if up_t2 else 'preserved earlier values'})"
                    )
                
        # Tier 3: PubMed (Only if PMID exists)
        if clean_pm:
            if needs_update('Abstract') or needs_update('Concepts'):
                t3_passed += 1
                pm_data = pm_batch_results.get(clean_pm) or fetch_pubmed_by_pmid(clean_pm)
                if pm_data:
                    up_t3 = {}
                    apply_pubmed_data(pm_data, row, fields_to_enrich, up_t3, missed, existing_updates=all_updates)
                    if up_t3:
                        t3_resolved += 1
                        for k, v in up_t3.items():
                            t3_fields_cnt[k] += 1
                            all_updates[k] = v
                            rec_audit['field_values_assigned'][k] = (v, "Tier 3 PubMed")
                    tier3_msg = (
                        f"Tier 3 (PubMed): PMID {clean_pm} (https://pubmed.ncbi.nlm.nih.gov/{clean_pm}/) "
                        f"| Populated {len(up_t3)} field(s): {', '.join(up_t3.keys()) if up_t3 else 'None'}"
                    )
                    rec_audit['tier_actions'].append(tier3_msg)
                    if log_list is not None and up_t3:
                        log_list.append(f"[Tier 3 PubMed] Row {idx} (PMID {clean_pm}): Populated {len(up_t3)} field(s) ({', '.join(up_t3.keys())})")
                    
        # Tier 4: Semantic Scholar (if still missing Abstract OR if author still has initials)
        curr_auth = all_updates.get('Author') or _get_field(row, 'Author')
        needs_author_aer = bool(curr_auth and pd.notna(curr_auth) and author_has_initials(str(curr_auth)))
        if has_doi and (needs_update('Abstract') or needs_author_aer):
            t4_passed += 1
            ss_data = fetch_semanticscholar_by_doi(doi or clean_doi, log_list=log_list)
            if ss_data:
                up_t4 = {}
                apply_semanticscholar_data(ss_data, row, fields_to_enrich, up_t4, missed, existing_updates=all_updates)
                if up_t4:
                    t4_resolved += 1
                    for k, v in up_t4.items():
                        t4_fields_cnt[k] += 1
                        all_updates[k] = v
                        rec_audit['field_values_assigned'][k] = (v, "Tier 4 Semantic Scholar")
                ss_id = ss_data.get('paperId') or ''
                ss_url = f"https://www.semanticscholar.org/paper/{ss_id}" if ss_id else "N/A"
                rec_audit['semanticscholar_id'] = ss_id
                tier4_msg = (
                    f"Tier 4 (Semantic Scholar): Paper ID {ss_id} ({ss_url}) "
                    f"| Populated {len(up_t4)} field(s): {', '.join(up_t4.keys()) if up_t4 else 'None'}"
                )
                rec_audit['tier_actions'].append(tier4_msg)
                if log_list is not None and up_t4:
                    log_list.append(f"[Tier 4 Semantic Scholar] Row {idx} ({clean_doi}): Populated {len(up_t4)} field(s) ({', '.join(up_t4.keys())})")
                
        # Tier 5: Residual Title Fallback (ONLY if STILL no DOI AND no OpenAlex PMID match found)
        has_matched_pmid = bool(clean_pm and clean_pm in oa_pmid_batch_results)
        if not has_doi and not has_matched_pmid and title:
            t5_passed += 1
            author_val = _get_field(row, 'Author')
            year_val = _get_field(row, 'Publication Year')
            oa_title_data = fetch_openalex_data_by_title(title, author=author_val, year=year_val)
            if oa_title_data:
                up_t5 = {}
                apply_openalex_data(oa_title_data, row, fields_to_enrich, up_t5, missed, is_ultimate=is_ultimate)
                if up_t5.get('enriched'):
                    t5_resolved += 1
                    fields_p = []
                    for k, v in up_t5.items():
                        if k != 'enriched':
                            t5_fields_cnt[k] += 1
                            all_updates[k] = v
                            fields_p.append(k)
                            rec_audit['field_values_assigned'][k] = (v, "Tier 5 OpenAlex Title Search")
                    if 'DOI' in up_t5:
                        clean_doi = str(up_t5['DOI']).replace("https://doi.org/", "").lower().strip()
                        t15_dois_discovered += 1
                        doi_by_engine['Tier 5 Title'] += 1
                        rec_audit['doi'] = clean_doi
                        rec_audit['doi_url'] = f"https://doi.org/{clean_doi}"
                        rec_audit['crossref_id'] = clean_doi
                        rec_audit['crossref_api'] = f"https://api.crossref.org/works/{clean_doi}"
                    
                    oa_id_val = up_t5.get('OpenAlex ID') or oa_title_data.get('id')
                    if oa_id_val:
                        clean_oa = str(oa_id_val).replace("https://openalex.org/", "").replace("works/", "").strip()
                        rec_audit['openalex_id'] = clean_oa
                        rec_audit['openalex_url'] = f"https://openalex.org/works/{clean_oa}"
                        rec_audit['openalex_api'] = f"https://api.openalex.org/works/{clean_oa}"
                    
                    oa_disp = rec_audit['openalex_id'] or 'Found'
                    oa_url_disp = rec_audit['openalex_url'] or ''
                    tier5_msg = f"Tier 5 (OpenAlex Title Search): Matched Work {oa_disp} ({oa_url_disp}). Populated {len(fields_p)} field(s): {', '.join(fields_p)}"
                    rec_audit['tier_actions'].append(tier5_msg)
                    if fields_p and log_list is not None:
                        log_list.append(f"[Tier 5 Title Match] Row {idx}: Work {oa_disp} ({oa_url_disp}) → Populated {len(fields_p)} field(s) ({', '.join(fields_p)}) for Title '{str(title)[:55]}'")
                
        # Apply all updates to dataframe
        if all_updates:
            for col, val in all_updates.items():
                if col != 'enriched':
                    if col not in df.columns:
                        df[col] = pd.Series(pd.NA, index=df.index, dtype=object)
                    elif df[col].dtype != 'object' and not isinstance(val, (int, float, np.number)):
                        df[col] = df[col].astype(object)
                    df.at[idx, col] = val
                    
        # Column-level failure audit for this record
        still_missing = []
        for f in fields_to_enrich:
            val_check = _get_field(df.loc[idx], f)
            if val_check is None:
                still_missing.append(f)
                
        rec_audit['failed_columns'] = still_missing
        records_audit_trail.append(rec_audit)

        if still_missing:
            failed_records_audit.append({
                "row": idx,
                "title": str(title)[:55] if title else 'Untitled Record',
                "doi": str(doi) if doi else 'No DOI',
                "source_file": str(_get_field(row, 'Source File') or 'Unknown File'),
                "enriched_count": len([k for k in all_updates if k != 'enriched']),
                "failed_columns": still_missing
            })

        completed += 1
        pct = completed / tasks_count
        progress_bar.progress(pct)
        
        if completed % 5 == 0 or completed == tasks_count:
            current_dois_now = initial_doi_count + t0_discovered + t15_dois_discovered
            render_doi_tracker_line(
                discovered_p0=t0_discovered, 
                discovered_fallback=t15_dois_discovered, 
                current_phase=f"Enrichment Loop: {completed:,}/{tasks_count:,} records ({pct:.0%})"
            )
            status_text.markdown(
                f"**Progress: {completed:,}/{tasks_count:,} ({pct:.0%})** | "
                f"**DOIs Found Up to Now: {current_dois_now:,}** | "
                f"T1 (OA Batch): **{t1_resolved:,}** | "
                f"T2 (Crossref): **{t2_resolved:,}/{t2_passed:,}** | "
                f"T3 (PubMed): **{t3_resolved:,}/{t3_passed:,}** | "
                f"T4 (Semantic): **{t4_resolved:,}/{t4_passed:,}** | "
                f"T5 (Title): **{t5_resolved:,}/{t5_passed:,}**"
            )

    # Post-enrichment Heuristic: Deduce Affiliations from Address if missing
    aff_deduced_count = 0
    if 'Affiliations' in df.columns and 'Address' in df.columns:
        if df['Affiliations'].dtype != 'object':
            df['Affiliations'] = df['Affiliations'].astype(object)
        aff_m = df['Affiliations'].isna() | (df['Affiliations'].astype(str).str.strip() == '')
        addr_v = df['Address'].notna() & (df['Address'].astype(str).str.strip() != '')
        mask_aff = aff_m & addr_v
        aff_deduced_count = int(mask_aff.sum())
        if mask_aff.any():
            df.loc[mask_aff, 'Affiliations'] = df.loc[mask_aff, 'Address']
            if log_list is not None:
                log_list.append(f"[Heuristic] Deduced Affiliations from Address for {aff_deduced_count:,} records.")

    # Post-enrichment Heuristic: Deduce Country strictly from author Address / Affiliations (excluding conference Location)
    cnt_deduced_count = 0
    if 'Country' in df.columns:
        if df['Country'].dtype != 'object':
            df['Country'] = df['Country'].astype(object)
        from core.ingestion import extract_country_from_text
        cnt_missing = df['Country'].isna() | (df['Country'].astype(str).str.strip() == '')
        for idx in df[cnt_missing].index:
            for col_c in ['Address', 'Affiliations']:
                if col_c in df.columns and pd.notna(df.at[idx, col_c]):
                    deduced_c = extract_country_from_text(str(df.at[idx, col_c]))
                    if deduced_c:
                        df.at[idx, 'Country'] = deduced_c
                        cnt_deduced_count += 1
                        break
        if cnt_deduced_count > 0 and log_list is not None:
            log_list.append(f"[Heuristic] Deduced Country from Author Affiliations/Address for {cnt_deduced_count:,} records.")

    # Post-enrichment Heuristic: Deduce Language if still missing
    lang_deduced_count = 0
    if 'Language' in df.columns:
        if df['Language'].dtype != 'object':
            df['Language'] = df['Language'].astype(object)
        lang_missing = df['Language'].isna() | (df['Language'].astype(str).str.strip() == '')
        for idx in df[lang_missing].index:
            cnt_val = str(df.at[idx, 'Country']) if 'Country' in df.columns and pd.notna(df.at[idx, 'Country']) else ""
            if any(k in cnt_val.lower() for k in ['brazil', 'brasil', 'portugal']):
                df.at[idx, 'Language'] = 'PT'
                lang_deduced_count += 1
            elif any(k in cnt_val.lower() for k in ['united states', 'united kingdom', 'australia', 'canada']):
                df.at[idx, 'Language'] = 'EN'
                lang_deduced_count += 1
        if lang_deduced_count > 0 and log_list is not None:
            log_list.append(f"[Heuristic] Deduced Language for {lang_deduced_count:,} records.")

    # Final normalization: Standardize Author names into Western format (First Name First) and strip academic degrees
    if 'Author' in df.columns:
        from features.gender import standardize_author_string
        def _std_author(val):
            if pd.notna(val) and str(val).strip() and str(val).strip().lower() not in ('nan', '<na>', 'none'):
                std = standardize_author_string(str(val))
                return std if std else val
            return val
        df['Author'] = df['Author'].apply(_std_author)
        if log_list is not None:
            log_list.append("[Normalization] Standardized author names into Western standard format (First Name First).")

    # Automatic Post-Enrichment Deduplication: Consolidate any records that now share identical DOIs or OpenAlex IDs
    from core.deduplication import deduplicate_dataset
    df, post_enrich_dups, new_dups = deduplicate_dataset(df, return_duplicates=True, phase_name="Post-Enrichment")
    if 'prisma_duplicates' not in st.session_state:
        st.session_state.prisma_duplicates = []
    st.session_state.prisma_duplicates.extend(new_dups)
    if post_enrich_dups > 0 and log_list is not None:
        log_list.append(f"[Deduplication] Consolidated {post_enrich_dups:,} duplicate records sharing newly enriched identifiers.")

    start_timestamp = datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
    end_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    duration = time.time() - start_time
    
    fully_enriched = tasks_count - len(failed_records_audit)
    partially_enriched = sum(1 for r in failed_records_audit if r.get("enriched_count", 0) > 0)
    failed_enriched = sum(1 for r in failed_records_audit if r.get("enriched_count", 0) == 0)
    
    total_successful_runs = fully_enriched + partially_enriched
    success_rate = (total_successful_runs / tasks_count * 100) if tasks_count > 0 else 0

    formatted_duration = format_duration(duration)

    final_dois_count = initial_doi_count + t0_discovered + t15_dois_discovered
    final_doi_pct = (final_dois_count / total_records * 100) if total_records > 0 else 0
    final_doi_summary_line = (
        f"🎯 DOIs Found Up to Now: {final_dois_count:,} / {total_records:,} records "
        f"({final_doi_pct:.1f}% coverage) — ({initial_doi_count:,} initial at ingestion + {t0_discovered + t15_dois_discovered:,} newly discovered)"
    )
    st.session_state.last_doi_summary_line = final_doi_summary_line
    render_doi_tracker_line(
        discovered_p0=t0_discovered, 
        discovered_fallback=t15_dois_discovered, 
        current_phase="Enrichment Complete"
    )

    post_dedup_msg = f" · Consolidated {post_enrich_dups} duplicate records." if post_enrich_dups > 0 else ""
    status_text.success(
        f"🎉 **Enrichment Pipeline Completed in {formatted_duration}!**\n\n"
        f"**{final_doi_summary_line}**\n\n"
        f"Enhanced metadata for **{total_successful_runs:,}/{tasks_count:,} records** ({success_rate:.1f}% hit rate).{post_dedup_msg}"
    )

    audit_lines = [
        "=======================================================================",
        "        5-TIER BIBLIOMETRIC DATA ENRICHMENT AUDIT & EXECUTION LOG",
        "=======================================================================",
        f"Execution Timestamp: {start_timestamp} → {end_timestamp} (Duration: {formatted_duration})",
        "",
        "=======================================================================",
        "             DOI IDENTIFICATION & DISCOVERY SUMMARY (UP TO NOW)",
        "=======================================================================",
        f"• Total Records in Memory Dataset: {total_records:,}",
        f"• DOIs Originally Present at Ingestion: {initial_doi_count:,} ({(initial_doi_count/total_records*100 if total_records else 0):.1f}%)",
        f"• Missing DOI Records Investigated: {len(missing_doi_tasks):,}",
        f"• DOIs Successfully Discovered in Phase 0: {t0_discovered:,} ({(t0_discovered/len(missing_doi_tasks)*100 if missing_doi_tasks else 0):.1f}%)",
        f"    - Discovered via Crossref Works Search: {doi_by_engine['Crossref']:,}",
        f"    - Discovered via OpenAlex BM25 Search: {doi_by_engine['OpenAlex']:,}",
        f"    - Discovered via PubMed eSearch/eFetch: {doi_by_engine['PubMed']:,}",
        f"    - Discovered via Semantic Scholar Match: {doi_by_engine['Semantic Scholar']:,}",
        f"    - Discovered via PubMed PMID Batch: {doi_by_engine['PMID Batch']:,}",
        f"• DOIs Discovered in Fallback Tiers (1.5 / 5): {t15_dois_discovered:,}",
        "-----------------------------------------------------------------------",
        f"• TOTAL DOIS FOUND UP TO NOW: {final_dois_count:,} / {total_records:,} records ({final_doi_pct:.1f}% coverage)",
        f"• Newly Discovered DOIs Added to Dataset: +{t0_discovered + t15_dois_discovered:,} records",
        f"• Residual Records Still Without DOI: {total_records - final_dois_count:,} records",
        "=======================================================================",
        "",
        "[OVERALL DATASET CONTEXT & METRICS]",
        f"• Total Records Evaluated for Enrichment: {tasks_count:,}",
        f"• Post-Enrichment Duplicates Consolidated: {post_enrich_dups:,}",
        f"• Fully Enriched Records (Found 100% of requested fields): {fully_enriched:,} ({(fully_enriched/tasks_count*100 if tasks_count else 0):.1f}%)",
        f"• Partially Enriched Records (Gained new data): {partially_enriched:,} ({(partially_enriched/tasks_count*100 if tasks_count else 0):.1f}%)",
        f"• Unresolved Records (Gained NO data): {failed_enriched:,} ({(failed_enriched/tasks_count*100 if tasks_count else 0):.1f}%)",
        "",
        f"Target Fields Requested ({len(fields_to_enrich)} fields): {fields_to_enrich}",
        "",
        "--------------------------------------------------------------------------------",
        "1. MEMORY CLUSTER & FILE PROVENANCE CONTEXT",
        "--------------------------------------------------------------------------------",
        f"• Total Records in Memory Dataset: {total_records:,}",
        f"• Total Records Evaluated for Enrichment: {tasks_count:,}",
    ]
    
    if file_manifest:
        audit_lines.append(f"• Cluster Source Files Breakdown ({len(file_manifest)} files):")
        for fname, rcount in file_manifest.items():
            audit_lines.append(f"    - {fname}: {rcount} records")
    else:
        audit_lines.append("• Cluster Source Files: Single/Unspecified file source")
        
    audit_lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "2. TIER-BY-TIER METRICS & FIELD-LEVEL LINE POPULATION BREAKDOWN",
        "--------------------------------------------------------------------------------",
        f"• PHASE 0: Multi-Engine DOI Discovery (Crossref, OpenAlex, PubMed, Semantic Scholar)",
        f"    - Missing DOI Records Evaluated: {len(missing_doi_tasks):,}",
        f"    - DOIs Discovered: {t0_discovered:,}",
        f"    - Hit Rate: {(t0_discovered/len(missing_doi_tasks)*100 if missing_doi_tasks else 0):.1f}%",
        f"    - Engine Breakdown: {dict(doi_by_engine) if doi_by_engine else 'None'}",
        "",
        f"• TIER 1: OpenAlex Batch API (Bulk DOI Filtering)",
        f"    - DOIs Queried: {t1_queried:,}",
        f"    - Records Resolved: {t1_resolved:,} ({((t1_resolved/t1_queried*100) if t1_queried else 0):.1f}%)",
        f"    - Total Field Values Populated: {sum(t1_fields_cnt.values()):,} lines",
        f"    - Field Breakdown: {dict(t1_fields_cnt) if t1_fields_cnt else 'None'}",
        "",
        f"• TIER 2: Crossref REST API (DOI Metadata Fallback)",
        f"    - Records Passed: {t2_passed:,}",
        f"    - Records Resolved: {t2_resolved:,}",
        f"    - Total Field Values Populated: {sum(t2_fields_cnt.values()):,} lines",
        f"    - Field Breakdown: {dict(t2_fields_cnt) if t2_fields_cnt else 'None'}",
        "",
        f"• TIER 3: PubMed eUtils API (Biomedical MeSH/Abstract Fallback)",
        f"    - Records Passed: {t3_passed:,} (with valid PMID)",
        f"    - Records Resolved: {t3_resolved:,}",
        f"    - Total Field Values Populated: {sum(t3_fields_cnt.values()):,} lines",
        f"    - Field Breakdown: {dict(t3_fields_cnt) if t3_fields_cnt else 'None'}",
        "",
        f"• TIER 4: Semantic Scholar API (Abstract & AI TLDR Fallback)",
        f"    - Records Passed: {t4_passed:,}",
        f"    - Records Resolved: {t4_resolved:,}",
        f"    - Total Field Values Populated: {sum(t4_fields_cnt.values()):,} lines",
        f"    - Field Breakdown: {dict(t4_fields_cnt) if t4_fields_cnt else 'None'}",
        "",
        f"• TIER 5: OpenAlex Fuzzy Title Search (Residual Non-DOI Local Papers)",
        f"    - Records Passed: {t5_passed:,} (searched by Title)",
        f"    - Records Resolved: {t5_resolved:,}",
        f"    - Total Field Values Populated: {sum(t5_fields_cnt.values()):,} lines",
        f"    - Field Breakdown: {dict(t5_fields_cnt) if t5_fields_cnt else 'None'}",
        "",
        "--------------------------------------------------------------------------------",
        "3. POST-ENRICHMENT HEURISTIC DEDUCTIONS & STANDARDIZATION",
        "--------------------------------------------------------------------------------",
        f"• Affiliations Deduced from Address: {aff_deduced_count:,} records",
        f"• Country Deduced from Affiliations/Address: {cnt_deduced_count:,} records",
        f"• Language Deduced from Country: {lang_deduced_count:,} records",
        f"• Author Western Name Normalization: Completed",
        f"• Post-Enrichment Duplicates Consolidated: {post_enrich_dups:,} records",
        "",
        "--------------------------------------------------------------------------------",
        "4. UNRESOLVED RECORDS & SPECIFIC MISSING COLUMNS AUDIT",
        "--------------------------------------------------------------------------------",
        f"Total Records with Remaining Missing Fields: {len(failed_records_audit):,} / {tasks_count:,}",
        ""
    ])
    
    if failed_records_audit:
        for rec in failed_records_audit:
            audit_lines.append(
                f"• [Row {rec['row']}] Source: {rec['source_file']}\n"
                f"  Title: '{rec['title']}' | DOI: '{rec['doi']}'\n"
                f"  Status: Enriched {rec['enriched_count']} field(s) during run.\n"
                f"  ❌ FAILED / STILL MISSING COLUMNS ({len(rec['failed_columns'])}): {rec['failed_columns']}\n"
            )
    else:
        audit_lines.append("🎉 100% SUCCESS: All evaluated records were fully populated with zero missing target fields!")

    if records_audit_trail:
        audit_lines.extend([
            "",
            "--------------------------------------------------------------------------------",
            "5. DETAILED RECORD-BY-RECORD IDENTIFIER TRACE & PROVENANCE AUDIT",
            "--------------------------------------------------------------------------------",
            "This section documents the exact API identifiers, URLs, date resolutions, and",
            "engine source decisions for all evaluated records.",
            "• TIP: OpenAlex Work IDs ('W...') can be verified in a browser by visiting their direct link",
            "  (https://openalex.org/works/<ID>). Searching raw 'W...' in openalex.org searches title text.",
            "• TIP: Crossref records are indexed by DOI at https://api.crossref.org/works/<DOI>.",
            ""
        ])
        for ra in records_audit_trail:
            t_title = str(ra.get('title', 'Untitled'))
            if len(t_title) > 80:
                t_title = t_title[:77] + "..."
            audit_lines.append(f"• [Row {ra['row']}] \"{t_title}\"")
            audit_lines.append(f"  Source File: {ra['source_file']}")
            
            # Identifiers
            id_lines = []
            if ra.get('doi'):
                id_lines.append(f"DOI: {ra['doi']} (Resolver: https://doi.org/{ra['doi']})")
            if ra.get('openalex_id'):
                id_lines.append(f"OpenAlex Work ID: {ra['openalex_id']}")
                id_lines.append(f"  - Direct Web URL: https://openalex.org/works/{ra['openalex_id']}")
                id_lines.append(f"  - Direct API URL: https://api.openalex.org/works/{ra['openalex_id']}")
            if ra.get('crossref_id'):
                id_lines.append(f"Crossref Work ID: {ra['crossref_id']}")
                id_lines.append(f"  - Direct Crossref API: https://api.crossref.org/works/{ra['crossref_id']}")
                if ra.get('cr_dates_info'):
                    id_lines.append(f"  - Crossref Dates: {ra['cr_dates_info']}")
            if ra.get('pmid'):
                id_lines.append(f"PubMed PMID: {ra['pmid']} (https://pubmed.ncbi.nlm.nih.gov/{ra['pmid']}/)")
            if ra.get('semanticscholar_id'):
                id_lines.append(f"Semantic Scholar ID: {ra['semanticscholar_id']} (https://www.semanticscholar.org/paper/{ra['semanticscholar_id']})")
                
            if id_lines:
                audit_lines.append("  Identifiers & Direct Verification Links:")
                for id_l in id_lines:
                    audit_lines.append(f"    * {id_l}")
                    
            # Tier actions
            if ra.get('tier_actions'):
                audit_lines.append("  Tier Execution Trace:")
                for act in ra['tier_actions']:
                    audit_lines.append(f"    * {act}")
                    
            # Enriched values summary
            if ra.get('field_values_assigned'):
                audit_lines.append("  Enriched Fields Populated in this Run:")
                for f_name, (f_val, f_src) in ra['field_values_assigned'].items():
                    v_str = str(f_val)
                    if len(v_str) > 70:
                        v_str = v_str[:67] + "..."
                    audit_lines.append(f"    * {f_name} = '{v_str}' (via {f_src})")
                    
            if ra.get('failed_columns'):
                audit_lines.append(f"  Remaining Missing Target Columns ({len(ra['failed_columns'])}): {ra['failed_columns']}")
            else:
                audit_lines.append("  Status: 100% Complete (zero missing target fields)")
                
            audit_lines.append("")
        
    audit_lines.extend([
        "=" * 80,
        f"FINAL SUMMARY: {total_successful_runs}/{tasks_count} records received enhancement data. Audit saved to disk.",
        f"TOTAL DOIS IDENTIFIED: {final_dois_count:,} / {total_records:,} ({final_doi_pct:.1f}% coverage).",
        "=" * 80
    ])

    report_text = "\n".join(audit_lines)

    from utils.project_manager import save_project_file, get_timestamp_str, get_project_dir
    log_filename_base = f"enrichment_{get_timestamp_str()}.log"
    log_filename = save_project_file("logs", log_filename_base, report_text)
            
    # Push rich metrics into Streamlit System Logs & trigger immediate confirmation toast
    if log_list is not None:
        log_list.append(report_text)
    st.session_state.last_enrichment_report = report_text
    st.session_state.last_enrichment_logfile = log_filename
    st.toast(f"💾 Audit log automatically saved to `{log_filename}`!", icon="📄")
    
    return df
