#!/usr/bin/env python3
"""
MCP Server for development tools using FastMCP.
This server provides essential development tools that can be used by LangChain agents.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import glob
import re
import subprocess
import json
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from mcp.server.fastmcp import FastMCP

# Import centralized ChromaDB configuration
try:
    from app.config.chroma_config import get_chroma_path
    CHROMA_CONFIG_AVAILABLE = True
except ImportError:
    CHROMA_CONFIG_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ChromaDB Vector Store for semantic search
class ChromaVectorStore:
    def __init__(self, persist_directory: str = "./chroma_db"):
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
vector_store = ChromaVectorStore()

# Create MCP server instance
mcp = FastMCP("DevelopmentTools")

def get_project_root() -> Path:
    """Get the project root directory. Can be overridden by MCP_PROJECT_PATH environment variable."""
    # Check if a specific project path is set via environment variable
    env_project_path = os.environ.get('MCP_PROJECT_PATH')
    if env_project_path:
        project_root = Path(env_project_path).resolve()
        logger.info(f"Using MCP_PROJECT_PATH: {project_root}")
        return project_root
    
    # Default to NextLovable root directory
    current_file = Path(__file__).resolve()
    # Navigate up to the fastapi-mcp-agent directory, then up to NextLovable
    project_root = current_file.parent.parent.parent.parent.parent
    logger.info(f"Using default project root: {project_root}")
    return project_root

def resolve_path(path: str) -> Path:
    """Resolve a path relative to the project root with security checks."""
    project_root = get_project_root()
    file_path = (project_root / path.lstrip('/')).resolve()

    # Security check - prevent accessing files outside project
    if not str(file_path).startswith(str(project_root)):
        raise ValueError(f"Access denied: Cannot access files outside project directory. Path: {path}")

    return file_path

@mcp.tool()
def read_file(path: str) -> str:
    """Read the contents of a file. Use this to examine source code, configuration files, or any text content.

    Args:
        path: Relative path to the file from project root
    """
    try:
        file_path = resolve_path(path)

        if not file_path.exists() or not file_path.is_file():
            return f"File not found: {path}"

        # Check file size (limit to 1MB)
        if file_path.stat().st_size > 1024 * 1024:
            return f"File too large to read ({file_path.stat().st_size} bytes). Maximum size is 1MB."

        content = file_path.read_text(encoding='utf-8', errors='replace')
        return f"File: {path}\n\n{content}"
    except Exception as e:
        return f"Error reading file: {str(e)}"

@mcp.tool()
def list_dir(path: str = ".") -> str:
    """List the contents of a directory. Use this to explore project structure and find files.

    Args:
        path: Relative path to the directory from project root (default: current directory)
    """
    try:
        dir_path = resolve_path(path)

        if not dir_path.exists() or not dir_path.is_dir():
            return f"Directory not found: {path}"

        items = []
        for item in sorted(dir_path.iterdir()):
            item_type = "[DIR]" if item.is_dir() else "[FILE]"
            size = f"({item.stat().st_size} bytes)" if item.is_file() else ""
            items.append(f"{item_type} {item.name} {size}")

        result = f"Directory: {path}\n\nContents:\n"
        result += "\n".join(items) if items else "Directory is empty"
        return result
    except Exception as e:
        return f"Error listing directory {path}: {str(e)}"

@mcp.tool()
def grep_search(query: str, include_pattern: str = "*") -> str:
    """Search for text patterns in files using regex. Use this to find specific code or text across the project.

    Args:
        query: The regex pattern to search for
        include_pattern: Glob pattern for files to search in (default: all files)
    """
    try:
        project_root = get_project_root()
        results = []

        # Find files matching the pattern
        pattern = str(project_root / "**" / include_pattern)
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
                            rel_path = file_path.relative_to(project_root)
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
            return f"No matches found for '{query}' in files matching '{include_pattern}'"
    except Exception as e:
        return f"Error searching for '{query}': {str(e)}"

@mcp.tool()
def run_terminal_command(command: str) -> str:
    """Run a terminal command in the project directory. Use this for building, testing, or running scripts.

    Args:
        command: The terminal command to execute
    """
    try:
        project_root = get_project_root()

        # Run command in project root directory
        result = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        output += f"\nExit code: {result.returncode}"

        return output
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error running command: {str(e)}"

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates the file if it doesn't exist.

    Args:
        path: Relative path to the file from project root
        content: The content to write to the file
    """
    try:
        file_path = resolve_path(path)

        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        file_path.write_text(content, encoding='utf-8')
        return f"Successfully wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"Error writing to file: {str(e)}"

@mcp.tool()
def create_directory(path: str) -> str:
    """Create a new directory. Creates parent directories as needed.

    Args:
        path: Relative path to the directory from project root
    """
    try:
        dir_path = resolve_path(path)

        if dir_path.exists():
            return f"Directory already exists: {path}"

        dir_path.mkdir(parents=True, exist_ok=True)
        return f"Successfully created directory: {path}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"

@mcp.tool()
def replace_in_file(path: str, old_string: str, new_string: str) -> str:
    """Replace text in a file. Use this to make targeted edits to existing files.

    Args:
        path: Relative path to the file from project root
        old_string: The text to replace (must be unique in the file)
        new_string: The replacement text
    """
    try:
        file_path = resolve_path(path)

        if not file_path.exists() or not file_path.is_file():
            return f"File not found: {path}"

        content = file_path.read_text(encoding='utf-8')

        if old_string not in content:
            return f"Old string not found in file: {old_string}"

        # Count occurrences
        count = content.count(old_string)
        if count > 1:
            return f"Old string appears {count} times. Please make it more specific."

        new_content = content.replace(old_string, new_string, 1)
        file_path.write_text(new_content, encoding='utf-8')

        return f"Successfully replaced text in {path}"
    except Exception as e:
        return f"Error replacing text in file: {str(e)}"

@mcp.tool()
def get_project_structure(max_depth: int = 3) -> str:
    """Get the overall project structure as a tree. Use this to understand the codebase layout.

    Args:
        max_depth: Maximum depth to traverse (default: 3)
    """
    try:
        project_root = get_project_root()

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

@mcp.tool()
def search_files(pattern: str, path: str = ".") -> str:
    """Search for files matching a pattern using glob syntax. Use this to find specific files in the project.

    Args:
        pattern: Glob pattern to search for (e.g., "*.py", "**/*.js")
        path: Directory to search in (default: current directory)
    """
    try:
        search_path = resolve_path(path)
        
        if not search_path.exists() or not search_path.is_dir():
            return f"Directory not found: {path}"

        # Use glob to find matching files
        full_pattern = str(search_path / pattern)
        files = glob.glob(full_pattern, recursive=True)
        
        if not files:
            return f"No files found matching pattern '{pattern}' in {path}"
        
        # Convert to relative paths and sort
        project_root = get_project_root()
        relative_files = []
        for file_path in sorted(files):
            try:
                rel_path = Path(file_path).relative_to(project_root)
                file_size = Path(file_path).stat().st_size if Path(file_path).is_file() else 0
                file_type = "[FILE]" if Path(file_path).is_file() else "[DIR]"
                relative_files.append(f"{file_type} {rel_path} ({file_size} bytes)")
            except ValueError:
                # Skip files outside project root
                continue
        
        result = f"Found {len(relative_files)} files matching '{pattern}' in {path}:\n\n"
        result += "\n".join(relative_files[:50])  # Limit to 50 results
        
        if len(relative_files) > 50:
            result += f"\n\n... and {len(relative_files) - 50} more files"
        
        return result
    except Exception as e:
        return f"Error searching for files: {str(e)}"

@mcp.tool()
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

@mcp.tool()
def replace_in_file_regex(file_path: str, search_text: str, replace_text: str) -> str:
    """Find and replace text in a file using regex patterns.

    Args:
        file_path: Path to the file to modify
        search_text: Regex pattern to search for
        replace_text: Text to replace matches with
    """
    try:
        file_path_obj = resolve_path(file_path)
        
        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"
        
        # Read file content
        content = file_path_obj.read_text(encoding='utf-8')
        
        # Perform regex replacement
        new_content = re.sub(search_text, replace_text, content)
        
        # Check if any changes were made
        if content == new_content:
            return f"No matches found for pattern '{search_text}' in {file_path}"
        
        # Write back to file
        file_path_obj.write_text(new_content, encoding='utf-8')
        
        # Count replacements
        matches = len(re.findall(search_text, content))
        return f"Successfully replaced {matches} occurrences of '{search_text}' in {file_path}"
    except Exception as e:
        return f"Error replacing text in file: {str(e)}"

@mcp.tool()
def insert_at_line(file_path: str, line_number: int, content: str) -> str:
    """Insert text at a specific line number in a file.

    Args:
        file_path: Path to the file to modify
        line_number: Line number to insert at (1-based)
        content: Text content to insert
    """
    try:
        file_path_obj = resolve_path(file_path)
        
        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"
        
        # Read file lines
        lines = file_path_obj.read_text(encoding='utf-8').splitlines()
        
        # Validate line number
        if line_number < 1 or line_number > len(lines) + 1:
            return f"Invalid line number {line_number}. File has {len(lines)} lines."
        
        # Insert content at specified line (convert to 0-based index)
        lines.insert(line_number - 1, content)
        
        # Write back to file
        new_content = '\n'.join(lines)
        file_path_obj.write_text(new_content, encoding='utf-8')
        
        return f"Successfully inserted content at line {line_number} in {file_path}"
    except Exception as e:
        return f"Error inserting content: {str(e)}"

@mcp.tool()
def delete_lines(file_path: str, start_line: int, end_line: int) -> str:
    """Delete a range of lines from a file.

    Args:
        file_path: Path to the file to modify
        start_line: First line to delete (1-based, inclusive)
        end_line: Last line to delete (1-based, inclusive)
    """
    try:
        file_path_obj = resolve_path(file_path)
        
        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"
        
        # Read file lines
        lines = file_path_obj.read_text(encoding='utf-8').splitlines()
        
        # Validate line numbers
        if start_line < 1 or end_line < 1 or start_line > len(lines) or end_line > len(lines):
            return f"Invalid line range {start_line}-{end_line}. File has {len(lines)} lines."
        
        if start_line > end_line:
            return f"Start line {start_line} cannot be greater than end line {end_line}"
        
        # Delete lines (convert to 0-based indices)
        del lines[start_line - 1:end_line]
        
        # Write back to file
        new_content = '\n'.join(lines)
        file_path_obj.write_text(new_content, encoding='utf-8')
        
        deleted_count = end_line - start_line + 1
        return f"Successfully deleted {deleted_count} lines ({start_line}-{end_line}) from {file_path}"
    except Exception as e:
        return f"Error deleting lines: {str(e)}"

@mcp.tool()
def read_lines(file_path: str, start_line: int = 1, end_line: int = None) -> str:
    """Read specific lines from a file by line numbers.

    Args:
        file_path: Path to the file to read
        start_line: First line to read (1-based, default: 1)
        end_line: Last line to read (1-based, default: end of file)
    """
    try:
        file_path_obj = resolve_path(file_path)
        
        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"
        
        # Read file lines
        lines = file_path_obj.read_text(encoding='utf-8').splitlines()
        
        # Set default end_line if not provided
        if end_line is None:
            end_line = len(lines)
        
        # Validate line numbers
        if start_line < 1 or end_line < 1 or start_line > len(lines):
            return f"Invalid line range. File has {len(lines)} lines."
        
        if start_line > end_line:
            return f"Start line {start_line} cannot be greater than end line {end_line}"
        
        # Extract requested lines (convert to 0-based indices)
        selected_lines = lines[start_line - 1:end_line]
        
        # Format output with line numbers
        result = f"Lines {start_line}-{min(end_line, len(lines))} from {file_path}:\n\n"
        for i, line in enumerate(selected_lines, start=start_line):
            result += f"{i:4d}: {line}\n"
        
        return result
    except Exception as e:
        return f"Error reading lines: {str(e)}"

@mcp.tool()
def search_code(query: str, file_extensions: str = "*.ts,*.js,*.py,*.tsx,*.jsx", max_results: int = 20) -> str:
    """Search for code patterns across the project using advanced search.

    Args:
        query: Search query (supports regex)
        file_extensions: Comma-separated list of file extensions to search (default: common code files)
        max_results: Maximum number of results to return (default: 20)
    """
    try:
        project_root = get_project_root()
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

@mcp.tool()
def create_sandbox(name: str, type: str = "react") -> str:
    """Create a new development sandbox environment for testing code.

    Args:
        name: Name of the sandbox
        type: Type of sandbox (react, node, python, etc.)
    """
    try:
        project_root = get_project_root()
        sandbox_path = project_root / "sandboxes" / name
        
        if sandbox_path.exists():
            return f"Sandbox '{name}' already exists at {sandbox_path}"
        
        # Create sandbox directory
        sandbox_path.mkdir(parents=True, exist_ok=True)
        
        # Create basic structure based on type
        if type.lower() == "react":
            # Create basic React structure
            (sandbox_path / "src").mkdir(exist_ok=True)
            (sandbox_path / "public").mkdir(exist_ok=True)
            
            # Create package.json
            package_json = {
                "name": name,
                "version": "1.0.0",
                "private": True,
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0"
                },
                "scripts": {
                    "start": "react-scripts start",
                    "build": "react-scripts build",
                    "test": "react-scripts test"
                }
            }
            (sandbox_path / "package.json").write_text(json.dumps(package_json, indent=2))
            
            # Create basic App.js
            app_js = '''import React from 'react';

function App() {
  return (
    <div className="App">
      <h1>Welcome to {name} Sandbox</h1>
      <p>Start building your React application here!</p>
    </div>
  );
}

export default App;
'''.format(name=name)
            (sandbox_path / "src" / "App.js").write_text(app_js)
            
        elif type.lower() == "node":
            # Create basic Node.js structure
            package_json = {
                "name": name,
                "version": "1.0.0",
                "main": "index.js",
                "scripts": {
                    "start": "node index.js",
                    "dev": "nodemon index.js"
                }
            }
            (sandbox_path / "package.json").write_text(json.dumps(package_json, indent=2))
            
            # Create basic index.js
            index_js = f'''console.log('Welcome to {name} sandbox!');

// Start building your Node.js application here
'''
            (sandbox_path / "index.js").write_text(index_js)
            
        elif type.lower() == "python":
            # Create basic Python structure
            (sandbox_path / "src").mkdir(exist_ok=True)
            
            # Create requirements.txt
            (sandbox_path / "requirements.txt").write_text("# Add your Python dependencies here\n")
            
            # Create main.py
            main_py = f'''#!/usr/bin/env python3
"""
{name} Sandbox
Start building your Python application here!
"""

def main():
    print(f"Welcome to {name} sandbox!")

if __name__ == "__main__":
    main()
'''
            (sandbox_path / "src" / "main.py").write_text(main_py)
        
        # Create README
        readme = f'''# {name} Sandbox

This is a {type} development sandbox created for testing and experimentation.

## Getting Started

1. Navigate to the sandbox directory: `cd sandboxes/{name}`
2. Install dependencies (if applicable)
3. Start developing!

## Structure

- This sandbox contains a basic {type} project structure
- Modify files as needed for your development and testing

Created: {Path(__file__).stat().st_mtime}
'''
        (sandbox_path / "README.md").write_text(readme)
        
        return f"Successfully created {type} sandbox '{name}' at {sandbox_path}"
    except Exception as e:
        return f"Error creating sandbox: {str(e)}"

 
@mcp.tool()
def validate_syntax(file_path: str, language: str = "auto") -> str:
    """Validate syntax of a code file. Supports multiple languages.

    Args:
        file_path: Path to the file to validate
        language: Programming language (auto, python, javascript, typescript, json, yaml, xml)
    """
    try:
        file_path_obj = resolve_path(file_path)

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

@mcp.tool()
def format_code(file_path: str, language: str = "auto") -> str:
    """Format code using appropriate formatter for the language.

    Args:
        file_path: Path to the file to format
        language: Programming language (auto, python, javascript, typescript, json, css, html)
    """
    try:
        file_path_obj = resolve_path(file_path)

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
            elif ext == ".html":
                language = "html"
            else:
                return f"Cannot auto-detect language for extension: {ext}"

        content = file_path_obj.read_text(encoding='utf-8')
        formatted_content = content

        if language == "python":
            try:
                import black
                formatted_content = black.format_str(content, mode=black.FileMode())
            except ImportError:
                # Fallback to basic formatting
                import autopep8
                formatted_content = autopep8.fix_code(content)

        elif language in ["javascript", "typescript"]:
            try:
                import prettier
                formatted_content = prettier.format(content, parser="babel" if language == "javascript" else "typescript")
            except ImportError:
                # Basic formatting fallback
                formatted_content = content

        elif language == "json":
            try:
                import json
                parsed = json.loads(content)
                formatted_content = json.dumps(parsed, indent=2)
            except:
                pass

        elif language == "css":
            try:
                import cssbeautifier
                formatted_content = cssbeautifier.beautify(content)
            except ImportError:
                pass

        elif language == "html":
            try:
                import bs4
                soup = bs4.BeautifulSoup(content, 'html.parser')
                formatted_content = soup.prettify()
            except ImportError:
                pass

        if formatted_content != content:
            file_path_obj.write_text(formatted_content, encoding='utf-8')
            return f"Successfully formatted {file_path}"
        else:
            return f"No formatting changes needed for {file_path}"

    except Exception as e:
        return f"Error formatting code: {str(e)}"

@mcp.tool()
def analyze_imports(file_path: str) -> str:
    """Analyze imports and dependencies in a code file.

    Args:
        file_path: Path to the file to analyze
    """
    try:
        file_path_obj = resolve_path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        ext = file_path_obj.suffix.lower()

        imports = []
        dependencies = []

        if ext == ".py":
            # Python imports
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('import ') or line.startswith('from '):
                    imports.append(line)

                    # Extract package names
                    if line.startswith('import '):
                        parts = line[7:].split(',')
                        for part in parts:
                            pkg = part.strip().split('.')[0]
                            if pkg and pkg not in ['os', 'sys', 'json', 're', 'datetime', 'typing']:
                                dependencies.append(pkg)
                    elif line.startswith('from '):
                        pkg = line[5:].split(' import ')[0].strip()
                        if pkg and pkg not in ['os', 'sys', 'json', 're', 'datetime', 'typing']:
                            dependencies.append(pkg)

        elif ext in [".js", ".ts", ".tsx", ".jsx"]:
            # JavaScript/TypeScript imports
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('import ') or line.startswith('require('):
                    imports.append(line)

                    # Extract package names
                    if line.startswith('import '):
                        # Handle various import patterns
                        if ' from ' in line:
                            pkg_part = line.split(' from ')[1].strip()
                            if pkg_part.startswith('"') or pkg_part.startswith("'"):
                                pkg = pkg_part.strip('"\'').split('/')[0]
                                if pkg and not pkg.startswith('.'):
                                    dependencies.append(pkg)
                    elif line.startswith('const ') and 'require(' in line:
                        match = re.search(r"require\(['\"]([^'\"]+)", line)
                        if match:
                            pkg = match.group(1).split('/')[0]
                            if pkg and not pkg.startswith('.'):
                                dependencies.append(pkg)

        result = f"Import Analysis for {file_path}:\n\n"
        result += f"Imports Found: {len(imports)}\n"
        if imports:
            result += "Import Statements:\n" + "\n".join(f"  {imp}" for imp in imports[:20])
            if len(imports) > 20:
                result += f"\n  ... and {len(imports) - 20} more"

        result += f"\n\nExternal Dependencies: {len(set(dependencies))}\n"
        if dependencies:
            unique_deps = sorted(set(dependencies))
            result += "Packages: " + ", ".join(unique_deps[:10])
            if len(unique_deps) > 10:
                result += f", ... and {len(unique_deps) - 10} more"

        return result

    except Exception as e:
        return f"Error analyzing imports: {str(e)}"

@mcp.tool()
def generate_tests(file_path: str, test_type: str = "unit") -> str:
    """Generate basic test structure for a code file.

    Args:
        file_path: Path to the file to generate tests for
        test_type: Type of tests to generate (unit, integration, e2e)
    """
    try:
        file_path_obj = resolve_path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        ext = file_path_obj.suffix.lower()
        file_name = file_path_obj.stem

        test_content = ""

        if ext == ".py":
            # Generate Python tests
            test_file = f"test_{file_name}.py"
            test_content = f'''"""
Unit tests for {file_name}.py
Generated automatically - customize as needed
"""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module to test
# from {file_name} import *

class Test{file_name.title()}(unittest.TestCase):
    """Test cases for {file_name} module."""

    def setUp(self):
        """Set up test fixtures."""
        pass

    def tearDown(self):
        """Clean up test fixtures."""
        pass

    def test_example(self):
        """Example test case - replace with actual tests."""
        self.assertTrue(True)

    # Add more test methods here based on the functions/classes in {file_name}.py

if __name__ == '__main__':
    unittest.main()
'''

        elif ext in [".js", ".ts"]:
            # Generate JavaScript/TypeScript tests
            test_file = f"{file_name}.test.{ext}"
            test_content = f'''/**
 * Unit tests for {file_name}.{ext}
 * Generated automatically - customize as needed
 */

const {{ expect, describe, it, beforeEach, afterEach }} = require('@jest/globals');

// Import the module to test
// const {{ {file_name} }} = require('./{file_name}');

describe('{file_name}', () => {{
  beforeEach(() => {{
    // Set up test fixtures
  }});

  afterEach(() => {{
    // Clean up test fixtures
  }});

  it('should work correctly', () => {{
    // Example test - replace with actual tests
    expect(true).toBe(true);
  }});

  // Add more test cases here based on the functions/classes in {file_name}.{ext}
}});
'''

        if test_content:
            # Create test file in appropriate location
            test_path = file_path_obj.parent / test_file
            test_path.write_text(test_content, encoding='utf-8')
            return f"Generated test file: {test_path}"
        else:
            return f"Test generation not supported for {ext} files"

    except Exception as e:
        return f"Error generating tests: {str(e)}"

@mcp.tool()
def check_dependencies(package_file: str = "auto") -> str:
    """Check and analyze project dependencies.

    Args:
        package_file: Package file to analyze (auto, package.json, requirements.txt, pyproject.toml)
    """
    try:
        project_root = get_project_root()

        if package_file == "auto":
            # Auto-detect package file
            if (project_root / "package.json").exists():
                package_file = "package.json"
            elif (project_root / "requirements.txt").exists():
                package_file = "requirements.txt"
            elif (project_root / "pyproject.toml").exists():
                package_file = "pyproject.toml"
            else:
                return "No package file found (package.json, requirements.txt, or pyproject.toml)"

        file_path = project_root / package_file
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
            try:
                import tomllib
                data = tomllib.loads(content)
            except ImportError:
                try:
                    import tomli
                    data = tomli.loads(content)
                except ImportError:
                    return "tomli/tomllib required for TOML parsing"

            result = f"Dependencies Analysis for {package_file}:\n\n"

            # Check different possible dependency sections
            dep_sections = ['dependencies', 'optional-dependencies', 'dev-dependencies']
            for section in dep_sections:
                if 'project' in data and section in data['project']:
                    deps = data['project'][section]
                    result += f"{section.title()}: {len(deps)}\n"
                    if deps:
                        for dep in deps[:10]:
                            result += f"  {dep}\n"
                        if len(deps) > 10:
                            result += f"  ... and {len(deps) - 10} more\n"
                    result += "\n"

            return result

        return f"Unsupported package file type: {package_file}"

    except Exception as e:
        return f"Error analyzing dependencies: {str(e)}"

@mcp.tool()
def run_linter(file_path: str = ".", language: str = "auto") -> str:
    """Run linter on code files to check for issues.

    Args:
        file_path: Path to file or directory to lint
        language: Programming language (auto, python, javascript, typescript)
    """
    try:
        project_root = get_project_root()
        target_path = resolve_path(file_path)

        if language == "auto":
            if target_path.is_file():
                ext = target_path.suffix.lower()
                if ext == ".py":
                    language = "python"
                elif ext in [".js", ".mjs"]:
                    language = "javascript"
                elif ext in [".ts", ".tsx"]:
                    language = "typescript"
            else:
                # For directories, check common files
                if (project_root / "requirements.txt").exists() or any(f.suffix == ".py" for f in target_path.rglob("*") if f.is_file()):
                    language = "python"
                elif (project_root / "package.json").exists():
                    language = "javascript"

        result = f"Linting {file_path} ({language}):\n\n"

        if language == "python":
            try:
                import pylint.lint
                from pylint.reporters.text import TextReporter
                from io import StringIO

                output = StringIO()
                reporter = TextReporter(output)
                pylint.lint.Run([str(target_path)], reporter=reporter, exit=False)
                result += output.getvalue()

            except ImportError:
                # Fallback to basic checks
                result += "Pylint not available. Running basic syntax check...\n"
                if target_path.is_file():
                    content = target_path.read_text(encoding='utf-8')
                    try:
                        compile(content, str(target_path), 'exec')
                        result += "✓ Syntax check passed\n"
                    except SyntaxError as e:
                        result += f"✗ Syntax error: {e}\n"

        elif language in ["javascript", "typescript"]:
            try:
                import eslint
                # This would require eslint to be installed and configured
                result += "ESLint integration would go here\n"
            except ImportError:
                result += "ESLint not available. Consider installing eslint for JavaScript/TypeScript linting.\n"

        else:
            result += f"Linting not implemented for language: {language}\n"

        return result

    except Exception as e:
        return f"Error running linter: {str(e)}"

@mcp.tool()
def git_status() -> str:
    """Get the current git status of the project."""
    try:
        project_root = get_project_root()

        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            status_output = result.stdout.strip()
            if status_output:
                return f"Git Status:\n{status_output}"
            else:
                return "Git repository is clean - no changes to commit"
        else:
            return f"Git status failed: {result.stderr}"

    except FileNotFoundError:
        return "Git is not installed or not available"
    except subprocess.TimeoutExpired:
        return "Git status timed out"
    except Exception as e:
        return f"Error getting git status: {str(e)}"

@mcp.tool()
def git_commit(message: str, files: str = ".") -> str:
    """Commit changes to git with a message.

    Args:
        message: Commit message
        files: Files to commit (default: all changes)
    """
    try:
        project_root = get_project_root()

        # Add files
        add_result = subprocess.run(
            ["git", "add", files],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        if add_result.returncode != 0:
            return f"Failed to add files: {add_result.stderr}"

        # Commit
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )

        if commit_result.returncode == 0:
            return f"Successfully committed changes:\n{commit_result.stdout}"
        else:
            return f"Commit failed: {commit_result.stderr}"

    except Exception as e:
        return f"Error committing changes: {str(e)}"

@mcp.tool()
def install_dependencies(package_manager: str = "auto") -> str:
    """Install project dependencies using the appropriate package manager.

    Args:
        package_manager: Package manager to use (auto, npm, yarn, pnpm, pip, poetry)
    """
    try:
        project_root = get_project_root()

        if package_manager == "auto":
            # Auto-detect package manager
            if (project_root / "pnpm-lock.yaml").exists():
                package_manager = "pnpm"
            elif (project_root / "yarn.lock").exists():
                package_manager = "yarn"
            elif (project_root / "package.json").exists():
                package_manager = "npm"
            elif (project_root / "requirements.txt").exists() or (project_root / "pyproject.toml").exists():
                package_manager = "pip"
            else:
                return "Could not auto-detect package manager. No package files found."

        if package_manager == "pnpm":
            cmd = ["pnpm", "install"]
        elif package_manager == "yarn":
            cmd = ["yarn", "install"]
        elif package_manager == "npm":
            cmd = ["npm", "install"]
        elif package_manager == "pip":
            if (project_root / "requirements.txt").exists():
                cmd = ["pip", "install", "-r", "requirements.txt"]
            elif (project_root / "pyproject.toml").exists():
                cmd = ["pip", "install", "."]
            else:
                return "No Python dependency file found (requirements.txt or pyproject.toml)"
        else:
            return f"Unsupported package manager: {package_manager}"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"

        output += f"\nExit code: {result.returncode}"

        return f"Package installation result:\n{output}"

    except subprocess.TimeoutExpired:
        return "Package installation timed out after 5 minutes"
    except Exception as e:
        return f"Error installing dependencies: {str(e)}"

@mcp.tool()
def create_project_template(template_type: str, project_name: str) -> str:
    """Create a new project from a template.

    Args:
        template_type: Type of project template (react, vue)
        project_name: Name for the new project
    """
    try:
        project_root = get_project_root()
        project_path = project_root / "sandboxes" / project_name

        if project_path.exists():
            return f"Project '{project_name}' already exists"

        project_path.mkdir(parents=True, exist_ok=True)

        if template_type.lower() == "react":
            # Create React project structure
            src_dir = project_path / "src"
            src_dir.mkdir(exist_ok=True)

            # package.json
            package_json = {
                "name": project_name,
                "version": "0.1.0",
                "private": True,
                "dependencies": {
                    "react": "^18.2.0",
                    "react-dom": "^18.2.0",
                    "react-scripts": "5.0.1"
                },
                "scripts": {
                    "start": "react-scripts start",
                    "build": "react-scripts build",
                    "test": "react-scripts test",
                    "eject": "react-scripts eject"
                }
            }
            (project_path / "package.json").write_text(json.dumps(package_json, indent=2))

            # App.js
            app_js = f'''import React from 'react';
import './App.css';

function App() {{
  return (
    <div className="App">
      <header className="App-header">
        <h1>Welcome to {project_name}</h1>
        <p>React application created with MCP tools</p>
      </header>
    </div>
  );
}}

export default App;
'''
            (src_dir / "App.js").write_text(app_js)

            # App.css
            app_css = '''.App {{
  text-align: center;
}}

.App-header {{
  background-color: #282c34;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: calc(10px + 2vmin);
  color: white;
}}
'''
            (src_dir / "App.css").write_text(app_css)

            # index.js
            index_js = '''import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
'''
            (src_dir / "index.js").write_text(index_js)

            # index.css and index.html
            (src_dir / "index.css").write_text('body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }')
            (project_path / "index.html").write_text(f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" /><title>{project_name}</title></head><body><div id="root"></div></body></html>')

        elif template_type.lower() == "vue":
            # Create Vue project structure
            src_dir = project_path / "src"
            src_dir.mkdir(exist_ok=True)

            # package.json
            package_json = {
                "name": project_name,
                "version": "0.1.0",
                "private": True,
                "scripts": {
                    "serve": "vue-cli-service serve",
                    "build": "vue-cli-service build",
                    "lint": "vue-cli-service lint"
                },
                "dependencies": {
                    "vue": "^3.3.0"
                },
                "devDependencies": {
                    "@vue/cli-service": "^5.0.8",
                    "@vue/compiler-sfc": "^3.3.0"
                }
            }
            (project_path / "package.json").write_text(json.dumps(package_json, indent=2))

            # main.js
            main_js = '''import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
'''
            (src_dir / "main.js").write_text(main_js)

            # App.vue
            app_vue = f'''<template>
  <div id="app">
    <header>
      <h1>Welcome to {project_name}</h1>
      <p>Vue application created with MCP tools</p>
    </header>
  </div>
</template>

<script>
export default {{
  name: 'App'
}}
</script>

<style>
#app {{
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}}

header {{
  background-color: #42b883;
  padding: 20px;
  color: white;
}}
</style>
'''
            (src_dir / "App.vue").write_text(app_vue)

            # index.html
            (project_path / "index.html").write_text(f'''<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>{project_name}</title>
  </head>
  <body>
    <noscript>
      <strong>We're sorry but {project_name} doesn't work properly without JavaScript enabled. Please enable it to continue.</strong>
    </noscript>
    <div id="app"></div>
    <!-- built files will be auto injected -->
  </body>
</html>''')

        else:
            return f"Template type '{template_type}' not supported. Available: react, vue"

        return f"Successfully created {template_type} project '{project_name}' at {project_path}"

    except Exception as e:
        return f"Error creating project template: {str(e)}"

@mcp.tool()
def print_tree(directory: str = ".", max_depth: int = 3, show_files: bool = True) -> str:
    """Print a tree view of the directory structure.

    Args:
        directory: Directory path to print tree for (default: current directory)
        max_depth: Maximum depth to traverse (default: 3)
        show_files: Whether to show files in addition to directories (default: True)
    """
    try:
        dir_path = resolve_path(directory)

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

@mcp.tool()
def validate_vue_syntax(file_path: str) -> str:
    """Validate Vue.js file syntax and structure.

    Args:
        file_path: Path to the Vue file to validate
    """
    try:
        file_path_obj = resolve_path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')

        if not file_path_obj.suffix.lower() in ['.vue', '.js', '.ts']:
            return f"Not a Vue-related file: {file_path}"

        issues = []

        # Basic Vue syntax validation
        if file_path_obj.suffix.lower() == '.vue':
            # Check for basic Vue structure
            if '<template>' not in content:
                issues.append("Missing <template> tag")
            if '<script>' not in content:
                issues.append("Missing <script> tag")

            # Check template syntax
            import re
            # Check for unclosed tags
            open_tags = re.findall(r'<([a-zA-Z][a-zA-Z0-9]*)(?:\s[^>]*)?>', content)
            close_tags = re.findall(r'</([a-zA-Z][a-zA-Z0-9]*)>', content)

            # Simple check for mismatched tags
            if len(open_tags) != len(close_tags):
                issues.append(f"Potential unclosed tags: {len(open_tags)} open, {len(close_tags)} close")

        # Check JavaScript/TypeScript syntax
        if '<script' in content or file_path_obj.suffix.lower() in ['.js', '.ts']:
            script_content = content
            if '<script' in content:
                script_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
                if script_match:
                    script_content = script_match.group(1)

            # Basic JavaScript syntax checks
            if '{' in script_content and '}' not in script_content:
                issues.append("Unclosed braces in script")
            if '(' in script_content and ')' not in script_content:
                issues.append("Unclosed parentheses in script")

        if issues:
            return f"Vue syntax validation issues in {file_path}:\n" + "\n".join(f"  - {issue}" for issue in issues)
        else:
            return f"Vue syntax validation passed for {file_path}"

    except Exception as e:
        return f"Error validating Vue syntax: {str(e)}"

@mcp.tool()
def validate_react_syntax(file_path: str) -> str:
    """Validate React.js file syntax and structure.

    Args:
        file_path: Path to the React file to validate
    """
    try:
        file_path_obj = resolve_path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        ext = file_path_obj.suffix.lower()

        if ext not in ['.jsx', '.tsx', '.js', '.ts']:
            return f"Not a React-related file: {file_path}"

        issues = []

        # Check for React imports
        has_react_import = any(imp in content for imp in ['import React', 'from "react"', "from 'react'"])
        has_jsx = '<' in content and '>' in content

        if has_jsx and not has_react_import and ext in ['.jsx', '.tsx']:
            issues.append("JSX detected but no React import found")

        # Check for unclosed JSX tags
        import re
        jsx_tags = re.findall(r'<[^>]+>', content)
        open_jsx = [tag for tag in jsx_tags if not tag.startswith('</') and not tag.endswith('/>')]
        close_jsx = [tag for tag in jsx_tags if tag.startswith('</')]
        self_closing = [tag for tag in jsx_tags if tag.endswith('/>')]

        # Basic JSX structure check
        if len(open_jsx) > len(close_jsx) + len(self_closing):
            issues.append("Potential unclosed JSX tags")

        # Check for common React patterns
        if 'useState' in content and not has_react_import:
            issues.append("useState used but React not imported")

        if 'useEffect' in content and not has_react_import:
            issues.append("useEffect used but React not imported")

        # Check for proper component structure
        if ext in ['.jsx', '.tsx']:
            # Look for export default or function component
            has_export = 'export default' in content or 'export function' in content or 'export const' in content
            if not has_export and len(content.strip()) > 50:  # Only warn for substantial files
                issues.append("No default export found - may not be a valid React component")

        if issues:
            return f"React syntax validation issues in {file_path}:\n" + "\n".join(f"  - {issue}" for issue in issues)
        else:
            return f"React syntax validation passed for {file_path}"

    except Exception as e:
        return f"Error validating React syntax: {str(e)}"

@mcp.tool()
def validate_terminal_command(command: str) -> str:
    """Validate terminal command syntax and safety.

    Args:
        command: Terminal command to validate
    """
    try:
        if not command or not command.strip():
            return "Error: Empty command"

        cmd = command.strip()

        # Dangerous commands to flag
        dangerous_commands = [
            'rm -rf /', 'rm -rf /*', 'rm -rf ~', 'rm -rf /home',
            'dd if=', 'mkfs', 'fdisk', 'format',
            'sudo rm', 'sudo dd', 'sudo mkfs',
            'chmod 777', 'chown root',
            'curl | bash', 'wget | bash', 'sh -c',
            'eval', 'exec', 'source'
        ]

        # Check for dangerous patterns
        warnings = []
        for dangerous in dangerous_commands:
            if dangerous in cmd.lower():
                warnings.append(f"Dangerous command pattern detected: {dangerous}")

        # Check for proper command structure
        if cmd.startswith('|') or cmd.startswith('&') or cmd.startswith(';'):
            warnings.append("Command starts with pipe, background, or semicolon operator")

        if cmd.endswith('|') or cmd.endswith('&') or cmd.endswith(';'):
            warnings.append("Command ends with pipe, background, or semicolon operator")

        # Check for unclosed quotes
        single_quotes = cmd.count("'")
        double_quotes = cmd.count('"')
        backticks = cmd.count('`')

        if single_quotes % 2 != 0:
            warnings.append("Unclosed single quotes")
        if double_quotes % 2 != 0:
            warnings.append("Unclosed double quotes")
        if backticks % 2 != 0:
            warnings.append("Unclosed backticks")

        # Check for common syntax issues
        if '&&' in cmd and not cmd.split('&&')[0].strip():
            warnings.append("Empty command before &&")
        if '&&' in cmd and not cmd.split('&&')[-1].strip():
            warnings.append("Empty command after &&")

        if '||' in cmd and not cmd.split('||')[0].strip():
            warnings.append("Empty command before ||")
        if '||' in cmd and not cmd.split('||')[-1].strip():
            warnings.append("Empty command after ||")

        # Basic command validation
        parts = cmd.split()
        if not parts:
            return "Error: No command specified"

        base_cmd = parts[0]

        # Check if command exists (basic check)
        common_commands = [
            'ls', 'cd', 'pwd', 'mkdir', 'rmdir', 'cp', 'mv', 'rm', 'touch', 'cat', 'grep', 'find',
            'ps', 'kill', 'top', 'htop', 'df', 'du', 'free', 'uptime',
            'npm', 'yarn', 'pnpm', 'node', 'python', 'python3', 'pip', 'pip3',
            'git', 'docker', 'docker-compose', 'kubectl',
            'curl', 'wget', 'ssh', 'scp', 'rsync',
            'tar', 'gzip', 'zip', 'unzip',
            'chmod', 'chown', 'chgrp', 'sudo', 'su',
            'systemctl', 'service', 'journalctl',
            'vim', 'nano', 'emacs', 'code'
        ]

        if base_cmd not in common_commands and not any(cmd.startswith(prefix) for prefix in ['./', '/', '~']):
            warnings.append(f"Unrecognized command: {base_cmd} (may not be installed)")

        if warnings:
            return f"Terminal command validation warnings for: {cmd}\n" + "\n".join(f"  - {warning}" for warning in warnings)
        else:
            return f"Terminal command validation passed: {cmd}"

    except Exception as e:
        return f"Error validating terminal command: {str(e)}"

@mcp.tool()
def run_code_quality_check(file_path: str) -> str:
    """Run comprehensive code quality checks on a file.

    Args:
        file_path: Path to the file to check
    """
    try:
        file_path_obj = resolve_path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        ext = file_path_obj.suffix.lower()

        issues = []

        # General code quality checks
        lines = content.split('\n')
        total_lines = len(lines)

        # Check line length
        long_lines = [i+1 for i, line in enumerate(lines) if len(line) > 100]
        if long_lines:
            issues.append(f"Lines too long (>100 chars): {long_lines[:5]}")

        # Check for TODO/FIXME comments
        todo_lines = [i+1 for i, line in enumerate(lines) if 'TODO' in line.upper() or 'FIXME' in line.upper()]
        if todo_lines:
            issues.append(f"TODO/FIXME comments found on lines: {todo_lines}")

        # Check for console.log statements (common in JS/TS)
        if ext in ['.js', '.ts', '.jsx', '.tsx']:
            console_logs = [i+1 for i, line in enumerate(lines) if 'console.log' in line]
            if console_logs:
                issues.append(f"console.log statements found on lines: {console_logs[:5]}")

        # Check for empty catch blocks
        if ext in ['.js', '.ts', '.jsx', '.tsx', '.py']:
            empty_catches = []
            for i, line in enumerate(lines):
                if ('catch' in line and '{' in line) or ('except' in line and ':' in line):
                    # Check next few lines for empty block
                    for j in range(1, min(5, len(lines) - i)):
                        next_line = lines[i + j].strip()
                        if next_line == '}' or next_line == 'pass' or next_line == '':
                            continue
                        elif next_line.startswith('//') or next_line.startswith('#'):
                            continue
                        else:
                            break
                    else:
                        empty_catches.append(i+1)
            if empty_catches:
                issues.append(f"Empty catch/except blocks on lines: {empty_catches}")

        # Language-specific checks
        if ext in ['.py']:
            # Python-specific checks
            if not content.strip().startswith('"""') and len(content.strip()) > 50:
                issues.append("Missing module docstring")

            # Check for unused imports (basic)
            import_lines = [line.strip() for line in lines if line.strip().startswith('import ') or 'from ' in line and ' import ' in line]
            if len(import_lines) > 10:
                issues.append("Many imports detected - consider organizing imports")

        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            # JavaScript/TypeScript specific checks
            if 'var ' in content:
                var_lines = [i+1 for i, line in enumerate(lines) if 'var ' in line]
                issues.append(f"'var' declarations found (prefer 'const'/'let'): lines {var_lines[:3]}")

            # Check for missing semicolons (basic)
            js_lines = [line for line in lines if not line.strip().startswith('//') and not line.strip().startswith('*') and line.strip()]
            missing_semicolons = []
            for i, line in enumerate(js_lines):
                stripped = line.strip()
                if (stripped and not stripped.startswith('//') and not stripped.startswith('*') and
                    not stripped.startswith('import ') and not stripped.startsWith('export ') and
                    not stripped.endswith(';') and not stripped.endswith(',') and
                    not stripped.endswith('{') and not stripped.endswith('}') and
                    not stripped.endswith(':') and not stripped.startswith('if ') and
                    not stripped.startswith('for ') and not stripped.startswith('while ') and
                    not stripped.startswith('function ') and not stripped.endswith('return')):
                    if any(keyword in stripped for keyword in ['=', 'console.log', 'alert', 'setTimeout', 'setInterval']):
                        missing_semicolons.append(i+1)
            if missing_semicolons:
                issues.append(f"Potential missing semicolons on lines: {missing_semicolons[:5]}")

        # Complexity metrics
        if total_lines > 500:
            issues.append(f"File is very long ({total_lines} lines) - consider splitting")

        # Check for duplicate code (basic)
        line_counts = {}
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) > 10:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

        duplicates = [line for line, count in line_counts.items() if count > 2]
        if duplicates:
            issues.append(f"Duplicate lines detected: {len(duplicates)} lines appear multiple times")

        if issues:
            return f"Code quality issues in {file_path}:\n" + "\n".join(f"  - {issue}" for issue in issues)
        else:
            return f"Code quality check passed for {file_path} ({total_lines} lines)"

    except Exception as e:
        return f"Error running code quality check: {str(e)}"

@mcp.tool()
def generate_unit_tests(file_path: str, test_framework: str = "auto") -> str:
    """Generate basic unit tests for a code file.

    Args:
        file_path: Path to the file to generate tests for
        test_framework: Test framework to use (auto, jest, pytest, mocha)
    """
    try:
        file_path_obj = resolve_path(file_path)

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
            import re
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
            import re
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

@mcp.tool()
def analyze_dependencies(file_path: str) -> str:
    """Analyze project dependencies and suggest improvements.

    Args:
        file_path: Path to package.json, requirements.txt, or project file
    """
    try:
        file_path_obj = resolve_path(file_path)

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

@mcp.tool()
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
        return f"Error generating commit message: {str(e)}"

@mcp.tool()
def optimize_code(file_path: str) -> str:
    """Optimize code for performance and readability.

    Args:
        file_path: Path to the file to optimize
    """
    try:
        file_path_obj = resolve_path(file_path)

        if not file_path_obj.exists() or not file_path_obj.is_file():
            return f"File not found: {file_path}"

        content = file_path_obj.read_text(encoding='utf-8')
        ext = file_path_obj.suffix.lower()

        optimizations = []

        if ext in ['.js', '.jsx', '.ts', '.tsx']:
            # JavaScript/TypeScript optimizations
            lines = content.split('\n')

            # Check for inefficient patterns
            if 'for (let i = 0; i < arr.length; i++)' in content:
                optimizations.append("Consider using for...of or Array.forEach for better readability")

            if 'arr.push.apply(arr,' in content:
                optimizations.append("Consider using spread operator: arr.push(...items)")

            if 'function(' in content and '=> {' in content:
                optimizations.append("Mix of function declarations and arrow functions detected")

            # Check for unused variables (basic)
            var_declarations = []
            for line in lines:
                if 'const ' in line or 'let ' in line or 'var ' in line:
                    var_declarations.append(line.strip())

            if len(var_declarations) > 20:
                optimizations.append("Many variable declarations - consider breaking into smaller functions")

        elif ext == '.py':
            # Python optimizations
            lines = content.split('\n')

            if any('import *' in line for line in lines):
                optimizations.append("Avoid 'import *' - import specific functions instead")

            if any('print(' in line for line in lines if not line.strip().startswith('#')):
                optimizations.append("Debug print statements found - remove for production")

            # Check for list comprehensions vs loops
            if '[x for x in' in content and 'for ' in content and 'append(' in content:
                optimizations.append("Consider using list comprehensions instead of loops with append")

        # General optimizations
        if len(content) > 10000:
            optimizations.append("Large file detected - consider splitting into smaller modules")

        # Check for code duplication (basic)
        lines = content.split('\n')
        line_counts = {}
        for line in lines:
            stripped = line.strip()
            if len(stripped) > 20 and not stripped.startswith('//') and not stripped.startswith('#'):
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

        duplicates = [line for line, count in line_counts.items() if count > 1]
        if duplicates:
            optimizations.append(f"Code duplication detected: {len(duplicates)} lines repeated")

        if optimizations:
            return f"Code optimization suggestions for {file_path}:\n" + "\n".join(f"  - {opt}" for opt in optimizations)
        else:
            return f"No optimization opportunities found in {file_path}"

    except Exception as e:
        return f"Error optimizing code: {str(e)}"

# Initialize ChromaDB vector store
vector_store = ChromaVectorStore()

@mcp.tool()
def semantic_search(query: str) -> str:
    """Search for relevant code or documentation comments from the user's current workspace using semantic similarity."""
    if not query:
        raise ValueError("Query is required for semantic search")
    
    results = vector_store.semantic_search(query, n_results=5)
    if not results:
        return f"No results found for query: '{query}'"
    
    formatted_results = f"Search results for '{query}':\n\n"
    for i, doc in enumerate(results, 1):
        content_preview = doc['content'][:300] + "..." if len(doc['content']) > 300 else doc['content']
        formatted_results += f"{i}. {content_preview}\n\n"
    
    return formatted_results

@mcp.tool()
def add_code_to_vector_store(content: str, metadata: Optional[Dict[str, Any]] = None, collection_name: str = "codebase") -> str:
    """Add code snippets or documentation to the vector store for semantic search."""
    if not content:
        raise ValueError("Content is required")
    
    vector_store.add_documents([content], [metadata or {}], collection_name)
    return f"Added content to vector store collection '{collection_name}'"

@mcp.tool()
def get_vector_store_stats() -> str:
    """Get statistics about the vector store collections."""
    stats = vector_store.get_stats()
    return f"Vector store statistics:\n{stats}"