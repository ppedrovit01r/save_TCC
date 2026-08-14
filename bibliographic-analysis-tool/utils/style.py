import streamlit as st

def apply_custom_css():
    st.markdown("""
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <style>
        /* Unified Extended Sidebar */
        [data-testid="stSidebar"] {
            min-width: 420px !important;
            max-width: 500px !important;
            font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        }
        
        /* Make metrics pop with user's chosen Gold accent */
        [data-testid="stMetricValue"] {
            color: #C69C55 !important;
            font-weight: 700;
        }
        
        /* Replace Streamlit default red/coral rgb(255, 75, 75) on pressed/active primary buttons with #697aa2 */
        button[kind="primary"] {
            background-color: #697aa2 !important;
            border-color: #697aa2 !important;
            color: #FFFFFF !important;
        }
        
        button[kind="primary"]:hover, button[kind="primary"]:focus, button[kind="primary"]:active {
            background-color: #556589 !important;
            border-color: #556589 !important;
            color: #FFFFFF !important;
            box-shadow: 0 0 8px rgba(105, 122, 162, 0.4) !important;
        }

        button[kind="secondary"]:hover {
            border-color: #697aa2 !important;
            color: #697aa2 !important;
        }

        /* Clean divider margins */
        hr {
            margin: 0.8rem 0 !important;
        }
    </style>
    """, unsafe_allow_html=True)