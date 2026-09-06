import re
import hashlib
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "source"
}
MAX_FEED_BYTES = 5 * 1024 * 1024

def canonicalize_url(url: str) -> str:
    """Normalizes URL for deterministic deduplication."""
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = re.sub(r":(80|443)$", "", parsed.netloc.lower())
    
    query_pairs = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    
    # Remove trailing slash ONLY if path is just "/"
    path = parsed.path
    
    return urlunparse((scheme, netloc, path, "", query, ""))

def compute_content_hash(text: str) -> str:
    """Computes SHA-256 over normalized whitespace body text."""
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

class CanonicalURL:
    """Optional Pydantic/Dataclass wrapper if needed later"""
    def __init__(self, raw_url: str):
        self.raw_url = raw_url
        self.canonical = canonicalize_url(raw_url)
        
    def __str__(self):
        return self.canonical

import httpx
import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Optional, Tuple
from app.models.feed import FeedSource
from app.core.security import validate_outbound_target, validate_outbound_url as security_validate_url

# US3: High-Concurrency Worker Pool Semaphore
poll_semaphore = asyncio.Semaphore(5)


class PollFailure(StrEnum):
    UNSAFE_TARGET = "unsafe_target"
    REDIRECT_LIMIT = "redirect_limit"
    RESPONSE_TOO_LARGE = "response_too_large"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"


@dataclass(frozen=True)
class PollResult:
    content: str | None
    status_code: int
    etag: str | None
    last_modified: str | None
    failure: PollFailure | None = None

    def __iter__(self):
        yield self.content
        yield self.status_code
        yield self.etag
        yield self.last_modified


async def poll_feed(
    feed: FeedSource,
    *,
    client=None,
    validator: Callable[[str], str] | None = None,
) -> PollResult:
    """
    Polls a feed safely.
    Returns (content, status_code, new_etag, new_last_modified).
    """
    async with poll_semaphore:
        headers = {}
        if feed.etag:
            headers["If-None-Match"] = feed.etag
        if feed.last_modified:
            headers["If-Modified-Since"] = feed.last_modified

        try:
            owns_client = client is None
            if owns_client:
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False
                )
            try:
                request_url = feed.url
                for _ in range(4):
                    try:
                        if validator is None:
                            if not security_validate_url(request_url):
                                raise ValueError("unsafe target")
                        else:
                            validator(request_url)
                    except (ValueError, TypeError):
                        return PollResult(None, 403, None, None, PollFailure.UNSAFE_TARGET)

                    response = await client.get(request_url, headers=headers)

                    if 300 <= response.status_code < 400:
                        location = response.headers.get("Location")
                        if not location:
                            return PollResult(None, response.status_code, None, None, PollFailure.HTTP_ERROR)
                        response_url = str(getattr(getattr(response, "request", None), "url", request_url))
                        request_url = urljoin(response_url, location)
                        continue
                
                    if response.status_code == 304:
                        return PollResult(None, 304, None, None)

                    response.raise_for_status()

                    content_length = response.headers.get("Content-Length")
                    if content_length is not None and int(content_length) > MAX_FEED_BYTES:
                        return PollResult(None, 413, None, None, PollFailure.RESPONSE_TOO_LARGE)
                    body = response.content
                    if isinstance(body, (bytes, bytearray)) and len(body) > MAX_FEED_BYTES:
                        return PollResult(None, 413, None, None, PollFailure.RESPONSE_TOO_LARGE)

                    new_etag = response.headers.get("ETag")
                    new_lm = response.headers.get("Last-Modified")

                    return PollResult(response.text, response.status_code, new_etag, new_lm)
                
                return PollResult(None, 508, None, None, PollFailure.REDIRECT_LIMIT)
            finally:
                if owns_client and hasattr(client, "aclose"):
                    await client.aclose()
        except httpx.RequestError:
            return PollResult(None, 500, None, None, PollFailure.NETWORK_ERROR)
        except httpx.HTTPStatusError as error:
            return PollResult(None, error.response.status_code, None, None, PollFailure.HTTP_ERROR)

import feedparser
from app.ingest.chunker import html_to_markdown, chunk_markdown_ast
from app.domain.models import MarkdownChunk


def extract_feed_entries(feed: FeedSource, content: str) -> list[tuple[str, str, str]]:
    """Extract canonical entry URLs and normalized markdown without persistence."""
    parsed = feedparser.parse(content)
    entries: list[tuple[str, str, str]] = []
    for entry in parsed.entries:
        title = str(entry.get("title", "")).strip()
        link = str(entry.get("link", "")).strip()
        html_content = entry.get("content", [{"value": ""}])[0].get("value", "")
        if not html_content:
            html_content = entry.get("summary", "")
        if not title or not link or not html_content:
            continue
        markdown = html_to_markdown(html_content)
        if markdown:
            entries.append((title, canonicalize_url(link), markdown))
    return entries

async def process_feed(feed: FeedSource) -> list[MarkdownChunk]:
    """
    Polls a feed, parses it, extracts entries, converts to markdown,
    and chunks the content.
    """
    content, status, new_etag, new_lm = await poll_feed(feed)
    
    if not content or status == 304:
        return []
        
    chunks = []
    for title, _link, markdown_text in extract_feed_entries(feed, content):
        # Add a title heading to the markdown text for AST breadcrumbs
        full_markdown = f"# {title}\n\n{markdown_text}"
        
        entry_chunks = list(chunk_markdown_ast(full_markdown))
        # Optional: attach source link to chunks if needed
        chunks.extend(entry_chunks)
        
    return chunks

async def run_poller_pool(feeds: list[FeedSource]):
    """
    Runs process_feed concurrently for multiple feeds.
    Includes defensive try-except blocks so one failure doesn't crash the pool.
    """
    async def safe_process(feed: FeedSource):
        try:
            return await process_feed(feed)
        except Exception as e:
            # T020 Defensive block
            print(f"Error processing feed {feed.url}: {e}")
            return []
            
    tasks = [safe_process(f) for f in feeds]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_chunks = []
    for res in results:
        if isinstance(res, list):
            all_chunks.extend(res)
            
    return all_chunks
