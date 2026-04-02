"""Deliverable lifecycle service — interface for DB + S3 implementation."""

from typing import Any


class DeliverableService:
    async def list(
        self, enterprise_id: str, thread_id: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        raise NotImplementedError

    async def get(self, deliverable_id: str) -> dict:
        raise NotImplementedError

    async def download(self, deliverable_id: str) -> bytes:
        raise NotImplementedError
