"""
Database engine, session factory, and helpers.
DATABASE_URL defaults to SQLite at project root: timewars.db
Override via DB_URL env variable for PostgreSQL in production.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db.models import Base

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = f"sqlite:///{_ROOT / 'timewars.db'}"
DATABASE_URL = os.getenv("DB_URL", _DEFAULT_DB)

# connect_args only needed for SQLite
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
