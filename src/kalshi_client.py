from __future__ import annotations

import base64
import datetime as dt
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
import streamlit as st
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from src.utils import USER_AGENT, safe_float


KALSHI_PRODUCTION_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_DEMO_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"


@dataclass(frozen=True)
class KalshiCredentials:
    environment: str
    base_url: str
    api_key_id: str | None
    private_key: str | None

    @property
    def available(self) -> bool:
        return bool(self.api_key_id and self.private_key)


def _secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        result = st.secrets.get(name)
        return str(result) if result else None
    except Exception:
        return None


def get_credentials() -> KalshiCredentials:
    environment = (_secret("KALSHI_ENVIRONMENT") or "production").lower()
    api_key_id = _secret("KALSHI_API_KEY_ID") or _secret("KALSHI_DEMO_API_KEY_ID")
    private_key = _secret("KALSHI_PRIVATE_KEY") or _secret("KALSHI_DEMO_PRIVATE_KEY")
    if private_key:
        private_key = normalize_private_key(private_key)
    explicit_base = _secret("KALSHI_API_BASE_URL")
    base_url = (
        explicit_base.rstrip("/")
        if explicit_base
        else KALSHI_DEMO_BASE_URL
        if environment == "demo"
        else KALSHI_PRODUCTION_BASE_URL
    )
    return KalshiCredentials(environment, base_url, api_key_id, private_key)


def normalize_private_key(value: str) -> str:
    key = value.replace("\\n", "\n").strip().strip('"').strip("'").strip()
    if "BEGIN" in key:
        return key
    return f"-----BEGIN RSA PRIVATE KEY-----\n{key}\n-----END RSA PRIVATE KEY-----"


def _load_private_key(private_key_pem: str):
    return serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)


def _sign_request(private_key_pem: str, timestamp: str, method: str, path: str) -> str:
    signature = _load_private_key(private_key_pem).sign(
        f"{timestamp}{method.upper()}{path}".encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def price_to_cents(value: Any) -> float | None:
    number = safe_float(value)
    if number is None:
        return None
    if 0 <= number <= 1:
        return round(number * 100, 2)
    return round(number, 2)


def compute_yes_no_prices(market: dict[str, Any]) -> dict[str, float | None]:
    yes_ask = price_to_cents(market.get("yes_ask_dollars") or market.get("yes_ask"))
    no_ask = price_to_cents(market.get("no_ask_dollars") or market.get("no_ask"))
    yes_bid = price_to_cents(market.get("yes_bid_dollars") or market.get("yes_bid"))
    no_bid = price_to_cents(market.get("no_bid_dollars") or market.get("no_bid"))
    if yes_ask is None and no_bid is not None:
        yes_ask = round(100 - no_bid, 2)
    if no_ask is None and yes_bid is not None:
        no_ask = round(100 - yes_bid, 2)
    last_price = price_to_cents(market.get("last_price_dollars") or market.get("last_trade_price"))
    return {
        "yes_price": yes_ask,
        "no_price": no_ask,
        "yes_bid": yes_bid,
        "no_bid": no_bid,
        "last_price": last_price,
    }


class KalshiClient:
    def __init__(self) -> None:
        self.credentials = get_credentials()
        self.last_successful_request: str | None = None
        self.last_error: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.credentials.available

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        headers = self._base_headers()
        if not self.credentials.available:
            return headers
        timestamp = str(int(dt.datetime.now(dt.UTC).timestamp() * 1000))
        parsed_path = urlparse(f"{self.credentials.base_url}{path}").path
        signature = _sign_request(self.credentials.private_key or "", timestamp, method, parsed_path)
        headers.update(
            {
                "KALSHI-ACCESS-KEY": self.credentials.api_key_id or "",
                "KALSHI-ACCESS-TIMESTAMP": timestamp,
                "KALSHI-ACCESS-SIGNATURE": signature,
            }
        )
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        auth_required: bool = False,
    ) -> dict[str, Any]:
        headers = self._auth_headers(method, path) if auth_required else self._base_headers()
        response = requests.request(
            method,
            f"{self.credentials.base_url}{path}",
            params=params,
            data=json.dumps(payload) if payload is not None else None,
            headers=headers,
            timeout=25,
        )
        response.raise_for_status()
        self.last_successful_request = dt.datetime.now(dt.UTC).isoformat()
        return response.json() if response.content else {}

    @st.cache_data(ttl=300, show_spinner=False)
    def get_series_markets(_self, series_ticker: str, status: str = "open", limit: int = 25) -> list[dict[str, Any]]:
        payload = _self.request(
            "GET",
            "/markets",
            params={"series_ticker": series_ticker, "status": status, "limit": limit},
        )
        return payload.get("markets", [])

    @st.cache_data(ttl=300, show_spinner=False)
    def get_orderbook(_self, ticker: str) -> dict[str, Any]:
        return _self.request("GET", f"/markets/{ticker}/orderbook")

    def get_balance(self) -> dict[str, Any]:
        return self.request("GET", "/portfolio/balance", auth_required=True)

    def get_positions(self) -> dict[str, Any]:
        return self.request("GET", "/portfolio/positions", auth_required=True)


def parse_balance(raw_balance: dict[str, Any]) -> float | None:
    for key in (
        "cash_balance",
        "balance",
        "portfolio_balance",
        "available_balance",
        "cash_balance_dollars",
        "balance_dollars",
    ):
        value = raw_balance.get(key)
        parsed = safe_float(value)
        if parsed is not None:
            return parsed
    nested = raw_balance.get("balance") if isinstance(raw_balance.get("balance"), dict) else None
    if nested:
        return parse_balance(nested)
    return None
