import streamlit as st

def apply_custom_css():
    st.markdown("""
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <style>
        /* Unified Extended Sidebar: Only enforce min-width when sidebar is expanded */
        [data-testid="stSidebar"][aria-expanded="true"],
        section[data-testid="stSidebar"]:not([aria-expanded="false"]) {
            min-width: 420px !important;
            max-width: 500px !important;
            font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            transition: min-width 0.3s ease-in-out, max-width 0.3s ease-in-out, transform 0.3s ease-in-out !important;
        }

        /* Clean collapse: zero width, margin, and padding so the layout has NO empty space and no negative offset */
        [data-testid="stSidebar"][aria-expanded="false"],
        section[data-testid="stSidebar"][aria-expanded="false"] {
            min-width: 0px !important;
            max-width: 0px !important;
            width: 0px !important;
            margin: 0px !important;
            padding: 0px !important;
            border: none !important;
            overflow: hidden !important;
            transition: min-width 0.3s ease-in-out, max-width 0.3s ease-in-out, transform 0.3s ease-in-out !important;
        }

        /* Hide sidebar internal contents when collapsed so nothing leaks into layout */
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"],
        [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarResizeHandle"] {
            display: none !important;
        }

        /* Prominent expand sidebar button when sidebar is collapsed (Streamlit 1.42+) */
        button[data-testid="stExpandSidebarButton"],
        [data-testid="stExpandSidebarButton"] {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            visibility: visible !important;
            opacity: 1 !important;
            background-color: #FFFFFF !important;
            border: 1.5px solid #697aa2 !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 8px rgba(105, 122, 162, 0.25) !important;
            color: #697aa2 !important;
            padding: 4px 10px !important;
            cursor: pointer !important;
            transition: all 0.2s ease-in-out !important;
        }

        button[data-testid="stExpandSidebarButton"]:hover,
        [data-testid="stExpandSidebarButton"]:hover {
            background-color: #697aa2 !important;
            color: #FFFFFF !important;
            border-color: #556589 !important;
            transform: scale(1.05) !important;
            box-shadow: 0 4px 12px rgba(105, 122, 162, 0.4) !important;
        }

        [data-testid="stExpandSidebarButton"] svg,
        [data-testid="stExpandSidebarButton"] span {
            fill: currentColor !important;
            color: inherit !important;
        }

        [data-testid="stExpandSidebarButton"]::after {
            content: " Expand Sidebar";
            font-size: 12px;
            font-weight: 600;
            margin-left: 6px;
            color: inherit;
            white-space: nowrap;
        }

        /* Prominent collapse sidebar button inside sidebar header */
        button[data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapseButton"] button {
            color: #697aa2 !important;
            border-radius: 6px !important;
            transition: all 0.2s ease-in-out !important;
        }

        button[data-testid="stSidebarCollapseButton"]:hover,
        [data-testid="stSidebarCollapseButton"] button:hover {
            background-color: rgba(105, 122, 162, 0.15) !important;
            color: #556589 !important;
        }

        /* Fallback for older Streamlit collapsed controls */
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"] {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            visibility: visible !important;
            opacity: 1 !important;
            background-color: #FFFFFF !important;
            border: 1.5px solid #697aa2 !important;
            border-radius: 8px !important;
            box-shadow: 0 2px 8px rgba(105, 122, 162, 0.25) !important;
            color: #697aa2 !important;
            padding: 4px 10px !important;
            cursor: pointer !important;
            transition: all 0.2s ease-in-out !important;
        }

        [data-testid="stSidebarCollapsedControl"]:hover,
        [data-testid="collapsedControl"]:hover {
            background-color: #697aa2 !important;
            color: #FFFFFF !important;
            border-color: #556589 !important;
            transform: scale(1.05) !important;
            box-shadow: 0 4px 12px rgba(105, 122, 162, 0.4) !important;
        }

        /* Allow main container to smoothly expand to 100% full viewport width */
        .main,
        [data-testid="stMain"] {
            transition: all 0.3s ease-in-out !important;
        }

        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 100% !important;
            padding-top: 3.5rem !important;
            padding-bottom: 3rem !important;
            padding-left: 2.5rem !important;
            padding-right: 2.5rem !important;
            transition: padding 0.3s ease-in-out !important;
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

        /* Flush right-alignment for download buttons in header bars and action columns */
        div[data-testid="stDownloadButton"],
        div.stDownloadButton {
            display: flex !important;
            justify-content: flex-end !important;
            width: 100% !important;
        }
        div[data-testid="stDownloadButton"] > button,
        div.stDownloadButton > button,
        div[data-testid="stDownloadButton"] > a,
        div.stDownloadButton > a {
            margin-left: auto !important;
        }
    </style>
    """, unsafe_allow_html=True)