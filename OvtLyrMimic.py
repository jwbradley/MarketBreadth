#!/usr/bin/env python3
"""
OVTLYR Nine Rules Analysis (v2)

Python implementation mimicking OVTLYR's Nine Rules framework.
Now integrates with the market breadth collector and stock screener
for real breadth data and auto-generated watchlists.

Data sources:
  - ovtlyr_watchlist.json (from stock_screener.py --watchlist)
  - market_breadth_latest.json (from market_breadth_collector.py)
  - Or: manual ticker list via command-line arguments

Usage:
  python3 OvtLyrMimic.py                           # Analyze watchlist from stock_screener
  python3 OvtLyrMimic.py --tickers AAPL MSFT NVDA  # Analyze specific tickers
  python3 OvtLyrMimic.py --watchlist path/to/file   # Custom watchlist file
  python3 OvtLyrMimic.py --briefing                 # Markdown output
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import sys
import argparse
from datetime import datetime

# File paths
DATA_DIR = os.environ.get('GSR_DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_FILE = os.path.join(DATA_DIR, 'ovtlyr_watchlist.json')
BREADTH_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')


class OVTLYRNineRules:
    """
    OVTLYR Nine Rules analysis for a single stock.
    Integrates real market and sector breadth data.
    """

    def __init__(self, ticker, market_breadth_pct=None, sector_breadth_pct=None):
        self.ticker = ticker
        self.market_breadth_pct = market_breadth_pct
        self.sector_breadth_pct = sector_breadth_pct
        self.data = None
        self.spy_data = None
        self.rules_status = {}

    def fetch_data(self, period='6mo'):
        """Fetch stock and SPY data."""
        try:
            self.data = yf.download(self.ticker, period=period, progress=False, auto_adjust=True)
            self.spy_data = yf.download('SPY', period=period, progress=False, auto_adjust=True)

            if isinstance(self.data.columns, pd.MultiIndex):
                self.data.columns = self.data.columns.get_level_values(0)
            if isinstance(self.spy_data.columns, pd.MultiIndex):
                self.spy_data.columns = self.spy_data.columns.get_level_values(0)

            return not self.data.empty and not self.spy_data.empty
        except Exception:
            return False

    def _ema(self, data, period):
        return data['Close'].ewm(span=period, adjust=False).mean()

    def _rsi(self, period=14):
        delta = self.data['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _atr(self, period=14):
        high, low, close = self.data['High'], self.data['Low'], self.data['Close']
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def rule_1_trend_confirmation(self):
        """Price > 10 EMA > 20 EMA > 50 EMA"""
        ema10 = float(self._ema(self.data, 10).iloc[-1])
        ema20 = float(self._ema(self.data, 20).iloc[-1])
        ema50 = float(self._ema(self.data, 50).iloc[-1])
        price = float(self.data['Close'].iloc[-1])

        passed = price > ema10 > ema20 > ema50
        self.rules_status['Rule 1: Trend Confirmation'] = {
            'passed': passed,
            'details': f"Price: ${price:.2f}, 10EMA: ${ema10:.2f}, 20EMA: ${ema20:.2f}, 50EMA: ${ema50:.2f}"
        }
        return passed

    def rule_2_signal_alignment(self):
        """Price above 20 EMA with positive 5-day momentum"""
        ema20 = float(self._ema(self.data, 20).iloc[-1])
        price = float(self.data['Close'].iloc[-1])
        price_5d_ago = float(self.data['Close'].iloc[-5])

        passed = (price > ema20) and (price > price_5d_ago)
        self.rules_status['Rule 2: Signal Alignment'] = {
            'passed': passed,
            'details': f"Above 20EMA: {price > ema20}, 5-day momentum: {price > price_5d_ago}"
        }
        return passed

    def rule_3_market_breadth(self):
        """Market breadth > 50% (real data from breadth collector)"""
        if self.market_breadth_pct is not None:
            breadth = self.market_breadth_pct
        else:
            # Fallback: estimate from SPY position vs 50 EMA
            spy_ema50 = float(self._ema(self.spy_data, 50).iloc[-1])
            spy_price = float(self.spy_data['Close'].iloc[-1])
            breadth = 60 if spy_price > spy_ema50 else 40

        passed = breadth >= 50
        self.rules_status['Rule 3: Market Breadth'] = {
            'passed': passed,
            'details': f"Breadth: {breadth:.1f}% above 50-DMA (threshold: 50%)"
        }
        return passed

    def rule_4_sector_strength(self):
        """Sector breadth > 50% (real data from breadth collector)"""
        if self.sector_breadth_pct is not None:
            breadth = self.sector_breadth_pct
        else:
            breadth = 55  # Default assumption if no data

        passed = breadth >= 50
        self.rules_status['Rule 4: Sector Strength'] = {
            'passed': passed,
            'details': f"Sector breadth: {breadth:.1f}% above 50-DMA (threshold: 50%)"
        }
        return passed

    def rule_5_behavioral_sentiment(self):
        """RSI between 40-70 (strength without overextension)"""
        rsi = float(self._rsi().iloc[-1])
        passed = 40 <= rsi <= 70
        self.rules_status['Rule 5: Behavioral Sentiment'] = {
            'passed': passed,
            'details': f"RSI: {rsi:.1f} (optimal: 40-70)"
        }
        return passed

    def rule_6_liquidity_volume(self):
        """Current volume > 80% of 20-day average"""
        avg_vol = float(self.data['Volume'].rolling(20).mean().iloc[-1])
        curr_vol = float(self.data['Volume'].iloc[-1])
        passed = curr_vol > (avg_vol * 0.8)
        self.rules_status['Rule 6: Liquidity/Volume'] = {
            'passed': passed,
            'details': f"Volume: {curr_vol:,.0f}, 20d avg: {avg_vol:,.0f}, ratio: {curr_vol/avg_vol:.2f}x"
        }
        return passed

    def rule_7_position_sizing(self):
        """ATR < 8% of price (manageable volatility)"""
        atr = float(self._atr().iloc[-1])
        price = float(self.data['Close'].iloc[-1])
        atr_pct = (atr / price) * 100
        passed = atr_pct < 8
        self.rules_status['Rule 7: Position Sizing (ATR)'] = {
            'passed': passed,
            'details': f"ATR: ${atr:.2f} ({atr_pct:.1f}% of price)"
        }
        return passed

    def rule_8_multi_timeframe(self):
        """Price above both 20 EMA (short) and 100 EMA (long)"""
        ema20 = float(self._ema(self.data, 20).iloc[-1])
        ema100 = float(self._ema(self.data, 100).iloc[-1])
        price = float(self.data['Close'].iloc[-1])
        passed = (price > ema20) and (price > ema100)
        self.rules_status['Rule 8: Multi-Timeframe'] = {
            'passed': passed,
            'details': f"Above 20EMA: {price > ema20}, Above 100EMA: {price > ema100}"
        }
        return passed

    def rule_9_no_contradictions(self):
        """No bearish divergence (price up + RSI down while overbought)"""
        rsi = self._rsi()
        current_rsi = float(rsi.iloc[-1])
        rsi_5d_ago = float(rsi.iloc[-5])
        price = float(self.data['Close'].iloc[-1])
        price_5d_ago = float(self.data['Close'].iloc[-5])

        price_rising = price > price_5d_ago
        rsi_rising = current_rsi > rsi_5d_ago

        if price_rising and not rsi_rising:
            passed = current_rsi < 70  # Bearish divergence only a problem if overbought
        else:
            passed = True

        self.rules_status['Rule 9: No Contradictions'] = {
            'passed': passed,
            'details': f"Price: {'Up' if price_rising else 'Down'}, RSI: {'Up' if rsi_rising else 'Down'} ({current_rsi:.1f})"
        }
        return passed

    def evaluate(self):
        """Run all 9 rules and return results."""
        if self.data is None:
            if not self.fetch_data():
                return None

        results = [
            self.rule_1_trend_confirmation(),
            self.rule_2_signal_alignment(),
            self.rule_3_market_breadth(),
            self.rule_4_sector_strength(),
            self.rule_5_behavioral_sentiment(),
            self.rule_6_liquidity_volume(),
            self.rule_7_position_sizing(),
            self.rule_8_multi_timeframe(),
            self.rule_9_no_contradictions(),
        ]

        passed_count = sum(results)
        total = len(results)

        # Relative strength vs SPY (bonus info)
        rs_vs_spy = None
        if len(self.data) >= 20 and len(self.spy_data) >= 20:
            stock_ret = (float(self.data['Close'].iloc[-1]) / float(self.data['Close'].iloc[-20]) - 1) * 100
            spy_ret = (float(self.spy_data['Close'].iloc[-1]) / float(self.spy_data['Close'].iloc[-20]) - 1) * 100
            rs_vs_spy = round(stock_ret - spy_ret, 2)

        # Generate signal
        if passed_count >= 8:
            signal = "STRONG BUY"
        elif passed_count >= 6:
            signal = "BUY"
        elif passed_count >= 4:
            signal = "NEUTRAL"
        else:
            signal = "SELL/AVOID"

        return {
            'ticker': self.ticker,
            'signal': signal,
            'rules_passed': passed_count,
            'total_rules': total,
            'percentage': round((passed_count / total) * 100, 1),
            'rs_vs_spy': rs_vs_spy,
            'details': self.rules_status
        }


def load_watchlist(watchlist_path=None):
    """Load the watchlist generated by stock_screener.py."""
    path = watchlist_path or WATCHLIST_FILE
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)


def load_breadth():
    """Load market breadth data."""
    if not os.path.exists(BREADTH_FILE):
        return None
    with open(BREADTH_FILE, 'r') as f:
        return json.load(f)


def get_sector_breadth(breadth_data, sector_name):
    """Get pct_above_50dma for a specific sector."""
    if breadth_data and 'sectors' in breadth_data and sector_name in breadth_data['sectors']:
        return breadth_data['sectors'][sector_name].get('pct_above_50dma')
    return None


def run_analysis(tickers, market_breadth_pct=None, sector_map=None, breadth_data=None, verbose=True):
    """Run OVTLYR analysis on a list of tickers."""
    results = []

    for ticker_info in tickers:
        if isinstance(ticker_info, dict):
            ticker = ticker_info['ticker']
            sector = ticker_info.get('sector')
            sector_breadth = ticker_info.get('sector_breadth_pct')
        else:
            ticker = ticker_info
            sector = sector_map.get(ticker) if sector_map else None
            sector_breadth = get_sector_breadth(breadth_data, sector) if sector and breadth_data else None

        if verbose:
            print(f"  Analyzing {ticker}...", end=' ')

        analyzer = OVTLYRNineRules(ticker, market_breadth_pct, sector_breadth)
        result = analyzer.evaluate()

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
    """Print summary table."""
    print(f"\n{'='*90}")
    print(f"{'Ticker':<8} {'Sector':<28} {'Signal':<12} {'Rules':<8} {'RS/SPY':<8} {'Pass%':<8}")
    print(f"{'-'*90}")

    results.sort(key=lambda x: x['rules_passed'], reverse=True)

    for r in results:
        rs = f"{r['rs_vs_spy']:+.1f}%" if r.get('rs_vs_spy') is not None else "N/A"
        sector = (r.get('sector') or 'N/A')[:27]
        print(f"{r['ticker']:<8} {sector:<28} {r['signal']:<12} {r['rules_passed']}/9{'':<4} {rs:<8} {r['percentage']:.0f}%")

    print(f"{'='*90}")

    # Signal distribution
    signals = {}
    for r in results:
        signals[r['signal']] = signals.get(r['signal'], 0) + 1
    print(f"\nSignal Distribution:")
    for sig in ['STRONG BUY', 'BUY', 'NEUTRAL', 'SELL/AVOID']:
        print(f"  {sig}: {signals.get(sig, 0)}")
    print(f"\nTotal Analyzed: {len(results)}")


def print_briefing(results):
    """Print markdown briefing."""
    print(f"## OVTLYR Nine Rules Analysis ({datetime.now().strftime('%Y-%m-%d')})")
    print()
    print(f"| {'Ticker':>6} | {'Sector':>25} | {'Signal':>12} | {'Rules':>5} | {'RS/SPY':>7} |")
    print(f"|{'-'*8}|{'-'*27}|{'-'*14}|{'-'*7}|{'-'*9}|")

    results.sort(key=lambda x: x['rules_passed'], reverse=True)
    for r in results:
        rs = f"{r['rs_vs_spy']:+.1f}%" if r.get('rs_vs_spy') is not None else "N/A"
        sector = (r.get('sector') or 'N/A')[:25]
        print(f"| {r['ticker']:>6} | {sector:>25} | {r['signal']:>12} | {r['rules_passed']:>3}/9 | {rs:>7} |")


def main():
    parser = argparse.ArgumentParser(
        description='OVTLYR Nine Rules Analysis — integrates with market breadth and stock screener',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  From watchlist:    python3 OvtLyrMimic.py
  Specific tickers:  python3 OvtLyrMimic.py --tickers AAPL MSFT NVDA AMD
  Custom watchlist:  python3 OvtLyrMimic.py --watchlist my_stocks.json
  Markdown output:   python3 OvtLyrMimic.py --briefing
  Verbose details:   python3 OvtLyrMimic.py --verbose
        """
    )
    parser.add_argument('--tickers', nargs='+', help='Specific tickers to analyze')
    parser.add_argument('--watchlist', type=str, default=None, help='Path to watchlist JSON')
    parser.add_argument('--briefing', action='store_true', help='Markdown briefing output')
    parser.add_argument('--verbose', action='store_true', help='Show per-rule details for each stock')

    args = parser.parse_args()

    # Load breadth data for real market/sector context
    breadth_data = load_breadth()
    market_breadth_pct = None
    if breadth_data and 'sp500' in breadth_data:
        market_breadth_pct = breadth_data['sp500'].get('pct_above_50dma')
        print(f"Market breadth loaded: {market_breadth_pct}% above 50-DMA")

    # Determine what to analyze
    if args.tickers:
        # Manual ticker list
        tickers = args.tickers
        print(f"\nAnalyzing {len(tickers)} tickers: {', '.join(tickers)}")
        print(f"{'='*60}\n")
        results = run_analysis(tickers, market_breadth_pct, breadth_data=breadth_data)

    else:
        # Load from watchlist
        watchlist = load_watchlist(args.watchlist)
        if watchlist is None:
            print("No watchlist found. Run: python3 stock_screener.py --watchlist")
            print("Or specify tickers: python3 OvtLyrMimic.py --tickers AAPL MSFT")
            sys.exit(1)

        # Use watchlist's market breadth if available
        if watchlist.get('market_breadth_pct'):
            market_breadth_pct = watchlist['market_breadth_pct']

        print(f"\nWatchlist loaded: {len(watchlist['stocks'])} stocks from {watchlist['source_date']}")
        print(f"Market breadth: {market_breadth_pct}% above 50-DMA")
        print(f"{'='*60}\n")

        results = run_analysis(watchlist['stocks'], market_breadth_pct, breadth_data=breadth_data)

    # Show detailed rule output if verbose
    if args.verbose and results:
        for r in results:
            print(f"\n{'='*60}")
            print(f"  {r['ticker']} — {r['signal']} ({r['rules_passed']}/9)")
            print(f"{'='*60}")
            if 'details' in r:
                for rule_name, status in r['details'].items():
                    symbol = "+" if status['passed'] else "x"
                    print(f"  [{symbol}] {rule_name}")
                    print(f"      {status['details']}")

    # Output
    if args.briefing:
        print()
        print_briefing(results)
    else:
        print_summary(results)


if __name__ == "__main__":
    main()
