def format_duration(seconds: float) -> str:
    """
    Formats a duration in seconds into human-readable text:
    'XX days YY hours ZZ minutes AA seconds'.
    When the number is 0, it is omitted.
    
    Examples:
        45.2 -> '45.2 seconds'
        138.7 -> '2 minutes 19 seconds'
        3665.0 -> '1 hour 1 minute 5 seconds'
        90061.5 -> '1 day 1 hour 1 minute 2 seconds'
        0 -> '0 seconds'
    """
    if seconds is None:
        return "0 seconds"
    
    try:
        total_seconds = float(seconds)
    except (ValueError, TypeError):
        return str(seconds)

    if total_seconds < 0:
        return f"-{format_duration(abs(total_seconds))}"
    
    days = int(total_seconds // 86400)
    rem = total_seconds % 86400
    hours = int(rem // 3600)
    rem = rem % 3600
    minutes = int(rem // 60)
    secs = rem % 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    if days == 0 and hours == 0 and minutes == 0:
        # Sub-minute: show exact with decimal precision
        if secs == int(secs):
            parts.append(f"{int(secs)} seconds")
        else:
            formatted_secs = f"{secs:.2f}".rstrip('0').rstrip('.')
            parts.append(f"{formatted_secs} seconds")
    else:
        rounded_secs = int(round(secs))
        if rounded_secs > 0:
            parts.append(f"{rounded_secs} second{'s' if rounded_secs != 1 else ''}")

    return " ".join(parts) if parts else "0 seconds"


def clean_year_value(val) -> str:
    """
    Cleans a single year value so that it never displays with trailing '.0' or as a float.
    Returns a clean 4-digit year string (e.g. '2024') or '' if missing/invalid.
    
    Examples:
        2027.0 -> '2027'
        2024 -> '2024'
        '2024.0' -> '2024'
        '2024-05-12' -> '2024'
        np.nan -> ''
        None -> ''
    """
    if val is None:
        return ""
    
    import numpy as np
    import pandas as pd
    import re
    
    if isinstance(val, (float, np.floating)):
        if np.isnan(val):
            return ""
        return str(int(val))
    if isinstance(val, (int, np.integer)):
        return str(int(val))
        
    s = str(val).strip()
    if not s or s.lower() in ("nan", "<na>", "none", "null", "unknown", "unknown year", "n/a"):
        return ""
        
    if s.endswith(".0"):
        s_int = s[:-2]
        if s_int.isdigit():
            return s_int
            
    m = re.search(r'\b(18\d{2}|19\d{2}|20\d{2})\b', s)
    if m:
        return m.group(1)
        
    try:
        f = float(s)
        if not np.isnan(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
        
    return s


def clean_year_series(series) -> 'pd.Series':
    """
    Standardizes a pandas Series of Publication Years into clean strings (e.g. '2024' or '').
    Prevents pandas from casting the column to float64 with '.0' upon presence of NaNs.
    """
    if series is None:
        return series
    try:
        import pandas as pd
        if not isinstance(series, pd.Series) or series.empty:
            return series
        return series.apply(clean_year_value)
    except Exception:
        return series


def clean_pages_value(val) -> str:
    """
    Cleans a single Pages value so that it never displays with trailing '.0' or as a float.
    Handles numeric page numbers, page ranges, and missing/NaN values uniformly as strings.
    
    Examples:
        42.0 -> '42'
        '42.0' -> '42'
        '1817-1818' -> '1817-1818'
        'e12345' -> 'e12345'
        np.nan -> ''
        None -> ''
    """
    if val is None:
        return ""
        
    import numpy as np
    import pandas as pd

    if isinstance(val, (float, np.floating)):
        if np.isnan(val):
            return ""
        if val.is_integer():
            return str(int(val))
        return str(val)
        
    if isinstance(val, (int, np.integer)):
        return str(int(val))

    s = str(val).strip()
    if not s or s.lower() in ("nan", "<na>", "none", "null", "unknown", "n/a"):
        return ""

    if s.endswith(".0"):
        s_int = s[:-2]
        if s_int.isdigit():
            return s_int

    return s


def clean_pages_series(series) -> 'pd.Series':
    """
    Standardizes a pandas Series of Pages into clean strings (e.g. '42', '1817-1818', or '').
    Prevents mixed float and string objects that cause PyArrow serialization errors in Streamlit.
    """
    if series is None:
        return series
    try:
        import pandas as pd
        if not isinstance(series, pd.Series) or series.empty:
            return series
        return series.apply(clean_pages_value).astype(str)
    except Exception:
        return series


def clean_metadata_value(val) -> str:
    """
    Cleans a general textual/metadata value (e.g. Volume, Issue, ISSN, PMID) into a uniform string.
    Removes trailing '.0' if representing an integer, and converts missing/NaN values to empty strings.
    """
    if val is None:
        return ""
        
    import numpy as np
    import pandas as pd

    if isinstance(val, (float, np.floating)):
        if np.isnan(val):
            return ""
        if val.is_integer():
            return str(int(val))
        return str(val)
        
    if isinstance(val, (int, np.integer)):
        return str(int(val))
        
    if isinstance(val, (list, tuple)):
        return ", ".join(str(x) for x in val if pd.notna(x) and str(x).strip())

    s = str(val).strip()
    if not s or s.lower() in ("nan", "<na>", "none", "null", "unknown", "n/a"):
        return ""

    if s.endswith(".0"):
        s_int = s[:-2]
        if s_int.isdigit():
            return s_int

    return s


def clean_metadata_series(series) -> 'pd.Series':
    """
    Standardizes a pandas Series of textual metadata into clean strings.
    """
    if series is None:
        return series
    try:
        import pandas as pd
        if not isinstance(series, pd.Series) or series.empty:
            return series
        return series.apply(clean_metadata_value).astype(str)
    except Exception:
        return series


def sanitize_df_for_streamlit(df: 'pd.DataFrame') -> 'pd.DataFrame':
    """
    Sanitizes a pandas DataFrame before rendering in Streamlit (via st.dataframe, st.data_editor, etc.).
    Ensures that mixed-type columns (specifically object columns containing a mixture of strings,
    floats, ints, or nested collections) are coerced to uniform types, preventing PyArrow serialization
    exceptions such as ArrowTypeError: ("Expected bytes, got a 'float' object").
    """
    if df is None:
        return df
    try:
        import pandas as pd
        import numpy as np
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df

        clean_df = df.copy()
        
        # Columns that should remain purely numeric
        numeric_col_names = {
            'times cited', 'citations', 'count', 'frequency', 'n_docs', 
            'centrality', 'density', 'probability', 'position', 'growth_coefficient'
        }

        for col in clean_df.columns:
            col_lower = str(col).lower().strip()
            if col_lower in numeric_col_names:
                continue

            col_series = clean_df[col]

            if col == 'Publication Year':
                clean_df[col] = clean_year_series(col_series)
            elif col == 'Pages':
                clean_df[col] = clean_pages_series(col_series)
            elif col in ('Volume', 'Issue', 'PMID', 'ISSN', 'DOI', 'OpenAlex ID', 'Language', 'Document Type'):
                clean_df[col] = clean_metadata_series(col_series)
            elif col_series.dtype == 'object':
                non_nulls = col_series.dropna()
                if not non_nulls.empty:
                    val_types = set(type(x) for x in non_nulls)
                    # If mixed scalar types, non-primitives, or float in object column
                    if len(val_types) > 1 or any(t in (dict, list, tuple, set) for t in val_types) or float in val_types:
                        clean_df[col] = clean_metadata_series(col_series)

        return clean_df
    except Exception:
        return df


def normalize_doi_url(val) -> str | None:
    """
    Normalizes a DOI string or URL into a canonical https://doi.org/... URL.
    Returns None if the value is empty, invalid, or missing.
    
    Examples:
        '10.1002/deo2.70359' -> 'https://doi.org/10.1002/deo2.70359'
        'https://doi.org/10.1002/deo2.70359' -> 'https://doi.org/10.1002/deo2.70359'
        'http://dx.doi.org/10.1002/deo2.70359' -> 'https://doi.org/10.1002/deo2.70359'
        'doi:10.1002/deo2.70359' -> 'https://doi.org/10.1002/deo2.70359'
        np.nan -> None
    """
    if val is None:
        return None
    import pandas as pd
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', 'null', '-', 'n/a'):
        return None
    if s.startswith('http://') or s.startswith('https://'):
        if s.startswith('http://dx.doi.org/'):
            return 'https://doi.org/' + s[18:]
        elif s.startswith('http://doi.org/'):
            return 'https://doi.org/' + s[15:]
        return s
    if s.lower().startswith('doi:'):
        s = s[4:].strip()
    s = s.lstrip('/')
    return f"https://doi.org/{s}"



