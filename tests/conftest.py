import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_store():
    """Each test gets a fresh in-memory store, never touching Google Sheets."""
    from core import db as db_module
    from core.store import MemoryStore

    db_module.set_store(MemoryStore())
    yield
    db_module.reset_store()
