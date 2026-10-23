# Choosing optimization targets (data-first)

## SQL (read-only on prod stats or on the local copy)

```sql
SELECT queryid,
       calls,
       round(total_exec_time) AS total_ms,
       round(mean_exec_time, 2) AS mean_ms,
       rows,
       left(query, 120) AS query_preview
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

Also review by `mean_exec_time DESC` and by `calls DESC` (high call count → N+1 suspects).

Helper: `python scripts/radar/pg_stat_top.py --order total|mean|calls --limit 10`

## Cross-check with HTTP

Join top SQL with access-log or APM routes by volume and p95 latency. Prefer routes that are both hot in SQL **and** hot in traffic.

## Suspicions to confirm (from the plan)

Do not treat these as proven — only as hypotheses to measure:

- Listing with filter + high `OFFSET`
- Search with `ILIKE '%x%'`
- N+1 on detail / company pages
- Alerts fired in a loop
- Ingest row-by-row
- Admin count queries

## One change per comparison

Baseline → apply a single fix on the **copy** → re-measure → private log. Equality via response hash (`scripts/radar/hash_response.py`), ignoring volatile fields.
