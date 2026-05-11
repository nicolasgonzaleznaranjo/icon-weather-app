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
from src.market_data import load_home_snapshot
from src.trade_log import (
    compute_trade_kpis,
    get_best_worst_days,
    get_market_performance,
    recent_trades_table,
)
from src.utils import bootstrap_page


bootstrap_page("Dashboard")

st.markdown(
    """
    <div class="hero-block">
        <div>
            <div class="eyebrow">Dashboard</div>
            <h1>Dashboard</h1>
            <p>Fast operating view for real Kalshi portfolio value, recent performance, and what matters most right now.</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

snapshot = load_home_snapshot()
trade_log = snapshot["trade_log"]
trade_source = snapshot["trade_source"]
portfolio = snapshot["portfolio"]
kpis = compute_trade_kpis(trade_log)
market_perf = get_market_performance(trade_log)
known_market_perf = market_perf[market_perf["market"].notna() & (market_perf["market"] != "Unknown")].copy()
recent_trades = recent_trades_table(trade_log, limit=12)
best_day, worst_day = get_best_worst_days(trade_log)

metric_card_row(
    [
        (
            "Portfolio Value",
            f"${float(portfolio['portfolio_value']):,.2f}" if portfolio.get("portfolio_value") is not None else "N/A",
            "positive" if (portfolio.get("portfolio_value") or 0) >= 0 else "",
        ),
        (
            "Cash Balance",
            f"${float(portfolio['balance']):,.2f}" if portfolio.get("balance") is not None else "N/A",
            "",
        ),
        ("Total PNL", f"${kpis['total_pnl']:,.2f}", "positive" if kpis["total_pnl"] >= 0 else "negative"),
        ("Total Trades", f"{kpis['total_trades']}", ""),
    ]
)

if trade_source == "csv":
    st.warning("Kalshi trade history is unavailable right now, so Dashboard performance is falling back to the local ledger.")

metric_card_row(
    [
        ("Win Rate", f"{kpis['win_rate']:.1%}", "positive" if kpis["win_rate"] >= 0.5 else ""),
        ("ROI Total", f"{kpis['roi_total']:.1%}", "positive" if kpis["roi_total"] >= 0 else "negative"),
        ("% Retorno del mes", f"{kpis['month_return']:.1%}", "positive" if kpis["month_return"] >= 0 else "negative"),
        ("Max Drawdown", f"${kpis['max_drawdown']:,.2f}", "negative"),
    ]
)

st.markdown(
    """
    <div class='mini-panel' style='margin-bottom:1rem;'>
        <strong>Guía rápida del día</strong><br>
        Verde = días o mercados ganadores. Rojo = perdedores. En Cumulative PNL, la etiqueta final te dice exactamente dónde vas. En Daily PNL y PNL by Market, cada barra ya muestra el valor real encima.
    </div>
    """,
    unsafe_allow_html=True,
)

insight_cols = st.columns(4)
with insight_cols[0]:
    st.markdown("<div class='section-label'>Best Market</div>", unsafe_allow_html=True)
    if known_market_perf.empty:
        st.info("No market data yet.")
    else:
        best_market = known_market_perf.sort_values("net_pnl", ascending=False).iloc[0]
        st.markdown(
            f"<div class='mini-panel'><strong>{best_market['market']}</strong><br><span class='metric-positive'>${best_market['net_pnl']:,.2f}</span></div>",
            unsafe_allow_html=True,
        )
with insight_cols[1]:
    st.markdown("<div class='section-label'>Worst Market</div>", unsafe_allow_html=True)
    if known_market_perf.empty:
        st.info("No market data yet.")
    else:
        worst_market = known_market_perf.sort_values("net_pnl", ascending=True).iloc[0]
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
    cumulative_period = st.radio(
        "Vista acumulada",
        ["Diario", "Semana", "Mes", "Año"],
        index=2,
        horizontal=True,
        label_visibility="collapsed",
        key="cumulative_period",
    )
    st.plotly_chart(plot_cumulative_pnl(trade_log, cumulative_period), use_container_width=True)
with chart_col2:
    st.markdown("<div class='section-label'>Daily PNL</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_daily_pnl(trade_log), use_container_width=True)

chart_col3, chart_col4 = st.columns((1.2, 1))
with chart_col3:
    st.markdown("<div class='section-label'>PNL by Market</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_pnl_by_market(known_market_perf if not known_market_perf.empty else market_perf), use_container_width=True)
with chart_col4:
    st.markdown("<div class='section-label'>Win / Loss Breakdown</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_win_loss_breakdown(trade_log), use_container_width=True)

chart_col5, chart_col6 = st.columns((1.2, 1))
with chart_col5:
    st.markdown("<div class='section-label'>PNL Distribution</div>", unsafe_allow_html=True)
    st.plotly_chart(plot_pnl_distribution(trade_log), use_container_width=True)
with chart_col6:
    st.markdown("<div class='section-label'>Most Active Markets</div>", unsafe_allow_html=True)
    if known_market_perf.empty:
        st.info("No market activity yet.")
    else:
        active = known_market_perf.sort_values("total_trades", ascending=False).head(8).copy()
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
