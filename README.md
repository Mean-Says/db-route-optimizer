# db-route-optimizer

A [Claude Code](https://docs.claude.com/en/docs/claude-code) **skill** (and CLI) that finds
and fixes database / API performance bottlenecks — and **proves every fix with a number**.

Most "make it faster" advice stops at the change. This skill enforces a measurement-first loop:
prove the problem (count queries / read the plan), benchmark the baseline, apply one change,
re-benchmark, and record the **% improvement and Nx speedup** to a log. No claim without a
reproducible log from `make reproduce`.

Open source (MIT), for public benefit. Not sold. No SaaS, no paid plan.

Core stack for v0.1: **Python**, SQLAlchemy (optional), PostgreSQL / SQLite.

## Installation

### As a Claude Code skill

Clone or copy this folder into your Claude Code skills directory (see the
[official docs](https://docs.claude.com/en/docs/claude-code/skills) for the current path):

```bash
git clone https://github.com/Mean-Says/db-route-optimizer.git ~/.claude/skills/db-route-optimizer
```

Then ask Claude things like *"optimize this endpoint and show me the before/after"*,
*"is this an N+1?"*, or *"add an index and prove the speedup"*.

### As a CLI (`pipx` / `uv`)

From a checkout (or after publish to PyPI):

```bash
# pipx
pipx install .

# or uv
uv tool install .

# with SQLAlchemy / Postgres extras
pipx install '.[sqlalchemy]'
pipx install '.[postgres]'
```

Entry points: `dbro-bench`, `dbro-querycount`, `dbro-explain`.

Without installing, the scripts still work:

```bash
python scripts/bench.py --help
python scripts/querycount.py
python scripts/explain_query.py --help
```

## 5-minute quickstart

```bash
# 1) Prove N+1 by counting (needs: pip install '.[sqlalchemy]')
dbro-querycount
#   N+1:     51 queries ...
#   batched: 2 queries ...

# 2) Explain a query (local SQLite / Postgres only for ANALYZE)
export DATABASE_URL=sqlite:///tmp/demo.db
dbro-explain --plain "SELECT 1"

# 3) Bench before/after and log the gain (stdlib only)
dbro-bench --cmd "python -c 'pass'" --n 30 --warmup 5 --label baseline --out /tmp/base.json
dbro-bench --cmd "python -c 'pass'" --n 30 --warmup 5 --label candidate --out /tmp/cand.json
dbro-bench --compare /tmp/base.json /tmp/cand.json --name "noop" --log /tmp/optimization_log.md

# Portuguese output
dbro-bench --lang pt-BR --compare /tmp/base.json /tmp/cand.json --name "noop"
```

Reproducible demo (3 scenarios × Postgres + SQLite):

```bash
cd examples/demo_fastapi
make reproduce-sqlite   # no Docker
make reproduce          # Postgres 16 via docker compose + SQLite
```

Numbers in docs come only from the log under `examples/demo_fastapi/`
([optimization_log.md](examples/demo_fastapi/optimization_log.md) +
`runs/<backend>/latest.json`). Example (SQLite, n=30, warmup=5, seed=42 — see log for
environment): N+1 **51→2 queries**, median **~47% faster**; batch insert median **~91% faster**.
Missing-index latency on SQLite at 5k rows is small; see the verified suggest-index entry in the
JSON. Placeholders look like `[MEDIR: ...]` until measured.

## What it does

- **Detects** common killers: N+1, missing indexes, row-by-row writes.
- **Proves N+1** by counting queries (`1 + N` over a list = N+1).
- **Benchmarks** before vs after (median / p95) into a markdown log.
- **EXPLAIN** with read-only + timeout, password redaction, and verified `--suggest-index`
  on a local copy only.
- **Keeps you honest**: one change per comparison; equality checked; CI query guard.

## The workflow

```
1. Identify & prove   count queries / EXPLAIN — don't guess
2. Baseline           benchmark current code, save numbers
3. Optimize           apply ONE change (isolate the variable)
4. Re-benchmark       same conditions, candidate code
5. Compare & record   % faster + Nx speedup -> optimization log
6. Verify             identical output + tests pass + CI query guard
```

## Tools

| Tool | What it does |
|------|----------------|
| `dbro-bench` / `scripts/bench.py` | Latency bench + `--compare` (stdlib). |
| `dbro-querycount` / `scripts/querycount.py` | SQLAlchemy query counter, duplicates, raise/fail mode. |
| `dbro-explain` / `scripts/explain_query.py` | Dialect-aware EXPLAIN; read-only; `--suggest-index --verify`. |

## References (`references/`)

- `db-optimization.md` — DB antipatterns & fixes
- `route-optimization.md` — endpoint-level wins
- `query-counting.md` — counting queries per stack + CI guard

## Why not just an APM / nplusone / a linter?

Those are complementary: detectors *suggest*; this project *proves and records* with a
reproducible before/after log.

## Contributing / security

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
[SECURITY.md](SECURITY.md), and [CHANGELOG.md](CHANGELOG.md).

## Radar de Empregos playbook (Etapa 2 prep)

Closed-app measurements stay private. Public hooks/checklists/scripts:
[`docs/radar/`](docs/radar/README.md). Requires a sanitized local Postgres copy — see the access
table in that README.

## Article drafts (Etapa 3)

PT-BR + EN drafts (demo numbers from measured logs; Radar still `[MEDIR]`):
[`docs/article/`](docs/article/README.md). Not for public posting until placeholders are cleared.

## License

MIT — see [LICENSE](LICENSE).

