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
from datetime import date, datetime, timedelta

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
    entry_label,
    entry_timing_score,
    evaluate_nine_rules,
    extension_flag,
    nine_rules_signal,
    rank_sectors,
    relative_strength,
    setup_quality_score,
)
import market_cache  # noqa: E402

# Configuration
DATA_DIR = os.environ.get(
    'MARKET_BREADTH_DIR',
    os.environ.get('GSR_DATA_DIR', os.path.dirname(os.path.abspath(__file__))),
)
BREADTH_FILE = os.path.join(DATA_DIR, 'market_breadth_latest.json')
CONSTITUENTS_FILE = os.path.join(DATA_DIR, 'sp500_constituents.csv')
OUTPUT_FILE = os.path.join(DATA_DIR, 'stock_screener_results.json')
HISTORY_FILE = os.path.join(DATA_DIR, 'stock_screener_history.json')

# Liquidity floor (20-day avg dollar volume)
MIN_DOLLAR_VOLUME = float(os.environ.get('SCREENER_MIN_DOLLAR_VOL', 20_000_000))
# How many sector names to pre-rank before deep analysis (buffer for fails)
PRESCREEN_MULTIPLIER = 3
# Runs to retain in the history file (~1 trading year)
HISTORY_MAX_RUNS = 260      # trading days of history, not individual runs
INTRADAY_MAX_PER_DAY = 12   # hourly runs per day, with headroom
# Warn when a name reports earnings within this many sessions
EARNINGS_WARN_DAYS = 7

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
    Deprecated: superseded by ta_indicators.entry_label(), which reads the setup
    and entry axes separately instead of collapsing them into one score.
    Kept as a thin shim so any external caller keeps working.
    """
    setup = indicators.get('setup_score')
    timing = indicators.get('entry_score')
    if setup is None or timing is None:
        setup = setup_quality_score(indicators, None, sector_type)
        timing = entry_timing_score(indicators, sector_type)
    return entry_label(setup, timing, sector_type)


def score_stock(indicators, sector_ad_ratio=None, sector_type='top'):
    """
    Legacy single composite, retained so older consumers keep working.

    Prefer setup_score / entry_score. This blend is intentionally weighted toward
    setup quality (70/30) because it is what the watchlist ranks on, but it will
    still compress genuinely different situations into one number - which is the
    whole reason the two axes exist.
    """
    setup = setup_quality_score(indicators, sector_ad_ratio, sector_type)
    timing = entry_timing_score(indicators, sector_type)
    return int(round((0.7 * setup) + (0.3 * timing)))


# ---------------------------------------------------------------------------
# Earnings calendar cross-reference
# ---------------------------------------------------------------------------

def fetch_earnings_map(sessions_ahead=10, verbose=True):
    """
    {ticker: {'report_date','timing','days_away'}} for the next N sessions.

    Reuses the Nasdaq calendar client in earnings_expected_move rather than
    re-implementing it. Returns {} on any failure - an unreachable calendar must
    degrade to "no earnings info", never block the screen.
    """
    try:
        from earnings_expected_move import (
            fetch_earnings_calendar,
            upcoming_sessions,
        )
    except ImportError as e:
        if verbose:
            print(f"[{LOG_PREFIX}] Earnings cross-ref unavailable ({e}); skipping.")
        return {}

    try:
        sessions = upcoming_sessions(sessions_ahead)
        entries = fetch_earnings_calendar(sessions, verbose=False)
    except Exception as e:
        if verbose:
            print(f"[{LOG_PREFIX}] Earnings calendar fetch failed ({e}); continuing.")
        return {}

    today = date.today()
    out = {}
    for entry in entries:
        try:
            rd = datetime.strptime(entry['report_date'], '%Y-%m-%d').date()
        except (ValueError, KeyError):
            continue
        out[entry['ticker']] = {
            'report_date': entry['report_date'],
            'timing': entry.get('timing', 'unknown'),
            'days_away': (rd - today).days,
        }
    if verbose:
        print(
            f"[{LOG_PREFIX}] Earnings calendar: {len(out)} reporters "
            f"across next {sessions_ahead} sessions"
        )
    return out


def apply_earnings(indicators, earnings_map):
    """Tag a stock with its upcoming earnings event, if any."""
    info = earnings_map.get(indicators['ticker'])
    if not info:
        indicators['earnings_date'] = None
        indicators['earnings_days_away'] = None
        indicators['earnings_timing'] = None
        indicators['earnings_warning'] = False
        return
    indicators['earnings_date'] = info['report_date']
    indicators['earnings_days_away'] = info['days_away']
    indicators['earnings_timing'] = info['timing']
    indicators['earnings_warning'] = info['days_away'] <= EARNINGS_WARN_DAYS


# ---------------------------------------------------------------------------
# Run history / days-on-list
# ---------------------------------------------------------------------------

def load_history():
    """Prior runs, oldest first. Missing or corrupt file yields []."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
    except (ValueError, OSError):
        print(f"[{LOG_PREFIX}] WARNING: {HISTORY_FILE} unreadable; starting fresh.")
        return []
    return data if isinstance(data, list) else []


def compute_tenure(all_results, history, current_date):
    """
    Annotate each stock with days_on_list / first_seen / is_new.

    Whether a name is new to the screen today or has been sitting on it for three
    weeks is one of the strongest "look at this now" signals available, and it was
    being discarded on every run because the results file is overwritten.

    days_on_list counts distinct prior run dates in the current unbroken streak,
    so a name that drops off and returns reads as new again.
    """
    # Ordered distinct run dates, most recent first, excluding today's.
    past_runs = []
    for run in reversed(history):
        rd = run.get('date')
        if rd and rd != current_date and rd not in past_runs:
            past_runs.append(rd)

    # ticker -> set of dates it appeared on
    appearances = {}
    for run in history:
        rd = run.get('date')
        if not rd or rd == current_date:
            continue
        for tk in run.get('tickers', []):
            appearances.setdefault(tk, set()).add(rd)

    for info in all_results.values():
        for s in info['stocks']:
            seen = appearances.get(s['ticker'], set())
            streak = 0
            for rd in past_runs:
                if rd in seen:
                    streak += 1
                else:
                    break
            s['days_on_list'] = streak + 1
            s['is_new'] = streak == 0
            s['first_seen'] = min(seen) if seen else current_date


def append_history(output):
    """Append a compact record of this run and trim to HISTORY_MAX_RUNS."""
    history = load_history()
    tickers = []
    detail = {}
    for sector, info in output['sectors'].items():
        for s in info['stocks']:
            tickers.append(s['ticker'])
            detail[s['ticker']] = {
                'sector': sector,
                'sector_type': info['type'],
                'setup': s.get('setup_score'),
                'entry': s.get('entry_score'),
                'label': s.get('entry_label'),
            }

    # One record per calendar date, always holding the most recent run of that
    # date. The screener runs hourly, so without this collapse an eight-run day
    # would count as eight days of tenure. runs_today preserves the fact that
    # earlier runs happened, and intraday_history keeps the within-day series.
    prior_same_date = [r for r in history if r.get('date') == output['date']]
    runs_today = (prior_same_date[-1].get('runs_today', 1) + 1) if prior_same_date else 1
    intraday = list(prior_same_date[-1].get('intraday', [])) if prior_same_date else []
    intraday.append({
        'generated': output['generated'],
        'bar_is_partial': output.get('bar_is_partial'),
        'session_fraction': output.get('session_fraction'),
        'market_breadth_pct': output.get('market_breadth_pct'),
        'ticker_count': len(tickers),
    })
    intraday = intraday[-INTRADAY_MAX_PER_DAY:]

    history = [r for r in history if r.get('date') != output['date']]
    history.append({
        'date': output['date'],
        'generated': output['generated'],
        'market_breadth_pct': output.get('market_breadth_pct'),
        'runs_today': runs_today,
        'bar_is_partial': output.get('bar_is_partial'),
        'session_fraction': output.get('session_fraction'),
        'intraday': intraday,
        'tickers': tickers,
        'detail': detail,
    })
    history.sort(key=lambda r: r.get('date', ''))
    history = history[-HISTORY_MAX_RUNS:]

    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=1)
    print(
        f"[{LOG_PREFIX}] History updated: {len(history)} trading days retained "
        f"({runs_today} run(s) today) in {HISTORY_FILE}"
    )


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
                hist = market_cache.history(t, period='1y', auto_adjust=True)
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
    earnings_map=None,
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
            hist = market_cache.history(ticker, period='1y', auto_adjust=True)
        except Exception:
            hist = None
        indicators = calculate_from_ohlcv(hist, spy_close=spy_close, min_bars=200)
        if not indicators:
            continue

        indicators['ticker'] = ticker
        indicators['sector'] = sector_name
        indicators['sector_type'] = sector_type

        # Two axes, kept separate: structural quality vs quality of entry today.
        setup = setup_quality_score(indicators, sector_ad_ratio, sector_type)
        timing = entry_timing_score(indicators, sector_type)
        indicators['setup_score'] = round(setup, 1)
        indicators['entry_score'] = round(timing, 1)
        indicators['entry_label'] = entry_label(setup, timing, sector_type)
        indicators['extension_flag'] = extension_flag(indicators)
        # Legacy blended score for older consumers.
        indicators['score'] = int(round((0.7 * setup) + (0.3 * timing)))

        rules = evaluate_nine_rules(
            indicators,
            market_breadth_pct=market_breadth_pct,
            sector_breadth_pct=sector_breadth_pct,
            liquidity_floor=MIN_DOLLAR_VOLUME,
        )
        indicators['rules_passed'] = rules['rules_passed']
        indicators['rules_total'] = rules['total_rules']
        indicators['rules_detail'] = {
            k: v['passed'] for k, v in rules['rules'].items()
        }
        indicators['nine_rules_signal_label'] = nine_rules_signal(rules['rules_passed'])
        indicators['signal'] = indicators['entry_label']
        apply_earnings(indicators, earnings_map or {})

        results.append(indicators)
        if (i + 1) % 5 == 0:
            print(f"[{LOG_PREFIX}]     Processed {i + 1}/{len(candidates)} candidates...")

    # Rank on setup quality; entry timing is a separate decision, not a tiebreak.
    results.sort(key=lambda x: (x['setup_score'], x['entry_score']), reverse=True)
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
    spy_hist = market_cache.history('SPY', period='1y', auto_adjust=True)
    spy_close = spy_hist['Close'] if spy_hist is not None and not spy_hist.empty else None

    # Earnings calendar once, shared across sectors.
    earnings_map = fetch_earnings_map()
    print()

    all_results = {}

    for sector in top_sectors:
        print(f"[{LOG_PREFIX}] === TOP SECTOR: {sector} ===")
        results = analyze_sector(
            sector, sp500, breadth, top_stocks,
            sector_type='top',
            market_breadth_pct=market_breadth_pct,
            spy_close=spy_close,
            earnings_map=earnings_map,
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
            earnings_map=earnings_map,
        )
        all_results[sector] = {
            'type': 'bottom',
            'composite_score': sector_scores.get(sector) if sector_scores else None,
            'stocks': results,
        }
        print(f"[{LOG_PREFIX}]   Completed: {len(results)} stocks analyzed")
        print()

    # Tenure needs the prior runs before this one is appended.
    compute_tenure(all_results, load_history(), breadth['date'])

    # Which bar did the indicators actually come from?
    bar_dates = {
        s.get('bar_date')
        for info in all_results.values() for s in info['stocks']
        if s.get('bar_date')
    }
    partial_dropped = any(
        s.get('partial_bar_dropped')
        for info in all_results.values() for s in info['stocks']
    )
    live_bar = any(
        s.get('bar_is_partial')
        for info in all_results.values() for s in info['stocks']
    )
    session_fracs = [
        s.get('session_fraction') for info in all_results.values()
        for s in info['stocks'] if s.get('session_fraction') is not None
    ]
    session_frac = max(session_fracs) if session_fracs else 1.0

    output = {
        'date': breadth['date'],
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market_breadth_pct': market_breadth_pct,
        'sector_selection': 'composite',
        'min_dollar_volume': MIN_DOLLAR_VOLUME,
        'bar_date': sorted(bar_dates)[-1] if bar_dates else None,
        'partial_bar_dropped': partial_dropped,
        'bar_is_partial': live_bar,
        'session_fraction': round(session_frac, 3),
        'scoring': 'two_axis_setup_entry',
        'earnings_calendar_names': len(earnings_map),
        'sectors': all_results,
    }
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"[{LOG_PREFIX}] Results saved to {OUTPUT_FILE}")
    if partial_dropped:
        print(
            f"[{LOG_PREFIX}] NOTE: still-forming intraday bar dropped; "
            f"indicators reflect the close of {output['bar_date']}."
        )
    elif live_bar:
        print(
            f"[{LOG_PREFIX}] NOTE: intraday snapshot of {output['bar_date']} "
            f"({session_frac * 100:.0f}% of session elapsed); prices are live and "
            f"volume is pro-rated to the elapsed fraction."
        )

    append_history(output)

    return output


def _load_results():
    if not os.path.exists(OUTPUT_FILE):
        print("No screener results found. Run without --briefing first.")
        return None
    with open(OUTPUT_FILE, 'r') as f:
        return json.load(f)


def _asof_line(data, prefix):
    """
    One line describing which bar the numbers came from.

    An intraday run must not be labelled 'as of close' - the whole point of the
    hourly schedule is that it is deliberately not a closing snapshot.
    """
    bar = data.get('bar_date')
    if not bar:
        return None
    if data.get('partial_bar_dropped'):
        return f"**{prefix} as of close:** {bar} (partial intraday bar dropped)"
    if data.get('bar_is_partial'):
        pct = (data.get('session_fraction') or 0) * 100
        return (
            f"**{prefix} as of:** {bar} intraday snapshot, "
            f"{pct:.0f}% of session elapsed (volume pro-rated)"
        )
    return f"**{prefix} as of close:** {bar}"


def _rr_str(s):
    """
    R:R display. None means price is at/near 52-week highs with no measurable
    overhead resistance - shown as 'open' because that is a bullish condition,
    not missing data.
    """
    rr = s.get('rr_ratio')
    if rr is not None:
        return f"{rr:.2f}"
    if s.get('target_basis') == 'open_no_overhead':
        return 'open'
    return 'N/A'


def _flags(s):
    """Compact flag string: extension, divergence, earnings, freshness."""
    flags = []
    ext = s.get('extension_flag')
    if ext:
        flags.append(ext)
    if s.get('bearish_divergence'):
        flags.append('DIV-')
    if s.get('bullish_divergence'):
        flags.append('DIV+')
    if s.get('earnings_warning'):
        d = s.get('earnings_days_away')
        flags.append(f'ER{d:+d}d' if d is not None else 'ER')
    if s.get('is_new'):
        flags.append('NEW')
    return ','.join(flags) if flags else '-'


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
    line = _asof_line(data, 'Indicators')
    if line:
        print(line)
    print()

    for sector, info in data['sectors'].items():
        label = "STRONGEST" if info['type'] == 'top' else "WEAKEST"
        comp = info.get('composite_score')
        comp_str = f" | composite: {comp}" if comp is not None else ""
        print(f"### {label}: {sector}{comp_str}")
        print()
        print(
            f"| {'Ticker':>6} | {'Price':>8} | {'Setup':>5} | {'Entry':>5} | "
            f"{'Rules':>5} | {'RSI':>5} | {'RS/SPY':>7} | {'x50DMA':>7} | "
            f"{'Stop':>8} | {'R:R':>5} | {'Days':>4} | {'Flags':>16} | "
            f"{'Action':>28} |"
        )
        print(
            f"|{'-'*8}|{'-'*10}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*9}|"
            f"{'-'*9}|{'-'*10}|{'-'*7}|{'-'*6}|{'-'*18}|{'-'*30}|"
        )

        for s in info['stocks']:
            rs_spy = f"{s['rs_vs_spy']:+.1f}%" if s.get('rs_vs_spy') is not None else "N/A"
            ext = (
                f"{s['ext_50dma_atr']:+.1f}A"
                if s.get('ext_50dma_atr') is not None else "N/A"
            )
            rr = _rr_str(s)
            rules = f"{s.get('rules_passed', 'N/A')}/{s.get('rules_total', 9)}"
            stop = f"${s['stop_price']:.2f}" if s.get('stop_price') is not None else "N/A"
            print(
                f"| {s['ticker']:>6} | ${s['price']:>7.2f} | "
                f"{s.get('setup_score', 0):>5.0f} | {s.get('entry_score', 0):>5.0f} | "
                f"{rules:>5} | {s['rsi']:>5.1f} | {rs_spy:>7} | {ext:>7} | "
                f"{stop:>8} | {rr:>5} | {s.get('days_on_list', 1):>4} | "
                f"{_flags(s):>16} | {s.get('entry_label', ''):>28} |"
            )
        print()

    print(
        "_Setup = structural quality (trend, RS, liquidity). "
        "Entry = timing quality (extension, RSI, Bollinger). "
        "A high Setup with a low Entry is a good stock at a bad price._"
    )
    print()
    print(
        "_x50DMA is extension above the 50-DMA in ATR units: +1.0A is one "
        "average day's range above the mean, +4.0A is stretched. "
        "Stop is 2-ATR (or just under a nearby swing low); R:R measures to the "
        "52-week high where that is at least 1R away._"
    )
    print()


def _opp_table(rows, max_rows):
    """Shared table renderer for the opportunity buckets."""
    print(
        f"| {'Ticker':>6} | {'Sector':>22} | {'Setup':>5} | {'Entry':>5} | "
        f"{'Rules':>5} | {'RS/SPY':>7} | {'x50DMA':>7} | {'Stop':>8} | "
        f"{'R:R':>5} | {'Days':>4} | {'Flags':>16} |"
    )
    print(
        f"|{'-'*8}|{'-'*24}|{'-'*7}|{'-'*7}|{'-'*7}|{'-'*9}|{'-'*9}|"
        f"{'-'*10}|{'-'*7}|{'-'*6}|{'-'*18}|"
    )
    for s in rows[:max_rows]:
        rs = f"{s['rs_vs_spy']:+.1f}%" if s.get('rs_vs_spy') is not None else "N/A"
        ext = f"{s['ext_50dma_atr']:+.1f}A" if s.get('ext_50dma_atr') is not None else "N/A"
        rr = _rr_str(s)
        stop = f"${s['stop_price']:.2f}" if s.get('stop_price') is not None else "N/A"
        rules = f"{s.get('rules_passed', 0)}/{s.get('rules_total', 9)}"
        print(
            f"| {s['ticker']:>6} | {s['sector']:>22} | "
            f"{s.get('setup_score', 0):>5.0f} | {s.get('entry_score', 0):>5.0f} | "
            f"{rules:>5} | {rs:>7} | {ext:>7} | {stop:>8} | {rr:>5} | "
            f"{s.get('days_on_list', 1):>4} | {_flags(s):>16} |"
        )
    print()


def show_opportunities(min_setup=60, max_rows=10):
    """
    Actionable buckets for the daily log.

    Split by what you would actually DO, not by which sector a name came from:
    buy now, wait for a pullback, or watch. The old version ranked one saturated
    score, so eight names tied at 100 and the genuinely-buyable ones were
    indistinguishable from the ones already extended 25% above their mean.
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
    line = _asof_line(data, 'Data')
    if line:
        print(line)
    print()

    buy_now, wait, watch = [], [], []
    new_today, earnings_soon = [], []

    for sector, info in data['sectors'].items():
        for s in info['stocks']:
            row = {**s, 'sector': sector, 'sector_type': info['type']}
            if s.get('is_new'):
                new_today.append(row)
            if s.get('earnings_warning'):
                earnings_soon.append(row)

            setup = s.get('setup_score', 0)
            timing = s.get('entry_score', 0)
            if setup < min_setup:
                continue
            lbl = s.get('entry_label', '')
            if lbl in ('BUY NOW', 'BUY / SCALE IN', 'RS LEADER - ENTRY OK'):
                buy_now.append(row)
            elif lbl in ('STRONG - WAIT FOR PULLBACK', 'RS LEADER - EXTENDED'):
                wait.append(row)
            elif timing >= 55 or lbl in ('REVERSAL WATCH', 'SPECULATIVE ENTRY'):
                watch.append(row)

    for bucket in (buy_now, wait, watch, new_today, earnings_soon):
        bucket.sort(
            key=lambda x: (x.get('setup_score', 0), x.get('entry_score', 0)),
            reverse=True,
        )

    print("### Actionable now (good setup AND good entry)")
    print()
    if not buy_now:
        print("_Nothing lines up on both axes today. That is a real answer, "
              "not a gap - forcing an entry into extension is how good setups "
              "become bad trades._")
        print()
    else:
        _opp_table(buy_now, max_rows)

    print("### Strong but extended (wait for a pullback)")
    print()
    if not wait:
        print("_None._")
        print()
    else:
        print(
            "_These have the trend and the relative strength. They are simply "
            "too far above the mean to enter here; note the stop distance._"
        )
        print()
        _opp_table(wait, max_rows)

    print("### Building / secondary")
    print()
    if not watch:
        print("_None._")
        print()
    else:
        _opp_table(watch, max_rows)

    if new_today:
        names = ', '.join(
            f"{s['ticker']} (setup {s.get('setup_score', 0):.0f}/"
            f"entry {s.get('entry_score', 0):.0f})"
            for s in new_today[:8]
        )
        print(f"### New to the screen today ({len(new_today)})")
        print()
        print(names)
        print()

    if earnings_soon:
        print(f"### Earnings within {EARNINGS_WARN_DAYS} days ({len(earnings_soon)})")
        print()
        print("_Technicals do not survive an earnings gap. Size accordingly or wait._")
        print()
        for s in earnings_soon[:12]:
            d = s.get('earnings_days_away')
            when = f"{s.get('earnings_date')} ({s.get('earnings_timing', '?')})"
            print(f"- **{s['ticker']}** — {when}, in {d} day{'s' if d != 1 else ''}")
        print()

    print(
        "_Setup ranks the stock; Entry ranks today's price. Read both._"
    )
    print()


def export_watchlist(output_path=None, min_setup=60, top_per_sector=5, top_only_primary=True):
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
        'min_setup_score': min_setup,
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
        qualifying = [
            s for s in info['stocks'] if s.get('setup_score', 0) >= min_setup
        ][:top_per_sector]
        if info['type'] == 'bottom' and top_only_primary:
            # Keep only clearer weak-sector theses
            qualifying = [
                s for s in qualifying
                if s.get('entry_label', '').startswith('RS LEADER')
                or s.get('entry_label') == 'REVERSAL WATCH'
                or s.get('rules_passed', 0) >= 6
            ][:top_per_sector]

        for stock in qualifying:
            watchlist['stocks'].append({
                'ticker': stock['ticker'],
                'sector': sector,
                'sector_type': info['type'],
                'setup_score': stock.get('setup_score'),
                'entry_score': stock.get('entry_score'),
                'entry_label': stock.get('entry_label'),
                'score': stock.get('score'),
                'signal': stock.get('signal'),
                'rules_passed': stock.get('rules_passed', 0),
                'sector_breadth_pct': sector_breadth_pct,
                'rs_vs_spy': stock.get('rs_vs_spy'),
                'ext_50dma_atr': stock.get('ext_50dma_atr'),
                'stop_price': stock.get('stop_price'),
                'risk_pct': stock.get('risk_pct'),
                'rr_ratio': stock.get('rr_ratio'),
                'days_on_list': stock.get('days_on_list'),
                'is_new': stock.get('is_new'),
                'earnings_date': stock.get('earnings_date'),
                'earnings_days_away': stock.get('earnings_days_away'),
                'earnings_warning': stock.get('earnings_warning', False),
            })

    # Sort: top-sector first, then by setup quality
    watchlist['stocks'].sort(
        key=lambda x: (
            0 if x.get('sector_type') == 'top' else 1,
            -(x.get('setup_score') or 0),
        )
    )

    with open(output_path, 'w') as f:
        json.dump(watchlist, f, indent=2)

    print(
        f"[{LOG_PREFIX}] Watchlist exported: {len(watchlist['stocks'])} stocks "
        f"(min setup {min_setup}) to {output_path}"
    )
    warned = 0
    for s in watchlist['stocks']:
        er = ''
        if s.get('earnings_warning'):
            er = f"  ** ER in {s['earnings_days_away']}d ({s['earnings_date']})"
            warned += 1
        new = ' NEW' if s.get('is_new') else ''
        print(
            f"  {s['ticker']:>6} | {s['sector']:24s} | {s.get('sector_type', '?'):6s} | "
            f"setup {s.get('setup_score', 0):>5.1f} | entry {s.get('entry_score', 0):>5.1f} | "
            f"{s.get('rules_passed', 0)}/9 | d{s.get('days_on_list', 1):<3}{new} | "
            f"{s.get('entry_label', '')}{er}"
        )
    if warned:
        print(
            f"[{LOG_PREFIX}] WARNING: {warned} watchlist name(s) report earnings "
            f"within {EARNINGS_WARN_DAYS} days."
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
        'sector', 'sector_type', 'ticker', 'price', 'bar_date',
        'setup_score', 'entry_score', 'entry_label', 'extension_flag',
        'score', 'signal', 'nine_rules_signal_label',
        'rules_passed', 'rules_total', 'trend_score', 'ma_aligned', 'ema_aligned',
        'above_20dma', 'above_50dma', 'above_200dma',
        'sma20', 'sma50', 'sma200', 'rsi', 'macd', 'macd_signal', 'macd_hist',
        'macd_bullish', 'bb_pct', 'bb_position', 'atr_pct', 'atr_vs_own_median',
        'ext_20dma_pct', 'ext_50dma_pct', 'ext_200dma_pct',
        'ext_50dma_atr', 'ext_50dma_pctile',
        'stop_price', 'stop_basis', 'risk_per_share', 'risk_pct',
        'target_price', 'target_basis', 'rr_ratio', 'high_52w',
        'volume_ratio', 'avg_volume_20d', 'daily_volume', 'dollar_volume_20d',
        'rs_vs_spy', 'rs_vs_spy_60', 'bearish_divergence', 'bullish_divergence',
        'days_on_list', 'is_new', 'first_seen',
        'earnings_date', 'earnings_days_away', 'earnings_timing', 'earnings_warning',
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
        help='Show best-opportunities section (buy now / wait / watch)',
    )
    parser.add_argument(
        '--min-setup', type=float, default=60.0,
        help='Minimum setup-quality score for opportunities/watchlist (default 60)',
    )
    parser.add_argument('--csv', nargs='?', const='', default=None, help='Export to CSV')
    parser.add_argument(
        '--watchlist', nargs='?', const='', default=None,
        help='Export watchlist for nine_rules_gate.py',
    )

    parser.add_argument(
        '--no-cache', action='store_true',
        help='Bypass the OHLCV disk cache and re-fetch (see market_cache.py)',
    )

    args = parser.parse_args()

    if args.no_cache:
        market_cache.disable()

    if args.briefing:
        show_briefing()
    elif args.opportunities:
        show_opportunities(min_setup=args.min_setup)
    elif args.csv is not None:
        export_csv(args.csv if args.csv else None)
    elif args.watchlist is not None:
        export_watchlist(
            args.watchlist if args.watchlist else None,
            min_setup=args.min_setup,
        )
    else:
        run_screener(args.sectors, args.top_stocks, args.sector)


if __name__ == '__main__':
    main()
