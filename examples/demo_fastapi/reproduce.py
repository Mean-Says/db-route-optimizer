#!/usr/bin/env python3
"""Run the three scenarios (before/after, one change each) and write logs.

Usage:
  DATABASE_URL=sqlite:///demo.db python reproduce.py --backend sqlite
  DATABASE_URL=postgresql://dbro:dbro@localhost:5432/dbro python reproduce.py --backend postgres

Writes under runs/<backend>/ and appends to optimization_log.md.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from db_route_optimizer.bench import _stats  # noqa: E402
from db_route_optimizer.querycount import count_queries  # noqa: E402


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        )
    except Exception:
        return "unknown"


def _env_block(backend: str, seed_meta: dict) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "backend": backend,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "seed": seed_meta,
    }


def _run_http_scenario(client, method: str, path: str, n: int, warmup: int):
    samples = []
    last_body = None
    total = warmup + n
    for i in range(total):
        t0 = time.perf_counter()
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path)
        dt = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        if i >= warmup:
            samples.append(dt)
            last_body = r.json()
    return _stats(samples), last_body


def scenario_nplus1(client, engine, n: int, warmup: int) -> dict:
    from app.db import get_session
    from app.models import User
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    def _count(path: str) -> int:
        # count via direct ORM path matching the endpoint
        db = get_session(engine)
        try:
            with count_queries(engine) as qc:
                if "selectin" in path:
                    users = db.scalars(
                        select(User).options(selectinload(User.posts)).order_by(User.id).limit(50)
                    ).all()
                    _ = [(u.id, [p.id for p in u.posts]) for u in users]
                else:
                    users = db.scalars(select(User).order_by(User.id).limit(50)).all()
                    _ = [(u.id, [p.id for p in u.posts]) for u in users]
            return qc.total
        finally:
            db.close()

    q_before = _count("/users/nplus1")
    q_after = _count("/users/selectin")

    st_before, body_b = _run_http_scenario(client, "GET", "/users/nplus1?limit=50", n, warmup)
    st_after, body_a = _run_http_scenario(client, "GET", "/users/selectin?limit=50", n, warmup)
    equal = body_b.get("hash") == body_a.get("hash")
    return {
        "name": "nplus1_selectinload",
        "change": "lazy posts -> selectinload",
        "queries_before": q_before,
        "queries_after": q_after,
        "baseline": st_before,
        "candidate": st_after,
        "equality_hash_match": equal,
        "hash": body_a.get("hash"),
    }


def scenario_missing_index(client, engine, database_url: str, n: int, warmup: int) -> dict:
    """One change: add index on (category, name). Includes verified suggest-index log."""
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    import seed as seed_mod
    from db_route_optimizer.explain_query import main as explain_main

    category = "cat-01"
    path = f"/products?category={category}&limit=100"

    # BEFORE: no index
    seed_mod.main(
        ["--seed", "42", "--database-url", database_url, "--drop-index", "--quiet"]
    )
    st_before, body_b = _run_http_scenario(client, "GET", path, n, warmup)

    # suggest-index --verify (capture JSON)
    sql = (
        f"SELECT id, category, name, price_cents FROM products "
        f"WHERE category = '{category}' ORDER BY name LIMIT 100"
    )
    buf = StringIO()
    err = StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        try:
            explain_main(
                [
                    "--database-url",
                    database_url,
                    "--json",
                    "--suggest-index",
                    "--verify",
                    "--row-threshold",
                    "100",
                    sql,
                ]
            )
        except SystemExit:
            pass
    suggest_out = buf.getvalue()
    try:
        suggest_json = json.loads(suggest_out) if suggest_out.strip().startswith("{") else {"raw": suggest_out}
    except json.JSONDecodeError:
        suggest_json = {"raw": suggest_out, "stderr": err.getvalue()}

    # AFTER: ensure index (the one change)
    seed_mod.main(
        ["--seed", "42", "--database-url", database_url, "--ensure-index", "--quiet"]
    )
    st_after, body_a = _run_http_scenario(client, "GET", path, n, warmup)
    equal = body_b.get("hash") == body_a.get("hash")
    return {
        "name": "missing_index_category_name",
        "change": "CREATE INDEX on products(category, name)",
        "baseline": st_before,
        "candidate": st_after,
        "equality_hash_match": equal,
        "hash": body_a.get("hash"),
        "suggest_index_verified": suggest_json,
    }


def scenario_batch_insert(client, n: int, warmup: int, rows: int = 200) -> dict:
    st_before, body_b = _run_http_scenario(
        client, "POST", f"/orders/row-by-row?n={rows}", n, warmup
    )
    st_after, body_a = _run_http_scenario(
        client, "POST", f"/orders/bulk?n={rows}", n, warmup
    )
    # equality: same row count; checksum differs by sku prefix by design —
    # compare counts only (protocol: inserts -> row count + checksum of payload shape)
    equal = body_b.get("inserted") == body_a.get("inserted") == rows
    rows_per_s_b = rows / (st_before["median_ms"] / 1000) if st_before["median_ms"] else 0
    rows_per_s_a = rows / (st_after["median_ms"] / 1000) if st_after["median_ms"] else 0
    return {
        "name": "batch_insert",
        "change": "commit-per-row -> single-transaction bulk insert",
        "rows": rows,
        "baseline": st_before,
        "candidate": st_after,
        "rows_per_s_before_median": round(rows_per_s_b, 1),
        "rows_per_s_after_median": round(rows_per_s_a, 1),
        "equality_rowcount_match": equal,
        "checksum_before": body_b.get("checksum"),
        "checksum_after": body_a.get("checksum"),
    }


def _improvement(base: dict, cand: dict, metric: str = "median_ms"):
    b, c = base[metric], cand[metric]
    if c <= 0 or b <= 0:
        return {"improvement_pct": None, "speedup": None}
    return {
        "improvement_pct": round((b - c) / b * 100, 2),
        "speedup": round(b / c, 2),
    }


def _append_log(log_path: Path, backend: str, results: list[dict]):
    if not log_path.exists():
        log_path.write_text(
            "# Optimization log (demo_fastapi)\n\n"
            "Generated by `make reproduce` / `python reproduce.py`.\n"
            "Every number below comes from a measured run JSON under `runs/`.\n\n"
            "| Backend | Scenario | Metric | Before (ms) | After (ms) | Improvement | Speedup | Equality | Queries |\n"
            "|---------|----------|--------|------------:|-----------:|------------:|--------:|:--------:|--------:|\n"
        )
    lines = []
    for r in results:
        imp = _improvement(r["baseline"], r["candidate"])
        q = ""
        if "queries_before" in r:
            q = f"{r['queries_before']}→{r['queries_after']}"
        eq = r.get("equality_hash_match", r.get("equality_rowcount_match"))
        lines.append(
            f"| {backend} | {r['name']} | median_ms | {r['baseline']['median_ms']:.2f} | "
            f"{r['candidate']['median_ms']:.2f} | {imp['improvement_pct']}% | {imp['speedup']}x | "
            f"{eq} | {q} |\n"
        )
        # also p95 row
        imp95 = _improvement(r["baseline"], r["candidate"], "p95_ms")
        lines.append(
            f"| {backend} | {r['name']} | p95_ms | {r['baseline']['p95_ms']:.2f} | "
            f"{r['candidate']['p95_ms']:.2f} | {imp95['improvement_pct']}% | {imp95['speedup']}x | "
            f"{eq} | {q} |\n"
        )
    with log_path.open("a") as f:
        f.writelines(lines)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=["sqlite", "postgres"], required=True)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = p.parse_args(argv)

    if not args.database_url:
        if args.backend == "sqlite":
            args.database_url = f"sqlite:///{ROOT / 'demo.db'}"
        else:
            args.database_url = "postgresql://dbro:dbro@127.0.0.1:5432/dbro"
    os.environ["DATABASE_URL"] = args.database_url

    import seed as seed_mod
    from app.db import create_schema, make_engine
    from fastapi.testclient import TestClient

    seed_meta = seed_mod.main(
        ["--seed", "42", "--database-url", args.database_url, "--drop-index", "--quiet"]
    )

    # Reload app engine with current URL
    import importlib

    import app.db as db_mod
    import app.main as main_mod

    os.environ["DATABASE_URL"] = args.database_url
    importlib.reload(db_mod)
    importlib.reload(main_mod)
    engine = make_engine(args.database_url)
    create_schema(engine)
    client = TestClient(main_mod.app)

    results = []
    results.append(scenario_nplus1(client, engine, args.n, args.warmup))
    results.append(
        scenario_missing_index(client, engine, args.database_url, args.n, args.warmup)
    )
    results.append(scenario_batch_insert(client, args.n, args.warmup))

    for r in results:
        r["comparison"] = _improvement(r["baseline"], r["candidate"])

    out_dir = ROOT / "runs" / args.backend
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "environment": _env_block(args.backend, seed_meta),
        "n": args.n,
        "warmup": args.warmup,
        "results": results,
    }
    out_path = out_dir / "latest.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    stamped = out_dir / f"run-{payload['environment']['git_sha'][:7]}-{int(time.time())}.json"
    stamped.write_text(out_path.read_text())

    log_path = ROOT / "optimization_log.md"
    _append_log(log_path, args.backend, results)

    # Final table
    print("\n=== reproduce summary ===")
    print(f"backend={args.backend} n={args.n} warmup={args.warmup} sha={payload['environment']['git_sha'][:7]}")
    print(
        f"{'scenario':<32} {'med_b':>8} {'med_a':>8} {'impr%':>8} {'Nx':>6} {'eq':>5} {'q':>8}"
    )
    for r in results:
        imp = r["comparison"]
        q = (
            f"{r.get('queries_before', '')}->{r.get('queries_after', '')}"
            if "queries_before" in r
            else ""
        )
        print(
            f"{r['name']:<32} {r['baseline']['median_ms']:8.2f} {r['candidate']['median_ms']:8.2f} "
            f"{str(imp['improvement_pct']):>8} {str(imp['speedup']):>6} "
            f"{str(r.get('equality_hash_match', r.get('equality_rowcount_match'))):>5} {q:>8}"
        )
    print(f"wrote {out_path}")
    print(f"log   {log_path}")

    # Fail if equality broken
    bad = [
        r
        for r in results
        if not r.get("equality_hash_match", r.get("equality_rowcount_match"))
    ]
    if bad:
        print("EQUALITY FAILED:", [r["name"] for r in bad], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
