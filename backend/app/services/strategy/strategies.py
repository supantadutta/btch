"""V1 strategy set. Each returns a Signal with direction, confidence,
human-readable reasoning, invalidation, and stop/target suggestions."""
from __future__ import annotations

from typing import Sequence

from . import indicators as ta
from .base import (
    Candle, Direction, HoldingStyle, MarketState, Regime, Signal, Strategy, series,
)


class TrendBreakout(Strategy):
    """EMA trend alignment + breakout of the N-bar high/low, ATR-based stop."""
    id, name = "trend_breakout", "Trend-Following Breakout"
    default_params = {"ema_fast": 21, "ema_slow": 55, "lookback": 20, "atr_period": 14,
                      "atr_stop_mult": 2.0, "atr_target_mult": 3.5}

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        p = self.params
        need = max(p["ema_slow"], p["lookback"], p["atr_period"]) + 2
        if len(candles) < need:
            return self._neutral(market, candles[-1].ts_ms if candles else 0, "insufficient history")
        h, l, c, _ = series(candles)
        ef, es = ta.ema(c, p["ema_fast"])[-1], ta.ema(c, p["ema_slow"])[-1]
        hi_prev = ta.highest(h, p["lookback"])[-2]
        lo_prev = ta.lowest(l, p["lookback"])[-2]
        a = ta.atr(h, l, c, p["atr_period"])[-1]
        last, ts = c[-1], candles[-1].ts_ms
        if None in (ef, es, hi_prev, lo_prev, a):
            return self._neutral(market, ts, "indicators warming up")

        if ef > es and last > hi_prev:
            edge = (last - hi_prev) / a if a else 0.0
            conf = min(0.9, 0.5 + 0.2 * edge)
            return Signal(
                self.id, market.symbol, ts, Direction.LONG, round(conf, 3),
                reasoning=(f"EMA{p['ema_fast']} above EMA{p['ema_slow']} (uptrend) and close "
                           f"{last:.2f} broke the {p['lookback']}-bar high {hi_prev:.2f}"),
                invalidation=f"close back below breakout level {hi_prev:.2f}",
                holding_style=HoldingStyle.SWING,
                suggested_stop=last - p["atr_stop_mult"] * a,
                suggested_target=last + p["atr_target_mult"] * a,
                suggested_risk_pct=0.75, regime=Regime.TRENDING_UP,
            )
        if ef < es and last < lo_prev:
            edge = (lo_prev - last) / a if a else 0.0
            conf = min(0.9, 0.5 + 0.2 * edge)
            return Signal(
                self.id, market.symbol, ts, Direction.SHORT, round(conf, 3),
                reasoning=(f"EMA{p['ema_fast']} below EMA{p['ema_slow']} (downtrend) and close "
                           f"{last:.2f} broke the {p['lookback']}-bar low {lo_prev:.2f}"),
                invalidation=f"close back above breakdown level {lo_prev:.2f}",
                holding_style=HoldingStyle.SWING,
                suggested_stop=last + p["atr_stop_mult"] * a,
                suggested_target=last - p["atr_target_mult"] * a,
                suggested_risk_pct=0.75, regime=Regime.TRENDING_DOWN,
            )
        return self._neutral(market, ts, "no aligned trend + breakout")


class MeanReversionVWAP(Strategy):
    """Fade stretched deviations from session VWAP when RSI confirms exhaustion
    and price pierces the Bollinger band."""
    id, name = "mean_reversion", "VWAP/RSI Mean Reversion"
    default_params = {"rsi_period": 14, "rsi_low": 28.0, "rsi_high": 72.0,
                      "vwap_dev_atr": 1.5, "atr_period": 14, "bb_period": 20, "bb_mult": 2.0}

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        p = self.params
        need = max(p["rsi_period"], p["bb_period"], p["atr_period"]) + 2
        if len(candles) < need:
            return self._neutral(market, candles[-1].ts_ms if candles else 0, "insufficient history")
        h, l, c, v = series(candles)
        r = ta.rsi(c, p["rsi_period"])[-1]
        vw = ta.vwap(h, l, c, v)[-1]
        a = ta.atr(h, l, c, p["atr_period"])[-1]
        bb_lo, _, bb_hi = ta.bollinger(c, p["bb_period"], p["bb_mult"])
        last, ts = c[-1], candles[-1].ts_ms
        if None in (r, vw, a, bb_lo[-1], bb_hi[-1]) or not a:
            return self._neutral(market, ts, "indicators warming up")
        dev_atr = (last - vw) / a

        if dev_atr <= -p["vwap_dev_atr"] and r <= p["rsi_low"] and last <= bb_lo[-1]:
            conf = min(0.85, 0.45 + 0.1 * (-dev_atr - p["vwap_dev_atr"]) + (p["rsi_low"] - r) / 100)
            return Signal(
                self.id, market.symbol, ts, Direction.LONG, round(conf, 3),
                reasoning=(f"price {abs(dev_atr):.1f} ATR below session VWAP {vw:.2f}, "
                           f"RSI {r:.0f} oversold, close under lower Bollinger band — fade toward VWAP"),
                invalidation="another close beyond 1 ATR further from VWAP",
                holding_style=HoldingStyle.INTRADAY,
                suggested_stop=last - 1.0 * a, suggested_target=vw,
                suggested_risk_pct=0.5, regime=Regime.RANGING,
            )
        if dev_atr >= p["vwap_dev_atr"] and r >= p["rsi_high"] and last >= bb_hi[-1]:
            conf = min(0.85, 0.45 + 0.1 * (dev_atr - p["vwap_dev_atr"]) + (r - p["rsi_high"]) / 100)
            return Signal(
                self.id, market.symbol, ts, Direction.SHORT, round(conf, 3),
                reasoning=(f"price {dev_atr:.1f} ATR above session VWAP {vw:.2f}, "
                           f"RSI {r:.0f} overbought, close over upper Bollinger band — fade toward VWAP"),
                invalidation="another close beyond 1 ATR further from VWAP",
                holding_style=HoldingStyle.INTRADAY,
                suggested_stop=last + 1.0 * a, suggested_target=vw,
                suggested_risk_pct=0.5, regime=Regime.RANGING,
            )
        return self._neutral(market, ts, "price within normal VWAP band")


class MomentumConfirmation(Strategy):
    """MACD histogram expansion + RSI midline + rising open interest = follow momentum."""
    id, name = "momentum_confirm", "Momentum Confirmation"
    default_params = {"rsi_period": 14, "atr_period": 14}

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        p = self.params
        if len(candles) < 40:
            return self._neutral(market, candles[-1].ts_ms if candles else 0, "insufficient history")
        h, l, c, _ = series(candles)
        _, _, hist = ta.macd(c)
        r = ta.rsi(c, p["rsi_period"])[-1]
        a = ta.atr(h, l, c, p["atr_period"])[-1]
        last, ts = c[-1], candles[-1].ts_ms
        if hist[-1] is None or hist[-2] is None or r is None or a is None:
            return self._neutral(market, ts, "indicators warming up")
        oi_conf = 0.1 if market.open_interest_change_pct > 0.5 else 0.0
        oi_note = (f"; OI +{market.open_interest_change_pct:.1f}% confirms participation"
                   if oi_conf else "")

        if hist[-1] > 0 and hist[-1] > hist[-2] and r > 55:
            conf = min(0.85, 0.5 + oi_conf + min(0.15, hist[-1] / last * 1000))
            return Signal(
                self.id, market.symbol, ts, Direction.LONG, round(conf, 3),
                reasoning=f"MACD histogram positive and expanding, RSI {r:.0f} above midline{oi_note}",
                invalidation="MACD histogram contracting two consecutive bars",
                holding_style=HoldingStyle.INTRADAY,
                suggested_stop=last - 1.5 * a, suggested_target=last + 2.5 * a,
                suggested_risk_pct=0.5, regime=Regime.TRENDING_UP,
            )
        if hist[-1] < 0 and hist[-1] < hist[-2] and r < 45:
            conf = min(0.85, 0.5 + oi_conf + min(0.15, -hist[-1] / last * 1000))
            return Signal(
                self.id, market.symbol, ts, Direction.SHORT, round(conf, 3),
                reasoning=f"MACD histogram negative and expanding, RSI {r:.0f} below midline{oi_note}",
                invalidation="MACD histogram contracting two consecutive bars",
                holding_style=HoldingStyle.INTRADAY,
                suggested_stop=last + 1.5 * a, suggested_target=last - 2.5 * a,
                suggested_risk_pct=0.5, regime=Regime.TRENDING_DOWN,
            )
        return self._neutral(market, ts, "momentum not confirmed")


class RegimeFilter(Strategy):
    """ADX-based regime classifier. Filter: tags the regime; the ensemble uses
    it to route trend vs reversion strategies. Never votes a direction."""
    id, name, is_filter = "regime_filter", "Market Regime Filter", True
    default_params = {"adx_period": 14, "adx_trend": 25.0, "atr_period": 14, "atr_highvol_pct": 3.0}

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        p = self.params
        if len(candles) < 3 * p["adx_period"]:
            return self._neutral(market, candles[-1].ts_ms if candles else 0,
                                 "insufficient history", Regime.UNKNOWN)
        h, l, c, _ = series(candles)
        adx_v = ta.adx(h, l, c, p["adx_period"])[-1]
        a = ta.atr(h, l, c, p["atr_period"])[-1]
        ef, es = ta.ema(c, 21)[-1], ta.ema(c, 55)[-1]
        last, ts = c[-1], candles[-1].ts_ms
        if None in (adx_v, a, ef, es):
            return self._neutral(market, ts, "indicators warming up", Regime.UNKNOWN)
        atr_pct = a / last * 100
        if atr_pct >= p["atr_highvol_pct"]:
            regime, why = Regime.HIGH_VOL, f"ATR {atr_pct:.1f}% of price ≥ {p['atr_highvol_pct']}%"
        elif adx_v >= p["adx_trend"]:
            regime = Regime.TRENDING_UP if ef > es else Regime.TRENDING_DOWN
            why = f"ADX {adx_v:.0f} ≥ {p['adx_trend']} with EMA21 {'>' if ef > es else '<'} EMA55"
        else:
            regime, why = Regime.RANGING, f"ADX {adx_v:.0f} < {p['adx_trend']}"
        sig = self._neutral(market, ts, f"regime: {regime.value} ({why})", regime)
        sig.meta = {"adx": adx_v, "atr_pct": atr_pct}
        return sig


class FundingFilter(Strategy):
    """Veto entries when the real funding rate is at a crowded extreme
    (entering with the crowd right before a funding payment is negative-EV)."""
    id, name, is_filter = "funding_filter", "Funding-Rate Safety Filter", True
    default_params = {"abs_limit": 0.0010}   # |8h rate| = 0.10%

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        ts = candles[-1].ts_ms if candles else 0
        fr, limit = market.funding_rate, self.params["abs_limit"]
        if abs(fr) >= limit:
            crowd = "longs" if fr > 0 else "shorts"
            sig = self._neutral(
                market, ts,
                f"funding rate {fr:+.4%} beyond ±{limit:.2%} — crowded {crowd}; new entries vetoed",
                veto=True,
            )
            sig.meta = {"funding_rate": fr, "veto_side": "long" if fr > 0 else "short"}
            return sig
        return self._neutral(market, ts, f"funding rate {fr:+.4%} within safe band")


class VolatilityFilter(Strategy):
    """Veto when realized volatility is too low (no edge after costs) or too
    high (uncontrollable risk); otherwise passes with an ATR context tag."""
    id, name, is_filter = "volatility_filter", "Volatility Filter", True
    default_params = {"atr_period": 14, "min_atr_pct": 0.05, "max_atr_pct": 5.0}

    def evaluate(self, candles: Sequence[Candle], market: MarketState) -> Signal:
        p = self.params
        if len(candles) < p["atr_period"] + 2:
            return self._neutral(market, candles[-1].ts_ms if candles else 0, "insufficient history")
        h, l, c, _ = series(candles)
        a = ta.atr(h, l, c, p["atr_period"])[-1]
        last, ts = c[-1], candles[-1].ts_ms
        if a is None or not last:
            return self._neutral(market, ts, "indicators warming up")
        atr_pct = a / last * 100
        if atr_pct < p["min_atr_pct"]:
            return self._neutral(
                market, ts, f"ATR {atr_pct:.2f}% below {p['min_atr_pct']}% — costs exceed edge; veto",
                veto=True)
        if atr_pct > p["max_atr_pct"]:
            return self._neutral(
                market, ts, f"ATR {atr_pct:.2f}% above {p['max_atr_pct']}% — volatility cap; veto",
                Regime.HIGH_VOL, veto=True)
        sig = self._neutral(market, ts, f"volatility normal (ATR {atr_pct:.2f}%)")
        sig.meta = {"atr_pct": atr_pct}
        return sig


ALL_STRATEGIES: list[type[Strategy]] = [
    TrendBreakout, MeanReversionVWAP, MomentumConfirmation,
    RegimeFilter, FundingFilter, VolatilityFilter,
]
