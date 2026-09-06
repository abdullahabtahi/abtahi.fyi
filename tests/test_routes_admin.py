import os
from unittest.mock import AsyncMock
import pytest
from httpx import AsyncClient, ASGITransport
from app.web.app import create_app
from app.auth.dependencies import require_identity, require_csrf, require_job_identity
from app.domain.models import Identity

os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["CSRF_SECRET"] = "test-secret"
os.environ["ALLOWLISTED_EMAIL"] = "test@example.com"
app = create_app()

app.dependency_overrides[require_identity] = lambda: Identity(uid="test-user", email="test@example.com")
# Mock require_csrf for the accepted test
app.dependency_overrides[require_csrf] = lambda: True

@pytest.mark.asyncio
async def test_polling_route_requires_privileged_job_identity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            "/api/poll-feeds",
            headers={"X-CSRF-Token": "test-token"},
            cookies={"session": "test-session"}
        )
        assert response.status_code == 403

@pytest.mark.asyncio
async def test_polling_route_accepts_only_privileged_job_identity():
    from app.routers.admin import get_ingestion_service

    service = AsyncMock()
    service.collect_registered_feeds.return_value = {"completed": 1, "skipped": 0, "failed": 0}
    app.dependency_overrides[require_job_identity] = lambda: True
    app.dependency_overrides[get_ingestion_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/poll-feeds")
        assert response.status_code == 200
        assert response.json()["completed"] == 1

    app.dependency_overrides.pop(require_job_identity, None)
    app.dependency_overrides.pop(get_ingestion_service, None)
