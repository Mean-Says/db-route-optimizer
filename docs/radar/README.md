# Etapa 2 — Radar de Empregos playbook (prep)

This tree prepares the **public** side of Etapa 2 from the project plan: use
db-route-optimizer against a **local sanitized copy** of the Radar Postgres database.
Production stays **read-only** (stats + access logs only). Private measurement logs never
land in this repo.

The Radar application itself is **closed source** (Python/FastAPI + Postgres on a VPS).
This repo only ships hooks, checklists, and scripts.

## Access required (blocked without these)

| Item | Why | Status in the agent environment that opened this PR |
|------|-----|-----------------------------------------------------|
| Closed Radar app repo (or deploy checkout) | Run/measure HTTP routes; apply migrations | **Missing** — not in Mean-Says public org as an app repo; only `radar-scrapers` (ingest scrapers) is public |
| Sanitized local Postgres dump (`pg_dump -Fc` → `pg_restore`, same major) | Measure before/after without touching prod | **Missing** — no dump / `DATABASE_URL` for a copy |
| Read-only prod role + `pg_stat_statements` (may need `shared_preload_libraries` + maintenance restart) | Choose targets by data | **Missing** — no VPS credentials |
| Access logs (or APM) for route volume/latency | Cross-check hot routes vs SQL | **Missing** |
| `.env` with copy URL **outside git** | Point tools at the local copy | Template only: `.env.radar.example` |

Public org artifact found: [Mean-Says/radar-scrapers](https://github.com/Mean-Says/radar-scrapers) (scrapers → `POST /api/jobs/ingest`). That is **not** the FastAPI app under optimization.

## Workflow (once access exists)

1. **Security** — follow [CHECKLIST.md](CHECKLIST.md). Prod: statistics only. Dump off-peak → restore locally → sanitize → `ANALYZE`.
2. **Pick targets** — [TARGET_SELECTION.md](TARGET_SELECTION.md) + `python scripts/radar/pg_stat_top.py`.
3. **Measure on the copy** — protocol §3 (`warmup≥5`, `n≥30`, one change, equality hash). Use `dbro-bench` / `dbro-querycount` / `dbro-explain` from the Phase 0 package when available, or `python scripts/bench.py` on `main`.
4. **Private log** — copy `examples/radar_private/optimization_log.TEMPLATE.md` to a path **outside** this repo (or a private gist). Never commit real SQL literals, table names, or PII.
5. **Ship to prod** — migration + normal deploy only; confirm via observation (`pg_stat_statements`, logs), no live bench on prod.
6. **Publishable slice** — fill [PUBLISHABLE_TABLE.md](PUBLISHABLE_TABLE.md); Rafael reviews before Etapa 3 cites it.
7. **Feedback to the skill** — bugs found here → public issues/PRs on this repo **before** the Etapa 3 article.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/radar/pg_stat_top.py` | Top queries by `total_exec_time` / `mean_exec_time` / `calls` (read-only) |
| `scripts/radar/hash_response.py` | SHA-256 of JSON body with volatile keys stripped (equality check) |
| `scripts/radar/measure_endpoint.py` | Thin wrapper: bench an HTTP URL and optionally hash the body |

## DoD (from the plan) — tracking

- [ ] Sanitized local copy; zero writes to prod
- [ ] Targets justified by data
- [ ] ≥3 optimizations measured and privately logged
- [ ] Applied via deploy; confirmed by observation
- [ ] Anonymized table reviewed by Rafael
