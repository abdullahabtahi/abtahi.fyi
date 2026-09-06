import pytest
from fastapi.testclient import TestClient

from app.domain.models import Identity
from app.web.app import create_app


class InMemoryReviewStore:
    def __init__(self) -> None:
        self.operations = {}
        self.proposals = [{"id": f"p{i}", "title": f"Proposal {i}", "body": "Evidence"} for i in range(1, 5)]
        self.unavailable = False

    async def run_once(self, uid, key, digest, operation):
        if self.unavailable:
            from app.services.review import ReviewStoreUnavailable

            raise ReviewStoreUnavailable()
        saved = self.operations.get((uid, key))
        if saved is not None:
            if saved["digest"] != digest:
                from app.services.review import IdempotencyConflict

                raise IdempotencyConflict()
            return saved["result"]
        result = operation()
        self.operations[(uid, key)] = {"digest": digest, "result": result}
        return result

    async def get_operation(self, uid, key):
        saved = self.operations.get((uid, key))
        return saved["result"] if saved else None

    async def get_pending_proposals(self, uid, limit=3):
        return self.proposals[:limit]


@pytest.fixture
def test_client():
    from app.api.routes_study import get_review_store
    from app.auth.dependencies import require_csrf, require_identity

    app = create_app()
    app.dependency_overrides[require_identity] = lambda: Identity(
        uid="test-user", email="test@test.com"
    )
    app.dependency_overrides[require_csrf] = lambda: True
    store = InMemoryReviewStore()
    app.dependency_overrides[get_review_store] = lambda: store
    return TestClient(app), store

def test_today_route_limits_proposals(test_client):
    client, store = test_client
    response = client.get("/today")
    assert response.status_code == 200
    assert "Today queue" in response.text
    assert "Proposal 1" in response.text
    assert "Proposal 3" in response.text
    assert "Proposal 4" not in response.text
    assert "/api/proposals/p1/connect" in response.text

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

def test_submit_reflection_requires_idempotency_key(test_client):
    client, store = test_client
    response = client.post("/api/reflections", data={"reflection_text": "Great concept!"})
    assert response.status_code == 400


def test_source_revision_consent_is_private_csrf_protected_and_owner_scoped(test_client):
    from app.api.routes_study import get_consent_store

    class ConsentStore:
        def __init__(self) -> None:
            self.decisions = []

        async def append(self, decision):
            self.decisions.append(decision)

        async def latest(self, uid, revision_id, purpose, provider):
            return None

    client, _ = test_client
    store = ConsentStore()
    client.app.dependency_overrides[get_consent_store] = lambda: store

    response = client.post(
        "/api/source-revisions/revision-1/consent",
        data={"purpose": "proposal", "provider": "google-genai", "granted": "true"},
        headers={"Idempotency-Key": "consent-1"},
    )

    assert response.status_code == 200
    assert response.json()["granted"] is True
    assert store.decisions[0].uid == "test-user"


def test_connect_requires_idempotency_key(test_client):
    client, store = test_client
    response = client.post("/api/proposals/p1/connect")
    assert response.status_code == 400


def test_connect_reuses_saved_result_for_the_same_key(test_client):
    client, store = test_client
    headers = {"Idempotency-Key": "operation-1"}

    first = client.post(
        "/api/proposals/p1/connect", data={"reviewed_content": "Evidence"}, headers=headers
    )
    repeated = client.post(
        "/api/proposals/p1/connect", data={"reviewed_content": "Evidence"}, headers=headers
    )

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert "Connected" in repeated.text
    assert len(store.operations) == 1


def test_connect_requires_reviewed_content(test_client):
    client, _ = test_client

    response = client.post(
        "/api/proposals/p1/connect",
        headers={"Idempotency-Key": "operation-1"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "reviewed_content is required"


def test_defer_returns_truthful_saved_outcome(test_client):
    client, store = test_client

    response = client.post(
        "/api/proposals/p1/defer",
        data={"defer_window": "TOMORROW"},
        headers={"Idempotency-Key": "operation-1"},
    )

    assert response.status_code == 200
    assert "Deferred" in response.text


def test_defer_requires_a_valid_window(test_client):
    client, _ = test_client

    response = client.post(
        "/api/proposals/p1/defer",
        data={"defer_window": "NOT_A_WINDOW"},
        headers={"Idempotency-Key": "operation-1"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "defer_window is required"


def test_undo_route_is_available(test_client):
    client, _ = test_client

    response = client.post(
        "/api/proposals/p1/undo",
        data={"dismissal_operation_id": "dismiss-1"},
        headers={"Idempotency-Key": "operation-2"},
    )

    assert response.status_code != 404


def test_dismiss_result_includes_csrf_protected_undo_control(test_client):
    client, _ = test_client

    response = client.post(
        "/api/proposals/p1/dismiss", headers={"Idempotency-Key": "dismiss-1"}
    )

    assert response.status_code == 200
    assert 'hx-post="/api/proposals/p1/undo"' in response.text
    assert "dismissal_operation_id" in response.text
    assert "X-CSRF-Token" in response.text


def test_store_failure_returns_retryable_response_not_success(test_client):
    client, store = test_client
    store.unavailable = True

    response = client.post(
        "/api/proposals/p1/connect",
        data={"reviewed_content": "Evidence"},
        headers={"Idempotency-Key": "operation-1"},
    )

    assert response.status_code == 503
    assert "Connected" not in response.text
    assert "Retry" in response.text
    assert "operation-1" in response.text

def test_csrf_rejection():
    app = create_app()
    from app.auth.dependencies import require_identity, get_csrf_secret
    from app.domain.models import Identity
    app.dependency_overrides[require_identity] = lambda: Identity(uid="test-user", email="test@test.com")
    app.dependency_overrides[get_csrf_secret] = lambda: "test-secret"
    # Do NOT override require_csrf, so it will fail
    client = TestClient(app)
    response = client.post(
        "/api/proposals/p1/connect", headers={"Idempotency-Key": "operation-1"}
    )
    assert response.status_code == 403
    assert "missing CSRF token" in response.json()["detail"]
