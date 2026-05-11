from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config import DATABASE_PATH, DATA_DIR


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS market_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_ts TEXT NOT NULL,
        city TEXT,
        market_ticker TEXT,
        event_ticker TEXT,
        market_type TEXT,
        contract_label TEXT,
        implied_probability REAL,
        yes_buy_cents INTEGER,
        no_buy_cents INTEGER,
        midpoint_cents INTEGER,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_ts TEXT NOT NULL,
        balance_cents INTEGER,
        portfolio_value_cents INTEGER,
        realized_pnl_cents INTEGER,
        open_positions_count INTEGER,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fill_id TEXT UNIQUE,
        order_id TEXT,
        ticker TEXT,
        side TEXT,
        action TEXT,
        count_fp REAL,
        yes_price_dollars REAL,
        no_price_dollars REAL,
        fee_cost REAL,
        created_time TEXT,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_ts TEXT NOT NULL,
        ticker TEXT,
        position_fp REAL,
        market_exposure_dollars REAL,
        realized_pnl_dollars REAL,
        fees_paid_dollars REAL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signal_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_ts TEXT NOT NULL,
        city TEXT,
        market_ticker TEXT,
        rank_value INTEGER,
        signal_strength TEXT,
        recommendation TEXT,
        estimated_edge REAL,
        confidence_score REAL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analytics_cache (
        cache_key TEXT PRIMARY KEY,
        cache_value TEXT NOT NULL,
        updated_ts TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_ts TEXT NOT NULL,
        summary_type TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_settings (
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL,
        updated_ts TEXT NOT NULL
    )
    """,
]


def initialize_database(path: Path = DATABASE_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()


@contextmanager
def connect_db(path: Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    initialize_database(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_setting(key: str, value: str) -> None:
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value, updated_ts)
            VALUES (?, ?, ?)
            ON CONFLICT(setting_key)
            DO UPDATE SET setting_value=excluded.setting_value, updated_ts=excluded.updated_ts
            """,
            (key, value, utc_now_iso()),
        )
        conn.commit()


def get_setting(key: str) -> str | None:
    with connect_db() as conn:
        row = conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
            (key,),
        ).fetchone()
    return row["setting_value"] if row else None


def insert_market_snapshots(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    snapshot_ts = utc_now_iso()
    with connect_db() as conn:
        conn.executemany(
            """
            INSERT INTO market_snapshots (
                snapshot_ts, city, market_ticker, event_ticker, market_type, contract_label,
                implied_probability, yes_buy_cents, no_buy_cents, midpoint_cents, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_ts,
                    row.get("city"),
                    row.get("ticker"),
                    row.get("event_ticker"),
                    row.get("type"),
                    row.get("contract"),
                    row.get("implied_probability"),
                    row.get("yes_buy_cents"),
                    row.get("no_buy_cents"),
                    row.get("midpoint_cents"),
                    json.dumps(row),
                )
                for row in rows
            ],
        )
        conn.commit()


def insert_portfolio_snapshot(balance_payload: dict[str, Any], positions: list[dict[str, Any]]) -> None:
    snapshot_ts = utc_now_iso()
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO portfolio_snapshots (
                snapshot_ts, balance_cents, portfolio_value_cents, realized_pnl_cents,
                open_positions_count, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_ts,
                balance_payload.get("balance"),
                balance_payload.get("portfolio_value"),
                balance_payload.get("realized_pnl"),
                len(positions),
                json.dumps({"balance": balance_payload, "positions": positions}),
            ),
        )
        conn.executemany(
            """
            INSERT INTO positions (
                snapshot_ts, ticker, position_fp, market_exposure_dollars,
                realized_pnl_dollars, fees_paid_dollars, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_ts,
                    item.get("ticker"),
                    item.get("position_fp"),
                    item.get("market_exposure_dollars"),
                    item.get("realized_pnl_dollars"),
                    item.get("fees_paid_dollars"),
                    json.dumps(item),
                )
                for item in positions
            ],
        )
        conn.commit()


def insert_trade_fills(fills: list[dict[str, Any]]) -> None:
    if not fills:
        return
    with connect_db() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO trades (
                fill_id, order_id, ticker, side, action, count_fp,
                yes_price_dollars, no_price_dollars, fee_cost, created_time, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.get("fill_id"),
                    item.get("order_id"),
                    item.get("ticker") or item.get("market_ticker"),
                    item.get("side"),
                    item.get("action"),
                    float(item.get("count_fp") or 0),
                    float(item.get("yes_price_dollars") or 0),
                    float(item.get("no_price_dollars") or 0),
                    float(item.get("fee_cost") or 0),
                    item.get("created_time"),
                    json.dumps(item),
                )
                for item in fills
            ],
        )
        conn.commit()


def insert_signal_snapshots(signals: list[dict[str, Any]]) -> None:
    if not signals:
        return
    snapshot_ts = utc_now_iso()
    with connect_db() as conn:
        conn.executemany(
            """
            INSERT INTO signal_snapshots (
                snapshot_ts, city, market_ticker, rank_value, signal_strength,
                recommendation, estimated_edge, confidence_score, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_ts,
                    item.get("city"),
                    item.get("ticker"),
                    item.get("rank"),
                    item.get("signal_strength"),
                    item.get("recommendation"),
                    item.get("estimated_edge"),
                    item.get("confidence_score"),
                    json.dumps(item),
                )
                for item in signals
            ],
        )
        conn.commit()


def insert_ai_summary(summary_type: str, summary_text: str, payload: dict[str, Any]) -> None:
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO ai_summaries (snapshot_ts, summary_type, summary_text, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (utc_now_iso(), summary_type, summary_text, json.dumps(payload)),
        )
        conn.commit()


def query_dataframe(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
