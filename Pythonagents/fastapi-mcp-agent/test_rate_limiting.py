#!/usr/bin/env python3
"""
Test script for the advanced rate limiting system.
Tests concurrent requests and provider-specific rate limits.
"""

import asyncio
import time
import logging
from app.agents.rate_limiter import with_rate_limit, get_provider_rate_limit_info, rate_limiter

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def simulate_request(model_name: str, request_id: int, duration: float = 0.1):
    """Simulate a request with rate limiting."""
    start_time = time.time()
    try:
        async with with_rate_limit(model_name):
            logger.info(f"Request {request_id} for {model_name} started")
            await asyncio.sleep(duration)  # Simulate processing time
            logger.info(f"Request {request_id} for {model_name} completed")
            return True
    except Exception as e:
        logger.error(f"Request {request_id} for {model_name} failed: {e}")
        return False
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Request {request_id} for {model_name} took {elapsed:.2f}s")

async def test_concurrent_requests():
    """Test multiple concurrent requests to verify rate limiting."""
    logger.info("Starting concurrent request test...")

    # Test different models
    models = [
        "groq-mixtral-8x7b",
        "openai-gpt-4",
        "anthropic-claude-3",
        "gemini-2.0-flash"
    ]

    # Create multiple concurrent requests for each model
    tasks = []
    for model in models:
        for i in range(5):  # 5 requests per model
            task = simulate_request(model, i + 1, 0.05)
            tasks.append(task)

    # Execute all requests concurrently
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    total_time = time.time() - start_time

    # Analyze results
    successful = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if isinstance(r, Exception) or r is False)

    logger.info(f"Test completed in {total_time:.2f}s")
    logger.info(f"Successful requests: {successful}")
    logger.info(f"Failed requests: {failed}")
    logger.info(f"Total requests: {len(results)}")

    # Check rate limit status
    for model in models:
        info = get_provider_rate_limit_info(model)
        logger.info(f"Rate limit info for {model}: {info}")

    return successful, failed

async def test_sequential_requests():
    """Test sequential requests to verify proper queuing."""
    logger.info("Starting sequential request test...")

    model = "groq-mixtral-8x7b"  # Fast provider for testing

    # Make many sequential requests
    successful = 0
    failed = 0

    for i in range(10):
        result = await simulate_request(model, i + 1, 0.01)
        if result:
            successful += 1
        else:
            failed += 1

    logger.info(f"Sequential test: {successful} successful, {failed} failed")

    # Check final rate limit status
    info = get_provider_rate_limit_info(model)
    logger.info(f"Final rate limit info: {info}")

    return successful, failed

async def test_caching():
    """Test response caching functionality."""
    logger.info("Starting caching test...")

    # Test data
    input_text = "def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)"
    model_name = "groq-mixtral-8x7b"
    user_id = "test_user"

    # Generate cache key
    cache_key = rate_limiter.get_cache_key(input_text, model_name, user_id)

    # First call should execute and cache
    async def mock_llm_call(**kwargs):
        await asyncio.sleep(0.01)  # Simulate API call
        return "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)"

    start_time = time.time()
    result1 = await rate_limiter.execute_with_caching(mock_llm_call, cache_key, model_name=model_name)
    first_call_time = time.time() - start_time

    # Second call should use cache
    start_time = time.time()
    result2 = await rate_limiter.execute_with_caching(mock_llm_call, cache_key, model_name=model_name)
    second_call_time = time.time() - start_time

    # Results should be identical
    assert result1 == result2, "Cached result should match original"

    # Second call should be much faster (cached)
    assert second_call_time < first_call_time * 0.5, f"Cache should be faster: {second_call_time} vs {first_call_time}"

    logger.info(f"✅ Caching test passed: {first_call_time:.3f}s vs {second_call_time:.3f}s")
    return True

async def test_token_bucket():
    """Test token bucket rate limiting."""
    logger.info("Starting token bucket test...")

    model_name = "groq-mixtral-8x7b"
    provider = rate_limiter.get_provider_from_model(model_name)

    # Get initial token count
    initial_tokens = rate_limiter.token_buckets[provider]["tokens"]
    logger.info(f"Initial tokens: {initial_tokens}")

    # Consume some tokens
    consumed = 0
    for i in range(5):
        if rate_limiter._consume_token(provider):
            consumed += 1
        else:
            break

    logger.info(f"Consumed {consumed} tokens")

    # Check tokens decreased
    current_tokens = rate_limiter.token_buckets[provider]["tokens"]
    assert current_tokens < initial_tokens, "Tokens should decrease after consumption"

    # Wait for refill
    await asyncio.sleep(1)  # Wait 1 second for refill

    # Check tokens refilled
    rate_limiter._refill_token_bucket(provider)
    refilled_tokens = rate_limiter.token_buckets[provider]["tokens"]
    assert refilled_tokens > current_tokens, f"Tokens should refill: {current_tokens} -> {refilled_tokens}"

    logger.info(f"✅ Token bucket test passed: {current_tokens} -> {refilled_tokens}")
    return True

async def test_backoff_retry():
    """Test exponential backoff on failures."""
    logger.info("Starting backoff test...")

    model_name = "groq-mixtral-8x7b"
    provider = rate_limiter.get_provider_from_model(model_name)

    # Simulate failures
    initial_failures = rate_limiter.consecutive_failures[provider]

    for i in range(3):
        delay = rate_limiter.record_failure(model_name)
        logger.info(f"Failure {i+1}: backoff delay {delay:.2f}s")

    # Check backoff increased
    final_failures = rate_limiter.consecutive_failures[provider]
    assert final_failures == initial_failures + 3, "Failure count should increase"

    # Reset on success
    rate_limiter.record_success(model_name)
    assert rate_limiter.consecutive_failures[provider] == 0, "Success should reset failure count"

    logger.info("✅ Backoff test passed")
    return True

async def main():
    """Run all rate limiting tests."""
    logger.info("=== Advanced Rate Limiting Test Suite ===")

    try:
        # Test 1: Concurrent requests
        logger.info("\n--- Test 1: Concurrent Requests ---")
        concurrent_success, concurrent_fail = await test_concurrent_requests()

        # Test 2: Sequential requests
        logger.info("\n--- Test 2: Sequential Requests ---")
        sequential_success, sequential_fail = await test_sequential_requests()

        # Test 3: Caching
        logger.info("\n--- Test 3: Response Caching ---")
        await test_caching()

        # Test 4: Token Bucket
        logger.info("\n--- Test 4: Token Bucket Algorithm ---")
        await test_token_bucket()

        # Test 5: Backoff Retry
        logger.info("\n--- Test 5: Exponential Backoff ---")
        await test_backoff_retry()

        # Summary
        total_success = concurrent_success + sequential_success
        total_fail = concurrent_fail + sequential_fail

        logger.info("\n=== Test Summary ===")
        logger.info(f"Total successful requests: {total_success}")
        logger.info(f"Total failed requests: {total_fail}")
        logger.info(f"Success rate: {(total_success / (total_success + total_fail) * 100):.1f}%")

        if total_fail == 0:
            logger.info("✅ All tests passed! Rate limiting is working correctly.")
        else:
            logger.warning(f"⚠️  {total_fail} requests failed. Check rate limiting configuration.")

    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())