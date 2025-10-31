#!/usr/bin/env python3
"""
Simple MCP Filesystem Server
Provides basic file operations for the sandbox environment.
"""

import asyncio
import json
import sys
import os
from pathlib import Path

class SimpleFilesystemServer:
    def __init__(self, allowed_dir):
        self.allowed_dir = Path(allowed_dir).resolve()

    async def list_tools(self):
        return [
            {
                "name": "read_file",
                "description": "Read the contents of a file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the file to read"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "list_dir",
                "description": "List contents of a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the directory to list"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "search_files",
                "description": "Search for files matching a pattern",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern to match"},
                        "path": {"type": "string", "description": "Directory to search in"}
                    },
                    "required": ["pattern"]
                }
            }
        ]

    async def call_tool(self, name, args):
        try:
            if name == "read_file":
                file_path = Path(args["path"]).resolve()
                # Security check - ensure path is within allowed directory
                if not str(file_path).startswith(str(self.allowed_dir)):
                    return {"error": "Access denied: path outside allowed directory"}

                if file_path.exists() and file_path.is_file():
                    content = file_path.read_text()
                    return {"content": content, "path": str(file_path)}
                else:
                    return {"error": "File not found"}

            elif name == "list_dir":
                dir_path = Path(args.get("path", str(self.allowed_dir))).resolve()
                if not str(dir_path).startswith(str(self.allowed_dir)):
                    return {"error": "Access denied: path outside allowed directory"}

                if dir_path.exists() and dir_path.is_dir():
                    items = []
                    for item in dir_path.iterdir():
                        items.append({
                            "name": item.name,
                            "type": "directory" if item.is_dir() else "file",
                            "path": str(item)
                        })
                    return {"items": items, "path": str(dir_path)}
                else:
                    return {"error": "Directory not found"}

            elif name == "search_files":
                import glob
                pattern = args["pattern"]
                search_path = args.get("path", str(self.allowed_dir))
                search_path = Path(search_path).resolve()

                if not str(search_path).startswith(str(self.allowed_dir)):
                    return {"error": "Access denied: path outside allowed directory"}

                matches = []
                for match in search_path.glob(pattern):
                    if match.exists():
                        matches.append(str(match))
                return {"matches": matches, "pattern": pattern}

            else:
                return {"error": f"Unknown tool: {name}"}

        except Exception as e:
            return {"error": str(e)}

async def handle_mcp():
    # Get allowed directory from command line args or use default
    allowed_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
    server = SimpleFilesystemServer(allowed_dir)

    # Read from stdin, write to stdout
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            message = json.loads(line.strip())

            if message.get("method") == "initialize":
                # Send initialize response
                response = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {"listChanged": True}
                        },
                        "serverInfo": {
                            "name": "simple-filesystem-server",
                            "version": "1.0.0"
                        }
                    }
                }
                print(json.dumps(response), flush=True)

            elif message.get("method") == "tools/list":
                tools = await server.list_tools()
                response = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {"tools": tools}
                }
                print(json.dumps(response), flush=True)

            elif message.get("method") == "tools/call":
                result = await server.call_tool(
                    message["params"]["name"],
                    message["params"]["arguments"]
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": result
                }
                print(json.dumps(response), flush=True)

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32000, "message": str(e)}
            }
            print(json.dumps(error_response), flush=True)

if __name__ == "__main__":
    asyncio.run(handle_mcp())