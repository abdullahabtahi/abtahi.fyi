from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PrivateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class FeedSource(PrivateRecord):
    id: str
    url: str
    last_fetched_at: Optional[datetime] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None

class IngestedItem(PrivateRecord):
    id: str
    feed_id: str
    title: str
    canonical_url: str
    content_markdown: str
    content_hash: str
    published_at: Optional[datetime] = None

class ContentChunk(PrivateRecord):
    id: str
    item_id: str
    text: str
    token_count: int
    sequence_index: int


class ApprovedFeed(PrivateRecord):
    id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    active: bool = True
    etag: str | None = None
    last_modified: str | None = None


class SourceRevision(PrivateRecord):
    id: str = Field(min_length=1)
    uid: str = Field(min_length=1)
    feed_id: str = Field(min_length=1)
    canonical_url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    archive_key: str = Field(min_length=1)
    captured_at: datetime


class SourcePassage(PrivateRecord):
    id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    location: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ConsentDecision(PrivateRecord):
    uid: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    granted: bool
    decided_at: datetime


class CollectionStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class CollectionOutcome(PrivateRecord):
    feed_id: str = Field(min_length=1)
    status: CollectionStatus
    reason: str | None = None
    revision_ids: tuple[str, ...] = ()
