from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import TRADE_LOG_PATH


FIELDS = [
    "timestamp",
    "action",
    "market_ticker",
    "city",
    "type",
    "contract_temp",
    "side",
    "price",
    "quantity",
    "status",
    "order_id",
    "error_message",
]


class TradeLogger:
    def __init__(self, path: Path = TRADE_LOG_PATH):
        self.path = path
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_log (
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    market_ticker TEXT,
                    city TEXT,
                    type TEXT,
                    contract_temp TEXT,
                    side TEXT,
                    price INTEGER,
                    quantity INTEGER,
                    status TEXT,
                    order_id TEXT,
                    error_message TEXT
                )
                """
            )

    def log(self, **values: Any) -> None:
        record = {field: values.get(field) for field in FIELDS}
        record["timestamp"] = record["timestamp"] or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO trade_log ({','.join(FIELDS)}) VALUES ({','.join(['?'] * len(FIELDS))})",
                [record[field] for field in FIELDS],
            )
