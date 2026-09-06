import pytest
from unittest.mock import patch, MagicMock
from app.settings import Settings
from app.ai.client import get_genai_client

def test_get_genai_client_defaults_to_vertex_ai(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "spatial-cat-489006-a4")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with patch("app.ai.client.genai.Client") as mock_client_cls:
        settings = Settings(
            GCP_PROJECT_ID="spatial-cat-489006-a4",
            CSRF_SECRET="secret",
            ALLOWLISTED_EMAIL="test@example.com",
            GCP_LOCATION="us-central1",
            GEMINI_API_KEY=None,
        )
        client = get_genai_client(settings)
        mock_client_cls.assert_called_once_with(
            vertexai=True,
            project="spatial-cat-489006-a4",
            location="us-central1",
        )

def test_get_genai_client_uses_api_key_when_provided():
    with patch("app.ai.client.genai.Client") as mock_client_cls:
        settings = Settings(
            GCP_PROJECT_ID="spatial-cat-489006-a4",
            CSRF_SECRET="secret",
            ALLOWLISTED_EMAIL="test@example.com",
            GEMINI_API_KEY="test-real-api-key",
        )
        client = get_genai_client(settings)
        mock_client_cls.assert_called_once_with(
            api_key="test-real-api-key",
        )
