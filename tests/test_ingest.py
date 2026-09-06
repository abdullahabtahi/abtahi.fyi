import pytest
from app.ingest.poller import canonicalize_url, compute_content_hash, CanonicalURL

def test_url_canonicalization_strips_utm():
    raw_url = "https://example.com/article?utm_source=twitter&utm_medium=social&important=true"
    result = canonicalize_url(raw_url)
    assert result == "https://example.com/article?important=true"
    
    url2 = "https://test.org/?gclid=12345&foo=bar"
    assert canonicalize_url(url2) == "https://test.org/?foo=bar"

def test_url_canonicalization_standardizes_slashes_and_lowercase():
    # Removes default port 443 and trailing slash on root
    assert canonicalize_url("HTTPS://Example.COM:443/") == "https://example.com/"
    
    # Keeps path trailing slashes or normalizes them (based on standard)
    assert canonicalize_url("HTTP://test.org:80/path/") == "http://test.org/path/"

def test_compute_content_hash_deterministic():
    text1 = "This is some   text\nwith\rnewlines and   spaces."
    text2 = "This is some text with newlines and spaces."
    
    hash1 = compute_content_hash(text1)
    hash2 = compute_content_hash(text2)
    
    assert hash1 == hash2
    # Check it's a valid sha256 hex string
    assert len(hash1) == 64

from app.ingest.chunker import chunk_markdown_ast
from app.domain.models import MarkdownChunk

def test_ast_markdown_chunking_preserves_breadcrumbs():
    markdown_content = """
# Main Document
Some intro text.
## Section 1
This is section 1 text.
### Subsection A
Detailed subsection info.
"""
    chunks = list(chunk_markdown_ast(markdown_content))
    
    assert len(chunks) == 3
    assert chunks[0].breadcrumb == "[Main Document]"
    assert "intro text" in chunks[0].text
    
    assert chunks[1].breadcrumb == "[Main Document > Section 1]"
    assert "section 1 text" in chunks[1].text
    
    assert chunks[2].breadcrumb == "[Main Document > Section 1 > Subsection A]"
    assert "Detailed subsection info" in chunks[2].text

def test_chunk_length_bounds():
    # Generate long text
    long_text = "word " * 1000
    markdown_content = f"# Big Doc\n{long_text}"
    
    chunks = list(chunk_markdown_ast(markdown_content))
    
    # It should split into multiple chunks
    assert len(chunks) > 1
    # Each chunk should have the breadcrumb
    for chunk in chunks:
        assert chunk.breadcrumb == "[Big Doc]"
        # Token approximation check (very rough length check for characters)
        assert len(chunk.text) <= 2500  # ~500 tokens * 5 chars

import asyncio
from unittest.mock import AsyncMock, patch
import httpx
from httpx import Response
from app.models.feed import FeedSource
from app.ingest.poller import poll_feed

@pytest.mark.asyncio
async def test_poll_feed_success():
    feed = FeedSource(id="1", url="https://example.com/feed.xml", last_fetched_at=None, etag=None, last_modified=None)
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = Response(
            200, 
            content=b"<rss><channel><title>Test Feed</title></channel></rss>",
            headers={"ETag": '"12345"', "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT"},
            request=httpx.Request("GET", "https://example.com/feed.xml")
        )
        
        result, status, new_etag, new_lm = await poll_feed(feed)
        
        assert status == 200
        assert new_etag == '"12345"'
        assert new_lm == "Wed, 21 Oct 2015 07:28:00 GMT"
        assert result is not None
        assert "Test Feed" in result


@pytest.mark.asyncio
async def test_poll_feed_disables_automatic_redirects():
    feed = FeedSource(id="1", url="https://example.com/feed.xml")
    client_options = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, *args, **kwargs):
            return Response(
                200,
                content=b"<rss></rss>",
                request=httpx.Request("GET", feed.url),
            )

    def create_client(**kwargs):
        client_options.update(kwargs)
        return Client()

    with patch("app.ingest.poller.httpx.AsyncClient", side_effect=create_client):
        await poll_feed(feed)

    assert client_options["follow_redirects"] is False


@pytest.mark.asyncio
async def test_poll_feed_rejects_redirect_to_non_public_url():
    feed = FeedSource(id="1", url="https://example.com/feed.xml")

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, *args, **kwargs):
            return Response(
                302,
                headers={"Location": "http://169.254.169.254/metadata"},
                request=httpx.Request("GET", feed.url),
            )

    with (
        patch("app.ingest.poller.httpx.AsyncClient", return_value=Client()),
        patch("app.ingest.poller.security_validate_url", side_effect=[True, False]),
    ):
        content, status, _, _ = await poll_feed(feed)

    assert content is None
    assert status == 403

@pytest.mark.asyncio
async def test_poll_feed_conditional_get():
    feed = FeedSource(id="1", url="https://example.com/feed.xml", last_fetched_at=None, etag='"12345"', last_modified=None)
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = Response(304)
        
        result, status, new_etag, new_lm = await poll_feed(feed)
        
        assert status == 304
        assert result is None
        
        # Verify conditional headers were sent
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["If-None-Match"] == '"12345"'

@pytest.mark.asyncio
async def test_poll_feed_ssrf_blocked():
    feed = FeedSource(id="1", url="http://169.254.169.254/latest/meta-data/", last_fetched_at=None, etag=None, last_modified=None)
    
    # Should block without making an HTTP call
    with patch("httpx.AsyncClient.get") as mock_get:
        result, status, new_etag, new_lm = await poll_feed(feed)
        
        assert status == 403
        assert result is None
        mock_get.assert_not_called()

from app.ingest.poller import process_feed

@pytest.mark.asyncio
async def test_process_feed():
    feed = FeedSource(id="1", url="https://example.com/feed.xml", last_fetched_at=None, etag=None, last_modified=None)
    
    with patch("app.ingest.poller.poll_feed") as mock_poll:
        mock_poll.return_value = (
            """<?xml version="1.0" encoding="utf-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <title>Example Feed</title>
              <entry>
                <title>Test Entry</title>
                <content type="html"><![CDATA[<p>This is a <b>test</b>.</p>]]></content>
              </entry>
            </feed>""",
            200, None, None
        )
        
        chunks = await process_feed(feed)
        assert len(chunks) == 1
        assert chunks[0].breadcrumb == "[Test Entry]"
        assert "This is a **test**." in chunks[0].text
