#!/usr/bin/env python3
"""
Request optimization utilities for reducing API calls and improving efficiency.
Implements batching, caching, and intelligent request management.
"""

import asyncio
import json
import time
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import pickle

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """Cached API response with metadata."""
    response: Any
    timestamp: float
    model: str
    hash_key: str
    hit_count: int = 0


@dataclass
class BatchRequest:
    """Batched request for processing multiple operations together."""
    requests: List[Dict[str, Any]]
    model: str
    priority: int = 1
    created_at: float = field(default_factory=time.time)


class RequestOptimizer:
    """Optimizes API requests through batching, caching, and intelligent scheduling."""

    def __init__(self, cache_ttl: int = 3600, max_cache_size: int = 1000):
        self.cache_ttl = cache_ttl  # Cache time-to-live in seconds
        self.max_cache_size = max_cache_size
        
        # Response cache
        self.response_cache: Dict[str, CachedResponse] = {}
        
        # Request batching
        self.pending_batches: Dict[str, BatchRequest] = {}
        self.batch_timeout = 2.0  # Wait up to 2 seconds to batch requests
        
        # Request deduplication
        self.active_requests: Dict[str, asyncio.Future] = {}
        
        # Statistics
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "batched_requests": 0,
            "deduplicated_requests": 0,
            "total_requests": 0
        }

    def _generate_cache_key(self, prompt: str, model: str, tools: List[str] = None) -> str:
        """Generate a cache key for the request."""
        content = f"{model}:{prompt}"
        if tools:
            content += f":tools:{','.join(sorted(tools))}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _is_cache_valid(self, cached: CachedResponse) -> bool:
        """Check if cached response is still valid."""
        return time.time() - cached.timestamp < self.cache_ttl

    def _cleanup_cache(self):
        """Remove expired entries and maintain cache size."""
        current_time = time.time()
        
        # Remove expired entries
        expired_keys = [
            key for key, cached in self.response_cache.items()
            if current_time - cached.timestamp > self.cache_ttl
        ]
        for key in expired_keys:
            del self.response_cache[key]
        
        # If still over limit, remove least recently used
        if len(self.response_cache) > self.max_cache_size:
            sorted_items = sorted(
                self.response_cache.items(),
                key=lambda x: (x[1].hit_count, x[1].timestamp)
            )
            items_to_remove = len(self.response_cache) - self.max_cache_size
            for key, _ in sorted_items[:items_to_remove]:
                del self.response_cache[key]

    async def get_cached_response(self, prompt: str, model: str, tools: List[str] = None) -> Optional[Any]:
        """Get cached response if available and valid."""
        cache_key = self._generate_cache_key(prompt, model, tools)
        
        if cache_key in self.response_cache:
            cached = self.response_cache[cache_key]
            if self._is_cache_valid(cached):
                cached.hit_count += 1
                self.stats["cache_hits"] += 1
                logger.info(f"Cache hit for request (key: {cache_key[:8]}...)")
                return cached.response
            else:
                # Remove expired entry
                del self.response_cache[cache_key]
        
        self.stats["cache_misses"] += 1
        return None

    async def cache_response(self, prompt: str, model: str, response: Any, tools: List[str] = None):
        """Cache a response for future use."""
        cache_key = self._generate_cache_key(prompt, model, tools)
        
        self.response_cache[cache_key] = CachedResponse(
            response=response,
            timestamp=time.time(),
            model=model,
            hash_key=cache_key
        )
        
        # Cleanup if needed
        if len(self.response_cache) > self.max_cache_size * 1.2:
            self._cleanup_cache()

    async def deduplicate_request(self, request_key: str, request_func) -> Any:
        """Deduplicate identical requests that are currently in flight."""
        if request_key in self.active_requests:
            logger.info(f"Deduplicating request: {request_key[:8]}...")
            self.stats["deduplicated_requests"] += 1
            return await self.active_requests[request_key]
        
        # Create new request
        future = asyncio.create_task(request_func())
        self.active_requests[request_key] = future
        
        try:
            result = await future
            return result
        finally:
            # Clean up completed request
            if request_key in self.active_requests:
                del self.active_requests[request_key]

    def should_use_faster_model(self, task_type: str, current_model: str = None) -> Tuple[bool, str]:
        """Determine if we should use a faster model for this task."""
        from .optimization_config import get_optimal_model_for_task, DEFAULT_OPTIMIZATION_CONFIG
        
        if not DEFAULT_OPTIMIZATION_CONFIG.enable_smart_model_selection:
            return False, current_model or ""
        
        # Get rate limited providers
        rate_limited_providers = []
        from .rate_limiter import rate_limiter
        
        # Check which providers are currently experiencing issues
        for provider_name in ["groq", "openai", "anthropic"]:
            provider_enum = None
            for p in rate_limiter.provider_configs.keys():
                if p.value == provider_name:
                    provider_enum = p
                    break
            
            if provider_enum and rate_limiter.consecutive_failures.get(provider_enum, 0) > 2:
                rate_limited_providers.append(provider_name)
        
        # Get optimal model for task
        optimal_model = get_optimal_model_for_task(
            task_type=task_type,
            prefer_speed=DEFAULT_OPTIMIZATION_CONFIG.prefer_speed_over_quality,
            max_cost=DEFAULT_OPTIMIZATION_CONFIG.cost_threshold_per_request,
            exclude_providers=rate_limited_providers
        )
        
        if optimal_model and optimal_model != current_model:
            return True, optimal_model
        
        return False, current_model or ""

    def optimize_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group tool calls that can be executed in parallel."""
        # Group by tool type for potential batching
        tool_groups = defaultdict(list)
        
        for tool_call in tool_calls:
            tool_name = tool_call.get('name', 'unknown')
            # Group read-only operations together
            if tool_name in ['read_file', 'list_dir', 'get_project_structure']:
                tool_groups['read_ops'].append(tool_call)
            # Group write operations separately (need sequential execution)
            elif tool_name in ['write_file', 'create_directory']:
                tool_groups['write_ops'].append(tool_call)
            else:
                tool_groups['other'].append(tool_call)
        
        # Return groups that can be executed in parallel
        batches = []
        for group_name, calls in tool_groups.items():
            if group_name == 'read_ops':
                # Read operations can be batched
                batches.append(calls)
            else:
                # Other operations should be executed sequentially
                for call in calls:
                    batches.append([call])
        
        return batches

    async def optimize_agent_workflow(self, agents: List[str], task_complexity: str) -> Dict[str, Any]:
        """Optimize the agent workflow based on task complexity."""
        optimizations = {
            "skip_review": False,
            "use_fast_models": {},
            "parallel_execution": False,
            "reduced_iterations": {}
        }
        
        # For simple tasks, skip review agent
        if task_complexity == "simple":
            optimizations["skip_review"] = True
            optimizations["reduced_iterations"] = {
                "planning": 1,
                "code_generation": 2
            }
        
        # Use faster models for specific agents
        for agent in agents:
            should_use_fast, fast_model = self.should_use_faster_model(
                agent.lower().replace("agent", ""), task_complexity
            )
            if should_use_fast:
                optimizations["use_fast_models"][agent] = fast_model
        
        return optimizations

    def get_stats(self) -> Dict[str, Any]:
        """Get optimization statistics."""
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        cache_hit_rate = (self.stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            **self.stats,
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "cache_size": len(self.response_cache),
            "active_requests": len(self.active_requests)
        }


# Global optimizer instance
request_optimizer = RequestOptimizer()