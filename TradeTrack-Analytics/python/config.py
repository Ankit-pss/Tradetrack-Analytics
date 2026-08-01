"""
TradeTrack Analytics — central configuration.

Every path, constant and market assumption used across the data generator,
cleaning pipeline, KPI engine, visualisation layer and ML model lives here so
the project has one source of truth.
"""
from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
SQL_DIR = os.path.join(PROJECT_ROOT, "sql")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboard")
POWERBI_DIR = os.path.join(PROJECT_ROOT, "powerbi")

RAW_TRADES_CSV = os.path.join(RAW_DIR, "trades_raw.csv")
CLEAN_TRADES_CSV = os.path.join(PROCESSED_DIR, "trades_clean.csv")
DAILY_CSV = os.path.join(PROCESSED_DIR, "daily_performance.csv")
TRADER_CSV = os.path.join(PROCESSED_DIR, "trader_summary.csv")
MONTHLY_CSV = os.path.join(PROCESSED_DIR, "monthly_performance.csv")
DIM_CALENDAR_CSV = os.path.join(PROCESSED_DIR, "dim_calendar.csv")
SQLITE_DB = os.path.join(DATA_DIR, "tradetrack.db")
KPI_JSON = os.path.join(REPORTS_DIR, "kpi_summary.json")

for _d in (RAW_DIR, PROCESSED_DIR, IMAGES_DIR, REPORTS_DIR, DASHBOARD_DIR):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------
# Simulation parameters
# --------------------------------------------------------------------------
RANDOM_SEED = 20260731
MIN_TRADES = 10_000            # hard floor asserted after simulation
START_DATE = "2024-01-01"
END_DATE = "2026-06-30"

# Asset universe: reference price, annualised vol, tick fee (bps of notional),
# whether the market trades on weekends, and the instrument class.
ASSETS = {
    "BTC":    {"price": 42_000.0, "daily_vol": 0.032, "fee_bps": 7.5,  "weekend": True,  "class": "Crypto"},
    "ETH":    {"price": 2_300.0,  "daily_vol": 0.038, "fee_bps": 8.5,  "weekend": True,  "class": "Crypto"},
    "GOLD":   {"price": 2_060.0,  "daily_vol": 0.009, "fee_bps": 3.0,  "weekend": False, "class": "Commodity"},
    "NASDAQ": {"price": 16_500.0, "daily_vol": 0.011, "fee_bps": 2.2,  "weekend": False, "class": "Index"},
    "US30":   {"price": 37_600.0, "daily_vol": 0.008, "fee_bps": 2.0,  "weekend": False, "class": "Index"},
    "EURUSD": {"price": 1.0950,   "daily_vol": 0.0045, "fee_bps": 1.2, "weekend": False, "class": "Forex"},
}

# Annualised drift used for the synthetic price paths (keeps prices plausible
# across the 2.5-year window instead of drifting to zero or to the moon).
ASSET_DRIFT = {"BTC": 0.55, "ETH": 0.35, "GOLD": 0.18, "NASDAQ": 0.20, "US30": 0.12, "EURUSD": 0.01}

# Strategy playbook. `edge` is the win-probability offset applied ON TOP of the
# RR-implied breakeven rate, `rr` the planned reward:risk band, `hold` the
# holding-time band in minutes and `stop_k` scales the stop distance against
# realised volatility.
STRATEGIES = {
    "Breakout":         {"edge": +0.004, "rr": (1.8, 3.2), "hold": (25, 240),    "stop_k": (0.45, 0.90), "weight": 0.20},
    "Trend Following":  {"edge": +0.022, "rr": (2.2, 4.0), "hold": (120, 1_800), "stop_k": (0.60, 1.20), "weight": 0.18},
    "Mean Reversion":   {"edge": +0.012, "rr": (1.0, 1.8), "hold": (30, 300),    "stop_k": (0.50, 1.00), "weight": 0.16},
    "Scalping":         {"edge": -0.010, "rr": (0.8, 1.4), "hold": (3, 35),      "stop_k": (0.15, 0.35), "weight": 0.19},
    "News Trading":     {"edge": -0.030, "rr": (1.5, 3.5), "hold": (5, 90),      "stop_k": (0.55, 1.30), "weight": 0.09},
    "Swing":            {"edge": +0.016, "rr": (2.5, 5.0), "hold": (600, 5_760), "stop_k": (0.90, 1.80), "weight": 0.10},
    "Order Block (SMC)": {"edge": +0.006, "rr": (2.0, 3.6), "hold": (40, 420),   "stop_k": (0.40, 0.85), "weight": 0.08},
}

# Trading sessions in UTC. Entry hour decides the session label.
SESSIONS = {
    "Asia":     {"hours": (0, 8),   "edge": -0.018, "weight": 0.24},
    "London":   {"hours": (8, 13),  "edge": +0.020, "weight": 0.38},
    "New York": {"hours": (13, 21), "edge": +0.006, "weight": 0.38},
}

# Emotional state -> behavioural consequences.
#   p_edge     : win-probability modifier
#   risk_mult  : how much bigger/smaller the risk taken is
#   cut_early  : probability the trader bails before target is reached
EMOTIONS = {
    "Disciplined": {"p_edge": +0.030, "risk_mult": 1.00, "cut_early": 0.12, "base_w": 0.30},
    "Confident":   {"p_edge": +0.012, "risk_mult": 1.10, "cut_early": 0.18, "base_w": 0.20},
    "Neutral":     {"p_edge": +0.000, "risk_mult": 1.00, "cut_early": 0.22, "base_w": 0.22},
    "Anxious":     {"p_edge": -0.020, "risk_mult": 0.85, "cut_early": 0.48, "base_w": 0.10},
    "FOMO":        {"p_edge": -0.038, "risk_mult": 1.45, "cut_early": 0.30, "base_w": 0.08},
    "Greedy":      {"p_edge": -0.028, "risk_mult": 1.60, "cut_early": 0.15, "base_w": 0.06},
    "Revenge":     {"p_edge": -0.060, "risk_mult": 2.20, "cut_early": 0.25, "base_w": 0.04},
}

# Weekday win-probability modifiers (0 = Monday). Mondays are noisy, Fridays
# suffer from position-squaring; midweek is the sweet spot.
WEEKDAY_EDGE = {0: -0.014, 1: +0.009, 2: +0.013, 3: +0.002, 4: -0.016, 5: -0.007, 6: -0.009}

# Trader roster.
#   edge       : win-probability edge ABOVE the RR-implied breakeven rate.
#                Positive = a real edge; negative = a structurally losing trader.
#                Expectancy per trade in R units is approximately edge x (1 + RR),
#                so +0.030 at RR 2.3 is roughly +0.10R — a genuinely good trader.
#   discipline : how often the trader stays in a controlled emotional state
#   size_bias  : risk appetite multiplier on the per-trade risk budget
TRADERS = [
    {"id": "TR-001", "name": "A. Kapoor",    "edge": +0.042, "discipline": 0.86, "size_bias": 0.90, "start_balance": 50_000,  "weight": 0.12},
    {"id": "TR-002", "name": "M. Chen",      "edge": +0.030, "discipline": 0.80, "size_bias": 1.00, "start_balance": 25_000,  "weight": 0.11},
    {"id": "TR-003", "name": "S. Iyer",      "edge": +0.000, "discipline": 0.62, "size_bias": 1.30, "start_balance": 15_000,  "weight": 0.10},
    {"id": "TR-004", "name": "J. Okafor",    "edge": +0.040, "discipline": 0.90, "size_bias": 0.80, "start_balance": 100_000, "weight": 0.10},
    {"id": "TR-005", "name": "L. Fernandez", "edge": -0.022, "discipline": 0.48, "size_bias": 1.70, "start_balance": 10_000,  "weight": 0.09},
    {"id": "TR-006", "name": "K. Watanabe",  "edge": +0.018, "discipline": 0.75, "size_bias": 1.00, "start_balance": 35_000,  "weight": 0.09},
    {"id": "TR-007", "name": "D. Novak",     "edge": -0.010, "discipline": 0.55, "size_bias": 1.50, "start_balance": 20_000,  "weight": 0.08},
    {"id": "TR-008", "name": "R. Sharma",    "edge": +0.036, "discipline": 0.83, "size_bias": 0.95, "start_balance": 60_000,  "weight": 0.08},
    {"id": "TR-009", "name": "E. Bauer",     "edge": +0.012, "discipline": 0.70, "size_bias": 1.10, "start_balance": 30_000,  "weight": 0.07},
    {"id": "TR-010", "name": "P. Silva",     "edge": -0.036, "discipline": 0.42, "size_bias": 1.90, "start_balance": 12_000,  "weight": 0.06},
    {"id": "TR-011", "name": "N. Haddad",    "edge": +0.028, "discipline": 0.78, "size_bias": 1.05, "start_balance": 45_000,  "weight": 0.05},
    {"id": "TR-012", "name": "T. Bergman",   "edge": +0.010, "discipline": 0.72, "size_bias": 1.15, "start_balance": 28_000,  "weight": 0.05},
]

# An account is considered blown (and the trader stops trading) below this
# fraction of their opening balance.
BLOWUP_THRESHOLD = 0.15

# Position size is computed against equity capped at this multiple of the
# opening balance (models profitable traders withdrawing rather than
# compounding risk indefinitely).
SIZING_CAP = 2.5

# --------------------------------------------------------------------------
# Analytics constants
# --------------------------------------------------------------------------
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.045          # annual, used by the Sharpe / Sortino calcs

# Data-quality faults deliberately injected into the RAW file so the cleaning
# stage has real work to do (and so the notebook can prove it fixed them).
DIRTY = {
    "duplicate_rows": 180,
    "missing_exit_price": 140,     # trades still marked open
    "missing_emotion": 260,
    "missing_notes": 400,
    "casing_noise": 500,           # "btc", " Breakout ", "buy"
    "numeric_as_string": 300,      # "1,250.75" style
    "impossible_duration": 45,     # negative / zero durations
    "outlier_prices": 25,          # fat-finger price entries
}
