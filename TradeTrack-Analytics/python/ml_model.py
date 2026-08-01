"""
TradeTrack Analytics — trade-outcome classifier.
=================================================

Question: given only what is knowable at the MOMENT OF ENTRY, can we predict
whether a trade will close profitably?

Two things make or break this model, and both are handled explicitly:

1. LEAKAGE. Most of the columns in the blotter are recorded when the trade
   CLOSES: net_profit, r_multiple, realised_rr, duration, fees, the running
   equity and drawdown, the current win/loss streak. Feeding any of them to the
   model produces a 99% accuracy score and a worthless model. Only the
   `SAFE_FEATURES` list below is used, and `assert_no_leakage()` fails the run
   if a banned column ever reaches the feature matrix.

   `account_balance` is a subtle case: it is the balance AFTER the trade
   settled, so it is shifted one trade back per trader to recover the balance
   the trader actually had on entry.

2. SPLIT. A random split lets the model learn from the future. The split here
   is CHRONOLOGICAL — train on the first 80% of the timeline, test on the last
   20% — which is the only honest evaluation for a time-ordered process.

Evaluation is framed against the two baselines that matter:
  * majority-class accuracy (always predict "Loss") — 65% here, so raw
    accuracy is a misleading headline;
  * the base win rate — the model is only useful if the trades it flags win
    MORE often than an unfiltered trade does, and if the R-expectancy of the
    filtered subset beats the unfiltered one.

Run:  python python/ml_model.py
Out:  reports/ml_model_report.md, images/12_ml_*.png
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score, brier_score_loss, classification_report, confusion_matrix,
    f1_score, precision_score, recall_score, roc_auc_score, roc_curve,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import viz_theme as T  # noqa: E402
from config import CLEAN_TRADES_CSV, IMAGES_DIR, REPORTS_DIR  # noqa: E402

T.apply_theme()

RANDOM_STATE = 42
TEST_FRACTION = 0.20

# --------------------------------------------------------------------------
# Feature contract
# --------------------------------------------------------------------------
CATEGORICAL_FEATURES = [
    "trader_id", "asset", "asset_class", "strategy", "trading_session",
    "trade_type", "emotional_state", "weekday", "risk_bucket", "rr_bucket",
]

NUMERIC_FEATURES = [
    "entry_hour", "weekday_num", "risk_pct", "risk_reward_ratio",
    "reward_pct", "trade_seq_in_day", "prev_result", "prev_r_multiple",
    "prev_loss_streak", "minutes_since_prev_exit", "is_quick_reentry",
    "is_tilt_state", "is_controlled_state", "opening_balance",
    "risk_amount_at_entry", "stop_distance_pct",
]

# Anything recorded at or after the close. If one of these reaches the model,
# the run is invalid — hence the hard assertion rather than a comment.
LEAKY_COLUMNS = {
    "net_profit", "profit_loss", "fees", "gross_profit", "gross_loss",
    "r_multiple", "realised_rr", "rr_slippage", "exit_price", "exit_time",
    "exit_date", "exit_datetime", "trade_duration_min", "duration_bucket",
    "win_loss", "is_win", "win_streak", "loss_streak", "streak_id",
    "account_balance", "equity_peak", "drawdown_abs", "drawdown_pct",
    "cum_pnl_trader", "cum_pnl_portfolio", "max_drawdown_pct",
    "fee_pct_of_risk", "fee_bps_of_notional", "trades_that_day",
    "is_overtrading_day", "trade_notes",
}


def assert_no_leakage(columns) -> None:
    leaked = LEAKY_COLUMNS.intersection(columns)
    if leaked:
        raise AssertionError(
            f"LEAKAGE: post-close columns reached the feature matrix: {sorted(leaked)}"
        )


# --------------------------------------------------------------------------
def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    df = df.sort_values("entry_datetime").reset_index(drop=True)
    g = df.groupby("trader_id")

    # account_balance is post-trade -> shift to recover the entry-time balance.
    df["opening_balance"] = g["account_balance"].shift(1)
    df["opening_balance"] = df["opening_balance"].fillna(
        df["account_balance"] - df["net_profit"])

    # Dollars risked, expressed from entry-time information only.
    df["risk_amount_at_entry"] = df["opening_balance"] * df["risk_pct"] / 100.0
    # Stop width as a % of entry price — a pure entry-time quantity.
    df["stop_distance_pct"] = df["stop_distance"] / df["entry_price"] * 100

    features = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    assert_no_leakage(features)

    X = df[features].copy()
    for col in NUMERIC_FEATURES:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    # First trade per trader has no predecessor; a neutral fill keeps the row.
    X[NUMERIC_FEATURES] = X[NUMERIC_FEATURES].fillna(X[NUMERIC_FEATURES].median())
    X[CATEGORICAL_FEATURES] = X[CATEGORICAL_FEATURES].astype(str)

    y = df["is_win"].astype(int)
    return X, y, df


def chronological_split(X, y, df, test_fraction=TEST_FRACTION):
    """Train on the past, test on the future. Never a random split."""
    cut = int(len(X) * (1 - test_fraction))
    split_date = df["entry_datetime"].iloc[cut]
    return (X.iloc[:cut], X.iloc[cut:], y.iloc[:cut], y.iloc[cut:],
            df.iloc[:cut], df.iloc[cut:], split_date)


def make_pipeline(model):
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=25),
         CATEGORICAL_FEATURES),
        ("num", "passthrough", NUMERIC_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def get_models() -> dict:
    """Random Forest plus a gradient-booster.

    XGBoost is used when its native library loads (it needs OpenMP, which is
    not present on every machine); scikit-learn's GradientBoostingClassifier is
    the drop-in fallback so the project runs anywhere.
    """
    models = {
        "Random Forest": RandomForestClassifier(
            n_estimators=400, max_depth=12, min_samples_leaf=25,
            max_features="sqrt", class_weight="balanced_subsample",
            random_state=RANDOM_STATE, n_jobs=-1),
    }
    try:
        from xgboost import XGBClassifier
        models["XGBoost"] = XGBClassifier(
            n_estimators=400, max_depth=5, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85, reg_lambda=2.0,
            eval_metric="logloss", random_state=RANDOM_STATE, n_jobs=-1)
        print("  gradient booster: XGBoost")
    except Exception as exc:                                   # noqa: BLE001
        models["Gradient Boosting"] = GradientBoostingClassifier(
            n_estimators=300, max_depth=3, learning_rate=0.05,
            subsample=0.85, random_state=RANDOM_STATE)
        print(f"  gradient booster: sklearn GradientBoosting "
              f"(XGBoost unavailable: {type(exc).__name__})")
    return models


# --------------------------------------------------------------------------
def evaluate(name, pipe, X_te, y_te, df_te) -> dict:
    pred = pipe.predict(X_te)
    proba = pipe.predict_proba(X_te)[:, 1]

    cm = confusion_matrix(y_te, pred)
    majority = float(max(y_te.mean(), 1 - y_te.mean()))

    # Business framing: take only the trades the model likes most and measure
    # what that filter would have done to the desk's expectancy.
    r_te = df_te["r_multiple"].to_numpy()
    order = np.argsort(-proba)
    top_decile = order[: max(1, len(order) // 10)]
    top_quartile = order[: max(1, len(order) // 4)]
    flagged = proba >= 0.5

    return {
        "model": name,
        "accuracy": float(accuracy_score(y_te, pred)),
        "majority_baseline": majority,
        "precision_win": float(precision_score(y_te, pred, zero_division=0)),
        "recall_win": float(recall_score(y_te, pred, zero_division=0)),
        "f1_win": float(f1_score(y_te, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_te, proba)),
        "brier": float(brier_score_loss(y_te, proba)),
        "base_win_rate": float(y_te.mean()),
        "confusion_matrix": cm.tolist(),
        "report": classification_report(y_te, pred, target_names=["Loss", "Win"],
                                        zero_division=0),
        "proba": proba,
        "pred": pred,
        "expectancy_all_r": float(np.nanmean(r_te)),
        "expectancy_flagged_r": float(np.nanmean(r_te[flagged])) if flagged.any() else float("nan"),
        "expectancy_top_decile_r": float(np.nanmean(r_te[top_decile])),
        "expectancy_top_quartile_r": float(np.nanmean(r_te[top_quartile])),
        "win_rate_top_decile": float(y_te.to_numpy()[top_decile].mean()),
        "win_rate_top_quartile": float(y_te.to_numpy()[top_quartile].mean()),
        "n_flagged": int(flagged.sum()),
        "n_test": int(len(y_te)),
    }


def feature_names(pipe) -> list[str]:
    pre = pipe.named_steps["pre"]
    cat = pre.named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES)
    return list(cat) + NUMERIC_FEATURES


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def plot_confusion(res: dict, name: str) -> None:
    cm = np.array(res["confusion_matrix"])
    cm_pct = cm / cm.sum() * 100

    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    ax.imshow(cm_pct, cmap=T.CMAP_SEQ, vmin=0, vmax=cm_pct.max())
    labels = ["Loss", "Win"]
    ax.set_xticks([0, 1]); ax.set_xticklabels([f"Predicted\n{l}" for l in labels])
    ax.set_yticks([0, 1]); ax.set_yticklabels([f"Actual\n{l}" for l in labels])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks([-0.5, 0.5, 1.5], minor=True)
    ax.set_yticks([-0.5, 0.5, 1.5], minor=True)
    ax.grid(which="minor", color=T.SURFACE, linewidth=2.0)
    ax.tick_params(which="minor", length=0)

    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]:,}\n{cm_pct[i, j]:.1f}%", ha="center",
                    va="center", fontsize=13, fontweight="600",
                    color=T.TEXT_PRIMARY if cm_pct[i, j] < cm_pct.max() * 0.6
                    else "#0b0e13")

    T.title(ax, f"Confusion matrix — {name}",
            f"Hold-out set · n={res['n_test']:,} · accuracy {res['accuracy'] * 100:.1f}% "
            f"vs {res['majority_baseline'] * 100:.1f}% majority baseline")
    fig.savefig(os.path.join(IMAGES_DIR, "12_ml_confusion_matrix.png"),
                facecolor=T.PAGE)
    plt.close(fig)


def plot_importance(pipe, X_te, y_te, name: str, top_n: int = 18) -> pd.DataFrame:
    """Permutation importance — measured on the HOLD-OUT set.

    Tree `feature_importances_` is impurity-based and inflates high-cardinality
    features; permutation importance on unseen data measures what the feature
    is actually worth predictively.
    """
    perm = permutation_importance(pipe, X_te, y_te, n_repeats=8,
                                  random_state=RANDOM_STATE, n_jobs=-1,
                                  scoring="roc_auc")
    imp = (pd.DataFrame({"feature": X_te.columns,
                         "importance": perm.importances_mean,
                         "std": perm.importances_std})
           .sort_values("importance", ascending=False))

    top = imp.head(top_n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(top))
    colors = [T.CATEGORICAL[0] if v > 0 else T.TEXT_MUTED for v in top["importance"]]
    T.rounded_bars(ax, y, top["importance"].values, colors, width=0.62,
                   horizontal=True)
    ax.errorbar(top["importance"], y, xerr=top["std"], fmt="none",
                ecolor=T.TEXT_MUTED, elinewidth=1.0, capsize=2.5, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(top["feature"], fontsize=9, color=T.TEXT_SECONDARY)
    ax.axvline(0, color=T.AXIS, linewidth=1.0)
    ax.set_xlabel("Drop in ROC-AUC when the feature is shuffled")
    T.style_axes(ax, xgrid=True, ygrid=False)
    T.title(ax, f"What actually predicts a winning trade — {name}",
            "Permutation importance on the hold-out set (not impurity importance)")
    fig.savefig(os.path.join(IMAGES_DIR, "12_ml_feature_importance.png"),
                facecolor=T.PAGE)
    plt.close(fig)
    return imp


def plot_lift(res: dict, y_te, df_te, name: str) -> pd.DataFrame:
    """Decile lift — the chart that answers 'is this model worth money?'."""
    d = pd.DataFrame({"proba": res["proba"], "is_win": y_te.to_numpy(),
                      "r": df_te["r_multiple"].to_numpy()})
    d["decile"] = pd.qcut(d["proba"].rank(method="first"), 10,
                          labels=[f"D{i}" for i in range(1, 11)])
    g = d.groupby("decile", observed=True).agg(
        trades=("is_win", "size"), win_rate=("is_win", "mean"),
        expectancy_r=("r", "mean")).reset_index()

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"wspace": 0.26})
    x = np.arange(len(g))
    base = float(y_te.mean())

    T.rounded_bars(ax, x, g["win_rate"].values * 100,
                   [T.PROFIT if v > base else T.CATEGORICAL[0]
                    for v in g["win_rate"]], width=0.64)
    ax.axhline(base * 100, color=T.WARNING, linewidth=1.6, linestyle=(0, (5, 3)),
               zorder=4)
    ax.annotate(f"base win rate {base * 100:.1f}%", xy=(0, base * 100),
                xytext=(2, 6), textcoords="offset points", fontsize=9,
                color=T.WARNING, fontweight="600")
    ax.set_xticks(x); ax.set_xticklabels(g["decile"], fontsize=9)
    ax.set_ylabel("Win rate (%)")
    ax.set_xlabel("Model confidence decile (D10 = most confident)")
    T.style_axes(ax)
    T.title(ax, "Win rate by model-confidence decile", "Hold-out set")

    T.rounded_bars(ax2, x, g["expectancy_r"].values,
                   T.pnl_colors(g["expectancy_r"].values), width=0.64)
    ax2.axhline(0, color=T.AXIS, linewidth=1.0, zorder=2)
    ax2.set_xticks(x); ax2.set_xticklabels(g["decile"], fontsize=9)
    ax2.set_ylabel("Expectancy (R)")
    ax2.set_xlabel("Model confidence decile")
    T.style_axes(ax2)
    T.title(ax2, "…and expectancy in R",
            "The business test: does trading only the top deciles pay?")
    fig.savefig(os.path.join(IMAGES_DIR, "12_ml_decile_lift.png"), facecolor=T.PAGE)
    plt.close(fig)
    return g


def plot_roc(results: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 6))
    for i, (name, res) in enumerate(results.items()):
        fpr, tpr, _ = roc_curve(res["_y_true"], res["proba"])
        ax.plot(fpr, tpr, color=T.CATEGORICAL[i], linewidth=2,
                label=f"{name}  (AUC {res['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], color=T.TEXT_MUTED, linewidth=1.2,
            linestyle=(0, (4, 4)), label="No skill (AUC 0.500)")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.legend(loc="lower right")
    T.style_axes(ax, xgrid=True)
    T.title(ax, "ROC — predicting a profitable trade at entry",
            "Chronological hold-out set")
    fig.savefig(os.path.join(IMAGES_DIR, "12_ml_roc_curve.png"), facecolor=T.PAGE)
    plt.close(fig)


# --------------------------------------------------------------------------
def write_report(results: dict, best_name: str, imp: pd.DataFrame,
                 lift: pd.DataFrame, split_date, n_train, n_test) -> None:
    best = results[best_name]
    path = os.path.join(REPORTS_DIR, "ml_model_report.md")
    with open(path, "w") as fh:
        fh.write("# Machine Learning — Trade Outcome Classifier\n\n")
        fh.write("## Problem\n\n"
                 "Binary classification: will this trade close profitably (net of fees), "
                 "using only information available **at the moment of entry**?\n\n")

        fh.write("## Guardrails\n\n")
        fh.write(f"- **Chronological split** at `{split_date}` — "
                 f"{n_train:,} train / {n_test:,} test. A random split would let the "
                 "model learn from the future.\n")
        fh.write(f"- **{len(LEAKY_COLUMNS)} post-close columns are hard-banned** "
                 "(`net_profit`, `r_multiple`, `trade_duration_min`, the running "
                 "streaks and equity columns, …). A runtime assertion fails the "
                 "build if any of them reaches the feature matrix.\n")
        fh.write("- `account_balance` is shifted one trade back per trader, because "
                 "the stored value is the balance *after* the trade settled.\n\n")

        fh.write("## Results\n\n")
        fh.write("| Model | Accuracy | Majority baseline | Precision (Win) | "
                 "Recall (Win) | F1 (Win) | ROC-AUC | Brier |\n")
        fh.write("|---|---|---|---|---|---|---|---|\n")
        for name, r in results.items():
            fh.write(f"| {name} | {r['accuracy']:.3f} | {r['majority_baseline']:.3f} | "
                     f"{r['precision_win']:.3f} | {r['recall_win']:.3f} | "
                     f"{r['f1_win']:.3f} | {r['roc_auc']:.3f} | {r['brier']:.4f} |\n")

        fh.write(f"\n### Confusion matrix — {best_name}\n\n")
        cm = np.array(best["confusion_matrix"])
        fh.write("| | Predicted Loss | Predicted Win |\n|---|---|---|\n")
        fh.write(f"| **Actual Loss** | {cm[0, 0]:,} | {cm[0, 1]:,} |\n")
        fh.write(f"| **Actual Win**  | {cm[1, 0]:,} | {cm[1, 1]:,} |\n\n")
        fh.write("```\n" + best["report"] + "```\n\n")

        fh.write("## Reading the accuracy number honestly\n\n")
        fh.write(
            f"Only {best['base_win_rate'] * 100:.1f}% of hold-out trades are winners, so a "
            f"model that predicts \"Loss\" every time scores "
            f"{best['majority_baseline'] * 100:.1f}% accuracy while being useless. "
            f"The measures that matter are ROC-AUC ({best['roc_auc']:.3f}, where 0.5 is "
            f"a coin flip) and whether the flagged trades actually earn more.\n\n")

        fh.write("### Does the model make money?\n\n")
        fh.write("| Trade selection | Win rate | Expectancy (R) |\n|---|---|---|\n")
        fh.write(f"| All hold-out trades | {best['base_win_rate'] * 100:.2f}% | "
                 f"{best['expectancy_all_r']:+.4f} |\n")
        fh.write(f"| Top confidence quartile | {best['win_rate_top_quartile'] * 100:.2f}% | "
                 f"{best['expectancy_top_quartile_r']:+.4f} |\n")
        fh.write(f"| Top confidence decile | {best['win_rate_top_decile'] * 100:.2f}% | "
                 f"{best['expectancy_top_decile_r']:+.4f} |\n\n")

        fh.write("### Decile lift\n\n")
        fh.write(lift.to_markdown(index=False, floatfmt=",.4f") + "\n\n")

        fh.write("## Top predictive features\n\n")
        fh.write("Permutation importance on the hold-out set (drop in ROC-AUC when "
                 "the column is shuffled):\n\n")
        fh.write(imp.head(15).to_markdown(index=False, floatfmt=",.5f") + "\n\n")

        fh.write("## Interpretation\n\n")
        fh.write(
            "The signal the model finds is **behavioural and structural, not "
            "predictive of the market**: planned reward:risk (which mechanically sets "
            "the hit rate), the trader's own identity, emotional state at entry, "
            "session and the tilt indicators. That is the correct result — the edge "
            "in a trading journal lives in execution discipline, not in forecasting "
            "price. A model claiming to forecast the market from a blotter would be "
            "a leakage bug, not a discovery.\n\n")

        fh.write("### The important caveat: win rate is not the objective\n\n")
        d1, d10 = lift.iloc[0], lift.iloc[-1]
        fh.write(
            f"Win rate climbs cleanly across the confidence deciles "
            f"({d1['win_rate'] * 100:.1f}% in D1 to {d10['win_rate'] * 100:.1f}% in D10), "
            "but **expectancy in R does not climb with it** — the decile table above "
            "is close to flat, and some high-confidence deciles are negative.\n\n"
            "That is not a broken model, it is the model correctly learning an "
            "identity we already proved in SQL: a trade with a near-1:1 target hits "
            "far more often than a 4:1 target, and it is also worth far less when it "
            "does. Ranking trades by *probability of winning* therefore preferentially "
            "selects low-RR trades, whose expectancy is poor once fees are paid.\n\n"
            "**Consequence for deployment:** this classifier should not be used as a "
            "trade filter on its own. The correct target is expected R — a regression "
            "on `r_multiple`, or a classifier on `r_multiple > 0` weighted by the R "
            "actually earned. That is the first item in Future Improvements, and it is "
            "the difference between a model that looks good on a slide and one that "
            "makes money.\n\n")
        fh.write("![Confusion matrix](../images/12_ml_confusion_matrix.png)\n\n")
        fh.write("![Feature importance](../images/12_ml_feature_importance.png)\n\n")
        fh.write("![Decile lift](../images/12_ml_decile_lift.png)\n\n")
        fh.write("![ROC curve](../images/12_ml_roc_curve.png)\n")
    print(f"\n  written: {path}")


def main() -> None:
    df = pd.read_csv(CLEAN_TRADES_CSV, parse_dates=["trade_date", "entry_datetime"])
    print(f"Building leakage-safe feature matrix from {len(df):,} trades ...")
    X, y, df = build_features(df)
    print(f"  {X.shape[1]} raw features "
          f"({len(CATEGORICAL_FEATURES)} categorical, {len(NUMERIC_FEATURES)} numeric)")
    print(f"  banned post-close columns: {len(LEAKY_COLUMNS)} — leakage check passed")

    X_tr, X_te, y_tr, y_te, df_tr, df_te, split_date = chronological_split(X, y, df)
    print(f"  chronological split at {split_date}: "
          f"{len(X_tr):,} train / {len(X_te):,} test")
    print(f"  train win rate {y_tr.mean() * 100:.2f}% · "
          f"test win rate {y_te.mean() * 100:.2f}%\n")

    results = {}
    for name, model in get_models().items():
        pipe = make_pipeline(model)
        pipe.fit(X_tr, y_tr)
        res = evaluate(name, pipe, X_te, y_te, df_te)
        res["_pipe"] = pipe
        res["_y_true"] = y_te
        results[name] = res
        print(f"  {name:<20} acc {res['accuracy']:.3f} | AUC {res['roc_auc']:.3f} | "
              f"F1(win) {res['f1_win']:.3f} | top-decile WR "
              f"{res['win_rate_top_decile'] * 100:.1f}%")

    best_name = max(results, key=lambda n: results[n]["roc_auc"])
    best = results[best_name]
    print(f"\n  best by ROC-AUC: {best_name}")

    print("\nRendering diagnostics ...")
    plot_confusion(best, best_name)
    imp = plot_importance(best["_pipe"], X_te, y_te, best_name)
    lift = plot_lift(best, y_te, df_te, best_name)
    plot_roc(results)
    for f in ("12_ml_confusion_matrix", "12_ml_feature_importance",
              "12_ml_decile_lift", "12_ml_roc_curve"):
        print(f"  images/{f}.png")

    write_report(results, best_name, imp, lift, split_date, len(X_tr), len(X_te))

    with open(os.path.join(REPORTS_DIR, "ml_metrics.json"), "w") as fh:
        json.dump({n: {k: v for k, v in r.items() if not k.startswith("_")
                       and k not in ("proba", "pred")}
                   for n, r in results.items()}, fh, indent=2, default=str)


if __name__ == "__main__":
    main()
