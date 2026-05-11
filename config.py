from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv()

APP_TITLE = "ICON Climate Underwriting Terminal"
APP_TIMEZONE = "America/New_York"
KALSHI_PRODUCTION_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
KALSHI_DEMO_BASE_URL = "https://external-api.demo.kalshi.co/trade-api/v2"
CITIES_PATH = Path("config/cities.csv")
DATA_DIR = Path("data")
DATABASE_PATH = DATA_DIR / "icon_underwriting.db"


@dataclass(frozen=True)
class KalshiCredentials:
    api_key_id: str | None
    private_key: str | None
    environment: str
    base_url: str

    @property
    def available(self) -> bool:
        return bool(self.api_key_id and self.private_key)


def _streamlit_secret(name: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(name)
        return str(value) if value else None
    except Exception:
        return None


def get_env(name: str) -> str | None:
    return os.getenv(name) or _streamlit_secret(name)


def get_kalshi_credentials() -> KalshiCredentials:
    environment = (get_env("KALSHI_ENVIRONMENT") or "demo").lower()
    api_key_id = get_env("KALSHI_API_KEY_ID") or get_env("KALSHI_DEMO_API_KEY_ID")
    private_key = get_env("KALSHI_PRIVATE_KEY") or get_env("KALSHI_DEMO_PRIVATE_KEY")
    if private_key:
        private_key = _normalize_private_key(str(private_key))
    explicit_url = get_env("KALSHI_API_BASE_URL")
    base_url = (
        explicit_url.rstrip("/")
        if explicit_url
        else KALSHI_DEMO_BASE_URL
        if environment == "demo"
        else KALSHI_PRODUCTION_BASE_URL
    )
    return KalshiCredentials(
        api_key_id=api_key_id,
        private_key=private_key,
        environment=environment,
        base_url=base_url,
    )


def _normalize_private_key(value: str) -> str:
    key = value.replace("\\n", "\n").strip().strip('"').strip("'").strip()
    if "BEGIN" in key:
        return key
    # Support users pasting only the base64 body into Streamlit Secrets.
    return (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        + key
        + "\n-----END RSA PRIVATE KEY-----"
    )
