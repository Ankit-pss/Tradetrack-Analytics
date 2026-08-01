"""
TradeTrack Analytics — dashboard data layer.
=============================================

Compiles the cleaned blotter into `dashboard/data.js`, the single asset the
dashboard loads.

The payload is COLUMNAR and dictionary-encoded rather than a list of row
objects. A naive `df.to_json(orient="records")` of 10,000+ trades produces
several megabytes of repeated key names; encoding each categorical column as an
integer index into a small lookup table, and shipping one array per field, cuts
that by roughly an order of magnitude and is also the layout the client-side
filter loop wants — a filter pass is then a single scan over typed arrays
rather than property lookups on 10,000 objects.

Run:  python python/build_dashboard.py
Out:  dashboard/data.js
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (CLEAN_TRADES_CSV, DASHBOARD_DIR, PROCESSED_DIR,  # noqa: E402
                    TRADERS)

STARTING_CAPITAL = float(sum(t["start_balance"] for t in TRADERS))

JOURNAL_TRADES_CSV = os.path.join(PROCESSED_DIR, "journal_trades_clean.csv")

CATEGORICALS = ["asset", "strategy", "trading_session", "trade_type",
                "trader_id", "weekday", "risk_bucket", "emotional_state",
                "data_source"]


def capital_by_source(df: pd.DataFrame) -> dict:
    """Opening capital for each source, so equity and drawdown use the right base.

    The simulated desk opens on the sum of the configured trader balances; the
    live journal opens on whatever `--capital` was passed to import_journal.py.
    That figure isn't stored directly, but every row carries both the running
    balance and the cumulative P&L that produced it, so the opening balance is
    recoverable as their difference on the first trade. Baselining 13 real
    trades against the simulated desk's capital would report a drawdown near
    zero purely because the denominator is ~40x too large.
    """
    out: dict = {}
    for source, grp in df.groupby("data_source"):
        if source == "synthetic":
            out[source] = STARTING_CAPITAL
            continue
        first = grp.sort_values("trade_date").iloc[0]
        opening = float(first["account_balance"]) - float(first["cum_pnl_trader"])
        out[source] = round(opening, 2)
    return out


def encode(df: pd.DataFrame) -> dict:
    """Dictionary-encode the categorical columns; keep numerics as raw arrays."""
    payload: dict = {"dims": {}, "cols": {}}

    for col in CATEGORICALS:
        cats = sorted(df[col].dropna().unique().tolist())
        lookup = {v: i for i, v in enumerate(cats)}
        payload["dims"][col] = cats
        payload["cols"][col] = df[col].map(lookup).fillna(-1).astype(int).tolist()

    # Dates as days since epoch-start -> a compact integer the client can filter
    # numerically without parsing 10,000 date strings.
    dates = pd.to_datetime(df["trade_date"])
    origin = dates.min()
    payload["dateOrigin"] = origin.strftime("%Y-%m-%d")
    payload["cols"]["day"] = ((dates - origin).dt.days).astype(int).tolist()

    payload["cols"]["net"] = df["net_profit"].round(2).tolist()
    payload["cols"]["gross"] = df["profit_loss"].round(2).tolist()
    payload["cols"]["fees"] = df["fees"].round(2).tolist()
    payload["cols"]["win"] = df["is_win"].astype(int).tolist()
    payload["cols"]["rr"] = df["risk_reward_ratio"].round(2).tolist()
    payload["cols"]["r"] = df["r_multiple"].round(4).tolist()
    payload["cols"]["risk"] = df["risk_pct"].round(3).tolist()
    # -1 means "no exit time recorded" — the journal app leaves it blank on most
    # trades. Filling those with 0 would quietly pull the average holding time
    # down, so the client excludes the sentinel from duration stats instead.
    payload["cols"]["dur"] = (df["trade_duration_min"].fillna(-1)
                              .round(0).astype(int).tolist())
    payload["cols"]["hour"] = df["entry_hour"].astype(int).tolist()

    payload["n"] = int(len(df))
    payload["capitalBySource"] = capital_by_source(df)
    payload["startingCapital"] = float(sum(payload["capitalBySource"].values()))
    payload["dateMin"] = str(dates.min().date())
    payload["dateMax"] = str(dates.max().date())
    payload["generated"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    return payload


def load_trades() -> pd.DataFrame:
    """Every trade the dashboard can show, both sources included.

    The warehouse honours `--data`, but the dashboard deliberately does not:
    the Source toggle in the UI filters client-side, so the payload has to
    carry both sources or there is nothing to toggle between. If the journal
    has never been imported the file is simply absent and the dashboard shows
    the simulated desk alone.
    """
    frames = [pd.read_csv(CLEAN_TRADES_CSV, parse_dates=["trade_date"])]

    if os.path.exists(JOURNAL_TRADES_CSV):
        real = pd.read_csv(JOURNAL_TRADES_CSV, parse_dates=["trade_date"])
        frames.append(real)
        print(f"  sources  {len(frames[0]):,} synthetic + {len(real):,} real")
    else:
        print(f"  sources  {len(frames[0]):,} synthetic "
              f"(no journal import found — run python/import_journal.py)")

    df = pd.concat(frames, ignore_index=True)
    if "data_source" not in df.columns:
        df["data_source"] = "synthetic"
    df["data_source"] = df["data_source"].fillna("synthetic")
    return df.sort_values("trade_date").reset_index(drop=True)


def main() -> None:
    df = load_trades()
    payload = encode(df)

    out = os.path.join(DASHBOARD_DIR, "data.js")
    with open(out, "w") as fh:
        fh.write("/* Generated by python/build_dashboard.py — do not edit by hand. */\n")
        fh.write("const TT_DATA = ")
        json.dump(payload, fh, separators=(",", ":"))
        fh.write(";\n")

    size_kb = os.path.getsize(out) / 1024
    print(f"  encoded {payload['n']:,} trades -> {out}")
    print(f"  payload {size_kb:,.0f} KB "
          f"({len(payload['cols'])} columns, "
          f"{len(payload['dims'])} dictionary-encoded dimensions)")
    print(f"  date range {payload['dateMin']} -> {payload['dateMax']}")


if __name__ == "__main__":
    main()
