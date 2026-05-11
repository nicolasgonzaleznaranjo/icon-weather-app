from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskSettings:
    trading_enabled: bool
    authenticated: bool
    quantity: int
    max_slippage_cents: int
    max_exposure_per_contract: float
    max_total_exposure: float
    max_daily_loss: float


@dataclass
class RiskResult:
    allowed: bool
    reason: str = ""


def check_order_risk(
    *,
    settings: RiskSettings,
    price_cents: int | None,
    displayed_price_cents: int | None,
    current_contract_exposure: float,
    total_exposure: float,
    today_pnl: float | None,
) -> RiskResult:
    if not settings.trading_enabled:
        return RiskResult(False, "Trading toggle is off.")
    if not settings.authenticated:
        return RiskResult(False, "Demo API credentials are unavailable or failed authentication.")
    if settings.quantity <= 0:
        return RiskResult(False, "Quantity must be greater than zero.")
    if price_cents is None:
        return RiskResult(False, "No executable price is available.")
    if displayed_price_cents is not None:
        move = abs(int(price_cents) - int(displayed_price_cents))
        if move > settings.max_slippage_cents:
            return RiskResult(False, f"Price moved {move}c, above max slippage.")
    order_exposure = settings.quantity * int(price_cents) / 100
    if current_contract_exposure + order_exposure > settings.max_exposure_per_contract:
        return RiskResult(False, "Max exposure per contract would be exceeded.")
    if total_exposure + order_exposure > settings.max_total_exposure:
        return RiskResult(False, "Max total exposure would be exceeded.")
    if today_pnl is not None and today_pnl <= -abs(settings.max_daily_loss):
        return RiskResult(False, "Max daily loss has been reached.")
    return RiskResult(True)
