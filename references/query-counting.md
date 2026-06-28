# Deterministic query counting (N+1 detection)

Don't guess N+1 from grep — count the queries a code path emits. `1 + N` over a list = N+1.
This is what makes detection rigorous (the approach behind nplusone, pytest-capquery,
Django's `assertNumQueries`). Then lock it with an assertion so regressions fail CI.

`scripts/querycount.py` is a ready SQLAlchemy implementation + pytest guard. Per-stack below.

## Table of contents
- [Python — SQLAlchemy](#python--sqlalchemy)
- [Python — Django](#python--django)
- [Node — Prisma](#node--prisma)
- [Node — TypeORM / Sequelize / Knex](#node--typeorm--sequelize--knex)
- [Ruby — ActiveRecord](#ruby--activerecord)
- [Raw drivers / any language](#raw-drivers--any-language)
- [Production (APM)](#production-apm)
- [How to use the count](#how-to-use-the-count)

## Python — SQLAlchemy
Use `scripts/querycount.py`:
```python
from querycount import count_queries
with count_queries(engine) as qc:      # engine, async engine, or session.bind
    await handler(...)
qc.assert_max(5)                        # raises with the duplicated-statement fingerprint
```
Library: `nplusone` (runtime warnings). Mechanism: `before_cursor_execute` event.

## Python — Django
```python
from django.test.utils import CaptureQueriesContext
from django.db import connection
with CaptureQueriesContext(connection) as ctx:
    client.get("/users")
assert len(ctx) <= 5, [q["sql"] for q in ctx.captured_queries]
# or in a TestCase:  with self.assertNumQueries(5): ...
```
Library: `nplusone`, `django-debug-toolbar` (dev), `django-zen-queries`.

## Node — Prisma
```ts
let count = 0;
prisma.$on("query", () => { count++; });
await handler();
if (count > 5) throw new Error(`N+1? ${count} queries`);
```
Set `log: [{ emit: "event", level: "query" }]` on `new PrismaClient(...)`.

## Node — TypeORM / Sequelize / Knex
- **TypeORM**: `logging: true` + count `logger.logQuery` calls, or wrap `DataSource.query`.
- **Sequelize**: pass `benchmark: true` and a `logging: (sql, ms) => count++` hook.
- **Knex**: `knex.on("query", () => count++)`.

## Ruby — ActiveRecord
```ruby
count = 0
callback = ->(*, payload) { count += 1 unless payload[:name] == "SCHEMA" }
ActiveSupport::Notifications.subscribed(callback, "sql.active_record") { get "/users" }
assert count <= 5
```
Gem: `bullet` (flags N+1 + unused eager loads in dev/test).

## Raw drivers / any language
No ORM? Wrap the execute function (monkeypatch / decorator / proxy) and increment a counter,
or enable the DB's statement log for the request and count lines. The principle is universal:
**intercept the one place queries leave your process, count, assert.**

## Production (APM)
Datadog APM, Sentry Performance, New Relic, and Postgres `pg_stat_statements` surface N+1 from
real traffic (a span with N near-identical child DB spans). Use these when you can't reproduce
the hot path in a test.

## How to use the count
1. **Detect**: run the suspected handler inside the counter. `1 + N` (N = list size) = N+1.
2. **Fix**: batch into one query (`IN (...)`) or eager-load the relation (see db-optimization.md).
3. **Verify**: same handler, count again — should be constant (2–3), not `1 + N`.
4. **Guard**: keep an `assert_max(k)` test so a future change that reintroduces N+1 fails CI.
