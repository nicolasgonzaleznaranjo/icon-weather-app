from __future__ import annotations

import pandas as pd
import streamlit as st

from src.market_data import load_market_snapshots
from src.utils import bootstrap_page


bootstrap_page("Temperature Record")
st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Reference</div>
            <h1>Temperature Record</h1>
            <p>NWS forecast, Kalshi contract context, and official observed-source references organized in the same spirit as your workbook tab.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("Refresh Temperature Record"):
    load_market_snapshots.clear()
    st.rerun()

history_df = load_market_snapshots()["historical"].copy()
for column in ["NWS Forecasted High T", "NWS Forecasted Low T", "NWS Realized High T", "NWS Realized Low T"]:
    history_df[column] = history_df[column].map(lambda x: f"{int(x)}°" if pd.notna(x) else "N/A")
history_df["Delta NWS"] = history_df["Delta NWS"].map(lambda x: f"{x:+.1f}°" if pd.notna(x) else "N/A")
history_df["Delta Kalshi"] = history_df["Delta Kalshi"].map(lambda x: f"{x:+.1f}°" if pd.notna(x) else "N/A")

st.dataframe(
    history_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Forecast Source": st.column_config.LinkColumn("Forecast Source"),
        "Observed Source": st.column_config.LinkColumn("Observed Source"),
        "Climate Source": st.column_config.LinkColumn("Climate Source"),
    },
)
