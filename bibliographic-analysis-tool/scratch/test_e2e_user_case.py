from streamlit.testing.v1 import AppTest

def test_user_reproduction():
    code = """
import sys
sys.path.insert(0, r'c:/Users/pedro/Videos/save_TCC/bibliographic-analysis-tool')
import streamlit as st
from features.prisma_assistant import _build_horizontal_slr_diagram, compute_balanced_database_survival

if 'prisma_state' not in st.session_state:
    st.session_state.prisma_state = {
        'db_initial_query_hits': {},
        'db_ic_progression': {},
        'ec_overrides': {},
        'inclusion_criteria': [
            {'id': 'IC 1', 'title': 'Publication Type'},
            {'id': 'IC 2', 'title': 'Language'},
            {'id': 'IC 3', 'title': 'Published After 2022'},
            {'id': 'IC 4', 'title': 'Open Access'}
        ],
        'exclusion_criteria': [
            {'id': 'EC 1', 'title': 'Out of Scope'},
            {'id': 'EC 2', 'title': 'No Evaluation'}
        ]
    }

prisma_state = st.session_state.prisma_state

db_groups = {
    'Scopus': {'imported_count': 35},
    'SpringerLink': {'imported_count': 200},
    'IEEE Xplore': {'imported_count': 9}
}

user_ics = prisma_state['inclusion_criteria']
user_ecs = prisma_state['exclusion_criteria']

tab1, tab5 = st.tabs(["1. Database Provenance", "5. PRISMA Flowchart"])

# --- TAB 1 ---
with tab1:
    for db_name, grp in db_groups.items():
        imported_cnt = grp['imported_count']
        hit_key_t1 = f"hits_{db_name}"
        hit_key_t5 = f"ov_p1_init_{db_name}"

        if db_name not in prisma_state['db_initial_query_hits']:
            prisma_state['db_initial_query_hits'][db_name] = imported_cnt
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

        if db_name not in prisma_state['db_ic_progression']:
            prisma_state['db_ic_progression'][db_name] = {}

        for ic in user_ics:
            ic_id = ic['id']
            ic_key_t1 = f"ic_funnel_{db_name}_{ic_id}"
            ic_key_t5 = f"ov_p1_ic_{db_name}_{ic_id}"

            if ic_id not in prisma_state['db_ic_progression'][db_name]:
                prisma_state['db_ic_progression'][db_name][ic_id] = imported_cnt
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

# --- TAB 5 ---
with tab5:
    db_progressions = {}
    for db_name, grp in db_groups.items():
        init_val = prisma_state['db_initial_query_hits'].get(db_name, grp['imported_count'])
        ic_steps = []
        saved_ic_dict = prisma_state.get('db_ic_progression', {}).get(db_name, {})
        for ic in user_ics:
            ic_id = ic['id']
            ic_title = ic['title']
            val = saved_ic_dict.get(ic_id, grp['imported_count'])
            ic_steps.append((ic_id, int(val), ic_title))
        db_progressions[db_name] = {
            'initial': int(init_val),
            'ics': ic_steps,
            'final': 10
        }

    overridden_progressions = {}
    for db_name, pdata in db_progressions.items():
        hit_key_t1 = f"hits_{db_name}"
        hit_key_t5 = f"ov_p1_init_{db_name}"
        current_hits = int(prisma_state['db_initial_query_hits'].get(db_name, pdata['initial']))
        if hit_key_t5 not in st.session_state:
            st.session_state[hit_key_t5] = current_hits

        def _on_tab5_hits_change(db=db_name, k1=hit_key_t1, k5=hit_key_t5):
            val = st.session_state[k5]
            prisma_state['db_initial_query_hits'][db] = val
            st.session_state[k1] = val

        ov_init = st.number_input(f"T5 Hits {db_name}", min_value=0, key=hit_key_t5, on_change=_on_tab5_hits_change)

        ov_ics = []
        for s_code, s_cnt, s_title in pdata['ics']:
            ic_key_t1 = f"ic_funnel_{db_name}_{s_code}"
            ic_key_t5 = f"ov_p1_ic_{db_name}_{s_code}"
            current_ic_val = int(prisma_state['db_ic_progression'].get(db_name, {}).get(s_code, s_cnt))
            if ic_key_t5 not in st.session_state:
                st.session_state[ic_key_t5] = current_ic_val

            def _on_tab5_ic_change(db=db_name, iid=s_code, k1=ic_key_t1, k5=ic_key_t5):
                val = st.session_state[k5]
                prisma_state['db_ic_progression'].setdefault(db, {})[iid] = val
                st.session_state[k1] = val

            new_s_cnt = st.number_input(f"T5 {s_code} {db_name}", min_value=0, key=ic_key_t5, on_change=_on_tab5_ic_change)
            ov_ics.append((s_code, int(new_s_cnt), s_title))

        overridden_progressions[db_name] = {
            'initial': ov_init,
            'ics': ov_ics,
            'final': pdata['final']
        }

    dot_string = _build_horizontal_slr_diagram(overridden_progressions, [{'id': 'EC 1', 'title': 'Out', 'count': 10, 'remaining': 234}])
    st.text(dot_string)
"""
    at = AppTest.from_string(code)
    at.run()
    assert not at.exception

    # User inputs what was in Image 2:
    at.number_input(key="hits_Scopus").set_value(112)
    at.number_input(key="ic_funnel_Scopus_IC 1").set_value(110)
    at.number_input(key="ic_funnel_Scopus_IC 2").set_value(109)
    at.number_input(key="ic_funnel_Scopus_IC 3").set_value(94)
    at.number_input(key="ic_funnel_Scopus_IC 4").set_value(35)
    at.run()
    assert not at.exception

    # Verify Tab 5 widgets received the user inputs
    print("Tab 5 hits_Scopus widget:", at.number_input(key="ov_p1_init_Scopus").value)
    print("Tab 5 IC 1 widget:", at.number_input(key="ov_p1_ic_Scopus_IC 1").value)
    print("Tab 5 IC 2 widget:", at.number_input(key="ov_p1_ic_Scopus_IC 2").value)
    print("Tab 5 IC 3 widget:", at.number_input(key="ov_p1_ic_Scopus_IC 3").value)
    print("Tab 5 IC 4 widget:", at.number_input(key="ov_p1_ic_Scopus_IC 4").value)

    assert at.number_input(key="ov_p1_init_Scopus").value == 112
    assert at.number_input(key="ov_p1_ic_Scopus_IC 1").value == 110
    assert at.number_input(key="ov_p1_ic_Scopus_IC 2").value == 109
    assert at.number_input(key="ov_p1_ic_Scopus_IC 3").value == 94
    assert at.number_input(key="ov_p1_ic_Scopus_IC 4").value == 35

    # Check dot string in Tab 5
    dot = at.text[0].value
    print("\nTotal hits in diagram:", "Total Initial Hits: 321" in dot)
    print("Passed to screening in diagram:", "Passed to Screening: 244" in dot)
    print("Scopus 112 hits in diagram:", "Scopus<br/><b>112 hits</b>" in dot)
    print("Scopus IC 1: 110 in diagram:", "IC 1: <b>110 articles</b>" in dot)
    print("Scopus IC 2: 109 in diagram:", "IC 2: <b>109 articles</b>" in dot)
    print("Scopus IC 3: 94 in diagram:", "IC 3: <b>94 articles</b>" in dot)
    print("Scopus IC 4: 35 in diagram:", "IC 4: <b>35 articles</b>" in dot)

    assert "Total Initial Hits: 321" in dot
    assert "Passed to Screening: 244" in dot
    assert "Scopus<br/><b>112 hits</b>" in dot
    assert "IC 1: <b>110 articles</b>" in dot
    assert "IC 2: <b>109 articles</b>" in dot
    assert "IC 3: <b>94 articles</b>" in dot
    assert "IC 4: <b>35 articles</b>" in dot

    print("\nSUCCESS! E2E REPRODUCTION VERIFIED!")

test_user_reproduction()
