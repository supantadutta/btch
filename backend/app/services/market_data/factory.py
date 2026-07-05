"""Provider selection — the seam that makes the data venue a config choice.
Adding OKX/Hyperliquid later means implementing MarketDataProvider and adding a
branch here; nothing downstream changes."""
from __future__ import annotations

from .base import MarketDataProvider
from .binance import BinanceProvider
from .bybit import BybitProvider


def make_provider(name: str, settings) -> MarketDataProvider:
    name = (name or "bybit").lower()
    if name == "bybit":
        return BybitProvider(settings.bybit_rest_url, settings.bybit_ws_public_url)
    if name == "binance":
        return BinanceProvider()  # defaults to testnet base URLs
    raise ValueError(f"unknown market-data provider '{name}'")
