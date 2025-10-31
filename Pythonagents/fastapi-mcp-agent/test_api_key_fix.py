#!/usr/bin/env python3
"""
Test script to verify API key passing through the agent creation chain.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.agents.agent_graphs import create_agent_instances

async def test_api_key_passing():
    """Test that API keys are properly passed through the creation chain."""
    # Test API keys
    test_api_keys = {
        'groq': 'test-groq-key',
        'openai': 'test-openai-key',
        'gemini': 'test-gemini-key',
        'openrouter': 'test-openrouter-key'
    }

    print("Testing API key passing...")
    print(f"Input API keys: {test_api_keys}")

    try:
        # Create agent instances with test API keys
        result = await create_agent_instances(
            model='groq-openai/gpt-oss-120b',
            session_id='test-session',
            api_keys=test_api_keys
        )

        print("✓ Agent instances created successfully")
        print(f"✓ Planning agent created: {type(result['planning_agent'])}")
        print(f"✓ Code gen agent created: {type(result['code_gen_agent'])}")
        print(f"✓ Review agent created: {type(result['review_agent'])}")

        return True

    except Exception as e:
        print(f"✗ Error creating agent instances: {e}")
        return False

if __name__ == "__main__":
    import asyncio
    success = asyncio.run(test_api_key_passing())
    sys.exit(0 if success else 1)