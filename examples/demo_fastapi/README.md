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

Seed duration: measured on each run (`seed_seconds` in the JSON). On the cloud agent that
first produced `runs/sqlite/latest.json`, `seed_seconds ≈ 0.16–0.17` (Linux x86_64, Python 3.12).

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

**Status:** `make reproduce-sqlite` is measured and logged in this tree. Full `make reproduce`
(Postgres + SQLite) was **not** run in the environment that opened the Phase 0 PR — that VM
had no Docker. CI still runs explain against a `postgres:16` service. To fill Postgres rows in
`optimization_log.md` / `runs/postgres/`, run `make reproduce` on a machine with Docker and
commit the new log JSON (do not invent numbers).

## Outputs

- `runs/sqlite/latest.json`, `runs/postgres/latest.json` — full stats (median, p95, n≥30)
- `optimization_log.md` — markdown table (only measured numbers)

Protocol: warmup≥5, n≥30, one change per comparison, equality via response hash
(inserts: row count + checksum).
