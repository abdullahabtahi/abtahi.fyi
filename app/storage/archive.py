from typing import Protocol


class ArchiveUnavailable(Exception):
    """The immutable source archive could not durably retain content."""


class SourceArchive(Protocol):
    async def put_immutable(self, object_key: str, content: str) -> str:
        """Store content once and return its private object key."""


class CloudStorageSourceArchive:
    """Cloud Storage adapter for private, content-addressed source objects."""

    def __init__(self, bucket) -> None:
        self.bucket = bucket

    async def put_immutable(self, object_key: str, content: str) -> str:
        import asyncio

        def upload() -> str:
            try:
                blob = self.bucket.blob(object_key)
                if not blob.exists():
                    blob.upload_from_string(content, content_type="text/markdown; charset=utf-8")
                return object_key
            except Exception as error:
                raise ArchiveUnavailable("source archive is unavailable") from error

        return await asyncio.to_thread(upload)
