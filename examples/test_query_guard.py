"""Example: guard against N+1 regressions in CI.

Copy this pattern into your test suite. The point: assert the number of queries a code path
emits, so a future change that reintroduces N+1 fails the build instead of silently shipping.

Run locally:  pytest examples/test_query_guard.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from querycount import count_queries  # noqa: E402

sa = pytest.importorskip("sqlalchemy")


@pytest.fixture
def engine():
    eng = sa.create_engine("sqlite://")
    md = sa.MetaData()
    users = sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    posts = sa.Table("posts", md, sa.Column("id", sa.Integer, primary_key=True),
                     sa.Column("user_id", sa.Integer))
    md.create_all(eng)
    with eng.begin() as c:
        c.execute(users.insert(), [{"id": i} for i in range(1, 51)])
        c.execute(posts.insert(), [{"id": i, "user_id": (i % 50) + 1} for i in range(1, 201)])
    eng._users, eng._posts = users, posts
    return eng


def _batched(conn, eng):
    uids = [r.id for r in conn.execute(sa.select(eng._users.c.id))]
    conn.execute(sa.select(eng._posts).where(eng._posts.c.user_id.in_(uids))).all()


def _n_plus_1(conn, eng):
    uids = [r.id for r in conn.execute(sa.select(eng._users.c.id))]
    for uid in uids:
        conn.execute(sa.select(eng._posts).where(eng._posts.c.user_id == uid)).all()


def test_batched_stays_constant(engine):
    """The good path: a couple of queries regardless of list size."""
    with engine.connect() as conn:
        with count_queries(engine) as qc:
            _batched(conn, engine)
    qc.assert_max(5)  # passes — this is what you lock in


def test_guard_catches_n_plus_1(engine):
    """The guard fires when N+1 sneaks back in (here we trigger it on purpose)."""
    with engine.connect() as conn:
        with count_queries(engine) as qc:
            _n_plus_1(conn, engine)
    with pytest.raises(AssertionError, match="expected <= 5 queries"):
        qc.assert_max(5)
