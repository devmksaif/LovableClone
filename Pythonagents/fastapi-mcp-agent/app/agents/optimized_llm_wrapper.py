#!/usr/bin/env python3
"""
Optimized LLM wrapper that integrates caching, rate limiting, and request optimization.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager

from .rate_limiter import rate_limiter, with_rate_limit
from .request_optimizer import request_optimizer

logger = logging.getLogger(__name__)


class OptimizedLLMWrapper:
    """Wrapper for LLM calls with optimization features."""

    def __init__(self, llm, model_name: str):
        self.llm = llm
        self.model_name = model_name
        self.provider = rate_limiter.get_provider_from_model(model_name)

    async def ainvoke_optimized(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[str]] = None,
        use_cache: bool = True,
        task_type: str = "general"
    ) -> Any:
        """Optimized async invoke with caching and rate limiting."""
        
        # Generate cache key from messages
        prompt_text = self._messages_to_cache_key(messages)
        
        # Check cache first
        if use_cache:
            cached_response = await request_optimizer.get_cached_response(
                prompt_text, self.model_name, tools
            )
            if cached_response is not None:
                return cached_response

        # Create request key for deduplication
        request_key = f"{self.model_name}:{hash(prompt_text)}"
        
        # Define the actual request function
        async def make_request():
            return await self._make_rate_limited_request(messages)
        
        # Use deduplication for identical requests
        try:
            response = await request_optimizer.deduplicate_request(request_key, make_request)
            
            # Record success for rate limiter
            rate_limiter.record_success(self.model_name)
            
            # Cache the response
            if use_cache:
                await request_optimizer.cache_response(
                    prompt_text, self.model_name, response, tools
                )
            
            return response
            
        except Exception as e:
            # Handle rate limiting errors
            if "429" in str(e) or "rate limit" in str(e).lower():
                backoff_delay = rate_limiter.record_failure(self.model_name)
                logger.warning(f"Rate limit hit for {self.model_name}, backing off {backoff_delay:.1f}s")
                await asyncio.sleep(backoff_delay)
                # Retry once after backoff
                try:
                    response = await self._make_rate_limited_request(messages)
                    rate_limiter.record_success(self.model_name)
                    if use_cache:
                        await request_optimizer.cache_response(
                            prompt_text, self.model_name, response, tools
                        )
                    return response
                except Exception as retry_e:
                    logger.error(f"Retry failed for {self.model_name}: {retry_e}")
                    raise retry_e
            else:
                logger.error(f"LLM request failed for {self.model_name}: {e}")
                raise e

    async def _make_rate_limited_request(self, messages: List[Dict[str, Any]]) -> Any:
        """Make the actual rate-limited request."""
        async with with_rate_limit(self.model_name):
            return await self.llm.ainvoke(messages)

    def _messages_to_cache_key(self, messages: List[Dict[str, Any]]) -> str:
        """Convert messages to a cache key string."""
        # Extract text content from messages for caching
        content_parts = []
        for msg in messages:
            if isinstance(msg, dict):
                content_parts.append(msg.get('content', ''))
            elif hasattr(msg, 'content'):
                content_parts.append(str(msg.content))
            else:
                content_parts.append(str(msg))
        return ' '.join(content_parts)

    async def batch_tool_calls(self, tool_calls: List[Dict[str, Any]], tools: List[Any]) -> List[Dict[str, Any]]:
        """Execute tool calls in optimized batches."""
        if not tool_calls:
            return []

        # Optimize tool call execution order
        batches = request_optimizer.optimize_tool_calls(tool_calls)
        results = []

        for batch in batches:
            # Execute tools in this batch (potentially in parallel for read operations)
            batch_results = await self._execute_tool_batch(batch, tools)
            results.extend(batch_results)
            
            # Small delay between batches to prevent overwhelming
            if len(batches) > 1:
                await asyncio.sleep(0.3)

        return results

    async def _execute_tool_batch(self, tool_calls: List[Dict[str, Any]], tools: List[Any]) -> List[Dict[str, Any]]:
        """Execute a batch of tool calls."""
        if len(tool_calls) == 1:
            # Single tool call
            return [await self._execute_single_tool(tool_calls[0], tools)]
        
        # Multiple tool calls - check if they can be parallelized
        read_only_tools = {'read_file', 'list_dir', 'get_project_structure', 'grep_search'}
        
        if all(call.get('name') in read_only_tools for call in tool_calls):
            # Parallel execution for read-only operations
            tasks = [self._execute_single_tool(call, tools) for call in tool_calls]
            return await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Sequential execution for write operations
            results = []
            for call in tool_calls:
                result = await self._execute_single_tool(call, tools)
                results.append(result)
                await asyncio.sleep(0.1)  # Small delay between operations
            return results

    async def _execute_single_tool(self, tool_call: Dict[str, Any], tools: List[Any]) -> Dict[str, Any]:
        """Execute a single tool call."""
        try:
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('args', {})
            
            # Find the tool
            tool = next((t for t in tools if t.name == tool_name), None)
            if not tool:
                return {
                    "role": "tool",
                    "tool_call_id": tool_call.get('id', 'unknown'),
                    "content": f"Error: Tool {tool_name} not found"
                }
            
            # Execute the tool
            result = await tool.arun(**tool_args)
            return {
                "role": "tool",
                "tool_call_id": tool_call.get('id', 'unknown'),
                "content": str(result)
            }
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {
                "role": "tool",
                "tool_call_id": tool_call.get('id', 'unknown'),
                "content": f"Error executing tool: {str(e)}"
            }


def create_optimized_llm(llm, model_name: str) -> OptimizedLLMWrapper:
    """Create an optimized LLM wrapper."""
    return OptimizedLLMWrapper(llm, model_name)


@asynccontextmanager
async def optimized_llm_call(model_name: str, task_type: str = "general"):
    """Context manager for optimized LLM calls with automatic optimization."""
    from .optimization_config import get_fallback_model
    
    # Check if we should use a faster model for this task
    should_optimize, optimized_model = request_optimizer.should_use_faster_model(task_type, model_name)
    
    if should_optimize and optimized_model:
        logger.info(f"Using optimized model {optimized_model} for {task_type} task instead of {model_name}")
        model_to_use = optimized_model
    else:
        model_to_use = model_name
    
    try:
        yield model_to_use
    except Exception as e:
        # If rate limited, try to get a fallback model
        if "429" in str(e) or "rate limit" in str(e).lower():
            fallback_model = get_fallback_model(model_to_use)
            if fallback_model:
                logger.warning(f"Rate limited on {model_to_use}, falling back to {fallback_model}")
                yield fallback_model
            else:
                raise e
        else:
            raise e
    finally:
        # Log optimization stats periodically
        stats = request_optimizer.get_stats()
        if stats["total_requests"] % 10 == 0:  # Every 10 requests
            logger.info(f"Optimization stats: {stats}")