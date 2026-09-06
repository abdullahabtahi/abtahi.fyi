from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import auth_router, get_allowed_email, get_csrf_secret, get_token_verifier
from tests.conftest import FakeTokenVerifier


def _client(verifier: FakeTokenVerifier) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    app.dependency_overrides[get_allowed_email] = lambda: "owner@example.com"
    app.dependency_overrides[get_csrf_secret] = lambda: "test-secret"
    return TestClient(app)


def test_session_exchange_uses_secure_companion_cookies() -> None:
    verifier = FakeTokenVerifier(
        {"uid": "owner", "email": "owner@example.com", "email_verified": True}
    )

    response = _client(verifier).post("/api/auth/session", json={"idToken": "token"})

    cookies = " ".join(response.headers.get_list("set-cookie")).lower()
    assert response.status_code == 200
    assert "session=fake_cookie_for_token" in cookies
    assert "csrf_nonce=" in cookies
    assert cookies.count("secure") == 2
    assert cookies.count("httponly") == 2
    assert cookies.count("samesite=lax") == 2


def test_session_exchange_hides_identity_verification_details() -> None:
    verifier = FakeTokenVerifier(
        {"uid": "other", "email": "other@example.com", "email_verified": True}
    )

    response = _client(verifier).post("/api/auth/session", json={"idToken": "token"})

    assert response.status_code == 403
    assert response.json() == {"detail": "authentication failed"}
    assert "allowlist" not in response.text.lower()
    assert "other@example.com" not in response.text


def test_sign_in_template_does_not_reveal_allowlist_rejection() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "app"
        / "templates"
        / "sign_in.html"
    )

    assert "Access Restricted:" not in template_path.read_text()
