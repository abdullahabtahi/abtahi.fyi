import pytest
from app.ingest.chunker import html_to_markdown

def test_html_to_markdown_basic():
    html = "<h1>Title</h1><p>Some paragraph text.</p>"
    markdown = html_to_markdown(html)
    assert "# Title" in markdown
    assert "Some paragraph text." in markdown

def test_html_to_markdown_strips_scripts():
    html = """
    <div>
        <script>alert('xss');</script>
        <style>.class { color: red; }</style>
        <p>Actual content</p>
    </div>
    """
    markdown = html_to_markdown(html)
    assert "alert" not in markdown
    assert ".class" not in markdown
    assert "Actual content" in markdown
