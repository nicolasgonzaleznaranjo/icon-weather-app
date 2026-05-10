from __future__ import annotations

from datetime import date, datetime
import math
import re
from typing import Any

import pandas as pd

from src.data_models import ContractSpec


def parse_event_date(ticker: str) -> date | None:
    match = re.search(r"-(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})", ticker, flags=re.IGNORECASE)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return datetime.strptime(f"20{year}-{month.title()}-{day}", "%Y-%b-%d").date()
    except ValueError:
        return None


def extract_contract_label(title: str) -> str:
    title = title.replace("Will the maximum temperature be", "").replace("Will the minimum temperature be", "").strip(" ?")
    title = title.replace("  ", " ")
    if " on " in title:
        title = title.split(" on ", 1)[0]
    return title.strip()


def parse_contract_spec(label: str) -> ContractSpec:
    less_than = re.search(r"<\s*(\d+(?:\.\d+)?)", label)
    if less_than:
        value = float(less_than.group(1))
        return ContractSpec(label, "less_than", None, value, None, value)

    greater_than = re.search(r">\s*(\d+(?:\.\d+)?)", label)
    if greater_than:
        value = float(greater_than.group(1))
        return ContractSpec(label, "greater_than", value, None, value, None)

    band = re.search(r"(\d+(?:\.\d+)?)\D+(\d+(?:\.\d+)?)", label)
    if band:
        low = float(band.group(1))
        high = float(band.group(2))
        return ContractSpec(label, "range", low, high, low, high)

    single = re.search(r"(\d+(?:\.\d+)?)", label)
    if single:
        value = float(single.group(1))
        return ContractSpec(label, "single", value, value, value, value)

    return ContractSpec(label, "unknown", None, None, None, None)


def modeled_yes_probability(contract: ContractSpec, forecast_value: float | None) -> float | None:
    if forecast_value is None:
        return None
    if contract.kind == "greater_than" and contract.display_lower is not None:
        threshold = contract.display_lower
        return 1 / (1 + math.exp((threshold - forecast_value) / 1.8))
    if contract.kind == "less_than" and contract.display_upper is not None:
        threshold = contract.display_upper
        return 1 / (1 + math.exp((forecast_value - threshold) / 1.8))
    if contract.kind in {"range", "single"} and contract.center is not None:
        distance = abs(contract.center - forecast_value)
        return max(0.01, min(0.98, 0.92 * math.exp(-((distance / 2.35) ** 2))))
    return None


def contract_distance(contract: ContractSpec, forecast_value: float | None) -> float | None:
    if forecast_value is None:
        return None
    if contract.kind == "range" and contract.center is not None:
        return contract.center - forecast_value
    if contract.kind == "single" and contract.center is not None:
        return contract.center - forecast_value
    if contract.kind == "greater_than" and contract.display_lower is not None:
        return contract.display_lower - forecast_value
    if contract.kind == "less_than" and contract.display_upper is not None:
        return contract.display_upper - forecast_value
    return None


def market_maturity_label(close_time: str | None) -> tuple[str | None, float | None]:
    if not close_time:
        return None, None
    close_dt = datetime.fromisoformat(close_time.replace("Z", "+00:00"))
    hours = (close_dt - datetime.now(close_dt.tzinfo)).total_seconds() / 3600
    if hours <= 0:
        return "Settling / closed", hours
    if hours < 2:
        return "Very mature", hours
    if hours < 5:
        return "Late session", hours
    if hours < 10:
        return "Mid session", hours
    return "Early window", hours


def evaluate_contract(
    *,
    market_type: str,
    contract_label: str,
    forecast_value: float | None,
    yes_price: float | None,
    no_price: float | None,
    volume: float | None,
    liquidity: float | None,
    close_time: str | None,
) -> dict[str, Any]:
    spec = parse_contract_spec(contract_label)
    yes_prob = modeled_yes_probability(spec, forecast_value)
    implied_yes = (yes_price / 100) if yes_price is not None else None
    implied_no = (no_price / 100) if no_price is not None else None
    yes_edge = (yes_prob - implied_yes) if yes_prob is not None and implied_yes is not None else None
    no_edge = ((1 - yes_prob) - implied_no) if yes_prob is not None and implied_no is not None else None
    direction = "Avoid"
    best_edge = None
    chosen_price = None

    if yes_edge is not None and (best_edge is None or yes_edge > best_edge):
        best_edge = yes_edge
        direction = "YES"
        chosen_price = yes_price
    if no_edge is not None and (best_edge is None or no_edge > best_edge):
        best_edge = no_edge
        direction = "NO"
        chosen_price = no_price

    distance = contract_distance(spec, forecast_value)
    maturity_label, hours_to_settlement = market_maturity_label(close_time)
    liquidity_ok = (volume or 0) >= 50 or (liquidity or 0) >= 100
    price_ok = chosen_price is not None and 5 <= chosen_price <= 95

    if best_edge is None or not price_ok:
        status = "Avoid"
    elif best_edge >= 0.12 and liquidity_ok and (hours_to_settlement is None or hours_to_settlement > 1.5):
        status = "Strong candidate"
    elif best_edge >= 0.07 and (hours_to_settlement is None or hours_to_settlement > 1):
        status = "Tradable"
    elif best_edge >= 0.03:
        status = "Watch"
    else:
        status = "Avoid"

    note_parts = []
    if best_edge is not None:
        note_parts.append(f"Model edge {best_edge:+.1%}")
    if distance is not None:
        note_parts.append(f"Distance {distance:+.1f}°")
    if liquidity_ok:
        note_parts.append("Liquidity present")
    else:
        note_parts.append("Thin liquidity")
    if maturity_label:
        note_parts.append(maturity_label)

    return {
        "contract_label": spec.raw_label,
        "distance_from_forecast": distance,
        "implied_probability": implied_yes,
        "modeled_yes_probability": yes_prob,
        "yes_edge": yes_edge,
        "no_edge": no_edge,
        "suggested_direction": direction,
        "edge": best_edge,
        "status": status,
        "note": " • ".join(note_parts),
        "hours_to_settlement": hours_to_settlement,
        "maturity_label": maturity_label,
    }


def sort_monitor_rows(df: pd.DataFrame) -> pd.DataFrame:
    order = {"Strong candidate": 0, "Tradable": 1, "Watch": 2, "Avoid": 3}
    if df.empty or "Status" not in df.columns:
        return df
    sorted_df = df.copy()
    sorted_df["status_order"] = sorted_df["Status"].map(order).fillna(4)
    sorted_df = sorted_df.sort_values(
        [
            "status_order",
            "Edge" if "Edge" in sorted_df.columns else "status_order",
            "Market" if "Market" in sorted_df.columns else "status_order",
            "Distance" if "Distance" in sorted_df.columns else "status_order",
        ],
        ascending=[True, False, True, True],
        na_position="last",
    )
    return sorted_df.drop(columns=["status_order"])
