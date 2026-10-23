# Demo: FastAPI + SQLAlchemy 2.x

Reproducible before/after measurements for three scenarios (one change each):

1. **N+1** — lazy `User.posts` → `selectinload`
2. **Missing index** — filter/order on `products(category, name)` → verified index
3. **Batch insert** — commit-per-row → single-transaction bulk insert

## Environment

Documented in each `runs/<backend>/latest.json` (`environment` block): git SHA, Python,
platform, seed cardinalities, seed duration.

Declared seed cardinalities (see `seed.py`):

| Entity | Count |
|--------|------:|
| users | 200 |
| posts | 1000 (5 per user) |
| products | 5000 |
| categories | 20 |

Seed duration: measured on each run (`seed_seconds` in the JSON). Initial choice pending
first timed run — `[MEDIR: seed_seconds on CI/dev]`.

## Quick start (SQLite, no Docker)

```bash
cd examples/demo_fastapi
make reproduce-sqlite
```

## Full reproduce (Postgres 16 via Docker + SQLite)

```bash
make reproduce
```

Requires Docker. Postgres URL default: `postgresql://dbro:dbro@127.0.0.1:5432/dbro`.

## Outputs

- `runs/sqlite/latest.json`, `runs/postgres/latest.json` — full stats (median, p95, n≥30)
- `optimization_log.md` — markdown table (only measured numbers)

Protocol: warmup≥5, n≥30, one change per comparison, equality via response hash
(inserts: row count + checksum).
