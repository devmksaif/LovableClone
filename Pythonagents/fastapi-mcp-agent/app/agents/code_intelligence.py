"""
AST-Based Code Analysis Engine for Deep Code Understanding

This module provides intelligent code analysis capabilities similar to VSCode IntelliSense,
using tree-sitter for multi-language AST parsing and symbol extraction.

Features:
- Multi-language support (Python, JavaScript, TypeScript, JSX, TSX, Vue)
- Symbol extraction (functions, classes, variables, imports)
- Cross-file reference finding
- Type information analysis
- Dependency graph generation
- High-performance caching

Required packages:
- tree-sitter>=0.20.1
- tree-sitter-python
- tree-sitter-javascript
- tree-sitter-typescript
"""

import os
import json
import logging
import hashlib
from tokenize import Name
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

# Tree-sitter imports
try:
    import tree_sitter
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    tree_sitter = None
    Language = None
    Parser = None

# Language-specific parsers
try:
    import tree_sitter_python
    PYTHON_PARSER_AVAILABLE = True
except ImportError:
    PYTHON_PARSER_AVAILABLE = False

try:
    import tree_sitter_javascript
    JAVASCRIPT_PARSER_AVAILABLE = True
except ImportError:
    JAVASCRIPT_PARSER_AVAILABLE = False

try:
    import tree_sitter_typescript
    TYPESCRIPT_PARSER_AVAILABLE = True
except ImportError:
    TYPESCRIPT_PARSER_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class Location:
    """Represents a location in a file."""
    file_path: str
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None

@dataclass
class Symbol:
    """Represents a code symbol (function, class, variable, etc.)."""
    name: str
    kind: str  # 'function', 'class', 'variable', 'method', 'property', etc.
    location: Location
    type_info: Optional[str] = None
    docstring: Optional[str] = None
    scope: Optional[str] = None  # 'global', 'class', 'function', etc.
    parent_symbol: Optional[str] = None
    children: List[str] = field(default_factory=list)

@dataclass
class TypeInfo:
    """Type information for a symbol."""
    symbol_name: str
    type_annotation: Optional[str] = None
    inferred_type: Optional[str] = None
    base_types: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)

@dataclass
class DependencyInfo:
    """Dependency information for a file."""
    file_path: str
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

class CodeIntelligenceService:
    """AST-based code analysis service using tree-sitter."""

    def __init__(self):
        if not TREE_SITTER_AVAILABLE:
            raise ImportError("tree-sitter is required for CodeIntelligenceService")

        self.parsers = {}
        self.languages = {}
        self._setup_parsers()

        # Caching
        self._ast_cache: Dict[str, Any] = {}
        self._symbol_cache: Dict[str, List[Symbol]] = {}
        self._file_hashes: Dict[str, str] = {}

        # Project-wide symbol index
        self._global_symbols: Dict[str, List[Symbol]] = {}
        self._symbol_references: Dict[str, List[Location]] = {}

    def _setup_parsers(self):
        """Initialize tree-sitter parsers for supported languages."""
        if PYTHON_PARSER_AVAILABLE:
            try:
                self.languages['python'] = Language(tree_sitter_python.language())
                self.parsers['python'] = Parser(self.languages['python'])
                logger.info("Python parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Python parser: {e}")

        if JAVASCRIPT_PARSER_AVAILABLE:
            try:
                self.languages['javascript'] = Language(tree_sitter_javascript.language())
                self.parsers['javascript'] = Parser(self.languages['javascript'])
                logger.info("JavaScript parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize JavaScript parser: {e}")

        if TYPESCRIPT_PARSER_AVAILABLE:
            try:
                # TypeScript parser handles both .ts and .tsx
                self.languages['typescript'] = Language(tree_sitter_typescript.language_typescript())
                self.parsers['typescript'] = Parser(self.languages['typescript'])
                logger.info("TypeScript parser initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize TypeScript parser: {e}")

    def _get_language_for_file(self, file_path: str) -> Optional[str]:
        """Determine the language for a file based on its extension."""
        ext = Path(file_path).suffix.lower()

        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.vue': 'javascript',  # Vue files use JavaScript/TypeScript
        }

        return language_map.get(ext)

    def _get_file_hash(self, file_path: str) -> str:
        """Get MD5 hash of file contents for cache validation."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def _is_cache_valid(self, file_path: str) -> bool:
        """Check if cached data is still valid."""
        current_hash = self._get_file_hash(file_path)
        cached_hash = self._file_hashes.get(file_path)
        return current_hash == cached_hash

    def parse_file(self, file_path: str) -> Optional[Any]:
        """
        Parse a file and return its AST structure.

        Args:
            file_path: Path to the file to parse

        Returns:
            Tree-sitter tree object or None if parsing failed
        """
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            return None

        # Check cache
        if self._is_cache_valid(file_path) and file_path in self._ast_cache:
            return self._ast_cache[file_path]

        language = self._get_language_for_file(file_path)
        if not language or language not in self.parsers:
            logger.warning(f"No parser available for file: {file_path} (language: {language})")
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()

            parser = self.parsers[language]
            tree = parser.parse(bytes(source_code, 'utf-8'))

            # Cache the result
            self._ast_cache[file_path] = tree
            self._file_hashes[file_path] = self._get_file_hash(file_path)

            return tree

        except Exception as e:
            logger.error(f"Failed to parse file {file_path}: {e}")
            return None

    def get_symbols(self, file_path: str) -> List[Symbol]:
        """
        Extract all symbols from a file.

        Args:
            file_path: Path to the file to analyze

        Returns:
            List of Symbol objects
        """
        # Check cache
        if self._is_cache_valid(file_path) and file_path in self._symbol_cache:
            return self._symbol_cache[file_path]

        tree = self.parse_file(file_path)
        if not tree:
            return []

        symbols = []
        self._extract_symbols_from_tree(tree, file_path, symbols)

        # Cache the result
        self._symbol_cache[file_path] = symbols

        # Update global symbol index
        self._update_global_symbols(file_path, symbols)

        return symbols

    def _extract_symbols_from_tree(self, tree, file_path: str, symbols: List[Symbol], parent: Optional[str] = None):
        """Recursively extract symbols from AST tree."""
        def traverse_node(node, current_scope=None):
            if node.type == 'function_definition' or node.type == 'function_declaration':
                symbol = self._extract_function_symbol(node, file_path, current_scope, parent)
                if symbol:
                    symbols.append(symbol)
                    # Recurse into function body
                    for child in node.children:
                        if child.type == 'block':
                            traverse_node(child, symbol.name)

            elif node.type == 'class_definition' or node.type == 'class_declaration':
                symbol = self._extract_class_symbol(node, file_path, current_scope, parent)
                if symbol:
                    symbols.append(symbol)
                    # Recurse into class body
                    for child in node.children:
                        if child.type in ['block', 'class_body']:
                            traverse_node(child, symbol.name)

            elif node.type == 'variable_declaration' or node.type == 'lexical_declaration':
                var_symbols = self._extract_variable_symbols(node, file_path, current_scope, parent)
                symbols.extend(var_symbols)

            elif node.type == 'import_statement' or node.type == 'import_from_statement':
                import_symbols = self._extract_import_symbols(node, file_path, current_scope, parent)
                symbols.extend(import_symbols)

            # Recurse into children
            for child in node.children:
                traverse_node(child, current_scope)

        traverse_node(tree.root_node)

    def _extract_function_symbol(self, node, file_path: str, scope: Optional[str], parent: Optional[str]) -> Optional[Symbol]:
        """Extract function symbol from AST node."""
        try:
            # Get function name
            name_node = None
            for child in node.children:
                if child.type == 'identifier' or child.type == 'property_identifier':
                    name_node = child
                    break

            if not name_node:
                return None

            name = name_node.text.decode('utf-8') if isinstance(name_node.text, bytes) else str(name_node.text)

            # Get location
            location = Location(
                file_path=file_path,
                line=name_node.start_point[0] + 1,
                column=name_node.start_point[1],
                end_line=name_node.end_point[0] + 1,
                end_column=name_node.end_point[1]
            )

            # Get parameters (simplified)
            params = []
            for child in node.children:
                if child.type == 'parameters' or child.type == 'formal_parameters':
                    params = [p.text.decode('utf-8') if isinstance(p.text, bytes) else str(p.text) for p in child.children if p.type == 'identifier']

            type_info = f"({', '.join(params)})" if params else "()"

            return Symbol(
                name=name,
                kind='function',
                location=location,
                type_info=type_info,
                scope=scope or 'global',
                parent_symbol=parent
            )

        except Exception as e:
            logger.warning(f"Failed to extract function symbol: {e}")
            return None

    def _extract_class_symbol(self, node, file_path: str, scope: Optional[str], parent: Optional[str]) -> Optional[Symbol]:
        """Extract class symbol from AST node."""
        try:
            # Get class name
            name_node = None
            for child in node.children:
                if child.type == 'identifier':
                    name_node = child
                    break

            if not name_node:
                return None

            name = name_node.text.decode('utf-8') if isinstance(name_node.text, bytes) else str(name_node.text)

            location = Location(
                file_path=file_path,
                line=name_node.start_point[0] + 1,
                column=name_node.start_point[1],
                end_line=name_node.end_point[0] + 1,
                end_column=name_node.end_point[1]
            )

            return Symbol(
                name=name,
                kind='class',
                location=location,
                scope=scope or 'global',
                parent_symbol=parent
            )

        except Exception as e:
            logger.warning(f"Failed to extract class symbol: {e}")
            return None

    def _extract_variable_symbols(self, node, file_path: str, scope: Optional[str], parent: Optional[str]) -> List[Symbol]:
        """Extract variable symbols from AST node."""
        symbols = []
        try:
            for child in node.children:
                if child.type == 'variable_declarator':
                    name_node = None
                    for grandchild in child.children:
                        if grandchild.type == 'identifier':
                            name_node = grandchild
                            break

                    if name_node:
                        name = name_node.text.decode('utf-8') if isinstance(name_node.text, bytes) else str(name_node.text)

                        location = Location(
                            file_path=file_path,
                            line=name_node.start_point[0] + 1,
                            column=name_node.start_point[1]
                        )

                        symbols.append(Symbol(
                            name=name,
                            kind='variable',
                            location=location,
                            scope=scope or 'global',
                            parent_symbol=parent
                        ))

        except Exception as e:
            logger.warning(f"Failed to extract variable symbols: {e}")

        return symbols

    def _extract_import_symbols(self, node, file_path: str, scope: Optional[str], parent: Optional[str]) -> List[Symbol]:
        """Extract import symbols from AST node."""
        symbols = []
        try:
            # This is a simplified implementation
            # In practice, you'd need more sophisticated parsing for different import types
            for child in node.children:
                if child.type == 'identifier':
                    name = child.text.decode('utf-8') if isinstance(child.text, bytes) else str(child.text)

                    location = Location(
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                        column=child.start_point[1]
                    )

                    symbols.append(Symbol(
                        name=name,
                        kind='import',
                        location=location,
                        scope=scope or 'global',
                        parent_symbol=parent
                    ))

        except Exception as e:
            logger.warning(f"Failed to extract import symbols: {e}")

        return symbols

    def find_references(self, symbol_name: str, file_path: Optional[str] = None) -> List[Location]:
        """
        Find all references to a symbol.

        Args:
            symbol_name: Name of the symbol to find
            file_path: Optional file to search in (searches all if None)

        Returns:
            List of Location objects where the symbol is referenced
        """
        references = []

        # If file_path specified, search only that file
        if file_path:
            tree = self.parse_file(file_path)
            if tree:
                self._find_symbol_references_in_tree(tree, file_path, symbol_name, references)
        else:
            # Search all indexed files
            for indexed_file in self._global_symbols.keys():
                tree = self.parse_file(indexed_file)
                if tree:
                    self._find_symbol_references_in_tree(tree, indexed_file, symbol_name, references)

        return references

    def _find_symbol_references_in_tree(self, tree, file_path: str, symbol_name: str, references: List[Location]):
        """Find references to a symbol in an AST tree."""
        def traverse_node(node):
            if node.type == 'identifier':
                name = node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
                if name == symbol_name:
                    references.append(Location(
                        file_path=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                        end_line=node.end_point[0] + 1,
                        end_column=node.end_point[1]
                    ))

            for child in node.children:
                traverse_node(child)

        traverse_node(tree.root_node)

    def get_type_info(self, symbol: Symbol) -> Optional[TypeInfo]:
        """
        Get type information for a symbol.

        Args:
            symbol: Symbol to analyze

        Returns:
            TypeInfo object or None
        """
        # This is a simplified implementation
        # In practice, you'd need language-specific type analysis
        tree = self.parse_file(symbol.location.file_path)
        if not tree:
            return None

        # For now, return basic type info
        return TypeInfo(
            symbol_name=symbol.name,
            type_annotation=symbol.type_info,
            inferred_type=self._infer_type_from_context(tree, symbol)
        )

    def _infer_type_from_context(self, tree, symbol: Symbol) -> Optional[str]:
        """Infer type from AST context (simplified)."""
        # This would need sophisticated type inference logic
        # For now, return None
        return None

    def analyze_dependencies(self, file_path: str) -> DependencyInfo:
        """
        Analyze dependencies for a file.

        Args:
            file_path: Path to the file to analyze

        Returns:
            DependencyInfo object
        """
        tree = self.parse_file(file_path)
        if not tree:
            return DependencyInfo(file_path=file_path)

        imports = []
        exports = []

        def traverse_node(node):
            if node.type in ['import_statement', 'import_from_statement']:
                # Extract import information
                import_text = node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
                imports.append(import_text.strip())

            elif node.type == 'export_statement':
                # Extract export information
                export_text = node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
                exports.append(export_text.strip())

            for child in node.children:
                traverse_node(child)

        traverse_node(tree.root_node)

        # Analyze dependencies (simplified - just direct imports)
        dependencies = []
        for imp in imports:
            if 'from' in imp:
                # Extract module name from "from module import ..."
                parts = imp.split()
                if len(parts) >= 2 and parts[0] == 'from':
                    dependencies.append(parts[1])

        return DependencyInfo(
            file_path=file_path,
            imports=imports,
            exports=exports,
            dependencies=dependencies
        )

    def _update_global_symbols(self, file_path: str, symbols: List[Symbol]):
        """Update the global symbol index."""
        self._global_symbols[file_path] = symbols

        # Update reference index
        for symbol in symbols:
            if symbol.name not in self._symbol_references:
                self._symbol_references[symbol.name] = []
            self._symbol_references[symbol.name].append(symbol.location)

    async def index_project_files(self, project_root: str):
        """
        Asynchronously index all files in a project for cross-file analysis.

        Args:
            project_root: Root directory of the project
        """
        import asyncio

        supported_extensions = {'.py', '.js', '.jsx', '.ts', '.tsx', '.vue'}

        # Collect all files to index
        files_to_index = []
        for root, dirs, files in os.walk(project_root):
            # Skip common directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', '.git'}]

            for file in files:
                if Path(file).suffix.lower() in supported_extensions:
                    file_path = os.path.join(root, file)
                    files_to_index.append(file_path)

        # Index files asynchronously
        for file_path in files_to_index:
            try:
                # Run symbol extraction in thread pool to avoid blocking
                symbols = await asyncio.get_event_loop().run_in_executor(None, self.get_symbols, file_path)
                logger.info(f"Indexed file: {file_path} ({len(symbols)} symbols)")
            except Exception as e:
                logger.warning(f"Failed to index file {file_path}: {e}")

    async def analyze_code_file(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze a code file and return detailed information about its structure.

        Args:
            file_path: Path to the file to analyze

        Returns:
            Dictionary containing symbols, dependencies, and analysis
        """
        symbols = self.get_symbols(file_path)
        dependencies = self.analyze_dependencies(file_path)

        result = {
            "file_path": file_path,
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "line": s.location.line,
                    "type_info": s.type_info,
                    "scope": s.scope
                } for s in symbols
            ],
            "dependencies": {
                "imports": dependencies.imports,
                "exports": dependencies.exports,
                "dependency_modules": dependencies.dependencies
            }
        }

        return result

         

    async def find_symbol_references(self, symbol_name: str, file_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find all references to a symbol across the codebase.

        Args:
            symbol_name: Name of the symbol to find
            file_path: Optional file to search in

        Returns:
            List of reference dictionaries
        """
        references = self.find_references(symbol_name, file_path)

        return [
            {
                "file": r.file_path,
                "line": r.line,
                "column": r.column,
                "context": ""  # Could be enhanced to show code context
            } for r in references
        ]

    async def get_symbol_info(self, file_path: str, symbol_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific symbol.

        Args:
            file_path: File containing the symbol
            symbol_name: Name of the symbol

        Returns:
            Dictionary containing symbol information or None if not found
        """
        symbols = self.get_symbols(file_path)
        symbol = next((s for s in symbols if s.name == symbol_name), None)

        if not symbol:
            return None

        type_info = self.get_type_info(symbol)

        result = {
            "name": symbol.name,
            "type": symbol.kind,
            "file": symbol.location.file_path,
            "line": symbol.location.line,
            "docstring": symbol.docstring
        }

        return result

    def index_project(self, project_root: str):

        """
        Args:
            file_path: File containing the symbol
            symbol_name: Name of the symbol

        Returns:
            Dictionary containing symbol information or None if not found
        """
        symbols = self.get_symbols(file_path)
        symbol = next((s for s in symbols if s.name == symbol_name), None)

        if not symbol:
            return None

        type_info = self.get_type_info(symbol)

        result = {
            "name": symbol.name,
            "type": symbol.kind,
            "file": symbol.location.file_path,
            "line": symbol.location.line,
            "docstring": symbol.docstring
        }

        return result

    def index_project(self, project_root: str):
        """
        Index all files in a project for cross-file analysis.

        Args:
            project_root: Root directory of the project
        """
        supported_extensions = {'.py', '.js', '.jsx', '.ts', '.tsx', '.vue'}

        for root, dirs, files in os.walk(project_root):
            # Skip common directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', '__pycache__', '.git'}]

            for file in files:
                if Path(file).suffix.lower() in supported_extensions:
                    file_path = os.path.join(root, file)
                    try:
                        self.get_symbols(file_path)
                        logger.info(f"Indexed file: {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to index file {file_path}: {e}")

    def clear_cache(self):
        """Clear all caches."""
        self._ast_cache.clear()
        self._symbol_cache.clear()
        self._file_hashes.clear()
        self._global_symbols.clear()
        self._symbol_references.clear()

# Global service instance
_code_intelligence_service = None

def get_code_intelligence_service() -> CodeIntelligenceService:
    """Get or create the global code intelligence service instance."""
    global _code_intelligence_service
    if _code_intelligence_service is None:
        try:
            _code_intelligence_service = CodeIntelligenceService()
        except ImportError as e:
            logger.error(f"Failed to initialize CodeIntelligenceService: {e}")
            raise
    return _code_intelligence_service

# Tool decorators for agent integration
from langchain_core.tools import tool

@tool
def analyze_code_file(file_path: str) -> str:
    """
    Analyze a code file and return detailed information about its structure.

    Args:
        file_path: Path to the file to analyze

    Returns:
        JSON string containing symbols, dependencies, and analysis
    """
    try:
        service = get_code_intelligence_service()

        symbols = service.get_symbols(file_path)
        dependencies = service.analyze_dependencies(file_path)

        result = {
            "file_path": file_path,
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "line": s.location.line,
                    "type_info": s.type_info,
                    "scope": s.scope
                } for s in symbols
            ],
            "dependencies": {
                "imports": dependencies.imports,
                "exports": dependencies.exports,
                "dependency_modules": dependencies.dependencies
            }
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error analyzing file: {str(e)}"

@tool
def find_symbol_references(symbol_name: str, file_path: Optional[str] = None) -> str:
    """
    Find all references to a symbol across the codebase.

    Args:
        symbol_name: Name of the symbol to find
        file_path: Optional file to search in (searches all indexed files if None)

    Returns:
        JSON string containing reference locations
    """
    try:
        service = get_code_intelligence_service()

        references = service.find_references(symbol_name, file_path)

        result = {
            "symbol_name": symbol_name,
            "references": [
                {
                    "file_path": r.file_path,
                    "line": r.line,
                    "column": r.column
                } for r in references
            ]
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error finding references: {str(e)}"

@tool
def get_symbol_info(symbol_name: str, file_path: str) -> str:
    """
    Get detailed information about a specific symbol.

    Args:
        symbol_name: Name of the symbol
        file_path: File containing the symbol

    Returns:
        JSON string containing symbol information
    """
    try:
        service = get_code_intelligence_service()

        symbols = service.get_symbols(file_path)
        symbol = next((s for s in symbols if s.name == symbol_name), None)

        if not symbol:
            return f"Symbol '{symbol_name}' not found in {file_path}"

        type_info = service.get_type_info(symbol)

        result = {
            "name": symbol.name,
            "kind": symbol.kind,
            "location": {
                "file_path": symbol.location.file_path,
                "line": symbol.location.line,
                "column": symbol.location.column
            },
            "type_info": symbol.type_info,
            "scope": symbol.scope,
            "parent_symbol": symbol.parent_symbol,
            "type_details": {
                "annotation": type_info.type_annotation if type_info else None,
                "inferred": type_info.inferred_type if type_info else None
            } if type_info else None
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"Error getting symbol info: {str(e)}"

@tool
def index_project_files(project_root: str) -> str:
    """
    Index all code files in a project for intelligent analysis.

    Args:
        project_root: Root directory of the project to index

    Returns:
        Status message
    """
    try:
        service = get_code_intelligence_service()
        service.index_project(project_root)
        return f"Successfully indexed project files in {project_root}"

    except Exception as e:
        return f"Error indexing project: {str(e)}"

# Export the tools for use in agents
CODE_INTELLIGENCE_TOOLS = [
    analyze_code_file,
    find_symbol_references,
    get_symbol_info,
    index_project_files
]