#!/usr/bin/env python3
"""
Demo script for the React Agent implementation using langgraph.prebuilt

This script demonstrates how to create and use a React agent with local tools.
"""

import asyncio
import os
from app.agents.agent_graphs import create_react_agent_with_tools, demo_react_agent
from app.agents.local_tools import LOCAL_TOOLS


async def test_agent_structure():
    """Test that the React agent is properly structured."""
    print("=== Testing React Agent Structure ===")

    try:
        # This will fail without API keys, but shows the structure
        agent = create_react_agent_with_tools('groq/mixtral-8x7b-32768')
        print("✓ Agent creation would succeed with valid API keys")

    except Exception as e:
        print(f"Expected error without API keys: {e}")

    # Show available tools
    print(f"\n=== Available Tools ({len(LOCAL_TOOLS)}) ===")
    for i, tool in enumerate(LOCAL_TOOLS, 1):
        print(f"{i}. {tool.name}")
        print(f"   {tool.description}")
        print()


def show_usage_examples():
    """Show usage examples for the React agent."""
    print("=== React Agent Usage Examples ===")
    print("""
# Basic usage with default local tools
from app.agents.agent_graphs import create_react_agent_with_tools

agent = create_react_agent_with_tools('groq/mixtral-8x7b-32768')

# Run a query
result = await agent.ainvoke({
    'messages': [{'role': 'user', 'content': 'What files are in the current directory?'}]
})

# With custom tools
from my_tools import custom_tool1, custom_tool2

agent = create_react_agent_with_tools(
    'openai/gpt-4',
    tools=[custom_tool1, custom_tool2]
)

# With explicit API keys
agent = create_react_agent_with_tools(
    'anthropic/claude-3-sonnet-20240229',
    api_keys={'anthropic': 'your-anthropic-key'}
)
""")


async def main():
    """Main demo function."""
    print("LangGraph React Agent Demo")
    print("=" * 40)

    # Test agent structure
    await test_agent_structure()

    # Show usage examples
    show_usage_examples()

    # Try to run demo if API keys are available
    api_keys_available = any([
        os.getenv('GROQ_API_KEY'),
        os.getenv('OPENAI_API_KEY'),
        os.getenv('ANTHROPIC_API_KEY'),
        os.getenv('GOOGLE_API_KEY')
    ])

    if api_keys_available:
        print("\n=== Running Live Demo ===")
        print("API keys detected, running demo...")
        await demo_react_agent()
    else:
        print("\n=== Demo Skipped ===")
        print("No API keys found. Set environment variables to run live demo:")
        print("- GROQ_API_KEY")
        print("- OPENAI_API_KEY")
        print("- ANTHROPIC_API_KEY")
        print("- GOOGLE_API_KEY")


if __name__ == "__main__":
    asyncio.run(main())