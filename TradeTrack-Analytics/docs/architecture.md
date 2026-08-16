# System Architecture

## Overview

TradeTrack Analytics is a **layered data architecture** transforming raw trades into insights through deterministic, validated transformations.

```
┌─────────────────────────────────────────────────────────────────────┐
│ DATA SOURCES                                                        │
├─────────────────────────────────────────────────────────────────────┤
│ • Simulated trade blotter (GBM + behavioral model)                  │
│ • OR: Real trades from TradeTrack Journal app (import_journal.py)   │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │
                      (datasets/raw/trades_raw.csv)
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ DATA CLEANING LAYER                                                 │
├─────────────────────────────────────────────────────────────────────┤
│ • Deduplicate (exact + repeated trade_id)                           │
│ • Type coercion ("1,250.75" → float)                                │
│ • Categorical hygiene (trim, canonical case)                        │
│ • Timestamp assembly (date + time → datetime)                       │
│ • Duration repair (recompute from timestamps)                       │
│ • Outlier detection (robust MAD z-score + structural tests)         │
│ • Missing values (open trades quarantine, fields default)           │
│ • Integrity checks (stop/target side validity, P&L reconciliation)  │
│ • Feature engineering (77 columns: R-multiple, notional, streaks)   │
│ Output: datasets/processed/*.csv                                    │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ DATA WAREHOUSE LAYER (SQLite)                                       │
├─────────────────────────────────────────────────────────────────────┤
│ SCHEMA: Star (fact + dimensions)                                    │
│  ┌─────────────────────────────────────────────────┐                │
│  │ fact_trades          (10,781 rows)              │                │
│  │  • trade_id (PK)                                │                │
│  │  • trader_fk, asset_fk, strategy_fk             │                │
│  │  • entry_price, exit_price, R, net_profit      │                │
│  │  • entry_time, exit_time, duration             │                │
│  │  • 40+ analytical columns                       │                │
│  └─────────────────────────────────────────────────┘                │
│  ┌──────────────────┐ ┌──────────────┐ ┌──────────────┐             │
│  │ dim_trader       │ │ dim_asset    │ │ dim_strategy │             │
│  │ • trader_id      │ │ • asset_id   │ │ • strategy_id│             │
│  │ • name, edge     │ │ • symbol     │ │ • name       │             │
│  │ • risk_appetite  │ │ • class      │ │ • style      │             │
│  └──────────────────┘ └──────────────┘ └──────────────┘             │
│                                                                      │
│ INDEXES: 7 (speed critical queries)                                 │
│ VIEWS: 3 (materialized aggregations)                                │
│ Output: datasets/tradetrack.db (star schema warehouse)              │
└──────────────────────────────────────────┬──────────────────────────┘
                                           │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
        ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
        │ SQL ANALYSIS     │  │ KPI COMPUTATION  │  │ VISUALIZATION    │
        │ (21 queries)     │  │ (kpi_engine.py)  │  │ (charts, images) │
        │                  │  │                  │  │                  │
        │ • Performance    │  │ • Sharpe ratio   │  │ • 16 PNG charts  │
        │ • Risk metrics   │  │ • Drawdown       │  │ • 5 HTML exports │
        │ • Streaks        │  │ • Win rate       │  │ • Theme system   │
        │ • Heatmaps       │  │ • Expectancy     │  │                  │
        │                  │  │ • Profit factor  │  │                  │
        └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘
                 │                     │                     │
                 ├─────────────────────┴─────────────────────┤
                 │                                           │
                 ▼                                           ▼
        ┌─────────────────────┐                ┌──────────────────────┐
        │ REPORTING LAYER     │                │ MACHINE LEARNING     │
        │                     │                │                      │
        │ • reports/          │                │ • ml_model.py        │
        │ • sql_analysis.md   │                │   (classifier)       │
        │ • business_insights │                │ • ml_expected_r.py   │
        │ • kpi_summary.json  │                │   (regression)       │
        │ • data_quality.md   │                │ • model_report.md    │
        │ • ml_model_report   │                │ • model_card         │
        │ • images/           │                │                      │
        └─────────────────────┘                └──────────┬───────────┘
                 │                                         │
                 └─────────────────┬───────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────┐
        │ DASHBOARD DATA LAYER                               │
        │                                                    │
        │ • frontend/dashboard/data.js                       │
        │ • Columnar, dictionary-encoded format (705 KB)    │
        │ • All trade & aggregation data in one file        │
        └─────────────────────────┬────────────────────────┘
                                  │
                                  ▼
        ┌────────────────────────────────────────────────────┐
        │ DASHBOARD APPLICATION                              │
        │                                                    │
        │ frontend/dashboard/index.html                      │
        │  • 6 KPI cards (animated)                          │
        │  • 10 interactive charts                           │
        │  • 5 live filters (date, asset, strategy, etc.)   │
        │  • Glassmorphism design, dark theme                │
        │  • Zero runtime dependencies                       │
        └────────────────────────────────────────────────────┘
```

---

## Architecture Components

### 1. Data Sources

#### Option A: Simulated Blotter
```python
# analytics/scripts/generate_dataset.py
generate_trades(
    num_traders=12,
    num_instruments=6,
    date_range="2024-01-01 to 2026-06-30"
)
→ datasets/raw/trades_raw.csv (11,130 rows, intentionally dirty)
```

**Simulation includes:**
- GBM price paths with volatility clustering
- Win probability anchored to RR break-even rate
- Per-trader behavioral profiles (skill, discipline, risk appetite)
- Psychology feedback loop (losing → FOMO/revenge → larger size)
- Survivorship (account blow-ups stop trading)

#### Option B: Real Trades
```bash
python analytics/scripts/import_journal.py --capital 5000
```
Reads from TradeTrack Journal app database and maps to analytical schema.

---

### 2. Data Cleaning Pipeline

**Input:** `datasets/raw/trades_raw.csv` (11,130 rows)  
**Output:** `datasets/processed/trades_clean.csv` (10,781 rows) + aggregations  
**Module:** `analytics/scripts/data_cleaning.py`

#### Cleaning Stages (in order)

| Stage | Problem | Solution | Count |
|-------|---------|----------|-------|
| Deduplication | Exact duplicate rows + repeated trade_id | Keep first, drop rest | 180 + 156 |
| Type coercion | Strings formatted as "1,250.75" | Regex, strip, cast | 156 |
| Categorical hygiene | Casing/whitespace variants | Map to canonical | 460 |
| Timestamp assembly | Split date + time columns | Combine, parse datetime | — |
| Duration repair | Duration ≤ 0 (impossible) | Recompute from entry/exit | 45 |
| Outlier detection | Corrupted entry prices | Robust MAD z-score + structural test | 29 |
| Missing values | Open trades, null fields | Quarantine, default | 140 + 258 |
| Integrity checks | Stop/target on wrong side, P&L mismatch | Fail loudly | — |

#### Feature Engineering

Starting with 7 raw columns (entry, exit, stop, target, quantity, asset, strategy), add 77 computed features:

| Category | Examples |
|----------|----------|
| **Risk metrics** | r_multiple, target_range, stop_distance, rr_actual |
| **P&L metrics** | notional, fee_ratio, gross_profit, net_profit |
| **Equity curves** | account_equity_at_entry, account_equity_at_exit, max_drawdown |
| **Streaks** | win_streak, loss_streak, streak_counter |
| **Sequences** | trade_num_intraday, trade_num_trader |
| **Time features** | hour_of_entry, day_of_week, is_weekend |
| **Behavioral** | emotional_state, revenge_factor, sizing_factor |

---

### 3. SQL Warehouse Layer

**Location:** `datasets/tradetrack.db`  
**Design:** Star schema (1 fact table + 3 dimensions)  
**Size:** ~5 MB, 10,781 fact rows + dimension rows  

#### Fact Table: `fact_trades`

```sql
CREATE TABLE fact_trades (
    trade_id INTEGER PRIMARY KEY,
    trader_fk INTEGER,
    asset_fk INTEGER,
    strategy_fk INTEGER,
    entry_price REAL,
    exit_price REAL,
    quantity INTEGER,
    entry_time DATETIME,
    exit_time DATETIME,
    duration_minutes INTEGER,
    side TEXT,              -- 'Long' or 'Short'
    
    -- Risk metrics
    r_multiple REAL,
    rr_actual REAL,
    target_range REAL,
    stop_distance REAL,
    
    -- P&L metrics
    gross_profit REAL,
    fees REAL,
    net_profit REAL,
    notional REAL,
    fee_bps REAL,
    
    -- Performance context
    account_equity_at_entry REAL,
    account_equity_at_exit REAL,
    max_drawdown_post REAL,
    
    -- Behavioral
    emotional_state TEXT,
    streak_counter INTEGER,
    
    FOREIGN KEY (trader_fk) REFERENCES dim_trader(trader_id),
    FOREIGN KEY (asset_fk) REFERENCES dim_asset(asset_id),
    FOREIGN KEY (strategy_fk) REFERENCES dim_strategy(strategy_id)
);
```

#### Dimension Tables

```sql
-- dim_trader: Trader profiles (12 rows)
-- dim_asset: Asset universe (6 rows)
-- dim_strategy: Strategy definitions (7 rows)
```

#### Indexes (7 total)

```sql
CREATE INDEX idx_trader ON fact_trades(trader_fk);
CREATE INDEX idx_asset ON fact_trades(asset_fk);
CREATE INDEX idx_strategy ON fact_trades(strategy_fk);
CREATE INDEX idx_entry_time ON fact_trades(entry_time);
CREATE INDEX idx_exit_time ON fact_trades(exit_time);
CREATE INDEX idx_net_profit ON fact_trades(net_profit);
CREATE INDEX idx_emotional ON fact_trades(emotional_state);
```

#### Views (3 total)

```sql
-- view_daily: Daily P&L by trader/asset
-- view_monthly: Monthly P&L by trader
-- view_trader_summary: Career stats per trader
```

---

### 4. SQL Analysis Layer

**Module:** `analytics/scripts/run_sql_analysis.py`  
**SQL Source:** `database/sql/02_analysis_queries.sql`  
**Output:** `reports/sql_analysis_results.md`  

**21 Queries covering:**

| Category | Count | Examples |
|----------|-------|----------|
| **Performance** | 5 | P&L by strategy, by hour, by day |
| **Risk** | 4 | Max drawdown, drawdown duration, VaR |
| **Streaks** | 3 | Win/loss streaks (gaps-and-islands) |
| **Comparisons** | 5 | Expected vs actual win rate, strategy edges |
| **Behavioral** | 4 | Disposition effect, overtrading, revenge |

**Execution model:**
- Parse SQL file into individual queries
- Execute each query on database
- Render results to Markdown with headers and descriptions
- **Fail fast** if any query doesn't parse or returns empty

---

### 5. KPI Computation Layer

**Module:** `analytics/scripts/kpi_engine.py`  
**Input:** `datasets/processed/trades_clean.csv`  
**Output:** `reports/kpi_summary.json` (machine-readable) + terminal output  

#### KPIs Computed

| Metric | Formula | Interpretation |
|--------|---------|-----------------|
| **Win Rate** | wins / total_trades | % of trades closing profitably |
| **Profit Factor** | gross_wins / abs(gross_losses) | Dollars won per dollar lost (gross) |
| **Sharpe Ratio** | mean_return / std_return | Return per unit of volatility |
| **Sortino Ratio** | mean_return / downside_std | Return per unit of downside volatility |
| **Expectancy** | (mean_win × win_rate) − (mean_loss × loss_rate) | Expected R per trade |
| **Max Drawdown** | (peak_equity − trough_equity) / peak_equity | Worst peak-to-trough loss |
| **Profit Factor (net)** | net_wins / abs(net_losses) | Same but after fees |
| **Avg RR** | mean(rr_actual) | Average reward:risk achieved |

---

### 6. Visualization Layer

**Module:** `analytics/scripts/visualizations.py`  
**Input:** `datasets/processed/trades_clean.csv`  
**Output:** `reports/images/*.png` (static) + `frontend/dashboard/charts/*.html` (interactive)  

#### Chart Types

| Chart | Type | Purpose |
|-------|------|---------|
| Equity curve | Line (Matplotlib) | Cumulative P&L trajectory |
| Monthly P&L | Bar (Plotly) | Profitability by month |
| Win/loss distribution | Histogram (Matplotlib) | P&L distribution shape |
| Risk distribution | Histogram (Matplotlib) | R-multiple distribution |
| Asset performance | Bar (Plotly) | P&L by instrument |
| Strategy performance | Grouped bar (Plotly) | Strategy comparison |
| Session analysis | Bar (Plotly) | Hour-of-day contribution |
| Weekday heatmap | Heatmap (Matplotlib) | Win rate by day × hour |
| Correlation matrix | Heatmap (Matplotlib) | Feature relationships |
| Psychology | Grouped bar (Plotly) | Performance by emotional state |
| ML confusion matrix | Heatmap (Matplotlib) | Model classification accuracy |
| ML feature importance | Horizontal bar (Plotly) | Top features driving predictions |

---

### 7. Machine Learning Layer

#### 7a. Classification Model

**Module:** `analytics/scripts/ml_model.py`  
**Input:** `datasets/processed/trades_clean.csv`  
**Output:** `reports/ml_model_report.md` + model artifacts  
**Question:** "Will this trade close profitably using only pre-entry information?"

**Design:**

```
Objective: Binary classification (Win / Loss)

Training split: Chronological (first 70% by date)
Test split: Chronological (last 30% by date)
Leakage control: 31 post-close columns HARD-BANNED (runtime assertion)

Features used: 46 pre-close columns
  • entry_price, stop_distance, target_range
  • account_equity, max_drawdown_to_date
  • win_streak, loss_streak
  • trader skill edge, asset volatility
  • hour_of_entry, day_of_week

Models compared:
  • Random Forest: 60.2% accuracy, 0.618 ROC-AUC
  • Gradient Boosting: 63.5% accuracy, 0.605 ROC-AUC
  • XGBoost (optional): similar performance

Evaluation metrics:
  • Accuracy (not primary — 63.5% baseline from predicting Loss always)
  • ROC-AUC (rank ordering quality)
  • Top-decile win rate (lift on best predictions)
  • Confidence calibration

Honest limitations:
  • Model learns that low-RR trades win more (true, but those trades are worth less)
  • Ranking by P(win) correlates NEGATIVELY with actual R earned
  • Even top decile lift (+0.056R from +0.041R base) is thin
```

#### 7b. Regression Model (Expected R)

**Module:** `analytics/scripts/ml_expected_r.py`  
**Objective:** "What R will this trade earn?" (regression vs classification)

**Head-to-head Comparison:**

| Signal | Spearman ρ vs actual R | Top 25% | Top 50% |
|--------|---|---|---|
| **Expected R (regression)** | +0.067** | +0.112R | +0.116R |
| P(win) (classification) | −0.016 | +0.009R | +0.019R |
| Baseline (take all) | — | +0.041R | +0.041R |

**Finding:** Expected-R ranking beats probability ranking, because the desk cares about money, not win rate.

---

### 8. Reporting Layer

**Outputs:**

```
reports/
├── business_insights.md          20 findings, every number computed
├── data_quality_report.md         Cleaning decisions log
├── sql_analysis_results.md        Output of all 21 queries
├── ml_model_report.md            Model card & evaluation
├── ml_expected_r_report.md       Regression model results
├── kpi_summary.json              Machine-readable KPIs
└── images/                       16 PNG charts + exports
```

---

### 9. Dashboard Application

**Location:** `frontend/dashboard/`  
**Design:** Zero-dependency single-file application  
**Data source:** `data.js` (generated columnar data layer)  

#### Architecture

```
index.html (DOM + event listeners)
   ↓
app.js (filtering & chart rendering logic)
   ↓
data.js (columnar, dictionary-encoded data)
   ↓
styles.css (glassmorphism design system)
```

#### Data Format (data.js)

```javascript
// Columnar layout: minimize string duplication
window.TradeTrackData = {
  metadata: {
    trade_count: 10781,
    period_start: "2024-01-01",
    period_end: "2026-06-30"
  },
  
  // Dictionaries for categorical reduction
  traders: ["Trader1", "Trader2", ...],      // 12 entries
  assets: ["BTC", "ETH", ...],               // 6 entries
  strategies: ["Scalping", "DayTrade", ...], // 7 entries
  
  // Column arrays (one entry per trade)
  trades: {
    ids: [1, 2, 3, ...],                 // 10,781 values
    trader_idx: [0, 2, 1, ...],          // Dictionary index (0-11)
    asset_idx: [0, 1, 0, ...],           // Dictionary index (0-5)
    strategy_idx: [1, 0, 2, ...],        // Dictionary index (0-6)
    entry_price: [42500.5, ...],
    exit_price: [42650.75, ...],
    net_profit: [150.25, ...],
    r_multiple: [1.5, ...],
    entry_timestamp: [1234567890, ...],
    // ... 40+ more columns
  }
};
```

**Size:** 705 KB (dictionary encoding vs 3+ MB row-oriented JSON)

#### Filtering Algorithm

```javascript
// Vectorized filter on 10,781 trades in <100ms
function applyFilters(filters) {
  const mask = [];
  
  for (let i = 0; i < tradeCount; i++) {
    let include = true;
    
    if (filters.dateRange && !inRange(data.entry_timestamp[i], filters.dateRange)) {
      include = false;
    }
    if (filters.assets.length && !filters.assets.includes(data.asset_idx[i])) {
      include = false;
    }
    // ... other dimensions
    
    mask[i] = include;
  }
  
  // Recompute all KPIs and charts using mask
  return computeKPIs(mask);
}
```

---

## Data Flow Diagram

```
┌──────────────────────┐
│  generate_dataset    │
│  (simulator)         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────┐     ┌─────────────────────┐
│  trades_raw.csv                  │     │ import_journal.py   │
│  (11,130 rows, intentional dirt) │◄────│ (real trades)       │
└──────────┬───────────────────────┘     └─────────────────────┘
           │
           │ [CLEANING PIPELINE]
           │
           ▼
┌──────────────────────────────────┐
│  trades_clean.csv                │
│  (10,781 rows, 77 columns)       │
└──────────┬───────────────────────┘
           │
      ┌────┴────────────────────┐
      │                         │
      ▼                         ▼
┌─────────────────┐    ┌───────────────────┐
│  load_to_sql    │    │  KPI computation  │
│                 │    │  ML models        │
▼                 ▼    │  Visualizations   │
tradetrack.db  (all feed into)
                 │
      ┌──────────┼──────────┐
      ▼          ▼          ▼
   Insights  Dashboard  BI Tools
   (MD)      (HTML)    (DAX/PBI)
```

---

## Reproducibility & Quality Assurance

### Determinism

- **Seeded RNG** — every random number controlled by `config.RANDOM_SEED`
- **Sorted outputs** — all aggregations sort by key for consistent ordering
- **Explicit dates** — no relative dates, all timestamps hardcoded

### Validation

```
Pipeline Entry Points:
  ✓ Row count validation (raw → clean → warehouse)
  ✓ P&L reconciliation (source → computed, must agree)
  ✓ Assertion guards (ML leakage check fails build)
  ✓ Query execution (all 21 queries run every build)
  ✓ Cross-checks (notebook reimplements KPI independently)
```

### Testing Strategy

```python
# Reconciliation in load_to_sql.py
source_row_count = 10781
warehouse_row_count = SELECT COUNT(*) FROM fact_trades
assert source_row_count == warehouse_row_count

source_net_pnl = sum(trades_clean.csv.net_profit)
warehouse_net_pnl = SELECT SUM(net_profit) FROM fact_trades
assert source_net_pnl == warehouse_net_pnl (to the cent)
```

---

## Next Steps

- **[analytics_pipeline.md](analytics_pipeline.md)** — Each pipeline stage in detail
- **[database_design.md](database_design.md)** — Schema, indexes, and SQL patterns
- **[machine_learning.md](machine_learning.md)** — Model development and evaluation
- **[dashboard.md](dashboard.md)** — UI design and interactivity
