import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import asyncio
from app.cache.redis_cache import redis_cache, get_cache
from app.tasks.llm_tasks import process_llm_request
from app.agents.rate_limiter import RateLimiter, RateLimitConfig
import json

logger = logging.getLogger(__name__)

class LLMRequestMiddleware:
    """
    Middleware for managing LLM requests with queuing, caching, and load balancing.
    """

    def __init__(self):
        self.cache = redis_cache
        self.rate_limiter = RateLimiter()
        self.max_queue_size = 1000
        self.max_concurrent_requests = 10
        self._semaphore = asyncio.Semaphore(self.max_concurrent_requests)

    async def initialize(self):
        """Initialize middleware components."""
        await self.cache.connect()
        logger.info("LLM Request Middleware initialized")

    async def process_request(self, request_data: Dict[str, Any],
                            use_cache: bool = True,
                            use_queue: bool = True) -> Dict[str, Any]:
        """
        Main entry point for processing LLM requests through middleware.

        Args:
            request_data: The LLM request data
            use_cache: Whether to check cache first
            use_queue: Whether to queue requests when busy

        Returns:
            Processed response data
        """
        session_id = request_data.get('session_id', 'unknown')
        user_request = request_data.get('user_request', '')

        logger.info(f"Processing request for session {session_id}")

        # Check rate limits first
        if not await self._check_rate_limits(request_data):
            return {
                "error": "Rate limit exceeded",
                "generated_code": "",
                "review_feedback": "Too many requests. Please wait before trying again.",
                "session_id": session_id
            }

        # Check cache if enabled
        if use_cache:
            cached_response = await self._check_cache(request_data)
            if cached_response:
                logger.info(f"Cache hit for session {session_id}")
                return cached_response

        # Check if we should queue or process immediately
        queue_length = await self.cache.get_request_queue_length()

        if use_queue and queue_length >= self.max_queue_size:
            return {
                "error": "Queue full",
                "generated_code": "",
                "review_feedback": "Server is busy. Please try again later.",
                "session_id": session_id
            }

        # Use semaphore to limit concurrent requests
        async with self._semaphore:
            if use_queue and queue_length > 0:
                # Queue the request for background processing
                return await self._queue_request(request_data)
            else:
                # Process immediately
                return await self._process_immediately(request_data)

    async def _check_rate_limits(self, request_data: Dict[str, Any]) -> bool:
        """Check if request passes rate limiting."""
        try:
            session_id = request_data.get('session_id', 'unknown')
            model = request_data.get('model', 'gpt-4')

            # Check rate limit using provider-specific limits
            provider = self.rate_limiter.get_provider_from_model(model)
            allowed, wait_time = self.rate_limiter._check_rate_limits(provider)

            if not allowed:
                logger.warning(f"Rate limit exceeded for session {session_id}, wait {wait_time}s")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking rate limits: {e}")
            return True  # Allow request on error to avoid blocking

    async def _check_cache(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check if request result is cached."""
        try:
            # Create cache key from relevant request data
            cache_key_data = {
                "user_request": request_data.get('user_request', ''),
                "model": request_data.get('model', 'gpt-4'),
                "sandbox_context": request_data.get('sandbox_context', {}),
                "api_keys": list(request_data.get('api_keys', {}).keys())
            }

            cached = await self.cache.get_cached_response(cache_key_data)
            return cached.get('response') if cached else None

        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

    async def _queue_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Queue request for background processing."""
        try:
            session_id = request_data.get('session_id', 'unknown')

            # Add to queue with priority based on request type
            priority = self._calculate_priority(request_data)
            success = await self.cache.enqueue_request(request_data, priority=priority)

            if success:
                logger.info(f"Queued request for session {session_id} with priority {priority}")

                # Submit Celery task
                task = process_llm_request.delay(request_data)

                return {
                    "queued": True,
                    "task_id": task.id,
                    "queue_position": await self.cache.get_request_queue_length(),
                    "estimated_wait": self._estimate_wait_time(),
                    "generated_code": "",
                    "review_feedback": f"Your request has been queued for processing. Task ID: {task.id}",
                    "session_id": session_id
                }
            else:
                return {
                    "error": "Failed to queue request",
                    "generated_code": "",
                    "review_feedback": "Failed to queue request. Please try again.",
                    "session_id": session_id
                }

        except Exception as e:
            logger.error(f"Error queuing request: {e}")
            return {
                "error": str(e),
                "generated_code": "",
                "review_feedback": "An error occurred while queuing your request.",
                "session_id": session_id
            }

    async def _process_immediately(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process request immediately."""
        try:
            # Use Celery task even for immediate processing for consistency
            task = process_llm_request.delay(request_data)

            # Wait for result with timeout
            result = task.get(timeout=300)  # 5 minute timeout

            logger.info(f"Immediate processing completed for session {request_data.get('session_id')}")

            # Cache the result
            await self._cache_result(request_data, result)

            return result

        except Exception as e:
            logger.error(f"Error in immediate processing: {e}")
            session_id = request_data.get('session_id', 'unknown')
            return {
                "error": str(e),
                "generated_code": "# Error occurred\nprint('An error occurred during processing')",
                "review_feedback": f"Processing failed: {str(e)}",
                "session_id": session_id
            }

    async def _cache_result(self, request_data: Dict[str, Any], result: Dict[str, Any]):
        """Cache the processing result."""
        try:
            cache_key_data = {
                "user_request": request_data.get('user_request', ''),
                "model": request_data.get('model', 'gpt-4'),
                "sandbox_context": request_data.get('sandbox_context', {}),
                "api_keys": list(request_data.get('api_keys', {}).keys())
            }

            await self.cache.set_cached_response(cache_key_data, result, ttl_seconds=3600)

        except Exception as e:
            logger.error(f"Error caching result: {e}")

    def _calculate_priority(self, request_data: Dict[str, Any]) -> int:
        """Calculate request priority (higher number = higher priority)."""
        priority = 0

        # Premium users get higher priority
        if request_data.get('is_premium', False):
            priority += 10

        # Shorter requests get slightly higher priority
        user_request = request_data.get('user_request', '')
        if len(user_request) < 100:
            priority += 2

        # Urgent requests
        if 'urgent' in user_request.lower() or 'emergency' in user_request.lower():
            priority += 5

        return priority

    def _estimate_wait_time(self) -> str:
        """Estimate wait time based on queue length."""
        # Simple estimation: assume 30 seconds per request
        avg_processing_time = 30
        queue_length = 0  # We'd need to get this from cache

        estimated_seconds = queue_length * avg_processing_time

        if estimated_seconds < 60:
            return f"{estimated_seconds} seconds"
        elif estimated_seconds < 3600:
            return f"{estimated_seconds // 60} minutes"
        else:
            return f"{estimated_seconds // 3600} hours"

    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status."""
        try:
            queue_length = await self.cache.get_request_queue_length()
            cache_stats = await self.cache.get_cache_stats()

            return {
                "queue_length": queue_length,
                "max_queue_size": self.max_queue_size,
                "cache_stats": cache_stats,
                "active_requests": self.max_concurrent_requests - self._semaphore._value
            }

        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"error": str(e)}

    async def cancel_request(self, task_id: str) -> bool:
        """Cancel a queued request."""
        try:
            # This would require more complex Celery integration
            # For now, just return success
            logger.info(f"Request to cancel task {task_id}")
            return True
        except Exception as e:
            logger.error(f"Error canceling request: {e}")
            return False

# Global middleware instance
llm_middleware = LLMRequestMiddleware()