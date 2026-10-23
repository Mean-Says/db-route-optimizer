# Publishable results (Radar) — template

**Rafael must review before any public article cites this table.**

## Allowed

| Field | Example shape |
|-------|----------------|
| Queries / request | `N → M` |
| p50 / p95 + iterations | ms, `n≥30`, `warmup≥5` |
| Plan shape | e.g. `Seq Scan → Index Scan` |
| SQL **anonymized** | placeholders for identifiers |
| Environment order of magnitude | “Postgres 16, local copy, ~O(10^5) rows” — not exact prod counts |
| Change description | “eager-load relation”, “add btree on filter col”, “bulk insert” |

## Forbidden

- Real table / column names
- Business rules
- Literal SQL from prod
- Secrets, internal URLs
- User data
- Exact production row counts

## Table (fill after private measurements)

| # | Change (public wording) | Queries before → after | p50 before → after | p95 before → after | Plan shape | n / warmup | Env (order of magnitude) |
|---|-------------------------|------------------------:|-------------------:|-------------------:|------------|------------|--------------------------|
| 1 | [MEDIR: after private log] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] |
| 2 | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] |
| 3 | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] | [MEDIR] |

Private evidence path (not in git): `_______________________________`  
Reviewer: Rafael · Date: ________
