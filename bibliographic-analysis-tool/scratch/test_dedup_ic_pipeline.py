import os
import sys
import pandas as pd
import json
import shutil

# Ensure project root is in path
sys.path.insert(0, os.path.abspath("."))

from features.prisma_assistant import (
    get_raw_retrieved_audit_stats,
    _build_horizontal_slr_diagram,
    _build_vertical_slr_diagram,
    execute_auto_exclude_missing_abstracts,
    execute_restore_missing_abstracts,
    is_missing_abstract
)
from utils.project_manager import (
    save_project_prisma_state,
    load_project_prisma_state,
    deep_clean_json,
    PROJECTS_ROOT
)

def test_dedup_ic_pipeline():
    print("=== TEST 1: Serialization of Series and Complex Objects ===")
    # Verify that deep_clean_json thoroughly cleans Series, DataFrames, NAs, timestamps
    raw_series = pd.Series({"a": 1, "b": "test", "c": pd.NA})
    nested_structure = {
        "series": raw_series,
        "dataframe": pd.DataFrame([{"x": 10, "y": 20}]),
        "nested_list": [pd.Series([100, 200])],
        "exclusions": {
            "0": {"code": "EC 1", "series_meta": pd.Series({"doi": "10.1234/test"})}
        }
    }
    cleaned = deep_clean_json(nested_structure)
    # Must dump with zero errors
    dumped = json.dumps(cleaned)
    assert "10.1234/test" in dumped
    print("Serialization test passed 100%!")

    print("=== TEST 2: PRISMA & SLR Deduplication and Missing Abstracts Audit Pipeline ===")

    # Setup mock data: 4 files, total 9 records, 3 duplicates, 2 missing abstracts
    surviving_df = pd.DataFrame([
        {"Title": "Paper A", "Abstract": "Valid abstract A", "DOI": "10.1001/a", "Source File": "file1.csv"},
        {"Title": "Paper B", "Abstract": "", "DOI": "10.1001/b", "Source File": "file1.csv"}, # Missing abstract
        {"Title": "Paper C", "Abstract": "None", "DOI": "10.1001/c", "Source File": "file1.csv"}, # Missing abstract
        {"Title": "Paper D", "Abstract": "Valid abstract D", "DOI": "10.1001/d", "Source File": "file2.csv"},
        {"Title": "Paper E", "Abstract": "Valid abstract E", "DOI": "10.1001/e", "Source File": "file3.csv"},
        {"Title": "Paper F", "Abstract": "Valid abstract F", "DOI": "10.1001/f", "Source File": "file4.csv"}
    ])
    assert len(surviving_df) == 6

    # Verify is_missing_abstract
    assert is_missing_abstract(surviving_df.loc[1]) is True
    assert is_missing_abstract(surviving_df.loc[2]) is True
    assert is_missing_abstract(surviving_df.loc[0]) is False

    file_manifest = {"file1.csv": 3, "file2.csv": 2, "file3.csv": 2, "file4.csv": 2}
    loaded_files = ["file1.csv", "file2.csv", "file3.csv", "file4.csv"]

    # 3 duplicates with embedded pandas Series as 'kept' and 'removed' to stress-test serialization
    duplicates_list = [
        {"phase": "Ingestion", "stage": "DOI", "kept": pd.Series({"Title": "Paper A", "Source File": "file1.csv"}), "removed": pd.Series({"Title": "Paper A Dup", "Source File": "file2.csv"})},
        {"phase": "Ingestion", "stage": "DOI", "kept": pd.Series({"Title": "Paper B", "Source File": "file1.csv"}), "removed": pd.Series({"Title": "Paper B Dup", "Source File": "file3.csv"})},
        {"phase": "Ingestion", "stage": "DOI", "kept": pd.Series({"Title": "Paper C", "Source File": "file1.csv"}), "removed": pd.Series({"Title": "Paper C Dup", "Source File": "file4.csv"})}
    ]

    file_raw_counts, total_raw, total_dups, total_screen_pool = get_raw_retrieved_audit_stats(
        loaded_files=loaded_files,
        file_manifest=file_manifest,
        raw_df=surviving_df,
        prisma_duplicates=duplicates_list
    )
    assert total_raw == 9
    assert total_dups == 3
    assert total_screen_pool == 6
    assert total_raw - total_dups == total_screen_pool

    # Project Persistence with pandas Series inside duplicates
    test_proj = "Test_Dedup_Audit_Proj"
    test_state = {
        "project_name": test_proj,
        "mode": "advanced",
        "file_db_mapping": {
            "file1.csv": "Scopus",
            "file2.csv": "IEEE Xplore",
            "file3.csv": "Scopus",
            "file4.csv": "ACM DL"
        },
        "loaded_files": loaded_files,
        "file_manifest": file_manifest,
        "prisma_imported_count": 9,
        "inclusion_criteria": [
            {"id": "IC 1", "title": "English", "desc": ""},
            {"id": "IC 2", "title": "Peer-Reviewed", "desc": ""}
        ],
        "exclusion_criteria": [
            {"id": "EC 1", "title": "Out of Scope", "desc": ""}
        ],
        "screening_queue": list(surviving_df.index),
        "exclusions": {},
        "screened_ok": []
    }

    # Execute auto exclude missing abstracts
    cnt_noabs, stage = execute_auto_exclude_missing_abstracts(surviving_df, test_state)
    assert cnt_noabs == 2
    assert stage == "Pre_Screening"
    assert test_state["missing_abstracts_count"] == 2
    assert len(test_state["exclusion_criteria"]) == 1 # EC 1 only, no Missing Abstract in EC list!
    assert test_state["exclusion_criteria"][0]["id"] == "EC 1"

    # Save to disk (MUST NOT fail with Series is not JSON serializable)
    save_path = save_project_prisma_state(test_state, prisma_duplicates=duplicates_list, project_name=test_proj)
    assert os.path.exists(save_path)

    loaded_state = load_project_prisma_state(test_proj, valid_indices=surviving_df.index)
    assert loaded_state is not None
    assert loaded_state["missing_abstracts_count"] == 2
    print("Auto-exclude missing abstracts and project persistence passed 100%!")

    print("=== TEST 3: Horizontal Diagram Builder (In-Order Arrows & Pre-Screening Transition) ===")
    db_progressions = {
        "Scopus": {
            "initial": 50,
            "ics": [("IC 1", 30, "English"), ("IC 2", 5, "Peer-Reviewed")],
            "final": 2
        },
        "IEEE Xplore": {
            "initial": 20,
            "ics": [("IC 1", 10, "English"), ("IC 2", 2, "Peer-Reviewed")],
            "final": 1
        },
        "ACM DL": {
            "initial": 20,
            "ics": [("IC 1", 10, "English"), ("IC 2", 2, "Peer-Reviewed")],
            "final": 1
        }
    }
    ec_data = [
        {"id": "EC 1", "title": "Out of Scope", "count": 1, "remaining": 3},
        {"id": "EC 2", "title": "Data Limits", "count": 0, "remaining": 3}
    ]

    h_dot = _build_horizontal_slr_diagram(
        db_progressions=db_progressions,
        ec_data=ec_data,
        total_duplicates=3,
        total_missing_abstracts=2
    )

    # 1. Check A4 half-page constraint
    assert 'size="7.4,4.6!"' in h_dot, "Horizontal diagram must specify A4 size attribute"
    assert 'ratio="compress"' in h_dot, "Horizontal diagram must specify ratio compress"

    # 2. Check Pre-screening transition
    assert "total_retrieved_pool" in h_dot, "Horizontal diagram must contain total_retrieved_pool"
    assert "dedup_tag" in h_dot, "Horizontal diagram must contain dedup_tag"
    assert "- 3" in h_dot, "Horizontal diagram must show duplicates - 3"
    assert "noabs_tag" in h_dot, "Horizontal diagram must contain noabs_tag"
    assert "- 2" in h_dot, "Horizontal diagram must show no abstract - 2"
    assert "total_screen_pool" in h_dot, "Horizontal diagram must contain total_screen_pool"
    # total_raw_retrieved (9) - dups (3) - noabs (2) = 4 entered screening
    assert "4<br/><font point-size=\"8\" color=\"#0369A1\"><b>ENTERED SCREENING</b></font>" in h_dot

    # 3. Check strictly in-order sequential edges
    assert "total_screen_pool -> ec_box_0 [color=\"#0284C7\", penwidth=1.4];" in h_dot
    assert "ec_box_0 -> ec_box_1 [color=\"#0284C7\", penwidth=1.2];" in h_dot
    assert "ec_box_1 -> final_selected [penwidth=1.5, color=\"#16A34A\"];" in h_dot
    assert "{rank=same; ec_box_0; ec_cnt_0;}" in h_dot
    assert "{rank=same; ec_box_1; ec_cnt_1;}" in h_dot
    # Ensure previous artificial column constraint that caused jumping is GONE:
    assert "{rank=same; ec_box_0; ec_box_1;}" not in h_dot

    print("Horizontal SLR diagram layout, in-order arrows, and A4 sizing passed 100%!")

    print("=== TEST 4: Vertical Diagram Builder (Pre-Screening Transition & A4 Sizing) ===")
    v_dot = _build_vertical_slr_diagram(
        db_progressions=db_progressions,
        ec_data=ec_data,
        user_ics=[{"id": "IC 1", "title": "English"}, {"id": "IC 2", "title": "Peer-Reviewed"}],
        total_duplicates=3,
        total_missing_abstracts=2
    )

    assert 'size="6.8,5.0!"' in v_dot, "Vertical diagram must specify A4 size attribute"
    assert "IC_node_1 -> Screen" in v_dot, "Screen pool must branch off the final IC node"
    assert "IC_node_1 -> Dups" in v_dot, "Dups must branch off the final IC node"
    assert "IC_node_1 -> NoAbs" in v_dot, "NoAbs must branch off the final IC node"
    assert "{rank=same; Screen Dups NoAbs}" in v_dot, "Screen, Dups, and NoAbs must be on the same horizontal rank"
    assert "n = 4" in v_dot, "Screen pool must show n = 4"
    print("Vertical PRISMA diagram layout, pre-screening transition, and A4 sizing passed 100%!")

    # Test restoration of missing abstracts
    restored = execute_restore_missing_abstracts(surviving_df, test_state)
    assert restored == 2
    assert test_state["missing_abstracts_count"] == 0
    assert len(test_state["exclusions"]) == 0
    print("Restore missing abstracts test passed 100%!")

    # Clean up test project directory
    shutil.rmtree(os.path.join(PROJECTS_ROOT, test_proj), ignore_errors=True)
    print("=== ALL 4 INTEGRATION TESTS PASSED WITH 100% COMPLIANCE! ===")

if __name__ == "__main__":
    test_dedup_ic_pipeline()
