from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.utils import TRADE_LOG_PATH


@st.cache_data(ttl=300)
def load_trade_log(path: str | Path = TRADE_LOG_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    for column in ["date_opened", "date_closed"]:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    numeric_columns = [
        "entry_price",
        "exit_price",
        "contracts",
        "fees",
        "gross_pnl",
        "net_pnl",
        "roi",
        "forecast_at_entry",
        "forecast_at_exit",
        "settlement_value",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["fees"] = df["fees"].fillna(df["contracts"].fillna(0) * 0.01)
    df["close_day"] = df["date_closed"].dt.date
    return df


def compute_trade_kpis(df: pd.DataFrame) -> dict[str, float]:
    closed = df[df["status"].str.lower() != "open"].copy() if not df.empty else df
    pnl_series = closed["net_pnl"].fillna(0) if not closed.empty else pd.Series(dtype=float)
    winners = pnl_series[pnl_series > 0]
    losers = pnl_series[pnl_series < 0]
    invested = (closed["entry_price"].fillna(0) * closed["contracts"].fillna(0) + closed["fees"].fillna(0)).sum()
    cumulative = pnl_series.cumsum()
    drawdown = cumulative - cumulative.cummax()
    gross_profit = winners.sum()
    gross_loss = abs(losers.sum())
    return {
        "total_pnl": float(pnl_series.sum()) if not pnl_series.empty else 0.0,
        "total_trades": int(len(closed)),
        "win_rate": float((pnl_series > 0).mean()) if not pnl_series.empty else 0.0,
        "roi_total": float(pnl_series.sum() / invested) if invested else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else (gross_profit if gross_profit else 0.0),
        "average_win": float(winners.mean()) if not winners.empty else 0.0,
        "average_loss": float(losers.mean()) if not losers.empty else 0.0,
        "largest_win": float(winners.max()) if not winners.empty else 0.0,
        "largest_loss": float(losers.min()) if not losers.empty else 0.0,
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
    }


def recent_trades_table(df: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Date Closed", "Market", "Type", "Direction", "Entry Price", "Exit Price", "Contracts", "Fees", "Net PNL", "ROI", "Result"])
    recent = df.sort_values("date_closed", ascending=False).head(limit).copy()
    recent["ROI"] = recent["roi"].fillna(0) * 100
    return recent.rename(
        columns={
            "date_closed": "Date Closed",
            "market": "Market",
            "high_low": "Type",
            "direction": "Direction",
            "entry_price": "Entry Price",
            "exit_price": "Exit Price",
            "contracts": "Contracts",
            "fees": "Fees",
            "net_pnl": "Net PNL",
            "result": "Result",
        }
    )[["Date Closed", "Market", "Type", "Direction", "Entry Price", "Exit Price", "Contracts", "Fees", "Net PNL", "ROI", "Result"]]


def get_market_performance(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["market", "net_pnl", "total_trades", "win_rate", "open_exposure"])
    grouped = (
        df.groupby("market", dropna=False)
        .agg(
            net_pnl=("net_pnl", "sum"),
            total_trades=("trade_id", "count"),
            win_rate=("net_pnl", lambda s: (s > 0).mean()),
            open_exposure=("entry_price", lambda s: 0.0),
        )
        .reset_index()
    )
    open_rows = df[df["status"].str.lower() == "open"].copy()
    if not open_rows.empty:
        open_rows["open_exposure"] = open_rows["entry_price"].fillna(0) * open_rows["contracts"].fillna(0)
        exposure = open_rows.groupby("market", as_index=False)["open_exposure"].sum()
        grouped = grouped.drop(columns=["open_exposure"]).merge(exposure, on="market", how="left")
        grouped["open_exposure"] = grouped["open_exposure"].fillna(0.0)
    return grouped


def get_best_worst_days(df: pd.DataFrame):
    if df.empty:
        return None, None
    daily = df.dropna(subset=["close_day"]).groupby("close_day", as_index=False)["net_pnl"].sum()
    if daily.empty:
        return None, None
    best = daily.sort_values("net_pnl", ascending=False).iloc[0].to_dict()
    worst = daily.sort_values("net_pnl", ascending=True).iloc[0].to_dict()
    return best, worst
