"""
ChromaDB Integration Service

This service provides automatic file indexing to ChromaDB for all file operations
including creation, modification, and editing. It also handles sandbox file indexing.
"""

import os
import logging
import hashlib
import mimetypes
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
from datetime import datetime

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

# Import centralized ChromaDB configuration
try:
    from app.config.chroma_config import get_chroma_path
    CHROMA_CONFIG_AVAILABLE = True
except ImportError:
    CHROMA_CONFIG_AVAILABLE = False

logger = logging.getLogger(__name__)

class ChromaDBIntegrationService:
    """Service for automatic ChromaDB integration with file operations."""
    
    def __init__(self, persist_directory: str = None):
        if not CHROMADB_AVAILABLE:
            logger.warning("ChromaDB not available - file indexing disabled")
            self.enabled = False
            return
            
        self.enabled = True
        
        # Use centralized configuration if available, otherwise fall back to provided path or default
        if persist_directory is None:
            if CHROMA_CONFIG_AVAILABLE:
                persist_directory = get_chroma_path("integration")
                logger.info(f"Using centralized ChromaDB path: {persist_directory}")
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
        
        # File extensions to index
        self.indexable_extensions = {
            '.py', '.js', '.jsx', '.ts', '.tsx', '.vue', '.java', '.cpp', '.c', '.h',
            '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala', '.r',
            '.m', '.mm', '.sh', '.sql', '.html', '.css', '.scss', '.sass', '.less',
            '.json', '.yaml', '.yml', '.xml', '.md', '.txt', '.env', '.config',
            '.dockerfile', '.gitignore', '.gitattributes'
        }
        
        # Directories to exclude from indexing
        self.excluded_dirs = {
            'node_modules', '.git', '.vscode', '.idea', '__pycache__', '.pytest_cache',
            'venv', 'env', '.env', 'dist', 'build', '.next', '.nuxt', 'target',
            'bin', 'obj', '.gradle', '.mvn', 'coverage', '.nyc_output'
        }
        
        logger.info("ChromaDB Integration Service initialized")
    
    def get_or_create_collection(self, name: str):
        """Get or create a ChromaDB collection."""
        if not self.enabled:
            return None
            
        if name not in self.collections:
            self.collections[name] = self.client.get_or_create_collection(name=name)
        return self.collections[name]
    
    def should_index_file(self, file_path: str) -> bool:
        """Determine if a file should be indexed."""
        if not self.enabled:
            return False
            
        path = Path(file_path)
        
        # Check if file extension is indexable
        if path.suffix.lower() not in self.indexable_extensions:
            return False
            
        # Check if any parent directory is excluded
        for part in path.parts:
            if part in self.excluded_dirs:
                return False
                
        # Check file size (skip files larger than 1MB)
        try:
            if path.exists() and path.stat().st_size > 1024 * 1024:
                return False
        except (OSError, PermissionError):
            return False
            
        return True
    
    def generate_file_id(self, file_path: str, content: str = None) -> str:
        """Generate a unique ID for a file."""
        # Use file path and content hash for unique ID
        path_hash = hashlib.md5(file_path.encode()).hexdigest()[:8]
        if content:
            content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
            return f"file_{path_hash}_{content_hash}"
        return f"file_{path_hash}"
    
    def chunk_content(self, content: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
        """Split content into overlapping chunks."""
        if len(content) <= chunk_size:
            return [content]
            
        chunks = []
        start = 0
        while start < len(content):
            end = start + chunk_size
            chunk = content[start:end]
            chunks.append(chunk)
            start = end - overlap
            
        return chunks
    
    def extract_metadata(self, file_path: str, content: str) -> Dict[str, Any]:
        """Extract metadata from file."""
        path = Path(file_path)
        
        metadata = {
            'file_path': str(path),
            'filename': path.name,
            'extension': path.suffix.lower(),
            'directory': str(path.parent),
            'size': len(content),
            'indexed_at': datetime.now().isoformat(),
            'content_type': mimetypes.guess_type(str(path))[0] or 'text/plain'
        }
        
        # Add language-specific metadata
        if path.suffix.lower() in ['.py']:
            metadata['language'] = 'python'
        elif path.suffix.lower() in ['.js', '.jsx']:
            metadata['language'] = 'javascript'
        elif path.suffix.lower() in ['.ts', '.tsx']:
            metadata['language'] = 'typescript'
        elif path.suffix.lower() in ['.vue']:
            metadata['language'] = 'vue'
        elif path.suffix.lower() in ['.html']:
            metadata['language'] = 'html'
        elif path.suffix.lower() in ['.css', '.scss', '.sass', '.less']:
            metadata['language'] = 'css'
        elif path.suffix.lower() in ['.md']:
            metadata['language'] = 'markdown'
        elif path.suffix.lower() in ['.json']:
            metadata['language'] = 'json'
        elif path.suffix.lower() in ['.yaml', '.yml']:
            metadata['language'] = 'yaml'
        
        return metadata
    
    def index_file(self, file_path: str, content: str = None, collection_name: str = "files") -> bool:
        """Index a single file in ChromaDB."""
        if not self.enabled or not self.should_index_file(file_path):
            return False
            
        try:
            # Read content if not provided
            if content is None:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
                    return False
            
            # Skip empty files
            if not content.strip():
                return False
                
            collection = self.get_or_create_collection(collection_name)
            if not collection:
                return False
            
            # Extract metadata
            metadata = self.extract_metadata(file_path, content)
            
            # Chunk content for large files
            chunks = self.chunk_content(content)
            
            # Prepare documents for indexing
            documents = []
            metadatas = []
            ids = []
            
            for i, chunk in enumerate(chunks):
                doc_id = f"{self.generate_file_id(file_path, chunk)}_{i}"
                chunk_metadata = metadata.copy()
                chunk_metadata.update({
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'chunk_size': len(chunk)
                })
                
                documents.append(chunk)
                metadatas.append(chunk_metadata)
                ids.append(doc_id)
            
            # Generate embeddings
            embeddings = self.embedding_model.encode(documents).tolist()
            
            # Add to collection (upsert to handle updates)
            collection.upsert(
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Indexed file {file_path} with {len(chunks)} chunks")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index file {file_path}: {e}")
            return False
    
    def remove_file_from_index(self, file_path: str, collection_name: str = "files") -> bool:
        """Remove a file from the ChromaDB index."""
        if not self.enabled:
            return False
            
        try:
            collection = self.get_or_create_collection(collection_name)
            if not collection:
                return False
            
            # Find all documents for this file
            results = collection.get(
                where={"file_path": file_path}
            )
            
            if results['ids']:
                collection.delete(ids=results['ids'])
                logger.info(f"Removed {len(results['ids'])} chunks for file {file_path}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to remove file {file_path} from index: {e}")
            
        return False
    
    def index_directory(self, directory_path: str, collection_name: str = "files", 
                       recursive: bool = True) -> Dict[str, Any]:
        """Index all files in a directory."""
        if not self.enabled:
            return {"success": False, "error": "ChromaDB not available"}
            
        indexed_files = []
        skipped_files = []
        errors = []
        
        try:
            path = Path(directory_path)
            if not path.exists():
                return {"success": False, "error": f"Directory not found: {directory_path}"}
            
            # Get all files
            if recursive:
                files = path.rglob('*')
            else:
                files = path.iterdir()
            
            for file_path in files:
                if file_path.is_file():
                    file_str = str(file_path)
                    
                    if self.should_index_file(file_str):
                        if self.index_file(file_str, collection_name=collection_name):
                            indexed_files.append(file_str)
                        else:
                            errors.append(f"Failed to index: {file_str}")
                    else:
                        skipped_files.append(file_str)
            
            result = {
                "success": True,
                "indexed_files": len(indexed_files),
                "skipped_files": len(skipped_files),
                "errors": len(errors),
                "details": {
                    "indexed": indexed_files[:10],  # Show first 10
                    "skipped": skipped_files[:10],   # Show first 10
                    "errors": errors[:10]            # Show first 10
                }
            }
            
            logger.info(f"Directory indexing complete: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to index directory {directory_path}: {e}")
            return {"success": False, "error": str(e)}
    
    def search_files(self, query: str, collection_name: str = "files", 
                    n_results: int = 10) -> List[Dict[str, Any]]:
        """Search for files using semantic similarity."""
        if not self.enabled:
            return []
            
        try:
            collection = self.get_or_create_collection(collection_name)
            if not collection:
                return []
            
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
                        'score': 1.0 - (results['distances'][0][i] if results['distances'] and results['distances'][0] else 0),
                        'id': results['ids'][0][i] if results['ids'] and results['ids'][0] else None
                    })
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search files: {e}")
            return []
    
    def get_collection_stats(self, collection_name: str = "files") -> Dict[str, Any]:
        """Get statistics for a collection."""
        if not self.enabled:
            return {"enabled": False}
            
        try:
            collection = self.get_or_create_collection(collection_name)
            if not collection:
                return {"error": "Collection not found"}
            
            # Get collection info
            count = collection.count()
            
            return {
                "enabled": True,
                "collection_name": collection_name,
                "document_count": count,
                "persist_directory": str(self.persist_directory)
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}

    def index_chat_message(self, message: str, role: str, session_id: str, 
                          message_index: int = 0, collection_name: str = "chat_history") -> bool:
        """
        Index a chat message into ChromaDB for semantic search.
        
        Args:
            message: The chat message content
            role: The role (user, assistant, system)
            session_id: The session identifier
            message_index: The message index in the conversation
            collection_name: The ChromaDB collection name
            
        Returns:
            bool: True if indexing was successful, False otherwise
        """
        if not self.enabled:
            logger.warning("ChromaDB not enabled - skipping chat message indexing")
            return False
            
        try:
            collection = self.get_or_create_collection(collection_name)
            if not collection:
                logger.error(f"Failed to get or create collection: {collection_name}")
                return False
            
            # Generate unique ID for this message
            message_id = f"{session_id}_{message_index}_{role}_{hashlib.md5(message.encode()).hexdigest()[:8]}"
            
            # Prepare metadata
            metadata = {
                "type": "chat_message",
                "role": role,
                "session_id": session_id,
                "message_index": message_index,
                "timestamp": datetime.now().isoformat(),
                "content_type": "text",
                "length": len(message)
            }
            
            # Chunk the message if it's too long
            chunks = self.chunk_content(message, chunk_size=500, overlap=50)
            
            # Index each chunk
            for i, chunk in enumerate(chunks):
                chunk_id = f"{message_id}_chunk_{i}"
                chunk_metadata = metadata.copy()
                chunk_metadata["chunk_index"] = i
                chunk_metadata["total_chunks"] = len(chunks)
                
                # Generate embedding
                embedding = self.embedding_model.encode(chunk).tolist()
                
                # Add to collection
                collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[chunk_metadata]
                )
            
            logger.info(f"Successfully indexed chat message: {message_id} ({len(chunks)} chunks)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index chat message: {e}")
            return False

    def search_chat_history(self, query: str, session_id: str = None, 
                           collection_name: str = "chat_history", 
                           n_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search chat history using semantic search.
        
        Args:
            query: The search query
            session_id: Optional session ID to filter results
            collection_name: The ChromaDB collection name
            n_results: Number of results to return
            
        Returns:
            List of search results with metadata
        """
        if not self.enabled:
            logger.warning("ChromaDB not enabled - skipping chat history search")
            return []
            
        try:
            collection = self.get_or_create_collection(collection_name)
            if not collection:
                logger.error(f"Collection not found: {collection_name}")
                return []
            
            # Generate query embedding
            query_embedding = self.embedding_model.encode(query).tolist()
            
            # Prepare where clause for filtering
            where_clause = {"type": "chat_message"}
            if session_id:
                where_clause["session_id"] = session_id
            
            # Search
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_clause,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format results
            formatted_results = []
            if results and results.get('documents') and len(results['documents']) > 0:
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results.get('metadatas') else {}
                    distance = results['distances'][0][i] if results.get('distances') else 0
                    
                    formatted_results.append({
                        "content": doc,
                        "metadata": metadata,
                        "similarity_score": 1 - distance,  # Convert distance to similarity
                        "distance": distance
                    })
            
            logger.info(f"Chat history search returned {len(formatted_results)} results")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search chat history: {e}")
            return []

# Global instance
chroma_integration = ChromaDBIntegrationService()