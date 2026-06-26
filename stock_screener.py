#!/usr/bin/env python3
"""
Stock Screener — Technical Analysis of Top/Bottom Sector Leaders

Reads market breadth data to identify the top 2 and bottom 2 sectors,
then performs technical analysis on the top 10-20 stocks in each sector.

Indicators calculated per stock:
  - Price vs 20/50/200 DMA (trend alignment)
  - RSI (14-day) — overbought/oversold
  - MACD + Signal + Histogram — momentum
  - Bollinger Bands %B — volatility positioning
  - Volume ratio vs 20-day average — liquidity/conviction
  - Average daily volume — liquidity screen

Setup:
  pip install yfinance pandas numpy
  Requires: market_breadth_latest.json (from market_breadth_collector.py)

Usage:
  python3 stock_screener.py                    # Auto-select top 2 + bottom 2 sectors
  python3 stock_screener.py --sectors 2        # Top/bottom N sectors (default 2)
  python3 stock_screener.py --top-stocks 15    # Analyze top N stocks per sector (default 10)
  python3 stock_screener.py --sector "Energy"  # Analyze a specific sector
  python3 stock_screener.py --briefing         # Markdown output for reports
  python3 stock_screener.py --csv              # Export to CSV
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

# Configuration
DATA_DIR = os.environ.get('MARKET_BREADTH_DIR',
           os.environ.get('GSR_DATA_DIR',
           os.path.dirname(os.path.abspath(__file__))))
BREADTH_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')
OUTPUT_FILE = os.path.join(DATA_DIR, 'stock_screener_results.json')

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
    """Identify top N and bottom N sectors by A/D ratio."""
    if specific_sector:
        return [specific_sector], []

    sectors = breadth_data['sectors']
    sorted_sectors = sorted(sectors.items(), key=lambda x: x[1]['ad_ratio'], reverse=True)

    top = [s[0] for s in sorted_sectors[:num_sectors]]
    bottom = [s[0] for s in sorted_sectors[-num_sectors:]]

    return top, bottom


def calculate_indicators(ticker_symbol):
    """Calculate all technical indicators for a single stock."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        hist = ticker.history(period='1y')

        if hist.empty or len(hist) < 200:
            return None

        close = hist['Close']
        volume = hist['Volume']
        latest_price = float(close.iloc[-1])

        # Moving Averages
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        sma200 = close.rolling(200).mean()

        # RSI (14-day)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal

        # Bollinger Bands (20-day, 2 std)
        bb_std = close.rolling(20).std()
        bb_upper = sma20 + (bb_std * 2)
        bb_lower = sma20 - (bb_std * 2)
        bb_pct = (close - bb_lower) / (bb_upper - bb_lower)

        # Volume
        avg_vol_20 = volume.rolling(20).mean()
        vol_ratio = float(volume.iloc[-1] / avg_vol_20.iloc[-1]) if avg_vol_20.iloc[-1] > 0 else 0

        # Trend alignment score (0-3: how many MAs price is above)
        trend_score = sum([
            latest_price > float(sma20.iloc[-1]),
            latest_price > float(sma50.iloc[-1]),
            latest_price > float(sma200.iloc[-1])
        ])

        # MA alignment (bullish: 20 > 50 > 200)
        ma_aligned = (float(sma20.iloc[-1]) > float(sma50.iloc[-1]) > float(sma200.iloc[-1]))

        return {
            'ticker': ticker_symbol,
            'price': round(latest_price, 2),
            'sma20': round(float(sma20.iloc[-1]), 2),
            'sma50': round(float(sma50.iloc[-1]), 2),
            'sma200': round(float(sma200.iloc[-1]), 2),
            'above_20dma': latest_price > float(sma20.iloc[-1]),
            'above_50dma': latest_price > float(sma50.iloc[-1]),
            'above_200dma': latest_price > float(sma200.iloc[-1]),
            'trend_score': trend_score,
            'ma_aligned': ma_aligned,
            'rsi': round(float(rsi.iloc[-1]), 1),
            'macd': round(float(macd.iloc[-1]), 3),
            'macd_signal': round(float(signal.iloc[-1]), 3),
            'macd_hist': round(float(macd_hist.iloc[-1]), 3),
            'macd_bullish': float(macd.iloc[-1]) > float(signal.iloc[-1]),
            'bb_pct': round(float(bb_pct.iloc[-1]), 2),
            'bb_position': 'overbought' if float(bb_pct.iloc[-1]) > 0.8 else ('oversold' if float(bb_pct.iloc[-1]) < 0.2 else 'neutral'),
            'volume_ratio': round(vol_ratio, 2),
            'avg_volume_20d': int(avg_vol_20.iloc[-1]),
            'daily_volume': int(volume.iloc[-1]),
        }
    except Exception as e:
        return None


def score_stock(indicators):
    """Generate a composite score (0-100) based on all indicators."""
    score = 50  # Start neutral

    # Trend alignment (+/- 20)
    score += (indicators['trend_score'] - 1.5) * 13

    # MA alignment bonus
    if indicators['ma_aligned']:
        score += 5

    # RSI (+/- 15)
    rsi = indicators['rsi']
    if 40 <= rsi <= 60:
        score += 5  # Neutral is fine
    elif rsi > 70:
        score -= 10  # Overbought risk
    elif rsi < 30:
        score += 10  # Oversold opportunity (for bottom sectors, this is key)

    # MACD (+/- 10)
    if indicators['macd_bullish']:
        score += 8
    else:
        score -= 8

    # Bollinger position (+/- 10)
    bb = indicators['bb_pct']
    if 0.2 <= bb <= 0.8:
        score += 5
    elif bb < 0.1:
        score += 8  # Oversold bounce potential
    elif bb > 0.95:
        score -= 8  # Extended

    # Volume confirmation (+/- 5)
    if indicators['volume_ratio'] > 1.5:
        score += 5  # High volume = conviction
    elif indicators['volume_ratio'] < 0.5:
        score -= 3  # Low volume = weak move

    return max(0, min(100, round(score)))


def analyze_sector(sector_name, sp500_df, top_n=10):
    """Analyze top N stocks in a sector by market presence."""
    sector_stocks = sp500_df[sp500_df['GICS Sector'] == sector_name]['Symbol'].tolist()
    sector_stocks = [t.replace('.', '-') for t in sector_stocks]

    print(f"[{LOG_PREFIX}]   Analyzing {len(sector_stocks)} stocks in {sector_name} (top {top_n})...")

    results = []
    for i, ticker in enumerate(sector_stocks[:top_n * 2]):  # Fetch extra in case some fail
        if len(results) >= top_n:
            break
        indicators = calculate_indicators(ticker)
        if indicators:
            indicators['sector'] = sector_name
            indicators['score'] = score_stock(indicators)
            results.append(indicators)
            if (i + 1) % 5 == 0:
                print(f"[{LOG_PREFIX}]     Processed {i+1}/{min(len(sector_stocks), top_n*2)} tickers...")

    # Sort by composite score
    results.sort(key=lambda x: x['score'], reverse=True)
    return results


def run_screener(num_sectors=2, top_stocks=10, specific_sector=None):
    """Main screener routine."""
    breadth = load_breadth()
    sp500 = load_constituents()

    top_sectors, bottom_sectors = get_target_sectors(breadth, num_sectors, specific_sector)

    print(f"[{LOG_PREFIX}] Stock Screener — Technical Analysis")
    print(f"[{LOG_PREFIX}] Breadth data from: {breadth['date']}")
    if not specific_sector:
        print(f"[{LOG_PREFIX}] Top sectors (strongest A/D): {top_sectors}")
        print(f"[{LOG_PREFIX}] Bottom sectors (weakest A/D): {bottom_sectors}")
    else:
        print(f"[{LOG_PREFIX}] Analyzing sector: {specific_sector}")
    print()

    all_results = {}

    # Analyze top sectors (buy candidates)
    for sector in top_sectors:
        print(f"[{LOG_PREFIX}] === TOP SECTOR: {sector} ===")
        results = analyze_sector(sector, sp500, top_stocks)
        all_results[sector] = {'type': 'top', 'stocks': results}
        print(f"[{LOG_PREFIX}]   Completed: {len(results)} stocks analyzed")
        print()

    # Analyze bottom sectors (avoid/short candidates)
    for sector in bottom_sectors:
        print(f"[{LOG_PREFIX}] === BOTTOM SECTOR: {sector} ===")
        results = analyze_sector(sector, sp500, top_stocks)
        all_results[sector] = {'type': 'bottom', 'stocks': results}
        print(f"[{LOG_PREFIX}]   Completed: {len(results)} stocks analyzed")
        print()

    # Save results
    output = {
        'date': breadth['date'],
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sectors': all_results
    }
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[{LOG_PREFIX}] Results saved to {OUTPUT_FILE}")

    return output


def show_briefing():
    """Output markdown briefing."""
    if not os.path.exists(OUTPUT_FILE):
        print("No screener results found. Run without --briefing first.")
        return

    with open(OUTPUT_FILE, 'r') as f:
        data = json.load(f)

    print(f"## Stock Screener ({data['date']})")
    print()

    for sector, info in data['sectors'].items():
        label = "STRONGEST" if info['type'] == 'top' else "WEAKEST"
        print(f"### {label}: {sector}")
        print()
        print(f"| {'Ticker':>6} | {'Price':>8} | {'Score':>5} | {'Trend':>5} | {'RSI':>5} | {'MACD':>6} | {'BB%':>5} | {'Vol':>5} | {'Signal':>10} |")
        print(f"|{'-'*8}|{'-'*10}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*8}|{'-'*7}|{'-'*7}|{'-'*12}|")

        for s in info['stocks']:
            trend = f"{s['trend_score']}/3"
            macd_dir = "Bull" if s['macd_bullish'] else "Bear"
            vol = f"{s['volume_ratio']:.1f}x"

            # Generate signal
            if s['score'] >= 70:
                signal = "Strong Buy"
            elif s['score'] >= 60:
                signal = "Buy"
            elif s['score'] >= 40:
                signal = "Neutral"
            elif s['score'] >= 30:
                signal = "Weak"
            else:
                signal = "Avoid"

            print(f"| {s['ticker']:>6} | ${s['price']:>7.2f} | {s['score']:>5} | {trend:>5} | {s['rsi']:>5.1f} | {macd_dir:>6} | {s['bb_pct']:>5.2f} | {vol:>5} | {signal:>10} |")

        print()


def export_csv(output_path=None):
    """Export results to CSV."""
    if not os.path.exists(OUTPUT_FILE):
        print("No results found. Run screener first.")
        return

    if not output_path:
        output_path = os.path.join(DATA_DIR, 'stock_screener_results.csv')

    with open(OUTPUT_FILE, 'r') as f:
        data = json.load(f)

    rows = []
    for sector, info in data['sectors'].items():
        for stock in info['stocks']:
            stock['sector_type'] = info['type']
            rows.append(stock)

    fieldnames = ['sector', 'sector_type', 'ticker', 'price', 'score',
                  'trend_score', 'ma_aligned', 'above_20dma', 'above_50dma', 'above_200dma',
                  'sma20', 'sma50', 'sma200', 'rsi', 'macd', 'macd_signal', 'macd_hist',
                  'macd_bullish', 'bb_pct', 'bb_position', 'volume_ratio', 'avg_volume_20d', 'daily_volume']

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f"[{LOG_PREFIX}] Exported {len(rows)} stocks to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Stock Screener — Technical analysis of top/bottom sector leaders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze top 2 + bottom 2:     python3 stock_screener.py
  Top/bottom 3 sectors:         python3 stock_screener.py --sectors 3
  More stocks per sector:       python3 stock_screener.py --top-stocks 20
  Specific sector:              python3 stock_screener.py --sector "Energy"
  Markdown briefing:            python3 stock_screener.py --briefing
  Export to CSV:                python3 stock_screener.py --csv
        """
    )
    parser.add_argument('--sectors', type=int, default=2, help='Number of top/bottom sectors to analyze')
    parser.add_argument('--top-stocks', type=int, default=10, help='Number of stocks per sector')
    parser.add_argument('--sector', type=str, default=None, help='Analyze a specific sector')
    parser.add_argument('--briefing', action='store_true', help='Show markdown briefing')
    parser.add_argument('--csv', nargs='?', const='', default=None, help='Export to CSV')

    args = parser.parse_args()

    if args.briefing:
        show_briefing()
    elif args.csv is not None:
        export_csv(args.csv if args.csv else None)
    else:
        run_screener(args.sectors, args.top_stocks, args.sector)


if __name__ == '__main__':
    main()
