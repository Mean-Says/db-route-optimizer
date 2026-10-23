"""Engine / session helpers."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def make_engine(url: str | None = None, *, echo: bool = False):
    url = url or os.environ.get("DATABASE_URL", "sqlite:///demo.db")
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, echo=echo, future=True, connect_args=connect_args)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def create_schema(engine):
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    return make_session_factory(engine)()
