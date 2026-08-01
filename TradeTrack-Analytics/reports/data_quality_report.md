# Data Quality Report

- **Raw rows ingested:** 11,130
- **Clean closed trades:** 10,781
- **Open trades quarantined:** 140

## Cleaning log

1. loaded 11,130 raw rows x 30 columns
1. removed 180 exact duplicate rows
1. coerced 156 string-formatted numeric values to float
1. normalised casing/whitespace on 720 categorical values
1. repaired 45 impossible (<=0) trade durations from timestamps; 0 left as null
1. flagged 17 fat-finger entry prices (robust MAD z-score > 8)
1. quarantined 140 still-open trades (no exit recorded)
1. filled 258 missing emotional_state -> 'Unspecified', 396 missing notes -> ''
1. net_profit == profit_loss - fees fails on 0 rows
1. stop/target on the wrong side of entry on 29 rows (14 missed by the MAD test alone)
1. dropped 29 structurally invalid rows from the analytical table
1. engineered 78 total columns on 10,781 clean trades

## Rules applied

| Issue | Detection | Treatment |
|---|---|---|
| Duplicate submissions | exact row match, then repeated `trade_id` | drop, keep first |
| Thousands-separated numbers | regex `[,\s$]` in a numeric column | strip and cast to float |
| Casing / whitespace noise | value not in the canonical domain | map to canonical label |
| Impossible duration (<= 0) | `trade_duration_min <= 0` | recompute from timestamps, else null |
| Fat-finger entry price | robust MAD z-score > 12 within asset | flag and exclude from analysis |
| Open trades | `exit_price` or `net_profit` null | quarantine to a separate file |
| Missing emotional state | null | `'Unspecified'` (kept, not dropped) |
| Missing notes | null | empty string |
