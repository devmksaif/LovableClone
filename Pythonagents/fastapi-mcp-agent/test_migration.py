#!/usr/bin/env python3
"""
Test script to validate the migrated TypeScript to Python agent system.
Tests basic imports and functionality without requiring API keys.
"""

import sys
import os
sys.path.insert(0, '/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent')

# Mock the MCP integration to avoid import errors
from unittest.mock import MagicMock

mock_mcp_integration = MagicMock()
mock_mcp_integration.MCPIntegration = MagicMock
mock_mcp_integration.mcp_integration = MagicMock()
sys.modules['app.agents.mcp_integration'] = mock_mcp_integration

def test_imports():
    """Test that all modules can be imported."""
    print("Testing Python agent system imports...")

    try:
        # Test model providers
        from app.agents.model_providers import create_llm, get_model_name
        print("✓ model_providers imported successfully")

        # Test tools
        from app.agents.tools import read_file_tool, write_file_tool, set_session_context
        print("✓ tools imported successfully")

        # Test streaming agents
        from app.agents.streaming_agents import intent_analysis_agent, emit_step_progress
        print("✓ streaming_agents imported successfully")

        # Test agent core
        from app.agents.agent_core import AgentState, AgentGraph, create_agent_graph
        print("✓ agent_core imported successfully")

        # Test utils
        from app.agents.utils import set_session_memory, get_project_folder, validate_file_content
        print("✓ utils imported successfully")

        # Test main agent graphs
        from app.agents.agent_graphs import AgentGraph as MainAgentGraph, create_agent_graph as main_create_graph
        print("✓ agent_graphs imported successfully")

        print("\n🎉 All imports successful!")
        return True

    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality without API keys."""
    print("\nTesting basic functionality...")

    try:
        from app.agents.model_providers import get_model_name

        # Test model name mapping
        assert get_model_name("groq-mixtral-8x7b") == "mixtral-8x7b-32768"
        assert get_model_name("unknown-model") == "unknown-model"
        print("✓ Model name mapping works")

        from app.agents.utils import validate_file_content

        # Test file validation
        valid_result = validate_file_content("test.py", "print('Hello, World!')")
        assert valid_result["isValid"] == True

        invalid_result = validate_file_content("test.py", "...")
        assert invalid_result["isValid"] == False
        print("✓ File validation works")

        from app.agents.agent_core import AgentState

        # Test agent state
        state = AgentState(user_request="Test request", session_id="test-123")
        assert state.user_request == "Test request"
        assert state.session_id == "test-123"
        print("✓ Agent state works")

        print("\n🎉 Basic functionality tests passed!")
        return True

    except Exception as e:
        print(f"❌ Functionality test error: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Testing Migrated TypeScript to Python Agent System")
    print("=" * 60)

    success = True

    # Test imports
    if not test_imports():
        success = False

    # Test basic functionality
    if not test_basic_functionality():
        success = False

    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests passed! Python agent system migration successful.")
        print("\nNext steps:")
        print("1. Install required packages: pip install langchain-core langchain-openai langchain-anthropic langchain-google-genai langchain-groq pydantic fastapi uvicorn")
        print("2. Set up API keys as environment variables")
        print("3. Test with actual LLM providers")
        print("4. Integrate with MCP servers")
    else:
        print("❌ Some tests failed. Check the errors above.")

    return success

if __name__ == "__main__":
    main()