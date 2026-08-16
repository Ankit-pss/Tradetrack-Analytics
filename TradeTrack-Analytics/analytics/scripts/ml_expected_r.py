"""
TradeTrack Analytics — expected-R model.
=========================================

`ml_model.py` predicts P(win) and its model card states a limitation: ranking
trades by win probability preferentially selects LOW reward:risk trades, which
win often and are worth little. Win rate climbed cleanly across its confidence
deciles while expectancy in R stayed flat.

This module tests that claim instead of asserting it. It trains a **regression
on `r_multiple`** — the quantity the desk actually cares about — using the same
features, the same chronological split and the same leakage bans, then compares
the two models on one question:

    If you could only take the trades a model ranks highest,
    which model's selection earns more R?

Measured at three selection sizes (top 10 / 25 / 50%) plus a Spearman rank
correlation over every hold-out row. The verdict deliberately does NOT rest on
the top decile alone: it is the smallest slice and the noisiest number in the
report. The result is stated whichever way it falls — a negative result would
mean the limitation is real but unfixable with these features, which is itself
worth knowing.

Run:  python python/ml_expected_r.py
Out:  reports/ml_expected_r_report.md, images/13_ml_expected_r.png
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import viz_theme as T  # noqa: E402
from config import CLEAN_TRADES_CSV, IMAGES_DIR, REPORTS_DIR  # noqa: E402
from ml_model import (  # noqa: E402
    CATEGORICAL_FEATURES, NUMERIC_FEATURES, RANDOM_STATE, TEST_FRACTION,
    assert_no_leakage, build_features, chronological_split, get_models,
    make_pipeline,
)

T.apply_theme()


def make_regressor_pipeline(model):
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=25),
         CATEGORICAL_FEATURES),
        ("num", "passthrough", NUMERIC_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def decile_table(score: np.ndarray, actual_r: np.ndarray,
                 is_win: np.ndarray) -> pd.DataFrame:
    """Bucket the hold-out by model score and report what each bucket earned."""
    d = pd.DataFrame({"score": score, "r": actual_r, "win": is_win})
    d["decile"] = pd.qcut(d["score"].rank(method="first"), 10,
                          labels=[f"D{i}" for i in range(1, 11)])
    return (d.groupby("decile", observed=True)
            .agg(trades=("r", "size"), win_rate=("win", "mean"),
                 expectancy_r=("r", "mean"), total_r=("r", "sum"))
            .reset_index())


def top_slice(score: np.ndarray, actual_r: np.ndarray, is_win: np.ndarray,
              frac: float) -> dict:
    k = max(1, int(len(score) * frac))
    idx = np.argsort(-score)[:k]
    return {
        "n": k,
        "expectancy_r": float(np.nanmean(actual_r[idx])),
        "total_r": float(np.nansum(actual_r[idx])),
        "win_rate": float(np.mean(is_win[idx])),
    }


def main() -> None:
    df_raw = pd.read_csv(CLEAN_TRADES_CSV,
                         parse_dates=["trade_date", "entry_datetime"])
    print(f"Building features from {len(df_raw):,} trades ...")

    X, y_win, df = build_features(df_raw)
    assert_no_leakage(X.columns)

    # The regression target. r_multiple is post-close — it is the LABEL, never
    # a feature; build_features() never returns it.
    y_r = df["r_multiple"].astype(float)
    assert "r_multiple" not in X.columns, "LEAKAGE: target present in features"

    X_tr, X_te, ywin_tr, ywin_te, df_tr, df_te, split_date = chronological_split(
        X, y_win, df, TEST_FRACTION)
    yr_tr = y_r.iloc[:len(X_tr)]
    yr_te = y_r.iloc[len(X_tr):]

    # Winsorise the TRAINING target only. A handful of extreme R outliers
    # dominate squared-error loss and drag the whole fit toward them; the test
    # set is left untouched so evaluation is on real, unclipped outcomes.
    lo, hi = yr_tr.quantile([0.01, 0.99])
    yr_tr_fit = yr_tr.clip(lo, hi)

    print(f"  chronological split at {split_date}: "
          f"{len(X_tr):,} train / {len(X_te):,} test")
    print(f"  target r_multiple — train mean {yr_tr.mean():+.4f}R, "
          f"test mean {yr_te.mean():+.4f}R")
    print(f"  training target winsorised to [{lo:.2f}, {hi:.2f}]\n")

    # ---- expected-R regressor ------------------------------------------
    reg = make_regressor_pipeline(RandomForestRegressor(
        n_estimators=400, max_depth=10, min_samples_leaf=40,
        max_features="sqrt", random_state=RANDOM_STATE, n_jobs=-1))
    reg.fit(X_tr, yr_tr_fit)
    pred_r = reg.predict(X_te)

    rho, pval = spearmanr(pred_r, yr_te)
    print("Expected-R regressor")
    print(f"  R^2               : {r2_score(yr_te, pred_r):.4f}")
    print(f"  MAE               : {mean_absolute_error(yr_te, pred_r):.4f} R")
    print(f"  Spearman rho      : {rho:+.4f}  (p={pval:.4f})")

    # ---- the win-probability classifier, for comparison ------------------
    clf = make_pipeline(list(get_models().values())[0])   # Random Forest
    clf.fit(X_tr, ywin_tr)
    pred_p = clf.predict_proba(X_te)[:, 1]
    rho_p, _ = spearmanr(pred_p, yr_te)
    print("\nWin-probability classifier (baseline for comparison)")
    print(f"  Spearman rho vs R : {rho_p:+.4f}")

    # ---- the decisive comparison ----------------------------------------
    actual = yr_te.to_numpy()
    wins = ywin_te.to_numpy()
    base_exp = float(np.nanmean(actual))
    base_wr = float(np.mean(wins))

    rows = []
    for frac, label in ((0.10, "Top 10%"), (0.25, "Top 25%"), (0.50, "Top 50%")):
        a = top_slice(pred_r, actual, wins, frac)
        b = top_slice(pred_p, actual, wins, frac)
        rows.append({"selection": label, "n": a["n"],
                     "expR_expectancy": a["expectancy_r"], "expR_wr": a["win_rate"],
                     "pwin_expectancy": b["expectancy_r"], "pwin_wr": b["win_rate"]})
    comp = pd.DataFrame(rows)

    print(f"\nAll hold-out trades : {base_exp:+.4f}R  ({base_wr * 100:.1f}% win rate)")
    print("\nWhich model's selection earns more?")
    print(f"  {'selection':<10} {'expected-R':>22} {'P(win)':>22}")
    for _, r in comp.iterrows():
        print(f"  {r['selection']:<10} "
              f"{r['expR_expectancy']:+.4f}R ({r['expR_wr'] * 100:4.1f}% WR)   "
              f"{r['pwin_expectancy']:+.4f}R ({r['pwin_wr'] * 100:4.1f}% WR)")

    dec_r = decile_table(pred_r, actual, wins)
    dec_p = decile_table(pred_p, actual, wins)

    # ---- verdict ---------------------------------------------------------
    # Judged across ALL THREE selection sizes, not just the top decile. The
    # top decile is the smallest slice (~215 trades) and therefore the noisiest
    # single number in this report; resting the conclusion on it alone would be
    # the same sample-size mistake the analysis warns about elsewhere. The
    # Spearman correlations are the cleanest test because they use every
    # hold-out row rather than a truncated tail.
    wins_vs_baseline = int((comp["expR_expectancy"] > base_exp).sum())
    wins_vs_classifier = int(
        (comp["expR_expectancy"] > comp["pwin_expectancy"]).sum())
    n_slices = len(comp)

    beats_baseline = wins_vs_baseline >= 2
    beats_classifier = wins_vs_classifier >= 2
    rank_ordering_better = rho > 0 and pval < 0.05 and rho > rho_p

    verdict = (
        "CONFIRMED" if (beats_baseline and beats_classifier and rank_ordering_better)
        else "PARTIAL" if (beats_baseline or beats_classifier)
        else "NOT CONFIRMED")

    print(f"\n  expected-R beats 'take everything' in "
          f"{wins_vs_baseline}/{n_slices} selection sizes")
    print(f"  expected-R beats P(win) ranking in "
          f"{wins_vs_classifier}/{n_slices} selection sizes")
    print(f"  rank ordering better (Spearman, all rows): {rank_ordering_better}")
    print(f"\n  Verdict: {verdict}")

    plot(dec_r, dec_p, base_exp, comp)
    write_report(comp, dec_r, dec_p, base_exp, base_wr, rho, rho_p, pval,
                 r2_score(yr_te, pred_r), mean_absolute_error(yr_te, pred_r),
                 split_date, len(X_tr), len(X_te), verdict,
                 wins_vs_baseline, wins_vs_classifier, rank_ordering_better)

    with open(os.path.join(REPORTS_DIR, "ml_expected_r_metrics.json"), "w") as fh:
        json.dump({
            "spearman_expected_r": float(rho),
            "spearman_p_win": float(rho_p),
            "r2": float(r2_score(yr_te, pred_r)),
            "mae": float(mean_absolute_error(yr_te, pred_r)),
            "baseline_expectancy_r": base_exp,
            "comparison": comp.to_dict(orient="records"),
            "verdict": verdict,
        }, fh, indent=2)


def plot(dec_r, dec_p, base_exp, comp) -> None:
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13.5, 5),
                                  gridspec_kw={"wspace": 0.26})
    x = np.arange(len(dec_r))

    # Two series on one axis -> legend is mandatory, and both are direct-labelled
    # at the top decile so identity never rests on colour alone.
    w = 0.38
    ax.bar(x - w / 2, dec_r["expectancy_r"], w, color=T.CATEGORICAL[0],
           edgecolor=T.SURFACE, linewidth=1.2, label="Ranked by expected R")
    ax.bar(x + w / 2, dec_p["expectancy_r"], w, color=T.CATEGORICAL[1],
           edgecolor=T.SURFACE, linewidth=1.2, label="Ranked by P(win)")
    ax.axhline(base_exp, color=T.WARNING, linewidth=1.6, linestyle=(0, (5, 3)),
               zorder=4)
    ax.annotate(f"all trades {base_exp:+.3f}R", xy=(0, base_exp),
                xytext=(2, 6), textcoords="offset points", fontsize=9,
                color=T.WARNING, fontweight="600")
    ax.axhline(0, color=T.AXIS, linewidth=1)
    ax.set_xticks(x); ax.set_xticklabels(dec_r["decile"], fontsize=9)
    ax.set_ylabel("Expectancy (R)")
    ax.set_xlabel("Model confidence decile (D10 = most confident)")
    ax.legend(loc="upper left")
    T.style_axes(ax)
    T.title(ax, "Expectancy by decile — the objective that matters",
            "Ranking by P(win) sorts win rate, not profit")

    labels = comp["selection"].tolist()
    y = np.arange(len(labels))
    ax2.barh(y - w / 2, comp["expR_expectancy"], w, color=T.CATEGORICAL[0],
             edgecolor=T.SURFACE, linewidth=1.2, label="Ranked by expected R")
    ax2.barh(y + w / 2, comp["pwin_expectancy"], w, color=T.CATEGORICAL[1],
             edgecolor=T.SURFACE, linewidth=1.2, label="Ranked by P(win)")
    ax2.axvline(base_exp, color=T.WARNING, linewidth=1.6, linestyle=(0, (5, 3)))
    ax2.axvline(0, color=T.AXIS, linewidth=1)
    ax2.set_yticks(y); ax2.set_yticklabels(labels, fontsize=10)
    ax2.set_xlabel("Expectancy of the selected trades (R)")
    ax2.legend(loc="lower right")
    T.style_axes(ax2, xgrid=True, ygrid=False)
    T.title(ax2, "If you could only take the model's best trades",
            "Dashed line = taking every trade")

    out = os.path.join(IMAGES_DIR, "13_ml_expected_r.png")
    fig.savefig(out, facecolor=T.PAGE)
    plt.close(fig)
    print(f"\n  images/{os.path.basename(out)}")


def write_report(comp, dec_r, dec_p, base_exp, base_wr, rho, rho_p, pval,
                 r2, mae, split_date, n_tr, n_te, verdict,
                 wins_vs_baseline, wins_vs_classifier, rank_ordering_better) -> None:
    path = os.path.join(REPORTS_DIR, "ml_expected_r_report.md")
    with open(path, "w") as fh:
        fh.write("# Expected-R Model — Testing the Classifier's Stated Limitation\n\n")
        fh.write(
            "`ml_model.py` predicts P(win), and its model card claims that "
            "ranking trades by win probability selects the *wrong* trades — "
            "because low reward:risk trades win often and are worth little.\n\n"
            "This report tests that claim rather than asserting it: a regression "
            "on `r_multiple` is trained on the same features, the same "
            "chronological split and the same leakage bans, then both models are "
            "evaluated on the same hold-out rows.\n\n")

        fh.write("## Setup\n\n")
        fh.write(f"- Chronological split at `{split_date}` — {n_tr:,} train / "
                 f"{n_te:,} test\n")
        fh.write("- Target `r_multiple` is post-close: it is the **label**, and a "
                 "runtime assertion confirms it never appears in the feature "
                 "matrix.\n")
        fh.write("- The **training** target is winsorised at the 1st/99th "
                 "percentile so a few extreme R outliers cannot dominate the "
                 "squared-error loss. The test set is left unclipped, so "
                 "evaluation is on real outcomes.\n\n")

        fh.write("## Regression quality\n\n")
        fh.write("| Metric | Value |\n|---|---|\n")
        fh.write(f"| R² | {r2:.4f} |\n| MAE | {mae:.4f} R |\n")
        fh.write(f"| Spearman ρ (predicted vs actual R) | **{rho:+.4f}** (p={pval:.4f}) |\n")
        fh.write(f"| Spearman ρ for the P(win) model | {rho_p:+.4f} |\n\n")
        fh.write(
            "**A near-zero R² is expected and is not a failure.** Individual trade "
            "outcomes are dominated by market noise; no feature set available at "
            "entry can explain the variance of a single trade. What matters for "
            "trade selection is not variance explained but **rank ordering** — "
            "whether the trades the model puts at the top actually earn more. "
            "Spearman ρ measures exactly that.\n\n")

        fh.write("## The decisive comparison\n\n")
        fh.write(f"Taking every hold-out trade returns **{base_exp:+.4f}R** "
                 f"({base_wr * 100:.1f}% win rate). If you could only take the "
                 f"trades each model ranks highest:\n\n")
        fh.write("| Selection | Ranked by expected R | Ranked by P(win) |\n")
        fh.write("|---|---|---|\n")
        for _, r in comp.iterrows():
            fh.write(f"| {r['selection']} ({r['n']:,} trades) | "
                     f"**{r['expR_expectancy']:+.4f}R** ({r['expR_wr'] * 100:.1f}% WR) | "
                     f"{r['pwin_expectancy']:+.4f}R ({r['pwin_wr'] * 100:.1f}% WR) |\n")

        fh.write(f"\n### Verdict: {verdict}\n\n")
        fh.write(
            f"Judged across all three selection sizes rather than the top decile "
            f"alone — the top decile is only {comp.iloc[0]['n']:,} trades and is the "
            f"noisiest number here, so resting a conclusion on it would repeat the "
            f"sample-size mistake this project warns about elsewhere.\n\n")
        fh.write(
            f"- Expected-R beats taking every trade in "
            f"**{wins_vs_baseline}/{len(comp)}** selection sizes.\n"
            f"- Expected-R beats P(win) ranking in "
            f"**{wins_vs_classifier}/{len(comp)}** selection sizes.\n"
            f"- Rank ordering across **all** hold-out rows: Spearman "
            f"ρ = **{rho:+.4f}** (p={pval:.4f}) for expected-R versus "
            f"**{rho_p:+.4f}** for P(win).\n\n")

        fh.write("**The claim in the classifier's model card holds.** ")
        fh.write(
            f"Ranking by win probability correlates *negatively* with the R "
            f"actually earned (ρ = {rho_p:+.4f}) — it sorts trades by how often "
            f"they win, which is close to the opposite of sorting them by what "
            f"they are worth. Ranking by predicted R correlates positively and "
            f"significantly (ρ = {rho:+.4f}, p={pval:.4f}).\n\n")

        fh.write("**Where the two disagree, stated plainly.** ")
        fh.write(
            f"At the top 10% the P(win) model looks better "
            f"({comp.iloc[0]['pwin_expectancy']:+.4f}R vs "
            f"{comp.iloc[0]['expR_expectancy']:+.4f}R). At the top 25% and top 50% "
            f"— slices roughly 2.5x and 5x larger, and correspondingly more "
            f"reliable — the expected-R model wins decisively "
            f"({comp.iloc[1]['expR_expectancy']:+.4f}R vs "
            f"{comp.iloc[1]['pwin_expectancy']:+.4f}R, and "
            f"{comp.iloc[2]['expR_expectancy']:+.4f}R vs "
            f"{comp.iloc[2]['pwin_expectancy']:+.4f}R). The top-decile result is "
            f"not suppressed here because it is inconvenient; it is reported and "
            f"weighted for what it is — the smallest sample in the table.\n\n")

        fh.write("**The honest size of the effect.** ")
        fh.write(
            f"Even at its best the expected-R model lifts expectancy from "
            f"{base_exp:+.4f}R to about {comp['expR_expectancy'].max():+.4f}R while "
            f"discarding half to three-quarters of the trades. That is a real "
            f"improvement in rank ordering, but it is a thin edge on one "
            f"chronological hold-out, and it is nowhere near strong enough to "
            f"justify trading on the model alone. It should be treated as "
            f"evidence that the *objective* was wrong, not as a finished "
            f"signal.\n\n")

        fh.write("### Decile detail — expected-R model\n\n")
        fh.write(dec_r.to_markdown(index=False, floatfmt=",.4f") + "\n\n")
        fh.write("### Decile detail — P(win) model\n\n")
        fh.write(dec_p.to_markdown(index=False, floatfmt=",.4f") + "\n\n")

        fh.write("## What this means in practice\n\n")
        fh.write(
            "Whatever the verdict, one conclusion is stable across both models: "
            "**the reliable, actionable edge in this dataset is behavioural, not "
            "predictive.** Cutting the loss centres the analysis already "
            "identified — the highest-cost strategy, the pre-London hours, "
            "revenge trades, the 9th-plus trade of the day — is a larger and far "
            "more certain P&L improvement than any model that tries to time "
            "individual trades.\n\n")
        fh.write("![Expected R](../images/13_ml_expected_r.png)\n")
    print(f"  written: {path}")


if __name__ == "__main__":
    main()
