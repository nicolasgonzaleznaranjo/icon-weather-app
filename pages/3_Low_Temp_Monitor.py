from __future__ import annotations

import streamlit as st

from src.market_data import load_low_monitor_rows
from src.utils import bootstrap_page

bootstrap_page("Low Temperature Monitor")
st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Monitor</div>
            <h1>Low Temperature Monitor</h1>
            <p>One-line city monitor for the low-temp setup, using the same workbook order and hiding all the link clutter.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("Refresh Low Temp Data"):
    load_low_monitor_rows.clear()
    st.rerun()

monitor_df = load_low_monitor_rows().copy()
st.dataframe(
    monitor_df,
    use_container_width=True,
    hide_index=True,
    height=820,
)
