"""
TradeTrack Analytics — KPI & risk-metric engine.
=================================================

Every headline number the dashboard, the report and the notebook quote is
computed here, once, so the layers cannot disagree with each other.

Metric definitions used throughout (stated explicitly because trading metrics
are defined inconsistently in the wild):

  Win rate        wins / closed trades. A trade is a win if NET profit
                  (after fees) is positive — fees are part of the outcome.
  Profit factor   gross profit / gross loss. > 1 means the winners pay for
                  the losers. Below ~1.2 the edge is inside the noise.
  Expectancy      mean net P&L per trade, also reported in R (risk units) so
                  a $12 scalp and a $4,000 swing are comparable.
  R-multiple      net P&L / dollars risked on that trade (|entry - stop| x qty).
  Max drawdown    largest peak-to-trough fall of the cumulative equity curve,
                  in both dollars and % of the running peak.
  Sharpe          annualised (mean daily return - daily risk-free) / stdev of
                  daily returns, x sqrt(252). Daily return is the portfolio's
                  net P&L for the day over the combined opening capital.
  Sortino         as Sharpe but the denominator is downside deviation only,
                  which is the honest measure for an asymmetric P&L stream.
  Calmar          annualised return / max drawdown %.
  Recovery factor net profit / max drawdown $ — how many drawdowns of the
                  worst size the strategy earned back.

Run:  python python/kpi_engine.py
Out:  reports/kpi_summary.json
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    CLEAN_TRADES_CSV, KPI_JSON, RISK_FREE_RATE, TRADERS,
    TRADING_DAYS_PER_YEAR,
)

STARTING_CAPITAL = float(sum(t["start_balance"] for t in TRADERS))


# ==========================================================================
def load_clean(path: str = CLEAN_TRADES_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["trade_date", "entry_datetime", "exit_datetime"])
    return df


# ==========================================================================
# Core building blocks
# ==========================================================================
def win_rate(df: pd.DataFrame) -> float:
    return float(df["is_win"].mean() * 100) if len(df) else 0.0


def profit_factor(df: pd.DataFrame) -> float:
    gross_profit = df.loc[df["net_profit"] > 0, "net_profit"].sum()
    gross_loss = -df.loc[df["net_profit"] < 0, "net_profit"].sum()
    return float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")


def expectancy(df: pd.DataFrame) -> dict:
    wins = df.loc[df["is_win"] == 1, "net_profit"]
    losses = df.loc[df["is_win"] == 0, "net_profit"]
    wr = df["is_win"].mean()
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    return {
        "expectancy_usd": float(df["net_profit"].mean()),
        "expectancy_r": float(df["r_multiple"].mean()),
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        # The classic formulation, kept as a cross-check on the simple mean.
        "expectancy_formula": float(wr * avg_win + (1 - wr) * avg_loss),
    }


def equity_curve(df: pd.DataFrame, starting_capital: float | None = None) -> pd.DataFrame:
    """Portfolio equity curve at DAILY grain.

    Daily is the reporting convention for drawdown, and it is deliberately the
    same grain the SQL query (`16_highest_drawdown`) and the dashboard use.
    Computing this on the raw trade sequence instead would report a different,
    larger figure — intraday swings between trades create peaks and troughs
    that never existed as a marked-to-market equity value — and the three
    layers of the project would then disagree with each other.
    """
    capital = STARTING_CAPITAL if starting_capital is None else starting_capital
    daily = df.groupby("trade_date")["net_profit"].sum().sort_index()
    e = daily.rename("net_profit").to_frame()
    e["cum_pnl"] = e["net_profit"].cumsum()
    e["equity"] = capital + e["cum_pnl"]
    e["peak"] = e["equity"].cummax()
    e["drawdown_usd"] = e["equity"] - e["peak"]
    e["drawdown_pct"] = e["drawdown_usd"] / e["peak"] * 100
    return e.reset_index()


def max_drawdown(df: pd.DataFrame, starting_capital: float | None = None) -> dict:
    """Deepest peak-to-trough decline, selected on PERCENTAGE not dollars.

    Selecting on dollars biases the answer toward whenever equity happened to
    be largest; percentage of the running peak is the scale-free measure and is
    what a risk committee actually asks for.
    """
    e = equity_curve(df, starting_capital)
    i = int(e["drawdown_pct"].idxmin())
    trough_row = e.loc[i]
    peak_idx = int(e.loc[:i, "equity"].idxmax())
    return {
        "max_drawdown_usd": float(-trough_row["drawdown_usd"]),
        "max_drawdown_pct": float(-trough_row["drawdown_pct"]),
        "peak_date": str(pd.Timestamp(e.loc[peak_idx, "trade_date"]).date()),
        "trough_date": str(pd.Timestamp(trough_row["trade_date"]).date()),
        "peak_equity": float(e.loc[peak_idx, "equity"]),
        "trough_equity": float(trough_row["equity"]),
    }


def daily_returns(df: pd.DataFrame, starting_capital: float | None = None) -> pd.Series:
    """Daily portfolio return = net P&L that day / combined opening capital."""
    capital = STARTING_CAPITAL if starting_capital is None else starting_capital
    daily_pnl = df.groupby("trade_date")["net_profit"].sum()
    full = pd.date_range(daily_pnl.index.min(), daily_pnl.index.max(), freq="D")
    daily_pnl = daily_pnl.reindex(full, fill_value=0.0)
    # Only days the desk actually traded count toward the risk statistics.
    traded = df.groupby("trade_date").size().reindex(full, fill_value=0) > 0
    return (daily_pnl[traded] / capital).astype(float)


def sharpe_ratio(df: pd.DataFrame, starting_capital: float | None = None) -> float:
    r = daily_returns(df, starting_capital)
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    rf_daily = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
    return float((r.mean() - rf_daily) / r.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(df: pd.DataFrame, starting_capital: float | None = None) -> float:
    r = daily_returns(df, starting_capital)
    rf_daily = RISK_FREE_RATE / TRADING_DAYS_PER_YEAR
    downside = r[r < rf_daily] - rf_daily
    dd = np.sqrt((downside ** 2).mean()) if len(downside) else 0.0
    if dd == 0:
        return 0.0
    return float((r.mean() - rf_daily) / dd * np.sqrt(TRADING_DAYS_PER_YEAR))


def longest_streaks(df: pd.DataFrame) -> dict:
    """Longest consecutive win / loss runs, computed within each trader.

    Streaks are per-trader by definition: interleaving twelve traders'
    trades into one sequence would manufacture streaks nobody actually had.
    """
    best_win = {"trader_id": None, "length": 0}
    best_loss = {"trader_id": None, "length": 0}
    for tid, grp in df.sort_values("entry_datetime").groupby("trader_id"):
        s = grp["is_win"].to_numpy()
        run_id = np.r_[0, np.cumsum(s[1:] != s[:-1])]
        runs = pd.Series(s).groupby(run_id).agg(["first", "size"])
        w = runs.loc[runs["first"] == 1, "size"]
        l = runs.loc[runs["first"] == 0, "size"]
        if len(w) and int(w.max()) > best_win["length"]:
            best_win = {"trader_id": tid, "length": int(w.max())}
        if len(l) and int(l.max()) > best_loss["length"]:
            best_loss = {"trader_id": tid, "length": int(l.max())}
    return {"longest_win_streak": best_win, "longest_loss_streak": best_loss}


def breakdown(df: pd.DataFrame, dim: str) -> pd.DataFrame:
    """Standard performance table for any categorical dimension."""
    out = df.groupby(dim).agg(
        trades=("trade_id", "size"),
        wins=("is_win", "sum"),
        net_profit=("net_profit", "sum"),
        gross_profit=("gross_profit", "sum"),
        gross_loss=("gross_loss", "sum"),
        fees=("fees", "sum"),
        avg_r=("r_multiple", "mean"),
        avg_rr=("risk_reward_ratio", "mean"),
        avg_risk_pct=("risk_pct", "mean"),
        avg_duration_min=("trade_duration_min", "mean"),
    ).reset_index()
    out["win_rate"] = out["wins"] / out["trades"] * 100
    out["profit_factor"] = out["gross_profit"] / out["gross_loss"].replace(0, np.nan)
    out["expectancy_usd"] = out["net_profit"] / out["trades"]
    return out.sort_values("net_profit", ascending=False).reset_index(drop=True)


# ==========================================================================
def compute_all(df: pd.DataFrame, starting_capital: float | None = None) -> dict:
    capital = STARTING_CAPITAL if starting_capital is None else starting_capital
    exp = expectancy(df)
    dd = max_drawdown(df, capital)
    streaks = longest_streaks(df)

    daily = df.groupby("trade_date")["net_profit"].sum().sort_values()
    n_days = int(df["trade_date"].nunique())
    span_days = (df["trade_date"].max() - df["trade_date"].min()).days
    years = max(span_days / 365.25, 1e-9)

    net = float(df["net_profit"].sum())
    total_return_pct = net / capital * 100
    cagr = ((capital + net) / capital) ** (1 / years) - 1

    by_asset = breakdown(df, "asset")
    by_strategy = breakdown(df, "strategy")
    by_session = breakdown(df, "trading_session")
    by_weekday = breakdown(df, "weekday")
    by_emotion = breakdown(df, "emotional_state")

    kpis = {
        "meta": {
            "start_date": str(df["trade_date"].min().date()),
            "end_date": str(df["trade_date"].max().date()),
            "trading_days": n_days,
            "traders": int(df["trader_id"].nunique()),
            "starting_capital": capital,
            "assets": sorted(df["asset"].unique().tolist()),
            "strategies": sorted(df["strategy"].unique().tolist()),
        },
        "headline": {
            "total_trades": int(len(df)),
            "gross_profit_usd": float(df["profit_loss"].sum()),
            "total_fees_usd": float(df["fees"].sum()),
            "net_profit_usd": net,
            "total_return_pct": float(total_return_pct),
            "cagr_pct": float(cagr * 100),
            "win_rate_pct": win_rate(df),
            "wins": int(df["is_win"].sum()),
            "losses": int((1 - df["is_win"]).sum()),
            "profit_factor": profit_factor(df),
            "avg_rr_planned": float(df["risk_reward_ratio"].mean()),
            "avg_rr_realised": float(df["realised_rr"].mean()),
            "avg_risk_pct": float(df["risk_pct"].mean()),
            "avg_trade_duration_min": float(df["trade_duration_min"].mean()),
            "median_trade_duration_min": float(df["trade_duration_min"].median()),
            **exp,
        },
        "risk": {
            **dd,
            "sharpe_ratio": sharpe_ratio(df, capital),
            "sortino_ratio": sortino_ratio(df, capital),
            "calmar_ratio": float(cagr * 100 / dd["max_drawdown_pct"])
            if dd["max_drawdown_pct"] > 0 else 0.0,
            "recovery_factor": float(net / dd["max_drawdown_usd"])
            if dd["max_drawdown_usd"] > 0 else 0.0,
            "largest_win_usd": float(df["net_profit"].max()),
            "largest_loss_usd": float(df["net_profit"].min()),
            "worst_trade_r": float(df["r_multiple"].min()),
            "best_trade_r": float(df["r_multiple"].max()),
            "daily_volatility_pct": float(daily_returns(df, capital).std(ddof=1) * 100),
            **streaks,
        },
        "best_worst": {
            "best_day": {"date": str(daily.index[-1].date()), "net_profit": float(daily.iloc[-1])},
            "worst_day": {"date": str(daily.index[0].date()), "net_profit": float(daily.iloc[0])},
            "best_asset": {"asset": by_asset.iloc[0]["asset"],
                           "net_profit": float(by_asset.iloc[0]["net_profit"])},
            "worst_asset": {"asset": by_asset.iloc[-1]["asset"],
                            "net_profit": float(by_asset.iloc[-1]["net_profit"])},
            "best_strategy": {"strategy": by_strategy.iloc[0]["strategy"],
                              "net_profit": float(by_strategy.iloc[0]["net_profit"])},
            "worst_strategy": {"strategy": by_strategy.iloc[-1]["strategy"],
                               "net_profit": float(by_strategy.iloc[-1]["net_profit"])},
            "best_session": {"session": by_session.iloc[0]["trading_session"],
                             "net_profit": float(by_session.iloc[0]["net_profit"])},
            "worst_session": {"session": by_session.iloc[-1]["trading_session"],
                              "net_profit": float(by_session.iloc[-1]["net_profit"])},
            "best_weekday": {"weekday": by_weekday.iloc[0]["weekday"],
                             "net_profit": float(by_weekday.iloc[0]["net_profit"])},
            "worst_weekday": {"weekday": by_weekday.iloc[-1]["weekday"],
                              "net_profit": float(by_weekday.iloc[-1]["net_profit"])},
        },
        "breakdowns": {
            "by_asset": by_asset.round(4).to_dict(orient="records"),
            "by_strategy": by_strategy.round(4).to_dict(orient="records"),
            "by_session": by_session.round(4).to_dict(orient="records"),
            "by_weekday": by_weekday.round(4).to_dict(orient="records"),
            "by_emotion": by_emotion.round(4).to_dict(orient="records"),
        },
    }
    return kpis


def print_summary(k: dict) -> None:
    h, r = k["headline"], k["risk"]
    print("\n" + "=" * 62)
    print(" TRADETRACK ANALYTICS — PORTFOLIO KPI SUMMARY")
    print("=" * 62)
    print(f" Period              : {k['meta']['start_date']} -> {k['meta']['end_date']}")
    print(f" Traders / trades    : {k['meta']['traders']} / {h['total_trades']:,}")
    print(f" Starting capital    : ${k['meta']['starting_capital']:,.0f}")
    print("-" * 62)
    print(f" Gross P&L           : ${h['gross_profit_usd']:>14,.2f}")
    print(f" Fees                : ${-h['total_fees_usd']:>14,.2f}")
    print(f" NET P&L             : ${h['net_profit_usd']:>14,.2f}  ({h['total_return_pct']:+.2f}%)")
    print(f" CAGR                : {h['cagr_pct']:>15.2f}%")
    print("-" * 62)
    print(f" Win rate            : {h['win_rate_pct']:>15.2f}%  ({h['wins']:,}W / {h['losses']:,}L)")
    print(f" Profit factor       : {h['profit_factor']:>15.3f}")
    print(f" Expectancy          : ${h['expectancy_usd']:>14,.2f} / trade  ({h['expectancy_r']:+.3f} R)")
    print(f" Avg win / avg loss  : ${h['avg_win_usd']:>14,.2f} / ${h['avg_loss_usd']:,.2f}")
    print(f" Avg RR planned/real : {h['avg_rr_planned']:>15.2f} / {h['avg_rr_realised']:.2f}")
    print(f" Avg risk per trade  : {h['avg_risk_pct']:>15.2f}%")
    print(f" Avg trade duration  : {h['avg_trade_duration_min']:>15.1f} min "
          f"(median {h['median_trade_duration_min']:.0f})")
    print("-" * 62)
    print(f" Max drawdown        : ${r['max_drawdown_usd']:>14,.2f}  ({r['max_drawdown_pct']:.2f}%)")
    print(f"   peak -> trough    : {r['peak_date']} -> {r['trough_date']}")
    print(f" Sharpe / Sortino    : {r['sharpe_ratio']:>15.2f} / {r['sortino_ratio']:.2f}")
    print(f" Calmar / Recovery   : {r['calmar_ratio']:>15.2f} / {r['recovery_factor']:.2f}")
    print(f" Longest win streak  : {r['longest_win_streak']['length']:>15} "
          f"({r['longest_win_streak']['trader_id']})")
    print(f" Longest loss streak : {r['longest_loss_streak']['length']:>15} "
          f"({r['longest_loss_streak']['trader_id']})")
    print("=" * 62)


def main() -> None:
    df = load_clean()
    kpis = compute_all(df)
    with open(KPI_JSON, "w") as fh:
        json.dump(kpis, fh, indent=2, default=str)
    print_summary(kpis)
    print(f"\nwritten: {KPI_JSON}")


if __name__ == "__main__":
    main()
