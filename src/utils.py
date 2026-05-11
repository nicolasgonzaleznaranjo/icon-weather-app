from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from html import escape

from src.data_models import MarketConfig


ROOT = Path(__file__).resolve().parents[1]
MARKETS_PATH = ROOT / "config" / "markets.csv"
TRADE_LOG_PATH = ROOT / "data" / "trade_log.csv"
CACHED_FORECASTS_PATH = ROOT / "data" / "cached_forecasts.csv"
KALSHI_TRANSACTIONS_PATH = ROOT / "data" / "Kalshi-Transactions-2026.csv"
KALSHI_RECENT_ACTIVITY_PATH = ROOT / "data" / "Kalshi-Recent-Activity-All.csv"
KALSHI_SETTLEMENTS_PATH = ROOT / "data" / "Kalshi-Recent-Activity-Settlement.csv"
USER_AGENT = "ICONWeatherApp/1.0 (support@iconweatherapp.local)"


def bootstrap_page(page_title: str) -> None:
    st.set_page_config(
        page_title=f"{page_title} | ICON Weather App",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');
            :root {
                --bg: #080a0d;
                --surface: #111419;
                --surface-2: #171b22;
                --border: #252b35;
                --text: #eef2f7;
                --muted: #9aa4b2;
                --green: #6ec27c;
                --red: #ff6b6b;
                --amber: #d8b36b;
                --blue: #61a7ff;
            }
            .stApp { background: var(--bg); color: var(--text); }
            html, body, .stApp, [class*="css"], [data-testid="stSidebar"], button, input, textarea, select, table, th, td {
                font-family: 'Space Mono', monospace !important;
            }
            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #0d1015 0%, #0a0c10 100%);
                border-right: 1px solid rgba(255,255,255,.06);
            }
            [data-testid="stSidebar"] * { color: var(--text); }
            .hero-block {
                display:flex;
                justify-content:space-between;
                gap:1rem;
                align-items:flex-end;
                padding: 0.25rem 0 1rem 0;
            }
            .hero-block h1 {
                margin: 0;
                color: var(--text);
                font-size: clamp(2rem, 4vw, 3rem);
                line-height: 1.02;
            }
            .hero-block p {
                margin: .35rem 0 0 0;
                color: var(--muted);
                font-size: 1rem;
                max-width: 880px;
            }
            .eyebrow {
                color: var(--blue);
                font-size: .78rem;
                text-transform: uppercase;
                letter-spacing: .08em;
                margin-bottom: .45rem;
            }
            .section-label {
                color: var(--text);
                font-size: 1rem;
                font-weight: 700;
                margin: .25rem 0 .75rem 0;
            }
            .metric-grid {
                display:grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap:.8rem;
                margin-bottom: .8rem;
            }
            .metric-card, .mini-panel {
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 1rem 1rem .95rem 1rem;
            }
            .metric-card .label {
                color: var(--muted);
                font-size: .76rem;
                text-transform: uppercase;
                letter-spacing: .06em;
                margin-bottom: .55rem;
            }
            .metric-card .value {
                color: var(--text);
                font-size: clamp(1.35rem, 2.4vw, 2rem);
                font-weight: 800;
                line-height: 1.05;
                word-break: break-word;
            }
            .metric-positive { color: var(--green); }
            .metric-negative { color: var(--red); }
            .metric-neutral { color: var(--text); }
            .status-pill {
                display: inline-block;
                padding: .24rem .6rem;
                border-radius: 999px;
                font-size: .72rem;
                font-weight: 700;
                letter-spacing: .03em;
                border: 1px solid rgba(255,255,255,.08);
            }
            .status-strong { background: rgba(110,194,124,.14); color: var(--green); }
            .status-tradable { background: rgba(97,167,255,.12); color: var(--blue); }
            .status-watch { background: rgba(216,179,107,.12); color: var(--amber); }
            .status-avoid { background: rgba(255,107,107,.12); color: var(--red); }
            .mini-panel strong { font-size: .95rem; }
            .stDataFrame, div[data-testid="stTable"] {
                border: 1px solid var(--border);
                border-radius: 16px;
                overflow: hidden;
            }
            .monitor-wrap {
                border: 1px solid var(--border);
                border-radius: 16px;
                overflow: hidden;
                background: var(--surface);
                overflow-x: auto;
            }
            .monitor-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 1.02rem;
                min-width: 860px;
            }
            .monitor-table th {
                background: #1b1f27;
                color: var(--muted);
                font-size: .86rem;
                font-weight: 700;
                letter-spacing: .02em;
                padding: 1rem .85rem;
                text-align: left;
                border-bottom: 1px solid var(--border);
                white-space: nowrap;
            }
            .monitor-table td {
                padding: 1rem .85rem;
                border-bottom: 1px solid rgba(255,255,255,.06);
                vertical-align: middle;
            }
            .monitor-table tbody tr:nth-child(odd) td {
                background: rgba(255,255,255,.015);
            }
            .monitor-table tbody tr:nth-child(even) td {
                background: rgba(255,255,255,.045);
            }
            .monitor-table tr:last-child td {
                border-bottom: none;
            }
            .monitor-table tr.highlight-row td {
                background: rgba(97,167,255,.12);
            }
            .monitor-table .center-col {
                text-align: center;
            }
            .monitor-table .left-col {
                text-align: left;
            }
            .signal-check {
                color: var(--green);
                font-weight: 800;
            }
            .signal-no-check {
                color: var(--muted);
                font-weight: 700;
            }
            div[data-testid="stMetric"] {
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: .8rem;
            }
            .diag-good, .diag-bad, .diag-warn {
                border-radius: 14px;
                padding: .95rem 1rem;
                border: 1px solid var(--border);
                margin-bottom: .8rem;
            }
            .diag-good { background: rgba(110,194,124,.10); }
            .diag-bad { background: rgba(255,107,107,.10); }
            .diag-warn { background: rgba(216,179,107,.10); }
            @media (max-width: 980px) {
                .hero-block { align-items:flex-start; flex-direction:column; }
                .monitor-table {
                    font-size: .98rem;
                    min-width: 760px;
                }
                .monitor-table th {
                    font-size: .82rem;
                    padding: .9rem .75rem;
                }
                .monitor-table td {
                    padding: .92rem .75rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=3600)
def load_market_config() -> pd.DataFrame:
    return pd.read_csv(MARKETS_PATH)


def market_configs() -> list[MarketConfig]:
    df = load_market_config()
    return [
        MarketConfig(
            market_name=row.market_name,
            nws_station=row.nws_station,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            timezone=row.timezone,
            forecast_source=row.forecast_source,
            settlement_source=row.settlement_source,
            climate_source=row.climate_source,
            kalshi_high_slug=row.kalshi_high_slug,
            kalshi_low_slug=row.kalshi_low_slug,
            kalshi_high_series=row.kalshi_high_series,
            kalshi_low_series=row.kalshi_low_series,
            weather_office=row.weather_office,
        )
        for row in df.itertuples(index=False)
    ]


def local_now(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "N/A"):
            return default
        return float(str(value).replace("$", "").replace("%", "").replace("¢", "").replace(",", ""))
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    number = safe_float(value)
    return int(round(number)) if number is not None else default


def display_price(cents: float | int | None) -> str:
    if cents is None or pd.isna(cents):
        return "N/A"
    return f"{int(round(cents))}c"


def display_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1%}"


def display_delta(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:+.1f}°"


def status_badge(status: str) -> str:
    css_class = {
        "Strong candidate": "status-strong",
        "Tradable": "status-tradable",
        "Watch": "status-watch",
        "Avoid": "status-avoid",
    }.get(status, "status-watch")
    return f"<span class='status-pill {css_class}'>{status}</span>"


def secret_present(name: str) -> bool:
    import os

    env_value = os.getenv(name)
    if env_value:
        return True
    try:
        return name in st.secrets
    except Exception:
        return False


def render_monitor_table(df: pd.DataFrame, *, highlight_city: str | None = None) -> None:
    if df.empty:
        st.info("No rows available yet.")
        return
    centered = {"Signal", "City", "Observed Today", "Forecast Today (F)", "Hourly Forecast (F)", "Kalshi Forecast (F)", "Code"}
    left_aligned = {"Short description"}
    def col_class(name: str) -> str:
        if name in centered:
            return "center-col"
        if name in left_aligned:
            return "left-col"
        return ""
    header = "".join(f"<th class='{col_class(str(column))}'>{escape(str(column))}</th>" for column in df.columns)
    body_rows: list[str] = []
    for _, row in df.iterrows():
        row_classes: list[str] = []
        if highlight_city and str(row.get("City", "")) == highlight_city:
            row_classes.append("highlight-row")
        cells: list[str] = []
        for column in df.columns:
            value = row[column]
            if column == "Signal":
                css = "signal-check" if str(value).strip().lower() == "check" else "signal-no-check"
                cell_html = f"<span class='{css}'>{escape(str(value))}</span>"
            else:
                cell_html = escape("" if pd.isna(value) else str(value))
            cells.append(f"<td class='{col_class(str(column))}'>{cell_html}</td>")
        class_attr = f" class='{' '.join(row_classes)}'" if row_classes else ""
        body_rows.append(f"<tr{class_attr}>{''.join(cells)}</tr>")
    html = f"""
    <div class="monitor-wrap">
        <table class="monitor-table">
            <thead><tr>{header}</tr></thead>
            <tbody>{''.join(body_rows)}</tbody>
        </table>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
