from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src.kalshi_client import KalshiClient, cents_int_to_dollars, dollars_field, parse_balance
from src.utils import KALSHI_TRANSACTIONS_PATH, TRADE_LOG_PATH, load_market_config


def _market_lookup() -> dict[str, dict]:
    config = load_market_config()
    lookup: dict[str, dict] = {}

    alias_map = {
        "KXHIGHCHI": ("Chicago", "KORD", "High"),
        "KXHIGHDEN": ("Denver", "KDEN", "High"),
        "KXHIGHLAX": ("Los Angeles", "KLAX", "High"),
        "KXHIGHMIA": ("Miami", "KMIA", "High"),
        "KXHIGHNY": ("New York City", "KNYC", "High"),
        "KXHIGHPHIL": ("Philadelphia", "KPHL", "High"),
        "KXHIGHTDC": ("Washington DC", "KDCA", "High"),
        "KXHIGHTHOU": ("Houston", "KIAH", "High"),
        "KXHIGHTLV": ("Las Vegas", "KLAS", "High"),
        "KXHIGHTMIN": ("Minneapolis", "KMSP", "High"),
        "KXHIGHTNOLA": ("New Orleans", "KMSY", "High"),
        "KXHIGHTSATX": ("San Antonio", "KSAT", "High"),
        "KXLOWTDC": ("Washington DC", "KDCA", "Low"),
        "KXLOWTHOU": ("Houston", "KIAH", "Low"),
        "KXLOWTLV": ("Las Vegas", "KLAS", "Low"),
        "KXLOWTPHIL": ("Philadelphia", "KPHL", "Low"),
        "KXLOWTSATX": ("San Antonio", "KSAT", "Low"),
    }

    for row in config.itertuples(index=False):
        high_payload = {
            "market": row.market_name,
            "nws_station": row.nws_station,
            "high_low": "High",
        }
        low_payload = {
            "market": row.market_name,
            "nws_station": row.nws_station,
            "high_low": "Low",
        }
        lookup[row.kalshi_high_series] = high_payload
        lookup[row.kalshi_low_series] = low_payload

    for series, (market, station, high_low) in alias_map.items():
        lookup[series] = {"market": market, "nws_station": station, "high_low": high_low}
    return lookup


def _series_match(ticker: str, lookup: dict[str, dict]) -> dict:
    prefix = ticker.split("-", 1)[0]
    if prefix in lookup:
        return lookup[prefix]
    for series, payload in lookup.items():
        if prefix.startswith(series):
            return payload
    return {"market": "Unknown", "nws_station": "N/A", "high_low": "N/A"}


def _decode_contract_threshold(ticker: str) -> str:
    suffix = ticker.split("-")[-1] if "-" in ticker else ticker
    if suffix.startswith("B"):
        try:
            value = float(suffix[1:])
            low = int(value)
            high = low + 1
            return f"{low}° to {high}°"
        except ValueError:
            return suffix
    if suffix.startswith("T"):
        try:
            threshold = int(float(suffix[1:]))
            return f"{threshold - 1}° or below"
        except ValueError:
            return suffix
    return suffix


def _coerce_money(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_imported_kalshi_transactions(path: str | Path = KALSHI_TRANSACTIONS_PATH) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(csv_path)
    if raw.empty:
        return pd.DataFrame()
    lookup = _market_lookup()
    raw["date_opened"] = pd.to_datetime(raw["open_timestamp"], errors="coerce")
    raw["date_closed"] = pd.to_datetime(raw["close_timestamp"], errors="coerce")
    raw["contracts"] = pd.to_numeric(raw["quantity"], errors="coerce")
    raw["entry_price"] = pd.to_numeric(raw["entry_price_cents"], errors="coerce") / 100
    raw["exit_price"] = pd.to_numeric(raw["exit_price_cents"], errors="coerce") / 100
    raw["fees"] = (
        pd.to_numeric(raw["open_fees_cents"], errors="coerce").fillna(0)
        + pd.to_numeric(raw["close_fees_cents"], errors="coerce").fillna(0)
    ) / 100
    raw["gross_pnl"] = pd.to_numeric(raw["realized_pnl_without_fees_cents"], errors="coerce") / 100
    raw["net_pnl"] = pd.to_numeric(raw["realized_pnl_with_fees_cents"], errors="coerce") / 100

    records: list[dict] = []
    for idx, row in raw.iterrows():
        meta = _series_match(str(row.get("market_ticker") or ""), lookup)
        invested = float((row.get("entry_price") or 0) * (row.get("contracts") or 0) + (row.get("fees") or 0))
        net_pnl = float(row.get("net_pnl") or 0)
        records.append(
            {
                "trade_id": f"CSV-{idx + 1:04d}",
                "date_opened": row.get("date_opened"),
                "date_closed": row.get("date_closed"),
                "market": meta["market"],
                "nws_station": meta["nws_station"],
                "high_low": meta["high_low"],
                "contract_threshold": _decode_contract_threshold(str(row.get("market_ticker") or "")),
                "direction": str(row.get("side") or "").upper(),
                "entry_price": row.get("entry_price"),
                "exit_price": row.get("exit_price"),
                "contracts": row.get("contracts"),
                "fees": row.get("fees"),
                "gross_pnl": row.get("gross_pnl"),
                "net_pnl": net_pnl,
                "roi": (net_pnl / invested) if invested else None,
                "status": "Closed",
                "result": "Win" if net_pnl > 0 else "Loss" if net_pnl < 0 else "Flat",
                "thesis": "",
                "forecast_at_entry": None,
                "forecast_at_exit": None,
                "settlement_value": row.get("exit_price"),
                "notes": "Imported from Kalshi transactions CSV",
                "market_ticker": row.get("market_ticker"),
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        df["close_day"] = df["date_closed"].dt.date
    return df


@st.cache_data(ttl=300)
def load_trade_log(path: str | Path = TRADE_LOG_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    for column in ["date_opened", "date_closed"]:
        if column in df.columns:
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
    df = _coerce_money(df, numeric_columns)
    if "fees" in df.columns:
        df["fees"] = df["fees"].fillna(df["contracts"].fillna(0) * 0.01)
    if "status" in df.columns:
        df["status"] = df.apply(
            lambda row: "Open" if pd.isna(row.get("date_closed")) else str(row.get("status") or "Closed"),
            axis=1,
        )
    df["close_day"] = df["date_closed"].dt.date if "date_closed" in df.columns else pd.Series(dtype="object")
    return df


@st.cache_data(ttl=60, show_spinner=False)
def load_kalshi_account_snapshot() -> dict:
    client = KalshiClient()
    snapshot = {
        "connected": False,
        "balance": None,
        "portfolio_value": None,
        "positions_value": None,
        "positions": pd.DataFrame(),
        "settlements": pd.DataFrame(),
        "error": None,
        "source": "kalshi",
    }
    if not client.authenticated:
        snapshot["error"] = "Kalshi credentials missing."
        return snapshot

    lookup = _market_lookup()
    try:
        balance_payload = client.get_balance()
        positions_payload = client.get_positions()
        settlements_payload = client.get_settlements(limit=500)
        settlements = settlements_payload.get("settlements", [])
        cursor = settlements_payload.get("cursor")
        while cursor and len(settlements) < 1500:
            page = client.get_settlements(limit=500, cursor=cursor)
            settlements.extend(page.get("settlements", []))
            cursor = page.get("cursor")
    except Exception as exc:
        snapshot["error"] = str(exc)
        return snapshot

    balance = parse_balance(balance_payload)
    positions_value = parse_balance(
        {
            "portfolio_value": balance_payload.get("portfolio_value"),
            "portfolio_value_dollars": balance_payload.get("portfolio_value_dollars"),
        }
    )
    positions_market_values: list[float] = []

    positions_rows: list[dict] = []
    for row in positions_payload.get("market_positions", []):
        ticker = str(row.get("ticker") or "")
        meta = _series_match(ticker, lookup)
        contracts = pd.to_numeric(row.get("position_fp"), errors="coerce")
        contract_value = float(contracts) if pd.notna(contracts) else 0.0
        exposure = dollars_field(row.get("market_exposure_dollars"))
        realized = dollars_field(row.get("realized_pnl_dollars"))
        fees = dollars_field(row.get("fees_paid_dollars"))
        market_value = None
        for key in ("market_value_dollars", "current_value_dollars", "position_value_dollars", "value_dollars"):
            market_value = dollars_field(row.get(key))
            if market_value is not None:
                break
        if market_value is not None:
            positions_market_values.append(market_value)
        if abs(contract_value) < 1e-9:
            continue
        positions_rows.append(
            {
                "trade_id": f"OPEN-{ticker}",
                "date_opened": pd.NaT,
                "date_closed": pd.NaT,
                "market": meta["market"],
                "nws_station": meta["nws_station"],
                "high_low": meta["high_low"],
                "contract_threshold": _decode_contract_threshold(ticker),
                "direction": "YES" if contract_value > 0 else "NO",
                "entry_price": None,
                "exit_price": None,
                "contracts": abs(contract_value),
                "fees": fees,
                "gross_pnl": realized,
                "net_pnl": realized,
                "roi": None,
                "status": "Open",
                "result": "Open",
                "thesis": "",
                "forecast_at_entry": None,
                "forecast_at_exit": None,
                "settlement_value": None,
                "notes": "Live Kalshi position",
                "market_ticker": ticker,
                "close_day": pd.NaT,
                "open_exposure": exposure,
                "market_value": market_value,
            }
        )

    if positions_market_values:
        positions_value = round(sum(positions_market_values), 2)
    portfolio_value = (balance or 0.0) + (positions_value or 0.0) if balance is not None or positions_value is not None else None

    settlements_rows: list[dict] = []
    for row in settlements:
        ticker = str(row.get("ticker") or "")
        meta = _series_match(ticker, lookup)
        yes_count = pd.to_numeric(row.get("yes_count_fp"), errors="coerce")
        no_count = pd.to_numeric(row.get("no_count_fp"), errors="coerce")
        contracts = yes_count if pd.notna(yes_count) and yes_count > 0 else no_count
        direction = "YES" if pd.notna(yes_count) and yes_count > 0 else "NO"
        total_cost = (dollars_field(row.get("yes_total_cost_dollars")) or 0.0) + (
            dollars_field(row.get("no_total_cost_dollars")) or 0.0
        )
        revenue = cents_int_to_dollars(row.get("revenue")) or 0.0
        fees = dollars_field(row.get("fee_cost")) or 0.0
        net_pnl = revenue - total_cost - fees
        settled_time = pd.to_datetime(row.get("settled_time"), errors="coerce")
        invested = total_cost + fees
        settlements_rows.append(
            {
                "trade_id": f"SETTLED-{ticker}-{settled_time.date() if pd.notna(settled_time) else 'na'}",
                "date_opened": pd.NaT,
                "date_closed": settled_time,
                "market": meta["market"],
                "nws_station": meta["nws_station"],
                "high_low": meta["high_low"],
                "contract_threshold": _decode_contract_threshold(ticker),
                "direction": direction,
                "entry_price": round(total_cost / contracts, 4) if pd.notna(contracts) and contracts else None,
                "exit_price": round(revenue / contracts, 4) if pd.notna(contracts) and contracts else None,
                "contracts": float(contracts) if pd.notna(contracts) else None,
                "fees": fees,
                "gross_pnl": revenue - total_cost,
                "net_pnl": net_pnl,
                "roi": (net_pnl / invested) if invested else None,
                "status": "Closed",
                "result": "Win" if net_pnl > 0 else "Loss" if net_pnl < 0 else "Flat",
                "thesis": "",
                "forecast_at_entry": None,
                "forecast_at_exit": None,
                "settlement_value": cents_int_to_dollars(row.get("value")),
                "notes": "Live Kalshi settlement",
                "market_ticker": ticker,
                "close_day": settled_time.date() if pd.notna(settled_time) else None,
            }
        )

    snapshot["connected"] = True
    snapshot["balance"] = balance
    snapshot["positions_value"] = positions_value
    snapshot["portfolio_value"] = portfolio_value
    snapshot["positions"] = pd.DataFrame(positions_rows)
    snapshot["settlements"] = pd.DataFrame(settlements_rows)
    return snapshot


def get_effective_trade_log() -> tuple[pd.DataFrame, str]:
    imported = load_imported_kalshi_transactions()
    if not imported.empty:
        live = load_kalshi_account_snapshot()
        positions = live.get("positions", pd.DataFrame())
        frames = [df for df in [positions, imported] if not df.empty]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return combined, "kalshi_csv"
    live = load_kalshi_account_snapshot()
    settlements = live.get("settlements", pd.DataFrame())
    positions = live.get("positions", pd.DataFrame())
    if live.get("connected") and (not settlements.empty or not positions.empty):
        frames = [df for df in [positions, settlements] if not df.empty]
        combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return combined, "kalshi"
    return load_trade_log(), "csv"


def get_portfolio_summary() -> dict[str, float | None | str]:
    live = load_kalshi_account_snapshot()
    return {
        "source": "kalshi" if live.get("connected") else "csv",
        "balance": live.get("balance"),
        "positions_value": live.get("positions_value"),
        "portfolio_value": live.get("portfolio_value"),
        "error": live.get("error"),
    }


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
        return pd.DataFrame(
            columns=["Date Closed", "Market", "Type", "Direction", "Entry Price", "Exit Price", "Contracts", "Fees", "Net PNL", "ROI", "Result"]
        )
    recent = df.sort_values(["date_closed", "date_opened"], ascending=False).head(limit).copy()
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
        )
        .reset_index()
    )
    open_rows = df[df["status"].str.lower() == "open"].copy()
    if not open_rows.empty and "open_exposure" in open_rows.columns:
        exposure = open_rows.groupby("market", as_index=False)["open_exposure"].sum()
        grouped = grouped.merge(exposure, on="market", how="left")
        grouped["open_exposure"] = grouped["open_exposure"].fillna(0.0)
    else:
        grouped["open_exposure"] = 0.0
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


def get_recent_may_performance(df: pd.DataFrame, days: int = 14) -> pd.DataFrame:
    if df.empty or "date_closed" not in df.columns:
        return pd.DataFrame()
    cutoff = datetime.utcnow() - timedelta(days=days)
    return df[df["date_closed"].fillna(pd.Timestamp.min) >= cutoff].copy()
