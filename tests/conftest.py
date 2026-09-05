import pytest
from typing import Dict, Any

class FakeTokenVerifier:
    def __init__(self, claims: Dict[str, Any] = None):
        self.claims = claims or {}
        self.created_cookies = []
        self.should_fail_create = False
        self.should_fail_verify = False

    def create_session_cookie(self, id_token: str, expires_in) -> str:
        if self.should_fail_create:
            raise ValueError("Failed to create cookie")
        cookie = f"fake_cookie_for_{id_token}"
        self.created_cookies.append(cookie)
        return cookie

    def verify_session_cookie(self, cookie: str, check_revoked: bool) -> dict:
        if self.should_fail_verify:
            raise ValueError("Invalid cookie")
        return self.claims

@pytest.fixture
def fake_verifier():
    return FakeTokenVerifier()

@pytest.fixture(autouse=True)
def setup_test_env():
    import os
    os.environ.setdefault("GCP_PROJECT_ID", "test-project")
    os.environ.setdefault("CSRF_SECRET", "test-secret")
    os.environ.setdefault("ALLOWLISTED_EMAIL", "owner@example.com")
