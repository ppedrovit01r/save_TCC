import streamlit as st

def apply_custom_css():
    st.html("""
    <style>
        /* Style the persistent left column to look like a secondary menu */
        .persistent-menu {
            background-color: var(--secondary-background-color);
            padding: 20px;
            border-radius: 10px;
            border-left: 4px solid var(--primary-color);
            height: 100%;
        }
        
        /* Make metrics pop slightly more */
        [data-testid="stMetricValue"] {
            color: var(--primary-color);
        }
    </style>
    """)