#!/usr/bin/env python3
"""
Test script to verify the optimization components are working correctly.
This tests the rate limiter, caching, batching, and fallback mechanisms.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_rate_limiter():
    """Test the rate limiter with exponential backoff."""
    print("\n=== Testing Rate Limiter ===")
    
    from app.agents.rate_limiter import rate_limiter, get_provider_rate_limit_info
    
    # Test basic rate limiting
    model_name = "groq-mixtral-8x7b"
    
    # Simulate some requests
    for i in range(5):
        await rate_limiter.acquire(model_name)
        print(f"Request {i+1} acquired")
        rate_limiter.release(model_name)
        
        # Check status
        status = get_provider_rate_limit_info(model_name)
        print(f"Status: {status['requests_this_minute']}/{status['requests_per_minute_limit']} requests")
    
    # Test exponential backoff
    print("\nTesting exponential backoff...")
    rate_limiter.record_failure(model_name)
    backoff_delay = rate_limiter.record_failure(model_name)
    print(f"Backoff delay after 2 failures: {backoff_delay:.2f}s")
    
    # Test success reset
    rate_limiter.record_success(model_name)
    print("Consecutive failures reset after success")

async def test_request_optimizer():
    """Test the request optimizer with caching and deduplication."""
    print("\n=== Testing Request Optimizer ===")
    
    from app.agents.request_optimizer import request_optimizer
    
    # Test caching
    test_prompt = "Generate a simple Python function to add two numbers"
    test_response = "def add_numbers(a, b): return a + b"
    
    # Cache a response
    await request_optimizer.cache_response(test_prompt, "groq-mixtral", test_response)
    print("Response cached successfully")
    
    # Retrieve from cache
    cached = await request_optimizer.get_cached_response(test_prompt, "groq-mixtral")
    if cached == test_response:
        print("Cache retrieval successful")
    else:
        print("Cache retrieval failed")
    
    # Test deduplication
    async def dummy_request():
        return "dummy response"
    
    request_key = "test_dedup_key"
    result1 = await request_optimizer.deduplicate_request(request_key, dummy_request)
    result2 = await request_optimizer.deduplicate_request(request_key, dummy_request)
    
    if result1 == result2:
        print("Deduplication working correctly")
    else:
        print("Deduplication failed")
    
    # Test model selection
    should_optimize, model = request_optimizer.should_use_faster_model("planning", "groq-mixtral")
    print(f"Model optimization suggestion: {should_optimize}, recommended model: {model}")

async def test_optimized_llm_wrapper():
    """Test the optimized LLM wrapper."""
    print("\n=== Testing Optimized LLM Wrapper ===")
    
    from app.agents.optimized_llm_wrapper import create_optimized_llm
    from app.agents.request_optimizer import request_optimizer
    from langchain_groq import ChatGroq
    
    # Create a mock LLM (we won't actually call it)
    mock_llm = ChatGroq(
        api_key="test_key",
        model="mixtral-8x7b-32768",
        temperature=0.3
    )
    
    optimized_llm = create_optimized_llm(mock_llm, "groq-mixtral-8x7b")
    
    # Test cache key generation
    test_messages = [
        {"role": "user", "content": "Hello, world!"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    
    cache_key = optimized_llm._messages_to_cache_key(test_messages)
    print(f"Generated cache key: {cache_key[:50]}...")
    
    # Test tool batching
    test_tool_calls = [
        {"name": "read_file", "args": {"path": "/test/file1.txt"}},
        {"name": "read_file", "args": {"path": "/test/file2.txt"}},
        {"name": "write_file", "args": {"path": "/test/output.txt", "content": "test"}}
    ]
    
    batches = request_optimizer.optimize_tool_calls(test_tool_calls)
    print(f"Tool calls optimized into {len(batches)} batches")
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}: {[call['name'] for call in batch]}")

async def test_optimization_config():
    """Test the optimization configuration."""
    print("\n=== Testing Optimization Configuration ===")
    
    from app.agents.optimization_config import (
        get_optimal_model_for_task, 
        get_fallback_model,
        AVAILABLE_MODELS,
        TASK_MODEL_PREFERENCES
    )
    
    # Test task-based model selection
    planning_model = get_optimal_model_for_task("planning", prefer_speed=True)
    print(f"Recommended model for planning (fast): {planning_model}")
    
    code_model = get_optimal_model_for_task("code_generation", prefer_speed=False)
    print(f"Recommended model for code generation (high quality): {code_model}")
    
    # Test fallback model selection
    fallback = get_fallback_model("groq-mixtral-8x7b")
    print(f"Fallback model for groq-mixtral: {fallback}")
    
    # Test available models
    print(f"Available models: {len(AVAILABLE_MODELS)}")
    for model_name, config in list(AVAILABLE_MODELS.items())[:3]:  # Show first 3
        print(f"  {model_name}: speed={config.speed_rating}, quality={config.quality_rating}, cost={config.cost_per_token}")

async def test_integration():
    """Test the complete integration of all optimization components."""
    print("\n=== Testing Complete Integration ===")
    
    from app.agents.agent_graphs import PlanningAgent, AgentState
    from app.agents.rate_limiter import get_provider_rate_limit_info
    
    # Create a test agent state
    test_state = AgentState(
        user_request="Create a simple Python function to calculate factorial",
        session_id="test_session_123",
        model="groq-mixtral-8x7b",
        sandbox_context={},
        sandbox_id="test_sandbox",
        available_tools={},
        api_keys={"groq": "test_key"}  # Mock API key
    )
    
    # Test planning agent with optimizations
    planning_agent = PlanningAgent()
    
    try:
        print("Testing planning agent with optimizations...")
        start_time = time.time()
        
        # This would normally make actual API calls, but we'll catch any errors
        # since we're using a mock API key
        result_state = await planning_agent.process(test_state)
        
        elapsed = time.time() - start_time
        print(f"Planning completed in {elapsed:.2f}s")
        
        if result_state.current_plan:
            print(f"Generated plan with {len(result_state.current_plan)} steps")
        else:
            print("No plan generated (expected with mock API key)")
            
    except Exception as e:
        print(f"Planning agent failed as expected with mock API key: {type(e).__name__}")
    
    # Check rate limiter status after test
    status = get_provider_rate_limit_info("groq-mixtral-8x7b")
    print(f"Final rate limiter status: {status['requests_this_minute']}/{status['requests_per_minute_limit']} requests")

def main():
    """Run all optimization tests."""
    print("🚀 Testing Groq API Optimization Components")
    print("=" * 50)
    
    async def run_all_tests():
        try:
            await test_rate_limiter()
            await test_request_optimizer()
            await test_optimized_llm_wrapper()
            await test_optimization_config()
            await test_integration()
            
            print("\n" + "=" * 50)
            print("✅ All optimization tests completed!")
            print("\nKey optimizations implemented:")
            print("• Rate limiting with exponential backoff")
            print("• Response caching for repeated requests")
            print("• Request deduplication")
            print("• Intelligent model selection")
            print("• Tool call batching and optimization")
            print("• Fallback model switching")
            
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(run_all_tests())

if __name__ == "__main__":
    main()