from __future__ import annotations

import pandas as pd
import streamlit as st

from src.charts import (
    metric_card_row,
    plot_cumulative_pnl,
    plot_daily_pnl,
    plot_pnl_by_market,
    plot_pnl_distribution,
    plot_win_loss_breakdown,
)
from src.trade_log import (
    compute_trade_kpis,
    get_best_worst_days,
    get_market_performance,
    load_trade_log,
    recent_trades_table,
)
from src.utils import bootstrap_page


bootstrap_page("Performance Overview")

st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Performance Overview</div>
            <h1>ICON Weather App</h1>
            <p>Fast operating view for PNL, hit rate, market mix, and what mattered most recently.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

trade_log = load_trade_log()
kpis = compute_trade_kpis(trade_log)
market_perf = get_market_performance(trade_log)
recent_trades = recent_trades_table(trade_log, limit=12)
best_day, worst_day = get_best_worst_days(trade_log)

metric_card_row(
    [
        ("Total PNL", f"${kpis['total_pnl']:,.2f}", "positive" if kpis["total_pnl"] >= 0 else "negative"),
        ("Total Trades", f"{kpis['total_trades']}", ""),
        ("Win Rate", f"{kpis['win_rate']:.1%}", "positive" if kpis["win_rate"] >= 0.5 else ""),
        ("ROI Total", f"{kpis['roi_total']:.1%}", "positive" if kpis["roi_total"] >= 0 else "negative"),
        ("Profit Factor", f"{kpis['profit_factor']:.2f}", "positive" if kpis["profit_factor"] >= 1 else "negative"),
    ]
)

metric_card_row(
    [
        ("Average Win", f"${kpis['average_win']:,.2f}", "positive"),
        ("Average Loss", f"${kpis['average_loss']:,.2f}", "negative"),
        ("Largest Win", f"${kpis['largest_win']:,.2f}", "positive"),
        ("Largest Loss", f"${kpis['largest_loss']:,.2f}", "negative"),
        ("Max Drawdown", f"${kpis['max_drawdown']:,.2f}", "negative"),
    ]
)

insight_cols = st.columns(4)
with insight_cols[0]:
    st.markdown("<div class='section-label'>Best Market</div>", unsafe_allow_html=True)
    if market_perf.empty:
        st.info("No market data yet.")
    else:
        best_market = market_perf.sort_values("net_pnl", ascending=False).iloc[0]
        st.markdown(
            f"<div class='mini-panel'><strong>{best_market['market']}</strong><br><span class='metric-positive'>${best_market['net_pnl']:,.2f}</span></div>",
            unsafe_allow_html=True,
        )
with insight_cols[1]:
    st.markdown("<div class='section-label'>Worst Market</div>", unsafe_allow_html=True)
    if market_perf.empty:
        st.info("No market data yet.")
    else:
        worst_market = market_perf.sort_values("net_pnl", ascending=True).iloc[0]
        st.markdown(
            f"<div class='mini-panel'><strong>{worst_market['market']}</strong><br><span class='metric-negative'>${worst_market['net_pnl']:,.2f}</span></div>",
            unsafe_allow_html=True,
        )
with insight_cols[2]:
    st.markdown("<div class='section-label'>Best Day</div>", unsafe_allow_html=True)
    if best_day is None:
        st.info("No closed-day data yet.")
    else:
        st.markdown(
            f"<div class='mini-panel'><strong>{best_day['close_day']}</strong><br><span class='metric-positive'>${best_day['net_pnl']:,.2f}</span></div>",
            unsafe_allow_html=True,
        )
with insight_cols[3]:
    st.markdown("<div class='section-label'>Worst Day</div>", unsafe_allow_html=True)
    if worst_day is None:
        st.info("No closed-day data yet.")
    else:
        st.markdown(
            f"<div class='mini-panel'><strong>{worst_day['close_day']}</strong><br><span class='metric-negative'>${worst_day['net_pnl']:,.2f}</span></div>",
            unsafe_allow_html=True,
        )

chart_col1, chart_col2 = st.columns((1.3, 1))
with chart_col1:
    st.markdown("<div class='section-label'>Cumulative PNL</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_cumulative_pnl(trade_log), use_container_width=True)
with chart_col2:
    st.markdown("<div class='section-label'>Daily PNL</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_daily_pnl(trade_log), use_container_width=True)

chart_col3, chart_col4 = st.columns((1.2, 1))
with chart_col3:
    st.markdown("<div class='section-label'>PNL by Market</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_pnl_by_market(market_perf), use_container_width=True)
with chart_col4:
    st.markdown("<div class='section-label'>Win / Loss Breakdown</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_win_loss_breakdown(trade_log), use_container_width=True)

chart_col5, chart_col6 = st.columns((1.2, 1))
with chart_col5:
    st.markdown("<div class='section-label'>PNL Distribution</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_pnl_distribution(trade_log), use_container_width=True)
with chart_col6:
    st.markdown("<div class='section-label'>Most Active Markets</div>", unsafe_allow_html=True)
    if market_perf.empty:
        st.info("No market activity yet.")
    else:
        active = market_perf.sort_values("total_trades", ascending=False).head(8).copy()
        active["Win Rate"] = active["win_rate"].map(lambda x: f"{x:.0%}" if pd.notna(x) else "N/A")
        active["Net PNL"] = active["net_pnl"].map(lambda x: f"${x:,.2f}")
        st.dataframe(
            active[["market", "total_trades", "Win Rate", "Net PNL"]].rename(
                columns={"market": "Market", "total_trades": "Trades"}
            ),
            use_container_width=True,
            hide_index=True,
        )

st.markdown("<div class='section-label'>Recent Trades</div>", unsafe_allow_html=True)
st.dataframe(
    recent_trades,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Entry Price": st.column_config.NumberColumn(format="$%.2f"),
        "Exit Price": st.column_config.NumberColumn(format="$%.2f"),
        "Fees": st.column_config.NumberColumn(format="$%.2f"),
        "Net PNL": st.column_config.NumberColumn(format="$%.2f"),
        "ROI": st.column_config.NumberColumn(format="%.1f%%"),
    },
)
