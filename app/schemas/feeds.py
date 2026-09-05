from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class FyiExtensions(BaseModel):
    tags: List[str] = Field(default_factory=list)
    pagerank_score: Optional[float] = None
    betweenness_score: Optional[float] = None
    community_id: Optional[int] = None

    model_config = ConfigDict(extra="forbid")

class JSONFeedItem(BaseModel):
    id: str
    url: str
    title: str
    content_html: str
    date_published: str
    fyi: FyiExtensions = Field(default_factory=FyiExtensions, alias="_fyi")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

class JSONFeed(BaseModel):
    version: str = "https://jsonfeed.org/version/1.1"
    title: str
    home_page_url: str
    feed_url: str
    items: List[JSONFeedItem]

    model_config = ConfigDict(extra="forbid")

class PublicItem(BaseModel):
    id: str
    title: str
    summary: str
    content_html: str
    tags: List[str] = Field(default_factory=list)
    published_at: datetime
    connections: int = 0

    model_config = ConfigDict(extra="forbid")
