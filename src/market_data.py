from __future__ import annotations

from datetime import datetime
import pandas as pd
import streamlit as st

from src.kalshi_client import KalshiClient, compute_yes_no_prices
from src.nws_client import NWSClient, forecast_snapshot
from src.rules_engine import evaluate_contract, extract_contract_label, parse_event_date, sort_monitor_rows
from src.trade_log import get_market_performance, load_trade_log
from src.utils import load_market_config, local_now


@st.cache_data(ttl=600, show_spinner=False)
def load_market_snapshots() -> dict[str, pd.DataFrame | dict]:
    config = load_market_config()
    kalshi = KalshiClient()
    nws = NWSClient()
    trade_log = load_trade_log()
    performance = get_market_performance(trade_log)

    high_rows: list[dict] = []
    low_rows: list[dict] = []
    map_rows: list[dict] = []
    historical_rows: list[dict] = []
    errors: list[str] = []

    for row in config.itertuples(index=False):
        perf_match = performance[performance["market"] == row.market_name]
        perf = perf_match.iloc[0].to_dict() if not perf_match.empty else {}
        local_time = local_now(row.timezone).strftime("%b %d %I:%M %p")

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

        map_rows.append(
            {
                "market_name": row.market_name,
                "nws_station": row.nws_station,
                "latitude": float(row.latitude),
                "longitude": float(row.longitude),
                "forecast_high": f"{int(forecast['forecast_high'])}°" if forecast.get("forecast_high") is not None else "N/A",
                "forecast_low": f"{int(forecast['forecast_low'])}°" if forecast.get("forecast_low") is not None else "N/A",
                "current_pnl": f"${float(perf.get('net_pnl', 0.0) or 0.0):,.2f}",
                "total_trades": int(perf.get("total_trades", 0) or 0),
                "win_rate": f"{float(perf.get('win_rate', 0.0) or 0.0):.0%}",
                "open_exposure": f"${float(perf.get('open_exposure', 0.0) or 0.0):,.2f}",
                "color": [110, 194, 124, 185] if float(perf.get("net_pnl", 0.0) or 0.0) >= 0 else [255, 107, 107, 185],
                "radius": max(35000, int(perf.get("total_trades", 0) or 0) * 5000 + int(abs(float(perf.get("open_exposure", 0.0) or 0.0)) * 400)),
            }
        )

        historical_rows.append(
            {
                "City": row.market_name,
                "Date": target_date.isoformat() if target_date else datetime.now().date().isoformat(),
                "NWS Forecasted High T": forecast.get("forecast_high"),
                "NWS Forecasted Low T": forecast.get("forecast_low"),
                "Kalshi Forecasted High T": ", ".join(extract_contract_label(m["title"]) for m in high_markets[:4]) if high_markets else "N/A",
                "Kalshi Forecasted Low T": ", ".join(extract_contract_label(m["title"]) for m in low_markets[:4]) if low_markets else "N/A",
                "NWS Realized High T": forecast.get("observed_high_today"),
                "NWS Realized Low T": forecast.get("observed_low_today"),
                "Delta NWS": (forecast.get("observed_high_today") - forecast.get("forecast_high")) if forecast.get("observed_high_today") is not None and forecast.get("forecast_high") is not None else None,
                "Delta Kalshi": None,
                "Forecast Source": forecast.get("forecast_url") or row.forecast_source,
                "Observed Source": forecast.get("observed_url") or row.settlement_source,
                "Climate Source": row.climate_source,
            }
        )

        for market in high_markets:
            label = extract_contract_label(str(market.get("title", "")))
            prices = compute_yes_no_prices(market)
            rule = evaluate_contract(
                market_type="high",
                contract_label=label,
                forecast_value=forecast.get("forecast_high"),
                yes_price=prices["yes_price"],
                no_price=prices["no_price"],
                volume=float(market.get("volume") or 0),
                liquidity=float(market.get("liquidity_dollars") or 0),
                close_time=market.get("close_time"),
            )
            high_rows.append(
                {
                    "Signal": rule["status"],
                    "Market": row.market_name,
                    "NWS Station": row.nws_station,
                    "Local Time": local_time,
                    "Observed Today": forecast.get("observed_high_today"),
                    "Forecast High": forecast.get("forecast_high"),
                    "Forecast Updated": forecast.get("forecast_updated"),
                    "Short Forecast": forecast.get("short_forecast"),
                    "NWS Forecast URL": forecast.get("hourly_url") or row.forecast_source,
                    "Observed Source": forecast.get("observed_url") or row.settlement_source,
                    "Kalshi Contract": label,
                    "YES Price": prices["yes_price"],
                    "NO Price": prices["no_price"],
                    "Implied Probability": rule["implied_probability"],
                    "Distance": rule["distance_from_forecast"],
                    "Suggested Direction": rule["suggested_direction"],
                    "Edge": rule["edge"],
                    "Status": rule["status"],
                    "Liquidity / Volume": f"${float(market.get('liquidity_dollars') or 0):,.0f} / {float(market.get('volume') or 0):,.0f}",
                    "Time to Settlement": rule["maturity_label"] or "N/A",
                    "Market Link": row.kalshi_high_slug,
                    "Notes": rule["note"],
                }
            )

        for market in low_markets:
            label = extract_contract_label(str(market.get("title", "")))
            prices = compute_yes_no_prices(market)
            rule = evaluate_contract(
                market_type="low",
                contract_label=label,
                forecast_value=forecast.get("forecast_low"),
                yes_price=prices["yes_price"],
                no_price=prices["no_price"],
                volume=float(market.get("volume") or 0),
                liquidity=float(market.get("liquidity_dollars") or 0),
                close_time=market.get("close_time"),
            )
            low_rows.append(
                {
                    "Signal": rule["status"],
                    "Market": row.market_name,
                    "NWS Station": row.nws_station,
                    "Local Time": local_time,
                    "Observed Today": forecast.get("observed_low_today"),
                    "Forecast Low": forecast.get("forecast_low"),
                    "Forecast Updated": forecast.get("forecast_updated"),
                    "Short Forecast": forecast.get("short_forecast"),
                    "NWS Forecast URL": forecast.get("hourly_url") or row.forecast_source,
                    "Observed Source": forecast.get("observed_url") or row.settlement_source,
                    "Kalshi Contract": label,
                    "YES Price": prices["yes_price"],
                    "NO Price": prices["no_price"],
                    "Implied Probability": rule["implied_probability"],
                    "Distance": rule["distance_from_forecast"],
                    "Suggested Direction": rule["suggested_direction"],
                    "Edge": rule["edge"],
                    "Status": rule["status"],
                    "Liquidity / Volume": f"${float(market.get('liquidity_dollars') or 0):,.0f} / {float(market.get('volume') or 0):,.0f}",
                    "Time to Settlement": rule["maturity_label"] or "N/A",
                    "Market Link": row.kalshi_low_slug,
                    "Notes": rule["note"],
                }
            )

        if not high_markets:
            high_rows.append(
                {
                    "Signal": "Avoid",
                    "Market": row.market_name,
                    "NWS Station": row.nws_station,
                    "Local Time": local_time,
                    "Observed Today": forecast.get("observed_high_today"),
                    "Forecast High": forecast.get("forecast_high"),
                    "Forecast Updated": forecast.get("forecast_updated"),
                    "Short Forecast": forecast.get("short_forecast"),
                    "NWS Forecast URL": forecast.get("hourly_url") or row.forecast_source,
                    "Observed Source": forecast.get("observed_url") or row.settlement_source,
                    "Kalshi Contract": "No active contract found",
                    "YES Price": None,
                    "NO Price": None,
                    "Implied Probability": None,
                    "Distance": None,
                    "Suggested Direction": "Avoid",
                    "Edge": None,
                    "Status": "Avoid",
                    "Liquidity / Volume": "N/A",
                    "Time to Settlement": "N/A",
                    "Market Link": row.kalshi_high_slug,
                    "Notes": "Series did not return active markets.",
                }
            )
        if not low_markets:
            low_rows.append(
                {
                    "Signal": "Avoid",
                    "Market": row.market_name,
                    "NWS Station": row.nws_station,
                    "Local Time": local_time,
                    "Observed Today": forecast.get("observed_low_today"),
                    "Forecast Low": forecast.get("forecast_low"),
                    "Forecast Updated": forecast.get("forecast_updated"),
                    "Short Forecast": forecast.get("short_forecast"),
                    "NWS Forecast URL": forecast.get("hourly_url") or row.forecast_source,
                    "Observed Source": forecast.get("observed_url") or row.settlement_source,
                    "Kalshi Contract": "No active contract found",
                    "YES Price": None,
                    "NO Price": None,
                    "Implied Probability": None,
                    "Distance": None,
                    "Suggested Direction": "Avoid",
                    "Edge": None,
                    "Status": "Avoid",
                    "Liquidity / Volume": "N/A",
                    "Time to Settlement": "N/A",
                    "Market Link": row.kalshi_low_slug,
                    "Notes": "Series did not return active markets.",
                }
            )

    return {
        "high": sort_monitor_rows(pd.DataFrame(high_rows)),
        "low": sort_monitor_rows(pd.DataFrame(low_rows)),
        "map": pd.DataFrame(map_rows),
        "historical": pd.DataFrame(historical_rows),
        "errors": {"messages": errors},
    }
