"""Link integrity and health validator for public content items.

Enforces production-grade quality: guarantees external links referenced in
public markdown frontmatter are syntactically valid, secure (HTTPS preferred),
and resolvable, preventing broken links or mock URLs from reaching production.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.schemas.feeds import PublicItem

logger = logging.getLogger(__name__)

# Standard browser user agent to prevent false 403s from WAFs (Cloudflare, Fly.io, etc.)
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 (abtahi.fyi-healthcheck/1.0)"


@dataclass(frozen=True)
class LinkValidationResult:
    url: str
    is_valid: bool
    status_code: int | None = None
    error_message: str | None = None
    final_url: str | None = None


def validate_url_syntax(url: str, expected_domain: str | None = None) -> tuple[bool, str | None]:
    """Validates URL structure, security schemes, and optional domain matching."""
    if not url or not isinstance(url, str):
        return False, "URL is empty or not a string"

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme not in ("http", "https"):
        return False, f"Insecure or unsupported scheme: '{parsed.scheme}'. Must be http or https."

    if not parsed.netloc:
        return False, "Missing hostname in URL"

    # Reject localhost or internal IPs in public canonical URLs
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1", "0.0.0.0") or host.endswith(".local"):
        return False, f"Disallowed local/internal host: '{host}'"

    # Verify domain matching if expected
    if expected_domain:
        expected_clean = expected_domain.lower().strip()
        host_clean = host.lower().strip()
        if host_clean != expected_clean and not host_clean.endswith("." + expected_clean):
            return False, f"Domain mismatch: host '{host_clean}' does not match expected '{expected_clean}'"

    return True, None


async def check_url_health(
    url: str,
    timeout_seconds: float = 8.0,
    client: httpx.AsyncClient | None = None,
) -> LinkValidationResult:
    """Asynchronously performs an HTTP HEAD (falling back to GET) to verify link reachability."""
    is_valid_syntax, syntax_err = validate_url_syntax(url)
    if not is_valid_syntax:
        return LinkValidationResult(url=url, is_valid=False, error_message=syntax_err)

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    
    async def _probe(c: httpx.AsyncClient) -> LinkValidationResult:
        try:
            # First try lightweight HEAD request
            response = await c.head(url, headers=headers, timeout=timeout_seconds, follow_redirects=True)
            # Some servers (e.g. AWS S3, Cloudflare, certain nginx configs) return 405 Method Not Allowed or 403 on HEAD
            if response.status_code in (403, 405):
                response = await c.get(url, headers=headers, timeout=timeout_seconds, follow_redirects=True)
            
            if response.status_code < 400:
                return LinkValidationResult(
                    url=url,
                    is_valid=True,
                    status_code=response.status_code,
                    final_url=str(response.url),
                )
            else:
                return LinkValidationResult(
                    url=url,
                    is_valid=False,
                    status_code=response.status_code,
                    error_message=f"HTTP {response.status_code} {response.reason_phrase}",
                )
        except httpx.TimeoutException:
            return LinkValidationResult(
                url=url,
                is_valid=False,
                error_message=f"Connection timed out after {timeout_seconds}s",
            )
        except httpx.RequestError as exc:
            return LinkValidationResult(
                url=url,
                is_valid=False,
                error_message=f"Network request error: {exc}",
            )

    if client:
        return await _probe(client)
    else:
        async with httpx.AsyncClient(verify=True) as local_client:
            return await _probe(local_client)


async def validate_public_items_links(
    items: list[PublicItem],
    live_network_check: bool = False,
) -> dict[str, LinkValidationResult]:
    """Validates all canonical URLs present in a list of public items.
    
    If live_network_check is True, reaches out over the network to verify HTTP status.
    Always verifies syntax, scheme, and domain consistency.
    """
    results: dict[str, LinkValidationResult] = {}
    
    if not live_network_check:
        for item in items:
            if item.canonical_url:
                is_valid, err = validate_url_syntax(item.canonical_url, item.domain)
                results[item.id] = LinkValidationResult(
                    url=item.canonical_url,
                    is_valid=is_valid,
                    error_message=err,
                )
        return results

    async with httpx.AsyncClient(verify=True) as client:
        for item in items:
            if item.canonical_url:
                res = await check_url_health(item.canonical_url, client=client)
                results[item.id] = res

    return results
