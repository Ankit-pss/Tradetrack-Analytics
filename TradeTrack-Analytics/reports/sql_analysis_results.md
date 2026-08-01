# SQL Analysis — Executed Results

Every query in `sql/02_analysis_queries.sql` executed against the SQLite warehouse (`data/tradetrack.db`). Regenerate with `python python/run_sql_analysis.py`.

**21 queries · 21 passed**

---

## 01 Total Profit

> Headline P&L. Splits gross from fees so the cost of trading is explicit.

```sql
SELECT
    ROUND(SUM(profit_loss), 2)                              AS gross_profit,
    ROUND(SUM(fees), 2)                                     AS total_fees,
    ROUND(SUM(net_profit), 2)                               AS net_profit,
    ROUND(SUM(fees) * 100.0 / NULLIF(ABS(SUM(profit_loss)), 0), 2)
                                                            AS fees_pct_of_gross
FROM fact_trades
```

|   gross_profit |   total_fees |   net_profit |   fees_pct_of_gross |
|---------------:|-------------:|-------------:|--------------------:|
|    486,550.850 |  266,366.860 |  220,183.990 |              54.750 |

---

## 02 Total Trades

> Volume overview — trades, traders, instruments and the active window.

```sql
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
FROM fact_trades
```

|   total_trades |   traders |   assets_traded |   strategies_used |   active_days | first_trade   | last_trade   |   avg_trades_per_active_day |
|---------------:|----------:|----------------:|------------------:|--------------:|:--------------|:-------------|----------------------------:|
|          10781 |        12 |               6 |                 7 |           855 | 2024-01-01    | 2026-06-30   |                      12.610 |

---

## 03 Win Rate

> Win rate plus the payoff ratio it has to be judged against. A 35% win rate is excellent at 3R and catastrophic at 0.5R, so neither number means anything alone.

```sql
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
FROM fact_trades
```

|   total_trades |      wins |    losses |   win_rate_pct |   avg_win |   avg_loss |   payoff_ratio |   breakeven_win_rate_pct |
|---------------:|----------:|----------:|---------------:|----------:|-----------:|---------------:|-------------------------:|
|     10,781.000 | 3,787.000 | 6,994.000 |         35.130 |   890.220 |   -450.540 |          1.976 |                   33.600 |

---

## 04 Average Profit

> Average winning trade, in dollars and in R units. The median is reported alongside the mean because P&L is heavily right-skewed — a handful of outsized winners drag the mean well above the typical trade, and quoting only the mean overstates the routine result. SQLite has no MEDIAN(), so it is computed by the standard ORDER BY / LIMIT / OFFSET trick (LIMIT 2 for even counts, 1 for odd).

```sql
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
FROM wins
```

|   winning_trades |   avg_profit_usd |   median_profit_usd |   avg_profit_r |   largest_win |   avg_duration_min |
|-----------------:|-----------------:|--------------------:|---------------:|--------------:|-------------------:|
|        3,787.000 |          890.220 |             508.910 |          1.799 |    13,746.870 |            197.800 |

---

## 05 Average Loss

> Average losing trade. avg_loss_r materially worse than -1.0 means stops are being blown through rather than honoured.

```sql
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
WHERE is_win = 0
```

|   losing_trades |   avg_loss_usd |   avg_loss_r |   largest_loss |   avg_duration_min |   trades_worse_than_1R |   pct_stop_overrun |
|----------------:|---------------:|-------------:|---------------:|-------------------:|-----------------------:|-------------------:|
|       6,994.000 |       -450.540 |       -0.967 |     -5,061.010 |            285.800 |              1,947.000 |             27.840 |

---

## 06 Profit By Asset

> Per-instrument P&L with profit factor and fee drag.

```sql
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
ORDER BY net_profit DESC
```

| asset   | asset_class   |   trades |   win_rate_pct |   net_profit |       fees |   profit_factor |   avg_r |   expectancy_usd |
|:--------|:--------------|---------:|---------------:|-------------:|-----------:|----------------:|--------:|-----------------:|
| BTC     | Crypto        |     2612 |         35.530 |   78,682.480 | 66,008.820 |           1.105 |   0.023 |           30.120 |
| NASDAQ  | Index         |     1716 |         34.620 |   57,710.660 | 28,765.040 |           1.113 |   0.016 |           33.630 |
| GOLD    | Commodity     |     1580 |         35.890 |   37,822.390 | 56,283.960 |           1.085 |  -0.015 |           23.940 |
| ETH     | Crypto        |     2039 |         34.090 |   29,778.260 | 41,901.820 |           1.049 |  -0.001 |           14.600 |
| US30    | Index         |     1388 |         35.880 |   15,195.910 | 31,977.240 |           1.038 |   0.003 |           10.950 |
| EURUSD  | Forex         |     1446 |         34.920 |      994.290 | 41,429.980 |           1.002 |  -0.010 |            0.690 |

---

## 07 Profit By Month

> Monthly P&L with a running cumulative total (window function).

```sql
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
ORDER BY year_month
```

| year_month   |   trades |   win_rate_pct |   net_profit |   cumulative_profit |   avg_risk_pct |
|:-------------|---------:|---------------:|-------------:|--------------------:|---------------:|
| 2024-01      |      383 |         36.290 |   -8,392.320 |          -8,392.320 |          1.448 |
| 2024-02      |      439 |         33.710 |  -19,729.360 |         -28,121.680 |          1.503 |
| 2024-03      |      496 |         30.850 |  -27,624.480 |         -55,746.160 |          1.589 |
| 2024-04      |      466 |         36.270 |   38,409.700 |         -17,336.460 |          1.546 |
| 2024-05      |      482 |         31.950 |   -4,282.110 |         -21,618.570 |          1.566 |
| 2024-06      |      448 |         33.260 |    7,155.930 |         -14,462.640 |          1.402 |
| 2024-07      |      466 |         32.190 |  -23,614.790 |         -38,077.430 |          1.588 |
| 2024-08      |      438 |         36.530 |   16,558.440 |         -21,518.990 |          1.480 |
| 2024-09      |      331 |         38.970 |   20,546.240 |            -972.750 |          1.366 |
| 2024-10      |      378 |         31.220 |  -14,180.940 |         -15,153.690 |          1.296 |
| 2024-11      |      403 |         35.480 |    6,313.700 |          -8,839.990 |          1.319 |
| 2024-12      |      392 |         31.630 |  -11,790.550 |         -20,630.540 |          1.369 |
| 2025-01      |      357 |         35.850 |   -3,941.170 |         -24,571.710 |          1.287 |
| 2025-02      |      314 |         36.940 |    3,569.440 |         -21,002.270 |          1.315 |
| 2025-03      |      345 |         32.170 |  -14,108.490 |         -35,110.760 |          1.279 |

_(30 rows returned, first 15 shown)_

---

## 08 Profit By Week

> ISO-week P&L. Weekly grain is the shortest window where a discretionary trader's results carry any signal at all.

```sql
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
ORDER BY year_week
```

| year_week   | week_start   |   trades |   win_rate_pct |   net_profit |   cumulative_profit |
|:------------|:-------------|---------:|---------------:|-------------:|--------------------:|
| 2024-W01    | 2024-01-01   |       77 |         40.260 |   -2,452.030 |          -2,452.030 |
| 2024-W02    | 2024-01-08   |       90 |         35.560 |   -7,544.180 |          -9,996.210 |
| 2024-W03    | 2024-01-15   |       71 |         35.210 |   -4,591.890 |         -14,588.100 |
| 2024-W04    | 2024-01-22   |       87 |         36.780 |    5,700.350 |          -8,887.750 |
| 2024-W05    | 2024-01-29   |       97 |         32.990 |   -1,295.550 |         -10,183.300 |
| 2024-W06    | 2024-02-05   |       98 |         35.710 |    1,574.240 |          -8,609.060 |
| 2024-W07    | 2024-02-12   |      120 |         25.830 |  -13,913.330 |         -22,522.390 |
| 2024-W08    | 2024-02-19   |      112 |         32.140 |   -6,098.050 |         -28,620.440 |
| 2024-W09    | 2024-02-26   |       83 |         42.170 |   -2,914.400 |         -31,534.840 |
| 2024-W10    | 2024-03-04   |      113 |         31.860 |   -3,159.560 |         -34,694.400 |
| 2024-W11    | 2024-03-11   |      101 |         34.650 |      460.460 |         -34,233.940 |
| 2024-W12    | 2024-03-18   |      135 |         28.890 |   -8,108.380 |         -42,342.320 |
| 2024-W13    | 2024-03-25   |      134 |         30.600 |  -13,403.840 |         -55,746.160 |
| 2024-W14    | 2024-04-01   |      133 |         29.320 |      687.160 |         -55,059.000 |
| 2024-W15    | 2024-04-08   |      122 |         32.790 |   11,291.580 |         -43,767.420 |

_(131 rows returned, first 15 shown)_

---

## 09 Profit By Strategy

> Strategy scorecard. expectancy_r is the ranking column — dollar P&L merely rewards whichever strategy was sized biggest.

```sql
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
ORDER BY expectancy_r DESC
```

| strategy          |   trades |   win_rate_pct |   avg_planned_rr |   avg_realised_rr |   net_profit |        fees |   profit_factor |   expectancy_r |   avg_duration_min |
|:------------------|---------:|---------------:|-----------------:|------------------:|-------------:|------------:|----------------:|---------------:|-------------------:|
| Trend Following   |     1933 |         30.010 |            3.100 |             0.182 |  167,254.240 |  29,045.750 |           1.275 |          0.149 |            316.500 |
| Swing             |     1117 |         23.990 |            3.780 |             0.076 |   16,947.320 |  11,645.630 |           1.042 |          0.056 |          1,569.800 |
| Mean Reversion    |     1734 |         45.500 |            1.420 |             0.078 |   85,403.740 |  31,717.200 |           1.206 |          0.040 |             78.300 |
| Breakout          |     2079 |         30.400 |            2.510 |             0.043 |   76,290.800 |  41,176.220 |           1.121 |          0.002 |             63.000 |
| Order Block (SMC) |      849 |         28.500 |            2.790 |             0.043 |    4,853.020 |  17,644.190 |           1.018 |         -0.003 |            103.800 |
| News Trading      |     1006 |         27.830 |            2.490 |            -0.078 |  -24,736.650 |  14,284.800 |           0.920 |         -0.109 |             13.000 |
| Scalping          |     2063 |         48.280 |            1.090 |            -0.009 | -105,828.480 | 120,853.070 |           0.799 |         -0.126 |              7.100 |

---

## 10 Best Trading Session

> Session ranking. Ordered by expectancy per trade, not total P&L, so a session does not win merely by having the most trades in it.

```sql
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
ORDER BY expectancy_r DESC
```

| trading_session   |   trades |   win_rate_pct |   net_profit |   expectancy_usd |   expectancy_r |   profit_factor |
|:------------------|---------:|---------------:|-------------:|-----------------:|---------------:|----------------:|
| London            |     4097 |         36.560 |  256,585.450 |           62.630 |          0.052 |           1.222 |
| New York          |     4033 |         35.310 |   43,660.250 |           10.830 |          0.015 |           1.036 |
| Asia              |     2651 |         32.630 |  -80,061.710 |          -30.200 |         -0.084 |           0.899 |

---

## 11 Worst Trading Session

> The same ranking inverted, with the hour-level detail needed to act on it (which hours inside the losing session actually bleed).

```sql
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
LIMIT 15
```

| trading_session   |   entry_hour |   trades |   win_rate_pct |   net_profit |   expectancy_r |
|:------------------|-------------:|---------:|---------------:|-------------:|---------------:|
| Asia              |            6 |      335 |         31.040 |   -8,744.760 |         -0.155 |
| Asia              |            0 |      315 |         33.020 |   -9,600.410 |         -0.125 |
| Asia              |            1 |      325 |         32.920 |  -20,003.150 |         -0.083 |
| Asia              |            3 |      352 |         33.240 |   -7,768.210 |         -0.079 |
| Asia              |            4 |      316 |         31.960 |  -25,432.370 |         -0.071 |
| Asia              |            5 |      350 |         33.140 |   -9,351.830 |         -0.071 |
| Asia              |            7 |      337 |         33.530 |   -6,093.210 |         -0.048 |
| Asia              |            2 |      321 |         32.090 |    6,932.230 |         -0.043 |
| London            |           10 |      800 |         34.000 |   38,998.240 |         -0.036 |
| New York          |           16 |      490 |         35.100 |   -9,993.460 |         -0.036 |
| New York          |           18 |      510 |         35.100 |  -19,224.880 |         -0.030 |
| New York          |           17 |      497 |         34.000 |    9,765.250 |         -0.027 |
| London            |            9 |      846 |         33.690 |    2,481.760 |         -0.022 |
| London            |           12 |      835 |         34.370 |   36,265.200 |         -0.008 |
| New York          |           13 |      534 |         36.140 |   -1,226.320 |          0.004 |

---

## 12 Longest Winning Streak

> Longest consecutive run of winners, per trader. Classic gaps-and-islands: subtracting a dense rank from a partitioned rank yields a constant key for each unbroken run.

```sql
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
LIMIT 10
```

| trader_id   |   streak_length | streak_start        | streak_end          |
|:------------|----------------:|:--------------------|:--------------------|
| TR-001      |               8 | 2025-03-26 19:31:19 | 2025-04-10 05:15:37 |
| TR-006      |               7 | 2025-03-07 19:26:11 | 2025-03-12 15:12:28 |
| TR-001      |               7 | 2025-07-14 07:32:23 | 2025-07-17 18:01:15 |
| TR-003      |               7 | 2025-09-07 14:07:05 | 2025-09-15 09:54:37 |
| TR-012      |               7 | 2026-03-24 19:22:17 | 2026-03-27 09:54:07 |
| TR-008      |               6 | 2024-05-03 08:08:32 | 2024-05-08 20:24:02 |
| TR-004      |               6 | 2024-05-08 08:36:08 | 2024-05-11 12:00:16 |
| TR-008      |               6 | 2024-07-15 13:03:21 | 2024-07-18 13:54:01 |
| TR-009      |               6 | 2024-12-27 11:19:13 | 2025-01-03 11:45:47 |
| TR-002      |               6 | 2025-05-02 16:26:16 | 2025-05-14 15:29:01 |

---

## 13 Longest Losing Streak

> The mirror image — the risk-management question. A long losing run combined with a rising risk_pct is the signature of revenge trading.

```sql
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
LIMIT 10
```

| trader_id   |   streak_length | streak_start        | streak_end          |   avg_risk_pct_during_streak |
|:------------|----------------:|:--------------------|:--------------------|-----------------------------:|
| TR-005      |              30 | 2024-04-02 05:49:59 | 2024-04-14 19:25:05 |                        2.228 |
| TR-003      |              21 | 2024-02-15 02:08:22 | 2024-02-25 09:11:46 |                        1.660 |
| TR-010      |              21 | 2024-04-28 14:48:44 | 2024-05-09 08:20:28 |                        2.551 |
| TR-008      |              18 | 2025-05-05 09:08:05 | 2025-05-22 10:46:24 |                        1.116 |
| TR-002      |              17 | 2024-02-28 08:50:59 | 2024-03-11 15:38:42 |                        1.226 |
| TR-008      |              17 | 2025-06-16 19:56:54 | 2025-06-24 18:10:16 |                        1.278 |
| TR-005      |              16 | 2024-05-18 19:31:36 | 2024-05-30 16:19:11 |                        2.547 |
| TR-001      |              15 | 2024-05-17 03:49:06 | 2024-05-27 19:55:55 |                        1.378 |
| TR-012      |              15 | 2024-10-23 12:15:05 | 2024-10-31 19:18:39 |                        1.635 |
| TR-008      |              15 | 2025-02-14 19:31:44 | 2025-03-03 19:26:29 |                        1.051 |

---

## 14 Top 10 Profitable Days

> The best sessions on the desk, and what drove them.

```sql
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
LIMIT 10
```

| trade_date   |   trades |   traders |   win_rate_pct |   net_profit |   best_single_trade | top_strategy      |
|:-------------|---------:|----------:|---------------:|-------------:|--------------------:|:------------------|
| 2025-10-23   |        3 |         1 |        100.000 |   20,005.600 |          12,440.870 | Swing             |
| 2025-12-15   |       12 |         3 |         66.670 |   17,004.700 |           8,359.080 | Order Block (SMC) |
| 2026-03-24   |       13 |         5 |         61.540 |   16,829.370 |           9,025.380 | Breakout          |
| 2025-07-30   |       13 |         5 |         61.540 |   15,437.610 |          11,544.640 | News Trading      |
| 2026-03-08   |        6 |         1 |         50.000 |   14,520.500 |          11,637.050 | Swing             |
| 2025-10-07   |       21 |         7 |         57.140 |   14,096.840 |           5,816.160 | Order Block (SMC) |
| 2026-05-15   |       10 |         4 |         60.000 |   12,636.830 |           8,613.590 | Trend Following   |
| 2026-02-13   |       22 |         6 |         54.550 |   12,445.190 |           8,354.280 | Trend Following   |
| 2026-01-21   |       17 |         6 |         41.180 |   12,151.030 |           5,955.960 | Trend Following   |
| 2025-06-10   |       15 |         6 |         53.330 |   11,025.400 |           6,776.990 | Swing             |

---

## 15 Average Trade Duration

> Holding time by outcome. Losers held materially LONGER than winners is the disposition effect — cutting winners early, letting losers run.

```sql
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
FROM fact_trades
```

| win_loss   |   trades |   avg_duration_min |   avg_duration_hours |   min_duration_min |   max_duration_min |
|:-----------|---------:|-------------------:|---------------------:|-------------------:|-------------------:|
| Loss       |     6994 |            285.800 |                4.760 |              1.000 |          5,760.000 |
| Win        |     3787 |            197.800 |                3.300 |              1.000 |          5,760.000 |
| ALL        |    10781 |            254.900 |                4.250 |              1.000 |          5,760.000 |

---

## 16 Highest Drawdown

> Peak-to-trough drawdown of the DESK equity curve, derived in SQL with a running maximum rather than exported to a spreadsheet.

```sql
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
LIMIT 10
```

| trough_date   |   cumulative_pnl |   running_peak |   drawdown_usd |   drawdown_pct_of_equity |
|:--------------|-----------------:|---------------:|---------------:|-------------------------:|
| 2024-04-02    |      -61,581.180 |        910.890 |     62,492.070 |                   14.502 |
| 2024-04-01    |      -58,055.210 |        910.890 |     58,966.100 |                   13.684 |
| 2024-04-08    |      -56,730.980 |        910.890 |     57,641.870 |                   13.377 |
| 2024-03-31    |      -55,746.160 |        910.890 |     56,657.050 |                   13.148 |
| 2024-04-04    |      -55,209.530 |        910.890 |     56,120.420 |                   13.024 |
| 2024-04-07    |      -55,059.000 |        910.890 |     55,969.890 |                   12.989 |
| 2024-04-06    |      -54,410.160 |        910.890 |     55,321.050 |                   12.838 |
| 2024-04-03    |      -54,371.580 |        910.890 |     55,282.470 |                   12.829 |
| 2024-04-05    |      -53,968.880 |        910.890 |     54,879.770 |                   12.736 |
| 2024-04-09    |      -52,646.660 |        910.890 |     53,557.550 |                   12.429 |

---

## 17 Most Profitable Asset

> Best instrument ranked by expectancy per trade, with a volume floor so a lucky 20-trade sample cannot take the top slot.

```sql
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
ORDER BY expectancy_r DESC
```

| asset   | asset_class   |   trades |   net_profit |   expectancy_usd |   expectancy_r |   win_rate_pct |   profit_factor |
|:--------|:--------------|---------:|-------------:|-----------------:|---------------:|---------------:|----------------:|
| BTC     | Crypto        |     2612 |   78,682.480 |           30.120 |          0.023 |         35.530 |           1.105 |
| NASDAQ  | Index         |     1716 |   57,710.660 |           33.630 |          0.016 |         34.620 |           1.113 |
| US30    | Index         |     1388 |   15,195.910 |           10.950 |          0.003 |         35.880 |           1.038 |
| ETH     | Crypto        |     2039 |   29,778.260 |           14.600 |         -0.001 |         34.090 |           1.049 |
| EURUSD  | Forex         |     1446 |      994.290 |            0.690 |         -0.010 |         34.920 |           1.002 |
| GOLD    | Commodity     |     1580 |   37,822.390 |           23.940 |         -0.015 |         35.890 |           1.085 |

---

## 18 Risk Reward Analysis

> Does taking a wider target actually pay? Groups by planned-RR band and compares the realised win rate against the break-even rate that band mathematically requires — the single most revealing table in the deck.

```sql
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
ORDER BY avg_planned_rr
```

| rr_bucket   |   trades |   avg_planned_rr |   actual_win_rate_pct |   breakeven_win_rate_pct |   edge_pp |   avg_realised_rr |   expectancy_r |   net_profit |
|:------------|---------:|-----------------:|----------------------:|-------------------------:|----------:|------------------:|---------------:|-------------:|
| <1R         |      726 |            0.900 |                52.890 |                   52.550 |     0.340 |             0.001 |         -0.113 |  -40,724.350 |
| 1-2R        |     3618 |            1.400 |                44.310 |                   41.680 |     2.620 |             0.035 |         -0.033 |   36,789.060 |
| 2-3R        |     3665 |            2.550 |                30.830 |                   28.160 |     2.670 |             0.068 |          0.031 |  178,285.710 |
| >3R         |     2772 |            3.590 |                24.170 |                   21.790 |     2.380 |             0.082 |          0.051 |   45,833.570 |

---

## 19 Monthly Growth

> Month-over-month growth of the cumulative equity curve, using LAG to reference the prior month without a self-join.

```sql
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
ORDER BY year_month
```

| year_month   |   trades |     net_pnl |      equity |   prev_equity |   mom_growth_pct |
|:-------------|---------:|------------:|------------:|--------------:|-----------------:|
| 2024-01      |      383 |  -8,392.320 | 421,607.680 |       nan     |          nan     |
| 2024-02      |      439 | -19,729.360 | 401,878.320 |   421,607.680 |           -4.680 |
| 2024-03      |      496 | -27,624.480 | 374,253.840 |   401,878.320 |           -6.874 |
| 2024-04      |      466 |  38,409.700 | 412,663.540 |   374,253.840 |           10.263 |
| 2024-05      |      482 |  -4,282.110 | 408,381.430 |   412,663.540 |           -1.038 |
| 2024-06      |      448 |   7,155.930 | 415,537.360 |   408,381.430 |            1.752 |
| 2024-07      |      466 | -23,614.790 | 391,922.570 |   415,537.360 |           -5.683 |
| 2024-08      |      438 |  16,558.440 | 408,481.010 |   391,922.570 |            4.225 |
| 2024-09      |      331 |  20,546.240 | 429,027.250 |   408,481.010 |            5.030 |
| 2024-10      |      378 | -14,180.940 | 414,846.310 |   429,027.250 |           -3.305 |
| 2024-11      |      403 |   6,313.700 | 421,160.010 |   414,846.310 |            1.522 |
| 2024-12      |      392 | -11,790.550 | 409,369.460 |   421,160.010 |           -2.800 |
| 2025-01      |      357 |  -3,941.170 | 405,428.290 |   409,369.460 |           -0.963 |
| 2025-02      |      314 |   3,569.440 | 408,997.730 |   405,428.290 |            0.880 |
| 2025-03      |      345 | -14,108.490 | 394,889.240 |   408,997.730 |           -3.450 |

_(30 rows returned, first 15 shown)_

---

## 20 Cumulative Profit

> The equity curve itself, at daily grain, with the running drawdown alongside. This is the query behind the dashboard's headline chart. Note the two-step CTE: a window function may not be nested inside another window function, so the running SUM is materialised first and the running MAX is then taken over that result.

```sql
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
ORDER BY trade_date
```

| trade_date   |   trades |   daily_pnl |   cumulative_pnl |      equity |   peak_cumulative |   drawdown_usd |
|:-------------|---------:|------------:|-----------------:|------------:|------------------:|---------------:|
| 2024-01-01   |       15 |     910.890 |          910.890 | 430,910.890 |           910.890 |          0.000 |
| 2024-01-02   |        7 |    -237.180 |          673.710 | 430,673.710 |           910.890 |        237.180 |
| 2024-01-03   |       16 |  -2,716.190 |       -2,042.480 | 427,957.520 |           910.890 |      2,953.370 |
| 2024-01-04   |        9 |    -783.350 |       -2,825.830 | 427,174.170 |           910.890 |      3,736.720 |
| 2024-01-05   |       22 |  -1,467.450 |       -4,293.280 | 425,706.720 |           910.890 |      5,204.170 |
| 2024-01-06   |        7 |     384.240 |       -3,909.040 | 426,090.960 |           910.890 |      4,819.930 |
| 2024-01-07   |        1 |   1,457.010 |       -2,452.030 | 427,547.970 |           910.890 |      3,362.920 |
| 2024-01-08   |       11 |  -1,212.800 |       -3,664.830 | 426,335.170 |           910.890 |      4,575.720 |
| 2024-01-09   |       17 |    -922.060 |       -4,586.890 | 425,413.110 |           910.890 |      5,497.780 |
| 2024-01-10   |        9 |     956.580 |       -3,630.310 | 426,369.690 |           910.890 |      4,541.200 |
| 2024-01-11   |        9 |     184.420 |       -3,445.890 | 426,554.110 |           910.890 |      4,356.780 |
| 2024-01-12   |       32 |  -5,672.550 |       -9,118.440 | 420,881.560 |           910.890 |     10,029.330 |
| 2024-01-13   |        7 |    -173.620 |       -9,292.060 | 420,707.940 |           910.890 |     10,202.950 |
| 2024-01-14   |        5 |    -704.150 |       -9,996.210 | 420,003.790 |           910.890 |     10,907.100 |
| 2024-01-15   |       20 |  -1,390.080 |      -11,386.290 | 418,613.710 |           910.890 |     12,297.180 |

_(855 rows returned, first 15 shown)_

---

## 21 Trader Ranking

> Desk leaderboard. Ranked on expectancy in R units — the only measure that is fair across traders running different account sizes — with profit factor, max drawdown and tilt rate as the risk-adjusted context.

```sql
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
ORDER BY expectancy_r DESC
```

|   rank | trader_id   | trader_name   |   trades |   win_rate_pct |   net_profit |   fees_paid |   expectancy_r |   total_r |   profit_factor |   max_drawdown_pct |   avg_risk_pct |   tilt_rate_pct |   worst_losing_streak | recommended_action   |
|-------:|:------------|:--------------|---------:|---------------:|-------------:|------------:|---------------:|----------:|----------------:|-------------------:|---------------:|----------------:|----------------------:|:---------------------|
|      1 | TR-004      | J. Okafor     |      833 |         41.300 |  198,242.580 |  65,994.290 |          0.147 |   122.090 |           1.280 |             18.670 |          0.890 |           9.600 |                     9 | Maintain             |
|      2 | TR-001      | A. Kapoor     |      967 |         38.680 |   30,241.360 |  34,381.810 |          0.110 |   106.070 |           1.076 |             28.480 |          1.050 |          13.240 |                    15 | Maintain             |
|      3 | TR-006      | K. Watanabe   |     1110 |         38.920 |   46,950.670 |  34,786.150 |          0.088 |    97.930 |           1.119 |             33.010 |          1.169 |          15.590 |                    10 | Maintain             |
|      4 | TR-011      | N. Haddad     |     1074 |         37.060 |   55,046.520 |  48,484.400 |          0.086 |    92.750 |           1.096 |             30.200 |          1.242 |          16.670 |                    11 | Maintain             |
|      5 | TR-008      | R. Sharma     |     1125 |         35.200 |  -19,457.720 |  27,139.830 |          0.003 |     3.150 |           0.946 |             64.180 |          1.121 |          17.330 |                    18 | Reduce size / review |
|      6 | TR-002      | M. Chen       |     1034 |         34.620 |   -3,566.730 |  14,067.830 |         -0.002 |    -1.940 |           0.980 |             44.890 |          1.210 |          17.890 |                    17 | Reduce size / review |
|      7 | TR-012      | T. Bergman    |     1088 |         33.920 |  -15,066.510 |  10,589.410 |         -0.031 |   -33.690 |           0.889 |             74.860 |          1.413 |          20.500 |                    15 | Behavioural coaching |
|      8 | TR-003      | S. Iyer       |     1208 |         32.700 |  -11,678.400 |   7,258.600 |         -0.044 |   -53.560 |           0.873 |             82.390 |          1.591 |          22.520 |                    21 | Behavioural coaching |
|      9 | TR-009      | E. Bauer      |      831 |         31.770 |  -23,246.140 |   8,537.500 |         -0.095 |   -79.210 |           0.800 |             85.110 |          1.360 |          20.820 |                    15 | Behavioural coaching |
|     10 | TR-010      | P. Silva      |      409 |         30.560 |  -10,031.430 |   2,914.160 |         -0.119 |   -48.860 |           0.756 |             86.440 |          2.414 |          25.670 |                    21 | Behavioural coaching |
|     11 | TR-007      | D. Novak      |      727 |         30.950 |  -18,825.280 |   9,868.860 |         -0.128 |   -92.860 |           0.847 |             89.900 |          1.871 |          24.480 |                    14 | Behavioural coaching |
|     12 | TR-005      | L. Fernandez  |      375 |         28.530 |   -8,424.930 |   2,344.020 |         -0.160 |   -60.080 |           0.737 |             86.520 |          2.147 |          27.470 |                    30 | Behavioural coaching |

---

