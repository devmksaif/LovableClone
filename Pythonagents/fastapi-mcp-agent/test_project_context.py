#!/usr/bin/env python3
"""
Test script to verify project directory context and path resolution.
"""

import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_project_context():
    """Test project directory context and path resolution."""
    
    server_params = StdioServerParameters(
        command="python",
        args=["/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent/mcp_server.py"],
        env=None
    )
    
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                logger.info("=== Testing Project Directory Context ===")
                
                # Test 1: Get project structure to see current working directory
                logger.info("\n--- Test 1: Get Project Structure ---")
                try:
                    result = await session.call_tool("get_project_structure", {"max_depth": 2})
                    logger.info(f"Project structure (first 500 chars): {result.content[0].text[:500]}...")
                except Exception as e:
                    logger.error(f"Error getting project structure: {e}")
                
                # Test 2: List current directory
                logger.info("\n--- Test 2: List Current Directory ---")
                try:
                    result = await session.call_tool("list_dir", {"path": "."})
                    logger.info(f"Current directory contents: {result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error listing current directory: {e}")
                
                # Test 3: Check if we can access the parent NextLovable directory
                logger.info("\n--- Test 3: Check Parent Directory Access ---")
                try:
                    result = await session.call_tool("list_dir", {"path": "../.."})
                    logger.info(f"Parent directory contents: {result.content[0].text[:300]}...")
                except Exception as e:
                    logger.error(f"Error accessing parent directory: {e}")
                
                # Test 4: Try to access sandboxes from the correct path
                logger.info("\n--- Test 4: Access Sandboxes from Correct Path ---")
                try:
                    result = await session.call_tool("list_dir", {"path": "../../sandboxes"})
                    logger.info(f"Sandboxes directory: {result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error accessing sandboxes: {e}")
                
                # Test 5: Read a file from the correct sandbox path
                logger.info("\n--- Test 5: Read File from Correct Sandbox Path ---")
                try:
                    result = await session.call_tool("read_file", {"path": "../../sandboxes/sandbox_e4ba318baf5c4856/package.json"})
                    logger.info(f"Package.json content: {result.content[0].text}")
                except Exception as e:
                    logger.error(f"Error reading package.json: {e}")
                
                # Test 6: Check if we can access the main NextLovable project files
                logger.info("\n--- Test 6: Access Main Project Files ---")
                try:
                    result = await session.call_tool("read_file", {"path": "../../package.json"})
                    logger.info(f"Main package.json found, length: {len(result.content[0].text)} characters")
                except Exception as e:
                    logger.error(f"Error reading main package.json: {e}")
                
                # Test 7: Search for files in the main project
                logger.info("\n--- Test 7: Search Files in Main Project ---")
                try:
                    result = await session.call_tool("grep_search", {"query": "NextLovable", "include_pattern": "*.md"})
                    logger.info(f"Search results: {result.content[0].text[:300]}...")
                except Exception as e:
                    logger.error(f"Error searching files: {e}")
                
                logger.info("\n=== Project Context Testing Complete ===")
                
    except Exception as e:
        logger.error(f"Failed to connect to MCP server: {e}")

if __name__ == "__main__":
    asyncio.run(test_project_context())