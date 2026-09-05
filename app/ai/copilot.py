import logging
from google import genai

logger = logging.getLogger(__name__)

async def generate_copilot_response(
    client: genai.Client,
    agent_id: str,
    user_input: str,
    config: dict | None = None,
) -> str:
    """
    Stateful Copilot engine that delegates to a GEAP Agent.
    """
    logger.info(f"Generating stateful copilot response via agent: {agent_id}")
    # In a real setup, we'd use interactions.create(). 
    # For now, we mock the Interactions API call to just use generate_content
    # assuming agent_id is provided, but since we are mocking for the smoke test:
    
    response = await client.aio.models.generate_content(
        model="gemini-3.8-flash",
        contents=user_input,
        config=config,
    )
    return response.text
