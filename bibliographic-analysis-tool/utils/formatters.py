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

