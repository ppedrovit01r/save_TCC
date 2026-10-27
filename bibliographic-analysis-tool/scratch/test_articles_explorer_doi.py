import sys, os, re
sys.path.insert(0, os.path.abspath(os.getcwd()))

import pandas as pd
import numpy as np
from utils.formatters import normalize_doi_url

# Test 1: normalize_doi_url
assert normalize_doi_url("10.1002/deo2.70359") == "https://doi.org/10.1002/deo2.70359"
assert normalize_doi_url("https://doi.org/10.1002/deo2.70359") == "https://doi.org/10.1002/deo2.70359"
assert normalize_doi_url("http://dx.doi.org/10.1002/deo2.70359") == "https://doi.org/10.1002/deo2.70359"
assert normalize_doi_url("doi: 10.1002/deo2.70359") == "https://doi.org/10.1002/deo2.70359"
assert normalize_doi_url("/10.1002/deo2.70359") == "https://doi.org/10.1002/deo2.70359"
assert normalize_doi_url(np.nan) is None
assert normalize_doi_url(None) is None
assert normalize_doi_url("nan") is None
assert normalize_doi_url("") is None
print("[OK] Test 1: normalize_doi_url passed 100%!")

# Test 2: Regex extraction matching Streamlit frontend logic
regex = re.compile(r"https?://(?:dx\.)?doi\.org/(.*)")
match = regex.match("https://doi.org/10.1002/deo2.70359")
assert match is not None
assert match.group(1) == "10.1002/deo2.70359"
print("[OK] Test 2: Regex extraction passed 100%!")

# Test 3: Dataframe transformation in Articles Explorer table
df = pd.DataFrame({
    "Title": ["Article A", "Article B", "Article C"],
    "DOI": ["10.1002/deo2.70359", "https://doi.org/10.1109/test.123", np.nan]
})
df["DOI"] = df["DOI"].apply(normalize_doi_url)

assert df.at[0, "DOI"] == "https://doi.org/10.1002/deo2.70359"
assert df.at[1, "DOI"] == "https://doi.org/10.1109/test.123"
assert df.at[2, "DOI"] is None
print("[OK] Test 3: Dataframe DOI transformation passed 100%!")

print("ALL DOI LINK TESTS PASSED SUCCESSFULLY!")
