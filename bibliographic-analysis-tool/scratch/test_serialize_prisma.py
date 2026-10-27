import json
import os

def serialize_prisma_state(state):
    serializable = {}
    for k, v in state.items():
        if k == 'exclusions':
            # keys can be numpy.int64 or int
            serializable[k] = {str(idx): val for idx, val in v.items()}
        elif k in ('screening_queue', 'screened_ok'):
            serializable[k] = [int(idx) if str(idx).isdigit() else str(idx) for idx in v]
        elif k in ('db_initial_query_hits', 'db_final_overrides', 'ec_overrides', 'file_db_mapping', 'custom_reasons', 'mode'):
            serializable[k] = v
        elif k == 'db_ic_progression':
            # {db: {ic_id: int}}
            serializable[k] = {str(db): {str(ic): int(cnt) for ic, cnt in prog.items()} for db, prog in v.items()}
        elif k in ('inclusion_criteria', 'exclusion_criteria'):
            serializable[k] = [dict(c) for c in v]
        else:
            try:
                json.dumps(v)
                serializable[k] = v
            except Exception:
                pass
    return serializable

def deserialize_prisma_state(data, valid_indices=None):
    state = dict(data)
    if 'exclusions' in state and isinstance(state['exclusions'], dict):
        # convert string index keys back to int if numeric
        rebuilt_ex = {}
        for idx_str, val in state['exclusions'].items():
            k = int(idx_str) if idx_str.isdigit() else idx_str
            rebuilt_ex[k] = val
        state['exclusions'] = rebuilt_ex
    if 'screening_queue' in state and isinstance(state['screening_queue'], list):
        state['screening_queue'] = [int(i) if str(i).isdigit() else str(i) for i in state['screening_queue']]
        if valid_indices is not None:
            state['screening_queue'] = [i for i in state['screening_queue'] if i in valid_indices]
    if 'screened_ok' in state and isinstance(state['screened_ok'], list):
        state['screened_ok'] = [int(i) if str(i).isdigit() else str(i) for i in state['screened_ok']]
        if valid_indices is not None:
            state['screened_ok'] = [i for i in state['screened_ok'] if i in valid_indices]
    return state

# Test
test_state = {
    'mode': 'advanced',
    'exclusions': {0: {'code': 'EC 1', 'reason': 'Out of scope'}},
    'screening_queue': [1, 2, 3],
    'screened_ok': [4],
    'db_initial_query_hits': {'Scopus': 112},
    'db_ic_progression': {'Scopus': {'IC 1': 110, 'IC 2': 109, 'IC 3': 94, 'IC 4': 35}},
    'inclusion_criteria': [{'id': 'IC 1', 'title': 'Test'}],
    'exclusion_criteria': [{'id': 'EC 1', 'title': 'Test'}]
}

s = serialize_prisma_state(test_state)
json_str = json.dumps(s, indent=2)
loaded = json.loads(json_str)
d = deserialize_prisma_state(loaded, valid_indices={0, 1, 2, 3, 4})
assert d['db_initial_query_hits']['Scopus'] == 112
assert d['db_ic_progression']['Scopus']['IC 3'] == 94
assert 0 in d['exclusions']
print("TEST PASSED! Serialization & Deserialization work perfectly.")
