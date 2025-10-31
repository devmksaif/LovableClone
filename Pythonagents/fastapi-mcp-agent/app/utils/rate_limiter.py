import redis
import time
import json
from typing import Optional, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Redis-based rate limiter for external API calls with intelligent queuing."""

    def __init__(self, redis_client: redis.Redis, prefix: str = "api_ratelimit"):
        self.redis = redis_client
        self.prefix = prefix

    def _get_usage_key(self, provider: str, api_key_hash: str) -> str:
        """Generate Redis key for tracking API usage."""
        return f"{self.prefix}:usage:{provider}:{api_key_hash}"

    def _get_queue_key(self, provider: str) -> str:
        """Generate Redis key for request queue."""
        return f"{self.prefix}:queue:{provider}"

    def _get_reset_time_key(self, provider: str, api_key_hash: str) -> str:
        """Generate Redis key for rate limit reset time."""
        return f"{self.prefix}:reset:{provider}:{api_key_hash}"

    async def check_api_limits(self, provider: str, api_key_hash: str,
                              requests_per_minute: int = 60,
                              requests_per_hour: int = 1000) -> Tuple[bool, int, Optional[float]]:
        """
        Check if we can make an API call without hitting rate limits.

        Args:
            provider: API provider name (e.g., 'openai', 'groq')
            api_key_hash: Hashed API key for tracking
            requests_per_minute: Max requests per minute
            requests_per_hour: Max requests per hour

        Returns:
            (can_proceed: bool, queue_length: int, wait_seconds: Optional[float])
        """
        try:
            usage_key = self._get_usage_key(provider, api_key_hash)
            reset_key = self._get_reset_time_key(provider, api_key_hash)

            # Get current usage counts
            current_minute = int(time.time() // 60)
            current_hour = int(time.time() // 3600)

            minute_key = f"{usage_key}:minute:{current_minute}"
            hour_key = f"{usage_key}:hour:{current_hour}"

            minute_count = int(self.redis.get(minute_key) or 0)
            hour_count = int(self.redis.get(hour_key) or 0)

            # Check rate limits
            minute_limit_exceeded = minute_count >= requests_per_minute
            hour_limit_exceeded = hour_count >= requests_per_hour

            if minute_limit_exceeded or hour_limit_exceeded:
                # Calculate wait time until next window
                reset_time = float(self.redis.get(reset_key) or time.time())
                wait_seconds = max(0, reset_time - time.time())

                # Get queue length
                queue_key = self._get_queue_key(provider)
                queue_length = self.redis.llen(queue_key)

                logger.warning(f"Rate limit exceeded for {provider}: minute={minute_count}/{requests_per_minute}, hour={hour_count}/{requests_per_hour}, queue={queue_length}")
                return False, queue_length, wait_seconds

            # Within limits, can proceed
            return True, 0, None

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Allow request on Redis failure to avoid blocking
            return True, 0, None

    async def record_api_call(self, provider: str, api_key_hash: str) -> None:
        """Record an API call for rate limiting."""
        try:
            usage_key = self._get_usage_key(provider, api_key_hash)
            reset_key = self._get_reset_time_key(provider, api_key_hash)

            current_minute = int(time.time() // 60)
            current_hour = int(time.time() // 3600)

            minute_key = f"{usage_key}:minute:{current_minute}"
            hour_key = f"{usage_key}:hour:{current_hour}"

            # Increment counters with expiration
            self.redis.incr(minute_key)
            self.redis.incr(hour_key)

            # Set expiration for minute and hour windows
            self.redis.expire(minute_key, 120)  # 2 minutes
            self.redis.expire(hour_key, 7200)  # 2 hours

            # Update reset time
            reset_time = (current_minute + 1) * 60  # Next minute
            self.redis.set(reset_key, reset_time, ex=120)

            logger.debug(f"Recorded API call for {provider}: minute_key={minute_key}")

        except Exception as e:
            logger.error(f"Failed to record API call: {e}")

    async def queue_request(self, provider: str, request_data: Dict[str, Any]) -> str:
        """
        Queue a request when rate limits are exceeded.

        Args:
            provider: API provider name
            request_data: Request data to queue

        Returns:
            queue_id: Unique ID for the queued request
        """
        try:
            queue_key = self._get_queue_key(provider)
            queue_id = f"{provider}:{int(time.time())}:{hash(str(request_data))}"

            queued_item = {
                "id": queue_id,
                "data": request_data,
                "provider": provider,
                "timestamp": time.time()
            }

            # Add to queue (Redis list)
            self.redis.rpush(queue_key, json.dumps(queued_item))

            logger.info(f"Queued request {queue_id} for {provider}")
            return queue_id

        except Exception as e:
            logger.error(f"Failed to queue request: {e}")
            raise

    async def get_next_queued_request(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Get the next request from the queue.

        Returns:
            queued_item: Next item to process, or None if queue empty
        """
        try:
            queue_key = self._get_queue_key(provider)

            # Get first item from queue
            item_json = self.redis.lpop(queue_key)

            if not item_json:
                return None

            queued_item = json.loads(item_json)
            logger.info(f"Dequeued request {queued_item['id']} for {provider}")
            return queued_item

        except Exception as e:
            logger.error(f"Failed to get next queued request: {e}")
            return None

    async def get_queue_length(self, provider: str) -> int:
        """Get the current queue length for a provider."""
        try:
            queue_key = self._get_queue_key(provider)
            return self.redis.llen(queue_key)
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0

    async def get_provider_limits(self, provider: str) -> Dict[str, Any]:
        """Get current usage stats for a provider."""
        try:
            # This is a simplified implementation - in practice you'd track per API key
            api_key_hash = "default"  # Placeholder
            usage_key = self._get_usage_key(provider, api_key_hash)

            current_minute = int(time.time() // 60)
            current_hour = int(time.time() // 3600)

            minute_key = f"{usage_key}:minute:{current_minute}"
            hour_key = f"{usage_key}:hour:{current_hour}"

            minute_count = int(self.redis.get(minute_key) or 0)
            hour_count = int(self.redis.get(hour_key) or 0)
            queue_length = await self.get_queue_length(provider)

            return {
                "provider": provider,
                "minute_usage": minute_count,
                "hour_usage": hour_count,
                "queue_length": queue_length,
                "minute_limit": 60,  # Configurable
                "hour_limit": 1000   # Configurable
            }

        except Exception as e:
            logger.error(f"Failed to get provider limits: {e}")
            return {
                "provider": provider,
                "error": str(e)
            }