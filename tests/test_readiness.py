from fastapi.testclient import TestClient

from app.web.app import create_app


def test_healthz_is_unavailable_after_initialization_failure() -> None:
    def fail_initialization() -> None:
        raise RuntimeError("projection initialization failed")

    with TestClient(create_app(initialize=fail_initialization)) as client:
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
