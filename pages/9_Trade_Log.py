from __future__ import annotations

import streamlit as st

from src.trade_log import load_trade_log
from src.utils import bootstrap_page


bootstrap_page("Trade Log")
st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Trades</div>
            <h1>Trade Log</h1>
            <p>Ledger of weather positions, fees, exits, and results.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

trade_log = load_trade_log()
st.dataframe(
    trade_log,
    use_container_width=True,
    hide_index=True,
    column_config={
        "entry_price": st.column_config.NumberColumn("Entry Price", format="$%.2f"),
        "exit_price": st.column_config.NumberColumn("Exit Price", format="$%.2f"),
        "fees": st.column_config.NumberColumn("Fees", format="$%.2f"),
        "gross_pnl": st.column_config.NumberColumn("Gross PNL", format="$%.2f"),
        "net_pnl": st.column_config.NumberColumn("Net PNL", format="$%.2f"),
        "roi": st.column_config.NumberColumn("ROI", format="%.2f"),
    },
)
