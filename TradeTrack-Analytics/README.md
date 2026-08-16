# TradeTrack Analytics
### AI-Powered Trading Performance & Risk Analysis Platform

An end-to-end data analytics project analyzing **10,781 closed trades** from 12 traders across 6 instruments and 7 strategies — from data generation and cleaning, through SQL warehousing and Python analysis, to an interactive dashboard and a leakage-controlled machine-learning model.

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.9%2B-3987E5" alt="Python">
  <img src="https://img.shields.io/badge/SQL-SQLite%20warehouse-199E70" alt="SQL">
  <img src="https://img.shields.io/badge/Power%20BI-DAX%20%2B%20theme-C98500" alt="Power BI">
  <img src="https://img.shields.io/badge/ML-scikit--learn-9085E9" alt="ML">
  <img src="https://img.shields.io/badge/pipeline-reproducible-0CA30C" alt="Reproducible">
</p>

![Dashboard](reports/images/dashboard_preview.png)

---

## 📊 The Headline Result

| Metric | Value | | Metric | Value |
|---|---|---|---|---|
| **Closed trades** | **10,781** | | **Profit factor** | **1.07** |
| **Net P&L** | **+$220,184** (+51.2%) | | **Sharpe / Sortino** | **0.80 / 0.95** |
| **Win rate** | **35.13%** | | **Max drawdown** | **14.50%** ($62,492) |
| **Avg reward : risk** | **2.32 : 1** | | **Expectancy** | **$20.42** (+0.005R) / trade |

**Key Insight:** The desk is profitable, but the edge is thin. Fees consume 54.7% of gross profit, one strategy is gross-positive and net-negative purely on transaction costs, and the single largest behavioral effect is revenge trading at 2.3× normal position size.

---

## 🎯 Project Objectives

1. **Demonstrate full analytics lifecycle** — from raw data to actionable insights
2. **Measure real trading performance** — net of fees, using R-multiples for comparability
3. **Identify behavioral patterns** — why traders succeed or fail, not just what they traded
4. **Build a production ML model** — with guardrails against data leakage
5. **Create a zero-dependency dashboard** — interactive, responsive, no build step required

---

## 📁 Project Structure

```
TradeTrack-Analytics/
│
├── analytics/                          Data & analytics core
│   ├── scripts/                        Python pipeline modules
│   │   ├── config.py                   Centralized configuration
│   │   ├── run_all.py                  Pipeline orchestrator
│   │   ├── generate_dataset.py         Synthetic trade generation
│   │   ├── data_cleaning.py            Cleaning & feature engineering
│   │   ├── load_to_sql.py              Warehouse loader
│   │   ├── kpi_engine.py               KPI metrics library
│   │   ├── visualizations.py           Chart generation
│   │   ├── ml_model.py                 Classification model
│   │   └── generate_insights.py        Business insights engine
│   ├── models/                         ML model artifacts (references)
│   └── notebooks/                      Jupyter analytical notebooks
│
├── frontend/                           Dashboard & visualization
│   └── dashboard/                      Zero-dependency web dashboard
│       ├── index.html                  Main dashboard UI
│       ├── app.js                      Client-side application logic
│       ├── data.js                     Generated data layer
│       ├── styles.css                  Design system
│       └── charts/                     Exported interactive charts
│
├── database/                           Data warehouse layer
│   ├── sql/
│   │   ├── 01_schema.sql               DDL, indexes, views
│   │   └── 02_analysis_queries.sql     21 analytical SQL queries
│   └── README.md                       Database documentation
│
├── datasets/                           Data layer
│   ├── raw/
│   │   └── trades_raw.csv              11,130 rows (raw export)
│   ├── processed/
│   │   ├── trades_clean.csv            10,781 cleaned trades (77 columns)
│   │   ├── daily_performance.csv       Daily aggregation
│   │   ├── monthly_performance.csv     Monthly aggregation
│   │   ├── trader_summary.csv          Trader dimension
│   │   └── dim_calendar.csv            Date dimension
│   ├── tradetrack.db                   SQLite warehouse (star schema)
│   └── README.md                       Dataset documentation
│
├── reports/                            Analysis outputs
│   ├── images/                         Generated visualizations (16 charts)
│   ├── business_insights.md            20 computed insights
│   ├── data_quality_report.md          Cleaning decisions & statistics
│   ├── sql_analysis_results.md         Output of all 21 SQL queries
│   ├── ml_model_report.md              Model card & evaluation
│   └── kpi_summary.json                KPI metrics (machine-readable)
│
├── reporting/                          BI & reporting tools
│   └── powerbi/
│       ├── measures.dax                70+ DAX measures
│       ├── tradetrack_theme.json       Importable dark theme
│       ├── data_model.md               Schema & modeling notes
│       └── README.md                   Page-by-page spec
│
├── docs/                               Technical documentation
│   ├── project_overview.md             What, why, and how
│   ├── architecture.md                 System design & data flow
│   ├── analytics_pipeline.md           Pipeline stages explained
│   ├── database_design.md              Schema & queries
│   ├── machine_learning.md             Model development & evaluation
│   └── dashboard.md                    UI components & design
│
├── requirements.txt                    Python dependencies
├── README.md                           This file
├── LICENSE                             MIT License
└── .gitignore                          Git exclusions

```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- pip or conda
- ~2GB disk space (raw dataset + SQLite warehouse)

### Installation

```bash
# Clone and setup environment
git clone <repository-url>
cd TradeTrack-Analytics

# Create virtual environment
python -m venv venv
source venv/bin/activate                # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Full Pipeline

```bash
# Run complete analysis (generates data, cleans, loads warehouse, builds dashboard)
python analytics/scripts/run_all.py                    # ~30 seconds

# Rerun without regenerating the dataset
python analytics/scripts/run_all.py --skip-generate

# Run a specific stage
python analytics/scripts/run_all.py --only ml_model
```

### Viewing Results

```bash
# Open the interactive dashboard
open frontend/dashboard/index.html                     # macOS
# or
start frontend\dashboard\index.html                    # Windows
# or
xdg-open frontend/dashboard/index.html                 # Linux

# View analytical notebook
jupyter notebook analytics/notebooks/TradeTrack_Analytics.ipynb
```

---

## 📊 Pipeline Architecture

| Stage | Module | Input | Output | Purpose |
|---|---|---|---|---|
| 1 | `generate_dataset.py` | Parameters | `datasets/raw/trades_raw.csv` | Simulate blotter with defects |
| 2 | `data_cleaning.py` | Raw CSV | `datasets/processed/*.csv` | Clean, engineer 77 features |
| 3 | `load_to_sql.py` | Clean CSV | `datasets/tradetrack.db` | Build star-schema warehouse |
| 4 | `run_sql_analysis.py` | Database | `reports/sql_analysis_results.md` | Execute 21 analytical queries |
| 5 | `kpi_engine.py` | Clean CSV | `reports/kpi_summary.json` | Compute performance metrics |
| 6 | `visualizations.py` | Clean CSV | `reports/images/*.png` | Render 16-chart deck |
| 7 | `ml_model.py` | Clean CSV | `reports/ml_model_report.md` | Train classifier, evaluate |
| 8 | `ml_expected_r.py` | Clean CSV | `reports/ml_expected_r_report.md` | Compare objectives |
| 9 | `generate_insights.py` | All outputs | `reports/business_insights.md` | Derive 20 insights |
| 10 | `build_dashboard.py` | All data | `frontend/dashboard/data.js` | Compile dashboard data layer |

---

## 🔧 Key Features

### Data Generation
- **GBM price paths** with volatility clustering
- **Win probability anchored to break-even rate** — ensures mechanical consistency
- **Behavioral profiles** per trader — skill, discipline, risk appetite
- **Psychology feedback loop** — losing streaks trigger FOMO/revenge trading
- **Survivorship** — traders who blow up 85% account stop trading

### Data Cleaning
Handles production journal defects with documented decisions:
- 180 duplicates (exact match or repeated trade_id)
- 156 numbers formatted as `"1,250.75"` (regex + cast)
- 460 casing/whitespace variants (map to canonical)
- 45 impossible durations ≤ 0 (recompute from timestamps)
- 29 corrupted prices (dual validation: robust MAD z-score + structural)
- 140 open trades (quarantine, do not delete)
- 258 missing emotional states (default to 'Unspecified')

### SQL Warehouse
- **Star schema** with 1 fact table + 3 dimensions
- **21 analytical queries** executed on every run:
  - Gaps-and-islands streak detection
  - Window-function drawdown curves
  - Month-over-month growth tracking
  - Risk/reward band analysis
- **3 views** for common rollups
- **7 indexes** for query performance
- **Reconciliation checks** on row counts and P&L totals

### Machine Learning
- **Leakage-controlled classifier** using pre-trade information only
- **31 post-close columns hard-banned** by runtime assertion
- **Chronological split** (never random) — train on past, test on future
- **Multiple models compared** — Random Forest, Gradient Boosting
- **Model card** states honest limitations — high P(win) ≠ high expectancy

### Dashboard
- **Zero dependencies** — vanilla JS, no CDN, no build step
- **6 animated KPI cards** — gross, net, win rate, avg RR, max drawdown, duration
- **10 interactive charts** — equity curve, monthly P&L, distributions, heatmaps
- **5 live filters** — date range, asset, strategy, session, side
- **Glassmorphism design** — responsive to mobile, honors `prefers-reduced-motion`
- **Columnar data layer** — dictionary-encoded for 705KB payload

---

## 📈 Sample Insights

Full analysis in [`reports/business_insights.md`](reports/business_insights.md):

| # | Finding | Impact |
|---|---|---|
| 1 | **One hour carries the desk** | 08:00 UTC: +0.212R, 42.6% WR, $113.3K = 51% of profit |
| 2 | **Scalping is gross-positive, net-negative** | +$15K gross → -$105.8K net (fees 11.7% vs 3.6% elsewhere) |
| 3 | **Fees consume over half of gross profit** | $266K of $487K gross (54.7%) |
| 4 | **Revenge trading is most destructive** | -0.141R vs +0.089R disciplined, at 2.3× position size |
| 5 | **Quality collapses after 8th trade/day** | 9th+: -0.209R at 24.6% WR, largest average size |
| 6 | **High win rate ≠ profitable** | <1R band: 52.9% win rate, -0.113R expectancy |

---

## 🛠️ Technology Stack

| Layer | Tools | Rationale |
|---|---|---|
| **Data Generation** | NumPy (GBM), pandas | Deterministic simulation with market-realistic properties |
| **Cleaning & ETL** | pandas, NumPy, SciPy | Vectorized operations, statistical tests |
| **Warehouse** | SQLite 3 | Lightweight, portable, sufficient for 10K rows + indexes |
| **SQL Analysis** | Window functions, CTEs | Advanced analytical techniques |
| **Visualization** | Matplotlib, Plotly | Static charts (PNG) + interactive exports (HTML) |
| **ML** | scikit-learn | Random Forest, Gradient Boosting, model evaluation |
| **Dashboard** | Vanilla JS, SVG | Zero runtime dependencies, works offline |
| **BI** | Power BI | DAX measures, themes, end-user reporting |
| **Notebooks** | Jupyter | Interactive analysis and cross-validation |

---

## ✅ Reproducibility & Quality Assurance

- **Deterministic pipeline** — seeded at `config.RANDOM_SEED`, reproduces exactly
- **Automated reconciliation** — warehouse loader checks row counts & P&L totals
- **Query execution** — all 21 SQL queries run on every pipeline run
- **Cross-validation** — notebook reimplements KPI calculations independently
- **Assertion guards** — ML stage fails if post-close features leak into training
- **Documentation** — every cleaning decision logged with rationale

---

## 📚 Documentation

Navigate the technical docs:

- **[project_overview.md](docs/project_overview.md)** — What is this, why was it built, who uses it
- **[architecture.md](docs/architecture.md)** — System design, data flow, component interactions
- **[analytics_pipeline.md](docs/analytics_pipeline.md)** — Pipeline stages, inputs/outputs, decision logic
- **[database_design.md](docs/database_design.md)** — Schema, queries, why SQLite
- **[machine_learning.md](docs/machine_learning.md)** — Model development, leakage controls, evaluation
- **[dashboard.md](docs/dashboard.md)** — UI design, KPI cards, chart library

---

## 🔗 Integration with TradeTrack Journal

The main TradeTrack web app (server/ and client/ at repo root) feeds real trades into this analytics pipeline:

```
┌─────────────────────┐       import_journal.py      ┌──────────────────────────┐
│  TradeTrack Journal │ ──────────────────────────> │  TradeTrack Analytics    │
│  (server/ client/)  │ (honors 1 unit = qty/100)   │ cleaning → SQL → ML →    │
└─────────────────────┘                             │  dashboard → insights    │
                                                     └──────────────────────────┘
```

To analyze your trading journal:

```bash
python analytics/scripts/import_journal.py --capital 5000
```

This script:
- Reads trades from the web app's SQLite database
- Maps them into the analytical schema
- Reconciles P&L against a recomputation
- Prints sample-size and coverage warnings before results

---

## 📋 Chart Library

All 15 charts available in [`reports/images/`](reports/images/):

| Chart | Purpose |
|---|---|
| Equity curve | Cumulative P&L trajectory with crosshair |
| Monthly P&L | Bar chart by month with profitability |
| Win/loss distribution | P&L histogram with quartiles |
| Risk distribution | R-multiple histogram by side |
| Asset performance | P&L breakdown by instrument |
| Strategy performance | Win rate, expectancy, by strategy |
| Session analysis | Hour-of-day contribution |
| Weekday heatmap | Win rate by day × hour |
| Correlation matrix | Feature relationships |
| Psychology impact | Win rate & P&L by emotional state |
| ML model confusion matrix | Classification accuracy |
| ML decile lift | Expected-R model ranking |

---

## 🚦 Running Tests & Validation

```bash
# Full pipeline with validation
python analytics/scripts/run_all.py

# Spot-check: view the generated reports
cat reports/data_quality_report.md
cat reports/business_insights.md

# Validate dashboard data layer
tail -c 500 frontend/dashboard/data.js    # Should be valid JSON

# Run Jupyter notebook end-to-end
jupyter notebook analytics/notebooks/TradeTrack_Analytics.ipynb
```

---

## 🔮 Future Improvements

- **Walk-forward validation** — expanding window instead of single split
- **Per-venue fee modeling** — commission renegotiation ROI
- **Market-regime features** — volatility and trend state conditioning
- **dbt + Postgres** — production-grade data warehouse with schema tests
- **Streamlit/FastAPI** — live trade scoring and deployment
- **Survivorship-adjusted reporting** — cohort analysis with account blowup accounting

---

## 📄 License

MIT — see [LICENSE](LICENSE)

---

## 👤 Author

Built as a portfolio project demonstrating the full analytics lifecycle: data engineering, SQL warehousing, statistical analysis, machine learning, dashboard design, and stakeholder communication.

For questions or collaboration, open an issue or contact directly.

---

## 📌 Key Statistics at a Glance

| Aspect | Value |
|---|---|
| **Trades analyzed** | 10,781 |
| **Traders** | 12 |
| **Instruments** | 6 (BTC, ETH, EURUSD, GBPUSD, AAPL, SPY) |
| **Strategies** | 7 |
| **Date range** | 2024-01-01 to 2026-06-30 |
| **SQL queries** | 21 (all executed per run) |
| **Engineered features** | 77 |
| **Dashboard data size** | 705 KB (compressed) |
| **Pipeline execution time** | ~30 seconds |
| **Notebook cells** | 250+ |
| **DAX measures** | 70+ |
| **Insights** | 20 |

---

*Last updated: 2026-08-16*
