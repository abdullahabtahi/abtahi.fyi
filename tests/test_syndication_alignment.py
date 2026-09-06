import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.web.app import create_app
from app.core.public_loader import PublicContentLoader
from app.core.network import network_cache

@pytest_asyncio.fixture
async def app_client():
    app = create_app()
    # Ensure items are loaded into the network cache for test queries
    loader = PublicContentLoader()
    items = loader.load_all_items()
    network_cache.load_from_items(items)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

# Phase 2 Foundation Test
def test_public_content_loader_and_cache_foundation():
    loader = PublicContentLoader()
    items = loader.load_all_items()
    assert len(items) >= 3
    
    # Check typed items
    ids = {item.id for item in items}
    assert "declarative-attention" in ids
    assert "eebench-circuit-design" in ids
    assert "superseded-sample" in ids

    # Check edges parsed
    decl_item = next(i for i in items if i.id == "declarative-attention")
    assert len(decl_item.edges) >= 2
    edge_types = {e.edge_type for e in decl_item.edges}
    assert "supports" in edge_types or "challenges" in edge_types

    # Check graph cache
    network_cache.load_from_items(items)
    snapshot = network_cache.get_snapshot()
    assert snapshot.total_items >= 3
    assert snapshot.total_edges >= 3
    assert len(snapshot.tensions) >= 1

# --- User Story 1 Tests ---

@pytest.mark.asyncio
async def test_timeline_single_column_day_headers_and_badges(app_client):
    """T008: Verify single-column (640px) reading stream with <time> day headers and edge badges."""
    response = await app_client.get("/")
    assert response.status_code == 200
    html = response.text

    # Verify single-column measure
    assert "max-w-[640px]" in html

    # Verify day header with <time>
    assert "day-header" in html
    assert "<time" in html

    # Verify item titles and badges
    assert "Declarative Attention in Autonomous Systems" in html
    assert "EEBench: Measuring Hardware Efficiency in Tensor Compilers" in html

@pytest.mark.asyncio
async def test_permalink_relationship_groups_and_superseded_banner(app_client):
    """T009: Verify permalink incoming/outgoing relationship groups and superseded_by warning."""
    # Test item with connections
    response = await app_client.get("/i/declarative-attention")
    assert response.status_code == 200
    html = response.text

    assert "Declarative Attention in Autonomous Systems" in html
    # Should render relationship section with groups
    assert "connection-group" in html or "relationship-group" in html
    assert "eebench-circuit-design" in html

    # Test superseded item
    response_superseded = await app_client.get("/i/superseded-sample")
    assert response_superseded.status_code == 200
    html_superseded = response_superseded.text

    # Should render superseded warning banner
    assert "superseded-banner" in html_superseded or "superseded_by" in html_superseded
    assert "declarative-attention" in html_superseded

# --- User Story 2 Tests ---

@pytest.mark.asyncio
async def test_agent_feeds_and_discovery_endpoints(app_client):
    """T013: Verify /llms.txt, /feed.json, and /feed.xml endpoints."""
    # 1. /llms.txt
    resp_llms = await app_client.get("/llms.txt")
    assert resp_llms.status_code == 200
    assert "text/markdown" in resp_llms.headers["content-type"]
    llms_text = resp_llms.text
    assert "Abdullah Abtahi" in llms_text
    assert "riff" in llms_text.lower()
    assert "/feed.json" in llms_text
    assert "/feed.xml" in llms_text
    assert "/api/fyi/q" in llms_text

    # 2. /feed.json
    resp_json = await app_client.get("/feed.json")
    assert resp_json.status_code == 200
    data = resp_json.json()
    assert data["version"] == "https://jsonfeed.org/version/1.1"
    items = data["items"]
    assert len(items) >= 2
    # Verify _fyi extensions
    for it in items:
        assert "_fyi" in it
        assert "item_type" in it["_fyi"]

    # 3. /feed.xml (Atom 1.0)
    resp_atom = await app_client.get("/feed.xml")
    assert resp_atom.status_code == 200
    assert "atom+xml" in resp_atom.headers["content-type"] or "xml" in resp_atom.headers["content-type"]
    xml_text = resp_atom.text
    assert "<feed" in xml_text
    assert "http://www.w3.org/2005/Atom" in xml_text
    assert "<entry>" in xml_text

@pytest.mark.asyncio
async def test_dual_routing_query_api(app_client):
    """T014: Verify dual path-based and query-based REST Query API endpoints."""
    # 1. Search: path vs query string
    r1 = await app_client.get("/api/fyi/q/search/attention")
    assert r1.status_code == 200
    results_path = r1.json()

    r2 = await app_client.get("/api/fyi/q/search?q=attention")
    assert r2.status_code == 200
    results_query = r2.json()

    assert len(results_path) > 0
    assert len(results_query) > 0
    assert results_path[0]["id"] == results_query[0]["id"]

    # 2. Edges
    r_edges = await app_client.get("/api/fyi/q/edges/declarative-attention")
    assert r_edges.status_code == 200
    edges_data = r_edges.json()
    assert "outgoing" in edges_data
    assert "incoming" in edges_data

    # 3. Items list & detail
    r_items = await app_client.get("/api/fyi/q/items")
    assert r_items.status_code == 200
    assert len(r_items.json()) >= 3

    r_item = await app_client.get("/api/fyi/q/items/declarative-attention")
    assert r_item.status_code == 200
    assert r_item.json()["id"] == "declarative-attention"

    # 4. Summary snapshot
    r_summary = await app_client.get("/api/fyi/q/summary")
    assert r_summary.status_code == 200
    summary_data = r_summary.json()
    assert "total_items" in summary_data
    assert "total_edges" in summary_data
    assert "top_connected" in summary_data

# --- User Story 3 Tests ---

@pytest.mark.asyncio
async def test_intellectual_tensions_page(app_client):
    """T020: Verify /tensions renders true 'challenges' conflict pairs with quotes and rationale."""
    response = await app_client.get("/tensions")
    assert response.status_code == 200
    html = response.text

    assert "tension-card" in html
    # Check that it renders challenges relationship
    assert "challenges" in html.lower() or "tension" in html.lower()
    # Check that reason is displayed
    assert "Procedural token loops introduce non-deterministic state bloat" in html or "declarative-attention" in html

@pytest.mark.asyncio
async def test_gravity_centers_and_themes_pages(app_client):
    """T021: Verify /connected renders PageRank authority hubs and /themes renders Louvain community synthesis."""
    # 1. /connected
    r_conn = await app_client.get("/connected")
    assert r_conn.status_code == 200
    html_conn = r_conn.text
    assert "PageRank" in html_conn or "Authority" in html_conn
    assert "declarative-attention" in html_conn or "EEBench" in html_conn

    # 2. /themes
    r_themes = await app_client.get("/themes")
    assert r_themes.status_code == 200
    html_themes = r_themes.text
    assert "theme-card" in html_themes or "community" in html_themes.lower()

# --- User Story 4 Tests ---

@pytest.mark.asyncio
async def test_zero_leakage_of_private_study_concepts(app_client):
    """T025: Prove 0% leakage of private study data across public endpoints."""
    # 1. Direct path/query search for private curriculum IDs
    r_search = await app_client.get("/api/fyi/q/search/m1l1")
    assert r_search.status_code == 200
    assert len(r_search.json()) == 0

    # 2. Public feed contains zero private items
    r_feed = await app_client.get("/feed.json")
    assert r_feed.status_code == 200
    feed_text = r_feed.text
    assert "m1l1" not in feed_text.lower()
    assert "private" not in feed_text.lower()

    # 3. PublicContentLoader strictly rejects private file paths
    loader = PublicContentLoader()
    with pytest.raises(ValueError, match="Security Violation"):
        loader.load_item("content/private/module1.md")

@pytest.mark.asyncio
async def test_semantic_fallback_to_fts5(app_client, monkeypatch):
    """T026: Verify graceful fallback to FTS5 keyword search on Gemini embedding failure."""
    from unittest.mock import patch

    # Mock embedding failure (simulating outage or quota exhaustion)
    with patch("app.routers.api_public._get_query_embedding_cached", return_value=None):
        response = await app_client.get("/api/fyi/q/semantic/attention")
        assert response.status_code == 200
        assert response.headers.get("X-Search-Fallback") == "true"
        data = response.json()
        assert len(data) > 0
        assert any(r.get("fallback") is True for r in data)
        assert any("attention" in r["title"].lower() for r in data)

@pytest.mark.asyncio
async def test_summary_response_latency_benchmark(app_client):
    """T027: Verify sub-50ms (typically sub-15ms) response time for /api/fyi/q/summary."""
    import time
    
    # Warmup
    await app_client.get("/api/fyi/q/summary")

    # Benchmark 3 requests
    durations = []
    for _ in range(3):
        start = time.perf_counter()
        resp = await app_client.get("/api/fyi/q/summary")
        duration = time.perf_counter() - start
        assert resp.status_code == 200
        durations.append(duration)

    avg_duration = sum(durations) / len(durations)
    assert avg_duration < 0.05, f"Expected <50ms, got {avg_duration*1000:.2f}ms"




