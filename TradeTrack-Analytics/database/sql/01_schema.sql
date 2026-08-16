-- ============================================================================
-- TradeTrack Analytics — Warehouse Schema
-- ----------------------------------------------------------------------------
-- A compact star schema over the cleaned blotter:
--
--        dim_trader ──┐
--                     ├──< fact_trades >──┬── dim_calendar
--        dim_asset  ──┘                   └── dim_strategy
--
-- The fact table is at TRADE grain (one row = one closed trade). Every measure
-- is additive over that grain, which is what keeps the BI layer honest: totals
-- can be summed along any dimension without double counting.
--
-- Written for SQLite (the project ships a file-based warehouse so it runs with
-- zero setup). ANSI-compatible apart from the STRFTIME calls, which are noted
-- inline with their PostgreSQL equivalents.
-- ============================================================================

DROP VIEW  IF EXISTS vw_trade_enriched;
DROP VIEW  IF EXISTS vw_daily_pnl;
DROP VIEW  IF EXISTS vw_monthly_pnl;
DROP TABLE IF EXISTS fact_trades;
DROP TABLE IF EXISTS dim_trader;
DROP TABLE IF EXISTS dim_asset;
DROP TABLE IF EXISTS dim_strategy;
DROP TABLE IF EXISTS dim_calendar;

-- ----------------------------------------------------------------------------
-- Dimensions
-- ----------------------------------------------------------------------------
CREATE TABLE dim_trader (
    trader_id        TEXT PRIMARY KEY,
    trader_name      TEXT NOT NULL,
    first_trade_date TEXT,
    last_trade_date  TEXT,
    total_trades     INTEGER
);

CREATE TABLE dim_asset (
    asset       TEXT PRIMARY KEY,
    asset_class TEXT NOT NULL
);

CREATE TABLE dim_strategy (
    strategy TEXT PRIMARY KEY
);

CREATE TABLE dim_calendar (
    date        TEXT PRIMARY KEY,
    year        INTEGER NOT NULL,
    quarter     TEXT    NOT NULL,
    month       INTEGER NOT NULL,
    month_name  TEXT    NOT NULL,
    year_month  TEXT    NOT NULL,
    iso_week    INTEGER NOT NULL,
    year_week   TEXT    NOT NULL,
    weekday_num INTEGER NOT NULL,
    weekday     TEXT    NOT NULL,
    is_weekend  INTEGER NOT NULL
);

-- ----------------------------------------------------------------------------
-- Fact table — one row per CLOSED trade
-- ----------------------------------------------------------------------------
CREATE TABLE fact_trades (
    trade_id           TEXT PRIMARY KEY,
    trader_id          TEXT NOT NULL REFERENCES dim_trader(trader_id),
    trade_date         TEXT NOT NULL REFERENCES dim_calendar(date),
    entry_time         TEXT,
    exit_time          TEXT,
    exit_date          TEXT,
    entry_datetime     TEXT,
    exit_datetime      TEXT,

    -- dimensions
    trading_session    TEXT NOT NULL,          -- Asia | London | New York
    asset              TEXT NOT NULL REFERENCES dim_asset(asset),
    asset_class        TEXT NOT NULL,
    trade_type         TEXT NOT NULL,          -- Buy | Sell
    strategy           TEXT NOT NULL REFERENCES dim_strategy(strategy),
    emotional_state    TEXT,

    -- price geometry
    entry_price        REAL NOT NULL,
    exit_price         REAL NOT NULL,
    stop_loss          REAL,
    take_profit        REAL,
    quantity           REAL NOT NULL,
    stop_distance      REAL,
    notional           REAL,

    -- risk & reward
    risk_pct           REAL,                   -- planned risk as % of equity
    reward_pct         REAL,                   -- planned reward as % of equity
    risk_amount        REAL,                   -- dollars at risk
    risk_reward_ratio  REAL,                   -- planned RR
    realised_rr        REAL,                   -- achieved RR
    r_multiple         REAL,                   -- net P&L / dollars risked

    -- outcome
    profit_loss        REAL NOT NULL,          -- gross, before fees
    fees               REAL NOT NULL,
    net_profit         REAL NOT NULL,          -- after fees; the truth column
    win_loss           TEXT NOT NULL,
    is_win             INTEGER NOT NULL,       -- 1/0, for AVG() win rates
    gross_profit       REAL,                   -- net_profit when > 0 else 0
    gross_loss         REAL,                   -- -net_profit when < 0 else 0
    trade_duration_min REAL,

    -- account state at the time of the trade
    account_balance    REAL,
    equity_peak        REAL,
    drawdown_pct       REAL,
    cum_pnl_trader     REAL,

    -- behavioural / sequencing features
    trade_seq          INTEGER,
    trade_seq_in_day   INTEGER,
    trades_that_day    INTEGER,
    win_streak         INTEGER,
    loss_streak        INTEGER,
    prev_result        REAL,
    prev_loss_streak   REAL,
    is_quick_reentry   INTEGER,
    is_tilt_state      INTEGER,

    -- pre-computed calendar attributes (denormalised for query speed)
    year               INTEGER,
    quarter            TEXT,
    month              INTEGER,
    month_name         TEXT,
    year_month         TEXT,
    iso_week           INTEGER,
    year_week          TEXT,
    weekday_num        INTEGER,
    weekday            TEXT,
    entry_hour         INTEGER,
    duration_bucket    TEXT,
    risk_bucket        TEXT,
    rr_bucket          TEXT,
    trade_notes        TEXT,

    -- data lineage
    data_source        TEXT NOT NULL           -- synthetic | real
);

-- Indexes chosen from the actual access patterns in 02_analysis_queries.sql:
-- every query filters or groups on at least one of these.
CREATE INDEX idx_ft_date      ON fact_trades(trade_date);
CREATE INDEX idx_ft_trader    ON fact_trades(trader_id);
CREATE INDEX idx_ft_asset     ON fact_trades(asset);
CREATE INDEX idx_ft_strategy  ON fact_trades(strategy);
CREATE INDEX idx_ft_session   ON fact_trades(trading_session);
CREATE INDEX idx_ft_source    ON fact_trades(data_source);
CREATE INDEX idx_ft_month     ON fact_trades(year_month);
CREATE INDEX idx_ft_trader_dt ON fact_trades(trader_id, entry_datetime);

-- ----------------------------------------------------------------------------
-- Views — the grain changes most reports need
-- ----------------------------------------------------------------------------

-- Daily desk-level P&L with a running equity curve and drawdown.
CREATE VIEW vw_daily_pnl AS
SELECT
    trade_date,
    COUNT(*)                                   AS trades,
    COUNT(DISTINCT trader_id)                  AS active_traders,
    SUM(is_win)                                AS wins,
    COUNT(*) - SUM(is_win)                     AS losses,
    ROUND(AVG(is_win) * 100.0, 2)              AS win_rate_pct,
    ROUND(SUM(profit_loss), 2)                 AS gross_pnl,
    ROUND(SUM(fees), 2)                        AS fees,
    ROUND(SUM(net_profit), 2)                  AS net_pnl,
    ROUND(AVG(r_multiple), 4)                  AS avg_r,
    ROUND(AVG(trade_duration_min), 1)          AS avg_duration_min
FROM fact_trades
GROUP BY trade_date;

-- Monthly P&L with month-over-month growth of cumulative equity.
CREATE VIEW vw_monthly_pnl AS
SELECT
    year_month,
    COUNT(*)                                   AS trades,
    SUM(is_win)                                AS wins,
    ROUND(AVG(is_win) * 100.0, 2)              AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                  AS net_pnl,
    ROUND(SUM(gross_profit), 2)                AS gross_profit,
    ROUND(SUM(gross_loss), 2)                  AS gross_loss,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_loss), 0), 3) AS profit_factor,
    ROUND(AVG(risk_reward_ratio), 2)           AS avg_planned_rr,
    ROUND(AVG(risk_pct), 3)                    AS avg_risk_pct
FROM fact_trades
GROUP BY year_month;

-- Trade-level view with the labels a BI tool wants pre-joined.
CREATE VIEW vw_trade_enriched AS
SELECT
    f.*,
    t.trader_name,
    CASE
        WHEN f.entry_hour BETWEEN 0  AND 7  THEN 'Asia (00-08 UTC)'
        WHEN f.entry_hour BETWEEN 8  AND 12 THEN 'London (08-13 UTC)'
        ELSE                                     'New York (13-24 UTC)'
    END AS session_label,
    CASE WHEN f.net_profit > 0 THEN 'Win' ELSE 'Loss' END AS outcome
FROM fact_trades f
JOIN dim_trader t ON t.trader_id = f.trader_id;
