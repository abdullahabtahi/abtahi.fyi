import pytest
import httpx

from app.core.link_validator import (
    validate_url_syntax,
    check_url_health,
    validate_public_items_links,
)
from app.core.public_loader import PublicContentLoader


def test_validate_url_syntax_valid():
    ok, err = validate_url_syntax("https://eebench.org/", expected_domain="eebench.org")
    assert ok is True
    assert err is None

    # Subdomain matching
    ok, err = validate_url_syntax("https://docs.eebench.org/guide", expected_domain="eebench.org")
    assert ok is True
    assert err is None


def test_validate_url_syntax_disallowed_schemes_and_hosts():
    # Insecure / disallowed schemes
    ok, err = validate_url_syntax("javascript:alert(1)")
    assert ok is False
    assert "Insecure or unsupported scheme" in err

    ok, err = validate_url_syntax("file:///etc/passwd")
    assert ok is False

    # Localhost disallowed in public links
    ok, err = validate_url_syntax("http://localhost:8000/test")
    assert ok is False
    assert "Disallowed local/internal host" in err

    ok, err = validate_url_syntax("http://127.0.0.1:5000/api")
    assert ok is False
    assert "Disallowed local/internal host" in err


def test_validate_url_syntax_domain_mismatch():
    ok, err = validate_url_syntax("https://attacker.com/spoof", expected_domain="eebench.org")
    assert ok is False
    assert "Domain mismatch" in err


def test_all_public_markdown_items_have_valid_canonical_urls():
    """Production quality guardrail: every canonical URL in content/public must be valid."""
    loader = PublicContentLoader()
    items = loader.load_all_items()
    assert len(items) >= 3

    for item in items:
        if item.canonical_url:
            ok, err = validate_url_syntax(item.canonical_url, item.domain)
            assert ok is True, f"Invalid canonical_url in item '{item.id}': {err}"


@pytest.mark.asyncio
async def test_check_url_health_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await check_url_health("https://example.org/valid", client=client)
        assert res.is_valid is True
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_check_url_health_404_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await check_url_health("https://eebench.org/paper/circuit-design", client=client)
        assert res.is_valid is False
        assert res.status_code == 404
        assert "HTTP 404" in res.error_message


@pytest.mark.asyncio
async def test_check_url_health_head_fallback_to_get():
    """Some WAFs reject HEAD requests with 405 or 403, requiring GET fallback."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await check_url_health("https://protected.org/page", client=client)
        assert res.is_valid is True
        assert res.status_code == 200

