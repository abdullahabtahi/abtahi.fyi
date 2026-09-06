import pytest
from fastapi.testclient import TestClient
from app.web.app import create_app
from app.auth.dependencies import get_token_verifier, get_allowed_email
from app.domain.models import Identity

class FakeTokenVerifier:
    def __init__(self, claims=None):
        self.claims = claims or {"uid": "test-owner", "email": "abtahi@example.com", "email_verified": True}

    def verify_session_cookie(self, cookie: str, check_revoked: bool):
        return self.claims

def test_anonymous_header_has_no_signin_and_footer_has_signin():
    app = create_app(initialize=lambda: None)
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/")
    assert resp.status_code == 200

    # Header must NOT contain sign-in button
    # Split by <header> and </header>
    header_html = resp.text.split("<header")[1].split("</header>")[0]
    assert "Sign In" not in header_html
    assert "nav-signin-btn" not in header_html

    # Footer MUST contain sign-in button
    footer_html = resp.text.split("<footer")[1].split("</footer>")[0]
    assert "Sign In" in footer_html
    assert "footer-signin-btn" in footer_html
    assert "/sign-in" in footer_html

def test_authenticated_header_has_study_dropdown_and_signout():
    fake_verifier = FakeTokenVerifier()
    app = create_app(initialize=lambda: None)
    app.dependency_overrides[get_token_verifier] = lambda: fake_verifier
    app.dependency_overrides[get_allowed_email] = lambda: "abtahi@example.com"
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("session", "valid-test-cookie")

    resp = client.get("/")
    assert resp.status_code == 200

    header_html = resp.text.split("<header")[1].split("</header>")[0]
    assert "Study" in header_html
    assert "Study Map" in header_html
    assert "Today Queue" in header_html
    assert "Ingest Notes" in header_html
    assert "Sources Archive" in header_html
    assert "Sign Out" in header_html
    assert "abtahi@example.com" in header_html

    footer_html = resp.text.split("<footer")[1].split("</footer>")[0]
    assert "Sign Out" in footer_html
    assert "footer-signin-btn" not in footer_html

class InMemoryReviewStore:
    def __init__(self):
        self.proposals = []

    async def get_pending_proposals(self, uid, limit=3):
        return self.proposals

def test_study_pages_render_unified_subnav():
    from app.api.routes_study import get_review_store
    fake_verifier = FakeTokenVerifier()
    app = create_app(initialize=lambda: None)
    app.dependency_overrides[get_token_verifier] = lambda: fake_verifier
    app.dependency_overrides[get_allowed_email] = lambda: "abtahi@example.com"
    app.dependency_overrides[get_review_store] = lambda: InMemoryReviewStore()
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("session", "valid-test-cookie")

    # 1. /study
    resp_study = client.get("/study")
    assert resp_study.status_code == 200
    assert 'aria-label="Study Workspace Navigation"' in resp_study.text
    assert 'href="/study"' in resp_study.text
    assert 'href="/today"' in resp_study.text
    assert 'href="/study/ingest"' in resp_study.text
    assert 'href="/sources"' in resp_study.text

    # 2. /today
    resp_today = client.get("/today")
    assert resp_today.status_code == 200
    assert 'aria-label="Study Workspace Navigation"' in resp_today.text
    assert "style=\"width:48px;height:48px;\"" in resp_today.text
    assert "style=\"width:24px;height:24px;\"" in resp_today.text
    assert "max-w-md" in resp_today.text

    # 3. /study/ingest
    resp_ingest = client.get("/study/ingest")
    assert resp_ingest.status_code == 200
    assert 'aria-label="Study Workspace Navigation"' in resp_ingest.text

    # 4. /sources
    resp_sources = client.get("/sources")
    assert resp_sources.status_code == 200
    assert 'aria-label="Study Workspace Navigation"' in resp_sources.text
