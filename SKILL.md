---
name: db-route-optimizer
description: >-
  Identifies and fixes performance bottlenecks in database queries and API routes/endpoints,
  proves N+1 with deterministic query counting, and quantifies every fix by benchmarking
  before vs after (% improvement + Nx speedup) into an optimization log. Stack-agnostic:
  works with any relational DB and ORM (PostgreSQL/MySQL/SQLite; SQLAlchemy/Django/Prisma/
  TypeORM/ActiveRecord) and any web framework (FastAPI/Express/Django/Rails/etc). Use when the
  user wants to optimize or speed up a slow query or endpoint, fix N+1 queries, add missing
  indexes, reduce latency, profile a route, count queries, or benchmark before/after
  performance. Triggers: "optimize this query/route", "it's slow", "make it faster", "N+1",
  "missing index", "count the queries", "compare speed before and after", "how many times
  faster", "% improvement", "endpoint latency".
---

# DB & Route Optimizer

Optimize database queries and API endpoints across any stack, and **always quantify the result** —
prove N+1 by counting queries, then record before/after latency, % improvement, and speedup.

## Core rule: measure -> change -> measure -> record

Never claim an optimization without a number. The flow is non-negotiable:

1. **Identify & prove** the hotspot — count queries / read the plan, don't guess.
2. **Baseline** — benchmark the current code. Save the numbers.
3. **Optimize** — apply ONE change from the references (isolate the variable).
4. **Re-benchmark** — same conditions, candidate code.
5. **Compare & record** — % faster + Nx speedup into the optimization log.
6. **Verify correctness** — output is identical and tests pass. A faster-but-wrong query is a regression.

Safety: benchmark read-only endpoints; never run write operations against production from a
workstation. Add indexes/schema changes only through the project's migration tool, never ad-hoc on prod.
If the project has its own rules (how to run, how to verify, what not to touch), follow those first.

## Step 1 — Identify & prove

Pick the technique that fits — see `references/db-optimization.md` ("Find the hotspot"):
- **Count queries** (the rigorous N+1 test): run the suspect path through a query counter.
  `1 + N` over a list = N+1. `scripts/querycount.py` (SQLAlchemy) + per-stack snippets in
  `references/query-counting.md` (Django/Prisma/TypeORM/ActiveRecord/raw).
- **Read the plan**: `scripts/explain_query.py "<SQL>"` (Postgres/MySQL/SQLite). `Seq Scan`/full
  scan under a filter on a big table = missing index.
- **Grep** for the shape: a query inside a `for`/`map`/`.each`, ORM relation access in a loop,
  reads with no limit, blocking calls in async handlers.

Top suspects, in order: N+1 queries · queries inside a loop · missing index · unbounded reads ·
blocking calls on the event loop · FTS without the right index.

## Step 2 — Baseline benchmark

```bash
python scripts/bench.py --url "https://<host>/<read-only-endpoint>" --n 50 --warmup 5 \
  --label baseline --out /tmp/perf/base.json
# rate-limited host? add --sleep 0.3   |  self-signed/local TLS? --insecure
```
For a query (not HTTP), wrap a read-only script: `--cmd "python run_query.py"`. To benchmark a
query path directly, count queries with `querycount.py` and/or time it with `explain_query.py`.

## Step 3 — Optimize (one change)

- DB problems -> `references/db-optimization.md` (N+1, indexes, count+fetch, over-fetch, loops,
  pagination, FTS, bulk writes, transactions) — examples in SQLAlchemy/Django/Prisma/ActiveRecord.
- Endpoint problems -> `references/route-optimization.md` (blocking loop, concurrency, serialization,
  caching, payload, middleware).

Change one thing at a time so the measured delta is attributable.

## Step 4 — Re-benchmark

```bash
python scripts/bench.py --url "https://<host>/<same-endpoint>" --n 50 --warmup 5 \
  --label candidate --out /tmp/perf/cand.json
```
Identical `--n`, `--warmup`, target, and conditions as the baseline.

## Step 5 — Compare & record

```bash
python scripts/bench.py --compare /tmp/perf/base.json /tmp/perf/cand.json \
  --name "GET /users" --log docs/perf/optimization_log.md
```
Prints e.g. `-> 92.3% faster | 13.07x` and appends a row to the log (Target | Metric | Before |
After | Improvement | Speedup). Report median by default; also mention p95 (`--metric p95_ms`) since
event-loop/caching fixes mostly improve the tail. For N+1 fixes, also record the query-count drop
(e.g. `401 -> 3 queries`) — it's the cleanest before/after when wall-time isn't measurable.

## Step 6 — Verify correctness

- Response is semantically identical before/after (diff a sample payload).
- Test suite green. Keep a `assert_max(k)` query-count test (see `query-counting.md`) so a future
  change that reintroduces N+1 fails CI.
- Commit only after tests pass; follow the project's commit/deploy conventions.

## Scripts
- `scripts/bench.py` — latency benchmark + before/after comparison (stdlib only). `--url`/`--cmd`,
  `--compare`, logs % improvement and Nx speedup to a markdown table. `--sleep` (rate limits),
  `--insecure` (TLS), `--metric`.
- `scripts/querycount.py` — deterministic query counter + N+1 guard (SQLAlchemy; self-test runnable).
- `scripts/explain_query.py` — `EXPLAIN [ANALYZE]` for a query, dialect-aware (PG/MySQL/SQLite).

## References
- `references/db-optimization.md` — DB antipatterns & fixes, multi-ORM.
- `references/route-optimization.md` — endpoint/route-level optimizations, multi-framework.
- `references/query-counting.md` — deterministic N+1 detection per stack + CI regression guard.
