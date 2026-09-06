import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.web.app import create_app
from app.auth.dependencies import require_identity, require_csrf
from app.domain.models import Identity

os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["CSRF_SECRET"] = "test-secret"
os.environ["ALLOWLISTED_EMAIL"] = "test@example.com"
app = create_app()

app.dependency_overrides[require_identity] = lambda: Identity(uid="test-user", email="test@example.com")
# Mock require_csrf for the accepted test
app.dependency_overrides[require_csrf] = lambda: True

@pytest.mark.asyncio
async def test_poll_feeds_reports_unavailable_until_durable_pipeline_exists():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/poll-feeds",
            headers={"X-CSRF-Token": "test-token"},
            cookies={"session": "test-session"}
        )
        assert response.status_code == 501
        assert response.json()["status"] == "unavailable"

@pytest.mark.asyncio
async def test_poll_feeds_forbidden_no_csrf():
    # Remove the csrf override to test real rejection
    app.dependency_overrides.pop(require_csrf, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/poll-feeds", cookies={"session": "test-session"})
        assert response.status_code == 403

    # Restore it in case other tests run
    app.dependency_overrides[require_csrf] = lambda: True
