import pytest
from httpx import AsyncClient, ASGITransport
from app.web.app import create_app
import os
os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["CSRF_SECRET"] = "test-secret"
os.environ["ALLOWLISTED_EMAIL"] = "test@example.com"
app = create_app()

@pytest.mark.asyncio
async def test_poll_feeds_accepted():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/poll-feeds",
            headers={"X-CSRF-Token": "test-token"},
            cookies={"csrf_token": "test-token"}
        )
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"

@pytest.mark.asyncio
async def test_poll_feeds_forbidden_no_csrf():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/poll-feeds")
        assert response.status_code == 403
