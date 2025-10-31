import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
import json

logger = logging.getLogger(__name__)

async def update_sandbox_metadata_if_needed(file_path: str) -> None:
    """Helper function to update sandbox metadata after file operations."""
    try:
        # Get the current session sandbox ID
        from .utils import get_session_memory
        session_data = await get_session_memory()
        
        if session_data and "sandbox_id" in session_data:
            sandbox_id = session_data["sandbox_id"]
            
            # Import sandbox service and update metadata
            from app.sandbox_service import sandbox_service
            await sandbox_service.update_project_metadata(sandbox_id)
            logger.debug(f"Updated metadata for sandbox {sandbox_id} after file operation on {file_path}")
        else:
            logger.debug("No sandbox ID found in session, skipping metadata update")
    except Exception as e:
        logger.warning(f"Failed to update sandbox metadata after file operation: {e}")

class ReadFileTool(BaseTool):
    """Tool for reading file contents."""
    name: str = "read_file"
    description: str = "Read the contents of a file. Use this to examine source code, configuration files, or any text content."

    def _run(self, path: str) -> str:
        """Read file contents synchronously."""
        try:
            # Get the current sandbox directory from session context
            from .utils import get_project_folder
            try:
                sandbox_root = get_project_folder()
            except:
                # Fallback to NextLovable root if no session is set
                current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                sandbox_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to sandbox root for security
            from pathlib import Path
            file_path = Path(sandbox_root) / path.lstrip('/')

            # Basic security check - prevent accessing files outside sandbox
            file_path = file_path.resolve()
            sandbox_root_path = Path(sandbox_root).resolve()

            if not str(file_path).startswith(str(sandbox_root_path)):
                return f"Access denied: Cannot access files outside sandbox directory. Path: {path}"

            if file_path.exists() and file_path.is_file():
                # Check file size (limit to 1MB)
                if file_path.stat().st_size > 1024 * 1024:
                    return f"File too large to read ({file_path.stat().st_size} bytes). Maximum size is 1MB."

                content = file_path.read_text(encoding='utf-8', errors='replace')
                return f"File: {path}\n\n{content}"
            else:
                return f"File not found: {path}"
        except Exception as e:
            return f"Error reading file {path}: {str(e)}"

class ListDirTool(BaseTool):
    """Tool for listing directory contents."""
    name: str = "list_dir"
    description: str = "List the contents of a directory. Use this to explore project structure and find files."

    def _run(self, path: str = ".") -> str:
        """List directory contents synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to project root for security
            from pathlib import Path
            dir_path = Path(project_root) / path.lstrip('/')

            # Basic security check
            dir_path = dir_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(dir_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot access directories outside project directory. Path: {path}"

            if dir_path.exists() and dir_path.is_dir():
                items = []
                for item in sorted(dir_path.iterdir()):
                    item_type = "[DIR]" if item.is_dir() else "[FILE]"
                    size = f"({item.stat().st_size} bytes)" if item.is_file() else ""
                    items.append(f"{item_type} {item.name} {size}")

                result = f"Directory: {path}\n\nContents:\n"
                result += "\n".join(items) if items else "Directory is empty"
                return result
            else:
                return f"Directory not found: {path}"
        except Exception as e:
            return f"Error listing directory {path}: {str(e)}"

class SearchFilesTool(BaseTool):
    """Tool for searching files by pattern."""
    name: str = "grep_search"
    description: str = "Search for text patterns in files using regex. Use this to find specific code or text across the project."

    def _run(self, query: str, includePattern: str = "*") -> str:
        """Search for text in files synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            import glob
            import re

            search_path = Path(project_root)
            results = []

            # Find files matching the pattern
            pattern = str(search_path / "**" / includePattern)
            files = glob.glob(pattern, recursive=True)

            for file_path_str in files[:50]:  # Limit to 50 files
                file_path = Path(file_path_str)

                # Skip common directories
                if any(skip in str(file_path) for skip in ['node_modules', '.git', '__pycache__', '.next']):
                    continue

                try:
                    if file_path.exists() and file_path.is_file():
                        content = file_path.read_text(encoding='utf-8', errors='replace')
                        lines = content.split('\n')

                        for line_num, line in enumerate(lines, 1):
                            if re.search(query, line, re.IGNORECASE):
                                rel_path = file_path.relative_to(search_path)
                                results.append(f"{rel_path}:{line_num}: {line.strip()}")

                                if len(results) >= 100:  # Limit results
                                    break
                except:
                    continue

                if len(results) >= 100:
                    break

            if results:
                return f"Found {len(results)} matches for '{query}':\n\n" + "\n".join(results)
            else:
                return f"No matches found for '{query}' in files matching '{includePattern}'"
        except Exception as e:
            return f"Error searching for '{query}': {str(e)}"

class RunTerminalCommandTool(BaseTool):
    """Tool for running terminal commands safely."""
    name: str = "run_terminal_command"
    description: str = "Run a terminal command in the project directory. Use this for building, testing, or running scripts."

    def _run(self, command: str) -> str:
        """Run terminal command synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            import subprocess
            # Run command with timeout and capture output
            result = subprocess.run(
                command,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )

            output = f"Command: {command}\n"
            output += f"Exit code: {result.returncode}\n\n"

            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"

            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            return output

        except subprocess.TimeoutExpired:
            return f"Command timed out after 30 seconds: {command}"
        except Exception as e:
            return f"Error running command '{command}': {str(e)}"

class GetProjectStructureTool(BaseTool):
    """Tool for getting project structure information."""
    name: str = "get_project_structure"
    description: str = "Get the overall structure of the project including directories and key files."

    def _run(self) -> str:
        """Get project structure synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path

            def get_structure(path, prefix="", max_depth=3, current_depth=0):
                if current_depth > max_depth:
                    return []

                items = []
                try:
                    for item in sorted(Path(path).iterdir()):
                        if item.name.startswith('.') or item.name in ['node_modules', '__pycache__', '.git']:
                            continue

                        if item.is_dir():
                            items.append(f"{prefix}📁 {item.name}/")
                            if current_depth < max_depth:
                                items.extend(get_structure(item, prefix + "  ", max_depth, current_depth + 1))
                        else:
                            # Show important files
                            if any(item.name.endswith(ext) for ext in ['.ts', '.tsx', '.js', '.jsx', '.py', '.json', '.md', '.yml', '.yaml']):
                                items.append(f"{prefix}📄 {item.name}")
                except:
                    pass

                return items

            structure = get_structure(project_root)
            return f"Project Structure:\n\n" + "\n".join(structure)

        except Exception as e:
            return f"Error getting project structure: {str(e)}"

class CreateSandboxTool(BaseTool):
    """Tool for creating development sandboxes."""
    name: str = "create_sandbox"
    description: str = "Create a new development sandbox environment for testing code."

    def _run(self, name: str, type: str = "react") -> str:
        """Create a sandbox synchronously."""
        try:
            # This would integrate with the sandbox manager
            # For now, return a placeholder response
            return f"Created sandbox '{name}' of type '{type}'. Sandbox ID: sandbox_{name.lower().replace(' ', '_')}"
        except Exception as e:
            return f"Error creating sandbox: {str(e)}"

class MCPIntegration:
    """Simplified MCP integration providing essential LangChain tools."""

    def __init__(self):
        self.initialized = False

    async def initialize_mcp_clients(self):
        """Initialize - no external clients needed."""
        if not self.initialized:
            self.initialized = True
            logger.info("MCP integration initialized with built-in tools")

    async def get_langchain_tools(self) -> List[Any]:
        """Get essential LangChain tools for agents."""
        if not self.initialized:
            await self.initialize_mcp_clients()

        # Return the core tools that agents need
        tools = [
            ReadFileTool(),
            ListDirTool(),
            SearchFilesTool(),
            RunTerminalCommandTool(),
            GetProjectStructureTool(),
            CreateSandboxTool()
        ]

        logger.info(f"Loaded {len(tools)} essential LangChain tools for agents")
        return tools

    async def get_available_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get available tools info."""
        tools = await self.get_langchain_tools()
        return {
            "built_in": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "type": "function"
                } for tool in tools
            ]
        }

    async def execute_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool (legacy method)."""
        tools = await self.get_langchain_tools()
        tool = next((t for t in tools if t.name == tool_name), None)
        if tool:
            return tool._run(**arguments)
        raise ValueError(f"Tool {tool_name} not found")

    async def process_chat_request(
        self,
        user_request: str,
        session_id: str,
        model: str,
        sandbox_context: Dict[str, Any],
        sandbox_id: str
    ) -> Dict[str, Any]:
        """Process chat request (legacy method)."""
        # Set session memory to establish sandbox context for MCP tools
        from .utils import set_session_memory
        await set_session_memory(session_id)
        
        return {
            "user_request": user_request,
            "session_id": session_id,
            "model": model,
            "sandbox_context": sandbox_context,
            "sandbox_id": sandbox_id,
            "processed": True
        }

# Global MCP integration instance
mcp_integration = MCPIntegration()

async def initialize_mcp_clients():
    """Initialize MCP clients (called during app startup)."""
    await mcp_integration.initialize_mcp_clients()

async def process_chat_request(
    user_request: str,
    session_id: str,
    model: str,
    sandbox_context: Dict[str, Any],
    sandbox_id: str
) -> Dict[str, Any]:
    """Process chat request using MCP integration."""
    return await mcp_integration.process_chat_request(
        user_request, session_id, model, sandbox_context, sandbox_id
    )
 
class ListDirTool(BaseTool):
    """Tool for listing directory contents."""
    name: str = "list_dir"
    description: str = "List the contents of a directory. Use this to explore project structure and find files."

    def _run(self, path: str = ".") -> str:
        """List directory contents synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to project root for security
            from pathlib import Path
            dir_path = Path(project_root) / path.lstrip('/')

            # Basic security check
            dir_path = dir_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(dir_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot access directories outside project directory. Path: {path}"

            if dir_path.exists() and dir_path.is_dir():
                items = []
                for item in sorted(dir_path.iterdir()):
                    item_type = "[DIR]" if item.is_dir() else "[FILE]"
                    size = f"({item.stat().st_size} bytes)" if item.is_file() else ""
                    items.append(f"{item_type} {item.name} {size}")

                result = f"Directory: {path}\n\nContents:\n"
                result += "\n".join(items) if items else "Directory is empty"
                return result
            else:
                return f"Directory not found: {path}"
        except Exception as e:
            return f"Error listing directory {path}: {str(e)}"

class SearchFilesTool(BaseTool):
    """Tool for searching files by pattern."""
    name: str = "grep_search"
    description: str = "Search for text patterns in files using regex. Use this to find specific code or text across the project."

    def _run(self, query: str, includePattern: str = "*") -> str:
        """Search for text in files synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            import glob
            import re

            search_path = Path(project_root)
            results = []

            # Find files matching the pattern
            pattern = str(search_path / "**" / includePattern)
            files = glob.glob(pattern, recursive=True)

            for file_path_str in files[:50]:  # Limit to 50 files
                file_path = Path(file_path_str)

                # Skip common directories
                if any(skip in str(file_path) for skip in ['node_modules', '.git', '__pycache__', '.next']):
                    continue

                try:
                    if file_path.exists() and file_path.is_file():
                        content = file_path.read_text(encoding='utf-8', errors='replace')
                        lines = content.split('\n')

                        for line_num, line in enumerate(lines, 1):
                            if re.search(query, line, re.IGNORECASE):
                                rel_path = file_path.relative_to(search_path)
                                results.append(f"{rel_path}:{line_num}: {line.strip()}")

                                if len(results) >= 100:  # Limit results
                                    break
                except:
                    continue

                if len(results) >= 100:
                    break

            if results:
                return f"Found {len(results)} matches for '{query}':\n\n" + "\n".join(results)
            else:
                return f"No matches found for '{query}' in files matching '{includePattern}'"
        except Exception as e:
            return f"Error searching for '{query}': {str(e)}"

class RunTerminalCommandTool(BaseTool):
    """Tool for running terminal commands safely."""
    name: str = "run_terminal_command"
    description: str = "Run a terminal command in the project directory. Use this for building, testing, or running scripts."

    def _run(self, command: str) -> str:
        """Run terminal command synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            import subprocess
            # Run command with timeout and capture output
            result = subprocess.run(
                command,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )

            output = f"Command: {command}\n"
            output += f"Exit code: {result.returncode}\n\n"

            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"

            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            return output

        except subprocess.TimeoutExpired:
            return f"Command timed out after 30 seconds: {command}"
        except Exception as e:
            return f"Error running command '{command}': {str(e)}"

class GetProjectStructureTool(BaseTool):
    """Tool for getting project structure information."""
    name: str = "get_project_structure"
    description: str = "Get the overall structure of the project including directories and key files."

    def _run(self) -> str:
        """Get project structure synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path

            def get_structure(path, prefix="", max_depth=3, current_depth=0):
                if current_depth > max_depth:
                    return []

                items = []
                try:
                    for item in sorted(Path(path).iterdir()):
                        if item.name.startswith('.') or item.name in ['node_modules', '__pycache__', '.git']:
                            continue

                        if item.is_dir():
                            items.append(f"{prefix}📁 {item.name}/")
                            if current_depth < max_depth:
                                items.extend(get_structure(item, prefix + "  ", max_depth, current_depth + 1))
                        else:
                            # Show important files
                            if any(item.name.endswith(ext) for ext in ['.ts', '.tsx', '.js', '.jsx', '.py', '.json', '.md', '.yml', '.yaml']):
                                items.append(f"{prefix}📄 {item.name}")
                except:
                    pass

                return items

            structure = get_structure(project_root)
            return f"Project Structure:\n\n" + "\n".join(structure)

        except Exception as e:
            return f"Error getting project structure: {str(e)}"

class CreateSandboxTool(BaseTool):
    """Tool for creating development sandboxes."""
    name: str = "create_sandbox"
    description: str = "Create a new development sandbox environment for testing code."

    def _run(self, name: str, type: str = "react") -> str:
        """Create a sandbox synchronously."""
        try:
            # This would integrate with the sandbox manager
            # For now, return a placeholder response
            return f"Created sandbox '{name}' of type '{type}'. Sandbox ID: sandbox_{name.lower().replace(' ', '_')}"
        except Exception as e:
            return f"Error creating sandbox: {str(e)}"

            # Basic security check - prevent accessing files outside project
            file_path = file_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(file_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot access files outside project directory. Path: {path}"

            if file_path.exists() and file_path.is_file():
                # Check file size (limit to 1MB)
                if file_path.stat().st_size > 1024 * 1024:
                    return f"File too large to read ({file_path.stat().st_size} bytes). Maximum size is 1MB."

                content = file_path.read_text(encoding='utf-8', errors='replace')
                return f"File: {path}\n\n{content}"
            else:
                return f"File not found: {path}"
        except Exception as e:
            return f"Error reading file {path}: {str(e)}"

class ListDirTool(BaseTool):
    """Tool for listing directory contents."""
    name: str = "list_dir"
    description: str = "List the contents of a directory. Use this to explore project structure and find files."

    def _run(self, path: str = ".") -> str:
        """List directory contents synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to project root for security
            from pathlib import Path
            dir_path = Path(project_root) / path.lstrip('/')

            # Basic security check
            dir_path = dir_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(dir_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot access directories outside project directory. Path: {path}"

            if dir_path.exists() and dir_path.is_dir():
                items = []
                for item in sorted(dir_path.iterdir()):
                    item_type = "[DIR]" if item.is_dir() else "[FILE]"
                    size = f"({item.stat().st_size} bytes)" if item.is_file() else ""
                    items.append(f"{item_type} {item.name} {size}")

                result = f"Directory: {path}\n\nContents:\n"
                result += "\n".join(items) if items else "Directory is empty"
                return result
            else:
                return f"Directory not found: {path}"
        except Exception as e:
            return f"Error listing directory {path}: {str(e)}"

class SearchFilesTool(BaseTool):
    """Tool for searching files by pattern."""
    name: str = "search_files"
    description: str = "Search for files matching a pattern using glob syntax. Use this to find specific files in the project."

    def _run(self, pattern: str, path: str = ".") -> str:
        """Search for files matching pattern synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to project root for security
            from pathlib import Path
            search_path = Path(project_root) / path.lstrip('/')

            # Basic security check
            search_path = search_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(search_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot search outside project directory. Path: {path}"

            if not search_path.exists():
                return f"Search path not found: {path}"

            import glob
            # Use glob to find matches
            glob_pattern = str(search_path / pattern)
            matches = glob.glob(glob_pattern, recursive=True)

            # Filter results to stay within project directory
            filtered_matches = []
            for match in matches:
                match_path = Path(match).resolve()
                if str(match_path).startswith(str(project_root_path)):
                    # Get relative path for cleaner output
                    rel_path = match_path.relative_to(project_root_path)
                    filtered_matches.append(str(rel_path))

            if filtered_matches:
                result = f"Found {len(filtered_matches)} files matching '{pattern}' in '{path}':\n\n"
                result += "\n".join(filtered_matches)
                return result
            else:
                return f"No files found matching pattern '{pattern}' in '{path}'"
        except Exception as e:
            return f"Error searching files with pattern '{pattern}': {str(e)}"

class RunTerminalCommandTool(BaseTool):
    """Tool for running terminal commands safely."""
    name: str = "run_terminal_command"
    description: str = "Run a terminal command in the project directory. Use this for building, testing, or running scripts."

    def _run(self, command: str) -> str:
        """Run terminal command synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            import subprocess
            # Run command with timeout and capture output
            result = subprocess.run(
                command,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )

            output = f"Command: {command}\n"
            output += f"Exit code: {result.returncode}\n\n"

            if result.stdout:
                output += f"STDOUT:\n{result.stdout}\n"

            if result.stderr:
                output += f"STDERR:\n{result.stderr}\n"

            return output

        except subprocess.TimeoutExpired:
            return f"Command timed out after 30 seconds: {command}"
        except Exception as e:
            return f"Error running command '{command}': {str(e)}"

class WriteFileTool(BaseTool):
    """Tool for writing content to files."""
    name: str = "write_file"
    description: str = "Write or overwrite content to a file. Use this to create or update files."

    def _run(self, file_path: str, content: str) -> str:
        """Write content to file synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to project root for security
            from pathlib import Path
            full_path = Path(project_root) / file_path.lstrip('/')

            # Basic security check
            full_path = full_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(full_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot write files outside project directory. Path: {file_path}"

            # Create directory if it doesn't exist
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content to file
            full_path.write_text(content, encoding='utf-8')
            
            # Trigger metadata update asynchronously (fire and forget)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the coroutine to run in the background
                    asyncio.create_task(update_sandbox_metadata_if_needed(file_path))
                else:
                    # Run the coroutine if no loop is running
                    loop.run_until_complete(update_sandbox_metadata_if_needed(file_path))
            except Exception as e:
                logger.debug(f"Could not schedule metadata update: {e}")
            
            return f"Successfully wrote {len(content)} characters to {file_path}"
        except Exception as e:
            return f"Error writing to file {file_path}: {str(e)}"

class CreateDirectoryTool(BaseTool):
    """Tool for creating directories."""
    name: str = "create_directory"
    description: str = "Create a new directory (including parent directories if needed)."

    def _run(self, dir_path: str) -> str:
        """Create directory synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            # Resolve the path relative to project root for security
            from pathlib import Path
            full_path = Path(project_root) / dir_path.lstrip('/')

            # Basic security check
            full_path = full_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(full_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot create directories outside project directory. Path: {dir_path}"

            # Create directory
            full_path.mkdir(parents=True, exist_ok=True)
            
            # Trigger metadata update asynchronously (fire and forget)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the coroutine to run in the background
                    asyncio.create_task(update_sandbox_metadata_if_needed(str(full_path)))
                else:
                    # Run the coroutine if no loop is running
                    loop.run_until_complete(update_sandbox_metadata_if_needed(str(full_path)))
            except Exception as e:
                logger.debug(f"Could not schedule metadata update: {e}")
            
            return f"Successfully created directory {dir_path}"
        except Exception as e:
            return f"Error creating directory {dir_path}: {str(e)}"

class MoveFileTool(BaseTool):
    """Tool for moving or renaming files."""
    name: str = "move_file"
    description: str = "Move or rename a file from source path to destination path."

    def _run(self, source_path: str, dest_path: str) -> str:
        """Move file synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            source_full = (Path(project_root) / source_path.lstrip('/')).resolve()
            dest_full = (Path(project_root) / dest_path.lstrip('/')).resolve()
            project_root_path = Path(project_root).resolve()

            # Security checks
            if not str(source_full).startswith(str(project_root_path)):
                return f"Access denied: Source path outside project directory. Path: {source_path}"
            if not str(dest_full).startswith(str(project_root_path)):
                return f"Access denied: Destination path outside project directory. Path: {dest_path}"

            if not source_full.exists():
                return f"Source file not found: {source_path}"

            # Create destination directory if needed
            dest_full.parent.mkdir(parents=True, exist_ok=True)

            # Move file
            source_full.rename(dest_full)
            
            # Trigger metadata update asynchronously (fire and forget)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the coroutine to run in the background
                    asyncio.create_task(update_sandbox_metadata_if_needed(dest_path))
                else:
                    # Run the coroutine if no loop is running
                    loop.run_until_complete(update_sandbox_metadata_if_needed(dest_path))
            except Exception as e:
                logger.debug(f"Could not schedule metadata update: {e}")
            
            return f"Successfully moved {source_path} to {dest_path}"
        except Exception as e:
            return f"Error moving file from {source_path} to {dest_path}: {str(e)}"

class ReplaceInFileTool(BaseTool):
    """Tool for replacing text in files using regex."""
    name: str = "replace_in_file"
    description: str = "Find and replace text in a file using regex patterns."

    def _run(self, file_path: str, search_text: str, replace_text: str) -> str:
        """Replace text in file synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            import re
            full_path = Path(project_root) / file_path.lstrip('/')

            # Security check
            full_path = full_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(full_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot modify files outside project directory. Path: {file_path}"

            if not full_path.exists():
                return f"File not found: {file_path}"

            # Read current content
            content = full_path.read_text(encoding='utf-8')

            # Replace using regex
            new_content = re.sub(search_text, replace_text, content)

            # Write back if changed
            if new_content != content:
                full_path.write_text(new_content, encoding='utf-8')
                return f"Successfully replaced text in {file_path}"
            else:
                return f"No matches found for replacement in {file_path}"
        except Exception as e:
            return f"Error replacing text in {file_path}: {str(e)}"

class InsertAtLineTool(BaseTool):
    """Tool for inserting text at a specific line in a file."""
    name: str = "insert_at_line"
    description: str = "Insert text at a specific line number in a file."

    def _run(self, file_path: str, line_number: int, content: str) -> str:
        """Insert text at line synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            full_path = Path(project_root) / file_path.lstrip('/')

            # Security check
            full_path = full_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(full_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot modify files outside project directory. Path: {file_path}"

            if not full_path.exists():
                return f"File not found: {file_path}"

            # Read current content
            file_content = full_path.read_text(encoding='utf-8')
            lines = file_content.split('\n')

            # Insert at specified line (1-indexed)
            if line_number < 1:
                line_number = 1
            if line_number > len(lines) + 1:
                line_number = len(lines) + 1

            lines.insert(line_number - 1, content)
            new_content = '\n'.join(lines)

            # Write back
            full_path.write_text(new_content, encoding='utf-8')
            return f"Successfully inserted text at line {line_number} in {file_path}"
        except Exception as e:
            return f"Error inserting text at line {line_number} in {file_path}: {str(e)}"

class DeleteLinesTool(BaseTool):
    """Tool for deleting lines from a file."""
    name: str = "delete_lines"
    description: str = "Delete a range of lines from a file."

    def _run(self, file_path: str, start_line: int, end_line: int) -> str:
        """Delete lines from file synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            full_path = Path(project_root) / file_path.lstrip('/')

            # Security check
            full_path = full_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(full_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot modify files outside project directory. Path: {file_path}"

            if not full_path.exists():
                return f"File not found: {file_path}"

            # Read current content
            file_content = full_path.read_text(encoding='utf-8')
            lines = file_content.split('\n')

            # Delete lines (1-indexed, inclusive)
            if start_line < 1:
                start_line = 1
            if end_line > len(lines):
                end_line = len(lines)
            if start_line > end_line:
                return f"Invalid line range: start_line ({start_line}) > end_line ({end_line})"

            # Delete the range
            del lines[start_line - 1:end_line]
            new_content = '\n'.join(lines)

            # Write back
            full_path.write_text(new_content, encoding='utf-8')
            
            # Trigger metadata update asynchronously (fire and forget)
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule the coroutine to run in the background
                    asyncio.create_task(update_sandbox_metadata_if_needed(file_path))
                else:
                    # Run the coroutine if no loop is running
                    loop.run_until_complete(update_sandbox_metadata_if_needed(file_path))
            except Exception as e:
                logger.debug(f"Could not schedule metadata update: {e}")
            
            return f"Successfully deleted lines {start_line}-{end_line} from {file_path}"
        except Exception as e:
            return f"Error deleting lines {start_line}-{end_line} from {file_path}: {str(e)}"

class ReadLinesTool(BaseTool):
    """Tool for reading specific lines from a file."""
    name: str = "read_lines"
    description: str = "Read specific lines from a file by line numbers."

    def _run(self, file_path: str, start_line: int = 1, end_line: int = None) -> str:
        """Read lines from file synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            full_path = Path(project_root) / file_path.lstrip('/')

            # Security check
            full_path = full_path.resolve()
            project_root_path = Path(project_root).resolve()

            if not str(full_path).startswith(str(project_root_path)):
                return f"Access denied: Cannot read files outside project directory. Path: {file_path}"

            if not full_path.exists():
                return f"File not found: {file_path}"

            # Read content
            content = full_path.read_text(encoding='utf-8')
            lines = content.split('\n')

            # Get line range
            if start_line < 1:
                start_line = 1
            if end_line is None or end_line > len(lines):
                end_line = len(lines)
            if start_line > end_line:
                return f"Invalid line range: start_line ({start_line}) > end_line ({end_line})"

            # Extract lines
            selected_lines = lines[start_line - 1:end_line]
            result = f"Lines {start_line}-{end_line} from {file_path}:\n\n"
            for i, line in enumerate(selected_lines, start_line):
                result += f"{i:4d}: {line}\n"

            return result
        except Exception as e:
            return f"Error reading lines from {file_path}: {str(e)}"

class SearchCodeTool(BaseTool):
    """Tool for searching code patterns across the project."""
    name: str = "search_code"
    description: str = "Search for code patterns across the project using advanced search."

    def _run(self, query: str, file_extensions: str = "*.ts,*.js,*.py,*.tsx,*.jsx", max_results: int = 20) -> str:
        """Search for code patterns synchronously."""
        try:
            # Get the project root
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            project_root = os.path.dirname(current_dir)  # Go up to NextLovable

            from pathlib import Path
            import re
            import glob

            search_path = Path(project_root)
            extensions = [ext.strip() for ext in file_extensions.split(',')]
            results = []

            # Find files with matching extensions
            for ext in extensions:
                pattern = str(search_path / "**" / ext)
                files = glob.glob(pattern, recursive=True)

                for file_path_str in files[:20]:  # Limit files per extension
                    file_path = Path(file_path_str)

                    # Skip common directories
                    if any(skip in str(file_path) for skip in ['node_modules', '.git', '__pycache__', '.next']):
                        continue

                    try:
                        if file_path.exists() and file_path.is_file():
                            content = file_path.read_text(encoding='utf-8', errors='replace')
                            lines = content.split('\n')

                            for line_num, line in enumerate(lines, 1):
                                # More sophisticated code pattern matching
                                if re.search(query, line, re.IGNORECASE | re.MULTILINE):
                                    rel_path = file_path.relative_to(search_path)
                                    results.append({
                                        'file': str(rel_path),
                                        'line': line_num,
                                        'content': line.strip(),
                                        'context': {
                                            'before': lines[line_num - 2].strip() if line_num > 1 else '',
                                            'after': lines[line_num].strip() if line_num < len(lines) else ''
                                        }
                                    })

                                    if len(results) >= max_results:
                                        break
                    except:
                        continue

                    if len(results) >= max_results:
                        break

                if len(results) >= max_results:
                    break

            if results:
                output = f"Found {len(results)} code matches for '{query}':\n\n"
                for result in results:
                    output += f"📄 {result['file']}:{result['line']}\n"
                    output += f"   {result['content']}\n"
                    if result['context']['before']:
                        output += f"   ...{result['context']['before']}\n"
                    if result['context']['after']:
                        output += f"   ...{result['context']['after']}\n"
                    output += "\n"
                return output
            else:
                return f"No code matches found for '{query}' in files with extensions: {file_extensions}"
        except Exception as e:
            return f"Error searching code for '{query}': {str(e)}"




class MCPIntegration:
    """Simplified MCP integration providing essential LangChain tools."""

    def __init__(self):
        self.initialized = False

    async def initialize_mcp_clients(self):
        """Initialize - no external clients needed."""
        if not self.initialized:
            self.initialized = True
            logger.info("MCP integration initialized with built-in tools")

    async def get_langchain_tools(self) -> List[Any]:
        """Get essential LangChain tools for agents."""
        if not self.initialized:
            await self.initialize_mcp_clients()

        # Return the core coding tools that agents need
        tools = [
            ReadFileTool(),
            ListDirTool(),
            WriteFileTool(),
            CreateDirectoryTool(),
            MoveFileTool(),
            ReplaceInFileTool(),
            InsertAtLineTool(),
            DeleteLinesTool(),
            ReadLinesTool(),
            SearchFilesTool(),
            SearchCodeTool(),
            RunTerminalCommandTool(),
            GetProjectStructureTool(),
            CreateSandboxTool()
        ]

        logger.info(f"Loaded {len(tools)} essential LangChain tools for agents")
        return tools

    async def get_available_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get available tools info."""
        tools = await self.get_langchain_tools()
        return {
            "built_in": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "type": "function"
                } for tool in tools
            ]
        }

    async def execute_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool (legacy method)."""
        tools = await self.get_langchain_tools()
        tool = next((t for t in tools if t.name == tool_name), None)
        if tool:
            return tool._run(**arguments)
        raise ValueError(f"Tool {tool_name} not found")

    async def process_chat_request(
        self,
        user_request: str,
        session_id: str,
        model: str,
        sandbox_context: Dict[str, Any],
        sandbox_id: str
    ) -> Dict[str, Any]:
        """Process chat request with MCP tools and project context."""
        # Set session memory to establish sandbox context for MCP tools
        from .utils import set_session_memory
        await set_session_memory(session_id)
        
        # Get available tools info
        available_tools = await self.get_available_tools()
        
        # Gather project context if sandbox_context contains project_path
        project_context = None
        if sandbox_context and "project_path" in sandbox_context:
            try:
                from app.services.project_context import ProjectContextService
                context_service = ProjectContextService(sandbox_context["project_path"])
                project_context = await context_service.gather_full_context(
                    max_depth=2,  # Limit depth for performance
                    include_file_contents=False  # Don't include file contents by default
                )
                logger.info(f"Gathered project context for {sandbox_context['project_path']}")
            except Exception as e:
                logger.warning(f"Failed to gather project context: {e}")
                project_context = {"error": str(e)}

        return {
            "user_request": user_request,
            "session_id": session_id,
            "model": model,
            "sandbox_context": sandbox_context,
            "sandbox_id": sandbox_id,
            "project_context": project_context,
            "available_tools": available_tools,
            "tool_results": [],  # Will be populated during execution
            "processed": True
        }

# Global MCP integration instance
mcp_integration = MCPIntegration()

async def initialize_mcp_clients():
    """Initialize MCP clients (called during app startup)."""
    await mcp_integration.initialize_mcp_clients()

async def process_chat_request(
    user_request: str,
    session_id: str,
    model: str,
    sandbox_context: Dict[str, Any],
    sandbox_id: str
) -> Dict[str, Any]:
    """Process chat request using MCP integration."""
    return await mcp_integration.process_chat_request(
        user_request, session_id, model, sandbox_context, sandbox_id
    )