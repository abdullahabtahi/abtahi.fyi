"""TDD test suite for Nightly Synthesis & Graph Dream Cycle (Spec 012)."""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest
import networkx as nx

from app.core.db import init_sqlite_db
from app.schemas.synthesis import (
    ConsolidationStatus,
    ConsolidationMetrics,
    ConsolidationReport,
    ThemeSynthesisResult,
    TriangularTensionRecord,
    SocraticInquiryRecord,
)


class FakeGeminiClient:
    """Mock Gemini client simulating structured structured output for theme essay synthesis."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.call_count = 0

    async def generate_theme(self, community_nodes: list[dict]) -> ThemeSynthesisResult:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Simulated upstream Gemini model quota/unavailable error")

        node_titles = [n.get("title", "") for n in community_nodes]
        slug = "-".join([n.get("id", "item") for n in community_nodes[:2]])
        return ThemeSynthesisResult(
            title=f"Synthesis on {node_titles[0] if node_titles else 'Complex Systems'}",
            summary="A structured synthesis analyzing emergent interactions and empirical constraints across clustered concepts.",
            body_markdown=(
                "## Architectural Synthesis\n\n"
                "When analyzing these interconnected nodes, the structural topology reveals "
                "a profound coupling between declarative specification and physical execution constraints. "
                "Rather than isolating individual heuristics, systemic resilience emerges from balanced feedback loops."
            ),
            suggested_slug=f"theme-{slug}",
        )


@pytest.fixture
def isolated_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = init_sqlite_db(path)
    yield conn, path
    conn.close()
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_content_dirs():
    tmp_dir = tempfile.mkdtemp(prefix="dream_cycle_content_")
    themes_dir = os.path.join(tmp_dir, "themes")
    inquiries_dir = os.path.join(tmp_dir, "inquiries")
    archive_dir = os.path.join(inquiries_dir, "archive")
    os.makedirs(themes_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    yield {
        "root": tmp_dir,
        "themes": themes_dir,
        "inquiries": inquiries_dir,
        "archive": archive_dir,
    }
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def graph_fixture_data():
    fixture_path = Path(__file__).parent / "fixtures" / "dream_cycle_graph.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_synthesis_schemas():
    """Verify synthesis schema validation and constraints."""
    metrics = ConsolidationMetrics(
        total_nodes_scanned=10,
        total_edges_scanned=15,
        communities_detected=2,
        themes_generated=1,
        themes_preserved=1,
        edges_decayed=3,
        edges_pruned=1,
        triangular_tensions_found=1,
        inquiries_generated=1,
        inquiries_active=2,
    )
    assert metrics.inquiries_active <= 3

    # Verification of max active inquiries constraint (le=3)
    with pytest.raises(Exception):
        ConsolidationMetrics(
            total_nodes_scanned=10,
            total_edges_scanned=15,
            communities_detected=2,
            themes_generated=1,
            themes_preserved=1,
            edges_decayed=3,
            edges_pruned=1,
            triangular_tensions_found=1,
            inquiries_generated=1,
            inquiries_active=4,  # Violates le=3
        )


def test_database_tables_created(isolated_db):
    """Verify DDL creates all 3 dream cycle tables with correct indexes."""
    conn, _ = isolated_db
    cursor = conn.cursor()

    # Verify archived_edges
    cursor.execute("PRAGMA table_info(archived_edges);")
    cols = {row[1] for row in cursor.fetchall()}
    assert "edge_id" in cols
    assert "final_confidence" in cols
    assert "reason" in cols

    # Verify triangular_tensions
    cursor.execute("PRAGMA table_info(triangular_tensions);")
    cols = {row[1] for row in cursor.fetchall()}
    assert "triad_id" in cols
    assert "contradiction_summary" in cols

    # Verify consolidation_runs
    cursor.execute("PRAGMA table_info(consolidation_runs);")
    cols = {row[1] for row in cursor.fetchall()}
    assert "run_id" in cols
    assert "report_json" in cols


# --- User Story 1 Tests (T006, T007) ---

def test_louvain_community_extraction_and_hashing(graph_fixture_data):
    """T006: Test Louvain community detection and cluster hashing."""
    from app.core.network import NetworkScienceCache

    cache = NetworkScienceCache()
    # Hydrate nodes and edges
    for node in graph_fixture_data["nodes"]:
        cache.G.add_node(node["id"], title=node["title"], item_type=node["type"])
    for edge in graph_fixture_data["edges"]:
        cache.G.add_edge(
            edge["source"],
            edge["target"],
            edge_type=edge["type"],
            confidence=edge.get("confidence", 1.0),
            created_at=edge.get("created_at", "2026-05-01T00:00:00Z"),
            last_reinforced_at=edge.get("last_reinforced_at", "2026-05-01T00:00:00Z"),
        )

    communities = cache.extract_louvain_communities(min_size=3)
    assert len(communities) >= 1
    
    for comm in communities:
        assert comm["size"] >= 3
        assert len(comm["cluster_hash"]) == 12
        # Determinism check
        h1 = cache.compute_cluster_hash(comm["members"])
        h2 = cache.compute_cluster_hash(comm["members"])
        assert h1 == h2 == comm["cluster_hash"]


@pytest.mark.asyncio
async def test_theme_essay_generation_and_zero_token_preservation(temp_content_dirs, graph_fixture_data):
    """T007: Test theme essay generation via Fallback Ladder and zero-token preservation on re-run."""
    from app.core.network import NetworkScienceCache
    from app.ai.synthesis import generate_theme_essay, synthesize_community_themes

    cache = NetworkScienceCache()
    for node in graph_fixture_data["nodes"]:
        cache.G.add_node(node["id"], title=node["title"], summary=node.get("summary", ""), item_type=node["type"])
    for edge in graph_fixture_data["edges"]:
        cache.G.add_edge(edge["source"], edge["target"], edge_type=edge["type"])

    fake_client = FakeGeminiClient()
    communities = cache.extract_louvain_communities(min_size=3)
    assert len(communities) >= 1

    # First run: Generates theme essay and writes file
    themes_dir = temp_content_dirs["themes"]
    report = await synthesize_community_themes(
        communities=communities,
        graph=cache.G,
        themes_dir=themes_dir,
        client=fake_client,
        dry_run=False,
    )
    assert report["generated"] >= 1
    assert report["preserved"] == 0
    assert fake_client.call_count >= 1

    # Verify theme files created on disk with valid YAML frontmatter
    theme_files = list(Path(themes_dir).glob("theme-*.md"))
    assert len(theme_files) >= 1
    content = theme_files[0].read_text(encoding="utf-8")
    assert "cluster_hash:" in content
    assert "member_ids:" in content

    # Second run: Zero-token invariant — should preserve existing themes and make 0 LLM calls
    initial_calls = fake_client.call_count
    second_report = await synthesize_community_themes(
        communities=communities,
        graph=cache.G,
        themes_dir=themes_dir,
        client=fake_client,
        dry_run=False,
    )
    assert second_report["generated"] == 0
    assert second_report["preserved"] >= 1
    assert fake_client.call_count == initial_calls  # Zero new API calls!


@pytest.mark.asyncio
async def test_post_consolidate_endpoint_dry_run_and_auth():
    """Verify POST /api/consolidate requires privileged job identity and supports dry run."""
    from app.web.app import create_app
    from app.auth.dependencies import require_job_identity
    from httpx import AsyncClient, ASGITransport

    app = create_app()

    # 1. Unauthenticated request without session or token should fail
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        unauth_resp = await ac.post("/api/consolidate?dry_run=true")
        assert unauth_resp.status_code == 403

    # 2. Privileged job request with dry_run=true
    app.dependency_overrides[require_job_identity] = lambda: True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/consolidate?dry_run=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["status"] == "dry_run"
        assert "metrics" in data
        assert data["metrics"]["total_nodes_scanned"] >= 0


# --- User Story 2 Tests (T012) ---

def test_edge_confidence_decay_rates_exemptions_and_pruning(isolated_db):
    """T012: Verify edge decay calculations, challenges half-rate, superseded_by exemption, and <0.30 pruning."""
    from app.core.network import NetworkScienceCache
    from app.ai.synthesis import prune_stale_edges

    conn, _ = isolated_db
    cache = NetworkScienceCache()

    # Seed edges:
    # 1. Standard edge 100 days old (conf 0.90 -> 0.90 * 0.95 = 0.855)
    # 2. Challenges edge 100 days old (conf 0.90 -> 0.90 * 0.975 = 0.8775)
    # 3. Superseded_by edge 100 days old (conf 0.90 -> exempt, 0.90)
    # 4. Low confidence edge 100 days old (conf 0.31 -> 0.31 * 0.95 = 0.2945 < 0.30 -> pruned)
    # 5. Fresh edge 10 days old (conf 0.90 -> no decay)
    cache.G.add_node("n1")
    cache.G.add_node("n2")
    cache.G.add_node("n3")
    cache.G.add_node("n4")
    cache.G.add_node("n5")

    as_of = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    old_date = "2026-05-01T00:00:00Z"    # ~128 days old
    fresh_date = "2026-09-01T00:00:00Z"  # 5 days old

    cache.G.add_edge("n1", "n2", edge_type="supports", confidence=0.90, last_reinforced_at=old_date)
    cache.G.add_edge("n2", "n3", edge_type="challenges", confidence=0.90, last_reinforced_at=old_date)
    cache.G.add_edge("n3", "n4", edge_type="superseded_by", confidence=0.90, last_reinforced_at=old_date)
    cache.G.add_edge("n4", "n5", edge_type="supports", confidence=0.31, last_reinforced_at=old_date)
    cache.G.add_edge("n1", "n5", edge_type="supports", confidence=0.90, last_reinforced_at=fresh_date)

    decay_results = cache.calculate_edge_decay(as_of_date=as_of)
    by_edge = {(d["source"], d["target"]): d for d in decay_results}

    # 1. Standard 5% decay
    assert by_edge[("n1", "n2")]["new_confidence"] == round(0.90 * 0.95, 4)
    assert by_edge[("n1", "n2")]["is_pruned"] is False

    # 2. Challenges half-rate 2.5% decay
    assert by_edge[("n2", "n3")]["new_confidence"] == round(0.90 * 0.975, 4)
    assert by_edge[("n2", "n3")]["is_pruned"] is False

    # 3. Superseded_by 0% decay exemption
    assert by_edge[("n3", "n4")]["new_confidence"] == 0.90
    assert by_edge[("n3", "n4")]["is_pruned"] is False

    # 4. Below 0.30 pruning
    assert by_edge[("n4", "n5")]["new_confidence"] < 0.30
    assert by_edge[("n4", "n5")]["is_pruned"] is True

    # 5. Fresh edge: no decay
    assert by_edge[("n1", "n5")]["new_confidence"] == 0.90

    # Prune and verify SQLite archiving
    decayed_cnt, pruned_cnt = prune_stale_edges(cache.G, decay_results, db_conn=conn, dry_run=False)
    assert decayed_cnt == 3
    assert pruned_cnt == 1

    # Verify edge was removed from graph
    assert not cache.G.has_edge("n4", "n5")
    assert cache.G.has_edge("n1", "n2")

    # Verify archived_edges table in SQLite
    cursor = conn.cursor()
    cursor.execute("SELECT source_id, target_id, final_confidence, reason FROM archived_edges WHERE source_id='n4';")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "n4"
    assert row[1] == "n5"
    assert row[3] == "confidence_pruned"


def test_citation_reinforcement_hook():
    """T015: Verify citation reinforcement boosts confidence by +0.05 and updates last_reinforced_at."""
    from app.core.network import NetworkScienceCache
    from app.services.review import ReviewService
    from unittest.mock import MagicMock

    cache = NetworkScienceCache()
    cache.G.add_edge("concept-a", "concept-b", confidence=0.80, last_reinforced_at="2026-05-01T00:00:00Z")

    mock_store = MagicMock()
    now_fixed = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
    service = ReviewService(store=mock_store, now=lambda: now_fixed)

    ok = service.reinforce_connection("concept-a", "concept-b", boost=0.05, network_cache=cache)
    assert ok is True

    edge_data = cache.G["concept-a"]["concept-b"]
    assert edge_data["confidence"] == 0.85
    assert edge_data["last_reinforced_at"] == now_fixed.isoformat()

    # Cap at 1.0 check
    service.reinforce_connection("concept-a", "concept-b", boost=0.20, network_cache=cache)
    assert cache.G["concept-a"]["concept-b"]["confidence"] == 1.0


# --- User Story 3 Tests (T016) ---

@pytest.mark.asyncio
async def test_triangular_contradiction_detection_and_api(graph_fixture_data):
    """T016: Test length-3 directed cycle contradiction detection and GET /api/tensions?triangular=true."""
    from app.core.network import NetworkScienceCache, network_cache
    from app.web.app import create_app
    from httpx import AsyncClient, ASGITransport

    # Setup graph with triad
    network_cache.G.clear()
    for node in graph_fixture_data["nodes"]:
        network_cache.G.add_node(node["id"], title=node["title"], item_type=node["type"])
    for edge in graph_fixture_data["edges"]:
        network_cache.G.add_edge(edge["source"], edge["target"], edge_type=edge["type"])

    triads = network_cache.detect_triangular_contradictions()
    assert len(triads) >= 1

    triad_nodes = {triads[0].node_a, triads[0].node_b, triads[0].node_c}
    assert "node-triad-a" in triad_nodes
    assert "node-triad-b" in triad_nodes
    assert "node-triad-c" in triad_nodes

    # Query API endpoint
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/tensions?triangular=true")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert "triad_id" in data[0]
        assert "contradiction_summary" in data[0]
        assert "edge_ca_type" in data[0]

        # Query HTML page
        html_resp = await ac.get("/tensions")
        assert html_resp.status_code == 200
        assert "Triangular Contradiction Triads" in html_resp.text
        assert "3-Cycle Contradiction" in html_resp.text


# --- User Story 4 Tests (T021) ---

@pytest.mark.asyncio
async def test_frontier_socratic_inquiries_max_3_and_auto_resolution(temp_content_dirs, graph_fixture_data):
    """T021: Test frontier concept identification, strict max-3 capping, and auto-resolution to archive."""
    from app.core.network import NetworkScienceCache
    from app.ai.synthesis import generate_socratic_inquiries, resolve_active_inquiries

    cache = NetworkScienceCache()
    for node in graph_fixture_data["nodes"]:
        cache.G.add_node(node["id"], title=node["title"], summary=node.get("summary", ""), item_type=node["type"])
    for edge in graph_fixture_data["edges"]:
        cache.G.add_edge(edge["source"], edge["target"], edge_type=edge["type"])

    cache.precompute_metrics()

    # 1. Frontier concept discovery
    frontier = cache.find_frontier_concepts()
    assert len(frontier) >= 1

    inquiries_dir = temp_content_dirs["inquiries"]
    archive_dir = temp_content_dirs["archive"]

    # 2. Generate inquiries
    gen_count, active_count = await generate_socratic_inquiries(
        frontier_concepts=frontier,
        inquiries_dir=inquiries_dir,
        dry_run=False,
    )
    assert gen_count >= 1
    assert active_count <= 3

    # Verify files created with status active
    active_files = [f for f in Path(inquiries_dir).glob("*.md") if "archive" not in str(f)]
    assert len(active_files) == active_count
    assert len(active_files) <= 3  # STRICT invariant

    # 3. Simulate excess concepts: even with 10 frontier concepts, active files must never exceed 3
    fake_excess = [{"id": f"fake-concept-{i}", "title": f"Fake Concept {i}"} for i in range(10)]
    gen_excess, active_excess = await generate_socratic_inquiries(
        frontier_concepts=fake_excess,
        inquiries_dir=inquiries_dir,
        dry_run=False,
    )
    active_files_after = [f for f in Path(inquiries_dir).glob("*.md") if "archive" not in str(f)]
    assert len(active_files_after) == 3
    assert active_excess == 3

    # 4. Test auto-resolution: pick target concept of one inquiry, add 2 supports edges, run resolve
    inquiry_file = active_files[0]
    import frontmatter
    post = frontmatter.load(str(inquiry_file))
    target = post.metadata["target_concept"]

    # Add 2 incoming supports to target concept in graph
    cache.G.add_node("evidence-1")
    cache.G.add_node("evidence-2")
    cache.G.add_edge("evidence-1", target, edge_type="supports")
    cache.G.add_edge("evidence-2", target, edge_type="supports")

    resolved_count = resolve_active_inquiries(
        graph=cache.G,
        inquiries_dir=inquiries_dir,
        archive_dir=archive_dir,
        dry_run=False,
    )
    assert resolved_count >= 1

    # Verify moved to archive and status updated to resolved
    assert not inquiry_file.exists()
    archived_file = Path(archive_dir) / inquiry_file.name
    assert archived_file.exists()
    archived_post = frontmatter.load(str(archived_file))
    assert archived_post.metadata["status"] == "resolved"
    assert "resolved_at" in archived_post.metadata


@pytest.mark.asyncio
async def test_get_api_inquiries_endpoint(temp_content_dirs):
    """T025: Test GET /api/inquiries endpoint with status filtering and max-3 limit."""
    from app.web.app import create_app
    from httpx import AsyncClient, ASGITransport
    import frontmatter

    # Seed inquiries
    inq_dir = temp_content_dirs["inquiries"]
    arch_dir = temp_content_dirs["archive"]

    # 2 active, 1 archived
    p1 = frontmatter.Post("Question 1?", id="inq-1", target_concept="c1", status="active", created_at="2026-09-01T00:00:00Z")
    with open(os.path.join(inq_dir, "inq-1.md"), "w", encoding="utf-8") as f:
        frontmatter.dump(p1, f)

    p2 = frontmatter.Post("Question 2?", id="inq-2", target_concept="c2", status="active", created_at="2026-09-02T00:00:00Z")
    with open(os.path.join(inq_dir, "inq-2.md"), "w", encoding="utf-8") as f:
        frontmatter.dump(p2, f)

    p3 = frontmatter.Post("Question 3 (resolved)?", id="inq-3", target_concept="c3", status="resolved", created_at="2026-08-01T00:00:00Z", resolved_at="2026-08-10T00:00:00Z")
    with open(os.path.join(arch_dir, "inq-3.md"), "w", encoding="utf-8") as f:
        frontmatter.dump(p3, f)

    # Point public loader to temp content dir
    from app.routers.syndication import loader
    orig_dir = loader.content_dir
    loader.content_dir = temp_content_dirs["root"]

    try:
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Active
            resp = await ac.get("/api/inquiries?status=active")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert all(item["status"] == "active" for item in data)

            # Resolved
            resp_res = await ac.get("/api/inquiries?status=resolved")
            assert resp_res.status_code == 200
            data_res = resp_res.json()
            assert len(data_res) == 1
            assert data_res[0]["id"] == "inq-3"
            assert data_res[0]["status"] == "resolved"

            # All
            resp_all = await ac.get("/api/inquiries?status=all")
            assert resp_all.status_code == 200
            data_all = resp_all.json()
    finally:
        loader.content_dir = orig_dir


# --- Phase 7: Polish & End-to-End Success Criteria Tests (T026-T028) ---

@pytest.mark.asyncio
async def test_end_to_end_consolidation_dream_cycle(isolated_db, temp_content_dirs, graph_fixture_data):
    """T026-T028: Full verification of consolidation cycle covering all 7 success criteria."""
    from app.core.network import NetworkScienceCache
    from app.ai.synthesis import run_consolidation

    conn, _ = isolated_db
    cache = NetworkScienceCache()

    # Hydrate graph with full fixture
    for node in graph_fixture_data["nodes"]:
        cache.G.add_node(
            node["id"],
            title=node["title"],
            summary=node.get("summary", ""),
            item_type=node["type"],
        )
    for edge in graph_fixture_data["edges"]:
        cache.G.add_edge(
            edge["source"],
            edge["target"],
            edge_type=edge["type"],
            confidence=edge.get("confidence", 1.0),
            created_at=edge.get("created_at"),
            last_reinforced_at=edge.get("last_reinforced_at"),
        )
    cache.precompute_metrics()

    fake_client = FakeGeminiClient()
    content_dir = temp_content_dirs["root"]

    # 1. First Run: Live Consolidation
    report = await run_consolidation(
        db_conn=conn,
        network_cache=cache,
        content_dir=content_dir,
        client=fake_client,
        dry_run=False,
    )

    assert report.status == ConsolidationStatus.SUCCESS
    assert report.dry_run is False
    assert report.metrics.total_nodes_scanned == len(cache.G)
    assert report.metrics.communities_detected >= 1
    assert report.metrics.themes_generated >= 1
    assert report.metrics.edges_decayed >= 1
    assert report.metrics.triangular_tensions_found >= 1
    assert report.metrics.inquiries_active <= 3

    # SC-004: Verify SQLite audit logging in consolidation_runs
    cursor = conn.cursor()
    cursor.execute("SELECT run_id, status, themes_generated, report_json FROM consolidation_runs WHERE run_id=?;", (report.run_id,))
    run_row = cursor.fetchone()
    assert run_row is not None
    assert run_row[1] == "success"

    # T026: Verify SQLite snapshot table updated
    cursor.execute("SELECT snapshot_key, snapshot_json FROM public_graph_snapshot WHERE snapshot_key='default';")
    snap_row = cursor.fetchone()
    assert snap_row is not None
    assert "total_items" in snap_row[1]

    # SC-003: Verify triangular tensions in SQLite
    cursor.execute("SELECT COUNT(*) FROM triangular_tensions;")
    assert cursor.fetchone()[0] >= 1

    # SC-002: Second Run (Zero-Token Re-run)
    initial_llm_calls = fake_client.call_count
    second_report = await run_consolidation(
        db_conn=conn,
        network_cache=cache,
        content_dir=content_dir,
        client=fake_client,
        dry_run=False,
    )

    assert second_report.status == ConsolidationStatus.SUCCESS
    assert second_report.metrics.themes_generated == 0
    assert second_report.metrics.themes_preserved >= 1
    assert fake_client.call_count == initial_llm_calls  # Zero new LLM calls consumed!
    assert second_report.duration_ms < 5000  # Well within target






