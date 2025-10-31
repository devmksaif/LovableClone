#!/usr/bin/env python3
"""
Test script to verify MCP tool operations on sandbox directories.
"""

import asyncio
import json
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mcp_tools():
    """Test MCP tools operations on sandbox directories."""
    
    # Server parameters for the centralized MCP server
    server_params = StdioServerParameters(
        command="python",
        args=["/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent/mcp_server.py"],
        env=None
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # List available tools
                logger.info("=== Testing MCP Server Tool Availability ===")
                tools_result = await session.list_tools()
                logger.info(f"Available tools: {len(tools_result.tools)}")
                for tool in tools_result.tools:
                    logger.info(f"  - {tool.name}: {tool.description}")
                
                # Test 1: List sandbox directories
                logger.info("\n=== Test 1: List Sandbox Directories ===")
                try:
                    list_result = await session.call_tool(
                        "list_dir",
                        {"path": "sandboxes"}
                    )
                    logger.info(f"List sandbox result: {list_result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error listing sandbox directories: {e}")
                
                # Test 2: Read a file from sandbox
                logger.info("\n=== Test 2: Read File from Sandbox ===")
                try:
                    read_result = await session.call_tool(
                        "read_file",
                        {"path": "sandboxes/sandbox_e4ba318baf5c4856/package.json"}
                    )
                    logger.info(f"Read file result: {read_result.content[0].text[:200]}...")
                except Exception as e:
                    logger.error(f"Error reading file from sandbox: {e}")
                
                # Test 3: Create a test file in sandbox
                logger.info("\n=== Test 3: Create Test File in Sandbox ===")
                test_content = """// Test file created by MCP tools
console.log("MCP tools are working correctly!");
"""
                try:
                    write_result = await session.call_tool(
                        "write_file",
                        {
                            "path": "sandboxes/sandbox_e4ba318baf5c4856/mcp_test.js",
                            "content": test_content
                        }
                    )
                    logger.info(f"Write file result: {write_result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error writing file to sandbox: {e}")
                
                # Test 4: Verify the test file was created
                logger.info("\n=== Test 4: Verify Test File Creation ===")
                try:
                    verify_result = await session.call_tool(
                        "read_file",
                        {"path": "sandboxes/sandbox_e4ba318baf5c4856/mcp_test.js"}
                    )
                    logger.info(f"Verify file content: {verify_result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error verifying test file: {e}")
                
                # Test 5: Search for files in sandbox
                logger.info("\n=== Test 5: Search Files in Sandbox ===")
                try:
                    search_result = await session.call_tool(
                        "grep_search",
                        {
                            "pattern": "vue",
                            "path": "sandboxes"
                        }
                    )
                    logger.info(f"Search result: {search_result.content[0].text[:300]}...")
                except Exception as e:
                    logger.error(f"Error searching files in sandbox: {e}")
                
                # Test 6: Get project structure
                logger.info("\n=== Test 6: Get Project Structure ===")
                try:
                    structure_result = await session.call_tool(
                        "get_project_structure",
                        {"path": "sandboxes/sandbox_e4ba318baf5c4856"}
                    )
                    logger.info(f"Project structure result: {structure_result.content[0].text[:300]}...")
                except Exception as e:
                    logger.error(f"Error getting project structure: {e}")
                
                # Test 7: Run terminal command in sandbox
                logger.info("\n=== Test 7: Run Terminal Command in Sandbox ===")
                try:
                    cmd_result = await session.call_tool(
                        "run_terminal_command",
                        {
                            "command": "ls -la",
                            "working_directory": "sandboxes/sandbox_e4ba318baf5c4856"
                        }
                    )
                    logger.info(f"Terminal command result: {cmd_result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error running terminal command: {e}")
                
                logger.info("\n=== MCP Tools Testing Complete ===")
                
    except Exception as e:
        logger.error(f"Failed to connect to MCP server: {e}")

if __name__ == "__main__":
    asyncio.run(test_mcp_tools())