from __future__ import annotations

import streamlit as st


st.set_page_config(page_title="ICON Weather App", layout="wide", initial_sidebar_state="expanded")

navigation = st.navigation(
    [
        st.Page("views/dashboard.py", title="Dashboard", icon=":material/home:", default=True),
        st.Page("pages/2_High_Temp_Monitor.py", title="High Temp Monitor"),
        st.Page("pages/3_Low_Temp_Monitor.py", title="Low Temp Monitor"),
        st.Page("pages/4_Market_Map.py", title="Market Map"),
        st.Page("pages/8_Temperature_Record.py", title="Temperature Record"),
        st.Page("pages/9_Trade_Log.py", title="Trade Log"),
    ],
    position="sidebar",
)

navigation.run()
