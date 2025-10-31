import logging
from typing import Dict, Any, Optional
from app.celery_config import celery_app
from app.cache.redis_cache import redis_cache
from app.agents.agent_graphs import create_agent_instances, create_agent_nodes_with_instances
from app.agents.agent_graphs import AgentState, AgentGraph
import asyncio
import json
import psutil
import os
import gc
import signal
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@contextmanager
def memory_monitor():
    """Context manager to monitor memory usage and cleanup on exit."""
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB

    try:
        yield
    finally:
        # Force garbage collection
        gc.collect()

        # Check for memory leaks
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = final_memory - initial_memory

        if memory_delta > 100:  # More than 100MB increase
            logger.warning(f"Memory leak detected: {memory_delta:.1f}MB increase")

        # Log memory usage
        logger.debug(f"Memory usage: {final_memory:.1f}MB (delta: {memory_delta:+.1f}MB)")

def signal_handler(signum, frame):
    """Handle segmentation faults and other critical signals."""
    logger.critical(f"Received signal {signum}, performing emergency cleanup")
    gc.collect()
    # Don't exit here - let the exception propagate

# Register signal handlers for critical signals
signal.signal(signal.SIGSEGV, signal_handler)
signal.signal(signal.SIGBUS, signal_handler)
signal.signal(signal.SIGILL, signal_handler)

@celery_app.task(bind=True, name='process_llm_request')
def process_llm_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task to process LLM requests asynchronously.
    This handles the actual LLM processing outside the main request loop.
    """
    try:
        logger.info(f"Processing LLM request: {request_data.get('id', 'unknown')}")

        # Extract request parameters
        user_request = request_data.get('user_request', '')
        session_id = request_data.get('session_id', '')
        model = request_data.get('model', 'gpt-4')
        sandbox_context = request_data.get('sandbox_context', {})
        sandbox_id = request_data.get('sandbox_id')
        api_keys = request_data.get('api_keys', {})

        if not user_request or not session_id:
            raise ValueError("Missing required parameters: user_request or session_id")

        # Check cache first
        cache_key_data = {
            "user_request": user_request,
            "model": model,
            "sandbox_context": sandbox_context,
            "api_keys": list(api_keys.keys()) if api_keys else []
        }

        # Note: In a real implementation, we'd need to make this async
        # For now, we'll process synchronously within the Celery task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Check cache
            cached_response = loop.run_until_complete(
                redis_cache.get_cached_response(cache_key_data)
            )

            if cached_response:
                logger.info("Returning cached response")
                return cached_response

            # Process the request using existing agent infrastructure
            result = loop.run_until_complete(_process_request_async(
                user_request, session_id, model, sandbox_context, sandbox_id, api_keys
            ))

            # Cache the result
            loop.run_until_complete(
                redis_cache.set_cached_response(cache_key_data, result, ttl_seconds=3600)
            )

            return result

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error processing LLM request: {e}")
        # Update task state for monitoring
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise

@celery_app.task(bind=True, name='batch_process_requests')
def batch_process_requests(self, request_batch: list) -> list:
    """
    Process multiple LLM requests in batch for efficiency.
    """
    results = []

    for request_data in request_batch:
        try:
            result = process_llm_request.apply(args=[request_data]).get()
            results.append({
                'request_id': request_data.get('id'),
                'success': True,
                'result': result
            })
        except Exception as e:
            logger.error(f"Batch processing failed for request {request_data.get('id')}: {e}")
            results.append({
                'request_id': request_data.get('id'),
                'success': False,
                'error': str(e)
            })

    return results

@celery_app.task(bind=True, name='cleanup_expired_cache')
def cleanup_expired_cache(self) -> Dict[str, Any]:
    """
    Periodic task to clean up expired cache entries and optimize storage.
    """
    try:
        # Redis automatically handles TTL expiration, but we can add custom cleanup logic
        logger.info("Running cache cleanup task")

        # Get cache stats
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            stats = loop.run_until_complete(redis_cache.get_cache_stats())
            return {
                'success': True,
                'stats': stats,
                'cleaned_entries': 0  # Redis handles this automatically
            }
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Error in cache cleanup: {e}")
        return {'success': False, 'error': str(e)}

async def _process_request_async(user_request: str, session_id: str, model: str,
                               sandbox_context: Dict[str, Any], sandbox_id: Optional[str],
                               api_keys: Dict[str, str]) -> Dict[str, Any]:
    """
    Internal async function to process ``a single LLM request.
    """
    try:
        # Create agent instances
        agent_instances = await create_agent_instances(model=model, session_id=session_id, api_keys=api_keys)
        agent_nodes = await create_agent_nodes_with_instances(agent_instances, websocket=None)

        # Create initial state
        state = AgentState(
            user_request=user_request,
            session_id=session_id,
            model=model,
            sandbox_context=sandbox_context,
            sandbox_id=sandbox_id,
            available_tools=[],  # Will be populated by MCP
            tool_results=[],
            api_keys=api_keys
        )

        # Create and execute agent graph
        agent_graph = AgentGraph(agent_nodes)

        # Execute with timeout and error handling
        try:
            state_dict = await asyncio.wait_for(
                agent_graph.graph.ainvoke(state),
                timeout=300  # 5 minute timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Request timed out for session {session_id}")
            state_dict = {
                'generated_code': '# Request timed out\nprint("Request processing timed out")',
                'review_feedback': 'Request processing timed out after 5 minutes',
                'current_plan': [],
                'progress_updates': [{'step': 'timeout', 'message': 'Request timed out'}],
                'session_id': session_id
            }

        # Format final result
        result = {
            "generated_code": state_dict.get('generated_code', ''),
            "review_feedback": state_dict.get('review_feedback', ''),
            "plan": state_dict.get('current_plan', []),
            "progress_updates": state_dict.get('progress_updates', []),
            "session_id": session_id,
            "processed_at": str(asyncio.get_event_loop().time())
        }

        return result

    except Exception as e:
        logger.error(f"Error in async request processing: {e}")
        # Return error result
        return {
            "generated_code": "# Error occurred\nprint('An error occurred during processing')",
            "review_feedback": f"Error: {str(e)}",
            "plan": [],
            "progress_updates": [{"step": "error", "message": str(e)}],
            "session_id": session_id,
            "error": True
        }

@celery_app.task(bind=True, name='process_queued_requests')
def process_queued_requests(self, provider: str) -> Dict[str, Any]:
    """
    Celery task to process queued requests for a specific provider.
    This task continuously processes requests from the queue when rate limits allow.
    """
    from app.utils.rate_limiter import RateLimiter
    import hashlib

    try:
        logger.info(f"Starting queued request processing for provider: {provider}")

        # Initialize rate limiter
        rate_limiter = RateLimiter(redis_cache.redis_client)

        processed_count = 0
        failed_count = 0
        max_iterations = 100  # Prevent infinite loops

        for _ in range(max_iterations):
            try:
                # Get next queued request
                queued_item = rate_limiter.get_next_queued_request(provider)

                if not queued_item:
                    logger.info(f"No more queued requests for {provider}")
                    break

                request_data = queued_item['data']
                logger.info(f"Processing queued request {queued_item['id']}")

                # Check if we can proceed with API call
                # Use a hash of the API key for tracking (simplified)
                api_key_hash = "default"  # In practice, get from request_data

                can_proceed, queue_length, wait_seconds = rate_limiter.check_api_limits(
                    provider=provider,
                    api_key_hash=api_key_hash
                )

                if not can_proceed:
                    if wait_seconds and wait_seconds > 0:
                        logger.info(f"Still rate limited for {provider}, waiting {wait_seconds}s")
                        # Re-queue the request
                        rate_limiter.queue_request(provider, request_data)
                        break
                    else:
                        logger.warning(f"Cannot proceed with request for {provider}")
                        continue

                # Process the request
                result = process_llm_request.apply(args=[request_data]).get(timeout=300)

                # Record the API call
                rate_limiter.record_api_call(provider, api_key_hash)

                processed_count += 1
                logger.info(f"Successfully processed queued request {queued_item['id']}")

                # Small delay to prevent overwhelming the system
                import time
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to process queued request: {e}")
                failed_count += 1
                continue

        return {
            'success': True,
            'provider': provider,
            'processed_count': processed_count,
            'failed_count': failed_count,
            'remaining_queue': rate_limiter.get_queue_length(provider)
        }

    except Exception as e:
        logger.error(f"Error in queued request processing task: {e}")
        self.update_state(state='FAILURE', meta={'error': str(e)})
        return {
            'success': False,
            'provider': provider,
            'error': str(e)
        }