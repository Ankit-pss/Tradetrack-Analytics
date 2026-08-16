# Database Design

## Overview

TradeTrack Analytics uses a **star schema** SQLite warehouse optimized for analytical queries. The design separates facts (individual trades) from dimensions (traders, assets, strategies), enabling efficient aggregation and dimension slicing.

**Location:** `datasets/tradetrack.db`  
**Size:** ~5 MB  
**Rows:** 10,781 fact records + dimension rows  
**Purpose:** Centralized source of truth for all analytical queries  

---

## Schema Diagram

```
                    ┌─────────────────────┐
                    │   fact_trades       │
                    │  (10,781 rows)      │
                    ├─────────────────────┤
                    │ trade_id (PK)       │
                    │ trader_fk → dim_trader
                    │ asset_fk  → dim_asset
                    │ strategy_fk → dim_strategy
                    │ entry_price, exit_price
                    │ quantity, side (L/S)
                    │ entry_time, exit_time
                    │ gross_profit, fees
                    │ net_profit
                    │ ... 40+ analytical cols
                    └──────┬──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌──────────────────┐  ┌────────────────┐  ┌──────────────────┐
    │ dim_trader       │  │ dim_asset      │  │ dim_strategy     │
    │ (12 rows)        │  │ (6 rows)       │  │ (7 rows)         │
    ├──────────────────┤  ├────────────────┤  ├──────────────────┤
    │ trader_id (PK)   │  │ asset_id (PK)  │  │ strategy_id (PK) │
    │ name             │  │ symbol         │  │ name             │
    │ skill_edge       │  │ class          │  │ style            │
    │ risk_appetite    │  │ volatility     │  │ description      │
    │ drawdown_max     │  │ tick_fee_bps   │  │                  │
    │                  │  │ trades_weekend │  │                  │
    └──────────────────┘  └────────────────┘  └──────────────────┘
```

---

## Fact Table: `fact_trades`

**Purpose:** One row per closed trade (10,781 rows)

```sql
CREATE TABLE fact_trades (
    -- Primary key
    trade_id INTEGER PRIMARY KEY,
    
    -- Foreign keys (star join)
    trader_fk INTEGER NOT NULL,
    asset_fk INTEGER NOT NULL,
    strategy_fk INTEGER NOT NULL,
    
    -- Entry details
    entry_price REAL NOT NULL,
    entry_time DATETIME NOT NULL,
    
    -- Exit details
    exit_price REAL NOT NULL,
    exit_time DATETIME NOT NULL,
    
    -- Trade structure
    quantity INTEGER NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('Long', 'Short')),
    
    -- Risk definition
    stoploss_price REAL NOT NULL,
    target_price REAL NOT NULL,
    
    -- Risk metrics (computed)
    r_multiple REAL NOT NULL,
    rr_actual REAL NOT NULL,
    
    -- P&L (net of fees)
    gross_profit REAL NOT NULL,
    fees REAL NOT NULL,
    net_profit REAL NOT NULL,
    notional REAL NOT NULL,
    fee_bps REAL NOT NULL,
    
    -- Duration
    duration_minutes INTEGER NOT NULL,
    
    -- Context at entry
    account_equity_at_entry REAL NOT NULL,
    max_drawdown_to_date REAL,
    
    -- Context at exit
    account_equity_at_exit REAL NOT NULL,
    max_drawdown_post REAL,
    
    -- Behavioral
    emotional_state TEXT,
    win_streak_at_entry INTEGER,
    loss_streak_at_entry INTEGER,
    
    -- Trade sequence
    trade_num_intraday INTEGER NOT NULL,
    trade_num_trader INTEGER NOT NULL,
    
    -- Flags
    is_winner BOOLEAN NOT NULL,
    is_open BOOLEAN DEFAULT 0,
    
    -- Foreign key constraints
    FOREIGN KEY (trader_fk) REFERENCES dim_trader(trader_id),
    FOREIGN KEY (asset_fk) REFERENCES dim_asset(asset_id),
    FOREIGN KEY (strategy_fk) REFERENCES dim_strategy(strategy_id)
);
```

### Columns Explained

| Column | Type | Purpose | Example |
|---|---|---|---|
| `trade_id` | INTEGER | Unique identifier | 1, 2, 3, ... |
| `trader_fk` | INTEGER | References dim_trader | 5 |
| `asset_fk` | INTEGER | References dim_asset | 1 (BTC) |
| `strategy_fk` | INTEGER | References dim_strategy | 2 (DayTrade) |
| `entry_price` | REAL | Entry price | 42500.50 |
| `exit_price` | REAL | Exit price | 42650.75 |
| `quantity` | INTEGER | Trade size (in units) | 100 |
| `side` | TEXT | Long or Short | 'Long' |
| `stoploss_price` | REAL | Stop level | 42200.00 |
| `target_price` | REAL | Target level | 43000.00 |
| `r_multiple` | REAL | |exit - entry| / |entry - stop| | 2.5 |
| `rr_actual` | REAL | (exit - entry) / (entry - stop) × side | 2.5 (long win) |
| `gross_profit` | REAL | P&L before fees | 150.50 |
| `fees` | REAL | Commission + slippage | 10.50 |
| `net_profit` | REAL | P&L after fees | 140.00 |
| `duration_minutes` | INTEGER | Trade holding time | 425 |
| `emotional_state` | TEXT | Trader state at entry | 'Disciplined', 'FOMO', 'Revenge' |

---

## Dimension Tables

### `dim_trader` (12 rows)

```sql
CREATE TABLE dim_trader (
    trader_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    skill_edge REAL NOT NULL,              -- % advantage per trade
    risk_appetite REAL NOT NULL,           -- sizing multiplier
    blow_up_date DATE,                     -- when account dropped to 15%
    career_trades INTEGER,
    career_net_profit REAL,
    career_win_rate REAL,
    career_sharpe REAL
);
```

**Sample data:**
```
trader_id | name     | skill_edge | risk_appetite
1         | Trader_A | 0.005      | 0.8
2         | Trader_B | 0.003      | 1.2
3         | Trader_C | 0.008      | 1.0 (blew up)
```

### `dim_asset` (6 rows)

```sql
CREATE TABLE dim_asset (
    asset_id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    class TEXT NOT NULL,                   -- Crypto, Forex, Equity
    volatility_annual REAL,
    tick_fee_bps REAL,                     -- Fee per trade
    trades_on_weekends BOOLEAN DEFAULT 0,
    reference_price REAL
);
```

**Sample data:**
```
asset_id | symbol | class    | volatility | tick_fee_bps
1        | BTC    | Crypto   | 0.032      | 7.5
2        | ETH    | Crypto   | 0.038      | 8.5
3        | EURUSD | Forex    | 0.009      | 2.0
```

### `dim_strategy` (7 rows)

```sql
CREATE TABLE dim_strategy (
    strategy_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    style TEXT,                            -- Scalping, DayTrade, Swing
    description TEXT,
    avg_rr REAL,
    avg_holding_hours REAL,
    trades_count INTEGER,
    net_profit REAL,
    win_rate REAL
);
```

**Sample data:**
```
strategy_id | name      | style     | avg_rr | net_profit
1           | Scalping  | Scalping  | 0.8    | -105838
2           | DayTrade  | DayTrade  | 1.5    | 89234
```

---

## Indexes (7 total)

Indexes optimize the 21 analytical queries by fast table lookups and range scans.

```sql
-- Foreign key lookups
CREATE INDEX idx_trader ON fact_trades(trader_fk);
CREATE INDEX idx_asset ON fact_trades(asset_fk);
CREATE INDEX idx_strategy ON fact_trades(strategy_fk);

-- Time-series queries (daily, monthly reports)
CREATE INDEX idx_entry_time ON fact_trades(entry_time);
CREATE INDEX idx_exit_time ON fact_trades(exit_time);

-- Filtering queries
CREATE INDEX idx_net_profit ON fact_trades(net_profit);
CREATE INDEX idx_emotional ON fact_trades(emotional_state);
```

**Index Statistics:**
- Total index size: ~400 KB
- Average query speedup: 10-50× on range queries

---

## Views (3 total)

Views materialize common aggregations for dashboard and reports.

### `view_daily`

```sql
CREATE VIEW view_daily AS
SELECT
    DATE(entry_time) as trade_date,
    trader_fk,
    COUNT(*) as trades_count,
    SUM(net_profit) as daily_pnl,
    SUM(gross_profit) as daily_pnl_gross,
    SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) as winners,
    ROUND(100.0 * SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate
FROM fact_trades
GROUP BY DATE(entry_time), trader_fk
ORDER BY trade_date DESC;
```

### `view_monthly`

```sql
CREATE VIEW view_monthly AS
SELECT
    STRFTIME('%Y-%m', entry_time) as month,
    trader_fk,
    COUNT(*) as trades_count,
    SUM(net_profit) as monthly_pnl,
    SUM(gross_profit) as monthly_pnl_gross,
    SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) as winners
FROM fact_trades
GROUP BY STRFTIME('%Y-%m', entry_time), trader_fk
ORDER BY month DESC;
```

### `view_trader_summary`

```sql
CREATE VIEW view_trader_summary AS
SELECT
    t.trader_id,
    t.name,
    COUNT(f.trade_id) as total_trades,
    SUM(f.net_profit) as total_net_profit,
    ROUND(100.0 * SUM(CASE WHEN f.net_profit > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate,
    ROUND(AVG(f.r_multiple), 2) as avg_rr,
    MIN(f.account_equity_at_exit) as min_equity,
    MAX(f.account_equity_at_entry) as max_equity
FROM dim_trader t
LEFT JOIN fact_trades f ON t.trader_id = f.trader_fk
GROUP BY t.trader_id, t.name;
```

---

## Key SQL Queries

### Query 1: Performance by Strategy

```sql
SELECT
    s.name,
    COUNT(f.trade_id) as trades,
    SUM(f.net_profit) as net_pnl,
    ROUND(100.0 * SUM(CASE WHEN f.net_profit > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
    ROUND(AVG(f.r_multiple), 2) as avg_rr,
    ROUND(SUM(f.fees), 0) as total_fees
FROM dim_strategy s
JOIN fact_trades f ON s.strategy_id = f.strategy_fk
GROUP BY s.strategy_id, s.name
ORDER BY net_pnl DESC;
```

### Query 2: Max Drawdown per Trader (Window Function)

```sql
WITH daily_equity AS (
    SELECT
        trader_fk,
        DATE(entry_time) as trade_date,
        SUM(net_profit) as daily_pnl,
        SUM(account_equity_at_exit) OVER (
            PARTITION BY trader_fk 
            ORDER BY DATE(entry_time)
        ) as cumulative_equity
    FROM fact_trades
    GROUP BY trader_fk, DATE(entry_time)
)
SELECT
    trader_fk,
    MAX(cumulative_equity) as peak_equity,
    MIN(cumulative_equity) as trough_equity,
    ROUND(100.0 * (MIN(cumulative_equity) - MAX(cumulative_equity)) / MAX(cumulative_equity), 2) as max_drawdown_pct
FROM daily_equity
GROUP BY trader_fk;
```

### Query 3: Win/Loss Streaks (Gaps-and-Islands)

```sql
WITH streak_markers AS (
    SELECT
        trader_fk,
        trade_id,
        net_profit,
        ROW_NUMBER() OVER (PARTITION BY trader_fk ORDER BY entry_time) - 
        ROW_NUMBER() OVER (PARTITION BY trader_fk, SIGN(net_profit) ORDER BY entry_time) as streak_id
    FROM fact_trades
)
SELECT
    trader_fk,
    streak_id,
    SIGN((SELECT net_profit FROM fact_trades LIMIT 1)) as direction,
    COUNT(*) as streak_length,
    SUM(net_profit) as streak_pnl,
    MAX(entry_time) as streak_end_date
FROM streak_markers
GROUP BY trader_fk, streak_id
HAVING COUNT(*) >= 3
ORDER BY streak_length DESC;
```

### Query 4: Hour-of-Day Performance

```sql
SELECT
    CAST(STRFTIME('%H', entry_time) AS INTEGER) as hour_utc,
    COUNT(*) as trades,
    ROUND(100.0 * SUM(CASE WHEN net_profit > 0 THEN 1 ELSE 0 END) / COUNT(*), 1) as win_rate,
    ROUND(AVG(r_multiple), 2) as avg_rr,
    SUM(net_profit) as pnl,
    ROUND(AVG(net_profit), 2) as avg_trade
FROM fact_trades
GROUP BY CAST(STRFTIME('%H', entry_time) AS INTEGER)
ORDER BY hour_utc;
```

### Query 5: Disposition Effect (Hold Time by Win/Loss)

```sql
SELECT
    CASE WHEN net_profit > 0 THEN 'Winner' ELSE 'Loser' END as outcome,
    COUNT(*) as trades,
    ROUND(AVG(duration_minutes), 0) as avg_hold_minutes,
    ROUND(MIN(duration_minutes), 0) as min_hold,
    ROUND(MAX(duration_minutes), 0) as max_hold,
    ROUND(STDDEV(duration_minutes), 0) as stddev_hold
FROM fact_trades
GROUP BY CASE WHEN net_profit > 0 THEN 'Winner' ELSE 'Loser' END;
```

---

## Reconciliation Checks

During `load_to_sql.py`, the pipeline validates data integrity:

```python
# Row count reconciliation
source_count = len(trades_clean)
warehouse_count = SELECT COUNT(*) FROM fact_trades
assert source_count == warehouse_count, f"Row mismatch: {source_count} vs {warehouse_count}"

# P&L reconciliation
source_pnl = trades_clean['net_profit'].sum()
warehouse_pnl = SELECT SUM(net_profit) FROM fact_trades
assert abs(source_pnl - warehouse_pnl) < 0.01, f"P&L mismatch: {source_pnl} vs {warehouse_pnl}"

# Sanity checks
min_pnl = SELECT MIN(net_profit) FROM fact_trades
max_pnl = SELECT MAX(net_profit) FROM fact_trades
assert min_pnl < 0 and max_pnl > 0, "P&L distribution looks wrong"
```

**Benefit:** If any reconciliation fails, the build aborts immediately.

---

## Why SQLite?

### Pros
- **Lightweight** — single file, no server setup
- **Portable** — works on any machine without installation
- **Fast enough** — indexes handle 10K rows at <100ms per query
- **Standard** — SQL is universal
- **Auditable** — queries are readable and reproducible

### Cons
- **Not distributed** — no horizontal scaling (not needed here)
- **No concurrent writes** — fine for analytical use (read-heavy)
- **Limited to local disk** — file size limited by disk space

### When to Upgrade

```
If you needed:
- 100M+ rows → migrate to PostgreSQL or Snowflake
- Concurrent writers → PostgreSQL with proper locking
- Real-time dashboards → add a serving layer (FastAPI)
- dbt integration → Postgres + dbt (next-level data engineering)
```

---

## SQL Best Practices in This Project

### 1. Always Use Explicit Joins
```sql
-- ✓ Good: explicit star join
SELECT f.*, t.name, a.symbol, s.name
FROM fact_trades f
JOIN dim_trader t ON f.trader_fk = t.trader_id
JOIN dim_asset a ON f.asset_fk = a.asset_id
JOIN dim_strategy s ON f.strategy_fk = s.strategy_id;

-- ✗ Bad: implicit join (harder to read, may miss dependencies)
SELECT * FROM fact_trades, dim_trader WHERE trader_fk = trader_id;
```

### 2. Window Functions for Running Totals
```sql
-- ✓ Window function (efficient, one pass)
SELECT
    trade_id,
    net_profit,
    SUM(net_profit) OVER (ORDER BY entry_time) as cumulative_pnl
FROM fact_trades;

-- ✗ Subquery (less efficient, multiple scans)
SELECT f1.trade_id, f1.net_profit,
    (SELECT SUM(f2.net_profit) FROM fact_trades f2 
     WHERE f2.entry_time <= f1.entry_time) as cumulative_pnl
FROM fact_trades f1;
```

### 3. CTEs for Readability
```sql
-- ✓ Readable CTE
WITH daily_performance AS (
    SELECT DATE(entry_time) as day, SUM(net_profit) as pnl
    FROM fact_trades
    GROUP BY DATE(entry_time)
)
SELECT day, pnl, 
       AVG(pnl) OVER (ORDER BY day ROWS BETWEEN 7 PRECEDING AND CURRENT ROW) as ma_7d
FROM daily_performance;
```

---

## Schema Validation

```bash
# Verify schema loaded correctly
sqlite3 datasets/tradetrack.db ".schema fact_trades"

# Check row counts
sqlite3 datasets/tradetrack.db "SELECT COUNT(*) FROM fact_trades"

# Verify indexes exist
sqlite3 datasets/tradetrack.db ".indices"

# Check for orphan foreign keys
sqlite3 datasets/tradetrack.db "PRAGMA foreign_key_check"
```

---

## Next Steps

- **[machine_learning.md](machine_learning.md)** — Model development and evaluation
- **[dashboard.md](dashboard.md)** — UI design and interactivity
- **[analytics_pipeline.md](analytics_pipeline.md)** — Pipeline stages explained
