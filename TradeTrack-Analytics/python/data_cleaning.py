"""
TradeTrack Analytics — cleaning & feature-engineering pipeline.
===============================================================

Takes the raw blotter export (`data/raw/trades_raw.csv`) and produces the
analytical layer the SQL, dashboard and ML stages all consume.

Cleaning steps, in order (each one logs what it changed):
    1.  Deduplicate           — exact duplicate rows + duplicate trade_ids
    2.  Type coercion         — "1,250.75" style strings -> float
    3.  Categorical hygiene   — trim whitespace, canonical casing
    4.  Timestamp assembly    — entry/exit datetimes from date + time columns
    5.  Duration repair       — recompute from timestamps, null the impossible
    6.  Outlier handling      — fat-finger entry prices via a robust MAD z-score
    7.  Missing values        — open trades quarantined, journal fields defaulted
    8.  Integrity checks      — stop/target on the correct side of entry, and
                                net_profit == profit_loss - fees

Feature engineering then adds the columns that make the analysis possible:
R-multiples, realised RR, notional, fee-to-risk ratio, equity curves and
drawdown per trader, win/loss streaks, and the intraday sequence number used to
measure overtrading.

Run:  python python/data_cleaning.py
Out:  data/processed/trades_clean.csv           (trade grain)
      data/processed/daily_performance.csv      (day grain)
      data/processed/monthly_performance.csv    (month grain)
      data/processed/trader_summary.csv         (trader grain)
      data/processed/dim_calendar.csv           (date dimension)
      reports/data_quality_report.md
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    ASSETS, CLEAN_TRADES_CSV, DAILY_CSV, DIM_CALENDAR_CSV, EMOTIONS,
    MONTHLY_CSV, PROCESSED_DIR, RAW_TRADES_CSV, REPORTS_DIR, STRATEGIES,
    TRADER_CSV,
)

NUMERIC_COLS = [
    "entry_price", "exit_price", "stop_loss", "take_profit", "quantity",
    "risk_pct", "reward_pct", "profit_loss", "fees", "net_profit",
    "trade_duration_min", "account_balance", "max_drawdown_pct",
    "risk_reward_ratio",
]

# Canonical domains, keyed by the UPPER-CASED form of the incoming value.
# Driving these off config means labels containing acronyms or parentheses --
# "Order Block (SMC)", "FOMO" -- survive round-tripping, which naive
# .str.title() would mangle into "Order Block (Smc)" and "Fomo".
CANONICAL = {
    "asset": {a.upper(): a for a in ASSETS},
    "trade_type": {"BUY": "Buy", "SELL": "Sell"},
    "trading_session": {"ASIA": "Asia", "LONDON": "London", "NEW YORK": "New York"},
    "strategy": {s.upper(): s for s in STRATEGIES},
    "emotional_state": {e.upper(): e for e in EMOTIONS},
}

_log: list[str] = []


def log(msg: str) -> None:
    _log.append(msg)
    print(f"  {msg}")


# ==========================================================================
# Cleaning
# ==========================================================================
def load_raw(path: str = RAW_TRADES_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    log(f"loaded {len(df):,} raw rows x {df.shape[1]} columns")
    return df


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates()
    log(f"removed {before - len(df):,} exact duplicate rows")

    before = len(df)
    df = df.drop_duplicates(subset=["trade_id"], keep="first")
    dropped = before - len(df)
    if dropped:
        log(f"removed {dropped:,} further rows with a repeated trade_id")
    return df.reset_index(drop=True)


def coerce_numerics(df: pd.DataFrame) -> pd.DataFrame:
    """Strip thousands separators / stray symbols and cast to float."""
    fixed = 0
    for col in NUMERIC_COLS:
        raw = df[col]
        as_str = raw.astype(str)
        needs_fix = as_str.str.contains(r"[,\s$]", na=False)
        fixed += int(needs_fix.sum())
        cleaned = as_str.str.replace(r"[,\s$]", "", regex=True).replace(
            {"nan": np.nan, "None": np.nan, "": np.nan}
        )
        df[col] = pd.to_numeric(cleaned, errors="coerce")
    log(f"coerced {fixed:,} string-formatted numeric values to float")
    return df


def normalise_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    touched = 0
    text_cols = ["asset", "trade_type", "trading_session", "strategy",
                 "emotional_state", "trader_id", "trader_name", "asset_class"]
    # Identifier columns are case-significant codes, not prose — they get
    # trimmed and upper-cased but never title-cased (TR-001, not Tr-001).
    id_cols = {"trader_id"}
    for col in text_cols:
        original = df[col].copy()
        s = df[col].astype(str).str.strip()
        s = s.replace({"nan": np.nan, "None": np.nan, "": np.nan})
        if col in id_cols:
            s = s.str.upper()
        elif col in CANONICAL:
            mapper = CANONICAL[col]
            s = s.str.upper().map(mapper).fillna(s)
        else:
            # Title-case only the rows that arrived mangled; leave correct
            # multi-word labels such as "Order Block (SMC)" untouched.
            mangled = s.notna() & (s.str.isupper() | s.str.islower())
            s = s.mask(mangled, s.str.title())
        df[col] = s
        touched += int((original.astype(str) != s.astype(str)).sum())
    log(f"normalised casing/whitespace on {touched:,} categorical values")
    return df


def build_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df["exit_date_parsed"] = pd.to_datetime(df["exit_date"], errors="coerce")

    df["entry_datetime"] = pd.to_datetime(
        df["trade_date"].dt.strftime("%Y-%m-%d") + " " + df["entry_time"].astype(str),
        errors="coerce",
    )
    df["exit_datetime"] = pd.to_datetime(
        df["exit_date_parsed"].dt.strftime("%Y-%m-%d") + " " + df["exit_time"].astype(str),
        errors="coerce",
    )
    bad = int(df["entry_datetime"].isna().sum())
    if bad:
        log(f"{bad:,} rows had an unparseable entry timestamp")
    return df.drop(columns=["exit_date_parsed"])


def repair_durations(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute duration from timestamps; a negative/zero value is impossible."""
    recomputed = (df["exit_datetime"] - df["entry_datetime"]).dt.total_seconds() / 60.0

    invalid = df["trade_duration_min"].notna() & (df["trade_duration_min"] <= 0)
    n_invalid = int(invalid.sum())

    df["trade_duration_min"] = np.where(
        recomputed.notna() & (recomputed > 0), recomputed, df["trade_duration_min"]
    )
    still_bad = df["trade_duration_min"].notna() & (df["trade_duration_min"] <= 0)
    df.loc[still_bad, "trade_duration_min"] = np.nan

    log(f"repaired {n_invalid:,} impossible (<=0) trade durations from timestamps; "
        f"{int(still_bad.sum()):,} left as null")
    return df


def flag_price_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Fat-finger detection via a robust modified z-score on log(entry_price).

    A median-absolute-deviation score is used rather than a mean/std z-score
    because the contaminating values are exactly the kind of extreme outliers
    that inflate a standard deviation and hide themselves.
    """
    df["price_outlier"] = False
    for asset, grp in df.groupby("asset"):
        px = pd.to_numeric(grp["entry_price"], errors="coerce")
        lp = np.log(px.where(px > 0))
        med = lp.median()
        mad = (lp - med).abs().median()
        if not np.isfinite(mad) or mad == 0:
            continue
        score = 0.6745 * (lp - med) / mad
        # A 10x fat-finger scores around 10 against a normal price series, so
        # the cut sits at 8 — well above genuine 2.5-year price drift (< 5).
        df.loc[grp.index, "price_outlier"] = score.abs() > 8

    n = int(df["price_outlier"].sum())
    log(f"flagged {n:,} fat-finger entry prices (robust MAD z-score > 8)")
    return df, n


def handle_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split open trades out and default the optional journal fields."""
    open_mask = df["exit_price"].isna() | df["net_profit"].isna()
    open_trades = df[open_mask].copy()
    closed = df[~open_mask].copy()
    log(f"quarantined {len(open_trades):,} still-open trades (no exit recorded)")

    n_emotion = int(closed["emotional_state"].isna().sum())
    closed["emotional_state"] = closed["emotional_state"].fillna("Unspecified")
    n_notes = int(closed["trade_notes"].isna().sum())
    closed["trade_notes"] = closed["trade_notes"].fillna("")
    log(f"filled {n_emotion:,} missing emotional_state -> 'Unspecified', "
        f"{n_notes:,} missing notes -> ''")
    return closed, open_trades


def integrity_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Enforce the trade arithmetic; drop rows that cannot possibly be right."""
    recomputed_net = df["profit_loss"] - df["fees"]
    mismatch = (recomputed_net - df["net_profit"]).abs() > 0.05
    log(f"net_profit == profit_loss - fees fails on {int(mismatch.sum()):,} rows")

    # A long must have its stop below and its target above the entry (and the
    # mirror for a short). This structural invariant catches corrupted entry
    # prices that the distributional MAD test misses -- a 10x fat-finger on a
    # high-volatility asset can sit inside the distribution but still puts the
    # entry on the wrong side of its own stop.
    long = df["trade_type"].eq("Buy")
    side_ok = np.where(
        long,
        (df["stop_loss"] < df["entry_price"]) & (df["take_profit"] > df["entry_price"]),
        (df["stop_loss"] > df["entry_price"]) & (df["take_profit"] < df["entry_price"]),
    )
    bad_side = ~side_ok
    caught_only_here = int((bad_side & ~df["price_outlier"]).sum())
    log(f"stop/target on the wrong side of entry on {int(bad_side.sum()):,} rows "
        f"({caught_only_here:,} missed by the MAD test alone)")

    corrupt = df["price_outlier"] | bad_side | mismatch
    before = len(df)
    df = df[~corrupt].drop(columns=["price_outlier"]).reset_index(drop=True)
    log(f"dropped {before - len(df):,} structurally invalid rows from the "
        f"analytical table")
    return df


# ==========================================================================
# Feature engineering
# ==========================================================================
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("entry_datetime").reset_index(drop=True)

    # --- calendar -------------------------------------------------------
    d = df["trade_date"]
    df["year"] = d.dt.year
    df["quarter"] = "Q" + d.dt.quarter.astype(str)
    df["month"] = d.dt.month
    df["month_name"] = d.dt.strftime("%b")
    df["year_month"] = d.dt.strftime("%Y-%m")
    df["iso_week"] = d.dt.isocalendar().week.astype(int)
    df["year_week"] = d.dt.strftime("%G-W%V")
    df["weekday_num"] = d.dt.weekday
    df["weekday"] = d.dt.day_name()
    df["is_weekend"] = df["weekday_num"] >= 5
    df["entry_hour"] = df["entry_datetime"].dt.hour

    # --- risk / reward geometry -----------------------------------------
    df["stop_distance"] = (df["entry_price"] - df["stop_loss"]).abs()
    df["target_distance"] = (df["take_profit"] - df["entry_price"]).abs()
    df["risk_amount"] = df["stop_distance"] * df["quantity"]
    df["notional"] = df["entry_price"] * df["quantity"]

    # R-multiple: the single most useful normaliser in trading analytics —
    # it makes a $12 scalp and a $4,000 swing directly comparable.
    df["r_multiple"] = np.where(df["risk_amount"] > 0,
                                df["net_profit"] / df["risk_amount"], np.nan)

    direction = np.where(df["trade_type"].eq("Buy"), 1.0, -1.0)
    move = (df["exit_price"] - df["entry_price"]) * direction
    df["realised_rr"] = np.where(df["stop_distance"] > 0,
                                 move / df["stop_distance"], np.nan)
    df["rr_slippage"] = df["realised_rr"] - df["risk_reward_ratio"]

    df["fee_pct_of_risk"] = np.where(df["risk_amount"] > 0,
                                     df["fees"] / df["risk_amount"] * 100, np.nan)
    df["fee_bps_of_notional"] = np.where(df["notional"] > 0,
                                         df["fees"] / df["notional"] * 10_000, np.nan)

    # --- outcome flags ---------------------------------------------------
    df["is_win"] = (df["net_profit"] > 0).astype(int)
    df["win_loss"] = np.where(df["is_win"] == 1, "Win", "Loss")
    df["gross_profit"] = df["net_profit"].clip(lower=0)
    df["gross_loss"] = (-df["net_profit"]).clip(lower=0)

    # --- buckets ----------------------------------------------------------
    df["duration_bucket"] = pd.cut(
        df["trade_duration_min"],
        bins=[0, 15, 60, 240, 1_440, np.inf],
        labels=["<15m", "15-60m", "1-4h", "4-24h", ">1d"],
    ).astype(str)
    df["risk_bucket"] = pd.cut(
        df["risk_pct"],
        bins=[0, 0.5, 1.0, 2.0, 3.0, np.inf],
        labels=["<0.5%", "0.5-1%", "1-2%", "2-3%", ">3%"],
    ).astype(str)
    df["rr_bucket"] = pd.cut(
        df["risk_reward_ratio"],
        bins=[0, 1.0, 2.0, 3.0, np.inf],
        labels=["<1R", "1-2R", "2-3R", ">3R"],
    ).astype(str)
    df["session_hour_block"] = df["entry_hour"].astype(str).str.zfill(2) + ":00"

    # --- per-trader path-dependent features ------------------------------
    df["trade_seq"] = df.groupby("trader_id").cumcount() + 1
    df["trade_seq_in_day"] = df.groupby(["trader_id", "trade_date"]).cumcount() + 1
    df["trades_that_day"] = df.groupby(["trader_id", "trade_date"])["trade_id"].transform("size")
    df["is_overtrading_day"] = df["trades_that_day"] >= 6

    # Equity, running peak and drawdown, per trader.
    df["cum_pnl_trader"] = df.groupby("trader_id")["net_profit"].cumsum()
    df["equity_peak"] = df.groupby("trader_id")["account_balance"].cummax()
    df["drawdown_abs"] = df["equity_peak"] - df["account_balance"]
    df["drawdown_pct"] = np.where(df["equity_peak"] > 0,
                                  df["drawdown_abs"] / df["equity_peak"] * 100, 0.0)

    # Portfolio-level cumulative P&L (the headline equity curve).
    df["cum_pnl_portfolio"] = df["net_profit"].cumsum()

    # Streaks: consecutive wins / losses within each trader's own sequence.
    df["streak_id"] = (
        df.groupby("trader_id")["is_win"]
        .transform(lambda s: (s != s.shift()).cumsum())
    )
    run = df.groupby(["trader_id", "streak_id"]).cumcount() + 1
    df["win_streak"] = np.where(df["is_win"] == 1, run, 0)
    df["loss_streak"] = np.where(df["is_win"] == 0, run, 0)

    # Prior-trade context — the features the ML model is allowed to see.
    grp = df.groupby("trader_id")
    df["prev_result"] = grp["is_win"].shift(1)
    df["prev_r_multiple"] = grp["r_multiple"].shift(1)
    df["prev_loss_streak"] = grp["loss_streak"].shift(1).fillna(0)
    df["minutes_since_prev_exit"] = (
        (df["entry_datetime"] - grp["exit_datetime"].shift(1)).dt.total_seconds() / 60.0
    )
    # A re-entry within 10 minutes of closing a loser is the classic tilt tell.
    df["is_quick_reentry"] = (
        (df["minutes_since_prev_exit"] < 10) & (df["prev_result"] == 0)
    ).astype(int)

    df["is_tilt_state"] = df["emotional_state"].isin(["Revenge", "FOMO", "Greedy"]).astype(int)
    df["is_controlled_state"] = df["emotional_state"].isin(
        ["Disciplined", "Confident", "Neutral"]).astype(int)

    log(f"engineered {df.shape[1]} total columns on {len(df):,} clean trades")
    return df


# ==========================================================================
# Aggregate marts
# ==========================================================================
def build_daily(df: pd.DataFrame) -> pd.DataFrame:
    daily = df.groupby("trade_date").agg(
        trades=("trade_id", "size"),
        traders=("trader_id", "nunique"),
        wins=("is_win", "sum"),
        net_profit=("net_profit", "sum"),
        gross_profit=("gross_profit", "sum"),
        gross_loss=("gross_loss", "sum"),
        fees=("fees", "sum"),
        avg_r=("r_multiple", "mean"),
        avg_risk_pct=("risk_pct", "mean"),
        avg_duration_min=("trade_duration_min", "mean"),
    ).reset_index()
    daily["losses"] = daily["trades"] - daily["wins"]
    daily["win_rate"] = daily["wins"] / daily["trades"] * 100
    daily["cum_net_profit"] = daily["net_profit"].cumsum()
    daily["running_peak"] = daily["cum_net_profit"].cummax()
    daily["drawdown"] = daily["cum_net_profit"] - daily["running_peak"]
    denom = daily["running_peak"].replace(0, np.nan)
    daily["drawdown_pct"] = (daily["drawdown"] / denom * 100).fillna(0)
    daily["weekday"] = daily["trade_date"].dt.day_name()
    daily["year_month"] = daily["trade_date"].dt.strftime("%Y-%m")
    return daily


def build_monthly(df: pd.DataFrame) -> pd.DataFrame:
    m = df.groupby("year_month").agg(
        trades=("trade_id", "size"),
        wins=("is_win", "sum"),
        net_profit=("net_profit", "sum"),
        gross_profit=("gross_profit", "sum"),
        gross_loss=("gross_loss", "sum"),
        fees=("fees", "sum"),
        avg_r=("r_multiple", "mean"),
        avg_rr=("risk_reward_ratio", "mean"),
        avg_risk_pct=("risk_pct", "mean"),
    ).reset_index().sort_values("year_month")
    m["win_rate"] = m["wins"] / m["trades"] * 100
    m["profit_factor"] = m["gross_profit"] / m["gross_loss"].replace(0, np.nan)
    m["cum_net_profit"] = m["net_profit"].cumsum()
    # Month-over-month growth of the cumulative portfolio P&L.
    m["mom_growth_pct"] = m["cum_net_profit"].pct_change().replace(
        [np.inf, -np.inf], np.nan) * 100
    return m


def build_trader_summary(df: pd.DataFrame) -> pd.DataFrame:
    t = df.groupby(["trader_id", "trader_name"]).agg(
        trades=("trade_id", "size"),
        wins=("is_win", "sum"),
        net_profit=("net_profit", "sum"),
        gross_profit=("gross_profit", "sum"),
        gross_loss=("gross_loss", "sum"),
        fees=("fees", "sum"),
        avg_r=("r_multiple", "mean"),
        total_r=("r_multiple", "sum"),
        avg_rr=("risk_reward_ratio", "mean"),
        avg_risk_pct=("risk_pct", "mean"),
        max_drawdown_pct=("drawdown_pct", "max"),
        final_balance=("account_balance", "last"),
        max_win_streak=("win_streak", "max"),
        max_loss_streak=("loss_streak", "max"),
        tilt_rate=("is_tilt_state", "mean"),
        first_trade=("trade_date", "min"),
        last_trade=("trade_date", "max"),
    ).reset_index()
    t["win_rate"] = t["wins"] / t["trades"] * 100
    t["profit_factor"] = t["gross_profit"] / t["gross_loss"].replace(0, np.nan)
    t["tilt_rate"] = t["tilt_rate"] * 100
    t["expectancy_usd"] = t["net_profit"] / t["trades"]
    return t.sort_values("net_profit", ascending=False).reset_index(drop=True)


def build_calendar(df: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(df["trade_date"].min(), df["trade_date"].max(), freq="D")
    cal = pd.DataFrame({"date": dates})
    cal["year"] = cal["date"].dt.year
    cal["quarter"] = "Q" + cal["date"].dt.quarter.astype(str)
    cal["month"] = cal["date"].dt.month
    cal["month_name"] = cal["date"].dt.strftime("%b")
    cal["year_month"] = cal["date"].dt.strftime("%Y-%m")
    cal["iso_week"] = cal["date"].dt.isocalendar().week.astype(int)
    cal["year_week"] = cal["date"].dt.strftime("%G-W%V")
    cal["weekday_num"] = cal["date"].dt.weekday
    cal["weekday"] = cal["date"].dt.day_name()
    cal["is_weekend"] = cal["weekday_num"] >= 5
    return cal


# ==========================================================================
def write_quality_report(rows_raw: int, rows_clean: int, open_trades: int) -> None:
    path = os.path.join(REPORTS_DIR, "data_quality_report.md")
    with open(path, "w") as fh:
        fh.write("# Data Quality Report\n\n")
        fh.write(f"- **Raw rows ingested:** {rows_raw:,}\n")
        fh.write(f"- **Clean closed trades:** {rows_clean:,}\n")
        fh.write(f"- **Open trades quarantined:** {open_trades:,}\n\n")
        fh.write("## Cleaning log\n\n")
        for line in _log:
            fh.write(f"1. {line}\n")
        fh.write("\n## Rules applied\n\n")
        fh.write(
            "| Issue | Detection | Treatment |\n"
            "|---|---|---|\n"
            "| Duplicate submissions | exact row match, then repeated `trade_id` | drop, keep first |\n"
            "| Thousands-separated numbers | regex `[,\\s$]` in a numeric column | strip and cast to float |\n"
            "| Casing / whitespace noise | value not in the canonical domain | map to canonical label |\n"
            "| Impossible duration (<= 0) | `trade_duration_min <= 0` | recompute from timestamps, else null |\n"
            "| Fat-finger entry price | robust MAD z-score > 12 within asset | flag and exclude from analysis |\n"
            "| Open trades | `exit_price` or `net_profit` null | quarantine to a separate file |\n"
            "| Missing emotional state | null | `'Unspecified'` (kept, not dropped) |\n"
            "| Missing notes | null | empty string |\n"
        )
    print(f"  written: {path}")


def main() -> None:
    print("Cleaning raw blotter ...")
    raw = load_raw()
    rows_raw = len(raw)

    df = deduplicate(raw)
    df = coerce_numerics(df)
    df = normalise_categoricals(df)
    df = build_timestamps(df)
    df = repair_durations(df)
    df, _ = flag_price_outliers(df)
    df, open_trades = handle_missing(df)
    df = integrity_checks(df)

    print("\nEngineering features ...")
    df = engineer_features(df)

    print("\nBuilding aggregate marts ...")
    daily = build_daily(df)
    monthly = build_monthly(df)
    traders = build_trader_summary(df)
    calendar = build_calendar(df)

    df.to_csv(CLEAN_TRADES_CSV, index=False)
    daily.to_csv(DAILY_CSV, index=False)
    monthly.to_csv(MONTHLY_CSV, index=False)
    traders.to_csv(TRADER_CSV, index=False)
    calendar.to_csv(DIM_CALENDAR_CSV, index=False)
    open_trades.to_csv(os.path.join(PROCESSED_DIR, "open_trades.csv"), index=False)

    for p in (CLEAN_TRADES_CSV, DAILY_CSV, MONTHLY_CSV, TRADER_CSV, DIM_CALENDAR_CSV):
        print(f"  written: {os.path.relpath(p, os.path.dirname(PROCESSED_DIR))}")

    write_quality_report(rows_raw, len(df), len(open_trades))

    print(f"\nClean dataset: {len(df):,} trades, {df.shape[1]} columns, "
          f"{df['trade_date'].min():%Y-%m-%d} -> {df['trade_date'].max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
