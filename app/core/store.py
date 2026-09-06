import frontmatter
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.gfm import gfm_plugin

def parse_content(markdown_text: str) -> tuple[dict, str]:
    metadata, body = frontmatter.parse(markdown_text)
    return metadata, body

# Cache the MarkdownIt instance at module level to avoid costly instantiations
_md_instance = (
    MarkdownIt('commonmark', {'html': True})
    .use(dollarmath_plugin)
    .use(gfm_plugin)
)

def render_html(markdown_body: str) -> str:
    return _md_instance.render(markdown_body)

from pathlib import Path
from app.domain.models import ContentItem

def load_public_items(content_root: str) -> list[ContentItem]:
    public_path = Path(content_root) / "public"
    items = []
    
    if not public_path.exists():
        return items

    for md_file in public_path.rglob("*.md"):
        # Auto-classification based on parent folder name (US3)
        # Assuming structure: content/public/{category}/file.md
        # The category is relative to public_path
        rel_path = md_file.relative_to(public_path)
        category_folder = rel_path.parts[0] if len(rel_path.parts) > 0 else "notes"
        
        # Map folder names to ContentItem types
        # "notes" -> "note", "links" -> "link", etc.
        if category_folder == "inquiries":
            item_type = "inquiry"
        else:
            item_type = category_folder[:-1] if category_folder.endswith('s') else category_folder
        
        metadata, body = parse_content(md_file.read_text(encoding="utf-8"))
        
        items.append(ContentItem(
            id=md_file.stem,
            plane="public",
            type=item_type,
            title=metadata.get("title", md_file.stem),
            metadata=metadata,
            raw_content=body,
            html_content=render_html(body)
        ))
        
    return items

import re
from app.domain.models import EdgeReference

class DanglingEdgeError(Exception):
    pass

def extract_edges(source_id: str, markdown_body: str) -> list[EdgeReference]:
    # Extract standard links [text](target-id)
    # Filter out http/https links
    edges = []
    # simplistic regex for markdown links
    link_pattern = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
    for match in link_pattern.finditer(markdown_body):
        target = match.group(1)
        if not target.startswith(("http://", "https://", "mailto:")):
            edges.append(EdgeReference(source_id=source_id, target_id=target, edge_type="related_to"))
    
    return edges

def lint_graph(items: list[ContentItem], edges: list[EdgeReference]) -> None:
    valid_ids = {item.id for item in items}
    
    for edge in edges:
        if edge.target_id not in valid_ids:
            raise DanglingEdgeError(f"Dangling edge from {edge.source_id} to non-existent target {edge.target_id}")

if __name__ == "__main__":
    import sys
    import pprint
    
    if len(sys.argv) < 3:
        print("Usage: python -m app.core.store [load|scan|lint] [path]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    target_path = sys.argv[2]
    
    if cmd == "load":
        md = Path(target_path).read_text(encoding="utf-8")
        metadata, body = parse_content(md)
        print("Metadata:", metadata)
        print("HTML length:", len(render_html(body)))
    elif cmd == "scan":
        items = load_public_items(target_path)
        print(f"Scanned {len(items)} items.")
        for item in items:
            print(f"- {item.id} ({item.type})")
    elif cmd == "lint":
        items = load_public_items(target_path)
        all_edges = []
        for item in items:
            all_edges.extend(extract_edges(item.id, item.raw_content))
        try:
            lint_graph(items, all_edges)
            print("Graph is valid. No dangling edges.")
        except DanglingEdgeError as e:
            print("Lint error:", e)
            sys.exit(1)
