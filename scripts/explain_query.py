#!/usr/bin/env python3
"""Run EXPLAIN (ANALYZE) on a query and print the plan + timing — dialect-aware.

Reveals the real cost: seq/full scans, missing indexes, bad row estimates, nested-loop N+1
shapes. Use it to justify an index or a rewrite with a number, not a hunch.

Usage:
  DATABASE_URL=postgresql://...  python explain_query.py "SELECT ... WHERE ..."
  DATABASE_URL=mysql://...       python explain_query.py --file query.sql
  python explain_query.py --plain "UPDATE ..."     # plan only, does NOT execute

Notes:
  - ANALYZE *executes* the query. Use the default (ANALYZE) only on SELECTs; for
    INSERT/UPDATE/DELETE use --plain (plan only, no execution / no writes).
  - Reads DATABASE_URL from env. Driver suffixes like "+asyncpg"/"+aiomysql" are stripped
    (this uses a sync connection via SQLAlchemy). Point at a DEV db or run it where it's safe;
    never run writes against production from a workstation.
  - Requires SQLAlchemy + a DB driver (psycopg2/pymysql/sqlite3). Supports Postgres, MySQL, SQLite.
"""
import argparse
import os
import re
import sys


def _sync_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("set DATABASE_URL", file=sys.stderr)
        sys.exit(1)
    # strip async drivers -> let SQLAlchemy pick the default sync driver
    return re.sub(r"\+\w+", "", url)


def _explain_sql(dialect, sql, analyze):
    if dialect == "postgresql":
        mode = "ANALYZE, BUFFERS, " if analyze else ""
        return f"EXPLAIN ({mode}FORMAT TEXT) {sql}"
    if dialect == "mysql":
        return f"EXPLAIN {'ANALYZE ' if analyze else ''}{sql}"
    if dialect == "sqlite":
        return f"EXPLAIN QUERY PLAN {sql}"  # sqlite has no ANALYZE-execute form here
    return f"EXPLAIN {sql}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("sql", nargs="?", help="SQL query string")
    p.add_argument("--file", help="read SQL from a file")
    p.add_argument("--plain", action="store_true", help="plan only (no ANALYZE / no execution)")
    args = p.parse_args()

    sql = args.sql
    if args.file:
        with open(args.file) as f:
            sql = f.read()
    if not sql:
        p.error("provide SQL as an argument or via --file")
    sql = sql.strip().rstrip(";")

    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("needs SQLAlchemy + a DB driver (pip install sqlalchemy psycopg2-binary)", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(_sync_url())
    dialect = engine.dialect.name
    explain = _explain_sql(dialect, sql, analyze=not args.plain)
    with engine.connect() as conn:
        for row in conn.execute(text(explain)):
            print(" | ".join(str(x) for x in row) if len(row) > 1 else str(row[0]))


if __name__ == "__main__":
    main()
