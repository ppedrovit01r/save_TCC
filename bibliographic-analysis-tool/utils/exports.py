import streamlit as st
import pandas as pd
from typing import Callable, Any

from utils.project_manager import format_timestamped_filename, save_project_file, open_project_folder, get_active_project_name

@st.cache_data
def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    if df is None or df.empty:
        return b""
    return df.to_csv(index=False).encode("utf-8-sig")

def _save_export_on_click(subfolder: str, file_name: str, data: bytes, mode: str = "wb"):
    stamped_name = format_timestamped_filename(file_name)
    try:
        saved_path = save_project_file(subfolder, stamped_name, data, mode=mode)
        st.toast(f"Saved to Project workspace: {stamped_name}", icon="📁")
        return saved_path
    except Exception as e:
        print(f"Error auto-saving export: {e}")
        return ""

def _download_button(df: pd.DataFrame, label: str, file_name: str, key: str = None, enable_browser_download: bool = True, disabled: bool = False):
    """
    Global component for saving DataFrames into the active Project workspace.
    Saves automatically to Projects/<active_project>/exports/ on click and optionally offers browser download.
    """
    btn_key = key or f"dl_btn_{file_name}_{abs(hash(label))}"
    if df is None or df.empty or disabled:
        st.download_button(label=label, data=b"", file_name=file_name, key=btn_key, disabled=True)
        return

    csv_bytes = _df_to_csv_bytes(df)
    stamped_name = format_timestamped_filename(file_name)

    if enable_browser_download:
        st.download_button(
            label=label,
            data=csv_bytes,
            file_name=stamped_name,
            mime="text/csv",
            key=btn_key,
            disabled=disabled,
            on_click=_save_export_on_click,
            args=("exports", file_name, csv_bytes, "wb"),
            help=f"Saves to Projects/{get_active_project_name()}/exports/ and downloads file"
        )
    else:
        # Direct save notification mode
        if st.button(label, icon=":material/save:", key=btn_key, disabled=disabled):
            _save_export_on_click("exports", file_name, csv_bytes, "wb")

def render_project_saved_notice(subfolder: str = "exports", context_text: str = ""):
    """
    Renders a clean notice informing the user that files are automatically saved to their project workspace,
    with a button to open the project folder in their file explorer.
    """
    proj_name = get_active_project_name()
    desc = context_text if context_text else f"All exports and sessions are automatically saved directly into <code>Projects/{proj_name}/{subfolder}/</code>."
    
    st.markdown(f"""
    <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-left: 4px solid #697aa2; padding: 10px 14px; border-radius: 6px; margin: 10px 0 12px 0;">
        <div style="font-size: 13px; color: #334155; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
            <div>
                <i class="bi bi-folder-check" style="color: #697aa2; font-size: 15px; margin-right: 4px;"></i>
                {desc}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def safe_download(component_fn, *args, **kwargs):
    """Wraps download buttons to prevent breakage if the data isn't ready."""
    try:
        component_fn(*args, **kwargs)
    except ValueError:
        st.warning("There is no data available for download yet. Please ensure the data is loaded and try again.")
    except st.errors.StreamlitAPIException as err:
        st.error(f"Download button configuration error: {err}")

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