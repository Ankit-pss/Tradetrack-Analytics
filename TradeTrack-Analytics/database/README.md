# Database Layer

## SQLite Star Schema Warehouse

Production-grade data warehouse for analytical queries.

### Schema

```
datasets/tradetrack.db
├── fact_trades (10,781 rows)
│   ├── trade_id (PK)
│   ├── trader_fk → dim_trader
│   ├── asset_fk → dim_asset
│   ├── strategy_fk → dim_strategy
│   └── 40+ analytical columns
│
├── dim_trader (12 rows)
├── dim_asset (6 rows)
└── dim_strategy (7 rows)
```

### Files

- `sql/01_schema.sql` — DDL, indexes, views
- `sql/02_analysis_queries.sql` — 21 analytical queries (all executed every run)

### Key Queries

```sql
-- Performance by strategy
SELECT strategy, COUNT(*), SUM(net_profit), win_rate
FROM fact_trades f
JOIN dim_strategy s ON f.strategy_fk = s.strategy_id
GROUP BY strategy
ORDER BY net_profit DESC;

-- Max drawdown per trader (window functions)
SELECT trader_fk, 
       MAX(cumulative_equity) OVER (PARTITION BY trader_fk ORDER BY entry_time) as peak,
       MIN(cumulative_equity) OVER (PARTITION BY trader_fk ORDER BY entry_time) as trough
FROM fact_trades;

-- Win/loss streaks (gaps-and-islands)
WITH streaks AS (...)
SELECT trader_fk, direction, COUNT(*) as length
FROM streaks
GROUP BY trader_fk, direction;
```

### Reconciliation Checks

Every build validates:
- Row count: source CSV → warehouse (must match exactly)
- P&L: sum(net_profit) in CSV → SUM(net_profit) in DB (to the cent)
- Referential integrity: all foreign keys valid

Build aborts if any check fails.

---

**Documentation:** See [../docs/database_design.md](../docs/database_design.md)
