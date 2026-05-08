"""Per-folder access policy for thread-scoped files.

Two layers consult this:

1. The REST router (``actor="user"``) — an authenticated human at the
   keyboard going through the Word add-in.
2. (Future) Agent tools (``actor="agent"``) — Python functions running
   inside the LangGraph agent's process.

Both call ``FilePolicy.check`` with the relative path within the thread
(e.g. ``input/userUpload/foo.pdf``, never the full storage key). Lookups
use longest-prefix match — the most-specific rule wins. Paths that
match no rule are denied by default.

Adding a folder convention: extend ``_RULES`` and re-sort by length
descending. The class is data-only; no infra dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from fastapi import HTTPException


# Permission tokens.
READ = "read"
WRITE = "write"


@dataclass(frozen=True)
class _Rule:
    """One folder convention: prefix + permissions per actor."""

    prefix: str  # ends with "/" (folder boundary)
    user_perms: frozenset[str]
    agent_perms: frozenset[str]


class FilePolicy:
    """Static folder-permission table. Thread-agnostic.

    The policy operates on *relative* paths within a thread. The
    ``threads/{thread_id}/`` storage prefix is added by the handler when
    converting to a storage key.
    """

    # Sorted longest-prefix first so ``check`` can short-circuit on the
    # first matching rule.
    _RULES: list[_Rule] = sorted(
        [
            _Rule(
                prefix="input/userUpload/",
                user_perms=frozenset({READ, WRITE}),
                agent_perms=frozenset({READ}),
            ),
            _Rule(
                prefix="input/",
                user_perms=frozenset({READ, WRITE}),
                agent_perms=frozenset({READ}),
            ),
            _Rule(
                prefix="output/",
                user_perms=frozenset({READ, WRITE}),
                agent_perms=frozenset({READ, WRITE}),
            ),
        ],
        key=lambda r: -len(r.prefix),
    )

    @classmethod
    def can(cls, path: str, actor: str, permission: str) -> bool:
        """Return whether ``actor`` may perform ``permission`` on ``path``.

        Args:
            path: Thread-relative path (e.g. ``input/userUpload/foo.pdf``
                or ``output/`` for the folder itself). Must not start with
                ``/`` or contain ``..``.
            actor: ``"user"`` or ``"agent"``.
            permission: ``READ`` or ``WRITE``.

        Returns:
            True iff a rule matches ``path`` and grants ``permission`` to
            ``actor``. Default-deny on no match.
        """
        if not _is_safe_relative(path):
            return False
        # Append a trailing "/" so a leaf like ``input/foo.pdf`` is treated
        # as living inside the ``input/`` folder for prefix matching. The
        # rule prefixes themselves all end with "/" by construction.
        candidate = path if path.endswith("/") else path + "/"
        for rule in cls._RULES:
            if candidate.startswith(rule.prefix):
                perms = rule.user_perms if actor == "user" else rule.agent_perms
                return permission in perms
        return False

    @classmethod
    def check(cls, path: str, actor: str, permission: str) -> None:
        """Raise 403 if ``can`` returns False; otherwise no-op.

        Convenience wrapper for FastAPI handlers — turns a deny decision
        into the appropriate HTTP error.

        Args:
            path: See ``can``.
            actor: See ``can``.
            permission: See ``can``.

        Raises:
            HTTPException: 400 if ``path`` fails sanity checks (traversal,
                absolute path, empty); 403 if access is denied.
        """
        if not _is_safe_relative(path):
            raise HTTPException(
                status_code=400, detail=f"Invalid path: {path!r}"
            )
        if not cls.can(path, actor, permission):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"{actor} not permitted to {permission} {path!r}"
                ),
            )


def _is_safe_relative(path: str) -> bool:
    """Reject paths with traversal segments, absolute roots, or empties."""
    if not path:
        return False
    if path.startswith("/"):
        return False
    parts = path.split("/")
    return ".." not in parts and "" not in [p for p in parts[:-1]]
