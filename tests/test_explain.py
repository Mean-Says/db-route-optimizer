"""Tests for explain_query: SQLite plan, URL redaction, ANALYZE refusal."""
from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from db_route_optimizer.explain_query import (
    is_local_url,
    is_select,
    main,
    redact_url,
    suggest_index_from_plan,
)


def test_redact_password():
    url = "postgresql://user:s3cret@db.example.com:5432/app"
    out = redact_url(url)
    assert "s3cret" not in out
    assert "***" in out
    assert "user" in out
    assert "db.example.com" in out


def test_redact_no_password():
    url = "sqlite:///tmp/x.db"
    assert redact_url(url) == url


def test_is_local():
    assert is_local_url("sqlite:///tmp/x.db")
    assert is_local_url("postgresql://u:p@localhost:5432/db")
    assert is_local_url("postgresql://u:p@127.0.0.1/db")
    assert not is_local_url("postgresql://u:p@db.example.com/db")


def test_is_select():
    assert is_select("SELECT 1")
    assert is_select("  with x as (select 1) select * from x")
    assert not is_select("UPDATE t SET a=1")
    assert not is_select("DELETE FROM t")


def test_refuse_analyze_on_update(capsys):
    with pytest.raises(SystemExit) as ei:
        main(["--analyze", "UPDATE users SET name='x' WHERE id=1"])
    # may exit 1 for missing DATABASE_URL first — set sqlite
    with pytest.raises(SystemExit) as ei:
        main(
            [
                "--database-url",
                "sqlite://",
                "--analyze",
                "UPDATE users SET name='x' WHERE id=1",
            ]
        )
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "ANALYZE" in err or "refusing" in err.lower() or "recusando" in err.lower()


def test_explain_sqlite(tmp_path, capsys):
    db = tmp_path / "t.db"
    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE items (id INTEGER PRIMARY KEY, category TEXT)"))
        c.execute(
            sa.text("INSERT INTO items (id, category) VALUES (1, 'a'), (2, 'b')")
        )
    main(
        [
            "--database-url",
            f"sqlite:///{db}",
            "--plain",
            "SELECT * FROM items WHERE category = 'a'",
        ]
    )
    out = capsys.readouterr().out
    assert "SCAN" in out.upper() or "items" in out.lower() or "SEARCH" in out.upper()


def test_explain_json(tmp_path, capsys):
    db = tmp_path / "t.db"
    eng = sa.create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE items (id INTEGER PRIMARY KEY)"))
    main(
        [
            "--database-url",
            f"sqlite:///{db}",
            "--plain",
            "--json",
            "SELECT * FROM items",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert data["dialect"] == "sqlite"
    assert "plan" in data


def test_suggest_index_sqlite_heuristic():
    plan = [{"id": 0, "parent": 0, "detail": "SCAN TABLE products"}]
    sql = "SELECT * FROM products WHERE category = ? ORDER BY name"
    suggestions = suggest_index_from_plan("sqlite", plan, sql, row_threshold=1)
    assert suggestions
    assert "CREATE INDEX" in suggestions[0]
    assert "products" in suggestions[0]
