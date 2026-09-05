from fastapi.testclient import TestClient

from app.web.app import create_app


def test_healthz_returns_only_readiness_status() -> None:
    response = TestClient(create_app()).get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
