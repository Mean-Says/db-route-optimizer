#!/usr/bin/env python3
"""Deterministic seed (--seed 42) with declared cardinalities.

Cardinalities chosen after timing the seed on this environment; see SEED_NOTES below.
If seed is too slow on your machine, lower COUNTS and document the change in runs/.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
import time

from sqlalchemy import delete, text

# Declared cardinalities (tune + document if seed is too slow).
COUNTS = {
    "users": 200,
    "posts_per_user": 5,  # -> 1000 posts
    "products": 5000,
    "categories": 20,
}

# Measured on Linux x86_64 / Python 3.12 (cloud agent): seed_seconds ≈ 0.17s for these counts.
SEED_NOTES = (
    "counts: users=200, posts=1000, products=5000, categories=20; "
    "measured seed_seconds≈0.17 on Linux/Python 3.12 (see runs/*/latest.json)."
)


def main(argv=None):
    p = argparse.ArgumentParser(description="Seed demo database deterministically.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--database-url", default=os.environ.get("DATABASE_URL", "sqlite:///demo.db"))
    p.add_argument("--ensure-index", action="store_true", help="create products(category, name) index")
    p.add_argument("--drop-index", action="store_true", help="drop products category/name index if present")
    p.add_argument("--quiet", action="store_true", help="do not print JSON meta to stdout")
    args = p.parse_args(argv)

    # Make app imports work when run from examples/demo_fastapi
    sys.path.insert(0, os.path.dirname(__file__))
    from app.db import create_schema, get_session, make_engine
    from app.models import OrderRow, Post, Product, User

    t0 = time.perf_counter()
    eng = make_engine(args.database_url)
    create_schema(eng)
    rng = random.Random(args.seed)

    with get_session(eng) as db:
        db.execute(delete(OrderRow))
        db.execute(delete(Post))
        db.execute(delete(Product))
        db.execute(delete(User))
        db.commit()

        users = [User(id=i, name=f"user-{i:04d}") for i in range(1, COUNTS["users"] + 1)]
        db.add_all(users)
        db.flush()

        posts = []
        pid = 1
        for u in users:
            for j in range(COUNTS["posts_per_user"]):
                posts.append(Post(id=pid, user_id=u.id, title=f"post-{u.id}-{j}"))
                pid += 1
        db.add_all(posts)

        categories = [f"cat-{i:02d}" for i in range(COUNTS["categories"])]
        products = []
        for i in range(1, COUNTS["products"] + 1):
            products.append(
                Product(
                    id=i,
                    category=categories[i % len(categories)],
                    name=f"product-{i:05d}",
                    price_cents=rng.randint(100, 50_000),
                )
            )
        db.add_all(products)
        db.commit()

        if args.drop_index:
            _drop_product_index(db, eng.dialect.name)
            db.commit()
        if args.ensure_index:
            _ensure_product_index(db, eng.dialect.name)
            db.commit()

    elapsed = time.perf_counter() - t0
    fingerprint = hashlib.sha256(
        f"{args.seed}:{COUNTS}:{args.database_url}".encode()
    ).hexdigest()[:12]
    meta = {
        "seed": args.seed,
        "counts": {
            **COUNTS,
            "posts": COUNTS["users"] * COUNTS["posts_per_user"],
        },
        "database": args.database_url.split("@")[-1],
        "seed_seconds": round(elapsed, 3),
        "fingerprint": fingerprint,
        "notes": SEED_NOTES,
    }
    if not args.quiet:
        print(json_dumps(meta))
    return meta


def json_dumps(obj):
    import json

    return json.dumps(obj, indent=2)


def _ensure_product_index(db, dialect: str):
    if dialect == "postgresql":
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_products_category_name "
                "ON products (category, name)"
            )
        )
    else:
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_products_category_name "
                "ON products (category, name)"
            )
        )


def _drop_product_index(db, dialect: str):
    db.execute(text("DROP INDEX IF EXISTS ix_products_category_name"))


if __name__ == "__main__":
    main()
