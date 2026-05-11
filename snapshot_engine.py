from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import APP_TIMEZONE
from database import (
    get_setting,
    insert_ai_summary,
    insert_market_snapshots,
    insert_portfolio_snapshot,
    insert_signal_snapshots,
    insert_trade_fills,
    upsert_setting,
)


def snapshot_interval_minutes(now: datetime) -> int:
    local = now.astimezone(ZoneInfo(APP_TIMEZONE))
    start = local.replace(hour=5, minute=30, second=0, microsecond=0)
    end = local.replace(hour=10, minute=0, second=0, microsecond=0)
    return 5 if start <= local <= end else 30


def should_run_snapshot(now: datetime) -> bool:
    last_run = get_setting("last_snapshot_ts")
    if not last_run:
        return True
    try:
        previous = datetime.fromisoformat(last_run)
    except ValueError:
        return True
    elapsed_minutes = (now - previous).total_seconds() / 60
    return elapsed_minutes >= snapshot_interval_minutes(now)


def maybe_snapshot(
    *,
    now: datetime,
    market_rows: list[dict],
    signal_rows: list[dict],
    balance_payload: dict,
    position_rows: list[dict],
    fills: list[dict],
    summary_text: str,
) -> bool:
    if not should_run_snapshot(now):
        return False
    insert_market_snapshots(market_rows)
    insert_signal_snapshots(signal_rows)
    insert_portfolio_snapshot(balance_payload, position_rows)
    insert_trade_fills(fills)
    if summary_text:
        insert_ai_summary("daily_summary", summary_text, {"signals": signal_rows[:10]})
    upsert_setting("last_snapshot_ts", now.isoformat())
    return True
