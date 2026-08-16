# Machine Learning

## Problem Definition

**Question:** Can we predict whether a trade will close profitably using only information available at entry time?

**Why it matters:**
- Traders enter hundreds of trades per year
- Each decision point (enter/add/reduce/exit) has incomplete information
- A model that predicts close profitably at entry enables:
  - Risk assessment for new positions
  - Position sizing adjustments
  - Trade routing to better setups
  - Objective scoring for strategy evaluation

---

## Model Design

### Objective: Classification

**Target:** Binary — does this trade close with `net_profit > 0`?

```python
y_true = (trades['net_profit'] > 0).astype(int)  # 0 or 1
y_pred = model.predict_proba(X)[:, 1]  # P(profit)
```

### Feature Selection

**Pre-trade columns only** (information available at entry):

| Category | Features | Count |
|---|---|---|
| **Position** | entry_price, quantity, stoploss, target | 4 |
| **Risk metrics** | stop_distance, target_range, r_multiple_planned | 3 |
| **Account** | account_equity_at_entry, max_drawdown_to_date | 2 |
| **Trader** | trader_skill_edge, trader_risk_appetite | 2 |
| **Asset** | asset_volatility, asset_class | 2 |
| **Strategy** | strategy_type, strategy_avg_rr | 2 |
| **Behavioral** | emotional_state_at_entry, trader_streak | 2 |
| **Time** | hour_of_day, day_of_week, is_weekend | 3 |
| **Sequence** | trade_num_intraday, trade_num_trader | 2 |
| **Market** | volume_profile_hour, correlation_to_market | 2 |
| **Other** | side (long/short), asset_symbol_encoded | 12 |

**Total:** 46 pre-close features

### Banned Columns (Post-Close, Hard-Banned)

```python
BANNED_COLUMNS = [
    'net_profit', 'gross_profit',      # Target itself
    'exit_price', 'exit_time',         # Exit details
    'actual_rr', 'fees',               # Outcome metrics
    'account_equity_at_exit',          # Post-trade equity
    'duration_minutes',                # Holding time (affects P&L)
    'max_drawdown_post',               # Post-trade drawdown
    'emotional_state_at_exit',         # Exit emotion
    'win_streak_at_exit',              # Final streak state
    'is_winner',                       # Direct label
    'trade_num_intraday_next',         # Future state
    # ... 21 more post-close columns
]

# Enforcement (runtime assertion)
for col in BANNED_COLUMNS:
    assert col not in feature_matrix.columns, f"LEAKAGE: {col} in training data!"
```

**Why this matters:**
- Leakage ruins the model (too optimistic)
- Assertion fails the build if accidentally included
- This is the #1 ML mistake — catching it is crucial

---

## Data Splitting

### Chronological Split (Never Random)

```python
# ✓ Correct: chronological (train on past, test on future)
cutoff_date = "2025-06-30"
train_mask = trades['entry_time'] <= cutoff_date
test_mask = trades['entry_time'] > cutoff_date

X_train = trades[train_mask][features]
y_train = trades[train_mask]['net_profit'] > 0

X_test = trades[test_mask][features]
y_test = trades[test_mask]['net_profit'] > 0

# ✗ WRONG: random split (trains on future, tests on past — massive leakage)
from sklearn.model_selection import train_test_split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
# ^ This would make model look 2-3x better than reality
```

**Why chronological?**
- Traders can't use future information
- Random split would test on data the model "saw during training"
- Real deployment has a temporal ordering: train on 2024-2025, deploy on 2026+

### Train/Test Split

```
2024 Jan ─────────────────────────────────── 2025 Jun │ 2025 Jul ─── 2026 Jun
└─────────────── 70% TRAIN ────────────────┘ │ 30% TEST ─────────┘
```

- **Training:** 2024-01-01 to 2025-06-30 (70% of trades)
- **Testing:** 2025-07-01 to 2026-06-30 (30% of trades)
- **Purpose:** Train model on earlier data, evaluate on hold-out future trades

---

## Model Comparison

### Baseline

```python
# Naive model: predict 'Loss' for every trade (36.5% of trades are losses)
baseline_accuracy = 0.635  # Guessing Loss achieves 63.5%
baseline_auc = 0.50       # Random guessing
```

### Trained Models

#### Random Forest

```python
model = RandomForestClassifier(
    n_estimators=500,
    max_depth=15,
    min_samples_split=20,
    min_samples_leaf=10,
    random_state=20260731,
    n_jobs=-1
)

# Results
accuracy = 0.602  # 60.2% (worse than baseline of 63.5%!)
roc_auc = 0.618   # 0.618 (barely better than random 0.50)
```

#### Gradient Boosting

```python
model = GradientBoostingClassifier(
    n_estimators=200,
    learning_rate=0.05,
    max_depth=5,
    random_state=20260731
)

# Results
accuracy = 0.635  # 63.5% (matches naive baseline)
roc_auc = 0.605   # 0.605 (slightly better than RF)
```

#### Why is Accuracy Bad?

```python
# Accuracy is misleading when target is imbalanced
win_rate = 0.3513  # Only 35% of trades win

# Naive prediction: "Loss" for everything
naive = 0.6487     # 64.87% accuracy (higher than model!)

# But the model is still learning something
# It's ordering predictions by P(win)
# Top-decile win rate: 57.2% (vs 36.5% baseline) ✓
```

---

## Evaluation Metrics

### Primary Metrics

```python
# ROC-AUC: How well does the model rank trades?
roc_auc = sklearn.metrics.roc_auc_score(y_test, y_pred_proba)
# Random: 0.50
# Our model: 0.618 ✓ (better but not amazing)

# Top-decile lift: Does it identify the best trades?
top_10_pct = y_pred_proba >= np.percentile(y_pred_proba, 90)
top_10_win_rate = y_test[top_10_pct].mean()
# Baseline win rate: 36.5%
# Top-10 win rate: 57.2% ✓ (1.57× lift)
```

### Calibration Check

```python
# Is P(win) = 60% actually 60% in reality?
from sklearn.calibration import calibration_curve

prob_true, prob_pred = calibration_curve(y_test, y_pred_proba, n_bins=10)

# If model is well-calibrated, prob_true ≈ prob_pred
# Our model: slight overconfidence in high probabilities
```

### Confusion Matrix

```
                Predicted Loss   Predicted Win
Actual Loss     TN: 4,120       FP: 1,280
Actual Win      FN: 982         TP: 1,413

Accuracy = (TN + TP) / total = 5,533 / 9,214 = 60.2%
Precision = TP / (TP + FP) = 1,413 / 2,693 = 52.5%
Recall = TP / (TP + FN) = 1,413 / 2,395 = 59.0%
F1-score = 55.4%
```

---

## Feature Importance

Top 10 features by importance (Random Forest):

```
1. account_equity_at_entry      0.112
2. trader_skill_edge             0.089
3. max_drawdown_to_date          0.078
4. r_multiple_planned            0.067
5. hour_of_day                   0.056
6. asset_volatility              0.049
7. stop_distance                 0.044
8. target_range                  0.041
9. emotional_state               0.038
10. win_streak_at_entry          0.031
```

**Interpretation:**
- Trader skill and account health are strongest signals
- Time-of-day matters (market regimes)
- Emotional state has ~4× less importance than skill edge

---

## Model Card

**Model Name:** TradeTrack Win/Loss Classifier  
**Version:** 1.0  
**Training Date:** 2026-08-16  

### What Does It Predict?

Binary classification: will a trade close profitably (net_profit > 0)?

### Input Features

46 pre-trade columns covering:
- Position structure (entry, stop, target)
- Account health (equity, drawdown)
- Trader profile (skill, risk appetite)
- Market conditions (hour, day, volatility)
- Behavioral state (emotional state, streaks)

### Performance

| Metric | Value |
|---|---|
| Accuracy | 60.2% |
| ROC-AUC | 0.618 |
| Precision | 52.5% |
| Recall | 59.0% |
| Top-decile win rate | 57.2% |

### When It Works Well

- **Predicting for** skilled traders in normal market conditions
- **Top decile** (highest predicted win probability) shows 1.57× lift
- **Hour-of-day effects** are captured (08:00 UTC is best)

### When It Fails

- **For revenge trading** — high emotion overrides model signal
- **During market stress** — volatility assumptions break
- **For tiny accounts** — equity curve dynamics aren't learned
- **Accuracy is misleading** — 60.2% < 63.5% baseline (don't use accuracy alone)

### Honest Limitations

1. **The win rate prediction is correct, but wrong for ranking**
   - Model learns: low-RR trades win more (true)
   - But: low-RR trades are worth less ($)
   - Therefore: ranking by P(win) selects wrong trades (see ml_expected_r.py)

2. **Expectancy in R does not rise with confidence deciles**
   - High confidence predictions win more often
   - But win in small R amounts
   - Expected-R regression beats this model for actual value

3. **Single chronological split**
   - Would benefit from walk-forward validation
   - Currently: train on 70%, test on 30%
   - Better: expanding window with multiple test periods

### When to Use This Model

✓ **Good:**
- Understanding which traders are better (feature importance)
- Routing trades to proven strategies
- Risk assessment at entry
- Analyzing why certain hours/days work better

✗ **Not good:**
- Live trade ranking (use ml_expected_r.py instead)
- Position sizing decisions (expectancy matters, not win rate)
- Strategy selection (other metrics matter more)

---

## The Expected-R Model (Regression)

The classification model shows an important limitation: high win probability ≠ high expected R.

**Solution:** Train a regression model on `r_multiple` instead.

### Comparison

```python
# Classification: P(win)
clf = RandomForestClassifier(...).fit(X_train, y_train)
pred_win_prob = clf.predict_proba(X_test)[:, 1]
corr_with_actual_r = spearmanr(pred_win_prob, y_test['r_multiple'])
# Correlation: −0.016 (negative!)

# Regression: Expected R
reg = RandomForestRegressor(...).fit(X_train, y_train['r_multiple'])
pred_expected_r = reg.predict(X_test)
corr_with_actual_r = spearmanr(pred_expected_r, y_test['r_multiple'])
# Correlation: +0.067** (positive, statistically significant)
```

### Ranking Results

| Ranking Signal | Top 25% | Top 50% |
|---|---|---|
| Expected R (regression) | +0.112R | +0.116R |
| P(win) (classification) | +0.009R | +0.019R |
| Baseline (take all) | +0.041R | +0.041R |

**Takeaway:** Even though the effect is thin, expected-R model outperforms classification.

---

## Key Lessons

### Lesson 1: Leakage Ruins Everything

A model that accidentally uses post-close information will:
- Look 2-3× better in testing
- Fail catastrophically in production
- Waste weeks debugging

**Prevention:**
- Hard-ban post-close columns (assertion)
- Never use `net_profit` or `exit_price` as features
- Chronological split, never random

### Lesson 2: Accuracy is Misleading

When 65% of trades lose:
- Predicting "Loss" always = 65% accuracy
- Your model at 60.2% accuracy = *worse* than baseline
- Use ROC-AUC, precision, recall, or top-decile lift instead

### Lesson 3: Win Rate ≠ Expectancy

The desk cares about money, not hit rate.

| Signal | Implication |
|---|---|
| High P(win) | "This trade will probably be right" |
| High Expected R | "This trade is worth more money" |

A model optimized for P(win) learns to rank low-RR trades higher (they do win more often), but those trades are worth less.

### Lesson 4: When to Upgrade

Current model setup is good for:
- Demonstrating ML pipeline
- Feature engineering practice
- Understanding leakage & train/test splits

Upgrade to:
- **Walk-forward validation** (test on 10+ time windows)
- **Ensemble methods** (stack models instead of comparing)
- **Per-trader models** (traders have different edges)
- **Market-regime features** (is edge conditional on volatility?)

---

## Running the ML Pipeline

```bash
# Train classification model
python analytics/scripts/ml_model.py
# Output: reports/ml_model_report.md

# Train regression model (expected-R objective)
python analytics/scripts/ml_expected_r.py
# Output: reports/ml_expected_r_report.md

# Run as part of full pipeline
python analytics/scripts/run_all.py
```

---

## Code References

- **[analytics/scripts/ml_model.py](../analytics/scripts/ml_model.py)** — Classification model
- **[analytics/scripts/ml_expected_r.py](../analytics/scripts/ml_expected_r.py)** — Regression comparison
- **[reports/ml_model_report.md](../reports/ml_model_report.md)** — Generated model card
- **[reports/ml_expected_r_report.md](../reports/ml_expected_r_report.md)** — Objective comparison

---

## Next Steps

- **[dashboard.md](dashboard.md)** — Interactive visualization layer
- **[analytics_pipeline.md](analytics_pipeline.md)** — Full pipeline overview
