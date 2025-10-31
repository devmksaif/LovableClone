#!/usr/bin/env python3
"""
Configuration for optimization settings and model selection strategies.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    name: str
    provider: str
    cost_per_token: float
    speed_rating: int  # 1-10, 10 being fastest
    quality_rating: int  # 1-10, 10 being highest quality
    context_window: int
    supports_tools: bool = True


@dataclass
class OptimizationConfig:
    """Configuration for optimization settings."""
    # Caching settings
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600  # 1 hour
    max_cache_size: int = 1000
    
    # Rate limiting settings
    enable_aggressive_rate_limiting: bool = True
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0
    
    # Request optimization
    enable_request_deduplication: bool = True
    enable_batch_tool_calls: bool = True
    max_parallel_tools: int = 3
    
    # Model selection
    enable_smart_model_selection: bool = True
    prefer_speed_over_quality: bool = False
    cost_threshold_per_request: float = 0.01  # Max cost per request in USD


# Available models with their characteristics
AVAILABLE_MODELS: Dict[str, ModelConfig] = {
    # Groq models (fast but rate limited)
    "groq-openai/gpt-oss-120b": ModelConfig(
        name="groq-openai/gpt-oss-120b",
        provider="groq",
        cost_per_token=0.0000005,  # Very cheap
        speed_rating=9,  # Very fast
        quality_rating=7,  # Good quality
        context_window=32768,
        supports_tools=True
    ),
    "groq/mixtral-8x7b-32768": ModelConfig(
        name="groq/mixtral-8x7b-32768",
        provider="groq",
        cost_per_token=0.0000007,
        speed_rating=9,
        quality_rating=8,
        context_window=32768,
        supports_tools=True
    ),
    
    # OpenAI models (reliable but more expensive)
    "openai/gpt-4o-mini": ModelConfig(
        name="openai/gpt-4o-mini",
        provider="openai",
        cost_per_token=0.00015,
        speed_rating=7,
        quality_rating=9,
        context_window=128000,
        supports_tools=True
    ),
    "openai/gpt-3.5-turbo": ModelConfig(
        name="openai/gpt-3.5-turbo",
        provider="openai",
        cost_per_token=0.0005,
        speed_rating=8,
        quality_rating=7,
        context_window=16384,
        supports_tools=True
    ),
    
    # Anthropic models (high quality)
    "anthropic/claude-3-haiku-20240307": ModelConfig(
        name="anthropic/claude-3-haiku-20240307",
        provider="anthropic",
        cost_per_token=0.00025,
        speed_rating=8,
        quality_rating=8,
        context_window=200000,
        supports_tools=True
    ),
}


# Task-specific model recommendations
TASK_MODEL_PREFERENCES: Dict[str, List[str]] = {
    "planning": [
        "groq-openai/gpt-oss-120b",  # Fast and good enough for planning
        "openai/gpt-3.5-turbo",
        "groq/mixtral-8x7b-32768"
    ],
    "code_generation": [
        "groq/mixtral-8x7b-32768",  # Good balance of speed and quality
        "openai/gpt-4o-mini",
        "anthropic/claude-3-haiku-20240307"
    ],
    "review": [
        "openai/gpt-4o-mini",  # Higher quality for review
        "anthropic/claude-3-haiku-20240307",
        "groq/mixtral-8x7b-32768"
    ],
    "general": [
        "groq-openai/gpt-oss-120b",
        "openai/gpt-3.5-turbo",
        "groq/mixtral-8x7b-32768"
    ]
}


# Provider fallback order when rate limited
PROVIDER_FALLBACK_ORDER: List[str] = [
    "groq",      # Try Groq first (fastest)
    "openai",    # Fallback to OpenAI
    "anthropic", # Final fallback to Anthropic
]


def get_optimal_model_for_task(
    task_type: str, 
    prefer_speed: bool = True,
    max_cost: Optional[float] = None,
    exclude_providers: Optional[List[str]] = None
) -> Optional[str]:
    """
    Get the optimal model for a specific task type.
    
    Args:
        task_type: Type of task (planning, code_generation, review, general)
        prefer_speed: Whether to prioritize speed over quality
        max_cost: Maximum cost per token allowed
        exclude_providers: List of providers to exclude (e.g., due to rate limiting)
    
    Returns:
        Model name or None if no suitable model found
    """
    exclude_providers = exclude_providers or []
    preferences = TASK_MODEL_PREFERENCES.get(task_type, TASK_MODEL_PREFERENCES["general"])
    
    for model_name in preferences:
        if model_name not in AVAILABLE_MODELS:
            continue
            
        model_config = AVAILABLE_MODELS[model_name]
        
        # Skip if provider is excluded
        if model_config.provider in exclude_providers:
            continue
            
        # Skip if cost is too high
        if max_cost and model_config.cost_per_token > max_cost:
            continue
            
        # For speed preference, prioritize fast models
        if prefer_speed and model_config.speed_rating >= 7:
            return model_name
            
        # For quality preference, prioritize high-quality models
        if not prefer_speed and model_config.quality_rating >= 8:
            return model_name
            
        # If no specific preference, return first available
        return model_name
    
    return None


def get_fallback_model(current_model: str, exclude_providers: Optional[List[str]] = None) -> Optional[str]:
    """
    Get a fallback model when the current model is rate limited.
    
    Args:
        current_model: The model that's currently rate limited
        exclude_providers: Additional providers to exclude
    
    Returns:
        Fallback model name or None
    """
    exclude_providers = exclude_providers or []
    
    # Add current model's provider to exclusion list
    if current_model in AVAILABLE_MODELS:
        current_provider = AVAILABLE_MODELS[current_model].provider
        exclude_providers = list(exclude_providers) + [current_provider]
    
    # Try to find a model from a different provider
    for provider in PROVIDER_FALLBACK_ORDER:
        if provider in exclude_providers:
            continue
            
        # Find the best model from this provider
        for model_name, config in AVAILABLE_MODELS.items():
            if config.provider == provider:
                return model_name
    
    return None


# Default optimization configuration
DEFAULT_OPTIMIZATION_CONFIG = OptimizationConfig(
    cache_enabled=True,
    cache_ttl_seconds=1800,  # 30 minutes
    max_cache_size=500,
    enable_aggressive_rate_limiting=True,
    backoff_multiplier=1.5,
    max_backoff_seconds=30.0,
    enable_request_deduplication=True,
    enable_batch_tool_calls=True,
    max_parallel_tools=2,  # Conservative for rate limiting
    enable_smart_model_selection=True,
    prefer_speed_over_quality=True,  # Prefer speed to avoid rate limits
    cost_threshold_per_request=0.005
)