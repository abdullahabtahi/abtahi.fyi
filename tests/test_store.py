import pytest
from app.core.store import parse_content, render_html, load_public_items, lint_graph

def test_parse_content_extracts_metadata_and_body():
    markdown = "---\ntitle: 'Test Note'\ndate: '2026-09-05'\n---\n# Hello World"
    metadata, body = parse_content(markdown)
    assert metadata.get("title") == "Test Note"
    assert metadata.get("date") == "2026-09-05"
    assert "# Hello World" in body

def test_parse_content_no_frontmatter():
    markdown = "# Hello World\nNo metadata here."
    metadata, body = parse_content(markdown)
    assert metadata == {}
    assert "No metadata here." in body
def test_render_html_alerts_and_math():
    markdown_body = "> [!WARNING]\n> This is an alert.\n\nMath: $E=mc^2$"
    html = render_html(markdown_body)
    assert "markdown-alert" in html
    assert "markdown-alert-warning" in html
    assert "math inline" in html or "class=\"math" in html
def test_load_public_items_ignores_private(tmp_path):
    public_dir = tmp_path / "content" / "public" / "notes"
    public_dir.mkdir(parents=True)
    private_dir = tmp_path / "content" / "private" / "notes"
    private_dir.mkdir(parents=True)
    
    (public_dir / "pub_note.md").write_text("---\ntitle: 'Public'\n---\nHello")
    (private_dir / "priv_note.md").write_text("---\ntitle: 'Private'\n---\nSecret")
    
    items = load_public_items(str(tmp_path / "content"))
    
    assert len(items) == 1
    assert items[0].id == "pub_note"
    assert items[0].plane == "public"
def test_auto_classification_assigns_type_based_on_folder(tmp_path):
    public_dir = tmp_path / "content" / "public"
    for cat in ["notes", "links", "themes", "inquiries"]:
        cat_dir = public_dir / cat
        cat_dir.mkdir(parents=True)
        (cat_dir / f"{cat}_item.md").write_text(f"---\ntitle: 'test {cat}'\n---\nHello")
        
    items = load_public_items(str(tmp_path / "content"))
    
    assert len(items) == 4
    types = {item.type for item in items}
    assert types == {"note", "link", "theme", "inquiry"}

from app.core.store import extract_edges, DanglingEdgeError

def test_extract_edges_from_markdown():
    markdown = "Here is a [link](some-id) and another [one](other-id). And a footnote [^cite1]."
    edges = extract_edges("source-id", markdown)
    assert len(edges) == 2
    target_ids = {e.target_id for e in edges}
    assert target_ids == {"some-id", "other-id"}

def test_lint_graph_raises_dangling_edge_error():
    from app.domain.models import ContentItem, EdgeReference
    items = [
        ContentItem(id="a", plane="public", type="note", title="A", metadata={}, raw_content="", html_content=""),
    ]
    edges = [
        EdgeReference(source_id="a", target_id="b", edge_type="related_to")
    ]
    import pytest
    with pytest.raises(DanglingEdgeError, match="b"):
        lint_graph(items, edges)


def test_firestore_review_store_implements_review_store_protocol():
    from unittest.mock import MagicMock
    from app.core.firestore import FirestoreReviewStore, ReviewStore

    mock_db = MagicMock()
    store = FirestoreReviewStore(mock_db)
    assert isinstance(store, ReviewStore)
    assert hasattr(store, "get_pending_proposals")
    assert callable(store.get_pending_proposals)
    assert hasattr(store, "run_proposal_once")
    assert hasattr(store, "apply_private_projection")

