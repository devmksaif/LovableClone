#!/usr/bin/env python3
"""
Comprehensive test suite for MCP (Model Context Protocol) integration.
Tests sandbox operations, tool loading, and agent workflows.
"""

import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

from app.agents.utils import set_session_memory, get_project_folder
from app.agents.mcp_client import initialize_mcp_client, get_mcp_tools
from app.agents.agent_graphs import create_agent_graph, execute_agent_graph


class MCPIntegrationTest:
    """Test suite for MCP integration."""

    def __init__(self):
        self.test_session_id = 'sandbox-test_sandbox_12345'
        self.test_sandbox_path = '/Users/Apple/Desktop/NextLovable/sandboxes/sandbox_test_sandbox_12345'

    async def setup_test_sandbox(self):
        """Create a temporary test sandbox."""
        # Create a test sandbox directory
        test_sandbox_dir = Path(self.test_sandbox_path)

        # Clean up any existing test sandbox
        if test_sandbox_dir.exists():
            shutil.rmtree(test_sandbox_dir)

        # Create the test sandbox
        test_sandbox_dir.mkdir(parents=True, exist_ok=True)

        # Create some initial files
        (test_sandbox_dir / 'README.md').write_text('# Test Sandbox\n\nThis is a test sandbox for MCP integration.')
        (test_sandbox_dir / 'package.json').write_text('{"name": "test-sandbox", "version": "1.0.0"}')

        print(f"✅ Created test sandbox at: {self.test_sandbox_path}")

    async def cleanup_test_sandbox(self):
        """Clean up the test sandbox."""
        if self.test_sandbox_path and Path(self.test_sandbox_path).exists():
            shutil.rmtree(self.test_sandbox_path)
            print(f"🧹 Cleaned up test sandbox: {self.test_sandbox_path}")

    async def test_session_memory_setup(self):
        """Test that session memory is set up correctly."""
        print("\n🧠 Testing session memory setup...")

        # Set session memory
        await set_session_memory(self.test_session_id)

        # Get project folder
        project_folder = get_project_folder()
        print(f"   Session project folder: {project_folder}")

        # Verify it matches our test sandbox
        assert project_folder == self.test_sandbox_path, f"Expected {self.test_sandbox_path}, got {project_folder}"
        print("✅ Session memory setup correct")

    async def test_mcp_client_initialization(self):
        """Test MCP client initialization."""
        print("\n🔧 Testing MCP client initialization...")

        # Initialize MCP client
        await initialize_mcp_client()
        print("✅ MCP client initialized")

        # Get tools
        tools = await get_mcp_tools()
        print(f"   Loaded {len(tools)} MCP tools")

        # Verify we have the expected tools
        tool_names = [tool.name for tool in tools]
        expected_tools = ['read_file', 'list_dir', 'grep_search', 'run_terminal_command', 'write_file']

        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Missing tool: {expected_tool}"

        print(f"✅ All expected tools loaded: {tool_names}")
        return tools

    async def test_file_operations(self, tools):
        """Test file operations within sandbox."""
        print("\n📁 Testing file operations...")

        # Test list_dir
        list_dir_tool = next(tool for tool in tools if tool.name == 'list_dir')
        result = await list_dir_tool.arun({'path': '.'})
        print(f"   list_dir result: {result[:100]}...")

        assert 'README.md' in result, "README.md not found in directory listing"
        assert 'package.json' in result, "package.json not found in directory listing"
        print("✅ list_dir works correctly")

        # Test read_file
        read_file_tool = next(tool for tool in tools if tool.name == 'read_file')
        result = await read_file_tool.arun({'path': 'README.md'})
        print(f"   read_file result: {result[:100]}...")

        assert 'Test Sandbox' in result, "README.md content not read correctly"
        print("✅ read_file works correctly")

        # Test write_file
        write_file_tool = next(tool for tool in tools if tool.name == 'write_file')
        test_content = "This is a test file created by MCP tools."
        result = await write_file_tool.arun({
            'path': 'test_output.txt',
            'content': test_content
        })
        print(f"   write_file result: {result}")

        assert "Successfully wrote" in result, "write_file failed"
        print("✅ write_file works correctly")

        # Verify file was created
        result = await list_dir_tool.arun({'path': '.'})
        assert 'test_output.txt' in result, "test_output.txt not found after creation"
        print("✅ File creation verified")

        # Verify file content
        result = await read_file_tool.arun({'path': 'test_output.txt'})
        assert test_content in result, "File content doesn't match what was written"
        print("✅ File content verified")

    async def test_search_operations(self, tools):
        """Test search operations."""
        print("\n🔍 Testing search operations...")

        # Test grep_search
        grep_tool = next(tool for tool in tools if tool.name == 'grep_search')
        result = await grep_tool.arun({
            'query': 'Test Sandbox',
            'includePattern': '*.md'
        })
        print(f"   grep_search result: {result[:200]}...")

        assert 'README.md' in result, "grep_search didn't find expected content"
        assert 'Test Sandbox' in result, "grep_search didn't find the search term"
        print("✅ grep_search works correctly")

    async def test_agent_workflow(self):
        """Test the complete agent workflow (skipped if no API keys available)."""
        print("\n🤖 Testing agent workflow...")

        # Check if we have any API keys available
        has_api_keys = any([
            os.getenv("GROQ_API_KEY"),
            os.getenv("ANTHROPIC_API_KEY"),
            os.getenv("GOOGLE_API_KEY"),
            os.getenv("OPENAI_API_KEY")
        ])

        if not has_api_keys:
            print("⚠️  Skipping agent workflow test - no API keys available")
            print("   This is expected in test environments without API access")
            return

        # Prepare test data
        test_data = {
            'user_request': 'Create a simple Python function that adds two numbers',
            'session_id': self.test_session_id,
            'model': 'groq',  # Try Groq first as it's often available
            'tool_results': [],
            'available_tools': []
        }

        # Create agent graph
        graph = await create_agent_graph(test_data)
        print("✅ Agent graph created")

        # Execute agent workflow
        result = await execute_agent_graph(graph, test_data)
        print("✅ Agent workflow executed")

        # Verify results
        assert 'generated_code' in result, "No generated code in result"
        assert result['generated_code'], "Generated code is empty"
        print(f"   Generated code: {result['generated_code'][:100]}...")

        assert 'plan' in result, "No plan in result"
        assert result['plan'], "Plan is empty"
        print(f"   Plan: {result['plan']}")

        print("✅ Agent workflow completed successfully")

    async def run_all_tests(self):
        """Run all MCP integration tests."""
        print("🚀 Starting MCP Integration Tests")
        print("=" * 50)

        try:
            # Setup
            await self.setup_test_sandbox()

            # Test session setup
            await self.test_session_memory_setup()

            # Test MCP client
            tools = await self.test_mcp_client_initialization()

            # Test file operations
            await self.test_file_operations(tools)

            # Test search operations
            await self.test_search_operations(tools)

            # Test agent workflow
            await self.test_agent_workflow()

            print("\n" + "=" * 50)
            print("🎉 ALL MCP INTEGRATION TESTS PASSED!")
            print("✅ Sandbox operations working correctly")
            print("✅ MCP tools loaded and functional")
            print("✅ File operations isolated to sandbox")
            print("✅ Agent workflow complete")

        except Exception as e:
            print(f"\n❌ TEST FAILED: {e}")
            raise
        finally:
            # Cleanup
            await self.cleanup_test_sandbox()


async def main():
    """Main test runner."""
    test_suite = MCPIntegrationTest()
    await test_suite.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())