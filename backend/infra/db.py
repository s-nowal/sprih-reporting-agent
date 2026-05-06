"""Async SQLAlchemy engine and session factory for MariaDB."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_url() -> str:
    """Build the async MySQL connection URL from settings."""
    return (
        f"mysql+aiomysql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )


def get_checkpointer_url() -> str:
    """Build the connection URL consumed by ``AIOMySQLSaver.from_conn_string``.

    Uses the plain ``mysql://`` scheme expected by the langgraph-checkpoint-mysql
    package, which manages its own aiomysql connection pool independently of
    the SQLAlchemy engine. Sourced from the same ``settings`` fields as
    ``_get_url`` so the two cannot drift apart.

    Returns:
        A ``mysql://user:password@host:port/db`` URL string.
    """
    return (
        f"mysql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )


def get_engine(echo: bool | None = None) -> AsyncEngine:
    """Return the shared async engine, creating it lazily on first call.

    Args:
        echo: SQL echo flag passed to SQLAlchemy. Defaults to ``settings.debug``
            when the engine is first created. Ignored on subsequent calls since
            the singleton is already initialised.
    """
    global _engine
    if _engine is None:
        effective_echo = settings.debug if echo is None else echo
        _engine = create_async_engine(_get_url(), echo=effective_echo, pool_recycle=3600)
    return _engine


def make_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create and return an async session factory bound to the shared engine.

    Called once by ``Registry.from_config``. Caches the factory on the
    module-level ``_session_factory`` variable.

    Returns:
        async_sessionmaker[AsyncSession]: Configured with ``expire_on_commit=False``.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """Create all tables from ORM metadata. Safe to call repeatedly."""
    from backend.models import Base  # noqa: F811

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
