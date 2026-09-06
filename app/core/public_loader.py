import os
import glob
from urllib.parse import urlparse
import frontmatter
from datetime import datetime, timezone
import sqlite3
from markdown_it import MarkdownIt

from app.schemas.feeds import (
    PublicItem,
    ItemType,
    EdgeRecord,
    EdgeType,
    EdgeDirection,
)

class PublicContentLoader:
    _shared_md: MarkdownIt | None = None

    def __init__(self, content_dir: str = "content/public"):
        # Absolute path relative to project root
        self.content_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), content_dir)
        if PublicContentLoader._shared_md is None:
            PublicContentLoader._shared_md = MarkdownIt("commonmark", {"html": False})
        self.md = PublicContentLoader._shared_md

    def load_all_items(self) -> list[PublicItem]:
        items = []
        if not os.path.exists(self.content_dir):
            return items

        # Recursively discover all .md files under content/public/
        pattern = os.path.join(self.content_dir, "**", "*.md")
        for filepath in glob.glob(pattern, recursive=True):
            item = self.load_item(filepath)
            if item:
                items.append(item)
        
        # Sort descending by published_at
        items.sort(key=lambda x: x.published_at, reverse=True)
        return items

    def load_item(self, filepath: str) -> PublicItem | None:
        # Enforce Privacy-by-Design Firewall
        normalized_path = os.path.normpath(filepath)
        if "private" in normalized_path.split(os.sep):
            raise ValueError(f"Security Violation: Attempted to load private file {filepath}")

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)
            
            slug = post.get("id") or os.path.splitext(os.path.basename(filepath))[0]
            title = post.get("title", slug)
            summary = post.get("summary")
            commentary = post.get("commentary")
            canonical_url = post.get("canonical_url")
            domain = post.get("domain")
            if canonical_url and not domain:
                try:
                    domain = urlparse(canonical_url).netloc
                except Exception:
                    domain = None

            superseded_by = post.get("superseded_by")
            essay_url = post.get("essay_url")
            essay_title = post.get("essay_title")
            thesis = post.get("thesis")

            # Parse ItemType
            raw_type = post.get("type", "riff").lower()
            try:
                item_type = ItemType(raw_type)
            except ValueError:
                item_type = ItemType.RIFF

            raw_tags = post.get("tags", [])
            tags = tuple(raw_tags) if isinstance(raw_tags, list) else ()

            published_str = post.get("date")
            if isinstance(published_str, datetime):
                if published_str.tzinfo is None:
                    published_at = published_str.replace(tzinfo=timezone.utc)
                else:
                    published_at = published_str
            elif published_str:
                try:
                    published_at = datetime.fromisoformat(str(published_str).replace('Z', '+00:00'))
                except ValueError:
                    published_at = datetime.now(timezone.utc)
            else:
                published_at = datetime.now(timezone.utc)

            # Parse edge declarations
            parsed_edges: list[EdgeRecord] = []
            for raw_edge in post.get("edges", []):
                if isinstance(raw_edge, dict) and "target" in raw_edge:
                    edge_type_str = raw_edge.get("type", "supports").lower()
                    try:
                        edge_type = EdgeType(edge_type_str)
                    except ValueError:
                        edge_type = EdgeType.SUPPORTS

                    parsed_edges.append(
                        EdgeRecord(
                            source_id=slug,
                            target_id=raw_edge["target"],
                            edge_type=edge_type,
                            direction=EdgeDirection.OUTGOING,
                            confidence=float(raw_edge.get("confidence", 1.0)),
                            reason=str(raw_edge.get("reason", "")),
                        )
                    )

            # If superseded_by is defined as top-level frontmatter, ensure edge exists
            if superseded_by and not any(e.target_id == superseded_by and e.edge_type == EdgeType.SUPERSEDED_BY for e in parsed_edges):
                parsed_edges.append(
                    EdgeRecord(
                        source_id=slug,
                        target_id=superseded_by,
                        edge_type=EdgeType.SUPERSEDED_BY,
                        direction=EdgeDirection.OUTGOING,
                        confidence=1.0,
                        reason=f"Superseded by {superseded_by}",
                    )
                )

            content_html = self.md.render(post.content)

            return PublicItem(
                id=slug,
                item_type=item_type,
                title=title,
                summary=summary,
                commentary=commentary,
                content_html=content_html,
                raw_markdown=post.content,
                canonical_url=canonical_url,
                domain=domain,
                published_at=published_at,
                tags=tags,
                edges=tuple(parsed_edges),
                superseded_by=superseded_by,
                essay_url=essay_url,
                essay_title=essay_title,
                thesis=thesis,
                connections=len(parsed_edges)
            )
        except Exception as e:
            if "Security Violation" in str(e):
                raise
            return None

    def index_fts(self, conn: sqlite3.Connection, items: list[PublicItem] | None = None) -> int:
        """
        Indexes public items into the SQLite FTS5 table public_items_fts.
        """
        if items is None:
            items = self.load_all_items()

        # Delete existing entries and re-populate FTS5 table
        cursor = conn.cursor()
        cursor.execute("DELETE FROM public_items_fts;")
        for item in items:
            cursor.execute(
                """
                INSERT INTO public_items_fts (id, title, summary, commentary, content, tags)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    item.id,
                    item.title,
                    item.summary or "",
                    item.commentary or "",
                    item.raw_markdown or "",
                    " ".join(item.tags),
                ),
            )
        conn.commit()
        return len(items)
