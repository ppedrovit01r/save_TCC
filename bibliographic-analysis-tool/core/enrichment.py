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
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from core.ingestion import deduplicate_and_merge_columns
from utils.formatters import format_duration
from features.gender import author_has_initials, split_authors_string, disambiguate_paper_authors, clean_author_text

CACHE_DIR = "/tmp" if os.name == 'posix' else tempfile.gettempdir()
requests_cache.install_cache(os.path.join(CACHE_DIR, 'openalex_cache'), expire_after=604800)
SS_CACHE_FILE = os.path.join(CACHE_DIR, 'semanticscholar_cache.json')

# Polite Pool Header (Replace with your actual email in production)
HEADERS = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}

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
def fetch_openalex_batch(dois: list) -> dict:
    if not dois: return {}
    clean_dois = [str(doi).strip().replace("https://doi.org/", "").replace("doi:", "").lower() for doi in dois if pd.notna(doi) and str(doi).strip()]
    if not clean_dois: return {}
    
    results = {}
    batch_size = 50
    for i in range(0, len(clean_dois), batch_size):
        batch = clean_dois[i:i+batch_size]
        filter_str = "doi:" + "|".join(batch)
        url = f"https://api.openalex.org/works?filter={filter_str}&per-page={batch_size}"
        try:
            time.sleep(0.15)  # Respect OpenAlex polite pool (~6.6 req/sec <= 10 req/sec limit)
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for work in data.get('results', []):
                    work_doi = work.get('doi')
                    if work_doi:
                        work_doi_clean = str(work_doi).replace("https://doi.org/", "").lower()
                        results[work_doi_clean] = work
        except Exception:
            pass
    return results

def fetch_openalex_batch_by_pmids(pmids: list) -> dict:
    if not pmids:
        return {}
    clean_pmids = []
    for p in pmids:
        if pd.notna(p):
            digits = re.sub(r'\D', '', str(p).rstrip('.0'))
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
        try:
            time.sleep(0.15)
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for work in data.get('results', []):
                    pmid_url = work.get('ids', {}).get('pmid', '')
                    if pmid_url:
                        pmid_val = str(pmid_url).rstrip('/').split('/')[-1]
                        results[pmid_val] = work
        except Exception:
            pass
    return results

# Tier 2: Crossref
def fetch_crossref_by_doi(doi: str) -> dict:
    if pd.isna(doi) or not str(doi).strip(): return None
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "")
    url = f"https://api.crossref.org/works/{clean_doi}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        time.sleep(0.5)
        if response.status_code == 200:
            return response.json().get('message')
    except Exception:
        pass
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

def fetch_semanticscholar_batch(dois: list) -> dict:
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
        try:
            time.sleep(1.0)  # Strictly <= 1 req/sec Semantic Scholar rate limit
            resp = requests.post(url, json={"ids": ids_payload}, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for doi_key, paper in zip(chunk, data):
                        if paper and isinstance(paper, dict) and not paper.get('error'):
                            results[doi_key] = paper
                            cache[doi_key] = paper
                            cache_dirty = True
        except Exception:
            pass

    if cache_dirty:
        _save_ss_cache(cache)

    return results

def fetch_semanticscholar_by_doi(doi: str) -> dict:
    if pd.isna(doi) or not str(doi).strip(): return None
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "").lower()
    batch_res = fetch_semanticscholar_batch([clean_doi])
    return batch_res.get(clean_doi)

# Tier 5: OpenAlex Fuzzy Title Search
def fetch_openalex_data_by_title(title: str) -> dict:
    if pd.isna(title) or not str(title).strip(): return None
    clean_title = str(title).strip()
    clean_query = re.sub(r'^[\[\(]\s*|\s*[\]\)]$', '', clean_title).strip()
    encoded_title = urllib.parse.quote(clean_query)
    url = f"https://api.openalex.org/works?filter=title.search:{encoded_title}&per-page=3"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        time.sleep(1.1)
        if response.status_code == 200:
            data = response.json()
            for cand in data.get('results', []):
                cand_title = cand.get('title', '')
                if not cand_title:
                    continue
                q_norm = re.sub(r'[^\w\s]', '', clean_query).lower().strip()
                c_norm = re.sub(r'[^\w\s]', '', cand_title).lower().strip()
                if not q_norm or not c_norm:
                    continue
                if q_norm == c_norm:
                    return cand
                ratio = difflib.SequenceMatcher(None, q_norm, c_norm).ratio()
                # Strict threshold: require at least 82% similarity to prevent generic phrases from hijacking unrelated works
                if ratio >= 0.82:
                    return cand
    except Exception:
        pass
    return None

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

def apply_crossref_data(cr_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list):
    needs_update = lambda f: f in fields_to_enrich and _get_field(row, f) is None and f not in updates
    
    if ('Title' in fields_to_enrich or needs_update('Title')) and 'Title' not in updates:
        cr_title = cr_data.get('title')
        if cr_title and isinstance(cr_title, list) and len(cr_title) > 0 and str(cr_title[0]).strip():
            updates['Title'] = str(cr_title[0]).strip()

    if ('Abstract' in fields_to_enrich or needs_update('Abstract')) and 'Abstract' not in updates:
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
        if val: updates['Publisher'] = val
        
    if needs_update('Publication Year'):
        try:
            val = cr_data['published-print']['date-parts'][0][0]
            from utils.formatters import clean_year_value
            val_clean = clean_year_value(val)
            if val_clean:
                updates['Publication Year'] = val_clean
        except:
            pass
            
    author_curr = updates.get('Author') or _get_field(row, 'Author')
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
            elif 'Author' not in updates:
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

def apply_pubmed_data(pm_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list):
    needs_update = lambda f: f in fields_to_enrich and _get_field(row, f) is None and f not in updates
    if ('Abstract' in fields_to_enrich or needs_update('Abstract')) and pm_data.get('abstract'):
        updates['Abstract'] = pm_data['abstract']
    if ('Concepts' in fields_to_enrich or needs_update('Concepts')) and pm_data.get('mesh'):
        updates['Concepts'] = "; ".join(pm_data['mesh'])

def apply_semanticscholar_data(ss_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list):
    needs_update = lambda f: f in fields_to_enrich and _get_field(row, f) is None and f not in updates
    
    if ('Title' in fields_to_enrich or needs_update('Title')) and 'Title' not in updates:
        ss_title = ss_data.get('title')
        if ss_title and str(ss_title).strip():
            updates['Title'] = str(ss_title).strip()

    if ('Abstract' in fields_to_enrich or needs_update('Abstract')) and 'Abstract' not in updates:
        val = ss_data.get('abstract') or (ss_data.get('tldr') or {}).get('text')
        if val and str(val).strip():
            updates['Abstract'] = str(val).strip()

    # Author Disambiguation via Semantic Scholar AER
    author_curr = updates.get('Author') or _get_field(row, 'Author')
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
    df = deduplicate_and_merge_columns(df)
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
        log_list.append("Optimization: No API calls made. All selected fields are already populated in the dataset.")
        progress_bar.progress(1.0)
        return df

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
        m1.metric("Total Dataset Records", f"{len(df):,}")
        m2.metric("Records Evaluated", f"{tasks_count:,}")
        m3.metric("Valid DOIs (Tiers 1-4)", f"{t1_queried:,}")
        m4.metric("No DOIs (Tier 5 Title)", f"{tasks_count - t1_queried:,}")
        
        status_text = st.empty()
        progress_bar = st.progress(0)

    # TIER 1: OpenAlex Batch API (The bulk)
    status_text.markdown(f"**Tier 1:** Querying OpenAlex Batch API for **{t1_queried:,} DOIs** in batches of 50...")
    oa_batch_results = fetch_openalex_batch(dois_to_fetch)
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
    oa_pmid_batch_results = fetch_openalex_batch_by_pmids(pmids_for_oa) if pmids_for_oa else {}
    
    completed = 0
    for idx, row in tasks:
        doi = _get_field(row, 'DOI')
        title = _get_field(row, 'Title')
        pmid = _get_field(row, 'PMID')
        clean_pm = re.sub(r'\D', '', str(pmid).rstrip('.0')) if pmid else ""
        has_doi = doi is not None
        clean_doi = str(doi).replace("https://doi.org/", "").lower().strip() if has_doi else ""
        
        all_updates = {}
        missed = []
        
        needs_update = lambda f: f in fields_to_enrich and (_get_field(row, f) is None or is_ultimate) and f not in all_updates
        
        # Tier 1 Apply (by DOI)
        oa_data = oa_batch_results.get(clean_doi)
        if oa_data:
            up_t1 = {}
            apply_openalex_data(oa_data, row, fields_to_enrich, up_t1, missed, is_ultimate=is_ultimate)
            if up_t1.get('enriched'):
                t1_resolved += 1
                for k, v in up_t1.items():
                    if k != 'enriched':
                        t1_fields_cnt[k] += 1
                        all_updates[k] = v

        # Tier 1.5: If record has NO DOI, but HAS a valid PMID: query OpenAlex by PMID directly!
        if not has_doi and clean_pm:
            oa_pm_data = oa_pmid_batch_results.get(clean_pm)
            if oa_pm_data:
                up_pm = {}
                apply_openalex_data(oa_pm_data, row, fields_to_enrich, up_pm, missed, is_ultimate=is_ultimate)
                if up_pm.get('enriched'):
                    t1_resolved += 1
                    for k, v in up_pm.items():
                        if k != 'enriched':
                            t1_fields_cnt[k] += 1
                            all_updates[k] = v
                    if 'DOI' in up_pm:
                        clean_doi = str(up_pm['DOI']).replace("https://doi.org/", "").lower().strip()
                        has_doi = True
            
        # Tier 2: Crossref (if unresolved DOI or missing publisher / year / journal / abstract / author)
        if has_doi and (not oa_data or needs_update('Publisher') or needs_update('Publication Year') or needs_update('Journal') or needs_update('Abstract') or needs_update('Author')):
            t2_passed += 1
            cr_data = fetch_crossref_by_doi(doi or clean_doi)
            if cr_data:
                up_t2 = {}
                apply_crossref_data(cr_data, row, fields_to_enrich, up_t2, missed)
                if up_t2:
                    t2_resolved += 1
                    for k, v in up_t2.items():
                        t2_fields_cnt[k] += 1
                        all_updates[k] = v
                
        # Tier 3: PubMed (Only if PMID exists)
        if clean_pm:
            if needs_update('Abstract') or needs_update('Concepts'):
                t3_passed += 1
                pm_data = pm_batch_results.get(clean_pm) or fetch_pubmed_by_pmid(clean_pm)
                if pm_data:
                    up_t3 = {}
                    apply_pubmed_data(pm_data, row, fields_to_enrich, up_t3, missed)
                    if up_t3:
                        t3_resolved += 1
                        for k, v in up_t3.items():
                            t3_fields_cnt[k] += 1
                            all_updates[k] = v
                    
        # Tier 4: Semantic Scholar (if still missing Abstract OR if author still has initials)
        curr_auth = all_updates.get('Author') or _get_field(row, 'Author')
        needs_author_aer = bool(curr_auth and pd.notna(curr_auth) and author_has_initials(str(curr_auth)))
        if has_doi and (needs_update('Abstract') or needs_author_aer):
            t4_passed += 1
            ss_data = fetch_semanticscholar_by_doi(doi or clean_doi)
            if ss_data:
                up_t4 = {}
                apply_semanticscholar_data(ss_data, row, fields_to_enrich, up_t4, missed)
                if up_t4:
                    t4_resolved += 1
                    for k, v in up_t4.items():
                        t4_fields_cnt[k] += 1
                        all_updates[k] = v
                
        # Tier 5: OpenAlex Fuzzy Title (ONLY if no DOI AND no OpenAlex PMID match found)
        has_matched_pmid = bool(clean_pm and clean_pm in oa_pmid_batch_results)
        if not has_doi and not has_matched_pmid and title:
            t5_passed += 1
            oa_title_data = fetch_openalex_data_by_title(title)
            if oa_title_data:
                up_t5 = {}
                apply_openalex_data(oa_title_data, row, fields_to_enrich, up_t5, missed, is_ultimate=is_ultimate)
                if up_t5.get('enriched'):
                    t5_resolved += 1
                    for k, v in up_t5.items():
                        if k != 'enriched':
                            t5_fields_cnt[k] += 1
                            all_updates[k] = v
                
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
            status_text.markdown(
                f"**Progress: {completed:,}/{tasks_count:,} ({pct:.0%})** | "
                f"T1 (OpenAlex Batch): **{t1_resolved:,}** | "
                f"T2 (Crossref): **{t2_resolved:,}/{t2_passed:,}** | "
                f"T3 (PubMed): **{t3_resolved:,}/{t3_passed:,}** | "
                f"T4 (Semantic): **{t4_resolved:,}/{t4_passed:,}** | "
                f"T5 (Title Search): **{t5_resolved:,}/{t5_passed:,}**"
            )

    # Post-enrichment Heuristic: Deduce Affiliations from Address if missing
    if 'Affiliations' in df.columns and 'Address' in df.columns:
        if df['Affiliations'].dtype != 'object':
            df['Affiliations'] = df['Affiliations'].astype(object)
        aff_m = df['Affiliations'].isna() | (df['Affiliations'].astype(str).str.strip() == '')
        addr_v = df['Address'].notna() & (df['Address'].astype(str).str.strip() != '')
        mask_aff = aff_m & addr_v
        if mask_aff.any():
            df.loc[mask_aff, 'Affiliations'] = df.loc[mask_aff, 'Address']

    # Post-enrichment Heuristic: Deduce Country strictly from author Address / Affiliations (excluding conference Location)
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
                        break

    # Post-enrichment Heuristic: Deduce Language if still missing
    if 'Language' in df.columns:
        if df['Language'].dtype != 'object':
            df['Language'] = df['Language'].astype(object)
        lang_missing = df['Language'].isna() | (df['Language'].astype(str).str.strip() == '')
        for idx in df[lang_missing].index:
            cnt_val = str(df.at[idx, 'Country']) if 'Country' in df.columns and pd.notna(df.at[idx, 'Country']) else ""
            if any(k in cnt_val.lower() for k in ['brazil', 'brasil', 'portugal']):
                df.at[idx, 'Language'] = 'PT'
            elif any(k in cnt_val.lower() for k in ['united states', 'united kingdom', 'australia', 'canada']):
                df.at[idx, 'Language'] = 'EN'

    # Final normalization: Standardize Author names into Western format (First Name First) and strip academic degrees
    if 'Author' in df.columns:
        from features.gender import standardize_author_string
        def _std_author(val):
            if pd.notna(val) and str(val).strip() and str(val).strip().lower() not in ('nan', '<na>', 'none'):
                std = standardize_author_string(str(val))
                return std if std else val
            return val
        df['Author'] = df['Author'].apply(_std_author)

    # Automatic Post-Enrichment Deduplication: Consolidate any records that now share identical DOIs or OpenAlex IDs
    from core.deduplication import deduplicate_dataset
    df, post_enrich_dups = deduplicate_dataset(df)

    start_timestamp = datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
    end_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    duration = time.time() - start_time
    
    fully_enriched = tasks_count - len(failed_records_audit)
    partially_enriched = sum(1 for r in failed_records_audit if r.get("enriched_count", 0) > 0)
    failed_enriched = sum(1 for r in failed_records_audit if r.get("enriched_count", 0) == 0)
    
    total_successful_runs = fully_enriched + partially_enriched
    success_rate = (total_successful_runs / tasks_count * 100) if tasks_count > 0 else 0

    formatted_duration = format_duration(duration)

    post_dedup_msg = f" · Consolidated {post_enrich_dups} duplicate records." if post_enrich_dups > 0 else ""
    status_text.success(
        f"🎉 **Enrichment Pipeline Completed in {formatted_duration}!** "
        f"Enhanced data for **{total_successful_runs:,}/{tasks_count:,} records** ({success_rate:.1f}% hit rate).{post_dedup_msg}"
    )

    audit_lines = [
        "=======================================================================",
        "        5-TIER BIBLIOMETRIC DATA ENRICHMENT AUDIT & EXECUTION LOG",
        "=======================================================================",
        f"Execution Timestamp: {start_timestamp} → {end_timestamp} (Duration: {formatted_duration})",
        "",
        "[OVERALL DATASET CONTEXT & METRICS]",
        f"• Total Records in Memory Dataset: {len(df):,}",
        f"• Total Records Evaluated for Enrichment: {tasks_count:,}",
        f"• Post-Enrichment Duplicates Consolidated: {post_enrich_dups:,}",
        f"• Records with Valid DOIs (Tier 1-4 Candidates): {t1_queried:,}",
        f"• Records without DOIs (Tier 5 Fuzzy Title Search Candidates): {tasks_count - t1_queried:,}",
        f"• Fully Enriched Records (Found 100% of requested fields): {fully_enriched:,} ({(fully_enriched/tasks_count*100 if tasks_count else 0):.1f}%)",
        f"• Partially Enriched Records (Gained new data): {partially_enriched:,} ({(partially_enriched/tasks_count*100 if tasks_count else 0):.1f}%)",
        f"• Unresolved Records (Gained NO data): {failed_enriched:,} ({(failed_enriched/tasks_count*100 if tasks_count else 0):.1f}%)",
        "",
        f"Target Fields Requested ({len(fields_to_enrich)} fields): {fields_to_enrich}",
        "",
        "--------------------------------------------------------------------------------",
        "1. MEMORY CLUSTER & FILE PROVENANCE CONTEXT",
        "--------------------------------------------------------------------------------",
        f"• Total Records in Memory Dataset: {len(df)}",
        f"• Total Records Evaluated for Enrichment: {tasks_count}",
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
        f"• TIER 1: OpenAlex Batch API (Bulk DOI Filtering)",
        f"    - DOIs Queried: {t1_queried}",
        f"    - Records Resolved: {t1_resolved} ({((t1_resolved/t1_queried*100) if t1_queried else 0):.1f}%)",
        f"    - Total Field Values Populated: {sum(t1_fields_cnt.values())} lines",
        f"    - Field Breakdown: {dict(t1_fields_cnt) if t1_fields_cnt else 'None'}",
        "",
        f"• TIER 2: Crossref REST API (DOI Metadata Fallback)",
        f"    - Records Passed: {t2_passed}",
        f"    - Records Resolved: {t2_resolved}",
        f"    - Total Field Values Populated: {sum(t2_fields_cnt.values())} lines",
        f"    - Field Breakdown: {dict(t2_fields_cnt) if t2_fields_cnt else 'None'}",
        "",
        f"• TIER 3: PubMed eUtils API (Biomedical MeSH/Abstract Fallback)",
        f"    - Records Passed: {t3_passed} (with valid PMID)",
        f"    - Records Resolved: {t3_resolved}",
        f"    - Total Field Values Populated: {sum(t3_fields_cnt.values())} lines",
        f"    - Field Breakdown: {dict(t3_fields_cnt) if t3_fields_cnt else 'None'}",
        "",
        f"• TIER 4: Semantic Scholar API (Abstract & AI TLDR Fallback)",
        f"    - Records Passed: {t4_passed}",
        f"    - Records Resolved: {t4_resolved}",
        f"    - Total Field Values Populated: {sum(t4_fields_cnt.values())} lines",
        f"    - Field Breakdown: {dict(t4_fields_cnt) if t4_fields_cnt else 'None'}",
        "",
        f"• TIER 5: OpenAlex Fuzzy Title Search (Legacy / Non-DOI Local Papers)",
        f"    - Records Passed: {t5_passed} (searched by Title)",
        f"    - Records Resolved: {t5_resolved}",
        f"    - Total Field Values Populated: {sum(t5_fields_cnt.values())} lines",
        f"    - Field Breakdown: {dict(t5_fields_cnt) if t5_fields_cnt else 'None'}",
        "",
        "--------------------------------------------------------------------------------",
        "3. UNRESOLVED RECORDS & SPECIFIC MISSING COLUMNS AUDIT",
        "--------------------------------------------------------------------------------",
        f"Total Records with Remaining Missing Fields: {len(failed_records_audit)} / {tasks_count}",
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
        
    audit_lines.extend([
        "=" * 80,
        f"FINAL SUMMARY: {total_successful_runs}/{tasks_count} records received enhancement data. Audit saved to disk.",
        "=" * 80
    ])

    report_text = "\n".join(audit_lines)

    from utils.project_manager import save_project_file, get_timestamp_str, get_project_dir
    log_filename_base = f"enrichment_{get_timestamp_str()}.log"
    log_filename = save_project_file("logs", log_filename_base, report_text)
            
    # Push rich metrics into Streamlit System Logs & trigger immediate confirmation toast
    log_list.append(report_text)
    st.session_state.last_enrichment_report = report_text
    st.session_state.last_enrichment_logfile = log_filename
    st.toast(f"💾 Audit log automatically saved to `{log_filename}`!", icon="📄")
    
    return df
