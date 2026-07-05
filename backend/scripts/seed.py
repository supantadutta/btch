"""Bootstrap a sample paper account with a few realistic closed trades so the
analytics pages render on first run. Uses the REAL engine + fill simulator over
representative book snapshots (not fabricated PnL). Run: python scripts/seed.py
"""
from __future__ import annotations

from decimal import Decimal

from app.services.paper_engine.account import PaperAccount
from app.services.paper_engine.engine import PaperEngine
from app.services.paper_engine.models import BookTop, FillConfig, Order, OrderType, Side


def book(sym, ts, bid, ask):
    return BookTop(sym, ts, Decimal(bid), Decimal(ask), Decimal("10"), Decimal("10"))


def main() -> None:
    acct = PaperAccount(starting_balance=Decimal("100000"))
    eng = PaperEngine(acct, FillConfig())

    # Trade 1: long BTC, exit in profit
    eng.submit(Order("BTCUSDT", Side.BUY, OrderType.MARKET, Decimal("0.5"), leverage=Decimal("3")),
               now_ms=0, entry_reason="trend_breakout: EMA21>EMA55 + 20-bar breakout")
    eng.on_book(book("BTCUSDT", 100, "60000", "60005"))
    eng.submit(Order("BTCUSDT", Side.SELL, OrderType.MARKET, Decimal("0.5"), reduce_only=True),
               now_ms=200, exit_reason="take_profit hit")
    eng.on_book(book("BTCUSDT", 300, "61200", "61205"))

    # Trade 2: short ETH, small loss
    eng.submit(Order("ETHUSDT", Side.SELL, OrderType.MARKET, Decimal("5"), leverage=Decimal("3")),
               now_ms=400, entry_reason="mean_reversion: 1.6 ATR above VWAP, RSI 74")
    eng.on_book(book("ETHUSDT", 500, "3000", "3001"))
    eng.submit(Order("ETHUSDT", Side.BUY, OrderType.MARKET, Decimal("5"), reduce_only=True),
               now_ms=600, exit_reason="stop_loss")
    eng.on_book(book("ETHUSDT", 700, "3015", "3016"))

    print(f"Seeded paper account: balance={acct.balance:.2f}")
    for t in acct.closed_trades:
        print(f"  {t.position.symbol} {t.position.side.value}: pnl={t.pnl:.2f} "
              f"exit={t.exit_reason}")
    print("NOTE: PnL is produced by the real fill simulator, net of fees. "
          "No profit is implied for live trading.")


if __name__ == "__main__":
    main()
