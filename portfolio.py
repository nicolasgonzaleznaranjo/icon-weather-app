from __future__ import annotations

from typing import Any


def cents_to_dollars(value: int | float | None) -> float | None:
    if value is None:
        return None
    return float(value) / 100


def dollars_string_to_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def normalize_positions(raw_positions: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    positions = raw_positions.get("market_positions") if isinstance(raw_positions, dict) else raw_positions
    positions = positions or []
    normalized: list[dict[str, Any]] = []
    for item in positions:
        normalized.append(
            {
                "ticker": item.get("ticker"),
                "position_fp": float(item.get("position_fp") or 0),
                "market_exposure_dollars": dollars_string_to_float(item.get("market_exposure_dollars")),
                "realized_pnl_dollars": dollars_string_to_float(item.get("realized_pnl_dollars")),
                "fees_paid_dollars": dollars_string_to_float(item.get("fees_paid_dollars")),
                "resting_orders_count": int(item.get("resting_orders_count") or 0),
                "raw": item,
            }
        )
    return normalized


def portfolio_summary(balance_payload: dict[str, Any], positions: list[dict[str, Any]], fills: list[dict[str, Any]]) -> dict[str, float]:
    realized = sum(item.get("realized_pnl_dollars", 0.0) for item in positions)
    open_risk = sum(item.get("market_exposure_dollars", 0.0) for item in positions)
    gross_profit = sum(float(fill.get("yes_price_dollars") or 0) for fill in fills if fill.get("action") == "sell")
    gross_loss = sum(float(fill.get("yes_price_dollars") or 0) for fill in fills if fill.get("action") == "buy")
    win_rate = 0.0
    if fills:
        wins = sum(1 for fill in fills if float(fill.get("yes_price_dollars") or 0) > 0.5)
        win_rate = wins / len(fills)
    return {
        "cash_balance": cents_to_dollars(balance_payload.get("balance")) or 0.0,
        "portfolio_value": cents_to_dollars(balance_payload.get("portfolio_value")) or 0.0,
        "realized_pnl": realized,
        "open_risk": open_risk,
        "contracts_open": sum(item.get("position_fp", 0.0) for item in positions),
        "win_rate": win_rate,
        "profit_factor": (gross_profit / gross_loss) if gross_loss else 0.0,
    }
