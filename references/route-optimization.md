# Route / endpoint optimization — stack-agnostic

Once the queries behind an endpoint are tight (`db-optimization.md`), these are the request-level
wins. Examples span a few frameworks; the principles hold for any HTTP layer.

## Table of contents
- [1. Blocking calls in async handlers](#1-blocking-calls-in-async-handlers)
- [2. Sequential I/O that could be concurrent](#2-sequential-io-that-could-be-concurrent)
- [3. Serialization / payload size](#3-serialization--payload-size)
- [4. Caching](#4-caching)
- [5. Work the client didn't ask for](#5-work-the-client-didnt-ask-for)
- [6. Middleware & dependency cost](#6-middleware--dependency-cost)
- [Measure](#measure)

## 1. Blocking calls in async handlers
A synchronous/blocking call inside an async handler freezes the event loop — every concurrent
request stalls. Suspects: HTTP calls with a sync client, file/PDF parsing, crypto, heavy CPU, LLM SDKs.
```python
# Python (FastAPI/asyncio) — offload blocking work
data = await anyio.to_thread.run_sync(lambda: requests.get(url))   # or use httpx.AsyncClient
```
```js
// Node — never block the loop with sync fs / heavy CPU; use async APIs or a worker_thread
```
Rule: in an async runtime, every awaited call should be non-blocking; push CPU-heavy or
unavoidably-sync work to a thread/worker/queue. (In a sync stack like Rails/Django-WSGI this is moot —
there the lever is the query and the worker count.)

## 2. Sequential I/O that could be concurrent
Independent external calls (different services — not the same DB session) should run together.
```python
a, b, c = await asyncio.gather(fa(), fb(), fc())     # total = max, not sum
```
```js
const [a, b, c] = await Promise.all([fa(), fb(), fc()]);
```
Caveat: don't parallelize calls that share a non-concurrency-safe connection — batch those into one query.
Also respect deliberate pacing (rate-limited third-party APIs): parallelizing can trip 429s.

## 3. Serialization / payload size
- Paginate large lists (see db-optimization.md #6); don't serialize thousands of rows.
- Return only fields the client renders; skip heavy nested objects it ignores.
- Enable gzip/brotli for large JSON.
- Heavy response-model re-validation can dominate on hot endpoints — drop it only on proven hotspots,
  keep it elsewhere for correctness.

## 4. Caching — usually the biggest single win for read-heavy endpoints
- **In-process TTL cache** for hot, low-cardinality data that changes rarely.
- **Shared cache** (Redis/Memcached) when you have multiple workers/instances.
- **HTTP caching** (`Cache-Control`, `ETag`) so the browser/CDN skips the round trip entirely.
- **Persisted result cache** for expensive computed work (reports, LLM output) keyed by inputs —
  never recompute a cached result.
Invalidate on write; a stale cache is a correctness bug, not a perf win.

## 5. Work the client didn't ask for
Compute expensive extras (scores, recommendations, derived data) lazily / on request, not eagerly for
every list item. Move secondary data behind a separate endpoint instead of fattening the list response.

## 6. Middleware & dependency cost
- A dependency that hits the DB on every request (auth, feature flags) runs on every route — make it
  cheap and cached, and ensure it does one indexed query.
- Order middleware so cheap rejects (rate limit, auth) happen before expensive work.

## Measure
Benchmark the actual endpoint with `scripts/bench.py --url <endpoint>` before and after. Report the
median drop and the p95 (tail) — event-loop and caching fixes mostly improve the tail.
