"""Local filesystem storage adapter (simulates S3 for dev/sandbox).

The adapter exposes an S3-style object API (``read``, ``write``,
``exists``, ``list_objects``) so callers can target it identically against
a future ``BotoS3Storage``. ``abs_path`` is a LocalStorage-only escape
hatch and will not exist on the real S3 implementation.

To add a new backend:
1. Create ``infra/<backend>_storage.py`` with the adapter class.
2. Add a branch in ``get_storage()`` and set ``SPRIH_STORAGE_BACKEND=<backend>`` in .env.
"""

from datetime import datetime
from pathlib import Path


class LocalStorage:
    """Read/write objects under a local-filesystem-backed S3 mock."""

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _abs(self, rel_path: str) -> Path:
        """Resolve a storage-relative path to an absolute filesystem path."""
        return self.root / rel_path

    def write(self, rel_path: str, content: bytes) -> str:
        """Write raw bytes to ``rel_path`` under root. Creates parent dirs. Returns ``rel_path``."""
        full = self._abs(rel_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return rel_path

    def write_text(self, rel_path: str, content: str) -> str:
        """Write UTF-8 text to ``rel_path``. Returns ``rel_path``."""
        return self.write(rel_path, content.encode("utf-8"))

    def read(self, rel_path: str) -> bytes:
        """Read raw bytes from ``rel_path``."""
        return self._abs(rel_path).read_bytes()

    def read_text(self, rel_path: str) -> str:
        """Read UTF-8 text from ``rel_path``."""
        return self._abs(rel_path).read_text(encoding="utf-8")

    def exists(self, rel_path: str) -> bool:
        """Check whether ``rel_path`` exists under root."""
        return self._abs(rel_path).exists()

    def list_objects(self, prefix: str) -> list[dict]:
        """List every object (recursive) whose key starts with ``prefix``.

        Models S3 ``ListObjectsV2`` semantics on top of the local filesystem:
        directories themselves are not returned, only file objects.

        Args:
            prefix: Storage-relative key prefix (no leading ``/``). Trailing
                slashes are tolerated and treated as directory boundaries.

        Returns:
            List of dicts with keys:
              - ``key``: full storage key (storage-relative path).
              - ``size``: object size in bytes.
              - ``modified_at``: filesystem mtime as a local-time ISO 8601 string.

            Returns ``[]`` if the prefix matches no existing objects.
        """
        base = self._abs(prefix)
        if not base.exists():
            return []

        # If the prefix names a single file, return just that one object.
        if base.is_file():
            stat = base.stat()
            key = base.relative_to(self.root).as_posix()
            return [{
                "key": key,
                "size": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }]

        # Otherwise walk the subtree.
        results: list[dict] = []
        for fp in base.rglob("*"):
            try:
                if not fp.is_file():
                    continue
                stat = fp.stat()
            except OSError:
                continue
            results.append({
                "key": fp.relative_to(self.root).as_posix(),
                "size": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        results.sort(key=lambda o: o["key"])
        return results

    def abs_path(self, rel_path: str) -> str:
        """Return the absolute filesystem path for a storage-relative path.

        LocalStorage-only escape hatch used by the mirror service. Will not
        exist on the future ``BotoS3Storage`` implementation; callers that
        need a future-proof path should use ``list_objects`` + ``read``
        instead.
        """
        return str(self._abs(rel_path))


def get_storage(settings) -> LocalStorage:
    """Return the storage adapter selected by ``settings.storage_backend``.

    This is the swap point for adding backends. To add S3:
    1. Create ``infra/s3_storage.py`` with an ``S3Storage`` class.
    2. Add an ``"s3"`` branch here and set ``SPRIH_STORAGE_BACKEND=s3`` in .env.

    Args:
        settings: Application settings (``backend.config.Settings``).

    Returns:
        An initialised storage adapter.

    Raises:
        ValueError: If ``settings.storage_backend`` is not a known value.
    """
    if settings.storage_backend == "local":
        return LocalStorage(settings.storage_root)
    raise ValueError(f"Unknown storage_backend: {settings.storage_backend!r}")
