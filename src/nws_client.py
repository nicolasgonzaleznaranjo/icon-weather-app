from __future__ import annotations

from datetime import date, datetime
from io import StringIO
import re
from typing import Any

import pandas as pd
import requests
import streamlit as st

from src.utils import USER_AGENT


class NWSClient:
    def __init__(self) -> None:
        self.last_successful_request: str | None = None
        self.last_error: str | None = None

    def _get_json(self, url: str) -> dict[str, Any]:
        response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}, timeout=25)
        response.raise_for_status()
        self.last_successful_request = datetime.utcnow().isoformat()
        return response.json()

    @st.cache_data(ttl=900, show_spinner=False)
    def get_point_metadata(_self, latitude: float, longitude: float) -> dict[str, Any]:
        data = _self._get_json(f"https://api.weather.gov/points/{latitude},{longitude}")
        return data.get("properties", {})

    @st.cache_data(ttl=900, show_spinner=False)
    def get_forecast(_self, url: str) -> dict[str, Any]:
        data = _self._get_json(url)
        return data.get("properties", {})

    @st.cache_data(ttl=900, show_spinner=False)
    def get_hourly_forecast(_self, url: str) -> dict[str, Any]:
        data = _self._get_json(url)
        return data.get("properties", {})

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_station_history_meta(_self, station: str) -> dict[str, Any]:
        url = f"https://forecast.weather.gov/data/obhistory/{station}.html"
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        response.raise_for_status()
        match = re.search(r'DC.date.created" scheme="ISO8601" content="([^"]+)"', response.text)
        observed_high_today = None
        observed_low_today = None
        try:
            tables = pd.read_html(StringIO(response.text))
            table = next((t for t in tables if any("Time" in str(col) for col in t.columns)), None)
            if table is not None:
                temp_column = next((col for col in table.columns if "Air" in str(col) or "Temperature" in str(col)), None)
                if temp_column is not None:
                    temp_values = pd.to_numeric(table[temp_column], errors="coerce").dropna()
                    if not temp_values.empty:
                        observed_high_today = float(temp_values.max())
                        observed_low_today = float(temp_values.min())
        except Exception:
            pass
        return {
            "url": url,
            "last_updated": match.group(1) if match else None,
            "observed_high_today": observed_high_today,
            "observed_low_today": observed_low_today,
        }


def forecast_snapshot(client: NWSClient, latitude: float, longitude: float, target_date: date | None = None) -> dict[str, Any]:
    point = client.get_point_metadata(latitude, longitude)
    forecast_url = point.get("forecast")
    hourly_url = point.get("forecastHourly")
    station = str(point.get("stationIdentifier") or "").split("/")[-1] if point.get("stationIdentifier") else None
    if not forecast_url or not hourly_url:
        raise ValueError("NWS point metadata did not return forecast URLs.")

    forecast = client.get_forecast(forecast_url)
    hourly = client.get_hourly_forecast(hourly_url)
    history = client.get_station_history_meta(station) if station else {"url": None, "last_updated": None, "observed_high_today": None, "observed_low_today": None}
    periods = hourly.get("periods", [])
    target_date = target_date or datetime.now().date()

    target_periods = []
    for period in periods:
        start = datetime.fromisoformat(period["startTime"])
        if start.date() == target_date:
            target_periods.append(period)

    if not target_periods:
        daily_periods = forecast.get("periods", [])
        day_period = next((p for p in daily_periods if datetime.fromisoformat(p["startTime"]).date() == target_date and p.get("isDaytime")), None)
        night_period = next((p for p in daily_periods if datetime.fromisoformat(p["startTime"]).date() == target_date and not p.get("isDaytime")), None)
        return {
            "forecast_high": day_period.get("temperature") if day_period else None,
            "forecast_low": night_period.get("temperature") if night_period else None,
            "forecast_updated": forecast.get("updateTime") or hourly.get("updateTime"),
            "short_forecast": (day_period or night_period or {}).get("shortForecast"),
            "forecast_url": forecast_url,
            "hourly_url": hourly_url,
            "grid_url": point.get("forecastGridData"),
            "observed_url": history.get("url"),
            "observed_high_today": history.get("observed_high_today"),
            "observed_low_today": history.get("observed_low_today"),
        }

    temps = [period.get("temperature") for period in target_periods if isinstance(period.get("temperature"), (int, float))]
    forecast_high = max(temps) if temps else None
    forecast_low = min(temps) if temps else None
    current_period = target_periods[0] if target_periods else {}
    return {
        "forecast_high": forecast_high,
        "forecast_low": forecast_low,
        "forecast_updated": hourly.get("updateTime") or forecast.get("updateTime"),
        "short_forecast": current_period.get("shortForecast"),
        "forecast_url": forecast_url,
        "hourly_url": hourly_url,
        "grid_url": point.get("forecastGridData"),
        "observed_url": history.get("url"),
        "observed_high_today": history.get("observed_high_today"),
        "observed_low_today": history.get("observed_low_today"),
    }
