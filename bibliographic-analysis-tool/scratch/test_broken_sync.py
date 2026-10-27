from streamlit.testing.v1 import AppTest

def test_broken_sync():
    code = """
import streamlit as st

if 'data' not in st.session_state:
    st.session_state.data = {'hits': 35}

# TAB 1
with st.container():
    saved_hits = st.session_state.data['hits']
    hit_key_t1 = 'hits_Scopus'
    hit_key_t5 = 'ov_p1_init_Scopus'

    if hit_key_t1 in st.session_state and st.session_state[hit_key_t1] != int(saved_hits):
        st.session_state[hit_key_t1] = int(saved_hits)

    def _on_hits_change():
        val = st.session_state[hit_key_t1]
        st.session_state.data['hits'] = val
        st.session_state[hit_key_t5] = val

    new_hits = st.number_input(
        'T1 hits',
        value=int(saved_hits),
        key=hit_key_t1,
        on_change=_on_hits_change
    )
    st.session_state.data['hits'] = new_hits
    st.session_state[hit_key_t5] = new_hits

# TAB 5
with st.container():
    hit_key_t1 = 'hits_Scopus'
    hit_key_t5 = 'ov_p1_init_Scopus'
    current_hits = int(st.session_state.data['hits'])

    if hit_key_t5 in st.session_state and st.session_state[hit_key_t5] != current_hits:
        st.session_state[hit_key_t5] = current_hits

    def _on_tab5_hits_change():
        val = st.session_state[hit_key_t5]
        st.session_state.data['hits'] = val
        st.session_state[hit_key_t1] = val

    ov_init = st.number_input(
        'T5 hits',
        value=current_hits,
        key=hit_key_t5,
        on_change=_on_tab5_hits_change
    )
    st.session_state.data['hits'] = ov_init
    st.session_state[hit_key_t1] = ov_init
"""
    at = AppTest.from_string(code)
    at.run()
    print("Initial:")
    print("t1:", at.number_input(key="hits_Scopus").value)
    print("t5:", at.number_input(key="ov_p1_init_Scopus").value)

    # Change T1 to 112
    at.number_input(key="hits_Scopus").set_value(112).run()
    print("\nAfter setting T1 to 112:")
    print("t1:", at.number_input(key="hits_Scopus").value)
    print("t5:", at.number_input(key="ov_p1_init_Scopus").value)
    print("data hits:", at.session_state.data['hits'])

test_broken_sync()
