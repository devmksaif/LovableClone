"""
Symbol Indexing & Workspace Intelligence Service

This service provides fast symbol lookup across the entire workspace,
maintaining an in-memory symbol table for instant access to definitions,
references, and import suggestions.

Features:
- In-memory symbol table with O(1) lookups
- Automatic indexing of workspace files
- Real-time updates on file changes
- Import suggestion system
- Integration with code intelligence for symbol extraction

Performance Targets:
- Index 1000+ files in < 5 seconds
- Symbol lookup in < 10ms
- 95%+ accuracy for import suggestions
"""

import os
import json
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache
import threading
from concurrent.futures import ThreadPoolExecutor

from .code_intelligence import CodeIntelligenceService, Symbol

logger = logging.getLogger(__name__)


@dataclass
class IndexedSymbol:
    """Enhanced symbol information for the index."""
    name: str
    type: str  # 'function', 'class', 'variable', 'method', 'property'
    file_path: str
    line: int
    column: int
    scope: str  # 'global', 'export', 'private', etc.
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None
    is_exported: bool = False
    last_modified: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "type": self.type,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "scope": self.scope,
            "signature": self.signature,
            "docstring": self.docstring,
            "parent_symbol": self.parent_symbol,
            "is_exported": self.is_exported,
            "last_modified": self.last_modified
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IndexedSymbol':
        """Create from dictionary."""
        return cls(**data)


@dataclass
class ImportSuggestion:
    """Import suggestion for a symbol."""
    symbol_name: str
    import_statement: str
    module_path: str
    is_default_export: bool = False
    confidence: float = 1.0


class SymbolIndexService:
    """
    Fast symbol indexing service for workspace-wide intelligence.

    Maintains an in-memory symbol table for instant lookups and provides
    intelligent import suggestions for code generation.
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.code_intel = CodeIntelligenceService()

        # Core symbol index
        self._symbol_index: Dict[str, IndexedSymbol] = {}
        self._file_symbols: Dict[str, List[str]] = {}  # file_path -> [symbol_names]
        self._reverse_index: Dict[str, Set[str]] = {}  # symbol_name -> set(file_paths)

        # Import suggestion data
        self._exported_symbols: Dict[str, List[IndexedSymbol]] = {}
        self._module_exports: Dict[str, Set[str]] = {}  # module_path -> set(exported_symbols)

        # Performance tracking
        self._index_built = False
        self._last_index_time = 0.0
        self._index_size = 0

        # Threading for async operations
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.RLock()

        logger.info(f"Initialized SymbolIndexService for workspace: {workspace_root}")

    async def build_index(self) -> float:
        """
        Build the complete symbol index for the workspace.

        Returns:
            Time taken to build index in seconds
        """
        start_time = time.time()

        try:
            # Clear existing index
            with self._lock:
                self._symbol_index.clear()
                self._file_symbols.clear()
                self._reverse_index.clear()
                self._exported_symbols.clear()
                self._module_exports.clear()

            # Collect all files to index
            files_to_index = []
            supported_extensions = {'.py', '.js', '.jsx', '.ts', '.tsx', '.vue'}

            for root, dirs, files in os.walk(self.workspace_root):
                # Skip common directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
                    'node_modules', '__pycache__', '.git', 'dist', 'build'
                }]

                for file in files:
                    if Path(file).suffix.lower() in supported_extensions:
                        files_to_index.append(os.path.join(root, file))

            logger.info(f"Found {len(files_to_index)} files to index")

            # Index files in parallel
            semaphore = asyncio.Semaphore(10)  # Limit concurrent file processing

            async def index_file(file_path: str):
                async with semaphore:
                    try:
                        await self._index_single_file(file_path)
                    except Exception as e:
                        logger.warning(f"Failed to index {file_path}: {e}")

            # Process files in batches to avoid overwhelming the system
            batch_size = 50
            for i in range(0, len(files_to_index), batch_size):
                batch = files_to_index[i:i + batch_size]
                await asyncio.gather(*[index_file(fp) for fp in batch])

            # Update metadata
            with self._lock:
                self._index_built = True
                self._last_index_time = time.time()
                self._index_size = len(self._symbol_index)

            build_time = time.time() - start_time
            logger.info(f"Built symbol index in {build_time:.2f}s")
            return build_time

        except Exception as e:
            logger.error(f"Failed to build index: {e}")
            return time.time() - start_time

    async def _index_single_file(self, file_path: str):
        """Index symbols from a single file."""
        try:
            # Get symbols from code intelligence service
            symbols = await asyncio.get_event_loop().run_in_executor(
                None, self.code_intel.get_symbols, file_path
            )

            indexed_symbols = []
            exported_symbols = []

            for symbol in symbols:
                indexed_symbol = IndexedSymbol(
                    name=symbol.name,
                    type=symbol.kind,
                    file_path=file_path,
                    line=symbol.location.line,
                    column=symbol.location.column,
                    scope=symbol.scope or 'global',
                    signature=getattr(symbol, 'type_info', None),
                    docstring=symbol.docstring,
                    parent_symbol=symbol.parent_symbol,
                    is_exported=self._is_symbol_exported(symbol, file_path)
                )

                indexed_symbols.append(indexed_symbol)

                if indexed_symbol.is_exported:
                    exported_symbols.append(indexed_symbol)

            # Update index atomically
            with self._lock:
                # Add to main symbol index
                for sym in indexed_symbols:
                    self._symbol_index[sym.name] = sym

                # Update file symbols mapping
                self._file_symbols[file_path] = [s.name for s in indexed_symbols]

                # Update reverse index
                for sym in indexed_symbols:
                    if sym.name not in self._reverse_index:
                        self._reverse_index[sym.name] = set()
                    self._reverse_index[sym.name].add(file_path)

                # Update exported symbols
                rel_path = os.path.relpath(file_path, self.workspace_root)
                module_path = self._get_module_path(rel_path)

                if exported_symbols:
                    self._exported_symbols[module_path] = exported_symbols
                    self._module_exports[module_path] = {s.name for s in exported_symbols}

        except Exception as e:
            logger.warning(f"Error indexing file {file_path}: {e}")

    def _is_symbol_exported(self, symbol: Symbol, file_path: str) -> bool:
        """Determine if a symbol is exported from its file."""
        # Simple heuristics for export detection
        if symbol.scope == 'export':
            return True

        # Check if it's a class or function at module level
        if symbol.kind in ['class', 'function'] and (symbol.scope == 'global' or symbol.parent_symbol is None):
            # For Python: check if it doesn't start with underscore
            if file_path.endswith('.py') and not symbol.name.startswith('_'):
                return True
            # For TypeScript/JavaScript: assume exported unless marked private
            if file_path.endswith(('.ts', '.tsx', '.js', '.jsx')):
                return True

        return False

    def _get_module_path(self, rel_path: str) -> str:
        """Convert file path to module path."""
        path = Path(rel_path)
        if path.suffix in ['.py']:
            # Remove .py extension for Python modules
            return str(path.with_suffix(''))
        elif path.suffix in ['.ts', '.tsx', '.js', '.jsx']:
            # Remove extension for JS/TS modules
            return str(path.with_suffix(''))
        return rel_path

    async def find_symbol(self, symbol_name: str) -> Optional[IndexedSymbol]:
        """
        Find a symbol by name.

        Returns the most relevant symbol definition.
        """
        with self._lock:
            if symbol_name in self._symbol_index:
                return self._symbol_index[symbol_name]
            return None

    async def get_symbols_in_file(self, file_path: str) -> List[IndexedSymbol]:
        """
        Get all symbols defined in a specific file.
        """
        with self._lock:
            symbol_names = self._file_symbols.get(file_path, [])
            return [self._symbol_index[name] for name in symbol_names if name in self._symbol_index]

    async def search_symbols(self, query: str, limit: int = 10) -> List[IndexedSymbol]:
        """
        Search for symbols matching a query string.

        Supports fuzzy matching and partial matches.
        """
        query_lower = query.lower()
        matches = []

        with self._lock:
            for name, symbol in self._symbol_index.items():
                if query_lower in name.lower():
                    matches.append(symbol)

        # Sort by relevance (exact matches first, then prefix matches)
        matches.sort(key=lambda s: (
            s.name.lower().startswith(query_lower),  # Exact prefix match
            len(s.name),  # Shorter names first
            s.name.lower()  # Alphabetical
        ), reverse=True)

        return matches[:limit]

    async def get_import_suggestions(self, file_path: str, used_symbols: List[str]) -> List[ImportSuggestion]:
        """
        Suggest import statements for symbols used in a file.

        Args:
            file_path: The file that needs imports
            used_symbols: List of symbol names being used

        Returns:
            List of import suggestions with confidence scores
        """
        suggestions = []
        file_dir = Path(file_path).parent

        with self._lock:
            for symbol_name in used_symbols:
                if symbol_name not in self._symbol_index:
                    continue

                symbol = self._symbol_index[symbol_name]
                if not symbol.is_exported:
                    continue

                # Calculate relative import path
                symbol_dir = Path(symbol.file_path).parent
                rel_path = os.path.relpath(symbol.file_path, file_dir)

                # Convert to import path
                if rel_path.endswith('.py'):
                    import_path = rel_path[:-3].replace(os.sep, '.')
                elif rel_path.endswith(('.ts', '.tsx', '.js', '.jsx')):
                    import_path = rel_path.rsplit('.', 1)[0].replace(os.sep, '/')
                else:
                    continue

                # Handle relative imports
                if not import_path.startswith('.'):
                    import_path = f"./{import_path}"

                # Create import statement
                if symbol.type == 'default':
                    import_stmt = f"import {symbol_name} from '{import_path}'"
                else:
                    import_stmt = f"import {{ {symbol_name} }} from '{import_path}'"

                suggestions.append(ImportSuggestion(
                    symbol_name=symbol_name,
                    import_statement=import_stmt,
                    module_path=import_path,
                    confidence=0.95  # High confidence for indexed symbols
                ))

        return suggestions

    async def update_file(self, file_path: str):
        """
        Update the index for a modified file.
        """
        # Remove old symbols from this file
        with self._lock:
            if file_path in self._file_symbols:
                old_symbols = self._file_symbols[file_path]
                for sym_name in old_symbols:
                    if sym_name in self._reverse_index:
                        self._reverse_index[sym_name].discard(file_path)
                        if not self._reverse_index[sym_name]:
                            del self._reverse_index[sym_name]

                del self._file_symbols[file_path]

        # Re-index the file
        await self._index_single_file(file_path)

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        with self._lock:
            return {
                "total_symbols": len(self._symbol_index),
                "indexed_files": len(self._file_symbols),
                "exported_symbols": sum(len(symbols) for symbols in self._exported_symbols.values()),
                "index_built": self._index_built,
                "last_index_time": self._last_index_time,
                "index_size_mb": self._index_size * 0.001  # Rough estimate
            }

    def clear_index(self):
        """Clear the entire index."""
        with self._lock:
            self._symbol_index.clear()
            self._file_symbols.clear()
            self._reverse_index.clear()
            self._exported_symbols.clear()
            self._module_exports.clear()
            self._index_built = False


# Global service instance
_symbol_index_service = None

def get_symbol_index_service(workspace_root: str = None) -> SymbolIndexService:
    """Get or create the global symbol index service."""
    global _symbol_index_service

    if workspace_root is None:
        # Try to infer from current working directory
        workspace_root = os.getcwd()

    if _symbol_index_service is None or str(_symbol_index_service.workspace_root) != workspace_root:
        _symbol_index_service = SymbolIndexService(workspace_root)

    return _symbol_index_service


# Tool integrations for agents
try:
    from langchain_core.tools import tool
except ImportError:
    tool = lambda func: func  # Fallback if langchain not available


@tool
def find_symbol_definition(symbol_name: str) -> str:
    """
    Find the definition of a symbol across the entire workspace.

    Args:
        symbol_name: Name of the symbol to find

    Returns:
        JSON string with symbol definition details
    """
    try:
        service = get_symbol_index_service()

        async def _find():
            symbol = await service.find_symbol(symbol_name)
            if symbol:
                return json.dumps(symbol.to_dict(), indent=2)
            else:
                return f"Symbol '{symbol_name}' not found in workspace"

        # Run in event loop if needed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _find())
                    return future.result()
            else:
                return loop.run_until_complete(_find())
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(_find())

    except Exception as e:
        return f"Error finding symbol definition: {str(e)}"


@tool
def suggest_imports(file_path: str, used_symbols: List[str]) -> str:
    """
    Suggest import statements for symbols used in a file.

    Args:
        file_path: Path to the file that needs imports
        used_symbols: List of symbol names being used in the file

    Returns:
        JSON string with import suggestions
    """
    try:
        service = get_symbol_index_service()

        async def _suggest():
            suggestions = await service.get_import_suggestions(file_path, used_symbols)

            result = {
                "file_path": file_path,
                "suggestions": [
                    {
                        "symbol": s.symbol_name,
                        "import_statement": s.import_statement,
                        "module_path": s.module_path,
                        "confidence": s.confidence
                    } for s in suggestions
                ]
            }

            return json.dumps(result, indent=2)

        # Run in event loop if needed
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _suggest())
                    return future.result()
            else:
                return loop.run_until_complete(_suggest())
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(_suggest())

    except Exception as e:
        return f"Error suggesting imports: {str(e)}"


# Export the tools
SYMBOL_INDEX_TOOLS = [find_symbol_definition, suggest_imports]