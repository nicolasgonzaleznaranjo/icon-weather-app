from __future__ import annotations

import pandas as pd
import streamlit as st

from src.charts import build_map_deck
from src.market_data import load_map_rows
from src.utils import bootstrap_page


bootstrap_page("Market Map")
st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Context</div>
            <h1>Market Map</h1>
            <p>Portfolio and forecast context across the full 20-city weather universe.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button("Refresh Map Data"):
    load_map_rows.clear()
    st.rerun()

map_df = load_map_rows().copy()
deck = build_map_deck(map_df)
if deck is not None:
    st.pydeck_chart(deck, use_container_width=True)
else:
    st.info("Map data is not available yet.")

focus_city = st.selectbox("Map focus", map_df["market_name"].tolist())
focus_row = map_df.loc[map_df["market_name"] == focus_city].iloc[0]
focus_cols = st.columns(4)
focus_cols[0].metric("Forecast High / Low", f"{focus_row['forecast_high']} / {focus_row['forecast_low']}")
focus_cols[1].metric("Current PNL", focus_row["current_pnl"])
focus_cols[2].metric("Total Trades", int(focus_row["total_trades"]))
focus_cols[3].metric("Win Rate", focus_row["win_rate"])

st.markdown("<div class='section-label'>Map Table</div>", unsafe_allow_html=True)
st.dataframe(map_df.drop(columns=["color", "radius"]), use_container_width=True, hide_index=True)
