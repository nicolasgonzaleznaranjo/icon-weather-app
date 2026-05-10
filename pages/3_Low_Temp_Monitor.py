from __future__ import annotations

import pandas as pd
import streamlit as st

from src.market_data import load_market_snapshots
from src.utils import bootstrap_page, display_delta, display_pct, display_price


bootstrap_page("Low Temperature Monitor")
st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Monitor</div>
            <h1>Low Temperature Monitor</h1>
            <p>Daily minimum temperature view for overnight and early-session setups, with the same discipline around price, distance, and timing.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("Refresh Low Temp Data"):
    load_market_snapshots.clear()
    st.rerun()

snapshot = load_market_snapshots()
monitor_df = snapshot["low"].copy()

summary_cols = st.columns(4)
summary_cols[0].metric("Strong Candidates", int((monitor_df["Status"] == "Strong candidate").sum()))
summary_cols[1].metric("Tradable", int((monitor_df["Status"] == "Tradable").sum()))
summary_cols[2].metric("Watch", int((monitor_df["Status"] == "Watch").sum()))
summary_cols[3].metric("Contracts Loaded", int(len(monitor_df)))

display_df = monitor_df.copy()
display_df["Observed Today"] = display_df["Observed Today"].map(lambda x: f"{int(x)}°" if pd.notna(x) else "N/A")
display_df["Forecast Low"] = display_df["Forecast Low"].map(lambda x: f"{int(x)}°" if pd.notna(x) else "N/A")
display_df["YES Price"] = display_df["YES Price"].map(display_price)
display_df["NO Price"] = display_df["NO Price"].map(display_price)
display_df["Implied Probability"] = display_df["Implied Probability"].map(display_pct)
display_df["Distance"] = display_df["Distance"].map(display_delta)
display_df["Edge"] = display_df["Edge"].map(display_pct)
display_df["Forecast Updated"] = display_df["Forecast Updated"].fillna("N/A")

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Market Link": st.column_config.LinkColumn("Market Link"),
        "NWS Forecast URL": st.column_config.LinkColumn("NWS Forecast URL"),
        "Observed Source": st.column_config.LinkColumn("Observed Source"),
    },
)
