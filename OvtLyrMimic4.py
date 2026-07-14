#!/usr/bin/env python3
"""
OVTLYR Nine Rules Analysis — v4 (independent universe; lives in MarketBreadth)

Re-scores names independently of the funnel path in OvtLyrMimic.py so you can
compare core book vs what stock_screener bubbled. Optionally *reads* local
watchlist / breadth JSON — does not require re-running collectors first.

Universe layers (combine freely):
  1. Core always     Mag7 + liquid large-caps + sector ETFs (+ SPY/QQQ/GLD/SLV)
  2. Personal book   tickers.txt (or --file) — one symbol per line
  3. Screener feed   --watchlist PATH to ovtlyr_watchlist.json
  4. CLI ad-hoc      --tickers AAPL FOO BAR

Defaults:
  python3 OvtLyrMimic4.py
      → core only (or core + personal file if present)

  python3 OvtLyrMimic4.py --union-watchlist
      → core ∪ personal ∪ screener watchlist (best for match checks)

  python3 OvtLyrMimic4.py --watchlist-only
      → only what bubbled from the screener

Daily cron (getTodaysStockScreenerData.sh) writes:
  logs/MimicOVTLR-DailyOutput.log

Improvements vs standalone OvtLyrMimic3:
  - Dynamic universe (CLI / file / watchlist / union)
  - Wilder RSI + nine-rules math aligned with ta_indicators
  - Real market/sector breadth when market_breadth_latest.json is available
  - SPY downloaded once and reused
  - ATM IV expected move (optional)
  - Overlap report: core vs screener
  - Dated reports default under logs/
  - Verbose / briefing / min-score filters

Usage examples:
  python3 OvtLyrMimic4.py
  python3 OvtLyrMimic4.py --tickers SMCI ARM TSM
  python3 OvtLyrMimic4.py --file my_tickers.txt
  python3 OvtLyrMimic4.py --union-watchlist
  python3 OvtLyrMimic4.py --watchlist-only --verbose
  python3 OvtLyrMimic4.py --no-expected-move --briefing
  python3 OvtLyrMimic4.py --output logs/custom.txt
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
from contextlib import redirect_stdout
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip install yfinance pandas numpy")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths (same DATA_DIR convention as OvtLyrMimic.py / stock_screener.py)
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get(
    "MARKET_BREADTH_DIR",
    os.environ.get("GSR_DATA_DIR", SCRIPT_DIR),
)
LOGS_DIR = os.path.join(DATA_DIR, "logs")
DEFAULT_PERSONAL_FILE = os.path.join(DATA_DIR, "tickers.txt")
DEFAULT_WATCHLIST = os.path.join(DATA_DIR, "ovtlyr_watchlist.json")
DEFAULT_BREADTH = os.path.join(DATA_DIR, "market_breadth_latest.json")
DEFAULT_CONSTITUENTS = os.path.join(DATA_DIR, "sp500_constituents.csv")
DEFAULT_DAILY_LOG = os.path.join(LOGS_DIR, "MimicOVTLR-DailyOutput.log")

TRADING_DAYS_PER_YEAR = 252.0

# Prefer shared ta_indicators in this package (identical scoring).
# Fall back to embedded copies if import fails.
_HAS_SHARED_TA = False
try:
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    from ta_indicators import (  # type: ignore  # noqa: E402
        calculate_from_ohlcv as _shared_calculate_from_ohlcv,
        evaluate_nine_rules as _shared_evaluate_nine_rules,
        nine_rules_signal as _shared_nine_rules_signal,
    )
    _HAS_SHARED_TA = True
except Exception:
    _HAS_SHARED_TA = False


# ---------------------------------------------------------------------------
# Core universe (intentional static layer — liquid / always-on book)
# Speculative names belong in tickers.txt, not here.
# ---------------------------------------------------------------------------

MAGNIFICENT_SEVEN = ["AAPL", "AMZN", "GOOGL", "MSFT", "META", "NVDA", "TSLA"]

CORE_LARGE_CAPS = [
    "AMD", "AVGO", "BRK-B", "COST", "CSCO", "HD", "INTC", "LOW",
    "MU", "NFLX", "ORCL", "PYPL", "TGT", "UNP", "WMT", "APP", "PLTR",
    "CRM", "JPM", "V", "MA", "LLY", "XOM",
]

INDEX_AND_COMMODITY_ETFS = ["SPY", "QQQ", "GLD", "SLV"]

SECTOR_ETFS = [
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
]

CORE_TICKERS: List[str] = (
    MAGNIFICENT_SEVEN + CORE_LARGE_CAPS + INDEX_AND_COMMODITY_ETFS + SECTOR_ETFS
)

SECTOR_ETF_SET = set(SECTOR_ETFS)
CONTEXT_ETF_SET = set(INDEX_AND_COMMODITY_ETFS) | SECTOR_ETF_SET


# ---------------------------------------------------------------------------
# Embedded TA (used only if MarketBreadth ta_indicators is unavailable)
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def _rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = _ema(close, 12) - _ema(close, 26)
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal, macd_line - signal


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _relative_strength(
    stock_close: pd.Series, bench_close: pd.Series, lookback: int = 20
) -> Optional[float]:
    if stock_close is None or bench_close is None:
        return None
    if len(stock_close) < lookback + 1 or len(bench_close) < lookback + 1:
        return None
    s = (float(stock_close.iloc[-1]) / float(stock_close.iloc[-lookback]) - 1) * 100
    b = (float(bench_close.iloc[-1]) / float(bench_close.iloc[-lookback]) - 1) * 100
    return round(s - b, 2)


def _detect_divergences(close: pd.Series, rsi: pd.Series, lookback: int = 5) -> Dict[str, bool]:
    if len(close) < lookback + 1 or len(rsi) < lookback + 1:
        return {"bearish_divergence": False, "bullish_divergence": False}
    price = float(close.iloc[-1])
    price_ago = float(close.iloc[-lookback])
    current_rsi = float(rsi.iloc[-1])
    rsi_ago = float(rsi.iloc[-lookback])
    price_rising = price > price_ago
    rsi_rising = current_rsi > rsi_ago
    return {
        "bearish_divergence": price_rising and (not rsi_rising) and current_rsi > 65.0,
        "bullish_divergence": (not price_rising) and rsi_rising and current_rsi < 35.0,
    }


def _embedded_calculate_from_ohlcv(
    hist: pd.DataFrame,
    spy_close: Optional[pd.Series] = None,
    min_bars: int = 200,
) -> Optional[Dict[str, Any]]:
    if hist is None or hist.empty or len(hist) < min_bars:
        return None
    if isinstance(hist.columns, pd.MultiIndex):
        hist = hist.copy()
        hist.columns = hist.columns.get_level_values(0)
    required = {"High", "Low", "Close", "Volume"}
    if not required.issubset(set(hist.columns)):
        return None

    close = hist["Close"].dropna()
    high, low, volume = hist["High"], hist["Low"], hist["Volume"]
    if len(close) < min_bars:
        return None

    latest = float(close.iloc[-1])
    e10, e20, e50, e100 = _ema(close, 10), _ema(close, 20), _ema(close, 50), _ema(close, 100)
    s20, s50, s200 = _sma(close, 20), _sma(close, 50), _sma(close, 200)
    rsi = _rsi_wilder(close, 14)
    macd_line, signal_line, macd_hist = _macd(close)
    atr_s = _atr(high, low, close, 14)
    atr_val = float(atr_s.iloc[-1])
    atr_pct = (atr_val / latest) * 100 if latest else 0.0
    avg_vol = float(volume.rolling(20).mean().iloc[-1] or 0)
    daily_vol = float(volume.iloc[-1] or 0)
    vol_ratio = (daily_vol / avg_vol) if avg_vol > 0 else 0.0
    current_rsi = float(rsi.iloc[-1])
    price_5d = float(close.iloc[-5]) if len(close) >= 5 else latest
    divs = _detect_divergences(close, rsi)

    fe10, fe20, fe50, fe100 = (
        float(e10.iloc[-1]), float(e20.iloc[-1]), float(e50.iloc[-1]), float(e100.iloc[-1])
    )
    return {
        "price": round(latest, 2),
        "ema10": round(fe10, 2),
        "ema20": round(fe20, 2),
        "ema50": round(fe50, 2),
        "ema100": round(fe100, 2),
        "sma20": round(float(s20.iloc[-1]), 2),
        "sma50": round(float(s50.iloc[-1]), 2),
        "sma200": round(float(s200.iloc[-1]), 2),
        "ema_aligned": latest > fe10 > fe20 > fe50,
        "multi_tf_aligned": (latest > fe20) and (latest > fe100),
        "rsi": round(current_rsi, 1),
        "macd": round(float(macd_line.iloc[-1]), 3),
        "macd_signal": round(float(signal_line.iloc[-1]), 3),
        "macd_hist": round(float(macd_hist.iloc[-1]), 3),
        "macd_bullish": float(macd_line.iloc[-1]) > float(signal_line.iloc[-1]),
        "atr": round(atr_val, 2),
        "atr_pct": round(atr_pct, 2),
        "volume_ratio": round(vol_ratio, 2),
        "avg_volume_20d": int(avg_vol),
        "daily_volume": int(daily_vol),
        "rs_vs_spy": _relative_strength(close, spy_close, 20) if spy_close is not None else None,
        "rs_vs_spy_60": _relative_strength(close, spy_close, 60) if spy_close is not None else None,
        "price_rising_5d": latest > price_5d,
        "bearish_divergence": divs["bearish_divergence"],
        "bullish_divergence": divs["bullish_divergence"],
    }


def _embedded_evaluate_nine_rules(
    indicators: Dict[str, Any],
    market_breadth_pct: Optional[float] = None,
    sector_breadth_pct: Optional[float] = None,
    market_threshold: float = 50.0,
    sector_threshold: float = 50.0,
) -> Dict[str, Any]:
    price = indicators["price"]
    e10, e20, e50 = indicators["ema10"], indicators["ema20"], indicators["ema50"]
    e100 = indicators.get("ema100") or e50
    rsi = indicators["rsi"]
    vol_ratio = indicators["volume_ratio"]
    atr_pct = indicators["atr_pct"]
    price_rising = indicators.get("price_rising_5d", True)
    bearish_div = indicators.get("bearish_divergence", False)

    r1 = bool(indicators.get("ema_aligned", price > e10 > e20 > e50))
    r2 = (price > e20) and price_rising
    if market_breadth_pct is not None:
        r3 = market_breadth_pct >= market_threshold
        r3d = f"Breadth: {market_breadth_pct:.1f}% above 50-DMA (threshold: {market_threshold:.0f}%)"
    else:
        r3 = False
        r3d = "Breadth: N/A (no market data)"
    if sector_breadth_pct is not None:
        r4 = sector_breadth_pct >= sector_threshold
        r4d = (
            f"Sector breadth: {sector_breadth_pct:.1f}% above 50-DMA "
            f"(threshold: {sector_threshold:.0f}%)"
        )
    else:
        r4 = False
        r4d = "Sector breadth: N/A (no sector data)"
    r5 = 40 <= rsi <= 70
    r6 = vol_ratio > 0.8
    r7 = atr_pct < 8
    r8 = bool(indicators.get("multi_tf_aligned", (price > e20) and (price > e100)))
    r9 = not bearish_div

    rules = {
        "Rule 1: Trend Confirmation": {
            "passed": r1,
            "details": f"Price: ${price:.2f}, 10EMA: ${e10:.2f}, 20EMA: ${e20:.2f}, 50EMA: ${e50:.2f}",
        },
        "Rule 2: Signal Alignment": {
            "passed": r2,
            "details": f"Above 20EMA: {price > e20}, 5-day momentum: {price_rising}",
        },
        "Rule 3: Market Breadth": {"passed": r3, "details": r3d},
        "Rule 4: Sector Strength": {"passed": r4, "details": r4d},
        "Rule 5: Behavioral Sentiment": {
            "passed": r5,
            "details": f"RSI: {rsi:.1f} (optimal: 40-70)",
        },
        "Rule 6: Liquidity/Volume": {
            "passed": r6,
            "details": (
                f"Volume ratio: {vol_ratio:.2f}x "
                f"(daily: {indicators.get('daily_volume', 0):,.0f}, "
                f"20d avg: {indicators.get('avg_volume_20d', 0):,.0f})"
            ),
        },
        "Rule 7: Position Sizing (ATR)": {
            "passed": r7,
            "details": f"ATR: ${indicators.get('atr', 0):.2f} ({atr_pct:.1f}% of price)",
        },
        "Rule 8: Multi-Timeframe": {
            "passed": r8,
            "details": f"Above 20EMA: {price > e20}, Above 100EMA: {price > e100}",
        },
        "Rule 9: No Contradictions": {
            "passed": r9,
            "details": f"Bearish divergence: {bearish_div}, RSI: {rsi:.1f}",
        },
    }
    passed = sum(1 for v in rules.values() if v["passed"])
    return {"rules": rules, "rules_passed": passed, "total_rules": 9}


def _embedded_nine_rules_signal(rules_passed: int) -> str:
    if rules_passed >= 8:
        return "STRONG BUY"
    if rules_passed >= 6:
        return "BUY"
    if rules_passed >= 4:
        return "NEUTRAL"
    return "SELL/AVOID"


def calculate_from_ohlcv(hist, spy_close=None, min_bars=200):
    if _HAS_SHARED_TA:
        return _shared_calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=min_bars)
    return _embedded_calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=min_bars)


def evaluate_nine_rules(indicators, market_breadth_pct=None, sector_breadth_pct=None, **kw):
    if _HAS_SHARED_TA:
        return _shared_evaluate_nine_rules(
            indicators,
            market_breadth_pct=market_breadth_pct,
            sector_breadth_pct=sector_breadth_pct,
            **kw,
        )
    return _embedded_evaluate_nine_rules(
        indicators,
        market_breadth_pct=market_breadth_pct,
        sector_breadth_pct=sector_breadth_pct,
        **kw,
    )


def nine_rules_signal(rules_passed: int) -> str:
    if _HAS_SHARED_TA:
        return _shared_nine_rules_signal(rules_passed)
    return _embedded_nine_rules_signal(rules_passed)


# ---------------------------------------------------------------------------
# Data loaders (optional MarketBreadth files — soft fail)
# ---------------------------------------------------------------------------

def load_json(path: str) -> Optional[dict]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not read {path}: {e}")
        return None


def load_sector_map(constituents_path: str = DEFAULT_CONSTITUENTS) -> Dict[str, str]:
    if not os.path.exists(constituents_path):
        return {}
    try:
        df = pd.read_csv(constituents_path)
        mapping = {}
        for _, row in df.iterrows():
            sym = str(row["Symbol"]).replace(".", "-")
            mapping[sym] = row["GICS Sector"]
        return mapping
    except Exception:
        return {}


def get_sector_breadth(breadth_data: Optional[dict], sector_name: Optional[str]) -> Optional[float]:
    if not breadth_data or not sector_name:
        return None
    sectors = breadth_data.get("sectors") or {}
    if sector_name in sectors:
        return sectors[sector_name].get("pct_above_50dma")
    return None


def load_tickers_file(path: str) -> List[str]:
    """One ticker per line; # comments and blanks ignored."""
    if not path or not os.path.exists(path):
        return []
    out: List[str] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # allow "AAPL  # note" or "AAPL,MSFT"
            token = line.split("#", 1)[0].strip()
            for part in token.replace(",", " ").split():
                t = part.strip().upper().replace(".", "-")
                if t:
                    out.append(t)
    return out


def load_watchlist_stocks(
    path: str,
    min_score: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Optional[dict]]:
    """
    Return (list of stock dicts with at least 'ticker', raw watchlist dict or None).
    Accepts MarketBreadth ovtlyr_watchlist.json shape.
    """
    data = load_json(path)
    if not data:
        return [], None
    stocks = data.get("stocks") or []
    out = []
    for s in stocks:
        if isinstance(s, str):
            out.append({"ticker": s.upper().replace(".", "-"), "source": "watchlist"})
            continue
        ticker = str(s.get("ticker", "")).upper().replace(".", "-")
        if not ticker:
            continue
        if min_score is not None and s.get("score") is not None:
            try:
                if float(s["score"]) < min_score:
                    continue
            except (TypeError, ValueError):
                pass
        item = dict(s)
        item["ticker"] = ticker
        item["source"] = item.get("source") or "watchlist"
        out.append(item)
    return out, data


# ---------------------------------------------------------------------------
# Expected move (ATM IV)
# ---------------------------------------------------------------------------

def _sorted_expirations(expirations: List[str], prefer_min_dte: int = 1) -> List[str]:
    today = date.today()
    scored = []
    for exp_str in expirations:
        try:
            exp_d = datetime.strptime(exp_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        dte = (exp_d - today).days
        if dte < prefer_min_dte:
            continue
        scored.append((dte, exp_str))
    scored.sort(key=lambda x: x[0])
    return [e for _, e in scored]


def _atm_iv_from_chain(side: pd.DataFrame, price: float) -> Optional[float]:
    if side is None or side.empty or price <= 0:
        return None
    if "strike" not in side.columns or "impliedVolatility" not in side.columns:
        return None
    work = side.dropna(subset=["strike", "impliedVolatility"]).copy()
    if work.empty:
        return None
    if "openInterest" in work.columns:
        oi = work["openInterest"].fillna(0)
        if (oi > 0).any():
            work = work.loc[oi > 0]
    if work.empty:
        return None
    atm_idx = (work["strike"] - price).abs().idxmin()
    iv = float(work.loc[atm_idx, "impliedVolatility"])
    if not math.isfinite(iv) or iv < 0.05 or iv > 5.0:
        return None
    return iv


def _iv_from_expiration(stock: yf.Ticker, exp_str: str, price: float) -> Optional[float]:
    try:
        chain = stock.option_chain(exp_str)
    except Exception:
        return None
    iv = _atm_iv_from_chain(chain.calls, price)
    if iv is None and getattr(chain, "puts", None) is not None:
        iv = _atm_iv_from_chain(chain.puts, price)
    return iv


def get_expected_move(
    ticker: str, price: float, max_expirations_to_try: int = 5
) -> Optional[Dict[str, Any]]:
    if price is None or price <= 0:
        return None
    try:
        stock = yf.Ticker(ticker)
        expirations = _sorted_expirations(list(stock.options or []), prefer_min_dte=1)
        if not expirations:
            return None
        iv = None
        exp_str = None
        for candidate in expirations[:max_expirations_to_try]:
            trial = _iv_from_expiration(stock, candidate, price)
            if trial is not None:
                iv = trial
                exp_str = candidate
                break
        if iv is None or exp_str is None:
            return None
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        dte = max((exp_date - date.today()).days, 1)
        sqrt_year = math.sqrt(TRADING_DAYS_PER_YEAR)
        daily = (price * iv) / sqrt_year
        weekly = (price * iv * math.sqrt(5.0)) / sqrt_year
        to_exp = (price * iv * math.sqrt(float(dte))) / sqrt_year
        return {
            "iv": round(iv * 100.0, 2),
            "iv_decimal": iv,
            "daily_move": round(daily, 2),
            "daily_pct": round((daily / price) * 100.0, 2),
            "weekly_move": round(weekly, 2),
            "weekly_pct": round((weekly / price) * 100.0, 2),
            "exp_move": round(to_exp, 2),
            "exp_pct": round((to_exp / price) * 100.0, 2),
            "dte": dte,
            "expiration": exp_str,
            "price_used": round(price, 2),
        }
    except Exception:
        return None


def attach_expected_moves(results: List[Dict[str, Any]], verbose: bool = True) -> None:
    if not results:
        return
    if verbose:
        print(f"\nFetching ATM IV / expected move for {len(results)} ticker(s)...")
    for r in results:
        ticker = r["ticker"]
        price = r.get("price")
        if not price or price <= 0:
            r["expected_move"] = None
            if verbose:
                print(f"  {ticker}: skipped (no price)")
            continue
        em = get_expected_move(ticker, float(price))
        r["expected_move"] = em
        if verbose:
            if em:
                print(
                    f"  {ticker}: IV {em['iv']:.1f}% | "
                    f"daily ±${em['daily_move']:.2f} ({em['daily_pct']:.1f}%) | "
                    f"exp {em['expiration']} ({em['dte']} DTE)"
                )
            else:
                print(f"  {ticker}: expected move unavailable")


# ---------------------------------------------------------------------------
# Universe assembly
# ---------------------------------------------------------------------------

TickerEntry = Dict[str, Any]


def _normalize_ticker(t: str) -> str:
    return str(t).strip().upper().replace(".", "-")


def _entry(ticker: str, source: str, **extra) -> TickerEntry:
    e: TickerEntry = {"ticker": _normalize_ticker(ticker), "source": source}
    e.update(extra)
    return e


def build_universe(
    include_core: bool = True,
    personal_path: Optional[str] = None,
    watchlist_path: Optional[str] = None,
    watchlist_only: bool = False,
    union_watchlist: bool = False,
    cli_tickers: Optional[Sequence[str]] = None,
    min_score: Optional[float] = None,
) -> Tuple[List[TickerEntry], Dict[str, Any]]:
    """
    Build de-duplicated universe with provenance.

    Modes:
      watchlist_only  → only watchlist (ignore core/personal unless also on CLI)
      union_watchlist → core ∪ personal ∪ watchlist ∪ CLI
      default         → core (if include_core) ∪ personal ∪ CLI
                        (+ watchlist if --watchlist given without --watchlist-only)
    """
    meta: Dict[str, Any] = {
        "sources_used": [],
        "core_tickers": set(),
        "watchlist_tickers": set(),
        "personal_tickers": set(),
        "cli_tickers": set(),
        "watchlist_raw": None,
    }
    by_ticker: Dict[str, TickerEntry] = {}

    def add_many(items: Sequence[Union[str, TickerEntry]], default_source: str) -> None:
        for item in items:
            if isinstance(item, str):
                e = _entry(item, default_source)
            else:
                e = dict(item)
                e["ticker"] = _normalize_ticker(e["ticker"])
                e.setdefault("source", default_source)
            t = e["ticker"]
            if t in by_ticker:
                # Merge sources for overlap reporting
                prev = by_ticker[t]
                srcs = set(str(prev.get("source", "")).split("+"))
                srcs.add(e["source"])
                # Prefer watchlist metadata when merging
                merged = dict(prev)
                for k, v in e.items():
                    if k == "source":
                        continue
                    if merged.get(k) is None and v is not None:
                        merged[k] = v
                merged["source"] = "+".join(sorted(s for s in srcs if s))
                by_ticker[t] = merged
            else:
                by_ticker[t] = e

    # CLI always wins as an add
    if cli_tickers:
        cleaned = [_normalize_ticker(t) for t in cli_tickers if t]
        add_many(cleaned, "cli")
        meta["cli_tickers"] = set(cleaned)
        meta["sources_used"].append("cli")

    use_watchlist = bool(watchlist_path) or watchlist_only or union_watchlist
    wl_path = watchlist_path or DEFAULT_WATCHLIST

    if watchlist_only:
        stocks, raw = load_watchlist_stocks(wl_path, min_score=min_score)
        if not stocks:
            print(f"Warning: watchlist empty or missing: {wl_path}")
        add_many(stocks, "watchlist")
        meta["watchlist_tickers"] = {s["ticker"] for s in stocks}
        meta["watchlist_raw"] = raw
        meta["sources_used"].append("watchlist")
        # CLI still allowed on top
        if cli_tickers:
            pass  # already added
    else:
        if include_core:
            add_many(CORE_TICKERS, "core")
            meta["core_tickers"] = set(CORE_TICKERS)
            meta["sources_used"].append("core")

        ppath = personal_path
        if ppath is None and os.path.exists(DEFAULT_PERSONAL_FILE):
            ppath = DEFAULT_PERSONAL_FILE
        if ppath:
            personal = load_tickers_file(ppath)
            if personal:
                add_many(personal, "personal")
                meta["personal_tickers"] = set(personal)
                meta["sources_used"].append(f"personal:{ppath}")

        if union_watchlist or (watchlist_path and not watchlist_only):
            stocks, raw = load_watchlist_stocks(wl_path, min_score=min_score)
            if stocks:
                add_many(stocks, "watchlist")
                meta["watchlist_tickers"] = {s["ticker"] for s in stocks}
                meta["watchlist_raw"] = raw
                meta["sources_used"].append(f"watchlist:{wl_path}")
            elif union_watchlist:
                print(f"Warning: --union-watchlist but no stocks at {wl_path}")

    # Stable order: core order first, then others alpha
    core_order = {t: i for i, t in enumerate(CORE_TICKERS)}
    ordered = sorted(
        by_ticker.values(),
        key=lambda e: (
            0 if e["ticker"] in core_order else 1,
            core_order.get(e["ticker"], 9999),
            e["ticker"],
        ),
    )
    return ordered, meta


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_ticker(
    ticker: str,
    market_breadth_pct: Optional[float] = None,
    sector_breadth_pct: Optional[float] = None,
    spy_close: Optional[pd.Series] = None,
    period: str = "1y",
) -> Optional[Dict[str, Any]]:
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return None

    min_bars = 200 if period in ("1y", "2y", "max") else 100
    indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=min_bars)
    if indicators is None and min_bars > 100:
        indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=100)
    if indicators is None:
        return None

    mb = market_breadth_pct
    # Soft SPY fallback only when no real breadth file
    if mb is None and spy_close is not None and len(spy_close) >= 50:
        spy_ema50 = float(spy_close.ewm(span=50, adjust=False).mean().iloc[-1])
        spy_price = float(spy_close.iloc[-1])
        mb = 60.0 if spy_price > spy_ema50 else 40.0

    rules_out = evaluate_nine_rules(
        indicators,
        market_breadth_pct=mb,
        sector_breadth_pct=sector_breadth_pct,
    )
    passed = rules_out["rules_passed"]
    signal = nine_rules_signal(passed)

    return {
        "ticker": ticker,
        "signal": signal,
        "rules_passed": passed,
        "total_rules": rules_out["total_rules"],
        "percentage": round((passed / rules_out["total_rules"]) * 100, 1),
        "rs_vs_spy": indicators.get("rs_vs_spy"),
        "price": indicators.get("price"),
        "rsi": indicators.get("rsi"),
        "details": rules_out["rules"],
        "indicators": indicators,
        "expected_move": None,
        "market_breadth_used": mb,
        "sector_breadth_used": sector_breadth_pct,
    }


def run_analysis(
    entries: List[TickerEntry],
    market_breadth_pct: Optional[float] = None,
    breadth_data: Optional[dict] = None,
    sector_map: Optional[Dict[str, str]] = None,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    sector_map = sector_map or {}
    try:
        spy_hist = yf.Ticker("SPY").history(period="1y", auto_adjust=True)
        spy_close = spy_hist["Close"] if not spy_hist.empty else None
    except Exception:
        spy_close = None

    results: List[Dict[str, Any]] = []
    for entry in entries:
        ticker = entry["ticker"]
        sector = entry.get("sector") or sector_map.get(ticker)
        sector_breadth = entry.get("sector_breadth_pct")
        if sector_breadth is None and sector:
            sector_breadth = get_sector_breadth(breadth_data, sector)

        # Sector ETFs: use market breadth as sector proxy when no GICS sector
        if sector_breadth is None and ticker in SECTOR_ETF_SET and market_breadth_pct is not None:
            sector_breadth = market_breadth_pct

        if verbose:
            src = entry.get("source", "?")
            print(f"  Analyzing {ticker:<6} [{src}]...", end=" ", flush=True)

        result = analyze_ticker(
            ticker,
            market_breadth_pct=market_breadth_pct,
            sector_breadth_pct=sector_breadth,
            spy_close=spy_close,
        )
        if result:
            result["sector"] = sector
            result["source"] = entry.get("source")
            result["screener_score"] = entry.get("score")
            result["screener_signal"] = entry.get("signal")
            result["kind"] = (
                "sector_etf" if ticker in SECTOR_ETF_SET
                else ("context_etf" if ticker in CONTEXT_ETF_SET else "stock")
            )
            results.append(result)
            if verbose:
                print(f"{result['signal']} ({result['rules_passed']}/9)")
        else:
            if verbose:
                print("FAILED (no data)")
            results.append({
                "ticker": ticker,
                "signal": "ERROR",
                "rules_passed": 0,
                "total_rules": 9,
                "percentage": 0.0,
                "rs_vs_spy": None,
                "price": None,
                "sector": sector,
                "source": entry.get("source"),
                "kind": "stock",
                "details": {},
                "expected_move": None,
            })

    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_overlap_report(
    meta: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> None:
    core = set(meta.get("core_tickers") or [])
    wl = set(meta.get("watchlist_tickers") or [])
    personal = set(meta.get("personal_tickers") or [])
    if not wl and not personal:
        return

    by_ticker = {r["ticker"]: r for r in results}
    print("\n" + "=" * 80)
    print("UNIVERSE OVERLAP (core vs screener / personal)")
    print("=" * 80)

    if wl:
        both = sorted(core & wl)
        core_only = sorted(core - wl)
        wl_only = sorted(wl - core)
        print(f"\nIn both core and screener watchlist ({len(both)}):")
        print("  " + (", ".join(both) if both else "(none)"))
        print(f"\nScreener-only - not in core ({len(wl_only)}):")
        print("  " + (", ".join(wl_only) if wl_only else "(none)"))
        # High-conviction on screener-only
        strong_wl_only = [
            t for t in wl_only
            if by_ticker.get(t, {}).get("signal") in ("STRONG BUY", "BUY")
        ]
        if strong_wl_only:
            print(f"\nScreener-only with BUY+ here ({len(strong_wl_only)}):")
            for t in strong_wl_only:
                r = by_ticker[t]
                print(f"  {t:<6} {r['signal']:<12} {r['rules_passed']}/9")

        strong_core_only = [
            t for t in core_only
            if by_ticker.get(t, {}).get("signal") in ("STRONG BUY", "BUY")
            and by_ticker.get(t, {}).get("kind") == "stock"
        ]
        if strong_core_only:
            print(f"\nCore-only stocks with BUY+ here ({len(strong_core_only)}):")
            for t in strong_core_only:
                r = by_ticker[t]
                print(f"  {t:<6} {r['signal']:<12} {r['rules_passed']}/9")

    if personal:
        print(f"\nPersonal book ({len(personal)}): {', '.join(sorted(personal))}")
        not_in_core = sorted(personal - core)
        if not_in_core:
            print(f"  Personal not in core: {', '.join(not_in_core)}")

    print("=" * 80)


def print_summary(results: List[Dict[str, Any]], show_expected_move: bool = True) -> None:
    print(f"\n{'=' * 100}")
    print(
        f"{'Ticker':<8} {'Kind':<10} {'Source':<18} {'Sector':<22} "
        f"{'Signal':<12} {'Rules':<8} {'RS/SPY':<8} {'Pass%':<6}"
    )
    print("-" * 100)

    ordered = sorted(results, key=lambda x: x.get("rules_passed", 0), reverse=True)
    for r in ordered:
        rs = f"{r['rs_vs_spy']:+.1f}%" if r.get("rs_vs_spy") is not None else "N/A"
        sector = (r.get("sector") or "N/A")[:21]
        src = (r.get("source") or "?")[:17]
        kind = (r.get("kind") or "stock")[:9]
        print(
            f"{r['ticker']:<8} {kind:<10} {src:<18} {sector:<22} "
            f"{r['signal']:<12} {r['rules_passed']}/9{'':<4} {rs:<8} {r['percentage']:.0f}%"
        )
    print("=" * 100)

    signals: Dict[str, int] = {}
    for r in results:
        signals[r["signal"]] = signals.get(r["signal"], 0) + 1
    print("\nSignal Distribution:")
    for sig in ["STRONG BUY", "BUY", "NEUTRAL", "SELL/AVOID", "ERROR"]:
        if signals.get(sig, 0):
            print(f"  {sig}: {signals.get(sig, 0)}")
    print(f"\nTotal Analyzed: {len(results)}")

    if show_expected_move:
        print_expected_moves(results)


def print_expected_moves(results: List[Dict[str, Any]]) -> None:
    title = f"Expected Move (1-sigma) - {datetime.now().strftime('%Y-%m-%d')}"
    print(f"\n{title}")
    print("-" * 100)
    moves = []
    for r in results:
        em = r.get("expected_move")
        price = r.get("price") or 0
        if em:
            moves.append(em)
            print(
                f"  {r['ticker']:<6}  ${float(price):>8.2f}  IV {em['iv']:>5.1f}%  "
                f"daily ±${em['daily_move']:.2f} ({em['daily_pct']:.1f}%)  "
                f"weekly ±${em['weekly_move']:.2f}  "
                f"to-exp ±${em['exp_move']:.2f}  DTE {em['dte']} ({em['expiration']})"
            )
        else:
            print(f"  {r['ticker']:<6}  expected move N/A")
    if moves:
        avg_iv = sum(m["iv"] for m in moves) / len(moves)
        avg_d = sum(m["daily_pct"] for m in moves) / len(moves)
        print(
            f"\n  Avg IV: {avg_iv:.1f}% | Avg daily EM: ±{avg_d:.2f}% | "
            f"Price x IV / sqrt(252) (1-sigma). Not a guarantee of realized range."
        )


def print_briefing(results: List[Dict[str, Any]], show_expected_move: bool = True) -> None:
    print(f"## OVTLYR Nine Rules v4 ({datetime.now().strftime('%Y-%m-%d')})")
    print()
    print(
        f"| {'Ticker':>6} | {'Source':>14} | {'Sector':>20} | "
        f"{'Signal':>12} | {'Rules':>5} | {'RS/SPY':>7} |"
    )
    print(f"|{'-' * 8}|{'-' * 16}|{'-' * 22}|{'-' * 14}|{'-' * 7}|{'-' * 9}|")
    ordered = sorted(results, key=lambda x: x.get("rules_passed", 0), reverse=True)
    for r in ordered:
        rs = f"{r['rs_vs_spy']:+.1f}%" if r.get("rs_vs_spy") is not None else "N/A"
        sector = (r.get("sector") or "N/A")[:20]
        src = (r.get("source") or "?")[:14]
        print(
            f"| {r['ticker']:>6} | {src:>14} | {sector:>20} | "
            f"{r['signal']:>12} | {r['rules_passed']:>3}/9 | {rs:>7} |"
        )
    if show_expected_move:
        print()
        print("### Expected Move (1-sigma)")
        print()
        print(
            f"| {'Ticker':>6} | {'Price':>8} | {'IV':>6} | "
            f"{'Daily +/-':>16} | {'DTE':>4} | {'Exp':>12} |"
        )
        print(f"|{'-' * 8}|{'-' * 10}|{'-' * 8}|{'-' * 18}|{'-' * 6}|{'-' * 14}|")
        for r in ordered:
            em = r.get("expected_move")
            price = r.get("price") or 0
            if em:
                daily = f"${em['daily_move']:.2f} ({em['daily_pct']:.1f}%)"
                print(
                    f"| {r['ticker']:>6} | ${float(price):>7.2f} | {em['iv']:>5.1f}% | "
                    f"{daily:>16} | {em['dte']:>4} | {em['expiration']:>12} |"
                )
            else:
                print(
                    f"| {r['ticker']:>6} | ${float(price):>7.2f} | {'N/A':>6} | "
                    f"{'N/A':>16} | {'N/A':>4} | {'N/A':>12} |"
                )


def print_verbose_details(results: List[Dict[str, Any]], show_em: bool) -> None:
    for r in results:
        print(f"\n{'=' * 60}")
        print(f"  {r['ticker']} - {r['signal']} ({r.get('rules_passed', 0)}/9)  [{r.get('source', '?')}]")
        print(f"{'=' * 60}")
        for rule_name, status in (r.get("details") or {}).items():
            symbol = "✓" if status.get("passed") else "✗"
            print(f"  {symbol} {rule_name}")
            print(f"    {status.get('details', '')}")
        em = r.get("expected_move")
        if em:
            print(
                f"  [i] Expected move: IV {em['iv']:.1f}% | "
                f"daily ±${em['daily_move']:.2f} ({em['daily_pct']:.1f}%) | "
                f"to {em['expiration']} ±${em['exp_move']:.2f} ({em['dte']} DTE)"
            )
        elif show_em:
            print("  [i] Expected move: N/A")


def default_output_path() -> str:
    """Dated report under logs/ (next free MimicOVTLR-v4-YYYYMMDD[-N].txt)."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    base = os.path.join(LOGS_DIR, f"MimicOVTLR-v4-{stamp}.txt")
    if not os.path.exists(base):
        return base
    n = 2
    while True:
        path = os.path.join(LOGS_DIR, f"MimicOVTLR-v4-{stamp}-{n}.txt")
        if not os.path.exists(path):
            return path
        n += 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OVTLYR Nine Rules v4 — independent analysis with optional screener universe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Core only:              python3 OvtLyrMimic4.py
  Core ∪ screener:        python3 OvtLyrMimic4.py --union-watchlist
  Screener only:          python3 OvtLyrMimic4.py --watchlist-only
  Ad-hoc:                 python3 OvtLyrMimic4.py --tickers SMCI ARM
  Personal file:          python3 OvtLyrMimic4.py --file tickers.txt
  No core + watchlist:    python3 OvtLyrMimic4.py --no-core --watchlist PATH
  Fast (no options IV):   python3 OvtLyrMimic4.py --no-expected-move
  Markdown:               python3 OvtLyrMimic4.py --briefing
  Daily log path:         logs/MimicOVTLR-DailyOutput.log (cron)
        """,
    )
    parser.add_argument("--tickers", nargs="+", help="Ad-hoc tickers to include")
    parser.add_argument(
        "--file",
        dest="personal_file",
        default=None,
        help=f"Personal tickers file (default: {DEFAULT_PERSONAL_FILE} if it exists)",
    )
    parser.add_argument(
        "--watchlist",
        type=str,
        default=None,
        help=f"Path to ovtlyr_watchlist.json (default: {DEFAULT_WATCHLIST})",
    )
    parser.add_argument(
        "--union-watchlist",
        action="store_true",
        help="Union core (+ personal) with MarketBreadth watchlist",
    )
    parser.add_argument(
        "--watchlist-only",
        action="store_true",
        help="Analyze only the screener watchlist (plus any --tickers)",
    )
    parser.add_argument(
        "--no-core",
        action="store_true",
        help="Exclude Mag7 / large-cap / sector ETF core list",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Min screener score when loading watchlist stocks",
    )
    parser.add_argument(
        "--breadth",
        type=str,
        default=None,
        help=f"Path to market_breadth_latest.json (default: {DEFAULT_BREADTH})",
    )
    parser.add_argument("--verbose", action="store_true", help="Per-rule details")
    parser.add_argument("--briefing", action="store_true", help="Markdown briefing")
    parser.add_argument(
        "--no-expected-move",
        action="store_true",
        help="Skip ATM IV / expected-move options fetch",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=f"Write full report to this path (default: logs/MimicOVTLR-v4-YYYYMMDD.txt)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not write an output file",
    )
    parser.add_argument(
        "--quiet-progress",
        action="store_true",
        help="Less per-ticker chatter during analysis",
    )

    args = parser.parse_args()
    show_em = not args.no_expected_move

    if args.watchlist_only and args.union_watchlist:
        print("Note: --watchlist-only takes precedence over --union-watchlist")

    # Breadth
    breadth_path = args.breadth or DEFAULT_BREADTH
    breadth_data = load_json(breadth_path)
    market_breadth_pct = None
    if breadth_data and "sp500" in breadth_data:
        market_breadth_pct = breadth_data["sp500"].get("pct_above_50dma")

    # Watchlist path for union / only
    wl_path = args.watchlist
    if args.union_watchlist or args.watchlist_only:
        wl_path = args.watchlist or DEFAULT_WATCHLIST
    elif args.watchlist:
        wl_path = args.watchlist

    entries, meta = build_universe(
        include_core=not args.no_core and not args.watchlist_only,
        personal_path=args.personal_file,
        watchlist_path=wl_path,
        watchlist_only=args.watchlist_only,
        union_watchlist=args.union_watchlist and not args.watchlist_only,
        cli_tickers=args.tickers,
        min_score=args.min_score,
    )

    # Prefer market_breadth from watchlist metadata if richer
    raw_wl = meta.get("watchlist_raw") or {}
    if raw_wl.get("market_breadth_pct") is not None and market_breadth_pct is None:
        market_breadth_pct = raw_wl["market_breadth_pct"]

    sector_map = load_sector_map()

    # Header
    buf = io.StringIO()

    def emit(s: str = "") -> None:
        print(s)
        buf.write(s + "\n")

    emit("=" * 80)
    emit("OVTLYR NINE RULES ANALYSIS - v4 (independent)")
    emit("=" * 80)
    emit(f"Run time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    emit(f"TA engine:    {'MarketBreadth ta_indicators (shared)' if _HAS_SHARED_TA else 'embedded Wilder RSI'}")
    emit(f"Sources:      {', '.join(meta['sources_used']) or '(none)'}")
    emit(f"Universe:     {len(entries)} symbols")
    emit(
        f"Market breadth: "
        + (f"{market_breadth_pct}% above 50-DMA" if market_breadth_pct is not None else "SPY EMA proxy / N/A")
    )
    if breadth_data:
        emit(f"Breadth file: {breadth_path}")
    emit("=" * 80)
    emit("")

    if not entries:
        emit("No tickers to analyze. Use --tickers, --file, core list, or --watchlist.")
        sys.exit(1)

    progress = not args.quiet_progress
    # Capture analysis progress to both console and buffer lightly
    print(f"Analyzing {len(entries)} symbols...\n")

    results = run_analysis(
        entries,
        market_breadth_pct=market_breadth_pct,
        breadth_data=breadth_data,
        sector_map=sector_map,
        verbose=progress,
    )

    if show_em and results:
        attach_expected_moves(results, verbose=progress)

    # Build report body into buffer via redirect for summary sections
    report = io.StringIO()
    with redirect_stdout(report):
        if args.verbose:
            print_verbose_details(results, show_em)
        if args.briefing:
            print()
            print_briefing(results, show_expected_move=show_em)
        else:
            print_summary(results, show_expected_move=show_em)
        print_overlap_report(meta, results)

    body = report.getvalue()
    print(body)
    buf.write(body)

    if not args.no_save:
        out_path = args.output or default_output_path()
        try:
            parent = os.path.dirname(os.path.abspath(out_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(out_path, "w") as f:
                f.write(buf.getvalue())
            print(f"\nReport saved: {out_path}")
        except Exception as e:
            print(f"\nWarning: could not write {out_path}: {e}")


if __name__ == "__main__":
    main()
