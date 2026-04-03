"""Local filesystem storage adapter (simulates S3 for dev/sandbox)."""

import os
from pathlib import Path


class LocalStorage:
    """Read/write files relative to a root directory."""

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

    def abs_path(self, rel_path: str) -> str:
        """Return the absolute filesystem path for a storage-relative path."""
        return str(self._abs(rel_path))
