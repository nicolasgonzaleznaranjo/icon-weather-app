from __future__ import annotations

from datetime import date, datetime, time, timedelta
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
            normalized_tables = []
            for t in tables:
                if isinstance(t.columns, pd.MultiIndex):
                    t.columns = [" ".join(str(part) for part in col if str(part) != "nan").strip() for col in t.columns]
                else:
                    t.columns = [str(col).strip() for col in t.columns]
                normalized_tables.append(t)

            table = next((t for t in normalized_tables if any("Time" in str(col) for col in t.columns)), None)
            if table is not None:
                temp_column = next(
                    (
                        col
                        for col in table.columns
                        if "temperature" in str(col).lower() and "air" in str(col).lower()
                    ),
                    None,
                )
                if temp_column is None:
                    temp_column = next(
                        (
                            col
                            for col in table.columns
                            if "temperature" in str(col).lower() and "6 hour" not in str(col).lower()
                        ),
                        None,
                    )
                time_column = next((col for col in table.columns if "Time" in str(col)), None)
                date_column = next((col for col in table.columns if str(col).strip().lower() == "date" or " date" in str(col).lower()), None)
                if temp_column is not None:
                    working = table.copy()
                    working[temp_column] = pd.to_numeric(working[temp_column], errors="coerce")
                    if date_column is not None:
                        working[date_column] = pd.to_numeric(working[date_column], errors="coerce")
                        latest_day = working[date_column].dropna().max()
                        if pd.notna(latest_day):
                            working = working[working[date_column] == latest_day].copy()

                    if time_column is not None:
                        working[time_column] = working[time_column].astype(str)

                        def _to_minutes(value: str) -> int | None:
                            cleaned = value.strip().upper().replace(" ", "")
                            match_ampm = re.match(r"(\d{1,2}):(\d{2})(AM|PM)", cleaned)
                            if match_ampm:
                                hour = int(match_ampm.group(1))
                                minute = int(match_ampm.group(2))
                                period = match_ampm.group(3)
                                if period == "AM":
                                    hour = 0 if hour == 12 else hour
                                else:
                                    hour = 12 if hour == 12 else hour + 12
                                return hour * 60 + minute
                            match_24 = re.match(r"(\d{1,2}):(\d{2})", cleaned)
                            if match_24:
                                return int(match_24.group(1)) * 60 + int(match_24.group(2))
                            return None

                        working["minutes"] = working[time_column].map(_to_minutes)
                        timed = working[working["minutes"].notna() & working[temp_column].notna()].copy()
                        if not timed.empty:
                            observed_low_today = float(timed[temp_column].min())
                            observed_high_today = float(timed[temp_column].max())
                        else:
                            temp_values = working[temp_column].dropna()
                            if not temp_values.empty:
                                observed_high_today = float(temp_values.max())
                                observed_low_today = float(temp_values.min())
                    else:
                        temp_values = working[temp_column].dropna()
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


def forecast_snapshot(client: NWSClient, latitude: float, longitude: float, target_date: date | None = None, station: str | None = None) -> dict[str, Any]:
    point = client.get_point_metadata(latitude, longitude)
    forecast_url = point.get("forecast")
    hourly_url = point.get("forecastHourly")
    station_id = station or (str(point.get("stationIdentifier") or "").split("/")[-1] if point.get("stationIdentifier") else None)
    if not forecast_url or not hourly_url:
        raise ValueError("NWS point metadata did not return forecast URLs.")

    forecast = client.get_forecast(forecast_url)
    hourly = client.get_hourly_forecast(hourly_url)
    history = client.get_station_history_meta(station_id) if station_id else {"url": None, "last_updated": None, "observed_high_today": None, "observed_low_today": None}
    periods = hourly.get("periods", [])
    target_date = target_date or datetime.now().date()
    now_local = datetime.now().astimezone()

    target_periods = []
    for period in periods:
        start = datetime.fromisoformat(period["startTime"])
        if start.date() == target_date:
            target_periods.append(period)

    remaining_periods = []
    for period in periods:
        start = datetime.fromisoformat(period["startTime"])
        if start.date() == target_date and start >= now_local:
            remaining_periods.append(period)

    cutoff = datetime.combine(now_local.date() + timedelta(days=1), time.min, tzinfo=now_local.tzinfo)
    remaining_today_periods = []
    for period in periods:
        start = datetime.fromisoformat(period["startTime"])
        if start >= now_local and start <= cutoff:
            remaining_today_periods.append(period)

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
    remaining_temps = [period.get("temperature") for period in remaining_periods if isinstance(period.get("temperature"), (int, float))]
    forecast_high = max(temps) if temps else None
    forecast_low = min(temps) if temps else None
    forecast_low_from_now = min(remaining_temps) if remaining_temps else forecast_low
    remaining_today_temps = [period.get("temperature") for period in remaining_today_periods if isinstance(period.get("temperature"), (int, float))]
    forecast_low_today = min(remaining_today_temps) if remaining_today_temps else forecast_low_from_now
    current_period = target_periods[0] if target_periods else {}
    return {
        "forecast_high": forecast_high,
        "forecast_low": forecast_low,
        "forecast_low_from_now": forecast_low_from_now,
        "forecast_low_today": forecast_low_today,
        "forecast_updated": hourly.get("updateTime") or forecast.get("updateTime"),
        "short_forecast": current_period.get("shortForecast"),
        "forecast_url": forecast_url,
        "hourly_url": hourly_url,
        "grid_url": point.get("forecastGridData"),
        "observed_url": history.get("url"),
        "observed_high_today": history.get("observed_high_today"),
        "observed_low_today": history.get("observed_low_today"),
    }
