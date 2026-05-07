"""Module-level registry for infrastructure singletons.

Primary API (startup / shutdown):
    registry = await Registry.from_config(settings)
    set_registry(registry)
    ...
    await teardown_registry()

Accessor API (services / LangChain tools):
    get_storage()   # returns the registered storage adapter
    get_db()        # returns the registered async session factory

LangChain ``@tool`` functions are module-level and cannot receive constructor-
injected dependencies. ``Registry`` holds the singletons; the module-level
accessors below bridge that gap.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from backend.infra.storage import LocalStorage

logger = logging.getLogger(__name__)


class Registry:
    """Holds named infrastructure singletons. Build with ``from_config``."""

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        """Register a named service. Overwrites any previous registration.

        Args:
            name: Lookup key (e.g. ``"storage"``, ``"db"``).
            service: The service instance to register.
        """
        self._services[name] = service

    def get(self, name: str) -> Any:
        """Return a registered service by name.

        Args:
            name: Lookup key used when the service was registered.

        Returns:
            The registered service instance.

        Raises:
            RuntimeError: If ``name`` was never registered.
        """
        if name not in self._services:
            raise RuntimeError(
                f"Service '{name}' not registered — was Registry.from_config() called?"
            )
        return self._services[name]

    @classmethod
    async def from_config(cls, settings: Any) -> Registry:
        """Build a fully-initialised registry from application settings.

        Runs DB table creation, seeds the default enterprise row, then
        registers the storage adapter and session factory.

        Args:
            settings: Application settings (``backend.config.Settings``).

        Returns:
            A ``Registry`` with ``"storage"`` and ``"db"`` registered.

        Raises:
            RuntimeError: If the database is unreachable.
            ValueError: If ``settings.storage_backend`` is not a known value.
        """
        from backend.infra.db import init_db, make_session_factory
        from backend.infra.storage import get_storage

        await init_db()

        reg = cls()
        reg.register("storage", get_storage(settings))
        reg.register("db", make_session_factory())
        await _seed_default_enterprise(settings)
        await _migrate_legacy_mirror_tables()
        return reg

    async def close(self) -> None:
        """Dispose all registered resources. Called by ``teardown_registry``.

        Disposes the database engine and clears all registered services.
        """
        from backend.infra.db import close_db

        await close_db()
        self._services.clear()


# --- Module-level singleton ---------------------------------------------------
# LangChain @tool functions are module-level and cannot receive constructor-
# injected dependencies. The singleton set here is the bridge between startup
# and any code that needs infra at call time.

_registry: Registry | None = None


def set_registry(registry: Registry) -> None:
    """Store the registry singleton. Called once at app startup.

    Args:
        registry: A fully-initialised ``Registry`` instance from ``Registry.from_config``.
    """
    global _registry
    _registry = registry


async def teardown_registry() -> None:
    """Close the registry and release all resources. Called at app shutdown.

    Safe to call even if ``set_registry`` was never called.
    """
    global _registry
    if _registry is not None:
        await _registry.close()
    _registry = None


def get_storage() -> LocalStorage:
    """Return the registered storage adapter.

    Returns:
        The storage adapter registered under ``"storage"``.

    Raises:
        RuntimeError: If ``set_registry`` has not been called.
    """
    if _registry is None:
        raise RuntimeError("Registry not initialised — call set_registry() at startup")
    return _registry.get("storage")


def get_db() -> async_sessionmaker[AsyncSession]:
    """Return the registered async session factory.

    Returns:
        The session factory registered under ``"db"``.

    Raises:
        RuntimeError: If ``set_registry`` has not been called.
    """
    if _registry is None:
        raise RuntimeError("Registry not initialised — call set_registry() at startup")
    return _registry.get("db")


async def _seed_default_enterprise(settings: Any) -> None:
    """Insert the dev/default enterprise row if it doesn't exist yet.

    Idempotent — uses INSERT ... ON DUPLICATE KEY UPDATE name=name (a no-op).
    Called once at startup. Required because every thread / job / google
    credentials row references ``enterprise_id`` and the dev-mode auth bypass
    uses ``settings.default_enterprise_id``.

    Args:
        settings: Application settings — supplies the id and display name.
    """
    from sqlalchemy.dialects.mysql import insert

    from backend.infra.db import make_session_factory
    from backend.models.enterprise import Enterprise

    factory = make_session_factory()
    async with factory() as session:
        stmt = insert(Enterprise).values(
            enterprise_id=settings.default_enterprise_id,
            name=settings.default_enterprise_name,
        )
        # ON DUPLICATE: keep existing row untouched (no-op update on PK).
        stmt = stmt.on_duplicate_key_update(
            enterprise_id=stmt.inserted.enterprise_id,
        )
        await session.execute(stmt)
        await session.commit()


async def _migrate_legacy_mirror_tables() -> None:
    """Bring the database schema up to the latest mirror layout.

    Three historical states are handled:

    1. Pre-refactor: had ``google_credentials`` + ``thread_drive_mappings``
       (Google-specific tables).
    2. First refactor: had ``mirror_credentials`` (provider-agnostic) +
       ``thread_mirror_mappings`` (separate mapping table).
    3. Current: ``mirror_credentials`` + mirror columns folded into
       ``threads``.

    On startup we ALTER ``threads`` to add the mirror columns idempotently,
    fold any state from either legacy mapping table into the thread row,
    and DROP the old tables. ``google_credentials`` is also migrated to
    ``mirror_credentials`` if present.

    Safe to call repeatedly — once everything is on the latest layout the
    function does a few INFORMATION_SCHEMA lookups and returns.
    """
    from sqlalchemy import text

    from backend.infra.db import make_session_factory

    factory = make_session_factory()

    async with factory() as session:
        # --- ALTER threads: add mirror columns idempotently ------------------
        # ``ADD COLUMN IF NOT EXISTS`` (MariaDB 10.0.2+) keeps this safe on
        # both fresh databases (where create_all already created them) and
        # existing ones.
        for col_sql in (
            "mirror_provider VARCHAR(32) NULL",
            "mirror_folder_id VARCHAR(256) NULL",
            "mirror_thread_title VARCHAR(200) NULL",
            "mirror_last_synced_at DATETIME NULL",
        ):
            await session.execute(
                text(f"ALTER TABLE threads ADD COLUMN IF NOT EXISTS {col_sql}")
            )

        # --- Detect legacy tables --------------------------------------------
        present = set(
            (
                await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = DATABASE() AND table_name IN "
                        "('google_credentials', 'thread_drive_mappings', "
                        "'thread_mirror_mappings')"
                    )
                )
            ).scalars().all()
        )

        if present:
            logger.info("Migrating legacy mirror tables: %s", sorted(present))

        # --- google_credentials → mirror_credentials -------------------------
        if "google_credentials" in present:
            await session.execute(
                text(
                    """
                    INSERT IGNORE INTO mirror_credentials
                        (enterprise_id, provider, agent_email, refresh_token,
                         scopes, parent_folder_id, config, created_at, updated_at)
                    SELECT enterprise_id, 'google_drive', agent_email,
                           refresh_token, scopes, drive_parent_folder_id,
                           NULL, created_at, updated_at
                    FROM google_credentials
                    """
                )
            )
            await session.execute(text("DROP TABLE google_credentials"))
            logger.info("Migrated google_credentials → mirror_credentials")

        # --- thread_mirror_mappings → threads.mirror_* (current path) --------
        if "thread_mirror_mappings" in present:
            await session.execute(
                text(
                    """
                    UPDATE threads t
                    JOIN thread_mirror_mappings m ON m.thread_id = t.thread_id
                    SET t.mirror_provider = m.provider,
                        t.mirror_folder_id = m.provider_folder_id,
                        t.mirror_thread_title = m.thread_title,
                        t.mirror_last_synced_at = m.last_synced_at
                    """
                )
            )
            await session.execute(text("DROP TABLE thread_mirror_mappings"))
            logger.info(
                "Folded thread_mirror_mappings into threads.mirror_* and dropped table"
            )

        # --- thread_drive_mappings → threads.mirror_* (legacy path) ----------
        # Reachable only on a database that skipped the intermediate refactor
        # (e.g. updated straight from the original Google-specific schema).
        if "thread_drive_mappings" in present:
            await session.execute(
                text(
                    """
                    UPDATE threads t
                    JOIN thread_drive_mappings d ON d.thread_id = t.thread_id
                    SET t.mirror_provider = 'google_drive',
                        t.mirror_folder_id = d.drive_folder_id,
                        t.mirror_thread_title = d.thread_title,
                        t.mirror_last_synced_at = d.last_synced_at
                    """
                )
            )
            await session.execute(text("DROP TABLE thread_drive_mappings"))
            logger.info(
                "Folded thread_drive_mappings into threads.mirror_* and dropped table"
            )

        await session.commit()


