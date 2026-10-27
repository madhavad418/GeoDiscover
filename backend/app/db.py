from collections.abc import Iterator
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
_url = get_settings().sqlalchemy_url
# A short connect timeout keeps /api/health fast (Railway health checks) when the DB is unreachable.
engine = create_engine(_url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args={"connect_timeout": 3}) if _url else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False) if engine else None


class Base(DeclarativeBase):
    """Base class for ORM models. Import models in app/models so Alembic sees them."""

    # Deterministic constraint names keep Alembic autogenerate diffs stable.
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


def get_db() -> Iterator[Session]:
    """FastAPI dependency: `db: Session = Depends(get_db)`."""
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Database is not configured (DATABASE_URL is unset)")
    with SessionLocal() as session:
        yield session


def database_status() -> str:
    if engine is None:
        return "not_configured"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"


def schema_status() -> str:
    """'current' when the database is at the newest Alembic revision, else 'outdated' / 'unknown'."""
    if engine is None:
        return "unknown"
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        heads = set(ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_heads())
        with engine.connect() as conn:
            current = set(conn.execute(text("SELECT version_num FROM alembic_version")).scalars())
        return "current" if current == heads else "outdated"
    except Exception:
        return "unknown"
