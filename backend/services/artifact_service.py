"""Artifact lifecycle service — interface for DB + S3 implementation."""


class ArtifactService:
    async def list(
        self, enterprise_id: str, thread_id: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        raise NotImplementedError

    async def get(self, artifact_id: str) -> dict:
        raise NotImplementedError

    async def download(self, artifact_id: str) -> bytes:
        raise NotImplementedError
