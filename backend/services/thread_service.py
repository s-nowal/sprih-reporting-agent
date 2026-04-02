"""Thread persistence service — interface for DB-backed implementation."""

from typing import Any


class ThreadService:
    async def create(self, thread_id: str, metadata: dict[str, Any]) -> dict:
        raise NotImplementedError

    async def get(self, thread_id: str) -> dict:
        raise NotImplementedError

    async def search(
        self, enterprise_id: str, metadata: dict | None, status: str | None,
        limit: int = 10, offset: int = 0,
    ) -> list[dict]:
        raise NotImplementedError

    async def update(self, thread_id: str, metadata: dict[str, Any]) -> dict:
        raise NotImplementedError

    async def delete(self, thread_id: str) -> None:
        raise NotImplementedError
