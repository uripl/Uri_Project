import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets a clean temporary SQLite DB."""
    test_db = tmp_path / "test.db"

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from core import db as db_module

    engine = create_engine(
        f"sqlite:///{test_db}",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)

    from core import repository as repo
    monkeypatch.setattr(repo, "SessionLocal", SessionLocal)

    from core.models import Base
    Base.metadata.create_all(engine)

    yield

    Base.metadata.drop_all(engine)
