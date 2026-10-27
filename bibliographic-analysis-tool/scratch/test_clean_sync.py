from streamlit.testing.v1 import AppTest

def test_clean_bidirectional_sync():
    code = """
import streamlit as st

if 'data' not in st.session_state:
    st.session_state.data = {
        'hits': {'Scopus': 35},
        'ic': {'Scopus': {'IC 1': 35, 'IC 2': 35, 'IC 3': 35, 'IC 4': 35}}
    }

db_name = 'Scopus'
ics = ['IC 1', 'IC 2', 'IC 3', 'IC 4']

# --- CALLBACKS ---
def on_t1_hits():
    v = st.session_state[f'hits_{db_name}']
    st.session_state.data['hits'][db_name] = v
    st.session_state[f'ov_p1_init_{db_name}'] = v

def on_t5_hits():
    v = st.session_state[f'ov_p1_init_{db_name}']
    st.session_state.data['hits'][db_name] = v
    st.session_state[f'hits_{db_name}'] = v

def on_t1_ic(ic_id):
    v = st.session_state[f'ic_{db_name}_{ic_id}']
    st.session_state.data['ic'][db_name][ic_id] = v
    st.session_state[f'ov_p1_ic_{db_name}_{ic_id}'] = v

def on_t5_ic(ic_id):
    v = st.session_state[f'ov_p1_ic_{db_name}_{ic_id}']
    st.session_state.data['ic'][db_name][ic_id] = v
    st.session_state[f'ic_{db_name}_{ic_id}'] = v

# Ensure session_state keys are initialized if not present
k_t1_hit = f'hits_{db_name}'
k_t5_hit = f'ov_p1_init_{db_name}'
init_hit_val = st.session_state.data['hits'][db_name]
if k_t1_hit not in st.session_state:
    st.session_state[k_t1_hit] = init_hit_val
if k_t5_hit not in st.session_state:
    st.session_state[k_t5_hit] = init_hit_val

for ic_id in ics:
    k_t1_ic = f'ic_{db_name}_{ic_id}'
    k_t5_ic = f'ov_p1_ic_{db_name}_{ic_id}'
    init_ic_val = st.session_state.data['ic'][db_name][ic_id]
    if k_t1_ic not in st.session_state:
        st.session_state[k_t1_ic] = init_ic_val
    if k_t5_ic not in st.session_state:
        st.session_state[k_t5_ic] = init_ic_val

tab1, tab5 = st.tabs(["Tab 1", "Tab 5"])

with tab1:
    st.number_input("Hits (T1)", min_value=0, key=k_t1_hit, on_change=on_t1_hits)
    for ic_id in ics:
        st.number_input(f"{ic_id} (T1)", min_value=0, key=f'ic_{db_name}_{ic_id}', on_change=on_t1_ic, args=(ic_id,))

with tab5:
    st.number_input("Hits (T5)", min_value=0, key=k_t5_hit, on_change=on_t5_hits)
    for ic_id in ics:
        st.number_input(f"{ic_id} (T5)", min_value=0, key=f'ov_p1_ic_{db_name}_{ic_id}', on_change=on_t5_ic, args=(ic_id,))

    # Flowchart generation reads st.session_state.data:
    flowchart_hits = st.session_state.data['hits'][db_name]
    flowchart_ics = {ic_id: st.session_state.data['ic'][db_name][ic_id] for ic_id in ics}
    st.write(f"FLOWCHART: Hits={flowchart_hits}, ICs={flowchart_ics}")
"""
    at = AppTest.from_string(code)
    at.run()
    assert not at.exception
    print("Initial run successful!")
    print("Flowchart text:", at.markdown[-1].value)

    # 1. User updates in Tab 1:
    at.number_input(key="hits_Scopus").set_value(112)
    at.number_input(key="ic_Scopus_IC 1").set_value(110)
    at.number_input(key="ic_Scopus_IC 2").set_value(109)
    at.number_input(key="ic_Scopus_IC 3").set_value(94)
    at.number_input(key="ic_Scopus_IC 4").set_value(35)
    at.run()
    assert not at.exception
    print("\nAfter Tab 1 edits:")
    print("Flowchart text:", at.markdown[-1].value)
    print("T5 widget hits:", at.number_input(key="ov_p1_init_Scopus").value)
    print("T5 widget IC 1:", at.number_input(key="ov_p1_ic_Scopus_IC 1").value)
    print("T5 widget IC 2:", at.number_input(key="ov_p1_ic_Scopus_IC 2").value)
    print("T5 widget IC 3:", at.number_input(key="ov_p1_ic_Scopus_IC 3").value)
    print("T5 widget IC 4:", at.number_input(key="ov_p1_ic_Scopus_IC 4").value)

    assert at.number_input(key="ov_p1_init_Scopus").value == 112
    assert at.number_input(key="ov_p1_ic_Scopus_IC 1").value == 110
    assert at.number_input(key="ov_p1_ic_Scopus_IC 2").value == 109
    assert at.number_input(key="ov_p1_ic_Scopus_IC 3").value == 94
    assert at.number_input(key="ov_p1_ic_Scopus_IC 4").value == 35

    # 2. User updates in Tab 5:
    at.number_input(key="ov_p1_ic_Scopus_IC 3").set_value(99)
    at.run()
    assert not at.exception
    print("\nAfter Tab 5 edit (IC 3 -> 99):")
    print("Flowchart text:", at.markdown[-1].value)
    print("T1 widget IC 3:", at.number_input(key="ic_Scopus_IC 3").value)
    assert at.number_input(key="ic_Scopus_IC 3").value == 99

    print("\nALL ASSERTIONS PASSED PERFECTLY!")

test_clean_bidirectional_sync()
