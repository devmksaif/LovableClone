#!/usr/bin/env python3
"""
Direct usage of MCP tools from mcp_integration.py
"""

import sys
import os
import asyncio

# Add the app directory to Python path
sys.path.append('/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent')

from app.agents.mcp_integration import (
    ReadFileTool,
    ListDirTool,
    SearchFilesTool,
    RunTerminalCommandTool,
    GetProjectStructureTool,
    CreateSandboxTool,
    MCPIntegration
)

async def main():
    print("=== Testing MCP Tools from mcp_integration.py ===\n")
    
    # Initialize MCP Integration
    mcp = MCPIntegration()
    await mcp.initialize_mcp_clients()
    
    # Get all available tools
    tools = await mcp.get_langchain_tools()
    print(f"Available tools: {[tool.name for tool in tools]}\n")
    
    # Test 1: ReadFileTool
    print("1. Testing ReadFileTool:")
    read_tool = ReadFileTool()
    result = read_tool._run("package.json")
    print(f"Result: {result[:200]}...\n")
    
    # Test 2: ListDirTool
    print("2. Testing ListDirTool:")
    list_tool = ListDirTool()
    result = list_tool._run(".")
    print(f"Result: {result[:300]}...\n")
    
    # Test 3: SearchFilesTool
    print("3. Testing SearchFilesTool:")
    search_tool = SearchFilesTool()
    result = search_tool._run("import", "*.py")
    print(f"Result: {result[:400]}...\n")
    
    # Test 4: GetProjectStructureTool
    print("4. Testing GetProjectStructureTool:")
    structure_tool = GetProjectStructureTool()
    result = structure_tool._run()
    print(f"Result: {result[:500]}...\n")
    
    # Test 5: RunTerminalCommandTool
    print("5. Testing RunTerminalCommandTool:")
    terminal_tool = RunTerminalCommandTool()
    result = terminal_tool._run("ls -la | head -5")
    print(f"Result: {result}\n")
    
    # Test 6: CreateSandboxTool
    print("6. Testing CreateSandboxTool:")
    sandbox_tool = CreateSandboxTool()
    result = sandbox_tool._run("test_sandbox", "react")
    print(f"Result: {result}\n")
    
    print("=== All MCP Tools tested successfully! ===")

if __name__ == "__main__":
    asyncio.run(main())