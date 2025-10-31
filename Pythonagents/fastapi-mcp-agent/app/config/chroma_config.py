"""
ChromaDB Configuration

Centralized configuration for ChromaDB to ensure all instances use absolute paths
and avoid creating database folders in sandbox directories.
"""

import os
from pathlib import Path

# Get the project root directory (parent of fastapi-mcp-agent)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
CHROMA_BASE_DIR = PROJECT_ROOT / "chroma_databases"

# Ensure the base directory exists
CHROMA_BASE_DIR.mkdir(exist_ok=True)

# ChromaDB paths configuration
CHROMA_PATHS = {
    "integration": str(CHROMA_BASE_DIR / "chroma_integration_db"),
    "memory": str(CHROMA_BASE_DIR / "chroma_memory_db"), 
    "vector_store": str(CHROMA_BASE_DIR / "chroma_vector_db"),
    "mcp_server": str(CHROMA_BASE_DIR / "chroma_mcp_db")
}

def get_chroma_path(db_type: str) -> str:
    """
    Get the absolute path for a ChromaDB instance.
    
    Args:
        db_type: Type of database ('integration', 'memory', 'vector_store', 'mcp_server')
        
    Returns:
        Absolute path string for the ChromaDB instance
    """
    if db_type not in CHROMA_PATHS:
        raise ValueError(f"Unknown ChromaDB type: {db_type}. Available types: {list(CHROMA_PATHS.keys())}")
    
    path = CHROMA_PATHS[db_type]
    # Ensure the directory exists
    Path(path).mkdir(exist_ok=True)
    return path

def get_all_chroma_paths() -> dict:
    """Get all configured ChromaDB paths."""
    return CHROMA_PATHS.copy()