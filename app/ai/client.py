import logging
from typing import Optional
from google import genai
from app.settings import Settings

logger = logging.getLogger(__name__)

def get_genai_client(settings: Optional[Settings] = None) -> genai.Client:
    """
    Returns an authenticated Google GenAI client.
    Prefers Vertex AI (Option A) using GCP credentials and project,
    with fallback to Google AI Studio API key if explicitly provided.
    """
    if settings is None:
        try:
            settings = Settings()
        except Exception:
            settings = None

    if settings and settings.GEMINI_API_KEY and settings.GEMINI_API_KEY not in ("mock-api-key", ""):
        logger.info("Initializing Google GenAI client via AI Studio API key")
        return genai.Client(api_key=settings.GEMINI_API_KEY)

    if settings and settings.GCP_PROJECT_ID:
        logger.info(
            f"Initializing Google GenAI client via Vertex AI on project '{settings.GCP_PROJECT_ID}' "
            f"in region '{getattr(settings, 'GCP_LOCATION', 'us-central1')}'"
        )
        return genai.Client(
            vertexai=True,
            project=settings.GCP_PROJECT_ID,
            location=getattr(settings, "GCP_LOCATION", "us-central1"),
        )

    return genai.Client()
