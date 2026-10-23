"""FastAPI app exposing before/after endpoints for the three scenarios."""
from __future__ import annotations

import hashlib
import json
import os

from fastapi import Depends, FastAPI, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from .db import create_schema, get_session, make_engine
from .models import OrderRow, Product, User

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///demo.db")
engine = make_engine(DATABASE_URL)
create_schema(engine)

app = FastAPI(title="db-route-optimizer demo", version="0.1.0")


def session_dep():
    db = get_session(engine)
    try:
        yield db
    finally:
        db.close()


def _users_payload(users: list[User]) -> list[dict]:
    return [
        {
            "id": u.id,
            "name": u.name,
            "posts": [{"id": p.id, "title": p.title} for p in u.posts],
        }
        for u in users
    ]


@app.get("/users/nplus1")
def users_nplus1(db: Session = Depends(session_dep), limit: int = Query(50, ge=1, le=500)):
    """BEFORE: lazy-load posts per user (N+1)."""
    users = db.scalars(select(User).order_by(User.id).limit(limit)).all()
    # touch relationship lazily
    payload = _users_payload(users)
    return {"users": payload, "hash": _hash(payload)}


@app.get("/users/selectin")
def users_selectin(db: Session = Depends(session_dep), limit: int = Query(50, ge=1, le=500)):
    """AFTER: selectinload posts (one change)."""
    users = db.scalars(
        select(User).options(selectinload(User.posts)).order_by(User.id).limit(limit)
    ).all()
    payload = _users_payload(users)
    return {"users": payload, "hash": _hash(payload)}


@app.get("/products")
def products(
    category: str = Query(...),
    db: Session = Depends(session_dep),
    limit: int = Query(100, ge=1, le=1000),
):
    """Filter + order on category/name — Seq Scan until index exists."""
    rows = db.scalars(
        select(Product)
        .where(Product.category == category)
        .order_by(Product.name)
        .limit(limit)
    ).all()
    payload = [
        {"id": r.id, "category": r.category, "name": r.name, "price_cents": r.price_cents}
        for r in rows
    ]
    return {"products": payload, "hash": _hash(payload)}


@app.post("/orders/row-by-row")
def orders_row_by_row(n: int = Query(200, ge=1, le=5000), db: Session = Depends(session_dep)):
    """BEFORE: commit per row."""
    # isolate: wipe demo rows for this run's sku prefix
    prefix = "rbr"
    db.execute(text("DELETE FROM order_rows WHERE sku LIKE :p"), {"p": f"{prefix}%"})
    db.commit()
    for i in range(n):
        db.add(OrderRow(sku=f"{prefix}-{i:05d}", qty=1, note="row"))
        db.commit()
    total, checksum = _order_checksum(db, prefix)
    return {"inserted": total, "checksum": checksum}


@app.post("/orders/bulk")
def orders_bulk(n: int = Query(200, ge=1, le=5000), db: Session = Depends(session_dep)):
    """AFTER: single-transaction bulk insert."""
    prefix = "blk"
    db.execute(text("DELETE FROM order_rows WHERE sku LIKE :p"), {"p": f"{prefix}%"})
    db.commit()
    db.add_all([OrderRow(sku=f"{prefix}-{i:05d}", qty=1, note="bulk") for i in range(n)])
    db.commit()
    total, checksum = _order_checksum(db, prefix)
    return {"inserted": total, "checksum": checksum}


@app.get("/health")
def health():
    return {"ok": True, "database": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL}


def _hash(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _order_checksum(db: Session, prefix: str) -> tuple[int, str]:
    rows = db.scalars(
        select(OrderRow).where(OrderRow.sku.like(f"{prefix}%")).order_by(OrderRow.sku)
    ).all()
    payload = [{"sku": r.sku, "qty": r.qty} for r in rows]
    return len(payload), _hash(payload)
