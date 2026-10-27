import sys
sys.path.insert(0, r'c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool')
from streamlit.testing.v1 import AppTest

def test_stale_key_scenario():
    code = """
import sys
sys.path.insert(0, r'c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool')
import streamlit as st
from features.prisma_assistant import _build_horizontal_slr_diagram

# Simulating existing state where Tab 5 has stale 35
if 'prisma_state' not in st.session_state:
    st.session_state.prisma_state = {
        'db_initial_query_hits': {'Scopus': 35},
        'db_ic_progression': {'Scopus': {'IC 1': 35, 'IC 2': 35, 'IC 3': 35, 'IC 4': 35}},
        'inclusion_criteria': [
            {'id': 'IC 1', 'title': 'Publication Type'},
            {'id': 'IC 2', 'title': 'Language'},
            {'id': 'IC 3', 'title': 'Published After 2022'},
            {'id': 'IC 4', 'title': 'Open Access'}
        ],
        'exclusion_criteria': [{'id': 'EC 1', 'title': 'Out', 'count': 10}]
    }

prisma_state = st.session_state.prisma_state
db_name = 'Scopus'
user_ics = prisma_state['inclusion_criteria']

# TAB 1
with st.container():
    hit_key_t1 = f"hits_{db_name}"
    hit_key_t5 = f"ov_p1_init_{db_name}"
    
    saved_hits = int(prisma_state['db_initial_query_hits'][db_name])
    if hit_key_t1 not in st.session_state:
        st.session_state[hit_key_t1] = saved_hits
    if hit_key_t5 not in st.session_state:
        st.session_state[hit_key_t5] = saved_hits

    def _on_hits_change(db=db_name, k1=hit_key_t1, k5=hit_key_t5):
        val = st.session_state[k1]
        prisma_state['db_initial_query_hits'][db] = val
        st.session_state[k5] = val

    st.number_input(f"Hits {db_name}", min_value=0, key=hit_key_t1, on_change=_on_hits_change)

    for ic in user_ics:
        ic_id = ic['id']
        ic_key_t1 = f"ic_funnel_{db_name}_{ic_id}"
        ic_key_t5 = f"ov_p1_ic_{db_name}_{ic_id}"
        saved_ic = int(prisma_state['db_ic_progression'][db_name][ic_id])

        if ic_key_t1 not in st.session_state:
            st.session_state[ic_key_t1] = saved_ic
        if ic_key_t5 not in st.session_state:
            st.session_state[ic_key_t5] = saved_ic

        def _on_ic_change(db=db_name, iid=ic_id, k1=ic_key_t1, k5=ic_key_t5):
            val = st.session_state[k1]
            prisma_state['db_ic_progression'].setdefault(db, {})[iid] = val
            st.session_state[k5] = val

        st.number_input(f"After {ic_id} {db_name}", min_value=0, key=ic_key_t1, on_change=_on_ic_change)

# TAB 5
with st.container():
    hit_key_t1 = f"hits_{db_name}"
    hit_key_t5 = f"ov_p1_init_{db_name}"
    current_hits = int(prisma_state['db_initial_query_hits'].get(db_name, 35))

    if hit_key_t5 not in st.session_state:
        st.session_state[hit_key_t5] = current_hits

    def _on_tab5_hits_change(db=db_name, k1=hit_key_t1, k5=hit_key_t5):
        val = st.session_state[k5]
        prisma_state['db_initial_query_hits'][db] = val
        st.session_state[k1] = val

    ov_init = st.number_input(f"T5 Hits {db_name}", min_value=0, key=hit_key_t5, on_change=_on_tab5_hits_change)

    ov_ics = []
    for ic in user_ics:
        s_code = ic['id']
        s_title = ic['title']
        ic_key_t1 = f"ic_funnel_{db_name}_{s_code}"
        ic_key_t5 = f"ov_p1_ic_{db_name}_{s_code}"
        current_ic_val = int(prisma_state['db_ic_progression'].get(db_name, {}).get(s_code, 35))

        if ic_key_t5 not in st.session_state:
            st.session_state[ic_key_t5] = current_ic_val

        def _on_tab5_ic_change(db=db_name, iid=s_code, k1=ic_key_t1, k5=ic_key_t5):
            val = st.session_state[k5]
            prisma_state['db_ic_progression'].setdefault(db, {})[iid] = val
            st.session_state[k1] = val

        new_s_cnt = st.number_input(f"T5 {s_code} {db_name}", min_value=0, key=ic_key_t5, on_change=_on_tab5_ic_change)
        ov_ics.append((s_code, int(new_s_cnt), s_title))

    overridden_progressions = {
        db_name: {
            'initial': ov_init,
            'ics': ov_ics,
            'final': 35
        }
    }

    dot_string = _build_horizontal_slr_diagram(overridden_progressions, [])
    st.text(dot_string)
"""
    at = AppTest.from_string(code)
    # 1. Run initially:
    at.run()
    assert not at.exception
    assert at.number_input(key="ov_p1_init_Scopus").value == 35

    # 2. User changes Tab 1 hits to 112:
    at.number_input(key="hits_Scopus").set_value(112)
    at.number_input(key="ic_funnel_Scopus_IC 1").set_value(110)
    at.number_input(key="ic_funnel_Scopus_IC 2").set_value(109)
    at.number_input(key="ic_funnel_Scopus_IC 3").set_value(94)
    at.number_input(key="ic_funnel_Scopus_IC 4").set_value(35)
    at.run()
    assert not at.exception

    # Check Tab 5 widgets and diagram:
    assert at.number_input(key="ov_p1_init_Scopus").value == 112
    assert at.number_input(key="ov_p1_ic_Scopus_IC 1").value == 110
    assert at.number_input(key="ov_p1_ic_Scopus_IC 2").value == 109
    assert at.number_input(key="ov_p1_ic_Scopus_IC 3").value == 94
    assert at.number_input(key="ov_p1_ic_Scopus_IC 4").value == 35

    dot = at.text[0].value
    assert "Total Initial Hits: 112" in dot
    assert "Passed to Screening: 35" in dot
    assert "Scopus<br/><b>112 hits</b>" in dot
    assert "IC 1: <b>110 articles</b>" in dot
    assert "IC 2: <b>109 articles</b>" in dot
    assert "IC 3: <b>94 articles</b>" in dot
    assert "IC 4: <b>35 articles</b>" in dot

    print("STALE KEY RECOVERY TEST PASSED 100%!")

test_stale_key_scenario()
