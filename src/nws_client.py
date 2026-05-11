from __future__ import annotations

from datetime import date, datetime, time, timedelta
import html
from io import StringIO
import re
from typing import Any
from zoneinfo import ZoneInfo

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

    @st.cache_data(ttl=900, show_spinner=False)
    def get_digital_temperature_points(_self, url: str, timezone_name: str) -> list[dict[str, Any]]:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        response.raise_for_status()
        html_text = response.text

        def _clean_cell(cell_html: str) -> str:
            text = re.sub(r"<[^>]+>", " ", cell_html, flags=re.IGNORECASE | re.DOTALL)
            text = html.unescape(text).replace("\xa0", " ")
            text = re.sub(r"\s+", " ", text).strip()
            return text

        def _parse_html_rows(markup: str) -> list[list[str]]:
            row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", markup, flags=re.IGNORECASE | re.DOTALL)
            parsed_rows: list[list[str]] = []
            for row_html in row_matches:
                expanded_row: list[str] = []
                for cell_match in re.finditer(
                    r"<t[dh]([^>]*)>(.*?)</t[dh]>",
                    row_html,
                    flags=re.IGNORECASE | re.DOTALL,
                ):
                    attrs = cell_match.group(1) or ""
                    cell_body = cell_match.group(2) or ""
                    cleaned = _clean_cell(cell_body)
                    colspan_match = re.search(r'colspan=["\']?(\d+)', attrs, flags=re.IGNORECASE)
                    colspan = int(colspan_match.group(1)) if colspan_match else 1
                    colspan = max(1, colspan)
                    expanded_row.extend([cleaned] * colspan)
                if any(expanded_row):
                    parsed_rows.append(expanded_row)
            return parsed_rows

        parsed_rows = _parse_html_rows(html_text)

        def _is_date_row(row: list[str]) -> bool:
            return bool(row) and row[0].strip().lower() == "date"

        def _is_hour_row(row: list[str]) -> bool:
            return bool(row) and row[0].strip().lower().startswith("hour")

        def _is_temp_row(row: list[str]) -> bool:
            if not row:
                return False
            label = row[0].strip().lower()
            return label.startswith("temperature")

        tz = ZoneInfo(timezone_name)
        now_local = datetime.now(tz)
        parsed_points: list[dict[str, Any]] = []
        date_row = next((row for row in parsed_rows if _is_date_row(row)), None)
        hour_row = next((row for row in parsed_rows if _is_hour_row(row)), None)
        temp_row = next((row for row in parsed_rows if _is_temp_row(row)), None)

        if date_row and hour_row and temp_row:
            date_values = date_row[1:]
            hour_values = hour_row[1:]
            temp_values = temp_row[1:]
            width = min(len(date_values), len(hour_values), len(temp_values))
            current_date = None

            for raw_date, raw_hour, raw_temp in zip(date_values[:width], hour_values[:width], temp_values[:width]):
                if re.fullmatch(r"\d{2}/\d{2}", raw_date or ""):
                    current_date = raw_date
                if not current_date or not re.fullmatch(r"\d{2}/\d{2}", current_date):
                    continue
                if not re.fullmatch(r"\d{1,2}", raw_hour or ""):
                    continue
                if not re.fullmatch(r"-?\d+(?:\.\d+)?", raw_temp or ""):
                    continue
                month_str, day_str = current_date.split("/")
                try:
                    point_dt = datetime(
                        now_local.year,
                        int(month_str),
                        int(day_str),
                        int(raw_hour),
                        0,
                        tzinfo=tz,
                    )
                except Exception:
                    continue
                parsed_points.append(
                    {
                        "timestamp": point_dt,
                        "date": point_dt.date(),
                        "hour": point_dt.strftime("%H:%M"),
                        "temperature": float(raw_temp),
                    }
                )

        if parsed_points:
            parsed_points.sort(key=lambda point: point["timestamp"])
            return parsed_points

        # Fallback to pandas table parsing if the row-based HTML parser finds nothing.
        try:
            tables = pd.read_html(StringIO(html_text))
        except Exception:
            return []

        target = None
        for table in tables:
            text = " ".join(table.astype(str).fillna("").head(8).astype(str).values.flatten())
            if "Date" in text and "Hour" in text and "Temperature" in text:
                target = table.copy()
                break

        if target is None or target.empty:
            return []

        target = target.fillna("")
        current_date = None
        hour_values: list[str] = []
        temp_values: list[str] = []
        date_values: list[str] = []
        for _, row in target.iterrows():
            first = str(row.iloc[0]).strip().lower()
            values = [str(v).strip() for v in row.tolist()][1:]
            if first == "date":
                date_values = values
            elif first.startswith("hour"):
                hour_values = values
            elif first.startswith("temperature"):
                temp_values = values

        width = min(len(date_values), len(hour_values), len(temp_values))
        for raw_date, raw_hour, raw_temp in zip(date_values[:width], hour_values[:width], temp_values[:width]):
            if re.fullmatch(r"\d{2}/\d{2}", raw_date or ""):
                current_date = raw_date
            if not current_date or not re.fullmatch(r"\d{2}/\d{2}", current_date):
                continue
            if not re.fullmatch(r"\d{1,2}", raw_hour or "") or not re.fullmatch(r"-?\d+(?:\.\d+)?", raw_temp or ""):
                continue
            month_str, day_str = current_date.split("/")
            try:
                point_dt = datetime(
                    now_local.year,
                    int(month_str),
                    int(day_str),
                    int(raw_hour),
                    0,
                    tzinfo=tz,
                )
            except Exception:
                continue
            parsed_points.append(
                {
                    "timestamp": point_dt,
                    "date": point_dt.date(),
                    "hour": point_dt.strftime("%H:%M"),
                    "temperature": float(raw_temp),
                }
            )

        parsed_points.sort(key=lambda point: point["timestamp"])
        return parsed_points


def select_digital_temperature_for_date(
    points: list[dict[str, Any]],
    target_date: date,
    mode: str,
) -> dict[str, Any]:
    day_points = [point for point in points if point.get("date") == target_date and isinstance(point.get("temperature"), (int, float))]
    if not day_points:
        return {"value": None, "hour": None, "points": [], "count": 0, "first_timestamp": None, "last_timestamp": None}

    selected = min(day_points, key=lambda point: float(point["temperature"])) if mode == "min" else max(
        day_points, key=lambda point: float(point["temperature"])
    )
    return {
        "value": float(selected["temperature"]),
        "hour": selected["hour"],
        "points": [
            f"{point['timestamp'].strftime('%Y-%m-%d %H:%M')}={float(point['temperature']):.1f}"
            for point in day_points
        ],
        "count": len(day_points),
        "first_timestamp": day_points[0]["timestamp"].strftime("%Y-%m-%d %H:%M"),
        "last_timestamp": day_points[-1]["timestamp"].strftime("%Y-%m-%d %H:%M"),
    }


def select_digital_temperature_for_window(
    points: list[dict[str, Any]],
    timezone_name: str,
    mode: str,
) -> dict[str, Any]:
    tz = ZoneInfo(timezone_name)
    now_local = datetime.now(tz)
    window_start = now_local.replace(minute=0, second=0, microsecond=0)
    next_window_end = datetime.combine(window_start.date() + timedelta(days=1), time(0, 0), tzinfo=tz)
    window_points = [
        point
        for point in points
        if isinstance(point.get("temperature"), (int, float))
        and point.get("timestamp") is not None
        and window_start <= point["timestamp"] <= next_window_end
    ]
    if not window_points:
        return {"value": None, "hour": None, "points": [], "count": 0, "first_timestamp": None, "last_timestamp": None}

    selected = min(window_points, key=lambda point: float(point["temperature"])) if mode == "min" else max(
        window_points, key=lambda point: float(point["temperature"])
    )
    return {
        "value": float(selected["temperature"]),
        "hour": selected["hour"],
        "points": [
            f"{point['timestamp'].strftime('%Y-%m-%d %H:%M')}={float(point['temperature']):.1f}"
            for point in window_points
        ],
        "count": len(window_points),
        "first_timestamp": window_points[0]["timestamp"].strftime("%Y-%m-%d %H:%M"),
        "last_timestamp": window_points[-1]["timestamp"].strftime("%Y-%m-%d %H:%M"),
    }


def forecast_snapshot(
    client: NWSClient,
    latitude: float,
    longitude: float,
    target_date: date | None = None,
    station: str | None = None,
    timezone_name: str | None = None,
    digital_forecast_url: str | None = None,
) -> dict[str, Any]:
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
    now_local = datetime.now(ZoneInfo(timezone_name)) if timezone_name else datetime.now().astimezone()

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

    digital_points: list[dict[str, Any]] = []
    digital_low_meta = {"value": None, "hour": None, "points": []}
    digital_high_meta = {"value": None, "hour": None, "points": []}
    if digital_forecast_url and timezone_name:
        try:
            digital_points = client.get_digital_temperature_points(digital_forecast_url, timezone_name)
            digital_low_meta = select_digital_temperature_for_window(digital_points, timezone_name, "min")
            digital_high_meta = select_digital_temperature_for_window(digital_points, timezone_name, "max")
        except Exception:
            pass

    if not target_periods:
        day_period = next((p for p in forecast.get("periods", []) if datetime.fromisoformat(p["startTime"]).date() == target_date and p.get("isDaytime")), None)
        night_period = next((p for p in forecast.get("periods", []) if datetime.fromisoformat(p["startTime"]).date() == target_date and not p.get("isDaytime")), None)
        forecast_high = day_period.get("temperature") if day_period else None
        forecast_low = night_period.get("temperature") if night_period else None
        forecast_high_today = digital_high_meta["value"] if digital_high_meta["value"] is not None else forecast_high
        forecast_low_today = digital_low_meta["value"] if digital_low_meta["value"] is not None else forecast_low
        return {
            "forecast_high": forecast_high,
            "forecast_high_today": forecast_high_today,
            "forecast_low": forecast_low,
            "forecast_low_today": forecast_low_today,
            "forecast_updated": forecast.get("updateTime") or hourly.get("updateTime"),
            "short_forecast": (day_period or night_period or {}).get("shortForecast"),
            "forecast_url": forecast_url,
            "hourly_url": hourly_url,
            "grid_url": point.get("forecastGridData"),
            "observed_url": history.get("url"),
            "observed_high_today": history.get("observed_high_today"),
            "observed_low_today": history.get("observed_low_today"),
            "active_market_date": target_date.isoformat(),
            "digital_forecast_url": digital_forecast_url,
            "digital_points_for_date": digital_low_meta["points"] or digital_high_meta["points"],
            "digital_selected_low_value": digital_low_meta["value"],
            "digital_selected_low_hour": digital_low_meta["hour"],
            "digital_selected_high_value": digital_high_meta["value"],
            "digital_selected_high_hour": digital_high_meta["hour"],
            "digital_points_count": digital_low_meta["count"] or digital_high_meta["count"],
            "digital_first_timestamp": digital_low_meta["first_timestamp"] or digital_high_meta["first_timestamp"],
            "digital_last_timestamp": digital_low_meta["last_timestamp"] or digital_high_meta["last_timestamp"],
        }

    temps = [period.get("temperature") for period in target_periods if isinstance(period.get("temperature"), (int, float))]
    remaining_temps = [period.get("temperature") for period in remaining_periods if isinstance(period.get("temperature"), (int, float))]
    forecast_high = max(temps) if temps else None
    forecast_low = min(temps) if temps else None
    forecast_low_from_now = min(remaining_temps) if remaining_temps else forecast_low
    remaining_today_temps = [period.get("temperature") for period in remaining_today_periods if isinstance(period.get("temperature"), (int, float))]
    forecast_low_today = digital_low_meta["value"] if digital_low_meta["value"] is not None else (min(remaining_today_temps) if remaining_today_temps else forecast_low_from_now)
    forecast_high_today = digital_high_meta["value"] if digital_high_meta["value"] is not None else forecast_high
    current_period = target_periods[0] if target_periods else {}
    return {
        "forecast_high": forecast_high,
        "forecast_high_today": forecast_high_today,
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
        "active_market_date": target_date.isoformat(),
        "digital_forecast_url": digital_forecast_url,
        "digital_points_for_date": digital_low_meta["points"] or digital_high_meta["points"],
        "digital_selected_low_value": digital_low_meta["value"],
        "digital_selected_low_hour": digital_low_meta["hour"],
        "digital_selected_high_value": digital_high_meta["value"],
        "digital_selected_high_hour": digital_high_meta["hour"],
        "digital_points_count": digital_low_meta["count"] or digital_high_meta["count"],
        "digital_first_timestamp": digital_low_meta["first_timestamp"] or digital_high_meta["first_timestamp"],
        "digital_last_timestamp": digital_low_meta["last_timestamp"] or digital_high_meta["last_timestamp"],
    }
