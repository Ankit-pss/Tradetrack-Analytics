"""
TradeTrack Analytics — synthetic trade-blotter generator.
==========================================================

Produces a realistic, internally consistent trading dataset of 10,000+ rows.

Why synthetic: real retail blotters are private. Rather than sampling columns
independently (which produces data with no discoverable structure), this module
simulates the *process* that creates a blotter:

    1. Geometric-Brownian-motion price paths per asset, so entry prices,
       stop distances and targets are all anchored to a plausible market.
    2. Per-trader behavioural profiles (skill, discipline, risk appetite).
    3. A psychology feedback loop — losing streaks raise the probability of
       revenge/FOMO states, which in turn raise size and lower win probability.
    4. Volatility-scaled stops, planned RR bands per strategy and position
       sizing derived from a risk-per-trade budget (risk% x account equity).
    5. Path-dependent exits: target hit, stop hit, or a discretionary exit
       somewhere in between.
    6. Equity compounding per trader, with running peak / drawdown tracking.

The result contains genuine, *recoverable* signal (session edge, strategy edge,
weekday effects, the cost of revenge trading, overtrading decay) which the SQL,
Python and dashboard layers then rediscover analytically.

Finally the raw export is deliberately dirtied — duplicates, nulls, casing
noise, string-formatted numbers, impossible durations, fat-finger prices — so
the cleaning stage is a real pipeline step rather than a formality.

Run:  python python/generate_dataset.py
Out:  data/raw/trades_raw.csv
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (  # noqa: E402
    ASSET_DRIFT, ASSETS, BLOWUP_THRESHOLD, DIRTY, EMOTIONS, END_DATE,
    MIN_TRADES, RANDOM_SEED, RAW_TRADES_CSV, SESSIONS, SIZING_CAP, START_DATE, STRATEGIES,
    TRADERS, WEEKDAY_EDGE,
)

rng = np.random.default_rng(RANDOM_SEED)


# ==========================================================================
# 1. Market simulation
# ==========================================================================
def build_price_paths(start: str, end: str) -> dict[str, pd.Series]:
    """Simulate a daily close series per asset using geometric Brownian motion.

    S_t = S_{t-1} * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    A mild volatility-clustering term is layered on top (a slow-moving vol
    multiplier) so the dataset contains calm and turbulent regimes, which is
    what makes drawdown analysis interesting.
    """
    days = pd.date_range(start, end, freq="D")
    paths: dict[str, pd.Series] = {}

    for asset, spec in ASSETS.items():
        n = len(days)
        mu_daily = ASSET_DRIFT[asset] / 365.0
        sigma = spec["daily_vol"]

        # Slow-moving regime multiplier in [0.6, 1.9] -> volatility clustering.
        regime = np.cumsum(rng.normal(0, 0.05, n))
        regime = 1.0 + 0.45 * np.tanh(regime / 6.0)
        regime = np.clip(regime, 0.6, 1.9)

        shocks = rng.standard_normal(n) * sigma * regime
        log_ret = (mu_daily - 0.5 * (sigma * regime) ** 2) + shocks
        prices = spec["price"] * np.exp(np.cumsum(log_ret))

        paths[asset] = pd.Series(prices, index=days, name=asset)

    return paths


def build_vol_paths(price_paths: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Realised 14-day volatility per asset — the ATR proxy used to size stops."""
    vols = {}
    for asset, series in price_paths.items():
        ret = series.pct_change()
        v = ret.rolling(14, min_periods=1).std().bfill()
        vols[asset] = v.clip(lower=ASSETS[asset]["daily_vol"] * 0.35)
    return vols


# ==========================================================================
# 2. Sampling helpers
# ==========================================================================
def weighted_choice(mapping: dict, key: str = "weight"):
    """Pick a key from {name: {..., 'weight': w}} proportionally to w."""
    names = list(mapping.keys())
    weights = np.array([mapping[n][key] for n in names], dtype=float)
    return names[int(rng.choice(len(names), p=weights / weights.sum()))]


def pick_session_hour(session: str) -> tuple[int, int]:
    """Random entry hour/minute inside a session window (UTC)."""
    lo, hi = SESSIONS[session]["hours"]
    hour = int(rng.integers(lo, hi))
    minute = int(rng.integers(0, 60))
    return hour, minute


def pick_emotion(loss_streak: int, discipline: float) -> str:
    """Emotional state, biased by discipline and by the current losing streak.

    This is the behavioural core of the dataset: two losses in a row sharply
    raise the odds of Revenge / FOMO, which then degrade the next trade.
    """
    names = list(EMOTIONS.keys())
    w = np.array([EMOTIONS[n]["base_w"] for n in names], dtype=float)

    controlled = {"Disciplined", "Confident", "Neutral"}
    for i, n in enumerate(names):
        if n in controlled:
            w[i] *= 0.45 + 1.35 * discipline
        else:
            w[i] *= 1.85 - 1.30 * discipline

    if loss_streak >= 2:
        tilt = min(loss_streak, 5)
        for i, n in enumerate(names):
            if n == "Revenge":
                w[i] *= 1.0 + 1.15 * tilt
            elif n in ("FOMO", "Anxious"):
                w[i] *= 1.0 + 0.45 * tilt
            elif n == "Disciplined":
                w[i] *= max(0.25, 1.0 - 0.22 * tilt)

    return names[int(rng.choice(len(names), p=w / w.sum()))]


def note_for(emotion: str, outcome: str, strategy: str, asset: str) -> str:
    """Short, human-sounding journal note consistent with the trade context."""
    win_notes = {
        "Disciplined": [
            f"Clean {strategy.lower()} setup on {asset}, waited for confirmation and let the target fill.",
            "Followed the plan exactly. Entry at level, stop below structure, target hit.",
            "A+ setup. Risk sized correctly, no interference after entry.",
        ],
        "Confident": [
            f"Read the {asset} structure well, scaled out at target.",
            "Good execution, momentum confirmed the bias early.",
        ],
        "Neutral": [
            f"Standard {strategy.lower()} entry, nothing special. Target reached.",
            "Textbook execution, no emotion involved.",
        ],
        "Anxious": [
            "Took profit early out of nervousness, trade ran further without me.",
            "Hesitated on entry, still worked but I left money on the table.",
        ],
        "FOMO": [
            f"Chased {asset} after the initial move — got lucky this time, not repeatable.",
            "Entered late without confirmation. Worked, but the process was wrong.",
        ],
        "Greedy": [
            "Oversized because the setup 'looked obvious'. Won, but risk was excessive.",
            "Added to the winner beyond plan. Outcome fine, discipline poor.",
        ],
        "Revenge": [
            "Jumped straight back in after the previous loss. Recovered, pure luck.",
            "Doubled size to make the loss back. Won — dangerous precedent.",
        ],
    }
    loss_notes = {
        "Disciplined": [
            f"Valid {strategy.lower()} setup, market simply rejected the level. Stop respected.",
            "Plan followed, thesis invalidated. Acceptable loss, nothing to fix.",
            f"{asset} reversed on higher-timeframe supply. Good loss.",
        ],
        "Confident": [
            "Was too sure of the bias and ignored the opposing signal.",
            "Overconfident after a winning run, skipped confirmation.",
        ],
        "Neutral": [
            "Setup failed, stop hit as planned.",
            f"Choppy conditions on {asset}, no follow-through.",
        ],
        "Anxious": [
            "Cut the position early in fear, price later reached my target.",
            "Second-guessed the entry and exited into noise.",
        ],
        "FOMO": [
            f"Chased the {asset} candle after the move was done. Immediate reversal.",
            "No setup, pure fear of missing out. Deserved loss.",
        ],
        "Greedy": [
            "Oversized well beyond the risk plan and got punished.",
            "Held past the invalidation hoping for more. Bad exit.",
        ],
        "Revenge": [
            "Revenge trade straight after a loss. Size was reckless, no setup.",
            "Tried to recover the previous loss in one trade. Textbook tilt.",
            "Entered within minutes of stopping out. Emotional, not analytical.",
        ],
    }
    pool = (win_notes if outcome == "Win" else loss_notes)[emotion]
    return str(rng.choice(pool))


# ==========================================================================
# 3. Trade simulation
# ==========================================================================
def simulate_trades() -> pd.DataFrame:
    price_paths = build_price_paths(START_DATE, END_DATE)
    vol_paths = build_vol_paths(price_paths)
    calendar = pd.date_range(START_DATE, END_DATE, freq="D")

    # Per-trader running state.
    state = {
        t["id"]: {
            "balance": float(t["start_balance"]),
            "peak": float(t["start_balance"]),
            "max_dd": 0.0,
            "loss_streak": 0,
            "blown": False,
            "profile": t,
        }
        for t in TRADERS
    }

    asset_names = list(ASSETS.keys())
    weekday_asset_p = np.array([0.22, 0.15, 0.16, 0.18, 0.14, 0.15])
    crypto_names = [a for a in asset_names if ASSETS[a]["weekend"]]

    rows: list[dict] = []
    trade_no = 0

    # Single pass over the calendar, day by day, so per-day trade counts (and
    # therefore the overtrading effect) are meaningful.
    for day in calendar:
        is_weekend = day.weekday() >= 5

        for trader in TRADERS:
            st = state[trader["id"]]

            # A blown account stops trading permanently.
            if st["blown"]:
                continue
            if st["balance"] < trader["start_balance"] * BLOWUP_THRESHOLD:
                st["blown"] = True
                continue

            # Weekend activity is crypto-only and much thinner.
            base_activity = 0.52 if not is_weekend else 0.14
            if rng.random() > base_activity:
                continue

            # Trades per day: tilted traders overtrade.
            lam = 1.7 + 1.6 * (1.0 - trader["discipline"])
            if st["loss_streak"] >= 2:
                lam *= 1.0 + 0.30 * min(st["loss_streak"], 4)
            n_today = int(np.clip(rng.poisson(lam), 1, 12))

            for seq in range(n_today):
                    # ---- context -------------------------------------------------
                    if is_weekend:
                        asset = str(rng.choice(crypto_names))
                    else:
                        asset = str(rng.choice(asset_names, p=weekday_asset_p))

                    strategy = weighted_choice(STRATEGIES)
                    session = weighted_choice(SESSIONS)
                    hour, minute = pick_session_hour(session)
                    emotion = pick_emotion(st["loss_streak"], trader["discipline"])
                    direction = "Buy" if rng.random() < 0.52 else "Sell"
                    sign = 1 if direction == "Buy" else -1

                    entry_dt = datetime(day.year, day.month, day.day, hour, minute,
                                        int(rng.integers(0, 60)))

                    # ---- price & volatility -------------------------------------
                    px_close = float(price_paths[asset].loc[day])
                    vol = float(vol_paths[asset].loc[day])
                    # Intraday entry price wanders around the daily close.
                    entry_price = px_close * (1.0 + rng.normal(0, vol * 0.45))

                    # ---- risk plan ----------------------------------------------
                    spec = STRATEGIES[strategy]
                    stop_k = rng.uniform(*spec["stop_k"])
                    stop_dist = entry_price * vol * stop_k
                    stop_dist = max(stop_dist, entry_price * 1e-4)
                    planned_rr = round(float(rng.uniform(*spec["rr"])), 2)
                    target_dist = stop_dist * planned_rr

                    stop_loss = entry_price - sign * stop_dist
                    take_profit = entry_price + sign * target_dist

                    # Risk budget: base risk% x trader appetite x emotional multiplier
                    base_risk_pct = float(np.clip(rng.normal(1.05, 0.35), 0.20, 2.6))
                    risk_pct = base_risk_pct * trader["size_bias"] * EMOTIONS[emotion]["risk_mult"]
                    risk_pct = float(np.clip(risk_pct, 0.10, 9.0))
                    # Position size is set against a *sizing equity* that is
                    # capped at SIZING_CAP x the opening balance. This models the
                    # real behaviour of profitable traders withdrawing profit
                    # instead of compounding risk forever — without it a single
                    # edge trader's equity runs away exponentially and swamps
                    # every portfolio-level aggregate.
                    sizing_equity = min(st["balance"], trader["start_balance"] * SIZING_CAP)
                    risk_amount = sizing_equity * risk_pct / 100.0

                    quantity = risk_amount / stop_dist
                    quantity = float(max(quantity, 1e-4))

                    # ---- outcome probability ------------------------------------
                    # Anchor: in an efficient market a target R away from a stop
                    # 1R away fills with probability 1/(1+R). Everything else is
                    # a small EDGE on top of that breakeven rate, so expectancy
                    # per trade is roughly edge x (1 + RR) in R units and a high
                    # RR mechanically implies a low win rate. Without this
                    # anchor the blotter compounds to implausible numbers.
                    p_breakeven = 1.0 / (1.0 + planned_rr)
                    edge = trader["edge"]
                    edge += spec["edge"]
                    edge += SESSIONS[session]["edge"]
                    edge += EMOTIONS[emotion]["p_edge"]
                    edge += WEEKDAY_EDGE[day.weekday()]
                    edge -= 0.006 * seq                  # overtrading decay
                    if ASSETS[asset]["class"] == "Crypto" and session == "Asia":
                        edge += 0.008
                    if ASSETS[asset]["class"] == "Index" and session == "New York":
                        edge += 0.018
                    if ASSETS[asset]["class"] == "Forex" and session == "London":
                        edge += 0.015
                    p = float(np.clip(p_breakeven + edge, 0.05, 0.92))

                    is_win = rng.random() < p
                    cut_early = rng.random() < EMOTIONS[emotion]["cut_early"]

                    # ---- exit path ----------------------------------------------
                    if is_win:
                        if cut_early:
                            frac = float(rng.uniform(0.25, 0.85))   # took profit early
                        else:
                            frac = 1.0 if rng.random() < 0.78 else float(rng.uniform(0.85, 1.15))
                        exit_price = entry_price + sign * target_dist * frac
                    else:
                        if cut_early:
                            frac = float(rng.uniform(0.20, 0.90))   # bailed before the stop
                        else:
                            # Slippage past the stop on ~12% of losers.
                            frac = 1.0 if rng.random() < 0.88 else float(rng.uniform(1.02, 1.45))
                        exit_price = entry_price - sign * stop_dist * frac

                    # ---- duration ------------------------------------------------
                    lo, hi = spec["hold"]
                    duration = int(np.clip(rng.lognormal(np.log(max(lo, 1) * 2.2), 0.75),
                                           lo, hi))
                    if cut_early:
                        duration = int(max(1, duration * rng.uniform(0.25, 0.7)))
                    exit_dt = entry_dt + timedelta(minutes=duration)

                    # ---- P&L -----------------------------------------------------
                    gross = (exit_price - entry_price) * quantity * sign
                    notional = entry_price * quantity
                    # Round-trip cost on the traded notional. Tight-stop styles
                    # carry a much larger notional per unit of risk, so scalping
                    # naturally bleeds more in fees — a real and visible effect.
                    fees = notional * ASSETS[asset]["fee_bps"] / 10_000.0
                    fees = round(float(min(fees, risk_amount * 0.75)), 2)
                    net = gross - fees

                    # ---- equity, drawdown ----------------------------------------
                    st["balance"] = max(0.0, st["balance"] + net)
                    st["peak"] = max(st["peak"], st["balance"])
                    dd = (st["peak"] - st["balance"]) / st["peak"] * 100.0
                    st["max_dd"] = max(st["max_dd"], dd)

                    outcome = "Win" if net > 0 else ("Loss" if net < 0 else "Breakeven")
                    st["loss_streak"] = 0 if net > 0 else st["loss_streak"] + 1

                    trade_no += 1
                    rows.append({
                        "trade_id": f"TT-{trade_no:06d}",
                        "trader_id": trader["id"],
                        "trader_name": trader["name"],
                        "trade_date": entry_dt.date().isoformat(),
                        "entry_time": entry_dt.strftime("%H:%M:%S"),
                        "exit_time": exit_dt.strftime("%H:%M:%S"),
                        "exit_date": exit_dt.date().isoformat(),
                        "trading_session": session,
                        "asset": asset,
                        "asset_class": ASSETS[asset]["class"],
                        "trade_type": direction,
                        "strategy": strategy,
                        "entry_price": round(entry_price, 5),
                        "exit_price": round(exit_price, 5),
                        "stop_loss": round(stop_loss, 5),
                        "take_profit": round(take_profit, 5),
                        "quantity": round(quantity, 6),
                        "risk_pct": round(risk_pct, 3),
                        "reward_pct": round(risk_pct * planned_rr, 3),
                        "profit_loss": round(gross, 2),
                        "fees": fees,
                        "net_profit": round(net, 2),
                        "trade_duration_min": duration,
                        "win_loss": outcome,
                        "account_balance": round(st["balance"], 2),
                        "max_drawdown_pct": round(st["max_dd"], 3),
                        "risk_reward_ratio": planned_rr,
                        "emotional_state": emotion,
                        "trade_notes": note_for(emotion, outcome, strategy, asset),
                        "data_source": "synthetic",
                    })

    df = pd.DataFrame(rows)
    return df.sort_values(["trade_date", "entry_time"]).reset_index(drop=True)


# ==========================================================================
# 4. Dirty-data injection (so the cleaning stage has real work)
# ==========================================================================
def dirty_it(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    n = len(df)

    def idx(k):
        return rng.choice(n, size=min(k, n), replace=False)

    # 1. Open trades: no exit yet.
    for i in idx(DIRTY["missing_exit_price"]):
        df.loc[i, ["exit_price", "exit_time", "exit_date", "profit_loss",
                   "net_profit", "win_loss", "trade_duration_min"]] = np.nan

    # 2. Missing journal fields.
    df.loc[idx(DIRTY["missing_emotion"]), "emotional_state"] = np.nan
    df.loc[idx(DIRTY["missing_notes"]), "trade_notes"] = np.nan

    # 3. Casing / whitespace noise on categoricals.
    for i in idx(DIRTY["casing_noise"]):
        col = str(rng.choice(["asset", "strategy", "trade_type", "trading_session"]))
        val = df.loc[i, col]
        if isinstance(val, str):
            style = rng.integers(0, 3)
            df.loc[i, col] = val.lower() if style == 0 else (
                val.upper() if style == 1 else f"  {val} ")

    # 4. Numbers exported as thousand-separated strings.
    df["entry_price"] = df["entry_price"].astype(object)
    df["net_profit"] = df["net_profit"].astype(object)
    for i in idx(DIRTY["numeric_as_string"]):
        col = "entry_price" if rng.random() < 0.5 else "net_profit"
        v = df.loc[i, col]
        if pd.notna(v):
            df.loc[i, col] = f"{float(v):,.2f}"

    # 5. Impossible durations (clock/timezone bugs upstream).
    for i in idx(DIRTY["impossible_duration"]):
        if pd.notna(df.loc[i, "trade_duration_min"]):
            df.loc[i, "trade_duration_min"] = int(rng.choice([-15, -3, 0, -120]))

    # 6. Fat-finger entry prices (10-100x).
    for i in idx(DIRTY["outlier_prices"]):
        v = df.loc[i, "entry_price"]
        try:
            df.loc[i, "entry_price"] = round(float(str(v).replace(",", "")) * float(rng.choice([10, 100])), 5)
        except (TypeError, ValueError):
            pass

    # 7. Exact duplicate rows (double-submitted from the journal UI).
    dupes = df.iloc[idx(DIRTY["duplicate_rows"])].copy()
    df = pd.concat([df, dupes], ignore_index=True)

    # Shuffle so duplicates are not trivially adjacent, then keep a stable order.
    df = df.sample(frac=1.0, random_state=RANDOM_SEED).reset_index(drop=True)
    return df


def main() -> None:
    print("Simulating market paths and trade flow ...")
    clean = simulate_trades()
    assert len(clean) >= MIN_TRADES, (
        f"only {len(clean)} trades simulated, need >= {MIN_TRADES}; "
        "raise base_activity or extend END_DATE"
    )
    print(f"  simulated {len(clean):,} trades "
          f"({clean['trade_date'].min()} -> {clean['trade_date'].max()})")

    raw = dirty_it(clean)
    raw.to_csv(RAW_TRADES_CSV, index=False)

    print(f"  injected data-quality faults -> {len(raw):,} raw rows")
    print(f"  written: {RAW_TRADES_CSV}")
    print("\nSanity check on the clean simulation:")
    closed = clean[clean["win_loss"].notna()]
    print(f"  win rate        : {(closed['win_loss'].eq('Win').mean() * 100):.2f}%")
    print(f"  net P&L         : {clean['net_profit'].sum():,.2f}")
    print(f"  avg RR planned  : {clean['risk_reward_ratio'].mean():.2f}")
    print(f"  traders         : {clean['trader_id'].nunique()}")


if __name__ == "__main__":
    main()
