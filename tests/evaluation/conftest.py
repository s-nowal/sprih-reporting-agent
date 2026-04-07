"""Evaluation test configuration — real infrastructure, no mocks.

Loads .env and initialises the DB, storage, and registry singletons so
that evaluation tests run the full real code path.

Requires:
    ``docker compose up -d`` — MariaDB must be reachable at the URL in .env
    ANTHROPIC_API_KEY and SERPER_API_KEY in .env
"""

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(autouse=True)
async def init_infra():
    """Initialise DB tables, storage adapter, and registry singletons per test.

    Resets the SQLAlchemy engine before each test so it is created in the
    current event loop (avoids "Future attached to a different loop" errors
    with pytest-asyncio's function-scoped loops).

    Uses the persistent DB configured in .env (same as production).
    Requires MariaDB to be running: ``docker compose up -d``.

    Raises:
        Exception: If the DB connection fails — verify ``docker compose up -d``.
    """
    from backend.config import settings
    from backend.infra.db import close_db, get_session_factory, init_db
    from backend.infra.registry import init_registry
    from backend.infra.storage import LocalStorage

    # Reset any engine created in a previous loop before reinitialising.
    await close_db()
    await init_db()
    init_registry(LocalStorage(settings.storage_root), get_session_factory())

    yield

    await close_db()
