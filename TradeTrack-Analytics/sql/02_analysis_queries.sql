-- ============================================================================
-- TradeTrack Analytics — Analysis Query Library
-- ----------------------------------------------------------------------------
-- 21 production-style analytical queries over the star schema in 01_schema.sql.
--
-- Conventions used throughout:
--   * net_profit (AFTER fees) is the only P&L column used for performance
--     judgements. Gross P&L flatters every strategy and is reported separately
--     so the fee drag is visible rather than hidden.
--   * Win rate is AVG(is_win) * 100 — is_win is stored as 1/0 precisely so
--     rate calculations stay a single scan with no CASE gymnastics.
--   * NULLIF(x, 0) guards every division. A single zero-denominator group
--     would otherwise abort the whole report.
--   * Window functions carry the running/cumulative logic instead of
--     correlated subqueries — O(n log n) instead of O(n^2).
--
-- Each block is delimited by a "-- @query:" marker so run_sql_analysis.py can
-- execute them individually and export the results.
-- ============================================================================


-- @query: 01_total_profit
-- @desc: Headline P&L. Splits gross from fees so the cost of trading is explicit.
SELECT
    ROUND(SUM(profit_loss), 2)                              AS gross_profit,
    ROUND(SUM(fees), 2)                                     AS total_fees,
    ROUND(SUM(net_profit), 2)                               AS net_profit,
    ROUND(SUM(fees) * 100.0 / NULLIF(ABS(SUM(profit_loss)), 0), 2)
                                                            AS fees_pct_of_gross
FROM fact_trades;


-- @query: 02_total_trades
-- @desc: Volume overview — trades, traders, instruments and the active window.
SELECT
    COUNT(*)                        AS total_trades,
    COUNT(DISTINCT trader_id)       AS traders,
    COUNT(DISTINCT asset)           AS assets_traded,
    COUNT(DISTINCT strategy)        AS strategies_used,
    COUNT(DISTINCT trade_date)      AS active_days,
    MIN(trade_date)                 AS first_trade,
    MAX(trade_date)                 AS last_trade,
    ROUND(COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT trade_date), 0), 2)
                                    AS avg_trades_per_active_day
FROM fact_trades;


-- @query: 03_win_rate
-- @desc: Win rate plus the payoff ratio it has to be judged against. A 35%
--        win rate is excellent at 3R and catastrophic at 0.5R, so neither
--        number means anything alone.
SELECT
    COUNT(*)                                                AS total_trades,
    SUM(is_win)                                             AS wins,
    COUNT(*) - SUM(is_win)                                  AS losses,
    ROUND(AVG(is_win) * 100.0, 2)                           AS win_rate_pct,
    ROUND(AVG(CASE WHEN is_win = 1 THEN net_profit END), 2) AS avg_win,
    ROUND(AVG(CASE WHEN is_win = 0 THEN net_profit END), 2) AS avg_loss,
    ROUND(
        ABS(AVG(CASE WHEN is_win = 1 THEN net_profit END))
      / NULLIF(ABS(AVG(CASE WHEN is_win = 0 THEN net_profit END)), 0), 3
    )                                                       AS payoff_ratio,
    -- Break-even win rate implied by that payoff ratio.
    ROUND(
        100.0 / (1.0 +
            ABS(AVG(CASE WHEN is_win = 1 THEN net_profit END))
          / NULLIF(ABS(AVG(CASE WHEN is_win = 0 THEN net_profit END)), 0)
        ), 2
    )                                                       AS breakeven_win_rate_pct
FROM fact_trades;


-- @query: 04_average_profit
-- @desc: Average winning trade, in dollars and in R units. The median is
--        reported alongside the mean because P&L is heavily right-skewed —
--        a handful of outsized winners drag the mean well above the typical
--        trade, and quoting only the mean overstates the routine result.
--        SQLite has no MEDIAN(), so it is computed by the standard
--        ORDER BY / LIMIT / OFFSET trick (LIMIT 2 for even counts, 1 for odd).
WITH wins AS (
    SELECT * FROM fact_trades WHERE is_win = 1
)
SELECT
    COUNT(*)                            AS winning_trades,
    ROUND(AVG(net_profit), 2)           AS avg_profit_usd,
    ROUND((
        SELECT AVG(net_profit) FROM (
            SELECT net_profit FROM wins
            ORDER BY net_profit
            LIMIT 2 - (SELECT COUNT(*) FROM wins) % 2
            OFFSET (SELECT (COUNT(*) - 1) / 2 FROM wins)
        )
    ), 2)                               AS median_profit_usd,
    ROUND(AVG(r_multiple), 3)           AS avg_profit_r,
    ROUND(MAX(net_profit), 2)           AS largest_win,
    ROUND(AVG(trade_duration_min), 1)   AS avg_duration_min
FROM wins;


-- @query: 05_average_loss
-- @desc: Average losing trade. avg_loss_r materially worse than -1.0 means
--        stops are being blown through rather than honoured.
SELECT
    COUNT(*)                            AS losing_trades,
    ROUND(AVG(net_profit), 2)           AS avg_loss_usd,
    ROUND(AVG(r_multiple), 3)           AS avg_loss_r,
    ROUND(MIN(net_profit), 2)           AS largest_loss,
    ROUND(AVG(trade_duration_min), 1)   AS avg_duration_min,
    SUM(CASE WHEN r_multiple < -1.05 THEN 1 ELSE 0 END)
                                        AS trades_worse_than_1R,
    ROUND(
        SUM(CASE WHEN r_multiple < -1.05 THEN 1 ELSE 0 END) * 100.0
      / NULLIF(COUNT(*), 0), 2
    )                                   AS pct_stop_overrun
FROM fact_trades
WHERE is_win = 0;


-- @query: 06_profit_by_asset
-- @desc: Per-instrument P&L with profit factor and fee drag.
SELECT
    asset,
    asset_class,
    COUNT(*)                                        AS trades,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(SUM(fees), 2)                             AS fees,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_loss), 0), 3)
                                                    AS profit_factor,
    ROUND(AVG(r_multiple), 4)                       AS avg_r,
    ROUND(SUM(net_profit) / NULLIF(COUNT(*), 0), 2) AS expectancy_usd
FROM fact_trades
GROUP BY asset, asset_class
ORDER BY net_profit DESC;


-- @query: 07_profit_by_month
-- @desc: Monthly P&L with a running cumulative total (window function).
SELECT
    year_month,
    COUNT(*)                                        AS trades,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(SUM(SUM(net_profit)) OVER (ORDER BY year_month
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2)
                                                    AS cumulative_profit,
    ROUND(AVG(risk_pct), 3)                         AS avg_risk_pct
FROM fact_trades
GROUP BY year_month
ORDER BY year_month;


-- @query: 08_profit_by_week
-- @desc: ISO-week P&L. Weekly grain is the shortest window where a discretionary
--        trader's results carry any signal at all.
SELECT
    year_week,
    MIN(trade_date)                                 AS week_start,
    COUNT(*)                                        AS trades,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(SUM(SUM(net_profit)) OVER (ORDER BY year_week
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2)
                                                    AS cumulative_profit
FROM fact_trades
GROUP BY year_week
ORDER BY year_week;


-- @query: 09_profit_by_strategy
-- @desc: Strategy scorecard. expectancy_r is the ranking column — dollar P&L
--        merely rewards whichever strategy was sized biggest.
SELECT
    strategy,
    COUNT(*)                                        AS trades,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(AVG(risk_reward_ratio), 2)                AS avg_planned_rr,
    ROUND(AVG(realised_rr), 3)                      AS avg_realised_rr,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(SUM(fees), 2)                             AS fees,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_loss), 0), 3)
                                                    AS profit_factor,
    ROUND(AVG(r_multiple), 4)                       AS expectancy_r,
    ROUND(AVG(trade_duration_min), 1)               AS avg_duration_min
FROM fact_trades
GROUP BY strategy
ORDER BY expectancy_r DESC;


-- @query: 10_best_trading_session
-- @desc: Session ranking. Ordered by expectancy per trade, not total P&L, so a
--        session does not win merely by having the most trades in it.
SELECT
    trading_session,
    COUNT(*)                                        AS trades,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(AVG(net_profit), 2)                       AS expectancy_usd,
    ROUND(AVG(r_multiple), 4)                       AS expectancy_r,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_loss), 0), 3)
                                                    AS profit_factor
FROM fact_trades
GROUP BY trading_session
ORDER BY expectancy_r DESC;


-- @query: 11_worst_trading_session
-- @desc: The same ranking inverted, with the hour-level detail needed to act
--        on it (which hours inside the losing session actually bleed).
SELECT
    trading_session,
    entry_hour,
    COUNT(*)                                        AS trades,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(AVG(r_multiple), 4)                       AS expectancy_r
FROM fact_trades
GROUP BY trading_session, entry_hour
HAVING COUNT(*) >= 30            -- suppress thin buckets
ORDER BY expectancy_r ASC
LIMIT 15;


-- @query: 12_longest_winning_streak
-- @desc: Longest consecutive run of winners, per trader.
--        Classic gaps-and-islands: subtracting a dense rank from a partitioned
--        rank yields a constant key for each unbroken run.
WITH seq AS (
    SELECT
        trader_id,
        trade_id,
        entry_datetime,
        is_win,
        ROW_NUMBER() OVER (PARTITION BY trader_id ORDER BY entry_datetime)
      - ROW_NUMBER() OVER (PARTITION BY trader_id, is_win ORDER BY entry_datetime)
            AS run_key
    FROM fact_trades
),
runs AS (
    SELECT
        trader_id,
        run_key,
        COUNT(*)              AS streak_length,
        MIN(entry_datetime)   AS streak_start,
        MAX(entry_datetime)   AS streak_end
    FROM seq
    WHERE is_win = 1
    GROUP BY trader_id, run_key
)
SELECT trader_id, streak_length, streak_start, streak_end
FROM runs
ORDER BY streak_length DESC, streak_start
LIMIT 10;


-- @query: 13_longest_losing_streak
-- @desc: The mirror image — the risk-management question. A long losing run
--        combined with a rising risk_pct is the signature of revenge trading.
WITH seq AS (
    SELECT
        trader_id,
        entry_datetime,
        is_win,
        risk_pct,
        ROW_NUMBER() OVER (PARTITION BY trader_id ORDER BY entry_datetime)
      - ROW_NUMBER() OVER (PARTITION BY trader_id, is_win ORDER BY entry_datetime)
            AS run_key
    FROM fact_trades
),
runs AS (
    SELECT
        trader_id,
        run_key,
        COUNT(*)            AS streak_length,
        MIN(entry_datetime) AS streak_start,
        MAX(entry_datetime) AS streak_end,
        ROUND(AVG(risk_pct), 3) AS avg_risk_pct_during_streak
    FROM seq
    WHERE is_win = 0
    GROUP BY trader_id, run_key
)
SELECT trader_id, streak_length, streak_start, streak_end, avg_risk_pct_during_streak
FROM runs
ORDER BY streak_length DESC, streak_start
LIMIT 10;


-- @query: 14_top_10_profitable_days
-- @desc: The best sessions on the desk, and what drove them.
SELECT
    trade_date,
    COUNT(*)                                        AS trades,
    COUNT(DISTINCT trader_id)                       AS traders,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(MAX(net_profit), 2)                       AS best_single_trade,
    (SELECT f2.strategy
       FROM fact_trades f2
      WHERE f2.trade_date = f.trade_date
      GROUP BY f2.strategy
      ORDER BY SUM(f2.net_profit) DESC
      LIMIT 1)                                      AS top_strategy
FROM fact_trades f
GROUP BY trade_date
ORDER BY net_profit DESC
LIMIT 10;


-- @query: 15_average_trade_duration
-- @desc: Holding time by outcome. Losers held materially LONGER than winners is
--        the disposition effect — cutting winners early, letting losers run.
SELECT
    win_loss,
    COUNT(*)                                    AS trades,
    ROUND(AVG(trade_duration_min), 1)           AS avg_duration_min,
    ROUND(AVG(trade_duration_min) / 60.0, 2)    AS avg_duration_hours,
    MIN(trade_duration_min)                     AS min_duration_min,
    MAX(trade_duration_min)                     AS max_duration_min
FROM fact_trades
GROUP BY win_loss

UNION ALL

SELECT
    'ALL',
    COUNT(*),
    ROUND(AVG(trade_duration_min), 1),
    ROUND(AVG(trade_duration_min) / 60.0, 2),
    MIN(trade_duration_min),
    MAX(trade_duration_min)
FROM fact_trades;


-- @query: 16_highest_drawdown
-- @desc: Peak-to-trough drawdown of the DESK equity curve, derived in SQL with
--        a running maximum rather than exported to a spreadsheet.
WITH daily AS (
    SELECT trade_date, SUM(net_profit) AS net_pnl
    FROM fact_trades
    GROUP BY trade_date
),
curve AS (
    SELECT
        trade_date,
        net_pnl,
        SUM(net_pnl) OVER (ORDER BY trade_date
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_pnl
    FROM daily
),
dd AS (
    SELECT
        trade_date,
        cum_pnl,
        MAX(cum_pnl) OVER (ORDER BY trade_date
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_peak
    FROM curve
)
SELECT
    trade_date                                  AS trough_date,
    ROUND(cum_pnl, 2)                           AS cumulative_pnl,
    ROUND(running_peak, 2)                      AS running_peak,
    ROUND(running_peak - cum_pnl, 2)            AS drawdown_usd,
    ROUND((running_peak - cum_pnl) * 100.0
          / NULLIF(430000.0 + running_peak, 0), 3) AS drawdown_pct_of_equity
FROM dd
ORDER BY drawdown_usd DESC
LIMIT 10;


-- @query: 17_most_profitable_asset
-- @desc: Best instrument ranked by expectancy per trade, with a volume floor so
--        a lucky 20-trade sample cannot take the top slot.
SELECT
    asset,
    asset_class,
    COUNT(*)                                        AS trades,
    ROUND(SUM(net_profit), 2)                       AS net_profit,
    ROUND(AVG(net_profit), 2)                       AS expectancy_usd,
    ROUND(AVG(r_multiple), 4)                       AS expectancy_r,
    ROUND(AVG(is_win) * 100.0, 2)                   AS win_rate_pct,
    ROUND(SUM(gross_profit) / NULLIF(SUM(gross_loss), 0), 3)
                                                    AS profit_factor
FROM fact_trades
GROUP BY asset, asset_class
HAVING COUNT(*) >= 200
ORDER BY expectancy_r DESC;


-- @query: 18_risk_reward_analysis
-- @desc: Does taking a wider target actually pay? Groups by planned-RR band and
--        compares the realised win rate against the break-even rate that band
--        mathematically requires — the single most revealing table in the deck.
SELECT
    rr_bucket,
    COUNT(*)                                        AS trades,
    ROUND(AVG(risk_reward_ratio), 2)                AS avg_planned_rr,
    ROUND(AVG(is_win) * 100.0, 2)                   AS actual_win_rate_pct,
    ROUND(100.0 / (1.0 + AVG(risk_reward_ratio)), 2)
                                                    AS breakeven_win_rate_pct,
    ROUND(AVG(is_win) * 100.0 - 100.0 / (1.0 + AVG(risk_reward_ratio)), 2)
                                                    AS edge_pp,
    ROUND(AVG(realised_rr), 3)                      AS avg_realised_rr,
    ROUND(AVG(r_multiple), 4)                       AS expectancy_r,
    ROUND(SUM(net_profit), 2)                       AS net_profit
FROM fact_trades
GROUP BY rr_bucket
ORDER BY avg_planned_rr;


-- @query: 19_monthly_growth
-- @desc: Month-over-month growth of the cumulative equity curve, using LAG to
--        reference the prior month without a self-join.
WITH monthly AS (
    SELECT
        year_month,
        SUM(net_profit) AS net_pnl,
        COUNT(*)        AS trades
    FROM fact_trades
    GROUP BY year_month
),
cumulative AS (
    SELECT
        year_month,
        trades,
        net_pnl,
        430000.0 + SUM(net_pnl) OVER (ORDER BY year_month
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS equity
    FROM monthly
)
SELECT
    year_month,
    trades,
    ROUND(net_pnl, 2)                                       AS net_pnl,
    ROUND(equity, 2)                                        AS equity,
    ROUND(LAG(equity) OVER (ORDER BY year_month), 2)        AS prev_equity,
    ROUND((equity - LAG(equity) OVER (ORDER BY year_month)) * 100.0
          / NULLIF(LAG(equity) OVER (ORDER BY year_month), 0), 3)
                                                            AS mom_growth_pct
FROM cumulative
ORDER BY year_month;


-- @query: 20_cumulative_profit
-- @desc: The equity curve itself, at daily grain, with the running drawdown
--        alongside. This is the query behind the dashboard's headline chart.
--        Note the two-step CTE: a window function may not be nested inside
--        another window function, so the running SUM is materialised first and
--        the running MAX is then taken over that result.
WITH daily AS (
    SELECT trade_date, COUNT(*) AS trades, SUM(net_profit) AS net_pnl
    FROM fact_trades
    GROUP BY trade_date
),
running AS (
    SELECT
        trade_date,
        trades,
        net_pnl,
        SUM(net_pnl) OVER (ORDER BY trade_date
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_pnl
    FROM daily
)
SELECT
    trade_date,
    trades,
    ROUND(net_pnl, 2)                                       AS daily_pnl,
    ROUND(cum_pnl, 2)                                       AS cumulative_pnl,
    -- 430,000 = combined opening capital of the twelve trader accounts.
    ROUND(430000.0 + cum_pnl, 2)                            AS equity,
    ROUND(MAX(cum_pnl) OVER w, 2)                           AS peak_cumulative,
    ROUND(MAX(cum_pnl) OVER w - cum_pnl, 2)                 AS drawdown_usd
FROM running
WINDOW w AS (ORDER BY trade_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
ORDER BY trade_date;


-- @query: 21_trader_ranking
-- @desc: Desk leaderboard. Ranked on expectancy in R units — the only measure
--        that is fair across traders running different account sizes — with
--        profit factor, max drawdown and tilt rate as the risk-adjusted context.
WITH per_trader AS (
    SELECT
        f.trader_id,
        t.trader_name,
        COUNT(*)                                            AS trades,
        ROUND(AVG(f.is_win) * 100.0, 2)                     AS win_rate_pct,
        ROUND(SUM(f.net_profit), 2)                         AS net_profit,
        ROUND(SUM(f.fees), 2)                               AS fees_paid,
        ROUND(AVG(f.r_multiple), 4)                         AS expectancy_r,
        ROUND(SUM(f.r_multiple), 2)                         AS total_r,
        ROUND(SUM(f.gross_profit) / NULLIF(SUM(f.gross_loss), 0), 3)
                                                            AS profit_factor,
        ROUND(MAX(f.drawdown_pct), 2)                       AS max_drawdown_pct,
        ROUND(AVG(f.risk_pct), 3)                           AS avg_risk_pct,
        ROUND(AVG(f.is_tilt_state) * 100.0, 2)              AS tilt_rate_pct,
        MAX(f.loss_streak)                                  AS worst_losing_streak
    FROM fact_trades f
    JOIN dim_trader t ON t.trader_id = f.trader_id
    GROUP BY f.trader_id, t.trader_name
)
SELECT
    RANK() OVER (ORDER BY expectancy_r DESC) AS rank,
    *,
    CASE
        WHEN profit_factor >= 1.30 AND max_drawdown_pct < 25 THEN 'Scale up'
        WHEN profit_factor >= 1.00                           THEN 'Maintain'
        WHEN tilt_rate_pct > 20                              THEN 'Behavioural coaching'
        ELSE                                                      'Reduce size / review'
    END AS recommended_action
FROM per_trader
ORDER BY expectancy_r DESC;
