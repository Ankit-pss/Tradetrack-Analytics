# Analytics

## Data Processing Pipeline

End-to-end pipeline: data generation → cleaning → SQL → ML → insights.

### Structure

```
analytics/
├── scripts/           Python pipeline modules
│   ├── run_all.py     Full pipeline orchestrator
│   ├── config.py      Centralized configuration
│   └── [10 stage modules...]
│
├── notebooks/         Jupyter notebooks
│   └── TradeTrack_Analytics.ipynb
│
└── models/            ML model references (artifacts)
```

### Pipeline Stages

1. **generate_dataset.py** — Simulate blotter (GBM + behavior)
2. **data_cleaning.py** — Clean & engineer 77 features
3. **load_to_sql.py** — Build star-schema warehouse
4. **run_sql_analysis.py** — Execute 21 queries
5. **kpi_engine.py** — Compute performance metrics
6. **visualizations.py** — Render 16-chart deck
7. **ml_model.py** — Train classification model
8. **ml_expected_r.py** — Train regression model
9. **generate_insights.py** — Compute 20 insights
10. **build_dashboard.py** — Compile dashboard data layer

### Quick Start

```bash
# Full pipeline (~30 seconds)
python analytics/scripts/run_all.py

# Skip data generation (reuse existing dataset)
python analytics/scripts/run_all.py --skip-generate

# Run single stage
python analytics/scripts/run_all.py --only ml_model
```

### Configuration

All paths, constants, and parameters defined in `scripts/config.py`:

```python
# Paths
PROJECT_ROOT = ...
DATASETS_DIR = os.path.join(PROJECT_ROOT, "datasets")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")

# Simulation
RANDOM_SEED = 20260731
NUM_TRADERS = 12
NUM_INSTRUMENTS = 6
DATE_RANGE = "2024-01-01" to "2026-06-30"
```

---

**Documentation:** See [../docs/analytics_pipeline.md](../docs/analytics_pipeline.md)
