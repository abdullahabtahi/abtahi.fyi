import logging
from google import genai
from google.genai import errors

logger = logging.getLogger(__name__)

# Fallback ladder ordered by availability and latency
MODEL_FALLBACK_LADDER = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.7-flash",
]

RECOVERABLE_STATUS_CODES = {503, 429, 404, 500}

async def generate_content_with_fallback(
    client: genai.Client,
    contents: str | list,
    config: dict | None = None,
) -> genai.types.GenerateContentResponse:
    last_error = None
    for model_name in MODEL_FALLBACK_LADDER:
        try:
            logger.info(f"Attempting generation with model: {model_name}")
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            return response
        except errors.APIError as e:
            last_error = e
            if e.code in RECOVERABLE_STATUS_CODES:
                logger.warning(f"Model {model_name} failed with code {e.code}. Retrying next model...")
                continue
            raise e
        except Exception as e:
            last_error = e
            logger.warning(f"Unexpected error with {model_name}: {e}. Retrying next model...")
            continue

    raise RuntimeError(f"All models in fallback ladder exhausted. Last error: {last_error}")
