"""Test isolation: never touch the configured (shared) database unless RUN_DATABASE_TESTS=1."""
import os

if os.environ.get("RUN_DATABASE_TESTS") != "1":
    os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.models.customer import PointGeometry  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@compiles(PointGeometry, "sqlite")
def _point_sqlite(element, compiler, **kw):
    return "TEXT"


@pytest.fixture
def sqlite_app():
    """The FastAPI app wired to a fresh in-memory SQLite database with every table created."""
    from app.db import get_db
    from app.main import app
    from app.models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        yield app, Session
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
