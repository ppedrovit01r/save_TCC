import os
import re
import datetime
import streamlit as st

PROJECTS_ROOT = "Projects"
GLOBAL_CACHE_DIR = os.path.join("utils", "cache")

def sanitize_project_name(name: str) -> str:
    """Sanitizes user project name to be a valid, clean folder name."""
    if not name or not name.strip():
        return f"Project_{get_timestamp_str()}"
    clean = re.sub(r'[^\w\-]', '_', name.strip())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean if clean else f"Project_{get_timestamp_str()}"

def get_timestamp_str() -> str:
    """Returns timestamp in YYMMDDHHMM format (e.g. 2609161025)."""
    return datetime.datetime.now().strftime("%y%m%d%H%M")

def get_active_project_name() -> str:
    """Returns current active project name from session state or default."""
    if "active_project_name" not in st.session_state or not st.session_state.active_project_name:
        st.session_state.active_project_name = "Default_Project"
    return st.session_state.active_project_name

def set_active_project(name: str) -> str:
    """Initializes and activates a project workspace directory under Projects/<clean_name>."""
    clean_name = sanitize_project_name(name)
    st.session_state.active_project_name = clean_name
    
    for sub in ["logs", "exports", "sessions"]:
        path = get_project_dir(sub)
        os.makedirs(path, exist_ok=True)
        
    return clean_name

def get_project_root() -> str:
    """Returns the root directory path of the active project."""
    proj_name = get_active_project_name()
    path = os.path.join(PROJECTS_ROOT, proj_name)
    os.makedirs(path, exist_ok=True)
    return path

def get_project_dir(subfolder: str = "logs") -> str:
    """Returns the path for a specific subfolder ('logs', 'exports', 'sessions') inside active project."""
    root = get_project_root()
    sub_path = os.path.join(root, subfolder)
    os.makedirs(sub_path, exist_ok=True)
    return sub_path

def format_timestamped_filename(base_name: str) -> str:
    """
    Appends _YYMMDDHHMM before the file extension.
    Example: 'thematic_flow_nodes.csv' -> 'thematic_flow_nodes_2609161025.csv'
    """
    ts = get_timestamp_str()
    parts = os.path.splitext(base_name)
    if len(parts) == 2 and parts[1]:
        clean_base = parts[0]
        ext = parts[1]
        # Avoid duplicate timestamps
        if re.search(r'_\d{10,12}$', clean_base):
            return f"{clean_base}{ext}"
        return f"{clean_base}_{ts}{ext}"
    else:
        return f"{base_name}_{ts}"

def save_project_file(subfolder: str, filename: str, data, mode: str = "w") -> str:
    """
    Saves a file into the active project's subfolder (e.g. 'logs', 'exports', 'sessions').
    Returns the absolute or relative path of the saved file.
    """
    target_dir = get_project_dir(subfolder)
    target_path = os.path.join(target_dir, filename)
    
    if isinstance(data, bytes) or "b" in mode:
        with open(target_path, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    else:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(str(data))
            
    return target_path

def get_global_cache_dir() -> str:
    """Returns the global cache directory under utils/cache."""
    os.makedirs(GLOBAL_CACHE_DIR, exist_ok=True)
    return GLOBAL_CACHE_DIR
