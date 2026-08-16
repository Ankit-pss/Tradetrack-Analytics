"""
TradeTrack Analytics — live journal importer.
==============================================

Bridges the TradeTrack **web app** (`server/database.db`) into this analytics
pipeline, so the same KPI definitions, SQL library and dashboard can be run
against real logged trades instead of the simulated dataset.

Two conventions from the app that this importer must honour exactly:

1.  **`quantity / 100 = ETH units`** (`server/app.py`: `eth_qty = quantity / 100`).
    The app stores `50` to mean 0.5 ETH. Reading `quantity` literally would
    report every P&L 100x too large, and every derived metric with it. The
    stored `profit_loss` is reconciled against a recomputation to prove the
    convention is applied correctly.

2.  **`date` is a full local ISO timestamp**, not a date. That is what makes
    session and hour-of-day analysis possible on real data.

Fields the web app does not capture are handled explicitly rather than being
silently defaulted:

    fees              not recorded  -> 0.0, and the report SAYS SO. Net == gross
                                      here, so cost analysis is unavailable.
    emotional_state   not recorded  -> 'Unspecified' (the app has a free-text
                                      `mistakes` field instead, which is mapped
                                      to a tilt flag when populated)
    trading_session   derived from the entry hour, using the app's LOCAL clock
    trader_id         single-user app -> a constant, configurable below

Run:  python python/import_journal.py
      python python/import_journal.py --capital 5000
Out:  data/processed/journal_trades_clean.csv
      reports/journal_kpi_summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ASSETS, PROCESSED_DIR, PROJECT_ROOT, REPORTS_DIR  # noqa: E402
import kpi_engine  # noqa: E402

# The web app lives one level above this analytics project.
JOURNAL_DB = os.path.join(os.path.dirname(PROJECT_ROOT), "server", "database.db")
OUT_CSV = os.path.join(PROCESSED_DIR, "journal_trades_clean.csv")
OUT_JSON = os.path.join(REPORTS_DIR, "journal_kpi_summary.json")

TRADER_ID = "TR-LIVE"
TRADER_NAME = "Journal User"
QUANTITY_DIVISOR = 100.0        # app convention: 100 quantity = 1 unit

# Below this, per-group statistics are noise. Quoting a Sharpe ratio on a
# handful of trades is the most common way a trading analysis misleads.
MIN_TRADES_FOR_STATS = 30


def session_from_hour(hour: int) -> str:
    if 0 <= hour < 8:
        return "Asia"
    if 8 <= hour < 13:
        return "London"
    return "New York"


def load_journal(path: str = JOURNAL_DB) -> pd.DataFrame:
    if not os.path.exists(path):
        raise SystemExit(f"journal database not found at {path}")
    conn = sqlite3.connect(path)
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY date", conn)
    conn.close()
    return df


def transform(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = raw.copy()
    notes: dict = {"rows_in": len(df)}

    # --- timestamps ------------------------------------------------------
    # The web app writes TWO ISO variants: "2026-04-22T14:30:48" from the
    # server, and "2026-04-21T22:15" (no seconds) from the browser's
    # datetime-local input. Pandas infers a single format from the first value
    # and would silently coerce the other variant to NaT, quietly dropping
    # those trades from every time-based analysis. format="ISO8601" accepts
    # both, and the count of each variant is reported.
    df["entry_datetime"] = pd.to_datetime(df["date"], format="ISO8601", errors="coerce")
    df["exit_datetime"] = pd.to_datetime(df["exit_date"], format="ISO8601",
                                         errors="coerce")
    notes["short_timestamps"] = int(
        df["date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$").sum())
    notes["unparseable_dates"] = int(df["entry_datetime"].isna().sum())
    df = df[df["entry_datetime"].notna()].reset_index(drop=True)
    df["trade_date"] = df["entry_datetime"].dt.normalize()

    # --- open vs closed --------------------------------------------------
    open_mask = df["exit_price"].isna() | df["profit_loss"].isna()
    notes["open_trades"] = int(open_mask.sum())
    df = df[~open_mask].reset_index(drop=True)

    # --- categoricals ----------------------------------------------------
    df["asset"] = df["asset"].astype(str).str.strip().str.upper()
    df["asset_class"] = df["asset"].map(
        {a: spec["class"] for a, spec in ASSETS.items()}).fillna("Other")
    df["trade_type"] = df["type"].astype(str).str.strip().str.capitalize()
    df["strategy"] = df["strategy"].astype(str).str.strip().replace({"": "Unspecified"})
    df["trader_id"] = TRADER_ID
    df["trader_name"] = TRADER_NAME

    # --- position size, honouring the app's /100 convention --------------
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce") / QUANTITY_DIVISOR
    for c in ("entry_price", "exit_price", "stoploss", "target", "profit_loss"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.rename(columns={"stoploss": "stop_loss", "target": "take_profit"})

    # --- reconcile the stored P&L against a recomputation ----------------
    # This is the check that proves the quantity convention is right. If the
    # divisor were wrong, recomputed would be 100x the stored value.
    direction = np.where(df["trade_type"].eq("Buy"), 1.0, -1.0)
    recomputed = (df["exit_price"] - df["entry_price"]) * df["quantity"] * direction
    mismatch = (recomputed - df["profit_loss"]).abs() > 0.01
    notes["pnl_mismatches"] = int(mismatch.sum())
    notes["max_pnl_diff"] = float((recomputed - df["profit_loss"]).abs().max())

    # --- money -----------------------------------------------------------
    # The web app does not record commissions. Reporting a fabricated estimate
    # would corrupt every net figure, so fees are zero AND flagged as absent.
    df["fees"] = 0.0
    df["net_profit"] = df["profit_loss"]
    notes["fees_recorded"] = False

    # --- risk geometry ---------------------------------------------------
    df["stop_distance"] = (df["entry_price"] - df["stop_loss"]).abs()
    df["target_distance"] = (df["take_profit"] - df["entry_price"]).abs()
    df["risk_amount"] = df["stop_distance"] * df["quantity"]
    df["notional"] = df["entry_price"] * df["quantity"]

    df["risk_reward_ratio"] = (df["target_distance"] / df["stop_distance"]
                               ).replace([np.inf, -np.inf], np.nan).round(2)
    df["r_multiple"] = np.where(df["risk_amount"] > 0,
                                df["net_profit"] / df["risk_amount"], np.nan)
    move = (df["exit_price"] - df["entry_price"]) * direction
    df["realised_rr"] = np.where(df["stop_distance"] > 0,
                                 move / df["stop_distance"], np.nan)
    df["rr_slippage"] = df["realised_rr"] - df["risk_reward_ratio"]
    df["fee_pct_of_risk"] = 0.0

    # --- outcome ---------------------------------------------------------
    df["is_win"] = (df["net_profit"] > 0).astype(int)
    df["win_loss"] = np.where(df["is_win"] == 1, "Win", "Loss")
    df["gross_profit"] = df["net_profit"].clip(lower=0)
    df["gross_loss"] = (-df["net_profit"]).clip(lower=0)
    df["trade_duration_min"] = (
        (df["exit_datetime"] - df["entry_datetime"]).dt.total_seconds() / 60)
    df.loc[df["trade_duration_min"] <= 0, "trade_duration_min"] = np.nan

    # --- calendar --------------------------------------------------------
    d = df["trade_date"]
    df["year"] = d.dt.year
    df["quarter"] = "Q" + d.dt.quarter.astype(str)
    df["month"] = d.dt.month
    df["month_name"] = d.dt.strftime("%b")
    df["year_month"] = d.dt.strftime("%Y-%m")
    df["iso_week"] = d.dt.isocalendar().week.astype("int64")
    df["year_week"] = d.dt.strftime("%G-W%V")
    df["weekday_num"] = d.dt.weekday
    df["weekday"] = d.dt.day_name()
    df["is_weekend"] = df["weekday_num"] >= 5
    df["entry_hour"] = df["entry_datetime"].dt.hour
    df["trading_session"] = df["entry_hour"].apply(session_from_hour)

    # --- journal fields the app does capture -----------------------------
    df["trade_notes"] = df["notes"].fillna("")
    mistakes = df["mistakes"].fillna("").astype(str).str.strip()
    df["emotional_state"] = np.where(mistakes != "", "Flagged (mistake logged)",
                                     "Unspecified")
    df["is_tilt_state"] = (mistakes != "").astype(int)
    df["is_controlled_state"] = 1 - df["is_tilt_state"]
    notes["mistakes_logged"] = int((mistakes != "").sum())

    # --- sequencing & equity ---------------------------------------------
    df = df.sort_values("entry_datetime").reset_index(drop=True)
    df["trade_id"] = "JN-" + df["id"].astype(int).astype(str).str.zfill(6)
    df["trade_seq"] = np.arange(1, len(df) + 1)
    df["trade_seq_in_day"] = df.groupby("trade_date").cumcount() + 1
    df["trades_that_day"] = df.groupby("trade_date")["trade_id"].transform("size")
    df["cum_pnl_trader"] = df["net_profit"].cumsum()
    df["cum_pnl_portfolio"] = df["cum_pnl_trader"]

    df["prev_result"] = df["is_win"].shift(1)
    df["prev_r_multiple"] = df["r_multiple"].shift(1)
    df["minutes_since_prev_exit"] = (
        (df["entry_datetime"] - df["exit_datetime"].shift(1)).dt.total_seconds() / 60)
    df["is_quick_reentry"] = ((df["minutes_since_prev_exit"] < 10)
                              & (df["prev_result"] == 0)).astype(int)

    streak_id = (df["is_win"] != df["is_win"].shift()).cumsum()
    run = df.groupby(streak_id).cumcount() + 1
    df["win_streak"] = np.where(df["is_win"] == 1, run, 0)
    df["loss_streak"] = np.where(df["is_win"] == 0, run, 0)
    df["prev_loss_streak"] = df["loss_streak"].shift(1).fillna(0)

    # --- buckets ---------------------------------------------------------
    df["duration_bucket"] = pd.cut(
        df["trade_duration_min"], [0, 15, 60, 240, 1440, np.inf],
        labels=["<15m", "15-60m", "1-4h", "4-24h", ">1d"]).astype(str)
    df["rr_bucket"] = pd.cut(df["risk_reward_ratio"], [0, 1, 2, 3, np.inf],
                             labels=["<1R", "1-2R", "2-3R", ">3R"]).astype(str)

    # --- data source tag -------------------------------------------------
    df["data_source"] = "real"
    return df, notes


def add_equity(df: pd.DataFrame, capital: float) -> pd.DataFrame:
    df["account_balance"] = capital + df["cum_pnl_trader"]
    df["equity_peak"] = df["account_balance"].cummax()
    df["drawdown_abs"] = df["equity_peak"] - df["account_balance"]
    df["drawdown_pct"] = np.where(df["equity_peak"] > 0,
                                  df["drawdown_abs"] / df["equity_peak"] * 100, 0.0)
    df["risk_pct"] = np.where(df["account_balance"] > 0,
                              df["risk_amount"] / df["account_balance"] * 100, np.nan)
    df["reward_pct"] = df["risk_pct"] * df["risk_reward_ratio"]

    # risk_pct only exists once the equity curve is known, so this bucket has to
    # be cut here rather than in transform(). Same bins as data_cleaning.py so
    # the two sources share one scale when they are blended.
    df["risk_bucket"] = pd.cut(
        df["risk_pct"],
        bins=[0, 0.5, 1.0, 2.0, 3.0, np.inf],
        labels=["<0.5%", "0.5-1%", "1-2%", "2-3%", ">3%"],
    ).astype(str)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Import the live TradeTrack journal")
    ap.add_argument("--db", default=JOURNAL_DB, help="path to the journal SQLite file")
    ap.add_argument("--capital", type=float, default=10_000.0,
                    help="opening account balance, used for %%-of-equity metrics")
    args = ap.parse_args()

    print("Importing the live TradeTrack journal ...")
    raw = load_journal(args.db)
    print(f"  source        : {os.path.relpath(args.db, os.path.dirname(PROJECT_ROOT))}")
    print(f"  rows in db    : {len(raw):,}")

    df, notes = transform(raw)
    df = add_equity(df, args.capital)

    print(f"  closed trades : {len(df):,}  (open: {notes['open_trades']})")
    print(f"  quantity rule : stored / {QUANTITY_DIVISOR:.0f} = units "
          f"(app convention)")
    print(f"  P&L reconcile : {notes['pnl_mismatches']} mismatches, "
          f"max diff {notes['max_pnl_diff']:.4f}")

    if notes["pnl_mismatches"]:
        print("  WARNING: stored profit_loss disagrees with the recomputation — "
              "check the quantity convention before trusting these figures.")

    df.to_csv(OUT_CSV, index=False)
    print(f"  written       : {os.path.relpath(OUT_CSV, PROJECT_ROOT)}")

    # ---- KPIs, using the SAME engine as the simulated dataset ------------
    kpis = kpi_engine.compute_all(df, starting_capital=args.capital)
    kpis["meta"]["source"] = "live journal"
    kpis["meta"]["fees_recorded"] = notes["fees_recorded"]
    kpis["meta"]["sample_adequate"] = len(df) >= MIN_TRADES_FOR_STATS
    with open(OUT_JSON, "w") as fh:
        json.dump(kpis, fh, indent=2, default=str)

    # ---- caveats FIRST -------------------------------------------------
    # Deliberately printed BEFORE the numbers. On a sample this small the
    # summary below contains figures (Sharpe, Calmar, CAGR) that are
    # arithmetically correct and practically meaningless; a reader who sees
    # them first will anchor on them regardless of any footnote.
    span_days = (df["trade_date"].max() - df["trade_date"].min()).days
    dur_coverage = float(df["trade_duration_min"].notna().mean())

    print("\n" + "!" * 62)
    print(" READ THIS BEFORE THE NUMBERS")
    print("!" * 62)
    if len(df) < MIN_TRADES_FOR_STATS:
        print(f" * SAMPLE TOO SMALL: {len(df)} closed trades (need >= "
              f"{MIN_TRADES_FOR_STATS}).")
        print(f"   One trade moves the win rate by {100 / len(df):.1f} percentage "
              f"points. The")
        print("   win rate, profit factor, Sharpe and drawdown below DESCRIBE what")
        print("   happened. They are not evidence of an edge.")
    if span_days < 90:
        print(f" * CAGR IS EXTRAPOLATED from {span_days} days of trading and should")
        print("   be ignored entirely. Annualising a 25-day sample is meaningless.")
    if not notes["fees_recorded"]:
        print(" * NO FEES RECORDED by the web app, so net P&L equals gross P&L.")
        print("   On the simulated desk fees consumed 54.7% of gross profit, so")
        print("   true net performance is materially worse than shown.")
    if dur_coverage < 0.9:
        print(f" * DURATION COVERAGE {dur_coverage:.0%}: only "
              f"{int(df['trade_duration_min'].notna().sum())} of {len(df)} trades")
        print("   record an exit time, so the average holding time is computed on")
        print("   that subset and is not representative.")
    n_assets, n_strats = df["asset"].nunique(), df["strategy"].nunique()
    if n_assets == 1 or n_strats == 1:
        print(f" * NO VARIATION to compare: {n_assets} asset(s), "
              f"{n_strats} strategy(ies).")
        print("   Per-asset and per-strategy breakdowns cannot say anything here.")
    if notes.get("short_timestamps"):
        print(f" * {notes['short_timestamps']} row(s) store a timestamp without "
              f"seconds ('...T22:15')")
        print("   while the rest include them. Both are parsed here, but the app")
        print("   should write one format — a naive reader would silently drop them.")
    print(" * Sessions derived from the app's LOCAL timestamps, not UTC.")
    print("!" * 62)

    kpi_engine.print_summary(kpis)

    print(f"\n  written: {os.path.relpath(OUT_JSON, PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
