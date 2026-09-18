import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import time
import re
import requests
from collections import defaultdict, Counter
import io
import base64
from utils.formatters import format_duration
from utils.project_manager import get_global_cache_dir, save_project_file, format_timestamped_filename, get_active_project_name, get_timestamp_str, open_project_folder
from utils.exports import render_project_saved_notice

# Try importing gender_guesser
try:
    import gender_guesser.detector as gender_detector
    HAS_GENDER_GUESSER = True
except ImportError:
    HAS_GENDER_GUESSER = False

# Try importing wordcloud
try:
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False

CACHE_DIR = os.path.join("utils", "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "gender_cache.json")
CACHE_INIT_FILE = os.path.join(CACHE_DIR, "gender_cache_init.json")
DEFAULT_CONFIDENCE_THRESHOLD = 0.75
DEFAULT_OFFLINE_THRESHOLD = 0.85

# Country data mapping (maps aliases to locale for gender-guesser and ISO-2 for NamSor)
# Short 2-letter codes that collide with common words/prepositions (de, in, it, no, es, at, is, be, to) are removed from substring matching
COUNTRY_DATA = {
    'brazil': {'locale': 'brazil', 'iso2': 'BR', 'name': 'Brazil'},
    'brasil': {'locale': 'brazil', 'iso2': 'BR', 'name': 'Brazil'},
    'united states': {'locale': 'usa', 'iso2': 'US', 'name': 'United States'},
    'usa': {'locale': 'usa', 'iso2': 'US', 'name': 'United States'},
    'united kingdom': {'locale': 'great_britain', 'iso2': 'GB', 'name': 'United Kingdom'},
    'uk': {'locale': 'great_britain', 'iso2': 'GB', 'name': 'United Kingdom'},
    'england': {'locale': 'great_britain', 'iso2': 'GB', 'name': 'United Kingdom'},
    'germany': {'locale': 'germany', 'iso2': 'DE', 'name': 'Germany'},
    'deutschland': {'locale': 'germany', 'iso2': 'DE', 'name': 'Germany'},
    'spain': {'locale': 'spain', 'iso2': 'ES', 'name': 'Spain'},
    'españa': {'locale': 'spain', 'iso2': 'ES', 'name': 'Spain'},
    'espana': {'locale': 'spain', 'iso2': 'ES', 'name': 'Spain'},
    'italy': {'locale': 'italy', 'iso2': 'IT', 'name': 'Italy'},
    'italia': {'locale': 'italy', 'iso2': 'IT', 'name': 'Italy'},
    'france': {'locale': 'france', 'iso2': 'FR', 'name': 'France'},
    'portugal': {'locale': 'portugal', 'iso2': 'PT', 'name': 'Portugal'},
    'china': {'locale': 'china', 'iso2': 'CN', 'name': 'China'},
    'india': {'locale': 'india', 'iso2': 'IN', 'name': 'India'},
    'japan': {'locale': 'japan', 'iso2': 'JP', 'name': 'Japan'},
    'south korea': {'locale': 'korea', 'iso2': 'KR', 'name': 'South Korea'},
    'korea': {'locale': 'korea', 'iso2': 'KR', 'name': 'South Korea'},
    'australia': {'locale': 'great_britain', 'iso2': 'AU', 'name': 'Australia'},
    'canada': {'locale': 'usa', 'iso2': 'CA', 'name': 'Canada'},
    'netherlands': {'locale': 'the_netherlands', 'iso2': 'NL', 'name': 'Netherlands'},
    'holland': {'locale': 'the_netherlands', 'iso2': 'NL', 'name': 'Netherlands'},
    'switzerland': {'locale': 'swiss', 'iso2': 'CH', 'name': 'Switzerland'},
    'sweden': {'locale': 'sweden', 'iso2': 'SE', 'name': 'Sweden'},
    'norway': {'locale': 'norway', 'iso2': 'NO', 'name': 'Norway'},
    'denmark': {'locale': 'denmark', 'iso2': 'DK', 'name': 'Denmark'},
    'finland': {'locale': 'finland', 'iso2': 'FI', 'name': 'Finland'},
    'poland': {'locale': 'poland', 'iso2': 'PL', 'name': 'Poland'},
    'austria': {'locale': 'austria', 'iso2': 'AT', 'name': 'Austria'},
    'belgium': {'locale': 'belgium', 'iso2': 'BE', 'name': 'Belgium'},
    'ireland': {'locale': 'ireland', 'iso2': 'IE', 'name': 'Ireland'},
    'russia': {'locale': 'russia', 'iso2': 'RU', 'name': 'Russia'},
    'mexico': {'locale': 'spain', 'iso2': 'MX', 'name': 'Mexico'},
    'argentina': {'locale': 'spain', 'iso2': 'AR', 'name': 'Argentina'},
    'chile': {'locale': 'spain', 'iso2': 'CL', 'name': 'Chile'},
    'colombia': {'locale': 'spain', 'iso2': 'CO', 'name': 'Colombia'},
    'tunisia': {'locale': 'france', 'iso2': 'TN', 'name': 'Tunisia'},
    'israel': {'locale': 'israel', 'iso2': 'IL', 'name': 'Israel'}
}

# Explicit ISO country codes mapping for when a code appears as an exact value or bounded code
EXACT_ISO_DATA = {
    'br': {'locale': 'brazil', 'iso2': 'BR', 'name': 'Brazil'},
    'bra': {'locale': 'brazil', 'iso2': 'BR', 'name': 'Brazil'},
    'us': {'locale': 'usa', 'iso2': 'US', 'name': 'United States'},
    'usa': {'locale': 'usa', 'iso2': 'US', 'name': 'United States'},
    'gb': {'locale': 'great_britain', 'iso2': 'GB', 'name': 'United Kingdom'},
    'gbr': {'locale': 'great_britain', 'iso2': 'GB', 'name': 'United Kingdom'},
    'de': {'locale': 'germany', 'iso2': 'DE', 'name': 'Germany'},
    'deu': {'locale': 'germany', 'iso2': 'DE', 'name': 'Germany'},
    'es': {'locale': 'spain', 'iso2': 'ES', 'name': 'Spain'},
    'esp': {'locale': 'spain', 'iso2': 'ES', 'name': 'Spain'},
    'fr': {'locale': 'france', 'iso2': 'FR', 'name': 'France'},
    'fra': {'locale': 'france', 'iso2': 'FR', 'name': 'France'},
    'it': {'locale': 'italy', 'iso2': 'IT', 'name': 'Italy'},
    'ita': {'locale': 'italy', 'iso2': 'IT', 'name': 'Italy'},
    'pt': {'locale': 'portugal', 'iso2': 'PT', 'name': 'Portugal'},
    'prt': {'locale': 'portugal', 'iso2': 'PT', 'name': 'Portugal'},
    'ca': {'locale': 'usa', 'iso2': 'CA', 'name': 'Canada'},
    'can': {'locale': 'usa', 'iso2': 'CA', 'name': 'Canada'},
    'au': {'locale': 'great_britain', 'iso2': 'AU', 'name': 'Australia'},
    'aus': {'locale': 'great_britain', 'iso2': 'AU', 'name': 'Australia'},
    'cn': {'locale': 'china', 'iso2': 'CN', 'name': 'China'},
    'chn': {'locale': 'china', 'iso2': 'CN', 'name': 'China'},
    'in': {'locale': 'india', 'iso2': 'IN', 'name': 'India'},
    'ind': {'locale': 'india', 'iso2': 'IN', 'name': 'India'},
    'jp': {'locale': 'japan', 'iso2': 'JP', 'name': 'Japan'},
    'jpn': {'locale': 'japan', 'iso2': 'JP', 'name': 'Japan'},
    'kr': {'locale': 'korea', 'iso2': 'KR', 'name': 'South Korea'},
    'kor': {'locale': 'korea', 'iso2': 'KR', 'name': 'South Korea'},
    'mx': {'locale': 'spain', 'iso2': 'MX', 'name': 'Mexico'},
    'ar': {'locale': 'spain', 'iso2': 'AR', 'name': 'Argentina'},
    'cl': {'locale': 'spain', 'iso2': 'CL', 'name': 'Chile'},
    'co': {'locale': 'spain', 'iso2': 'CO', 'name': 'Colombia'}
}

# -----------------------------------------------------------------------------
# Persistent Cache Management (Guarantees NamSor Quota Preservation)
# -----------------------------------------------------------------------------
def load_gender_cache() -> dict:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = {}
    
    # 1. Load primary active cache if exists
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    elif os.path.exists(os.path.join("logs", "gender_cache.json")):
        try:
            with open(os.path.join("logs", "gender_cache.json"), 'r', encoding='utf-8') as f:
                cache = json.load(f)
            save_gender_cache(cache)
        except Exception:
            cache = {}

    # 2. Seed from gender_cache_init.json (curated baseline lexicon) if present
    if os.path.exists(CACHE_INIT_FILE):
        try:
            with open(CACHE_INIT_FILE, 'r', encoding='utf-8') as f:
                init_cache = json.load(f)
                needs_save = False
                for k, v in init_cache.items():
                    if k not in cache:
                        cache[k] = v
                        needs_save = True
                if needs_save:
                    save_gender_cache(cache)
        except Exception:
            pass

    return cache

def save_gender_cache(cache: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def generate_gender_audit_log(results_dict: dict, strategy_name: str, offline_thresh: float, final_thresh: float) -> str:
    """Generates a detailed, comprehensive text audit log for gender inference execution."""
    authors_df = results_dict.get('authors_df', pd.DataFrame())
    articles_df = results_dict.get('articles_df', pd.DataFrame())
    duration = results_dict.get('duration', 0.0)
    cache_hits = results_dict.get('cache_hits', 0)
    offline_hits = results_dict.get('offline_hits', 0)
    namsor_calls = results_dict.get('namsor_calls', 0)
    quota_saved = results_dict.get('quota_saved_pct', 100.0)
    is_partial = results_dict.get('is_partial', False)
    
    total_authors = len(authors_df)
    total_articles = len(articles_df)
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proj_name = get_active_project_name()
    
    # Calculate gender statistics
    if not authors_df.empty and 'gender' in authors_df.columns:
        gender_counts = authors_df['gender'].value_counts().to_dict()
        female_count = gender_counts.get('female', 0)
        male_count = gender_counts.get('male', 0)
        unknown_count = gender_counts.get('unknown', 0)
        reliable_count = int(authors_df['reliable'].sum()) if 'reliable' in authors_df.columns else 0
        engine_counts = authors_df['engine'].value_counts().to_dict() if 'engine' in authors_df.columns else {}
    else:
        female_count = male_count = unknown_count = reliable_count = 0
        engine_counts = {}

    # Article-level leadership stats
    first_f = int(articles_df['first_author_female'].sum()) if not articles_df.empty and 'first_author_female' in articles_df.columns else 0
    first_m = int(articles_df['first_author_male'].sum()) if not articles_df.empty and 'first_author_male' in articles_df.columns else 0
    last_f = int(articles_df['last_author_female'].sum()) if not articles_df.empty and 'last_author_female' in articles_df.columns else 0
    last_m = int(articles_df['last_author_male'].sum()) if not articles_df.empty and 'last_author_male' in articles_df.columns else 0

    log_lines = [
        "=" * 80,
        "                    GENDER MAPPING INFERENCE & DIVERSITY AUDIT REPORT",
        "=" * 80,
        f"Generated At:             {now_str}",
        f"Active Project:           {proj_name}",
        f"Execution Status:         {'PARTIAL CHECKPOINT (Interrupted by Error)' if is_partial else 'COMPLETE SUCCESS'}",
        f"Total Execution Duration: {format_duration(duration)}",
        f"Inference Strategy:       {strategy_name}",
        f"Offline Acceptance Thresh:{int(offline_thresh * 100)}%",
        f"Final Confidence Thresh:  {int(final_thresh * 100)}%",
        "",
        "--------------------------------------------------------------------------------",
        "1. DATASET VOLUME & EXECUTION SCOPE",
        "--------------------------------------------------------------------------------",
        f"• Total Evaluated Articles:        {total_articles:,}",
        f"• Total Author Mentions Processed: {total_authors:,}",
        f"• Reliable Gender Classifications: {reliable_count:,} ({((reliable_count/total_authors)*100 if total_authors else 0):.1f}%)",
        "",
        "--------------------------------------------------------------------------------",
        "2. INFERENCE ENGINE & QUOTA OPTIMIZATION AUDIT",
        "--------------------------------------------------------------------------------",
        f"• Persistent Cache Hits (Free):    {cache_hits:,} names ({((cache_hits/total_authors)*100 if total_authors else 0):.1f}%)",
        f"• Offline Rule Matches (Free):     {offline_hits:,} names ({((offline_hits/total_authors)*100 if total_authors else 0):.1f}%)",
        f"• External NamSor API Requests:    {namsor_calls:,} calls ({((namsor_calls/total_authors)*100 if total_authors else 0):.1f}%)",
        f"• Quota Savings Efficiency:        {quota_saved:.1f}% free resolutions without network API consumption",
        f"• Classification Engine Breakdown:",
    ]
    
    for eng, cnt in engine_counts.items():
        log_lines.append(f"    - {eng}: {cnt:,} author mentions ({((cnt/total_authors)*100 if total_authors else 0):.1f}%)")
        
    log_lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "3. GENDER DEMOGRAPHIC REPRESENTATION SUMMARY",
        "--------------------------------------------------------------------------------",
        f"• Female Authors: {female_count:,} ({((female_count/total_authors)*100 if total_authors else 0):.1f}%)",
        f"• Male Authors:   {male_count:,} ({((male_count/total_authors)*100 if total_authors else 0):.1f}%)",
        f"• Unknown/Unsure: {unknown_count:,} ({((unknown_count/total_authors)*100 if total_authors else 0):.1f}%)",
        "",
        "--------------------------------------------------------------------------------",
        "4. CAREER PROGRESSION & LEADERSHIP POSITIONING (SCISSORS EFFECT)",
        "--------------------------------------------------------------------------------",
        f"• First Author (Mentee / Lead Researcher):",
        f"    - Female: {first_f:,} articles ({((first_f/total_articles)*100 if total_articles else 0):.1f}%)",
        f"    - Male:   {first_m:,} articles ({((first_m/total_articles)*100 if total_articles else 0):.1f}%)",
        f"• Last Author (Senior PI / Advisor):",
        f"    - Female: {last_f:,} articles ({((last_f/total_articles)*100 if total_articles else 0):.1f}%)",
        f"    - Male:   {last_m:,} articles ({((last_m/total_articles)*100 if total_articles else 0):.1f}%)",
        f"• Progression Scissors Gap (First% - Last%):",
        f"    - Female Gap: {((first_f - last_f)/total_articles*100 if total_articles else 0):+.1f} percentage points",
        f"    - Male Gap:   {((first_m - last_m)/total_articles*100 if total_articles else 0):+.1f} percentage points",
        "",
        "=" * 80,
        "END OF GENDER AUDIT TRAIL",
        "=" * 80
    ])
    
    return "\n".join(log_lines)

# -----------------------------------------------------------------------------
# Author Parsing & First/Last Name Extraction
# -----------------------------------------------------------------------------
# Author Parsing & Multi-Author Delimiter Splitting
# -----------------------------------------------------------------------------
def split_authors_string(authors_str: str) -> list:
    """
    Splits an authors string into individual author strings robustly.
    Handles:
    - Semicolon separated: 'Santos, I.; Neto, P.; Resende, R.'
    - 'and' separated: 'John Smith and Jane Doe'
    - Comma-separated First-Last names: 'Ismayle S. Santos, Pedro A. Santos Neto, Rodolfo F. Resende'
    - Comma-separated Last, First pairs: 'Santos, Ismayle; Neto, Pedro'
    """
    if not authors_str or pd.isna(authors_str) or not isinstance(authors_str, str):
        return []
        
    s = authors_str.strip()
    if not s or s.lower() == 'nan':
        return []

    # 1. If semicolon exists, it is the primary academic separator
    if ';' in s:
        return [a.strip() for a in s.split(';') if a.strip()]

    # 2. If ' and ' exists (e.g. BibTeX format)
    if ' and ' in s.lower():
        parts = re.split(r'\s+and\s+', s, flags=re.IGNORECASE)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]

    # 3. Comma separated list of authors
    # Check if commas separate multiple full names:
    # E.g. "Ismayle S. Santos, Pedro A. Santos Neto, Rodolfo F. Resende"
    # Or "Santos, Ismayle" (single author: LastName, FirstName)
    if ',' in s:
        comma_parts = [p.strip() for p in s.split(',') if p.strip()]
        if len(comma_parts) == 1:
            return comma_parts
        if len(comma_parts) == 2:
            # Check if this is 1 author "LastName, FirstName" or 2 authors "FirstName LastName, FirstName LastName"
            p0_words = comma_parts[0].split()
            p1_words = comma_parts[1].split()
            # If both have multiple words (e.g. "Luan Luiz Gonçalves, Flávio Luiz Schiavoni"), they are 2 distinct authors!
            if len(p0_words) >= 2 and len(p1_words) >= 2:
                return comma_parts
            # Otherwise, "Silva, Maria" -> 1 author
            return [s]
        else:
            # 3 or more comma parts:
            # Check if it's a sequence of "LastName, FirstName, LastName, FirstName"
            # or a sequence of full names "First Last, First Last, First Last"
            # If almost all comma parts have 2 or more words (e.g. "Ismayle S. Santos", "Pedro A. Santos Neto"),
            # each comma part is a complete author name!
            multi_word_parts = sum(1 for p in comma_parts if len(p.split()) >= 2)
            if multi_word_parts >= len(comma_parts) - 1:
                return comma_parts
            elif len(comma_parts) % 2 == 0:
                # Pairs of "LastName, FirstName"
                paired = []
                for i in range(0, len(comma_parts), 2):
                    paired.append(f"{comma_parts[i]}, {comma_parts[i+1]}")
                return paired
            else:
                return comma_parts

    return [s]

def extract_name_parts(full_name: str) -> tuple:
    """
    Extracts first name and surname robustly.
    Handles 'LastName, FirstName Middle' and 'FirstName Middle LastName'.
    Handles hyphenated names (Marie-Claire -> Marie).
    Flags single-letter initials (e.g. 'W. Smith', 'J. Doe') as unclassifiable.
    Returns (cleaned_first_name, cleaned_last_name, is_initial).
    """
    if not full_name or pd.isna(full_name) or not isinstance(full_name, str):
        return None, None, True
        
    clean_name = re.sub(r'\(.*?\)', '', full_name)
    clean_name = re.sub(r'\[.*?\]', '', clean_name)
    clean_name = re.sub(r'<.*?>', '', clean_name)
    clean_name = clean_name.replace('"', '').replace("'", "").strip()
    
    if not clean_name:
        return None, None, True

    first_part = None
    last_part = ""
    
    # Case 1: "LastName, FirstName Middle"
    if ',' in clean_name:
        parts = [p.strip() for p in clean_name.split(',') if p.strip()]
        last_part = parts[0]
        if len(parts) > 1:
            after_comma = parts[1].split()
            if after_comma:
                first_part = after_comma[0]
        else:
            first_part = parts[0].split()[0] if parts[0].split() else None
    else:
        # Case 2: "FirstName Middle LastName"
        parts = clean_name.split()
        if parts:
            first_part = parts[0]
            if len(parts) > 1:
                last_part = parts[-1]

    if not first_part:
        return None, None, True

    # Check for single initial (e.g., 'W.', 'W', 'J.')
    first_part_clean = first_part.strip().rstrip('.')
    if len(first_part_clean) <= 1 or (len(first_part) == 2 and first_part.endswith('.')):
        return None, None, True

    # Handle hyphenated names: use first part
    if '-' in first_part:
        first_part = first_part.split('-')[0].strip()

    return first_part.strip().title(), last_part.strip().title(), False

def _resolve_single_country_info(text: str) -> tuple:
    val = text.strip().lower()
    if not val:
        return None, None, None
        
    val_clean = val.strip(' ,;.-')
    if val_clean in EXACT_ISO_DATA:
        d = EXACT_ISO_DATA[val_clean]
        return d['locale'], d['iso2'], d['name']
        
    # Full country names
    for key, data in COUNTRY_DATA.items():
        if re.search(r'\b' + re.escape(key) + r'\b', val):
            return data['locale'], data['iso2'], data['name']
            
    # Prominent institutions/cities for Brazil fallback
    if re.search(r'\b(universidade federal|instituto federal|universidade estadual|univ federal|usp|unicamp|unesp|ufrj|ufmg|ufrgs|ufsc|ufpr|ufpe|unb|ufba|ufc|ufscar|unifesp|puc-sp|puc-rio|pucrs|puc-pr|pucpr|pontifícia universidade católica|pontificia universidade catolica|fiocruz|inpe|embrapa)\b', val):
        return 'brazil', 'BR', 'Brazil'
        
    # Prominent institutions for Canada
    if re.search(r'\b(école de technologie supérieure|ecole de technologie superieure|ets montreal|quebec|montreal)\b', val):
        return 'usa', 'CA', 'Canada'
        
    return None, None, None

def extract_article_country_info(row: pd.Series) -> tuple:
    """Extracts (country_locale, country_iso2, display_country_name) strictly from author-bound fields (Country, Address, Affiliations).
    Supports semicolon-delimited countries/affiliations.
    Conference 'Location' is strictly excluded to prevent misattributing conference venue to author origin."""
    for col in ['Country', 'Address', 'Affiliations']:
        if col in row and pd.notna(row[col]) and str(row[col]).strip():
            raw_val = str(row[col]).strip()
            
            # If semicolon-separated, check each piece
            if ';' in raw_val:
                pieces = [p.strip() for p in raw_val.split(';') if p.strip()]
                for p in pieces:
                    loc, iso2, name = _resolve_single_country_info(p)
                    if name:
                        return loc, iso2, name
            else:
                loc, iso2, name = _resolve_single_country_info(raw_val)
                if name:
                    return loc, iso2, name
                
    return None, None, 'Unknown'

# -----------------------------------------------------------------------------
# Classification Engines (Offline Detector + NamSor API)
# -----------------------------------------------------------------------------
def classify_gender_offline(first_name: str, country_locale: str = None, detector=None) -> dict:
    """Classifies gender using gender-guesser with country specifics."""
    if not HAS_GENDER_GUESSER or detector is None:
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'Unavailable'}

    try:
        if country_locale:
            res = detector.get_gender(first_name, country_locale)
        else:
            res = detector.get_gender(first_name)
    except Exception:
        res = detector.get_gender(first_name)

    # Map gender-guesser outputs to standard schema
    if res == 'female':
        return {'gender': 'female', 'probability': 0.96, 'engine': 'gender-guesser'}
    elif res == 'mostly_female':
        return {'gender': 'female', 'probability': 0.80, 'engine': 'gender-guesser'}
    elif res == 'male':
        return {'gender': 'male', 'probability': 0.96, 'engine': 'gender-guesser'}
    elif res == 'mostly_male':
        return {'gender': 'male', 'probability': 0.80, 'engine': 'gender-guesser'}
    elif res == 'andy':
        return {'gender': 'unknown', 'probability': 0.50, 'engine': 'gender-guesser (epicene)'}
    else:
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'gender-guesser'}

def classify_gender_namsor(first_name: str, last_name: str = "", country_iso2: str = None, api_key: str = None) -> dict:
    """Queries NamSor v2 API with geo-localization as used in Minuzzo et al. (2026)."""
    if not api_key:
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'NamSor (No Key)'}

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-API-KEY': api_key.strip()
    }
    
    # Use Geo endpoint if country ISO2 is available
    if country_iso2 and len(country_iso2) == 2:
        url = f"https://v2.namsor.com/NamSorAPIv2/api2/json/genderGeo/{first_name}/{last_name or 'author'}/{country_iso2.upper()}"
    else:
        url = f"https://v2.namsor.com/NamSorAPIv2/api2/json/gender/{first_name}/{last_name or 'author'}"

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'gender': str(data.get('likelyGender', 'unknown')).lower(),
                'probability': float(data.get('probabilityCalibrated', 0.0)),
                'engine': 'NamSor API'
            }
        elif resp.status_code in [401, 403]:
            return {'gender': 'unknown', 'probability': 0.0, 'engine': f'NamSor Quota/Auth Error ({resp.status_code})'}
        else:
            return {'gender': 'unknown', 'probability': 0.0, 'engine': f'NamSor HTTP {resp.status_code}'}
    except Exception as e:
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'NamSor Network Error'}

# -----------------------------------------------------------------------------
# Cascaded Hybrid Resolver (Cache First -> Offline >=85% -> NamSor Fallback)
# -----------------------------------------------------------------------------
def classify_author_gender_hybrid(
    first_name: str,
    last_name: str,
    country_locale: str,
    country_iso2: str,
    gender_cache: dict,
    detector,
    namsor_api_key: str,
    offline_threshold: float = 0.85,
    final_threshold: float = 0.75
) -> tuple:
    """
    Intelligent Cascaded Hybrid Resolution to preserve NamSor Quota:
    1. Check Cache (immediate hit if found with high confidence or country-specific match).
    2. Run Offline Detector:
       - If probability >= offline_threshold (e.g. 85-90%), ACCEPT immediately (0 API calls!).
         Examples: 'Pedro', 'Maria', 'Carlos', 'John' are globally unambiguous (>95%).
    3. If Offline Detector is uncertain (< offline_threshold, e.g. 'andy', 'mostly', 'Daniele'):
       - If NamSor key is available: Call NamSor with geo-localization if country known.
       - Cache NamSor result to disk so it is never called again.
       - If NamSor fails/quota exceeded: gracefully fallback to the offline result.
    4. Apply final acceptance threshold (default 75% as in Minuzzo et al. 2026).
    Returns (result_dict, source_type) where source_type is 'cache', 'offline', or 'namsor'.
    """
    fn_lower = first_name.lower()
    
    # 1. Check Cache:
    # A) Check specific country key if country is known
    if country_iso2:
        c_key = f"{fn_lower}_{country_iso2.lower()}"
        if c_key in gender_cache:
            res = gender_cache[c_key].copy()
            res['reliable'] = res.get('probability', 0.0) >= final_threshold
            if not res['reliable']: res['gender'] = 'unknown'
            return res, 'cache'
            
    # B) Check generic key
    if fn_lower in gender_cache:
        cached_entry = gender_cache[fn_lower]
        # If generic cache is high confidence (>= offline_threshold), accept universally
        if cached_entry.get('probability', 0.0) >= offline_threshold:
            res = cached_entry.copy()
            res['reliable'] = True
            return res, 'cache'

    # 2. Run Offline Engine (gender_guesser + supplemental dictionary)
    offline_res = classify_gender_offline(first_name, country_locale, detector)
    offline_prob = offline_res.get('probability', 0.0)
    
    # If offline confidence is high (>= offline_threshold, e.g. 85% or 90%), accept offline!
    if offline_prob >= offline_threshold and offline_res.get('gender') in ['male', 'female']:
        # Cache universally under first_name
        gender_cache[fn_lower] = offline_res
        res = offline_res.copy()
        res['reliable'] = True
        return res, 'offline'

    # 3. If Offline is uncertain (< offline_threshold or 'andy'/'unknown'):
    # Try NamSor if API key provided
    if namsor_api_key and namsor_api_key.strip():
        namsor_res = classify_gender_namsor(first_name, last_name, country_iso2=country_iso2, api_key=namsor_api_key)
        
        # Check for Quota or Authentication errors (HTTP 401, 403)
        if 'Quota/Auth Error' in namsor_res.get('engine', '') or namsor_res.get('error_type') in ['quota', 'auth']:
            err_msg = namsor_res.get('engine', 'NamSor Quota Exhausted or Invalid API Key')
            return {'gender': 'unknown', 'probability': 0.0, 'engine': err_msg, 'is_quota_error': True, 'error_msg': err_msg}, 'namsor_error'

        # If NamSor returned a successful classification
        if 'Error' not in namsor_res.get('engine', '') and 'HTTP 40' not in namsor_res.get('engine', ''):
            # Cache under country-specific key if country is known
            if country_iso2:
                gender_cache[f"{fn_lower}_{country_iso2.lower()}"] = namsor_res
            # If high confidence (>= 90%), also cache universally
            if namsor_res.get('probability', 0.0) >= 0.90:
                gender_cache[fn_lower] = namsor_res
            else:
                gender_cache[f"{fn_lower}_{country_iso2 or 'generic'}"] = namsor_res
                
            res = namsor_res.copy()
            res['reliable'] = res.get('probability', 0.0) >= final_threshold
            if not res['reliable']:
                res['gender'] = 'unknown'
            return res, 'namsor'

    # 4. If NamSor was not available or failed non-critically: fallback to offline result
    res = offline_res.copy()
    res['reliable'] = offline_prob >= final_threshold
    if not res['reliable']:
        res['gender'] = 'unknown'
    return res, 'offline'

# -----------------------------------------------------------------------------
# Main Feature Presentation
# -----------------------------------------------------------------------------
def show(df: pd.DataFrame):
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <h2 style="font-size: 24px; font-weight: 700; color: #1E293B; margin-bottom: 4px;">
            <i class="bi bi-gender-ambiguous" style="color: #697aa2;"></i> Authorship Gender Disparity & Demographic Mapping
        </h2>
        <div style="color: #64748B; font-size: 14px;">
            Automated gender inference from first names with locational intelligence, career progression analysis (first vs. last author), 
            thematic alignment, and Cochran sample validation.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if df is None or df.empty:
        st.warning("⚠️ No dataset active in memory. Please upload and load your bibliographic records in the Data Preparation hub.")
        return

    # Check for Author column
    if 'Author' not in df.columns:
        st.error("🚨 The dataset does not contain an **Author** column. Please ensure author names are populated before running gender mapping.")
        return

    # Focus Mode Banner
    if 'focus_topics' in st.session_state and len(st.session_state.focus_topics) > 0:
        topic_str = ", ".join([str(t) for t in st.session_state.focus_topics])
        st.info(f"🎯 **Global Focus Mode Active:** Analyzing author gender disparity specifically for **Topic(s): [{topic_str}]** ({len(df)} articles).")

    # Load persistent cache for badge info
    gender_cache = load_gender_cache()
    cached_names_count = len(gender_cache)

    # Check for recent NamSor error
    if 'gender_error' in st.session_state:
        g_err = st.session_state.gender_error
        st.error(
            f"🛑 **{g_err.get('title', 'NamSor Quota / API Limit Reached')}**\n\n"
            f"**Details:** {g_err.get('message', 'Quota limit reached.')}\n\n"
            f"💾 **Work Preserved:** Analyzed **{g_err.get('processed_articles', 0)} of {g_err.get('total_articles', 0)} articles** "
            f"({g_err.get('processed_authors', 0)} author records). "
            f"All classifications are safely cached in `logs/gender_cache.json`!\n\n"
            f"👉 **Next Step:** You can enter a **new NamSor API key** below, or switch to **Pure Offline mode** to complete the remaining records instantly."
        )

    # 1. Pipeline Configuration Panel
    is_panel_expanded = ('gender_analysis_results' not in st.session_state) or ('gender_error' in st.session_state)
    with st.expander("⚙️ Cascaded Inference Engine & NamSor Quota Protection", expanded=is_panel_expanded):
        st.markdown(f"""
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #697aa2; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 13px; color: #334155;">
            <b>🛡️ Quota Optimization Active:</b> The system checks local cache and offline rules first. 
            Globally unambiguous names (e.g. <i>Pedro</i>, <i>Maria</i>, <i>Carlos</i> ≥ 85%) are resolved offline with zero API calls. 
            NamSor API is queried <b>only for culturally ambiguous names</b> (e.g. <i>Daniele</i> in Brazil vs. Italy, <i>Andrea</i>, <i>Nicola</i>), preserving your monthly quota!
            <br><span style="color: #64748B; font-size: 12px;">💾 Persistent Cache: <b>{cached_names_count:,} unique names</b> currently saved locally in <code>logs/gender_cache.json</code>.</span>
        </div>
        """, unsafe_allow_html=True)

        c_conf1, c_conf2 = st.columns([1.2, 1.8], gap="medium")
        
        with c_conf1:
            mode_choice = st.radio(
                "Inference Strategy",
                [
                    "Hybrid: Smart Cache + Offline (≥85%) + NamSor Fallback",
                    "Pure Offline: Zero API Keys (Free & Instant)"
                ],
                help="Hybrid mode uses the free offline detector for 80-90% of names and only calls NamSor when uncertain. Pure Offline mode never touches the network."
            )
            
            namsor_api_key_input = ""
            if "Hybrid" in mode_choice:
                namsor_api_key_input = st.text_input(
                    "NamSor API Key (Optional Fallback)", 
                    type="password", 
                    placeholder="Enter NamSor API key...",
                    help="Obtain at namsor.com. 1,000 free calls/month. If left blank, unresolved names fall back gracefully to the offline detector."
                )

        with c_conf2:
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                offline_thresh_pct = st.slider(
                    "Offline Acceptance Threshold (%)",
                    min_value=80,
                    max_value=95,
                    value=int(DEFAULT_OFFLINE_THRESHOLD * 100),
                    step=5,
                    help="If the offline detector achieves this probability, it is accepted immediately to save NamSor quota. Names below this trigger NamSor."
                )
                offline_threshold = offline_thresh_pct / 100.0

            with s_col2:
                final_thresh_pct = st.slider(
                    "Final Acceptance Threshold (%)",
                    min_value=50,
                    max_value=90,
                    value=int(DEFAULT_CONFIDENCE_THRESHOLD * 100),
                    step=5,
                    help="Names below this threshold after all engines are classified as 'Unknown'."
                )
                final_threshold = final_thresh_pct / 100.0

        run_btn = st.button("Run Gender Inference Pipeline", type="primary", icon=":material/play_arrow:", width="stretch")

    # 2. Execution Logic
    if run_btn or 'gender_analysis_results' not in st.session_state:
        if run_btn:
            detector = gender_detector.Detector(case_sensitive=False) if HAS_GENDER_GUESSER else None
            gender_cache = load_gender_cache()
            
            progress_bar = st.progress(0, text="Extracting author names and locational context...")
            
            total_rows = len(df)
            parsed_authors = [] # list of dicts for author directory
            article_assessments = [] # list of dicts for article-level assessment
            unique_authors_seen = {} # full_name -> stats
            
            start_t = time.time()
            cache_hits_count = 0
            offline_hits_count = 0
            namsor_calls_count = 0
            
            for idx, row in df.reset_index().iterrows():
                title = str(row.get('Title', 'Untitled Record'))
                year = str(row.get('Publication Year', 'Unknown'))
                authors_str = str(row.get('Author', ''))
                country_loc, country_iso2, display_country = extract_article_country_info(row)
                
                if not authors_str or authors_str.strip() == '' or authors_str.lower() == 'nan':
                    continue

                raw_author_list = split_authors_string(authors_str)
                    
                article_authors = []
                for a_pos, full_a_name in enumerate(raw_author_list):
                    first_n, last_n, is_initial = extract_name_parts(full_a_name)
                    
                    if is_initial or not first_n:
                        res = {
                            'gender': 'unknown',
                            'probability': 0.0,
                            'reliable': False,
                            'engine': 'Initial / Abbreviated'
                        }
                    else:
                        active_key = namsor_api_key_input if "Hybrid" in mode_choice else ""
                        res, source_type = classify_author_gender_hybrid(
                            first_name=first_n,
                            last_name=last_n,
                            country_locale=country_loc,
                            country_iso2=country_iso2,
                            gender_cache=gender_cache,
                            detector=detector,
                            namsor_api_key=active_key,
                            offline_threshold=offline_threshold,
                            final_threshold=final_threshold
                        )
                        
                        if source_type == 'cache':
                            cache_hits_count += 1
                        elif source_type == 'offline':
                            offline_hits_count += 1
                        elif source_type == 'namsor':
                            namsor_calls_count += 1
                        elif source_type == 'namsor_error':
                            # Critical API error (Quota exceeded or invalid key)
                            # 1. Save cache so all successful queries are not lost
                            save_gender_cache(gender_cache)
                            progress_bar.empty()
                            
                            # 2. Store error diagnostic in session_state
                            st.session_state.gender_error = {
                                'title': 'NamSor API Quota / Authentication Error',
                                'message': res.get('error_msg', 'Quota exhausted or invalid API key.'),
                                'processed_articles': idx,
                                'total_articles': total_rows,
                                'processed_authors': len(parsed_authors)
                            }
                            
                            # 3. Store partial results so user does not lose work
                            if parsed_authors:
                                st.session_state.gender_analysis_results = {
                                    'authors_df': pd.DataFrame(parsed_authors),
                                    'articles_df': pd.DataFrame(article_assessments),
                                    'unique_authors': list(unique_authors_seen.values()),
                                    'duration': time.time() - start_t,
                                    'cache_hits': cache_hits_count,
                                    'offline_hits': offline_hits_count,
                                    'namsor_calls': namsor_calls_count,
                                    'quota_saved_pct': ((cache_hits_count + offline_hits_count) / len(parsed_authors) * 100) if parsed_authors else 100.0,
                                    'threshold': final_threshold,
                                    'is_partial': True
                                }
                            st.rerun()

                    a_record = {
                        'article_index': idx,
                        'article_title': title,
                        'year': year,
                        'full_name': full_a_name,
                        'first_name': first_n or '',
                        'last_name': last_n or '',
                        'country': display_country,
                        'country_iso2': country_iso2 or '',
                        'gender': res.get('gender', 'unknown'),
                        'probability': res.get('probability', 0.0),
                        'reliable': res.get('reliable', False),
                        'engine': res.get('engine', 'Unknown'),
                        'position': 'first' if a_pos == 0 else ('last' if a_pos == len(raw_author_list) - 1 else 'middle')
                    }
                    parsed_authors.append(a_record)
                    article_authors.append(a_record)
                    
                    if full_a_name not in unique_authors_seen:
                        unique_authors_seen[full_a_name] = a_record

                # Analyze article composition
                m_count = sum(1 for a in article_authors if a['gender'] == 'male' and a['reliable'])
                f_count = sum(1 for a in article_authors if a['gender'] == 'female' and a['reliable'])
                u_count = sum(1 for a in article_authors if a['gender'] == 'unknown' or not a['reliable'])
                tot_a = len(article_authors)
                
                first_g = article_authors[0]['gender'] if article_authors and article_authors[0]['reliable'] else 'unknown'
                last_g = article_authors[-1]['gender'] if article_authors and article_authors[-1]['reliable'] else 'unknown'
                
                # Composition category
                if tot_a == 0:
                    comp = "No Authors"
                elif tot_a == 1:
                    if m_count == 1:
                        comp = "Single Man"
                    elif f_count == 1:
                        comp = "Single Woman"
                    else:
                        comp = "Unknown / Unclassified"
                else:
                    if f_count > 0 and m_count == 0:
                        comp = "Multi-Author (Only Women)"
                    elif m_count > 0 and f_count == 0:
                        comp = "Multi-Author (Only Men)"
                    elif f_count > m_count:
                        comp = "Multi-Author (More Women)"
                    elif m_count > f_count:
                        comp = "Multi-Author (More Men)"
                    elif f_count == m_count and f_count > 0:
                        comp = "Multi-Author (Equal Gender)"
                    else:
                        comp = "Unknown / Unclassified"

                is_multi_author = (tot_a >= 2)

                article_assessments.append({
                    'article_index': idx,
                    'title': title,
                    'year': year,
                    'total_authors': tot_a,
                    'is_multi_author': is_multi_author,
                    'male_count': m_count,
                    'female_count': f_count,
                    'unknown_count': u_count,
                    'has_female': f_count > 0,
                    'has_male': m_count > 0,
                    'composition': comp,
                    'detailed_composition': comp,
                    'first_author_gender': first_g,
                    'last_author_gender': last_g,
                    'first_author_female': first_g == 'female',
                    'last_author_female': last_g == 'female',
                    'first_author_male': first_g == 'male',
                    'last_author_male': last_g == 'male',
                    'country': display_country
                })

                if idx % 15 == 0 or idx == total_rows - 1:
                    pct = (idx + 1) / total_rows
                    progress_bar.progress(pct, text=f"Analyzing article {idx+1}/{total_rows} ({pct:.0%})...")

            save_gender_cache(gender_cache)
            progress_bar.empty()
            
            # Clear error state on successful complete run
            if 'gender_error' in st.session_state:
                del st.session_state['gender_error']
            
            duration = time.time() - start_t
            total_eval = len(parsed_authors)
            quota_saved = ((cache_hits_count + offline_hits_count) / total_eval * 100) if total_eval > 0 else 100.0
            
            # Save results to session_state
            results_payload = {
                'authors_df': pd.DataFrame(parsed_authors),
                'articles_df': pd.DataFrame(article_assessments),
                'unique_authors': list(unique_authors_seen.values()),
                'duration': duration,
                'cache_hits': cache_hits_count,
                'offline_hits': offline_hits_count,
                'namsor_calls': namsor_calls_count,
                'quota_saved_pct': quota_saved,
                'threshold': final_threshold,
                'is_partial': False
            }
            st.session_state.gender_analysis_results = results_payload

            # Generate and save detailed audit log into active project's logs folder
            audit_log_text = generate_gender_audit_log(
                results_payload, 
                strategy_name=mode_choice, 
                offline_thresh=offline_threshold, 
                final_thresh=final_threshold
            )
            st.session_state.last_gender_audit_log = audit_log_text
            log_fname = f"gender_mapping_{get_timestamp_str()}.log"
            try:
                saved_log_path = save_project_file("logs", log_fname, audit_log_text)
                st.session_state.last_gender_log_path = saved_log_path
            except Exception:
                pass

            formatted_duration = format_duration(duration)
            st.toast(f"Gender Analysis Complete! Processed {total_eval} author instances in {formatted_duration}. Audit log saved to project logs!", icon="🎉")

    # If results exist in session_state, display the analytics dashboard
    if 'gender_analysis_results' not in st.session_state:
        st.info("👆 Click **'Run Gender Inference Pipeline'** above to compute gender distributions.")
        return

    res_data = st.session_state.gender_analysis_results
    authors_df = res_data['authors_df']
    articles_df = res_data['articles_df']
    unique_authors = res_data['unique_authors']
    
    if articles_df.empty:
        st.warning("No authors could be extracted from the dataset.")
        return

    # Ensure backwards compatibility for previously run sessions
    if 'total_authors' not in articles_df.columns:
        articles_df['total_authors'] = articles_df.apply(
            lambda r: int(r.get('male_count', 0) + r.get('female_count', 0) + r.get('unknown_count', 0)), axis=1
        )
    if 'is_multi_author' not in articles_df.columns:
        articles_df['is_multi_author'] = articles_df['total_authors'] >= 2
    if 'first_author_male' not in articles_df.columns:
        articles_df['first_author_male'] = articles_df['first_author_gender'] == 'male'
    if 'last_author_male' not in articles_df.columns:
        articles_df['last_author_male'] = articles_df['last_author_gender'] == 'male'
    if 'has_male' not in articles_df.columns:
        articles_df['has_male'] = articles_df['male_count'] > 0

    def derive_composition(r):
        tot_a = r.get('total_authors', 0)
        f_count = r.get('female_count', 0)
        m_count = r.get('male_count', 0)
        if tot_a == 0:
            return "No Authors"
        elif tot_a == 1:
            if m_count == 1:
                return "Single Man"
            elif f_count == 1:
                return "Single Woman"
            else:
                return "Unknown / Unclassified"
        else:
            # Multi-author papers
            if f_count > 0 and m_count == 0:
                return "Multi-Author (Only Women)"
            elif m_count > 0 and f_count == 0:
                return "Multi-Author (Only Men)"
            elif f_count > m_count:
                return "Multi-Author (More Women)"
            elif m_count > f_count:
                return "Multi-Author (More Men)"
            elif f_count == m_count and f_count > 0:
                return "Multi-Author (Equal Gender)"
            else:
                return "Unknown / Unclassified"

    articles_df['composition'] = articles_df.apply(derive_composition, axis=1)
    articles_df['detailed_composition'] = articles_df['composition']

    if authors_df.empty:
        st.warning("No authors could be extracted from the dataset.")
        return

    # Calculate Top-Level Demographic Metrics
    u_authors_df = pd.DataFrame(unique_authors)
    total_unique_authors = len(u_authors_df)
    
    male_unique = (u_authors_df['gender'] == 'male').sum()
    female_unique = (u_authors_df['gender'] == 'female').sum()
    unknown_unique = (u_authors_df['gender'] == 'unknown').sum()
    
    male_pct = (male_unique / total_unique_authors * 100) if total_unique_authors else 0
    female_pct = (female_unique / total_unique_authors * 100) if total_unique_authors else 0
    unknown_pct = (unknown_unique / total_unique_authors * 100) if total_unique_authors else 0
    
    total_articles_eval = len(articles_df)
    articles_with_female = articles_df['has_female'].sum()
    female_art_pct = (articles_with_female / total_articles_eval * 100) if total_articles_eval else 0

    # Quota Protection & Efficiency Summary Card
    formatted_duration_str = format_duration(res_data.get('duration', 0))
    st.markdown(f"""
    <div style="background-color: #F0FDF4; border: 1px solid #DCFCE7; border-left: 4px solid #16A34A; padding: 10px 16px; border-radius: 6px; margin-bottom: 15px; font-size: 13px;">
        <span style="font-weight: 700; color: #166534;">🛡️ NamSor API Quota Efficiency Report:</span>
        <b>{res_data['quota_saved_pct']:.1f}% of author queries resolved without consuming API credits!</b>
        <div style="color: #15803d; margin-top: 3px;">
            • <b>{res_data['cache_hits']:,}</b> Cache Hits &nbsp;|&nbsp; 
            • <b>{res_data['offline_hits']:,}</b> Offline High-Confidence Resolves (≥85%) &nbsp;|&nbsp; 
            • <b>{res_data['namsor_calls']:,}</b> NamSor API Calls &nbsp;|&nbsp; 
            • Completed in <b>{formatted_duration_str}</b>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 3. KPI Metrics Bar
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Unique Authors", f"{total_unique_authors:,}")
    m2.metric("Female Authors", f"{female_unique:,}", f"{female_pct:.1f}% of authors", delta_color="normal")
    m3.metric("Male Authors", f"{male_unique:,}", f"{male_pct:.1f}% of authors", delta_color="normal")
    m4.metric("Unclassified / Initials", f"{unknown_unique:,}", f"{unknown_pct:.1f}% unclassified", delta_color="off")
    m5.metric("Articles with ≥1 Woman", f"{articles_with_female:,}", f"{female_art_pct:.1f}% of papers", delta_color="normal")

    st.divider()

    # 4. Interactive Tabs Structure
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Demographic Distribution (RQ1)",
        "✂️ Career Progression & 'Scissors Effect'",
        "🧠 Thematic Profile (RQ2)",
        "📂 Author Directory & Exports"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Demographic Distribution (RQ1)
    # -------------------------------------------------------------------------
    with tab1:
        st.markdown("<h4 style='font-size:17px; font-weight:700; color:#1E293B;'>Gender Distribution & Authorship Composition</h4>", unsafe_allow_html=True)
        
        c_t1_left, c_t1_right = st.columns([1, 1], gap="medium")
        
        with c_t1_left:
            # Figure 5 Equivalent: Bar chart of unique authors
            fig_bar = go.Figure(go.Bar(
                x=['Male Authors', 'Female Authors', 'Unknown / Ambiguous'],
                y=[male_unique, female_unique, unknown_unique],
                marker_color=['#2563EB', '#EC4899', '#94A3B8'],
                text=[f"{male_unique:,} ({male_pct:.1f}%)", f"{female_unique:,} ({female_pct:.1f}%)", f"{unknown_unique:,} ({unknown_pct:.1f}%)"],
                textposition='auto',
                hovertemplate="<b>%{x}</b>: %{y:,} authors<extra></extra>"
            ))
            fig_bar.update_layout(
                title=dict(text="Figure 5: Absolute Number of Unique Authors by Gender Category", font=dict(size=14)),
                yaxis=dict(title="Number of Authors"),
                margin=dict(l=20, r=20, t=40, b=20),
                height=340
            )
            st.plotly_chart(fig_bar, width='stretch')
            st.caption("Counts unique individuals across the analyzed corpus.")

        with c_t1_right:
            # Authorship composition donut chart
            comp_counts = articles_df['composition'].value_counts()
            color_map = {
                'Single Man': '#1D4ED8',
                'Single Woman': '#DB2777',
                'Multi-Author (Only Men)': '#3B82F6',
                'Multi-Author (Only Women)': '#EC4899',
                'Multi-Author (More Men)': '#93C5FD',
                'Multi-Author (More Women)': '#F472B6',
                'Multi-Author (Equal Gender)': '#10B981',
                'Unknown / Unclassified': '#CBD5E1',
                'No Authors': '#94A3B8'
            }
            pie_title = "Authorship Composition by Gender & Team Structure"

            fig_pie = px.pie(
                names=comp_counts.index,
                values=comp_counts.values,
                hole=0.45,
                color=comp_counts.index,
                color_discrete_map=color_map,
                title=pie_title
            )
            fig_pie.update_traces(textinfo='percent', textposition='inside')
            fig_pie.update_layout(
                margin=dict(l=20, r=20, t=40, b=20), 
                height=420, 
                showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_pie, width='stretch')
            
            # Drill-down expander to inspect the composition
            with st.expander("🔍 Inspect Authorship Breakdown per Article"):
                st.markdown("""
                **Why might 'More Men than Women' or 'Equal' be 0% in your corpus?**
                If your corpus consists predominantly of single-authored papers or teams where all classified authors share the same gender (or co-authors are initials/unclassified), mixed categories naturally remain at 0.
                """)
                comp_summary = pd.DataFrame({
                    'Category': comp_counts.index,
                    'Articles': comp_counts.values,
                    'Percentage': (comp_counts.values / len(articles_df) * 100).round(1)
                })
                st.dataframe(comp_summary, hide_index=True, width='stretch')

        st.divider()

        # Figures 7, 8, 9 Equivalent: Temporal Evolution Over the Years
        st.markdown("<h4 style='font-size:16px; font-weight:700; color:#1E293B;'>Figures 7–9: Temporal Evolution of Authors by Gender</h4>", unsafe_allow_html=True)
        
        # Clean years
        articles_df['year_clean'] = pd.to_numeric(articles_df['year'].astype(str).str.extract(r'((?:18|19|20)\d{2})')[0], errors='coerce')
        valid_years_df = articles_df.dropna(subset=['year_clean']).copy()
        valid_years_df['year_clean'] = valid_years_df['year_clean'].astype(int)
        
        if not valid_years_df.empty:
            yearly_stats = valid_years_df.groupby('year_clean').agg(
                Male=('male_count', 'sum'),
                Female=('female_count', 'sum'),
                Unknown=('unknown_count', 'sum'),
                Articles=('title', 'count')
            ).reset_index()

            yearly_stats['Total_Authors'] = yearly_stats['Male'] + yearly_stats['Female'] + yearly_stats['Unknown']
            yearly_stats['Female_Pct'] = (yearly_stats['Female'] / yearly_stats['Total_Authors'] * 100).fillna(0)
            yearly_stats['Male_Pct'] = (yearly_stats['Male'] / yearly_stats['Total_Authors'] * 100).fillna(0)
            yearly_stats['Unknown_Pct'] = (yearly_stats['Unknown'] / yearly_stats['Total_Authors'] * 100).fillna(0)

            mode_toggle = st.radio("Display Format", ["Normalized Percentage Distribution (%)", "Absolute Counts (Number of Authors)"], horizontal=True)

            if "Percentage" in mode_toggle:
                fig_time = go.Figure()
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Female_Pct'], name='Female Authors (%)', marker_color='#EC4899'))
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Male_Pct'], name='Male Authors (%)', marker_color='#2563EB'))
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Unknown_Pct'], name='Unknown (%)', marker_color='#CBD5E1'))
                fig_time.update_layout(
                    barmode='stack',
                    yaxis=dict(title="Percentage (%)", range=[0, 100]),
                    xaxis=dict(title="Publication Year", dtick=1),
                    title="Figure 9: Normalized Gender Percentage Distribution Over Time",
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
            else:
                fig_time = go.Figure()
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Male'], name='Male Authors', marker_color='#2563EB'))
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Female'], name='Female Authors', marker_color='#EC4899'))
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Unknown'], name='Unknown Authors', marker_color='#CBD5E1'))
                fig_time.update_layout(
                    barmode='group',
                    yaxis=dict(title="Total Author Appearances"),
                    xaxis=dict(title="Publication Year", dtick=1),
                    title="Figures 7 & 8: Absolute Number of Author Appearances by Year",
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
            st.plotly_chart(fig_time, width='stretch')

    # -------------------------------------------------------------------------
    # TAB 2: Career Progression & The Scissors Effect
    # -------------------------------------------------------------------------
    with tab2:
        st.markdown("<h4 style='font-size:17px; font-weight:700; color:#1E293B;'>Figures 10 & 11: Mentee vs. Advisor Positions (The 'Scissors Effect')</h4>", unsafe_allow_html=True)
        
        st.markdown("""
        In scientific literature, the **First Author** is traditionally regarded as the mentee/primary researcher (e.g. PhD student, postdoc), 
        while the **Last Author** signifies the senior academic advisor or laboratory director.
        Comparing female participation across these two roles reveals structural progression bottlenecks:
        """)

        c_cp_top1, c_cp_top2 = st.columns([1, 1], gap="medium")
        with c_cp_top1:
            gender_target_view = st.selectbox(
                "Select Gender to Analyze:",
                ["Female Representation (Mentee vs. Advisor)", "Male Representation (Mentee vs. Advisor)", "Comparative Overview (Both Genders)"],
                help="Analyze career progression for female researchers, male researchers, or view both together."
            )
        with c_cp_top2:
            cohort_scope = st.radio(
                "Article Cohort Filter:",
                ["Multi-Author Articles Only (≥2 Authors) [Recommended]", "All Articles (Includes Single-Author)"],
                horizontal=True,
                help="Single-author papers have identical First and Last author (the sole author). Multi-author papers isolate authentic Mentee (First Author) vs. Senior Advisor (Last Author) dynamics."
            )

        # Filter valid years
        analysis_df = valid_years_df.copy()
        if "Multi-Author" in cohort_scope:
            analysis_df = analysis_df[analysis_df['is_multi_author']].copy()
            if analysis_df.empty:
                st.warning("No multi-author articles found in the dataset with valid publication years.")
                return
            st.caption(f"Analyzing **{len(analysis_df):,}** multi-author articles across {analysis_df['year_clean'].nunique()} distinct years.")
        else:
            single_count = (analysis_df['is_multi_author'] == False).sum()
            st.caption(f"Analyzing all **{len(analysis_df):,}** articles (including **{single_count}** single-author publications where first author == last author).")

        if not analysis_df.empty:
            year_role_stats = analysis_df.groupby('year_clean').agg(
                Total_Papers=('title', 'count'),
                First_Female=('first_author_female', 'sum'),
                Last_Female=('last_author_female', 'sum'),
                First_Male=('first_author_male', 'sum'),
                Last_Male=('last_author_male', 'sum')
            ).reset_index()

            year_role_stats['First_Female_Pct'] = (year_role_stats['First_Female'] / year_role_stats['Total_Papers'] * 100).fillna(0)
            year_role_stats['Last_Female_Pct'] = (year_role_stats['Last_Female'] / year_role_stats['Total_Papers'] * 100).fillna(0)
            year_role_stats['First_Male_Pct'] = (year_role_stats['First_Male'] / year_role_stats['Total_Papers'] * 100).fillna(0)
            year_role_stats['Last_Male_Pct'] = (year_role_stats['Last_Male'] / year_role_stats['Total_Papers'] * 100).fillna(0)

            fig_scissors = go.Figure()
            
            if "Female" in gender_target_view or "Comparative" in gender_target_view:
                fig_scissors.add_trace(go.Scatter(
                    x=year_role_stats['year_clean'], 
                    y=year_role_stats['First_Female_Pct'],
                    mode='lines+markers',
                    name='Female First Author % (Mentee)',
                    line=dict(color='#EC4899', width=3),
                    marker=dict(size=7)
                ))
                fig_scissors.add_trace(go.Scatter(
                    x=year_role_stats['year_clean'], 
                    y=year_role_stats['Last_Female_Pct'],
                    mode='lines+markers',
                    name='Female Last Author % (Advisor)',
                    line=dict(color='#8B5CF6', width=3, dash='dash'),
                    marker=dict(size=7)
                ))

            if "Male" in gender_target_view or "Comparative" in gender_target_view:
                fig_scissors.add_trace(go.Scatter(
                    x=year_role_stats['year_clean'], 
                    y=year_role_stats['First_Male_Pct'],
                    mode='lines+markers',
                    name='Male First Author % (Mentee)',
                    line=dict(color='#2563EB', width=3),
                    marker=dict(size=7)
                ))
                fig_scissors.add_trace(go.Scatter(
                    x=year_role_stats['year_clean'], 
                    y=year_role_stats['Last_Male_Pct'],
                    mode='lines+markers',
                    name='Male Last Author % (Advisor)',
                    line=dict(color='#0284C7', width=3, dash='dash'),
                    marker=dict(size=7)
                ))

            max_y = max(
                50,
                year_role_stats['First_Female_Pct'].max() + 10 if "Female" in gender_target_view else 0,
                year_role_stats['First_Male_Pct'].max() + 10 if "Male" in gender_target_view else 0,
                100 if "Comparative" in gender_target_view else 50
            )

            fig_scissors.update_layout(
                title=f"Career Progression & Scissors Effect: First vs. Last Author Representation Over Time ({gender_target_view})",
                xaxis=dict(title="Publication Year", dtick=1),
                yaxis=dict(title="% Author Participation", range=[0, min(100, max_y)]),
                height=440,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig_scissors, width='stretch')

            avg_f_first = year_role_stats['First_Female_Pct'].mean()
            avg_f_last = year_role_stats['Last_Female_Pct'].mean()
            gap_f = avg_f_first - avg_f_last

            avg_m_first = year_role_stats['First_Male_Pct'].mean()
            avg_m_last = year_role_stats['Last_Male_Pct'].mean()
            gap_m = avg_m_first - avg_m_last

            if "Female" in gender_target_view:
                st.info(f"📌 **Key Finding (Female Cohort):** Female First Authors average **{avg_f_first:.1f}%**, whereas Female Last Authors (Senior Advisors) average **{avg_f_last:.1f}%** (a progression gap of **{gap_f:.1f} percentage points**).")
            elif "Male" in gender_target_view:
                st.info(f"📌 **Key Finding (Male Cohort):** Male First Authors average **{avg_m_first:.1f}%**, whereas Male Last Authors (Senior Advisors) average **{avg_m_last:.1f}%** (a difference of **{gap_m:.1f} percentage points**).")
            else:
                st.info(f"📌 **Comparative Findings:** Female first author avg: **{avg_f_first:.1f}%** (last: **{avg_f_last:.1f}%** | gap: **{gap_f:.1f} pp**). Male first author avg: **{avg_m_first:.1f}%** (last: **{avg_m_last:.1f}%** | gap: **{gap_m:.1f} pp**).")

    # -------------------------------------------------------------------------
    # TAB 3: Thematic Profile (RQ2)
    # -------------------------------------------------------------------------
    with tab3:
        st.markdown("<h4 style='font-size:17px; font-weight:700; color:#1E293B;'>Research Topics & Technological Focus by Gender</h4>", unsafe_allow_html=True)
        st.write("Examines the thematic focus and technological keywords in articles co-authored by women, men, or across the whole corpus.")

        c_th_top1, c_th_top2 = st.columns([1, 1])
        with c_th_top1:
            thematic_gender_sel = st.selectbox(
                "Filter Thematic Profile by Author Gender:",
                ["Articles with Female Authorship", "Articles with Male Authorship", "All Analyzed Articles"],
                help="Switch between female and male authorship cohorts to compare research priorities."
            )

        # Extract articles based on selection
        if "Female" in thematic_gender_sel:
            target_indices = articles_df[articles_df['has_female']]['article_index']
            kw_bar_color = ['#EC4899']
            chart_subtitle = "Articles with Female Authorship"
        elif "Male" in thematic_gender_sel:
            target_indices = articles_df[articles_df['has_male']]['article_index']
            kw_bar_color = ['#2563EB']
            chart_subtitle = "Articles with Male Authorship"
        else:
            target_indices = articles_df['article_index']
            kw_bar_color = ['#38BDF8']
            chart_subtitle = "All Analyzed Articles"

        selected_articles_df = df.loc[target_indices]
        
        all_keywords = []
        for kw_val in selected_articles_df.get('Keywords', []):
            if pd.notna(kw_val) and str(kw_val).strip():
                for kw in re.split(r'[;,]', str(kw_val)):
                    cleaned_kw = kw.strip().title()
                    if len(cleaned_kw) > 2:
                        all_keywords.append(cleaned_kw)

        if all_keywords:
            kw_counter = Counter(all_keywords)
            top20_kw = kw_counter.most_common(20)
            
            c_kw_left, c_kw_right = st.columns([1.2, 1], gap="medium")
            
            with c_kw_left:
                kw_df = pd.DataFrame(top20_kw, columns=['Topic / Keyword', 'Occurrences']).sort_values('Occurrences', ascending=True)
                fig_kw = px.bar(
                    kw_df,
                    x='Occurrences',
                    y='Topic / Keyword',
                    orientation='h',
                    title=f"Top 20 Main Topics ({chart_subtitle})",
                    color_discrete_sequence=kw_bar_color
                )
                fig_kw.update_layout(height=480, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_kw, width='stretch')

            with c_kw_right:
                st.markdown(f"<div style='font-weight:700; margin-bottom:6px;'>Thematic Word Cloud ({chart_subtitle})</div>", unsafe_allow_html=True)
                if HAS_WORDCLOUD:
                    colormap_choice = 'PuRd' if "Female" in thematic_gender_sel else ('Blues' if "Male" in thematic_gender_sel else 'cool')
                    wc = WordCloud(
                        width=600, 
                        height=440, 
                        background_color='white', 
                        colormap=colormap_choice, 
                        max_words=60
                    ).generate_from_frequencies(dict(top20_kw))
                    
                    fig_wc, ax = plt.subplots(figsize=(6, 4.4))
                    ax.imshow(wc, interpolation='bilinear')
                    ax.axis('off')
                    plt.tight_layout(pad=0)
                    st.pyplot(fig_wc)
                else:
                    st.dataframe(pd.DataFrame(top20_kw, columns=['Keyword', 'Frequency']), height=420)
        else:
            st.info(f"No populated keywords found for {chart_subtitle.lower()} to generate topic rankings.")

    # -------------------------------------------------------------------------
    # TAB 4: Author Directory & Exports
    # -------------------------------------------------------------------------
    with tab4:
        st.markdown("<h4 style='font-size:17px; font-weight:700; color:#1E293B;'>Curated Author Directory & Reproducible Exports</h4>", unsafe_allow_html=True)
        st.write("Browse all evaluated authors, inspect classification engines, and export structured datasets for downstream analysis.")

        c_exp_top1, c_exp_top2 = st.columns([2, 1])
        with c_exp_top1:
            search_q = st.text_input("Search author directory by name or first name:", placeholder="Type a name to filter...")
        with c_exp_top2:
            gender_filter = st.selectbox("Filter Gender", ["All", "female", "male", "unknown"])

        display_authors = authors_df.copy()
        if search_q.strip():
            display_authors = display_authors[
                display_authors['full_name'].str.contains(search_q, case=False, na=False) |
                display_authors['first_name'].str.contains(search_q, case=False, na=False)
            ]
        if gender_filter != "All":
            display_authors = display_authors[display_authors['gender'] == gender_filter]

        st.dataframe(
            display_authors[['full_name', 'first_name', 'gender', 'probability', 'reliable', 'country', 'engine', 'position', 'year', 'article_title']],
            hide_index=True,
            height=300,
            width="stretch"
        )

        st.markdown("<h5 style='font-size:15px; font-weight:700; margin-top:15px;'><i class='bi bi-download' style='color:#697aa2;'></i> Export Research Datasets & Audit Trail</h5>", unsafe_allow_html=True)
        render_project_saved_notice("exports", "Author records, gender metrics, caches, and audit logs are automatically saved to your active project workspace.")
        
        exp_col1, exp_col2, exp_col3, exp_col4, exp_col5, exp_col6 = st.columns(6, gap="small")
        
        with exp_col1:
            csv_authors = display_authors.to_csv(index=False).encode('utf-8-sig')
            fn_authors = format_timestamped_filename("Authors_Assessed.csv")
            try: save_project_file("exports", fn_authors, csv_authors, mode="wb")
            except Exception: pass
            st.download_button("Authors (.csv)", data=csv_authors, file_name=fn_authors, icon=":material/download:", width="stretch")
            
        with exp_col2:
            csv_articles = articles_df.to_csv(index=False).encode('utf-8-sig')
            fn_articles = format_timestamped_filename("LibAssessed_Gender.csv")
            try: save_project_file("exports", fn_articles, csv_articles, mode="wb")
            except Exception: pass
            st.download_button("Articles (.csv)", data=csv_articles, file_name=fn_articles, icon=":material/download:", width="stretch")

        with exp_col3:
            if not valid_years_df.empty:
                csv_yearly = yearly_stats.to_csv(index=False).encode('utf-8-sig')
                fn_yearly = format_timestamped_filename("Gender_Yearly_Report.csv")
                try: save_project_file("exports", fn_yearly, csv_yearly, mode="wb")
                except Exception: pass
                st.download_button("Yearly (.csv)", data=csv_yearly, file_name=fn_yearly, icon=":material/download:", width="stretch")
            else:
                st.button("Yearly (.csv)", disabled=True, width="stretch")

        with exp_col4:
            if gender_cache:
                cache_json = json.dumps(gender_cache, ensure_ascii=False, indent=2).encode('utf-8')
                fn_cache = format_timestamped_filename("gender_cache.json")
                try: save_project_file("sessions", fn_cache, cache_json, mode="wb")
                except Exception: pass
                st.download_button("Cache (.json)", data=cache_json, file_name=fn_cache, icon=":material/download:", width="stretch")
            else:
                st.button("Cache (.json)", disabled=True, width="stretch")

        with exp_col5:
            audit_text = st.session_state.get('last_gender_audit_log', '')
            if audit_text:
                fn_log = format_timestamped_filename("gender_audit_report.log")
                st.download_button("Audit Log", data=audit_text.encode('utf-8'), file_name=fn_log, icon=":material/description:", width="stretch")
            else:
                st.button("Audit Log", disabled=True, width="stretch", icon=":material/description:")

        with exp_col6:
            if st.button("Open Folder", icon=":material/folder_open:", width="stretch", key="btn_open_gender_folder", help="Opens active project folder"):
                open_project_folder("exports")
