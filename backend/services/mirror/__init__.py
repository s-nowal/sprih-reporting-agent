"""Mirror provider factory + public API.

Run-time entry point for the mirror layer. Most consumers only need
:func:`get_provider` — it returns the active :class:`MirrorProvider` for an
enterprise (or ``None`` if the enterprise hasn't connected any mirror
backend yet). Each provider class implements ``setup_thread_folder``,
``sync_in``, and ``sync_out`` against its own backend.

The router and credential CRUD helpers stay in submodules:

    from backend.services.mirror import credentials
    from backend.services.mirror import get_provider

To add a new provider (e.g. SharePoint via Microsoft Graph):

1. Implement a new ``MirrorProvider`` subclass in
   ``backend/services/mirror/<name>.py``.
2. Register the class in ``_PROVIDERS`` below under its ``provider_name``.
3. Add an OAuth router that stores credentials via
   :func:`backend.services.mirror.credentials.store` with the matching
   ``provider`` key.
"""

from __future__ import annotations

import logging
from typing import Type

from backend.services.mirror import credentials
from backend.services.mirror.base import MirrorProvider, generate_thread_title
from backend.services.mirror.google_drive import GoogleDriveMirrorProvider

logger = logging.getLogger(__name__)


#: Map of ``provider_name`` → concrete class. Add new providers here.
_PROVIDERS: dict[str, Type[MirrorProvider]] = {
    GoogleDriveMirrorProvider.provider_name: GoogleDriveMirrorProvider,
}


async def get_provider(enterprise_id: str) -> MirrorProvider | None:
    """Return the active mirror provider for an enterprise, or ``None``.

    Looks up any ``MirrorCredentials`` row for the enterprise and
    instantiates the matching provider class. Returns ``None`` if the
    enterprise has not connected any provider yet — callers should
    treat that as "skip mirror operations" (the run handler does).

    Args:
        enterprise_id: Tenant id.

    Returns:
        A concrete ``MirrorProvider`` instance ready to invoke, or
        ``None``.
    """
    creds = await credentials.load_first(enterprise_id)
    if creds is None:
        return None
    cls = _PROVIDERS.get(creds.provider)
    if cls is None:
        logger.warning(
            "Unknown mirror provider %r for enterprise %s; skipping",
            creds.provider, enterprise_id,
        )
        return None
    return cls(creds)


async def get_provider_for(
    enterprise_id: str, provider_name: str
) -> MirrorProvider | None:
    """Return a provider instance for a specific (enterprise, provider).

    Used by the OAuth router to pick the Google-specific provider
    regardless of what else the enterprise has connected.

    Args:
        enterprise_id: Tenant id.
        provider_name: ``provider_name`` of the desired backend.

    Returns:
        The provider instance, or ``None`` if no credentials row exists
        for that pair or the provider class isn't registered.
    """
    creds = await credentials.load(enterprise_id, provider_name)
    if creds is None:
        return None
    cls = _PROVIDERS.get(provider_name)
    if cls is None:
        return None
    return cls(creds)


__all__ = [
    "MirrorProvider",
    "GoogleDriveMirrorProvider",
    "credentials",
    "generate_thread_title",
    "get_provider",
    "get_provider_for",
]
