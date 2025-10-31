#!/usr/bin/env python3
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test():
    server_params = StdioServerParameters(
        command='python',
        args=['/Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent/mcp_server.py'],
        env=None
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Test creating a file
            print('=== Testing File Creation ===')
            try:
                result = await session.call_tool('write_file', {
                    'path': 'sandboxes/sandbox_e4ba318baf5c4856/mcp_test.js',
                    'content': '// MCP Test File\nconsole.log("MCP tools working!");'
                })
                print(f'SUCCESS: {result.content[0].text}')
            except Exception as e:
                print(f'ERROR: {e}')
            
            # Test reading the created file
            print('=== Testing Read Created File ===')
            try:
                result = await session.call_tool('read_file', {'path': 'sandboxes/sandbox_e4ba318baf5c4856/mcp_test.js'})
                print(f'SUCCESS: {result.content[0].text}')
            except Exception as e:
                print(f'ERROR: {e}')
            
            # Test terminal command
            print('=== Testing Terminal Command ===')
            try:
                result = await session.call_tool('run_terminal_command', {
                    'command': 'ls -la mcp_test.js',
                    'working_directory': 'sandboxes/sandbox_e4ba318baf5c4856'
                })
                print(f'SUCCESS: {result.content[0].text}')
            except Exception as e:
                print(f'ERROR: {e}')

if __name__ == "__main__":
    asyncio.run(test())