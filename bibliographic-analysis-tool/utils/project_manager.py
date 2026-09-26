import os
import re
import datetime
import shutil
import json
import pandas as pd
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

def set_active_project(name: str, migrate_from: str = "Default_Project") -> str:
    """Initializes and activates a project workspace directory under Projects/<clean_name>."""
    clean_name = sanitize_project_name(name)
    
    # If migrating from an existing temporary project (like Default_Project) to a named one
    if migrate_from and migrate_from != clean_name:
        migrate_project_data(migrate_from, clean_name)

    st.session_state.active_project_name = clean_name
    
    for sub in ["logs", "exports", "sessions"]:
        path = get_project_dir(sub)
        os.makedirs(path, exist_ok=True)
        
    clear_project_list_cache()
    return clean_name

def reset_active_project() -> None:
    """Closes the connection to the active project folder and resets to unattached state."""
    st.session_state.active_project_name = "Default_Project"

def get_project_root(project_name: str = None) -> str:
    """Returns the root directory path of the active or specified project."""
    proj_name = project_name or get_active_project_name()
    path = os.path.join(PROJECTS_ROOT, proj_name)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def get_project_dir(subfolder: str = "logs", project_name: str = None) -> str:
    """Returns the path for a specific subfolder ('logs', 'exports', 'sessions') inside project."""
    root = get_project_root(project_name)
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

def save_project_file(subfolder: str, filename: str, data, mode: str = "w", project_name: str = None) -> str:
    """
    Saves a file into the project's subfolder (e.g. 'logs', 'exports', 'sessions').
    Returns the absolute or relative path of the saved file.
    """
    target_dir = get_project_dir(subfolder, project_name)
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

def open_project_folder(subfolder: str = "", project_name: str = None) -> bool:
    """
    Opens the project folder (or subfolder like 'exports' or 'sessions') in the OS file explorer.
    """
    import subprocess
    import platform
    
    if subfolder:
        folder_path = get_project_dir(subfolder, project_name)
    else:
        folder_path = get_project_root(project_name)
        
    abs_path = os.path.abspath(folder_path)
    os.makedirs(abs_path, exist_ok=True)
    
    try:
        if platform.system() == "Windows":
            os.startfile(abs_path)
            return True
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", abs_path])
            return True
        else:
            subprocess.Popen(["xdg-open", abs_path])
            return True
    except Exception as e:
        print(f"Error opening folder: {e}")
        return False

def save_master_dataset(df: pd.DataFrame, project_name: str = None) -> str:
    """
    Saves the master DataFrame as master_dataset.csv directly in the project's root folder.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return ""
    root = get_project_root(project_name)
    out_path = os.path.join(root, "master_dataset.csv")
    try:
        save_df = df.copy()
        if "Publication Year" in save_df.columns:
            from utils.formatters import clean_year_series
            save_df["Publication Year"] = clean_year_series(save_df["Publication Year"])
        save_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        clear_project_list_cache()
        return out_path
    except Exception as e:
        print(f"Error saving master dataset: {e}")
        return ""

def load_master_dataset(project_name: str) -> pd.DataFrame:
    """
    Loads master_dataset.csv from the specified project's folder.
    """
    root = os.path.join(PROJECTS_ROOT, project_name)
    target_csv = os.path.join(root, "master_dataset.csv")
    if not os.path.exists(target_csv):
        # Check if there is an exported csv in exports
        exp_dir = os.path.join(root, "exports")
        if os.path.exists(exp_dir):
            for f in sorted(os.listdir(exp_dir), reverse=True):
                if f.startswith("exported_data_") and f.endswith(".csv"):
                    target_csv = os.path.join(exp_dir, f)
                    break

    if os.path.exists(target_csv):
        try:
            loaded_df = pd.read_csv(target_csv, low_memory=False)
            if loaded_df is not None and "Publication Year" in loaded_df.columns:
                from utils.formatters import clean_year_series
                loaded_df["Publication Year"] = clean_year_series(loaded_df["Publication Year"])
            return loaded_df
        except Exception as e:
            st.error(f"Error reading dataset from project '{project_name}': {e}")
            return None
    return None

def migrate_project_data(from_proj: str, to_proj: str):
    """
    Moves or merges files from an existing project folder (e.g. Default_Project) to to_proj.
    """
    src_root = os.path.join(PROJECTS_ROOT, from_proj)
    dst_root = os.path.join(PROJECTS_ROOT, to_proj)
    
    if not os.path.exists(src_root) or src_root == dst_root:
        return
        
    os.makedirs(dst_root, exist_ok=True)
    
    # Move files and directories
    try:
        for item in os.listdir(src_root):
            s_item = os.path.join(src_root, item)
            d_item = os.path.join(dst_root, item)
            if os.path.isdir(s_item):
                os.makedirs(d_item, exist_ok=True)
                for sub_file in os.listdir(s_item):
                    s_sub = os.path.join(s_item, sub_file)
                    d_sub = os.path.join(d_item, sub_file)
                    if not os.path.exists(d_sub):
                        shutil.move(s_sub, d_sub)
                    else:
                        shutil.copy2(s_sub, d_sub)
            else:
                if not os.path.exists(d_item):
                    shutil.move(s_item, d_item)
                else:
                    shutil.copy2(s_item, d_item)
    except Exception as e:
        print(f"Project migration notice: {e}")

def _count_csv_rows_fast(filepath: str) -> int:
    """Fast line counter using 1MB binary chunk buffer instead of line iteration."""
    try:
        with open(filepath, 'rb') as f:
            count = 0
            buf_size = 1024 * 1024
            buf = f.read(buf_size)
            while buf:
                count += buf.count(b'\n')
                buf = f.read(buf_size)
            return max(0, count - 1)
    except Exception:
        return 0

def clear_project_list_cache():
    """Invalidates the cached list of saved projects."""
    try:
        list_saved_projects.clear()
    except Exception:
        pass

@st.cache_data(ttl=60, show_spinner=False)
def list_saved_projects() -> list[dict]:
    """
    Scans PROJECTS_ROOT and returns a list of dictionaries with project metadata.
    Cached for 60 seconds or invalidated when projects are modified.
    """
    if not os.path.exists(PROJECTS_ROOT):
        return []
        
    projects = []
    for folder_name in os.listdir(PROJECTS_ROOT):
        full_path = os.path.join(PROJECTS_ROOT, folder_name)
        if not os.path.isdir(full_path):
            continue
        
        # Check for dataset
        master_csv = os.path.join(full_path, "master_dataset.csv")
        has_dataset = os.path.exists(master_csv)
        row_count = 0
        file_size_mb = 0.0
        
        if has_dataset:
            try:
                file_size_mb = os.path.getsize(master_csv) / (1024 * 1024)
                row_count = _count_csv_rows_fast(master_csv)
            except Exception:
                pass
        else:
            # Check exports folder for exported_data_*.csv
            exp_dir = os.path.join(full_path, "exports")
            if os.path.exists(exp_dir):
                csv_candidates = [f for f in os.listdir(exp_dir) if f.endswith(".csv")]
                if csv_candidates:
                    has_dataset = True
                    best_csv = sorted(csv_candidates, reverse=True)[0]
                    target_file = os.path.join(exp_dir, best_csv)
                    try:
                        file_size_mb = os.path.getsize(target_file) / (1024 * 1024)
                        row_count = _count_csv_rows_fast(target_file)
                    except Exception:
                        pass
                        
        mtime = os.path.getmtime(full_path)
        modified_dt = datetime.datetime.fromtimestamp(mtime)
        modified_str = modified_dt.strftime("%b %d, %Y - %H:%M")
        
        num_logs = len(os.listdir(os.path.join(full_path, "logs"))) if os.path.exists(os.path.join(full_path, "logs")) else 0
        num_exports = len(os.listdir(os.path.join(full_path, "exports"))) if os.path.exists(os.path.join(full_path, "exports")) else 0
        
        projects.append({
            "name": folder_name,
            "has_dataset": has_dataset,
            "row_count": row_count,
            "file_size_mb": file_size_mb,
            "modified_dt": modified_dt,
            "modified_str": modified_str,
            "num_logs": num_logs,
            "num_exports": num_exports
        })
        
    projects.sort(key=lambda x: x["modified_dt"], reverse=True)
    return projects

def get_project_metadata(project_name: str = None) -> dict:
    """Loads project_metadata.json from the project root."""
    root = get_project_root(project_name)
    meta_path = os.path.join(root, "project_metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_project_metadata(key: str, value, project_name: str = None) -> dict:
    """Updates a key in project_metadata.json and returns the updated metadata."""
    root = get_project_root(project_name)
    meta_path = os.path.join(root, "project_metadata.json")
    meta = get_project_metadata(project_name)
    meta[key] = value
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving project metadata: {e}")
    return meta

def is_author_standardization_dismissed(project_name: str = None) -> bool:
    """Checks if the author standardization advisory banner has been dismissed for this project."""
    if st.session_state.get("author_standardization_dismissed") is True:
        return True
    meta = get_project_metadata(project_name)
    dismissed = bool(meta.get("author_standardization_dismissed", False))
    if dismissed:
        st.session_state["author_standardization_dismissed"] = True
    return dismissed

def set_author_standardization_dismissed(dismissed: bool = True, project_name: str = None) -> None:
    """Sets the author standardization dismissal state both in session state and project_metadata.json."""
    st.session_state["author_standardization_dismissed"] = dismissed
    save_project_metadata("author_standardization_dismissed", dismissed, project_name)

_OVERRIDES_CACHE = {}
_OVERRIDES_MTIME = {}

def get_manual_author_overrides(project_name: str = None) -> dict:
    """Loads author_overrides.json containing manual author name replacements {original: new} with fast memory caching."""
    root = get_project_root(project_name)
    overrides_path = os.path.join(root, "author_overrides.json")
    if not os.path.exists(overrides_path):
        return {}
    try:
        mtime = os.path.getmtime(overrides_path)
        if overrides_path in _OVERRIDES_CACHE and _OVERRIDES_MTIME.get(overrides_path) == mtime:
            return _OVERRIDES_CACHE[overrides_path]
        with open(overrides_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _OVERRIDES_CACHE[overrides_path] = data
            _OVERRIDES_MTIME[overrides_path] = mtime
            return data
    except Exception:
        return {}

def save_manual_author_override(orig_name: str, new_name: str, project_name: str = None) -> dict:
    """Saves a manual author replacement mapping to author_overrides.json."""
    if not orig_name or not new_name:
        return {}
    root = get_project_root(project_name)
    overrides_path = os.path.join(root, "author_overrides.json")
    overrides = get_manual_author_overrides(project_name)
    overrides[orig_name.strip()] = new_name.strip()
    try:
        with open(overrides_path, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
        _OVERRIDES_CACHE[overrides_path] = overrides
        _OVERRIDES_MTIME[overrides_path] = os.path.getmtime(overrides_path)
    except Exception as e:
        print(f"Error saving manual author override: {e}")
    return overrides

def delete_manual_author_override(orig_name: str, project_name: str = None) -> dict:
    """Deletes a manual author replacement mapping from author_overrides.json."""
    root = get_project_root(project_name)
    overrides_path = os.path.join(root, "author_overrides.json")
    overrides = get_manual_author_overrides(project_name)
    if orig_name in overrides:
        del overrides[orig_name]
        try:
            with open(overrides_path, "w", encoding="utf-8") as f:
                json.dump(overrides, f, ensure_ascii=False, indent=2)
            _OVERRIDES_CACHE[overrides_path] = overrides
            _OVERRIDES_MTIME[overrides_path] = os.path.getmtime(overrides_path)
        except Exception as e:
            print(f"Error deleting manual author override: {e}")
    return overrides

