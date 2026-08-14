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
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from core.ingestion import deduplicate_and_merge_columns

CACHE_DIR = "/tmp" if os.name == 'posix' else tempfile.gettempdir()
requests_cache.install_cache(os.path.join(CACHE_DIR, 'openalex_cache'), expire_after=604800)

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
            author_names.append(auth['author']['display_name'])
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

def needs_enrichment(row: pd.Series, fields_to_enrich: list) -> bool:
    doi_val = _get_field(row, 'DOI')
    title_val = _get_field(row, 'Title')
    if not doi_val and title_val:
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
            response = requests.get(url, headers=HEADERS, timeout=15)
            time.sleep(1.1)
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

# Tier 3: PubMed
def fetch_pubmed_by_pmid(pmid: str) -> dict:
    if pd.isna(pmid) or not str(pmid).strip(): return None
    efetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml"
    try:
        time.sleep(0.34) # Max 3 req/sec without API key
        response = requests.get(efetch_url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            text = response.text
            mesh_matches = re.findall(r'<DescriptorName[^>]*>(.*?)</DescriptorName>', text)
            abstract_matches = re.findall(r'<AbstractText[^>]*>(.*?)</AbstractText>', text)
            abstract = " ".join(abstract_matches) if abstract_matches else None
            return {
                'mesh': mesh_matches,
                'abstract': abstract
            }
    except Exception:
        pass
    return None

# Tier 4: Semantic Scholar
def fetch_semanticscholar_by_doi(doi: str) -> dict:
    if pd.isna(doi) or not str(doi).strip(): return None
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "")
    # To add an API key, users can add 'x-api-key': 'YOUR_KEY' to HEADERS and remove sleep
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{clean_doi}?fields=abstract,tldr"
    try:
        time.sleep(3.1) # 100 req per 5 min without key
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

# Tier 5: OpenAlex Fuzzy Title Search
def fetch_openalex_data_by_title(title: str) -> dict:
    if pd.isna(title) or not str(title).strip(): return None
    clean_title = str(title).strip()
    encoded_title = urllib.parse.quote(clean_title)
    url = f"https://api.openalex.org/works?filter=title.search:{encoded_title}&per-page=1"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        time.sleep(1.1)
        if response.status_code == 200:
            data = response.json()
            if data.get('results') and len(data['results']) > 0:
                return data['results'][0]
    except Exception:
        pass
    return None

# ---------------------------------------------------------
# Updates Applicator
# ---------------------------------------------------------
def apply_openalex_data(oa_data: dict, row: pd.Series, fields_to_enrich: list, updates: dict, missed: list):
    needs_update = lambda f: f in fields_to_enrich and _get_field(row, f) is None
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

    if needs_update('Author'):
        val = format_authors(oa_data.get('authorships'))
        if pd.isna(val): missed.append('Author')
        else: updates['Author'] = val

    if needs_update('Affiliations') or needs_update('Country'):
        aff_val, cnt_val = format_affiliations_and_countries(oa_data.get('authorships'))
        if needs_update('Affiliations'):
            if pd.isna(aff_val): missed.append('Affiliations')
            else: updates['Affiliations'] = aff_val
        if needs_update('Country'):
            if pd.isna(cnt_val): missed.append('Country')
            else: updates['Country'] = cnt_val

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
        if pd.isna(val): missed.append('Publication Year')
        else: updates['Publication Year'] = val
        
    if needs_update('Times Cited'):
        val = oa_data.get('cited_by_count')
        if pd.isna(val): missed.append('Times Cited')
        else: updates['Times Cited'] = val

    if needs_update('Publisher'):
        primary_loc = oa_data.get('primary_location')
        val = primary_loc['source'].get('host_organization_name') if primary_loc and primary_loc.get('source') else pd.NA
        if pd.isna(val): missed.append('Publisher')
        else: updates['Publisher'] = val
        
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

    if needs_update('Publisher'):
        val = cr_data.get('publisher')
        if val: updates['Publisher'] = val
        
    if needs_update('Publication Year'):
        try:
            val = cr_data['published-print']['date-parts'][0][0]
            updates['Publication Year'] = val
        except:
            pass
            
    if needs_update('Author'):
        authors = cr_data.get('author', [])
        author_names = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in authors if a.get('family')]
        if author_names: updates['Author'] = ", ".join(author_names)

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

# ---------------------------------------------------------
# Main Enrichment Engine
# ---------------------------------------------------------
def enrich_dataset_openalex(df: pd.DataFrame, fields_to_enrich: list, log_list: list, file_manifest: dict = None) -> pd.DataFrame:
    df = deduplicate_and_merge_columns(df)
    st.write("Starting Data Enrichment Pipeline...")
    start_time = time.time()
    
    # 1. Pre-filter tasks
    tasks = []
    dois_to_fetch = []
    for idx, row in df.iterrows():
        if needs_enrichment(row, fields_to_enrich):
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
        m2.metric("Records Requiring Enrichment", f"{tasks_count:,}")
        m3.metric("Valid DOIs (Tiers 1-4)", f"{t1_queried:,}")
        m4.metric("No DOIs (Tier 5 Title)", f"{tasks_count - t1_queried:,}")
        
        status_text = st.empty()
        progress_bar = st.progress(0)

    # TIER 1: OpenAlex Batch API (The bulk)
    status_text.markdown(f"**Tier 1:** Querying OpenAlex Batch API for **{t1_queried:,} DOIs** in batches of 50...")
    oa_batch_results = fetch_openalex_batch(dois_to_fetch)
    status_text.markdown(f"**Tier 1 Complete:** Fetched metadata for **{len(oa_batch_results):,} / {t1_queried:,} DOIs**. Now processing fallbacks (Tiers 2-5)...")
    
    completed = 0
    for idx, row in tasks:
        doi = _get_field(row, 'DOI')
        title = _get_field(row, 'Title')
        has_doi = doi is not None
        clean_doi = str(doi).replace("https://doi.org/", "").lower().strip() if has_doi else ""
        
        all_updates = {}
        missed = []
        
        needs_update = lambda f: f in fields_to_enrich and _get_field(row, f) is None and f not in all_updates
        
        # Tier 1 Apply
        oa_data = oa_batch_results.get(clean_doi)
        if oa_data:
            up_t1 = {}
            apply_openalex_data(oa_data, row, fields_to_enrich, up_t1, missed)
            if up_t1.get('enriched'):
                t1_resolved += 1
                for k, v in up_t1.items():
                    if k != 'enriched':
                        t1_fields_cnt[k] += 1
                        all_updates[k] = v
            
        # Tier 2: Crossref (if unresolved DOI or missing basic publisher info)
        if has_doi and (not oa_data or needs_update('Publisher') or needs_update('Publication Year')):
            t2_passed += 1
            cr_data = fetch_crossref_by_doi(doi)
            if cr_data:
                up_t2 = {}
                apply_crossref_data(cr_data, row, fields_to_enrich, up_t2, missed)
                if up_t2:
                    t2_resolved += 1
                    for k, v in up_t2.items():
                        t2_fields_cnt[k] += 1
                        all_updates[k] = v
                
        # Tier 3: PubMed (Only if PMID exists)
        pmid = _get_field(row, 'PMID')
        if pmid:
            if needs_update('Abstract') or needs_update('Concepts'):
                t3_passed += 1
                pm_data = fetch_pubmed_by_pmid(pmid)
                if pm_data:
                    up_t3 = {}
                    apply_pubmed_data(pm_data, row, fields_to_enrich, up_t3, missed)
                    if up_t3:
                        t3_resolved += 1
                        for k, v in up_t3.items():
                            t3_fields_cnt[k] += 1
                            all_updates[k] = v
                    
        # Tier 4: Semantic Scholar (if still missing Abstract)
        if has_doi and needs_update('Abstract'):
            t4_passed += 1
            ss_data = fetch_semanticscholar_by_doi(doi)
            if ss_data:
                up_t4 = {}
                apply_semanticscholar_data(ss_data, row, fields_to_enrich, up_t4, missed)
                if up_t4:
                    t4_resolved += 1
                    for k, v in up_t4.items():
                        t4_fields_cnt[k] += 1
                        all_updates[k] = v
                
        # Tier 5: OpenAlex Fuzzy Title (if no identifier / local)
        if not has_doi and title:
            t5_passed += 1
            oa_title_data = fetch_openalex_data_by_title(title)
            if oa_title_data:
                up_t5 = {}
                apply_openalex_data(oa_title_data, row, fields_to_enrich, up_t5, missed)
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

    start_timestamp = datetime.datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
    end_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    duration = time.time() - start_time
    
    fully_enriched = tasks_count - len(failed_records_audit)
    partially_enriched = sum(1 for r in failed_records_audit if r.get("enriched_count", 0) > 0)
    failed_enriched = sum(1 for r in failed_records_audit if r.get("enriched_count", 0) == 0)
    
    total_successful_runs = fully_enriched + partially_enriched
    success_rate = (total_successful_runs / tasks_count * 100) if tasks_count > 0 else 0

    status_text.success(
        f"🎉 **Enrichment Pipeline Completed in {duration:.1f}s!** "
        f"Enhanced data for **{total_successful_runs:,}/{tasks_count:,} records** ({success_rate:.1f}% hit rate)."
    )

    audit_lines = [
        "=======================================================================",
        "        5-TIER BIBLIOMETRIC DATA ENRICHMENT AUDIT & EXECUTION LOG",
        "=======================================================================",
        f"Execution Timestamp: {start_timestamp} → {end_timestamp} (Duration: {duration:.2f}s)",
        "",
        "[OVERALL DATASET CONTEXT & METRICS]",
        f"• Total Records in Memory Dataset: {len(df):,}",
        f"• Total Records Evaluated for Enrichment: {tasks_count:,}",
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

    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"enrichment_{timestamp}.log")
    
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
        f.flush()
            
    # Push rich metrics into Streamlit System Logs & trigger immediate confirmation toast
    log_list.append(report_text)
    st.session_state.last_enrichment_report = report_text
    st.session_state.last_enrichment_logfile = log_filename
    st.toast(f"💾 Audit log automatically saved to `{log_filename}`!", icon="📄")
    
    return df
