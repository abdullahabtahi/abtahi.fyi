import os
import glob
import frontmatter
from datetime import datetime
from app.schemas.feeds import PublicItem
from markdown_it import MarkdownIt

class PublicContentLoader:
    def __init__(self, content_dir: str = "content/public"):
        # Absolute path relative to project root
        self.content_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), content_dir)
        # Reuse a single cached MarkdownIt instance to avoid overhead
        if not hasattr(PublicContentLoader, '_shared_md'):
            PublicContentLoader._shared_md = MarkdownIt("commonmark", {"html": True})
        self.md = PublicContentLoader._shared_md

    def load_all_items(self) -> list[PublicItem]:
        items = []
        if not os.path.exists(self.content_dir):
            return items

        for filepath in glob.glob(os.path.join(self.content_dir, "*.md")):
            item = self.load_item(filepath)
            if item:
                items.append(item)
        
        # Sort descending by published_at
        items.sort(key=lambda x: x.published_at, reverse=True)
        return items

    def load_item(self, filepath: str) -> PublicItem | None:
        # Enforce Privacy-by-Design Firewall
        if "private" in filepath:
            raise ValueError(f"Security Violation: Attempted to load private file {filepath}")

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)
            
            slug = os.path.splitext(os.path.basename(filepath))[0]
            title = post.get("title", slug)
            summary = post.get("summary", "")
            tags = post.get("tags", [])
            published_str = post.get("date", datetime.utcnow().isoformat())
            
            # Handle different date formats or simple iso parsing
            try:
                if isinstance(published_str, datetime):
                    published_at = published_str
                else:
                    published_at = datetime.fromisoformat(str(published_str).replace('Z', '+00:00'))
            except ValueError:
                published_at = datetime.utcnow()

            content_html = self.md.render(post.content)

            return PublicItem(
                id=slug,
                title=title,
                summary=summary,
                content_html=content_html,
                tags=tags,
                published_at=published_at,
                connections=0 # Will be populated by the router via NetworkScienceCache
            )
        except Exception:
            # Silently skip malformed items for now, or log error
            return None
