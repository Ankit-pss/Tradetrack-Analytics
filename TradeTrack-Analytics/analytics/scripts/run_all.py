"""
TradeTrack Analytics — full pipeline orchestrator.
===================================================

Runs every stage in dependency order and fails loudly on the first error, so
"it built" means every stage actually succeeded rather than the last one
printing something.

    generate_dataset  ->  data/raw/trades_raw.csv
    data_cleaning     ->  data/processed/*.csv, reports/data_quality_report.md
    load_to_sql       ->  data/tradetrack.db          (with reconciliation checks)
    run_sql_analysis  ->  reports/sql_analysis_results.md  (all 21 queries)
    kpi_engine        ->  reports/kpi_summary.json
    visualizations    ->  images/*.png, dashboard/charts/*.html
    ml_model          ->  reports/ml_model_report.md, images/12_ml_*.png
    generate_insights ->  reports/business_insights.md
    build_dashboard   ->  dashboard/data.js

Run:  python analytics/scripts/run_all.py
      python analytics/scripts/run_all.py --skip-generate   (keep the existing dataset)
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STAGES = [
    ("generate_dataset", "Simulate the trade blotter"),
    ("data_cleaning", "Clean and engineer features"),
    ("load_to_sql", "Build the SQLite warehouse"),
    ("run_sql_analysis", "Execute the 21 SQL analyses"),
    ("kpi_engine", "Compute KPI and risk metrics"),
    ("visualizations", "Render the chart deck"),
    ("ml_model", "Train and evaluate the classifier"),
    ("ml_expected_r", "Test the expected-R objective"),
    ("generate_insights", "Derive the 20 business insights"),
    ("build_dashboard", "Compile the dashboard data layer"),
]

BAR = "=" * 74


def run_stage(module_name: str, description: str, n: int, total: int,
              extra_kwargs: dict | None = None) -> float:
    print(f"\n{BAR}")
    print(f" [{n}/{total}]  {description}")
    print(f"{BAR}")
    t0 = time.time()

    module = importlib.import_module(module_name)
    entry = getattr(module, "main", None)
    if entry is None:
        # load_to_sql exposes build() rather than main()
        entry = getattr(module, "build")

    if extra_kwargs and module_name == "load_to_sql":
        entry(extra_kwargs.get("data_source", "synthetic"))
    else:
        entry()

    elapsed = time.time() - t0
    print(f"\n  ✓ {module_name} completed in {elapsed:.1f}s")
    return elapsed


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the TradeTrack Analytics pipeline")
    ap.add_argument("--skip-generate", action="store_true",
                    help="reuse the existing raw dataset instead of re-simulating")
    ap.add_argument("--only", metavar="STAGE",
                    help="run a single stage by module name")
    ap.add_argument("--data", choices=["synthetic", "real", "both"], default="synthetic",
                    help="which trades to load: synthetic (default), real (journal app), or both")
    args = ap.parse_args()

    stages = list(STAGES)
    if args.only:
        stages = [s for s in stages if s[0] == args.only]
        if not stages:
            print(f"unknown stage '{args.only}'. Available: "
                  f"{', '.join(s[0] for s in STAGES)}")
            return 2
    elif args.skip_generate:
        stages = [s for s in stages if s[0] != "generate_dataset"]

    print(BAR)
    print(" TRADETRACK ANALYTICS — FULL PIPELINE")
    print(BAR)
    print(f" {len(stages)} stages to run")
    print(f" data source: {args.data}")

    timings: list[tuple[str, float]] = []
    t_start = time.time()

    for i, (module_name, description) in enumerate(stages, start=1):
        try:
            kwargs = {"data_source": args.data} if args.data else {}
            elapsed = run_stage(module_name, description, i, len(stages),
                              extra_kwargs=kwargs)
            timings.append((module_name, elapsed))
        except Exception:                                        # noqa: BLE001
            print(f"\n{BAR}")
            print(f" ✗ PIPELINE FAILED at stage {i}/{len(stages)}: {module_name}")
            print(BAR)
            traceback.print_exc()
            return 1

    total = time.time() - t_start
    print(f"\n{BAR}")
    print(" PIPELINE COMPLETE")
    print(BAR)
    for name, elapsed in timings:
        print(f"   {name:<20} {elapsed:>7.1f}s")
    print(f"   {'TOTAL':<20} {total:>7.1f}s")
    print("\n Outputs:")
    print("   data/processed/trades_clean.csv     cleaned analytical dataset")
    print("   data/tradetrack.db                  SQLite warehouse")
    print("   reports/                            KPIs, SQL results, ML, insights")
    print("   images/                             chart deck (PNG)")
    print("   dashboard/index.html                interactive dashboard")
    print("   notebooks/TradeTrack_Analytics.ipynb  analytical narrative")
    return 0


if __name__ == "__main__":
    sys.exit(main())
