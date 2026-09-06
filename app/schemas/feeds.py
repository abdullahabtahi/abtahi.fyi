from enum import StrEnum
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class ItemType(StrEnum):
    RIFF = "riff"    # Original thinking, reaction, distinction, or small argument (no external URL)
    LINK = "link"    # External source + original commentary on why it matters (never a naked URL)
    ESSAY = "essay"  # Pointer to long-form essay with thesis and context

class EdgeType(StrEnum):
    SUPPORTS = "supports"              # Shared plane: Direct confirming proof/evidence
    CHALLENGES = "challenges"          # Shared plane: Intellectual contradiction or tension
    DEVELOPS_INTO = "develops_into"    # FYI plane: Evolutionary progression
    SUPERSEDED_BY = "superseded_by"    # FYI plane: Temporal invalidation
    RELATED_TO = "related_to"          # Shared plane: Lateral associative link
    EXAMPLE_OF = "example_of"          # Study plane (private)
    APPLICATION_OF = "application_of"  # Study plane (private)
    PREREQUISITE_FOR = "prerequisite_for" # Study plane (private)

class EdgeDirection(StrEnum):
    OUTGOING = "outgoing"  # Source item points to target
    INCOMING = "incoming"  # Target item points to source

class EdgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    target_id: str
    edge_type: EdgeType
    direction: EdgeDirection
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = Field(default="")

class PublicItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    item_type: ItemType = ItemType.RIFF
    title: str
    summary: Optional[str] = None          # Excerpt quote from source or opening premise
    commentary: Optional[str] = None       # Original analysis (mandatory for links)
    content_html: str                   # Rendered CommonMark body
    raw_markdown: str = ""              # Source markdown text
    canonical_url: Optional[str] = None    # External URL for links
    domain: Optional[str] = None           # Extracted domain (e.g. "eebench.org")
    published_at: datetime
    tags: Tuple[str, ...] = Field(default_factory=tuple)
    edges: Tuple[EdgeRecord, ...] = Field(default_factory=tuple)
    superseded_by: Optional[str] = None    # Target slug if superseded
    essay_url: Optional[str] = None        # Canonical URL for essays
    essay_title: Optional[str] = None
    thesis: Optional[str] = None
    connections: int = 0

class IntellectualTension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    source_title: str
    target_id: str
    target_title: str
    challenge_quote: str = ""
    reason: str = ""
    triangular_loop: Optional[Tuple[str, ...]] = None

class GraphSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: datetime
    total_items: int
    total_edges: int
    top_connected: Tuple[dict, ...]      # Items ranked by PageRank and degree
    tensions: Tuple[IntellectualTension, ...]
    communities: Tuple[dict, ...]        # Louvain community groups
    edge_type_distribution: Dict[str, int]

class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    item_type: ItemType
    permalink: str
    score: float                         # Similarity score
    snippet: str
    fallback: bool = False               # True if full-text keyword fallback was triggered

# Feed Extensions & JSONFeed 1.1 Support
class FyiExtensions(BaseModel):
    item_type: Optional[str] = None
    canonical_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    pagerank_score: Optional[float] = None
    betweenness_score: Optional[float] = None
    community_id: Optional[int] = None
    edges_count: Optional[int] = None

    model_config = ConfigDict(extra="forbid")

class JSONFeedItem(BaseModel):
    id: str
    url: str
    title: str
    content_html: str
    summary: Optional[str] = None
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
