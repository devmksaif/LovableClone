"""
Python equivalent of the TypeScript tools.ts
Defines various tools for file operations and other utilities.
"""

import os
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# Path safety imports
from app.utils.path_safety import (
    get_path_validator, 
    validate_file_path, 
    get_safe_file_path,
    AccessLevel, 
    PathValidationError
)

# ChromaDB integration import
try:
    from app.services.chroma_integration import chroma_integration
    CHROMA_INTEGRATION_AVAILABLE = True
except ImportError:
    CHROMA_INTEGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)

# Pydantic schemas for tool parameters
class FileReadSchema(BaseModel):
    """Schema for file reading operations."""
    filePath: str = Field(description="Path to the file to read")

class FileWriteSchema(BaseModel):
    """Schema for file writing operations."""
    filePath: str = Field(description="Path to the file to create or overwrite")
    content: str = Field(description="Content to write to the file")

class FileAppendSchema(BaseModel):
    """Schema for file appending operations."""
    filePath: str = Field(description="Path to the file to append to")
    content: str = Field(description="Content to append to the file")

class FileDeleteSchema(BaseModel):
    """Schema for file deletion operations."""
    filePath: str = Field(description="Path to the file to delete")

class DirectoryListSchema(BaseModel):
    """Schema for directory listing operations."""
    dirPath: str = Field(description="Path to the directory to list")

class FileSearchSchema(BaseModel):
    """Schema for file search operations."""
    dirPath: str = Field(description="Directory to search in")
    pattern: str = Field(description="Regex pattern to search for")

# Global state for session management
_current_session_id: Optional[str] = None
_current_project_folder: Optional[str] = None

def set_session_context(session_id: str, project_folder: str) -> None:
    """Set the current session context."""
    global _current_session_id, _current_project_folder
    _current_session_id = session_id
    _current_project_folder = project_folder

def get_current_session_id() -> Optional[str]:
    """Get the current session ID."""
    return _current_session_id

def get_project_folder() -> str:
    """Get the current project folder."""
    if not _current_project_folder:
        raise ValueError("No project folder set")
    return _current_project_folder

# File operation functions
def read_file_content(file_path: str) -> Dict[str, Any]:
    """Read file content safely."""
    try:
        full_path = Path(get_project_folder()) / file_path
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}

def write_file_content(file_path: str, content: str) -> Dict[str, Any]:
    """Write content to file safely."""
    try:
        full_path = Path(get_project_folder()) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Automatically index file in ChromaDB
        if CHROMA_INTEGRATION_AVAILABLE:
            try:
                # Run async function in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(chroma_integration.index_file(str(full_path)))
                loop.close()
                logger.info(f"Successfully indexed {file_path} in ChromaDB")
            except Exception as e:
                logger.warning(f"Failed to index {file_path} in ChromaDB: {e}")

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def append_file_content(file_path: str, content: str) -> Dict[str, Any]:
    """Append content to file safely."""
    try:
        full_path = Path(get_project_folder()) / file_path
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        with open(full_path, 'a', encoding='utf-8') as f:
            f.write(content)

        # Automatically index file in ChromaDB
        if CHROMA_INTEGRATION_AVAILABLE:
            try:
                # Run async function in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(chroma_integration.index_file(str(full_path)))
                loop.close()
                logger.info(f"Successfully indexed {file_path} in ChromaDB")
            except Exception as e:
                logger.warning(f"Failed to index {file_path} in ChromaDB: {e}")

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def delete_file_safe(file_path: str) -> Dict[str, Any]:
    """Delete file safely."""
    try:
        full_path = Path(get_project_folder()) / file_path
        if not full_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        # Security check - only allow deletion in generated directory
        if "generated" not in str(full_path):
            return {"success": False, "error": "Can only delete files in generated directory"}

        full_path.unlink()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_directory_contents(dir_path: str) -> Dict[str, Any]:
    """List directory contents safely."""
    try:
        full_path = Path(get_project_folder()) / dir_path
        if not full_path.exists():
            return {"success": False, "error": f"Directory not found: {dir_path}"}

        items = []
        for item in full_path.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "path": str(item.relative_to(get_project_folder()))
            })

        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}

def search_files_pattern(dir_path: str, pattern: str) -> Dict[str, Any]:
    """Search for files containing a regex pattern."""
    try:
        import re
        full_path = Path(get_project_folder()) / dir_path
        if not full_path.exists():
            return {"success": False, "error": f"Directory not found: {dir_path}"}

        matches = []
        for file_path in full_path.rglob("*"):
            if file_path.is_file():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if re.search(pattern, content):
                            matches.append({
                                "file": str(file_path.relative_to(get_project_folder())),
                                "matches": len(re.findall(pattern, content))
                            })
                except:
                    continue  # Skip files that can't be read

        return {"success": True, "matches": matches}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Tool definitions
@tool
async def read_file_tool(filePath: str) -> str:
    """Read the contents of a file. Use this to examine existing code or documents."""
    logger.info(f"📖 Reading file: {filePath}")

    result = read_file_content(filePath)
    if result["success"]:
        return f"File content:\n{result['content']}"
    else:
        return f"Error reading file: {result['error']}"

@tool
async def write_file_tool(filePath: str, content: str) -> str:
    """Create or overwrite a file with content. Use this to create new files or completely replace existing ones."""
    logger.info(f"✏️ Writing file: {filePath}")

    result = write_file_content(filePath, content)
    if result["success"]:
        return f"Successfully wrote {len(content)} characters to {filePath}"
    else:
        return f"Error writing file: {result['error']}"

@tool
async def append_to_file_tool(filePath: str, content: str) -> str:
    """Append content to the end of an existing file. Use this to add to existing files."""
    logger.info(f"📝 Appending to file: {filePath}")

    result = append_file_content(filePath, content)
    if result["success"]:
        return f"Successfully appended {len(content)} characters to {filePath}"
    else:
        return f"Error appending to file: {result['error']}"

@tool
async def delete_file_tool(filePath: str) -> str:
    """Delete a file. Only works on files in the generated directory for security."""
    logger.info(f"🗑️ Deleting file: {filePath}")

    result = delete_file_safe(filePath)
    if result["success"]:
        return f"Successfully deleted {filePath}"
    else:
        return f"Error deleting file: {result['error']}"

@tool
async def list_directory_tool(dirPath: str) -> str:
    """List the contents of a directory. Use this to see what files are available."""
    logger.info(f"📁 Listing directory: {dirPath}")

    result = list_directory_contents(dirPath)
    if result["success"]:
        items = result["items"]
        if not items:
            return f"Directory {dirPath} is empty"
        else:
            item_list = "\n".join([f"{'📁' if item['type'] == 'directory' else '📄'} {item['name']}" for item in items])
            return f"Contents of {dirPath}:\n{item_list}"
    else:
        return f"Error listing directory: {result['error']}"

@tool
async def search_files_tool(dirPath: str, pattern: str) -> str:
    """Search for files containing a regex pattern. Use this to find specific code patterns or text."""
    logger.info(f"🔍 Searching files in {dirPath} for pattern: {pattern}")

    result = search_files_pattern(dirPath, pattern)
    if result["success"]:
        matches = result["matches"]
        if not matches:
            return f"No files found containing pattern '{pattern}' in {dirPath}"
        else:
            match_list = "\n".join([f"📄 {match['file']} ({match['matches']} matches)" for match in matches])
            return f"Files containing '{pattern}' in {dirPath}:\n{match_list}"
    else:
        return f"Error searching files: {result['error']}"

# Export all tools
__all__ = [
    'read_file_tool',
    'write_file_tool',
    'append_to_file_tool',
    'delete_file_tool',
    'list_directory_tool',
    'search_files_tool',
    'set_session_context',
    'get_current_session_id',
    'get_project_folder'
]