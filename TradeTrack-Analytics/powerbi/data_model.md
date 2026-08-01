# Power BI — Data Model

## Star schema

```
                    ┌──────────────┐
                    │ DimCalendar  │
                    │  Date  (PK)  │
                    └──────┬───────┘
                           │ 1
                           │
                           │ *
┌────────────┐ 1     *  ┌──┴──────────┐  *     1 ┌──────────────┐
│ DimTrader  ├─────────►│ FactTrades  │◄─────────┤ DimAsset     │
│ TraderID   │          │  trade grain│          │ Asset  (PK)  │
└────────────┘          └──┬──────────┘          └──────────────┘
                           │ *
                           │
                           │ 1
                    ┌──────┴───────┐
                    │ DimStrategy  │
                    │ Strategy (PK)│
                    └──────────────┘
```

**Grain:** one row of `FactTrades` = one **closed** trade. Open trades are
quarantined upstream into `open_trades.csv` and deliberately excluded — including
them would understate the win rate, because a trade with no exit has no outcome.

Every measure is additive over this grain, which is what keeps the model honest:
totals can be summed along any dimension without double counting.

---

## Relationships

| From | To | Cardinality | Direction | Active |
|---|---|---|---|---|
| `FactTrades[TradeDate]` | `DimCalendar[Date]` | Many-to-one | Single | Yes |
| `FactTrades[TraderID]` | `DimTrader[TraderID]` | Many-to-one | Single | Yes |
| `FactTrades[Asset]` | `DimAsset[Asset]` | Many-to-one | Single | Yes |
| `FactTrades[Strategy]` | `DimStrategy[Strategy]` | Many-to-one | Single | Yes |

**All relationships are single-direction.** Bi-directional filtering is the most
common cause of ambiguous-path errors and of measures that silently return the
wrong number once a second fact table is added. If a specific visual needs
reverse filtering, use `CROSSFILTER()` inside that one measure rather than
changing the model.

`DimCalendar` must be marked as a date table (`Table tools → Mark as date
table → Date`). Without it, `TOTALYTD`, `DATEADD` and `DATESINPERIOD` fall back
to Power BI's auto date hierarchy and produce subtly wrong results at period
boundaries.

---

## FactTrades — column reference

| Column | Type | Format | Notes |
|---|---|---|---|
| `TradeID` | Text | — | Primary key. Hide from report view. |
| `TraderID` | Text | — | FK → DimTrader |
| `TradeDate` | Date | `dd mmm yyyy` | FK → DimCalendar |
| `EntryDateTime` | DateTime | — | Used for sequencing, not for slicing |
| `ExitDateTime` | DateTime | — | |
| `TradingSession` | Text | — | Asia / London / New York |
| `Asset` | Text | — | FK → DimAsset |
| `Strategy` | Text | — | FK → DimStrategy |
| `TradeType` | Text | — | Buy / Sell |
| `EmotionalState` | Text | — | Includes `Unspecified` for missing journal entries |
| `EntryPrice` | Decimal | `#,0.00000` | |
| `ExitPrice` | Decimal | `#,0.00000` | |
| `StopLoss` | Decimal | `#,0.00000` | |
| `TakeProfit` | Decimal | `#,0.00000` | |
| `Quantity` | Decimal | `#,0.000000` | |
| `RiskPct` | Decimal | `0.00"%"` | Planned risk as % of equity |
| `RiskAmount` | Decimal | `$#,0.00` | Dollars at risk = \|entry − stop\| × qty |
| `RiskRewardRatio` | Decimal | `0.00` | **Planned** RR |
| `RealisedRR` | Decimal | `0.000` | **Achieved** RR |
| `RMultiple` | Decimal | `0.000` | Net P&L ÷ RiskAmount — the ranking column |
| `ProfitLoss` | Decimal | `$#,0;($#,0)` | Gross, before fees |
| `Fees` | Decimal | `$#,0.00` | |
| `NetProfit` | Decimal | `$#,0;($#,0)` | **After fees — the truth column** |
| `IsWin` | Whole number | `0` | 1/0 so `AVERAGE()` gives the win rate directly |
| `TradeDurationMin` | Decimal | `#,0` | |
| `AccountBalance` | Decimal | `$#,0` | Balance **after** the trade settled |
| `DrawdownPct` | Decimal | `0.00"%"` | Per-trader, at that point in time |
| `TradeSeqInDay` | Whole number | `0` | Nth trade of that trader's day |
| `IsTiltState` | Whole number | `0` | 1 if Revenge / FOMO / Greedy |
| `IsQuickReentry` | Whole number | `0` | Re-entry < 10 min after a loss |
| `RiskBucket` | Text | — | Needs a sort-by column |
| `RRBucket` | Text | — | Needs a sort-by column |
| `Weekday` | Text | — | Needs a sort-by column |

### Sort-by columns (do not skip these)

| Text column | Sort by | Why |
|---|---|---|
| `Weekday` | `WeekdayNum` (0–6) | Otherwise: "Friday, Monday, Saturday…" |
| `RiskBucket` | `RiskBucketOrder` (1–5) | Otherwise `"<0.5%"` sorts after `">3%"` |
| `RRBucket` | `RRBucketOrder` (1–4) | Same |
| `MonthName` | `Month` (1–12) | Otherwise: "Apr, Aug, Dec…" |

Add the order columns in Power Query:

```m
= Table.AddColumn(Source, "RiskBucketOrder", each
    let b = [risk_bucket] in
    if b = "<0.5%" then 1
    else if b = "0.5-1%" then 2
    else if b = "1-2%"   then 3
    else if b = "2-3%"   then 4
    else 5,
  Int64.Type)
```

Then `Column tools → Sort by column → RiskBucketOrder`.

---

## Model hygiene

- **Hide from report view:** all key columns (`TradeID`, foreign keys),
  every `*Order` sort column, and any column already surfaced by a measure.
  A field list a reader can trust is one where every visible field is meant to
  be dragged onto a canvas.
- **Set `Summarization = Do not summarize`** on `RiskPct`, `RMultiple`,
  `RiskRewardRatio` and `TradeDurationMin`. Their default `Sum` is meaningless
  and produces nonsense the moment someone drags the raw column onto a visual
  instead of using the measure.
- **Disable auto date/time** (`Options → Data Load → uncheck Auto date/time`).
  It creates a hidden date hierarchy per date column and bloats the model.
- **Storage mode:** Import. At ~10,800 rows the model is trivially small; there
  is no case for DirectQuery here, and Import keeps all DAX features available.

---

## Optional: connecting to the SQLite warehouse instead

`data/tradetrack.db` already contains the same star schema plus three views
(`vw_daily_pnl`, `vw_monthly_pnl`, `vw_trade_enriched`) built by
`sql/01_schema.sql`. Connecting to it via the SQLite ODBC driver means the SQL
and Power BI layers share one definition of every aggregate, which removes an
entire class of "the dashboard disagrees with the report" bugs.

```
Get Data → ODBC → SQLite3 Datasource → data/tradetrack.db
```

Import `fact_trades`, `dim_trader`, `dim_asset`, `dim_strategy` and
`dim_calendar`; leave the views for validation rather than loading them as model
tables, since they pre-aggregate and would break the star grain.
