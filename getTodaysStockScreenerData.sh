#!/bin/bash
# Run through all of the daily stock screener programs
# Program: ~/myPrograms/KSI/MarketBreadth/getTodaysStockScreenerData.sh
# OUTPUT:  ~/myPrograms/KSI/MarketBreadth/logs/todaysMarketBreadth.log
#          ~/myPrograms/KSI/MarketBreadth/logs/nine_rules_independent.log  (nine_rules_independent)
# LOG:     ~/myPrograms/KSI/MarketBreadth/logs/errors.log
# CRON:    30 15,7,8 * * 1-5 ~/myPrograms/KSI/MarketBreadth/getTodaysStockScreenerData.sh > ~/myPrograms/KSI/MarketBreadth/logs/errors.log 2>&1
# Prefer post-close (~16:30-17:45 CT) for clean Yahoo prints; morning runs re-report prior close.

set -uo pipefail
# Note: set -e intentionally NOT used - soft-fail per step so one collector
# cannot abort breadth/screener/opportunities reporting.

cd ~/myPrograms/KSI/

# shellcheck disable=SC1091
source GoldenRatios/.venv/bin/activate

VENV_PYTHON="GoldenRatios/.venv/bin/python3"
LOG_FILE=~/myPrograms/KSI/MarketBreadth/logs/todaysMarketBreadth.log
ERR_FILE=~/myPrograms/KSI/MarketBreadth/logs/errors.log

# Track soft failures for end-of-run summary
FAILURES=0
FAIL_LIST=()

run_step() {
  local label="$1"
  shift
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  echo "[$ts] START: $label" >> "$ERR_FILE"
  if "$@"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed: $label" >> "$LOG_FILE"
    return 0
  else
    local rc=$?
    FAILURES=$((FAILURES + 1))
    FAIL_LIST+=("$label (exit $rc)")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAILED: $label (exit $rc)" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAILED: $label (exit $rc)" >> "$ERR_FILE"
    return 0  # soft-fail: continue pipeline
  fi
}

# Append command stdout/stderr to LOG_FILE
run_report() {
  local label="$1"
  shift
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  {
    echo ""
    echo "<!-- $label @ $ts -->"
    if "$@"; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed: $label"
    else
      local rc=$?
      FAILURES=$((FAILURES + 1))
      FAIL_LIST+=("$label (exit $rc)")
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAILED: $label (exit $rc)"
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAILED: $label (exit $rc)" >> "$ERR_FILE"
    fi
  } >> "$LOG_FILE" 2>> "$ERR_FILE"
}

# Start marker (overwrites log for fresh daily run)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === MarketBreadth daily run START ===" > "$LOG_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === MarketBreadth daily run START ===" >> "$ERR_FILE"

# --- Data collection (progress in errors.log; markers in daily log) ---

run_step "gsr_data_collector.py" \
  $VENV_PYTHON GoldenRatios/gsr_data_collector.py

run_step "market_breadth_collector.py" \
  $VENV_PYTHON MarketBreadth/market_breadth_collector.py

run_step "market_ratios_collector.py" \
  $VENV_PYTHON GoldenRatios/market_ratios_collector.py

run_step "gsr_data_collector.py --csv" \
  $VENV_PYTHON GoldenRatios/gsr_data_collector.py --csv

run_step "update_gsr_chart.py" \
  $VENV_PYTHON GoldenRatios/update_gsr_chart.py

# Screener deep analysis (needed before watchlist / briefing / opportunities)
run_step "stock_screener.py --sectors 3" \
  $VENV_PYTHON MarketBreadth/stock_screener.py --sectors 3

run_step "stock_screener.py --watchlist" \
  $VENV_PYTHON MarketBreadth/stock_screener.py --watchlist

# --- Daily report (single human-readable log) ---

{
  echo ""
  echo "# Daily Market Brief"
  echo ""
} >> "$LOG_FILE"

run_report "market_ratios --status" \
  $VENV_PYTHON GoldenRatios/market_ratios_collector.py --status

run_report "gsr --status" \
  $VENV_PYTHON GoldenRatios/gsr_data_collector.py --status

run_report "market_breadth --briefing" \
  $VENV_PYTHON MarketBreadth/market_breadth_collector.py --briefing

# Best opportunities first (primary quick-view), then full screener tables
run_report "stock_screener --opportunities" \
  $VENV_PYTHON MarketBreadth/stock_screener.py --opportunities

run_report "stock_screener --briefing" \
  $VENV_PYTHON MarketBreadth/stock_screener.py --briefing

run_report "nine_rules_gate" \
  $VENV_PYTHON MarketBreadth/nine_rules_gate.py --briefing

# Independent nine-rules scan: re-scores core book + screener watchlist (no second cron).
# EM skipped here - MarketBreadth/nine_rules_gate.py already reports ATM IV on funnel names.
# Full independent report -> logs/nine_rules_independent.log (overwritten each run).
# A short pointer is left in the main MarketBreadth daily log.
NR_INDEP_LOG=~/myPrograms/KSI/MarketBreadth/logs/nine_rules_independent.log
mkdir -p "$(dirname "$NR_INDEP_LOG")"
{
  echo ""
  echo "<!-- nine_rules_independent (core+screener re-score) @ $(date '+%Y-%m-%d %H:%M:%S') -->"
  if $VENV_PYTHON MarketBreadth/nine_rules_independent.py \
      --union-watchlist --briefing --no-expected-move --no-save \
      > "$NR_INDEP_LOG" 2>> "$ERR_FILE"
  then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Completed: nine_rules_independent -> $NR_INDEP_LOG"
  else
    rc=$?
    FAILURES=$((FAILURES + 1))
    FAIL_LIST+=("nine_rules_independent (exit $rc)")
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAILED: nine_rules_independent (exit $rc) - see $NR_INDEP_LOG / $ERR_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FAILED: nine_rules_independent (exit $rc)" >> "$ERR_FILE"
  fi
} >> "$LOG_FILE"

# End marker
{
  echo ""
  if [[ "$FAILURES" -gt 0 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === MarketBreadth daily run COMPLETE with $FAILURES failure(s) ==="
    for f in "${FAIL_LIST[@]}"; do
      echo "  - $f"
    done
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === MarketBreadth daily run COMPLETE ==="
  fi
} >> "$LOG_FILE"

deactivate 2>/dev/null || true

# Non-zero exit if anything failed (cron/monitoring can alert)
exit "$FAILURES"
