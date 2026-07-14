#!/usr/bin/env python3
"""
OVTLYR Nine Rules Analysis (v3)

Uses shared ta_indicators.py (same math as stock_screener.py).
Integrates with market breadth collector and stock screener watchlists.

Data sources:
  - ovtlyr_watchlist.json (from stock_screener.py --watchlist)
  - market_breadth_latest.json (from market_breadth_collector.py)
  - Or: manual ticker list via --tickers

Usage:
  python3 OvtLyrMimic.py                           # Watchlist from screener
  python3 OvtLyrMimic.py --tickers AAPL MSFT NVDA  # Specific tickers
  python3 OvtLyrMimic.py --watchlist path/to/file
  python3 OvtLyrMimic.py --briefing
  python3 OvtLyrMimic.py --verbose
"""

import json
import os
import sys
import argparse
from datetime import datetime

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip install yfinance pandas numpy")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ta_indicators import (  # noqa: E402
    calculate_from_ohlcv,
    evaluate_nine_rules,
    nine_rules_signal,
)

DATA_DIR = os.environ.get(
    'MARKET_BREADTH_DIR',
    os.environ.get('GSR_DATA_DIR', os.path.dirname(os.path.abspath(__file__))),
)
WATCHLIST_FILE = os.path.join(DATA_DIR, 'ovtlyr_watchlist.json')
BREADTH_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')


def load_watchlist(watchlist_path=None):
    path = watchlist_path or WATCHLIST_FILE
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def load_breadth():
    if not os.path.exists(BREADTH_FILE):
        return None
    with open(BREADTH_FILE, 'r') as f:
        return json.load(f)


def load_sector_map():
    """Map ticker -> GICS sector from constituents CSV."""
    if not os.path.exists(CONSTITUENTS_FILE):
        return {}
    df = pd.read_csv(CONSTITUENTS_FILE)
    mapping = {}
    for _, row in df.iterrows():
        sym = str(row['Symbol']).replace('.', '-')
        mapping[sym] = row['GICS Sector']
    return mapping


def get_sector_breadth(breadth_data, sector_name):
    if breadth_data and 'sectors' in breadth_data and sector_name in breadth_data['sectors']:
        return breadth_data['sectors'][sector_name].get('pct_above_50dma')
    return None


def analyze_ticker(
    ticker,
    market_breadth_pct=None,
    sector_breadth_pct=None,
    spy_close=None,
    period='1y',
):
    """
    Fetch OHLCV, compute shared indicators, evaluate nine rules.
    period defaults to 1y so EMA100/SMA200 and screener math align.
    """
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception:
        return None

    # Need enough bars for full indicator set; allow shorter for 6mo edge cases
    min_bars = 200 if period in ('1y', '2y', 'max') else 100
    indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=min_bars)
    if indicators is None and min_bars > 100:
        indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=100)
    if indicators is None:
        return None

    # If market breadth missing, approximate from SPY vs 50 EMA only as last resort
    mb = market_breadth_pct
    if mb is None and spy_close is not None and len(spy_close) >= 50:
        spy_ema50 = spy_close.ewm(span=50, adjust=False).mean().iloc[-1]
        spy_price = float(spy_close.iloc[-1])
        mb = 60.0 if spy_price > spy_ema50 else 40.0

    rules_out = evaluate_nine_rules(
        indicators,
        market_breadth_pct=mb,
        sector_breadth_pct=sector_breadth_pct,
    )
    passed = rules_out['rules_passed']
    signal = nine_rules_signal(passed)

    return {
        'ticker': ticker,
        'signal': signal,
        'rules_passed': passed,
        'total_rules': rules_out['total_rules'],
        'percentage': round((passed / rules_out['total_rules']) * 100, 1),
        'rs_vs_spy': indicators.get('rs_vs_spy'),
        'price': indicators.get('price'),
        'rsi': indicators.get('rsi'),
        'details': rules_out['rules'],
        'indicators': indicators,
    }


def run_analysis(tickers, market_breadth_pct=None, breadth_data=None, verbose=True):
    """Run OVTLYR analysis on a list of tickers or watchlist dicts."""
    # Fetch SPY once
    try:
        spy_hist = yf.Ticker('SPY').history(period='1y', auto_adjust=True)
        spy_close = spy_hist['Close'] if not spy_hist.empty else None
    except Exception:
        spy_close = None

    sector_map = load_sector_map()
    results = []

    for ticker_info in tickers:
        if isinstance(ticker_info, dict):
            ticker = ticker_info['ticker']
            sector = ticker_info.get('sector')
            sector_breadth = ticker_info.get('sector_breadth_pct')
            if sector_breadth is None and sector:
                sector_breadth = get_sector_breadth(breadth_data, sector)
        else:
            ticker = ticker_info
            sector = sector_map.get(ticker)
            sector_breadth = get_sector_breadth(breadth_data, sector) if sector else None

        if verbose:
            print(f"  Analyzing {ticker}...", end=' ')

        result = analyze_ticker(
            ticker,
            market_breadth_pct=market_breadth_pct,
            sector_breadth_pct=sector_breadth,
            spy_close=spy_close,
        )

        if result:
            result['sector'] = sector
            results.append(result)
            if verbose:
                print(f"{result['signal']} ({result['rules_passed']}/9)")
        else:
            if verbose:
                print("FAILED (no data)")

    return results


def print_summary(results):
    print(f"\n{'=' * 90}")
    print(f"{'Ticker':<8} {'Sector':<28} {'Signal':<12} {'Rules':<8} {'RS/SPY':<8} {'Pass%':<8}")
    print(f"{'-' * 90}")

    results = sorted(results, key=lambda x: x['rules_passed'], reverse=True)

    for r in results:
        rs = f"{r['rs_vs_spy']:+.1f}%" if r.get('rs_vs_spy') is not None else "N/A"
        sector = (r.get('sector') or 'N/A')[:27]
        print(
            f"{r['ticker']:<8} {sector:<28} {r['signal']:<12} "
            f"{r['rules_passed']}/9{'':<4} {rs:<8} {r['percentage']:.0f}%"
        )

    print(f"{'=' * 90}")

    signals = {}
    for r in results:
        signals[r['signal']] = signals.get(r['signal'], 0) + 1
    print("\nSignal Distribution:")
    for sig in ['STRONG BUY', 'BUY', 'NEUTRAL', 'SELL/AVOID']:
        print(f"  {sig}: {signals.get(sig, 0)}")
    print(f"\nTotal Analyzed: {len(results)}")


def get_expected_move(ticker, price):
    """
    Calculate expected move using implied volatility from the nearest options expiration.
    Formula: Daily 1-sigma move = (Price × IV) / sqrt(252)
    Shortcut: Price × IV / 16
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return None

        # Use nearest expiration
        chain = stock.option_chain(expirations[0])
        calls = chain.calls

        # Find the ATM call (closest strike to current price)
        atm_idx = (calls['strike'] - price).abs().idxmin()
        iv = float(calls.loc[atm_idx, 'impliedVolatility'])

        # Days to nearest expiration
        exp_date = datetime.strptime(expirations[0], '%Y-%m-%d')
        dte = max((exp_date - datetime.now()).days, 1)

        daily_move = (price * iv) / np.sqrt(252)
        weekly_move = (price * iv * np.sqrt(5)) / np.sqrt(252)
        exp_move = (price * iv * np.sqrt(dte)) / np.sqrt(252)

        return {
            'iv': iv * 100,
            'daily_move': daily_move,
            'daily_pct': (daily_move / price) * 100,
            'weekly_move': weekly_move,
            'weekly_pct': (weekly_move / price) * 100,
            'exp_move': exp_move,
            'exp_pct': (exp_move / price) * 100,
            'dte': dte,
            'expiration': expirations[0]
        }
    except Exception:
        return None


def print_expected_moves(results):
    """Print expected move table for all analyzed tickers."""
    print(f"\n## Expected Move (1-sigma) - {datetime.now().strftime('%Y-%m-%d')}")
    print(f"\n| {'Ticker':>6} | {'Price':>8} | {'IV':>6} | {'Daily +/-':>14} | {'Weekly +/-':>16} | {'To Exp +/-':>16} | {'DTE':>4} |")
    print(f"|{'-'*8}|{'-'*10}|{'-'*8}|{'-'*16}|{'-'*18}|{'-'*18}|{'-'*6}|")

    moves = []
    for r in results:
        ticker = r['ticker']
        try:
            stock = yf.Ticker(ticker)
            price = float(stock.info.get('regularMarketPrice') or stock.info.get('currentPrice') or 0)
            if price == 0:
                price = float(r.get('details', {}).get('Rule 1: Trend Confirmation', {}).get('details', '').split('$')[1].split(',')[0])
        except Exception:
            continue

        em = get_expected_move(ticker, price)
        if em:
            moves.append((ticker, price, em))
            print(f"| {ticker:>6} | ${price:>6.2f} | {em['iv']:>5.1f}% | ${em['daily_move']:>6.2f} ({em['daily_pct']:>4.1f}%) | ${em['weekly_move']:>7.2f} ({em['weekly_pct']:>4.1f}%) | ${em['exp_move']:>7.2f} ({em['exp_pct']:>4.1f}%) | {em['dte']:>4} |")
        else:
            print(f"| {ticker:>6} | ${price:>6.2f} | {'N/A':>6} | {'N/A':>14} | {'N/A':>16} | {'N/A':>16} | {'N/A':>4} |")

    if moves:
        avg_iv = np.mean([m[2]['iv'] for m in moves])
        avg_daily_pct = np.mean([m[2]['daily_pct'] for m in moves])
        print(f"\n*Avg IV: {avg_iv:.1f}% | Avg daily expected move: +/-{avg_daily_pct:.2f}%*")
        print(f"*Formula: Price x IV / sqrt(252) (1 standard deviation, ~68% probability range)*")


def print_briefing(results):
    print(f"## OVTLYR Nine Rules Analysis ({datetime.now().strftime('%Y-%m-%d')})")
    print()
    print(f"| {'Ticker':>6} | {'Sector':>25} | {'Signal':>12} | {'Rules':>5} | {'RS/SPY':>7} |")
    print(f"|{'-' * 8}|{'-' * 27}|{'-' * 14}|{'-' * 7}|{'-' * 9}|")

    results = sorted(results, key=lambda x: x['rules_passed'], reverse=True)
    for r in results:
        rs = f"{r['rs_vs_spy']:+.1f}%" if r.get('rs_vs_spy') is not None else "N/A"
        sector = (r.get('sector') or 'N/A')[:25]
        print(
            f"| {r['ticker']:>6} | {sector:>25} | {r['signal']:>12} | "
            f"{r['rules_passed']:>3}/9 | {rs:>7} |"
        )

    # Add expected move section
    print_expected_moves(results)


def main():
    parser = argparse.ArgumentParser(
        description='OVTLYR Nine Rules — shared indicators with stock_screener',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  From watchlist:    python3 OvtLyrMimic.py
  Specific tickers:  python3 OvtLyrMimic.py --tickers AAPL MSFT NVDA AMD
  Custom watchlist:  python3 OvtLyrMimic.py --watchlist my_stocks.json
  Markdown output:   python3 OvtLyrMimic.py --briefing
  Verbose details:   python3 OvtLyrMimic.py --verbose
        """,
    )
    parser.add_argument('--tickers', nargs='+', help='Specific tickers to analyze')
    parser.add_argument('--watchlist', type=str, default=None, help='Path to watchlist JSON')
    parser.add_argument('--briefing', action='store_true', help='Markdown briefing output')
    parser.add_argument('--verbose', action='store_true', help='Show per-rule details')

    args = parser.parse_args()

    breadth_data = load_breadth()
    market_breadth_pct = None
    if breadth_data and 'sp500' in breadth_data:
        market_breadth_pct = breadth_data['sp500'].get('pct_above_50dma')
        print(f"Market breadth loaded: {market_breadth_pct}% above 50-DMA")

    if args.tickers:
        tickers = args.tickers
        print(f"\nAnalyzing {len(tickers)} tickers: {', '.join(tickers)}")
        print(f"{'=' * 60}\n")
        results = run_analysis(
            tickers, market_breadth_pct, breadth_data=breadth_data, verbose=True
        )
    else:
        watchlist = load_watchlist(args.watchlist)
        if watchlist is None:
            print("No watchlist found. Run: python3 stock_screener.py --watchlist")
            print("Or specify tickers: python3 OvtLyrMimic.py --tickers AAPL MSFT")
            sys.exit(1)

        if watchlist.get('market_breadth_pct') is not None:
            market_breadth_pct = watchlist['market_breadth_pct']

        print(
            f"\nWatchlist loaded: {len(watchlist['stocks'])} stocks "
            f"from {watchlist.get('source_date', '?')}"
        )
        print(f"Market breadth: {market_breadth_pct}% above 50-DMA")
        print(f"{'=' * 60}\n")

        results = run_analysis(
            watchlist['stocks'],
            market_breadth_pct,
            breadth_data=breadth_data,
            verbose=True,
        )

    if args.verbose and results:
        for r in results:
            print(f"\n{'=' * 60}")
            print(f"  {r['ticker']} — {r['signal']} ({r['rules_passed']}/9)")
            print(f"{'=' * 60}")
            if 'details' in r:
                for rule_name, status in r['details'].items():
                    symbol = "+" if status['passed'] else "x"
                    print(f"  [{symbol}] {rule_name}")
                    print(f"      {status['details']}")

    if args.briefing:
        print()
        print_briefing(results)
    else:
        print_summary(results)


if __name__ == '__main__':
    main()
