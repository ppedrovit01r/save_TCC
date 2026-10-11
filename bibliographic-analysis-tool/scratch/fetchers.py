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
