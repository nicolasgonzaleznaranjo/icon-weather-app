from __future__ import annotations

from datetime import date, datetime
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class WeatherMarket:
    ticker: str
    city: str
    market_type: str
    contract_label: str
    contract_display: str
    event_date: date | None
    event_ticker: str
    market: dict[str, Any]


def _text(market: dict[str, Any]) -> str:
    parts = [
        market.get("title"),
        market.get("subtitle"),
        market.get("event_title"),
        market.get("event_ticker"),
        market.get("series_ticker"),
        market.get("ticker"),
    ]
    return " ".join(str(part) for part in parts if part).replace("**", "")


def is_weather_temperature_market(market: dict[str, Any]) -> bool:
    haystack = _text(market).lower()
    return "temperature" in haystack or "temp" in haystack


def parse_market(market: dict[str, Any], city_lookup: dict[str, str] | None = None) -> WeatherMarket:
    raw_title = _text(market)
    haystack = raw_title.lower()
    ticker = str(market.get("ticker") or "")
    event_ticker = str(market.get("event_ticker") or "")

    market_type = (
        "High Temperature"
        if "high temp" in haystack or "maximum temperature" in haystack
        else "Low Temperature"
        if "low temp" in haystack or "minimum temperature" in haystack
        else "Temperature"
    )

    city = "Unknown"
    for candidate in (city_lookup or {}):
        if candidate.lower() in haystack:
            city = candidate
            break
    if city == "Unknown" and city_lookup:
        for candidate, series in city_lookup.items():
            if any(part and part.lower() in ticker.lower() for part in str(series).split()):
                city = candidate
                break

    label = extract_contract_label(raw_title)
    return WeatherMarket(
        ticker=ticker,
        city=city,
        market_type=market_type,
        contract_label=label,
        contract_display=label,
        event_date=_parse_event_date(raw_title, ticker),
        event_ticker=event_ticker,
        market=market,
    )


def extract_contract_label(raw_title: str) -> str:
    patterns = [
        (r"(>\s*\d{2,3}°?)", lambda m: m.group(1).replace(" ", "")),
        (r"(<\s*\d{2,3}°?)", lambda m: m.group(1).replace(" ", "")),
        (r"(\d{2,3})-(\d{2,3})°", lambda m: f"{m.group(1)}-{m.group(2)}°"),
        (r"(\d{2,3})\s*to\s*(\d{2,3})", lambda m: f"{m.group(1)}-{m.group(2)}°"),
        (r"(\d{2,3})°", lambda m: f"{m.group(1)}°"),
    ]
    for pattern, formatter in patterns:
        match = re.search(pattern, raw_title, flags=re.IGNORECASE)
        if match:
            return formatter(match)
    return raw_title


def _parse_event_date(raw_title: str, ticker: str) -> date | None:
    title_match = re.search(
        r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),\s+(\d{4})",
        raw_title,
        flags=re.IGNORECASE,
    )
    if title_match:
        month, day, year = title_match.groups()
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(f"{month} {day} {year}", fmt).date()
            except ValueError:
                continue

    ticker_match = re.search(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})", ticker, flags=re.IGNORECASE)
    if ticker_match:
        year, month, day = ticker_match.groups()
        try:
            return datetime.strptime(f"20{year} {month.upper()} {day}", "%Y %b %d").date()
        except ValueError:
            return None
    return None


def filter_weather_markets(markets: list[dict[str, Any]], city_lookup: dict[str, str] | None = None) -> list[WeatherMarket]:
    parsed: list[WeatherMarket] = []
    for market in markets:
        if is_weather_temperature_market(market):
            parsed.append(parse_market(market, city_lookup))
    return parsed
