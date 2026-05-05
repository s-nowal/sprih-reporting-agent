"""Source document service — interface for S3 + DB implementation."""


class SourceService:
    async def store(self, enterprise_id: str, filename: str, content: bytes) -> dict:
        raise NotImplementedError

    async def list(
        self, enterprise_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        raise NotImplementedError

    async def get(self, source_id: str) -> dict:
        raise NotImplementedError
