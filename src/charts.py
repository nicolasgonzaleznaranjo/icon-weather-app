from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st


PLOT_LAYOUT = {
    "paper_bgcolor": "#111419",
    "plot_bgcolor": "#111419",
    "font": {"color": "#eef2f7", "family": "Space Mono, Courier New, Courier, monospace"},
    "margin": {"l": 20, "r": 20, "t": 20, "b": 20},
}


def metric_card_row(cards: list[tuple[str, str, str]]) -> None:
    html = ["<div class='metric-grid'>"]
    for label, value, tone in cards:
        css = "metric-neutral"
        if tone == "positive":
            css = "metric-positive"
        elif tone == "negative":
            css = "metric-negative"
        html.append(
            f"<div class='metric-card'><div class='label'>{label}</div><div class='value {css}'>{value}</div></div>"
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def _empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, showarrow=False, font={"color": "#9aa4b2", "size": 16})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(**PLOT_LAYOUT, height=320)
    return fig


def _filter_cumulative_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    if df.empty:
        return df
    chart = df.dropna(subset=["date_closed"]).copy()
    if chart.empty:
        return chart
    chart["date_closed"] = pd.to_datetime(chart["date_closed"], errors="coerce")
    chart = chart.dropna(subset=["date_closed"]).sort_values("date_closed")
    if chart.empty:
        return chart

    end_time = chart["date_closed"].max()
    period_map = {
        "Diario": pd.Timedelta(days=1),
        "Semana": pd.Timedelta(days=7),
        "Mes": pd.Timedelta(days=30),
        "Año": pd.Timedelta(days=365),
    }
    window = period_map.get(period, pd.Timedelta(days=30))
    start_time = end_time - window
    return chart[chart["date_closed"] >= start_time].copy()


def plot_cumulative_pnl(df: pd.DataFrame, period: str = "Mes") -> go.Figure:
    if df.empty:
        return _empty_figure("No trade log loaded yet.")
    chart = _filter_cumulative_period(df, period)
    if chart.empty:
        return _empty_figure("No hay cierres en ese rango todavía.")
    chart["cumulative_pnl"] = chart["net_pnl"].fillna(0).cumsum()
    fig = px.line(chart, x="date_closed", y="cumulative_pnl")
    fig.update_traces(
        line={"color": "#6ec27c", "width": 3},
        mode="lines+markers",
        hovertemplate="%{x}<br>PNL acumulado: $%{y:.2f}<extra></extra>",
    )
    if not chart.empty:
        last = chart.iloc[-1]
        fig.add_annotation(
            x=last["date_closed"],
            y=last["cumulative_pnl"],
            text=f"${last['cumulative_pnl']:.2f}",
            showarrow=True,
            arrowhead=1,
            ax=25,
            ay=-25,
            font={"color": "#eef2f7"},
        )
    fig.update_layout(**PLOT_LAYOUT, height=330, yaxis_title="PNL ($)", xaxis_title="")
    return fig


def plot_daily_pnl(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No daily PNL yet.")
    daily = df.dropna(subset=["close_day"]).groupby("close_day", as_index=False)["net_pnl"].sum()
    daily["bar_color"] = daily["net_pnl"].apply(lambda v: "#6ec27c" if v > 0 else "#ff6b6b" if v < 0 else "#6b7280")
    fig = go.Figure(
        data=[
            go.Bar(
                x=daily["close_day"],
                y=daily["net_pnl"],
                marker_color=daily["bar_color"],
                text=[f"${v:.2f}" for v in daily["net_pnl"]],
                textposition="outside",
                hovertemplate="%{x}<br>PNL del día: $%{y:.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(**PLOT_LAYOUT, height=330, xaxis_title="", yaxis_title="PNL ($)")
    return fig


def plot_pnl_by_market(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No market PNL yet.")
    top = df.sort_values("net_pnl", ascending=False).head(12)
    top["bar_color"] = top["net_pnl"].apply(lambda v: "#6ec27c" if v > 0 else "#ff6b6b" if v < 0 else "#6b7280")
    fig = go.Figure(
        data=[
            go.Bar(
                x=top["market"],
                y=top["net_pnl"],
                marker_color=top["bar_color"],
                text=[f"${v:.2f}" for v in top["net_pnl"]],
                textposition="outside",
                hovertemplate="%{x}<br>PNL: $%{y:.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(**PLOT_LAYOUT, height=360, xaxis_title="", yaxis_title="PNL ($)")
    return fig


def plot_worst_markets(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No worst-market data yet.")
    worst = df.sort_values("net_pnl", ascending=True).head(12).copy()
    worst["bar_color"] = worst["net_pnl"].apply(lambda v: "#ff6b6b" if v < 0 else "#6ec27c" if v > 0 else "#6b7280")
    fig = go.Figure(
        data=[
            go.Bar(
                x=worst["market"],
                y=worst["net_pnl"],
                marker_color=worst["bar_color"],
                text=[f"${v:.2f}" for v in worst["net_pnl"]],
                textposition="outside",
                hovertemplate="%{x}<br>PNL: $%{y:.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(**PLOT_LAYOUT, height=330, xaxis_title="", yaxis_title="PNL ($)")
    return fig


def plot_win_loss_breakdown(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No outcomes yet.")
    counts = pd.DataFrame(
        {
            "Outcome": ["Wins", "Losses", "Flat"],
            "Count": [
                int((df["net_pnl"] > 0).sum()),
                int((df["net_pnl"] < 0).sum()),
                int((df["net_pnl"] == 0).sum()),
            ],
        }
    )
    fig = px.pie(counts, names="Outcome", values="Count", color="Outcome", color_discrete_map={"Wins": "#6ec27c", "Losses": "#ff6b6b", "Flat": "#4b5563"}, hole=0.6)
    fig.update_layout(**PLOT_LAYOUT, height=330, showlegend=True)
    return fig


def build_map_deck(df: pd.DataFrame) -> pdk.Deck | None:
    if df.empty:
        return None
    view_state = pdk.ViewState(latitude=float(df["latitude"].mean()), longitude=float(df["longitude"].mean()), zoom=3.4, pitch=0)
    point_layer = pdk.Layer(
        "ScatterplotLayer",
        df,
        get_position="[longitude, latitude]",
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
        opacity=0.82,
        stroked=True,
        get_line_color=[255, 255, 255, 40],
        line_width_min_pixels=1,
    )
    text_layer = pdk.Layer(
        "TextLayer",
        df,
        get_position="[longitude, latitude]",
        get_text="label",
        get_size=14,
        size_units="pixels",
        get_color=[238, 242, 247, 220],
        get_angle=0,
        get_text_anchor="middle",
        get_alignment_baseline="bottom",
        get_pixel_offset=[0, -18],
        billboard=True,
        pickable=False,
    )
    return pdk.Deck(
        map_provider="carto",
        map_style="dark",
        initial_view_state=view_state,
        layers=[point_layer, text_layer],
        tooltip={
            "html": "<b>{market_name}</b><br/>Station: {nws_station}<br/>Forecast High / Low: {forecast_high} / {forecast_low}<br/>Current PNL: {current_pnl}<br/>Trades: {total_trades}<br/>Win Rate: {win_rate}<br/>Open Exposure: {open_exposure}",
            "style": {"backgroundColor": "#111419", "color": "#eef2f7"},
        },
    )
