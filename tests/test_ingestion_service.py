from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.feed import ApprovedFeed, CollectionOutcome, SourceRevision
from app.services.ingestion import IngestionService


class MemoryArchive:
    def __init__(self) -> None:
        self.contents: dict[str, str] = {}

    async def put_immutable(self, object_key: str, content: str) -> str:
        self.contents.setdefault(object_key, content)
        return object_key


class MemorySourceStore:
    def __init__(self) -> None:
        self.revisions: dict[tuple[str, str, str], SourceRevision] = {}

    async def find_revision(self, uid: str, canonical_url: str, content_hash: str):
        return self.revisions.get((uid, canonical_url, content_hash))

    async def save_revision(self, revision: SourceRevision) -> None:
        self.revisions[(revision.uid, revision.canonical_url, revision.content_hash)] = revision


@pytest.mark.asyncio
async def test_archive_precedes_immutable_revision_and_deduplicates_normalized_content():
    archive = MemoryArchive()
    sources = MemorySourceStore()
    service = IngestionService(archive, sources)
    feed = ApprovedFeed(id="feed-1", url="https://example.com/feed.xml")

    first = await service.archive_source(
        uid="learner",
        feed=feed,
        canonical_url="https://example.com/article",
        title="Article",
        content="same   content",
        captured_at=datetime.now(UTC),
    )
    second = await service.archive_source(
        uid="learner",
        feed=feed,
        canonical_url="https://example.com/article",
        title="Article",
        content="same content",
        captured_at=datetime.now(UTC),
    )

    assert first.created is True
    assert second.created is False
    assert second.revision.id == first.revision.id
    assert archive.contents[first.revision.archive_key] == "same content"
    assert len(sources.revisions) == 1


def test_private_ingestion_models_are_frozen_and_reject_unknown_fields():
    with pytest.raises(ValidationError):
        ApprovedFeed(id="feed-1", url="https://example.com/feed", unexpected=True)
    outcome = CollectionOutcome(feed_id="feed-1", status="failed", reason="network_error")
    with pytest.raises(ValidationError):
        outcome.status = "completed"
