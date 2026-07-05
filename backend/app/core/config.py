from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vantage_env: str = "dev"
    vantage_mode: str = "paper"          # paper | exchange_demo ('live' rejected)
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://vantage:vantage@localhost:5432/vantage"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-secret"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 14
    secret_encryption_key: str = ""

    market_provider: str = "bybit"      # bybit | binance
    bybit_rest_url: str = "https://api.bybit.com"
    bybit_ws_public_url: str = "wss://stream.bybit.com/v5/public/linear"
    symbols: str = "BTCUSDT,ETHUSDT"
    base_timeframe: str = "1m"

    staleness_warn_s: float = 5
    staleness_block_s: float = 15
    staleness_kill_s: float = 60

    paper_starting_balance: Decimal = Decimal("100000")
    paper_taker_fee_bps: Decimal = Decimal("5.5")
    paper_maker_fee_bps: Decimal = Decimal("2.0")
    paper_slippage_model: str = "spread_plus_bps"
    paper_slippage_bps: Decimal = Decimal("1.0")
    paper_latency_ms: int = 80
    paper_max_leverage: Decimal = Decimal("5")

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip() for s in self.symbols.split(",") if s.strip()]

    def validate_mode(self) -> None:
        if self.vantage_mode not in ("paper", "exchange_demo"):
            raise ValueError(
                f"mode '{self.vantage_mode}' is not permitted in this build "
                "(live trading is disabled by design in V1)"
            )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_mode()
    return s
