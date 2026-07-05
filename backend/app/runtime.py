"""Application runtime: the live, in-process wiring of all engines around the
real market-data stream. Instantiated once at startup and shared by the API
and WebSocket layers. In-memory account state for V1 (DB persistence is the
Phase-2 wiring task); all market data is authentic Bybit data.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from loguru import logger

from .core.config import Settings
from .services.integrations.registry import REGISTRY, Integration
from .services.market_data.bybit import BybitProvider
from .services.market_data.hub import MarketHub
from .services.paper_engine.account import PaperAccount
from .services.paper_engine.engine import PaperEngine
from .services.paper_engine.models import ZERO, Fill, FillConfig, Order
from .services.risk.killswitch import AUTO_TRIGGERS, KillSwitchRegistry, Level
from .services.risk.limits import (
    AccountRiskState, MarketRiskState, OrderIntent, RiskDecision, RiskEngine, RiskLimits,
)
from .services.strategy.base import Candle, MarketState
from .services.strategy.ensemble import Ensemble
from .services.strategy.strategies import ALL_STRATEGIES


class Runtime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.symbols = settings.symbol_list
        self.provider = BybitProvider(settings.bybit_rest_url, settings.bybit_ws_public_url)
        self.hub = MarketHub(
            self.provider, self.symbols,
            staleness_warn_s=settings.staleness_warn_s,
            staleness_block_s=settings.staleness_block_s,
        )
        self.fill_config = FillConfig(
            taker_fee_bps=settings.paper_taker_fee_bps,
            maker_fee_bps=settings.paper_maker_fee_bps,
            slippage_model=settings.paper_slippage_model,
            slippage_bps=settings.paper_slippage_bps,
            latency_ms=settings.paper_latency_ms,
        )
        self.account = PaperAccount(starting_balance=settings.paper_starting_balance)
        self.engine = PaperEngine(account=self.account, fill_config=self.fill_config,
                                  on_fill=self._on_fill)
        self.risk_limits = RiskLimits(max_leverage=settings.paper_max_leverage)
        self.risk = RiskEngine(self.risk_limits)
        self.kill = KillSwitchRegistry(on_trip=self._on_kill_trip)
        self.strategies = [cls() for cls in ALL_STRATEGIES]
        self.ensemble = Ensemble(self.strategies)
        self.integrations: Dict[str, Integration] = {}

        self.recent_signals: List[dict] = []
        self.recent_fills: List[dict] = []
        self.day_pnl_anchor = self.account.starting_balance
        self.peak_equity = self.account.starting_balance
        self.consecutive_losses = 0

        # WS broadcast hooks set by the ws layer.
        self.broadcast: Optional[Callable[[str, dict], None]] = None

        self.hub.on_book = self._on_book
        self.hub.on_candle_closed = self._on_candle_closed

    # ── lifecycle ───────────────────────────────────────────────────

    async def start(self) -> None:
        logger.info("runtime starting: mode={} symbols={}", self.settings.vantage_mode, self.symbols)
        self.hub.start()
        self._monitor_task = asyncio.create_task(self._quality_monitor(), name="quality-monitor")

    async def stop(self) -> None:
        await self.hub.stop()
        if getattr(self, "_monitor_task", None):
            self._monitor_task.cancel()

    # ── market callbacks ────────────────────────────────────────────

    def _on_book(self, book) -> None:
        self.engine.on_book(book)
        eq = self._equity()
        self.peak_equity = max(self.peak_equity, eq)
        if self.broadcast:
            self.broadcast(f"book.{book.symbol}", {
                "symbol": book.symbol, "bid": str(book.bid), "ask": str(book.ask),
                "spread_bps": str(round(book.spread_bps, 2)),
            })

    def _on_candle_closed(self, symbol: str, candle: Candle) -> None:
        candles = list(self.hub.candles[symbol])
        ticker = self.hub.tickers.get(symbol, {})
        market = MarketState(
            symbol=symbol,
            funding_rate=float(ticker.get("fundingRate", 0) or 0),
            open_interest=float(ticker.get("openInterest", 0) or 0),
            spread_bps=self._spread_bps(symbol),
        )
        result = self.ensemble.evaluate(candles, market)
        sig = result.signal
        record = {
            "strategy_id": sig.strategy_id, "symbol": symbol, "ts_ms": sig.ts_ms,
            "direction": sig.direction.value, "confidence": sig.confidence,
            "reasoning": sig.reasoning, "invalidation": sig.invalidation,
            "regime": sig.regime.value,
        }
        self.recent_signals.insert(0, record)
        self.recent_signals = self.recent_signals[:100]
        if self.broadcast:
            self.broadcast("signals", record)
        # NOTE: auto-execution of ensemble signals is gated behind an explicit
        # per-account "autotrade" toggle (Phase 3 wiring); signals are surfaced
        # for review by default so a human stays in the loop.

    def _on_fill(self, fill: Fill) -> None:
        rec = {"symbol": fill.symbol, "side": fill.side.value, "qty": str(fill.qty),
               "price": str(fill.price), "fee": str(round(fill.fee, 4)),
               "slippage_bps": str(round(fill.slippage_bps, 3)), "ts_ms": fill.ts_ms}
        self.recent_fills.insert(0, rec)
        self.recent_fills = self.recent_fills[:100]
        if self.broadcast:
            self.broadcast("account.fills", rec)

    def _on_kill_trip(self, switch) -> None:
        logger.warning("KILL SWITCH tripped: {} {} — {}", switch.scope, switch.level, switch.reason)
        if switch.level is Level.HARD and switch.scope == "global":
            self.engine.flatten_all(f"kill_switch:{switch.reason}", int(time.time() * 1000))
        if self.broadcast:
            self.broadcast("risk", {"event": "killswitch_tripped", "scope": switch.scope,
                                    "level": switch.level.value if switch.level else None,
                                    "reason": switch.reason})

    # ── order gateway (risk + kill switch enforced) ─────────────────

    def place_order(self, order: Order, strategy_id: Optional[str] = None) -> dict:
        # 1) kill-switch gate
        if not order.reduce_only:
            blocked = self.kill.entries_blocked(order.symbol, strategy_id)
            if blocked:
                order.status = order.status.__class__.REJECTED
                return {"accepted": False, "reasons": [blocked]}
        else:
            blocked = self.kill.exits_blocked(order.symbol)
            if blocked:
                return {"accepted": False, "reasons": [blocked]}

        # 2) risk gate
        book = self.hub.books.get(order.symbol)
        ref_price = book.mid if book else (order.price or ZERO)
        decision = self._risk_check(order, ref_price)
        if not decision.allowed:
            order.status = order.status.__class__.REJECTED
            return {"accepted": False, "reasons": decision.reasons}

        # 3) submit to executor
        self.engine.submit(order, int(time.time() * 1000), strategy_id=strategy_id)
        if book:                       # let it interact with the current book immediately
            self.engine.on_book(book)
        return {"accepted": True, "order_id": order.id, "status": order.status.value}

    def _risk_check(self, order: Order, ref_price: Decimal) -> RiskDecision:
        marks = self._marks()
        pos = self.account.positions.get(order.symbol)
        intent = OrderIntent(
            symbol=order.symbol, side=order.side.value, qty=order.qty,
            price=ref_price or Decimal("1"), leverage=order.leverage,
            stop_price=order.trigger_price, reduce_only=order.reduce_only,
        )
        acct = AccountRiskState(
            equity=self._equity(), peak_equity=self.peak_equity,
            day_pnl=self._equity() - self.day_pnl_anchor, week_pnl=ZERO,
            open_positions=len(self.account.positions),
            total_notional=self.account.exposure(marks),
            symbol_notional=(pos.notional if pos else ZERO),
            consecutive_losses=self.consecutive_losses,
        )
        mkt = MarketRiskState(
            spread_bps=Decimal(str(self._spread_bps(order.symbol))),
            data_age_s=Decimal(str(round(self.hub.data_age_s(order.symbol), 1))),
            atr_pct=Decimal("1.0"),
            funding_rate=Decimal(str(self.hub.tickers.get(order.symbol, {}).get("fundingRate", 0) or 0)),
            connectivity_ok=self.hub.data_age_s(order.symbol) < self.settings.staleness_block_s,
        )
        # Reduce-only exits skip most gates inside RiskEngine.check already.
        return self.risk.check(intent, acct, mkt)

    # ── automatic kill-switch monitor ───────────────────────────────

    async def _quality_monitor(self) -> None:
        while True:
            try:
                for sym in self.symbols:
                    age = self.hub.data_age_s(sym)
                    if age > self.settings.staleness_kill_s:
                        self.kill.trip(f"symbol:{sym}", AUTO_TRIGGERS["stale_market_data"],
                                       f"data stale {age:.0f}s", actor="quality_monitor")
                eq = self._equity()
                dd = (self.peak_equity - eq) / self.peak_equity * 100 if self.peak_equity else 0
                if dd >= float(self.risk_limits.max_drawdown_pct):
                    self.kill.trip("global", AUTO_TRIGGERS["drawdown_exceeded"],
                                   f"drawdown {dd:.1f}%", actor="quality_monitor")
                day_loss = (self.day_pnl_anchor - eq) / self.day_pnl_anchor * 100 if self.day_pnl_anchor else 0
                if day_loss >= float(self.risk_limits.max_daily_loss_pct):
                    self.kill.trip("global", AUTO_TRIGGERS["daily_loss_exceeded"],
                                   f"daily loss {day_loss:.1f}%", actor="quality_monitor")
            except Exception:
                logger.exception("quality monitor tick failed")
            await asyncio.sleep(2.0)

    # ── valuation helpers ───────────────────────────────────────────

    def _marks(self) -> Dict[str, Decimal]:
        out = {}
        for sym in self.symbols:
            b = self.hub.books.get(sym)
            if b:
                out[sym] = b.mid
        return out

    def _equity(self) -> Decimal:
        return self.account.equity(self._marks())

    def _spread_bps(self, symbol: str) -> float:
        b = self.hub.books.get(symbol)
        return float(b.spread_bps) if b else 0.0

    # ── dashboard snapshot ──────────────────────────────────────────

    def overview(self) -> dict:
        marks = self._marks()
        eq = self.account.equity(marks)
        return {
            "mode": self.settings.vantage_mode,
            "equity": str(round(eq, 2)),
            "balance": str(round(self.account.balance, 2)),
            "unrealized_pnl": str(round(self.account.unrealized(marks), 2)),
            "realized_pnl": str(round(self.account.realized_pnl_total(), 2)),
            "day_pnl": str(round(eq - self.day_pnl_anchor, 2)),
            "peak_equity": str(round(self.peak_equity, 2)),
            "drawdown_pct": str(round((self.peak_equity - eq) / self.peak_equity * 100
                                      if self.peak_equity else 0, 2)),
            "margin_used": str(round(self.account.margin_used(), 2)),
            "exposure": str(round(self.account.exposure(marks), 2)),
            "open_positions": len(self.account.positions),
            "closed_trades": len(self.account.closed_trades),
            "data_health": self.hub.health(),
            "kill_switches": [{"scope": s.scope, "state": s.state.value,
                               "level": s.level.value if s.level else None, "reason": s.reason}
                              for s in self.kill.status()],
        }
