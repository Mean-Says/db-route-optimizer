"""Tests for querycount: N+1, duplicates, raise mode, missing SQLAlchemy hint."""
from __future__ import annotations

import sqlalchemy as sa
from db_route_optimizer.querycount import (
    DuplicateQueriesError,
    QueryBudgetExceeded,
    count_queries,
)


def _engine():
    eng = sa.create_engine("sqlite://")
    md = sa.MetaData()
    users = sa.Table("users", md, sa.Column("id", sa.Integer, primary_key=True))
    posts = sa.Table(
        "posts",
        md,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
    )
    md.create_all(eng)
    with eng.begin() as c:
        c.execute(users.insert(), [{"id": i} for i in range(1, 11)])
        c.execute(
            posts.insert(),
            [{"id": i, "user_id": (i % 10) + 1} for i in range(1, 41)],
        )
    return eng, users, posts


def test_n_plus_1_shape():
    eng, users, posts = _engine()
    with eng.connect() as c:
        with count_queries(eng) as qc:
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            for uid in uids:
                c.execute(sa.select(posts).where(posts.c.user_id == uid)).all()
    # 1 select users + 10 select posts = 11
    assert qc.total == 11
    with eng.connect() as c:
        with count_queries(eng) as qc2:
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            c.execute(sa.select(posts).where(posts.c.user_id.in_(uids))).all()
    assert qc2.total == 2


def test_duplicates_reported():
    eng, users, posts = _engine()
    with eng.connect() as c:
        with count_queries(eng) as qc:
            for _ in range(3):
                c.execute(sa.select(users.c.id)).all()
    dupes = qc.duplicates()
    assert dupes
    assert dupes[0][0] == 3


def test_raise_on_budget():
    eng, users, posts = _engine()
    try:
        with eng.connect() as c:
            with count_queries(eng, max_queries=2):
                uids = [r.id for r in c.execute(sa.select(users.c.id))]
                for uid in uids:
                    c.execute(sa.select(posts).where(posts.c.user_id == uid)).all()
        raised = False
    except QueryBudgetExceeded:
        raised = True
    assert raised


def test_raise_on_duplicate():
    eng, users, _posts = _engine()
    try:
        with eng.connect() as c:
            with count_queries(eng, raise_on_duplicate=True):
                c.execute(sa.select(users.c.id)).all()
                c.execute(sa.select(users.c.id)).all()
        raised = False
    except DuplicateQueriesError:
        raised = True
    assert raised


def test_assert_max():
    eng, users, posts = _engine()
    with eng.connect() as c:
        with count_queries(eng) as qc:
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            for uid in uids:
                c.execute(sa.select(posts).where(posts.c.user_id == uid)).all()
    try:
        qc.assert_max(5)
        ok = True
    except QueryBudgetExceeded:
        ok = False
    assert ok is False
