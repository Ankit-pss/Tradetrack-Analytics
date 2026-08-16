"""
TradeTrack Analytics — visualisation suite.
============================================

Renders the full chart deck as static PNGs (for the README, the notebook and
the PDF-style report) plus interactive Plotly HTML for the dashboard.

Chart forms are chosen by the job the data does, not by habit:
  * change over time      -> line (equity curve, cumulative P&L)
  * magnitude comparison  -> horizontal bars, sorted by value
  * polarity              -> diverging bars off a zero baseline
  * distribution          -> histogram with reference lines
  * two-dimension density -> heatmap on a single sequential ramp
  * correlation           -> diverging matrix with a neutral grey midpoint

Run:  python python/visualizations.py
Out:  images/*.png, dashboard/charts/*.html
"""
from __future__ import annotations

import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import viz_theme as T  # noqa: E402
from config import CLEAN_TRADES_CSV, DASHBOARD_DIR, IMAGES_DIR, TRADERS  # noqa: E402

STARTING_CAPITAL = float(sum(t["start_balance"] for t in TRADERS))
CHART_HTML_DIR = os.path.join(DASHBOARD_DIR, "charts")
os.makedirs(CHART_HTML_DIR, exist_ok=True)

T.apply_theme()


def save(fig, name: str) -> None:
    path = os.path.join(IMAGES_DIR, f"{name}.png")
    fig.savefig(path, facecolor=T.PAGE)
    plt.close(fig)
    print(f"  {os.path.relpath(path, os.path.dirname(IMAGES_DIR))}")


# ==========================================================================
# 1. Equity curve + drawdown
# ==========================================================================
def chart_equity_curve(df: pd.DataFrame) -> None:
    daily = df.groupby("trade_date")["net_profit"].sum().sort_index()
    equity = STARTING_CAPITAL + daily.cumsum()
    peak = equity.cummax()
    dd_pct = (equity - peak) / peak * 100

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(12, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.12})

    ax.plot(equity.index, equity.values, color=T.CATEGORICAL[0], linewidth=2.0,
            zorder=3, label="Desk equity")
    ax.fill_between(equity.index, STARTING_CAPITAL, equity.values,
                    where=equity.values >= STARTING_CAPITAL,
                    color=T.PROFIT, alpha=0.10, zorder=2)
    ax.fill_between(equity.index, STARTING_CAPITAL, equity.values,
                    where=equity.values < STARTING_CAPITAL,
                    color=T.LOSS, alpha=0.10, zorder=2)
    ax.axhline(STARTING_CAPITAL, color=T.TEXT_MUTED, linewidth=1.0,
               linestyle=(0, (4, 4)), zorder=1)

    # Direct-label the end point rather than every point.
    ax.annotate(f"{T.money(equity.iloc[-1])}",
                xy=(equity.index[-1], equity.iloc[-1]),
                xytext=(-6, 10), textcoords="offset points",
                color=T.TEXT_PRIMARY, fontsize=11, fontweight="600", ha="right")
    ax.text(equity.index[0], STARTING_CAPITAL, f" opening capital {T.money(STARTING_CAPITAL)}",
            va="bottom", ha="left", fontsize=8.5, color=T.TEXT_MUTED)

    # Mark the account blow-ups. The desk's improving curve is substantially a
    # survivorship effect -- losing traders stop trading -- and a reader who is
    # not told that will misread the second half as the desk getting better.
    last_trade = df.groupby("trader_id")["trade_date"].max()
    exits = last_trade[last_trade < df["trade_date"].max() - pd.Timedelta(days=30)]
    for exit_date in exits.sort_values():
        ax.axvline(exit_date, color=T.WARNING, linewidth=1.0, alpha=0.45,
                   linestyle=(0, (2, 3)), zorder=1)
    if len(exits):
        ax.annotate(f"↑ {len(exits)} accounts blown\n(12 → {df['trader_id'].nunique() - len(exits)} active)",
                    xy=(exits.iloc[len(exits) // 2], equity.min()),
                    xytext=(6, 12), textcoords="offset points",
                    fontsize=8.5, color=T.WARNING, va="bottom")

    ax.yaxis.set_major_formatter(lambda v, _: T.money(v))
    T.style_axes(ax)
    T.title(ax, "Desk equity curve",
            f"{len(df):,} closed trades · {df['trade_date'].min():%b %Y} – "
            f"{df['trade_date'].max():%b %Y} · net {T.money(df['net_profit'].sum())}")

    ax2.fill_between(dd_pct.index, 0, dd_pct.values, color=T.LOSS, alpha=0.28)
    ax2.plot(dd_pct.index, dd_pct.values, color=T.LOSS, linewidth=1.2)
    worst = dd_pct.idxmin()
    ax2.annotate(f"max drawdown {dd_pct.min():.1f}%",
                 xy=(worst, dd_pct.min()), xytext=(10, -4),
                 textcoords="offset points", fontsize=9, color=T.TEXT_SECONDARY)
    ax2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax2.set_ylabel("Drawdown", color=T.TEXT_MUTED, fontsize=9)
    T.style_axes(ax2)
    save(fig, "01_equity_curve")


# ==========================================================================
# 2. Monthly profit
# ==========================================================================
def chart_monthly_profit(df: pd.DataFrame) -> None:
    m = df.groupby("year_month")["net_profit"].sum()
    fig, ax = plt.subplots(figsize=(12, 5))
    x = np.arange(len(m))
    T.rounded_bars(ax, x, m.values, T.pnl_colors(m.values), width=0.62)

    ax.set_xticks(x)
    ax.set_xticklabels([pd.Period(i).strftime("%b\n%y") for i in m.index], fontsize=8)
    ax.set_xlim(-0.8, len(m) - 0.2)
    ax.axhline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax.yaxis.set_major_formatter(lambda v, _: T.money(v))

    best, worst = m.idxmax(), m.idxmin()
    for label, colour in ((best, T.PROFIT), (worst, T.LOSS)):
        i = list(m.index).index(label)
        ax.annotate(T.money(m[label]), xy=(i, m[label]),
                    xytext=(0, 6 if m[label] >= 0 else -16),
                    textcoords="offset points", ha="center", fontsize=9,
                    color=colour, fontweight="600")

    pos, neg = int((m > 0).sum()), int((m <= 0).sum())
    T.style_axes(ax)
    T.title(ax, "Monthly net P&L",
            f"{pos} profitable months vs {neg} losing · green = profit, red = loss")
    save(fig, "02_monthly_profit")


# ==========================================================================
# 3. Win / loss distribution
# ==========================================================================
def chart_win_loss(df: pd.DataFrame) -> None:
    g = (df.groupby("strategy")
           .agg(wins=("is_win", "sum"), trades=("is_win", "size"))
           .assign(losses=lambda d: d["trades"] - d["wins"],
                   win_rate=lambda d: d["wins"] / d["trades"] * 100)
           .sort_values("win_rate"))

    fig, ax = plt.subplots(figsize=(11, 5.5))
    y = np.arange(len(g))
    h = 0.62
    # Stacked composition; the 1.2pt surface edge gives the 2px segment gap.
    ax.barh(y, g["wins"], height=h, color=T.PROFIT, edgecolor=T.SURFACE,
            linewidth=1.2, label="Wins", zorder=3)
    ax.barh(y, g["losses"], left=g["wins"], height=h, color=T.LOSS,
            edgecolor=T.SURFACE, linewidth=1.2, label="Losses", zorder=3)

    for i, (_, row) in enumerate(g.iterrows()):
        ax.text(row["trades"] + 30, i, f"{row['win_rate']:.1f}%",
                va="center", fontsize=9.5, color=T.TEXT_PRIMARY, fontweight="600")

    ax.set_yticks(y)
    ax.set_yticklabels(g.index, fontsize=10, color=T.TEXT_SECONDARY)
    ax.set_xlim(0, g["trades"].max() * 1.16)
    T.style_axes(ax, xgrid=True, ygrid=False)
    ax.legend(loc="lower right", ncol=2)
    T.title(ax, "Win / loss composition by strategy",
            "Bar length = trade count · label = win rate. "
            "A high win rate is not the same as a profitable strategy.")
    save(fig, "03_win_loss_distribution")


# ==========================================================================
# 4. Profit histogram (R-multiples)
# ==========================================================================
def chart_profit_histogram(df: pd.DataFrame) -> None:
    r = df["r_multiple"].clip(-3, 6)
    fig, ax = plt.subplots(figsize=(11, 5.5))

    bins = np.linspace(-3, 6, 61)
    counts, edges = np.histogram(r, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    colors = [T.PROFIT if c > 0 else T.LOSS for c in centers]
    ax.bar(centers, counts, width=(edges[1] - edges[0]) * 0.86, color=colors,
           edgecolor=T.SURFACE, linewidth=0.6, zorder=3)

    ax.axvline(0, color=T.TEXT_MUTED, linewidth=1.0, zorder=4)
    mean_r = df["r_multiple"].mean()
    ax.axvline(mean_r, color=T.CATEGORICAL[0], linewidth=1.8,
               linestyle=(0, (5, 3)), zorder=5)
    ax.annotate(f"mean {mean_r:+.3f}R", xy=(mean_r, counts.max() * 0.92),
                xytext=(8, 0), textcoords="offset points", fontsize=9.5,
                color=T.CATEGORICAL[0], fontweight="600")
    ax.axvline(-1, color=T.WARNING, linewidth=1.4, linestyle=(0, (3, 3)), zorder=4)
    ax.annotate("−1R\n(stop honoured)", xy=(-1, counts.max() * 0.55),
                xytext=(-64, 0), textcoords="offset points", fontsize=8.5,
                color=T.WARNING, ha="left")

    ax.set_xlabel("R-multiple  (net P&L ÷ dollars risked)")
    ax.set_ylabel("Trades")
    T.style_axes(ax)
    T.title(ax, "Distribution of trade outcomes in R",
            "The spike at −1R is stops working as designed; the right tail is "
            "where the entire edge lives.")
    save(fig, "04_profit_histogram")


# ==========================================================================
# 5. Risk distribution
# ==========================================================================
def chart_risk_distribution(df: pd.DataFrame) -> None:
    order = ["<0.5%", "0.5-1%", "1-2%", "2-3%", ">3%"]
    g = (df.groupby("risk_bucket")
           .agg(trades=("trade_id", "size"), expectancy_r=("r_multiple", "mean"),
                net=("net_profit", "sum"))
           .reindex(order).dropna())

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.5, 5),
                                  gridspec_kw={"wspace": 0.28})
    x = np.arange(len(g))
    T.rounded_bars(ax, x, g["trades"].values,
                   [T.CATEGORICAL[0]] * len(g), width=0.62)
    ax.set_xticks(x); ax.set_xticklabels(g.index, fontsize=9.5)
    ax.set_ylabel("Trades")
    for i, v in enumerate(g["trades"].values):
        ax.text(i, v, f"{int(v):,}", ha="center", va="bottom", fontsize=9,
                color=T.TEXT_SECONDARY)
    T.style_axes(ax)
    T.title(ax, "How much is risked per trade", "Position-size discipline")

    T.rounded_bars(ax2, x, g["expectancy_r"].values,
                   T.pnl_colors(g["expectancy_r"].values), width=0.62)
    ax2.set_xticks(x); ax2.set_xticklabels(g.index, fontsize=9.5)
    ax2.axhline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax2.set_ylabel("Expectancy (R)")
    for i, v in enumerate(g["expectancy_r"].values):
        ax2.text(i, v, f"{v:+.3f}", ha="center",
                 va="bottom" if v >= 0 else "top", fontsize=9,
                 color=T.TEXT_SECONDARY)
    T.style_axes(ax2)
    T.title(ax2, "…and what it returns", "Expectancy per trade by risk band")
    save(fig, "05_risk_distribution")


# ==========================================================================
# 6. Asset performance
# ==========================================================================
def chart_asset_performance(df: pd.DataFrame) -> None:
    g = (df.groupby("asset")
           .agg(net=("net_profit", "sum"), trades=("trade_id", "size"),
                exp_r=("r_multiple", "mean"), wr=("is_win", "mean"))
           .sort_values("net"))

    fig, ax = plt.subplots(figsize=(11, 5.5))
    y = np.arange(len(g))
    T.rounded_bars(ax, y, g["net"].values, T.pnl_colors(g["net"].values),
                   width=0.6, horizontal=True)

    for i, (asset, row) in enumerate(g.iterrows()):
        offset = 8 if row["net"] >= 0 else -8
        ax.annotate(T.money(row["net"]), xy=(row["net"], i),
                    xytext=(offset, 0), textcoords="offset points",
                    va="center", ha="left" if row["net"] >= 0 else "right",
                    fontsize=9.5, color=T.TEXT_PRIMARY, fontweight="600")

    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{a}   ({int(r.trades):,} trades · {r.wr * 100:.0f}% WR)"
         for a, r in g.iterrows()], fontsize=9.5, color=T.TEXT_SECONDARY)
    ax.axvline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax.xaxis.set_major_formatter(lambda v, _: T.money(v))
    pad = max(abs(g["net"].min()), abs(g["net"].max())) * 0.22
    ax.set_xlim(g["net"].min() - pad, g["net"].max() + pad)
    T.style_axes(ax, xgrid=True, ygrid=False)
    T.title(ax, "Net P&L by instrument", "After fees · green = profit, red = loss")
    save(fig, "06_asset_performance")


# ==========================================================================
# 7. Strategy performance
# ==========================================================================
def chart_strategy_performance(df: pd.DataFrame) -> None:
    g = (df.groupby("strategy")
           .agg(net=("net_profit", "sum"), trades=("trade_id", "size"),
                exp_r=("r_multiple", "mean"), fees=("fees", "sum"))
           .sort_values("exp_r"))

    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    y = np.arange(len(g))
    T.rounded_bars(ax, y, g["exp_r"].values, T.pnl_colors(g["exp_r"].values),
                   width=0.6, horizontal=True)

    for i, (_, row) in enumerate(g.iterrows()):
        offset = 8 if row["exp_r"] >= 0 else -8
        ax.annotate(f"{row['exp_r']:+.3f}R   ({T.money(row['net'])})",
                    xy=(row["exp_r"], i), xytext=(offset, 0),
                    textcoords="offset points", va="center",
                    ha="left" if row["exp_r"] >= 0 else "right",
                    fontsize=9.5, color=T.TEXT_PRIMARY, fontweight="600")

    ax.set_yticks(y)
    ax.set_yticklabels([f"{s}   ({int(r.trades):,})" for s, r in g.iterrows()],
                       fontsize=9.5, color=T.TEXT_SECONDARY)
    ax.axvline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax.set_xlabel("Expectancy per trade (R)")
    pad = max(abs(g["exp_r"].min()), abs(g["exp_r"].max())) * 0.75
    ax.set_xlim(g["exp_r"].min() - pad, g["exp_r"].max() + pad)
    T.style_axes(ax, xgrid=True, ygrid=False)
    T.title(ax, "Strategy scorecard, ranked by expectancy in R",
            "R-normalised so a scalp and a swing are judged on the same scale")
    save(fig, "07_strategy_performance")


# ==========================================================================
# 8. Session analysis
# ==========================================================================
def chart_session_analysis(df: pd.DataFrame) -> None:
    g = (df.groupby("trading_session")
           .agg(net=("net_profit", "sum"), trades=("trade_id", "size"),
                exp_r=("r_multiple", "mean"), wr=("is_win", "mean"))
           .reindex(["Asia", "London", "New York"]))
    hourly = (df.groupby("entry_hour")
                .agg(net=("net_profit", "sum"), trades=("trade_id", "size")))

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5),
                                  gridspec_kw={"width_ratios": [1, 1.5], "wspace": 0.24})
    x = np.arange(len(g))
    T.rounded_bars(ax, x, g["net"].values, T.pnl_colors(g["net"].values), width=0.58)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s}\n{int(r.trades):,} trades · {r.wr * 100:.1f}% WR"
                        for s, r in g.iterrows()], fontsize=9)
    ax.axhline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax.yaxis.set_major_formatter(lambda v, _: T.money(v))
    for i, v in enumerate(g["net"].values):
        ax.text(i, v, T.money(v), ha="center", va="bottom" if v >= 0 else "top",
                fontsize=9.5, color=T.TEXT_PRIMARY, fontweight="600")
    T.style_axes(ax)
    T.title(ax, "Net P&L by session", "UTC session windows")

    hx = hourly.index.values
    T.rounded_bars(ax2, hx, hourly["net"].values,
                   T.pnl_colors(hourly["net"].values), width=0.7)
    ax2.axhline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax2.set_xticks(range(0, 24, 2))
    ax2.set_xlabel("Entry hour (UTC)")
    ax2.yaxis.set_major_formatter(lambda v, _: T.money(v))
    for lo, hi, name in ((0, 8, "Asia"), (8, 13, "London"), (13, 24, "New York")):
        ax2.axvspan(lo - 0.5, hi - 0.5, color=T.CATEGORICAL[0], alpha=0.045, zorder=0)
        ax2.text((lo + hi) / 2 - 0.5, ax2.get_ylim()[1] * 0.93, name,
                 ha="center", fontsize=8.5, color=T.TEXT_MUTED)
    T.style_axes(ax2)
    T.title(ax2, "…and by hour of day", "Where inside each session the money is made")
    save(fig, "08_session_analysis")


# ==========================================================================
# 9. Weekday x hour heatmap
# ==========================================================================
def chart_weekday_heatmap(df: pd.DataFrame) -> None:
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday", "Sunday"]
    pivot = (df.pivot_table(index="weekday", columns="entry_hour",
                            values="net_profit", aggfunc="sum")
               .reindex(order).fillna(0))

    hours = list(pivot.columns)
    fig, ax = plt.subplots(figsize=(13, 4.6))
    # Clip the scale at the 97.5th percentile of |value|: a couple of extreme
    # cells would otherwise flatten every other cell to the neutral midpoint
    # and hide the pattern the chart exists to show.
    lim = float(np.percentile(np.abs(pivot.values), 97.5)) or 1.0
    im = ax.imshow(pivot.values, cmap=T.CMAP_DIV, vmin=-lim, vmax=lim,
                   aspect="auto", interpolation="nearest")

    # Ticks must come from the data's own hour range -- the desk does not trade
    # 21:00-24:00 UTC, and padding the axis to 24 draws empty columns.
    ax.set_xticks(range(len(hours)))
    ax.set_xticklabels(hours, fontsize=8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=9.5, color=T.TEXT_SECONDARY)
    ax.set_xlabel("Entry hour (UTC)")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    # Thin surface gridlines separate the cells (the 2px fill gap).
    ax.set_xticks(np.arange(-0.5, len(hours), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(order), 1), minor=True)
    ax.grid(which="minor", color=T.SURFACE, linewidth=1.4)
    ax.tick_params(which="minor", length=0)

    cb = fig.colorbar(im, ax=ax, pad=0.015, fraction=0.026)
    cb.set_label("Net P&L", color=T.TEXT_MUTED, fontsize=9)
    cb.ax.yaxis.set_major_formatter(lambda v, _: T.money(v))
    cb.ax.tick_params(colors=T.TEXT_MUTED, labelsize=8, length=0)
    cb.outline.set_visible(False)

    T.title(ax, "Profit heatmap — weekday x hour of day",
            "Diverging scale, neutral grey at zero · blue = profit, red = loss")
    save(fig, "09_weekday_heatmap")


# ==========================================================================
# 10. Correlation matrix
# ==========================================================================
def chart_correlation(df: pd.DataFrame) -> None:
    cols = {
        "net_profit": "Net P&L",
        "r_multiple": "R-multiple",
        "risk_pct": "Risk %",
        "risk_reward_ratio": "Planned RR",
        "realised_rr": "Realised RR",
        "trade_duration_min": "Duration",
        "quantity": "Quantity",
        "fees": "Fees",
        "trades_that_day": "Trades that day",
        "prev_loss_streak": "Prior loss streak",
        "is_tilt_state": "Tilt state",
        "is_win": "Win",
    }
    corr = df[list(cols)].corr(numeric_only=True).rename(index=cols, columns=cols)

    fig, ax = plt.subplots(figsize=(9.5, 8))
    im = ax.imshow(corr.values, cmap=T.CMAP_DIV, vmin=-1, vmax=1)
    n = len(corr)
    ax.set_xticks(range(n)); ax.set_xticklabels(corr.columns, rotation=45,
                                                ha="right", fontsize=9)
    ax.set_yticks(range(n)); ax.set_yticklabels(corr.index, fontsize=9)
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks(np.arange(-0.5, n, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n, 1), minor=True)
    ax.grid(which="minor", color=T.SURFACE, linewidth=1.4)
    ax.tick_params(which="minor", length=0)

    # Label only the meaningful cells — a number in every cell is unreadable.
    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            if i != j and abs(v) >= 0.25:
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8.5,
                        color=T.TEXT_PRIMARY, fontweight="600")

    cb = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.036)
    cb.set_label("Pearson r", color=T.TEXT_MUTED, fontsize=9)
    cb.ax.tick_params(colors=T.TEXT_MUTED, labelsize=8, length=0)
    cb.outline.set_visible(False)

    T.title(ax, "Correlation matrix of trade attributes",
            "Cells labelled where |r| >= 0.25 · diverging scale, grey at zero")
    save(fig, "10_correlation_matrix")


# ==========================================================================
# 11. Trading psychology (bonus — the dataset's most distinctive finding)
# ==========================================================================
def chart_psychology(df: pd.DataFrame) -> None:
    g = (df[df["emotional_state"] != "Unspecified"]
         .groupby("emotional_state")
         .agg(exp_r=("r_multiple", "mean"), risk=("risk_pct", "mean"),
              trades=("trade_id", "size"), wr=("is_win", "mean"))
         .sort_values("exp_r"))

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5.2),
                                  gridspec_kw={"wspace": 0.30})
    y = np.arange(len(g))
    T.rounded_bars(ax, y, g["exp_r"].values, T.pnl_colors(g["exp_r"].values),
                   width=0.6, horizontal=True)
    ax.set_yticks(y); ax.set_yticklabels(
        [f"{e}  ({int(r.trades):,})" for e, r in g.iterrows()],
        fontsize=9.5, color=T.TEXT_SECONDARY)
    ax.axvline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax.set_xlabel("Expectancy per trade (R)")
    for i, v in enumerate(g["exp_r"].values):
        ax.annotate(f"{v:+.3f}", xy=(v, i), xytext=(8 if v >= 0 else -8, 0),
                    textcoords="offset points", va="center",
                    ha="left" if v >= 0 else "right", fontsize=9.5,
                    color=T.TEXT_PRIMARY, fontweight="600")
    pad = max(abs(g["exp_r"].min()), abs(g["exp_r"].max())) * 0.6
    ax.set_xlim(g["exp_r"].min() - pad, g["exp_r"].max() + pad)
    T.style_axes(ax, xgrid=True, ygrid=False)
    T.title(ax, "Expectancy by emotional state", "Self-reported at trade entry")

    T.rounded_bars(ax2, y, g["risk"].values, [T.WARNING] * len(g),
                   width=0.6, horizontal=True)
    ax2.set_yticks(y); ax2.set_yticklabels(g.index, fontsize=9.5,
                                           color=T.TEXT_SECONDARY)
    ax2.set_xlabel("Average risk per trade (% of equity)")
    for i, v in enumerate(g["risk"].values):
        ax2.annotate(f"{v:.2f}%", xy=(v, i), xytext=(8, 0),
                     textcoords="offset points", va="center", fontsize=9.5,
                     color=T.TEXT_PRIMARY, fontweight="600")
    ax2.set_xlim(0, g["risk"].max() * 1.25)
    T.style_axes(ax2, xgrid=True, ygrid=False)
    T.title(ax2, "…and the risk taken in that state",
            "The worst states are also the largest-sized")
    save(fig, "11_psychology")


# ==========================================================================
# Interactive Plotly exports for the dashboard
# ==========================================================================
def plotly_exports(df: pd.DataFrame) -> None:
    import plotly.graph_objects as go

    daily = df.groupby("trade_date")["net_profit"].sum().sort_index()
    equity = STARTING_CAPITAL + daily.cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity.index, y=equity.values, mode="lines", name="Desk equity",
        line=dict(color=T.CATEGORICAL[0], width=2),
        fill="tozeroy", fillcolor="rgba(57,135,229,0.10)",
        hovertemplate="%{x|%d %b %Y}<br><b>$%{y:,.0f}</b><extra></extra>"))
    fig.add_hline(y=STARTING_CAPITAL, line=dict(color=T.TEXT_MUTED, width=1, dash="dash"))
    fig.update_layout(**T.plotly_layout(
        "Desk equity curve",
        f"{len(df):,} closed trades · net {T.money(df['net_profit'].sum())}"))
    fig.update_yaxes(range=[equity.min() * 0.97, equity.max() * 1.02])
    fig.update_layout(hovermode="x unified")
    out = os.path.join(CHART_HTML_DIR, "equity_curve.html")
    fig.write_html(out, include_plotlyjs="cdn", full_html=True)
    print(f"  {os.path.relpath(out, DASHBOARD_DIR)}")

    m = df.groupby("year_month")["net_profit"].sum()
    fig2 = go.Figure(go.Bar(
        x=list(m.index), y=m.values,
        marker=dict(color=T.pnl_colors(m.values),
                    line=dict(color=T.SURFACE, width=1.2)),
        hovertemplate="%{x}<br><b>$%{y:,.0f}</b><extra></extra>"))
    fig2.update_layout(**T.plotly_layout("Monthly net P&L", "After fees"))
    out2 = os.path.join(CHART_HTML_DIR, "monthly_profit.html")
    fig2.write_html(out2, include_plotlyjs="cdn", full_html=True)
    print(f"  {os.path.relpath(out2, DASHBOARD_DIR)}")


def main() -> None:
    df = pd.read_csv(CLEAN_TRADES_CSV, parse_dates=["trade_date", "entry_datetime"])
    print(f"Rendering chart deck from {len(df):,} trades ...\n")
    chart_equity_curve(df)
    chart_monthly_profit(df)
    chart_win_loss(df)
    chart_profit_histogram(df)
    chart_risk_distribution(df)
    chart_asset_performance(df)
    chart_strategy_performance(df)
    chart_session_analysis(df)
    chart_weekday_heatmap(df)
    chart_correlation(df)
    chart_psychology(df)
    print("\nInteractive exports ...")
    plotly_exports(df)
    print("\ndone")


if __name__ == "__main__":
    main()
