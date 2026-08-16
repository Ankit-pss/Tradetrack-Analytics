# Project Overview

## What is TradeTrack Analytics?

TradeTrack Analytics is an **end-to-end data analytics platform** that demonstrates the complete data science lifecycle using real trading blotter data. It transforms raw trade data into actionable insights through rigorous data engineering, statistical analysis, machine learning, and interactive visualization.

The project analyzes **10,781 closed trades** from 12 traders across 6 financial instruments (cryptocurrencies, forex, and equities) and 7 trading strategies, producing insights about profitability, risk management, behavioral patterns, and predictive modeling.

---

## Why This Project Was Built

### Three Specific Problems

**1. Portfolio Project Gap**
The analytics landscape lacked a single project demonstrating:
- End-to-end pipeline (simulation → cleaning → warehousing → ML → dashboard)
- Production-grade guardrails (data leakage checks, reconciliation, reproducibility)
- Business storytelling through data (20 computed insights, not just metrics)

**2. Trading Industry's Metrics Problem**
Retail trading journals use flawed metrics:
- **Gross P&L** ignores fees (one strategy is +$15K gross, −$105K net due to 11.7% fees)
- **Dollar P&L** makes $12 scalps incomparable to $4,000 swings
- **Win rate alone** misleads (52.9% win rate with −0.113R expectancy)

This project uses **R-multiples** (risk-normalized returns) to make all trades comparable, and **net P&L** (real money received) to tell the truth.

**3. Interview Preparation**
A project that answers:
- "Can you build data pipelines?" ✓ (Python ETL, reconciliation checks)
- "Can you design databases?" ✓ (Star schema, window functions, 21 queries)
- "Can you do machine learning responsibly?" ✓ (Leakage controls, model card, honest limitations)
- "Can you communicate with data?" ✓ (20 insights, dashboard, Power BI)

---

## Target Users

### 1. **Data Engineering Candidates**
Use this to learn or interview about:
- Cleaning pipelines (handling production defects documented)
- SQL warehousing (star schema, window functions, performance optimization)
- Python data stack (pandas, NumPy, SciPy)
- Orchestration (run_all.py pipeline with dependency ordering)
- Reconciliation (validating data transformations end-to-end)

### 2. **Data Scientists & Analysts**
Study the project for:
- Feature engineering (77 engineered columns from base trades)
- ML guardrails (leakage controls, chronological splits, model cards)
- Exploratory data analysis (SQL + Jupyter + visualizations)
- Business storytelling (metrics that matter, not just what's easy to compute)

### 3. **Financial Analysts & Traders**
Use it to understand:
- Why fees matter (54.7% of gross profit)
- Behavioral economics (revenge trading at 2.3× normal size)
- Risk-adjusted returns (R-multiples, Sharpe ratio, maximum drawdown)
- Strategy evaluation (win rate vs. expectancy distinction)

### 4. **Full-Stack Engineers**
Learn how to build:
- Zero-dependency dashboards (vanilla JS, SVG, no build step)
- Interactive data visualization (5 filters, 10 charts, real-time filtering)
- Data-driven UI (columnar format, dictionary encoding)
- Responsive design (mobile-friendly, dark theme, accessibility)

---

## Main Objectives

### Objective 1: Data Truth
**Goal:** Measure trading performance accurately, net of fees, using risk-normalized metrics.

**Why it matters:**
- Gross P&L is fiction — fees are 54.7% of profit
- Dollar P&L doesn't tell you which strategy is best
- Win rate is a lagging indicator of quality

**How we achieve it:**
- Every P&L figure is after all costs (commissions, slippage, fees)
- All results in R-multiples (reward : risk), not dollars
- Win rate is compared against break-even rate, not presented in isolation

---

### Objective 2: Production Rigor
**Goal:** Build a pipeline that doesn't fail silently and can be trusted in production.

**Implementation:**
- **Reconciliation checks** — warehouse loader validates row counts and P&L totals
- **Assertion guards** — ML stage fails immediately if post-close features leak
- **Deterministic seeding** — full rebuild reproduces every figure exactly
- **Execution verification** — all 21 SQL queries run on every pipeline run
- **Cross-validation** — notebook reimplements KPI calculations independently

**Benefit:** "It ran" means the pipeline actually succeeded, not that it printed output.

---

### Objective 3: Behavioral Insights
**Goal:** Understand not just *what* traders traded, but *why* they won or lost.

**Key Patterns Discovered:**
- Revenge trading costs −0.141R vs +0.089R discipline, at **2.3× position size**
- One hour (08:00 UTC) carries **51% of total profit**
- Quality collapses after 8 trades/day (9th+ trade: −0.209R)
- Disposition effect: losers held 286 min vs 198 min for winners (+44%)

---

### Objective 4: Predictive Modeling
**Goal:** Build a model that scores trades at entry using only pre-trade information.

**Constraints (The Honest Limitations):**
- 31 post-close columns are **hard-banned** by runtime assertion
- Split is **chronological** (never random) — train on past, test on future
- **Accuracy is not the headline** — 36% of trades lose money, so guessing "Loss" every time scores 63.5%
- **Model learns what isn't useful** — high P(win) correlates with low R, so ranking by win probability sorts by wrong trades

**What We Found:**
- Random Forest: 60.2% accuracy, 0.618 ROC-AUC
- Expected-R model beats probability model: +0.116R vs +0.019R at top 50%
- But even the best model only lifts expectancy to +0.116R from +0.041R base

**Implication:** Predictive modeling works, but the effect is thin and conditional on objective choice.

---

### Objective 5: Communicative Dashboard
**Goal:** Make data accessible without requiring SQL skills or Jupyter notebooks.

**Features:**
- **Zero setup** — single HTML file, no build step, works offline
- **Interactive** — 5 filters recompute all 10 charts on 10,781 trades in <100ms
- **Accessible** — dark theme, glassmorphism, meets 3:1 contrast on categorical colors
- **Complete** — 6 KPI cards + 10 charts covers the full analytical scope

---

## Workflow: How to Use This Project

### For Learning / Portfolio Building

```
1. Clone the repo
2. Read this overview (you are here)
3. Run the pipeline: python analytics/scripts/run_all.py
4. Open the dashboard: open frontend/dashboard/index.html
5. Read the insights: cat reports/business_insights.md
6. Study the code:
   - analytics/scripts/data_cleaning.py (production defect handling)
   - database/sql/02_analysis_queries.sql (SQL patterns)
   - analytics/scripts/ml_model.py (leakage controls)
   - frontend/dashboard/app.js (filtering algorithm)
7. Read the technical docs: docs/
```

### For Interviewing

**Show this project to demonstrate:**

| Skill | Evidence |
|---|---|
| **Data Engineering** | data_cleaning.py: 8 documented cleaning stages + reconciliation |
| **SQL Mastery** | sql/02_analysis_queries.sql: CTEs, window functions, gaps-and-islands |
| **Python Data Stack** | config.py: centralized paths; run_all.py: orchestration; full pandas pipeline |
| **ML Rigor** | ml_model.py: leakage checks, assertions, model card, honest limitations |
| **Frontend** | app.js: 5-filter real-time interactive dashboard, zero dependencies |
| **Communication** | business_insights.md: 20 findings, every number computed + cited |

**Interview talking points:**

- "I built this because the industry uses bad metrics — my pipeline uses R-multiples so $12 scalps are comparable to $4K swings"
- "I control for data leakage in ML by hard-banning 31 post-close columns with a runtime assertion"
- "I validate the pipeline with reconciliation checks that abort on drift, so 'it ran' means it succeeded"
- "My dashboard is zero dependencies — vanilla JS and SVG, works offline, no build step needed"
- "I discovered that revenge trading costs 2.3× normal position size and −0.141R, which is the single largest behavioral effect"

### For Analyzing Your Own Trades

```bash
python analytics/scripts/import_journal.py --capital 5000
```

This reads your TradeTrack Journal app database and:
- Maps your trades into the analytical schema
- Honors the app's `quantity / 100 = 1 unit` convention
- Reconciles P&L to prove the mapping is correct
- Prints sample-size warnings before results

---

## Key Design Decisions

### Why Simulate Data Instead of Sample?

Real retail blotter data is proprietary. Rather than sampling columns independently (which produces data with no structure), the generator **simulates the process** that creates a blotter:

- **GBM price paths** with volatility clustering, so entry/stop/target are anchored to reality
- **Win probability anchored to RR break-even**, so a 4:1 target can't have an 80% win rate
- **Behavioral profiles** per trader (skill, discipline, risk appetite)
- **Psychology feedback loop** — losing streaks trigger FOMO/revenge states, raising size and lowering win rate
- **Survivorship** — traders who lose 85% of capital stop trading, creating genuine desk-level effects

**Result:** Structurally realistic data with rediscoverable signal that a real analyst would find.

### Why R-Multiples?

A trade where you risk $100 to make $200 (2:1) is worth the same whether your account is $1K or $1M. R-multiples make all trades comparable:

- **R = |entry − stop| × quantity**
- **Reward in R = net_profit / R**
- Scaling from $12 scalp to $4K swing becomes a ranking problem, not an apples-oranges problem

### Why SQL Before Python?

- SQL is the single source of truth for aggregations (if something's in the dashboard, query it from SQL)
- 21 queries run on every pipeline run, so they never rot
- Window functions and CTEs force clean thinking about joins and grouping
- Reconciliation checks in the loader prevent silent corruption

### Why Zero-Dependency Dashboard?

- No build step = no knowledge of webpack needed
- Works offline = can share as a file, no server required
- Fast = filters recompute 10,781 trades in <100ms
- Accessible = single-threaded, no streaming or async complexity

---

## Reproducibility & Determinism

Every figure in this project is reproducible:

- **Data generation** — seeded at `config.RANDOM_SEED`
- **All SQL queries** — executed on every run
- **Notebook** — generated from code and executed end-to-end
- **Insights** — computed by `generate_insights.py`, not typed by hand
- **Dashboard** — built from generated data layer

Run `python analytics/scripts/run_all.py` twice on the same machine, and you get bit-for-bit identical results.

---

## What's Not in This Project

### Out of Scope (Intentionally Excluded)

- **Real market data** — simulation demonstrates the full pipeline without licensing/compliance issues
- **Live scoring API** — orchestration only, no serving layer
- **Cloud infrastructure** — local Python + SQLite demonstrates the logic
- **A/B testing framework** — analysis of one desk, not multiple treatment groups

### Could Be Improved

- Walk-forward validation (expanding window, not single chronological split)
- Per-venue fee modeling (to quantify commission renegotiation ROI)
- Market-regime features (is strategy edge conditional on volatility?)
- dbt + Postgres (production grade, with schema tests)

---

## Jumping Into the Code

**For the impatient**, start here:

1. **analytics/scripts/config.py** — all paths and constants
2. **analytics/scripts/run_all.py** — pipeline orchestrator
3. **analytics/scripts/data_cleaning.py** — production defect handling (read the docstring)
4. **database/sql/01_schema.sql** — warehouse schema (star design)
5. **database/sql/02_analysis_queries.sql** — SQL patterns (CTEs, window functions)
6. **analytics/scripts/ml_model.py** — leakage controls (the `BANNED_COLUMNS` assertion)
7. **frontend/dashboard/app.js** — filtering algorithm (vectorized on the client)
8. **reports/business_insights.md** — the 20 insights (why traders win or lose)

---

## Questions to Ask Yourself

As you explore this project, consider:

1. **Data Cleaning:** What defects in the raw data would I miss? How would they propagate?
2. **SQL:** Why use window functions instead of subqueries? When does denormalization make sense?
3. **ML:** What post-close columns would I accidentally leak into training? How would I catch it?
4. **Visualization:** How would I design filters so 10,781 rows feel instant, not slow?
5. **Business Logic:** Why is win rate alone not enough? What's the relationship between win rate and reward?
6. **Reproducibility:** What would break if I changed the random seed? Why should that scare me?

---

## Next Steps

- **[docs/architecture.md](architecture.md)** — System design and data flow diagram
- **[docs/analytics_pipeline.md](analytics_pipeline.md)** — Each pipeline stage in detail
- **[docs/database_design.md](database_design.md)** — Schema, queries, and SQL patterns
- **[docs/machine_learning.md](machine_learning.md)** — Model development and evaluation
- **[docs/dashboard.md](dashboard.md)** — UI design and interactivity

---

**Created:** 2026-08-16  
**Last Updated:** 2026-08-16
