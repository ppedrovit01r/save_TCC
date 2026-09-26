import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import time
import datetime
import re
import requests
from collections import defaultdict, Counter
import io
import base64
from utils.formatters import format_duration
from utils.project_manager import get_global_cache_dir, save_project_file, format_timestamped_filename, get_active_project_name, get_timestamp_str, open_project_folder, save_master_dataset
from utils.exports import render_project_saved_notice, _save_export_on_click, _download_button

from urllib.parse import quote

import unicodedata
# Try importing unidecode
try:
    from unidecode import unidecode
    HAS_UNIDECODE = True
except ImportError:
    HAS_UNIDECODE = False

# Try importing wordcloud
try:
    from wordcloud import WordCloud
    import matplotlib.pyplot as plt
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False

import functools
CACHE_DIR = os.path.join("utils", "cache")
CACHE_FILE = os.path.join(CACHE_DIR, "gender_cache.json")
CACHE_INIT_FILE = os.path.join(CACHE_DIR, "gender_cache_init.json")
OA_AUTHORS_CACHE_FILE = os.path.join(CACHE_DIR, "openalex_authors_cache.json")
OA_AUTHOR_ENTITIES_CACHE_FILE = os.path.join(CACHE_DIR, "openalex_author_entities_cache.json")
ORCID_CACHE_FILE = os.path.join(CACHE_DIR, "orcid_authors_cache.json")
SS_AUTHORS_CACHE_FILE = os.path.join(CACHE_DIR, "semanticscholar_authors_cache.json")
DEFAULT_CONFIDENCE_THRESHOLD = 0.75

# In-memory singletons to avoid repeated disk reads
_GENDER_CACHE = None
_OA_AUTHORS_CACHE = None
_OA_AUTHOR_ENTITIES_CACHE = None
_ORCID_CACHE = None
_SS_AUTHORS_CACHE = None

# Country data mapping (maps aliases to ISO-2 for NamSor geo-localization)
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
    global _GENDER_CACHE
    if _GENDER_CACHE is not None:
        return _GENDER_CACHE

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

    _GENDER_CACHE = cache
    return cache

def save_gender_cache(cache: dict):
    global _GENDER_CACHE
    _GENDER_CACHE = cache
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def generate_gender_audit_log(results_dict: dict, strategy_name: str, final_thresh: float, **kwargs) -> str:
    """Generates a detailed, comprehensive text audit log for gender inference execution."""
    authors_df = results_dict.get('authors_df', pd.DataFrame())
    articles_df = results_dict.get('articles_df', pd.DataFrame())
    duration = results_dict.get('duration', 0.0)
    cache_hits = results_dict.get('cache_hits', 0)
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
        f"Acceptance Threshold:     {int(final_thresh * 100)}%",
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
    ]
    cache_misses = results_dict.get('cache_misses', 0)
    
    if 'Local Cache' in strategy_name or (namsor_calls == 0 and cache_misses > 0):
        log_lines.extend([
            f"• Verified Persistent Cache Hits:  {cache_hits:,} author mentions ({((cache_hits/total_authors)*100 if total_authors else 0):.1f}%)",
            f"• Not Found in Cache (Unknown):    {cache_misses:,} author mentions ({((cache_misses/total_authors)*100 if total_authors else 0):.1f}%)",
            f"• External Network API Requests:   0 calls (Pure Offline Mode)",
            f"• Cache Resolution Rate:           {((cache_hits/total_authors)*100 if total_authors else 0):.1f}% of names resolved from local cache",
            f"• Classification Engine Breakdown:",
        ])
    else:
        log_lines.extend([
            f"• Persistent Cache Hits (Free):    {cache_hits:,} names ({((cache_hits/total_authors)*100 if total_authors else 0):.1f}%)",
            f"• External NamSor API Requests:    {namsor_calls:,} calls ({((namsor_calls/total_authors)*100 if total_authors else 0):.1f}%)",
            f"• Quota Savings Efficiency:        {quota_saved:.1f}% free resolutions without network API consumption",
            f"• Classification Engine Breakdown:",
        ])
    
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
    ])

    disambiguated_count = results_dict.get('disambiguated_count', 0)
    disambiguation_log = results_dict.get('disambiguation_log', [])
    if disambiguated_count > 0:
        log_lines.extend([
            "",
            "--------------------------------------------------------------------------------",
            "5. AUTHOR NAME STANDARDIZATION & DISAMBIGUATION (OPENALEX)",
            "--------------------------------------------------------------------------------",
            f"• Authors Disambiguated from Initials to Full Names: {disambiguated_count:,}",
            "• Disambiguation Engine: OpenAlex Knowledge Graph Entity Disambiguation",
            "• Disambiguated Author Log:"
        ])
        for entry in disambiguation_log[:30]:
            log_lines.append(f"    - {entry}")
        if len(disambiguation_log) > 30:
            log_lines.append(f"    - ... and {len(disambiguation_log) - 30} more disambiguated authors")

    log_lines.extend([
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
# Academic degrees, titles, and credentials that should not be treated as author names
ACADEMIC_DEGREES_AND_TITLES = {
    'phd', 'ph.d', 'ph.d.', 'md', 'm.d', 'm.d.', 'ms', 'm.s', 'm.s.', 'msc', 'm.sc', 'm.sc.', 
    'ma', 'm.a', 'm.a.', 'ba', 'b.a', 'b.a.', 'bs', 'b.s', 'b.s.', 'bsc', 'b.sc', 'b.sc.',
    'mph', 'm.p.h', 'm.p.h.', 'pharmd', 'pharm.d', 'pharm.d.', 'dphil', 'd.phil', 'd.phil.', 
    'edd', 'ed.d', 'ed.d.', 'dvm', 'd.v.m', 'd.v.m.', 'dds', 'd.d.s', 'd.d.s.', 'do', 'd.o', 'd.o.',
    'rn', 'r.n', 'r.n.', 'mbbs', 'm.b.b.s', 'm.b.b.s.', 'frcp', 'frcs', 'facs', 'scd', 'sc.d', 'sc.d.',
    'jd', 'j.d', 'j.d.', 'llm', 'll.m', 'll.m.', 'llb', 'll.b', 'll.b.', 'psyd', 'psy.d', 'psy.d.',
    'obe', 'cbe', 'mbe', 'kbe', 'frs', 'fmedsci', 'dr', 'dr.', 'prof', 'prof.', 'professor'
}

def is_degree_token(t: str) -> bool:
    """Returns True if a token represents an academic credential or honorific rather than an author name."""
    if not t or not isinstance(t, str):
        return False
    clean = t.strip().lower().rstrip(' ,;.')
    return clean in ACADEMIC_DEGREES_AND_TITLES or t.strip().lower() in ACADEMIC_DEGREES_AND_TITLES

def strip_academic_degrees(s: str) -> str:
    """Removes trailing or leading academic degrees (e.g. ', PhD', ', MD', 'Prof.') from an author string."""
    if not s or not isinstance(s, str):
        return ""
    deg_list = [
        r'ph\.?d\.?', r'm\.?d\.?', r'm\.?s\.?', r'm\.?sc\.?', r'm\.?a\.?',
        r'b\.?a\.?', r'b\.?s\.?', r'b\.?sc\.?', r'm\.?p\.?h\.?', r'pharm\.?d\.?',
        r'd\.?phil\.?', r'ed\.?d\.?', r'd\.?v\.?m\.?', r'd\.?d\.?s\.?', r'd\.?o\.?',
        r'r\.?n\.?', r'm\.?b\.?b\.?s\.?', r'frcp', r'frcs', r'facs', r'sc\.?d\.?',
        r'j\.?d\.?', r'll\.?m\.?', r'll\.?b\.?', r'psy\.?d\.?', r'obe', r'cbe', r'mbe',
        r'kbe', r'frs', r'fmedsci', r'dr\.?', r'prof(?:essor)?\.?'
    ]
    pattern = r'(?:^|,\s*|\s+)(?:' + '|'.join(deg_list) + r')(?=\b|[,\s;.]|$)'
    prev = None
    curr = s.strip()
    while curr != prev:
        prev = curr
        curr = re.sub(pattern, '', curr, flags=re.IGNORECASE).strip(" ,;.")
    return curr

def contains_non_latin(s: str) -> bool:
    """Returns True if the string contains non-Latin alphabetic characters (e.g. CJK, Cyrillic, Greek, Arabic)."""
    if not s or not isinstance(s, str):
        return False
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith('L'):
            name = unicodedata.name(ch, '')
            if not name.startswith('LATIN'):
                return True
    return False

def romanize_text(s: str) -> str:
    """
    Transliterates non-Latin scripts (Chinese, Cyrillic, Greek, Arabic, Japanese, Korean)
    into Latin characters while preserving European Latin diacritics (accents/tildes/cedillas).
    """
    if not s or not isinstance(s, str):
        return ""
    if not contains_non_latin(s):
        return s
    if HAS_UNIDECODE:
        res = unidecode(s)
        # Normalize whitespace around delimiters and redundant multiple spaces
        res = re.sub(r'\s*,\s*', ', ', res)
        res = re.sub(r'\s*;\s*', '; ', res)
        res = re.sub(r'[ \t]+', ' ', res).strip()
        return res
    return s

@functools.lru_cache(maxsize=32768)
def clean_author_text(s: str) -> str:
    """
    Cleans author strings by fixing broken character encodings (e.g. \\ufffd, \\x92, smart quotes)
    into standard apostrophes, removing quotation marks, stripping academic degrees,
    romanizing non-Latin scripts (e.g. Chinese 峰 王 -> Feng Wang), and trimming whitespace.
    Preserves trailing period on initials like 'K.' or 'I.'.
    """
    if not s or pd.isna(s) or not isinstance(s, str):
        return ""
    cleaned = re.sub(r'[\ufffd\x92\u2019\u2018`´]', "'", str(s))
    cleaned = re.sub(r'["“”]', '', cleaned)
    cleaned = strip_academic_degrees(cleaned)
    if contains_non_latin(cleaned):
        cleaned = romanize_text(cleaned)
    return cleaned.strip(" ,;-'\"")

@functools.lru_cache(maxsize=32768)
def norm_surname(s: str) -> str:
    """
    Normalizes a surname for comparison by removing all non-alphanumeric characters (apostrophes, hyphens, spaces)
    and converting to lowercase.
    E.g. "O'Neill" -> "oneill", "O-Neill" -> "oneill", "De La Cruz" -> "delacruz"
    """
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

def split_authors_string(authors_str: str) -> list:
    """
    Splits an authors string into individual author strings robustly.
    Filters out academic degrees and credentials like 'PhD' or 'MD' so they are never recognized as authors.
    """
    if not authors_str or pd.isna(authors_str) or not isinstance(authors_str, str):
        return []
        
    s = re.sub(r'[\ufffd\x92\u2019\u2018`´]', "'", str(authors_str).strip())
    s = re.sub(r'["“”]', '', s).strip()
    INVALID_AUTHOR_TOKENS = {'nan', '<na>', 'none', 'null', 'n/a', 'unknown', 'et al', 'et al.', 'anonymous', ''}
    if not s or s.lower() in INVALID_AUTHOR_TOKENS:
        return []

    def _filter_valid(author_list):
        out = []
        for a in author_list:
            if a and str(a).strip().lower() not in INVALID_AUTHOR_TOKENS and len(str(a).strip()) >= 2:
                out.append(str(a).strip())
        return list(dict.fromkeys(out))

    # 1. Semicolon separated
    if ';' in s:
        res = []
        for a in s.split(';'):
            c = clean_author_text(a)
            if c and not is_degree_token(c):
                res.append(c)
        return _filter_valid(res)

    # 2. 'and' separated
    if ' and ' in s.lower():
        parts = re.split(r'\s+and\s+', s, flags=re.IGNORECASE)
        if len(parts) > 1:
            res = []
            for p in parts:
                c = clean_author_text(p)
                if c and not is_degree_token(c):
                    res.append(c)
            return _filter_valid(res)

    # 3. Comma separated list of authors
    if ',' in s:
        raw_parts = [p.strip() for p in s.split(',') if p.strip()]
        # Filter out standalone degree tokens (e.g. "PhD", "MD")
        comma_parts = []
        for p in raw_parts:
            if is_degree_token(p):
                continue
            cleaned_p = clean_author_text(p)
            if cleaned_p and not is_degree_token(cleaned_p):
                comma_parts.append(cleaned_p)

        if not comma_parts:
            return []
        if len(comma_parts) == 1:
            return _filter_valid([comma_parts[0]])
        if len(comma_parts) == 2:
            p0_words = comma_parts[0].split()
            p1_words = comma_parts[1].split()
            if len(p0_words) >= 2 and len(p1_words) >= 2:
                return _filter_valid(comma_parts)
            return _filter_valid([f"{comma_parts[0]}, {comma_parts[1]}"])
        else:
            multi_word_parts = sum(1 for p in comma_parts if len(p.split()) >= 2)
            if multi_word_parts >= len(comma_parts) - 1:
                return _filter_valid(comma_parts)
            elif len(comma_parts) % 2 == 0:
                paired = []
                for i in range(0, len(comma_parts), 2):
                    paired.append(f"{comma_parts[i]}, {comma_parts[i+1]}")
                return _filter_valid(paired)
            else:
                return _filter_valid(comma_parts)

    clean_single = clean_author_text(s)
    return _filter_valid([clean_single]) if clean_single and not is_degree_token(clean_single) else []

@functools.lru_cache(maxsize=16384)
def is_initial_token(t: str, is_mixed_case: bool = True) -> bool:
    """
    Determines whether a token represents initials (e.g. 'J', 'J.', 'JB', 'RSK', 'A.B.').
    """
    clean = t.strip().rstrip('.')
    if not clean:
        return False
    # Single letter (e.g. 'J', 'J.', 'A', 'A.')
    if len(clean) == 1 and clean[0].isupper():
        return True
    # Dotted initials (e.g. 'J.B.', 'R.S.K.', 'A.B.')
    if '.' in t and clean.isupper() and len(clean) <= 4:
        return True
    # If the author string contains lowercase letters (like 'Cross JB', 'Kihlberg J', 'da Silva AB'):
    # Any all-uppercase token of 1 to 4 letters is an initials token!
    if is_mixed_case:
        if 2 <= len(clean) <= 4 and clean.isupper():
            return True
    else:
        # All-caps string (e.g. 'CROSS JB', 'VIJAYAN RSK')
        if 2 <= len(clean) <= 4 and clean.isupper() and not any(v in clean for v in 'AEIOUY'):
            return True
        if len(clean) <= 2 and clean.isupper():
            return True
    return False

@functools.lru_cache(maxsize=32768)
def extract_name_parts(full_name: str) -> tuple:
    """
    Extracts first name and surname robustly across all academic formats:
    - PubMed/MEDLINE Inverted: 'Surname Initials' (e.g. 'Vijayan RSK', 'Kihlberg J', 'Cross JB', 'Poongavanam V', 'Cosic K')
    - Western Format: 'FirstName Middle... Surname' (e.g. 'Christhian Henrique Gomes Fonseca', 'Jan Kihlberg')
    - Dotted / Leading Initials: 'Initials Surname' (e.g. 'J. B. Cross', 'RSK Vijayan', 'K Cosic')
    - Comma Formats: 'LastName, FirstName Middle' or 'LastName, Initials' (e.g. 'Smith, John' / 'Santos, I.')
    
    Returns (cleaned_first_name, cleaned_last_name, is_initial).
    """
    if not full_name or pd.isna(full_name) or not isinstance(full_name, str):
        return None, None, True
        
    cleaned = clean_author_text(str(full_name))
    clean_name = re.sub(r'\(.*?\)|\[.*?\]|<.*?>', '', cleaned).strip()
    clean_name = clean_name.strip(" '\"")
    if not clean_name or clean_name.lower() == 'nan' or is_degree_token(clean_name):
        return None, None, True

    is_mixed = any(c.islower() for c in clean_name)

    # Case 1: Comma format: "LastName, FirstName Middle" or "LastName, Initials"
    if ',' in clean_name:
        parts = [strip_academic_degrees(p.strip()) for p in clean_name.split(',') if strip_academic_degrees(p.strip()) and not is_degree_token(p)]
        if not parts:
            return None, None, True
        last_part = parts[0]
        if len(parts) > 1:
            first_words = parts[1].split()
            first_part = first_words[0] if first_words else None
        else:
            first_part = None

        if not first_part:
            return None, last_part.title(), True

        is_init = is_initial_token(first_part, is_mixed) or len(first_part.rstrip('.')) <= 1
        return first_part.strip().title(), last_part.strip().title(), is_init

    parts = clean_name.split()
    if not parts:
        return None, None, True
    if len(parts) == 1:
        return parts[0].title(), '', is_initial_token(parts[0], is_mixed)

    # Case 2: Trailing initials (PubMed/NLM style): e.g. 'Vijayan RSK', 'Kihlberg J', 'Cross JB', 'Poongavanam V', 'da Silva AB'
    trailing_initials = []
    idx = len(parts) - 1
    while idx >= 1 and is_initial_token(parts[idx], is_mixed):
        trailing_initials.insert(0, parts[idx])
        idx -= 1

    if trailing_initials:
        last_part = ' '.join(parts[:idx+1])
        first_part = ' '.join(trailing_initials)
        return first_part, last_part.title(), True

    # Case 3: Leading initials: e.g. 'J. B. Cross', 'RSK Vijayan', 'J. Doe'
    leading_initials = []
    idx = 0
    while idx < len(parts) - 1 and is_initial_token(parts[idx], is_mixed):
        leading_initials.append(parts[idx])
        idx += 1

    if leading_initials:
        first_part = ' '.join(leading_initials)
        last_part = ' '.join(parts[idx:])
        return first_part, last_part.title(), True

    # Case 4: Standard Western: 'FirstName Middle... LastName' (e.g. 'Christhian Henrique Gomes Fonseca')
    first_part = parts[0]
    last_part = parts[-1]
    
    # Handle hyphenated first names (e.g. 'Marie-Claire' -> 'Marie')
    if '-' in first_part:
        first_part = first_part.split('-')[0].strip()

    return first_part.title(), last_part.title(), False

@functools.lru_cache(maxsize=32768)
def author_has_initials(author_str: str) -> bool:
    """
    Returns True if an author string is missing, contains initials instead of full given names,
    or contains un-romanized non-Latin characters (e.g. Chinese ideographs).
    """
    if not author_str or pd.isna(author_str) or not isinstance(author_str, str):
        return True
    s = author_str.strip()
    if not s or s.lower() in ['nan', 'none']:
        return True
    if contains_non_latin(s):
        return True
    
    authors = split_authors_string(s)
    if not authors:
        return True
    for a in authors:
        _, _, is_init = extract_name_parts(a)
        if is_init:
            return True
    return False

def standardize_author_name(author_token: str) -> str:
    """
    Standardizes an individual author name to natural Western format:
    Always First Name / Initials first, followed by Surname.
    Handles:
    - Trailing Initials (PubMed/NLM): 'Cosic K' -> 'K Cosic', 'Denton F' -> 'F Denton', 'O'Neill DW' -> 'DW O'Neill'
    - Comma Formats: 'Cosic, K.' -> 'K. Cosic', 'Smith, John' -> 'John Smith', 'Fonseca, Christhian Henrique Gomes' -> 'Christhian Henrique Gomes Fonseca'
    - Leading Initials: 'K Cosic', 'F Denton', 'J. B. Cross' -> preserved as-is
    - Full Western Names: 'Felix Creutzig', 'Christhian Henrique Gomes Fonseca' -> preserved as-is
    - Academic degrees like ', PhD' are stripped.
    """
    if not author_token or pd.isna(author_token) or not isinstance(author_token, str):
        return ""
    
    cleaned = clean_author_text(author_token)
    if not cleaned or is_degree_token(cleaned) or cleaned.lower() == 'nan':
        return ""
    
    # Check if manual override exists for this exact token or cleaned token
    try:
        from utils.project_manager import get_manual_author_overrides
        overrides = get_manual_author_overrides()
        if cleaned in overrides:
            return overrides[cleaned]
        if author_token.strip() in overrides:
            return overrides[author_token.strip()]
    except Exception:
        pass
        
    # Comma format: "Smith, John" or "Fonseca, Christhian Henrique Gomes" or "Cosic, K."
    if ',' in cleaned:
        raw_parts = [strip_academic_degrees(p.strip()) for p in cleaned.split(',') if strip_academic_degrees(p.strip()) and not is_degree_token(p)]
        if not raw_parts:
            return ""
        if len(raw_parts) == 1:
            return raw_parts[0]
        last_part = raw_parts[0]
        first_part = ' '.join(raw_parts[1:])
        return f"{first_part} {last_part}".strip()

    fn, ln, is_init = extract_name_parts(cleaned)
    
    if not fn and not ln:
        return cleaned
    if not fn:
        return ln
    if not ln:
        return fn

    # Trailing initials format (e.g. "Cosic K", "Denton F", "O'Neill DW"):
    # extract_name_parts gave fn="K", ln="Cosic" -> flip to "K Cosic"
    parts = cleaned.split()
    is_mixed = any(c.islower() for c in cleaned)
    if len(parts) >= 2 and is_initial_token(parts[-1], is_mixed):
        return f"{fn} {ln}".strip()
        
    # If already Western format with first name first (e.g. "Felix Creutzig", "Christhian Henrique Gomes Fonseca", "K Cosic"):
    # Keep cleaned directly so middle names and punctuation are preserved intact
    return cleaned

def standardize_author_string(authors_str: str) -> str:
    """
    Takes an author string and returns all authors in Western format separated by '; '.
    Guarantees first name / initials always appear first for every author and non-Latin scripts (e.g. Chinese) are romanized.
    """
    if not authors_str or pd.isna(authors_str) or not isinstance(authors_str, str):
        return ""
    if contains_non_latin(authors_str):
        authors_str = romanize_text(authors_str)
    tokens = split_authors_string(authors_str)
    std_tokens = []
    for t in tokens:
        std_name = standardize_author_name(t)
        if std_name and not is_degree_token(std_name):
            std_tokens.append(std_name)
    return "; ".join(std_tokens)


# -----------------------------------------------------------------------------
# OpenAlex, ORCID & Semantic Scholar Author Disambiguation Cache & Resolvers
# -----------------------------------------------------------------------------
def load_oa_authors_cache() -> dict:
    global _OA_AUTHORS_CACHE
    if _OA_AUTHORS_CACHE is not None:
        return _OA_AUTHORS_CACHE
    if os.path.exists(OA_AUTHORS_CACHE_FILE):
        try:
            with open(OA_AUTHORS_CACHE_FILE, "r", encoding="utf-8") as f:
                _OA_AUTHORS_CACHE = json.load(f)
                return _OA_AUTHORS_CACHE
        except Exception:
            _OA_AUTHORS_CACHE = {}
    else:
        _OA_AUTHORS_CACHE = {}
    return _OA_AUTHORS_CACHE

def save_oa_authors_cache(cache: dict):
    global _OA_AUTHORS_CACHE
    _OA_AUTHORS_CACHE = cache
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(OA_AUTHORS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_oa_author_entities_cache() -> dict:
    global _OA_AUTHOR_ENTITIES_CACHE
    if _OA_AUTHOR_ENTITIES_CACHE is not None:
        return _OA_AUTHOR_ENTITIES_CACHE
    if os.path.exists(OA_AUTHOR_ENTITIES_CACHE_FILE):
        try:
            with open(OA_AUTHOR_ENTITIES_CACHE_FILE, "r", encoding="utf-8") as f:
                _OA_AUTHOR_ENTITIES_CACHE = json.load(f)
                return _OA_AUTHOR_ENTITIES_CACHE
        except Exception:
            _OA_AUTHOR_ENTITIES_CACHE = {}
    else:
        _OA_AUTHOR_ENTITIES_CACHE = {}
    return _OA_AUTHOR_ENTITIES_CACHE

def save_oa_author_entities_cache(cache: dict):
    global _OA_AUTHOR_ENTITIES_CACHE
    _OA_AUTHOR_ENTITIES_CACHE = cache
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(OA_AUTHOR_ENTITIES_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_orcid_cache() -> dict:
    global _ORCID_CACHE
    if _ORCID_CACHE is not None:
        return _ORCID_CACHE
    if os.path.exists(ORCID_CACHE_FILE):
        try:
            with open(ORCID_CACHE_FILE, "r", encoding="utf-8") as f:
                _ORCID_CACHE = json.load(f)
                return _ORCID_CACHE
        except Exception:
            _ORCID_CACHE = {}
    else:
        _ORCID_CACHE = {}
    return _ORCID_CACHE

def save_orcid_cache(cache: dict):
    global _ORCID_CACHE
    _ORCID_CACHE = cache
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(ORCID_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_ss_authors_cache() -> dict:
    global _SS_AUTHORS_CACHE
    if _SS_AUTHORS_CACHE is not None:
        return _SS_AUTHORS_CACHE
    if os.path.exists(SS_AUTHORS_CACHE_FILE):
        try:
            with open(SS_AUTHORS_CACHE_FILE, "r", encoding="utf-8") as f:
                _SS_AUTHORS_CACHE = json.load(f)
                return _SS_AUTHORS_CACHE
        except Exception:
            _SS_AUTHORS_CACHE = {}
    else:
        _SS_AUTHORS_CACHE = {}
    return _SS_AUTHORS_CACHE

def save_ss_authors_cache(cache: dict):
    global _SS_AUTHORS_CACHE
    _SS_AUTHORS_CACHE = cache
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(SS_AUTHORS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def fetch_orcid_author_profile(orcid_id: str) -> dict:
    """
    Fetches researcher's verified personal profile from Public ORCID API.
    Returns {'given_name': ..., 'family_name': ..., 'credit_name': ..., 'orcid': ...}
    """
    if not orcid_id or pd.isna(orcid_id):
        return None
    clean_id = str(orcid_id).replace("https://orcid.org/", "").replace("http://orcid.org/", "").strip()
    if not clean_id or len(clean_id) < 15:
        return None

    cache = load_orcid_cache()
    if clean_id in cache:
        return cache[clean_id]

    url = f"https://pub.orcid.org/v3.0/{clean_id}/personal-details"
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            name_obj = data.get('name') or {}
            given = (name_obj.get('given-names') or {}).get('value')
            family = (name_obj.get('family-name') or {}).get('value')
            credit = (name_obj.get('credit-name') or {}).get('value')
            res = {
                'given_name': given,
                'family_name': family,
                'credit_name': credit,
                'orcid': clean_id
            }
            cache[clean_id] = res
            save_orcid_cache(cache)
            return res
    except Exception:
        pass
    return None


def fetch_openalex_author_entities_batch(author_ids: list) -> dict:
    """
    Batch fetches OpenAlex author entities by ID to extract display_name_alternatives and ORCID.
    """
    if not author_ids:
        return {}
    clean_ids = []
    for aid in author_ids:
        if aid and pd.notna(aid):
            cid = str(aid).replace("https://openalex.org/", "").strip()
            if cid.startswith("A") and cid not in clean_ids:
                clean_ids.append(cid)

    if not clean_ids:
        return {}

    cache = load_oa_author_entities_cache()
    needed = [cid for cid in clean_ids if cid not in cache]

    if needed:
        headers = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}
        batch_size = 50
        for i in range(0, len(needed), batch_size):
            batch = needed[i:i+batch_size]
            filter_str = "openalex:" + "|".join(batch)
            url = f"https://api.openalex.org/authors?filter={filter_str}&per-page={batch_size}"
            try:
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    for author_obj in data.get('results', []):
                        aid = str(author_obj.get('id', '')).replace("https://openalex.org/", "").strip()
                        if aid:
                            cache[aid] = {
                                'display_name': author_obj.get('display_name', ''),
                                'display_name_alternatives': author_obj.get('display_name_alternatives', []),
                                'orcid': author_obj.get('orcid', '')
                            }
                time.sleep(0.4)
            except Exception:
                pass
        save_oa_author_entities_cache(cache)

    return {cid: cache.get(cid) for cid in clean_ids if cid in cache}


def fetch_semanticscholar_authors_for_doi(doi: str) -> list:
    """
    Fetches authors list from Semantic Scholar for a DOI using local cache.
    """
    if not doi or pd.isna(doi):
        return []
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "").lower()
    if not clean_doi:
        return []

    cache = load_ss_authors_cache()
    if clean_doi in cache:
        return cache[clean_doi]

    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{clean_doi}?fields=title,authors,authors.name,authors.authorId"
    headers = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}
    try:
        time.sleep(1.0)
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            authors = data.get('authors', [])
            cache[clean_doi] = authors
            save_ss_authors_cache(cache)
            return authors
    except Exception:
        pass
    return []


def fetch_openalex_authorships_batch(dois: list) -> dict:
    """
    Fetches OpenAlex authorships for a list of DOIs in polite batches, using local persistent cache.
    Also pre-fetches OpenAlex author entities (for alternate_names) in polite background batches.
    """
    if not dois:
        return {}
    clean_map = {}
    for d in dois:
        if pd.notna(d) and str(d).strip() and str(d).strip().lower() != 'nan':
            clean_d = str(d).strip().replace("https://doi.org/", "").replace("doi:", "").lower()
            clean_map[clean_d] = str(d).strip()

    if not clean_map:
        return {}

    cache = load_oa_authors_cache()
    needed = [cd for cd in clean_map.keys() if cd not in cache]

    if needed:
        headers = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}
        batch_size = 50
        author_ids_to_fetch = []
        for i in range(0, len(needed), batch_size):
            batch = needed[i:i+batch_size]
            filter_str = "doi:" + "|".join(batch)
            url = f"https://api.openalex.org/works?filter={filter_str}&per-page={batch_size}"
            try:
                resp = requests.get(url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    for work in data.get('results', []):
                        work_doi = work.get('doi')
                        if work_doi:
                            w_clean = str(work_doi).replace("https://doi.org/", "").replace("doi:", "").lower()
                            authorships = work.get('authorships', [])
                            cache[w_clean] = {
                                'title': work.get('title', ''),
                                'authorships': authorships
                            }
                            for auth in authorships:
                                aid = auth.get('author', {}).get('id')
                                if aid:
                                    author_ids_to_fetch.append(aid)
                time.sleep(0.5)
            except Exception:
                pass
        save_oa_authors_cache(cache)

        if author_ids_to_fetch:
            fetch_openalex_author_entities_batch(author_ids_to_fetch)

    res = {}
    for cd, raw_d in clean_map.items():
        if cd in cache:
            res[raw_d] = cache[cd]
            res[cd] = cache[cd]
    return res


def disambiguate_paper_authors(
    raw_author_list: list, 
    oa_authorships: list = None,
    ss_authors: list = None,
    cr_authors: list = None
) -> tuple:
    """
    Selectively matches and resolves initialed authors in a bunched author list
    using a multi-tier resolution hierarchy:
      1. ORCID Public Profile (Direct from researcher)
      2. OpenAlex Primary Display Name
      3. OpenAlex Alternate Names (display_name_alternatives from author entity)
      4. Semantic Scholar AI Author Profiles (AER)
      5. Crossref Authors (given + family)
    
    CRITICAL: Authors that are already full names without initials are preserved
    completely untouched. Only initialed tokens are substituted.
    
    Returns (resolved_authors_list, was_any_enriched).
    """
    if not raw_author_list:
        return [], False

    oa_authorships = oa_authorships or []
    ss_authors = ss_authors or []
    cr_authors = cr_authors or []

    # Load entity cache for OpenAlex alternate names
    oa_entity_cache = load_oa_author_entities_cache()

    # Load manual overrides if any exist for the active project
    try:
        from utils.project_manager import get_manual_author_overrides
        manual_overrides = get_manual_author_overrides()
    except Exception:
        manual_overrides = {}

    # Pre-parse OpenAlex candidates
    oa_candidates = []
    for auth in oa_authorships:
        auth_obj = auth.get('author', {}) or {}
        disp_name = clean_author_text(auth_obj.get('display_name', ''))
        aid = str(auth_obj.get('id', '')).replace("https://openalex.org/", "").strip()
        orcid = auth_obj.get('orcid') or auth.get('raw_orcid')
        raw_oa = clean_author_text(auth.get('raw_author_name', ''))

        if disp_name or raw_oa:
            oa_f, oa_l, oa_init = extract_name_parts(disp_name or raw_oa)
            oa_candidates.append({
                'display_name': disp_name,
                'raw_oa': raw_oa,
                'author_id': aid,
                'orcid': orcid,
                'first_name': oa_f,
                'last_name': oa_l,
                'is_initial': oa_init
            })

    # Pre-parse Semantic Scholar candidates
    ss_candidates = []
    for ssa in ss_authors:
        name = clean_author_text(ssa.get('name', ''))
        if name:
            sf, sl, sinit = extract_name_parts(name)
            ss_candidates.append({
                'name': name,
                'first_name': sf,
                'last_name': sl,
                'is_initial': sinit
            })

    # Pre-parse Crossref candidates
    cr_candidates = []
    for cra in cr_authors:
        cg = clean_author_text(cra.get('given', ''))
        cf = clean_author_text(cra.get('family', ''))
        if cf:
            cr_name = f"{cg} {cf}".strip()
            cr_f, cr_l, cr_init = extract_name_parts(cr_name)
            cr_candidates.append({
                'name': cr_name,
                'given': cg,
                'family': cf,
                'first_name': cr_f,
                'last_name': cr_l,
                'is_initial': cr_init
            })

    resolved = []
    used_oa_indices = set()
    any_enriched = False

    for full_a_name in raw_author_list:
        raw_clean = clean_author_text(full_a_name)
        
        # Check Manual Overrides first
        if manual_overrides and (raw_clean in manual_overrides or full_a_name.strip() in manual_overrides):
            override_val = manual_overrides.get(raw_clean) or manual_overrides.get(full_a_name.strip())
            of, ol, oinit = extract_name_parts(override_val)
            resolved.append({
                'full_name': override_val,
                'first_name': of,
                'last_name': ol,
                'is_initial': oinit,
                'was_enriched': True,
                'provenance': 'Manual User Override'
            })
            any_enriched = True
            continue

        raw_f, raw_l, raw_init = extract_name_parts(full_a_name)

        # Rule 1: Already full name without initials -> KEEP AS-IS in Western format!
        if not raw_init and raw_f:
            std_full = standardize_author_name(full_a_name)
            resolved.append({
                'full_name': std_full if std_full else (raw_clean if raw_clean else full_a_name.strip()),
                'first_name': raw_f,
                'last_name': raw_l,
                'is_initial': False,
                'was_enriched': False,
                'provenance': 'Original Full Name'
            })
            continue

        resolved_match = None
        provenance = None
        matched_oa_idx = -1
        norm_raw_last = norm_surname(raw_l)

        # Search in OpenAlex candidates
        for i, cand in enumerate(oa_candidates):
            if i in used_oa_indices:
                continue

            norm_cand_last = norm_surname(cand['last_name'])
            norm_cand_full = norm_surname(cand['display_name'])

            if not norm_raw_last:
                continue

            surname_match = (norm_cand_last == norm_raw_last) or (norm_raw_last in norm_cand_full)
            if not surname_match:
                continue

            # Check initial alignment if present
            first_init_char = raw_f.strip()[0].upper() if raw_f else None
            cand_first_char = cand['first_name'][0].upper() if cand['first_name'] else None

            if first_init_char and cand_first_char and first_init_char != cand_first_char:
                continue

            # Match candidate found! Apply Priority:
            # 1. ORCID Path
            cand_orcid = cand.get('orcid')
            if cand_orcid:
                orcid_prof = fetch_orcid_author_profile(cand_orcid)
                if orcid_prof:
                    g = orcid_prof.get('given_name')
                    f = orcid_prof.get('family_name')
                    c = orcid_prof.get('credit_name')
                    if c and not author_has_initials(c):
                        resolved_match = clean_author_text(c)
                        provenance = f"ORCID ({cand_orcid})"
                        matched_oa_idx = i
                        break
                    elif g and f and not author_has_initials(g):
                        resolved_match = clean_author_text(f"{g} {f}".strip())
                        provenance = f"ORCID ({cand_orcid})"
                        matched_oa_idx = i
                        break

            # 2. OpenAlex Display Name
            if not cand['is_initial'] and cand['first_name']:
                resolved_match = clean_author_text(cand['display_name'])
                provenance = "OpenAlex Display Name"
                matched_oa_idx = i
                break

            # 3. OpenAlex Alternate Names (display_name_alternatives)
            cand_aid = cand.get('author_id')
            if cand_aid:
                if cand_aid not in oa_entity_cache:
                    oa_entity_cache.update(fetch_openalex_author_entities_batch([cand_aid]))
                entity_info = oa_entity_cache.get(cand_aid)
                if entity_info:
                    # Also check ORCID in author entity if not in authorship
                    ent_orcid = entity_info.get('orcid')
                    if ent_orcid and not cand_orcid:
                        orcid_prof = fetch_orcid_author_profile(ent_orcid)
                        if orcid_prof:
                            g = orcid_prof.get('given_name')
                            f = orcid_prof.get('family_name')
                            c = orcid_prof.get('credit_name')
                            if c and not author_has_initials(c):
                                resolved_match = clean_author_text(c)
                                provenance = f"ORCID ({ent_orcid})"
                                matched_oa_idx = i
                                break
                            elif g and f and not author_has_initials(g):
                                resolved_match = clean_author_text(f"{g} {f}".strip())
                                provenance = f"ORCID ({ent_orcid})"
                                matched_oa_idx = i
                                break

                    # Look through alternatives
                    for alt in entity_info.get('display_name_alternatives', []):
                        alt_clean = clean_author_text(alt)
                        alt_f, alt_l, alt_init = extract_name_parts(alt_clean)
                        if not alt_init and alt_f and len(alt_f) > 1:
                            norm_alt_l = norm_surname(alt_l)
                            norm_alt_full = norm_surname(alt_clean)
                            if (norm_alt_l == norm_raw_last or norm_raw_last in norm_alt_full):
                                if not first_init_char or (alt_f[0].upper() == first_init_char):
                                    resolved_match = alt_clean
                                    provenance = "OpenAlex Alternate Names"
                                    matched_oa_idx = i
                                    break
            if resolved_match:
                break

        # 4. Semantic Scholar AER Fallback
        if not resolved_match and ss_candidates and raw_l and norm_raw_last:
            first_init_char = raw_f.strip()[0].upper() if raw_f else None
            for ssc in ss_candidates:
                if not ssc['is_initial'] and ssc['first_name']:
                    norm_ssc_last = norm_surname(ssc['last_name'])
                    norm_ssc_full = norm_surname(ssc['name'])
                    if (norm_ssc_last == norm_raw_last or norm_raw_last in norm_ssc_full):
                        if not first_init_char or (ssc['first_name'][0].upper() == first_init_char):
                            resolved_match = clean_author_text(ssc['name'])
                            provenance = "Semantic Scholar"
                            break

        # 5. Crossref Fallback
        if not resolved_match and cr_candidates and raw_l and norm_raw_last:
            first_init_char = raw_f.strip()[0].upper() if raw_f else None
            for crc in cr_candidates:
                if not crc['is_initial'] and crc['first_name']:
                    norm_crc_last = norm_surname(crc['last_name'])
                    norm_crc_full = norm_surname(crc['name'])
                    if (norm_crc_last == norm_raw_last or norm_raw_last in norm_crc_full):
                        if not first_init_char or (crc['first_name'][0].upper() == first_init_char):
                            resolved_match = clean_author_text(crc['name'])
                            provenance = "Crossref"
                            break

        if resolved_match:
            if matched_oa_idx >= 0:
                used_oa_indices.add(matched_oa_idx)
            any_enriched = True
            rf, rl, _ = extract_name_parts(resolved_match)
            resolved.append({
                'full_name': resolved_match,
                'first_name': rf,
                'last_name': rl,
                'is_initial': False,
                'was_enriched': True,
                'provenance': provenance
            })
        else:
            # If unresolved initialed author, format in natural Western order: "Initials Surname" (e.g. "K Cosic", "F Denton", "DW O'Neill")
            std_fallback = standardize_author_name(full_a_name)
            fallback_full = std_fallback if std_fallback else (f"{raw_f} {raw_l}".strip() if (raw_init and raw_f and raw_l) else (raw_clean if raw_clean else full_a_name.strip()))
            resolved.append({
                'full_name': fallback_full,
                'first_name': raw_f,
                'last_name': raw_l,
                'is_initial': raw_init,
                'was_enriched': False,
                'provenance': 'None'
            })

    return resolved, any_enriched

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
# -----------------------------------------------------------------------------
# Classification Engines (NamSor API v2 + Locality Intelligence)
# -----------------------------------------------------------------------------
def classify_gender_namsor_single(first_name: str, last_name: str = "", country_iso2: str = None, api_key: str = None) -> dict:
    """Queries NamSor v2 API for a single name endpoint (geo or generic)."""
    if not api_key:
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'NamSor (No Key)'}

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-API-KEY': api_key.strip()
    }
    
    clean_fn = quote(first_name.strip())
    clean_ln = quote(last_name.strip() or 'author')

    # Use Geo endpoint if country ISO2 is available
    if country_iso2 and len(country_iso2) == 2:
        url = f"https://v2.namsor.com/NamSorAPIv2/api2/json/genderGeo/{clean_fn}/{clean_ln}/{country_iso2.upper()}"
        engine_label = f"NamSor API (Geo: {country_iso2.upper()})"
    else:
        url = f"https://v2.namsor.com/NamSorAPIv2/api2/json/gender/{clean_fn}/{clean_ln}"
        engine_label = "NamSor API (Generic)"

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'gender': str(data.get('likelyGender', 'unknown')).lower(),
                'probability': float(data.get('probabilityCalibrated', 0.0)),
                'engine': engine_label
            }
        elif resp.status_code in [401, 403]:
            return {
                'gender': 'unknown', 
                'probability': 0.0, 
                'engine': f'NamSor Quota/Auth Error ({resp.status_code})', 
                'is_quota_error': True, 
                'error_type': 'quota',
                'error_msg': f'NamSor Quota or Key Error ({resp.status_code})'
            }
        else:
            return {'gender': 'unknown', 'probability': 0.0, 'engine': f'NamSor HTTP {resp.status_code}'}
    except Exception:
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'NamSor Network Error'}

def classify_gender_namsor_adaptive(
    first_name: str, 
    last_name: str = "", 
    country_iso2: str = None, 
    api_key: str = None, 
    threshold: float = 0.75
) -> dict:
    """
    Queries NamSor v2 API with locality intelligence and automatic generic fallback.
    If a country-specific query does not meet the threshold (or returns unknown),
    it automatically queries the global generic endpoint so that nationality/locality
    is never an impediment to high-confidence classification.
    """
    if not api_key or not api_key.strip():
        return {'gender': 'unknown', 'probability': 0.0, 'engine': 'NamSor (No Key)'}

    # 1. If country_iso2 is provided, try country-specific query first
    if country_iso2 and len(country_iso2) == 2:
        geo_res = classify_gender_namsor_single(first_name, last_name, country_iso2=country_iso2, api_key=api_key)
        
        # Stop immediately if critical quota / auth error
        if geo_res.get('is_quota_error') or 'Quota/Auth Error' in geo_res.get('engine', ''):
            return geo_res
            
        geo_gender = geo_res.get('gender', 'unknown')
        geo_prob = geo_res.get('probability', 0.0)
        
        # If locality query meets the acceptance threshold, accept immediately
        if geo_gender in ['male', 'female'] and geo_prob >= threshold:
            return geo_res
            
        # 2. Locality was uncertain or below threshold -> fallback to global generic NamSor endpoint
        gen_res = classify_gender_namsor_single(first_name, last_name, country_iso2=None, api_key=api_key)
        if gen_res.get('is_quota_error') or 'Quota/Auth Error' in gen_res.get('engine', ''):
            return gen_res
            
        gen_gender = gen_res.get('gender', 'unknown')
        gen_prob = gen_res.get('probability', 0.0)
        
        # If generic query meets threshold or provides higher confidence, use generic result
        if (gen_gender in ['male', 'female'] and gen_prob >= threshold) or (gen_prob > geo_prob and gen_gender in ['male', 'female']):
            gen_res['engine'] = 'NamSor API (Generic Fallback)'
            return gen_res
            
        # Otherwise retain the highest confidence result
        return geo_res if geo_prob >= gen_prob else gen_res

    # No country specified: query generic global endpoint directly
    return classify_gender_namsor_single(first_name, last_name, country_iso2=None, api_key=api_key)

# Alias for backwards compatibility
classify_gender_namsor = classify_gender_namsor_adaptive

# -----------------------------------------------------------------------------
# Classification Resolver (Cache First -> NamSor API Adaptive Locality Fallback)
# -----------------------------------------------------------------------------
def classify_author_gender(
    first_name: str,
    last_name: str,
    country_iso2: str,
    gender_cache: dict,
    namsor_api_key: str = None,
    threshold: float = 0.75,
    **kwargs
) -> tuple:
    """
    Classifies author gender prioritizing verified local cache, followed by NamSor API:
    1. Check Local Cache:
       - Country-specific cache key: `{first_name}_{country_iso2}`
       - Generic cache key: `{first_name}`
       If found with probability >= threshold and in ['male', 'female'], accepted with 0 API calls!
    2. If Uncached or below threshold and NamSor API key provided:
       - Query NamSor adaptively (geo-localized with automatic generic fallback).
       - Store results in cache under both country and generic keys as appropriate.
    3. If no API key provided (Offline / Local Cache mode):
       - Use best available cached entry, or mark as unknown.
    Returns (result_dict, source_type) where source_type is 'cache', 'namsor', or 'namsor_error'.
    """
    fn_lower = first_name.strip().lower()
    
    # 1. Check Cache:
    # A) Specific country key
    if country_iso2:
        c_key = f"{fn_lower}_{country_iso2.strip().lower()}"
        if c_key in gender_cache:
            res = gender_cache[c_key].copy()
            if res.get('probability', 0.0) >= threshold and res.get('gender') in ['male', 'female']:
                res['reliable'] = True
                return res, 'cache'
                
    # B) Generic key
    if fn_lower in gender_cache:
        cached_entry = gender_cache[fn_lower]
        if cached_entry.get('probability', 0.0) >= threshold and cached_entry.get('gender') in ['male', 'female']:
            res = cached_entry.copy()
            res['reliable'] = True
            return res, 'cache'

    # 2. If uncached/sub-threshold and NamSor API key is active
    if namsor_api_key and namsor_api_key.strip():
        namsor_res = classify_gender_namsor_adaptive(
            first_name=first_name, 
            last_name=last_name, 
            country_iso2=country_iso2, 
            api_key=namsor_api_key, 
            threshold=threshold
        )
        
        # Check for Quota or Authentication errors
        if namsor_res.get('is_quota_error') or 'Quota/Auth Error' in namsor_res.get('engine', ''):
            err_msg = namsor_res.get('error_msg', 'NamSor Quota Exhausted or Invalid API Key')
            return {'gender': 'unknown', 'probability': 0.0, 'engine': err_msg, 'is_quota_error': True, 'error_msg': err_msg}, 'namsor_error'

        # Cache NamSor result
        if 'Error' not in namsor_res.get('engine', '') and 'HTTP 40' not in namsor_res.get('engine', ''):
            if country_iso2:
                gender_cache[f"{fn_lower}_{country_iso2.strip().lower()}"] = namsor_res
            if namsor_res.get('probability', 0.0) >= threshold or not country_iso2:
                gender_cache[fn_lower] = namsor_res
                
            res = namsor_res.copy()
            res['reliable'] = (res.get('probability', 0.0) >= threshold and res.get('gender') in ['male', 'female'])
            if not res['reliable']:
                res['gender'] = 'unknown'
            return res, 'namsor'

    # 3. Local Cache Only Mode (no API key or network disabled)
    res = {'gender': 'unknown', 'probability': 0.0, 'engine': 'Uncached (Local Cache Mode)'}
    found_in_cache = False
    if country_iso2 and f"{fn_lower}_{country_iso2.strip().lower()}" in gender_cache:
        res = gender_cache[f"{fn_lower}_{country_iso2.strip().lower()}"].copy()
        found_in_cache = True
    elif fn_lower in gender_cache:
        res = gender_cache[fn_lower].copy()
        found_in_cache = True

    res['reliable'] = (res.get('probability', 0.0) >= threshold and res.get('gender') in ['male', 'female'])
    if not res['reliable']:
        res['gender'] = 'unknown'
        # If it was in cache but sub-threshold or ambiguous, or not in cache at all
        if not found_in_cache:
            return res, 'cache_miss'
        return res, 'cache_subthreshold'
    return res, 'cache'

# Alias for backwards compatibility
classify_author_gender_hybrid = classify_author_gender

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

    with st.expander("⚠️ Methodological Note: Gender Inference & Inclusivity", expanded=False):
        st.markdown(
            """
            This tool relies on automated algorithms that infer gender based on first names using historical societal name-gender associations. Consequently, this approach inevitably imposes a strict binary framework (male or female) and inherently excludes non-binary and transgender identities. 
            
            We recognize this limitation and want to clarify that what is being measured is the social association between names and genders, rather than an individual's true self-identified gender.
            """
        )

    # 1. Pipeline Configuration Panel
    is_panel_expanded = ('gender_analysis_results' not in st.session_state) or ('gender_error' in st.session_state)
    with st.expander("⚙️ NamSor Inference Engine & Persistent Cache Configuration", expanded=is_panel_expanded):
        st.markdown(f"""
        <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #697aa2; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px; font-size: 13px; color: #334155;">
            <b>🛡️ NamSor API & Locality Intelligence:</b> The pipeline queries the verified persistent cache first, consuming zero API credits for previously resolved names. 
            Uncached names are queried via <b>NamSor v2</b> with author-bound geo-localization (ISO-2 country codes). 
            If a localized query does not meet the acceptance threshold (e.g. international researchers affiliated abroad), 
            the system <b>automatically falls back to global generic inference</b>, ensuring locality is never an impediment to high-confidence classification.
            <br><span style="color: #64748B; font-size: 12px;">💾 Persistent Cache: <b>{cached_names_count:,} unique names</b> currently saved locally in <code>utils/cache/gender_cache.json</code>.</span>
        </div>
        """, unsafe_allow_html=True)

        c_conf1, c_conf2 = st.columns([1.2, 1.8], gap="medium")
        
        with c_conf1:
            mode_choice = st.radio(
                "Inference Strategy",
                [
                    "NamSor API + Persistent Cache",
                    "Local Cache Only (Offline)"
                ],
                help="NamSor API queries the persistent cache first and calls NamSor API only for uncached names. Local Cache Only never makes network calls."
            )
            
            namsor_api_key_input = ""
            if "NamSor API" in mode_choice:
                namsor_api_key_input = st.text_input(
                    "NamSor API Key", 
                    type="password", 
                    placeholder="Enter NamSor API key...",
                    help="Obtain at namsor.com. 1,000 free calls/month. Classified names are saved permanently to local cache."
                )

        with c_conf2:
            final_thresh_pct = st.slider(
                "NamSor Acceptance Threshold (%)",
                min_value=50,
                max_value=95,
                value=int(DEFAULT_CONFIDENCE_THRESHOLD * 100),
                step=5,
                help="Names with NamSor calibrated probability below this threshold are marked as 'Unknown' ([Minuzzo et al. 2026](https://doi.org/10.5753/reviews.2026.6779) recommends 75%)."
            )
            final_threshold = final_thresh_pct / 100.0

        # Check if unstandardized author names are present
        authors_col = df['Author'] if 'Author' in df.columns else pd.Series(dtype=object)
        unstandardized_mask = authors_col.apply(lambda x: author_has_initials(x) if (pd.notna(x) and str(x).strip()) else False)
        unstandardized_count = int(unstandardized_mask.sum())
        
        if unstandardized_count > 0:
            c_gadv1, c_gadv2 = st.columns([3.4, 1.6])
            with c_gadv1:
                st.markdown(f"""
                <div style="background-color: #FEF3C7; border: 1px solid #FDE68A; border-left: 4px solid #D97706; padding: 10px 14px; border-radius: 6px; font-size: 13px; color: #92400E;">
                    <b>⚠️ Unexpanded Author Initials Detected ({unstandardized_count:,} articles):</b><br>
                    Authors with initials yield higher classification confidence when expanded to verified full names. 
                    You can disambiguate them via OpenAlex now, or proceed immediately with current names.
                </div>
                """, unsafe_allow_html=True)
            with c_gadv2:
                st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                if st.button("✨ Disambiguate (OpenAlex)", key="btn_gender_disambiguate_oa", icon=":material/magic_button:", width="stretch", help="Run OpenAlex author disambiguation across the corpus to expand initials into full names before running gender analysis."):
                    from core.enrichment import enrich_dataset_openalex
                    with st.spinner("Enriching author initials with OpenAlex..."):
                        proc_df = enrich_dataset_openalex(
                            st.session_state.master_df.copy(),
                            ['Author'],
                            st.session_state.get('execution_logs', []),
                            file_manifest=st.session_state.get('file_manifest', {}),
                            is_ultimate=False
                        )
                        st.session_state.master_df = proc_df
                        save_master_dataset(st.session_state.master_df)
                        st.session_state.has_unstandardized_authors = False
                        st.toast("Author initials expanded to full verified names!", icon="🎉")
                        st.rerun()

        run_btn = st.button("Run Gender Inference Pipeline", type="primary", icon=":material/play_arrow:", width="stretch")

    # 2. Execution Logic
    if run_btn or 'gender_analysis_results' not in st.session_state:
        if run_btn:
            gender_cache = load_gender_cache()
            
            progress_bar = st.progress(0, text="Initializing gender inference pipeline...")
            
            total_rows = len(df)
            parsed_authors = [] # list of dicts for author directory
            article_assessments = [] # list of dicts for article-level assessment
            unique_authors_seen = {} # full_name -> stats
            
            start_t = time.time()
            cache_hits_count = 0
            cache_misses_count = 0
            offline_hits_count = 0
            namsor_calls_count = 0
            disambiguated_count = 0
            disambiguation_log = []
            
            for idx, row in df.reset_index().iterrows():
                orig_idx = row.get('index', idx)
                title = str(row.get('Title', 'Untitled Record'))
                from utils.formatters import clean_year_value
                year = clean_year_value(row.get('Publication Year', '')) or 'Unknown'
                authors_str = str(row.get('Author', ''))
                country_loc, country_iso2, display_country = extract_article_country_info(row)
                
                if not authors_str or authors_str.strip() == '' or authors_str.lower() == 'nan':
                    continue

                raw_author_list = split_authors_string(authors_str)
                
                # Fast local pass: Apply manual user overrides and ensure Western format without network queries
                resolved_authors_list, was_enriched = disambiguate_paper_authors(raw_author_list, oa_authorships=[])
                new_author_str = "; ".join([a['full_name'] for a in resolved_authors_list])
                if new_author_str and new_author_str != authors_str:
                    try:
                        df.at[orig_idx, 'Author'] = new_author_str
                    except Exception:
                        pass
                    if 'master_df' in st.session_state and st.session_state.master_df is not None:
                        try:
                            st.session_state.master_df.at[orig_idx, 'Author'] = new_author_str
                        except Exception:
                            pass
                if was_enriched:
                    for ra in resolved_authors_list:
                        if ra.get('was_enriched'):
                            disambiguated_count += 1
                            disambiguation_log.append(f"'{title[:45]}...': {ra['last_name']} -> {ra['full_name']}")

                article_authors = []
                for a_pos, a_info in enumerate(resolved_authors_list):
                    first_n = a_info['first_name']
                    last_n = a_info['last_name']
                    is_initial = a_info['is_initial']
                    full_a_name = a_info['full_name']
                    
                    if is_initial or not first_n:
                        res = {
                            'gender': 'unknown',
                            'probability': 0.0,
                            'reliable': False,
                            'engine': 'Initial / Abbreviated'
                        }
                    else:
                        active_key = namsor_api_key_input if "NamSor API" in mode_choice else ""
                        res, source_type = classify_author_gender(
                            first_name=first_n,
                            last_name=last_n,
                            country_iso2=country_iso2,
                            gender_cache=gender_cache,
                            namsor_api_key=active_key,
                            threshold=final_threshold
                        )
                        
                        if source_type == 'cache':
                            cache_hits_count += 1
                        elif source_type in ['cache_miss', 'cache_subthreshold']:
                            cache_misses_count += 1
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
                                    'cache_misses': cache_misses_count,
                                    'offline_hits': 0,
                                    'namsor_calls': namsor_calls_count,
                                    'quota_saved_pct': (cache_hits_count / len(parsed_authors) * 100) if parsed_authors else 100.0,
                                    'threshold': final_threshold,
                                    'mode_choice': mode_choice,
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
            
            # Save updated dataset with disambiguated author names to project disk
            if disambiguated_count > 0 and 'master_df' in st.session_state and st.session_state.master_df is not None:
                try:
                    save_master_dataset(st.session_state.master_df)
                except Exception:
                    pass

            # Clear error state on successful complete run
            if 'gender_error' in st.session_state:
                del st.session_state['gender_error']
            
            duration = time.time() - start_t
            total_eval = len(parsed_authors)
            quota_saved = (cache_hits_count / total_eval * 100) if total_eval > 0 else 100.0
            
            # Save results to session_state
            results_payload = {
                'authors_df': pd.DataFrame(parsed_authors),
                'articles_df': pd.DataFrame(article_assessments),
                'unique_authors': list(unique_authors_seen.values()),
                'duration': duration,
                'cache_hits': cache_hits_count,
                'cache_misses': cache_misses_count,
                'offline_hits': 0,
                'namsor_calls': namsor_calls_count,
                'quota_saved_pct': quota_saved,
                'threshold': final_threshold,
                'mode_choice': mode_choice,
                'disambiguated_count': disambiguated_count,
                'disambiguation_log': disambiguation_log,
                'is_partial': False
            }
            st.session_state.gender_analysis_results = results_payload

            # Generate and save detailed audit log into active project's logs folder
            audit_log_text = generate_gender_audit_log(
                results_payload, 
                strategy_name=mode_choice, 
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
    cache_misses = res_data.get('cache_misses', 0)
    cache_hits = res_data.get('cache_hits', 0)
    namsor_calls = res_data.get('namsor_calls', 0)
    mode_choice_res = res_data.get('mode_choice', '')
    total_eval_mentions = len(authors_df)
    
    if res_data.get('disambiguated_count', 0) > 0:
        st.markdown(f"""
        <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-left: 4px solid #3B82F6; padding: 10px 16px; border-radius: 6px; margin-bottom: 12px; font-size: 13px; color: #1E3A8A;">
            <span style="font-weight: 700;">✨ Author Disambiguation Engine:</span>
            Successfully expanded <b>{res_data['disambiguated_count']:,} author records</b> from abbreviated initials into full verified names via OpenAlex!
        </div>
        """, unsafe_allow_html=True)

    is_local_cache_mode = ('Local Cache' in mode_choice_res) or (namsor_calls == 0 and cache_misses > 0)
    if is_local_cache_mode:
        cache_resolution_pct = (cache_hits / total_eval_mentions * 100) if total_eval_mentions else 0
        cache_miss_pct = (cache_misses / total_eval_mentions * 100) if total_eval_mentions else 0
        st.markdown(f"""
        <div style="background-color: #F8FAFC; border: 1px solid #CBD5E1; border-left: 4px solid #64748B; padding: 10px 16px; border-radius: 6px; margin-bottom: 15px; font-size: 13px;">
            <span style="font-weight: 700; color: #334155;">🛡️ Local Cache Resolution Report:</span>
            <b>{cache_hits:,} author queries ({cache_resolution_pct:.1f}%) resolved from verified local cache!</b>
            <div style="color: #475569; margin-top: 3px;">
                • <b>{cache_hits:,}</b> Verified Cache Hits ({cache_resolution_pct:.1f}%) &nbsp;|&nbsp; 
                • <b>{cache_misses:,}</b> Not Found in Cache ({cache_miss_pct:.1f}%, Marked as Unknown) &nbsp;|&nbsp; 
                • <b>0</b> NamSor API Calls &nbsp;|&nbsp; 
                • Completed in <b>{formatted_duration_str}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background-color: #F0FDF4; border: 1px solid #DCFCE7; border-left: 4px solid #16A34A; padding: 10px 16px; border-radius: 6px; margin-bottom: 15px; font-size: 13px;">
            <span style="font-weight: 700; color: #166534;">🛡️ NamSor API Quota Efficiency Report:</span>
            <b>{res_data['quota_saved_pct']:.1f}% of author queries resolved from verified local cache!</b>
            <div style="color: #15803d; margin-top: 3px;">
                • <b>{cache_hits:,}</b> Verified Cache Hits &nbsp;|&nbsp; 
                • <b>{namsor_calls:,}</b> NamSor API Calls &nbsp;|&nbsp; 
                • Completed in <b>{formatted_duration_str}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 3. Known Genders Toggle & KPI Metrics Bar
    filter_known_only = st.toggle(
        "Filter Known Genders Only (Exclude Unknown / Unclassified)",
        value=False,
        key="toggle_filter_known_genders",
        help="When enabled, recalculates all demographic metrics, authorship compositions, and visualizations focusing strictly on confirmed Male and Female authors, excluding unclassified initials and ambiguous records."
    )

    # Demographic calculations based on toggle state
    if filter_known_only:
        active_u_authors = u_authors_df[u_authors_df['gender'].isin(['male', 'female'])].copy()
        active_total_authors = len(active_u_authors)
        active_male = (active_u_authors['gender'] == 'male').sum()
        active_female = (active_u_authors['gender'] == 'female').sum()
        active_male_pct = (active_male / active_total_authors * 100) if active_total_authors else 0
        active_female_pct = (active_female / active_total_authors * 100) if active_total_authors else 0
        corpus_rep_pct = (active_total_authors / total_unique_authors * 100) if total_unique_authors else 0
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #F0F7FF 0%, #FFFFFF 100%); border: 1px solid #BFDBFE; border-left: 4px solid #2563EB; padding: 12px 18px; border-radius: 8px; margin: 10px 0 16px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 20px;">🎯</span>
                <div>
                    <div style="font-size: 13.5px; font-weight: 700; color: #1E3A8A;">
                        Known Authorship Cohort Active
                    </div>
                    <div style="font-size: 12.5px; color: #3B82F6; margin-top: 1px;">
                        Displaying verified <b>{active_total_authors:,} unique authors</b>, representing <b>{corpus_rep_pct:.1f}%</b> of the complete catalog ({total_unique_authors:,} unique authors).
                    </div>
                </div>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span style="background-color: #DBEAFE; color: #1E40AF; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600;">
                    {active_male:,} Men ({active_male_pct:.1f}%)
                </span>
                <span style="background-color: #FCE7F3; color: #9D174D; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600;">
                    {active_female:,} Women ({active_female_pct:.1f}%)
                </span>
                <span style="background-color: #F1F5F9; color: #64748B; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 500;">
                    {unknown_unique:,} Unclassified Excluded
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
            
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Classified Authors", f"{active_total_authors:,}", f"{corpus_rep_pct:.1f}% of total corpus", delta_color="normal")
        m2.metric("Female Authors", f"{active_female:,}", f"{active_female_pct:.1f}% of classified", delta_color="normal")
        m3.metric("Male Authors", f"{active_male:,}", f"{active_male_pct:.1f}% of classified", delta_color="normal")
        m4.metric("Excluded Unknown", f"{unknown_unique:,}", f"{unknown_pct:.1f}% of corpus", delta_color="off")
        m5.metric("Articles with ≥1 Woman", f"{articles_with_female:,}", f"{female_art_pct:.1f}% of papers", delta_color="normal")
    else:
        st.markdown(f"""
        <!--div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #94A3B8; padding: 10px 18px; border-radius: 8px; margin: 10px 0 16px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 18px;">🌐</span>
                <span style="font-size: 13px; color: #334155;">
                    <b>Full Corpus View:</b> Evaluating all <b>{total_unique_authors:,} unique authors</b> across the entire literature dataset (including unclassified initials).
                </span>
            </div>
            <span style="background-color: #E2E8F0; color: #475569; padding: 3px 9px; border-radius: 9999px; font-size: 11.5px; font-weight: 500;">
                {male_unique:,} Men ({male_pct:.1f}%) · {female_unique:,} Women ({female_pct:.1f}%) · {unknown_unique:,} Unclassified ({unknown_pct:.1f}%)
            </span>
        </div-->
        """, unsafe_allow_html=True)
            
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Unique Authors", f"{total_unique_authors:,}")
        m2.metric("Female Authors", f"{female_unique:,}", f"{female_pct:.1f}% of authors", delta_color="normal")
        m3.metric("Male Authors", f"{male_unique:,}", f"{male_pct:.1f}% of authors", delta_color="normal")
        m4.metric("Unclassified / Initials", f"{unknown_unique:,}", f"{unknown_pct:.1f}% unclassified", delta_color="off")
        m5.metric("Articles with ≥1 Woman", f"{articles_with_female:,}", f"{female_art_pct:.1f}% of papers", delta_color="normal")

    st.divider()

    # 4. Interactive Tabs Structure
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Demographic Distribution",
        "✂️ Career Progression & 'Scissors Effect'",
        "🧠 Thematic Profile",
        "📂 Author Directory & Exports"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Demographic Distribution
    # -------------------------------------------------------------------------
    with tab1:
        st.markdown("<h4 style='font-size:17px; font-weight:700; color:#1E293B;'>Gender Distribution & Authorship Composition</h4>", unsafe_allow_html=True)
        
        c_t1_left, c_t1_right = st.columns([1, 1], gap="medium")
        
        with c_t1_left:
            b_hdr1, b_hdr2 = st.columns([0.65, 0.35], vertical_alignment="center")
            with b_hdr1:
                st.markdown("<div style='font-size:14px; font-weight:700; color:#1E293B;'>Unique Authors by Gender</div>", unsafe_allow_html=True)
            with b_hdr2:
                if filter_known_only:
                    df_bar_export = pd.DataFrame({
                        'Gender': ['Male', 'Female'],
                        'Unique Authors': [active_male, active_female],
                        'Percentage': [active_male_pct, active_female_pct]
                    })
                else:
                    df_bar_export = pd.DataFrame({
                        'Gender': ['Male', 'Female', 'Unknown / Ambiguous'],
                        'Unique Authors': [male_unique, female_unique, unknown_unique],
                        'Percentage': [male_pct, female_pct, unknown_pct]
                    })
                _download_button(df_bar_export, "Download CSV", "authors_by_gender.csv", key="dl_gender_authors_bar")

            # Bar chart of unique authors
            if filter_known_only:
                fig_bar = go.Figure(go.Bar(
                    x=['Male Authors', 'Female Authors'],
                    y=[active_male, active_female],
                    marker_color=['#2563EB', '#EC4899'],
                    text=[f"{active_male:,} ({active_male_pct:.1f}%)", f"{active_female:,} ({active_female_pct:.1f}%)"],
                    textposition='auto',
                    hovertemplate="<b>%{x}</b>: %{y:,} authors (%{text})<extra></extra>"
                ))
                fig_bar.update_layout(
                    title=dict(text="Absolute Number of Unique Authors by Gender", font=dict(size=14)),
                    yaxis=dict(title="Number of Authors"),
                    margin=dict(l=20, r=20, t=20, b=20),
                    height=320
                )
                st.plotly_chart(fig_bar, width='stretch')
                st.caption(f"Showing confirmed Male & Female authors ({active_total_authors:,} individuals, representing {corpus_rep_pct:.1f}% of all {total_unique_authors:,} unique authors).")
            else:
                fig_bar = go.Figure(go.Bar(
                    x=['Male Authors', 'Female Authors', 'Unknown / Ambiguous'],
                    y=[male_unique, female_unique, unknown_unique],
                    marker_color=['#2563EB', '#EC4899', '#94A3B8'],
                    text=[f"{male_unique:,} ({male_pct:.1f}%)", f"{female_unique:,} ({female_pct:.1f}%)", f"{unknown_unique:,} ({unknown_pct:.1f}%)"],
                    textposition='auto',
                    hovertemplate="<b>%{x}</b>: %{y:,} authors<extra></extra>"
                ))
                fig_bar.update_layout(
                    title=dict(text="Absolute Number of Unique Authors by Gender Category", font=dict(size=14)),
                    yaxis=dict(title="Number of Authors"),
                    margin=dict(l=20, r=20, t=20, b=20),
                    height=320
                )
                st.plotly_chart(fig_bar, width='stretch')
                st.caption("Counts unique individuals across the analyzed corpus.")

        with c_t1_right:
            # Authorship composition donut chart
            if filter_known_only:
                # Exclude Unknown / Unclassified and No Authors to show classified team structures only
                classified_articles_df = articles_df[~articles_df['composition'].isin(['Unknown / Unclassified', 'No Authors'])].copy()
                comp_counts = classified_articles_df['composition'].value_counts()
                pie_title = f"Authorship Composition by Team Structure (Known Genders Only, n={len(classified_articles_df):,})"
            else:
                comp_counts = articles_df['composition'].value_counts()
                pie_title = "Authorship Composition by Gender & Team Structure"

            p_hdr1, p_hdr2 = st.columns([0.65, 0.35], vertical_alignment="center")
            with p_hdr1:
                st.markdown("<div style='font-size:14px; font-weight:700; color:#1E293B;'>Team Structure Breakdown</div>", unsafe_allow_html=True)
            with p_hdr2:
                df_comp_export = pd.DataFrame({
                    'Team Structure': comp_counts.index,
                    'Article Count': comp_counts.values
                })
                _download_button(df_comp_export, "Download CSV", "authorship_composition.csv", key="dl_gender_team_comp")

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

            if comp_counts.empty:
                st.info("No articles with classified gender composition available.")
            else:
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
                    margin=dict(l=20, r=20, t=20, b=20), 
                    height=400, 
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
                active_comp_df = classified_articles_df if filter_known_only else articles_df
                comp_summary = pd.DataFrame({
                    'Category': comp_counts.index,
                    'Articles': comp_counts.values,
                    'Percentage': (comp_counts.values / len(active_comp_df) * 100).round(1) if len(active_comp_df) > 0 else 0
                })
                st.dataframe(comp_summary, hide_index=True, width='stretch')

        st.divider()

        # Temporal Evolution Over the Years
        st.markdown("<h4 style='font-size:16px; font-weight:700; color:#1E293B;'>Temporal Evolution of Authors by Gender</h4>", unsafe_allow_html=True)
        
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

            if filter_known_only:
                yearly_stats['Total_Known'] = yearly_stats['Male'] + yearly_stats['Female']
                yearly_stats['Female_Pct'] = (yearly_stats['Female'] / yearly_stats['Total_Known'] * 100).fillna(0)
                yearly_stats['Male_Pct'] = (yearly_stats['Male'] / yearly_stats['Total_Known'] * 100).fillna(0)
                yearly_stats['Unknown_Pct'] = 0.0
            else:
                yearly_stats['Total_Authors'] = yearly_stats['Male'] + yearly_stats['Female'] + yearly_stats['Unknown']
                yearly_stats['Female_Pct'] = (yearly_stats['Female'] / yearly_stats['Total_Authors'] * 100).fillna(0)
                yearly_stats['Male_Pct'] = (yearly_stats['Male'] / yearly_stats['Total_Authors'] * 100).fillna(0)
                yearly_stats['Unknown_Pct'] = (yearly_stats['Unknown'] / yearly_stats['Total_Authors'] * 100).fillna(0)

            t_hdr1, t_hdr2 = st.columns([0.7, 0.3], vertical_alignment="center")
            with t_hdr1:
                mode_toggle = st.radio("", ["Normalized Percentage Distribution (%)", "Absolute Counts (Number of Authors)"], horizontal=True, label_visibility="collapsed")
            with t_hdr2:
                _download_button(yearly_stats, "Download Yearly Stats CSV", "gender_temporal_evolution.csv", key="dl_gender_temporal_stats")

            if "Percentage" in mode_toggle:
                fig_time = go.Figure()
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Female_Pct'], name='Female Authors (%)', marker_color='#EC4899'))
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Male_Pct'], name='Male Authors (%)', marker_color='#2563EB'))
                if not filter_known_only:
                    fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Unknown_Pct'], name='Unknown (%)', marker_color='#CBD5E1'))
                fig_time.update_layout(
                    barmode='stack',
                    yaxis=dict(title="Percentage (%)", range=[0, 100]),
                    xaxis=dict(title="Publication Year", dtick=1, tickformat="d"),
                    title="Normalized Gender Percentage Distribution Over Time" + (" (Known Genders Only)" if filter_known_only else ""),
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
            else:
                fig_time = go.Figure()
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Male'], name='Male Authors', marker_color='#2563EB'))
                fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Female'], name='Female Authors', marker_color='#EC4899'))
                if not filter_known_only:
                    fig_time.add_trace(go.Bar(x=yearly_stats['year_clean'], y=yearly_stats['Unknown'], name='Unknown Authors', marker_color='#CBD5E1'))
                fig_time.update_layout(
                    barmode='group',
                    yaxis=dict(title="Total Author Appearances"),
                    xaxis=dict(title="Publication Year", dtick=1, tickformat="d"),
                    title="Absolute Number of Author Appearances by Year" + (" (Known Genders Only)" if filter_known_only else ""),
                    height=400,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
            st.plotly_chart(fig_time, width='stretch')

    # -------------------------------------------------------------------------
    # TAB 2: Career Progression & The Scissors Effect
    # -------------------------------------------------------------------------
    with tab2:
        st.markdown("<h4 style='font-size:17px; font-weight:700; color:#1E293B;'>Mentee vs. Advisor Positions (The 'Scissors Effect')</h4>", unsafe_allow_html=True)
        
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

            sc_hdr1, sc_hdr2 = st.columns([0.7, 0.3], vertical_alignment="center")
            with sc_hdr1:
                st.markdown(f"<div style='font-size:15px; font-weight:700; color:#1E293B;'>Career Progression Dynamics ({gender_target_view})</div>", unsafe_allow_html=True)
            with sc_hdr2:
                _download_button(year_role_stats, "Download CSV", "gender_scissors_effect.csv", key="dl_gender_scissors_stats")

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
                title=f"First vs. Last Author Representation Over Time ({gender_target_view})",
                xaxis=dict(title="Publication Year", dtick=1, tickformat="d"),
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
    # TAB 3: Thematic Profile
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
                kw_h1, kw_h2 = st.columns([0.65, 0.35], vertical_alignment="center")
                with kw_h1:
                    st.markdown(f"<div style='font-size:14px; font-weight:700; color:#1E293B;'>Top 20 Main Topics ({chart_subtitle})</div>", unsafe_allow_html=True)
                with kw_h2:
                    _download_button(kw_df.sort_values('Occurrences', ascending=False), "Download CSV", "gender_topics_keywords.csv", key="dl_gender_topics_kw")

                fig_kw = px.bar(
                    kw_df,
                    x='Occurrences',
                    y='Topic / Keyword',
                    orientation='h',
                    color_discrete_sequence=kw_bar_color
                )
                fig_kw.update_layout(height=460, margin=dict(l=20, r=20, t=10, b=20))
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
            default_g_filter = "All (Known Only)" if filter_known_only else "All"
            filter_options = ["All (Known Only)", "female", "male"] if filter_known_only else ["All", "female", "male", "unknown"]
            gender_filter = st.selectbox("Filter Gender", filter_options, index=0)

        display_authors = authors_df.copy()
        if filter_known_only:
            display_authors = display_authors[display_authors['gender'].isin(['male', 'female'])]
        if search_q.strip():
            display_authors = display_authors[
                display_authors['full_name'].str.contains(search_q, case=False, na=False) |
                display_authors['first_name'].str.contains(search_q, case=False, na=False)
            ]
        if gender_filter in ["female", "male", "unknown"]:
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
            st.download_button(
                "Authors (.csv)", 
                data=csv_authors, 
                file_name=fn_authors, 
                icon=":material/download:", 
                width="stretch",
                on_click=_save_export_on_click,
                args=("exports", "Authors_Assessed.csv", csv_authors, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )
            
        with exp_col2:
            csv_articles = articles_df.to_csv(index=False).encode('utf-8-sig')
            fn_articles = format_timestamped_filename("LibAssessed_Gender.csv")
            st.download_button(
                "Articles (.csv)", 
                data=csv_articles, 
                file_name=fn_articles, 
                icon=":material/download:", 
                width="stretch",
                on_click=_save_export_on_click,
                args=("exports", "LibAssessed_Gender.csv", csv_articles, "wb"),
                help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
            )

        with exp_col3:
            if not valid_years_df.empty:
                csv_yearly = yearly_stats.to_csv(index=False).encode('utf-8-sig')
                fn_yearly = format_timestamped_filename("Gender_Yearly_Report.csv")
                st.download_button(
                    "Yearly (.csv)", 
                    data=csv_yearly, 
                    file_name=fn_yearly, 
                    icon=":material/download:", 
                    width="stretch",
                    on_click=_save_export_on_click,
                    args=("exports", "Gender_Yearly_Report.csv", csv_yearly, "wb"),
                    help=f"Saves directly to Projects/{get_active_project_name()}/exports/ and downloads"
                )
            else:
                st.button("Yearly (.csv)", disabled=True, width="stretch")

        with exp_col4:
            if gender_cache:
                cache_json = json.dumps(gender_cache, ensure_ascii=False, indent=2).encode('utf-8')
                fn_cache = format_timestamped_filename("gender_cache.json")
                st.download_button(
                    "Cache (.json)", 
                    data=cache_json, 
                    file_name=fn_cache, 
                    icon=":material/download:", 
                    width="stretch",
                    on_click=_save_export_on_click,
                    args=("sessions", "gender_cache.json", cache_json, "wb"),
                    help=f"Saves directly to Projects/{get_active_project_name()}/sessions/ and downloads"
                )
            else:
                st.button("Cache (.json)", disabled=True, width="stretch")

        with exp_col5:
            audit_text = st.session_state.get('last_gender_audit_log', '')
            if audit_text:
                fn_log = format_timestamped_filename("gender_audit_report.log")
                audit_bytes = audit_text.encode('utf-8')
                st.download_button(
                    "Audit Log", 
                    data=audit_bytes, 
                    file_name=fn_log, 
                    icon=":material/description:", 
                    width="stretch",
                    on_click=_save_export_on_click,
                    args=("logs", "gender_audit_report.log", audit_bytes, "wb"),
                    help=f"Saves directly to Projects/{get_active_project_name()}/logs/ and downloads"
                )
            else:
                st.button("Audit Log", disabled=True, width="stretch", icon=":material/description:")

        with exp_col6:
            if st.button("Open Folder", icon=":material/folder_open:", width="stretch", key="btn_open_gender_folder", help="Opens active project folder"):
                open_project_folder("exports")
