"""
TradeTrack Analytics — SQL analysis runner.
============================================

Parses `sql/02_analysis_queries.sql` on its `-- @query:` markers, executes each
query against the SQLite warehouse, and renders every result set into a single
markdown report.

This is what makes the SQL layer verifiable rather than decorative: every query
in the library is actually executed on every run, so a query that no longer
parses or returns nothing fails the build instead of quietly rotting.

Run:  python python/run_sql_analysis.py
Out:  reports/sql_analysis_results.md
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import REPORTS_DIR, SQL_DIR, SQLITE_DB  # noqa: E402

QUERY_FILE = os.path.join(SQL_DIR, "02_analysis_queries.sql")
OUT_FILE = os.path.join(REPORTS_DIR, "sql_analysis_results.md")
MAX_ROWS_SHOWN = 15


def parse_queries(path: str) -> list[dict]:
    """Split the library on `-- @query: name` / `-- @desc: ...` markers."""
    text = open(path).read()
    blocks = re.split(r"^--\s*@query:\s*", text, flags=re.MULTILINE)[1:]

    queries = []
    for block in blocks:
        lines = block.splitlines()
        name = lines[0].strip()

        desc_lines, body_start = [], 1
        for i, line in enumerate(lines[1:], start=1):
            m = re.match(r"^--\s*@desc:\s*(.*)", line)
            if m:
                desc_lines.append(m.group(1).strip())
                continue
            if desc_lines and re.match(r"^--\s{6,}(.*)", line):
                desc_lines.append(line.lstrip("- ").strip())
                continue
            body_start = i
            break

        sql = "\n".join(lines[body_start:]).strip()
        sql = sql.rstrip().rstrip(";")
        if sql:
            queries.append({"name": name, "desc": " ".join(desc_lines), "sql": sql})
    return queries


def fmt(df: pd.DataFrame) -> str:
    """Render a result set as a markdown table, truncated for readability."""
    shown = df.head(MAX_ROWS_SHOWN)
    out = shown.to_markdown(index=False, floatfmt=",.3f")
    if len(df) > MAX_ROWS_SHOWN:
        out += f"\n\n_({len(df):,} rows returned, first {MAX_ROWS_SHOWN} shown)_"
    return out


def main() -> None:
    if not os.path.exists(SQLITE_DB):
        raise SystemExit("warehouse not found — run python/load_to_sql.py first")

    conn = sqlite3.connect(SQLITE_DB)
    queries = parse_queries(QUERY_FILE)
    print(f"Executing {len(queries)} queries against {os.path.basename(SQLITE_DB)} ...\n")

    sections, failures = [], []
    for q in queries:
        try:
            df = pd.read_sql_query(q["sql"], conn)
            status = "OK" if len(df) else "EMPTY"
            if not len(df):
                failures.append((q["name"], "returned 0 rows"))
            print(f"  [{status:5}] {q['name']:<28} {len(df):>6,} rows")
            sections.append((q, df, None))
        except Exception as exc:                      # noqa: BLE001
            print(f"  [FAIL ] {q['name']:<28} {exc}")
            failures.append((q["name"], str(exc)))
            sections.append((q, None, str(exc)))

    with open(OUT_FILE, "w") as fh:
        fh.write("# SQL Analysis — Executed Results\n\n")
        fh.write(
            "Every query in `sql/02_analysis_queries.sql` executed against the "
            "SQLite warehouse (`data/tradetrack.db`). Regenerate with "
            "`python python/run_sql_analysis.py`.\n\n"
        )
        fh.write(f"**{len(queries)} queries · {len(queries) - len(failures)} passed**\n\n")
        fh.write("---\n\n")
        for q, df, err in sections:
            title = q["name"].replace("_", " ").title()
            fh.write(f"## {title}\n\n")
            if q["desc"]:
                fh.write(f"> {q['desc']}\n\n")
            fh.write("```sql\n" + q["sql"] + "\n```\n\n")
            if err:
                fh.write(f"**ERROR:** `{err}`\n\n")
            else:
                fh.write(fmt(df) + "\n\n")
            fh.write("---\n\n")

    conn.close()
    print(f"\n  written: {OUT_FILE}")
    if failures:
        print("\n  FAILURES:")
        for name, msg in failures:
            print(f"    {name}: {msg}")
        raise SystemExit(1)
    print(f"  all {len(queries)} queries executed successfully")


if __name__ == "__main__":
    main()
