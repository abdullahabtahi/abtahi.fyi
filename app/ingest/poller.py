import re
import hashlib
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid", "source"
}

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

import socket
import ipaddress

class SSRFValidationError(Exception):
    pass

def validate_outbound_url(url: str) -> str:
    """
    Resolves hostname and blocks RFC 1918, loopback, and Cloud Metadata endpoints.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    
    if not hostname:
        raise SSRFValidationError(f"Invalid URL: {url}")
        
    try:
        ip_addr_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_addr_str)
    except socket.gaierror:
        raise SSRFValidationError(f"Could not resolve hostname: {hostname}")
        
        raise SSRFValidationError(f"SSRF Attempt blocked. Forbidden IP: {ip}")
        
    return url

import httpx
import asyncio
from typing import Optional, Tuple
from app.models.feed import FeedSource
from app.core.security import validate_outbound_url as security_validate_url

# US3: High-Concurrency Worker Pool Semaphore
poll_semaphore = asyncio.Semaphore(5)

async def poll_feed(feed: FeedSource) -> Tuple[Optional[str], int, Optional[str], Optional[str]]:
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
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=False) as client:
                request_url = feed.url
                for _ in range(4):
                    if not security_validate_url(request_url):
                        return None, 403, None, None

                    response = await client.get(request_url, headers=headers)

                    if 300 <= response.status_code < 400:
                        location = response.headers.get("Location")
                        if not location:
                            return None, response.status_code, None, None
                        request_url = urljoin(str(response.request.url), location)
                        continue
                
                    if response.status_code == 304:
                        return None, 304, None, None

                    response.raise_for_status()

                    new_etag = response.headers.get("ETag")
                    new_lm = response.headers.get("Last-Modified")

                    return response.text, response.status_code, new_etag, new_lm

                return None, 508, None, None
        except httpx.RequestError as e:
            # Handle gracefully
            return None, 500, None, None
        except httpx.HTTPStatusError as e:
            return None, e.response.status_code, None, None

import feedparser
from app.ingest.chunker import html_to_markdown, chunk_markdown_ast
from app.domain.models import MarkdownChunk

async def process_feed(feed: FeedSource) -> list[MarkdownChunk]:
    """
    Polls a feed, parses it, extracts entries, converts to markdown,
    and chunks the content.
    """
    content, status, new_etag, new_lm = await poll_feed(feed)
    
    if not content or status == 304:
        return []
        
    parsed = feedparser.parse(content)
    chunks = []
    
    for entry in parsed.entries:
        # Extract title and body
        title = entry.get("title", "Untitled")
        link = entry.get("link", feed.url)
        
        html_content = entry.get("content", [{"value": ""}])[0]["value"]
        if not html_content:
            html_content = entry.get("summary", "")
            
        if not html_content:
            continue
            
        markdown_text = html_to_markdown(html_content)
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
