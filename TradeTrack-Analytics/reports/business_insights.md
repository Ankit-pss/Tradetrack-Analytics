# TradeTrack Analytics — 20 Business Insights

Derived from 10,781 closed trades across 12 traders, Jan 2024 – Jun 2026.

Every figure in this document is computed by `python/generate_insights.py` directly from `trades_clean.csv` — nothing is hand-entered, so the report cannot drift from the data.

Performance is measured in **R** (net P&L ÷ dollars risked) wherever strategies or traders are compared, because dollar P&L only reflects who was sized largest.

---

### 1. The desk is profitable, but the edge is thin

**Finding.** Across 10,781 closed trades the desk netted $220.2K on $430.0K of opening capital (+51.2%, CAGR 18.0%). A profit factor of 1.070 means winners barely cover losers.

**Evidence.** Win rate 35.13% at an average planned 2.32:1 reward:risk. Expectancy is $20 (+0.0048R) per trade — Sharpe 0.80, Sortino 0.95.

**Action.** Treat the aggregate as fragile. A profit factor near 1.05–1.10 is inside the range random variation can produce over this sample, so the priority is removing the identified loss centres below rather than adding size.

### 2. The improving equity curve is survivorship, not improvement

**Finding.** 4 of 12 accounts blew up and stopped trading. The desk's P&L improves sharply in the second half — but that is the losing traders leaving the sample, not the surviving traders getting better.

**Evidence.** 2024 net P&L -$20.6K across 12 active traders; H2-2025 onward $213.6K across 8. Blown accounts: TR-005, TR-007, TR-009, TR-010 (last trades Aug 2024, Sep 2024, Jul 2025, Oct 2025).

**Action.** Never quote the desk-level trend without the active-trader count beside it. Any performance review must be cohort-adjusted or it rewards attrition.

### 3. One hour — 08:00 UTC — carries the desk

**Finding.** The 08:00 UTC hour (the London open) returns +0.212R per trade against a desk average of +0.0048R.

**Evidence.** 802 trades, 42.6% win rate, $113.3K net — 51% of total desk profit from a single hour of the day.

**Action.** Concentrate size in the London open. This is the single highest-conviction scheduling change available and it requires no new strategy.

### 4. The pre-London hours are a persistent loss centre

**Finding.** The 06:00, 00:00, 01:00 UTC hours all return negative expectancy, together costing -$38.3K.

**Evidence.** 06:00 — -0.155R, 31.0% WR, 335 trades · 00:00 — -0.125R, 33.0% WR, 315 trades · 01:00 — -0.083R, 32.9% WR, 325 trades

**Action.** Impose a hard no-trade window before the London session. Thin liquidity widens spreads and stops get taken out on noise.

### 5. London is the best session, Asia the worst

**Finding.** London returns +0.052R per trade; Asia returns -0.084R — a spread of 0.136R on identical strategies.

**Evidence.** Asia — -0.084R, 32.6% WR, -$80.1K, 2,651 trades · London — +0.052R, 36.6% WR, $256.6K, 4,097 trades · New York — +0.015R, 35.3% WR, $43.7K, 4,033 trades

**Action.** Reallocate risk budget from Asia to London. The same playbook produces materially different results depending only on when it is run.

### 6. Wednesday is the most profitable weekday; Friday the least

**Finding.** Wednesday returns +0.076R ($152.8K net), while Friday returns -0.043R (-$51.2K). The midweek block carries the result and the week decays into Friday.

**Evidence.** Mon -0.021R (1,981) · Tue +0.033R (1,930) · Wed +0.076R (2,053) · Thu +0.001R (1,849) · Fri -0.043R (1,897) — weekend (crypto only): -0.042R over 1,071 trades

**Action.** Reduce size on Friday: positions squared into the weekend lose follow-through. Weekend crypto sessions are also negative at -0.042R on thin volume and should be opt-in rather than routine.

### 7. Trend Following is the only strategy with a durable edge

**Finding.** Trend Following returns +0.149R per trade over 1,933 trades ($167.3K net).

**Evidence.** Trend Following +0.149R · Swing +0.056R · Mean Reversion +0.040R · Breakout +0.002R · Order Block (SMC) -0.003R · News Trading -0.109R · Scalping -0.126R

**Action.** Shift allocation toward Trend Following. Its sample size is large enough that the result is unlikely to be noise.

### 8. Scalping is gross-positive and net-negative — fees eat it whole

**Finding.** Scalping generates $15.0K of GROSS profit and pays $120.9K in fees, for -$105.8K net. The strategy is not losing to the market; it is losing to transaction costs.

**Evidence.** Average fee is 11.72% of the amount risked, versus 3.53% for every other strategy — tight stops mean a large notional per unit of risk, and fees scale with notional, not with risk.

**Action.** Either stop trading Scalping or renegotiate commissions. At current rates it needs a materially higher hit rate just to break even.

### 9. Fees consume over half of all gross profit

**Finding.** Gross P&L is $486.6K; fees are $266.4K — 54.7% of the gross result — leaving $220.2K.

**Evidence.** Mean cost per trade $25 (5.10% of risk). Highest-cost instrument: BTC ($66.0K).

**Action.** Cost reduction is the highest-certainty P&L improvement available — it requires no forecasting skill at all. A 25% commission reduction would add roughly $66.6K straight to the bottom line.

### 10. High win rate and high profitability are opposites

**Finding.** Low reward:risk trades win far more often and still lose money, because a 0.9:1 target must win over half the time merely to break even — before fees.

**Evidence.** <1R: 52.9% actual vs 52.6% needed → -0.113R · 1-2R: 44.3% actual vs 41.7% needed → -0.033R · 2-3R: 30.8% actual vs 28.2% needed → +0.031R · >3R: 24.2% actual vs 21.8% needed → +0.051R

**Action.** Stop managing to win rate. Judge every strategy on expectancy in R against its own break-even hit rate, which is what the SQL scorecard reports.

### 11. Revenge trading is the single most destructive behaviour measured

**Finding.** Trades entered in a self-reported Revenge state return -0.141R against +0.089R when Disciplined — and they are sized 2.3x larger.

**Evidence.** Revenge: 694 trades, 28.5% WR, 2.68% average risk, -$41.6K net. Disciplined: 2,500 trades, 38.2% WR, 1.15% risk, $158.4K net.

**Action.** Enforce a mandatory cool-off lockout after two consecutive losses. This is the highest-value single control on the desk: worst expectancy combined with largest position size is the exact recipe for account destruction.

### 12. Risk rises as performance falls — the tilt spiral

**Finding.** As a losing streak lengthens, traders systematically increase position size while their expectancy deteriorates. The two move in exactly the wrong directions.

**Evidence.** 0 prior losses: 1.30% risk, +0.0230R · 1 prior losses: 1.34% risk, +0.0257R · 2 prior losses: 1.35% risk, +0.0006R · 3 prior losses: 1.39% risk, +0.0056R · 4 prior losses: 1.44% risk, -0.0336R · 5 prior losses: 1.50% risk, -0.0616R

**Action.** Invert the relationship in the risk policy: mandate a size REDUCTION after consecutive losses. A hard rule beats self-discipline under stress.

### 13. Trade quality collapses after the eighth trade of the day

**Finding.** The 9th and later trades of a session return -0.209R at a 24.6% win rate, while being sized 2.07% — the largest of any bucket.

**Evidence.** 1st: +0.0095R (3,651 trades) · 2nd-3rd: +0.0116R (4,550 trades) · 4th-5th: -0.0191R (1,891 trades) · 6th-8th: +0.0198R (632 trades) · 9th+: -0.2089R (57 trades)

**Action.** Cap daily trade count at eight. Beyond that point the desk is paying fees to lose money, and doing it in larger size.

### 14. Classic disposition effect: losers are held far longer than winners

**Finding.** Losing trades are held 286 minutes on average against 198 for winners — +45% longer. Traders cut winners quickly and hope losers recover.

**Evidence.** Median holding time 62 min (losses) vs 42 min (wins). Desk average 255 min.

**Action.** Automate exits. A bracket order placed at entry removes the discretionary moment where this bias operates.

### 15. More than a quarter of losses exceed the planned stop

**Finding.** 27.8% of losing trades close worse than −1.05R, meaning the stop was widened, ignored, or slipped through.

**Evidence.** Average loss is -0.967R against a designed −1.00R. Worst single trade -$5.1K (-2.01R).

**Action.** Use hard broker-side stops rather than mental ones. Every 0.1R of average stop overrun is a direct, permanent tax on expectancy.

### 16. A quarter of winning trades are closed well before target

**Finding.** 24.3% of winners were exited below 90% of their planned target, realising an average 1.86R against a planned 2.06R.

**Evidence.** Average slippage against plan across all trades: -2.264R. The Anxious state shows the highest early-exit rate.

**Action.** Pair the hard stop with a hard target. Cutting winners early while letting losers run (insight 14) is the same bias operating on both tails.

### 17. BTC is the most profitable instrument; GOLD the least

**Finding.** BTC returns +0.0233R per trade ($78.7K net over 2,612 trades), while GOLD returns -0.0155R.

**Evidence.** BTC +0.0233R · NASDAQ +0.0156R · US30 +0.0034R · ETH -0.0008R · EURUSD -0.0099R · GOLD -0.0155R

**Action.** Note that BTC also carries the largest fee bill ($66.0K); the edge survives the cost, but a cheaper venue would materially widen it.

### 18. There is a directional bias: longs outperform shorts

**Finding.** Long trades return +0.0260R against -0.0180R for shorts, on a near-even split of trade counts.

**Evidence.** Buy: 5,584 trades, 35.7% WR. Sell: 5,197 trades, 34.5% WR.

**Action.** Consistent with a rising underlying market across the period — review whether the short playbook has a genuine edge or is fighting the trend.

### 19. Drawdown is controlled, and recovery is strong

**Finding.** Worst peak-to-trough decline was $62.5K (14.50% of equity), between 2024-01-01 and 2024-04-02.

**Evidence.** Recovery factor 3.52 (net profit ÷ max drawdown), Calmar 1.24, daily volatility 0.835%. Longest losing streak 30 trades (TR-005).

**Action.** A sub-20% drawdown at this return level is institutionally acceptable. The constraint on scaling is the thin profit factor, not the drawdown.

### 20. Performance tracks discipline, not activity

**Finding.** Across the twelve traders, the correlation between tilt rate (share of trades entered in a Revenge/FOMO/Greedy state) and expectancy is -0.96 — strongly negative. The top four traders generate $330.5K while the bottom eight lose -$110.3K.

**Evidence.** TR-004: +0.147R, tilt 9.6% · TR-001: +0.110R, tilt 13.2% · TR-006: +0.088R, tilt 15.6% … TR-007: -0.128R, tilt 24.5% · TR-005: -0.160R, tilt 27.5%

**Action.** Allocate capital on expectancy in R and tilt rate, not on headline P&L. Behavioural coaching for the high-tilt cohort has a larger expected payoff than any new strategy.

---

## Summary of recommended actions

| Priority | Action | Rationale |
|---|---|---|
| 1 | Mandatory lockout after 2 consecutive losses | Revenge trades combine the worst expectancy with the largest size (insights 11, 12) |
| 2 | Stop trading, or re-price, the highest-cost strategy | Gross-positive but net-negative purely on fees (insight 8) |
| 3 | Hard daily cap of 8 trades | Quality collapses beyond it (insight 13) |
| 4 | Broker-side bracket orders on every entry | Fixes stop overrun and early-exit bias at once (insights 14, 15, 16) |
| 5 | Concentrate risk into the London open, cut the pre-London window | Largest scheduling edge available (insights 3, 4, 5) |
| 6 | Renegotiate commissions | Fees are over half of gross profit (insight 9) |

