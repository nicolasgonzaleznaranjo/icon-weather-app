from __future__ import annotations

import base64
import datetime as dt
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from config import get_kalshi_credentials


@dataclass
class KalshiResponse:
    ok: bool
    data: dict[str, Any]
    error: str | None = None


def _load_private_key(private_key_pem: str):
    return serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )


def _sign_request(private_key_pem: str, timestamp: str, method: str, full_path: str) -> str:
    private_key = _load_private_key(private_key_pem)
    message = f"{timestamp}{method.upper()}{full_path.split('?')[0]}".encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _price_to_cents(value: Any) -> int:
    raw = float(value)
    if 0 <= raw <= 1:
        raw *= 100
    return int(round(raw))


def _first_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return _price_to_cents(value)
    except (TypeError, ValueError):
        return None


def best_bid_cents(levels: Any) -> int | None:
    if not levels:
        return None
    prices: list[int] = []
    for level in levels:
        if isinstance(level, dict):
            raw_price = level.get("price") or level.get("yes_price") or level.get("no_price")
        elif isinstance(level, (list, tuple)) and level:
            raw_price = level[0]
        else:
            raw_price = None
        try:
            prices.append(_price_to_cents(raw_price))
        except (TypeError, ValueError):
            continue
    return max(prices) if prices else None


def compute_buy_prices(orderbook: dict[str, Any], market: dict[str, Any] | None = None) -> dict[str, int | None]:
    book = orderbook.get("orderbook") or orderbook.get("orderbook_fp") or orderbook
    source = market or {}

    yes_bid = (
        _first_int(book.get("yes_bid"))
        or best_bid_cents(book.get("yes") or book.get("yes_bids"))
        or best_bid_cents(book.get("yes_dollars"))
        or _first_int(source.get("yes_bid"))
    )
    no_bid = (
        _first_int(book.get("no_bid"))
        or best_bid_cents(book.get("no") or book.get("no_bids"))
        or best_bid_cents(book.get("no_dollars"))
        or _first_int(source.get("no_bid"))
    )
    yes_ask = _first_int(book.get("yes_ask") or book.get("yes_ask_price") or source.get("yes_ask"))
    no_ask = _first_int(book.get("no_ask") or book.get("no_ask_price") or source.get("no_ask"))

    return {
        "yes_buy_cents": yes_ask if yes_ask is not None else 100 - no_bid if no_bid is not None else None,
        "no_buy_cents": no_ask if no_ask is not None else 100 - yes_bid if yes_bid is not None else None,
        "best_yes_bid_cents": yes_bid,
        "best_no_bid_cents": no_bid,
        "midpoint_cents": midpoint_cents(yes_bid, no_bid, yes_ask, no_ask),
    }


def midpoint_cents(
    yes_bid: int | None,
    no_bid: int | None,
    yes_ask: int | None,
    no_ask: int | None,
) -> int | None:
    values = [value for value in (yes_bid, 100 - no_bid if no_bid is not None else None, yes_ask, 100 - no_ask if no_ask is not None else None) if value is not None]
    if not values:
        return None
    return int(round(sum(values) / len(values)))


class KalshiClient:
    def __init__(self):
        self.credentials = get_kalshi_credentials()
        self.base_url = self.credentials.base_url
        self.auth_failed = False
        self.last_error: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.credentials.available and not self.auth_failed

    def _headers(self) -> dict[str, str]:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        headers = self._headers()
        if not self.credentials.available:
            return headers

        try:
            timestamp = str(int(dt.datetime.now(dt.UTC).timestamp() * 1000))
            full_path = urlparse(self.base_url + path).path
            signature = _sign_request(
                self.credentials.private_key or "",
                timestamp,
                method,
                full_path,
            )
            headers.update(
                {
                    "KALSHI-ACCESS-KEY": self.credentials.api_key_id or "",
                    "KALSHI-ACCESS-TIMESTAMP": timestamp,
                    "KALSHI-ACCESS-SIGNATURE": signature,
                }
            )
        except Exception as exc:
            self.auth_failed = True
            self.last_error = f"Could not load Kalshi private key: {exc}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        auth_required: bool = False,
    ) -> KalshiResponse:
        if auth_required and not self.credentials.available:
            return KalshiResponse(False, {}, "Kalshi API credentials missing.")

        headers = self._auth_headers(method, path) if auth_required else self._headers()
        if auth_required and self.auth_failed:
            return KalshiResponse(False, {}, self.last_error or "Kalshi authentication failed.")

        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                data=json.dumps(payload) if payload is not None else None,
                headers=headers,
                timeout=15,
            )
            if response.status_code in (401, 403):
                self.auth_failed = True
            response.raise_for_status()
            return KalshiResponse(True, response.json() if response.content else {})
        except Exception as exc:
            self.last_error = str(exc)
            return KalshiResponse(False, {}, str(exc))

    def get_markets(self, **params) -> KalshiResponse:
        defaults = {"limit": 100}
        defaults.update({k: v for k, v in params.items() if v is not None})
        return self._request("GET", "/markets", params=defaults)

    def get_market_orderbook(self, ticker: str) -> KalshiResponse:
        return self._request("GET", f"/markets/{ticker}/orderbook")

    def get_balance(self) -> KalshiResponse:
        return self._request("GET", "/portfolio/balance", auth_required=True)

    def get_positions(self) -> KalshiResponse:
        return self._request("GET", "/portfolio/positions", auth_required=True)

    def get_fills(self, limit: int = 200) -> KalshiResponse:
        return self._request("GET", "/portfolio/fills", params={"limit": limit}, auth_required=True)
