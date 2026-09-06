import pytest
from fastapi import FastAPI, Depends, Request, Response
from fastapi.testclient import TestClient

from app.domain.models import Identity, ForbiddenError
from app.auth.service import verify_allowlisted_identity
from app.auth.dependencies import require_identity, auth_router, auth_pages_router, get_token_verifier, get_allowed_email
from tests.conftest import FakeTokenVerifier

app = FastAPI()
app.include_router(auth_router)
app.include_router(auth_pages_router)

@app.get("/api/private")
def private_route(identity: Identity = Depends(require_identity)):
    return {"status": "ok", "uid": identity.uid}

# Setup overrides
def override_get_allowed_email():
    return "owner@example.com"

app.dependency_overrides[get_allowed_email] = override_get_allowed_email

@pytest.fixture
def test_app(fake_verifier):
    app.dependency_overrides[get_token_verifier] = lambda: fake_verifier
    yield app
    app.dependency_overrides.pop(get_token_verifier, None)

@pytest.fixture
def client(test_app):
    return TestClient(test_app, follow_redirects=False)

def test_rejects_verified_token_for_non_allowlisted_email(fake_verifier):
    fake_verifier.claims = {"uid": "other", "email": "other@example.com", "email_verified": True}
    with pytest.raises(ForbiddenError):
        verify_allowlisted_identity(fake_verifier, "fake_token", "owner@example.com")

def test_rejects_unverified_email(fake_verifier):
    fake_verifier.claims = {"uid": "owner", "email": "owner@example.com", "email_verified": False}
    with pytest.raises(ForbiddenError):
        verify_allowlisted_identity(fake_verifier, "fake_token", "owner@example.com")

def test_rejects_missing_session_cookie(client):
    response = client.get("/api/private")
    assert response.status_code == 303
    assert response.headers["Location"] == "/sign-in"

def test_session_exchange_sets_httponly_cookie(client, fake_verifier):
    fake_verifier.claims = {"uid": "owner", "email": "owner@example.com", "email_verified": True}
    response = client.post("/api/auth/session", json={"idToken": "fake_token"})
    assert response.status_code == 200
    assert "session=fake_cookie_for_fake_token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_session_exchange_uses_injected_allowlist(client, fake_verifier, monkeypatch):
    monkeypatch.setenv("ALLOWLISTED_EMAIL", "different@example.com")
    fake_verifier.claims = {
        "uid": "owner",
        "email": "owner@example.com",
        "email_verified": True,
    }

    response = client.post("/api/auth/session", json={"idToken": "fake_token"})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "claims",
    [
        {"uid": "owner", "email": "owner@example.com", "email_verified": False},
        {"uid": "other", "email": "other@example.com", "email_verified": True},
    ],
)
def test_session_exchange_rejects_invalid_identity_claims(client, fake_verifier, claims):
    fake_verifier.claims = claims

    response = client.post("/api/auth/session", json={"idToken": "fake_token"})

    assert response.status_code == 403
    assert response.json() == {"detail": "authentication failed"}
    assert "set-cookie" not in response.headers

def test_session_exchange_rejects_missing_token(client):
    response = client.post("/api/auth/session", json={})
    assert response.status_code == 422 # FastAPI validation error for missing field

def test_private_route_allows_valid_session(client, fake_verifier):
    fake_verifier.claims = {"uid": "owner", "email": "owner@example.com", "email_verified": True}
    client.cookies.set("session", "valid_cookie")
    response = client.get("/api/private")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "uid": "owner"}

def test_identity_uid_comes_from_session_not_request(client, fake_verifier):
    fake_verifier.claims = {"uid": "owner", "email": "owner@example.com", "email_verified": True}
    client.cookies.set("session", "valid_cookie")
    # Even if they try to pass something else, the backend derives from claims
    response = client.get("/api/private")
    assert response.json()["uid"] == "owner"


def test_sign_in_page_renders_cleanly(client):
    response = client.get("/sign-in")
    assert response.status_code == 200
    assert "The Learner" in response.text
    assert "Continue with Google" in response.text
    assert "firebaseConfig" in response.text


def test_sign_in_redirects_to_today_when_already_authenticated(client, fake_verifier):
    fake_verifier.claims = {"uid": "owner", "email": "owner@example.com", "email_verified": True}
    client.cookies.set("session", "valid_cookie")
    response = client.get("/sign-in")
    assert response.status_code == 303
    assert response.headers["Location"] == "/today"


def test_logout_api_clears_session_cookies(client):
    client.cookies.set("session", "valid_cookie")
    client.cookies.set("csrf_nonce", "valid_nonce")
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    set_cookies = response.headers.get_list("set-cookie") if hasattr(response.headers, "get_list") else [response.headers.get("set-cookie", "")]
    set_cookie_str = " ".join(set_cookies)
    assert 'session=""' in set_cookie_str or "session=;" in set_cookie_str or 'max-age=0' in set_cookie_str.lower()


def test_logout_get_redirects_to_timeline(client):
    client.cookies.set("session", "valid_cookie")
    response = client.get("/logout")
    assert response.status_code == 303
    assert response.headers["Location"] == "/"


def test_auth_client_config_endpoint(client):
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    data = response.json()
    assert "apiKey" in data
    assert "authDomain" in data
    assert "projectId" in data
    assert data["projectId"] == "spatial-cat-489006-a4"


def test_full_app_navbar_anonymous_vs_authenticated(fake_verifier):
    from app.web.app import create_app
    test_full_app = create_app(initialize=lambda: None)
    test_full_app.dependency_overrides[get_token_verifier] = lambda: fake_verifier
    test_full_app.dependency_overrides[get_allowed_email] = lambda: "owner@example.com"
    full_client = TestClient(test_full_app, follow_redirects=False)

    # Anonymous visitor sees "Sign In" button linking to /sign-in
    anon_resp = full_client.get("/")
    assert anon_resp.status_code == 200
    assert "/sign-in" in anon_resp.text
    assert "Sign In" in anon_resp.text
    assert "Sign Out" not in anon_resp.text

    # Authenticated learner sees "Study" and "Sign Out"
    fake_verifier.claims = {"uid": "owner", "email": "owner@example.com", "email_verified": True}
    full_client.cookies.set("session", "valid_cookie")
    auth_resp = full_client.get("/")
    assert auth_resp.status_code == 200
    assert "/today" in auth_resp.text
    assert "Study" in auth_resp.text
    assert "Sign Out" in auth_resp.text
