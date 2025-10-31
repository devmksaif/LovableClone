import redis
import json
import hashlib
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class RedisCache:
    """Redis-based caching service for LLM requests and responses."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0,
                 password: Optional[str] = None, socket_timeout: int = 5):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.socket_timeout = socket_timeout
        self._client: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
        try:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                socket_timeout=self.socket_timeout,
                decode_responses=True
            )
            # Test connection
            await asyncio.get_event_loop().run_in_executor(None, self._client.ping)
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._client = None

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await asyncio.get_event_loop().run_in_executor(None, self._client.close)
            self._client = None

    def _get_cache_key(self, prefix: str, data: Dict[str, Any]) -> str:
        """Generate a deterministic cache key from request data."""
        # Create a sorted JSON string for consistent hashing
        data_str = json.dumps(data, sort_keys=True)
        hash_obj = hashlib.sha256(data_str.encode())
        return f"{prefix}:{hash_obj.hexdigest()[:16]}"

    async def get_cached_response(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Retrieve cached LLM response if available."""
        if not self._client:
            return None

        cache_key = self._get_cache_key("llm_response", request_data)

        try:
            cached_data = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get, cache_key
            )

            if cached_data:
                result = json.loads(cached_data)
                logger.info(f"Cache hit for key: {cache_key}")
                return result
            else:
                logger.info(f"Cache miss for key: {cache_key}")
                return None
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None

    async def set_cached_response(self, request_data: Dict[str, Any],
                                response_data: Dict[str, Any],
                                ttl_seconds: int = 3600) -> bool:
        """Cache LLM response with TTL."""
        if not self._client:
            return False

        cache_key = self._get_cache_key("llm_response", request_data)

        try:
            # Add metadata to cached response
            cached_data = {
                "response": response_data,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl_seconds": ttl_seconds
            }

            success = await asyncio.get_event_loop().run_in_executor(
                None, self._client.setex,
                cache_key, ttl_seconds, json.dumps(cached_data)
            )

            if success:
                logger.info(f"Cached response for key: {cache_key} (TTL: {ttl_seconds}s)")
            return bool(success)
        except Exception as e:
            logger.error(f"Error caching response: {e}")
            return False

    async def get_request_queue_length(self, queue_name: str = "llm_requests") -> int:
        """Get the length of the request queue."""
        if not self._client:
            return 0

        try:
            length = await asyncio.get_event_loop().run_in_executor(
                None, self._client.llen, queue_name
            )
            return length or 0
        except Exception as e:
            logger.error(f"Error getting queue length: {e}")
            return 0

    async def enqueue_request(self, request_data: Dict[str, Any],
                            queue_name: str = "llm_requests",
                            priority: int = 0) -> bool:
        """Add request to processing queue."""
        if not self._client:
            return False

        try:
            # Add metadata
            queue_item = {
                "request": request_data,
                "queued_at": datetime.utcnow().isoformat(),
                "priority": priority,
                "id": hashlib.sha256(
                    json.dumps(request_data, sort_keys=True).encode()
                ).hexdigest()[:16]
            }

            # Use priority queue (sorted set) for requests
            priority_queue = f"{queue_name}:priority"
            score = priority + (datetime.utcnow().timestamp() / 1000000)  # Add microsecond precision

            success = await asyncio.get_event_loop().run_in_executor(
                None, self._client.zadd,
                priority_queue, {json.dumps(queue_item): score}
            )

            if success:
                logger.info(f"Enqueued request with priority {priority}")
            return bool(success)
        except Exception as e:
            logger.error(f"Error enqueuing request: {e}")
            return False

    async def dequeue_request(self, queue_name: str = "llm_requests") -> Optional[Dict[str, Any]]:
        """Remove and return highest priority request from queue."""
        if not self._client:
            return None

        try:
            priority_queue = f"{queue_name}:priority"

            # Get the highest priority item (lowest score)
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._client.zpopmin, priority_queue, 1
            )

            if result:
                item_data = json.loads(result[0][0])
                logger.info(f"Dequeued request: {item_data['id']}")
                return item_data
            else:
                return None
        except Exception as e:
            logger.error(f"Error dequeuing request: {e}")
            return None

    async def store_session_data(self, session_id: str, data: Dict[str, Any],
                               ttl_seconds: int = 86400) -> bool:
        """Store session data with TTL."""
        if not self._client:
            return False

        try:
            cache_key = f"session:{session_id}"
            success = await asyncio.get_event_loop().run_in_executor(
                None, self._client.setex,
                cache_key, ttl_seconds, json.dumps(data)
            )
            return bool(success)
        except Exception as e:
            logger.error(f"Error storing session data: {e}")
            return False

    async def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data."""
        if not self._client:
            return None

        try:
            cache_key = f"session:{session_id}"
            data = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get, cache_key
            )

            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Error retrieving session data: {e}")
            return None

    async def publish_websocket_message(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish message to WebSocket channel."""
        if not self._client:
            return False

        try:
            success = await asyncio.get_event_loop().run_in_executor(
                None, self._client.publish,
                channel, json.dumps(message)
            )
            return success > 0
        except Exception as e:
            logger.error(f"Error publishing WebSocket message: {e}")
            return False

    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self._client:
            return {"connected": False}

        try:
            info = await asyncio.get_event_loop().run_in_executor(
                None, self._client.info
            )

            # Get queue lengths
            request_queue_len = await self.get_request_queue_length()

            return {
                "connected": True,
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "request_queue_length": request_queue_len,
                "uptime_seconds": info.get("uptime_in_seconds", 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"connected": False, "error": str(e)}

# Global cache instance
redis_cache = RedisCache()

@asynccontextmanager
async def get_cache():
    """Context manager for cache operations."""
    if not redis_cache._client:
        await redis_cache.connect()
    try:
        yield redis_cache
    finally:
        pass  # Keep connection alive