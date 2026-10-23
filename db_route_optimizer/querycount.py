#!/usr/bin/env python3
"""Deterministic query counting — turn "I think this is N+1" into a number.

Grep + reading code misses N+1s and yields false positives. The reliable way is to
COUNT the queries a code path actually emits. If a request over a list fires `1 + N`
queries, it's N+1.

SQLAlchemy implementation + pytest helper. For other stacks, see
references/query-counting.md.

--- SQLAlchemy usage ---
    from db_route_optimizer.querycount import count_queries
    with count_queries(engine) as qc:
        await my_handler(...)
    print(qc.total, qc.by_type)
    qc.assert_max(5)

--- raise/fail mode (tests / CI) ---
    with count_queries(engine, raise_on_duplicate=True, max_queries=10) as qc:
        client.get("/users")
"""
from __future__ import annotations

import argparse
import contextlib
import re
import sys
from collections import Counter

from db_route_optimizer.i18n import add_lang_arg, set_lang, t


class QueryBudgetExceeded(AssertionError):
    """Raised when total queries exceed the configured budget."""


class DuplicateQueriesError(AssertionError):
    """Raised when duplicate (SQL+params) groups are detected in raise mode."""


class QueryCounter:
    def __init__(self):
        self.total = 0
        self.by_type: dict[str, int] = {}
        self.statements: list[str] = []
        self.params: list[object] = []
        self._dup_keys: list[str] = []

    def _record(self, sql: str, parameters=None):
        self.total += 1
        m = re.match(r"\s*(\w+)", sql or "")
        verb = (m.group(1) if m else "OTHER").upper()
        self.by_type[verb] = self.by_type.get(verb, 0) + 1
        self.statements.append(sql)
        self.params.append(parameters)
        self._dup_keys.append(_dup_key(sql, parameters))

    def duplicates(self) -> list[tuple[int, str]]:
        """Return (count, sql) for groups with the same SQL+params, count > 1."""
        counts = Counter(self._dup_keys)
        out = []
        seen = set()
        for key, count in counts.most_common():
            if count <= 1 or key in seen:
                continue
            seen.add(key)
            # recover a readable SQL from the first matching statement
            idx = self._dup_keys.index(key)
            sql = self.statements[idx] or key
            out.append((count, _short_sql(sql)))
        return out

    def assert_max(self, n: int):
        if self.total > n:
            dupes = _top_duplicates(self.statements)
            hint = f" likely N+1: {dupes}" if dupes else ""
            raise QueryBudgetExceeded(f"expected <= {n} queries, got {self.total}.{hint}")

    def assert_no_duplicates(self):
        dupes = self.duplicates()
        if dupes:
            detail = "; ".join(f"{c}x {_short_sql(s)}" for c, s in dupes[:5])
            raise DuplicateQueriesError(f"duplicate queries detected: {detail}")

    def report_duplicates(self, file=sys.stdout) -> int:
        dupes = self.duplicates()
        if not dupes:
            return 0
        print(t("qc_duplicates_header"), file=file)
        for count, sql in dupes:
            print(t("qc_duplicate_line", count=count, sql=sql), file=file)
        return len(dupes)

    def __repr__(self):
        return f"<QueryCounter total={self.total} by_type={self.by_type}>"


def _short_sql(sql: str, n: int = 120) -> str:
    return re.sub(r"\s+", " ", (sql or "").strip())[:n]


def _dup_key(sql: str, parameters) -> str:
    """Stable key: normalized SQL + repr of params (order-insensitive for dicts)."""
    norm = re.sub(r"\s+", " ", (sql or "").strip())
    if parameters is None:
        return norm
    try:
        if isinstance(parameters, dict):
            param_repr = repr(sorted(parameters.items()))
        elif isinstance(parameters, (list, tuple)):
            param_repr = repr(tuple(parameters))
        else:
            param_repr = repr(parameters)
    except Exception:
        param_repr = str(type(parameters))
    return f"{norm}||{param_repr}"


def _top_duplicates(statements, top=2):
    """Repeated near-identical statements are the N+1 fingerprint."""
    norm: dict[str, int] = {}
    for s in statements:
        key = re.sub(r"\d+", "?", re.sub(r"\s+", " ", (s or "").strip()))[:120]
        norm[key] = norm.get(key, 0) + 1
    repeated = sorted(((c, k) for k, c in norm.items() if c > 1), reverse=True)[:top]
    return [f"{c}x {k}" for c, k in repeated]


def _require_sqlalchemy():
    try:
        import sqlalchemy  # noqa: F401
        from sqlalchemy import event  # noqa: F401
    except ImportError:
        print(t("qc_need_sqlalchemy"), file=sys.stderr)
        sys.exit(1)


@contextlib.contextmanager
def count_queries(target, *, max_queries: int | None = None, raise_on_duplicate: bool = False):
    """Count queries emitted while inside the block.

    `target` is a SQLAlchemy Engine, AsyncEngine, or anything with a `.sync_engine`
    or `.bind`. Works for sync and async engines (events attach to the sync core).

    If `max_queries` is set, raises QueryBudgetExceeded on exit when exceeded.
    If `raise_on_duplicate` is True, raises DuplicateQueriesError when any
    (SQL+params) group appears more than once.
    """
    _require_sqlalchemy()
    from sqlalchemy import event

    engine = getattr(target, "sync_engine", None) or getattr(target, "bind", None) or target
    counter = QueryCounter()

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter._record(statement, parameters)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _before)

    if max_queries is not None and counter.total > max_queries:
        raise QueryBudgetExceeded(
            t("qc_raise_budget", total=counter.total, max=max_queries)
        )
    if raise_on_duplicate and counter.duplicates():
        raise DuplicateQueriesError(
            t("qc_raise_duplicates", n=len(counter.duplicates()))
        )


def main(argv=None):
    """CLI: self-test N+1 vs batched, optional raise mode."""
    p = argparse.ArgumentParser(description="SQLAlchemy query counter / N+1 guard.")
    add_lang_arg(p)
    p.add_argument(
        "--raise",
        dest="raise_mode",
        action="store_true",
        help="exit non-zero if budget exceeded or duplicates found (self-test uses N+1 path)",
    )
    p.add_argument(
        "--max-queries",
        type=int,
        default=5,
        help="budget for --raise on the N+1 self-test path (default 5)",
    )
    p.add_argument(
        "--fail-on-duplicate",
        action="store_true",
        help="with --raise, also fail when duplicate SQL+params groups exist",
    )
    args = p.parse_args(argv)
    set_lang(args.lang)
    _require_sqlalchemy()

    import sqlalchemy as sa

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
        c.execute(users.insert(), [{"id": i} for i in range(1, 51)])
        c.execute(
            posts.insert(),
            [{"id": i, "user_id": (i % 50) + 1} for i in range(1, 201)],
        )

    exit_code = 0
    with eng.connect() as c:
        with count_queries(eng) as qc:
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            for uid in uids:
                c.execute(sa.select(posts).where(posts.c.user_id == uid)).all()
        print(t("qc_nplus1", total=qc.total, by_type=qc.by_type))
        qc.report_duplicates()

        with count_queries(eng) as qc2:
            uids = [r.id for r in c.execute(sa.select(users.c.id))]
            c.execute(sa.select(posts).where(posts.c.user_id.in_(uids))).all()
        print(t("qc_batched", total=qc2.total, by_type=qc2.by_type))

        if args.raise_mode:
            try:
                kwargs = {"max_queries": args.max_queries}
                if args.fail_on_duplicate:
                    kwargs["raise_on_duplicate"] = True
                with count_queries(eng, **kwargs) as qc3:
                    uids = [r.id for r in c.execute(sa.select(users.c.id))]
                    for uid in uids:
                        c.execute(sa.select(posts).where(posts.c.user_id == uid)).all()
                print(t("qc_ok", total=qc3.total))
            except (QueryBudgetExceeded, DuplicateQueriesError) as e:
                print(t("qc_guard_caught", err=e), file=sys.stderr)
                exit_code = 1
        else:
            try:
                qc.assert_max(5)
            except AssertionError as e:
                print(t("qc_guard_caught", err=e))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
