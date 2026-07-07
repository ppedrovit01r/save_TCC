import streamlit as st
import pandas as pd
from typing import Callable, Any

def _download_button(df: pd.DataFrame, label: str, file_name: str, key: str = None):
    """Global component for downloading DataFrames as CSV."""
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        key=key
    )

def safe_download(component_fn, *args, **kwargs):
    """Wraps download buttons to prevent breakage if the data isn't ready."""
    try:
        component_fn(*args, **kwargs)
    except (ValueError, st.errors.StreamlitAPIException):
        st.warning("There is no data available for download yet. Please ensure the data is loaded and try again.")

def safe_run(func: Callable[..., Any]) -> Callable[..., Any]:
    """Global decorator to catch column errors or division-by-zero errors in charts."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyError as err:
            st.error(f"[{func.__name__}] Missing column: {err}")
        except ZeroDivisionError:
            st.error(f"[{func.__name__}] Division by zero.")
        except ValueError as err:
            st.error(f"[{func.__name__}] Value error: {err}")
        except Exception as err:
            st.error(f"[{func.__name__}] Unexpected error:")
            st.exception(err)
    return wrapper