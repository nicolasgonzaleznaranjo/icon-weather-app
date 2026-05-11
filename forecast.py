from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from config import APP_TIMEZONE, CITIES_PATH


NWS_USER_AGENT = "ICON Weather Trading App demo contact: personal-use"


def _request_json(url: str) -> dict:
    response = requests.get(
        url,
        headers={
            "User-Agent": NWS_USER_AGENT,
            "Accept": "application/geo+json, application/json",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _period_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            ZoneInfo(APP_TIMEZONE)
        ).date()
    except Exception:
        return None


def _get_nws_high_low(lat: float, lon: float, target_date: date) -> dict[str, int | None]:
    point = _request_json(f"https://api.weather.gov/points/{lat},{lon}")
    forecast_url = point.get("properties", {}).get("forecast")
    if not forecast_url:
        return {"High Temp": None, "Low Temp": None}

    forecast = _request_json(forecast_url)
    periods = forecast.get("properties", {}).get("periods", [])
    high = None
    low = None

    for period in periods:
        if _period_date(period.get("startTime")) != target_date:
            continue
        temperature = period.get("temperature")
        if temperature is None:
            continue
        if period.get("isDaytime") is True:
            high = int(temperature)
        if period.get("isDaytime") is False:
            low = int(temperature)

    return {"High Temp": high, "Low Temp": low}


def load_city_forecasts(
    city_names: list[str] | None = None,
    target_date: date | None = None,
) -> dict[str, dict[str, int | None]]:
    try:
        cities = pd.read_csv(CITIES_PATH).sort_values(["priority", "city"])
    except Exception:
        return {}

    if city_names:
        cities = cities[cities["city"].isin(city_names)]

    target_date = target_date or datetime.now(ZoneInfo(APP_TIMEZONE)).date()

    forecasts: dict[str, dict[str, int | None]] = {}
    for _, row in cities.iterrows():
        city = str(row.get("city", "Unknown"))
        try:
            forecasts[city] = _get_nws_high_low(float(row["lat"]), float(row["lon"]), target_date)
        except Exception:
            forecasts[city] = {"High Temp": None, "Low Temp": None}
    return forecasts


def forecast_for(city: str, market_type: str, forecasts: dict[str, dict[str, int | None]]) -> int | None:
    return forecasts.get(city, {}).get(market_type)
