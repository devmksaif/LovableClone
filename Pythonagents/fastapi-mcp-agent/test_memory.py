#!/usr/bin/env python3
"""
Test script for memory functionality in the agent system.
Tests semantic, episodic, and procedural memory operations.
"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from agents.agent_graphs import (
    get_memory_store,
    store_user_profile,
    get_user_profile,
    store_agent_experience,
    search_user_memories,
    update_agent_instructions
)

async def test_memory_operations():
    """Test all memory operations."""
    print("Testing memory operations...")

    # Test user ID
    user_id = "test_user_123"

    try:
        # Test 1: Store and retrieve user profile (semantic memory)
        print("\n1. Testing semantic memory (user profile)...")
        profile_data = {
            "name": "Test User",
            "preferences": {
                "code_style": "pythonic",
                "framework": "fastapi",
                "code_review_preferences": "detailed"
            },
            "experience_level": "intermediate"
        }

        await store_user_profile(user_id, profile_data)
        print("✓ Stored user profile")

        retrieved_profile = await get_user_profile(user_id)
        print(f"✓ Retrieved profile: {retrieved_profile}")

        assert retrieved_profile["name"] == "Test User"
        assert retrieved_profile["preferences"]["code_style"] == "pythonic"
        print("✓ Profile data matches")

        # Test 2: Store agent experiences (episodic memory)
        print("\n2. Testing episodic memory (agent experiences)...")
        experience_data = {
            "action": "code_generation",
            "request": "Create a simple API endpoint",
            "success": True,
            "code_length": 150,
            "timestamp": "2024-01-15T10:30:00Z"
        }

        await store_agent_experience(user_id, experience_data, "session_123")
        print("✓ Stored agent experience")

        # Test 3: Search memories
        print("\n3. Testing memory search...")
        search_results = await search_user_memories(user_id, "code_generation", "experiences", limit=5)
        print(f"✓ Found {len(search_results)} experiences")

        assert len(search_results) > 0
        assert search_results[0]["value"]["action"] == "code_generation"
        print("✓ Search results contain expected data")

        # Test 4: Update agent instructions (procedural memory)
        print("\n4. Testing procedural memory (agent instructions)...")
        instructions_data = {
            "planning_instructions": "Always explore the sandbox first",
            "code_gen_instructions": "Use type hints and docstrings",
            "review_instructions": "Check for security vulnerabilities"
        }

        await update_agent_instructions(user_id, instructions_data)
        print("✓ Updated agent instructions")

        # Test 5: Retrieve updated instructions
        print("\n5. Testing instruction retrieval...")
        # Instructions are stored in profile, so let's check if they're there
        updated_profile = await get_user_profile(user_id)
        print(f"✓ Updated profile: {updated_profile}")

        print("\n✅ All memory operations completed successfully!")

    except Exception as e:
        print(f"\n❌ Memory test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_memory_operations())
    sys.exit(0 if success else 1)