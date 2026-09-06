import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.ingest.poller import canonicalize_url
from app.ingest.poller import PollFailure, extract_feed_entries, poll_feed
from app.models.feed import ApprovedFeed, CollectionStatus, FeedSource, SourceRevision
from app.storage.archive import SourceArchive


class SourceMetadataStore(Protocol):
    async def find_revision(
        self, uid: str, canonical_url: str, content_hash: str
    ) -> SourceRevision | None: ...

    async def save_revision(self, revision: SourceRevision) -> None: ...


@dataclass(frozen=True)
class ArchiveResult:
    revision: SourceRevision
    created: bool


class IngestionService:
    def __init__(
        self,
        archive: SourceArchive,
        sources: SourceMetadataStore,
        *,
        owner_uid: str = "",
        feeds: tuple[ApprovedFeed, ...] = (),
    ) -> None:
        self.archive = archive
        self.sources = sources
        self.owner_uid = owner_uid
        self.feeds = feeds

    async def archive_source(
        self,
        *,
        uid: str,
        feed: ApprovedFeed,
        canonical_url: str,
        title: str,
        content: str,
        captured_at: datetime,
    ) -> ArchiveResult:
        normalized_content = re.sub(r"\s+", " ", content).strip()
        content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        canonical_url = canonicalize_url(canonical_url)
        existing = await self.sources.find_revision(uid, canonical_url, content_hash)
        if existing is not None:
            return ArchiveResult(existing, created=False)

        object_key = f"private-sources/{uid}/{content_hash}.md"
        archive_key = await self.archive.put_immutable(object_key, normalized_content)
        revision = SourceRevision(
            id=str(uuid.uuid4()),
            uid=uid,
            feed_id=feed.id,
            canonical_url=canonical_url,
            title=title,
            content_hash=content_hash,
            archive_key=archive_key,
            captured_at=captured_at,
        )
        await self.sources.save_revision(revision)
        return ArchiveResult(revision, created=True)

    async def collect_registered_feeds(self) -> dict[str, int]:
        """Poll only configured feeds and count truthful terminal outcomes."""
        counts = {status.value: 0 for status in CollectionStatus}
        for feed in self.feeds:
            result = await poll_feed(
                FeedSource(id=feed.id, url=feed.url, etag=feed.etag, last_modified=feed.last_modified)
            )
            if result.failure is not None:
                counts[CollectionStatus.FAILED.value] += 1
                continue
            if result.status_code == 304 or result.content is None:
                counts[CollectionStatus.SKIPPED.value] += 1
                continue
            entries = extract_feed_entries(feed, result.content)
            if not entries:
                counts[CollectionStatus.SKIPPED.value] += 1
                continue
            try:
                for title, canonical_url, content in entries:
                    await self.archive_source(
                        uid=self.owner_uid,
                        feed=feed,
                        canonical_url=canonical_url,
                        title=title,
                        content=content,
                        captured_at=datetime.now().astimezone(),
                    )
            except Exception:
                counts[CollectionStatus.FAILED.value] += 1
            else:
                counts[CollectionStatus.COMPLETED.value] += 1
        return counts
