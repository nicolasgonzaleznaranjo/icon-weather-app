from __future__ import annotations

import streamlit as st

from src.trade_log import get_effective_trade_log, load_kalshi_account_snapshot
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

snapshot = load_kalshi_account_snapshot()
trade_log, trade_source = get_effective_trade_log()

open_positions = snapshot.get("positions")
if open_positions is not None and not open_positions.empty:
    st.markdown("<div class='section-label'>Open Kalshi Positions</div>", unsafe_allow_html=True)
    st.dataframe(
        open_positions[
            [
                "market",
                "nws_station",
                "high_low",
                "contract_threshold",
                "direction",
                "contracts",
                "fees",
                "net_pnl",
                "status",
                "market_ticker",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        height=320,
        column_config={
            "fees": st.column_config.NumberColumn("Fees", format="$%.2f"),
            "net_pnl": st.column_config.NumberColumn("Realized PNL", format="$%.2f"),
        },
    )

st.markdown(
    f"<div class='section-label'>{'Live Closed Ledger' if trade_source == 'kalshi' else 'Imported Ledger'}</div>",
    unsafe_allow_html=True,
)
closed_df = trade_log[trade_log["status"].str.lower() != "open"].copy()
st.dataframe(
    closed_df,
    use_container_width=True,
    hide_index=True,
    height=640,
    column_config={
        "entry_price": st.column_config.NumberColumn("Entry Price", format="$%.2f"),
        "exit_price": st.column_config.NumberColumn("Exit Price", format="$%.2f"),
        "fees": st.column_config.NumberColumn("Fees", format="$%.2f"),
        "gross_pnl": st.column_config.NumberColumn("Gross PNL", format="$%.2f"),
        "net_pnl": st.column_config.NumberColumn("Net PNL", format="$%.2f"),
        "roi": st.column_config.NumberColumn("ROI", format="%.2f"),
    },
)
