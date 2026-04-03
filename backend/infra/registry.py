"""Module-level registry for infrastructure singletons.

LangChain ``@tool`` functions are module-level and cannot receive constructor-
injected dependencies.  Per-request data (enterprise_id, job_id) flows through
LangGraph's ``config["configurable"]``.  Infrastructure singletons (DB session
factory, storage adapter) are stored here — set once at app startup, read by
tools, services, and handlers at call time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from backend.infra.storage import LocalStorage

_storage: LocalStorage | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_registry(
    storage: LocalStorage,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Initialise the registry with infrastructure singletons. Called once at app startup."""
    global _storage, _session_factory
    _storage = storage
    _session_factory = session_factory


def get_storage() -> LocalStorage:
    """Return the storage adapter. Raises if ``init_registry`` has not been called."""
    if _storage is None:
        raise RuntimeError("Registry not initialised — call init_registry() at startup")
    return _storage


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the async session factory. Raises if ``init_registry`` has not been called."""
    if _session_factory is None:
        raise RuntimeError("Registry not initialised — call init_registry() at startup")
    return _session_factory
