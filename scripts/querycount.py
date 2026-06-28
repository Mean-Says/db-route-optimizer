#!/usr/bin/env python3
"""Deterministic query counting — turn "I think this is N+1" into a number.

Grep + reading code misses N+1s and yields false positives. The reliable way is to
COUNT the queries a code path actually emits (this is what nplusone / pytest-capquery /
Django's assertNumQueries do). If a request over a list fires `1 + N` queries, it's N+1.

This file ships a concrete SQLAlchemy implementation (the most common case) and a pytest
helper to guard against regressions. For other stacks, see references/query-counting.md
(Django, Prisma/TypeORM, ActiveRecord, raw drivers) — the idea is identical: hook the
driver/ORM, count, assert.

--- SQLAlchemy usage ---
    from querycount import count_queries
    with count_queries(engine) as qc:        # engine OR a session's bind
        await my_handler(...)
    print(qc.total, qc.by_type)              # e.g. 401  {'SELECT': 401}
    qc.assert_max(5)                          # raises if it ballooned (N+1)

--- pytest regression guard ---
    def test_list_endpoint_is_not_n_plus_1(engine):
        with count_queries(engine) as qc:
            client.get("/users")
        qc.assert_max(5)   # fails the build if someone reintroduces N+1
"""
from __future__ import annotations
import contextlib
import re


class QueryCounter:
    def __init__(self):
        self.total = 0
        self.by_type: dict[str, int] = {}
        self.statements: list[str] = []

    def _record(self, sql: str):
        self.total += 1
        verb = (re.match(r"\s*(\w+)", sql or "").group(1) or "OTHER").upper()
        self.by_type[verb] = self.by_type.get(verb, 0) + 1
        self.statements.append(sql)

    def assert_max(self, n: int):
        if self.total > n:
            dupes = _top_duplicates(self.statements)
            hint = f" likely N+1: {dupes}" if dupes else ""
            raise AssertionError(f"expected <= {n} queries, got {self.total}.{hint}")

    def __repr__(self):
        return f"<QueryCounter total={self.total} by_type={self.by_type}>"


def _top_duplicates(statements, top=2):
    """Repeated near-identical statements are the N+1 fingerprint."""
    norm: dict[str, int] = {}
    for s in statements:
        key = re.sub(r"\d+", "?", re.sub(r"\s+", " ", (s or "").strip()))[:120]
        norm[key] = norm.get(key, 0) + 1
    repeated = sorted(((c, k) for k, c in norm.items() if c > 1), reverse=True)[:top]
    return [f"{c}x {k}" for c, k in repeated]


@contextlib.contextmanager
def count_queries(target):
    """Count queries emitted while inside the block.

    `target` is a SQLAlchemy Engine, AsyncEngine, or anything with a `.sync_engine`
    or `.bind`. Works for sync and async engines (events attach to the sync core).
    """
    from sqlalchemy import event

    engine = (
        getattr(target, "sync_engine", None)
        or getattr(target, "bind", None)
        or target
    )
    counter = QueryCounter()

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter._record(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)


if __name__ == "__main__":
    # Self-test with an in-memory SQLite DB: prove N+1 (1+N) vs batched (2).
    import sqlalchemy as sa

    eng = sa.create_engine("sqlite://")
    md = sa.MetaData()
    users = sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    posts = sa.Table("posts", md, sa.Column("id", sa.Integer, primary_key=True),
                     sa.Column("user_id", sa.Integer))
    md.create_all(eng)
    with eng.begin() as c:
        c.execute(users.insert(), [{"id": i} for i in range(1, 51)])
        c.execute(posts.insert(), [{"id": i, "user_id": (i % 50) + 1} for i in range(1, 201)])

    with eng.connect() as c:
        with count_queries(eng) as qc:  # N+1
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            for uid in uids:
                c.execute(sa.select(posts).where(posts.c.user_id == uid)).all()
        print(f"N+1:     {qc.total} queries  {qc.by_type}")

        with count_queries(eng) as qc2:  # batched
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            c.execute(sa.select(posts).where(posts.c.user_id.in_(uids))).all()
        print(f"batched: {qc2.total} queries  {qc2.by_type}")
        try:
            qc.assert_max(5)
        except AssertionError as e:
            print(f"guard caught it -> {e}")
