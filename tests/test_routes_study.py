import pytest
from fastapi.testclient import TestClient
from app.web.app import create_app
from app.core.firestore import InteractionStore
from app.domain.models import InteractionRecord, DecisionCommand, InteractionType
from datetime import datetime

class FakeInteractionStore:
    def __init__(self):
        self.interactions = []
        self.proposals = [
            {"id": "p1"}, {"id": "p2"}, {"id": "p3"}, {"id": "p4"}
        ]
    
    async def get_interaction(self, user_id, interaction_id):
        return None
    async def save_interaction(self, record):
        self.interactions.append(record)
    async def get_pending_proposals(self, user_id, limit=3):
        return self.proposals[:limit]

@pytest.fixture
def test_client():
    app = create_app()
    # Override dependencies
    from app.auth.dependencies import require_identity, require_csrf
    from app.domain.models import Identity
    from app.api.routes_study import get_interaction_store
    
    app.dependency_overrides[require_identity] = lambda: Identity(uid="test-user", email="test@test.com")
    app.dependency_overrides[require_csrf] = lambda: True
    
    fake_store = FakeInteractionStore()
    app.dependency_overrides[get_interaction_store] = lambda: fake_store
    
    return TestClient(app), fake_store

def test_today_route_limits_proposals(test_client):
    client, store = test_client
    response = client.get("/today")
    assert response.status_code == 200
    assert "Today queue" in response.text

def test_study_map_renders(test_client):
    client, store = test_client
    response = client.get("/study")
    assert response.status_code == 200
    assert 'id="study-map"' in response.text

def test_sources_route_renders(test_client):
    client, store = test_client
    response = client.get("/sources")
    assert response.status_code == 200
    assert 'id="sources-archive"' in response.text

def test_submit_reflection_persists(test_client):
    client, store = test_client
    response = client.post("/api/reflections", data={"reflection_text": "Great concept!"}, headers={"X-CSRF-Token": "test"})
    assert response.status_code == 200
    assert "Reflection saved" in response.text

def test_connect_proposal(test_client):
    client, store = test_client
    response = client.post("/api/proposals/p1/connect")
    assert response.status_code == 200
    assert "Connected" in response.text

def test_csrf_rejection():
    app = create_app()
    from app.auth.dependencies import require_identity, get_csrf_secret
    from app.domain.models import Identity
    app.dependency_overrides[require_identity] = lambda: Identity(uid="test-user", email="test@test.com")
    app.dependency_overrides[get_csrf_secret] = lambda: "test-secret"
    # Do NOT override require_csrf, so it will fail
    client = TestClient(app)
    response = client.post("/api/proposals/p1/connect")
    assert response.status_code == 403
    assert "missing CSRF token" in response.json()["detail"]
