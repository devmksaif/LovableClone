#!/usr/bin/env python3
"""
Test script for agent graphs with multiple model providers.
This tests the agent graph functionality without MCP dependencies.
"""

import os
import sys
import asyncio
from typing import Dict, Any

# Add the app directory to the path
sys.path.insert(0, '/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent')

# Now import the agent graphs
from app.agents.agent_graphs import AgentState, AgentGraph, create_agent_graph, execute_agent_graph

async def test_agent_graph():
    """Test the agent graph with different model configurations."""

    print("Testing Agent Graph with Multiple Model Providers")
    print("=" * 50)

    # Test data
    test_data = {
        "user_request": "Create a simple Python function to calculate fibonacci numbers",
        "session_id": "test-session-123",
        "model": None,  # Will test different models
        "sandbox_context": {},
        "sandbox_id": "test-sandbox",
        "available_tools": ["file_system", "code_execution"],
        "tool_results": []
    }

    # Test cases with different model preferences
    test_cases = [
        {"model": None, "description": "Default model selection"},
        {"model": "groq/mixtral-8x7b-32768", "description": "Groq model"},
        {"model": "anthropic/claude-3-sonnet-20240229", "description": "Anthropic model"},
        {"model": "google/gemini-pro", "description": "Google model"},
        {"model": "openai/gpt-4", "description": "OpenAI model"},
    ]

    for i, test_case in enumerate(test_cases):
        print(f"\nTest {i+1}: {test_case['description']}")
        print("-" * 30)

        # Update test data with model preference
        test_data["model"] = test_case["model"]

        try:
            # Create and execute agent graph
            graph = create_agent_graph({})
            result = await execute_agent_graph(graph, test_data)

            print(f"✓ Agent graph executed successfully")
            print(f"  - Generated code length: {len(result.get('generated_code', ''))}")
            print(f"  - Review feedback length: {len(result.get('review_feedback', ''))}")
            print(f"  - Progress updates: {len(result.get('progress_updates', []))}")

        except Exception as e:
            print(f"✗ Error: {str(e)}")
            # This is expected if API keys are not set
            if "API_KEY" in str(e) or "api key" in str(e).lower():
                print("  (Expected - API key not configured)")

    print("\n" + "=" * 50)
    print("Agent Graph Testing Complete")

if __name__ == "__main__":
    asyncio.run(test_agent_graph())