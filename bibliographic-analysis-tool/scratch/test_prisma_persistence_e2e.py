import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import shutil
import pandas as pd
import json

from utils.project_manager import (
    save_project_prisma_state,
    load_project_prisma_state,
    migrate_project_data,
    get_project_root,
    PROJECTS_ROOT
)

def run_e2e_persistence_test():
    test_proj = "Test_SLR_Persistence_Project"
    migrated_proj = "Test_SLR_Migrated_Project"

    # Clean up test dirs if existing
    for p in [test_proj, migrated_proj]:
        p_path = os.path.join(PROJECTS_ROOT, p)
        if os.path.exists(p_path):
            shutil.rmtree(p_path, ignore_errors=True)

    test_indices = [0, 1, 2, 3, 4]
    mock_df = pd.DataFrame({
        'Title': [f"Study {i}" for i in test_indices],
        'Source File': ['Scopus_Query.csv'] * 5
    }, index=test_indices)

    # 1. Construct representative SLR state with user custom numbers
    original_state = {
        'mode': 'advanced',
        'exclusions': {
            1: {
                'code': 'EC 1',
                'reason': 'Missing Abstract',
                'full_text': 'EC 1: Missing Abstract',
                'stage': 'Title_Abstract'
            },
            3: {
                'code': 'EC 2',
                'reason': 'Grey Literature',
                'full_text': 'EC 2: Grey Literature',
                'stage': 'Title_Abstract'
            }
        },
        'custom_reasons': ['Missing Abstract', 'Grey Literature', 'Non-English'],
        'screening_queue': [0, 2],
        'screened_ok': [4],
        'file_db_mapping': {'Scopus_Query.csv': 'Scopus'},
        'db_initial_query_hits': {'Scopus': 112},
        'db_ic_progression': {
            'Scopus': {
                'IC 1': 110,
                'IC 2': 109,
                'IC 3': 94,
                'IC 4': 35
            }
        },
        'inclusion_criteria': [
            {'id': 'IC 1', 'title': 'Peer-reviewed', 'desc': 'Must be peer-reviewed'},
            {'id': 'IC 2', 'title': 'English', 'desc': 'Must be written in English'},
            {'id': 'IC 3', 'title': 'AI focus', 'desc': 'Must involve AI/ML'},
            {'id': 'IC 4', 'title': 'Empirical', 'desc': 'Must contain empirical results'}
        ],
        'exclusion_criteria': [
            {'id': 'EC 1', 'title': 'Missing Abstract', 'stage': 'Title_Abstract', 'desc': 'No abstract'},
            {'id': 'EC 2', 'title': 'Grey Literature', 'stage': 'Title_Abstract', 'desc': 'Non-academic'}
        ],
        'ec_overrides': {'EC 1': 1, 'EC 2': 1},
        'db_final_overrides': {'Scopus': 1}
    }

    # 2. Save state
    save_path = save_project_prisma_state(original_state, project_name=test_proj)
    assert os.path.exists(save_path), f"File {save_path} does not exist!"
    print(f"[OK] State saved to {save_path}")

    # 3. Read back and verify JSON format
    with open(save_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data['db_initial_query_hits']['Scopus'] == 112
    assert data['db_ic_progression']['Scopus']['IC 3'] == 94
    assert data['db_ic_progression']['Scopus']['IC 4'] == 35
    print("[OK] JSON payload verified on disk")

    # 4. Load via load_project_prisma_state
    loaded = load_project_prisma_state(project_name=test_proj, valid_indices=mock_df.index)
    assert loaded is not None, "Failed to load state"
    assert loaded['mode'] == 'advanced'
    assert loaded['db_initial_query_hits']['Scopus'] == 112
    assert loaded['db_ic_progression']['Scopus']['IC 1'] == 110
    assert loaded['db_ic_progression']['Scopus']['IC 2'] == 109
    assert loaded['db_ic_progression']['Scopus']['IC 3'] == 94
    assert loaded['db_ic_progression']['Scopus']['IC 4'] == 35
    assert len(loaded['inclusion_criteria']) == 4
    assert len(loaded['exclusion_criteria']) == 2
    assert 1 in loaded['exclusions'] and isinstance(loaded['exclusions'][1], dict)
    assert loaded['exclusions'][1]['code'] == 'EC 1'
    assert 3 in loaded['exclusions']
    assert loaded['screening_queue'] == [0, 2]
    assert loaded['screened_ok'] == [4]
    print("[OK] State deserialization & type reconstruction verified 100%")

    # 5. Test migration / renaming
    migrate_project_data(test_proj, migrated_proj)
    migrated_file = os.path.join(PROJECTS_ROOT, migrated_proj, "prisma_state.json")
    assert os.path.exists(migrated_file), f"Migrated state {migrated_file} does not exist!"
    loaded_migrated = load_project_prisma_state(project_name=migrated_proj, valid_indices=mock_df.index)
    assert loaded_migrated['db_initial_query_hits']['Scopus'] == 112
    assert loaded_migrated['db_ic_progression']['Scopus']['IC 4'] == 35
    print("[OK] Project renaming migration verified 100%")

    # Cleanup
    for p in [test_proj, migrated_proj]:
        p_path = os.path.join(PROJECTS_ROOT, p)
        if os.path.exists(p_path):
            shutil.rmtree(p_path, ignore_errors=True)

    print("\nALL PRISMA PERSISTENCE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_e2e_persistence_test()
