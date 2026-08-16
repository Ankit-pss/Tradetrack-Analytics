# Datasets

## Data Storage Structure

```
datasets/
├── raw/
│   └── trades_raw.csv            11,130 rows (with intentional defects)
│
├── processed/
│   ├── trades_clean.csv          10,781 rows × 77 features
│   ├── daily_performance.csv     Daily P&L by trader
│   ├── monthly_performance.csv   Monthly P&L by trader
│   ├── trader_summary.csv        Trader summary statistics
│   ├── dim_calendar.csv          Date dimension
│   └── open_trades.csv           Quarantined open trades (not deleted)
│
└── tradetrack.db                 SQLite star-schema warehouse (5 MB)
```

## Raw Data (trades_raw.csv)

**Source:** Simulated trading blotter with realistic defects

**Columns:**
- trade_id, entry_time, exit_time
- entry_price, exit_price, quantity, side
- stoploss, target, strategy, asset, trader
- emotional_state, ...

**Row count:** 11,130 (349 defects to be cleaned)

**Defects (intentional):**
- 180 exact duplicate rows
- 156 numbers formatted as "1,250.75"
- 460 casing/whitespace variants
- 45 impossible durations (≤ 0)
- 29 corrupted prices
- 140 open trades (no exit)
- 258 missing emotional states

## Processed Data (trades_clean.csv)

**After cleaning:** 10,781 rows × 77 columns

**New columns (feature engineering):**
- Risk metrics: r_multiple, rr_actual, stop_distance, target_range
- P&L metrics: notional, fees, fee_bps, gross_profit, net_profit
- Equity curves per trader
- Streaks (win/loss/neutral)
- Sequences (trade number intraday, per trader)
- Time features (hour, day of week, month)
- Behavioral flags (revenge factor, sizing anomaly)
- Market context (correlation, volume profile)

## Data Quality Report

See `reports/data_quality_report.md` for detailed cleaning log:

- What defects were found
- How each was handled
- Counts and percentages
- Validation that no data was silently lost

## Warehouse Database (tradetrack.db)

SQLite star schema:
- `fact_trades` (10,781 rows)
- `dim_trader` (12 rows)
- `dim_asset` (6 rows)
- `dim_strategy` (7 rows)

Loaded by `load_to_sql.py` with reconciliation checks.

## Accessing the Data

```python
# Load clean trades
import pandas as pd
trades = pd.read_csv('datasets/processed/trades_clean.csv')

# Query warehouse
import sqlite3
conn = sqlite3.connect('datasets/tradetrack.db')
cursor = conn.cursor()
cursor.execute('SELECT * FROM fact_trades WHERE side = "Long"')
```

---

**Documentation:** See [../docs/analytics_pipeline.md](../docs/analytics_pipeline.md#data-sources)
