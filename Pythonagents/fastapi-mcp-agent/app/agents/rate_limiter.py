#!/usr/bin/env python3
"""
Rate limiting utilities for LLM API calls and tool executions.
Prevents excessive requests that could lead to rate limiting or API errors.
"""

import asyncio
import time
import logging
import hashlib
from typing import Dict, Any, Optional, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class Provider(Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    GEMINI = "gemini"
    OLLAMA = "ollama"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting per provider."""
    requests_per_minute: int
    requests_per_hour: int
    burst_limit: int = 5  # Allow burst of requests
    cooldown_seconds: float = 1.0  # Minimum delay between requests


class RateLimiter:
    """Advanced rate limiter with provider-specific limits and queuing."""

    def __init__(self):
        # Provider-specific rate limit configurations
        self.provider_configs = {
            Provider.OPENAI: RateLimitConfig(
                requests_per_minute=50,  # Conservative limit
                requests_per_hour=1000,
                burst_limit=3,
                cooldown_seconds=1.0
            ),
            Provider.ANTHROPIC: RateLimitConfig(
                requests_per_minute=50,
                requests_per_hour=1000,
                burst_limit=3,
                cooldown_seconds=1.0
            ),
            Provider.GROQ: RateLimitConfig(
                requests_per_minute=5,   # More conservative for Groq to avoid token limits
                requests_per_hour=50,    # Much more conservative hourly limit
                burst_limit=1,           # No burst for Groq
                cooldown_seconds=12.0    # Longer cooldown between requests
            ),
            Provider.GEMINI: RateLimitConfig(
                requests_per_minute=60,
                requests_per_hour=1000,
                burst_limit=5,
                cooldown_seconds=0.5
            ),
            Provider.OLLAMA: RateLimitConfig(
                requests_per_minute=100,  # Local model, less restrictive
                requests_per_hour=5000,
                burst_limit=10,
                cooldown_seconds=0.1
            ),
        }

        # Tracking state per provider
        self.request_history: Dict[Provider, list] = {provider: [] for provider in Provider}
        self.active_requests: Dict[Provider, int] = {provider: 0 for provider in Provider}
        self.last_request_time: Dict[Provider, float] = {provider: 0.0 for provider in Provider}

        # Global limits
        self.global_requests_per_minute = 100
        self.global_request_history: list = []
        self.global_active_requests = 0

        # Queues for pending requests
        self.request_queues: Dict[Provider, asyncio.Queue] = {provider: asyncio.Queue() for provider in Provider}

        # Background cleanup task (created lazily)
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Exponential backoff tracking
        self.backoff_delays: Dict[Provider, float] = {provider: 0.0 for provider in Provider}
        self.consecutive_failures: Dict[Provider, int] = {provider: 0 for provider in Provider}

        # Token bucket for more precise rate limiting
        self.token_buckets: Dict[Provider, Dict[str, Any]] = {}
        for provider in Provider:
            config = self.provider_configs[provider]
            self.token_buckets[provider] = {
                "tokens": config.requests_per_minute,  # Start with full bucket
                "max_tokens": config.requests_per_minute,
                "refill_rate": config.requests_per_minute / 60.0,  # tokens per second
                "last_refill": time.time()
            }

        # Response caching
        self.response_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = 300  # 5 minutes default TTL

    def get_provider_from_model(self, model_name: str) -> Provider:
        """Determine provider from model name."""
        model_lower = model_name.lower()

        if "gpt" in model_lower or "openai" in model_lower:
            return Provider.OPENAI
        elif "claude" in model_lower or "anthropic" in model_lower:
            return Provider.ANTHROPIC
        elif "groq" in model_lower or "mixtral" in model_lower:
            return Provider.GROQ
        elif "gemini" in model_lower or "google" in model_lower:
            return Provider.GEMINI
        elif "ollama" in model_lower or "llama" in model_lower:
            return Provider.OLLAMA
        else:
            # Default to OpenAI for unknown models
            return Provider.OPENAI

    async def _cleanup_old_requests(self):
        """Background task to clean up old request timestamps."""
        while True:
            try:
                current_time = time.time()

                # Clean up per-provider histories (older than 1 hour)
                for provider in Provider:
                    cutoff_time = current_time - 3600  # 1 hour ago
                    self.request_history[provider] = [
                        timestamp for timestamp in self.request_history[provider]
                        if timestamp > cutoff_time
                    ]

                # Clean up global history
                self.global_request_history = [
                    timestamp for timestamp in self.global_request_history
                    if timestamp > cutoff_time
                ]

                # Clear expired cache entries
                self.clear_expired_cache()

                await asyncio.sleep(60)  # Clean up every minute

            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")
                await asyncio.sleep(60)

    def _refill_token_bucket(self, provider: Provider):
        """Refill tokens in the bucket based on time elapsed."""
        bucket = self.token_buckets[provider]
        now = time.time()
        elapsed = now - bucket["last_refill"]

        # Add tokens based on refill rate
        tokens_to_add = elapsed * bucket["refill_rate"]
        bucket["tokens"] = min(bucket["max_tokens"], bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now

    def _consume_token(self, provider: Provider) -> bool:
        """Try to consume a token. Returns True if successful."""
        self._refill_token_bucket(provider)
        bucket = self.token_buckets[provider]

        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        return False

    def get_cache_key(self, input_text: str, model_name: str, user_id: str = "anonymous") -> str:
        """Generate a unique cache key for the request."""
        content = f"{user_id}:{model_name}:{input_text[:500]}"  # Limit input length
        return hashlib.md5(content.encode()).hexdigest()

    def get_cached_response(self, cache_key: str) -> Optional[Any]:
        """Retrieve a cached response if it exists and is valid."""
        if cache_key in self.response_cache:
            cached_data = self.response_cache[cache_key]
            if time.time() - cached_data["timestamp"] < self.cache_ttl:
                logger.debug(f"Cache hit for key: {cache_key[:8]}...")
                return cached_data["response"]
            else:
                # Expired, remove it
                del self.response_cache[cache_key]
        return None

    def cache_response(self, cache_key: str, response: Any):
        """Cache a response."""
        self.response_cache[cache_key] = {
            "response": response,
            "timestamp": time.time()
        }
        logger.debug(f"Cached response for key: {cache_key[:8]}...")

    def clear_expired_cache(self):
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, data in self.response_cache.items()
            if current_time - data["timestamp"] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.response_cache[key]
        if expired_keys:
            logger.debug(f"Cleared {len(expired_keys)} expired cache entries")

    def _check_rate_limits(self, provider: Provider) -> tuple[bool, float]:
        """
        Check if a request can be made using token bucket algorithm.
        Returns (can_proceed, wait_seconds).
        """
        current_time = time.time()
        config = self.provider_configs[provider]

        # Check cooldown
        time_since_last_request = current_time - self.last_request_time[provider]
        if time_since_last_request < config.cooldown_seconds:
            wait_time = config.cooldown_seconds - time_since_last_request
            return False, wait_time

        # Check token bucket
        if not self._consume_token(provider):
            # Calculate wait time for next token
            bucket = self.token_buckets[provider]
            tokens_needed = 1 - bucket["tokens"]
            wait_time = tokens_needed / bucket["refill_rate"]
            return False, min(wait_time, 60.0)  # Cap at 60 seconds

        # Check burst limit (active requests)
        if self.active_requests[provider] >= config.burst_limit:
            return False, config.cooldown_seconds

        # Check global limits
        global_minute_ago = current_time - 60
        global_recent = [t for t in self.global_request_history if t > global_minute_ago]
        if len(global_recent) >= self.global_requests_per_minute:
            oldest_global = min(global_recent)
            wait_time = 60 - (current_time - oldest_global)
            return False, max(wait_time, 1.0)

        if self.global_active_requests >= 20:  # Global burst limit
            return False, 1.0

        return True, 0.0

    def record_success(self, model_name: str) -> None:
        """Record a successful request to reset backoff."""
        provider = self.get_provider_from_model(model_name)
        self.consecutive_failures[provider] = 0
        self.backoff_delays[provider] = 0.0

    def record_failure(self, model_name: str) -> float:
        """Record a failed request and return backoff delay."""
        provider = self.get_provider_from_model(model_name)
        self.consecutive_failures[provider] += 1
        
        # Exponential backoff: 2^failures seconds, max 60 seconds
        base_delay = min(2 ** self.consecutive_failures[provider], 60)
        # Add jitter to prevent thundering herd
        import random
        jitter = random.uniform(0.5, 1.5)
        self.backoff_delays[provider] = base_delay * jitter
        
        logger.warning(f"Rate limit failure #{self.consecutive_failures[provider]} for {provider.value}, backing off {self.backoff_delays[provider]:.1f}s")
        return self.backoff_delays[provider]

    async def acquire(self, model_name: str) -> None:
        """
        Acquire permission to make a request. Will wait if necessary.
        """
        provider = self.get_provider_from_model(model_name)
        self._ensure_cleanup_task()

        # Apply exponential backoff if there were recent failures
        if self.backoff_delays[provider] > 0:
            logger.info(f"Applying backoff delay of {self.backoff_delays[provider]:.1f}s for {provider.value}")
            await asyncio.sleep(self.backoff_delays[provider])
            self.backoff_delays[provider] = 0.0  # Reset after applying

        while True:
            can_proceed, wait_time = self._check_rate_limits(provider)

            if can_proceed:
                # Record the request (for global tracking and active count)
                current_time = time.time()
                self.request_history[provider].append(current_time)
                self.global_request_history.append(current_time)
                self.active_requests[provider] += 1
                self.global_active_requests += 1
                self.last_request_time[provider] = current_time

                logger.debug(f"Rate limit acquired for {provider.value} ({model_name})")
                return

            # Wait before checking again
            logger.info(f"Rate limit exceeded for {provider.value}, waiting {wait_time:.1f}s")
            await asyncio.sleep(min(wait_time, 10.0))  # Cap wait time at 10 seconds

    def release(self, model_name: str) -> None:
        """
        Release a request slot after completion.
        """
        provider = self.get_provider_from_model(model_name)
        self.active_requests[provider] = max(0, self.active_requests[provider] - 1)
        self.global_active_requests = max(0, self.global_active_requests - 1)

    async def execute_with_caching(self, func: Callable, cache_key: str, *args, **kwargs) -> Any:
        """
        Execute a function with rate limiting and caching.
        Returns cached result if available, otherwise executes and caches.
        """
        # Check cache first
        cached_result = self.get_cached_response(cache_key)
        if cached_result is not None:
            return cached_result

        # Execute with rate limiting
        model_name = kwargs.get('model_name') or args[0] if args else 'unknown'
        await self.acquire(model_name)

        try:
            result = await func(*args, **kwargs)
            # Cache the successful result
            self.cache_response(cache_key, result)
            return result
        except Exception as e:
            # Only record failure for actual rate limit errors (429, 413)
            # Don't treat API errors like 400 (bad request) as rate limit failures
            if self._is_rate_limit_error(e):
                self.record_failure(model_name)
            raise e
        finally:
            self.release(model_name)

    def _ensure_cleanup_task(self):
        """Ensure the cleanup task is running."""
        if self.cleanup_task is None or self.cleanup_task.done():
            try:
                self.cleanup_task = asyncio.create_task(self._cleanup_old_requests())
            except RuntimeError:
                # No event loop, skip cleanup for now
                pass

    def _is_rate_limit_error(self, exception: Exception) -> bool:
        """Check if an exception represents a rate limit error that should trigger backoff."""
        # Check for HTTP status codes that indicate rate limiting
        if hasattr(exception, 'response') and hasattr(exception.response, 'status_code'):
            status_code = exception.response.status_code
            return status_code in [429, 413]  # Too Many Requests, Payload Too Large
        
        # Check exception message for rate limit indicators
        error_msg = str(exception).lower()
        rate_limit_indicators = [
            'rate limit', 'too many requests', 'quota exceeded', 
            'payload too large', 'request too large'
        ]
        return any(indicator in error_msg for indicator in rate_limit_indicators)

    async def __aenter__(self):
        """Enter the rate limiting context."""
        self._ensure_cleanup_task()
        
        provider = self.get_provider_from_model(self.model_name)
        provider_config = self.provider_configs[provider]

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    def get_provider_status(self, provider: Provider) -> Dict[str, Any]:
        """
        Get current status information for a provider.
        Returns dict with rate limit info, active requests, etc.
        """
        config = self.provider_configs[provider]
        current_time = time.time()
        minute_ago = current_time - 60

        recent_requests = [t for t in self.request_history[provider] if t > minute_ago]

        # Check token bucket status
        self._refill_token_bucket(provider)
        bucket = self.token_buckets[provider]

        return {
            "provider": provider.value,
            "requests_this_minute": len(recent_requests),
            "requests_per_minute_limit": config.requests_per_minute,
            "active_requests": self.active_requests[provider],
            "burst_limit": config.burst_limit,
            "available_tokens": bucket["tokens"],
            "max_tokens": bucket["max_tokens"],
            "cooldown_seconds": config.cooldown_seconds,
            "last_request_seconds_ago": current_time - self.last_request_time[provider],
            "consecutive_failures": self.consecutive_failures[provider],
            "backoff_delay": self.backoff_delays[provider]
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


@asynccontextmanager
async def with_rate_limit(model_name: str):
    """
    Context manager for rate-limited operations.

    Usage:
        async with with_rate_limit("gpt-4"):
            response = await llm.ainvoke(messages)
    """
    await rate_limiter.acquire(model_name)
    try:
        yield
    finally:
        rate_limiter.release(model_name)


def get_provider_rate_limit_info(model_name: str) -> Dict[str, Any]:
    """Get current rate limit status for a model."""
    provider = rate_limiter.get_provider_from_model(model_name)
    config = rate_limiter.provider_configs[provider]

    current_time = time.time()
    minute_ago = current_time - 60

    recent_requests = [t for t in rate_limiter.request_history[provider] if t > minute_ago]
    global_recent = [t for t in rate_limiter.global_request_history if t > minute_ago]

    return {
        "provider": provider.value,
        "requests_this_minute": len(recent_requests),
        "requests_per_minute_limit": config.requests_per_minute,
        "active_requests": rate_limiter.active_requests[provider],
        "burst_limit": config.burst_limit,
        "global_requests_this_minute": len(global_recent),
        "global_limit": rate_limiter.global_requests_per_minute,
        "cooldown_seconds": config.cooldown_seconds,
        "last_request_seconds_ago": current_time - rate_limiter.last_request_time[provider]
    }