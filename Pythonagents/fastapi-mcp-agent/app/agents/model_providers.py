"""
Python equivalent of the TypeScript model-providers.ts
Handles model selection and initialization for different LLM providers.
"""

import os
import logging
from typing import Optional, Any
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

# Import fallback configuration
from app.config.fallback_config import get_fallback_api_key, is_fallback_key

logger = logging.getLogger(__name__)

# Model ID to actual model name mapping
def get_model_name(model_id: str) -> str:
    """Map model IDs to actual model names."""
    model_mappings = {
        'groq-mixtral-8x7b': 'mixtral-8x7b-32768',
        'groq-llama-3.1-8b-instant': 'llama-3.1-8b-instant',
        'groq-llama-3.3-70b-versatile': 'llama-3.3-70b-versatile',
        'groq-qwen/qwen3-32b': "qwen/qwen3-32b",
        'gemini-2.5-flash': 'gemini-2.5-flash',
        'gemini-2.5-pro': 'gemini-2.5-pro',
        "groq-openai/gpt-oss-120b": "openai/gpt-oss-120b",
        "groq-moonshotai/kimi-k2-instruct-0905": "moonshotai/kimi-k2-instruct-0905"
    }
    return model_mappings.get(model_id, model_id)

def create_llm(model: Optional[str] = None, streaming: bool = False, api_keys: Optional[dict] = None) -> Any:
    """
    Initialize the LLM model with provider selection.

    Args:
        model: Model identifier (e.g., 'groq-mixtral-8x7b', 'gemini-2.5-pro', 'gpt-4')
        streaming: Whether to enable streaming responses
        api_keys: Optional dict of API keys from frontend (e.g., {'groq': 'key', 'openai': 'key'})

    Returns:
        Configured LLM instance

    Raises:
        ValueError: If model is not specified or API keys are not configured
    """
    logger.info(f"🔧 create_llm called with model: '{model}', api_keys provided: {bool(api_keys)}")

    # Require explicit model specification - no default fallback
    if not model:
        raise ValueError('Model must be explicitly specified. No default fallback available.')

    # Get API keys from environment, with fallback to hardcoded keys
    env_groq_key = os.getenv("GROQ_API_KEY")
    env_gemini_key = os.getenv("GEMINI_API_KEY")
    env_openai_key = os.getenv("OPENAI_API_KEY")
    env_openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    logger.info(f"🔍 Environment keys - Groq: {'SET' if env_groq_key else 'NOT SET'}, Gemini: {'SET' if env_gemini_key else 'NOT SET'}, OpenAI: {'SET' if env_openai_key else 'NOT SET'}, OpenRouter: {'SET' if env_openrouter_key else 'NOT SET'}")
    
    # Use API keys from request if provided, otherwise fall back to environment/fallback
    if api_keys:
        groq_api_key = api_keys.get("groq") or env_groq_key or get_fallback_api_key("groq")
        gemini_api_key = api_keys.get("gemini") or env_gemini_key or get_fallback_api_key("gemini")
        openai_api_key = api_keys.get("openai") or env_openai_key or get_fallback_api_key("openai")
        openrouter_api_key = api_keys.get("openrouter") or env_openrouter_key or get_fallback_api_key("openrouter")
        logger.info(f"🔑 Using API keys from request for available providers")
    else:
        groq_api_key = env_groq_key or get_fallback_api_key("groq")
        gemini_api_key = env_gemini_key or get_fallback_api_key("gemini")
        openai_api_key = env_openai_key or get_fallback_api_key("openai")
        openrouter_api_key = env_openrouter_key or get_fallback_api_key("openrouter")
    
    logger.info(f"🔑 Final keys - Groq: {groq_api_key[:10]}..., Gemini: {gemini_api_key[:10]}..., OpenAI: {openai_api_key[:10]}..., OpenRouter: {openrouter_api_key[:10]}...")

    # Try Groq first
    if model.startswith('groq-') and groq_api_key:
        actual_model = get_model_name(model)
        fallback_status = " (using fallback key)" if is_fallback_key(groq_api_key) else ""
        logger.info(f'⚡ Using Groq API - Model: {actual_model}{fallback_status}')
        return ChatGroq(
            api_key=groq_api_key,
            model=actual_model,
            temperature=0.1,  # Lower temperature for more deterministic tool usage
           
        )

    # Try Gemini
    elif model.startswith('gemini-') and gemini_api_key:
        actual_model = get_model_name(model)
        fallback_status = " (using fallback key)" if is_fallback_key(gemini_api_key) else ""
        logger.info(f'🤖 Using Google Gemini API - Model: {actual_model}{fallback_status}')
        return ChatGoogleGenerativeAI(
            api_key=gemini_api_key,
            model=actual_model,
            temperature=0.1,  # Lower temperature for more deterministic tool usage
    
        )

    # Try OpenAI
    elif (model.startswith('gpt-') or 'openai' in model) and openai_api_key:
        actual_model = get_model_name(model)
        fallback_status = " (using fallback key)" if is_fallback_key(openai_api_key) else ""
        logger.info(f'🧠 Using OpenAI API - Model: {actual_model}{fallback_status}')
        api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        return ChatOpenAI(
            api_key=openai_api_key,
            base_url=api_base,
            model=actual_model,
            temperature=0.1,  # Lower temperature for more deterministic tool usage
        
        )

    # Try OpenRouter as fallback
    elif openrouter_api_key:
        fallback_status = " (using fallback key)" if is_fallback_key(openrouter_api_key) else ""
        logger.info(f'🔄 Using OpenRouter API - Model: {model}{fallback_status}')
        api_base = os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1")
        return ChatOpenAI(
            api_key=openrouter_api_key,
            base_url=api_base,
            model=model,
            temperature=0.1,  # Lower temperature for more deterministic tool usage
      
        )

    # No suitable provider found
    available_providers = []
    if groq_api_key:
        available_providers.append('Groq')
    if gemini_api_key:
        available_providers.append('Gemini')
    if openai_api_key:
        available_providers.append('OpenAI')
    if openrouter_api_key:
        available_providers.append('OpenRouter')

    providers_str = ' '.join(available_providers) if available_providers else 'None'
    raise ValueError(f'Model "{model}" not available or API key not configured. Available providers: {providers_str}')

# Global LLM instance - must be initialized with create_llm(model)
llm: Optional[Any] = None