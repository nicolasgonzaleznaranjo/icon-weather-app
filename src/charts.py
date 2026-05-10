from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st


PLOT_LAYOUT = {
    "paper_bgcolor": "#111419",
    "plot_bgcolor": "#111419",
    "font": {"color": "#eef2f7"},
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


def plot_cumulative_pnl(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No trade log loaded yet.")
    chart = df.sort_values("date_closed").copy()
    chart["cumulative_pnl"] = chart["net_pnl"].fillna(0).cumsum()
    fig = px.line(chart, x="date_closed", y="cumulative_pnl")
    fig.update_traces(line={"color": "#6ec27c", "width": 3})
    fig.update_layout(**PLOT_LAYOUT, height=330, yaxis_title="PNL ($)", xaxis_title="")
    return fig


def plot_daily_pnl(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No daily PNL yet.")
    daily = df.dropna(subset=["close_day"]).groupby("close_day", as_index=False)["net_pnl"].sum()
    fig = px.bar(daily, x="close_day", y="net_pnl", color="net_pnl", color_continuous_scale=["#ff6b6b", "#6ec27c"])
    fig.update_layout(**PLOT_LAYOUT, height=330, coloraxis_showscale=False, xaxis_title="", yaxis_title="PNL ($)")
    return fig


def plot_pnl_by_market(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No market PNL yet.")
    top = df.sort_values("net_pnl", ascending=False).head(12)
    fig = px.bar(top, x="market", y="net_pnl", color="net_pnl", color_continuous_scale=["#ff6b6b", "#6ec27c"])
    fig.update_layout(**PLOT_LAYOUT, height=360, coloraxis_showscale=False, xaxis_title="", yaxis_title="PNL ($)")
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


def plot_pnl_distribution(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _empty_figure("No PNL distribution yet.")
    fig = px.histogram(df, x="net_pnl", nbins=20, color_discrete_sequence=["#61a7ff"])
    fig.update_layout(**PLOT_LAYOUT, height=330, xaxis_title="Net PNL ($)", yaxis_title="Trades")
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
        get_size=13,
        get_color=[238, 242, 247, 220],
        get_angle=0,
        get_text_anchor="'middle'",
        get_alignment_baseline="'bottom'",
        get_pixel_offset=[0, -18],
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
