"""E2E test fixtures — TestClient with real app lifespan.

The client runs against the real FastAPI app with all infrastructure:
MariaDB, LocalStorage, and LangGraph agent service. Requires Docker
containers to be running (``docker compose up -d``).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="session")
def client():
    """Session-scoped HTTP client backed by the real app.

    Uses Starlette's TestClient which triggers the ASGI lifespan:
    ``Registry.from_config``, ``set_registry``, ``init_agent_service`` on entry,
    ``teardown_registry`` on teardown.
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Standard dev-mode auth headers for an authenticated request."""
    return {"x-enterprise-id": "test-enterprise"}
