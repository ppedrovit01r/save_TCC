import streamlit as st
import tempfile
import os
import time
import datetime
import urllib.parse
import pandas as pd
import requests
import requests_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_DIR = "/tmp" if os.name == 'posix' else tempfile.gettempdir()
requests_cache.install_cache(os.path.join(CACHE_DIR, 'openalex_cache'), expire_after=604800)

# Polite Pool Header (Replace with your actual email in production)
HEADERS = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}

# ---------------------------------------------------------
# OpenAlex API Logic
# ---------------------------------------------------------
def fetch_openalex_data_by_title(title: str) -> dict:
    if pd.isna(title) or not str(title).strip():
        return None
        
    clean_title = urllib.parse.quote_plus(str(title).strip())
    url = f"https://api.openalex.org/works?filter=title.search:{clean_title}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        time.sleep(1.1) # Rate Limit Enforcer
        
        if response.status_code == 200:
            data = response.json()
            # If results exist, return the most relevant one (index 0)
            if data.get('results') and len(data['results']) > 0:
                return data['results'][0]
        elif response.status_code == 429:
            st.toast("⚠️ OpenAlex rate limit reached. Pausing slightly...", icon="⏳")
            time.sleep(5)
    except Exception:
        pass
    return None

def fetch_openalex_data_by_doi(doi: str) -> dict:
    if pd.isna(doi) or not str(doi).strip():
        return None
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "")
    url = f"https://api.openalex.org/works/doi:{clean_doi}"
    try:
         response = requests.get(url, headers=HEADERS, timeout=10)
         time.sleep(1.1)  # Politeness delay to avoid hitting rate limits
         if response.status_code == 200:
             return response.json()
         elif response.status_code == 429:
             print(f"Rate limit exceeded when fetching DOI '{doi}'. Consider slowing down requests.")
    except Exception as e:
         print(f"Error fetching data for DOI '{doi}': {e}")
    return None

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

def needs_enrichment(row: pd.Series, fields_to_enrich: list) -> bool:
    # check if DOI is missing or empty, and Title is present
    if pd.isna(row.get('DOI')) or str(row.get('DOI')).strip() == '':
        if pd.notna(row.get('Title')) and str(row.get('Title')).strip() != '':
            return True
        
    # regular checks for each field
    if 'Author' in fields_to_enrich and (pd.isna(row.get('Author')) or str(row.get('Author')).strip() == ''):
        return True
    if 'Publication Year' in fields_to_enrich and pd.isna(row.get('Publication Year')):
        return True
    if 'Times Cited' in fields_to_enrich and pd.isna(row.get('Times Cited')):
        return True
    if 'Publisher' in fields_to_enrich and (pd.isna(row.get('Publisher')) or str(row.get('Publisher')).strip() == ''):
        return True
    if 'Article References' in fields_to_enrich and (pd.isna(row.get('Article References')) or str(row.get('Article References')).strip() == ''):
        return True
    return False

def process_single_row(task_tuple: tuple, fields_to_enrich: list) -> tuple:
    index, row = task_tuple
    doi = row.get('DOI')
    title = row.get('Title')
    updates = {}
    missed = []
    
    has_doi = pd.notna(doi) and str(doi).strip() != ''
    has_title = pd.notna(title) and str(title).strip() != ''

    oa_data = None
    search_key = doi if has_doi else title if has_title else None #well, if there's no title... we're done
    
    if oa_data:
        updates['enriched'] = True
        # If found by title, save the missing DOI back into the dataset!
        if not has_doi:
            new_doi = oa_data.get('doi')
            if new_doi:
                updates['DOI'] = str(new_doi).replace("https://doi.org/", "")
            else:
                missed.append('DOI (Not returned by OpenAlex Title Search)')
        
        if 'Author' in fields_to_enrich and (pd.isna(row.get('Author')) or str(row.get('Author')).strip() == ''):
            val = format_authors(oa_data.get('authorships'))
            if pd.isna(val) or val == '': missed.append('Author')
            else: updates['Author'] = val
            
        if 'Publication Year' in fields_to_enrich and pd.isna(row.get('Publication Year')):
            val = oa_data.get('publication_year')
            if pd.isna(val): missed.append('Publication Year')
            else: updates['Publication Year'] = val
            
        if 'Times Cited' in fields_to_enrich and pd.isna(row.get('Times Cited')):
            val = oa_data.get('cited_by_count')
            if pd.isna(val): missed.append('Times Cited')
            else: updates['Times Cited'] = val
            
        if 'Publisher' in fields_to_enrich and (pd.isna(row.get('Publisher')) or str(row.get('Publisher')).strip() == ''):
            primary_loc = oa_data.get('primary_location')
            val = primary_loc['source'].get('host_organization_name') if primary_loc and primary_loc.get('source') else pd.NA
            if pd.isna(val) or val == '': missed.append('Publisher')
            else: updates['Publisher'] = val
            
        if 'Article References' in fields_to_enrich and (pd.isna(row.get('Article References')) or str(row.get('Article References')).strip() == ''):
             val = format_references(oa_data.get('referenced_works'))
             if pd.isna(val) or val == '': missed.append('Article References')
             else: updates['Article References'] = val
    else:
        if not has_doi:
            missed.append('DOI (Failed to find article by Title)')
        missed.extend(fields_to_enrich)
        
    return index, updates, missed, doi

def enrich_dataset_openalex(df: pd.DataFrame, fields_to_enrich: list, log_list: list) -> pd.DataFrame:
    st.write("Enriching full dataset via OpenAlex (using DOI)...")
    start_time = time.time()
    # 1. Pre-filter tasks to save API requests
    tasks = []
    for idx, row in df.iterrows():
        doi = row.get('DOI')
        if needs_enrichment(row, fields_to_enrich):
            tasks.append((idx, row))
            
    tasks_count = len(tasks)
    progress_bar = st.progress(0)
    
    # 2. Exit early if no API calls are needed
    if tasks_count == 0:
        log_list.append("Optimization: No API calls made. All selected fields are already populated in the dataset.")
        progress_bar.progress(1.0)
        return df

    enriched_count = 0
    detailed_log_lines = []
    
    # 3. Concurrent Processing
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_single_row, task, fields_to_enrich): task[0] for task in tasks}
        
        completed = 0
        for future in as_completed(futures):
            idx, updates, missed, doi = future.result()
            
            if updates.get('enriched'):
                enriched_count += 1
                for col, val in updates.items():
                    if col != 'enriched':
                        df.at[idx, col] = val

            if missed:
                detailed_log_lines.append(f"Row {idx} (DOI: {doi}): Failed to find {', '.join(missed)}")
                        
            completed += 1
            progress_bar.progress(completed / tasks_count)
            
    duration = time.time() - start_time

    # --- WRITE DETAILED LOG TO DISK ---
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"enrichment_{timestamp}.log")
    
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write(f"OpenAlex Enrichment Log - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("-" * 60 + "\n")
        f.write(f"Total time elapsed: {duration:.2f} seconds\n")
        f.write(f"Records requiring enrichment: {tasks_count}\n")
        f.write(f"Records successfully updated: {enriched_count}\n")
        f.write("-" * 60 + "\n")
        f.write("Detailed Misses (Requested fields not found in OpenAlex):\n")
        if detailed_log_lines:
            for line in detailed_log_lines:
                f.write(line + "\n")
        else:
            f.write("None. All requested fields were successfully fetched.\n")
            
    # Update UI Logs
    log_list.append(f"Enrichment completed in {duration:.2f}s. {enriched_count}/{tasks_count} records updated.")
    log_list.append(f"Detailed audit saved locally to: {log_filename}")
    
    return df