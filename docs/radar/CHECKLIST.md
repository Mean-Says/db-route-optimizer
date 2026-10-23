# Etapa 2 security checklist

Print and tick. Do **not** skip sanitization.

## Production (read-only)

- [ ] Dedicated DB role with **SELECT** on stats views only (`pg_stat_statements`, `pg_stat_activity` as needed); no DML/DDL.
- [ ] `pg_stat_statements` enabled (`shared_preload_libraries`); restart only in a maintenance window if required.
- [ ] No `EXPLAIN ANALYZE`, no DDL, no writes from workstations against prod.
- [ ] No benchmarking of write paths against prod.
- [ ] Credentials only in local secret store / VPS env — never in git or chat logs.

## Local copy

- [ ] `pg_dump -Fc` taken **off-peak**.
- [ ] Restored with `pg_restore` on the **same Postgres major** as prod.
- [ ] Sanitize before any measurement:
  - [ ] emails, names, phones
  - [ ] CVs / resumes / free-text PII
  - [ ] tokens, API keys, session IDs
  - [ ] IPs and other identifiers in logs tables
- [ ] `ANALYZE` after restore + sanitize.
- [ ] Copy URL only in `.env` (see `.env.radar.example`); `.env` is gitignored.
- [ ] Confirm host is local (`localhost` / `127.0.0.1`) before `dbro-explain --analyze` or `--suggest-index --verify`.

## Logging

- [ ] Measurement log stays **private** (not this public repo).
- [ ] Publishable table uses only allowed fields ([PUBLISHABLE_TABLE.md](PUBLISHABLE_TABLE.md)).
- [ ] Rafael reviews the anonymized table before any public article cites it.
