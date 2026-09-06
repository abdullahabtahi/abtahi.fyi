from fastapi.testclient import TestClient

from app.web.app import create_app


def test_healthz_is_unavailable_after_initialization_failure() -> None:
    def fail_initialization() -> None:
        raise RuntimeError("projection initialization failed")

    with TestClient(create_app(initialize=fail_initialization)) as client:
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_create_app_surfaces_invalid_configuration_as_unavailable(monkeypatch) -> None:
    from app.settings import ConfigurationUnavailable

    monkeypatch.setattr(
        "app.web.app.Settings",
        lambda: (_ for _ in ()).throw(ConfigurationUnavailable("configuration is unavailable")),
    )

    with TestClient(create_app(initialize=lambda: None)) as client:
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
