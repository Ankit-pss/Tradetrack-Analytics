"""
TradeTrack Analytics — warehouse loader.
=========================================

Builds the SQLite warehouse from the cleaned CSVs: executes the DDL in
`sql/01_schema.sql`, populates the dimensions and the fact table, and verifies
referential integrity plus a set of reconciliation totals.

The load is deliberately strict — it fails loudly if the fact table does not
reconcile against the source CSV, because a warehouse that silently drops rows
is worse than no warehouse at all.

Run:  python python/load_to_sql.py
      python python/load_to_sql.py --data real        (real trades only)
      python python/load_to_sql.py --data synthetic   (synthetic trades only)
      python python/load_to_sql.py --data both        (real + synthetic, marked by source)
Out:  data/tradetrack.db
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    ASSETS, CLEAN_TRADES_CSV, DIM_CALENDAR_CSV, PROCESSED_DIR, SQL_DIR, SQLITE_DB,
)

FACT_COLUMNS = [
    "trade_id", "trader_id", "trade_date", "entry_time", "exit_time", "exit_date",
    "entry_datetime", "exit_datetime", "trading_session", "asset", "asset_class",
    "trade_type", "strategy", "emotional_state", "entry_price", "exit_price",
    "stop_loss", "take_profit", "quantity", "stop_distance", "notional",
    "risk_pct", "reward_pct", "risk_amount", "risk_reward_ratio", "realised_rr",
    "r_multiple", "profit_loss", "fees", "net_profit", "win_loss", "is_win",
    "gross_profit", "gross_loss", "trade_duration_min", "account_balance",
    "equity_peak", "drawdown_pct", "cum_pnl_trader", "trade_seq",
    "trade_seq_in_day", "trades_that_day", "win_streak", "loss_streak",
    "prev_result", "prev_loss_streak", "is_quick_reentry", "is_tilt_state",
    "year", "quarter", "month", "month_name", "year_month", "iso_week",
    "year_week", "weekday_num", "weekday", "entry_hour", "duration_bucket",
    "risk_bucket", "rr_bucket", "trade_notes", "data_source",
]


def build(data_source: str = "synthetic") -> None:
    """Load trades from the specified source(s).

    Args:
        data_source: "synthetic" (10K generated), "real" (journal app),
                     or "both" (real + synthetic, marked by source).
    """
    if data_source not in ("synthetic", "real", "both"):
        raise ValueError(f"invalid --data option: {data_source}")

    # Map data_source to file(s)
    if data_source == "synthetic":
        trades = pd.read_csv(CLEAN_TRADES_CSV)
    elif data_source == "real":
        journal_csv = os.path.join(PROCESSED_DIR, "journal_trades_clean.csv")
        if not os.path.exists(journal_csv):
            raise SystemExit(f"real trades file not found: {journal_csv}\n"
                           "run: python python/import_journal.py")
        trades = pd.read_csv(journal_csv)
    else:  # both
        # Load both, merge, ensure data_source column exists
        trades_syn = pd.read_csv(CLEAN_TRADES_CSV)
        journal_csv = os.path.join(PROCESSED_DIR, "journal_trades_clean.csv")
        if not os.path.exists(journal_csv):
            raise SystemExit(f"real trades file not found: {journal_csv}\n"
                           "run: python python/import_journal.py")
        trades_real = pd.read_csv(journal_csv)
        # Ensure both have data_source column
        trades_syn["data_source"] = trades_syn.get("data_source", "synthetic")
        trades_real["data_source"] = trades_real.get("data_source", "real")
        # Combine and re-sort by timestamp
        trades = pd.concat([trades_syn, trades_real], ignore_index=True)
        trades = trades.sort_values("trade_date").reset_index(drop=True)

    # Ensure data_source column exists even for single-source loads
    if "data_source" not in trades.columns:
        trades["data_source"] = data_source

    calendar = pd.read_csv(DIM_CALENDAR_CSV)

    # Dates are stored as ISO text — SQLite has no date type, and ISO-8601
    # strings sort and compare correctly as text.
    for col in ("trade_date", "exit_date", "entry_datetime", "exit_datetime"):
        trades[col] = pd.to_datetime(trades[col], errors="coerce")
    trades["trade_date"] = trades["trade_date"].dt.strftime("%Y-%m-%d")
    trades["exit_date"] = trades["exit_date"].dt.strftime("%Y-%m-%d")
    trades["entry_datetime"] = trades["entry_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    trades["exit_datetime"] = trades["exit_datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")

    if os.path.exists(SQLITE_DB):
        os.remove(SQLITE_DB)

    conn = sqlite3.connect(SQLITE_DB)
    conn.execute("PRAGMA foreign_keys = ON")

    with open(os.path.join(SQL_DIR, "01_schema.sql")) as fh:
        conn.executescript(fh.read())
    print(f"  schema applied from {os.path.join('sql', '01_schema.sql')}")

    # --- dimensions -----------------------------------------------------
    dim_trader = (
        trades.groupby(["trader_id", "trader_name"])
        .agg(first_trade_date=("trade_date", "min"),
             last_trade_date=("trade_date", "max"),
             total_trades=("trade_id", "size"))
        .reset_index()
    )
    dim_trader.to_sql("dim_trader", conn, if_exists="append", index=False)

    dim_asset = pd.DataFrame(
        [{"asset": a, "asset_class": spec["class"]} for a, spec in ASSETS.items()]
    )
    dim_asset = dim_asset[dim_asset["asset"].isin(trades["asset"].unique())]
    dim_asset.to_sql("dim_asset", conn, if_exists="append", index=False)

    pd.DataFrame({"strategy": sorted(trades["strategy"].unique())}).to_sql(
        "dim_strategy", conn, if_exists="append", index=False)

    cal = calendar.rename(columns={"date": "date"}).copy()
    cal["date"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    cal["is_weekend"] = cal["is_weekend"].astype(int)
    cal.to_sql("dim_calendar", conn, if_exists="append", index=False)

    print(f"  dim_trader   : {len(dim_trader):,}")
    print(f"  dim_asset    : {len(dim_asset):,}")
    print(f"  dim_strategy : {trades['strategy'].nunique():,}")
    print(f"  dim_calendar : {len(cal):,}")

    # --- fact -----------------------------------------------------------
    fact = trades[FACT_COLUMNS].copy()
    fact.to_sql("fact_trades", conn, if_exists="append", index=False)
    print(f"  fact_trades  : {len(fact):,}")

    conn.commit()
    verify(conn, trades)
    conn.close()
    print(f"\n  warehouse written: {SQLITE_DB}")


def verify(conn: sqlite3.Connection, source: pd.DataFrame) -> None:
    """Reconcile the warehouse against the source CSV. Fail loudly on drift."""
    print("\nVerifying load ...")
    cur = conn.cursor()

    n_db = cur.execute("SELECT COUNT(*) FROM fact_trades").fetchone()[0]
    assert n_db == len(source), f"row count drift: db={n_db} csv={len(source)}"
    print(f"  row count reconciles          : {n_db:,}")

    net_db = cur.execute("SELECT ROUND(SUM(net_profit), 2) FROM fact_trades").fetchone()[0]
    net_csv = round(float(source["net_profit"].sum()), 2)
    assert abs(net_db - net_csv) < 0.05, f"P&L drift: db={net_db} csv={net_csv}"
    print(f"  net P&L reconciles            : ${net_db:,.2f}")

    orphans = cur.execute("""
        SELECT COUNT(*) FROM fact_trades f
        LEFT JOIN dim_trader   t ON t.trader_id = f.trader_id
        LEFT JOIN dim_asset    a ON a.asset     = f.asset
        LEFT JOIN dim_strategy s ON s.strategy  = f.strategy
        LEFT JOIN dim_calendar c ON c.date      = f.trade_date
        WHERE t.trader_id IS NULL OR a.asset IS NULL
           OR s.strategy IS NULL OR c.date IS NULL
    """).fetchone()[0]
    assert orphans == 0, f"{orphans} fact rows have no matching dimension row"
    print("  referential integrity         : 0 orphan fact rows")

    bad = cur.execute("""
        SELECT COUNT(*) FROM fact_trades
        WHERE ABS((profit_loss - fees) - net_profit) > 0.05
    """).fetchone()[0]
    assert bad == 0, f"{bad} rows fail net_profit = profit_loss - fees"
    print("  P&L arithmetic holds          : 0 violations")

    views = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name").fetchall()
    print(f"  views created                 : {', '.join(v[0] for v in views)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Load trades into SQLite warehouse")
    ap.add_argument("--data", choices=["synthetic", "real", "both"], default="synthetic",
                    help="which trades to load (default: synthetic)")
    args = ap.parse_args()

    print("Building SQLite warehouse ...")
    print(f"  data source: {args.data}")
    build(args.data)
