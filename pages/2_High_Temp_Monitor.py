from __future__ import annotations

import streamlit as st

from src.market_data import load_high_monitor_rows
from src.utils import bootstrap_page, render_monitor_table

bootstrap_page("High Temperature Monitor")
st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Monitor</div>
            <h1>High Temperature Monitor</h1>
            <p>One-line city monitor for the high-temp setup, matching the workbook shape and keeping only the fields you actually scan.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("Refresh High Temp Data"):
    load_high_monitor_rows.clear()
    st.rerun()

monitor_df = load_high_monitor_rows().copy()
highlight_city = st.selectbox("Highlight city", ["None"] + monitor_df["City"].tolist(), key="high-highlight")
render_monitor_table(monitor_df, highlight_city=None if highlight_city == "None" else highlight_city)
