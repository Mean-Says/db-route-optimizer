#!/usr/bin/env python3
"""List top pg_stat_statements rows (read-only). Stdlib + optional SQLAlchemy/psycopg.

Usage:
  RADAR_COPY_DATABASE_URL=postgresql://... python scripts/radar/pg_stat_top.py --order total
  DATABASE_URL=... python scripts/radar/pg_stat_top.py --order calls --limit 20

Refuses non-local hosts unless --allow-remote-stats (still SELECT-only).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import urlparse

_LOCAL = {"localhost", "127.0.0.1", "::1", ""}

SQL = {
    "total": """
        SELECT queryid, calls,
               round(total_exec_time)::bigint AS total_ms,
               round(mean_exec_time::numeric, 2) AS mean_ms,
               rows, left(query, 120) AS query_preview
        FROM pg_stat_statements
        ORDER BY total_exec_time DESC
        LIMIT %(limit)s
    """,
    "mean": """
        SELECT queryid, calls,
               round(total_exec_time)::bigint AS total_ms,
               round(mean_exec_time::numeric, 2) AS mean_ms,
               rows, left(query, 120) AS query_preview
        FROM pg_stat_statements
        ORDER BY mean_exec_time DESC
        LIMIT %(limit)s
    """,
    "calls": """
        SELECT queryid, calls,
               round(total_exec_time)::bigint AS total_ms,
               round(mean_exec_time::numeric, 2) AS mean_ms,
               rows, left(query, 120) AS query_preview
        FROM pg_stat_statements
        ORDER BY calls DESC
        LIMIT %(limit)s
    """,
}


def _url() -> str:
    return (
        os.environ.get("RADAR_COPY_DATABASE_URL")
        or os.environ.get("RADAR_PROD_STATS_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    )


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _redact(url: str) -> str:
    return re.sub(r":([^:@/]+)@", ":***@", url)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Top pg_stat_statements (read-only).")
    p.add_argument("--order", choices=["total", "mean", "calls"], default="total")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument(
        "--allow-remote-stats",
        action="store_true",
        help="allow non-local host (still SELECT-only; for prod stats role)",
    )
    args = p.parse_args(argv)

    url = _url()
    if not url:
        print(
            "set RADAR_COPY_DATABASE_URL or DATABASE_URL (see .env.radar.example)",
            file=sys.stderr,
        )
        return 1

    host = _host(url)
    if host not in _LOCAL and not args.allow_remote_stats:
        print(
            f"host '{host}' is not local; pass --allow-remote-stats for a read-only stats role",
            file=sys.stderr,
        )
        return 1

    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("needs sqlalchemy (+ psycopg): pip install sqlalchemy 'psycopg[binary]'", file=sys.stderr)
        return 1

    sync = re.sub(r"\+\w+", "", url)
    print(f"# database {_redact(sync)}  order={args.order} limit={args.limit}", file=sys.stderr)
    engine = create_engine(sync)
    q = SQL[args.order].replace("%(limit)s", str(int(args.limit)))
    with engine.connect() as conn:
        # read-only best-effort
        try:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET statement_timeout = 5000"))
        except Exception:
            pass
        rows = list(conn.execute(text(q)))
        conn.rollback()

    if not rows:
        print("no rows (is pg_stat_statements installed and visible to this role?)")
        return 0

    cols = rows[0]._mapping.keys()
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r._mapping[c]) for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
