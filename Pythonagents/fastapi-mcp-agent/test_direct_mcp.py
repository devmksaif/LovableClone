#!/usr/bin/env python3
"""
Direct usage of MCP tools from mcp_integration.py
"""

import asyncio
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
    
    # Test 1: ReadFileTool - Read the package.json from project root
    print("1. Testing ReadFileTool:")
    read_tool = ReadFileTool()
    result = read_tool._run("package.json")
    print(f"ReadFileTool result:\n{result}\n")
    print("-" * 50)
    
    # Test 2: ListDirTool - List current directory
    print("2. Testing ListDirTool:")
    list_tool = ListDirTool()
    result = list_tool._run(".")
    print(f"ListDirTool result:\n{result}\n")
    print("-" * 50)
    
    # Test 3: SearchFilesTool - Search for imports in Python files
    print("3. Testing SearchFilesTool:")
    search_tool = SearchFilesTool()
    result = search_tool._run("FastAPI", "*.py")
    print(f"SearchFilesTool result:\n{result}\n")
    print("-" * 50)
    
    # Test 4: GetProjectStructureTool
    print("4. Testing GetProjectStructureTool:")
    structure_tool = GetProjectStructureTool()
    result = structure_tool._run()
    print(f"GetProjectStructureTool result:\n{result}\n")
    print("-" * 50)
    
    # Test 5: RunTerminalCommandTool - Simple ls command
    print("5. Testing RunTerminalCommandTool:")
    terminal_tool = RunTerminalCommandTool()
    result = terminal_tool._run("ls -la")
    print(f"RunTerminalCommandTool result:\n{result}\n")
    print("-" * 50)
    
    # Test 6: CreateSandboxTool
    print("6. Testing CreateSandboxTool:")
    sandbox_tool = CreateSandboxTool()
    result = sandbox_tool._run("test_sandbox", "react")
    print(f"CreateSandboxTool result:\n{result}\n")
    print("-" * 50)
    
    print("=== All MCP Tools tested successfully! ===")

if __name__ == "__main__":
    asyncio.run(main())