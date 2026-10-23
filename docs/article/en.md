# Your AI wrote the query. Who measured it?

> Etapa 3 draft (EN) · ~1,400 words · numbers only from measured logs  
> Demo numbers: `examples/demo_fastapi/optimization_log.md` + `runs/sqlite/latest.json` (Phase 0 / Etapa 1 PR).  
> Radar case study: publishable slice only — still `[MEDIR]` until Etapa 2 fills the anonymized table.

The PR is green. Tests pass. The JSON looks clean. The route is still slow.

It is rarely “ORMs are slow.” More often the SQL is **correct** and **blind to the database**: wrong (or missing) index, lazy-load N+1, row-by-row inserts. Detectors *suggest*. What we need is a handbrake with a number: **count → measure → change one thing → measure again → write the log**.

## Why AI/ORM code gets slow (without inventing frequencies)

Market write-ups and papers rhyme on the pattern: LLMs get semantics right and efficiency wrong ([EESQLBench](https://doi.org/10.1145/3832269)); AI PRs show more excessive I/O while classic latency regressions stay relatively rare in count ([CodeRabbit](https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report)). There is no solid public source for “X% of N+1 is from AI,” so **we do not quote one**.

The useful layer is not another linter. It is the skill/CLI that **refuses “it’s faster” without proof**.

## What db-route-optimizer is

A Claude Code skill plus Python scripts (MIT, open source, **not sold**):

1. Prove the problem (`querycount` / `EXPLAIN`)
2. Baseline (`bench` median + p95)
3. One change
4. Candidate
5. Compare and append `optimization_log.md`
6. Verify equality (response hash / tests)

Install (once v0.1.0 is on `main` — today on `feat/phase0-python-mvp`):

```bash
git clone https://github.com/Mean-Says/db-route-optimizer.git ~/.claude/skills/db-route-optimizer

pipx install .
# or: uv tool install .
dbro-querycount
dbro-bench --help
dbro-explain --help
```

## Measured before/after (FastAPI demo, SQLite)

Protocol: `--seed 42`, warmup 5, n 30, one change per scenario, equality by hash. Full environment is in the run JSON (Python 3.12.3, Linux x86_64, seed users=200 / posts=1000 / products=5000, `seed_seconds≈0.16`).

Source: [optimization_log.md](https://github.com/Mean-Says/db-route-optimizer/blob/feat/phase0-python-mvp/examples/demo_fastapi/optimization_log.md) (Etapa 1 branch until merge).

| Scenario | Metric | Before | After | Gain |
|----------|--------|-------:|------:|-----:|
| N+1 → `selectinload` | queries/request | 51 | 2 | — |
| N+1 → `selectinload` | median (ms) | 12.87 | 6.79 | 47.24% · 1.90× |
| N+1 → `selectinload` | p95 (ms) | 22.51 | 7.50 | 66.68% · 3.00× |
| Row-by-row insert → bulk | median (ms) | 133.45 | 12.29 | 90.79% · 10.86× |
| Row-by-row insert → bulk | p95 (ms) | 177.38 | 14.10 | 92.05% · 12.58× |
| Index on filter/order | median (ms) | 4.57 | 4.34 | 5.03% · 1.05× |

The index latency win on SQLite at 5k rows was small; the JSON keeps the verified `--suggest-index` entry. Postgres usually makes the plan change louder — `[MEDIR: runs/postgres after make reproduce with Docker]`.

A second SQLite run kept the same **verdicts** (N+1 and batch clearly better; equality ok). Absolute ms jitter; we do not invent the story.

## The protocol (short)

1. Declared cardinality + fixed seed — toy data does not count.
2. Same environment; warmup ≥ 5; n ≥ 30; median and p95.
3. One change per comparison.
4. Correctness: equal hash (or tests); otherwise it did not “improve.”
5. Everything in the log with git SHA and environment.
6. Never bench writes/DDL/`EXPLAIN ANALYZE` on production.

## Real case: Radar de Empregos

The plan uses Radar (FastAPI + Postgres on a VPS) as the field test: sanitized local copy, targets from `pg_stat_statements`, ≥3 optimizations in a **private** log, and only an anonymized slice in the article.

**Not publicly measured yet.** No sanitized dump or closed-app checkout in the environment that drafted this. Public playbook: `docs/radar/` (Etapa 2 PR). Publishable table:

| Metric | Before | After | Gain |
|--------|-------:|------:|-----:|
| Queries/request | [MEDIR: Radar] | [MEDIR] | — |
| p50 | [MEDIR] | [MEDIR] | [MEDIR] |
| p95 | [MEDIR] | [MEDIR] | [MEDIR] |
| Plan shape | [MEDIR] | [MEDIR] | — |
| Environment (order of magnitude) | [MEDIR] | | |

Until Rafael reviews the anonymized table, the article must not cite real table names, literal SQL, or exact production counts.

## Honest limits

- Query counter is solid for SQLAlchemy; other stacks via references.
- No third-party HypoPG/Dexter/MCP integrations — in-house capabilities.
- Index suggestions become recommendations only after create-on-copy + re-measure.
- Full Postgres `make reproduce`: `[MEDIR]` until Docker is available.

## Contribute

Repo: https://github.com/Mean-Says/db-route-optimizer (MIT). Good-first issues after v0.1.0. Skill-list submissions come **after** this article is published (plan Etapa 3).

Measure → change → measure → record. No log number, no optimization — just vibes.
