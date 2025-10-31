"""
Fallback configuration with hardcoded API keys.
These keys will be used when environment variables are not available.
"""

import logging

logger = logging.getLogger(__name__)

# Hardcoded fallback API keys
# Note: These are real API keys from environment variables for fallback usage.
FALLBACK_API_KEYS = {
    "GROQ_API_KEY": "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",
    "GEMINI_API_KEY": "AIzaSyCBxulB71lOeo7gX_E6Z4cTq9S42u_hJ8c", 
    "OPENAI_API_KEY": "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",
    "OPENROUTER_API_KEY": "sk-or-placeholder_openrouter_api_key_for_fallback_usage_only"  # No key found in env
}

# Fallback model configurations
FALLBACK_MODELS = {
    "groq": {
        "default_model": "groq-mixtral-8x7b",
        "available_models": [
            "groq-mixtral-8x7b",
            "groq-llama-3.1-8b-instant", 
            "groq-llama-3.3-70b-versatile",
            "groq-qwen/qwen3-32b",
            "groq-openai/gpt-oss-120b"
        ]
    },
    "gemini": {
        "default_model": "gemini-2.5-flash",
        "available_models": [
            "gemini-2.5-flash",
            "gemini-2.5-pro"
        ]
    },
    "openai": {
        "default_model": "gpt-4",
        "available_models": [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-3.5-turbo"
        ]
    },
    "openrouter": {
        "default_model": "openai/gpt-4",
        "available_models": [
            "openai/gpt-4",
            "anthropic/claude-3-sonnet",
            "meta-llama/llama-3.1-8b-instruct"
        ]
    }
}

def get_fallback_api_key(provider: str) -> str:
    """
    Get fallback API key for a specific provider.
    
    Args:
        provider: The provider name (groq, gemini, openai, openrouter)
        
    Returns:
        Fallback API key for the provider
        
    Raises:
        ValueError: If provider is not supported
    """
    provider_key_map = {
        "groq": "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY", 
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY"
    }
    
    if provider not in provider_key_map:
        raise ValueError(f"Unsupported provider: {provider}")
        
    key_name = provider_key_map[provider]
    fallback_key = FALLBACK_API_KEYS.get(key_name)
    
    if fallback_key:
        logger.warning(f"🔑 Using fallback API key for {provider.upper()} provider")
        
    return fallback_key

def get_fallback_model(provider: str) -> str:
    """
    Get default fallback model for a specific provider.
    
    Args:
        provider: The provider name (groq, gemini, openai, openrouter)
        
    Returns:
        Default model for the provider
        
    Raises:
        ValueError: If provider is not supported
    """
    if provider not in FALLBACK_MODELS:
        raise ValueError(f"Unsupported provider: {provider}")
        
    return FALLBACK_MODELS[provider]["default_model"]

def is_fallback_key(api_key: str) -> bool:
    """
    Check if the provided API key is a fallback key.
    
    Args:
        api_key: The API key to check
        
    Returns:
        True if it's a fallback key, False otherwise
    """
    return api_key in FALLBACK_API_KEYS.values()