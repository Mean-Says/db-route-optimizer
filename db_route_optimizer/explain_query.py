#!/usr/bin/env python3
"""Run EXPLAIN on a query and print the plan — dialect-aware, safety-first.

Usage:
  DATABASE_URL=postgresql://...  dbro-explain "SELECT ... WHERE ..."
  DATABASE_URL=sqlite:///demo.db dbro-explain --file query.sql
  dbro-explain --plain "UPDATE ..."     # plan only, does NOT execute

Safety:
  - Non-local hosts default to --plain (no ANALYZE).
  - ANALYZE is refused on non-SELECT.
  - Passwords are redacted in all output.
  - Postgres: SET TRANSACTION READ ONLY + statement_timeout.
  - SQLite: PRAGMA query_only=ON (skipped when --verify creates an index).
  - --suggest-index is only a recommendation after --verify on a local/demo DB.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse, urlunparse

from db_route_optimizer.i18n import add_lang_arg, set_lang, t

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def redact_url(url: str) -> str:
    """Hide password in a database URL."""
    if not url:
        return url
    try:
        p = urlparse(url)
        if p.password is None:
            return url
        netloc = p.netloc
        # user:pass@host -> user:***@host
        if "@" in netloc:
            userinfo, hostpart = netloc.rsplit("@", 1)
            if ":" in userinfo:
                user = userinfo.split(":", 1)[0]
                netloc = f"{user}:***@{hostpart}"
            else:
                netloc = f"***@{hostpart}"
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return re.sub(r":([^:@/]+)@", ":***@", url)


def host_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        if p.scheme.startswith("sqlite"):
            return "localhost"
        return (p.hostname or "").lower()
    except Exception:
        return ""


def is_local_url(url: str) -> bool:
    host = host_from_url(url)
    if urlparse(url).scheme.startswith("sqlite"):
        return True
    return host in _LOCAL_HOSTS


def sync_url(url: str | None = None) -> str:
    url = url or os.getenv("DATABASE_URL")
    if not url:
        print(t("ex_set_url"), file=sys.stderr)
        sys.exit(1)
    # strip async drivers -> let SQLAlchemy pick the default sync driver
    return re.sub(r"\+\w+", "", url)


def is_select(sql: str) -> bool:
    return bool(re.match(r"^\s*(WITH\b[\s\S]+)?SELECT\b", sql, re.IGNORECASE))


def explain_sql(dialect: str, sql: str, analyze: bool) -> str:
    if dialect == "postgresql":
        mode = "ANALYZE, BUFFERS, " if analyze else ""
        return f"EXPLAIN ({mode}FORMAT JSON) {sql}"
    if dialect == "sqlite":
        return f"EXPLAIN QUERY PLAN {sql}"
    if dialect == "mysql":
        return f"EXPLAIN {'ANALYZE ' if analyze else ''}{sql}"
    return f"EXPLAIN {sql}"


def _apply_readonly(conn, dialect: str, timeout_ms: int, *, allow_writes: bool = False):
    if allow_writes:
        return
    if dialect == "postgresql":
        conn.execute(__sa_text(f"SET statement_timeout = {int(timeout_ms)}"))
        conn.execute(__sa_text("SET TRANSACTION READ ONLY"))
    elif dialect == "sqlite":
        conn.execute(__sa_text("PRAGMA query_only = ON"))


def __sa_text(sql: str):
    from sqlalchemy import text

    return text(sql)


def _fetch_plan(conn, dialect: str, sql: str, analyze: bool):
    explain = explain_sql(dialect, sql, analyze=analyze)
    rows = list(conn.execute(__sa_text(explain)))
    if dialect == "postgresql" and rows:
        # FORMAT JSON returns one cell with nested structure
        cell = rows[0][0]
        if isinstance(cell, str):
            cell = json.loads(cell)
        return cell
    if dialect == "sqlite":
        # rows: id, parent, notused, detail
        return [{"id": r[0], "parent": r[1], "detail": r[-1]} for r in rows]
    return [list(r) for r in rows]


def _plan_as_text(dialect: str, plan) -> str:
    if dialect == "postgresql":
        # re-run would need FORMAT TEXT; pretty-print JSON instead
        return json.dumps(plan, indent=2)
    if dialect == "sqlite":
        return "\n".join(f"{r.get('detail', r)}" for r in plan)
    return "\n".join(str(r) for r in plan)


def _walk_pg_plans(node, out=None):
    out = out or []
    if isinstance(node, list):
        for item in node:
            _walk_pg_plans(item, out)
        return out
    if not isinstance(node, dict):
        return out
    plan = node.get("Plan", node)
    if isinstance(plan, dict) and "Node Type" in plan:
        out.append(plan)
        for child in plan.get("Plans") or []:
            _walk_pg_plans(child, out)
    elif "Node Type" in node:
        out.append(node)
        for child in node.get("Plans") or []:
            _walk_pg_plans(child, out)
    return out


def suggest_index_from_plan(
    dialect: str,
    plan,
    sql: str,
    *,
    row_threshold: int = 1000,
) -> list[str]:
    """Heuristic: Seq Scan / SCAN table above threshold + filter/join cols -> CREATE INDEX.

    Equality columns before range. Returns suggested DDL strings (unverified).
    """
    suggestions: list[str] = []
    if dialect == "postgresql":
        nodes = _walk_pg_plans(plan)
        for n in nodes:
            if n.get("Node Type") != "Seq Scan":
                continue
            rows = n.get("Actual Rows") or n.get("Plan Rows") or 0
            if rows < row_threshold:
                continue
            table = n.get("Relation Name")
            if not table:
                continue
            filt = n.get("Filter") or n.get("Recheck Cond") or ""
            cols = _cols_from_filter(filt, sql, table)
            if not cols:
                cols = _cols_from_sql_where(sql)
            if not cols:
                continue
            # equality-looking first (col = ), then others
            eq, other = [], []
            for c in cols:
                if re.search(rf"\b{re.escape(c)}\s*=", filt + " " + sql, re.I):
                    eq.append(c)
                else:
                    other.append(c)
            ordered = eq + other
            idx_name = f"ix_{table}_{'_'.join(ordered[:3])}"
            col_list = ", ".join(ordered[:3])
            suggestions.append(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {table} ({col_list});")
    elif dialect == "sqlite":
        for row in plan or []:
            detail = str(row.get("detail", ""))
            # SCAN TABLE t / SCAN t
            m = re.search(r"SCAN(?: TABLE)? (\w+)", detail, re.I)
            if not m:
                continue
            table = m.group(1)
            cols = _cols_from_sql_where(sql)
            if not cols:
                continue
            idx_name = f"ix_{table}_{'_'.join(cols[:3])}"
            col_list = ", ".join(cols[:3])
            suggestions.append(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({col_list});")
    return suggestions


def _cols_from_filter(filt: str, sql: str, table: str) -> list[str]:
    cols = []
    for m in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|>=|<=|>|<|LIKE|ILIKE|IN\b)", filt or "", re.I):
        name = m.group(1)
        if name.lower() in {"and", "or", "not", "null", "true", "false"}:
            continue
        if name not in cols:
            cols.append(name)
    return cols


def _cols_from_sql_where(sql: str) -> list[str]:
    m = re.search(r"\bWHERE\b(.+?)(?:\bORDER\b|\bGROUP\b|\bLIMIT\b|$)", sql, re.I | re.S)
    if not m:
        return []
    clause = m.group(1)
    cols = []
    for cm in re.finditer(
        r"\b(?:\w+\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|>=|<=|>|<|LIKE|ILIKE|IN\b)",
        clause,
        re.I,
    ):
        name = cm.group(1)
        if name.lower() in {"and", "or", "not", "null", "true", "false"}:
            continue
        if name not in cols:
            cols.append(name)
    # also ORDER BY cols
    om = re.search(r"\bORDER\s+BY\s+(.+?)(?:\bLIMIT\b|$)", sql, re.I | re.S)
    if om:
        for part in om.group(1).split(","):
            cm = re.match(r"\s*(?:\w+\.)?([a-zA-Z_][a-zA-Z0-9_]*)", part)
            if cm and cm.group(1) not in cols:
                cols.append(cm.group(1))
    return cols


def _verify_index(engine, dialect: str, ddl: str, sql: str, analyze: bool, timeout_ms: int) -> dict:
    """Create index on local DB, re-EXPLAIN, drop index. Returns before/after plan summary."""
    from sqlalchemy import text

    # Strip CONCURRENTLY for transaction-friendly demo DBs
    ddl_run = ddl.replace("CONCURRENTLY ", "")
    before = None
    after = None
    with engine.connect() as conn:
        before = _fetch_plan(conn, dialect, sql, analyze=analyze)
        conn.commit()
    with engine.begin() as conn:
        conn.execute(text(ddl_run))
    with engine.connect() as conn:
        after = _fetch_plan(conn, dialect, sql, analyze=analyze)
        conn.commit()
    # best-effort drop
    idx = re.search(r"INDEX (?:IF NOT EXISTS )?(\w+)", ddl_run, re.I)
    if idx:
        drop = f"DROP INDEX IF EXISTS {idx.group(1)}"
        try:
            with engine.begin() as conn:
                conn.execute(text(drop))
        except Exception:
            pass
    return {"ddl": ddl, "before": before, "after": after}


def main(argv=None):
    p = argparse.ArgumentParser(description="EXPLAIN a query (dialect-aware, safety-first).")
    add_lang_arg(p)
    p.add_argument("sql", nargs="?", help="SQL query string")
    p.add_argument("--file", help="read SQL from a file")
    p.add_argument(
        "--plain",
        action="store_true",
        help="plan only (no ANALYZE / no execution)",
    )
    p.add_argument(
        "--analyze",
        action="store_true",
        help="force ANALYZE even on local hosts (ignored for non-SELECT / non-local)",
    )
    p.add_argument("--json", dest="as_json", action="store_true", help="emit JSON output")
    p.add_argument(
        "--timeout-ms",
        type=int,
        default=5000,
        help="Postgres statement_timeout in ms (default 5000)",
    )
    p.add_argument(
        "--row-threshold",
        type=int,
        default=1000,
        help="min rows for --suggest-index Seq Scan heuristic",
    )
    p.add_argument(
        "--suggest-index",
        action="store_true",
        help="print heuristic CREATE INDEX from the plan (unverified unless --verify)",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="with --suggest-index: create index on local DB, re-EXPLAIN, log before/after",
    )
    p.add_argument(
        "--database-url",
        default=None,
        help="override DATABASE_URL",
    )
    args = p.parse_args(argv)
    set_lang(args.lang)

    sql = args.sql
    if args.file:
        with open(args.file) as f:
            sql = f.read()
    if not sql:
        p.error("provide SQL as an argument or via --file")
    sql = sql.strip().rstrip(";")

    try:
        from sqlalchemy import create_engine
    except ImportError:
        print(t("ex_need_sqlalchemy"), file=sys.stderr)
        sys.exit(1)

    url = sync_url(args.database_url)
    redacted = redact_url(url)
    local = is_local_url(url)

    # Default to plain on non-local hosts
    analyze = False
    if args.plain:
        analyze = False
    elif args.analyze:
        analyze = True
    elif local:
        analyze = True  # local default: ANALYZE for SELECT
    else:
        print(t("ex_non_local_plain", host=host_from_url(url)), file=sys.stderr)
        analyze = False

    if analyze and not is_select(sql):
        print(t("ex_refuse_analyze"), file=sys.stderr)
        sys.exit(1)

    engine = create_engine(url)
    dialect = engine.dialect.name

    # MySQL is out of Etapa 1 scope for new features but keep basic explain
    allow_writes = bool(args.verify and args.suggest_index and local)

    with engine.connect() as conn:
        _apply_readonly(conn, dialect, args.timeout_ms, allow_writes=False)
        plan = _fetch_plan(conn, dialect, sql, analyze=analyze)
        # read-only txn: rollback is fine
        conn.rollback()

    result = {
        "database": redacted,
        "dialect": dialect,
        "analyze": analyze,
        "local": local,
        "sql": sql,
        "plan": plan,
    }

    suggestions: list[str] = []
    verified = None
    if args.suggest_index:
        suggestions = suggest_index_from_plan(
            dialect, plan, sql, row_threshold=args.row_threshold
        )
        result["suggestions"] = suggestions
        if not suggestions:
            print(t("ex_suggest_none"), file=sys.stderr)
        elif args.verify:
            if not local:
                print(t("ex_suggest_skip_remote"), file=sys.stderr)
                sys.exit(1)
            verified = []
            for ddl in suggestions:
                verified.append(
                    _verify_index(engine, dialect, ddl, sql, analyze=analyze, timeout_ms=args.timeout_ms)
                )
            result["verified"] = verified
            for v in verified:
                print(t("ex_suggest_verified", sql=v["ddl"]))
        else:
            for ddl in suggestions:
                print(t("ex_suggest", sql=ddl))

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(t("ex_redacted_url", url=redacted))
        print(_plan_as_text(dialect, plan))


if __name__ == "__main__":
    main()
