from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.kalshi_client import KalshiClient, compute_yes_no_prices
from src.nws_client import NWSClient, forecast_snapshot
from src.rules_engine import (
    contract_distance,
    evaluate_contract,
    extract_contract_label,
    modeled_yes_probability,
    parse_contract_spec,
    parse_event_date,
)
from src.trade_log import get_market_performance, get_portfolio_summary, get_effective_trade_log
from src.utils import load_market_config, local_now


STATUS_PRIORITY = {"Strong candidate": 0, "Tradable": 1, "Watch": 2, "Avoid": 3}


def _display_temp(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{int(round(float(value)))}°"


def _signal_from_status(status: str) -> str:
    return "Check" if status in {"Strong candidate", "Tradable"} else "No check"


def _best_contract(markets: list[dict[str, Any]], market_type: str, forecast_value: float | None) -> dict[str, Any] | None:
    ranked: list[dict[str, Any]] = []
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
        ranked.append({"market": market, "label": label, "prices": prices, "rule": rule})
    if not ranked:
        return None
    ranked.sort(
        key=lambda item: (
            STATUS_PRIORITY.get(item["rule"]["status"], 9),
            -(item["rule"]["edge"] or -999),
            abs(item["rule"]["distance_from_forecast"] or 999),
        )
    )
    return ranked[0]


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


def _next_night_forecast(nws: NWSClient, forecast_url: str, target_date) -> float | None:
    try:
        forecast = nws.get_forecast(forecast_url)
    except Exception:
        return None
    periods = forecast.get("periods", [])
    night_candidates = []
    for period in periods:
        start = datetime.fromisoformat(period["startTime"])
        if not period.get("isDaytime") and start.date() >= target_date:
            night_candidates.append(period)
    if not night_candidates:
        return None
    return night_candidates[0].get("temperature")


@st.cache_data(ttl=600, show_spinner=False)
def load_market_snapshots() -> dict[str, pd.DataFrame | dict]:
    config = load_market_config()
    kalshi = KalshiClient()
    nws = NWSClient()
    trade_log, trade_source = get_effective_trade_log()
    performance = get_market_performance(trade_log)
    portfolio = get_portfolio_summary()

    high_rows: list[dict] = []
    low_rows: list[dict] = []
    map_rows: list[dict] = []
    historical_rows: list[dict] = []
    errors: list[str] = []

    for row in config.itertuples(index=False):
        perf_match = performance[performance["market"] == row.market_name]
        perf = perf_match.iloc[0].to_dict() if not perf_match.empty else {}

        try:
            high_markets = kalshi.get_series_markets(row.kalshi_high_series, status="open", limit=20)
        except Exception as exc:
            high_markets = []
            errors.append(f"{row.market_name} high-temp Kalshi load failed: {exc}")
        try:
            low_markets = kalshi.get_series_markets(row.kalshi_low_series, status="open", limit=20)
        except Exception as exc:
            low_markets = []
            errors.append(f"{row.market_name} low-temp Kalshi load failed: {exc}")

        target_date = None
        if high_markets:
            target_date = parse_event_date(high_markets[0]["ticker"])
        elif low_markets:
            target_date = parse_event_date(low_markets[0]["ticker"])
        target_date = target_date or datetime.now().date()

        try:
            forecast = forecast_snapshot(nws, float(row.latitude), float(row.longitude), target_date=target_date)
        except Exception as exc:
            forecast = {
                "forecast_high": None,
                "forecast_low": None,
                "forecast_updated": None,
                "short_forecast": "NWS unavailable",
                "forecast_url": row.forecast_source,
                "hourly_url": row.forecast_source,
                "observed_url": row.settlement_source,
                "observed_high_today": None,
                "observed_low_today": None,
            }
            errors.append(f"{row.market_name} NWS load failed: {exc}")

        best_high = _best_contract(high_markets, "high", forecast.get("forecast_high"))
        best_low = _best_contract(low_markets, "low", forecast.get("forecast_low"))
        kalshi_high = _kalshi_single_forecast(high_markets)
        kalshi_low = _kalshi_single_forecast(low_markets)
        low_7_day = _next_night_forecast(nws, forecast.get("forecast_url") or row.forecast_source, target_date)

        high_status = best_high["rule"]["status"] if best_high else "Avoid"
        low_status = best_low["rule"]["status"] if best_low else "Avoid"

        high_rows.append(
            {
                "Signal": _signal_from_status(high_status),
                "City": row.market_name,
                "Hourly Forecast": _display_temp(forecast.get("forecast_high")),
                "Kalshi Forecast (F)": _display_temp(kalshi_high),
                "Short description": forecast.get("short_forecast") or "N/A",
                "Code": row.nws_station,
            }
        )

        low_rows.append(
            {
                "Signal": _signal_from_status(low_status),
                "City": row.market_name,
                "Observed Last 3 Days": _display_temp(forecast.get("observed_low_today")),
                "Hourly Forecast": _display_temp(forecast.get("forecast_low")),
                "7 Day Forecast": _display_temp(low_7_day),
                "Kalshi Forecast (F)": _display_temp(kalshi_low),
                "Short description": forecast.get("short_forecast") or "N/A",
                "Code": row.nws_station,
            }
        )

        map_rows.append(
            {
                "market_name": row.market_name,
                "label": row.market_name,
                "nws_station": row.nws_station,
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "forecast_high": _display_temp(forecast.get("forecast_high")),
                "forecast_low": _display_temp(forecast.get("forecast_low")),
                "current_pnl": f"${float(perf.get('net_pnl', 0.0) or 0.0):,.2f}",
                "total_trades": int(perf.get("total_trades", 0) or 0),
                "win_rate": f"{float(perf.get('win_rate', 0.0) or 0.0):.0%}",
                "open_exposure": f"${float(perf.get('open_exposure', 0.0) or 0.0):,.2f}",
                "color": [110, 194, 124, 190] if float(perf.get("net_pnl", 0.0) or 0.0) >= 0 else [255, 107, 107, 190],
                "radius": max(30000, int(perf.get("total_trades", 0) or 0) * 4500 + int(abs(float(perf.get("open_exposure", 0.0) or 0.0)) * 350)),
            }
        )

        delta_nws = None
        delta_kalshi = None
        if forecast.get("observed_high_today") is not None and forecast.get("forecast_high") is not None:
            delta_nws = forecast.get("observed_high_today") - forecast.get("forecast_high")
        if forecast.get("observed_high_today") is not None and kalshi_high is not None:
            delta_kalshi = forecast.get("observed_high_today") - kalshi_high

        historical_rows.append(
            {
                "City": row.market_name,
                "Date": target_date.isoformat(),
                "NWS Forecasted High T": _display_temp(forecast.get("forecast_high")),
                "NWS Forecasted Low T": _display_temp(forecast.get("forecast_low")),
                "Kalshi Forecasted High T": _display_temp(kalshi_high),
                "Kalshi Forecasted Low T": _display_temp(kalshi_low),
                "NWS Realized High T": _display_temp(forecast.get("observed_high_today")),
                "NWS Realized Low T": _display_temp(forecast.get("observed_low_today")),
                "Delta NWS": f"{delta_nws:+.1f}°" if delta_nws is not None else "N/A",
                "Delta Kalshi": f"{delta_kalshi:+.1f}°" if delta_kalshi is not None else "N/A",
            }
        )

    high_df = pd.DataFrame(high_rows).sort_values("City").reset_index(drop=True)
    low_df = pd.DataFrame(low_rows).sort_values("City").reset_index(drop=True)
    map_df = pd.DataFrame(map_rows).sort_values("market_name").reset_index(drop=True)
    historical_df = pd.DataFrame(historical_rows).sort_values("City").reset_index(drop=True)

    return {
        "high": high_df,
        "low": low_df,
        "map": map_df,
        "historical": historical_df,
        "errors": {"messages": errors},
        "portfolio": portfolio,
        "trade_source": trade_source,
    }
