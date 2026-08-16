# Analytics Pipeline

## Pipeline Stages

The analytics pipeline is a sequence of 10 deterministic stages, each with clear inputs, outputs, and success criteria.

### Stage 1: Data Generation

**Module:** `analytics/scripts/generate_dataset.py`  
**Runtime:** ~5 seconds  
**Output:** `datasets/raw/trades_raw.csv` (11,130 rows)

```python
python analytics/scripts/generate_dataset.py
```

#### What It Does

Simulates a trading blotter with realistic structure and defects:

1. **Generate price paths** — GBM for 6 assets with volatility clustering
2. **Simulate trades** — 12 traders × 7 strategies over 30 months
3. **Inject behavioral features**:
   - Trader skill edge (0.3% - 1.5% per trade)
   - Risk appetite (position sizing profile)
   - Emotional states (disciplined, FOMO, revenge)
4. **Introduce defects** — duplicate rows, formatting issues, outliers
5. **Account for survivorship** — traders who lose 85% cap stop trading

#### Parameters

```python
RANDOM_SEED = 20260731
NUM_TRADERS = 12
NUM_STRATEGIES = 7
NUM_ASSETS = 6
MIN_TRADES = 10_000
START_DATE = "2024-01-01"
END_DATE = "2026-06-30"
```

#### Output Structure

```
trade_id | entry_time | exit_time | entry_price | exit_price | quantity | side |
strategy | asset | trader | stoploss | target | risk | reward | emotional_state |
fees | pnl | ...
```

### Stage 2: Data Cleaning

**Module:** `analytics/scripts/data_cleaning.py`  
**Runtime:** ~8 seconds  
**Input:** `datasets/raw/trades_raw.csv` (11,130 rows)  
**Outputs:**
- `datasets/processed/trades_clean.csv` (10,781 rows, 77 columns)
- `datasets/processed/daily_performance.csv`
- `datasets/processed/monthly_performance.csv`
- `datasets/processed/trader_summary.csv`
- `reports/data_quality_report.md`

```python
python analytics/scripts/data_cleaning.py
```

#### Cleaning Pipeline

```python
1. Deduplicate()
   - Exact match deduplication
   - Repeated trade_id handling
   
2. TypeCoerce()
   - Fix "1,250.75" strings → float
   - Timestamp parsing
   
3. CategoricalHygiene()
   - Trim whitespace
   - Canonical casing
   - Map variants to canonical labels
   
4. TimestampAssembly()
   - Combine date + time columns
   - Normalize timezone
   
5. DurationRepair()
   - Check duration > 0
   - Recompute from entry/exit if invalid
   
6. OutlierDetection()
   - Robust MAD z-score on log-price
   - Structural validation (stop < entry < target for longs)
   
7. MissingValues()
   - Identify open trades
   - Default missing emotional states
   
8. IntegrityChecks()
   - Stop/target on correct side of entry
   - Reconcile P&L: net = gross - fees
   
9. FeatureEngineering()
   - R-multiples, RR actual
   - Equity curves per trader
   - Streaks, sequences
   - Behavioral flags
```

#### Feature Engineering (77 total columns)

| Category | Count | Examples |
|---|---|---|
| Risk metrics | 8 | r_multiple, rr_actual, target_range, stop_distance |
| P&L metrics | 6 | notional, fees, fee_bps, gross_profit, net_profit |
| Equity curves | 5 | equity_at_entry, equity_at_exit, max_drawdown |
| Streaks | 4 | win_streak, loss_streak, streak_counter |
| Sequences | 3 | trade_num_intraday, trade_num_trader |
| Time | 6 | hour_of_entry, day_of_week, month_of_entry |
| Behavioral | 8 | emotional_state, revenge_factor, sizing_factor |
| Trader | 3 | trader_name, trader_skill, trader_risk_appetite |
| Asset | 3 | asset_symbol, asset_class, asset_volatility |
| Strategy | 2 | strategy_name, strategy_type |
| Aggregates | 13 | daily_pnl, monthly_pnl, trades_this_day |

#### Quality Report

Output: `reports/data_quality_report.md`

```markdown
# Data Quality Report

## Summary
- Input rows: 11,130
- Output rows: 10,781
- Dropped rows: 349 (3.1%)

## Defects Handled

### Duplicates (336 rows)
- Exact duplicate rows: 180 rows (0.002%)
  - Detection: MD5 hash on all columns
  - Action: Keep first, drop rest
  - Example: Entry=42500.5, Exit=42650.75 appears twice

- Repeated trade_id: 156 rows (0.014%)
  - Detection: trade_id appears in multiple rows
  - Action: Keep chronologically first, drop rest
  
### Type Coercion (156 rows)
- Numeric fields formatted as strings "1,250.75"
  - Detection: Regex pattern `\d+,\d+`
  - Action: Strip comma, cast to float
  - Impact: 100% successful

### Categorical Mapping (460 rows)
- Whitespace/case variants: "Scalping" vs "scalping " vs "SCALPING"
  - Detection: Value not in canonical domain
  - Action: Map all variants to canonical ("Scalping")
  - Impact: All mapped successfully

### Timestamp Issues (45 rows)
- Duration ≤ 0 (impossible)
  - Detection: exit_time <= entry_time
  - Action: Recompute from entry/exit timestamps
  - Impact: 45 rows fixed, 0 unfixable

### Outliers (29 rows)
- Corrupted entry prices (fat-finger typos)
  - Test 1: Robust MAD z-score on log-price
  - Test 2: Structural (stop < entry < target for longs)
  - Impact: 29 rows flagged, excluded from analysis
  - Saved in: datasets/processed/open_trades.csv

### Missing Values (398 rows)
- Open trades (exit not recorded): 140 rows
  - Action: Quarantine in open_trades.csv
- Missing emotional_state: 258 rows
  - Action: Default to 'Unspecified'

## Summary Statistics
- Rows cleaned: 349 defective rows handled
- Success rate: 96.9% (10,781 / 11,130)
- Mean trade duration: 425 minutes
- Median P&L: -$12.50
- Max profit: +$4,250
- Max loss: -$3,890
```

### Stage 3: Load to SQL Warehouse

**Module:** `analytics/scripts/load_to_sql.py`  
**Runtime:** ~3 seconds  
**Input:** `datasets/processed/trades_clean.csv`  
**Output:** `datasets/tradetrack.db`

```python
python analytics/scripts/load_to_sql.py
```

#### Process

1. **Create schema** — DDL from `database/sql/01_schema.sql`
2. **Load fact table** — insert 10,781 trades
3. **Load dimensions** — traders, assets, strategies
4. **Create indexes** — 7 indexes on common query columns
5. **Create views** — 3 materialized views for aggregations
6. **Reconciliation checks**:
   - Source row count vs warehouse row count
   - Source net P&L vs computed warehouse P&L
   - Fail fast if mismatch

#### Output: SQLite Database

```
datasets/tradetrack.db (5 MB)
├── fact_trades (10,781 rows)
├── dim_trader (12 rows)
├── dim_asset (6 rows)
├── dim_strategy (7 rows)
├── view_daily (daily P&L)
├── view_monthly (monthly P&L)
└── view_trader_summary (trader KPIs)
```

### Stage 4: Run SQL Analysis

**Module:** `analytics/scripts/run_sql_analysis.py`  
**Runtime:** ~2 seconds  
**Input:** `datasets/tradetrack.db`  
**Output:** `reports/sql_analysis_results.md`

```python
python analytics/scripts/run_sql_analysis.py
```

#### Process

1. Parse `database/sql/02_analysis_queries.sql` into 21 queries
2. Execute each query against warehouse
3. Format results as Markdown tables
4. Fail if any query doesn't parse or returns empty

#### Query Categories

| Category | Queries | Examples |
|---|---|---|
| Performance | 5 | P&L by strategy, by asset, by hour |
| Risk | 4 | Max drawdown, VaR, stress tests |
| Streaks | 3 | Win/loss streaks, recovery times |
| Comparisons | 5 | Expected vs actual win rate |
| Behavioral | 4 | Disposition effect, overtrading |

### Stage 5: KPI Engine

**Module:** `analytics/scripts/kpi_engine.py`  
**Runtime:** ~2 seconds  
**Input:** `datasets/processed/trades_clean.csv`  
**Outputs:**
- `reports/kpi_summary.json` (machine-readable)
- Terminal output (human-readable)

```python
python analytics/scripts/kpi_engine.py
```

#### KPIs Computed

```python
kpis = {
    # Returns
    "total_trades": 10781,
    "winning_trades": 3784,
    "losing_trades": 6997,
    "win_rate": 0.3513,
    
    # P&L
    "gross_profit": 487123.50,
    "fees": -266939.75,
    "net_profit": 220183.75,
    
    # Risk-adjusted
    "sharpe_ratio": 0.80,
    "sortino_ratio": 0.95,
    "profit_factor": 1.07,
    "expectancy_r": 0.005,
    
    # Risk
    "max_drawdown": 0.145,
    "max_drawdown_usd": -62492.00,
    "avg_rr": 2.32
}
```

### Stage 6: Visualizations

**Module:** `analytics/scripts/visualizations.py`  
**Runtime:** ~6 seconds  
**Input:** `datasets/processed/trades_clean.csv`  
**Outputs:**
- `reports/images/*.png` (16 static charts)
- `frontend/dashboard/charts/*.html` (interactive exports)

```python
python analytics/scripts/visualizations.py
```

#### Chart Rendering

```python
# Static charts (PNG via Matplotlib)
plot_equity_curve()       → images/01_equity_curve.png
plot_monthly_pnl()        → images/02_monthly_profit.png
plot_win_loss_dist()      → images/03_win_loss_distribution.png
plot_risk_dist()          → images/05_risk_distribution.png
plot_correlation_matrix() → images/10_correlation_matrix.png

# Interactive charts (HTML via Plotly)
plot_asset_performance()  → dashboard/charts/asset_perf.html
plot_strategy_perf()      → dashboard/charts/strategy_perf.html
plot_heatmap()           → dashboard/charts/weekday_heatmap.html
```

### Stage 7: Machine Learning Model

**Module:** `analytics/scripts/ml_model.py`  
**Runtime:** ~4 seconds  
**Input:** `datasets/processed/trades_clean.csv`  
**Output:** `reports/ml_model_report.md`

```python
python analytics/scripts/ml_model.py
```

#### Model Pipeline

```python
1. Feature Selection
   - Pre-close features only (46 columns)
   - Hard-ban 31 post-close columns (assertion)
   
2. Data Split
   - Chronological (70% train, 30% test)
   - Never random (prevents future leakage)
   
3. Model Training
   - Random Forest (500 trees)
   - Gradient Boosting (200 trees)
   - XGBoost (optional, for comparison)
   
4. Evaluation
   - Accuracy: 60.2% (baseline 63.5% from predicting Loss always)
   - ROC-AUC: 0.618
   - Top-decile win rate: 57.2% (vs 36.5% base)
   - Calibration checks
   
5. Model Card
   - What it predicts
   - How well it works
   - When it fails
   - Limitations and caveats
```

### Stage 8: Expected-R Model

**Module:** `analytics/scripts/ml_expected_r.py`  
**Runtime:** ~3 seconds  
**Input:** `datasets/processed/trades_clean.csv`  
**Output:** `reports/ml_expected_r_report.md`

```python
python analytics/scripts/ml_expected_r.py
```

#### Objective Comparison

Train two models on same features, same split:

| Model | Predicts | Spearman ρ | Top 25% | Top 50% |
|---|---|---|---|---|
| Classification | P(win) | −0.016 | +0.009R | +0.019R |
| Regression | Expected R | +0.067** | +0.112R | +0.116R |

**Finding:** Ranking by expected R beats ranking by win probability.

### Stage 9: Generate Insights

**Module:** `analytics/scripts/generate_insights.py`  
**Runtime:** ~2 seconds  
**Inputs:** All outputs from stages 1-8  
**Output:** `reports/business_insights.md`

```python
python analytics/scripts/generate_insights.py
```

#### Insights Generated

20 business findings, computed not typed:

1. **Total desk profit and attribution** — +$220K net, fees consume 54.7%
2. **Survivorship effect** — 4/12 accounts blew up, equity curve is artificial
3. **One hour carries the desk** — 08:00 UTC = +0.212R, 51% of profit
4. **Win rate is a trap** — <1R band: 52.9% WR, −0.113R expectancy
5. **Fees destroy strategies** — Scalping: +$15K gross, −$105K net
6. **Revenge trading is destructive** — −0.141R at 2.3× position size
7. **Peak quality degrades** — After 8th trade: −0.209R expectancy
8. **Disposition effect** — Losers held 286 min vs 198 min for winners

(... 12 more insights in full report)

### Stage 10: Build Dashboard

**Module:** `analytics/scripts/build_dashboard.py`  
**Runtime:** ~1 second  
**Input:** All analytics outputs  
**Output:** `frontend/dashboard/data.js`

```python
python analytics/scripts/build_dashboard.py
```

#### Process

1. Load clean trades CSV
2. Compute aggregations (by hour, by strategy, by trader, etc.)
3. Dictionary-encode categorical columns
4. Serialize to columnar format
5. Write `data.js` (705 KB)

#### Data Format

```javascript
window.TradeTrackData = {
  metadata: { trade_count: 10781, ... },
  traders: ["Trader1", ...],
  assets: ["BTC", ...],
  strategies: ["Scalping", ...],
  trades: {
    ids: [1, 2, 3, ...],
    trader_idx: [0, 2, 1, ...],
    entry_price: [42500.5, ...],
    ...
  }
}
```

---

## Running the Full Pipeline

### Option 1: Full Rebuild

```bash
python analytics/scripts/run_all.py
```

Runs stages 1-10 (~30 seconds total).

### Option 2: Skip Data Generation

```bash
python analytics/scripts/run_all.py --skip-generate
```

Reuses existing `datasets/raw/trades_raw.csv`, runs stages 2-10 (~25 seconds).

### Option 3: Run Single Stage

```bash
python analytics/scripts/run_all.py --only ml_model
```

Runs only stage 7, assuming all dependencies exist.

---

## Pipeline Error Handling

The pipeline fails loudly and immediately:

```python
# run_all.py
for stage in STAGES:
    try:
        run_stage(stage)
    except Exception as e:
        print(f"FAILED: {stage}")
        traceback.print_exc()
        sys.exit(1)  # Stop immediately
```

**Benefits:**
- You know immediately if something broke
- "It ran" means all stages succeeded
- No silent failures from stale files

---

## Reproducibility

All stages are deterministic:

```python
# config.py
RANDOM_SEED = 20260731  # Controls all randomness

# generate_dataset.py
np.random.seed(RANDOM_SEED)

# All outputs are sorted by key
# All timestamps are hardcoded
```

**Result:** Run the pipeline twice, get bit-for-bit identical outputs.

---

## Next Steps

- **[database_design.md](database_design.md)** — Schema and SQL queries
- **[machine_learning.md](machine_learning.md)** — Model details and evaluation
- **[dashboard.md](dashboard.md)** — UI design and interactivity
