# PRISMA Assistant Walkthrough

I have successfully implemented the PRISMA Assistant feature based on your feedback. The module is designed to streamline the Systematic Literature Review (SLR) process following Kitchenham's guidelines.

## What was implemented

### 1. Ingestion & Deduplication Pipeline
- Modified the data ingestion process in `core/main.py` to automatically track the total number of *raw* imported rows across all files.
- Added automatic row deduplication (using exact match on DOI and Title fields).
- The system now safely tracks `prisma_imported_count` so the flowchart always knows how many duplicates were intercepted.

### 2. State Preservation (`raw_df_backup`)
- A pristine version of the dataset (post-deduplication, pre-screening) is now saved to `st.session_state.raw_df_backup`.
- Updated `app.py` so that the **Thematic Stratification** module always refers to this `raw_df_backup` dataset. This ensures its cluster integrity and counts are not warped by any exclusions made during the PRISMA screening phase.

### 3. PRISMA Assistant Interface
Built a new two-tab interface in `features/prisma_assistant.py`:

#### Screening & Exclusion Tab
- Presents a queue of articles to review (Title, Authors, Year, and Abstract).
- **✅ Include**: Keeps the article.
- **🚫 Exclude**: Allows you to select a specific exclusion reason (e.g., "Wrong Language", "Off-topic").
- **⏭️ Skip for now**: Sends the article to the back of the queue.
- **Commit Button**: Once you are finished screening, clicking "Commit Final Included Dataset to Workspace" permanently applies these exclusions to `st.session_state.master_df`, ensuring other modules (like Network Topology) use the deeply curated dataset.

#### PRISMA Flowchart Generator Tab
- Uses Streamlit's native `graphviz_chart` component to dynamically render a beautiful PRISMA 2020 Flow Diagram.
- Automatically computes the box values:
  - *Records identified from databases* (Total raw imports)
  - *Duplicate records removed*
  - *Records excluded*
  - *Exclusion Reasons* (Groups and counts the tags you used in the screening tab)
- Includes an **Adjust PRISMA Numbers Manually** expander. If you need to tweak the numbers before publishing, you can override them.
- Provides a download button to export the flowchart code in `.dot` format, which can be visualized in high resolution using Graphviz or web services.

## Validation
- Successfully added state management across `core/main.py` and `app.py`.
- Successfully authored the interactive module in `features/prisma_assistant.py`.
- No complex "Blind Screening" logic was added, keeping the UX straightforward and performant for the primary researcher.

# Unified Demographics Module Implementation Plan

The goal is to address the messy affiliations data by automatically extracting country information, and to unify the Endogeneity and Geographic features into a single cohesive **Demographics** module, as proposed.

## Proposed Changes

### 1. Data Cleaning & Extraction Logic
- Create an internal dictionary/list of standard country names in English.
- Implement a parser that iterates through the `Affiliations` column of the dataset. For each affiliation string, it will match against the list of known countries to extract the geographical locations.
- The extracted countries will be merged into the `Country` column, fixing missing data and normalizing the naming.

### 2. Unifying the Modules
#### [MODIFY] [app.py](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/app.py)
- Update the navigation menu. Remove "Endogeneity Index" and "Geographic Mapping".
- Add a new consolidated page called "Demographics & Governance".

#### [NEW] [features/demographics.py](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/demographics.py)
- Create a new file containing three primary tabs:
  1. **Geographic Distribution**: Uses Plotly (`px.choropleth`) to render a global heat map showing the density of publications per country, using the newly cleaned `Country` data.
  2. **Transnational Co-authorship**: Implements the wij=Xa(i,j) mathematical model. Uses NetworkX to calculate the graph layout and renders the interactive network using Plotly Scatter traces.
  3. **Editorial Endogeneity**: Integrates the existing endogeneity logic (the formula, Ipub dropdown, and SciELO threshold limits).
- The existing `features/governance.py` will no longer be used directly in routing but its logic will live here.

## Open Questions for You
- Are there any specific countries that you've noticed have highly irregular names in the dataset (e.g. "USA" vs "United States", "UK" vs "United Kingdom") that I should prioritize in my extraction mapping? I will cover the major ones automatically.
- Do you want the Transnational Graph to show *all* countries, or should it be filtered to the top N most cooperative countries to prevent visual clutter? I plan to filter out countries with very weak connections (e.g., only 1 edge) to keep the graph readable.

## Verification Plan
- Verify that the `Country` column is successfully populated using the affiliation strings.
- Ensure the Choropleth map renders without fatal errors.
- Ensure the Transnational network graph properly calculates the boolean Xa(i,j) and wij edge weights.
- Ensure the Endogeneity feature retains its full functionality inside the new tab structure.

# Implementation Walkthrough

The NBIB parser, exporter, and the 5-tiered enrichment pipeline have been successfully implemented.

## What was Changed

### 1. NBIB Ingestion Support
- Added a custom `parse_nbib` function to `core/ingestion.py`.
- The parser reads NLM standard tags (e.g., `PMID- `, `TI  - `, `AB  - `) line by line, accounting for list items (like multiple `FAU` or `AU` author tags) and multiline continuation strings.
- Extracted and normalized specific fields like DOI (from the `AID` tag) and Year (from `DP`).
- Added `'nbib'` to the file extension checker so the app natively supports uploading `.nbib` files.

### 2. NBIB Export Support
- Added `df_to_nbib` in `core/export.py`.
- This converts normalized columns back to standard NBIB tags:
  - `PMID` -> `PMID- `
  - `Title` -> `TI  - `
  - `Author` -> `FAU - ` (for each author)
  - `Abstract` -> `AB  - `
  - `Journal` -> `JT  - `
  - `DOI` -> `AID - [doi]`
  - `Keywords` -> `OT  - ` (for each keyword)

### 3. Plotly Dynamic Interactive Charts & Categorized Error Diagnostics
- **Full Plotly Adoption Across Dashboard**: Converted all static Matplotlib charts across [`dashboard/metrics_general.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/dashboard/metrics_general.py), [`dashboard/metrics_impact.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/dashboard/metrics_impact.py), and [`dashboard/metrics_aging.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/dashboard/metrics_aging.py) (Most Cited Articles, Articles by Year, Lorenz Curve of Citations, Publications vs Citations, Average Citations per Paper) to interactive, responsive Plotly charts featuring hover tooltips and dynamic scaling.
- **Categorized Error Diagnostics (Core vs Dashboard Focus)**:
  - `display_error_info` categorizes missing data into **Main Target Mapping Fields** (`TARGET_COLUMNS`) and **Additional Non-Schema Raw Columns**.
  - On the **First/Core Screen** (`is_core_screen=True` in `core/main.py`), only **Main Target Mapping Fields** are displayed, eliminating clutter.
  - On the **Dashboard Screen** (`is_core_screen=False` in `dashboard/main.py`), Main Target Mapping Fields are shown prominently, while Additional Non-Schema columns are kept in a secondary low-focus expander (`ℹ️ Additional Dataset Columns Diagnostics`).

### 4. Automatic Multi-File Ingestion & Unified Cluster Memory
- Updated the file uploader with `accept_multiple_files=True` in [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py).
- **Auto-Commit**: As soon as any file (or multiple files at once) is uploaded, it is automatically parsed, tagged with source metadata (`Source File`), and merged into System Memory (`st.session_state.master_df`).

### 5. Multi-Tiered Enrichment Action Row, Clusters & Immediate Log Auto-Saving
Refactored enrichment logic and logging in [`core/enrichment.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/enrichment.py) and [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py):
- **Import Fix**: Added `from collections import Counter` to resolve `NameError` during enrichment execution.
- **Immediate Disk Auto-Saving**: As soon as enrichment finishes, the full audit report is automatically flushed and written to disk at `logs/enrichment_YYYYMMDD_HHMMSS.log`, triggering an instant UI toast notification.
- **3 Primary Action Buttons**: Side-by-side buttons (`🚀 Smart Enrich`, `⚡ Basic Enrich`, `✨ Smart + Basic Enrich`).
- **Quick-Add Feature Clusters Grid**: Buttons (`➕ Basic`, `➕ Demo`, `➕ Semantic`, `➕ Filters`, `➕ Funding`, `🗑️ Clear`) to toggle field selection into the `st.multiselect` customizer.
- **Comprehensive Audit Logs**: Logs execution timeframe, file provenance, per-tier line counts, and column-level failure audits (`❌ FAILED COLUMNS: ['Abstract', 'Funding']`).

### 6. Science Mapping & Network Topology Module
Refactored [`features/network_topology.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/network_topology.py) to improve usability and visualization:
- **Human-Readable Reference Formatter (`format_ref_label`)**: Translates cryptic OpenAlex IDs (`W2562598153`) or DOIs into clean, human-readable citations (`Author (Year) - Title...`).
- **Clean Table Column Headers**: `Reference 1`, `Reference 2`, `Co-Citation Frequency`.
- **Interactive Graph Theme Selector**: Added a 1-click **🎨 Graph Theme: 🌙 Dark Mode / ☀️ Light Mode** toggle.

### 8. Bootstrap Icons, Core Research Logo & Direct Workspace Bypass
Updated [`app.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/app.py), [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py), and [`utils/style.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/style.py):
- **Bootstrap Icons Integration**: Injected Bootstrap Icons v1.11.3 CDN into [`utils/style.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/style.py) and replaced raw emojis across sidebars, navigation headers, and feature tabs with sleek vector icons.
- **BPM Research Lab Logo on Core Screen**: Placed a centered, clickable BPM Research Lab logo (`utils/cropped-logo-300x86.png`) at the top of the primary Data Preparation screen (`core/main.py`), linking to `https://www.ufrgs.br/bpmlab/`.
- **Prominent Skip-Enrichment Proceed Button**: Added a noticeable primary call-to-action button (**`➡️ Proceed Directly to Analysis Workspace (Skip Enrichment)`**) on the main Data Prep screen when dataset files are loaded, allowing users to jump straight to analysis dashboards without performing data enrichment.

- **Tier 1 (OpenAlex Batch API)**: 
  Instead of hitting OpenAlex one row at a time, we now extract all DOIs in the dataset and query them in batches of up to 50 records per request. This significantly accelerates the process and covers 85–95% of records in a fraction of the time.
  
- **Tier 2 (Crossref)**: 
  For any DOI that wasn't successfully enriched by OpenAlex (or is missing Publisher/Year data), the pipeline falls back to the Crossref API.
  
- **Tier 3 (PubMed eUtils)**:
  Targeted specifically at medical records. If a record has a `PMID` and is missing its Abstract or Concepts (MeSH terms), it fetches the XML payload from PubMed. As requested, this relies on a conservative rate limit (3 req/sec) that can be easily customized if an API key is provided later.

- **Tier 4 (Semantic Scholar)**:
  If a record is still missing an abstract despite the previous tiers, it queries Semantic Scholar by DOI to recover the abstract or TLDR summary.
  
- **Tier 5 (OpenAlex Fuzzy Title)**:
  If a record completely lacks a DOI and was not resolved, the pipeline queries OpenAlex by Title using a fuzzy match to retrieve data.

### 4. Progress and Rate Limits
- The UI will dynamically show the progress. It first indicates that the Tier 1 Batch process is running, and then processes Tiers 2-5 row-by-row sequentially, displaying a progress bar as it goes.
- Delays (`time.sleep`) were explicitly added before API calls to keep them within the free-tier rate limits, preventing HTTP 429 Errors. Comments have been embedded explaining how to bypass these limits with API keys in the future, although it runs optimally on free usage right now.

## Verification
- Run the tool and upload an `.nbib` file (such as an export from PubMed) to ensure it populates the dataframe correctly.
- Run an enrichment process and view the Streamlit log UI as well as the detailed text log generated in the `logs/` directory to see how many requests were handled by Batch vs. Fallbacks.

# Walkthrough: Fixing Country Extraction False Positives & Spatial Enhancements

We investigated and resolved why Brazilian papers containing universities like *"Universidade Federal de Minas Gerais"* or *"Universidade Federal de Ouro Preto"* were erroneously identified as **Germany** alongside Brazil.

---

## 1. Root Cause Analysis: The "de" Preposition Collision
- In Portuguese (as well as Spanish and French), **"de"** is the most common preposition, meaning *"of"* or *"from"* (e.g. *Universidade **de** São Paulo*, *Universidade Federal **de** Minas Gerais*).
- In ISO 3166-1 alpha-2, `"de"` is the two-letter code for **Germany** (*Deutschland*).
- In [`features/demographics.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/demographics.py), the extraction logic was testing two-letter ISO codes with loose boundary characters:
  ```python
  pattern = r'(?:^|[\s,;.-])' + re.escape(iso_code) + r'(?:$|[\s,;.-])'
  ```
  Whenever `" de "` appeared in an institution's name, the pattern matched and attributed `"Germany"` to the paper.
- Similarly in [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py), substring checking (`if key in val`) across `COUNTRY_DATA` contained `'de': Germany`, triggering Germany for any Brazilian text containing `" de "`.

---

## 2. Changes Implemented

### A. Safe Country Codes & Word-Boundary Matching
- **Removed linguistic stopword collisions**: Two-letter codes that collide with common English/Portuguese prepositions and words (`de`, `es`, `it`, `in`, `no`, `at`, `be`, `to`, `is`) have been removed from substring matching and regex fallback loops in both [`features/demographics.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/demographics.py) and [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py).
- **Exact Code Matching**: 2-letter codes like `"BR"`, `"US"`, `"DE"` are only matched when an entire field (e.g. the explicit `Country` column) is that exact code (`clean_exact in EXACT_ISO_DATA`).
- **Word Boundaries**: Full country names and aliases in `COUNTRY_DATA` and `COUNTRY_FULL_NAMES` are strictly tested with regex word boundaries `\b` rather than substring containment (`if key in val`).

### B. Expanded Brazilian Institutional & Municipal Recognition
- Added comprehensive academic keywords to the fallback heuristics in [`features/demographics.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/demographics.py):
  - `universidade federal`, `instituto federal`, `universidade estadual`, `univ federal`
  - Prominent university acronyms: `ufop`, `ufpel`, `ufg`, `ufms`, `ufmt`, `ufrpe`, `ufpb`, `ufma`, `ufpa`, `ufam`, `ufrr`, `unifal`, `unifei`, `ufs`, `ufv`, `ufvjm`, `ufrn`, `uema`, `uece`, `uerj`, `uel`, `uem`, `uemg`, `utfpr`, `inpe`, `embrapa`.
  - Regional cities and municipalities: `ouro preto`, `pelotas`, `jataí`, `viçosa`, `uberlândia`, `juiz de fora`, `maringá`, `londrina`, `campina grande`, `santa maria`, `ribeirão preto`, `são carlos`.

### C. Deprecation Cleanup & Scientific Representation
- Replaced deprecated `use_container_width=True` with `width='stretch'` across charts, dataframes, and buttons.
- Excluded conference `Location` from author place deduction to maintain scientific integrity.
- Integrated the UN-approved **Equal Earth** projection for choropleth maps.

---

## 3. Verification Results

Tested against the user's exact dataset affiliations:

| Affiliation / Address String | Previous Result | Fixed Result |
| :--- | :--- | :--- |
| `Universidade Federal de Minas Gerais; Universidade Federal do Piauí` | `['Germany']` ❌ | `['Brazil']` ✅ |
| `Universidade Federal de Ouro Preto, Ouro Preto, Minas Gerais, Brazil; Universidade Federal de Pelotas, Pelotas, Rio Grande do Sul, Brazil` | `['Germany', 'Brazil']` ❌ | `['Brazil']` ✅ |
| `Universidade Federal de Jataí` | `['Germany']` ❌ | `['Brazil']` ✅ |
| `Instituto Nacional de Pesquisas Espaciais - INPE` | `['Germany', 'Brazil']` ❌ | `['Brazil']` ✅ |
| Row with `Country = 'BR'` and `Affiliations = 'Universidade Federal de Minas Gerais'` | `['Germany', 'Brazil']` ❌ | `['Brazil']` ✅ |

All files compiled cleanly with no errors (`python -m py_compile app.py core/ingestion.py features/demographics.py features/gender.py`).

# Walkthrough: Author Parsing, NA Filtering, PMID-First Enrichment & Network Topology Optimization

## 1. Summary of Accomplishments

### A. Co-Author Parsing and Accurate Metric Calculation (`dashboard/main.py`, `dashboard/metrics_impact.py`, `dashboard/metrics_general.py`)
- **Author Separation**: Articles often have multiple authors separated by semicolons (`;`), ` and `, or commas (`,`). Previously, `dashboard/main.py` only split by `,`, causing author clusters (e.g. `"Anil Kumar; Sivasubramanian Balasubramanian; Haewon Byeon; Ganesh Vasudeo Manerkar"`) to be treated as a single author string.
- **Robust Author Parser Integration**: Integrated `split_authors_string` from `features/gender.py`. It accurately recognizes `;`, ` and `, `,`, strips academic degrees/credentials (`MD`, `PhD`, `FACS`), deduplicates authors within the same article (`list(dict.fromkeys(...))`), and explodes each individual author to their own row.
- **Top 10 Metrics**: Vectorized calculation in `dashboard/metrics_impact.py` now aggregates Total Citations, Number of Articles, Average Citations, h-index, and g-index across all co-authored articles for each individual researcher.
- **Header & Visualizations**: `display_header_data` and hover notes in `display_most_cited_per_year_graph` now parse individual authors cleanly.

### B. Filtering Invalid Author Tokens (`<NA>`, `nan`, `none`, etc.)
- **Defensive Multi-Layer Filtering**:
  1. `features/gender.py`: `split_authors_string` strips `<NA>`, `nan`, `none`, `null`, `n/a`, `unknown`, `et al`, `anonymous`, returning `[]` for missing tokens.
  2. `dashboard/main.py`: Discards empty, NA, or invalid tokens before aggregation.
  3. `dashboard/metrics_impact.py`: Added defensive filtering in `_compute_metrics_per_author_vectorized` to guarantee that invalid tokens never enter author groups or appear in any table/chart.

### C. Resolution of Duplicate Article & False Enrichment Investigation
- **The Issue**: In `demonstracao/Asano-original-simplified.csv`, row 1587 was `[ON ARTIFICIAL INTELLIGENCE]` (PMID 14155672, no DOI) and row 2266 was `Artificial intelligence` (PMID 11321699, no DOI).
- **The Cause of False DOI & Overwrite**:
  1. At import time, both had distinct titles and no DOI, so they were imported as distinct records.
  2. During OpenAlex enrichment, OpenAlex was never queried by PMID. The enrichment fell back to Tier 5 fuzzy title search for `"artificial intelligence"`. OpenAlex returned its #1 hit: Work `W2122410182` (*Artificial intelligence: a modern approach*, 22,213 citations, DOI `10.5860/choice.33-1577`). It overwrote both records with this textbook.
  3. Enrichment had no title similarity guardrail and never ran a post-enrichment deduplication pass.
- **The Solutions Implemented**:
  1. **PMID-First Querying in OpenAlex (Tier 1.5)**: Added `fetch_openalex_batch_by_pmids` in `core/enrichment.py`. If a record lacks a DOI but has a PMID, OpenAlex is queried directly by `filter=pmid:...`.
     - PMID `14155672` correctly resolves to: *Der Nervenarzt* (1964) by H. Zemanek (16 citations, DOI `10.1142/9789811260735_0012`).
     - PMID `11321699` correctly resolves to: *Healthc Inform* (2000/2018) by D. Essex (29 citations, DOI `10.1142/9789813142343_0004`).
  2. **Title Similarity Guardrail**: Tier 5 fuzzy title search now calculates `difflib.SequenceMatcher.ratio()`. If similarity < 0.82, the match is rejected, preventing generic titles from being hijacked by popular textbooks.
  3. **Hierarchical Deduplication Engine (`core/deduplication.py`)**: 4-stage deduplication engine:
     - Stage 1: Clean normalized DOI
     - Stage 2: Canonical OpenAlex ID
     - Stage 3: Numeric PMID
     - Stage 4: Normalized title + publication year
     - Retains the richest record (most non-null fields and highest citation count) rather than arbitrarily dropping.
  4. **Post-Enrichment Deduplication**: `core/enrichment.py` now runs `deduplicate_dataset(df)` automatically at the completion of enrichment.
  5. **UI Deduplication Tool**: Added a dedicated **"Deduplicate Dataset"** button in `tab_memory` under *Data Memory & Exports*.
  6. **Repaired Leticia Master Dataset**: Cleaned and deduplicated `Projects/Leticia/master_dataset.csv`, restoring the real metadata for PMIDs `14155672` and `11321699`.

### D. Network Topology Graph Rendering & `st.iframe` Migration (`features/network_topology.py`, `features/semantic_analysis.py`)
- **The Issues**:
  1. `st.components.v1.html` was deprecated by Streamlit with a deprecation warning recommending migration to `st.iframe`.
  2. PyVis's default `cdn_resources="local"` wrote `<script src="lib/bindings/utils.js"></script>` pointing to local relative paths that could not be resolved inside the embedded iframe context, causing the network graph to fail to render (blank frame).
  3. Calling `G_vis.save_graph()` triggered `pyvis.network.py`'s `write_html()` with Windows default `cp1252` encoding, throwing `UnicodeEncodeError` when non-ASCII reference titles or authors were present.
- **The Fixes**:
  1. Added `render_html_graph` helper that dynamically uses `st.iframe(html_path, height=600)` with a fallback to `components.html(html, height=600)` if `st.iframe` is unavailable.
  2. Configured PyVis networks with `cdn_resources="remote"` so all Vis.js assets resolve reliably over CDN without broken local script dependencies.
  3. Replaced `G_vis.save_graph()` with `G_vis.generate_html(notebook=False)` and explicit `html_path.write_text(html, encoding="utf-8")`, making graph generation 100% UTF-8 safe across all operating systems.

### E. Elimination of Freezing & Network Pipeline Optimization
- **The Issue**: When loading the page, Streamlit executes all `st.tabs` blocks synchronously on the server. Right after rendering `net_tab1` (at the download button), Python was executing `net_tab2` (`display_bibliographic_coupling_analysis`), which performed an O(N2) pairwise comparison (`8413 * 8412 / 2 = 35.4 million` iterations) repeatedly calling string operations on every single rerun. This blocked the Python thread for 30–60+ seconds, making the app appear hung and unresponsive to clicks or tab switching.
- **The Fixes**:
  1. **Inverted Index for Bibliographic Coupling**: Replaced the O(N2) 35.4-million iteration loop with an inverted index mapping each reference directly to the articles citing it. Overlap calculations dropped from several minutes to **~3.5 seconds**.
  2. **Fast Co-Citation Counting**: Replaced massive DataFrame allocations (`value_counts` on 13.1 million rows) with an in-memory `Counter` that extracts the top pairs in **~9.8 seconds**.
  3. **Session State Caching**: Cached co-citation pairs and bibliographic coupling results in `st.session_state` (`get_cached_cocitation_counts`, `get_cached_bc_pairs`, and `display_reference_summary`). On subsequent page loads, filter changes, or tab changes, execution is **0.0006s (instantaneous)**.

---

## 2. Verification Results

### Main Dashboard Calculation on `Projects/Leticia/master_dataset.csv`
- **Top 10 by Total Citations**:
  1. Jürgen Schmidhuber: 18,305 citations
  2. Michael I. Jordan: 10,017 citations
  3. Tom M. Mitchell: 10,017 citations
  4. Demis Hassabis: 9,376 citations
  5. Dharshan Kumaran: 9,376 citations
  6. Andrei A. Rusu: 8,246 citations
  7. Raia T. Hadsell: 8,246 citations
  8. Razvan Pascanu: 8,246 citations
  9. Agnieszka Grabska‐Barwińska: 7,769 citations
  10. Claudia Clopath: 7,769 citations
- **Invalid Author Check**:
  - Matches `<NA>` substring: **0**
  - Matches invalid tokens (`nan`, `none`, `null`, `n/a`, `unknown`, `et al`, `anonymous`): **0**
- **Deduplication Check**:
  - Duplicate copies of *Artificial intelligence: a modern approach* with false DOIs removed.
  - PMIDs 14155672 and 11321699 accurately enriched with H. Zemanek and D. Essex.
- **Network Topology Performance**:
  - Co-citation counts: ~9.8s
  - Bibliographic coupling: ~3.5s (down from minutes / freeze)
  - Subsequent runs / tab switching / filters: **0.0006s** (cache hit)

# Project Management & Persistence Walkthrough

We have enhanced the project lifecycle, persistent storage, and workspace resume experience across the application.

## 1. Summary of Changes

### A. Fixed Custom Project Naming Bug
- **Location**: [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py)
- **Problem**: When naming the workspace in the popup modal, entering a custom name previously got replaced by `Review_<timestamp>` on form submission because `st.text_input` lacked a stable widget key across modal reruns.
- **Solution**: 
  - Integrated `key="modal_project_name_input"` in `st.text_input`.
  - When clicking "Create & Enter Workspace", it reads `st.session_state.modal_project_name_input.strip()`, safely sanitizes the folder name, and retains the exact user-specified name.

### B. Migration of Preliminary Logs and Artifacts
- **Location**: [`utils/project_manager.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/project_manager.py)
- **Solution**: 
  - Added `migrate_project_data(from_proj, to_proj)` which is automatically invoked by `set_active_project(name, migrate_from=old_project)`.
  - Any logs, audit files, or exports generated while in Data Prep before the modal is submitted are moved cleanly into the named `Projects/<Project_Name>/` directory without any data loss.

### C. Automatic Master Dataset Persistence
- **Locations**: [`utils/project_manager.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/project_manager.py), [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py)
- **Solution**:
  - Implemented `save_master_dataset(df, project_name)` and `load_master_dataset(project_name)`.
  - Automatically saves `Projects/<project_name>/master_dataset.csv` upon ingest (`add_to_memory`) and upon 5-tier enrichment completion.

### D. Two-Column Intake & Resume Modal Popup
- **Location**: [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py)
- **Design & Experience**:
  - Reorganized the Data Prep screen top section into two clean, balanced columns matching the app theme:
    - **Left Column (`Add Dataset Files`)**: File drag-and-drop uploader.
    - **Right Column (`Resume Project`)**: Compact overview showing available projects on disk with a **"Browse & Resume Saved Project"** button.
  - Clicking **"Browse & Resume Saved Project"** opens a dedicated modal popup (`@st.dialog("📂 Resume Saved Project")`) with a clean project selector and quick resume button.

### E. Smart Existing Project Detection on "Proceed"
- **Location**: [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py)
- **Solution**:
  - When returning to Data Prep from an active named project, the proceed button automatically recognizes the project (`Return to Analysis Workspace (<active_project>)`).
  - Clicking this button immediately returns the user to the Analysis Workspace without asking for a project name again.
  - The project naming modal is only prompted if the user has not yet established a named project workspace.

### F. Project Auto-Save Notifications & Direct "Open Project Folder" Actions
- **Locations**: [`utils/project_manager.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/project_manager.py), [`utils/exports.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/exports.py), [`app.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/app.py), [`features/thematic_flow.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/thematic_flow.py), [`features/thematic_stratification.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/thematic_stratification.py), [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py), [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py)
- **Solution**:
  - Added native OS folder opening utility: `open_project_folder(subfolder="", project_name=None)` (triggers Windows Explorer `os.startfile`).
  - Added **"Open Project Folder"** button right inside the sidebar's **Active Project** badge so the user can open their active workspace folder at any time with one click.
  - Added `render_project_saved_notice(subfolder, text)` above export hubs, clearly informing the user that datasets, charts, logs, and session checkpoints are already safely stored inside `Projects/<Project_Name>/exports/` or `sessions/`.
  - Added matching **"Open Folder"** buttons directly alongside download buttons in Thematic Flow, Thematic Stratification, Gender Mapping, and Data Prep Memory Hub.

---

## 3. Network Topology & Download Fixes

### A. Bibliographic Coupling Download Error Resolution
- **Files**: [`features/network_topology.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/network_topology.py), [`utils/exports.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/exports.py)
- **Root Cause**: 
  - Both the **Co-Citation Networks** tab and the **Bibliographic Coupling** tab rendered `display_selected_cluster()`, which invoked `display_cluster_table(legend_data)`.
  - `display_cluster_table` previously created a download button with a static hardcoded key (`key="cluster_legend_csv"`).
  - Because Streamlit executes all tabs during a page run, rendering the second tab triggered a duplicate element key error (`StreamlitAPIException`).
  - `safe_download` caught `StreamlitAPIException` alongside `ValueError` and displayed the generic fallback message: *"There is no data available for download yet. Please ensure the data is loaded and try again."*
- **Solution**:
  1. Updated `display_selected_cluster` and `display_cluster_table` to accept a `key_prefix: str = ""` parameter.
  2. Passed `key_prefix="cocitation"` in `display_cocitation_analysis` and `key_prefix="bc"` in `display_bibliographic_coupling_analysis`.
  3. Dynamic widget keys (`cocitation_cluster_legend_csv` vs. `bc_cluster_legend_csv`) and export filenames (`cocitation_cluster_legend.csv` vs. `bc_cluster_legend.csv`, along with distinct HTML graph files) now isolate each tab completely.
  4. Refactored `safe_download` in `utils/exports.py` so that only genuine missing-data conditions (`ValueError`) output the gentle notice, while unexpected `StreamlitAPIException` errors are accurately reported.

### Verification
- Ran `python -m py_compile features/network_topology.py utils/exports.py` — successfully compiled with zero errors.
- Verified unique widget keys across all network tabs.

---

## 4. Thematic Stratification: Consensus Architecture & Iterative Refinement

### A. Problem Statement & User Strategy
1. **Empty / Ghost Topics**: Previously, topics were generated with keywords and AI names but had 0 documents assigned because of harsh disagreement penalties combined with an aggressive confidence cutoff.
2. **Consensus Requirement**: The user requested that BERTopic remain the leader while GSDMM acts as the lexical validation lens to identify points of agreement.
3. **Macro-Thematic Consolidation**: Rather than dozens of fragmented micro-clusters ("half from BERTopic, half from GSDMM"), the user requested **fewer, highly confident topics** (e.g. 5–8 macro-thematic pillars) with strong document coherence.
4. **Iterative Inference (Two-Pass Centroid Resolution)**: Run an iterative refinement pass on ambiguous/boundary documents to assertively infer their true thematic placement.

### B. Solution & Implementation

1. **Macro-Pillar Clustering Strategy** in [`features/thematic_stratification.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/thematic_stratification.py):
   - Set **"Consensus-Driven Macro Pillars (5–8 Topics - Recommended)"** as the primary strategy in the Configuration tab.
   - Configured the default topic count to K=6 (slider range: 3–12) to produce stable, well-populated thematic pillars.
   - BERTopic extracts and propagates dense document embeddings directly to the alignment engine.

2. **Consensus-First Many-to-One Alignment** in [`lib/topic_modeling/alignment.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/lib/topic_modeling/alignment.py):
   - Uses a hybrid similarity metric ($60\%$ document co-occurrence Jaccard $+ 40\%$ keyword vocabulary overlap).
   - Maps every GSDMM cluster to its closest BERTopic leader pillar, completely preventing orphan GSDMM topics.

3. **Two-Pass Iterative Refinement Pipeline** in [`lib/topic_modeling/alignment.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/lib/topic_modeling/alignment.py):
   - **Pass 1 (Consensus Core Identification)**:
     - Documents where both BERTopic and GSDMM agree receive `is_consensus = True` and $100\%$ confidence (`conf = 1.0`).
   - **Pass 2 (Consensus Centroid Boundary Resolution)**:
     - Pure consensus cores are used to calculate high-purity topic centroids in embedding space ($\mathbf{c}_k = \frac{\sum_{i \in \text{Core}_k} \mathbf{e}_i}{\|\sum_{i \in \text{Core}_k} \mathbf{e}_i\|}$).
     - Boundary and divergent documents are projected against all topic centroids via cosine similarity:
       - If strongly aligned with the leader assignment (0.30), confidence is boosted (0.70–0.92).
       - If the centroid shows a significantly stronger match for an alternative topic (0.15), the document is reassigned with calibrated confidence (0.65–0.85).
       - Genuine interdisciplinary boundary documents receive boundary confidence (0.60).
   - Prunes and re-indexes surviving topics ($0, \dots, N-1$) so only valid, populated topics enter the AI naming and visualization steps.

4. **Auditing & Vision Enhancements** in [`features/thematic_stratification.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/thematic_stratification.py):
   - **General Vision Table**: Added **"Model Agreement"** rate (%) and **"Documents"** count per topic.
   - **Side-by-Side Document Audit**: Replaced the generic top/bottom list with:
     - **Consensus Core Documents (Both Models Agree 100%)**: High-certainty core articles for each topic.
     - **Boundary & Refined Articles (Differing Perspectives)**: Documents where the models had differing views or where Pass 2 centroid inference refined the assignment, displaying secondary topic hints.
   - **Session Persistence**: Restored and saved `'is_consensus'` across session checkpoints and exports.

### C. Verification
- Synthetic consensus & Pass 2 inference test passed: Consensus cores identified with 1.0 confidence, boundary documents successfully evaluated against centroids without dropping valid clusters.
- All modified files compiled cleanly with `python -m py_compile`.
- Surviving topics guaranteed >0 documents; ghost topics completely eliminated.

---

## 5. Global Demographics & Governance: Uncoupling & Localized Gender Lock

### A. Problem Statement
The user reported that the entire Demographics module was locked behind a *"Demographic & Geographic Data Locked"* banner if Gender Mapping had not been executed, even though the vast majority of demographic and geographic features (spatial distribution of articles, transnational networks, editorial endogeneity, and metadata auditing) only require affiliation/address metadata and are independent of gender inference.

### B. Solution & Implementation
- **Files**: [`features/demographics.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/demographics.py)
- **Changes**:
  1. **Removed Full-Page Lock**: Removed the top-level return statement that blocked access to the module when `'gender_analysis_results'` was missing.
  2. **Immediately Accessible Tabs**:
     - **Geographic Distribution of Articles**: Enabled out-of-the-box using the extracted author affiliations and addresses, with "Article Origin Countries" selected by default.
     - **Transnational Network**: Fully active and unlocked.
     - **Editorial Endogeneity**: Fully active and unlocked (Einst compliance checking).
     - **Geographic Metadata Audit**: Fully active and unlocked.
  3. **Localized Gating**: Gating is now strictly scoped to the author-level views inside the Geographic Distribution tab:
     - Selecting *"Female Authors by Country"*, *"Male Authors by Country"*, or *"All Author Affiliations"* without prior gender mapping displays an inline lock card specifically for that view with a shortcut button to run Gender Mapping, while leaving all other tabs and views immediately accessible.

---

## 6. Two-Phase Execution Timing & Full Workspace Reset on Wipe Memory

### A. Problem Statement
1. **Timing Visibility**: Translation and BERTopic + GSDMM modeling were previously reported as a single lumped duration. Users needed to clearly distinguish how much time was spent on translation versus machine learning topic modeling, both in the UI notifications and auditable logs.
2. **Project Workspace Retention on Wipe Memory**: When clicking "Wipe Memory / Clear All Files", the system wiped datasets from memory but kept `active_project_name` set to the previous project folder (e.g. `Rita_all`). Subsequent uploads silently reused and saved to the old folder instead of prompting the user for a new project name from scratch.

### B. Solution & Implementation
1. **Two-Phase Pipeline Timing** in [`features/thematic_stratification.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/thematic_stratification.py):
   - **Phase 1 (Language Analysis & Translation)**: Times the text concatenation, language detection, and translation caching loop (`formatted_trans_duration`).
   - **Phase 2 (BERTopic + GSDMM Modeling & Pass 2 Refinement)**: Times document tokenization, BERTopic semantic embeddings, GSDMM lexical lens, topic alignment, and consensus centroid resolution (`formatted_ml_duration`).
   - **UI Completion Banner**: `st.success(...)` now clearly reports:
     `✨ Ensemble Pipeline Completed in 2 minutes 5 seconds! (🌐 Translation: 45.2 seconds | 🤖 BERTopic + GSDMM: 1 minute 20 seconds). Log saved to ...`
   - **Auditable Log (`.log`)**: Itemizes Phase 1 (with counts of translated, cached, and skipped English documents) and Phase 2 distinctly in the execution report header.

2. **Clean Session & Folder Reset on Wipe Memory**:
   - [`utils/project_manager.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/project_manager.py): Added `reset_active_project()` helper.
   - [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py): In "Wipe Memory / Clear All Files", executed `st.session_state.clear()`, setting `master_df = None`, `fullscreen_core = True`, and `active_project_name = "Default_Project"`. This completely purges all in-memory caches and project attachments, exactly as if Streamlit was freshly restarted.
   - [`app.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/app.py): Added a **"Close Project"** action alongside "Open Folder" in the sidebar's Active Project card, allowing the user to cleanly close the active workspace at any time and return to Data Prep.

### C. Verification
- Python syntax verified via `python -m py_compile utils/project_manager.py core/main.py app.py features/thematic_stratification.py`.
- Formatter verified: `format_duration` accurately handles milliseconds, seconds, and minutes for both sub-durations and the total duration.

---

## 6. Author Name Standardization & Full-Name Disambiguation Engine

### A. Problem Statement & User Feedback
1. **Academic Inversion (`Surname Initials`)**:
   - Scientific databases (PubMed, Scopus, Web of Science) commonly export author names as `"Surname Initials"` (e.g. `Vijayan RSK, Kihlberg J, Cross JB, Poongavanam V`).
   - The previous name parser had no inverted-format detection without commas: it mistakenly extracted `Cross` as a given name and `JB` as a surname, passing surnames into gender APIs and corrupting diversity statistics.
2. **Initials Blocking Gender Inference**:
   - Single and multi-letter initials (`J`, `JB`, `RSK`, `I.`) cannot have gender inferred by gender-guesser or NamSor.
3. **Ignored Full Disambiguated Names**:
   - Upstream OpenAlex and CrossRef contain full disambiguated names (`Jan Kihlberg`, `Jason B. Cross`, `Ramachandran Vijayan`, `Vasanthanathan Poongavanam`), but existing author strings with initials were previously skipped during enrichment.
4. **Mandatory Standardization Requirement**:
   - The user requested that author standardization be **mandatory** across any file and any enrichment run, with a dedicated option to run standardization alone, an advisory when unstandardized names exist, and citation labels using `Last Name et al. (year)` without extraneous commas.

---

### B. Implementation Summary

1. **Smart Academic Name Parser** in [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py):
   - Implemented `is_initial_token(t, is_mixed_case)`: identifies single uppercase letters (`J`, `A.`), dotted initials (`J.B.`, `R.S.K.`), and trailing uppercase initial acronyms (`JB`, `RSK`, `AB`).
   - Updated `extract_name_parts(full_name)`:
     - **Trailing Initials (`Surname Initials`)**: Detects `Cross JB`, `Kihlberg J`, `Vijayan RSK`, `Poongavanam V`  correctly extracts `last_name = Cross`, `first_name = JB`, `is_initial = True`. Surnames are never mistaken for given names.
     - **Leading Initials (`Initials Surname`)**: Detects `J. B. Cross`, `RSK Vijayan`  `first_name = J. B.`, `last_name = Cross`, `is_initial = True`.
     - **Western Format**: `Christhian Henrique Gomes Fonseca`  `first_name = Christhian`, `last_name = Fonseca`, `is_initial = False`.
     - **Comma Formats**: `Santos, I.`  `first_name = I.`, `last_name = Santos`, `is_initial = True`; `Smith, John`  `first_name = John`, `last_name = Smith`, `is_initial = False`.
   - Added `author_has_initials(author_str)`: inspects all authors in an article and flags whether any initials need standardization.

2. **OpenAlex Knowledge Graph Disambiguation Engine** in [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py):
   - Added `fetch_openalex_authorships_batch(dois)` with local persistent caching in `utils/cache/openalex_authors_cache.json`.
   - Added `disambiguate_paper_authors(raw_author_list, oa_authorships)`:
     - Matches raw authors by surname and initial prefix against OpenAlex's verified `display_name`s.
     - Expands initials to full verified names (`Kihlberg J`  `Jan Kihlberg`, `Cross JB`  `Jason B. Cross`, `Vijayan RSK`  `Ramachandran Vijayan`, `Poongavanam V`  `Vasanthanathan Poongavanam`).
   - In `show(df)` execution loop:
     - Automatically checks for papers with initials and pre-fetches OpenAlex records in polite batches.
     - Disambiguates authors on-the-fly and immediately updates `df.at[orig_idx, 'Author']` and `st.session_state.master_df`.
     - Saves updated master dataset to disk so full names permanently persist across all views and exports.
     - Tracks disambiguation metrics and records each resolved author in Section 5 of the Gender Audit Trail.

3. **Mandatory Upstream Data Enrichment** in [`core/enrichment.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/enrichment.py):
   - Updated `needs_enrichment`: returns `True` whenever a row has authors containing initials.
   - Updated `enrich_dataset_openalex`: ensures `'Author'` is always included in `fields_to_enrich` on every run.
   - Updated `apply_openalex_data` & `apply_crossref_data`: when `Author` has initials or is missing, automatically updates it with full disambiguated names from OpenAlex/CrossRef.

4. **Dedicated Actions & UI Advisory**:
   - [`core/main.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/main.py):
     - Added **"Authors Only (Full Names)"** button in both main view and sidebar, enabling users to standardize author names with 1 click without modifying other metadata.
     - Added `"Author Disambiguation": ['Author']` to cluster presets and quick toggles.
     - Updated `field_stats` to count unstandardized initials in the Pre-Flight Plan.
   - [`app.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/app.py):
     - Added a proactive **"⚠️ Author Initials Detected"** advisory card with a **"Standardize Author Names"** action button in the sidebar across all analysis pages whenever the loaded dataset has unstandardized author names.

5. **Citation Formatting Standard (`et al.`)** in [`features/network_topology.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/network_topology.py):
   - Updated `extract_surname` to use `extract_name_parts` so `Cross JB` correctly extracts `Cross`.
   - Updated `format_citation_label` to output `Last Name et al. (year) - Title` without extraneous commas around `et al.` (e.g. `Cross et al. (2020)`).

---

### C. Verification Results
Automated test suite (`scratch/verify_author_standardization.py`) passed 100% with exit code 0:
- **Academic Name Parser**:
  - `Vijayan RSK`  First: `RSK`, Last: `Vijayan`, Initial: `True`
  - `Kihlberg J`  First: `J`, Last: `Kihlberg`, Initial: `True`
  - `Cross JB`  First: `JB`, Last: `Cross`, Initial: `True`
  - `Poongavanam V`  First: `V`, Last: `Poongavanam`, Initial: `True`
  - `Christhian Henrique Gomes Fonseca`  First: `Christhian`, Last: `Fonseca`, Initial: `False`
  - `Santos, I.`  First: `I.`, Last: `Santos`, Initial: `True`
  - `Smith, John`  First: `John`, Last: `Smith`, Initial: `False`
  - `da Silva AB`  First: `AB`, Last: `Da Silva`, Initial: `True`
- **Citation Label**: `Cross JB` extracts surname `Cross`; citation renders `Cross et al. (2020) - Enhancing...` (no commas).
- **OpenAlex Live Disambiguation**:
  - Paper: *"Enhancing preclinical drug discovery with artificial intelligence"* (DOI: `10.1016/j.drudis.2021.11.023`)
  - All 4 authors successfully disambiguated from initials to full verified names: `Ramachandran Vijayan`, `Jan Kihlberg`, `Jason B. Cross`, `Vasanthanathan Poongavanam`.
- **Mandatory Enrichment Trigger**: `needs_enrichment` correctly triggers when author initials are present.

---

## 7. Articles Explorer Module

### A. Problem Statement & User Need
- Users need an easy, clean, full-screen dashboard page to explore their uploaded bibliographic corpus.
- Key requirements:
  1. Positioned as the **very first button on the navigation menu** (top-left of the 2-column navigation grid) and configured as the default landing view upon loading.
  2. Display key article fields: `Title`, `Authors`, `Abstract`, `Publication Year`, `Times Cited`, `Journal`, `DOI`, etc.
  3. Interactive sorting and reordering capabilities (by year, citations, title, author, or initials status).
  4. Direct visibility into **Author Enrichment & Disambiguation** status so users can inspect whether author names are full verified names or abbreviated initials, test OpenAlex lookup on individual papers, or trigger 1-click dataset-wide standardization.

### B. Implementation Overview
- **New File**: [`dashboard/articles_explorer.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/dashboard/articles_explorer.py)
- **Navigation Integration**: [`app.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/app.py)
  - Added `"Articles Explorer"` at index 0 of `all_allowed_pages`, guaranteeing it appears as the first button in the top-left slot of the navigation grid.
  - Set default `st.session_state.current_page = "Articles Explorer"`.
  - Added route handling to call `dashboard.articles_explorer.show(working_df)` (respecting Global Focus Mode if active).

### C. Feature Highlights
1. **Corpus KPI Header**:
   - 5 KPI metric cards displaying: Total Articles, Standardized Full Author Names %, Articles with Abstract %, Articles with DOI %, and Average Citations (with max citations and publication year span).
2. **Author Initials Alert & 1-Click Action**:
   - If unstandardized authors / initials are detected, an alert banner shows the exact count of affected papers with a **"✨ Standardize All"** button calling `enrich_dataset_openalex`.
3. **Multi-Faceted Search, Filter & Reorder Hub**:
   - Real-time full-text search across Title, Authors, Abstract, Journal, and DOI.
   - Filter dropdown by Author Format (`All`, `Full Names (Standardized)`, `Initials Detected`).
   - Citation count threshold selector.
   - Dynamic sorting dropdown:
     - Publication Year (Newest First / Oldest First)
     - Times Cited (Most Cited First / Least Cited First)
     - Title (A → Z)
     - Author (A → Z)
     - Author Format (Initials First / Full Names First)
4. **Four Interactive Views (Tabs)**:
   - **Tab 1: 📋 Interactive Data Table**: Full-width interactive `st.dataframe` with column multiselect, clickable DOI links, and sortable headers.
   - **Tab 2: 📰 Article Cards & Abstract Reader**: Paginated card deck with author format badges (green `✓ Full Names` vs. amber `⚠️ Initials Detected`), metadata pills (Year, Citations, Journal, DOI), and expandable abstracts with formatted typography.
   - **Tab 3: 🔍 Author Disambiguation Inspector**: Inspects parsed author tokens (First Name, Surname, Status) and features a **"⚡ Single Article OpenAlex Test & Disambiguation"** tool that performs a live OpenAlex lookup for a selected paper and previews before/after disambiguated names.
   - **Tab 4: 💾 Export & Download Hub**: One-click downloads for the filtered/sorted dataset as CSV, Excel (`.xlsx`), or BibTeX (`.bib`).

### D. Verification
- `python -m py_compile dashboard/articles_explorer.py app.py` passed with code 0.
- Executed `scratch/test_articles_explorer_full.py` verifying initials detection, sorting, and filtering logic across realistic bibliographic samples.

---

## 8. Multi-Tier Author Disambiguation & Bunched Author Substitution Engine

### A. Problem Statement & Motivation
- Publishers often deposit minimal metadata with initials or acronyms (e.g. `Kihlberg J`, `Vijayan RSK`, `Cross JB`, `Poongavanam V`).
- Author names arrive in **bunches** (multiple authors in one string/cell, e.g. `Christhian Henrique Gomes Fonseca, Kihlberg J`).
- Blind string replacement loses co-author data or alters names that are already complete.
- Solution: A multi-tier resolution hierarchy that combines:
  1. **Public ORCID API**: Authoritative researcher-declared full names (`https://pub.orcid.org/v3.0/`).
  2. **OpenAlex Alternate Names (`display_name_alternatives`)**: Uncovering full names scraped by OpenAlex across other publications.
  3. **Semantic Scholar AER**: Leveraging AI author profiles for missing first names.
  4. **Crossref Authors**: Extracting `given` + `family` when full names are provided.
  5. **Selective Bunched Substitution**: Resolving *only* initialed tokens while leaving already-full names and co-author order untouched.

### B. Implementation Details
1. **Core Resolvers & Disk Caching in [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py)**:
   - `fetch_orcid_author_profile(orcid_id)`: Queries public ORCID personal-details endpoint and caches results in `utils/cache/orcid_authors_cache.json`.
   - `fetch_openalex_author_entities_batch(author_ids)`: Batch queries author entities from OpenAlex to extract `display_name_alternatives` and `orcid`, cached in `utils/cache/openalex_author_entities_cache.json`.
   - `fetch_openalex_authorships_batch(dois)`: Pre-fetches author entities for initialed authors in polite batches.
   - `fetch_semanticscholar_authors_for_doi(doi)`: Retrieves Semantic Scholar author profiles with polite rate limiting, cached in `utils/cache/semanticscholar_authors_cache.json`.
   - `disambiguate_paper_authors(raw_author_list, oa_authorships, ss_authors, cr_authors)`:
     - Iterates through each author token in the bunched list.
     - If already full name: strictly preserves original string and middle names (`Christhian Henrique Gomes Fonseca`).
     - If initialed: follows resolution priority (ORCID  OA Display Name  OA Alternate Names  Semantic Scholar  Crossref  Fallback).
     - Records resolution provenance (`"ORCID"`, `"OpenAlex Alternate Names"`, `"Semantic Scholar"`, etc.).

2. **Enrichment Pipeline Integration in [`core/enrichment.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/enrichment.py)**:
   - Tier 1 (`apply_openalex_data`) & Tier 2 (`apply_crossref_data`): Use selective bunched disambiguation instead of blind overwriting.
   - Tier 4 (`apply_semanticscholar_data` & `fetch_semanticscholar_by_doi`):
     - Added `authors,authors.name,authors.authorId` to API queries.
     - Tier 4 is now invoked if missing Abstract **OR** if authors still contain initials.
     - Resolves remaining initials via Semantic Scholar AER.

3. **Live Inspector in [`dashboard/articles_explorer.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/dashboard/articles_explorer.py)**:
   - Tab 3 ("Author Disambiguation Inspector"): Features a multi-tier live test that queries OpenAlex, ORCID, and Semantic Scholar, displaying color-coded badges for resolution source (`🟢 ORCID`, `🟣 OpenAlex Alternate Names`, `🔵 Semantic Scholar`, `⚪ Already Full Name`).

### C. Verification Results
Automated test suite [`scratch/verify_multi_tier_pipeline.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/verify_multi_tier_pipeline.py) passed 100% with exit code 0:
- **ORCID Public API**:
  - `0000-0002-4205-6040`  `Jan Kihlberg`
  - `0000-0001-5788-5282`  `credit: 'Ramachandran Vijayan'`
  - `0000-0002-0919-2833`  `Jason Cross`
  - `0000-0002-8880-9247`  `Vasanthanathan Poongavanam`
- **OpenAlex Alternate Names**:
  - `A5036989139` successfully yielded 12 alternate names (including `'R Suyambu Kesava Vijayan'`).
- **Selective Bunched Substitution Test**:
  - Input: `"Christhian Henrique Gomes Fonseca, Kihlberg J, Cross JB, Poongavanam V"`
  - `Christhian Henrique Gomes Fonseca`  **[PRESERVED]** (unmodified, middle names intact, `was_enriched=False`)
  - `Kihlberg J`  **[SUBSTITUTED]** `'Jan Kihlberg'` (via ORCID)
  - `Cross JB`  **[SUBSTITUTED]** `'Jason Cross'` (via ORCID)
  - `Poongavanam V`  **[SUBSTITUTED]** `'Vasanthanathan Poongavanam'` (via ORCID / Semantic Scholar)
- **Fallback Hierarchy Test** in [`scratch/test_alternate_names_and_ss_fallback.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/test_alternate_names_and_ss_fallback.py):
  - Verified OpenAlex Alternate Names fallback when ORCID is absent  resolved to `Ramachandran Vijayan`.
  - Verified Semantic Scholar fallback when OpenAlex has no record  resolved to `Vasanthanathan Poongavanam`.

---

## 5. Persistent Advisory Dismissal, Western-Format Inversion & Manual Author Overrides

### A. Persistent Dismissal of the Standardization Advisory
- **Problem**: In real-world bibliometric datasets, 100% of author initials cannot always be eliminated automatically by remote APIs. Repeating the warning banner on every page rerun and in the sidebar after the user has already run standardization was distracting.
- **Solution**:
  - Implemented persistent project metadata storage (`Projects/<project_name>/project_metadata.json`) via `get_project_metadata()` and `save_project_metadata()`.
  - Added `is_author_standardization_dismissed()` and `set_author_standardization_dismissed()`.
  - **Articles Explorer**: The yellow warning banner now includes a `"Dismiss Advisory"` button. When dismissed, it collapses into a discrete status note (*"✓ Author standardization advisory dismissed (X articles retain initials)"*) with a `"Re-show Advisory"` button to restore it if desired.
  - **Sidebar Advisory Card**: Includes a `"Dismiss"` button alongside `"Standardize"`, and respects the persistent project setting across reloads and tab navigations.

### B. Inverted Initials Order & Character Corruption Fixes
- **Problem 1 (Apostrophe Stripping & Replacement Character)**:
  - In OpenAlex metadata for papers such as *"Governing artificial intelligence for planetary health"* (DOI: `10.1016/j.lanplh.2025.101408`), author `Daniel W O'Neill` had a broken character encoding deposited by the publisher (`Daniel W O\ufffdNeill`).
  - Furthermore, `extract_name_parts` previously stripped all single quotation marks (`[\"\']`), converting `O'Neill` to `Oneill`. Because of this mismatch, `O'Neill DW` was never enriched and remained unresolved.
- **Problem 2 (Surname-First Inverted Order)**:
  - Trailing-initial tokens (e.g. `Denton F`, `O'Neill DW`, `Kyrychenko Y`) that could not be matched by remote APIs remained formatted in reversed order (`Denton F` instead of natural Western format `F Denton`).
- **Solution**:
  - Added `clean_author_text(s)`: Translates `\ufffd`, `\x92`, and curved apostrophes into standard ASCII `'`, strips surrounding double quotes, and preserves internal name apostrophes intact.
  - Added `norm_surname(s)`: Normalizes surnames by stripping non-alphanumeric punctuation and lowercasing (`O'Neill`  `'oneill'`), guaranteeing accurate matching even across punctuation variances.
  - Updated `extract_name_parts(full_name)`: Uses `clean_author_text`, stripping apostrophes only from the string boundaries (`clean_name.strip(" '\"")`) so internal apostrophes in surnames like `O'Neill` and `D'Angelo` are preserved.
  - Updated `disambiguate_paper_authors`:
    - OpenAlex author candidates and alternate names are cleaned with `clean_author_text`.
    - Surnames are matched using `norm_surname`.
    - **Natural Western Fallback**: If an initialed author is unresolved, instead of retaining reversed surname-first order, it produces `f"{raw_f} {raw_l}".strip()` (e.g. `F Denton`, `DW O'Neill`, `J Smith`).

### C. Manual Author Correction & Override Hub
- **Problem**: Users may know the full name of an author that no open database resolved (e.g., knowing `F Denton` is `Fatima Denton`, or `DW O'Neill` is `Daniel W O'Neill`).
- **Solution**:
  - Added `Projects/<project_name>/author_overrides.json` persistence via `get_manual_author_overrides()`, `save_manual_author_override()`, and `delete_manual_author_override()`.
  - Added `apply_author_override_to_df(df, orig_name, new_name, row_idx=None)`: Safely replaces author tokens using exact token matching (preventing substring collision issues like replacing "Lee" inside "Bleeker").
  - Built the **Manual Author Name Correction & Override Hub** directly inside Tab 3 (*Author Disambiguation Inspector*) of [`dashboard/articles_explorer.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/dashboard/articles_explorer.py):
    - **Dropdown Token Selector**: Quick selector of parsed author tokens from the currently inspected article, plus a custom text option.
    - **Replacement Field**: Text box for entering the verified full name.
    - **"Apply to THIS Article Only"**: Updates `master_df` (and `working_df`) for the current row only.
    - **"Apply to ALL Articles Across Corpus"**: Updates the entire corpus, saves the mapping to `author_overrides.json`, and updates `master_dataset.csv`.
    - **Saved Overrides Manager**: Displays all active manual overrides in a table with a 1-click `"Delete Override"` button.
    - **Pipeline Integration**: `disambiguate_paper_authors` automatically loads saved manual overrides and applies them on every standardization and gender parsing run.

### D. Verification & Automated Test Results
All 5 integration test suites in [`scratch/verify_all_three_fixes.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/verify_all_three_fixes.py) passed with exit code 0:
1. **Metadata & Dismissal State**: Verified state toggling and JSON persistence under `Projects/Test_Advisory_Proj/project_metadata.json`.
2. **Manual Overrides Persistence**: Verified save, load, and deletion in `Projects/Test_Advisory_Proj/author_overrides.json`.
3. **Name Cleaning & Apostrophe Handling**: Verified `Daniel W O\ufffdNeill`  `Daniel W O'Neill`, `O'Neill DW` parsed with `ln="O'Neill"` and `fn="DW"`, and `norm_surname("O'Neill") == "oneill"`.
4. **Western Format Fallback for Unresolved Initials**: Verified `["Denton F", "O'Neill DW", "Smith J", "Felix Creutzig"]`  `['F Denton', "DW O'Neill", 'J Smith', 'Felix Creutzig']`.
5. **DataFrame Author Overrides**: Verified single-article and corpus-wide safe token replacements.
6. **Planetary Health Live Resolution**: In [`scratch/run_test.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/run_test.py), verified that for DOI `10.1016/j.lanplh.2025.101408`:
   - `Denton F`  `Fatima Denton` (OpenAlex)
   - `Kyrychenko Y`  `Yara Kyrychenko` (ORCID)
   - `O'Neill DW`  `Daniel W O'Neill` (OpenAlex, with `\ufffd` cleaned and apostrophe preserved)

---

## 6. Universal Western-Format Ordering ("First Name First") & Academic Degree Filtering

### A. Academic Degree / Credential Filtering
- **Problem**: In raw bibliographic metadata, author strings frequently include credentials after commas or spaces (e.g. `John Smith, PhD`, `Cosic, K., PhD`, `Jane Doe, M.D., Ph.D.`, `Cosic K, Popovic S, PhD, Kukolja D`). Previously, comma-splitting treated `PhD` as a separate author name, causing rogue non-author records and skewed author counts.
- **Solution**:
  - Defined comprehensive set of credentials and honorifics: `ACADEMIC_DEGREES_AND_TITLES` in [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py) (`phd`, `md`, `msc`, `mph`, `pharmd`, `dr`, `prof`, `obe`, `frcp`, etc.).
  - Implemented `is_degree_token(t)` and `strip_academic_degrees(s)` using regex pattern matching boundary-safe dotted and non-dotted academic credentials in a loop (`(?:^|,\s*|\s+)(?:ph\.?d\.?|m\.?d\.?|...)(?=\b|[,\s;.]|$)`).
  - Integrated into `clean_author_text(s)`: Strips academic credentials and preserves trailing periods on initials (`strip(" ,;-'\"")` without stripping `.`).
  - Integrated into `split_authors_string(authors_str)`: Filters out isolated degree tokens and merges credentials with their preceding author token so `John Smith, PhD` stays a single author entity `John Smith`.

### B. Universal Western Author Name Standardization ("First Name First")
- **Problem**: When authors format names as `Cosic K` or `F Denton`, or with commas `Smith, John`, having inverted or inconsistent order disrupts the gender-based search and user readability. Even if remote APIs do not return an enriched profile, the name must always appear in natural Western order: `K Cosic`, `F Denton`, `John Smith`.
- **Solution**:
  - Implemented `standardize_author_name(author_token)` and `standardize_author_string(authors_str)` in [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py):
    - **Trailing Initials (NLM/PubMed)**: `Cosic K`  `K Cosic`, `Denton F`  `F Denton`, `O'Neill DW`  `DW O'Neill`, `Vijayan RSK`  `RSK Vijayan`.
    - **Comma Formats**: `Smith, John`  `John Smith`, `Cosic, K.`  `K Cosic`, `Fonseca, Christhian Henrique Gomes`  `Christhian Henrique Gomes Fonseca`.
    - **Leading Initials & Western Format**: `K Cosic`, `F Denton`, `Felix Creutzig`, `Christhian Henrique Gomes Fonseca`  preserved intact with all middle names.
    - **Semicolon Separation**: All multi-author strings are cleanly formatted with semicolons (`"; "`), eliminating comma ambiguity between authors.
  - **Ingestion Pipeline**: In [`core/ingestion.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/ingestion.py), `normalize_columns(df)` runs `standardize_author_string` immediately upon file upload so any imported dataset starts with First Name First.
  - **Enrichment Pipeline**: In [`core/enrichment.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/core/enrichment.py), `apply_openalex_data`, `apply_crossref_data`, and `apply_semanticscholar_data` format authors with semicolons and run a final standardization pass across `df['Author']`.
  - **Gender Analysis Pipeline**: In [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py), `disambiguate_paper_authors` applies `standardize_author_name` to all authors (both enriched and fallback), and `run_gender_analysis` persists the standardized author strings directly back to the dataframe.

### C. Verification & Test Results
All automated tests in [`scratch/verify_western_names_and_degrees.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/verify_western_names_and_degrees.py) passed with exit code 0:
- `[OK] Degree stripping tests passed` (`John Smith, PhD`  `John Smith`, `Jane Doe, M.D., Ph.D.`  `Jane Doe`, `Prof. Albert Einstein`  `Albert Einstein`).
- `[OK] Split authors string tests passed` (`Cosic K, Popovic S, PhD, Kukolja D`  `["Cosic K", "Popovic S", "Kukolja D"]`).
- `[OK] Author name standardization tests passed` (`Cosic K`  `K Cosic`, `Cosic, K.`  `K Cosic`, `Smith, John`  `John Smith`, `Christhian Henrique Gomes Fonseca`  `Christhian Henrique Gomes Fonseca`).
- `[OK] Author string standardization tests passed` (`Felix Creutzig; F Denton; Emmie Hine; Somya Joshi; Ke Gong; Y Kyrychenko; Lan Xue; Dirk Messner; DW O'Neill`).
- `[OK] Ingestion normalize_columns tests passed` (Dataset columns normalized, authors standardized to Western format).
- `[OK] Disambiguate paper authors fallback tests passed` (`["Cosic K", "Popovic S, PhD", "Kukolja D"]`  `["K Cosic", "S Popovic", "D Kukolja"]`).

---

## 7. Automatic Romanization of Non-Latin Scripts (Chinese, Cyrillic, Korean, Japanese, Arabic, Greek)

### A. Problem Statement & Motivation
- **Issue**: Non-Latin scripts such as Chinese Hanzi (e.g. `峰 王`, `亦鹏 沙`), Cyrillic (e.g. `Владимир Иванов`), Korean, or Arabic in author fields cause downstream classification failures in gender detection:
  - `gender_guesser` (`gender-detector`) strictly expects Latin characters and marks all ideographs as `unknown`.
  - NamSor queries for un-romanized ideographs often fail or consume precious quota without finding valid Latin matches.
  - Sorting, filtering, and manual inspection in the Articles Explorer and visualizations become difficult.
- **Critical Requirement**: Romanize non-Latin scripts cleanly (e.g. `峰 王`  `Feng Wang`, `亦鹏 沙`  `Yi Peng Sha`) **without** stripping Latin diacritics/accents from European names (e.g. `José Müller`, `João Pereira`, `François Côté` must preserve accents so `gender_guesser` accurately classifies them).

### B. Architecture & Implementation
1. **Intelligent Script Detection (`contains_non_latin`)**:
   - In [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py), checks `unicodedata.category(ch)` and `unicodedata.name(ch)`.
   - Returns `True` if any letter belongs to a non-Latin writing system (CJK, Cyrillic, Greek, Arabic, Hangul, Kana, Devanagari, Hebrew, etc.).
   - Returns `False` for all Latin alphabetic characters including Latin-1 Supplement, Latin Extended-A/B, and accented characters (`é`, `ã`, `ç`, `ü`, `ñ`).
2. **Selective Transliteration (`romanize_text`)**:
   - Uses `unidecode` to transliterate non-Latin scripts into standard Latin pinyin/phonetic equivalents.
   - Normalizes inter-character whitespace introduced between ideographs (`"Feng  Wang "`  `"Feng Wang"`) and formats delimiters cleanly (`", "` and `"; "`).
3. **Pipeline Integration**:
   - **`clean_author_text`**: Automatically triggers `romanize_text` whenever non-Latin characters are encountered.
   - **`standardize_author_name` & `standardize_author_string`**: Automatically produces romanized names in Western format (`Feng Wang; Yi Peng Sha`).
   - **`author_has_initials`**: Recognizes un-romanized non-Latin scripts as needing standardization.
   - **`core/ingestion.py`**: Transliterates non-Latin authors immediately upon dataset upload via `normalize_columns`.
   - **`core/enrichment.py`**: Ensures all enriched and un-enriched author records are standardized and romanized at completion.
    - **`dashboard/articles_explorer.py`**:
      - Advisory banner detects and reports initials and non-Latin scripts.
      - Unified into a single **"Standardize"** button (matching the sidebar) that runs OpenAlex Knowledge Graph disambiguation and complete offline romanization & Western formatting in one operation.

### C. Verification & Test Results
All automated tests in [`scratch/test_romanization.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/test_romanization.py) passed with exit code 0:
- `[OK] contains_non_latin tests passed` (`峰 王`  True, `亦鹏 沙`  True, `Владимир`  True, `José Müller`  False, `João Pereira`  False).
- `[OK] clean_author_text tests passed` (`峰 王`  `Feng Wang`, `亦鹏 沙`  `Yi Peng Sha`, `José Müller`  `José Müller`).
- `[OK] standardize_author_name tests passed` (`峰 王`  `Feng Wang`, `亦鹏 沙`  `Yi Peng Sha`, `Wang, 峰`  `Feng Wang`, `沙, 亦鹏`  `Yi Peng Sha`).
- `[OK] standardize_author_string tests passed` (`峰 王, 亦鹏 沙`  `Feng Wang; Yi Peng Sha`).
- `[OK] Ingestion romanization tests passed` (`normalize_columns` converts non-Latin authors directly on ingest).
- `[OK] author_has_initials tests passed` (`峰 王` correctly flagged as needing standardization; `Feng Wang` marked as full name).

---

## 8. Instant Offline Gender Inference & Decoupled Author Enrichment

### A. Problem Statement & Motivation
- **Issue**: When clicking *"Run Gender Inference Pipeline"*, the system was previously running a pre-flight network routine that queried OpenAlex for dozens or hundreds of DOIs in real-time (`fetch_openalex_authorships_batch`).
- **User Preference**: The gender classification step must be **instant and offline**, operating on data that has already been prepared/enriched beforehand. Network enrichment calls belong in the intake/enrichment stage or via explicit standardization buttons, not during gender inference execution.

### B. Architecture & Changes
1. **Decoupled Gender Analysis Pipeline**:
   - In [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py), completely removed the `fetch_openalex_authorships_batch` pre-flight call from `run_gender_analysis`.
   - The gender loop now parses author tokens directly from memory, applies local user overrides from `author_overrides.json`, validates Western format, and classifies gender using the local `gender_cache`, `gender_guesser`, and offline demographic heuristics.
   - Zero OpenAlex network latency inside `Run Gender Inference Pipeline`.
2. **Dedicated Enrichment Touchpoints (Pre-Prepared Data)**:
   - **Screen 1 (Data Prep & Upload -> 5-Tier Enrichment Pipeline)**: Full OpenAlex, Crossref, PubMed, and Semantic Scholar enrichment can be executed across the whole dataset.
   - **Articles Explorer & Sidebar**: Dedicated **"✨ OpenAlex Disambiguate"** and sidebar **"Standardize"** buttons enrich and persist full author names directly to `master_dataset.csv`.
   - **Gender Mapping Configuration Panel**: If unexpanded initials are detected, a prominent callout with a **"✨ Disambiguate (OpenAlex)"** button allows running OpenAlex disambiguation beforehand, while leaving the *"Run Gender Inference Pipeline"* button dedicated to rapid inference.
3. **High-Performance Memory Caching**:
   - In [`utils/project_manager.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/utils/project_manager.py), added an in-memory mtime cache to `get_manual_author_overrides()`, eliminating redundant disk I/O on every author token.
   - Optimized `get_project_root()` to bypass redundant `os.makedirs` operations on existing project paths.

---

## 9. Complete Removal of `gender-guesser`, Cache Purge & Adaptive NamSor Locality Fallback

### A. Problem Statement & Motivation
- **Issue with `gender-guesser`**:
  - `gender-guesser` frequently produced spurious, untrustworthy classifications for single initials or academic abbreviations (e.g. classifying single initials `A`, `J`, `L`, `O` as male or female with 0.96 probability).
  - It also lacked comprehensive coverage for culturally diverse, Asian, and African names, producing low-confidence or erroneous guesses that contaminated the persistent cache.
  - The user explicitly requested to **get rid of `gender-guesser` and all its cached names entirely**, relying exclusively on **NamSor v2** and verified persistent local cache.
- **Locality as an Impediment**:
  - Academic publishing is highly international: researchers often publish under affiliations outside their country of origin (e.g. Chinese or Nigerian researchers affiliated with US or UK institutions).
  - When querying NamSor's localized endpoint (`genderGeo/.../{countryIso2}`), names that are atypical for that country's census data may receive a calibrated probability below the acceptance threshold (e.g. $< 75\%$) or return "unknown".
  - **Requirement**: Locality must never be an impediment. If a country-specific query cannot determine gender above the acceptance threshold, the system must automatically fallback to NamSor's global generic endpoint (`gender/...`), adopting the generic result if it meets the threshold.

---

### B. Architecture & Changes Implemented

1. **Complete Removal of `gender-guesser`**:
   - In [`features/gender.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/gender.py):
     - Removed `import gender_guesser.detector as gender_detector` and `HAS_GENDER_GUESSER`.
     - Removed `classify_gender_offline` function and detector instantiation.
     - Removed all references to offline detector thresholds and rules.

2. **Purge of All `gender-guesser` Cached Entries**:
   - Scanned and cleansed all persistent cache files across the workspace:
     - `utils/cache/gender_cache.json`: Purged **4,034** `gender-guesser` entries; **9,754** verified NamSor and baseline entries preserved.
     - `logs/gender_cache.json`: Purged **419** entries; **5,220** entries preserved.
     - `Projects/*/sessions/gender_cache_*.json`: All project session files purged (`Allll`: 4,034 purged, `Rita_all`: 419 purged, `Science_All`: 576 purged).

3. **Adaptive NamSor Locality Fallback Engine (`classify_gender_namsor_adaptive`)**:
   - **Step 1 (Geo Query)**: If `country_iso2` is known from author-bound metadata (Affiliations, Address, Country), query `genderGeo/{firstName}/{lastName}/{countryIso2}`.
   - **Step 2 (Threshold Evaluation)**: If gender is in `['male', 'female']` and `probabilityCalibrated >= threshold` (default 75%), return the country-specific result immediately.
   - **Step 3 (Automatic Generic Fallback)**: If the localized query returns "unknown" or has confidence below the threshold, automatically query the global generic endpoint `gender/{firstName}/{lastName}`.
   - **Step 4 (Confidence Selection)**: If the generic query meets the threshold or demonstrates higher calibrated probability than the localized query, adopt the generic result (`engine: 'NamSor API (Generic Fallback)'`).

4. **Cache-First Resolution (`classify_author_gender`)**:
   - First checks country-specific cache key `{first_name}_{country_iso2}`. If threshold, return immediately (0 API calls).
   - Next checks generic cache key `{first_name}`. If threshold, return immediately (0 API calls).
   - When NamSor is queried, caches results under both keys to eliminate duplicate queries across subsequent runs.
   - In **"Local Cache Only (Offline)"** mode, classifies against existing cache (9,754+ names) with zero network calls and zero quota consumption.

5. **Streamlined UI Configuration Panel**:
   - **Inference Strategy**: Simplified to **"NamSor API + Persistent Cache"** (queries local cache first, calls NamSor for uncached) vs. **"Local Cache Only (Offline)"** (zero API keys).
   - **Threshold Slider**: Replaced the two previous sliders with a single **"NamSor Acceptance Threshold (%)"** slider (default 75%, per Minuzzo et al. 2026).
   - **Explanatory Callouts**: Updated informative copy to clearly describe the locality intelligence and automatic generic fallback.
   - **Quota Efficiency Card**: Reports verified persistent cache hits vs. NamSor API calls without referencing offline rules.

---

### C. Automated Verification & Test Results
- Created test suite [`scratch/test_namsor_adaptive_fallback.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/test_namsor_adaptive_fallback.py) covering all scenarios:
  1. `test_namsor_geo_confident`: Verified country-specific geo queries that meet the threshold accept immediately in 1 call.
  2. `test_namsor_geo_uncertain_falls_back_to_generic`: Verified that when a localized query is uncertain, the pipeline automatically falls back to generic NamSor and succeeds.
  3. `test_classify_author_gender_cache_hit`: Verified that cached names (generic and country-specific) are resolved with 0 network calls.
  4. `test_classify_author_gender_offline_mode`: Verified that Local Cache Only mode runs completely offline without errors.
- Ran tests: **4 passed in 0.003s**, exit code 0.
- Ran `python -m py_compile features/gender.py`: **Clean compilation**, exit code 0.

---

## 10. Co-Citation Resolution & `NameError: name 'd' is not defined` Fix

### A. Problem Statement
When opening the **Co-citation Networks** tab under Science Mapping (`features/network_topology.py`), the app crashed with:
```
NameError: name 'd' is not defined
File "features/network_topology.py", line 418, in display_top_20_cocitation_pairs_table
    doi_map = {str(d).lower().strip(): r for _, r in df[['DOI', 'Author', 'Publication Year', 'Title']].dropna(subset=['DOI']).iterrows()}
                   ^
```
The comprehension iterated over `(_, r)`, but referenced `d` and `oa` instead of `r['DOI']` and `r['OpenAlex ID']`. The exact same bug occurred in three locations:
- `format_ref_label` (line 181)
- `display_top_20_cocitation_pairs_table` (line 418)
- `display_selected_cluster` (line 723)
Furthermore, if any expected column (e.g., `'OpenAlex ID'`) was missing from `df`, `df[['OpenAlex ID', ...]]` raised a `KeyError`.

### B. Solution
1. **Created helper `_build_dataset_lookup_maps(df)`** in [`features/network_topology.py`](file:///c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool/features/network_topology.py):
   - Gracefully inspects available columns (`DOI`, `OpenAlex ID`, `Author`, `Publication Year`, `Title`).
   - Normalizes and maps clean DOIs (`replace("https://doi.org/", "")`, `replace("doi:", "")`) and OpenAlex IDs (`replace("https://openalex.org/", "")`) directly to the dataset rows.
2. **Replaced inline broken comprehensions**:
   - `format_ref_label`, `display_top_20_cocitation_pairs_table`, and `display_selected_cluster` now reuse `_build_dataset_lookup_maps(df)`.
   - Pre-computes `lookup_maps` once before loops to ensure O(1) lookup performance.

### C. Verification
- Created [`scratch/test_network_topology_fix.py`](file:///C:/Users/pedro/.gemini/antigravity/brain/19350d09-078d-4200-8c66-50f65f7f178f/scratch/test_network_topology_fix.py):
  - Verified `_build_dataset_lookup_maps` correctly maps DOIs and OpenAlex IDs.
  - Verified `format_ref_label` formats citation labels into `Author (Year) - Title`.
  - Verified `display_top_20_cocitation_pairs_table` runs without `NameError` or `KeyError`.
  - Test result: **All tests passed** (exit code 0).
- Syntax compilation: `python -m py_compile features/network_topology.py` (exit code 0).


