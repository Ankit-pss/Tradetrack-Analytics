# Power BI — Dashboard Specification

Everything needed to build the TradeTrack report in Power BI Desktop: the data
model, the measure library, an importable theme, and a page-by-page visual spec.

| File | What it is |
|---|---|
| `measures.dax` | 70+ production DAX measures, grouped into display folders |
| `tradetrack_theme.json` | Importable dark fintech report theme |
| `data_model.md` | Star schema, relationships, column formatting |
| this file | Page layouts, visual choices, and the reasoning behind them |

> **Why no `.pbix` in the repo.** A `.pbix` is a binary that embeds a copy of
> the data, so it bloats the repo, diffs as noise, and goes stale the moment the
> pipeline re-runs. The text artefacts here rebuild the report in ~20 minutes
> and stay reviewable in version control. The same report is also implemented as
> a live, dependency-free web dashboard in `../dashboard/` — open `index.html`
> to see the intended result running.

---

## 1. Getting the data in

**Source:** `data/processed/trades_clean.csv` (or connect straight to
`data/tradetrack.db` via the ODBC SQLite driver to use the star schema and views
the SQL layer already builds).

```
Get Data → Text/CSV → data/processed/trades_clean.csv → Transform Data
```

Power Query steps:

1. **Set types explicitly.** Do not trust type detection — `trade_date` must be
   Date, `entry_datetime` DateTime, and every money column Decimal Number.
2. **Load `dim_calendar.csv`** as the date dimension and mark it as a date table
   (`Table tools → Mark as date table → Date`). Time intelligence measures
   (`TOTALYTD`, `DATEADD`, `DATESINPERIOD`) silently misbehave without this.
3. **Disable load** on any staging query so it does not become a model table.
4. **Reference, don't duplicate**, when deriving `DimTrader` / `DimAsset` /
   `DimStrategy` from the fact table — a duplicate re-runs the whole source query.

---

## 2. Theme

```
View → Themes → Browse for themes → tradetrack_theme.json
```

Palette notes — the choices are deliberate, not decorative:

- **Categorical slots are assigned in a fixed order and never cycled.** The same
  asset keeps the same hue on every page, so a reader learns the mapping once.
- The eight hues were validated for **colour-vision-deficiency separation** and
  for **≥ 3:1 contrast against the `#12161C` surface**.
- **Profit/loss uses the reserved status colours** (`good` `#0CA30C`, `bad`
  `#D03B3B`), never a categorical slot — profit-vs-loss is a *state*, not a
  series. Every P&L figure is also sign-formatted (`$#,0;($#,0)`), so colour
  never carries the meaning alone. That matters for accessibility and it matters
  when the report is printed in greyscale.

---

## 3. Page 1 — Executive Overview

The question this page answers: *is the desk making money, and how much risk is
it taking to do it?*

```
┌──────────────────────────────────────────────────────────────────────────┐
│  TradeTrack Analytics            [Date range] [Asset] [Strategy] [Session]│
├──────────┬──────────┬──────────┬──────────┬──────────┬───────────────────┤
│ Net      │ Win Rate │ Profit   │ Avg RR   │ Max      │ Avg Trade         │
│ Profit   │          │ Factor   │          │ Drawdown │ Duration          │
├──────────┴──────────┴──────────┴──────────┴──────────┴───────────────────┤
│  EQUITY CURVE  (area, daily)                     ← full width, tallest    │
│  + drawdown band beneath                                                  │
├───────────────────────────────────┬──────────────────────────────────────┤
│  Monthly Net P&L (diverging bars) │  Daily P&L distribution (histogram)  │
├───────────────────────────────────┼──────────────────────────────────────┤
│  Net P&L by Asset (bar, sorted)   │  Strategy scorecard (table)          │
└───────────────────────────────────┴──────────────────────────────────────┘
```

**Visuals**

| Visual | Type | Fields | Notes |
|---|---|---|---|
| KPI row | Card (×6) | `[Net Profit]`, `[Win Rate]`, `[Profit Factor]`, `[Avg Planned RR]`, `[Max Drawdown %]`, `[Avg Duration Label]` | Font colour bound to `[PnL Colour]` / `[Profit Factor Colour]` via *fx → Field value* |
| Equity curve | Area chart | Axis `DimCalendar[Date]`, Values `[Equity]` | Add a constant line at `[Opening Capital]` — it is the line that says "profitable or not" |
| Drawdown | Area chart | Axis `DimCalendar[Date]`, Values `[Drawdown %]` | Placed directly beneath and **x-axis aligned** with the equity curve |
| Monthly P&L | Clustered column | Axis `DimCalendar[YearMonth]`, Values `[Net Profit]` | Conditional fill on `[PnL Colour]` |
| Daily distribution | Column | Axis: binned `[Net Profit]` by day | Shows the fat left tail — the risk that actually matters |
| By asset | Bar (horizontal) | Axis `DimAsset[Asset]`, Values `[Net Profit]` | Sort descending; horizontal because the labels are words |
| Strategy scorecard | Table | `Strategy`, `[Total Trades]`, `[Win Rate]`, `[Breakeven Win Rate]`, `[Edge (pp)]`, `[Expectancy R]`, `[Profit Factor]`, `[Net Profit]` | **Sort by `[Expectancy R]`, not by P&L** |

> **The one visual choice that carries the analysis:** the strategy table shows
> `[Win Rate]` and `[Breakeven Win Rate]` side by side. Without the second
> column a 53%-win-rate strategy looks excellent — when it needs 53% just to
> break even and is actually losing money after fees.

---

## 4. Page 2 — Risk & Drawdown

| Visual | Type | Fields |
|---|---|---|
| Risk-adjusted KPIs | Card (×4) | `[Sharpe Ratio]`, `[Sortino Ratio]`, `[Calmar Ratio]`, `[Recovery Factor]` |
| Underwater plot | Area | `DimCalendar[Date]` × `[Drawdown %]`, inverted axis |
| Risk band performance | Combo | Axis `FactTrades[RiskBucket]`; columns `[Total Trades]`, line `[Expectancy R]` |
| RR band analysis | Clustered bar | Axis `[RRBucket]`; values `[Win Rate]` and `[Breakeven Win Rate]` |
| Stop discipline | Card + bar | `[Stop Overrun Rate]`, `[RR Slippage]` |
| Top 10 winning days | Table | `TradeDate`, `[Total Trades]`, `[Win Rate]`, `[Net Profit]` — Top N filter |
| Top 10 losing days | Table | as above, Bottom N |

**Avoid the dual-axis trap.** The combo visual above is the one place two
measures share a chart, and it works only because trade count and expectancy are
deliberately on *different* visual channels (column vs line) with the line's axis
labelled. Two y-scales on the same mark type is the single most common way a
Power BI chart lies about correlation — if in doubt, use two visuals.

---

## 5. Page 3 — Behavioural Analytics

The page that makes this a trading *journal* analysis rather than a broker
statement.

| Visual | Type | Fields |
|---|---|---|
| Expectancy by emotional state | Bar | `EmotionalState` × `[Expectancy R]`, sorted ascending |
| Risk taken by state | Bar | `EmotionalState` × `[Avg Risk %]` — **place directly beside the one above** |
| Discipline premium | Card | `[Discipline Premium R]`, `[Revenge Size Multiple]` |
| Tilt spiral | Line | Axis `[PrevLossStreak]`; `[Avg Risk %]` and `[Expectancy R]` as small multiples |
| Overtrading decay | Column | Axis `[TradeSeqInDay]` bucketed × `[Expectancy R]` |
| Disposition effect | Card + bar | `[Disposition Gap]`, `[Avg Duration Wins]` vs `[Avg Duration Losses]` |

> Pairing *expectancy by state* with *risk by state* side by side is the whole
> point of the page: the worst states are also the largest-sized. Two adjacent
> bar charts show that instantly; a single combined chart would bury it.

---

## 6. Page 4 — Trader Leaderboard

| Visual | Type | Fields |
|---|---|---|
| Leaderboard | Table | `[Trader Rank]`, `TraderName`, `[Total Trades]`, `[Win Rate]`, `[Expectancy R]`, `[Profit Factor]`, `[Max Drawdown %]`, `[Tilt Rate]`, `[Recommended Action]` |
| Equity by trader | Line, small multiples | `DimCalendar[Date]` × `[Equity]`, multiple by `TraderName` |
| Expectancy vs tilt | Scatter | X `[Tilt Rate]`, Y `[Expectancy R]`, size `[Total Trades]`, play axis by month |
| Survivorship | Line | `DimCalendar[Date]` × `[Active Traders]` |

**The survivorship visual is not optional.** Desk P&L improves sharply over the
period largely because losing traders blow up and stop trading — four of twelve
accounts. Any leaderboard shown without the active-trader count beside it
rewards attrition and flatters the surviving cohort.

---

## 7. Page 5 — Time & Session Analysis

| Visual | Type | Fields |
|---|---|---|
| Weekday × hour heatmap | Matrix, background colour | Rows `Weekday`, Columns `EntryHour`, Values `[Net Profit]` |
| Session performance | Bar | `TradingSession` × `[Expectancy R]` |
| Hour of day | Column | `EntryHour` × `[Net Profit]` |
| Weekday | Column | `Weekday` × `[Expectancy R]`, sorted Mon→Sun via a sort-by column |
| Rolling 30-day | Line | `[Net Profit Rolling 30D]`, `[Win Rate Rolling 30D]` as small multiples |

Heatmap colour: diverging, `bad → center → maximum`, **centre pinned at 0** and
the range clipped to roughly the 97.5th percentile of |value|. Without the clip,
two extreme cells flatten every other cell to the neutral midpoint and the
pattern the visual exists to show disappears.

Sort weekday with a numeric sort-by column (`WeekdayNum`), never alphabetically —
"Friday, Monday, Saturday…" is the classic Power BI tell.

---

## 8. Interactions and performance

- **Slicers:** date range, Asset, Strategy, Session, Trade Type, Trader. Sync
  across pages (`View → Sync slicers`) so filter context follows the reader.
- **Edit interactions:** set the KPI cards to *filter* from slicers but *not*
  cross-filter from chart selections — a headline number that changes when
  someone idly clicks a bar destroys trust in the number.
- **Drill-through** on `TraderName` and `Strategy` into a trade-detail page.
- **Performance:** keep `[Running Peak Equity]` off high-cardinality visuals —
  it is an `MAXX` over a filtered date table and is the most expensive measure
  in the model. If a visual is slow, materialise the running peak as a
  calculated column in Power Query instead.

---

## 9. Publishing checklist

- [ ] Date table marked as a date table
- [ ] All relationships single-direction, many-to-one, fact → dimension
- [ ] Money columns formatted `$#,0;($#,0)` so negatives read as `($1,234)`
- [ ] Percentages formatted to 2 dp; R-multiples to 3 dp
- [ ] Every visual has a title stating a *finding*, not a field name
- [ ] Alt text set on each visual
- [ ] Tab order set for keyboard navigation
- [ ] Tooltips show sample size (`[Total Trades]`) alongside every rate
- [ ] Report page size 1600×900, "Fit to page"
