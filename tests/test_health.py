from fastapi.testclient import TestClient
from app.web.app import create_app

def test_healthz_returns_only_readiness_status() -> None:
    with TestClient(create_app()) as client:
        for path in ["/healthz", "/health"]:
            response = client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

def test_healthz_returns_unavailable_when_unready() -> None:
    def failing_init():
        raise RuntimeError("Initialization failure")

    app = create_app(initialize=failing_init)
    with TestClient(app) as client:
        for path in ["/healthz", "/health"]:
            response = client.get(path)
            assert response.status_code == 503
            assert response.json() == {"status": "unavailable"}

