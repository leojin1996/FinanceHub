from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

LOGGER = logging.getLogger(__name__)

# Local dev default; override with FINANCEHUB_MYSQL_URL for other environments.
_DEFAULT_MYSQL_URL = "mysql+pymysql://test:test123@localhost:3306/financehub"


def _get_database_url() -> str:
    return os.environ.get("FINANCEHUB_MYSQL_URL", _DEFAULT_MYSQL_URL)


def get_database_url() -> str:
    """Connection string for MySQL (same as ``engine``; reads ``FINANCEHUB_MYSQL_URL``)."""
    return _get_database_url()


engine = create_engine(
    _get_database_url(),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def create_tables() -> None:
    from . import models as _models  # noqa: F841 — ensure models are imported so Base.metadata is populated

    Base.metadata.create_all(bind=engine)
    LOGGER.info("Database tables created/verified")


def get_db() -> Session:  # type: ignore[type-arg]
    """FastAPI dependency that yields a SQLAlchemy session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db  # type: ignore[misc]
    finally:
        db.close()
