"""
Python equivalent of the TypeScript utils.ts
Handles session management, project folder handling, and utility functions.
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Global memory instance for current session
current_memory: Optional[Any] = None
current_session_id: Optional[str] = None
current_project_folder_cache: Dict[str, str] = {}

def extract_sandbox_id(session_id: str) -> Optional[str]:
    """Extract sandbox ID from session ID."""
    if session_id.startswith('sandbox-sandbox_'):
        # Handle double prefix case: sandbox-sandbox_{id}
        return session_id.replace('sandbox-sandbox_', 'sandbox_')
    elif session_id.startswith('sandbox-'):
        # Handle normal case: sandbox-{id}
        return session_id.replace('sandbox-', 'sandbox_')
    return None

# Mock sandbox service for now
class MockSandboxService:
    def getSandboxSync(self, sandbox_id: str) -> Optional[Dict[str, Any]]:
        """Mock implementation of sandbox service."""
        # For now, return a mock sandbox with the correct project path
        if sandbox_id.startswith('sandbox_'):
            # Compute the correct sandbox path
            project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            sandbox_path = project_root / "sandboxes" / sandbox_id
            return {
                "config": {
                    "projectPath": str(sandbox_path)
                }
            }
        return None

sandbox_service = MockSandboxService()

async def set_session_memory(session_id: str) -> None:
    """Set the current session memory."""
    global current_memory, current_session_id, current_project_folder_cache

    current_session_id = session_id

    # Always extract sandbox ID - chats should always be in sandbox context
    sandbox_id = extract_sandbox_id(session_id)
    if not sandbox_id:
        raise ValueError('Invalid session ID - must be a sandbox session')

    sandbox = sandbox_service.getSandboxSync(sandbox_id)
    if not sandbox:
        raise ValueError('Sandbox not found')

    # Always use the sandbox project path
    project_folder = sandbox["config"]["projectPath"]
    if not os.path.exists(project_folder):
        os.makedirs(project_folder, exist_ok=True)

    current_project_folder_cache[session_id] = project_folder
    current_memory = f"memory_for_{session_id}"  # Mock memory
    logger.info(f"🏗️ Using sandbox project folder: {project_folder}")

def get_memory() -> Any:
    """Get the current session memory."""
    if not current_memory:
        # Always use sandbox context for chats
        if current_session_id:
            sandbox_id = extract_sandbox_id(current_session_id)
            if not sandbox_id:
                raise ValueError('Invalid session ID - must be a sandbox session')

            sandbox = sandbox_service.getSandboxSync(sandbox_id)
            if not sandbox:
                raise ValueError('Sandbox not found')

            # Always use the sandbox project path
            project_folder = sandbox["config"]["projectPath"]
            current_project_folder_cache[current_session_id] = project_folder
            current_memory = f"memory_for_{current_session_id}"
            logger.info(f"🏗️ Using sandbox project folder: {project_folder}")
        else:
            raise ValueError('No valid sandbox session found')

    return current_memory

def get_project_folder() -> str:
    """Get the current project folder."""
    if not current_session_id:
        raise ValueError('No session ID set')

    # Check cache first
    if current_session_id in current_project_folder_cache:
        return current_project_folder_cache[current_session_id]

    # Always use sandbox context for chats
    sandbox_id = extract_sandbox_id(current_session_id)
    if not sandbox_id:
        raise ValueError('Invalid session ID - must be a sandbox session')

    sandbox = sandbox_service.getSandboxSync(sandbox_id)
    if not sandbox:
        raise ValueError('Sandbox not found')

    # Always use the sandbox project path
    sandbox_path = sandbox["config"]["projectPath"]
    current_project_folder_cache[current_session_id] = sandbox_path
    logger.info(f"🏗️ Using sandbox project folder: {sandbox_path}")
    return sandbox_path

def get_current_session_id() -> Optional[str]:
    """Get the current session ID."""
    return current_session_id

def validate_file_content(filename: str, content: str) -> Dict[str, Any]:
    """Validate file content for quality."""
    trimmed = content.strip()

    # Check for placeholders
    if any(phrase in content.lower() for phrase in ['...', 'todo', 'placeholder']):
        return {"isValid": False, "reason": "Contains placeholders or TODO comments"}

    # Check for empty or very short files
    if len(trimmed) < 10:
        return {"isValid": False, "reason": "File is too short or empty"}

    # Check for incomplete code patterns
    if filename.endswith(('.ts', '.js')):
        # Check for incomplete functions, missing brackets, etc.
        open_braces = content.count('{')
        close_braces = content.count('}')
        if open_braces != close_braces:
            return {"isValid": False, "reason": "Mismatched braces"}

    return {"isValid": True, "reason": "Valid content"}

# Export all functions
__all__ = [
    'set_session_memory',
    'get_memory',
    'get_project_folder',
    'get_current_session_id',
    'validate_file_content',
    'extract_sandbox_id'
]