#!/usr/bin/env python3
"""
Nine Rules Gate

Short-list checklist using shared ta_indicators.py (same math as stock_screener.py).
Integrates with market breadth collector and stock screener watchlists.

Also reports IV-based expected move (1-sigma) from the nearest options
expiration - see Expected-Move-Guide.md.

Data sources:
  - nine_rules_watchlist.json (from stock_screener.py --watchlist)
  - market_breadth_latest.json (from market_breadth_collector.py)
  - Yahoo options chain for expected move / ATM IV
  - Or: manual ticker list via --tickers

Usage:
  python3 nine_rules_gate.py                           # Watchlist from screener
  python3 nine_rules_gate.py --tickers AAPL MSFT NVDA  # Specific tickers
  python3 nine_rules_gate.py --watchlist path/to/file
  python3 nine_rules_gate.py --briefing
  python3 nine_rules_gate.py --verbose
  python3 nine_rules_gate.py --no-expected-move        # Skip options chain fetch
"""

import json
import math
import os
import sys
import argparse
from datetime import datetime, date
from typing import Any, Dict, List, Optional

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
WATCHLIST_FILE = os.path.join(DATA_DIR, 'nine_rules_watchlist.json')
BREADTH_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')

# Trading days convention for annualized IV → horizon move
TRADING_DAYS_PER_YEAR = 252.0


def load_watchlist(watchlist_path=None):
    """Load screener watchlist JSON (prefers nine_rules_watchlist.json)."""
    candidates = []
    if watchlist_path:
        candidates.append(watchlist_path)
    else:
        candidates.append(WATCHLIST_FILE)
        # Legacy filename from pre-rename installs
        candidates.append(os.path.join(DATA_DIR, 'ovtlyr_watchlist.json'))
    for path in candidates:
        if path and os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
    return None


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


# ---------------------------------------------------------------------------
# Expected move (IV from nearest options expiration)
# ---------------------------------------------------------------------------

def _sorted_expirations(expirations: List[str], prefer_min_dte: int = 1) -> List[str]:
    """Return expiration strings sorted by ascending DTE (skip past / too-near dates)."""
    if not expirations:
        return []
    today = date.today()
    scored = []
    for exp_str in expirations:
        try:
            exp_d = datetime.strptime(exp_str, '%Y-%m-%d').date()
        except ValueError:
            continue
        dte = (exp_d - today).days
        if dte < prefer_min_dte:
            continue
        scored.append((dte, exp_str))
    scored.sort(key=lambda x: x[0])
    return [e for _, e in scored]


def _atm_iv_from_chain(side: pd.DataFrame, price: float) -> Optional[float]:
    """Return ATM impliedVolatility (decimal, e.g. 0.25) or None."""
    if side is None or side.empty or price <= 0:
        return None
    if 'strike' not in side.columns or 'impliedVolatility' not in side.columns:
        return None

    work = side.dropna(subset=['strike', 'impliedVolatility']).copy()
    if work.empty:
        return None

    # Prefer liquid-ish contracts when openInterest available
    if 'openInterest' in work.columns:
        oi = work['openInterest'].fillna(0)
        if (oi > 0).any():
            work = work.loc[oi > 0]
    if work.empty:
        return None

    atm_idx = (work['strike'] - price).abs().idxmin()
    iv = float(work.loc[atm_idx, 'impliedVolatility'])
    if not math.isfinite(iv):
        return None
    # Reject Yahoo placeholders / nonsense (0%, or >500% annualized)
    if iv < 0.05 or iv > 5.0:
        return None
    return iv


def _iv_from_expiration(stock: yf.Ticker, exp_str: str, price: float) -> Optional[float]:
    """ATM IV from calls, else puts, for one expiration."""
    try:
        chain = stock.option_chain(exp_str)
    except Exception:
        return None
    iv = _atm_iv_from_chain(chain.calls, price)
    if iv is None and getattr(chain, 'puts', None) is not None:
        iv = _atm_iv_from_chain(chain.puts, price)
    return iv


def get_expected_move(ticker: str, price: float, max_expirations_to_try: int = 5) -> Optional[Dict[str, Any]]:
    """
    Calculate 1-sigma expected move using ATM IV from the nearest usable options expiration.

    Tries the nearest listed expirations in order until a sane ATM IV is found
    (Yahoo often returns 0% IV on thin or 0-DTE-adjacent chains).

    Formulas (IV annualized as a decimal):
      daily  = price * IV / sqrt(252)
      weekly = price * IV * sqrt(5) / sqrt(252)
      to_exp = price * IV * sqrt(DTE) / sqrt(252)

    Shortcut often cited: daily ≈ price * IV / 16  (since sqrt(252) ≈ 15.87).
    """
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

        exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
        dte = max((exp_date - date.today()).days, 1)
        sqrt_year = math.sqrt(TRADING_DAYS_PER_YEAR)

        daily_move = (price * iv) / sqrt_year
        weekly_move = (price * iv * math.sqrt(5.0)) / sqrt_year
        exp_move = (price * iv * math.sqrt(float(dte))) / sqrt_year

        return {
            'iv': round(iv * 100.0, 2),           # percent
            'iv_decimal': iv,
            'daily_move': round(daily_move, 2),
            'daily_pct': round((daily_move / price) * 100.0, 2),
            'weekly_move': round(weekly_move, 2),
            'weekly_pct': round((weekly_move / price) * 100.0, 2),
            'exp_move': round(exp_move, 2),
            'exp_pct': round((exp_move / price) * 100.0, 2),
            'dte': dte,
            'expiration': exp_str,
            'price_used': round(price, 2),
        }
    except Exception:
        return None


def attach_expected_moves(results: List[Dict[str, Any]], verbose: bool = True) -> None:
    """Fetch options IV and attach expected_move dict onto each result (in place)."""
    if not results:
        return
    if verbose:
        print(f"\nFetching ATM IV / expected move for {len(results)} ticker(s)...")
    for r in results:
        ticker = r['ticker']
        price = r.get('price')
        if price is None or price <= 0:
            r['expected_move'] = None
            if verbose:
                print(f"  {ticker}: skipped (no price)")
            continue
        em = get_expected_move(ticker, float(price))
        r['expected_move'] = em
        if verbose:
            if em:
                print(
                    f"  {ticker}: IV {em['iv']:.1f}% | "
                    f"daily ±${em['daily_move']:.2f} ({em['daily_pct']:.1f}%) | "
                    f"exp {em['expiration']} ({em['dte']} DTE)"
                )
            else:
                print(f"  {ticker}: expected move unavailable (no chain/IV)")


def print_expected_moves(results: List[Dict[str, Any]], markdown: bool = True) -> None:
    """Print expected move table (markdown or plain). Uses pre-attached expected_move when present."""
    title = f"Expected Move (1-sigma) — {datetime.now().strftime('%Y-%m-%d')}"
    if markdown:
        print(f"\n## {title}")
        print()
        print(
            f"| {'Ticker':>6} | {'Price':>8} | {'IV':>6} | {'Daily +/-':>16} | "
            f"{'Weekly +/-':>16} | {'To Exp +/-':>16} | {'DTE':>4} | {'Exp':>12} |"
        )
        print(
            f"|{'-' * 8}|{'-' * 10}|{'-' * 8}|{'-' * 18}|"
            f"{'-' * 18}|{'-' * 18}|{'-' * 6}|{'-' * 14}|"
        )
    else:
        print(f"\n{title}")
        print("-" * 100)

    moves: List[Dict[str, Any]] = []
    for r in results:
        ticker = r['ticker']
        price = r.get('price')
        em = r.get('expected_move')
        # Lazy fetch if not pre-attached
        if em is None and 'expected_move' not in r and price:
            em = get_expected_move(ticker, float(price))
            r['expected_move'] = em

        if price is None:
            price = (em or {}).get('price_used') or 0

        if em:
            moves.append(em)
            daily = f"${em['daily_move']:.2f} ({em['daily_pct']:.1f}%)"
            weekly = f"${em['weekly_move']:.2f} ({em['weekly_pct']:.1f}%)"
            to_exp = f"${em['exp_move']:.2f} ({em['exp_pct']:.1f}%)"
            if markdown:
                print(
                    f"| {ticker:>6} | ${float(price):>7.2f} | {em['iv']:>5.1f}% | "
                    f"{daily:>16} | {weekly:>16} | {to_exp:>16} | "
                    f"{em['dte']:>4} | {em['expiration']:>12} |"
                )
            else:
                print(
                    f"  {ticker:<6}  ${float(price):>8.2f}  IV {em['iv']:>5.1f}%  "
                    f"daily {daily}  weekly {weekly}  to-exp {to_exp}  "
                    f"DTE {em['dte']} ({em['expiration']})"
                )
        else:
            if markdown:
                print(
                    f"| {ticker:>6} | ${float(price or 0):>7.2f} | {'N/A':>6} | "
                    f"{'N/A':>16} | {'N/A':>16} | {'N/A':>16} | {'N/A':>4} | {'N/A':>12} |"
                )
            else:
                print(f"  {ticker:<6}  expected move N/A")

    if moves:
        avg_iv = sum(m['iv'] for m in moves) / len(moves)
        avg_daily_pct = sum(m['daily_pct'] for m in moves) / len(moves)
        note = (
            f"Avg IV: {avg_iv:.1f}% | Avg daily expected move: +/-{avg_daily_pct:.2f}% | "
            f"Formula: Price x IV / sqrt(252) (1-sigma ~ 68% range if IV is well-specified)"
        )
        if markdown:
            print()
            print(f"*{note}*")
            print(
                "*IV from ATM option on nearest listed expiration; "
                "not a guarantee of realized range. See Expected-Move-Guide.md.*"
            )
        else:
            print(f"\n  {note}")


# ---------------------------------------------------------------------------
# Nine rules analysis
# ---------------------------------------------------------------------------

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

    min_bars = 200 if period in ('1y', '2y', 'max') else 100
    indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=min_bars)
    if indicators is None and min_bars > 100:
        indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=100)
    if indicators is None:
        return None

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
        'expected_move': None,  # filled later by attach_expected_moves
    }


def run_analysis(tickers, market_breadth_pct=None, breadth_data=None, verbose=True):
    """Run nine-rules gate on a list of tickers or watchlist dicts."""
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


def print_summary(results, show_expected_move=True):
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

    if show_expected_move:
        print_expected_moves(results, markdown=False)


def print_briefing(results, show_expected_move=True):
    print(f"## Nine Rules Gate ({datetime.now().strftime('%Y-%m-%d')})")
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

    if show_expected_move:
        print_expected_moves(results, markdown=True)


def main():
    parser = argparse.ArgumentParser(
        description='Nine Rules Gate - shared indicators + IV expected move',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  From watchlist:    python3 nine_rules_gate.py
  Specific tickers:  python3 nine_rules_gate.py --tickers AAPL MSFT NVDA AMD
  Custom watchlist:  python3 nine_rules_gate.py --watchlist my_stocks.json
  Markdown output:   python3 nine_rules_gate.py --briefing
  Verbose details:   python3 nine_rules_gate.py --verbose
  Skip options/IV:   python3 nine_rules_gate.py --no-expected-move
        """,
    )
    parser.add_argument('--tickers', nargs='+', help='Specific tickers to analyze')
    parser.add_argument('--watchlist', type=str, default=None, help='Path to watchlist JSON')
    parser.add_argument('--briefing', action='store_true', help='Markdown briefing output')
    parser.add_argument('--verbose', action='store_true', help='Show per-rule details')
    parser.add_argument(
        '--no-expected-move',
        action='store_true',
        help='Skip ATM IV / expected-move options fetch (faster)',
    )

    args = parser.parse_args()
    show_em = not args.no_expected_move

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
            print("Or specify tickers: python3 nine_rules_gate.py --tickers AAPL MSFT")
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

    if show_em and results:
        attach_expected_moves(results, verbose=True)

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
            em = r.get('expected_move')
            if em:
                print(
                    f"  [i] Expected move: IV {em['iv']:.1f}% | "
                    f"daily ±${em['daily_move']:.2f} ({em['daily_pct']:.1f}%) | "
                    f"to {em['expiration']} ±${em['exp_move']:.2f} ({em['dte']} DTE)"
                )
            elif show_em:
                print("  [i] Expected move: N/A")

    if args.briefing:
        print()
        print_briefing(results, show_expected_move=show_em)
    else:
        print_summary(results, show_expected_move=show_em)


if __name__ == '__main__':
    main()
