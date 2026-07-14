#!/usr/bin/env python3
"""
Stock Screener - Technical Analysis of Top/Bottom Sector Leaders

Reads market breadth data to identify strongest/weakest sectors via a
multi-metric composite (not single-day A/D alone), ranks stocks within each
sector by relative strength + liquidity (not alphabet), then scores them
with shared indicators (ta_indicators.py).

Setup:
  pip install yfinance pandas numpy
  Requires: market_breadth_latest.json (from market_breadth_collector.py)

Usage:
  python3 stock_screener.py                    # Top/bottom 2 sectors (composite)
  python3 stock_screener.py --sectors 3        # Top/bottom N sectors
  python3 stock_screener.py --top-stocks 15    # Analyze top N stocks per sector
  python3 stock_screener.py --sector "Energy"  # Specific sector
  python3 stock_screener.py --briefing         # Markdown briefing
  python3 stock_screener.py --opportunities    # Best-opportunities section only
  python3 stock_screener.py --csv              # Export CSV
  python3 stock_screener.py --watchlist        # Export for nine_rules_gate.py
"""

import json
import os
import sys
import argparse
import csv
from datetime import datetime

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip install yfinance pandas numpy")
    sys.exit(1)

# Shared indicators (same math as nine_rules_gate)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ta_indicators import (  # noqa: E402
    calculate_from_ohlcv,
    evaluate_nine_rules,
    nine_rules_signal,
    rank_sectors,
    relative_strength,
)

# Configuration
DATA_DIR = os.environ.get(
    'MARKET_BREADTH_DIR',
    os.environ.get('GSR_DATA_DIR', os.path.dirname(os.path.abspath(__file__))),
)
BREADTH_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')
OUTPUT_FILE = os.path.join(DATA_DIR, 'stock_screener_results.json')

# Liquidity floor (20-day avg dollar volume)
MIN_DOLLAR_VOLUME = float(os.environ.get('SCREENER_MIN_DOLLAR_VOL', 20_000_000))
# How many sector names to pre-rank before deep analysis (buffer for fails)
PRESCREEN_MULTIPLIER = 3

LOG_PREFIX = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def load_breadth():
    """Load latest breadth data to determine top/bottom sectors."""
    if not os.path.exists(BREADTH_FILE):
        print(f"ERROR: {BREADTH_FILE} not found. Run market_breadth_collector.py first.")
        sys.exit(1)
    with open(BREADTH_FILE, 'r') as f:
        return json.load(f)


def load_constituents():
    """Load S&P 500 constituent list."""
    if not os.path.exists(CONSTITUENTS_FILE):
        print(f"ERROR: {CONSTITUENTS_FILE} not found. Run market_breadth_collector.py first.")
        sys.exit(1)
    return pd.read_csv(CONSTITUENTS_FILE)


def get_target_sectors(breadth_data, num_sectors=2, specific_sector=None):
    """Identify top N and bottom N sectors by multi-metric composite score."""
    if specific_sector:
        return [specific_sector], [], {}

    top, bottom, scores = rank_sectors(breadth_data['sectors'], num_sectors)
    return top, bottom, scores


def signal_label(indicators, score, sector_type):
    """
    Thesis-aware signal (momentum vs reversal), not a single Strong Buy for all.
    """
    rsi = indicators['rsi']
    rs = indicators.get('rs_vs_spy')
    bull_div = indicators.get('bullish_divergence', False)
    bear_div = indicators.get('bearish_divergence', False)
    ema_ok = indicators.get('ema_aligned', False)

    if sector_type == 'top':
        if score >= 70 and ema_ok and not bear_div and (rs is None or rs > 0):
            return 'Momentum Buy'
        if score >= 60 and not bear_div:
            return 'Buy'
        if score >= 40:
            return 'Neutral'
        if score >= 30:
            return 'Weak'
        return 'Avoid'

    # Bottom sector: prefer relative strength within weakness, or washout reversal
    if bull_div and rsi < 40 and score >= 50:
        return 'Reversal Watch'
    if score >= 65 and (rs is not None and rs > 0):
        return 'RS in Weak Sector'
    if score >= 55:
        return 'Watch'
    if score < 35:
        return 'Avoid / Short Bias'
    return 'Neutral'


def score_stock(indicators, sector_ad_ratio=None, sector_type='top'):
    """
    Composite score 0-100.

    For top sectors, tilt toward trend/momentum.
    For bottom sectors, tilt slightly toward washout/reversal quality.
    """
    score = 50.0

    # Trend alignment (+/- 15)
    score += (indicators['trend_score'] - 1.5) * 10

    if indicators['ema_aligned']:
        score += 7
    elif indicators['ma_aligned']:
        score += 4

    if indicators['multi_tf_aligned']:
        score += 5

    rsi = indicators['rsi']
    if sector_type == 'top':
        # Momentum-friendly RSI band
        if 45 <= rsi <= 65:
            score += 6
        elif 40 <= rsi < 45 or 65 < rsi <= 70:
            score += 2
        elif rsi > 75:
            score -= 8
        elif rsi < 30:
            score -= 2  # washout less ideal for momentum thesis
    else:
        # Reversal-friendly: reward oversold, penalize overbought less relevant
        if rsi < 30:
            score += 8
        elif rsi < 40:
            score += 4
        elif 40 <= rsi <= 55:
            score += 2
        elif rsi > 70:
            score -= 6

    if indicators['macd_bullish']:
        score += 6
    else:
        score -= 6 if sector_type == 'top' else 3

    bb = indicators['bb_pct']
    if 0.2 <= bb <= 0.8:
        score += 4
    elif bb < 0.1:
        score += 6 if sector_type == 'bottom' else 3
    elif bb > 0.95:
        score -= 6

    if indicators['atr_pct'] < 3:
        score += 3
    elif indicators['atr_pct'] > 6:
        score -= 4

    if indicators['volume_ratio'] > 1.5:
        score += 5
    elif indicators['volume_ratio'] < 0.5:
        score -= 3

    if indicators['rs_vs_spy'] is not None:
        if indicators['rs_vs_spy'] > 3:
            score += 8
        elif indicators['rs_vs_spy'] > 0:
            score += 4
        elif indicators['rs_vs_spy'] < -5:
            score -= 6

    if indicators['bearish_divergence']:
        score -= 8
    elif indicators['bullish_divergence']:
        score += 8 if sector_type == 'bottom' else 4

    if sector_ad_ratio is not None:
        if sector_ad_ratio > 3:
            score += 6
        elif sector_ad_ratio > 1.5:
            score += 3
        elif sector_ad_ratio < 0.5:
            score -= 5

    return max(0, min(100, round(score)))


def _normalize_history(data, ticker):
    """Extract single-ticker OHLCV from a yf.download multi-ticker frame or single."""
    if data is None or data.empty:
        return None
    try:
        if isinstance(data.columns, pd.MultiIndex):
            # yfinance multi-ticker: columns are (OHLCV, ticker) or (ticker, OHLCV)
            level0 = data.columns.get_level_values(0)
            level1 = data.columns.get_level_values(1)
            if ticker in level1:
                frame = data.xs(ticker, axis=1, level=1, drop_level=True)
            elif ticker in level0:
                frame = data.xs(ticker, axis=1, level=0, drop_level=True)
            else:
                return None
        else:
            frame = data
        if 'Close' not in frame.columns:
            return None
        return frame.dropna(subset=['Close'])
    except Exception:
        return None


def prescreen_sector_tickers(tickers, spy_close, min_dollar_vol=MIN_DOLLAR_VOLUME, top_n=10):
    """
    Rank tickers by composite of 20d RS vs SPY + log dollar volume.
    Returns ordered list of ticker symbols (best first).
    """
    if not tickers:
        return []

    print(f"[{LOG_PREFIX}]     Pre-ranking {len(tickers)} tickers by RS + liquidity...")
    try:
        batch = yf.download(
            tickers,
            period='1y',
            progress=False,
            threads=True,
            group_by='ticker',
            auto_adjust=True,
        )
    except Exception as e:
        print(f"[{LOG_PREFIX}]     Batch download failed ({e}); using ticker order.")
        return tickers

    ranked = []
    for t in tickers:
        hist = _normalize_history(batch, t) if len(tickers) > 1 else batch
        if hist is None or hist.empty or len(hist) < 60:
            # Single-ticker download path when multi fails shape
            try:
                hist = yf.Ticker(t).history(period='1y', auto_adjust=True)
            except Exception:
                continue
        if hist is None or hist.empty or len(hist) < 60:
            continue

        close = hist['Close']
        volume = hist['Volume']
        price = float(close.iloc[-1])
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        if pd.isna(avg_vol) or avg_vol <= 0:
            continue
        dollar_vol = avg_vol * price
        if dollar_vol < min_dollar_vol:
            continue

        rs20 = relative_strength(close, spy_close, 20)
        rs60 = relative_strength(close, spy_close, 60)
        if rs20 is None:
            rs20 = 0.0
        if rs60 is None:
            rs60 = 0.0

        # Rank score: RS primary, liquidity secondary (log scale)
        liq = np.log10(max(dollar_vol, 1.0))
        rank_score = (0.6 * rs20) + (0.25 * rs60) + (0.15 * (liq - 7) * 10)
        ranked.append((t, rank_score, dollar_vol, rs20))

    ranked.sort(key=lambda x: x[1], reverse=True)
    if ranked:
        print(
            f"[{LOG_PREFIX}]     Liquidity-qualified: {len(ranked)} "
            f"(min ${min_dollar_vol/1e6:.0f}M avg dollar vol)"
        )
    return [t for t, _, _, _ in ranked]


def analyze_sector(
    sector_name,
    sp500_df,
    breadth_data,
    top_n=10,
    sector_type='top',
    market_breadth_pct=None,
    spy_close=None,
):
    """Analyze top N stocks in a sector (pre-ranked by RS + liquidity)."""
    sector_stocks = sp500_df[sp500_df['GICS Sector'] == sector_name]['Symbol'].tolist()
    sector_stocks = [t.replace('.', '-') for t in sector_stocks]

    sector_ad_ratio = None
    sector_breadth_pct = None
    if breadth_data and 'sectors' in breadth_data and sector_name in breadth_data['sectors']:
        sm = breadth_data['sectors'][sector_name]
        sector_ad_ratio = sm.get('ad_ratio')
        sector_breadth_pct = sm.get('pct_above_50dma')

    print(
        f"[{LOG_PREFIX}]   Analyzing {len(sector_stocks)} stocks in {sector_name} "
        f"(deep-score top {top_n})..."
    )
    if sector_ad_ratio is not None:
        print(
            f"[{LOG_PREFIX}]   Sector A/D: {sector_ad_ratio} | "
            f"% >50DMA: {sector_breadth_pct}"
        )

    # Pre-rank entire sector (or large subset) by RS + liquidity
    ordered = prescreen_sector_tickers(
        sector_stocks,
        spy_close,
        min_dollar_vol=MIN_DOLLAR_VOLUME,
        top_n=top_n,
    )
    if not ordered:
        # Fallback: no liquidity filter, original order
        print(f"[{LOG_PREFIX}]     Warning: prescreen empty; falling back to CSV order.")
        ordered = sector_stocks

    candidates = ordered[: max(top_n * PRESCREEN_MULTIPLIER, top_n)]

    results = []
    for i, ticker in enumerate(candidates):
        if len(results) >= top_n:
            break
        try:
            hist = yf.Ticker(ticker).history(period='1y', auto_adjust=True)
        except Exception:
            hist = None
        indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=200)
        if not indicators:
            continue

        indicators['ticker'] = ticker
        indicators['sector'] = sector_name
        indicators['sector_type'] = sector_type
        indicators['score'] = score_stock(indicators, sector_ad_ratio, sector_type)

        rules = evaluate_nine_rules(
            indicators,
            market_breadth_pct=market_breadth_pct,
            sector_breadth_pct=sector_breadth_pct,
        )
        indicators['rules_passed'] = rules['rules_passed']
        indicators['rules_total'] = rules['total_rules']
        indicators['rules_detail'] = {
            k: v['passed'] for k, v in rules['rules'].items()
        }
        indicators['nine_rules_signal_label'] = nine_rules_signal(rules['rules_passed'])
        indicators['signal'] = signal_label(indicators, indicators['score'], sector_type)

        results.append(indicators)
        if (i + 1) % 5 == 0:
            print(f"[{LOG_PREFIX}]     Processed {i + 1}/{len(candidates)} candidates...")

    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def run_screener(num_sectors=2, top_stocks=10, specific_sector=None):
    """Main screener routine."""
    breadth = load_breadth()
    sp500 = load_constituents()

    top_sectors, bottom_sectors, sector_scores = get_target_sectors(
        breadth, num_sectors, specific_sector
    )

    market_breadth_pct = None
    if 'sp500' in breadth:
        market_breadth_pct = breadth['sp500'].get('pct_above_50dma')

    print(f"[{LOG_PREFIX}] Stock Screener - Technical Analysis")
    print(f"[{LOG_PREFIX}] Breadth data from: {breadth['date']}")
    if market_breadth_pct is not None:
        print(f"[{LOG_PREFIX}] Market breadth: {market_breadth_pct}% above 50-DMA")
    if not specific_sector:
        print(f"[{LOG_PREFIX}] Top sectors (composite): {top_sectors}")
        if sector_scores:
            for s in top_sectors:
                print(f"[{LOG_PREFIX}]   {s}: composite={sector_scores.get(s, 'n/a')}")
        print(f"[{LOG_PREFIX}] Bottom sectors (composite): {bottom_sectors}")
        if sector_scores:
            for s in bottom_sectors:
                print(f"[{LOG_PREFIX}]   {s}: composite={sector_scores.get(s, 'n/a')}")
    else:
        print(f"[{LOG_PREFIX}] Analyzing sector: {specific_sector}")
    print()

    # SPY once for RS
    spy_hist = yf.Ticker('SPY').history(period='1y', auto_adjust=True)
    spy_close = spy_hist['Close'] if not spy_hist.empty else None

    all_results = {}

    for sector in top_sectors:
        print(f"[{LOG_PREFIX}] === TOP SECTOR: {sector} ===")
        results = analyze_sector(
            sector, sp500, breadth, top_stocks,
            sector_type='top',
            market_breadth_pct=market_breadth_pct,
            spy_close=spy_close,
        )
        all_results[sector] = {
            'type': 'top',
            'composite_score': sector_scores.get(sector) if sector_scores else None,
            'stocks': results,
        }
        print(f"[{LOG_PREFIX}]   Completed: {len(results)} stocks analyzed")
        print()

    for sector in bottom_sectors:
        print(f"[{LOG_PREFIX}] === BOTTOM SECTOR: {sector} ===")
        results = analyze_sector(
            sector, sp500, breadth, top_stocks,
            sector_type='bottom',
            market_breadth_pct=market_breadth_pct,
            spy_close=spy_close,
        )
        all_results[sector] = {
            'type': 'bottom',
            'composite_score': sector_scores.get(sector) if sector_scores else None,
            'stocks': results,
        }
        print(f"[{LOG_PREFIX}]   Completed: {len(results)} stocks analyzed")
        print()

    output = {
        'date': breadth['date'],
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market_breadth_pct': market_breadth_pct,
        'sector_selection': 'composite',
        'min_dollar_volume': MIN_DOLLAR_VOLUME,
        'sectors': all_results,
    }
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[{LOG_PREFIX}] Results saved to {OUTPUT_FILE}")

    return output


def _load_results():
    if not os.path.exists(OUTPUT_FILE):
        print("No screener results found. Run without --briefing first.")
        return None
    with open(OUTPUT_FILE, 'r') as f:
        return json.load(f)


def show_briefing():
    """Output markdown briefing for all screened sectors."""
    data = _load_results()
    if not data:
        return

    print(f"## Stock Screener ({data['date']})")
    print()
    if data.get('market_breadth_pct') is not None:
        print(f"**Market breadth:** {data['market_breadth_pct']}% above 50-DMA")
        print(f"**Sector selection:** {data.get('sector_selection', 'ad_ratio')}")
        print()

    for sector, info in data['sectors'].items():
        label = "STRONGEST" if info['type'] == 'top' else "WEAKEST"
        comp = info.get('composite_score')
        comp_str = f" | composite: {comp}" if comp is not None else ""
        print(f"### {label}: {sector}{comp_str}")
        print()
        print(
            f"| {'Ticker':>6} | {'Price':>8} | {'Score':>5} | {'Rules':>5} | "
            f"{'Trend':>5} | {'RSI':>5} | {'MACD':>6} | {'RS/SPY':>7} | "
            f"{'ATR%':>5} | {'Flags':>8} | {'Signal':>18} |"
        )
        print(
            f"|{'-'*8}|{'-'*10}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*8}|"
            f"{'-'*9}|{'-'*7}|{'-'*10}|{'-'*20}|"
        )

        for s in info['stocks']:
            trend = f"{s['trend_score']}/3"
            macd_dir = "Bull" if s['macd_bullish'] else "Bear"
            rs_spy = f"{s['rs_vs_spy']:+.1f}%" if s.get('rs_vs_spy') is not None else "N/A"
            atr = f"{s.get('atr_pct', 0):.1f}%"

            flags = []
            if s.get('bearish_divergence'):
                flags.append("DIV-")
            if s.get('bullish_divergence'):
                flags.append("DIV+")
            if s.get('ema_aligned'):
                flags.append("EMA")
            flag_str = ','.join(flags) if flags else '-'

            signal = s.get('signal') or 'Neutral'
            rules = f"{s.get('rules_passed', 'N/A')}/{s.get('rules_total', 9)}"
            print(
                f"| {s['ticker']:>6} | ${s['price']:>7.2f} | {s['score']:>5} | {rules:>5} | "
                f"{trend:>5} | {s['rsi']:>5.1f} | {macd_dir:>6} | {rs_spy:>7} | "
                f"{atr:>5} | {flag_str:>8} | {signal:>18} |"
            )
        print()


def show_opportunities(min_score=60, max_rows=10):
    """
    Concise 'best opportunities' section for the daily log.
    Prioritizes top-sector momentum names; lists bottom-sector setups separately.
    """
    data = _load_results()
    if not data:
        return

    print(f"## Best Opportunities ({data['date']})")
    print()
    mb = data.get('market_breadth_pct')
    if mb is not None:
        regime = "constructive" if mb >= 50 else "defensive / selective"
        print(f"**Regime:** market {mb}% above 50-DMA -> {regime}")
        print()

    momentum = []
    reversal = []

    for sector, info in data['sectors'].items():
        for s in info['stocks']:
            row = {**s, 'sector': sector, 'sector_type': info['type']}
            if info['type'] == 'top' and s.get('score', 0) >= min_score:
                momentum.append(row)
            elif info['type'] == 'bottom' and (
                s.get('signal') in ('Reversal Watch', 'RS in Weak Sector', 'Watch')
                or s.get('score', 0) >= min_score
            ):
                reversal.append(row)

    momentum.sort(key=lambda x: (x.get('score', 0), x.get('rules_passed', 0)), reverse=True)
    reversal.sort(key=lambda x: (x.get('score', 0), x.get('rules_passed', 0)), reverse=True)

    print("### Momentum (strong sectors)")
    print()
    if not momentum:
        print("_No names cleared the score threshold in top sectors._")
        print()
    else:
        print(
            f"| {'Ticker':>6} | {'Sector':>22} | {'Score':>5} | {'Rules':>5} | "
            f"{'RS/SPY':>7} | {'Signal':>18} |"
        )
        print(f"|{'-'*8}|{'-'*24}|{'-'*7}|{'-'*7}|{'-'*9}|{'-'*20}|")
        for s in momentum[:max_rows]:
            rs = f"{s['rs_vs_spy']:+.1f}%" if s.get('rs_vs_spy') is not None else "N/A"
            rules = f"{s.get('rules_passed', 0)}/{s.get('rules_total', 9)}"
            print(
                f"| {s['ticker']:>6} | {s['sector']:>22} | {s['score']:>5} | {rules:>5} | "
                f"{rs:>7} | {s.get('signal', ''):>18} |"
            )
        print()

    print("### Weak-sector setups (relative strength / reversal)")
    print()
    if not reversal:
        print("_No standout weak-sector setups._")
        print()
    else:
        print(
            f"| {'Ticker':>6} | {'Sector':>22} | {'Score':>5} | {'Rules':>5} | "
            f"{'RS/SPY':>7} | {'Signal':>18} |"
        )
        print(f"|{'-'*8}|{'-'*24}|{'-'*7}|{'-'*7}|{'-'*9}|{'-'*20}|")
        for s in reversal[:max_rows]:
            rs = f"{s['rs_vs_spy']:+.1f}%" if s.get('rs_vs_spy') is not None else "N/A"
            rules = f"{s.get('rules_passed', 0)}/{s.get('rules_total', 9)}"
            print(
                f"| {s['ticker']:>6} | {s['sector']:>22} | {s['score']:>5} | {rules:>5} | "
                f"{rs:>7} | {s.get('signal', ''):>18} |"
            )
        print()

    print(
        "_Primary focus: Momentum table. Weak-sector names are secondary "
        "(contrarian / RS survivors), not the same as momentum buys._"
    )
    print()


def export_watchlist(output_path=None, min_score=60, top_per_sector=5, top_only_primary=True):
    """Export watchlist for nine_rules_gate.py. Prefers top-sector names."""
    data = _load_results()
    if not data:
        print("No screener results found. Run screener first.")
        return

    if not output_path:
        output_path = os.path.join(DATA_DIR, 'nine_rules_watchlist.json')

    breadth = load_breadth() if os.path.exists(BREADTH_FILE) else None

    watchlist = {
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'source_date': data['date'],
        'min_score': min_score,
        'market_breadth_pct': data.get('market_breadth_pct'),
        'stocks': [],
    }

    if watchlist['market_breadth_pct'] is None and breadth and 'sp500' in breadth:
        watchlist['market_breadth_pct'] = breadth['sp500'].get('pct_above_50dma', 50)

    for sector, info in data['sectors'].items():
        sector_breadth_pct = None
        if breadth and 'sectors' in breadth and sector in breadth['sectors']:
            sector_breadth_pct = breadth['sectors'][sector].get('pct_above_50dma', 50)

        # Primary: top sectors. Bottom sectors still exported but tagged.
        qualifying = [s for s in info['stocks'] if s['score'] >= min_score][:top_per_sector]
        if info['type'] == 'bottom' and top_only_primary:
            # Keep only clearer weak-sector theses
            qualifying = [
                s for s in qualifying
                if s.get('signal') in ('Reversal Watch', 'RS in Weak Sector')
                or s.get('rules_passed', 0) >= 6
            ][:top_per_sector]

        for stock in qualifying:
            watchlist['stocks'].append({
                'ticker': stock['ticker'],
                'sector': sector,
                'sector_type': info['type'],
                'score': stock['score'],
                'signal': stock.get('signal'),
                'rules_passed': stock.get('rules_passed', 0),
                'sector_breadth_pct': sector_breadth_pct,
                'rs_vs_spy': stock.get('rs_vs_spy'),
            })

    # Sort: top-sector first, then by score
    watchlist['stocks'].sort(
        key=lambda x: (0 if x.get('sector_type') == 'top' else 1, -x.get('score', 0))
    )

    with open(output_path, 'w') as f:
        json.dump(watchlist, f, indent=2)

    print(
        f"[{LOG_PREFIX}] Watchlist exported: {len(watchlist['stocks'])} stocks "
        f"(min score {min_score}) to {output_path}"
    )
    for s in watchlist['stocks']:
        print(
            f"  {s['ticker']:>6} | {s['sector']:30s} | {s.get('sector_type', '?'):6s} | "
            f"Score: {s['score']} | Rules: {s['rules_passed']}/9 | {s.get('signal', '')}"
        )


def export_csv(output_path=None):
    """Export results to CSV."""
    data = _load_results()
    if not data:
        print("No results found. Run screener first.")
        return

    if not output_path:
        output_path = os.path.join(DATA_DIR, 'stock_screener_results.csv')

    rows = []
    for sector, info in data['sectors'].items():
        for stock in info['stocks']:
            stock = dict(stock)
            stock['sector_type'] = info['type']
            # Drop nested rules_detail for flat CSV
            stock.pop('rules_detail', None)
            rows.append(stock)

    fieldnames = [
        'sector', 'sector_type', 'ticker', 'price', 'score', 'signal', 'nine_rules_signal_label',
        'rules_passed', 'rules_total', 'trend_score', 'ma_aligned', 'ema_aligned',
        'above_20dma', 'above_50dma', 'above_200dma',
        'sma20', 'sma50', 'sma200', 'rsi', 'macd', 'macd_signal', 'macd_hist',
        'macd_bullish', 'bb_pct', 'bb_position', 'atr_pct', 'volume_ratio',
        'avg_volume_20d', 'daily_volume', 'dollar_volume_20d',
        'rs_vs_spy', 'rs_vs_spy_60', 'bearish_divergence', 'bullish_divergence',
    ]

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f"[{LOG_PREFIX}] Exported {len(rows)} stocks to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Stock Screener - technical analysis of top/bottom sector leaders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze top 2 + bottom 2:     python3 stock_screener.py
  Top/bottom 3 sectors:         python3 stock_screener.py --sectors 3
  More stocks per sector:       python3 stock_screener.py --top-stocks 20
  Specific sector:              python3 stock_screener.py --sector "Energy"
  Markdown briefing:            python3 stock_screener.py --briefing
  Best opportunities only:      python3 stock_screener.py --opportunities
  Export to CSV:                python3 stock_screener.py --csv
  Generate watchlist:           python3 stock_screener.py --watchlist
        """,
    )
    parser.add_argument('--sectors', type=int, default=2, help='Number of top/bottom sectors')
    parser.add_argument('--top-stocks', type=int, default=10, help='Stocks per sector to deep-score')
    parser.add_argument('--sector', type=str, default=None, help='Analyze a specific sector')
    parser.add_argument('--briefing', action='store_true', help='Show markdown briefing')
    parser.add_argument(
        '--opportunities', action='store_true',
        help='Show best-opportunities section (momentum + weak-sector setups)',
    )
    parser.add_argument('--csv', nargs='?', const='', default=None, help='Export to CSV')
    parser.add_argument(
        '--watchlist', nargs='?', const='', default=None,
        help='Export watchlist for nine_rules_gate.py',
    )

    args = parser.parse_args()

    if args.briefing:
        show_briefing()
    elif args.opportunities:
        show_opportunities()
    elif args.csv is not None:
        export_csv(args.csv if args.csv else None)
    elif args.watchlist is not None:
        export_watchlist(args.watchlist if args.watchlist else None)
    else:
        run_screener(args.sectors, args.top_stocks, args.sector)


if __name__ == '__main__':
    main()
