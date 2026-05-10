from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketConfig:
    market_name: str
    nws_station: str
    latitude: float
    longitude: float
    timezone: str
    forecast_source: str
    settlement_source: str
    climate_source: str
    kalshi_high_slug: str
    kalshi_low_slug: str
    kalshi_high_series: str
    kalshi_low_series: str
    weather_office: str


@dataclass(frozen=True)
class ContractSpec:
    raw_label: str
    kind: str
    lower_bound: float | None
    upper_bound: float | None
    display_lower: float | None
    display_upper: float | None

    @property
    def center(self) -> float | None:
        if self.lower_bound is None and self.upper_bound is None:
            return None
        if self.lower_bound is None:
            return self.upper_bound
        if self.upper_bound is None:
            return self.lower_bound
        return (self.lower_bound + self.upper_bound) / 2
