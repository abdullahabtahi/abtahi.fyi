import pytest
from fastapi.testclient import TestClient
from app.web.app import create_app
from app.auth.dependencies import get_workload_verifier
from app.settings import Settings

class FakeWorkloadVerifier:
    def __init__(self, valid_tokens: dict[str, dict] = None):
        self.valid_tokens = valid_tokens or {}

    def verify_workload_token(self, token: str, expected_audience: str, expected_principal: str) -> dict:
        if token not in self.valid_tokens:
            raise ValueError("Invalid workload token")
        claims = self.valid_tokens[token]
        if expected_audience and claims.get("aud") != expected_audience:
            raise ValueError("Audience mismatch")
        if expected_principal and claims.get("email") != expected_principal:
            raise ValueError("Principal mismatch")
        return claims

@pytest.fixture
def app_with_verifier(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("ALLOWLISTED_EMAIL", "learner@example.com")
    monkeypatch.setenv("CSRF_SECRET", "test-csrf-secret")
    monkeypatch.setenv("SCHEDULER_SERVICE_ACCOUNT", "scheduler@test-project.iam.gserviceaccount.com")
    monkeypatch.setenv("SCHEDULER_AUDIENCE", "https://test-service.run.app")
    
    app = create_app(initialize=lambda: None)
    return app

def test_unauthenticated_request_to_privileged_route_is_denied(app_with_verifier):
    client = TestClient(app_with_verifier)
    resp = client.post("/api/poll-feeds")
    assert resp.status_code == 403

def test_learner_cookie_cannot_invoke_privileged_route(app_with_verifier):
    client = TestClient(app_with_verifier)
    client.cookies.set("session", "learner-session-cookie")
    resp = client.post("/api/poll-feeds")
    assert resp.status_code == 403

def test_valid_oidc_workload_token_is_accepted(app_with_verifier):
    fake_verifier = FakeWorkloadVerifier({
        "valid-oidc-token": {
            "email": "scheduler@test-project.iam.gserviceaccount.com",
            "aud": "https://test-service.run.app",
            "iss": "https://accounts.google.com",
        }
    })
    app_with_verifier.dependency_overrides[get_workload_verifier] = lambda: fake_verifier
    client = TestClient(app_with_verifier)
    resp = client.post(
        "/api/poll-feeds",
        headers={"Authorization": "Bearer valid-oidc-token"}
    )
    # Status should not be 403
    assert resp.status_code != 403

def test_wrong_principal_is_denied(app_with_verifier):
    fake_verifier = FakeWorkloadVerifier({
        "wrong-principal-token": {
            "email": "wrong-actor@iam.gserviceaccount.com",
            "aud": "https://test-service.run.app",
            "iss": "https://accounts.google.com",
        }
    })
    app_with_verifier.dependency_overrides[get_workload_verifier] = lambda: fake_verifier
    client = TestClient(app_with_verifier)
    resp = client.post(
        "/api/poll-feeds",
        headers={"Authorization": "Bearer wrong-principal-token"}
    )
    assert resp.status_code == 403

def test_wrong_audience_is_denied(app_with_verifier):
    fake_verifier = FakeWorkloadVerifier({
        "wrong-aud-token": {
            "email": "scheduler@test-project.iam.gserviceaccount.com",
            "aud": "https://wrong-service.run.app",
            "iss": "https://accounts.google.com",
        }
    })
    app_with_verifier.dependency_overrides[get_workload_verifier] = lambda: fake_verifier
    client = TestClient(app_with_verifier)
    resp = client.post(
        "/api/poll-feeds",
        headers={"Authorization": "Bearer wrong-aud-token"}
    )
    assert resp.status_code == 403
