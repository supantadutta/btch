"""Technical indicators — pure Python, dependency-free, computed over real
exchange candles. Floats are acceptable here (analysis, not money math)."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


def ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def sma(values: Sequence[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rsi(closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    out[period] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0.0)) / period
        out[i] = 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)
    return out


def true_ranges(h: Sequence[float], l: Sequence[float], c: Sequence[float]) -> List[float]:
    tr = [h[0] - l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def atr(h: Sequence[float], l: Sequence[float], c: Sequence[float],
        period: int = 14) -> List[Optional[float]]:
    tr = true_ranges(h, l, c)
    out: List[Optional[float]] = [None] * len(c)
    if len(c) < period:
        return out
    prev = sum(tr[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(c)):
        prev = (prev * (period - 1) + tr[i]) / period   # Wilder smoothing
        out[i] = prev
    return out


def adx(h: Sequence[float], l: Sequence[float], c: Sequence[float],
        period: int = 14) -> List[Optional[float]]:
    n = len(c)
    out: List[Optional[float]] = [None] * n
    if n < 2 * period:
        return out
    tr = true_ranges(h, l, c)
    plus_dm = [0.0] + [max(h[i] - h[i - 1], 0.0)
                       if (h[i] - h[i - 1]) > (l[i - 1] - l[i]) else 0.0 for i in range(1, n)]
    minus_dm = [0.0] + [max(l[i - 1] - l[i], 0.0)
                        if (l[i - 1] - l[i]) > (h[i] - h[i - 1]) else 0.0 for i in range(1, n)]
    str_, spd, smd = sum(tr[1:period + 1]), sum(plus_dm[1:period + 1]), sum(minus_dm[1:period + 1])
    dxs: List[float] = []
    for i in range(period + 1, n):
        str_ = str_ - str_ / period + tr[i]
        spd = spd - spd / period + plus_dm[i]
        smd = smd - smd / period + minus_dm[i]
        pdi = 100 * spd / str_ if str_ else 0.0
        mdi = 100 * smd / str_ if str_ else 0.0
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0)
        if len(dxs) == period:
            out[i] = sum(dxs) / period
        elif len(dxs) > period:
            prev = out[i - 1]
            out[i] = (prev * (period - 1) + dxs[-1]) / period if prev is not None else None
    return out


def vwap(h: Sequence[float], l: Sequence[float], c: Sequence[float],
         v: Sequence[float]) -> List[Optional[float]]:
    """Cumulative session VWAP over the provided window."""
    out: List[Optional[float]] = [None] * len(c)
    cum_pv = cum_v = 0.0
    for i in range(len(c)):
        typical = (h[i] + l[i] + c[i]) / 3
        cum_pv += typical * v[i]
        cum_v += v[i]
        out[i] = cum_pv / cum_v if cum_v else None
    return out


def bollinger(closes: Sequence[float], period: int = 20, mult: float = 2.0
              ) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    mid = sma(closes, period)
    upper: List[Optional[float]] = [None] * len(closes)
    lower: List[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1: i + 1]
        m = mid[i]
        if m is None:
            continue
        var = sum((x - m) ** 2 for x in window) / period
        sd = var ** 0.5
        upper[i] = m + mult * sd
        lower[i] = m - mult * sd
    return lower, mid, upper


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
         ) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    ef, es = ema(closes, fast), ema(closes, slow)
    line: List[Optional[float]] = [
        (a - b) if a is not None and b is not None else None for a, b in zip(ef, es)
    ]
    valid = [x for x in line if x is not None]
    sig_valid = ema(valid, signal)
    sig: List[Optional[float]] = [None] * len(line)
    j = 0
    for i, x in enumerate(line):
        if x is not None:
            sig[i] = sig_valid[j]
            j += 1
    hist = [(a - b) if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def highest(values: Sequence[float], period: int) -> List[Optional[float]]:
    return [max(values[i - period + 1: i + 1]) if i >= period - 1 else None
            for i in range(len(values))]


def lowest(values: Sequence[float], period: int) -> List[Optional[float]]:
    return [min(values[i - period + 1: i + 1]) if i >= period - 1 else None
            for i in range(len(values))]
