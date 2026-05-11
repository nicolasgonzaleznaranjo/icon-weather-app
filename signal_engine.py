from __future__ import annotations

from collections import defaultdict
from typing import Any


def bucket_price(price_cents: int | None) -> str:
    if price_cents is None:
        return "N/A"
    lower = max(0, (price_cents // 5) * 5)
    return f"{lower}-{lower+5}"


def numeric_from_contract(contract_label: str) -> tuple[float | None, float | None]:
    cleaned = contract_label.replace("°", "").strip()
    if cleaned.startswith(">"):
        edge = float(cleaned[1:])
        return edge, edge
    if cleaned.startswith("<"):
        edge = float(cleaned[1:])
        return edge, edge
    if "-" in cleaned:
        low, high = cleaned.split("-", 1)
        return float(low), float(high)
    try:
        value = float(cleaned)
        return value, value
    except ValueError:
        return None, None


def distance_from_forecast(contract_label: str, forecast: float | None) -> float | None:
    if forecast is None:
        return None
    low, high = numeric_from_contract(contract_label)
    if low is None:
        return None
    midpoint = (low + high) / 2
    return round(midpoint - forecast, 1)


def infer_forecasts(market_rows: list[dict[str, Any]]) -> dict[tuple[str, str], float | None]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in market_rows:
        grouped[(row["city"], row["type"])].append(row)

    inferred: dict[tuple[str, str], float | None] = {}
    for key, rows in grouped.items():
        candidate = max(
            rows,
            key=lambda item: (
                item.get("midpoint_cents") is not None,
                item.get("midpoint_cents") or 0,
                item.get("yes_buy_cents") is not None,
            ),
        )
        low, high = numeric_from_contract(candidate["contract"])
        inferred[key] = (low + high) / 2 if low is not None else None
    return inferred


def historical_probability(row: dict[str, Any]) -> float:
    # Until we accumulate enough settlement history, use a conservative
    # underwriting prior centered slightly above the market-implied number
    # for rule-aligned setups and slightly below it otherwise.
    price = row.get("implied_probability") or 0.0
    distance = row.get("distance_from_forecast")
    market_type = row.get("type")
    if market_type == "High Temperature" and distance is not None and distance >= 2:
        return min(0.99, price + 0.07)
    if market_type == "Low Temperature" and distance is not None and distance <= -2:
        return min(0.99, price + 0.07)
    return row["implied_probability"]


def normalize(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    clipped = max(low, min(high, value))
    return (clipped - low) / (high - low)


def price_score(price_cents: int | None) -> float:
    if price_cents is None:
        return 0.0
    if 85 <= price_cents <= 90:
        return 1.0
    if 80 <= price_cents <= 95:
        return 0.7
    if price_cents >= 60:
        return 0.45
    return 0.1


def distance_score(distance: float | None, market_type: str) -> float:
    if distance is None:
        return 0.0
    if market_type == "High Temperature":
        if distance >= 2:
            return 1.0
        if distance >= 1:
            return 0.45
        return 0.05
    if market_type == "Low Temperature":
        if distance <= -2:
            return 1.0
        if distance <= -1:
            return 0.45
        return 0.05
    return 0.0


def stability_score(drift: float | None) -> float:
    if drift is None:
        return 0.5
    return 1.0 - normalize(abs(drift), 0, 4)


def liquidity_score(row: dict[str, Any]) -> float:
    available = [value for value in (row.get("yes_buy_cents"), row.get("no_buy_cents"), row.get("midpoint_cents")) if value is not None]
    if not available:
        return 0.0
    spread_proxy = max(available) - min(available)
    return 1.0 - normalize(spread_proxy, 0, 25)


def volatility_score(drift: float | None) -> float:
    if drift is None:
        return 0.6
    return 1.0 - normalize(abs(drift), 0, 6)


def consistency_score(row: dict[str, Any]) -> float:
    aligned = recommendation(row)
    if aligned in ("YES", "NO"):
        return 1.0
    if row.get("current_price") is not None and row["current_price"] >= 60:
        return 0.45
    return 0.1


def confidence_score(row: dict[str, Any]) -> float:
    # Pre-set deterministic underwriting formula:
    # 30% edge + 20% historical probability + 15% forecast stability
    # + 15% distance from forecast + 10% liquidity + 5% volatility + 5% consistency
    edge_component = normalize((row.get("estimated_edge") or 0.0) * 100, -10, 15)
    historical_component = normalize((row.get("historical_probability") or 0.0) * 100, 50, 95)
    stability_component = stability_score(row.get("forecast_drift"))
    distance_component = distance_score(row.get("distance_from_forecast"), row.get("type", ""))
    liquidity_component = liquidity_score(row)
    volatility_component = volatility_score(row.get("forecast_drift"))
    consistency_component = consistency_score(row)

    score = 100 * (
        0.30 * edge_component
        + 0.20 * historical_component
        + 0.15 * stability_component
        + 0.15 * distance_component
        + 0.10 * liquidity_component
        + 0.05 * volatility_component
        + 0.05 * consistency_component
    )
    if row.get("current_price") is not None:
        score += 6 * price_score(row["current_price"])
    return max(0.0, min(99.0, round(score, 1)))


def signal_strength(score: float) -> str:
    if score >= 85:
        return "VERY HIGH"
    if score >= 72:
        return "HIGH"
    if score >= 58:
        return "MEDIUM"
    return "LOW"


def recommendation(row: dict[str, Any]) -> str:
    price = row["current_price"]
    distance = row["distance_from_forecast"]
    if price is None or distance is None:
        return "WATCH"
    if row["type"] == "High Temperature" and distance >= 2 and price >= 60:
        return "YES"
    if row["type"] == "Low Temperature" and distance <= -2 and price >= 60:
        return "NO"
    return "WATCH"


def summarize_signals(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "No strong weather signals are available. Monitor liquidity, contract clustering, and price discipline."
    leaders = [item for item in signals[:4] if item.get("current_price") is not None]
    if not leaders:
        return "Signal set is thin. Active contracts are showing limited executable pricing."
    fragments = [
        f"{item['city']} {item['type']} {item['contract']} {item['recommendation']} @ {int(item['current_price'])}c ({item['signal_strength']})"
        for item in leaders
    ]
    return "Morning focus: " + "; ".join(fragments) + "."


def generate_signals(market_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    forecasts = infer_forecasts(market_rows)
    signals: list[dict[str, Any]] = []

    for row in market_rows:
        forecast = forecasts.get((row["city"], row["type"]))
        distance = distance_from_forecast(row["contract"], forecast)
        provisional = {
            **row,
            "forecast": forecast,
            "distance_from_forecast": distance,
            "forecast_drift": 0.0,
            "current_price": row["yes_buy_cents"],
        }
        side = recommendation(provisional)
        current_price = row["no_buy_cents"] if side == "NO" else row["yes_buy_cents"]
        implied_probability = (current_price / 100) if current_price is not None else None
        row_signal = {
            **row,
            "forecast": forecast,
            "distance_from_forecast": distance,
            "forecast_drift": 0.0,
            "recommendation": side,
            "recommendation_side": side,
            "current_price": current_price,
        }
        row_signal["historical_probability"] = historical_probability({"implied_probability": implied_probability or 0.0})
        row_signal["implied_probability"] = implied_probability
        row_signal["estimated_edge"] = round(row_signal["historical_probability"] - (row_signal["implied_probability"] or 0.0), 4)
        row_signal["confidence_score"] = confidence_score(row_signal)
        row_signal["signal_strength"] = signal_strength(row_signal["confidence_score"])
        signals.append(row_signal)

    signals.sort(
        key=lambda item: (
            {"VERY HIGH": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(item["signal_strength"], 4),
            -(item["estimated_edge"] or 0),
            -(item["current_price"] or 0),
        )
    )
    for index, signal in enumerate(signals, start=1):
        signal["rank"] = index
    return signals
