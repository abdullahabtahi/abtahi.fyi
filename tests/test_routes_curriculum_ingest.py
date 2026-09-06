from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.api.routes_study import get_concept_store, get_review_store
from app.auth.dependencies import require_csrf, require_identity
from app.domain.models import ConceptNode, CourseModule, Identity
from app.web.app import create_app


class InMemoryConceptStore:
    def __init__(self) -> None:
        self.modules: dict[str, CourseModule] = {}
        self.concepts: dict[str, ConceptNode] = {}
        self.sources: dict[str, dict] = {}

    async def save_concept(self, uid: str, concept: ConceptNode) -> None:
        self.concepts[concept.slug] = concept

    async def get_concept(self, uid: str, slug: str) -> ConceptNode | None:
        return self.concepts.get(slug)

    async def list_concepts(self, uid: str, module: str | None = None) -> list[ConceptNode]:
        res = list(self.concepts.values())
        if module:
            res = [c for c in res if c.module == module]
        res.sort(key=lambda c: (c.module, c.order, c.slug))
        return res

    async def append_citation(self, uid: str, slug: str, citation_text: str) -> None:
        if slug in self.concepts:
            c = self.concepts[slug]
            if citation_text not in c.citations:
                c.citations.append(citation_text)

    async def save_module(self, uid: str, module: CourseModule) -> None:
        self.modules[module.module_id] = module

    async def list_modules(self, uid: str) -> list[CourseModule]:
        return sorted(list(self.modules.values()), key=lambda m: m.module_id)

    async def save_source(self, uid: str, source_id: str, data: dict) -> None:
        self.sources[source_id] = data

    async def list_sources(self, uid: str) -> list[dict]:
        return list(self.sources.values())


@pytest.fixture
def study_client():
    app = create_app()
    concept_store = InMemoryConceptStore()
    review_store = AsyncMock()
    review_store.get_pending_proposals.return_value = []

    app.dependency_overrides[require_identity] = lambda: Identity(
        uid="test-user", email="test@example.com"
    )
    app.dependency_overrides[require_csrf] = lambda: True
    app.dependency_overrides[get_concept_store] = lambda: concept_store
    app.dependency_overrides[get_review_store] = lambda: review_store

    return TestClient(app), concept_store


def test_study_map_empty_state(study_client):
    client, _ = study_client
    response = client.get("/study")
    assert response.status_code == 200
    assert "Curriculum Study Map" in response.text
    assert "No course curriculum ingested yet" in response.text


def test_ingest_view_renders(study_client):
    client, _ = study_client
    response = client.get("/study/ingest")
    assert response.status_code == 200
    assert "Ingest Course Material" in response.text
    assert "Analyze & Preview Concepts" in response.text


def test_ingest_preview_endpoint(study_client):
    client, _ = study_client
    sample_text = """MODULE 1 | LESSON 1
Test Architecture & Design
1.1 Modular Decoupling
Decoupling enables independent deployment.
"""
    response = client.post(
        "/api/study/ingest/preview",
        data={"content_text": sample_text, "module_id": "M1L1"},
    )
    assert response.status_code == 200
    assert "Modular Decoupling" in response.text
    assert "Confirm & Add to Study Map" in response.text


def test_ingest_commit_persists_and_populates_study_map(study_client):
    client, store = study_client
    sample_text = """MODULE 1 | LESSON 1
Foundations of Resilience
1.1 Single Points of Failure
A chokepoint disables the entire network.
"""
    # 1. Commit concepts
    response = client.post(
        "/api/study/ingest/commit",
        data={"content_text": sample_text, "module_id": "M1L1"},
    )
    assert response.status_code == 200

    # 2. Check store has the concept
    assert "single-points-of-failure" in store.concepts
    concept = store.concepts["single-points-of-failure"]
    assert concept.title == "Single Points of Failure"

    # 3. Check /study now renders the module and concept
    study_resp = client.get("/study")
    assert study_resp.status_code == 200
    assert "M1L1" in study_resp.text
    assert "Foundations of Resilience" in study_resp.text
    assert "Single Points of Failure" in study_resp.text
    assert "/concepts/single-points-of-failure" in study_resp.text

    # 4. Check /concepts/{slug} renders the full synthesis
    concept_resp = client.get("/concepts/single-points-of-failure")
    assert concept_resp.status_code == 200
    assert "Single Points of Failure" in concept_resp.text
    assert "A chokepoint disables the entire network" in concept_resp.text


def test_unauthenticated_study_routes_redirect_to_signin():
    app = create_app()
    # Ensure NO dependency overrides for auth
    unauthed_client = TestClient(app)

    # Browser GET requests MUST redirect to /sign-in (HTTP 303)
    resp = unauthed_client.get("/study", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/sign-in"

    resp_ingest = unauthed_client.get("/study/ingest", follow_redirects=False)
    assert resp_ingest.status_code == 303
    assert resp_ingest.headers["location"] == "/sign-in"

    # API POST requests without auth MUST redirect or reject
    resp_post = unauthed_client.post(
        "/api/study/ingest/preview",
        data={"content_text": "sample", "module_id": "M1L1"},
        follow_redirects=False,
    )
    assert resp_post.status_code in {303, 403}


def test_authenticated_navigation_renders_study_and_today_links(study_client):
    client, _ = study_client
    resp = client.get("/study")
    assert resp.status_code == 200
    # Must have distinct links to Study Map, Today queue, and Ingest
    assert 'href="/study"' in resp.text
    assert 'href="/today"' in resp.text
    assert 'href="/study/ingest"' in resp.text
    assert "Study Map" in resp.text


def test_today_empty_state_provides_study_ctas(study_client):
    client, _ = study_client
    resp = client.get("/today")
    assert resp.status_code == 200
    assert "No proposals queued for today" in resp.text
    assert 'href="/study"' in resp.text
    assert 'href="/study/ingest"' in resp.text


@pytest.mark.asyncio
async def test_sources_archive_view_renders_sources_and_study_links(study_client):
    client, concept_store = study_client
    await concept_store.save_source(
        uid="test-user",
        source_id="src-test-m1",
        data={
            "source_id": "src-test-m1",
            "module_id": "M1L1",
            "title": "Lecture 1: Fragility and Chokepoints",
            "content_length": 1200,
            "concepts_count": 3,
            "created_at": "2026-09-06T10:00:00Z",
        },
    )

    resp = client.get("/sources")
    assert resp.status_code == 200
    assert 'id="sources-archive"' in resp.text
    assert "Lecture 1: Fragility and Chokepoints" in resp.text
    assert 'href="/study"' in resp.text
    assert 'href="/study/ingest"' in resp.text


def test_semantic_search_returns_live_results(study_client):
    client, _ = study_client
    resp = client.get("/api/semantic?query=attention")
    assert resp.status_code == 200
    assert "Found 1 result" in resp.text
    assert "/i/declarative-attention" in resp.text
    assert "Declarative Attention in Autonomous Systems" in resp.text


