from __future__ import annotations

import streamlit as st

from src.market_data import load_market_snapshots
from src.utils import bootstrap_page

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
    load_market_snapshots.clear()
    st.rerun()

snapshot = load_market_snapshots()
monitor_df = snapshot["high"].copy()
st.dataframe(
    monitor_df,
    use_container_width=True,
    hide_index=True,
    height=820,
)
