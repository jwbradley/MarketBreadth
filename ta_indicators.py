#!/usr/bin/env python3
"""
Shared technical analysis indicators for MarketBreadth tools.

Used by stock_screener.py and OvtLyrMimic.py so scoring and the Nine Rules
see the same RSI, EMA, MACD, ATR, and divergence math.

RSI uses Wilder's smoothing (industry standard).
All EMAs use ewm(span=..., adjust=False).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core series helpers
# ---------------------------------------------------------------------------

def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average (adjust=False for TA consistency)."""
    return series.ewm(span=span, adjust=False).mean()


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder RSI: average gain/loss use exponential smoothing with alpha=1/period.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Return (macd_line, signal_line, histogram)."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger_pct(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    mid = sma(close, window)
    std = close.rolling(window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    width = (upper - lower).replace(0, np.nan)
    return (close - lower) / width


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def relative_strength(
    stock_close: pd.Series,
    bench_close: pd.Series,
    lookback: int = 20,
) -> Optional[float]:
    """Stock return minus benchmark return over lookback days (percentage points)."""
    if stock_close is None or bench_close is None:
        return None
    if len(stock_close) < lookback + 1 or len(bench_close) < lookback + 1:
        return None
    stock_ret = (float(stock_close.iloc[-1]) / float(stock_close.iloc[-lookback]) - 1) * 100
    bench_ret = (float(bench_close.iloc[-1]) / float(bench_close.iloc[-lookback]) - 1) * 100
    return round(stock_ret - bench_ret, 2)


# ---------------------------------------------------------------------------
# Divergence helpers
# ---------------------------------------------------------------------------

def detect_divergences(
    close: pd.Series,
    rsi: pd.Series,
    lookback: int = 5,
    bearish_rsi_min: float = 65.0,
    bullish_rsi_max: float = 35.0,
) -> Dict[str, bool]:
    """
    Simple 5-day divergence:
      bearish: price up, RSI down, RSI still elevated
      bullish: price down, RSI up, RSI still depressed
    """
    if len(close) < lookback + 1 or len(rsi) < lookback + 1:
        return {'bearish_divergence': False, 'bullish_divergence': False}

    price = float(close.iloc[-1])
    price_ago = float(close.iloc[-lookback])
    current_rsi = float(rsi.iloc[-1])
    rsi_ago = float(rsi.iloc[-lookback])

    price_rising = price > price_ago
    rsi_rising = current_rsi > rsi_ago

    bearish = price_rising and (not rsi_rising) and current_rsi > bearish_rsi_min
    bullish = (not price_rising) and rsi_rising and current_rsi < bullish_rsi_max

    return {
        'bearish_divergence': bearish,
        'bullish_divergence': bullish,
    }


# ---------------------------------------------------------------------------
# Full indicator snapshot from OHLCV
# ---------------------------------------------------------------------------

def calculate_from_ohlcv(
    hist: pd.DataFrame,
    spy_close: Optional[pd.Series] = None,
    min_bars: int = 200,
) -> Optional[Dict[str, Any]]:
    """
    Compute a full indicator dict from a history DataFrame with
    columns: Open, High, Low, Close, Volume (yfinance style).

    Returns None if insufficient data.
    """
    if hist is None or hist.empty or len(hist) < min_bars:
        return None

    # Flatten MultiIndex columns if present
    if isinstance(hist.columns, pd.MultiIndex):
        hist = hist.copy()
        hist.columns = hist.columns.get_level_values(0)

    required = {'High', 'Low', 'Close', 'Volume'}
    if not required.issubset(set(hist.columns)):
        return None

    close = hist['Close'].dropna()
    high = hist['High']
    low = hist['Low']
    volume = hist['Volume']

    if len(close) < min_bars:
        return None

    latest_price = float(close.iloc[-1])

    ema10 = ema(close, 10)
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema100 = ema(close, 100)

    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)

    rsi = rsi_wilder(close, 14)
    macd_line, signal_line, macd_hist = macd(close)
    bb_pct = bollinger_pct(close)
    atr_series = atr(high, low, close, 14)
    atr_val = float(atr_series.iloc[-1])
    atr_pct = (atr_val / latest_price) * 100 if latest_price else 0.0

    avg_vol_20 = volume.rolling(20).mean()
    avg_vol_val = float(avg_vol_20.iloc[-1]) if not pd.isna(avg_vol_20.iloc[-1]) else 0.0
    daily_vol = float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0.0
    vol_ratio = (daily_vol / avg_vol_val) if avg_vol_val > 0 else 0.0
    dollar_vol_20 = avg_vol_val * latest_price

    rs_vs_spy = relative_strength(close, spy_close, 20) if spy_close is not None else None
    rs_vs_spy_60 = relative_strength(close, spy_close, 60) if spy_close is not None else None

    divs = detect_divergences(close, rsi)
    current_rsi = float(rsi.iloc[-1])
    price_5d_ago = float(close.iloc[-5]) if len(close) >= 5 else latest_price
    price_rising_5d = latest_price > price_5d_ago

    e10 = float(ema10.iloc[-1])
    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])
    e100 = float(ema100.iloc[-1])
    s20 = float(sma20.iloc[-1])
    s50 = float(sma50.iloc[-1])
    s200 = float(sma200.iloc[-1])

    ema_aligned = latest_price > e10 > e20 > e50
    ma_aligned = s20 > s50 > s200
    multi_tf_aligned = (latest_price > e20) and (latest_price > e100)
    trend_score = sum([
        latest_price > s20,
        latest_price > s50,
        latest_price > s200,
    ])

    macd_bullish = float(macd_line.iloc[-1]) > float(signal_line.iloc[-1])
    bb = float(bb_pct.iloc[-1]) if not pd.isna(bb_pct.iloc[-1]) else 0.5

    return {
        'price': round(latest_price, 2),
        'sma20': round(s20, 2),
        'sma50': round(s50, 2),
        'sma200': round(s200, 2),
        'ema10': round(e10, 2),
        'ema20': round(e20, 2),
        'ema50': round(e50, 2),
        'ema100': round(e100, 2),
        'above_20dma': latest_price > s20,
        'above_50dma': latest_price > s50,
        'above_200dma': latest_price > s200,
        'trend_score': trend_score,
        'ma_aligned': ma_aligned,
        'ema_aligned': ema_aligned,
        'multi_tf_aligned': multi_tf_aligned,
        'rsi': round(current_rsi, 1),
        'macd': round(float(macd_line.iloc[-1]), 3),
        'macd_signal': round(float(signal_line.iloc[-1]), 3),
        'macd_hist': round(float(macd_hist.iloc[-1]), 3),
        'macd_bullish': macd_bullish,
        'bb_pct': round(bb, 2),
        'bb_position': (
            'overbought' if bb > 0.8 else ('oversold' if bb < 0.2 else 'neutral')
        ),
        'atr': round(atr_val, 2),
        'atr_pct': round(atr_pct, 2),
        'volume_ratio': round(vol_ratio, 2),
        'avg_volume_20d': int(avg_vol_val),
        'daily_volume': int(daily_vol),
        'dollar_volume_20d': round(dollar_vol_20, 0),
        'rs_vs_spy': rs_vs_spy,
        'rs_vs_spy_60': rs_vs_spy_60,
        'price_rising_5d': price_rising_5d,
        'bearish_divergence': divs['bearish_divergence'],
        'bullish_divergence': divs['bullish_divergence'],
    }


# ---------------------------------------------------------------------------
# Nine Rules (shared) — used by screener and OvtLyrMimic
# ---------------------------------------------------------------------------

def evaluate_nine_rules(
    indicators: Dict[str, Any],
    market_breadth_pct: Optional[float] = None,
    sector_breadth_pct: Optional[float] = None,
    market_threshold: float = 50.0,
    sector_threshold: float = 50.0,
) -> Dict[str, Any]:
    """
    Evaluate OVTLYR-style nine rules from a precomputed indicator dict.

    Returns:
      {
        'rules': { name: {'passed': bool, 'details': str}, ... },
        'rules_passed': int,
        'total_rules': 9,
      }
    """
    price = indicators['price']
    e10 = indicators['ema10']
    e20 = indicators['ema20']
    e50 = indicators['ema50']
    e100 = indicators.get('ema100')
    if e100 is None:
        # Fallback if older payload
        e100 = e50
    rsi = indicators['rsi']
    vol_ratio = indicators['volume_ratio']
    atr_pct = indicators['atr_pct']
    price_rising = indicators.get('price_rising_5d', True)
    bearish_div = indicators.get('bearish_divergence', False)

    # Rule 1: Trend confirmation
    r1 = bool(indicators.get('ema_aligned', price > e10 > e20 > e50))
    # Rule 2: Signal alignment
    r2 = (price > e20) and price_rising
    # Rule 3: Market breadth (fail closed if unknown — do not invent SPY proxies here)
    if market_breadth_pct is not None:
        r3 = market_breadth_pct >= market_threshold
        r3_detail = (
            f"Breadth: {market_breadth_pct:.1f}% above 50-DMA "
            f"(threshold: {market_threshold:.0f}%)"
        )
    else:
        r3 = False
        r3_detail = "Breadth: N/A (no market data)"
    # Rule 4: Sector strength
    if sector_breadth_pct is not None:
        r4 = sector_breadth_pct >= sector_threshold
        r4_detail = (
            f"Sector breadth: {sector_breadth_pct:.1f}% above 50-DMA "
            f"(threshold: {sector_threshold:.0f}%)"
        )
    else:
        r4 = False
        r4_detail = "Sector breadth: N/A (no sector data)"
    # Rule 5: RSI zone
    r5 = 40 <= rsi <= 70
    # Rule 6: Volume
    r6 = vol_ratio > 0.8
    # Rule 7: ATR
    r7 = atr_pct < 8
    # Rule 8: Multi-timeframe
    r8 = bool(indicators.get('multi_tf_aligned', (price > e20) and (price > e100)))
    # Rule 9: No bearish divergence (detect_divergences already requires RSI elevated)
    r9 = not bearish_div

    rules = {
        'Rule 1: Trend Confirmation': {
            'passed': r1,
            'details': f"Price: ${price:.2f}, 10EMA: ${e10:.2f}, 20EMA: ${e20:.2f}, 50EMA: ${e50:.2f}",
        },
        'Rule 2: Signal Alignment': {
            'passed': r2,
            'details': f"Above 20EMA: {price > e20}, 5-day momentum: {price_rising}",
        },
        'Rule 3: Market Breadth': {
            'passed': r3,
            'details': r3_detail,
        },
        'Rule 4: Sector Strength': {
            'passed': r4,
            'details': r4_detail,
        },
        'Rule 5: Behavioral Sentiment': {
            'passed': r5,
            'details': f"RSI: {rsi:.1f} (optimal: 40-70)",
        },
        'Rule 6: Liquidity/Volume': {
            'passed': r6,
            'details': (
                f"Volume ratio: {vol_ratio:.2f}x "
                f"(daily: {indicators.get('daily_volume', 0):,.0f}, "
                f"20d avg: {indicators.get('avg_volume_20d', 0):,.0f})"
            ),
        },
        'Rule 7: Position Sizing (ATR)': {
            'passed': r7,
            'details': f"ATR: ${indicators.get('atr', 0):.2f} ({atr_pct:.1f}% of price)",
        },
        'Rule 8: Multi-Timeframe': {
            'passed': r8,
            'details': f"Above 20EMA: {price > e20}, Above 100EMA: {price > e100}",
        },
        'Rule 9: No Contradictions': {
            'passed': r9,
            'details': (
                f"Bearish divergence: {bearish_div}, RSI: {rsi:.1f}"
            ),
        },
    }

    passed = sum(1 for v in rules.values() if v['passed'])
    return {
        'rules': rules,
        'rules_passed': passed,
        'total_rules': 9,
    }


def nine_rules_signal(rules_passed: int) -> str:
    if rules_passed >= 8:
        return 'STRONG BUY'
    if rules_passed >= 6:
        return 'BUY'
    if rules_passed >= 4:
        return 'NEUTRAL'
    return 'SELL/AVOID'


# ---------------------------------------------------------------------------
# Sector strength composite (from breadth collector metrics)
# ---------------------------------------------------------------------------

def sector_composite_score(metrics: Dict[str, Any]) -> float:
    """
    Multi-metric sector strength score (0-100-ish).

    Weights:
      35%  pct_above_50dma
      20%  breadth_thrust
      20%  ad_ratio (mapped)
      15%  up_down_vol_ratio (mapped)
      10%  net_highs_lows (mapped)
    """
    pct50 = float(metrics.get('pct_above_50dma') or 0)
    thrust = float(metrics.get('breadth_thrust') or 50)
    ad = float(metrics.get('ad_ratio') or 1.0)
    udv = float(metrics.get('up_down_vol_ratio') or 1.0)
    net_hl = float(metrics.get('net_highs_lows') or 0)

    # Map A/D: 0 -> 0, 1 -> 50, 3+ -> 100
    ad_score = max(0.0, min(100.0, (ad / 3.0) * 100.0))
    # Map up/down vol similarly
    udv_score = max(0.0, min(100.0, (udv / 3.0) * 100.0))
    # Net H/L: -10 -> 0, 0 -> 50, +10 -> 100
    nhl_score = max(0.0, min(100.0, 50.0 + (net_hl * 5.0)))

    score = (
        0.35 * pct50
        + 0.20 * thrust
        + 0.20 * ad_score
        + 0.15 * udv_score
        + 0.10 * nhl_score
    )
    return round(score, 2)


def rank_sectors(
    sectors: Dict[str, Dict[str, Any]],
    num: int = 2,
) -> Tuple[list, list, Dict[str, float]]:
    """
    Return (top_sector_names, bottom_sector_names, scores_by_name)
    using composite sector strength.
    """
    scores = {name: sector_composite_score(m) for name, m in sectors.items()}
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = [name for name, _ in ordered[:num]]
    bottom = [name for name, _ in ordered[-num:]]
    # Avoid overlap when few sectors
    bottom = [b for b in bottom if b not in top]
    return top, bottom, scores
