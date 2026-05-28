import streamlit as st
import tempfile
import os
import pandas as pd
import requests
import requests_cache

# 1. Cache Setup (Expires in 7 days)
CACHE_DIR = "/tmp" if os.name == 'posix' else tempfile.gettempdir()
requests_cache.install_cache(os.path.join(CACHE_DIR, 'openalex_cache'), expire_after=604800)

# Polite Pool Header (Replace with your actual email in production)
HEADERS = {'User-Agent': 'mailto:pedro.alexandre@inf.ufrgs.br'}

# Target standardized columns
TARGET_COLUMNS = [
    'Author', 'Title', 'Abstract', 'Article References',
    'Times Cited', 'Publication Year', 'DOI', 'Publisher', 'Keywords'
]

def show():
    st.title("Data Preparation & Upload")

    uploaded_file = st.file_uploader(
        "Upload the Excel file (.xlsx)",
        type=["xlsx"]
    )

    if uploaded_file is None:
        st.info("Please upload an Excel file to begin.")
        return

    # Read and Normalize Immediately
    try:
        df_raw = pd.read_excel(uploaded_file)
        df_normalized = normalize_columns(df_raw)
        
        st.write("Normalized Data Preview:")
        st.dataframe(df_normalized.head(3))
        
    except Exception as e:
        st.error(f"Error reading Excel file: {e}")
        return

    st.markdown("---")
    st.subheader("What do you want to do with this file?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 1. Use Directly")
        st.write("If your file already has citation and reference data, load it directly into memory.")
        if st.button("Load to Memory", use_container_width=True):
            st.session_state.master_df = df_normalized
            st.success("✅ File loaded into memory! You can now navigate to the Analysis tabs.")

    with col2:
        st.markdown("#### 2. Enrich with OpenAlex")
        operation = st.radio(
            "Choose the operation:",
            ["Fill ONLY missing DOIs (Fast)", 
             "Enrich ENTIRE Dataset (Full OpenAlex Search)"]
        )

        if st.button("Process and Load", use_container_width=True):
            with st.spinner("Processing via OpenAlex... This might take a while depending on dataset size."):
                try:
                    if operation == "Fill ONLY missing DOIs (Fast)":
                         df_processed = fill_missing_dois(df_normalized.copy())
                    else:
                         df_temp = fill_missing_dois(df_normalized.copy())
                         df_processed = enrich_dataset_openalex(df_temp)

                    # Save the processed DataFrame directly to the global memory vault!
                    st.session_state.master_df = df_processed

                    # Save to a temporary file for downloading
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_out:
                        output_path = tmp_out.name
                        df_processed.to_excel(output_path, index=False)

                    with open(output_path, "rb") as f:
                        result_bytes = f.read()

                    st.success("✅ Processing complete! Data saved to memory for analysis.")
                    st.download_button(
                        label="Download Processed Excel File",
                        data=result_bytes,
                        file_name="processed_openalex.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass

                except Exception as e:
                    st.error(f"An error occurred during processing: {e}")

# ---------------------------------------------------------
# Normalization Logic
# ---------------------------------------------------------
def normalize_columns(df):
    df.columns = df.columns.str.strip().str.replace(r'\s+', ' ', regex=True)
    cols_lower = df.columns.str.lower()
    
    column_mapping = {
        "authors": "Author",
        "author": "Author",
        "title": "Title",
        "article title": "Title",
        "abstract note": "Abstract",
        "abstract": "Abstract",
        "references": "Article References",
        "article references": "Article References",
        "cited references": "Article References",
        "publication year": "Publication Year",
        "year": "Publication Year",
        "times cited": "Times Cited",
        "citations": "Times Cited",
        "citation count": "Times Cited",
        "doi": "DOI",
        "publisher": "Publisher",
        "keywords": "Keywords",
        "author keywords": "Keywords"
    }
    
    new_cols = []
    for col in cols_lower:
        mapped_name = column_mapping.get(col)
        if mapped_name:
            new_cols.append(mapped_name)
        else:
            new_cols.append(col.title())
            
    df.columns = new_cols
    
    for col in TARGET_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
            
    return df

# ---------------------------------------------------------
# OpenAlex API Logic
# ---------------------------------------------------------
def search_doi_by_title(title):
    if pd.isna(title) or not str(title).strip():
        return None
        
    url = f"https://api.openalex.org/works?search={title}&per-page=1"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('results') and len(data['results']) > 0:
            result = data['results'][0]
            doi_url = result.get('doi')
            if doi_url:
                return doi_url.replace("https://doi.org/", "")
    except Exception as e:
        print(f"Error fetching DOI for '{title}': {e}")
    return None

def fill_missing_dois(df):
    st.write("Fetching missing DOIs via Title search...")
    progress_bar = st.progress(0)
    total_rows = len(df)
    
    for index, row in df.iterrows():
        if pd.isna(row['DOI']) or str(row['DOI']).strip() == '':
            new_doi = search_doi_by_title(row['Title'])
            if new_doi:
                df.at[index, 'DOI'] = new_doi
        progress_bar.progress((index + 1) / total_rows)
        
    return df

def fetch_openalex_data_by_doi(doi):
    if pd.isna(doi) or not str(doi).strip():
        return None
        
    clean_doi = str(doi).strip().replace("https://doi.org/", "").replace("doi:", "")
    url = f"https://api.openalex.org/works/doi:{clean_doi}"
    
    try:
         response = requests.get(url, headers=HEADERS, timeout=10)
         if response.status_code == 200:
             return response.json()
    except Exception as e:
         print(f"Error fetching data for DOI '{doi}': {e}")
    return None

def format_authors(authorships):
    if not authorships: return pd.NA
    author_names = []
    for auth in authorships:
        if 'author' in auth and 'display_name' in auth['author']:
            author_names.append(auth['author']['display_name'])
    return ", ".join(author_names) if author_names else pd.NA

def format_references(referenced_works):
    if not referenced_works: return pd.NA
    ref_ids = [str(rw).replace("https://openalex.org/", "") for rw in referenced_works]
    return "; ".join(ref_ids)

def enrich_dataset_openalex(df):
    st.write("Enriching full dataset via OpenAlex (using DOI)...")
    progress_bar = st.progress(0)
    total_rows = len(df)
    
    for index, row in df.iterrows():
        doi = row['DOI']
        if pd.notna(doi) and str(doi).strip():
            oa_data = fetch_openalex_data_by_doi(doi)
            
            if oa_data:
                if pd.isna(row['Author']) or str(row['Author']).strip() == '':
                    df.at[index, 'Author'] = format_authors(oa_data.get('authorships'))
                    
                if pd.isna(row['Publication Year']):
                    df.at[index, 'Publication Year'] = oa_data.get('publication_year')
                    
                if pd.isna(row['Times Cited']):
                    df.at[index, 'Times Cited'] = oa_data.get('cited_by_count')
                    
                if pd.isna(row['Publisher']) or str(row['Publisher']).strip() == '':
                    primary_loc = oa_data.get('primary_location')
                    if primary_loc and primary_loc.get('source'):
                         df.at[index, 'Publisher'] = primary_loc['source'].get('host_organization_name')
                         
                if pd.isna(row['Article References']) or str(row['Article References']).strip() == '':
                     df.at[index, 'Article References'] = format_references(oa_data.get('referenced_works'))
                     
        progress_bar.progress((index + 1) / total_rows)
        
    return df