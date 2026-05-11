from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.kalshi_client import KalshiClient, compute_yes_no_prices
from src.nws_client import NWSClient, forecast_snapshot
from src.rules_engine import evaluate_contract, extract_contract_label, parse_contract_spec, parse_event_date
from src.trade_log import get_market_performance, get_portfolio_summary, get_effective_trade_log
from src.utils import load_market_config


STATUS_PRIORITY = {"Strong candidate": 0, "Tradable": 1, "Watch": 2, "Avoid": 3}


def _display_temp(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1f}°"


def _signal_from_status(status: str) -> str:
    return "Check" if status in {"Strong candidate", "Tradable"} else "No check"


def _kalshi_single_forecast(markets: list[dict[str, Any]]) -> float | None:
    ranked: list[tuple[float, float]] = []
    for market in markets:
        label = extract_contract_label(str(market.get("title", "")))
        spec = parse_contract_spec(label)
        prices = compute_yes_no_prices(market)
        candidate = prices["yes_price"] if prices["yes_price"] is not None else prices["last_price"]
        if candidate is None:
            continue
        if spec.center is not None:
            display_value = spec.center
        elif spec.display_upper is not None:
            display_value = spec.display_upper - 0.5
        elif spec.display_lower is not None:
            display_value = spec.display_lower + 0.5
        else:
            continue
        ranked.append((float(candidate), float(display_value)))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def _best_status(markets: list[dict[str, Any]], market_type: str, forecast_value: float | None) -> str:
    candidates: list[tuple[int, float]] = []
    for market in markets:
        label = extract_contract_label(str(market.get("title", "")))
        prices = compute_yes_no_prices(market)
        rule = evaluate_contract(
            market_type=market_type,
            contract_label=label,
            forecast_value=forecast_value,
            yes_price=prices["yes_price"],
            no_price=prices["no_price"],
            volume=float(market.get("volume") or 0),
            liquidity=float(market.get("liquidity_dollars") or 0),
            close_time=market.get("close_time"),
        )
        candidates.append((STATUS_PRIORITY.get(rule["status"], 9), -(rule["edge"] or 0.0)))
    if not candidates:
        return "Avoid"
    best = min(candidates)
    for status, rank in STATUS_PRIORITY.items():
        if rank == best[0]:
            return status
    return "Avoid"


def _next_night_forecast(nws: NWSClient, forecast_url: str, target_date) -> float | None:
    try:
        forecast = nws.get_forecast(forecast_url)
    except Exception:
        return None
    periods = forecast.get("periods", [])
    for period in periods:
        start = datetime.fromisoformat(period["startTime"])
        if not period.get("isDaytime") and start.date() >= target_date:
            return period.get("temperature")
    return None


def _load_city_basics(include_observed: bool = False) -> list[dict[str, Any]]:
    config = load_market_config()
    kalshi = KalshiClient()
    nws = NWSClient()
    rows: list[dict[str, Any]] = []

    for row in config.itertuples(index=False):
        try:
            high_markets = kalshi.get_series_markets(row.kalshi_high_series, status="open", limit=8)
        except Exception:
            high_markets = []
        try:
            low_markets = kalshi.get_series_markets(row.kalshi_low_series, status="open", limit=8)
        except Exception:
            low_markets = []

        target_date = None
        if high_markets:
            target_date = parse_event_date(high_markets[0]["ticker"])
        elif low_markets:
            target_date = parse_event_date(low_markets[0]["ticker"])
        target_date = target_date or datetime.now().date()

        try:
            forecast = forecast_snapshot(
                nws,
                float(row.latitude),
                float(row.longitude),
                target_date=target_date,
                station=row.nws_station,
                timezone_name=row.timezone,
                digital_forecast_url=row.forecast_source,
            )
        except Exception:
            forecast = {
                "forecast_high": None,
                "forecast_low": None,
                "short_forecast": "N/A",
                "observed_high_today": None,
                "observed_low_today": None,
                "forecast_url": row.forecast_source,
            }

        rows.append(
            {
                "market_name": row.market_name,
                "nws_station": row.nws_station,
                "target_date": target_date,
                "forecast_high": forecast.get("forecast_high"),
                "forecast_high_today": forecast.get("forecast_high_today"),
                "forecast_low": forecast.get("forecast_low"),
                "short_forecast": forecast.get("short_forecast") or "N/A",
                "observed_high_today": forecast.get("observed_high_today") if include_observed else None,
                "observed_low_today": forecast.get("observed_low_today") if include_observed else None,
                "forecast_low_from_now": forecast.get("forecast_low_from_now"),
                "forecast_low_today": forecast.get("forecast_low_today"),
                "forecast_url": forecast.get("forecast_url") or row.forecast_source,
                "high_markets": high_markets,
                "low_markets": low_markets,
            }
        )
    return rows


@st.cache_data(ttl=300, show_spinner=False)
def load_high_monitor_rows() -> pd.DataFrame:
    rows = []
    for item in _load_city_basics(include_observed=False):
        status = _best_status(item["high_markets"], "high", item["forecast_high"])
        rows.append(
            {
                "Signal": _signal_from_status(status),
                "City": item["market_name"],
                "Hourly Forecast (F)": _display_temp(
                    item["forecast_high_today"] if item["forecast_high_today"] is not None else item["forecast_high"]
                ),
                "Kalshi Forecast (F)": _display_temp(_kalshi_single_forecast(item["high_markets"])),
                "Short description": item["short_forecast"],
                "Code": item["nws_station"],
            }
        )
    df = pd.DataFrame(rows)
    df["signal_order"] = df["Signal"].map({"Check": 0, "No check": 1}).fillna(2)
    df = df.sort_values(["signal_order", "City"]).drop(columns=["signal_order"]).reset_index(drop=True)
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_low_monitor_rows() -> pd.DataFrame:
    rows = []
    for item in _load_city_basics(include_observed=True):
        status = _best_status(item["low_markets"], "low", item["forecast_low"])
        rows.append(
            {
                "Signal": _signal_from_status(status),
                "City": item["market_name"],
                "Observed Today": _display_temp(item["observed_low_today"]),
                "Forecast Today (F)": _display_temp(
                    item["forecast_low_today"]
                    if item["forecast_low_today"] is not None
                    else item["forecast_low_from_now"]
                    if item["forecast_low_from_now"] is not None
                    else item["forecast_low"]
                ),
                "Kalshi Forecast (F)": _display_temp(_kalshi_single_forecast(item["low_markets"])),
                "Short description": item["short_forecast"],
                "Code": item["nws_station"],
            }
        )
    df = pd.DataFrame(rows)
    df["signal_order"] = df["Signal"].map({"Check": 0, "No check": 1}).fillna(2)
    df = df.sort_values(["signal_order", "City"]).drop(columns=["signal_order"]).reset_index(drop=True)
    return df


@st.cache_data(ttl=900, show_spinner=False)
def load_temperature_record_rows() -> pd.DataFrame:
    rows = []
    for item in _load_city_basics(include_observed=True):
        kalshi_high = _kalshi_single_forecast(item["high_markets"])
        kalshi_low = _kalshi_single_forecast(item["low_markets"])
        delta_nws = None
        delta_kalshi = None
        if item["observed_high_today"] is not None and item["forecast_high"] is not None:
            delta_nws = item["observed_high_today"] - item["forecast_high"]
        if item["observed_high_today"] is not None and kalshi_high is not None:
            delta_kalshi = item["observed_high_today"] - kalshi_high
        rows.append(
            {
                "City": item["market_name"],
                "Date": item["target_date"].isoformat(),
                "NWS Forecasted High T": _display_temp(item["forecast_high"]),
                "NWS Forecasted Low T": _display_temp(item["forecast_low"]),
                "Kalshi Forecasted High T": _display_temp(kalshi_high),
                "Kalshi Forecasted Low T": _display_temp(kalshi_low),
                "NWS Realized High T": _display_temp(item["observed_high_today"]),
                "NWS Realized Low T": _display_temp(item["observed_low_today"]),
                "Delta NWS": f"{delta_nws:+.1f}°" if delta_nws is not None else "N/A",
                "Delta Kalshi": f"{delta_kalshi:+.1f}°" if delta_kalshi is not None else "N/A",
            }
        )
    return pd.DataFrame(rows).sort_values("City").reset_index(drop=True)


@st.cache_data(ttl=900, show_spinner=False)
def load_map_rows() -> pd.DataFrame:
    trade_log, _ = get_effective_trade_log()
    performance = get_market_performance(trade_log)
    rows = []
    for item in _load_city_basics(include_observed=False):
        perf_match = performance[performance["market"] == item["market_name"]]
        perf = perf_match.iloc[0].to_dict() if not perf_match.empty else {}
        rows.append(
            {
                "market_name": item["market_name"],
                "label": item["market_name"],
                "nws_station": item["nws_station"],
                "latitude": float(load_market_config().loc[load_market_config()["market_name"] == item["market_name"], "latitude"].iloc[0]),
                "longitude": float(load_market_config().loc[load_market_config()["market_name"] == item["market_name"], "longitude"].iloc[0]),
                "forecast_high": _display_temp(item["forecast_high"]),
                "forecast_low": _display_temp(item["forecast_low"]),
                "current_pnl": f"${float(perf.get('net_pnl', 0.0) or 0.0):,.2f}",
                "total_trades": int(perf.get("total_trades", 0) or 0),
                "win_rate": f"{float(perf.get('win_rate', 0.0) or 0.0):.0%}",
                "open_exposure": f"${float(perf.get('open_exposure', 0.0) or 0.0):,.2f}",
                "color": [110, 194, 124, 190] if float(perf.get("net_pnl", 0.0) or 0.0) >= 0 else [255, 107, 107, 190],
                "radius": max(30000, int(perf.get("total_trades", 0) or 0) * 4500 + int(abs(float(perf.get("open_exposure", 0.0) or 0.0)) * 350)),
            }
        )
    return pd.DataFrame(rows).sort_values("market_name").reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def load_home_snapshot() -> dict[str, Any]:
    trade_log, trade_source = get_effective_trade_log()
    return {
        "trade_log": trade_log,
        "trade_source": trade_source,
        "portfolio": get_portfolio_summary(),
    }
