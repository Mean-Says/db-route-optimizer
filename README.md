# db-route-optimizer

A [Claude Code](https://docs.claude.com/en/docs/claude-code) **skill** that finds and fixes
database and API performance bottlenecks — and **proves every fix with a number**.

Most "make it faster" advice stops at the change. This skill enforces a measurement-first loop:
prove the problem (count queries / read the plan), benchmark the baseline, apply one change,
re-benchmark, and record the **% improvement and Nx speedup** to a log. No claim without a number.

Stack-agnostic: any relational DB (PostgreSQL / MySQL / SQLite) and ORM (SQLAlchemy / Django /
Prisma / TypeORM / ActiveRecord), any web framework (FastAPI / Express / Django / Rails / …).

## What it does

- **Detects** the usual killers: N+1 queries, missing indexes, queries in loops, unbounded reads,
  blocking calls on the event loop, full-text search without the right index.
- **Proves N+1 deterministically** by counting the queries a code path emits (`1 + N` over a list
  = N+1) — not by guessing from grep.
- **Benchmarks before vs after** and records `92.3% faster | 13.07x` into a markdown log.
- **Keeps you honest**: behavior-preserving fixes only, verified against the test suite, with a
  query-count guard you can keep in CI to stop N+1 from coming back.

## The workflow

```
1. Identify & prove   count queries / EXPLAIN ANALYZE — don't guess
2. Baseline           benchmark current code, save numbers
3. Optimize           apply ONE change (isolate the variable)
4. Re-benchmark       same conditions, candidate code
5. Compare & record   % faster + Nx speedup -> optimization log
6. Verify             identical output + tests pass + CI query guard
```

## Tools (`scripts/`, stdlib-first)

| Script | What it does |
|--------|--------------|
| `bench.py` | Latency benchmark + before/after comparison. Times an HTTP endpoint (`--url`) or any command (`--cmd`), computes median/p95, and `--compare` two runs → % improvement + Nx speedup, logged to a markdown table. Handles rate limits (`--sleep`) and self-signed TLS (`--insecure`). Stdlib only. |
| `querycount.py` | Deterministic query counter + N+1 guard for SQLAlchemy. Run it (`python scripts/querycount.py`) to see N+1 (51 queries) vs batched (2). `assert_max(k)` fails CI on regression. |
| `explain_query.py` | `EXPLAIN [ANALYZE]` for a query, dialect-aware (Postgres / MySQL / SQLite). |

```bash
# count queries: prove N+1 (self-test)
python scripts/querycount.py
#   N+1:     51 queries  {'SELECT': 51}
#   batched: 2 queries   {'SELECT': 2}

# benchmark before/after and record the gain
python scripts/bench.py --url "https://example.com/api/users" --n 50 --label baseline --out base.json
# ...apply the fix...
python scripts/bench.py --url "https://example.com/api/users" --n 50 --label candidate --out cand.json
python scripts/bench.py --compare base.json cand.json --name "GET /users" --log optimization_log.md
#   -> 92.3% faster | 13.07x
```

## References (`references/`)

- `db-optimization.md` — DB antipatterns & fixes (N+1, indexes, count+fetch, over-fetch, loops,
  pagination, FTS, bulk writes, transactions), with examples across ORMs.
- `route-optimization.md` — endpoint-level wins (blocking loop, concurrency, serialization, caching,
  payload, middleware), across frameworks.
- `query-counting.md` — how to count queries on every stack (SQLAlchemy, Django, Prisma, TypeORM,
  ActiveRecord, raw drivers, APM) and guard against regressions in CI.

## Install

As a Claude Code skill, drop the folder into your skills directory:

```bash
git clone https://github.com/<owner>/db-route-optimizer.git ~/.claude/skills/db-route-optimizer
```

Then ask Claude things like *"optimize this endpoint and show me the before/after"*, *"is this an
N+1?"*, or *"add an index and prove the speedup"*. The scripts also work standalone — no Claude required.

## Why not just an APM / nplusone / a linter?

Those are great and complementary: **nplusone / pytest-capquery** catch N+1 at runtime,
**Datadog/Sentry** catch it in prod, **EXPLAIN** shows the plan. This skill is the *workflow that
ties them together* — prove → baseline → fix → re-measure → record — so an optimization always ends
with an auditable number, and the fix is checked for behavior preservation, not just speed.

## License

MIT — see [LICENSE](LICENSE).
