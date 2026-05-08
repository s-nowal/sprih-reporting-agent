"""Schemas for the thread-scoped file manager (``/threads/{tid}/files``).

Three response shapes:

* ``FileObject`` — what an item in a list looks like (key, size, mtime).
* ``FileContent`` — what a single-file READ returns (relative key + body).
* ``WriteResult`` — what a PUT or batch POST returns (key + size).

Paths in every schema are *thread-relative* — the ``threads/{tid}/``
prefix never leaks back to the client.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class FileObject(BaseModel):
    """One file in a list response."""

    key: str = Field(description="Thread-relative path (e.g. 'input/userUpload/foo.pdf').")
    size: int = Field(description="Size in bytes.")
    modified_at: datetime = Field(description="Filesystem mtime as ISO 8601.")


class FileContent(BaseModel):
    """Body returned by a single-file READ."""

    key: str
    content: str
    size: int


class WriteResult(BaseModel):
    """Outcome of a PUT or one item of a batch POST."""

    key: str
    size: int


class WriteFileRequest(BaseModel):
    """Body of ``PUT /threads/{tid}/files?path=...`` — text-only writes.

    For binary content, use the multipart ``POST`` endpoint.
    """

    content: str
