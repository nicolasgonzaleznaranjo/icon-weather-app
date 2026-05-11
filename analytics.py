from __future__ import annotations

from collections import defaultdict

import pandas as pd

from database import query_dataframe


def latest_equity_curve() -> pd.DataFrame:
    rows = query_dataframe(
        """
        SELECT snapshot_ts, portfolio_value_cents, balance_cents
        FROM portfolio_snapshots
        ORDER BY snapshot_ts
        """
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["equity"] = (df["portfolio_value_cents"].fillna(0) + df["balance_cents"].fillna(0)) / 100
    return df


def latest_signal_history() -> pd.DataFrame:
    return pd.DataFrame(
        query_dataframe(
            """
            SELECT snapshot_ts, city, market_ticker, rank_value, signal_strength,
                   estimated_edge, confidence_score
            FROM signal_snapshots
            ORDER BY snapshot_ts DESC
            LIMIT 500
            """
        )
    )


def market_snapshot_history() -> pd.DataFrame:
    return pd.DataFrame(
        query_dataframe(
            """
            SELECT snapshot_ts, city, market_type, contract_label, implied_probability, midpoint_cents
            FROM market_snapshots
            ORDER BY snapshot_ts DESC
            LIMIT 2000
            """
        )
    )


def exposure_by_city(position_rows: list[dict]) -> pd.DataFrame:
    bucket = defaultdict(float)
    for row in position_rows:
        bucket[row.get("city", "Unknown")] += row.get("market_exposure_dollars", 0.0)
    return pd.DataFrame({"city": list(bucket.keys()), "exposure": list(bucket.values())})
