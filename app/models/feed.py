from pydantic import BaseModel, HttpUrl
from typing import Optional
from datetime import datetime

class FeedSource(BaseModel):
    id: str
    url: str
    last_fetched_at: Optional[datetime] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None

class IngestedItem(BaseModel):
    id: str
    feed_id: str
    title: str
    canonical_url: str
    content_markdown: str
    content_hash: str
    published_at: Optional[datetime] = None

class ContentChunk(BaseModel):
    id: str
    item_id: str
    text: str
    token_count: int
    sequence_index: int
