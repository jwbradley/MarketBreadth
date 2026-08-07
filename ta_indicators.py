#!/usr/bin/env python3
"""
Shared technical analysis indicators for MarketBreadth tools.

Used by stock_screener.py and nine_rules_gate.py so scoring and the Nine Rules
see the same RSI, EMA, MACD, ATR, and divergence math.

RSI uses Wilder's smoothing (industry standard).
All EMAs use ewm(span=..., adjust=False).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

MARKET_TZ = ZoneInfo('America/New_York')
MARKET_CLOSE_HOUR = 16


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


# ---------------------------------------------------------------------------
# Partial-bar handling
# ---------------------------------------------------------------------------

def drop_partial_bar(
    hist: pd.DataFrame,
    now_et: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, bool]:
    """
    Remove the final bar when it belongs to a session that has not closed yet.

    yfinance returns a live, still-accumulating bar for the current session. Its
    Volume is only the shares traded so far, so any same-day volume comparison is
    biased low: a 14:30 ET run sees roughly three quarters of a day measured
    against a full-day average, which pushed volume_ratio to a median of 0.47 and
    failed the volume rule on 53 of 60 names for purely clock-related reasons.
    High/Low/Close are likewise provisional.

    Returns (frame, dropped) so callers can record which basis was used.
    """
    if hist is None or hist.empty:
        return hist, False

    now = now_et or datetime.now(MARKET_TZ)
    last_idx = hist.index[-1]

    try:
        last_ts = pd.Timestamp(last_idx)
    except (TypeError, ValueError):
        return hist, False

    # Compare in market time; tz-naive indices are assumed to be market dates.
    if last_ts.tz is None:
        last_session = last_ts.date()
    else:
        last_session = last_ts.tz_convert(MARKET_TZ).date()

    today_et = now.date()
    session_closed = now.hour >= MARKET_CLOSE_HOUR

    if last_session == today_et and not session_closed:
        return hist.iloc[:-1], True
    return hist, False


def session_fraction_elapsed(now_et: Optional[datetime] = None) -> float:
    """
    Fraction of the regular 09:30-16:00 ET session completed, 0.0-1.0.

    Used to pro-rate a still-forming bar's volume. A 10:30 ET run has only about
    15% of the day's shares in hand, so comparing that raw figure against a
    full-day 20-day average understates participation by roughly 6x.

    Volume is front- and back-loaded (the open and close are the busiest
    stretches), so elapsed clock time understates the true fraction early in the
    day. A mild curve corrects for that without pretending to be a real
    intraday volume profile.
    """
    now = now_et or datetime.now(MARKET_TZ)
    minutes = (now.hour * 60 + now.minute) - (9 * 60 + 30)
    total = (MARKET_CLOSE_HOUR * 60) - (9 * 60 + 30)  # 390 minutes
    if minutes <= 0:
        return 0.0
    if minutes >= total:
        return 1.0
    linear = minutes / total
    # U-shaped profile: ~0.20 of volume by the first 10% of the session.
    return float(linear ** 0.72)


def _percentile_rank(series: pd.Series, value: float) -> Optional[float]:
    """Percentile (0-100) of value within series. None when series is too short."""
    clean = series.dropna()
    if len(clean) < 20:
        return None
    return round(float((clean <= value).sum()) / len(clean) * 100.0, 1)


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
    use_complete_bars: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Compute a full indicator dict from a history DataFrame with
    columns: Open, High, Low, Close, Volume (yfinance style).

    Intraday runs keep the still-forming bar so prices are current, and the
    volume comparison is pro-rated by how much of the session has elapsed. This
    is what makes an hourly schedule useful: dropping the bar instead would make
    every run between 09:30 and 16:00 ET report the prior close, so eight runs a
    day would produce eight identical outputs.

    Set use_complete_bars to drop the live bar and describe only the last closed
    session - the right choice for backtests or exact end-of-day reconciliation.

    Returns None if insufficient data.
    """
    if hist is None or hist.empty:
        return None

    # Flatten MultiIndex columns if present
    if isinstance(hist.columns, pd.MultiIndex):
        hist = hist.copy()
        hist.columns = hist.columns.get_level_values(0)

    partial_dropped = False
    if use_complete_bars:
        hist, partial_dropped = drop_partial_bar(hist)

    if hist is None or hist.empty or len(hist) < min_bars:
        return None

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

    # Is the final bar still forming? If so its volume is partial, and the
    # 20-day average has to be scaled to the same slice of the day to compare.
    _, bar_is_partial = drop_partial_bar(hist)
    bar_is_partial = bar_is_partial and not partial_dropped
    session_frac = session_fraction_elapsed() if bar_is_partial else 1.0

    # Exclude the partial bar from the 20-day average so a half-day of volume
    # does not drag down the very baseline it is measured against.
    vol_for_avg = volume.iloc[:-1] if bar_is_partial else volume
    avg_vol_20 = vol_for_avg.rolling(20).mean()
    avg_vol_val = float(avg_vol_20.iloc[-1]) if not pd.isna(avg_vol_20.iloc[-1]) else 0.0
    daily_vol = float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0.0

    if avg_vol_val <= 0:
        vol_ratio = 0.0
    elif not bar_is_partial:
        vol_ratio = daily_vol / avg_vol_val
    elif session_frac > 0.02:
        vol_ratio = daily_vol / (avg_vol_val * session_frac)
    else:
        # Too early in the session to infer anything from volume.
        vol_ratio = 1.0

    # Dollar volume is a liquidity screen, so it uses the full-day average and
    # never the partial bar.
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

    # --- Extension from the mean -------------------------------------------
    # Two names can both be in a perfect uptrend while one sits 4% above its
    # 50-DMA (a base) and the other 26% above (a chase). Raw percent is not
    # comparable across tickers of different volatility, so extension is also
    # expressed in ATR units and as a percentile of the stock's own past year.
    ext_50 = ((latest_price / s50) - 1.0) * 100.0 if s50 else 0.0
    ext_200 = ((latest_price / s200) - 1.0) * 100.0 if s200 else 0.0
    ext_20 = ((latest_price / s20) - 1.0) * 100.0 if s20 else 0.0

    # ATR normalization breaks down when ATR itself collapses. A name pinned in a
    # 0.4% daily range - the classic signature of a stock under acquisition -
    # produced ext_50dma_atr of 25.0A on an 11.6% move and was flagged CHASE on
    # the strength of a vanishing denominator. Floor the divisor at a plausible
    # fraction of price so a dead-volatility ticker cannot dominate the ranking.
    atr_floor = latest_price * 0.005
    atr_for_norm = max(atr_val, atr_floor) if latest_price else atr_val
    ext_50_atr = (latest_price - s50) / atr_for_norm if atr_for_norm else 0.0
    # Even with the floor, cap the reported figure; beyond ~8 ATR the number is
    # no longer a meaningful distance measure.
    ext_50_atr = max(-8.0, min(8.0, ext_50_atr))

    ext_50_series = ((close / sma50) - 1.0) * 100.0
    ext_50_pctile = _percentile_rank(ext_50_series, ext_50)

    # --- Risk / position sizing --------------------------------------------
    # A 2-ATR stop is the volatility-scaled default. When a recent swing low sits
    # just below that level, the stop is nudged under it instead: resting a stop
    # immediately above an obvious structural low invites getting wicked out.
    # When the swing low is far below (a stock well extended off its base) the
    # 2-ATR stop is kept, since anchoring to that low would mean absurd risk.
    #
    # ATR is also floored here. A stock in a 0.4% daily range yields a 2-ATR stop
    # 0.8% below price, which is inside normal noise and not a survivable stop;
    # a 1.5% minimum keeps the figure honest without overriding real volatility.
    atr_for_stop = max(atr_val, latest_price * 0.0075) if latest_price else atr_val
    stop_2atr = latest_price - (2.0 * atr_for_stop)
    lookback_20 = low.tail(20).dropna()
    swing_low_20 = float(lookback_20.min()) if not lookback_20.empty else stop_2atr

    if stop_2atr - atr_for_stop <= swing_low_20 < stop_2atr:
        stop_price = swing_low_20 - (0.15 * atr_for_stop)
        stop_basis = 'swing_low_20'
    else:
        stop_price = stop_2atr
        stop_basis = '2atr'

    risk_per_share = max(latest_price - stop_price, 0.01)
    risk_pct = (risk_per_share / latest_price) * 100.0 if latest_price else 0.0

    # Nearest overhead resistance: the 52-week high, when it is far enough above
    # price to be a meaningful target. A name at or near new highs has no measurable
    # overhead supply, so rr_ratio is left None rather than reporting the tautology
    # of a 2R projection divided by 1R - that always prints "2.00" and reads like a
    # measurement when it is really an assumption.
    high_52w = float(high.tail(252).max()) if len(high) >= 20 else latest_price
    if high_52w >= latest_price + risk_per_share:
        target_price = high_52w
        target_basis = '52w_high'
        reward_per_share = target_price - latest_price
        rr_ratio = (reward_per_share / risk_per_share) if risk_per_share > 0 else None
    else:
        # Blue sky: no resistance between here and the high.
        target_price = latest_price + (2.0 * risk_per_share)
        target_basis = 'open_no_overhead'
        rr_ratio = None

    # --- Relative volatility ------------------------------------------------
    # atr_pct < 8 passes on essentially every liquid large cap. Comparing ATR to
    # the stock's own 100-day median tells you whether IT is unusually volatile.
    atr_pct_series = (atr_series / close) * 100.0
    atr_pct_median_100 = atr_pct_series.tail(100).median()
    atr_vs_own_median = (
        float(atr_pct / atr_pct_median_100)
        if atr_pct_median_100 and not pd.isna(atr_pct_median_100) and atr_pct_median_100 > 0
        else None
    )

    last_bar_date = None
    try:
        last_bar_date = pd.Timestamp(close.index[-1]).date().isoformat()
    except (TypeError, ValueError, AttributeError):
        pass

    return {
        'price': round(latest_price, 2),
        'bar_date': last_bar_date,
        'partial_bar_dropped': partial_dropped,
        'bar_is_partial': bar_is_partial,
        'session_fraction': round(session_frac, 3),
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
        'atr_vs_own_median': round(atr_vs_own_median, 2) if atr_vs_own_median else None,
        'ext_20dma_pct': round(ext_20, 2),
        'ext_50dma_pct': round(ext_50, 2),
        'ext_200dma_pct': round(ext_200, 2),
        'ext_50dma_atr': round(ext_50_atr, 2),
        'ext_50dma_pctile': ext_50_pctile,
        'stop_price': round(stop_price, 2),
        'stop_basis': stop_basis,
        'stop_2atr': round(stop_2atr, 2),
        'swing_low_20': round(swing_low_20, 2),
        'risk_per_share': round(risk_per_share, 2),
        'risk_pct': round(risk_pct, 2),
        'target_price': round(target_price, 2),
        'target_basis': target_basis,
        'rr_ratio': round(rr_ratio, 2) if rr_ratio is not None else None,
        'high_52w': round(high_52w, 2),
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
# Nine Rules (shared) - used by screener and nine_rules_gate
# ---------------------------------------------------------------------------

def evaluate_nine_rules(
    indicators: Dict[str, Any],
    market_breadth_pct: Optional[float] = None,
    sector_breadth_pct: Optional[float] = None,
    market_threshold: float = 50.0,
    sector_threshold: float = 50.0,
    liquidity_floor: float = 20_000_000.0,
) -> Dict[str, Any]:
    """
    Evaluate multi-factor technical nine rules from a precomputed indicator dict.

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
    # Rule 3: Market breadth (fail closed if unknown - do not invent SPY proxies here)
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
    # Rule 6: Liquidity - tradeable size AND participation.
    # The old test was volume_ratio > 0.8 alone, which on a mid-session run
    # compared a partial bar against a full-day average and failed ~88% of
    # names for clock reasons. Dollar volume is the part that actually decides
    # whether a position can be entered and exited; the participation leg is
    # kept but loosened, since a quiet drift higher is not a disqualifier.
    dollar_vol = indicators.get('dollar_volume_20d') or 0.0
    r6_liquid = dollar_vol >= liquidity_floor
    r6_participation = vol_ratio > 0.6
    r6 = r6_liquid and r6_participation
    # Rule 7: Position sizing - volatility relative to the stock's own norm.
    # atr_pct < 8 passed 60/60 on liquid large caps, making the rule a constant.
    # A name trading at >1.5x its own 100-day median ATR is genuinely harder to
    # size, whatever its absolute ATR happens to be.
    atr_rel = indicators.get('atr_vs_own_median')
    if atr_rel is not None:
        r7 = atr_pct < 8 and atr_rel < 1.5
        r7_detail = (
            f"ATR: ${indicators.get('atr', 0):.2f} ({atr_pct:.1f}% of price), "
            f"{atr_rel:.2f}x own 100d median (elevated above 1.5x)"
        )
    else:
        r7 = atr_pct < 8
        r7_detail = f"ATR: ${indicators.get('atr', 0):.2f} ({atr_pct:.1f}% of price)"
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
                f"${dollar_vol/1e6:.0f}M 20d dollar vol "
                f"(floor ${liquidity_floor/1e6:.0f}M): "
                f"{'OK' if r6_liquid else 'THIN'}; "
                f"volume ratio: {vol_ratio:.2f}x "
                f"(needs >0.60){'' if r6_participation else ' - LOW'}"
            ),
        },
        'Rule 7: Position Sizing (ATR)': {
            'passed': r7,
            'details': r7_detail,
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
# Two-axis scoring: setup quality vs entry timing
# ---------------------------------------------------------------------------
#
# The previous single 0-100 composite saturated: eight names printed exactly 100
# and the raw values behind them ran 99-107 before clipping, so the top of the
# list was effectively unranked. Worse, the one number could not distinguish a
# stock consolidating 4% above its 50-DMA from one stretched 26% above it -
# structurally identical, opposite entry decisions.
#
# Setup Quality  = is this a good business/trend to own? (structural, slow)
# Entry Timing   = is right now a good moment to buy it? (extension, fast)
#
# Keeping them separate means "great setup, terrible entry" stays visible
# instead of averaging into a meaningless mid-70s number.

class _Budget:
    """
    Accumulates a score alongside the minimum and maximum it could have reached
    given the terms that actually applied to this name.

    Normalizing against a fixed divisor was the earlier approach and it clipped:
    18 of 60 names pinned at 100 and the ranking went flat exactly at the top,
    where discrimination matters most. Tracking the achievable range per name
    also means a ticker missing an optional input (no RS history, no sector
    breadth) is not measured against points it never had a chance to earn.
    """

    __slots__ = ('score', 'lo', 'hi')

    def __init__(self, base: float) -> None:
        self.score = self.lo = self.hi = float(base)

    def add(self, value: float, low: float, high: float) -> None:
        self.score += float(value)
        self.lo += float(low)
        self.hi += float(high)

    def normalized(self) -> float:
        span = self.hi - self.lo
        if span <= 0:
            return 50.0
        return max(0.0, min(100.0, ((self.score - self.lo) / span) * 100.0))


def setup_quality_score(
    indicators: Dict[str, Any],
    sector_ad_ratio: Optional[float] = None,
    sector_type: str = 'top',
) -> float:
    """
    Structural quality of the setup, 0-100.

    Deliberately excludes extension and overbought measures - those belong to
    entry timing, not to whether the trend itself is sound.

    Every term declares the range it could have contributed, and the total is
    mapped from that achievable range onto 0-100. Relative strength enters
    continuously rather than in steps, because bucketed scoring flattened the
    ranking right where it needs to separate names.
    """
    top = sector_type == 'top'
    b = _Budget(50.0)

    b.add((indicators['trend_score'] - 1.5) * 10, -15.0, 15.0)

    if indicators['ema_aligned']:
        b.add(7.0, 0.0, 7.0)
    elif indicators['ma_aligned']:
        b.add(4.0, 0.0, 7.0)
    else:
        b.add(0.0, 0.0, 7.0)

    b.add(5.0 if indicators['multi_tf_aligned'] else 0.0, 0.0, 5.0)

    macd_penalty = -6.0 if top else -3.0
    b.add(6.0 if indicators['macd_bullish'] else macd_penalty, macd_penalty, 6.0)

    # Relative strength: the most durable edge here, so it is continuous and
    # carries weight on both horizons. tanh keeps a runaway 60% RS from
    # dominating while still ordering everything below it.
    rs20 = indicators.get('rs_vs_spy')
    if rs20 is not None:
        b.add(9.0 * float(np.tanh(rs20 / 8.0)), -9.0, 9.0)
    rs60 = indicators.get('rs_vs_spy_60')
    if rs60 is not None:
        b.add(7.0 * float(np.tanh(rs60 / 20.0)), -7.0, 7.0)

    # Liquidity, graded continuously on a log scale.
    # $30M -> ~-1, $100M -> ~+1.4, $1B -> ~+4
    dollar_vol = indicators.get('dollar_volume_20d') or 0.0
    if dollar_vol > 0:
        b.add(max(-3.0, min(4.0, (np.log10(dollar_vol) - 7.8) * 4.0)), -3.0, 4.0)

    # Volatility relative to the stock's own norm.
    atr_rel = indicators.get('atr_vs_own_median')
    if atr_rel is not None:
        if atr_rel > 1.8:
            b.add(-5.0, -5.0, 2.0)
        elif atr_rel < 1.1:
            b.add(2.0, -5.0, 2.0)
        else:
            b.add(0.0, -5.0, 2.0)

    div_reward = 8.0 if sector_type == 'bottom' else 4.0
    if indicators['bearish_divergence']:
        b.add(-8.0, -8.0, div_reward)
    elif indicators['bullish_divergence']:
        b.add(div_reward, -8.0, div_reward)
    else:
        b.add(0.0, -8.0, div_reward)

    if sector_ad_ratio is not None:
        if sector_ad_ratio > 3:
            b.add(6.0, -5.0, 6.0)
        elif sector_ad_ratio > 1.5:
            b.add(3.0, -5.0, 6.0)
        elif sector_ad_ratio < 0.5:
            b.add(-5.0, -5.0, 6.0)
        else:
            b.add(0.0, -5.0, 6.0)

    return b.normalized()


def entry_timing_score(
    indicators: Dict[str, Any],
    sector_type: str = 'top',
) -> float:
    """
    How good is *right now* as an entry, 0-100. High = room to run, low = chasing.

    Driven by distance from the mean, Bollinger position, and RSI. A name can
    have a 95 setup and a 20 entry; that is the case the old single score hid.
    Scored against the achievable range so heavily-extended names spread out
    instead of all bottoming out at zero.
    """
    top = sector_type == 'top'
    b = _Budget(50.0)

    # Extension in ATR units is the primary term - volatility-normalized so it
    # compares fairly across a utility and a semiconductor.
    ext_atr = indicators.get('ext_50dma_atr')
    if ext_atr is not None:
        if ext_atr <= 1.0:
            v = 20.0
        elif ext_atr <= 2.0:
            v = 12.0
        elif ext_atr <= 3.0:
            v = 2.0
        elif ext_atr <= 4.5:
            v = -12.0
        else:
            v = -25.0
        b.add(v, -25.0, 20.0)

    # Where does today's extension sit within the stock's own past year?
    pctile = indicators.get('ext_50dma_pctile')
    if pctile is not None:
        if pctile >= 95:
            v = -18.0
        elif pctile >= 85:
            v = -10.0
        elif pctile <= 40:
            v = 10.0
        elif pctile <= 60:
            v = 5.0
        else:
            v = 0.0
        b.add(v, -18.0, 10.0)

    bb = indicators.get('bb_pct', 0.5)
    if top:
        if bb > 0.95:
            v = -15.0
        elif bb > 0.85:
            v = -8.0
        elif 0.3 <= bb <= 0.7:
            v = 10.0
        elif bb < 0.3:
            v = 5.0
        else:
            v = 0.0
        b.add(v, -15.0, 10.0)
    else:
        if bb < 0.1:
            v = 12.0
        elif bb < 0.3:
            v = 6.0
        elif bb > 0.9:
            v = -10.0
        else:
            v = 0.0
        b.add(v, -10.0, 12.0)

    rsi = indicators['rsi']
    if top:
        if rsi > 78:
            v = -15.0
        elif rsi > 72:
            v = -7.0
        elif 45 <= rsi <= 65:
            v = 8.0
        elif rsi < 35:
            v = 4.0
        else:
            v = 0.0
        b.add(v, -15.0, 8.0)
    else:
        if rsi < 30:
            v = 12.0
        elif rsi < 40:
            v = 6.0
        elif rsi > 70:
            v = -10.0
        else:
            v = 0.0
        b.add(v, -10.0, 12.0)

    # Volume confirmation on the entry bar.
    vr = indicators.get('volume_ratio', 1.0)
    if vr > 1.5:
        v = 5.0
    elif vr < 0.5:
        v = -3.0
    else:
        v = 0.0
    b.add(v, -3.0, 5.0)

    return b.normalized()


def entry_label(setup: float, timing: float, sector_type: str = 'top') -> str:
    """
    Combine the two axes into an actionable phrase.

    The point of the split: a strong setup with poor timing reads
    'STRONG - WAIT FOR PULLBACK' rather than being averaged into 'Neutral'.
    """
    strong_setup = setup >= 70
    ok_setup = setup >= 55

    if sector_type == 'top':
        if strong_setup and timing >= 65:
            return 'BUY NOW'
        if strong_setup and timing >= 45:
            return 'BUY / SCALE IN'
        if strong_setup:
            return 'STRONG - WAIT FOR PULLBACK'
        if ok_setup and timing >= 65:
            return 'SPECULATIVE ENTRY'
        if ok_setup:
            return 'WATCH'
        return 'AVOID'

    # Weak-sector names: timing matters more, since the thesis is mean reversion.
    if strong_setup and timing >= 65:
        return 'RS LEADER - ENTRY OK'
    if strong_setup:
        return 'RS LEADER - EXTENDED'
    if ok_setup and timing >= 70:
        return 'REVERSAL WATCH'
    if ok_setup:
        return 'WATCH'
    return 'AVOID / SHORT BIAS'


def extension_flag(indicators: Dict[str, Any]) -> Optional[str]:
    """Short human tag for how stretched price is. None when unremarkable."""
    # A stock whose ATR has collapsed to a fraction of its own norm is usually
    # pinned by a pending acquisition. Its technicals are not tradeable signals,
    # and that matters more to the reader than how far it sits from a mean.
    atr_rel = indicators.get('atr_vs_own_median')
    atr_pct = indicators.get('atr_pct')
    if atr_rel is not None and atr_rel < 0.35 and (atr_pct or 0) < 1.0:
        return 'NO-VOL'

    ext_atr = indicators.get('ext_50dma_atr')
    pctile = indicators.get('ext_50dma_pctile')
    if ext_atr is None:
        return None
    if ext_atr > 4.5 or (pctile is not None and pctile >= 95):
        return 'CHASE'
    if ext_atr > 3.0 or (pctile is not None and pctile >= 85):
        return 'EXTENDED'
    if ext_atr < 0.5:
        return 'AT-MEAN'
    return None


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
