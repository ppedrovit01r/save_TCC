import pandas as pd
import io

def df_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

def df_to_excel(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    return output.getvalue()

def df_to_ris(df: pd.DataFrame) -> bytes:
    """Basic RIS generator from DataFrame"""
    ris_content = []
    for _, row in df.iterrows():
        ris_content.append("TY  - JOUR")
        if pd.notna(row.get('Title')): ris_content.append(f"T1  - {row['Title']}")
        if pd.notna(row.get('Author')): 
            for author in str(row['Author']).split(','):
                ris_content.append(f"AU  - {author.strip()}")
        if pd.notna(row.get('Publication Year')): ris_content.append(f"PY  - {int(row['Publication Year'])}")
        if pd.notna(row.get('DOI')): ris_content.append(f"DO  - {row['DOI']}")
        if pd.notna(row.get('Abstract')): ris_content.append(f"AB  - {row['Abstract']}")
        ris_content.append("ER  - \n")
    return "\n".join(ris_content).encode("utf-8")

def df_to_bib(df: pd.DataFrame) -> bytes:
    """Basic BibTeX generator from DataFrame"""
    bib_content = []
    for i, row in df.iterrows():
        author = str(row['Author']).replace(',', ' and ') if pd.notna(row.get('Author')) else 'Unknown'
        title = row['Title'] if pd.notna(row.get('Title')) else 'Unknown'
        year = int(row['Publication Year']) if pd.notna(row.get('Publication Year')) else 'Unknown'
        
        entry = f"@article{{ref{i},\n"
        entry += f"  title={{ {title} }},\n"
        entry += f"  author={{ {author} }},\n"
        entry += f"  year={{ {year} }},\n"
        if pd.notna(row.get('Publisher')): entry += f"  journal={{ {row['Publisher']} }},\n"
        if pd.notna(row.get('DOI')): entry += f"  doi={{ {row['DOI']} }},\n"
        entry += "}\n"
        bib_content.append(entry)
    return "\n".join(bib_content).encode("utf-8")