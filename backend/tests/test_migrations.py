"""Verify the Alembic baseline migration provisions the full schema and is
reversible, run against a temp SQLite DB via Alembic's command API."""
import pathlib

import pytest

pytest.importorskip("alembic")
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND = pathlib.Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "users", "audit_log", "instruments", "candles", "funding_rates", "open_interest",
    "accounts", "orders", "fills", "positions", "equity_snapshots", "signals",
    "risk_events", "integrations", "integration_secrets",
}


def _config(db_url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_migration_upgrade_creates_all_tables(tmp_path, monkeypatch):
    db_file = tmp_path / "m.sqlite"
    url = f"sqlite:///{db_file}"
    # env.py reads the app settings URL; point it at our temp SQLite.
    monkeypatch.setenv("DATABASE_URL", url)
    from app.core.config import get_settings
    get_settings.cache_clear()

    command.upgrade(_config(url), "head")

    insp = inspect(create_engine(url))
    tables = set(insp.get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"migration missing tables: {missing}"

    command.downgrade(_config(url), "base")
    insp2 = inspect(create_engine(url))
    assert "orders" not in insp2.get_table_names()
    get_settings.cache_clear()
