#!/usr/bin/env python3
"""
Market Breadth Collector
Calculates advance/decline ratios, % above moving averages, and new highs/lows
for the S&P 500 and each of the 11 GICS sectors.

Setup:
  1. pip install yfinance pandas
  2. Run: python3 market_breadth_collector.py

Crontab example (run at 5:45 PM CT Monday-Friday after market close):
  45 17 * * 1-5 /usr/bin/python3 /home/pi/scripts/market_breadth_collector.py >> /home/pi/logs/market_breadth.log 2>&1

Output:
  - market_breadth_latest.json: Current breadth snapshot (all sectors)
  - market_breadth_history.json: Daily history of breadth metrics
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("ERROR: Required packages not installed.")
    print("Run: pip install yfinance pandas")
    sys.exit(1)

# File paths
DATA_DIR = os.environ.get('MARKET_BREADTH_DIR',
           os.environ.get('GSR_DATA_DIR',
           os.path.dirname(os.path.abspath(__file__))))
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')
HISTORY_FILE = os.path.join(DATA_DIR, 'market_breadth_history.json')
LATEST_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')
CONSTITUENTS_URL = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'

LOG_PREFIX = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def update_constituents():
    """Download latest S&P 500 constituent list from GitHub."""
    print(f"[{LOG_PREFIX}] Updating S&P 500 constituent list...")
    try:
        sp500 = pd.read_csv(CONSTITUENTS_URL)
        sp500[['Symbol', 'Security', 'GICS Sector', 'GICS Sub-Industry']].to_csv(CONSTITUENTS_FILE, index=False)
        print(f"[{LOG_PREFIX}] Saved {len(sp500)} constituents to {CONSTITUENTS_FILE}")
        return sp500
    except Exception as e:
        print(f"[{LOG_PREFIX}] Failed to update constituents: {e}")
        if os.path.exists(CONSTITUENTS_FILE):
            print(f"[{LOG_PREFIX}] Using existing local file.")
            return pd.read_csv(CONSTITUENTS_FILE)
        sys.exit(1)


def load_constituents():
    """Load S&P 500 constituents, downloading if not present."""
    if not os.path.exists(CONSTITUENTS_FILE):
        return update_constituents()
    sp500 = pd.read_csv(CONSTITUENTS_FILE)
    file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(CONSTITUENTS_FILE))
    if file_age.days > 30:
        print(f"[{LOG_PREFIX}] Constituent list is {file_age.days} days old, refreshing...")
        return update_constituents()
    return sp500


def calculate_breadth(close_data, tickers_in_sector):
    """Calculate all breadth metrics for a set of tickers."""
    sector_close = close_data[close_data.columns.intersection(tickers_in_sector)]

    if sector_close.empty:
        return None

    total = sector_close.iloc[-1].notna().sum()
    if total == 0:
        return None

    # Advance/Decline (today)
    daily_chg = sector_close.pct_change().iloc[-1]
    advancing = int((daily_chg > 0).sum())
    declining = int((daily_chg < 0).sum())
    unchanged = int((daily_chg == 0).sum())
    ad_ratio = round(advancing / max(declining, 1), 2)

    # % Above 50 DMA
    sma50 = sector_close.rolling(50).mean()
    above_50 = int((sector_close.iloc[-1] > sma50.iloc[-1]).sum())
    pct_above_50 = round(above_50 / total * 100, 1)

    # % Above 200 DMA
    sma200 = sector_close.rolling(200).mean()
    above_200_series = sector_close.iloc[-1] > sma200.iloc[-1]
    above_200 = int(above_200_series.sum())
    # Handle case where not enough data for 200 DMA
    valid_200 = int(sma200.iloc[-1].notna().sum())
    pct_above_200 = round(above_200 / max(valid_200, 1) * 100, 1) if valid_200 > 0 else None

    # 52-week Highs and Lows
    high_252 = sector_close.rolling(252, min_periods=200).max()
    low_252 = sector_close.rolling(252, min_periods=200).min()
    new_highs = int((sector_close.iloc[-1] >= high_252.iloc[-1]).sum())
    new_lows = int((sector_close.iloc[-1] <= low_252.iloc[-1]).sum())

    return {
        'total_stocks': int(total),
        'advancing': advancing,
        'declining': declining,
        'unchanged': unchanged,
        'ad_ratio': ad_ratio,
        'above_50dma': above_50,
        'pct_above_50dma': pct_above_50,
        'above_200dma': above_200,
        'pct_above_200dma': pct_above_200,
        'new_52wk_highs': new_highs,
        'new_52wk_lows': new_lows,
    }


def collect_breadth():
    """Main collection routine: download data and calculate breadth for all sectors."""
    sp500 = load_constituents()

    # Fix ticker format for yfinance
    all_tickers = [t.replace('.', '-') for t in sp500['Symbol'].tolist()]
    ticker_to_sector = dict(zip(
        [t.replace('.', '-') for t in sp500['Symbol']],
        sp500['GICS Sector']
    ))

    sectors = sorted(sp500['GICS Sector'].unique())

    print(f"[{LOG_PREFIX}] Downloading 1yr price data for {len(all_tickers)} stocks...")
    data = yf.download(all_tickers, period='1y', progress=False, threads=True)
    close = data['Close']
    trade_date = close.index[-1].strftime('%Y-%m-%d')
    print(f"[{LOG_PREFIX}] Data through {trade_date}, {len(close)} trading days")

    # Calculate breadth for overall S&P 500
    print(f"[{LOG_PREFIX}] Calculating S&P 500 breadth...")
    overall = calculate_breadth(close, all_tickers)

    # Calculate breadth per sector
    sector_breadth = {}
    for sector in sectors:
        sector_tickers = [t.replace('.', '-') for t in
                         sp500[sp500['GICS Sector'] == sector]['Symbol'].tolist()]
        metrics = calculate_breadth(close, sector_tickers)
        if metrics:
            sector_breadth[sector] = metrics
            print(f"[{LOG_PREFIX}]   {sector}: A/D {metrics['advancing']}/{metrics['declining']}, "
                  f"{metrics['pct_above_50dma']}% >50DMA, "
                  f"{metrics['pct_above_200dma']}% >200DMA")

    # Build result
    result = {
        'date': trade_date,
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sp500': overall,
        'sectors': sector_breadth,
    }

    # Save latest
    with open(LATEST_FILE, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"[{LOG_PREFIX}] Saved latest to {LATEST_FILE}")

    # Append to history
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)

    # Remove existing entry for same date (re-run)
    history = [h for h in history if h['date'] != trade_date]
    history.append(result)
    history.sort(key=lambda x: x['date'])

    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)
    print(f"[{LOG_PREFIX}] History updated ({len(history)} days)")

    return result


def show_status():
    """Display current breadth status."""
    if not os.path.exists(LATEST_FILE):
        print("No breadth data found. Run without --status first.")
        return

    with open(LATEST_FILE, 'r') as f:
        data = json.load(f)

    print(f"Market Breadth — {data['date']}")
    print(f"Generated: {data['generated']}")
    print()

    sp = data['sp500']
    print(f"{'S&P 500 OVERALL':30s}  A/D: {sp['advancing']}/{sp['declining']} ({sp['ad_ratio']})  "
          f">50DMA: {sp['pct_above_50dma']}%  >200DMA: {sp['pct_above_200dma']}%  "
          f"Highs: {sp['new_52wk_highs']}  Lows: {sp['new_52wk_lows']}")
    print("-" * 100)

    for sector, metrics in sorted(data['sectors'].items()):
        print(f"{sector:30s}  A/D: {metrics['advancing']}/{metrics['declining']} ({metrics['ad_ratio']})  "
              f">50DMA: {metrics['pct_above_50dma']:5.1f}%  >200DMA: {metrics['pct_above_200dma']:5.1f}%  "
              f"Highs: {metrics['new_52wk_highs']}  Lows: {metrics['new_52wk_lows']}")


def show_briefing():
    """Output markdown briefing for inclusion in market reports."""
    if not os.path.exists(LATEST_FILE):
        print("No breadth data found. Run collection first.")
        return

    with open(LATEST_FILE, 'r') as f:
        data = json.load(f)

    sp = data['sp500']
    print(f"## Market Breadth ({data['date']})")
    print()
    print(f"**S&P 500 Overall:** {sp['advancing']} advancing / {sp['declining']} declining "
          f"(A/D ratio: {sp['ad_ratio']})")
    print(f"- Above 50-DMA: {sp['pct_above_50dma']}% ({sp['above_50dma']}/{sp['total_stocks']})")
    print(f"- Above 200-DMA: {sp['pct_above_200dma']}% ({sp['above_200dma']}/{sp['total_stocks']})")
    print(f"- 52-week Highs: {sp['new_52wk_highs']} | Lows: {sp['new_52wk_lows']}")
    print()

    # Sort sectors by A/D ratio to show strongest to weakest
    sorted_sectors = sorted(data['sectors'].items(),
                           key=lambda x: x[1]['ad_ratio'], reverse=True)

    print("**Sector Breadth (strongest to weakest):**")
    print()
    print(f"| {'Sector':30s} | {'A/D':>7s} | {'Ratio':>5s} | {'>50DMA':>7s} | {'>200DMA':>7s} | {'Highs':>5s} | {'Lows':>4s} |")
    print(f"|{'-'*32}|{'-'*9}|{'-'*7}|{'-'*9}|{'-'*9}|{'-'*7}|{'-'*6}|")
    for sector, m in sorted_sectors:
        print(f"| {sector:30s} | {m['advancing']:>3d}/{m['declining']:<3d} | {m['ad_ratio']:>5.2f} | "
              f"{m['pct_above_50dma']:>5.1f}% | {m['pct_above_200dma']:>5.1f}% | "
              f"{m['new_52wk_highs']:>5d} | {m['new_52wk_lows']:>4d} |")


def export_csv(output_path=None):
    """Export breadth history to CSV."""
    import csv

    if not os.path.exists(HISTORY_FILE):
        print("No history found. Run collection first.")
        return

    if not output_path:
        output_path = os.path.join(DATA_DIR, 'market_breadth_history.csv')

    with open(HISTORY_FILE, 'r') as f:
        history = json.load(f)

    # Flatten for CSV
    rows = []
    for day in history:
        # Overall S&P 500 row
        row = {'date': day['date'], 'sector': 'S&P 500'}
        row.update(day['sp500'])
        rows.append(row)
        # Per-sector rows
        for sector, metrics in day['sectors'].items():
            row = {'date': day['date'], 'sector': sector}
            row.update(metrics)
            rows.append(row)

    fieldnames = ['date', 'sector', 'total_stocks', 'advancing', 'declining', 'unchanged',
                  'ad_ratio', 'above_50dma', 'pct_above_50dma', 'above_200dma',
                  'pct_above_200dma', 'new_52wk_highs', 'new_52wk_lows']

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[{LOG_PREFIX}] Exported {len(rows)} rows to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Market Breadth Collector — S&P 500 and GICS sector breadth indicators',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Collect today's breadth:     python3 market_breadth_collector.py
  Show current status:         python3 market_breadth_collector.py --status
  Briefing for reports:        python3 market_breadth_collector.py --briefing
  Export to CSV:               python3 market_breadth_collector.py --csv
  Update constituent list:     python3 market_breadth_collector.py --update-constituents
        """
    )
    parser.add_argument('--status', action='store_true', help='Show current breadth status')
    parser.add_argument('--briefing', action='store_true', help='Output markdown briefing')
    parser.add_argument('--csv', nargs='?', const='', default=None, help='Export to CSV')
    parser.add_argument('--update-constituents', action='store_true', help='Force update S&P 500 list')

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.briefing:
        show_briefing()
    elif args.csv is not None:
        export_csv(args.csv if args.csv else None)
    elif args.update_constituents:
        update_constituents()
    else:
        collect_breadth()


if __name__ == '__main__':
    main()
