from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


CSS = """
<style>
:root {
  --bg: #060708;
  --panel: #101215;
  --panel-soft: #171a1f;
  --line: #2a2f38;
  --text: #f3f4f6;
  --muted: #a3abb9;
  --green: #6ba86d;
  --red: #ad5c56;
  --gold: #b89a57;
}
html, body, [data-testid="stAppViewContainer"] { background: var(--bg); color: var(--text); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: #0b0d10; border-right: 1px solid var(--line); }
.block-container { padding-top: 1rem; max-width: 100%; }
.icon-shell { display: grid; gap: 1rem; }
.hero-title { font-size: clamp(1.9rem, 3.5vw, 3rem); font-weight: 800; letter-spacing: 0; margin: 0; }
.hero-subtitle { color: var(--muted); font-size: 0.95rem; margin-top: 0.35rem; }
.section-title { font-size: 1rem; font-weight: 700; margin: 0 0 0.7rem; }
.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 0.75rem; }
.metric-card { background: linear-gradient(180deg, rgba(21,24,29,0.95), rgba(11,13,16,0.98)); border: 1px solid var(--line); padding: 0.85rem 0.95rem; min-height: 92px; }
.metric-label { color: var(--muted); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.04em; }
.metric-value { font-size: clamp(1.25rem, 2vw, 1.8rem); font-weight: 750; margin-top: 0.45rem; }
.metric-value.positive { color: var(--green); }
.metric-value.negative { color: var(--red); }
.summary-panel { background: var(--panel); border: 1px solid var(--line); padding: 1rem 1.1rem; }
.summary-copy { color: var(--text); font-size: 0.95rem; line-height: 1.45; }
.status-chip { display: inline-block; border: 1px solid var(--line); background: var(--panel-soft); padding: 0.3rem 0.55rem; font-size: 0.78rem; color: var(--muted); margin-right: 0.35rem; }
.danger-chip { color: #f5c2bf; border-color: rgba(173,92,86,0.5); background: rgba(173,92,86,0.14); }
.ok-chip { color: #cfe8d0; border-color: rgba(107,168,109,0.45); background: rgba(107,168,109,0.12); }
.compact-note { color: var(--muted); font-size: 0.8rem; }
div[data-testid="stDataFrame"] { border: 1px solid var(--line); }
@media (max-width: 1080px) {
  .metric-grid { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
}
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def render_metric_cards(metrics: list[tuple[str, str, str]]) -> None:
    cards = []
    for label, value, tone in metrics:
        cards.append(
            f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value {tone}'>{value}</div></div>"
        )
    st.markdown(f"<div class='metric-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)


def format_currency(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def format_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1%}"


def plot_equity_curve(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(
            go.Scatter(
                x=df["snapshot_ts"],
                y=df["equity"],
                mode="lines",
                line={"color": "#b89a57", "width": 2},
                fill="tozeroy",
                fillcolor="rgba(184,154,87,0.12)",
                name="Equity",
            )
        )
    fig.update_layout(
        paper_bgcolor="#101215",
        plot_bgcolor="#101215",
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        font={"color": "#f3f4f6"},
        xaxis={"showgrid": False},
        yaxis={"showgrid": True, "gridcolor": "#232832"},
    )
    return fig


def plot_market_map(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    frame = df.copy()
    frame["lat"] = pd.to_numeric(frame["lat"], errors="coerce")
    frame["lon"] = pd.to_numeric(frame["lon"], errors="coerce")
    frame["edge"] = pd.to_numeric(frame["edge"], errors="coerce").fillna(0.0)
    frame["exposure"] = pd.to_numeric(frame["exposure"], errors="coerce").fillna(1.0)
    frame = frame.dropna(subset=["lat", "lon"])
    if frame.empty:
        return go.Figure()

    fig = px.scatter_mapbox(
        frame,
        lat="lat",
        lon="lon",
        color="edge",
        size="exposure",
        hover_name="city",
        hover_data={
            "forecast": True,
            "contract": True,
            "price": True,
            "pnl": True,
            "lat": False,
            "lon": False,
            "edge": False,
            "exposure": False,
        },
        color_continuous_scale=["#7a3d36", "#b89a57", "#6ba86d"],
        zoom=3.2,
        height=520,
    )
    fig.update_layout(
        mapbox_style="carto-darkmatter",
        paper_bgcolor="#101215",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        font={"color": "#f3f4f6"},
    )
    return fig
