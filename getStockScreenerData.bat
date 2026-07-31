@echo off
setlocal

:: Run from the script's own directory so the python calls resolve regardless of the
:: caller's working directory (Task Scheduler, another shell, a different drive).
cd /d "%~dp0"

set "LOG=C:\Users\DT17787\OneDrive - SS&C Technologies, Inc\Documents\MarketNews\todayStockScreener.log"

echo [%date% %time%] === Stock Screener Data Collection Started === > "%LOG%"

echo [%date% %time%] Running: gsr_data_collector.py >> "%LOG%"
@python gsr_data_collector.py

echo [%date% %time%] Running: market_breadth_collector.py >> "%LOG%"
@python market_breadth_collector.py

echo [%date% %time%] Running: market_ratios_collector.py >> "%LOG%"
@python market_ratios_collector.py

echo [%date% %time%] Running: gsr_data_collector.py --csv >> "%LOG%"
@python gsr_data_collector.py --csv

echo [%date% %time%] Running: update_gsr_chart.py >> "%LOG%"
@python update_gsr_chart.py

echo [%date% %time%] Running: stock_screener.py --sectors 3 >> "%LOG%"
@python stock_screener.py --sectors 3 >> "%LOG%"

echo [%date% %time%] Running: stock_screener.py --watchlist >> "%LOG%"
@python stock_screener.py --watchlist >> "%LOG%"

echo. >> "%LOG%"
echo # Daily Market Brief >> "%LOG%"
echo. >> "%LOG%"

echo [%date% %time%] Running: market_ratios_collector.py --status >> "%LOG%"
@python market_ratios_collector.py --status >> "%LOG%"

echo [%date% %time%] Running: gsr_data_collector.py --status >> "%LOG%"
@python gsr_data_collector.py --status >> "%LOG%"

echo [%date% %time%] Running: market_breadth_collector.py --briefing >> "%LOG%"
@python market_breadth_collector.py --briefing >> "%LOG%"

echo [%date% %time%] Running: stock_screener.py --opportunities >> "%LOG%"
@python stock_screener.py --opportunities >> "%LOG%"

echo [%date% %time%] Running: stock_screener.py --briefing >> "%LOG%"
@python stock_screener.py --briefing >> "%LOG%"

echo [%date% %time%] Running: nine_rules_gate.py --briefing >> "%LOG%"
@python nine_rules_gate.py --briefing >> "%LOG%"

echo [%date% %time%] Running: nine_rules_independent.py --union-watchlist --briefing --no-expected-move --no-save >> "%LOG%"
@python nine_rules_independent.py --union-watchlist --briefing --no-expected-move --no-save >> "%LOG%"

echo [%date% %time%] Running: earnings_expected_move.py --briefing >> "%LOG%"
@python earnings_expected_move.py --briefing >> "%LOG%"

echo [%date% %time%] === Stock Screener Data Collection Complete === >> "%LOG%"
