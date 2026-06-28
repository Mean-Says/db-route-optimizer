# Database optimization — stack-agnostic

Antipatterns and fixes that apply to any relational DB + ORM. Examples show a few ORMs where
the syntax differs; the principle is the same everywhere. Pair with `query-counting.md` to
*prove* a problem before fixing and `bench.py` to *measure* the gain after.

## Table of contents
- [Find the hotspot](#find-the-hotspot)
- [1. N+1 queries](#1-n1-queries)
- [2. Missing indexes](#2-missing-indexes)
- [3. count + fetch in two trips](#3-count--fetch-in-two-trips)
- [4. Over-fetching columns / whole rows](#4-over-fetching-columns--whole-rows)
- [5. Queries inside a loop](#5-queries-inside-a-loop)
- [6. No pagination / unbounded reads](#6-no-pagination--unbounded-reads)
- [7. Full-text search without the right index](#7-full-text-search-without-the-right-index)
- [8. Row-by-row writes](#8-row-by-row-writes)
- [9. Connection & transaction scope](#9-connection--transaction-scope)
- [Verify a fix](#verify-a-fix)

## Find the hotspot
1. **Count queries** on the suspect path (`query-counting.md`). `1 + N` over a list = N+1.
2. **Read the plan**: `EXPLAIN ANALYZE` (Postgres/MySQL/SQLite) — `Seq Scan`/`full table scan`
   under a filter on a big table = missing index. `scripts/explain_query.py` runs it.
3. **Grep** for the shape: a query call inside a `for`/`map`/`.each`; ORM relationship access in
   a loop without eager loading; reads with no limit.

## 1. N+1 queries
One query for a list, then one extra per row. The #1 cause of slow endpoints.

```python
# SQLAlchemy — BAD
for u in session.scalars(select(User)):
    u.posts            # lazy load -> 1 query each (or raises on async)
# GOOD: eager load
session.scalars(select(User).options(selectinload(User.posts)))
```
```python
# Django — BAD: User.objects.all() then u.posts.all() in a loop
# GOOD:
User.objects.prefetch_related("posts")     # many; or select_related("profile") for FK/one-to-one
```
```ts
// Prisma — BAD: findMany() then per-row findMany(posts)
// GOOD:
prisma.user.findMany({ include: { posts: true } })
```
```ruby
# ActiveRecord — BAD: User.all then u.posts
# GOOD:
User.includes(:posts)
```
Rule of thumb: `selectinload`/`prefetch_related`/`include`/`includes` for collections;
`joinedload`/`select_related` (single JOIN) for many-to-one / one-to-one scalars.

## 2. Missing indexes
Columns used in `WHERE` / `JOIN` / `ORDER BY` need indexes. **Most DBs do NOT auto-index foreign keys.**
```sql
EXPLAIN ANALYZE SELECT ...;                 -- look for Seq Scan / full scan under a filter
CREATE INDEX CONCURRENTLY ix_orders_user ON orders (user_id);   -- Postgres: CONCURRENTLY avoids locking
```
- Index the FK columns you filter/join on.
- Composite index: equality columns first, range/sort column last.
- Add via your migration tool (Alembic/Django migrations/Prisma migrate/ActiveRecord) — never ad-hoc on prod.
- An index changes no results, so it's a near-zero-risk optimization — but it costs write throughput
  and disk, so index what's queried, not everything.

## 3. count + fetch in two trips
Exact totals are expensive on big tables. For "load more" UIs, fetch `limit + 1` and check length
instead of a separate `COUNT(*)`. Use approximate counts (`reltuples` in Postgres) when "about N" is fine.

## 4. Over-fetching columns / whole rows
Select only what you use. Hydrating full ORM objects to read one column or check existence wastes work
and prevents index-only scans.
```python
# BAD: select(User).where(...).first() is not None
# GOOD: select(User.id).where(...).first() is not None     # or session.query(exists())
```
```ts
prisma.user.findMany({ select: { id: true, name: true } })  // not the whole row
```

## 5. Queries inside a loop
Sequential round trips: latency = N × RTT. Collapse into one query with `IN (...)`, or for
independent *non-DB* I/O use the language's concurrency (gather/Promise.all). Never run concurrent
queries on a single shared session/connection that isn't concurrency-safe — batch instead.

## 6. No pagination / unbounded reads
Cap every read that can grow. Prefer **keyset (seek) pagination** over `OFFSET` on large tables —
`OFFSET` scans and discards rows, so deep pages get slower:
```sql
SELECT * FROM items WHERE id < :last_seen ORDER BY id DESC LIMIT 20;   -- O(1) per page
```

## 7. Full-text search without the right index
- Postgres FTS needs a **GIN** index on the `tsvector` (a `LIKE '%x%'` needs a trigram `gin_trgm_ops` index).
- The index expression/config must match the query exactly, or the planner won't use it.
- Prefer a stored generated `tsvector` column over computing it per query.
- MySQL: `FULLTEXT` index + `MATCH ... AGAINST`. Elasticsearch/Meilisearch when SQL FTS isn't enough.

## 8. Row-by-row writes
Replace N `INSERT`s with one bulk insert; dedup in the DB with upsert.
```sql
INSERT INTO jobs (...) VALUES (...), (...), ...
ON CONFLICT (url) DO NOTHING;          -- Postgres upsert; MySQL: INSERT ... ON DUPLICATE KEY UPDATE
```
ORM: `bulk_create` (Django), `createMany` (Prisma), `insert_all` (Rails), `add_all`/core `insert` (SQLAlchemy).

## 9. Connection & transaction scope
- Reuse one connection/session per request; don't open a new one per query.
- Commit once per unit of work, not per row.
- Use a connection pool sized to your workload; enable liveness checks (e.g. `pool_pre_ping`).

## Verify a fix
1. **Query count** drops from `1 + N` to constant (`query-counting.md`).
2. **Plan** changes (Seq Scan → Index Scan, fewer loops) via `EXPLAIN ANALYZE`.
3. **Wall time** improves under identical conditions (`bench.py`).
4. **Output is identical** — an optimization that changes results is a bug. Run the test suite.
