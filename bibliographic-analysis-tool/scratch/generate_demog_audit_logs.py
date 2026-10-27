import sys, os, datetime, json
sys.path.insert(0, os.path.abspath(os.getcwd()))

import pandas as pd
from collections import Counter
from features.demographics import extract_countries
from utils.project_manager import get_project_dir

def generate_audit_for_project(proj_name):
    csv_p = f'Projects/{proj_name}/master_dataset.csv'
    if not os.path.exists(csv_p):
        print(f'Project {proj_name} not found.')
        return
        
    df = pd.read_csv(csv_p, low_memory=False)
    
    def extract_all_countries(row):
        found = set()
        for col in ['Affiliations', 'Address', 'Country']:
            if col in row and pd.notna(row[col]):
                found.update(extract_countries(row[col]))
        return list(found)
        
    df['Country_Extracted'] = df.apply(extract_all_countries, axis=1)
    df['Has_Country'] = df['Country_Extracted'].apply(lambda x: len(x) > 0)
    
    total_raw = len(df)
    has_aff = df['Affiliations'].apply(lambda x: pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan').sum() if 'Affiliations' in df.columns else 0
    has_addr = df['Address'].apply(lambda x: pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan').sum() if 'Address' in df.columns else 0
    has_orig = df['Country'].apply(lambda x: pd.notna(x) and str(x).strip() != '' and str(x).lower() != 'nan') if 'Country' in df.columns else pd.Series(False, index=df.index)
    orig_count = int(has_orig.sum())
    
    has_extracted = df['Has_Country']
    identified_count = int(has_extracted.sum())
    missing_count = total_raw - identified_count
    
    deduced_mask = (~has_orig) & has_extracted
    deduced_count = int(deduced_mask.sum())
    
    deduced_df = df[deduced_mask]
    deduced_countries_flat = [c for sub in deduced_df['Country_Extracted'] for c in sub]
    country_freq = Counter(deduced_countries_flat).most_common()
    
    deduced_records = []
    for idx, r in deduced_df.iterrows():
        deduced_records.append({
            'index': int(idx),
            'title': str(r.get('Title', 'Untitled')),
            'affiliations': str(r.get('Affiliations', '')) if pd.notna(r.get('Affiliations')) else '',
            'address': str(r.get('Address', '')) if pd.notna(r.get('Address')) else '',
            'deduced_countries': list(r.get('Country_Extracted', []))
        })
        
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_dir = get_project_dir('logs', proj_name)
    os.makedirs(log_dir, exist_ok=True)
    
    orig_pct = (orig_count / total_raw * 100) if total_raw else 0
    deduced_pct = (deduced_count / total_raw * 100) if total_raw else 0
    ident_pct = (identified_count / total_raw * 100) if total_raw else 0
    missing_pct = (missing_count / total_raw * 100) if total_raw else 0
    aff_pct = (has_aff / total_raw * 100) if total_raw else 0
    addr_pct = (has_addr / total_raw * 100) if total_raw else 0
    
    # JSON log
    json_path = os.path.join(log_dir, 'geographic_inference_audit.json')
    json_payload = {
        'project_name': proj_name,
        'generated_at': now_str,
        'total_records': total_raw,
        'affiliations_present': int(has_aff),
        'affiliations_pct': round(aff_pct, 2),
        'address_present': int(has_addr),
        'address_pct': round(addr_pct, 2),
        'explicit_country_count': orig_count,
        'explicit_country_pct': round(orig_pct, 2),
        'heuristic_deduced_count': deduced_count,
        'heuristic_deduced_pct': round(deduced_pct, 2),
        'total_identified_count': identified_count,
        'total_identified_pct': round(ident_pct, 2),
        'missing_country_count': missing_count,
        'missing_country_pct': round(missing_pct, 2),
        'recovered_countries_breakdown': dict(country_freq),
        'deduced_records': deduced_records
    }
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)
        
    # Text log
    log_path = os.path.join(log_dir, 'geographic_inference_audit.log')
    lines = [
        '=' * 80,
        'GEOGRAPHIC PROVENANCE & DEMOGRAPHIC INFERENCE AUDIT LOG',
        '=' * 80,
        f'Project Name:                   {proj_name}',
        f'Generated At:                   {now_str}',
        f'Methodology:                    Rule-based gazetteer & administrative subdivision regex heuristics',
        '',
        '-' * 80,
        '1. CORPUS SUMMARY & QUALITY AUDIT METRICS',
        '-' * 80,
        f'Total Publications in Corpus:          {total_raw:>6,} (100.0%)',
        f'Affiliations Metadata Present:         {has_aff:>6,} ({aff_pct:.1f}%)',
        f'Author Address Metadata Present:       {has_addr:>6,} ({addr_pct:.1f}%)',
        f'Explicit Country Present in Raw Data:  {orig_count:>6,} ({orig_pct:.1f}%)',
        f'Country Recovered by Regex Heuristics: {deduced_count:>6,} ({deduced_pct:.1f}%)',
        '-' * 80,
        f'Total Geographic Provenance Identified: {identified_count:>6,} ({ident_pct:.1f}%)',
        f'Unresolved Records (Missing Country):   {missing_count:>6,} ({missing_pct:.1f}%)',
        '-' * 80,
        '',
        '2. BREAKDOWN OF RECOVERED COUNTRIES VIA HEURISTICS',
        '-' * 80
    ]
    for cname, cnt in country_freq:
        lines.append(f'  - {cname:<30}: {cnt:>4} records')
    lines.extend([
        '',
        '-' * 80,
        f'3. DEDUCTION PROVENANCE RECORDS ({deduced_count} publications recovered from Affiliations/Address)',
        '-' * 80
    ])
    for item in deduced_records:
        countries_str = ', '.join(item['deduced_countries'])
        aff_d = item['affiliations'][:90] + ('...' if len(item['affiliations']) > 90 else '')
        addr_d = item['address'][:90] + ('...' if len(item['address']) > 90 else '')
        lines.append(f"[Record #{item['index']}]")
        lines.append(f"  Title:    {item['title']}")
        if aff_d:
            lines.append(f"  Affil:    {aff_d}")
        if addr_d:
            lines.append(f"  Address:  {addr_d}")
        lines.append(f"  Deduced:  {countries_str}")
        lines.append('')
    lines.append('=' * 80)
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
        
    print(f'Successfully generated {log_path} and {json_path}!')

if __name__ == '__main__':
    for p in ['LeticiaAll21', 'Lryiciaall']:
        generate_audit_for_project(p)
