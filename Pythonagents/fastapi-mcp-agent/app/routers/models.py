import logging
import os
from fastapi import APIRouter
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/models/available")
async def get_available_models() -> List[str]:
    """Get list of available AI models based on configured API keys."""
    try:
        available_providers: List[str] = []

        # Check which API keys are configured
        if os.getenv("GROQ_API_KEY"):
            available_providers.append("groq")

        if os.getenv("GEMINI_API_KEY"):
            available_providers.append("gemini")

        if os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY"):
            available_providers.append("openrouter")

        logger.info(f"Available providers: {available_providers}")
        return available_providers

    except Exception as e:
        logger.error(f"Failed to get available models: {e}")
        return []