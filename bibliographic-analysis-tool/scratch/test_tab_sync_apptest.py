from streamlit.testing.v1 import AppTest

def test_sync():
    code = """
import streamlit as st

if 'data' not in st.session_state:
    st.session_state.data = {'hits': 35}

def on_t1():
    val = st.session_state['t1_hits']
    st.session_state.data['hits'] = val
    st.session_state['t5_hits'] = val

def on_t5():
    val = st.session_state['t5_hits']
    st.session_state.data['hits'] = val
    st.session_state['t1_hits'] = val

tab1, tab5 = st.tabs(["Tab 1", "Tab 5"])

with tab1:
    v1 = st.session_state.data['hits']
    if 't1_hits' not in st.session_state:
        st.session_state['t1_hits'] = v1
    n1 = st.number_input("T1 Hits", min_value=0, key="t1_hits", on_change=on_t1)

with tab5:
    v5 = st.session_state.data['hits']
    if 't5_hits' not in st.session_state:
        st.session_state['t5_hits'] = v5
    n5 = st.number_input("T5 Hits", min_value=0, key="t5_hits", on_change=on_t5)
    st.write(f"Flowchart Hits: {st.session_state.data['hits']}")
"""
    at = AppTest.from_string(code)
    at.run()
    print("Initial run:")
    print("t1_hits:", at.number_input(key="t1_hits").value)
    print("t5_hits:", at.number_input(key="t5_hits").value)
    print("text:", at.markdown[0].value if at.markdown else at.text)

    # Now change t1_hits to 112
    at.number_input(key="t1_hits").set_value(112).run()
    print("\nAfter setting t1_hits to 112:")
    print("t1_hits:", at.number_input(key="t1_hits").value)
    print("t5_hits:", at.number_input(key="t5_hits").value)
    print("data['hits']:", at.session_state.data['hits'])

    # Now change t5_hits to 200
    at.number_input(key="t5_hits").set_value(200).run()
    print("\nAfter setting t5_hits to 200:")
    print("t1_hits:", at.number_input(key="t1_hits").value)
    print("t5_hits:", at.number_input(key="t5_hits").value)
    print("data['hits']:", at.session_state.data['hits'])

test_sync()
