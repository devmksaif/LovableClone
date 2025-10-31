"""
Local tools for agent operations using @tool decorator.
These tools provide file system operations and other utilities for agents.
"""

import os
import json
import logging
import re
import time
import threading
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from functools import wraps

# Import path safety utilities
from app.utils.path_safety import (
    get_path_validator, 
    validate_file_path, 
    get_safe_file_path,
    AccessLevel, 
    PathValidationError
)

# Vector store imports
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    VECTOR_STORE_AVAILABLE = True
except ImportError:
    VECTOR_STORE_AVAILABLE = False

# ChromaDB integration import
try:
    from app.services.chroma_integration import chroma_integration
    CHROMA_INTEGRATION_AVAILABLE = True
except ImportError:
    CHROMA_INTEGRATION_AVAILABLE = False

# Import centralized ChromaDB configuration
try:
    from app.config.chroma_config import get_chroma_path
    CHROMA_CONFIG_AVAILABLE = True
except ImportError:
    CHROMA_CONFIG_AVAILABLE = False

logger = logging.getLogger(__name__)

# ChromaDB Vector Store for semantic search
class ChromaVectorStore:
    def __init__(self, persist_directory: str = None):
        if not VECTOR_STORE_AVAILABLE:
            raise ImportError("ChromaDB and sentence-transformers are required for vector store functionality")
        
        # Use centralized configuration if available, otherwise fall back to provided path or default
        if persist_directory is None:
            if CHROMA_CONFIG_AVAILABLE:
                persist_directory = get_chroma_path("vector_store")
                logger.info(f"Using centralized ChromaDB vector store path: {persist_directory}")
            else:
                persist_directory = "./chroma_db"
                logger.warning("Centralized ChromaDB config not available, using relative path")
        
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        
        # Initialize sentence transformer for embeddings
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Cache for collections
        self.collections = {}
    
    def get_or_create_collection(self, name: str):
        """Get or create a ChromaDB collection."""
        if name not in self.collections:
            self.collections[name] = self.client.get_or_create_collection(name=name)
        return self.collections[name]
    
    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]] = None, collection_name: str = "codebase"):
        """Add documents to a collection."""
        collection = self.get_or_create_collection(collection_name)
        
        # Generate embeddings
        embeddings = self.embedding_model.encode(documents).tolist()
        
        # Prepare data
        ids = [f"{collection_name}_{i}_{hash(text)}" for i, text in enumerate(documents)]
        
        if metadatas is None:
            metadatas = [{}] * len(documents)
        
        # Add to collection
        collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    
    def search(self, collection_name: str, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search for similar documents."""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query]).tolist()[0]
            
            # Search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    formatted_results.append({
                        'content': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else {},
                        'score': 1.0 - (results['distances'][0][i] if results['distances'] and results['distances'][0] else 0)
                    })
            
            return formatted_results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def semantic_search(self, query: str, n_results: int = 5, collection_name: str = "codebase") -> List[Dict[str, Any]]:
        """Search for similar documents using semantic similarity."""
        return self.search(collection_name, query, n_results)
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics for a collection."""
        try:
            collection = self.get_or_create_collection(collection_name)
            count = collection.count()
            return {'total_chunks': count}
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {'total_chunks': 0}

    def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics for the vector store."""
        try:
            stats = {}
            # Get all collection names from ChromaDB
            collection_names = self.client.list_collections()
            for collection in collection_names:
                stats[collection.name] = self.get_collection_stats(collection.name)
            return stats
        except Exception as e:
            logger.error(f"Failed to get vector store stats: {e}")
            return {}

# Global vector store instance
try:
    vector_store = ChromaVectorStore() if VECTOR_STORE_AVAILABLE else None
except Exception as e:
    logger.warning(f"Failed to initialize vector store: {e}")
    vector_store = None

# Tool Usage Logging System
class ToolUsageLogger:
    def __init__(self):
        self.tool_logs = []
        self.active_operations = {}
        self.logger = logging.getLogger(__name__ + ".tool_usage")
        
    def log_tool_start(self, tool_name: str, parameters: Dict[str, Any], session_id: str = None) -> str:
        """Log the start of a tool execution"""
        operation_id = f"{tool_name}_{int(time.time() * 1000)}"
        log_entry = {
            "operation_id": operation_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "start_time": datetime.now().isoformat(),
            "session_id": session_id or _current_session_id,
            "status": "started"
        }
        self.tool_logs.append(log_entry)
        self.active_operations[operation_id] = log_entry
        
        # Log to console with emoji
        self.logger.info(f"🔧 {tool_name} started - {operation_id}")
        return operation_id
        
    def log_tool_complete(self, operation_id: str, result: Any, success: bool = True):
        """Log the completion of a tool execution"""
        if operation_id in self.active_operations:
            log_entry = self.active_operations[operation_id]
            log_entry.update({
                "end_time": datetime.now().isoformat(),
                "result": str(result)[:500] if result else None,  # Truncate long results
                "success": success,
                "status": "completed" if success else "failed",
                "duration_ms": int((datetime.now() - datetime.fromisoformat(log_entry["start_time"])).total_seconds() * 1000)
            })
            
            # Update in tool_logs
            for i, log in enumerate(self.tool_logs):
                if log["operation_id"] == operation_id:
                    self.tool_logs[i] = log_entry
                    break
                    
            del self.active_operations[operation_id]
            
            # Log to console with emoji
            status_emoji = "✅" if success else "❌"
            self.logger.info(f"{status_emoji} {log_entry['tool_name']} completed - {log_entry['duration_ms']}ms")
            
    def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent tool usage logs"""
        return self.tool_logs[-limit:] if self.tool_logs else []
        
    def get_active_operations(self) -> List[Dict[str, Any]]:
        """Get currently active operations"""
        return list(self.active_operations.values())

# File Change Monitoring System
class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable[[str, str, str], None]):
        self.callback = callback
        self.logger = logging.getLogger(__name__ + ".file_monitor")
        
    def on_modified(self, event):
        if not event.is_directory:
            self.callback(event.src_path, "modified", datetime.now().isoformat())
            self.logger.info(f"📝 File modified: {event.src_path}")
            
    def on_created(self, event):
        if not event.is_directory:
            self.callback(event.src_path, "created", datetime.now().isoformat())
            self.logger.info(f"📄 File created: {event.src_path}")
            
    def on_deleted(self, event):
        if not event.is_directory:
            self.callback(event.src_path, "deleted", datetime.now().isoformat())
            self.logger.info(f"🗑️ File deleted: {event.src_path}")

class FileMonitor:
    def __init__(self):
        self.observer = Observer()
        self.file_changes = []
        self.is_monitoring = False
        self.watched_paths = set()
        
    def start_monitoring(self, path: str):
        """Start monitoring a directory for file changes"""
        if not self.is_monitoring:
            handler = FileChangeHandler(self._on_file_change)
            self.observer.schedule(handler, path, recursive=True)
            self.observer.start()
            self.is_monitoring = True
            self.watched_paths.add(path)
            
    def stop_monitoring(self):
        """Stop file monitoring"""
        if self.is_monitoring:
            self.observer.stop()
            self.observer.join()
            self.is_monitoring = False
            self.watched_paths.clear()
            
    def _on_file_change(self, file_path: str, change_type: str, timestamp: str):
        """Handle file change events"""
        # Filter out common temporary/cache files
        if any(skip in file_path for skip in ['.git', '__pycache__', 'node_modules', '.next', '.DS_Store']):
            return
            
        change_entry = {
            "file_path": file_path,
            "change_type": change_type,
            "timestamp": timestamp,
            "relative_path": os.path.relpath(file_path, get_project_folder()) if get_project_folder() else file_path
        }
        self.file_changes.append(change_entry)
        
        # Keep only last 100 changes
        if len(self.file_changes) > 100:
            self.file_changes = self.file_changes[-100:]
            
    def get_recent_changes(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent file changes"""
        return self.file_changes[-limit:] if self.file_changes else []

# Global instances
tool_usage_logger = ToolUsageLogger()
file_monitor = FileMonitor()

# Global session context
_current_session_id: Optional[str] = None
_current_project_folder: Optional[str] = None

# WebSocket notification functions
def notify_tool_usage(tool_name: str, event_type: str, data: Dict[str, Any]):
    """Send tool usage notification via WebSocket (non-blocking)."""
    try:
        # Import here to avoid circular imports
        from app.websocket_utils import broadcast_tool_usage
        
        # Run the async function in a new task if there's an event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task to run the broadcast
                asyncio.create_task(broadcast_tool_usage(tool_name, event_type, data, _current_session_id))
            else:
                # Run in new event loop
                asyncio.run(broadcast_tool_usage(tool_name, event_type, data, _current_session_id))
        except RuntimeError:
            # No event loop, run in new one
            asyncio.run(broadcast_tool_usage(tool_name, event_type, data, _current_session_id))
    except Exception as e:
        logger.warning(f"Failed to send tool usage notification: {e}")

def notify_file_operation(operation_type: str, file_path: str, data: Dict[str, Any]):
    """Send file operation notification via WebSocket (non-blocking)."""
    try:
        # Import here to avoid circular imports
        from app.websocket_utils import broadcast_file_operation
        
        # Run the async function in a new task if there's an event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task to run the broadcast
                asyncio.create_task(broadcast_file_operation(operation_type, file_path, data, _current_session_id))
            else:
                # Run in new event loop
                asyncio.run(broadcast_file_operation(operation_type, file_path, data, _current_session_id))
        except RuntimeError:
            # No event loop, run in new one
            asyncio.run(broadcast_file_operation(operation_type, file_path, data, _current_session_id))
    except Exception as e:
        logger.warning(f"Failed to send file operation notification: {e}")

def tool_with_notifications(func):
    """Decorator to add WebSocket notifications to tool functions."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        
        # Log tool start
        start_time = time.time()
        notify_tool_usage(tool_name, "start", {
            "parameters": {"args": args, "kwargs": kwargs},
            "start_time": start_time
        })
        
        try:
            # Execute the tool
            result = func(*args, **kwargs)
            
            # Log tool completion
            end_time = time.time()
            duration = end_time - start_time
            
            notify_tool_usage(tool_name, "complete", {
                "result": str(result)[:500] if result else None,  # Truncate long results
                "duration": duration,
                "success": True
            })
            
            return result
            
        except Exception as e:
            # Log tool error
            end_time = time.time()
            duration = end_time - start_time
            
            notify_tool_usage(tool_name, "error", {
                "error": str(e),
                "duration": duration,
                "success": False
            })
            
            raise  # Re-raise the exception
    
    return wrapper

def set_session_context(session_id: str, project_folder: str) -> None:
    """Set the current session context."""
    global _current_session_id, _current_project_folder
    _current_session_id = session_id
    _current_project_folder = project_folder
    logger.info(f"Set session context: {session_id}, folder: {project_folder}")

def get_project_folder() -> str:
    """Get the current project folder."""
    if _current_project_folder:
        return _current_project_folder

    # Fallback to NextLovable root if no session is set
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.dirname(current_dir)  # Go up to NextLovable

def read_file_content(file_path: str) -> Dict[str, Any]:
    """Read file content with comprehensive path safety validation."""
    try:
        # Initialize path validator with current project root
        project_root = get_project_folder()
        validator = get_path_validator(project_root)
        
        # Validate path with read access level
        is_valid, safe_path, error_msg = validator.validate_path(
            file_path, 
            AccessLevel.READ_ONLY, 
            "read"
        )
        
        if not is_valid:
            logger.warning(f"Path validation failed for read operation: {error_msg}")
            return {"success": False, "error": f"Access denied: {error_msg}"}

        if not safe_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        if not safe_path.is_file():
            return {"success": False, "error": f"Path is not a file: {file_path}"}

        # Check file size (limit to 1MB)
        if safe_path.stat().st_size > 1024 * 1024:
            return {"success": False, "error": f"File too large to read ({safe_path.stat().st_size} bytes). Maximum size is 1MB."}

        content = safe_path.read_text(encoding='utf-8', errors='replace')
        
        # Log successful file access
        logger.debug(f"Successfully read file: {file_path} -> {safe_path}")
        
        return {"success": True, "content": content}

    except PathValidationError as e:
        logger.error(f"Path validation error reading {file_path}: {str(e)}")
        return {"success": False, "error": f"Security error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error reading {file_path}: {str(e)}")
        return {"success": False, "error": f"Error reading file {file_path}: {str(e)}"}

def write_file_content(file_path: str, content: str) -> Dict[str, Any]:
    """Write content to file with comprehensive path safety validation."""
    try:
        # Initialize path validator with current project root
        project_root = get_project_folder()
        validator = get_path_validator(project_root)
        
        # Validate path with write access level
        is_valid, safe_path, error_msg = validator.validate_path(
            file_path, 
            AccessLevel.READ_WRITE, 
            "write"
        )
        
        if not is_valid:
            logger.warning(f"Path validation failed for write operation: {error_msg}")
            # Notify file operation error
            notify_file_operation("write", file_path, {
                "operation": "write_file",
                "error": f"Security validation failed: {error_msg}",
                "success": False
            })
            return {"success": False, "error": f"Access denied: {error_msg}"}

        # Create parent directories if they don't exist
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        safe_path.write_text(content, encoding='utf-8')
        
        # Log successful file write
        logger.debug(f"Successfully wrote file: {file_path} -> {safe_path}")
        
        # Automatically index file in ChromaDB
        if CHROMA_INTEGRATION_AVAILABLE:
            try:
                # Run async function in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(chroma_integration.index_file(str(safe_path)))
                loop.close()
                logger.info(f"Successfully indexed {file_path} in ChromaDB")
            except Exception as e:
                logger.warning(f"Failed to index {file_path} in ChromaDB: {e}")
        
        # Notify file operation
        notify_file_operation("write", file_path, {
            "operation": "write_file",
            "size": len(content),
            "success": True
        })
        
        return {"success": True}

    except PathValidationError as e:
        logger.error(f"Path validation error writing {file_path}: {str(e)}")
        # Notify file operation error
        notify_file_operation("write", file_path, {
            "operation": "write_file",
            "error": f"Security error: {str(e)}",
            "success": False
        })
        return {"success": False, "error": f"Security error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error writing {file_path}: {str(e)}")
        # Notify file operation error
        notify_file_operation("write", file_path, {
            "operation": "write_file",
            "error": str(e),
            "success": False
        })
        return {"success": False, "error": f"Error writing file {file_path}: {str(e)}"}

def list_directory(dir_path: str = ".") -> Dict[str, Any]:
    """List directory contents with comprehensive path safety validation."""
    try:
        # Initialize path validator with current project root
        project_root = get_project_folder()
        validator = get_path_validator(project_root)
        
        # Validate path with read access level
        is_valid, safe_path, error_msg = validator.validate_path(
            dir_path, 
            AccessLevel.READ_ONLY, 
            "list"
        )
        
        if not is_valid:
            logger.warning(f"Path validation failed for list operation: {error_msg}")
            return {"success": False, "error": f"Access denied: {error_msg}"}

        if not safe_path.exists():
            return {"success": False, "error": f"Directory not found: {dir_path}"}

        if not safe_path.is_dir():
            return {"success": False, "error": f"Path is not a directory: {dir_path}"}

        items = []
        for item in sorted(safe_path.iterdir()):
            item_type = "directory" if item.is_dir() else "file"
            size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
            items.append(f"{item_type}: {item.name}{size}")

        # Log successful directory listing
        logger.debug(f"Successfully listed directory: {dir_path} -> {safe_path}")
        
        return {"success": True, "items": items}

    except PathValidationError as e:
        logger.error(f"Path validation error listing {dir_path}: {str(e)}")
        return {"success": False, "error": f"Security error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error listing {dir_path}: {str(e)}")
        return {"success": False, "error": f"Error listing directory {dir_path}: {str(e)}"}

def run_terminal_command(command: str) -> Dict[str, Any]:
    """Run a terminal command with enhanced security validation."""
    try:
        import subprocess
        
        # Initialize path validator for command validation
        project_root = get_project_folder()
        validator = get_path_validator(project_root)

        # Enhanced security - prevent dangerous commands and patterns
        dangerous_commands = [
            'rm -rf', 'rmdir', 'del', 'format', 'fdisk', 'mkfs', 'dd if=', 'sudo',
            'chmod 777', 'chown', 'passwd', 'su -', 'curl', 'wget', 'nc -', 'netcat',
            'python -c', 'eval', 'exec', 'system(', 'os.system', 'subprocess.call',
            '$(', '`', 'sh -c', 'bash -c', '&&', '||', ';', '|', '>', '>>', '<'
        ]
        
        command_lower = command.lower()
        for dangerous in dangerous_commands:
            if dangerous in command_lower:
                logger.warning(f"Blocked dangerous command: {command}")
                return {"success": False, "error": f"Command contains potentially dangerous operation: '{dangerous}'"}

        # Check for path traversal attempts in command
        if '..' in command or '~' in command:
            logger.warning(f"Blocked command with path traversal attempt: {command}")
            return {"success": False, "error": "Command contains path traversal patterns"}

        # Validate working directory
        try:
            is_valid, safe_cwd, error_msg = validator.validate_path(
                ".", 
                AccessLevel.READ_ONLY, 
                "command_execution"
            )
            
            if not is_valid:
                logger.warning(f"Working directory validation failed: {error_msg}")
                return {"success": False, "error": f"Working directory access denied: {error_msg}"}
                
        except PathValidationError as e:
            logger.error(f"Path validation error for command execution: {str(e)}")
            return {"success": False, "error": f"Security error: {str(e)}"}

        # Log command execution attempt
        logger.info(f"Executing command: {command}")

        # Run the command with restricted environment
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=str(safe_cwd),
            env={
                'PATH': os.environ.get('PATH', ''),
                'HOME': os.environ.get('HOME', ''),
                'USER': os.environ.get('USER', ''),
                'PWD': str(safe_cwd)
            }
        )

        # Log command completion
        logger.debug(f"Command completed with return code: {result.returncode}")

        return {
            "success": True,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except subprocess.TimeoutExpired:
        logger.warning(f"Command timed out: {command}")
        return {"success": False, "error": "Command timed out after 30 seconds"}
    except PathValidationError as e:
        logger.error(f"Path validation error for command: {str(e)}")
        return {"success": False, "error": f"Security error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error running command '{command}': {str(e)}")
        return {"success": False, "error": f"Error running command: {str(e)}"}

# Tool definitions using @tool decorator

@tool
@tool_with_notifications
def grep_search(query: str, include_pattern: str = "*") -> str:
    """Search for text patterns in files using regex with enhanced security validation.

    Args:
        query: The regex pattern to search for
        include_pattern: Glob pattern for files to search in (default: all files)
    """
    try:
        import glob
        import re
        
        project_root = get_project_folder()
        validator = get_path_validator(project_root)
        results = []

        # Validate search pattern for security
        if '..' in include_pattern or '~' in include_pattern:
            return f"Error: Search pattern contains path traversal characters: {include_pattern}"

        # Find files matching the pattern
        pattern = str(Path(project_root) / "**" / include_pattern)
        files = glob.glob(pattern, recursive=True)

        for file_path_str in files[:50]:  # Limit to 50 files
            file_path = Path(file_path_str)

            # Skip common directories
            if any(skip in str(file_path) for skip in ['node_modules', '.git', '__pycache__', '.next']):
                continue

            try:
                # Validate file path with path safety
                rel_path = file_path.relative_to(Path(project_root))
                is_valid, safe_path, error_msg = validator.validate_path(
                    str(rel_path), 
                    AccessLevel.READ_ONLY, 
                    "grep_search"
                )
                
                if not is_valid:
                    logger.debug(f"Skipping file due to path validation: {rel_path} - {error_msg}")
                    continue

                if file_path.exists() and file_path.is_file():
                    content = file_path.read_text(encoding='utf-8', errors='replace')
                    lines = content.split('\n')

                    for line_num, line in enumerate(lines, 1):
                        if re.search(query, line, re.IGNORECASE):
                            results.append(f"{rel_path}:{line_num}: {line.strip()}")

                            if len(results) >= 100:  # Limit results
                                break
            except PathValidationError as e:
                logger.debug(f"Path validation error for {file_path}: {str(e)}")
                continue
            except Exception as e:
                logger.debug(f"Error processing file {file_path}: {str(e)}")
                continue

            if len(results) >= 100:
                break

        if results:
            return f"Found {len(results)} matches for '{query}':\n\n" + "\n".join(results)
        else:
            return f"No matches found for '{query}' in files matching '{include_pattern}'"
    except Exception as e:
        logger.error(f"Error in grep_search: {str(e)}")
        return f"Error searching for '{query}': {str(e)}"

@tool
@tool_with_notifications
def replace_in_file(path: str, old_string: str, new_string: str) -> str:
    """Replace text in a file with enhanced security validation.

    Args:
        path: Relative path to the file from project root
        old_string: The text to replace (must be unique in the file)
        new_string: The replacement text
    """
    try:
        project_root = get_project_folder()
        validator = get_path_validator(project_root)

        # Validate file path with path safety
        try:
            is_valid, safe_file_path, error_msg = validator.validate_path(
                path, 
                AccessLevel.WRITE, 
                "replace_in_file"
            )
            
            if not is_valid:
                logger.warning(f"File access denied for replace operation: {path} - {error_msg}")
                return f"Access denied: {error_msg}"
                
        except PathValidationError as e:
            logger.error(f"Path validation error for replace operation: {str(e)}")
            return f"Security error: {str(e)}"

        if not safe_file_path.exists() or not safe_file_path.is_file():
            return f"File not found: {path}"

        content = safe_file_path.read_text(encoding='utf-8')

        if old_string not in content:
            return f"Old string not found in file: {old_string}"

        # Count occurrences
        count = content.count(old_string)
        if count > 1:
            return f"Old string appears {count} times. Please make it more specific."

        new_content = content.replace(old_string, new_string, 1)
        safe_file_path.write_text(new_content, encoding='utf-8')

        # Log successful operation
        logger.info(f"Successfully replaced text in {path}")

        # Notify file operation
        notify_file_operation("modify", path, {
            "operation": "replace_text",
            "old_string": old_string[:100],  # Truncate for brevity
            "new_string": new_string[:100],
            "success": True
        })

        return f"Successfully replaced text in {path}"
    except PathValidationError as e:
        logger.error(f"Path validation error for replace operation: {str(e)}")
        # Notify file operation error
        notify_file_operation("modify", path, {
            "operation": "replace_text",
            "error": f"Security error: {str(e)}",
            "success": False
        })
        return f"Security error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in replace_in_file for {path}: {str(e)}")
        # Notify file operation error
        notify_file_operation("modify", path, {
            "operation": "replace_text",
            "error": str(e),
            "success": False
        })
        return f"Error replacing text in file: {str(e)}"

@tool
@tool_with_notifications
def replace_block_in_file(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """Replace a block of lines in a file with new content.

    Args:
        path: Relative path to the file from project root
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (1-indexed, inclusive)
        new_content: The replacement content for the block
    """
    try:
        project_root = get_project_folder()
        validator = get_path_validator(project_root)

        # Validate file path with path safety
        try:
            is_valid, safe_file_path, error_msg = validator.validate_path(
                path, 
                AccessLevel.WRITE, 
                "replace_block_in_file"
            )
            
            if not is_valid:
                logger.warning(f"File access denied for replace block operation: {path} - {error_msg}")
                return f"Access denied: {error_msg}"
                
        except PathValidationError as e:
            logger.error(f"Path validation error for replace block operation: {str(e)}")
            return f"Security error: {str(e)}"

        if not safe_file_path.exists() or not safe_file_path.is_file():
            return f"File not found: {path}"

        with open(safe_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Validate line numbers
        total_lines = len(lines)
        if start_line < 1 or start_line > total_lines:
            return f"Invalid start_line: {start_line}. File has {total_lines} lines."
        if end_line < start_line or end_line > total_lines:
            return f"Invalid end_line: {end_line}. Must be >= start_line and <= {total_lines}."

        # Replace the block
        new_lines = []
        if isinstance(new_content, str):
            new_lines = [line + '\n' if not line.endswith('\n') else line 
                        for line in new_content.splitlines()]
        else:
            new_lines = [str(line) + '\n' for line in new_content]

        # Replace lines from start_line-1 to end_line (inclusive)
        lines[start_line-1:end_line] = new_lines

        # Write back to file
        with open(safe_file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        # Log successful operation
        logger.info(f"Successfully replaced block in {path} (lines {start_line}-{end_line})")

        # Notify file operation
        notify_file_operation("modify", path, {
            "operation": "replace_block",
            "start_line": start_line,
            "end_line": end_line,
            "new_content_length": len(new_content),
            "success": True
        })

        return f"Successfully replaced block in {path} (lines {start_line}-{end_line})"
    except PathValidationError as e:
        logger.error(f"Path validation error for replace block operation: {str(e)}")
        # Notify file operation error
        notify_file_operation("modify", path, {
            "operation": "replace_block",
            "error": f"Security error: {str(e)}",
            "success": False
        })
        return f"Security error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error in replace_block_in_file for {path}: {str(e)}")
        # Notify file operation error
        notify_file_operation("modify", path, {
            "operation": "replace_block",
            "error": str(e),
            "success": False
        })
        return f"Error replacing block in file: {str(e)}"

@tool
def get_project_structure(max_depth: int = 3) -> str:
    """Get the overall project structure as a tree. Use this to understand the codebase layout.

    Args:
        max_depth: Maximum depth to traverse (default: 3)
    """
    try:
        project_root = Path(get_project_folder())

        def build_tree(path: Path, current_depth: int = 0, prefix: str = "") -> List[str]:
            if current_depth > max_depth:
                return []

            lines = []
            try:
                items = sorted(path.iterdir())
            except PermissionError:
                return [f"{prefix}[ACCESS DENIED] {path.name}"]

            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "

                # Skip common directories
                if item.name in ['node_modules', '.git', '__pycache__', '.next', '.vscode']:
                    lines.append(f"{prefix}{connector}[{item.name.upper()}]")
                    continue

                lines.append(f"{prefix}{connector}{item.name}")

                if item.is_dir() and current_depth < max_depth:
                    extension = "    " if is_last else "│   "
                    lines.extend(build_tree(item, current_depth + 1, prefix + extension))

            return lines

        tree_lines = [str(project_root.name) + "/"] + build_tree(project_root, 0, "")
        return "\n".join(tree_lines)
    except Exception as e:
        return f"Error getting project structure: {str(e)}"

@tool
def search_code(query: str, file_extensions: str = "*.ts,*.js,*.py,*.tsx,*.jsx", max_results: int = 20) -> str:
    """Search for code patterns across the project using advanced search.

    Args:
        query: Search query (supports regex)
        file_extensions: Comma-separated list of file extensions to search (default: common code files)
        max_results: Maximum number of results to return (default: 20)
    """
    try:
        import glob
        import re
        
        project_root = Path(get_project_folder())
        results = []
        
        # Parse file extensions
        extensions = [ext.strip() for ext in file_extensions.split(',')]
        
        # Search through files
        for ext in extensions:
            pattern = str(project_root / "**" / ext)
            files = glob.glob(pattern, recursive=True)
            
            for file_path_str in files:
                file_path = Path(file_path_str)
                
                # Skip common directories
                if any(skip in str(file_path) for skip in ['node_modules', '.git', '__pycache__', '.next', 'dist', 'build']):
                    continue
                
                try:
                    if file_path.exists() and file_path.is_file():
                        content = file_path.read_text(encoding='utf-8', errors='replace')
                        lines = content.split('\n')
                        
                        for line_num, line in enumerate(lines, 1):
                            if re.search(query, line, re.IGNORECASE):
                                rel_path = file_path.relative_to(project_root)
                                results.append({
                                    'file': str(rel_path),
                                    'line': line_num,
                                    'content': line.strip(),
                                    'match': re.search(query, line, re.IGNORECASE).group() if re.search(query, line, re.IGNORECASE) else query
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
            output = f"Found {len(results)} matches for '{query}':\n\n"
            for result in results:
                output += f"{result['file']}:{result['line']}: {result['content']}\n"
            return output
        else:
            return f"No matches found for '{query}' in files with extensions: {file_extensions}"
    except Exception as e:
        return f"Error searching code: {str(e)}"

@tool
@tool_with_notifications
def read_file(filePath: str) -> str:
    """Read the contents of a file. Use this to examine source code, configuration files, or any text content."""
    logger.info(f"📖 Reading file: {filePath}")

    result = read_file_content(filePath)
    if result["success"]:
        return f"File: {filePath}\n\n{result['content']}"
    else:
        return f"Error reading file: {result['error']}"

@tool
@tool_with_notifications
def write_file(filePath: str, content: str) -> str:
    """Create or overwrite a file with content. Use this to create new files or completely replace existing ones."""
    logger.info(f"✏️ Writing file: {filePath}")

    result = write_file_content(filePath, content)
    if result["success"]:
        return f"Successfully wrote {len(content)} characters to {filePath}"
    else:
        return f"Error writing file: {result['error']}"

@tool
@tool_with_notifications
def list_dir(dirPath: str = ".") -> str:
    """List the contents of a directory. Use this to explore project structure and find files."""
    logger.info(f"📁 Listing directory: {dirPath}")

    result = list_directory(dirPath)
    if result["success"]:
        items_str = "\n".join(result["items"])
        return f"Directory contents for {dirPath}:\n{items_str}"
    else:
        return f"Error listing directory: {result['error']}"

@tool
def run_terminal_command_tool(command: str) -> str:
    """Run a terminal command in the project directory. Use this for building, testing, or running scripts."""
    logger.info(f"💻 Running command: {command}")

    result = run_terminal_command(command)
    if result["success"]:
        output = ""
        if result["stdout"]:
            output += f"STDOUT:\n{result['stdout']}\n"
        if result["stderr"]:
            output += f"STDERR:\n{result['stderr']}\n"
        if result["returncode"] != 0:
            output += f"Exit code: {result['returncode']}"
        return output.strip() if output else f"Command completed with exit code {result['returncode']}"
    else:
        return f"Error running command: {result['error']}"

@tool
def search_files(pattern: str, dirPath: str = ".") -> str:
    """Search for files matching a pattern using glob syntax. Use this to find specific files in the project."""
    logger.info(f"🔍 Searching for files matching '{pattern}' in {dirPath}")

    try:
        import glob
        project_root = get_project_folder()
        search_path = Path(project_root) / dirPath.lstrip('/')

        # Security check
        search_path = search_path.resolve()
        project_root_path = Path(project_root).resolve()

        if not str(search_path).startswith(str(project_root_path)):
            return f"Access denied: Cannot search outside project directory. Path: {dirPath}"

        # Perform glob search
        matches = glob.glob(str(search_path / pattern), recursive=True)

        # Filter to only include files within project directory
        valid_matches = []
        for match in matches:
            match_path = Path(match).resolve()
            if str(match_path).startswith(str(project_root_path)):
                valid_matches.append(str(match_path.relative_to(project_root_path)))

        if valid_matches:
            return f"Found {len(valid_matches)} files matching '{pattern}':\n" + "\n".join(valid_matches)
        else:
            return f"No files found matching pattern '{pattern}' in {dirPath}"

    except Exception as e:
        return f"Error searching files: {str(e)}"

@tool
def create_directory(dirPath: str) -> str:
    """Create a new directory (including parent directories if needed)."""
    logger.info(f"📁 Creating directory: {dirPath}")

    try:
        project_root = get_project_folder()
        full_path = Path(project_root) / dirPath.lstrip('/')

        # Security check
        full_path = full_path.resolve()
        project_root_path = Path(project_root).resolve()

        if not str(full_path).startswith(str(project_root_path)):
            return f"Access denied: Cannot create directories outside project directory. Path: {dirPath}"

        full_path.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory: {dirPath}"

    except Exception as e:
        return f"Error creating directory {dirPath}: {str(e)}"

# Export all tools as a list
@tool
def validate_syntax(file_path: str, language: str = "auto") -> str:
    """Validate syntax of a code file. Supports multiple languages.

    Args:
        file_path: Path to the file to validate
        language: Programming language (auto, python, javascript, typescript, json, yaml, xml)
    """
    try:
        project_root = get_project_folder()
        file_path_obj = Path(project_root) / file_path.lstrip('/')

        # Security check
        file_path_obj = file_path_obj.resolve()
        project_root_path = Path(project_root).resolve()

        if not str(file_path_obj).startswith(str(project_root_path)):
            return f"Access denied: Cannot access files outside project directory. Path: {file_path}"

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')

        if language == "auto":
            ext = file_path_obj.suffix.lower()
            if ext == ".py":
                language = "python"
            elif ext in [".js", ".mjs"]:
                language = "javascript"
            elif ext in [".ts", ".tsx"]:
                language = "typescript"
            elif ext == ".json":
                language = "json"
            elif ext in [".yml", ".yaml"]:
                language = "yaml"
            elif ext == ".xml":
                language = "xml"
            else:
                return f"Cannot auto-detect language for extension: {ext}"

        errors = []

        if language == "python":
            try:
                compile(content, file_path, 'exec')
            except SyntaxError as e:
                errors.append(f"Syntax Error: {e.msg} at line {e.lineno}")
            except Exception as e:
                errors.append(f"Error: {str(e)}")

        elif language in ["javascript", "typescript"]:
            # Basic validation - check for common syntax issues
            import re
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                # Check for unmatched braces
                open_braces = line.count('{')
                close_braces = line.count('}')
                if open_braces != close_braces:
                    errors.append(f"Line {i}: Unmatched braces")

                # Check for missing semicolons (basic check)
                if line.strip().endswith(('++', '--', 'return', 'break', 'continue', 'throw')) and not line.strip().endswith(';'):
                    if not any(keyword in line for keyword in ['if', 'for', 'while', 'function']):
                        errors.append(f"Line {i}: Missing semicolon")

        elif language == "json":
            try:
                import json
                json.loads(content)
            except json.JSONDecodeError as e:
                errors.append(f"JSON Error: {e.msg} at line {e.lineno}")

        elif language == "yaml":
            try:
                import yaml
                yaml.safe_load(content)
            except yaml.YAMLError as e:
                errors.append(f"YAML Error: {str(e)}")

        elif language == "xml":
            try:
                import xml.etree.ElementTree as ET
                ET.fromstring(content)
            except ET.ParseError as e:
                errors.append(f"XML Error: {str(e)}")

        if errors:
            return f"Syntax validation failed for {file_path}:\n" + "\n".join(errors)
        else:
            return f"Syntax validation passed for {file_path}"

    except Exception as e:
        return f"Error validating syntax: {str(e)}"

@tool
def format_code(file_path: str, language: str = "auto") -> str:
    """Format code using appropriate formatter for the language.

    Args:
        file_path: Path to the file to format
        language: Programming language (auto, python, javascript, typescript, json, css, html)
    """
    try:
        project_root = get_project_folder()
        file_path_obj = Path(project_root) / file_path.lstrip('/')

        # Security check
        file_path_obj = file_path_obj.resolve()
        project_root_path = Path(project_root).resolve()

        if not str(file_path_obj).startswith(str(project_root_path)):
            return f"Access denied: Cannot access files outside project directory. Path: {file_path}"

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        if language == "auto":
            ext = file_path_obj.suffix.lower()
            if ext == ".py":
                language = "python"
            elif ext in [".js", ".mjs"]:
                language = "javascript"
            elif ext in [".ts", ".tsx"]:
                language = "typescript"
            elif ext == ".json":
                language = "json"
            elif ext == ".css":
                language = "css"
            elif ext in [".html", ".htm"]:
                language = "html"
            else:
                return f"Cannot auto-detect language for extension: {ext}"

        content = file_path_obj.read_text(encoding='utf-8')

        if language == "python":
            # Basic Python formatting
            import re
            lines = content.split('\n')
            formatted_lines = []
            for line in lines:
                # Remove trailing whitespace
                line = line.rstrip()
                # Add consistent indentation (basic)
                if line.strip():
                    formatted_lines.append(line)
                else:
                    formatted_lines.append('')
            formatted_content = '\n'.join(formatted_lines)

        elif language == "json":
            try:
                import json
                parsed = json.loads(content)
                formatted_content = json.dumps(parsed, indent=2, ensure_ascii=False)
            except json.JSONDecodeError as e:
                return f"Cannot format invalid JSON: {e.msg}"

        else:
            # For other languages, just clean up whitespace
            lines = content.split('\n')
            formatted_lines = [line.rstrip() for line in lines]
            formatted_content = '\n'.join(formatted_lines)

        # Write formatted content back
        file_path_obj.write_text(formatted_content, encoding='utf-8')
        return f"Successfully formatted {file_path}"

    except Exception as e:
        return f"Error formatting code: {str(e)}"

@tool
def check_dependencies(package_file: str = "auto") -> str:
    """Check and analyze project dependencies.

    Args:
        package_file: Package file to analyze (auto, package.json, requirements.txt, pyproject.toml)
    """
    try:
        project_root = get_project_folder()

        if package_file == "auto":
            # Auto-detect package file
            if (Path(project_root) / "package.json").exists():
                package_file = "package.json"
            elif (Path(project_root) / "requirements.txt").exists():
                package_file = "requirements.txt"
            elif (Path(project_root) / "pyproject.toml").exists():
                package_file = "pyproject.toml"
            else:
                return "No package file found (package.json, requirements.txt, or pyproject.toml)"

        file_path = Path(project_root) / package_file
        if not file_path.exists():
            return f"Package file not found: {package_file}"

        content = file_path.read_text(encoding='utf-8')

        if package_file == "package.json":
            try:
                import json
                data = json.loads(content)

                result = f"Dependencies Analysis for {package_file}:\n\n"

                deps = data.get('dependencies', {})
                dev_deps = data.get('devDependencies', {})

                result += f"Runtime Dependencies: {len(deps)}\n"
                if deps:
                    for name, version in list(deps.items())[:10]:
                        result += f"  {name}: {version}\n"
                    if len(deps) > 10:
                        result += f"  ... and {len(deps) - 10} more\n"

                result += f"\nDev Dependencies: {len(dev_deps)}\n"
                if dev_deps:
                    for name, version in list(dev_deps.items())[:10]:
                        result += f"  {name}: {version}\n"
                    if len(dev_deps) > 10:
                        result += f"  ... and {len(dev_deps) - 10} more\n"

                scripts = data.get('scripts', {})
                result += f"\nScripts: {len(scripts)}\n"
                if scripts:
                    for name, command in list(scripts.items())[:5]:
                        result += f"  {name}: {command}\n"
                    if len(scripts) > 5:
                        result += f"  ... and {len(scripts) - 5} more\n"

                return result

            except json.JSONDecodeError as e:
                return f"Invalid JSON in {package_file}: {e}"

        elif package_file == "requirements.txt":
            lines = content.split('\n')
            packages = []

            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Extract package name (handle version specifiers)
                    import re
                    pkg_name = re.split(r'[>=<~!]', line)[0].strip()
                    if pkg_name:
                        packages.append(pkg_name)

            result = f"Dependencies Analysis for {package_file}:\n\n"
            result += f"Python Packages: {len(packages)}\n"
            if packages:
                for pkg in packages[:20]:
                    result += f"  {pkg}\n"
                if len(packages) > 20:
                    result += f"  ... and {len(packages) - 20} more\n"

            return result

        elif package_file == "pyproject.toml":
            result = f"Dependencies Analysis for {package_file}:\n\n"
            result += "TOML dependency analysis not fully implemented yet"
            return result

        return f"Unsupported package file: {package_file}"

    except Exception as e:
        return f"Error checking dependencies: {str(e)}"

@tool
def analyze_dependencies(file_path: str) -> str:
    """Analyze project dependencies and suggest improvements.

    Args:
        file_path: Path to package.json, requirements.txt, or project file
    """
    try:
        project_root = get_project_folder()
        file_path_obj = Path(project_root) / file_path.lstrip('/')

        # Security check
        file_path_obj = file_path_obj.resolve()
        project_root_path = Path(project_root).resolve()

        if not str(file_path_obj).startswith(str(project_root_path)):
            return f"Access denied: Cannot access files outside project directory. Path: {file_path}"

        if not file_path_obj.exists():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        filename = file_path_obj.name.lower()

        analysis = []

        if filename == 'package.json':
            import json
            try:
                pkg_data = json.loads(content)

                # Check dependencies
                deps = pkg_data.get('dependencies', {})
                dev_deps = pkg_data.get('devDependencies', {})

                analysis.append(f"Total dependencies: {len(deps)}")
                analysis.append(f"Dev dependencies: {len(dev_deps)}")

                # Check for outdated practices
                if 'lodash' in deps:
                    analysis.append("Consider using lodash-es for tree-shaking")
                if 'moment' in deps:
                    analysis.append("Consider using date-fns or dayjs instead of moment")

                # Check for security issues (basic)
                risky_deps = ['left-pad', 'event-stream', 'flatmap-stream']
                found_risky = [dep for dep in deps.keys() if dep in risky_deps]
                if found_risky:
                    analysis.append(f"Potentially risky dependencies found: {found_risky}")

            except json.JSONDecodeError:
                return "Invalid JSON in package.json"

        elif filename == 'requirements.txt':
            lines = content.split('\n')
            deps = [line.strip() for line in lines if line.strip() and not line.startswith('#')]

            analysis.append(f"Python dependencies: {len(deps)}")

            # Check for version pinning
            unpinned = [dep for dep in deps if '==' not in dep and '>=' not in dep and '~=' not in dep]
            if unpinned:
                analysis.append(f"Unpinned dependencies: {len(unpinned)} (consider pinning versions)")

        elif filename in ['pyproject.toml', 'setup.py', 'setup.cfg']:
            analysis.append(f"Python project file detected: {filename}")
            analysis.append("Dependency analysis for Python project files not yet implemented")

        else:
            return f"Unsupported dependency file: {filename}"

        if analysis:
            return f"Dependency analysis for {file_path}:\n" + "\n".join(f"  - {item}" for item in analysis)
        else:
            return f"No specific issues found in {file_path}"

    except Exception as e:
        return f"Error analyzing dependencies: {str(e)}"

@tool
def semantic_search_codebase(query: str, max_results: int = 5) -> str:
    """Search the codebase using semantic similarity to find relevant code sections.
    
    Args:
        query: Natural language description of what you're looking for
        max_results: Maximum number of results to return (default: 5)
    """
    if not CHROMA_INTEGRATION_AVAILABLE:
        return "ChromaDB integration not available. Install chromadb and sentence-transformers to use semantic search."
    
    try:
        # Use the new ChromaDB integration service
        results = chroma_integration.search_files(query, collection_name="files", n_results=max_results)
        
        if not results:
            return f"No semantic matches found for: {query}"
        
        output = f"Found {len(results)} semantic matches for '{query}':\n\n"
        
        for i, result in enumerate(results, 1):
            metadata = result.get('metadata', {})
            file_path = metadata.get('file_path', 'Unknown file')
            line_start = metadata.get('line_start', 'Unknown line')
            score = result.get('score', 0)
            content = result.get('content', '').strip()
            
            output += f"{i}. {file_path}:{line_start} (similarity: {score:.3f})\n"
            output += f"   {content[:200]}{'...' if len(content) > 200 else ''}\n\n"
        
        return output
    except Exception as e:
        return f"Error in semantic search: {str(e)}"

@tool
def index_codebase_for_search(file_extensions: str = "*.py,*.js,*.ts,*.tsx,*.jsx,*.java,*.cpp,*.c,*.h", chunk_size: int = 500) -> str:
    """Index the codebase for semantic search by creating embeddings of code chunks.
    
    Args:
        file_extensions: Comma-separated list of file extensions to index
        chunk_size: Size of code chunks in characters (default: 500)
    """
    if not CHROMA_INTEGRATION_AVAILABLE:
        return "ChromaDB integration not available. Install chromadb and sentence-transformers to use indexing."
    
    try:
        project_root = Path(get_project_folder())
        
        # Use the new ChromaDB integration service to index the directory
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(chroma_integration.index_directory(
                str(project_root), 
                collection_name="files"
            ))
            
            # Get stats to report back
            stats = chroma_integration.get_collection_stats("files")
            total_chunks = stats.get('total_chunks', 0)
            
            return f"Successfully indexed codebase using new ChromaDB integration. Total chunks: {total_chunks}"
            
        finally:
            loop.close()
            
    except Exception as e:
        return f"Error indexing codebase: {str(e)}"

@tool
def get_vector_store_stats() -> str:
    """Get statistics about the ChromaDB collections and indexed content."""
    if not CHROMA_INTEGRATION_AVAILABLE:
        return "ChromaDB integration not available. Install chromadb and sentence-transformers to use vector store."
    
    try:
        # Get stats for the main files collection
        stats = chroma_integration.get_collection_stats("files")
        
        if not stats or stats.get('total_chunks', 0) == 0:
            return "No collections found in ChromaDB. Run index_codebase_for_search first."
        
        output = "ChromaDB Statistics:\n\n"
        
        total_chunks = stats.get('total_chunks', 0)
        output += f"Collection 'files': {total_chunks} chunks\n"
        
        output += f"\nTotal indexed chunks: {total_chunks}"
        
        return output
    except Exception as e:
        return f"Error getting ChromaDB stats: {str(e)}"

@tool
def find_similar_code(code_snippet: str, max_results: int = 5) -> str:
    """Find code sections similar to the provided code snippet.
    
    Args:
        code_snippet: Code snippet to find similar matches for
        max_results: Maximum number of results to return (default: 5)
    """
    if not CHROMA_INTEGRATION_AVAILABLE:
        return "ChromaDB integration not available. Install chromadb and sentence-transformers to use similarity search."
    
    try:
        # Use the new ChromaDB integration service to search for similar code
        results = chroma_integration.search_files(code_snippet, max_results=max_results)
        
        if not results:
            return "No similar code found"
        
        output = f"Found {len(results)} similar code sections:\n\n"
        
        for i, result in enumerate(results, 1):
            file_path = result.get('file_path', 'Unknown file')
            line_number = result.get('line_number', 'Unknown line')
            similarity_score = result.get('similarity_score', 0)
            content = result.get('content', '').strip()
            
            output += f"{i}. {file_path}:{line_number} (similarity: {similarity_score:.3f})\n"
            output += f"```\n{content[:300]}{'...' if len(content) > 300 else ''}\n```\n\n"
        
        return output
    except Exception as e:
        return f"Error finding similar code: {str(e)}"

@tool
def move_file(source_path: str, dest_path: str) -> str:
    """Move or rename a file from source path to destination path.

    Args:
        source_path: Current path of the file
        dest_path: New path for the file
    """
    try:
        source = resolve_path(source_path)
        dest = resolve_path(dest_path)
        
        if not source.exists():
            return f"Source file not found: {source_path}"
        
        # Create destination directory if it doesn't exist
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        source.rename(dest)
        return f"Successfully moved {source_path} to {dest_path}"
    except Exception as e:
        return f"Error moving file: {str(e)}"

@tool
def replace_line(file_path: str, line_number: int, new_content: str) -> str:
    """Replace a specific line in a file with new content.

    Args:
        file_path: Path to the file to modify
        line_number: Line number to replace (1-indexed)
        new_content: New content for the line
    """
    try:
        file_path_obj = resolve_path(file_path)
        
        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"
        
        # Read all lines
        lines = file_path_obj.read_text(encoding='utf-8').splitlines()
        
        # Check if line number is valid
        if line_number < 1 or line_number > len(lines):
            return f"Invalid line number: {line_number}. File has {len(lines)} lines."
        
        # Replace the line (convert to 0-indexed)
        old_content = lines[line_number - 1]
        lines[line_number - 1] = new_content
        
        # Write back to file
        file_path_obj.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        
        return f"Successfully replaced line {line_number} in {file_path}\nOld: {old_content}\nNew: {new_content}"
    except Exception as e:
        return f"Error replacing line: {str(e)}"

@tool
def print_directory_tree(directory: str = ".", max_depth: int = 3, show_files: bool = True) -> str:
    """Print a tree view of the directory structure.

    Args:
        directory: Directory path to print tree for (default: current directory)
        max_depth: Maximum depth to traverse (default: 3)
        show_files: Whether to show files in addition to directories (default: True)
    """
    try:
        dir_path = Path(directory)
        if not dir_path.is_absolute():
            dir_path = Path(get_project_folder()) / directory

        if not dir_path.exists():
            return f"Directory not found: {directory}"

        if not dir_path.is_dir():
            return f"Path is not a directory: {directory}"

        def build_tree(path, prefix="", depth=0):
            if depth > max_depth:
                return ""

            try:
                items = sorted(path.iterdir())
            except PermissionError:
                return f"{prefix}└── [Permission Denied]\n"

            tree_str = ""
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "

                if item.is_dir():
                    tree_str += f"{prefix}{connector}{item.name}/\n"
                    if depth < max_depth:
                        extension = "    " if is_last else "│   "
                        tree_str += build_tree(item, prefix + extension, depth + 1)
                elif show_files:
                    tree_str += f"{prefix}{connector}{item.name}\n"

            return tree_str

        tree_output = f"{dir_path.name}/\n"
        tree_output += build_tree(dir_path, "", 0)
        return tree_output

    except Exception as e:
        return f"Error printing directory tree: {str(e)}"

def get_project_structure(directory: str = ".", max_depth: int = 3, show_files: bool = True) -> str:
    """Print a tree view of the directory structure.

    Args:
        directory: Directory path to print tree for (default: current directory)
        max_depth: Maximum depth to traverse (default: 3)
        show_files: Whether to show files in addition to directories (default: True)
    """
    try:
        dir_path = Path(directory)
        if not dir_path.is_absolute():
            dir_path = Path(get_project_folder()) / directory

        if not dir_path.exists():
            return f"Directory not found: {directory}"

        if not dir_path.is_dir():
            return f"Path is not a directory: {directory}"

        def build_tree(path, prefix="", depth=0):
            if depth > max_depth:
                return ""

            try:
                items = sorted(path.iterdir())
            except PermissionError:
                return f"{prefix}└── [Permission Denied]\n"

            tree_str = ""
            for i, item in enumerate(items):
                is_last = i == len(items) - 1
                connector = "└── " if is_last else "├── "

                if item.is_dir():
                    tree_str += f"{prefix}{connector}{item.name}/\n"
                    if depth < max_depth:
                        extension = "    " if is_last else "│   "
                        tree_str += build_tree(item, prefix + extension, depth + 1)
                elif show_files:
                    tree_str += f"{prefix}{connector}{item.name}\n"

            return tree_str

        tree_output = f"{dir_path.name}/\n"
        tree_output += build_tree(dir_path)

        return tree_output

    except Exception as e:
        return f"Error printing directory tree: {str(e)}"

@tool
def generate_unit_tests(file_path: str, test_framework: str = "auto") -> str:
    """Generate basic unit tests for a code file.

    Args:
        file_path: Path to the file to generate tests for
        test_framework: Test framework to use (auto, jest, pytest, mocha)
    """
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.is_absolute():
            file_path_obj = Path(get_project_folder()) / file_path

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        ext = file_path_obj.suffix.lower()

        # Auto-detect framework
        if test_framework == "auto":
            if ext in ['.js', '.jsx', '.ts', '.tsx']:
                test_framework = "jest"
            elif ext == '.py':
                test_framework = "pytest"
            else:
                test_framework = "jest"  # default

        # Extract functions/classes to test
        functions = []
        classes = []

        if ext in ['.js', '.jsx', '.ts', '.tsx']:
            # Find function declarations
            func_matches = re.findall(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:\([^)]*\)\s*=>|function))', content)
            for match in func_matches:
                func_name = match[0] or match[1]
                if func_name and not func_name.startswith('_'):
                    functions.append(func_name)

            # Find class declarations
            class_matches = re.findall(r'class\s+(\w+)', content)
            classes.extend(class_matches)

        elif ext == '.py':
            # Find function definitions
            func_matches = re.findall(r'def\s+(\w+)', content)
            functions.extend([f for f in func_matches if not f.startswith('_')])

            # Find class definitions
            class_matches = re.findall(r'class\s+(\w+)', content)
            classes.extend(class_matches)

        # Generate test file content
        test_content = ""

        if test_framework == "jest":
            test_content = f'''const {{ {", ".join(functions[:5])} }} = require('./{file_path_obj.stem}');

describe('{file_path_obj.stem} tests', () => {{
'''

            for func in functions[:5]:
                test_content += f'''
  describe('{func}', () => {{
    test('should work correctly', () => {{
      // TODO: Implement test for {func}
      expect(true).toBe(true);
    }});
  }});'''

            for cls in classes[:3]:
                test_content += f'''

  describe('{cls}', () => {{
    let instance;

    beforeEach(() => {{
      instance = new {cls}();
    }});

    test('should create instance', () => {{
      expect(instance).toBeDefined();
    }});
  }});'''

            test_content += '''
});
'''

        elif test_framework == "pytest":
            test_content = f'''import pytest
from {file_path_obj.stem} import {", ".join(functions[:5])}

class Test{file_path_obj.stem.title()}:
'''

            for func in functions[:5]:
                test_content += f'''
    def test_{func}(self):
        """Test {func} function"""
        # TODO: Implement test for {func}
        assert True'''

            for cls in classes[:3]:
                test_content += f'''

    def test_{cls.lower()}_creation(self):
        """Test {cls} class creation"""
        instance = {cls}()
        assert instance is not None'''

        # Save test file
        test_dir = file_path_obj.parent / "tests"
        test_dir.mkdir(exist_ok=True)

        test_file_name = f"test_{file_path_obj.stem}.{'test.js' if test_framework == 'jest' else 'py'}"
        test_file_path = test_dir / test_file_name

        test_file_path.write_text(test_content)

        return f"Generated unit tests for {file_path} using {test_framework}:\n- Created: {test_file_path}\n- Functions tested: {len(functions)}\n- Classes tested: {len(classes)}"

    except Exception as e:
        return f"Error generating unit tests: {str(e)}"

@tool
def create_git_commit_message(files_changed: str) -> str:
    """Generate a meaningful git commit message based on changed files.

    Args:
        files_changed: Comma-separated list of files that were changed
    """
    try:
        if not files_changed or not files_changed.strip():
            return "Error: No files specified"

        files = [f.strip() for f in files_changed.split(',') if f.strip()]
        if not files:
            return "Error: No valid files specified"

        # Categorize changes
        categories = {
            'feat': [],
            'fix': [],
            'docs': [],
            'style': [],
            'refactor': [],
            'test': [],
            'chore': []
        }

        for file in files:
            file_lower = file.lower()

            # Feature additions
            if any(keyword in file_lower for keyword in ['component', 'page', 'feature', 'add']):
                categories['feat'].append(file)

            # Bug fixes
            elif any(keyword in file_lower for keyword in ['fix', 'bug', 'error', 'issue']):
                categories['fix'].append(file)

            # Documentation
            elif any(keyword in file_lower for keyword in ['readme', 'doc', 'md', 'txt']):
                categories['docs'].append(file)

            # Styling
            elif any(keyword in file_lower for keyword in ['css', 'scss', 'style', 'theme']):
                categories['style'].append(file)

            # Testing
            elif any(keyword in file_lower for keyword in ['test', 'spec', 'e2e']):
                categories['test'].append(file)

            # Refactoring
            elif any(keyword in file_lower for keyword in ['refactor', 'rename', 'move']):
                categories['refactor'].append(file)

            # Configuration/Maintenance
            else:
                categories['chore'].append(file)

        # Generate commit message
        primary_category = None
        primary_files = []

        # Find the category with the most files
        for cat, files_list in categories.items():
            if len(files_list) > len(primary_files):
                primary_category = cat
                primary_files = files_list

        if not primary_category:
            primary_category = 'chore'

        # Create descriptive message
        if len(primary_files) == 1:
            description = f"{primary_files[0]}"
        elif len(primary_files) <= 3:
            description = ", ".join(primary_files)
        else:
            description = f"{len(primary_files)} files"

        # Conventional commit format
        commit_message = f"{primary_category}: {description}"

        # Add scope if applicable
        if len(files) == 1:
            file_parts = files[0].split('/')
            if len(file_parts) > 1:
                scope = file_parts[0]
                commit_message = f"{primary_category}({scope}): {description}"

        return f"Generated commit message:\n{commit_message}"

    except Exception as e:
        return f"Error creating git commit message: {str(e)}"

@tool
def upload_codebase_to_chroma(
    root_directory: str = ".", 
    file_extensions: str = ".py,.js,.jsx,.ts,.tsx,.vue,.java,.cpp,.c,.h,.cs,.php,.rb,.go,.rs,.swift,.kt,.scala,.r,.m,.mm,.sh,.sql,.html,.css,.scss,.sass,.less,.json,.yaml,.yml,.xml,.md,.txt",
    chunk_size: int = 1000,
    overlap_size: int = 200,
    collection_name: str = "files"
) -> str:
    """Upload entire codebase to ChromaDB for semantic search, excluding unnecessary directories.

    Args:
        root_directory: Root directory to start indexing from (default: current directory)
        file_extensions: Comma-separated list of file extensions to include
        chunk_size: Size of each text chunk in characters (default: 1000)
        overlap_size: Overlap between chunks in characters (default: 200)
        collection_name: Name of the ChromaDB collection (default: 'files')
    """
    try:
        if not CHROMA_INTEGRATION_AVAILABLE:
            return "Error: ChromaDB integration not available. Install chromadb and sentence_transformers."

        root_path = Path(root_directory)
        if not root_path.is_absolute():
            root_path = Path(get_project_folder()) / root_directory

        if not root_path.exists():
            return f"Error: Directory not found: {root_directory}"

        # Use the new ChromaDB integration service to index the directory
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(chroma_integration.index_directory(
                str(root_path), 
                collection_name=collection_name
            ))
            
            # Get stats to report back
            stats = chroma_integration.get_collection_stats(collection_name)
            total_chunks = stats.get('total_chunks', 0)
            
            return f"""Codebase upload completed successfully using new ChromaDB integration!

📊 Upload Summary:
- Directory indexed: {root_path}
- Collection: {collection_name}
- Total chunks created: {total_chunks}

📈 Collection Stats:
- Total documents: {total_chunks}
- Collection name: {collection_name}

🔍 You can now use semantic_search_codebase to search through your code!"""
            
        finally:
            loop.close()

    except Exception as e:
        return f"Error uploading codebase: {str(e)}"


@tool
def get_tool_usage_logs(limit: int = 10) -> str:
    """Get recent tool usage logs with execution details and performance metrics.
    
    Args:
        limit: Maximum number of recent logs to return (default: 10)
    """
    try:
        logs = tool_usage_logger.get_recent_logs(limit)
        active_ops = tool_usage_logger.get_active_operations()
        
        if not logs and not active_ops:
            return "No tool usage logs available yet."
            
        result = "🔧 **Tool Usage Logs**\n\n"
        
        # Show active operations first
        if active_ops:
            result += "⚡ **Currently Active Operations:**\n"
            for op in active_ops:
                duration = int((datetime.now() - datetime.fromisoformat(op["start_time"])).total_seconds())
                result += f"- {op['tool_name']} (running for {duration}s) - {op['operation_id']}\n"
            result += "\n"
        
        # Show recent completed operations
        if logs:
            result += "📋 **Recent Tool Executions:**\n"
            for log in logs:
                status_emoji = "✅" if log.get("success", True) else "❌"
                duration = log.get("duration_ms", "N/A")
                duration_str = f"{duration}ms" if duration != "N/A" else "N/A"
                
                result += f"{status_emoji} **{log['tool_name']}** ({duration_str})\n"
                result += f"   Started: {log['start_time']}\n"
                
                # Show parameters (truncated)
                if log.get('parameters'):
                    params_str = str(log['parameters'])[:100]
                    if len(str(log['parameters'])) > 100:
                        params_str += "..."
                    result += f"   Parameters: {params_str}\n"
                
                # Show result (truncated)
                if log.get('result'):
                    result_str = str(log['result'])[:100]
                    if len(str(log['result'])) > 100:
                        result_str += "..."
                    result += f"   Result: {result_str}\n"
                
                result += "\n"
        
        return result
        
    except Exception as e:
        return f"Error retrieving tool usage logs: {str(e)}"


@tool
def get_file_changes(limit: int = 20) -> str:
    """Get recent file changes and modifications in the project.
    
    Args:
        limit: Maximum number of recent changes to return (default: 20)
    """
    try:
        changes = file_monitor.get_recent_changes(limit)
        
        if not changes:
            return "No file changes detected yet. File monitoring may not be active."
            
        result = "📁 **Recent File Changes**\n\n"
        
        # Group changes by type
        created_files = [c for c in changes if c['change_type'] == 'created']
        modified_files = [c for c in changes if c['change_type'] == 'modified']
        deleted_files = [c for c in changes if c['change_type'] == 'deleted']
        
        if created_files:
            result += "📄 **Created Files:**\n"
            for change in created_files[-10:]:  # Last 10 created
                result += f"- {change['relative_path']} ({change['timestamp']})\n"
            result += "\n"
            
        if modified_files:
            result += "📝 **Modified Files:**\n"
            for change in modified_files[-10:]:  # Last 10 modified
                result += f"- {change['relative_path']} ({change['timestamp']})\n"
            result += "\n"
            
        if deleted_files:
            result += "🗑️ **Deleted Files:**\n"
            for change in deleted_files[-5:]:  # Last 5 deleted
                result += f"- {change['relative_path']} ({change['timestamp']})\n"
            result += "\n"
        
        return result
        
    except Exception as e:
        return f"Error retrieving file changes: {str(e)}"


@tool
def start_file_monitoring(path: str = None) -> str:
    """Start real-time file monitoring for the specified directory.
    
    Args:
        path: Directory path to monitor (default: current project folder)
    """
    try:
        monitor_path = path or get_project_folder()
        
        if not os.path.exists(monitor_path):
            return f"Error: Path '{monitor_path}' does not exist."
            
        file_monitor.start_monitoring(monitor_path)
        
        return f"✅ File monitoring started for: {monitor_path}\n\nYou can now use 'get_file_changes' to see real-time file modifications."
        
    except Exception as e:
        return f"Error starting file monitoring: {str(e)}"


@tool
def stop_file_monitoring() -> str:
    """Stop real-time file monitoring."""
    try:
        file_monitor.stop_monitoring()
        return "✅ File monitoring stopped."
        
    except Exception as e:
        return f"Error stopping file monitoring: {str(e)}"


@tool
def get_development_dashboard() -> str:
    """Get a comprehensive development dashboard showing tool usage, file changes, and active operations."""
    try:
        result = "🚀 **Development Dashboard**\n\n"
        
        # Active operations
        active_ops = tool_usage_logger.get_active_operations()
        if active_ops:
            result += "⚡ **Active Operations:**\n"
            for op in active_ops:
                duration = int((datetime.now() - datetime.fromisoformat(op["start_time"])).total_seconds())
                result += f"- {op['tool_name']} (running for {duration}s)\n"
            result += "\n"
        else:
            result += "⚡ **Active Operations:** None\n\n"
        
        # Recent tool usage
        recent_tools = tool_usage_logger.get_recent_logs(5)
        if recent_tools:
            result += "🔧 **Recent Tool Usage:**\n"
            for log in recent_tools:
                status_emoji = "✅" if log.get("success", True) else "❌"
                duration = log.get("duration_ms", "N/A")
                duration_str = f"{duration}ms" if duration != "N/A" else "N/A"
                result += f"{status_emoji} {log['tool_name']} ({duration_str})\n"
            result += "\n"
        else:
            result += "🔧 **Recent Tool Usage:** None\n\n"
        
        # Recent file changes
        recent_changes = file_monitor.get_recent_changes(5)
        if recent_changes:
            result += "📁 **Recent File Changes:**\n"
            for change in recent_changes:
                emoji = {"created": "📄", "modified": "📝", "deleted": "🗑️"}.get(change['change_type'], "📄")
                result += f"{emoji} {change['relative_path']} ({change['change_type']})\n"
            result += "\n"
        else:
            result += "📁 **Recent File Changes:** None\n\n"
        
        # Monitoring status
        monitoring_status = "🟢 Active" if file_monitor.is_monitoring else "🔴 Inactive"
        result += f"📊 **File Monitoring:** {monitoring_status}\n"
        
        if file_monitor.watched_paths:
            result += f"📂 **Watched Paths:** {', '.join(file_monitor.watched_paths)}\n"
        
        return result
        
    except Exception as e:
        return f"Error generating development dashboard: {str(e)}"


# Copilot-style tools for code analysis and completion

@tool
def analyze_react_component(file_path: str) -> str:
    """Analyze a React component for structure, props, and best practices."""
    logger.info(f"⚛️ Analyzing React component: {file_path}")

    result = read_file_content(file_path)
    if not result["success"]:
        return f"Error reading file: {result['error']}"

    content = result["content"]

    # Analyze React component patterns
    analysis = {
        "is_functional": "function " in content or "const " in content and "=>" in content,
        "is_class": "class " in content and "extends React.Component" in content,
        "uses_hooks": any(hook in content for hook in ["useState", "useEffect", "useContext", "useReducer"]),
        "has_props": "props" in content or "Props" in content,
        "has_typescript": "interface" in content or ":" in content.split("//")[0],
        "imports_react": "import React" in content or "from 'react'" in content,
        "uses_jsx": "<" in content and ">" in content,
    }

    return f"""
🔍 React Component Analysis: {file_path}

📊 Component Type:
- Functional Component: {'✅' if analysis['is_functional'] else '❌'}
- Class Component: {'✅' if analysis['is_class'] else '❌'}

🪝 React Hooks Usage:
- Uses Hooks: {'✅' if analysis['uses_hooks'] else '❌'}

📝 Code Quality:
- Has Props Interface: {'✅' if analysis['has_props'] else '❌'}
- TypeScript: {'✅' if analysis['has_typescript'] else '❌'}
- Proper React Import: {'✅' if analysis['imports_react'] else '❌'}
- Uses JSX: {'✅' if analysis['uses_jsx'] else '❌'}

💡 Recommendations:
- {'Consider converting to functional component with hooks' if analysis['is_class'] else ''}
- {'Add TypeScript interfaces for props' if not analysis['has_typescript'] and analysis['has_props'] else ''}
- {'Add proper React import' if not analysis['imports_react'] else ''}
"""

@tool
def suggest_react_optimizations(file_path: str) -> str:
    """Suggest React-specific optimizations and best practices."""
    logger.info(f"⚡ Analyzing React optimizations for: {file_path}")

    result = read_file_content(file_path)
    if not result["success"]:
        return f"Error reading file: {result['error']}"

    content = result["content"]

    suggestions = []

    # Check for common React optimization opportunities
    if "useState(" in content and "useEffect(" not in content:
        suggestions.append("Consider useEffect for side effects")

    if "console.log(" in content:
        suggestions.append("Remove console.log statements for production")

    if "style={" in content and "css" not in content.lower():
        suggestions.append("Consider using CSS modules or styled-components")

    if "key={" not in content and "map(" in content:
        suggestions.append("Add key props to mapped elements")

    if len([line for line in content.split('\n') if line.strip()]) > 100:
        suggestions.append("Consider breaking down large components")

    return f"""
🚀 React Optimization Suggestions for {file_path}

{'✅ No major issues found!' if not suggestions else '💡 Suggested Improvements:'}

""" + "\n".join(f"- {suggestion}" for suggestion in suggestions)

@tool
def generate_react_component(component_name: str, component_type: str = "functional", features: str = "") -> str:
    """Generate a React component template with specified features."""
    logger.info(f"�️ Generating React component: {component_name}")

    features_list = [f.strip() for f in features.split(",") if f.strip()]

    # Base functional component template
    component_code = '''import React, { useState, useEffect } from 'react';

interface ''' + component_name + '''Props {
  // Add props here
}

const ''' + component_name + ''': React.FC<''' + component_name + '''Props> = (props) => {
  // Component state
  const [state, setState] = useState(initialState);

  // Component effects
  useEffect(() => {
    // Effect logic here
  }, []);

  return (
    <div className="''' + component_name.lower() + '''">
      <h2>''' + component_name + ''' Component</h2>
      {/* Component JSX here */}
    </div>
  );
};

export default ''' + component_name + ''';
'''

    # Add features based on request
    if "state" in features_list:
            component_code = component_code.replace("// Component state", """
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);""")

    if "api" in features_list:
            component_code = component_code.replace("// Effect logic here", """
    // Fetch data from API
    const fetchData = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/data');
        const data = await response.json();
        setData(data);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();""")

    if "styling" in features_list:
            component_code = component_code.replace("{/* Component JSX here */}", """
      <div className="component-content">
        <p>This is a styled component</p>
      </div>""")

    return f"""
🛠️ Generated React Component: {component_name}

```tsx
{component_code}
```

Features included: {', '.join(features_list) if features_list else 'Basic component'}
"""

@tool
def analyze_vue_component(file_path: str) -> str:
    """Analyze a Vue component for structure and best practices."""
    logger.info(f"� Analyzing Vue component: {file_path}")

    result = read_file_content(file_path)
    if not result["success"]:
        return f"Error reading file: {result['error']}"

    content = result["content"]

    analysis = {
        "is_sfc": "<template>" in content and "<script>" in content,
        "uses_composition_api": "setup(" in content or "ref(" in content or "<script setup" in content,
        "uses_options_api": "export default {" in content and "setup" not in content,
        "has_typescript": "lang=\"ts\"" in content or ".ts" in file_path,
        "uses_vue3": "defineComponent" in content or "<script setup" in content,
    }

    return f"""
🔍 Vue Component Analysis: {file_path}

📊 Component Type:
- Single File Component: {'✅' if analysis['is_sfc'] else '❌'}
- Composition API: {'✅' if analysis['uses_composition_api'] else '❌'}
- Options API: {'✅' if analysis['uses_options_api'] else '❌'}

🔧 Technical Details:
- Vue 3: {'✅' if analysis['uses_vue3'] else '❌'}
- TypeScript: {'✅' if analysis['has_typescript'] else '❌'}

💡 Recommendations:
- {'Consider migrating to Composition API' if analysis['uses_options_api'] else ''}
- {'Add TypeScript support for better development experience' if not analysis['has_typescript'] else ''}
"""

@tool
def suggest_frontend_improvements(file_path: str) -> str:
    """Suggest frontend-specific improvements for React/Vue components."""
    logger.info(f"🎨 Analyzing frontend improvements for: {file_path}")

    result = read_file_content(file_path)
    if not result["success"]:
        return f"Error reading file: {result['error']}"

    content = result["content"]
    suggestions = []

    # Frontend-specific checks
    if "style={" in content and len(content) > 1000:
        suggestions.append("Extract inline styles to CSS modules or styled-components")

    if "className=" in content and "module" not in content.lower():
        suggestions.append("Consider using CSS modules for scoped styling")

    if "useState" in content and "useCallback" not in content and "function" in content:
        suggestions.append("Consider useCallback for functions passed to child components")

    if "console." in content:
        suggestions.append("Remove console statements for production builds")

    if "any>" in content or "object>" in content:
        suggestions.append("Replace 'any' and 'object' types with specific interfaces")

    return f"""
🎨 Frontend Improvement Suggestions for {file_path}

{'✅ Code looks good!' if not suggestions else '💡 Suggested Improvements:'}

""" + "\n".join(f"- {suggestion}" for suggestion in suggestions)

# Tool definitions using @tool decorator

LOCAL_TOOLS = [
    read_file,
    write_file,
    list_dir,
    run_terminal_command_tool,
    search_files,
    create_directory,
    grep_search,
    replace_in_file,
    replace_block_in_file,
    move_file,
    replace_line,
    get_project_structure,
    search_code,
    validate_syntax,
    format_code,
    check_dependencies,
    analyze_dependencies,
    semantic_search_codebase,
    index_codebase_for_search,
    get_vector_store_stats,
    find_similar_code,
    print_directory_tree,
    generate_unit_tests,
    create_git_commit_message,
    upload_codebase_to_chroma,
    get_tool_usage_logs,
    get_file_changes,
    start_file_monitoring,
    stop_file_monitoring,
    get_development_dashboard,
    analyze_react_component,
    suggest_react_optimizations,
    generate_react_component,
    analyze_vue_component,
    suggest_frontend_improvements,
]

# Export individual tools for direct access
__all__ = [
    "LOCAL_TOOLS",
    "read_file",
    "write_file",
    "list_dir",
    "run_terminal_command_tool",
    "search_files",
    "create_directory",
    "grep_search",
    "replace_in_file",
    "replace_block_in_file",
    "move_file",
    "replace_line",
    "get_project_structure",
    "search_code",
    "validate_syntax",
    "format_code",
    "check_dependencies",
    "analyze_dependencies",
    "semantic_search_codebase",
    "index_codebase_for_search",
    "get_vector_store_stats",
    "find_similar_code",
    "print_directory_tree",
    "generate_unit_tests",
    "create_git_commit_message",
    "upload_codebase_to_chroma",
    "get_tool_usage_logs",
    "get_file_changes",
    "start_file_monitoring",
    "stop_file_monitoring",
    "get_development_dashboard",
    "set_session_context",
    "get_project_folder",
]