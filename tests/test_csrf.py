import pytest
from fastapi import FastAPI, Depends, Response, Header
from fastapi.testclient import TestClient
import hmac
import hashlib

from app.domain.models import Identity, ForbiddenError
from app.auth.dependencies import require_csrf, get_csrf_secret, require_identity
from app.web.csrf import generate_csrf_token

app = FastAPI()

def mock_require_identity():
    return Identity(uid="owner", email="owner@example.com")

def override_get_csrf_secret():
    return "test_secret"

app.dependency_overrides[require_identity] = mock_require_identity
app.dependency_overrides[get_csrf_secret] = override_get_csrf_secret

@app.post("/api/mutate")
def mutation_route(identity: Identity = Depends(mock_require_identity), csrf_ok: bool = Depends(require_csrf)):
    return {"status": "mutated"}

client = TestClient(app)

def test_mutation_rejected_without_csrf_token():
    response = client.post("/api/mutate")
    assert response.status_code == 403
    assert response.json()["detail"] == "missing CSRF token"

def test_mutation_rejected_with_invalid_csrf_token():
    client.cookies.set("csrf_nonce", "session-one")
    response = client.post("/api/mutate", headers={"X-CSRF-Token": "invalid_token"})
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid CSRF token"

def test_mutation_succeeds_with_valid_csrf_token():
    client.cookies.set("csrf_nonce", "session-one")
    valid_token = generate_csrf_token("owner", "session-one", "test_secret")
    response = client.post("/api/mutate", headers={"X-CSRF-Token": valid_token})
    assert response.status_code == 200
    assert response.json()["status"] == "mutated"

def test_csrf_token_is_session_bound():
    client.cookies.set("csrf_nonce", "session-one")
    valid_token_for_other = generate_csrf_token("owner", "session-two", "test_secret")
    response = client.post("/api/mutate", headers={"X-CSRF-Token": valid_token_for_other})
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid CSRF token"
