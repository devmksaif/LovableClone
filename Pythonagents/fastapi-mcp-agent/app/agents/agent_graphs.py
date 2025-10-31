import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.runnables import RunnableLambda
 


from .local_tools import LOCAL_TOOLS, set_session_context

from langgraph.graph import StateGraph, END
from langgraph.store.memory import InMemoryStore
from langgraph.prebuilt import create_react_agent

# ChromaDB imports for persistent memory store
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    SentenceTransformer = None

# Import centralized ChromaDB configuration
try:
    from app.config.chroma_config import get_chroma_path
    CHROMA_CONFIG_AVAILABLE = True
except ImportError:
    CHROMA_CONFIG_AVAILABLE = False


# Memory store item class to mimic InMemoryStore interface
@dataclass
class MemoryItem:
    """Represents a memory item with key and value."""
    key: str
    value: Any


class ChromaMemoryStore:
    """ChromaDB-based persistent memory store that mimics InMemoryStore interface."""
    
    def __init__(self, persist_directory: str = None):
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB and sentence-transformers are required for ChromaMemoryStore")
        
        # Use centralized configuration if available, otherwise fall back to provided path or default
        if persist_directory is None:
            if CHROMA_CONFIG_AVAILABLE:
                persist_directory = get_chroma_path("memory")
                logging.info(f"Using centralized ChromaDB memory path: {persist_directory}")
            else:
                persist_directory = "./chroma_memory_db"
                logging.warning("Centralized ChromaDB config not available, using relative path")
            
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        
        # Initialize sentence transformer for embeddings
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Cache for collections
        self.collections = {}
    
    def _get_collection_name(self, namespace) -> str:
        """Convert namespace tuple to collection name."""
        if isinstance(namespace, tuple):
            return "_".join(str(part) for part in namespace)
        return str(namespace)
    
    def _get_or_create_collection(self, collection_name: str):
        """Get or create a ChromaDB collection."""
        if collection_name not in self.collections:
            self.collections[collection_name] = self.client.get_or_create_collection(name=collection_name)
        return self.collections[collection_name]
    
    def get(self, namespace, key: str):
        """Get a value from the store."""
        collection_name = self._get_collection_name(namespace)
        collection = self._get_or_create_collection(collection_name)
        
        try:
            result = collection.get(ids=[key])
            if result['documents'] and len(result['documents']) > 0:
                # Parse the stored JSON
                value = json.loads(result['documents'][0])
                return MemoryItem(key=key, value=value)
        except Exception as e:
            logger.warning(f"Failed to get item {key} from namespace {namespace}: {e}")
        
        return None
    
    def put(self, namespace, key: str, value: Any):
        """Put a value into the store."""
        collection_name = self._get_collection_name(namespace)
        collection = self._get_or_create_collection(collection_name)
        
        try:
            # Serialize value to JSON
            value_json = json.dumps(value)
            
            # Generate embedding for the value (for semantic search)
            embedding = self.embedding_model.encode([value_json]).tolist()[0]
            
            # Store in ChromaDB
            collection.upsert(
                embeddings=[embedding],
                documents=[value_json],
                metadatas=[{"key": key, "namespace": str(namespace)}],
                ids=[key]
            )
        except Exception as e:
            logger.error(f"Failed to put item {key} in namespace {namespace}: {e}")
            raise
    
    def search(self, namespace, query: str = None, limit: int = 5):
        """Search for items in the store using semantic search."""
        collection_name = self._get_collection_name(namespace)
        collection = self._get_or_create_collection(collection_name)
        
        try:
            if query:
                # Generate query embedding
                query_embedding = self.embedding_model.encode([query]).tolist()[0]
                
                # Search
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit
                )
                
                # Format results
                items = []
                if results['documents'] and results['documents'][0]:
                    for i, doc in enumerate(results['documents'][0]):
                        try:
                            value = json.loads(doc)
                            key = results['metadatas'][0][i].get('key', f"item_{i}")
                            items.append(MemoryItem(key=key, value=value))
                        except (json.JSONDecodeError, KeyError):
                            continue
                
                return items
            else:
                # Return all items if no query
                result = collection.get(limit=limit)
                items = []
                if result['documents']:
                    for i, doc in enumerate(result['documents']):
                        try:
                            value = json.loads(doc)
                            key = result['metadatas'][i].get('key', f"item_{i}")
                            items.append(MemoryItem(key=key, value=value))
                        except (json.JSONDecodeError, KeyError):
                            continue
                
                return items
        except Exception as e:
            logger.warning(f"Failed to search namespace {namespace}: {e}")
            return []


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string.
    
    Uses tiktoken for accurate counting if available, otherwise falls back to 
    rough approximation: 1 token ≈ 4 characters for English text.
    """
    try:
        import tiktoken
        # Use cl100k_base encoding (used by GPT-3.5/4)
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        # Fallback to rough approximation
        return len(text) // 4


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a maximum token limit.
    
    Args:
        text: The text to truncate
        max_tokens: Maximum number of tokens allowed
        
    Returns:
        Truncated text that fits within the token limit
    """
    if estimate_tokens(text) <= max_tokens:
        return text
    
    # Calculate approximate character limit
    max_chars = max_tokens * 4
    
    if len(text) <= max_chars:
        return text
    
    # Truncate and add indication
    truncated = text[:max_chars - 100]  # Leave room for truncation message
    return truncated + "\n\n[... content truncated due to length ...]"


def prepare_agent_input(input_text: str, max_input_tokens: int = 2000) -> str:
    """Prepare input text for agent processing by intelligently truncating if necessary.
    
    Uses a smart truncation strategy that preserves the most important parts:
    1. User request (highest priority)
    2. Current plan/Code (high priority)  
    3. Context and metadata (medium priority)
    4. Session info (lowest priority)
    
    Args:
        input_text: The input text to prepare
        max_input_tokens: Maximum tokens allowed for input (default 2000 to leave room for output)
        
    Returns:
        Prepared input text that fits within token limits
    """
    current_tokens = estimate_tokens(input_text)
    if current_tokens <= max_input_tokens:
        return input_text
    
    # Parse the input to identify different sections
    lines = input_text.split('\n')
    sections = {}
    current_section = "header"
    sections[current_section] = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Identify section headers
        if line.startswith("User Request:"):
            current_section = "user_request"
            sections[current_section] = []
        elif line.startswith("Current Plan:") or line.startswith("Generated Code:"):
            current_section = "main_content"
            sections[current_section] = []
        elif line.startswith("Original Request:") or line.startswith("Plan:"):
            current_section = "context"
            sections[current_section] = []
        elif line.startswith("Sandbox Context:"):
            current_section = "sandbox_context"
            sections[current_section] = []
        elif line.startswith("Review Preferences:"):
            current_section = "metadata"
            sections[current_section] = []
        elif line.startswith("Session ID:"):
            current_section = "session"
            sections[current_section] = []
            
        sections[current_section].append(line)
    
    # Calculate token allocation (prioritized)
    allocations = {
        "user_request": max_input_tokens * 0.4,  # 40% for user request
        "main_content": max_input_tokens * 0.35, # 35% for plan/code
        "context": max_input_tokens * 0.15,      # 15% for context
        "sandbox_context": max_input_tokens * 0.05, # 5% for sandbox context (reduced)
        "metadata": max_input_tokens * 0.03,     # 3% for metadata
        "session": max_input_tokens * 0.02,      # 2% for session info
        "header": max_input_tokens * 0.1         # 10% for instructions
    }
    
    # Build optimized input
    optimized_parts = []
    
    for section_name in ["header", "user_request", "main_content", "context", "sandbox_context", "metadata", "session"]:
        if section_name in sections:
            section_text = '\n'.join(sections[section_name])
            section_tokens = estimate_tokens(section_text)
            max_section_tokens = allocations.get(section_name, max_input_tokens * 0.1)
            
            if section_tokens > max_section_tokens:
                # Smart truncation for this section
                if section_name == "user_request":
                    # Keep the beginning of user request
                    optimized_parts.append(truncate_text_to_tokens(section_text, int(max_section_tokens)))
                elif section_name == "main_content":
                    # For code/plan, keep the most recent/important parts
                    if "Generated Code:" in section_text:
                        # Keep the end of generated code (most recent)
                        lines = section_text.split('\n')
                        truncated = truncate_text_to_tokens('\n'.join(lines[-50:]), int(max_section_tokens))  # Last 50 lines
                        optimized_parts.append("Generated Code (truncated):\n" + truncated)
                    else:
                        # Keep the beginning of plan
                        optimized_parts.append(truncate_text_to_tokens(section_text, int(max_section_tokens)))
                elif section_name == "sandbox_context":
                    # For sandbox context, keep only essential info (project type, frameworks, file count)
                    try:
                        import json
                        context_data = json.loads(section_text)
                        if isinstance(context_data, dict) and 'context' in context_data:
                            ctx = context_data['context']
                            essential = {
                                'project_type': ctx.get('project', {}).get('type', 'unknown'),
                                'frameworks': ctx.get('project', {}).get('frameworks', []),
                                'file_count': ctx.get('structure', {}).get('fileCount', 0),
                                'dependencies_count': len(ctx.get('dependencies', {}))
                            }
                            optimized_parts.append(f"Sandbox Context (essential): {json.dumps(essential, indent=2)}")
                        else:
                            # Fallback: keep only first 100 chars
                            optimized_parts.append(section_text[:100] + "...")
                    except:
                        # If JSON parsing fails, truncate aggressively
                        optimized_parts.append(truncate_text_to_tokens(section_text, int(max_section_tokens)))
                else:
                    # For other sections, truncate from the end
                    optimized_parts.append(truncate_text_to_tokens(section_text, int(max_section_tokens)))
            else:
                optimized_parts.append(section_text)
    
    result = '\n\n'.join(optimized_parts)
    
    # Final safety check
    if estimate_tokens(result) > max_input_tokens:
        result = truncate_text_to_tokens(result, max_input_tokens)
    
    return result



logger = logging.getLogger(__name__)

# Global memory store for long-term memory
_memory_store = None

def get_memory_store():
    """Get or create the global memory store instance."""
    global _memory_store
    if _memory_store is None:
        if CHROMADB_AVAILABLE:
            try:
                _memory_store = ChromaMemoryStore()
                logger.info("Using ChromaDB for persistent memory storage")
            except Exception as e:
                logger.warning(f"Failed to initialize ChromaMemoryStore, falling back to InMemoryStore: {e}")
                _memory_store = InMemoryStore()
                # Add search method to InMemoryStore for compatibility
                _memory_store.search = lambda namespace, query=None, limit=5: []
        else:
            logger.warning("ChromaDB not available, using InMemoryStore")
            _memory_store = InMemoryStore()
            # Add search method to InMemoryStore for compatibility
            _memory_store.search = lambda namespace, query=None, limit=5: []
    return _memory_store

async def store_user_profile(user_id: str, profile_data: Dict[str, Any], session_id: str = None):
    """Store semantic memory about a user (facts, preferences, etc.)."""
    store = get_memory_store()
    namespace = (user_id, "profile")
    
    # Get existing profile if it exists
    existing_profile = None
    try:
        existing_item = store.get(namespace, "current")
        existing_profile = existing_item.value if existing_item else {}
    except:
        existing_profile = {}
    
    # Merge with new data
    updated_profile = {**existing_profile, **profile_data}
    updated_profile["last_updated"] = asyncio.get_event_loop().time()
    if session_id:
        updated_profile["last_session"] = session_id
    
    store.put(namespace, "current", updated_profile)
    logger.info(f"Updated profile for user {user_id}")

async def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve semantic memory about a user."""
    store = get_memory_store()
    namespace = (user_id, "profile")

    try:
        item = store.get(namespace, "current")
        if item and hasattr(item, 'value'):
            return item.value
        return {}
    except Exception as e:
        logger.warning(f"Failed to retrieve profile for user {user_id}: {e}")
        return {}

async def store_agent_experience(user_id: str, experience_data: Dict[str, Any], session_id: str):
    """Store episodic memory about agent experiences/actions."""
    store = get_memory_store()
    namespace = (user_id, "experiences")
    
    experience_id = f"{session_id}_{int(asyncio.get_event_loop().time())}"
    experience_data["timestamp"] = asyncio.get_event_loop().time()
    experience_data["session_id"] = session_id
    
    store.put(namespace, experience_id, experience_data)
    logger.info(f"Stored experience for user {user_id}: {experience_id}")

async def search_user_memories(user_id: str, query: str, memory_type: str = "profile", limit: int = 5) -> List[Dict[str, Any]]:
    """Search user memories using semantic search."""
    store = get_memory_store()
    namespace = (user_id, memory_type)
    
    try:
        items = store.search(namespace, query=query, limit=limit)
        return [{"key": item.key, "value": item.value} for item in items]
    except:
        return []

async def update_agent_instructions(user_id: str, instructions_data: Dict[str, Any]):
    """Update procedural memory (agent instructions) based on feedback."""
    store = get_memory_store()
    namespace = (user_id, "instructions")
    
    # Get current instructions
    current_instructions = {}
    try:
        item = store.get(namespace, "current")
        if item and hasattr(item, 'value'):
            current_instructions = item.value
    except Exception as e:
        logger.warning(f"Failed to retrieve current instructions for user {user_id}: {e}")
    
    # Merge with new instructions
    updated_instructions = {**current_instructions, **instructions_data}
    updated_instructions["last_updated"] = asyncio.get_event_loop().time()
    
    store.put(namespace, "current", updated_instructions)
    logger.info(f"Updated instructions for user {user_id}")


async def create_planning_agent_instance(model: str, mcp_tools: List[Any], session_id: str, api_keys: Optional[Dict[str, str]] = None):
    """Create a planning agent instance with the specified model and tools."""
    llm = get_model_provider(model, api_keys)
    memory_store = get_memory_store()
    
    # System prompt for planning agent
    system_prompt = """You are a Planning Agent. Break down user requests into detailed, actionable steps. Consider tools, challenges, and dependencies. Output structured task lists."""

    return {
        "agent": create_agent(llm, mcp_tools, system_prompt, store=memory_store),
        "llm": llm,
        "memory_store": memory_store,
        "system_prompt": system_prompt
    }

async def create_code_generation_agent_instance(model: str, mcp_tools: List[Any], session_id: str, api_keys: Optional[Dict[str, str]] = None):
    """Create a code generation agent instance with the specified model and tools."""
    # Enable streaming for real-time code generation
    llm = get_model_provider(model, api_keys, streaming=True)
    memory = InMemoryStore()
    
    # System prompt for code generation agent
    system_prompt = """You are a Code Generation Agent. Implement plans with high-quality, working code. Use tools effectively, follow best practices, and ensure production-ready solutions."""

    return {
        "agent": create_agent(llm, mcp_tools, system_prompt),
        "llm": llm,
        "memory": memory,
        "system_prompt": system_prompt
    }

async def create_review_agent_instance(model: str, mcp_tools: List[Any], session_id: str, api_keys: Optional[Dict[str, str]] = None):
    """Create a review agent instance with the specified model and tools."""
    llm = get_model_provider(model, api_keys)
    memory = InMemoryStore()
    
    # System prompt for review agent
    system_prompt = """You are a Review Agent. Evaluate code quality, identify issues, suggest improvements for security, performance, and best practices. Provide actionable feedback."""

    return {
        "agent": create_agent(llm, mcp_tools, system_prompt),
        "llm": llm,
        "memory": memory,
        "system_prompt": system_prompt
    }

async def create_integrator_agent_instance(model: str, mcp_tools: List[Any], session_id: str, api_keys: Optional[Dict[str, str]] = None):
    """Create an integrator agent instance that validates code quality, safety, imports, and integration within the project."""
    llm = get_model_provider(model, api_keys)
    memory_store = get_memory_store()
    
    # System prompt for integrator agent
    system_prompt = """You are an Integration Validator. Validate code quality, safety, imports, and project integration. Check syntax, security, and proper file operations.

Guidelines:
- Use available tools to validate file existence and accessibility
- Check import statements against project structure
- Parse code to detect syntax issues
- Flag potentially dangerous operations
- Provide specific recommendations for fixes

Output Format (JSON):
{{"validation_passed": true/false, "issues": ["critical issue 1", "critical issue 2"], "warnings": ["warning 1", "warning 2"], "recommendations": ["fix suggestion 1", "fix suggestion 2"], "security_concerns": ["security issue 1"], "import_issues": ["import problem 1"], "syntax_errors": ["syntax error 1"]}}

Be thorough in your validation and provide actionable feedback.
"""

    return {
        "agent": create_agent(llm, mcp_tools, system_prompt, store=memory_store),
        "llm": llm,
        "memory_store": memory_store,
        "system_prompt": system_prompt
    }

async def create_architect_agent_instance(model: str, mcp_tools: List[Any], session_id: str, api_keys: Optional[Dict[str, str]] = None):
    """Create an architect agent instance that provides project context and file editing guidance."""
    llm = get_model_provider(model, api_keys)
    memory_store = get_memory_store()
    
    # System prompt for architect agent
    system_prompt = """You are an Architect Agent. Analyze project structure, identify files to edit, and provide context about codebase relationships. Use tools to explore project layout."""

    # Create React agent that can use tools for project analysis
    react_agent = create_react_agent(
        model=llm,
        tools=mcp_tools,
        prompt=system_prompt,
        store=memory_store
    )

    return {
        "agent": react_agent,
        "llm": llm,
        "memory_store": memory_store,
        "system_prompt": system_prompt
    }

def parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse model ID to extract provider and model name."""
    # Handle different model ID formats
    if "/" in model_id:
        parts = model_id.split("/")
        if len(parts) >= 2:
            provider = parts[0]
            model_name = "/".join(parts[1:])
            # Handle groq-openai models - they should use groq provider
            # but preserve the full model name including openai/ prefix
            if provider == "groq-openai":
                provider = "groq"
                model_name = "openai/" + model_name  # Preserve the openai/ prefix
            # Handle groq-qwen models - they should use groq provider
            elif provider == "groq-qwen":
                provider = "groq"
                model_name = "qwen/" + model_name  # Preserve the qwen/ prefix
            elif provider == "groq-moonshotai":
                provider = "groq"
                model_name = "moonshotai/" + model_name  # Preserve the moonshotai/ prefix
            # Handle openrouter models - they should use openrouter provider
            elif provider == "openrouter":
                provider = "openrouter"
                # Keep the model name as-is for OpenRouter
            # Handle OpenRouter models that have :free or other OpenRouter-specific suffixes
            elif ":free" in model_name or ":paid" in model_name:
                provider = "openrouter"
                # Keep the model name as-is for OpenRouter
            return provider, model_name
    
    # Handle provider:model format
    if ":" in model_id:
        provider, model_name = model_id.split(":", 1)
        return provider, model_name
    
    # Handle specific model patterns
    if model_id.startswith("gpt-"):
        return "openai", model_id
    elif model_id.startswith("claude-"):
        return "anthropic", model_id
    elif model_id.startswith("gemini-"):
        return "google", model_id
    elif model_id.startswith("llama") or model_id.startswith("mixtral"):
        return "groq", model_id
    elif model_id.startswith("openrouter-"):
        return "openrouter", model_id
    
    # Fallback for unexpected format
    return 'openai', 'gpt-4'

@dataclass
class AgentState:
    """State object for the agent graph."""
    user_request: str
    session_id: str
    model: str
    sandbox_context: Dict[str, Any]
    sandbox_id: str
    available_tools: Dict[str, List[Dict[str, Any]]]
    tool_results: List[Dict[str, Any]] = None
    conversation_history: List[Dict[str, str]] = None
    current_plan: List[str] = None
    generated_code: str = ""
    review_feedback: str = ""
    progress_updates: List[Dict[str, Any]] = None
    langchain_tools: List[Any] = field(default_factory=list)
    api_keys: Optional[Dict[str, str]] = None
    integration_results: Optional[Dict[str, Any]] = None
    complexity: str = "simple"  # "simple" or "complex"
    needs_refactoring: bool = False
    context_analysis: str = ""  # Analysis result from context_analysis agent
    project_folder: str = ""  # Project folder for file operations

    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []
        if self.progress_updates is None:
            self.progress_updates = []
        if self.langchain_tools is None:
            self.langchain_tools = []


def get_model_provider(model_name: str, api_keys: Optional[dict] = None, streaming: bool = False):
    """Get a model provider instance based on model name and API keys."""
    # Parse the model ID to get provider and model name
    provider, parsed_model = parse_model_id(model_name)
    
    # Debug logging
    logger.info(f"get_model_provider called with model_name: {model_name}, provider: {provider}, parsed_model: {parsed_model}, streaming: {streaming}")
    logger.info(f"api_keys parameter: {api_keys}")
    
    # Get API keys from parameters or environment variables
    # If api_keys dict is provided, use values from it (even if empty), otherwise fall back to env vars
    groq_key = api_keys.get("groq") if api_keys else os.getenv("GROQ_API_KEY")
    anthropic_key = api_keys.get("anthropic") if api_keys else os.getenv("ANTHROPIC_API_KEY")
    google_key = api_keys.get("gemini") if api_keys else os.getenv("GOOGLE_API_KEY")
    openai_key = api_keys.get("openai") if api_keys else os.getenv("OPENAI_API_KEY")
    openrouter_key = api_keys.get("openrouter") if api_keys else os.getenv("OPENROUTER_API_KEY")
    
    # Debug logging for API keys
    logger.info(f"Groq key from api_keys: {api_keys.get('groq') if api_keys else 'None'}")
    logger.info(f"Final groq_key (first 20 chars): {groq_key[:20] if groq_key else 'None'}...")
    
    # Groq models
    if provider == "groq":
        if not groq_key:
            raise ValueError("GROQ API key is required for Groq models")
        return ChatGroq(
            api_key=groq_key,
            model=parsed_model,
            temperature=0.3,
            max_tokens=8192,
            timeout=60,
            max_retries=3,
           
        )
    
    # Anthropic models
    elif provider == "anthropic":
        if not anthropic_key:
            raise ValueError("Anthropic API key is required for Anthropic models")
        return ChatAnthropic(
            api_key=anthropic_key,
            model=parsed_model,
            temperature=0.3,
            max_tokens=8192,
            timeout=60,
            max_retries=3,
          
        )
    
    # Google models
    elif provider == "google":
        if not google_key:
            raise ValueError("Google API key is required for Google models")
        return ChatGoogleGenerativeAI(
            api_key=google_key,
            model=parsed_model,
            temperature=0.3,
            max_tokens=8192,
            timeout=60,
            max_retries=3,
        )
    
    # OpenAI models
    elif provider == "openai":
        if not openai_key:
            raise ValueError("OpenAI API key is required for OpenAI models")
        return ChatOpenAI(
            api_key=openai_key,
            model=parsed_model,
            temperature=0.3,
            max_tokens=8192,
            timeout=60,
            max_retries=3,
   
        )
    
    # OpenRouter models
    elif provider == "openrouter":
        if not openrouter_key:
            raise ValueError("OpenRouter API key is required for OpenRouter models")
        return ChatOpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            model=parsed_model,
            temperature=0.3,
            max_tokens=8192,
            timeout=60,
            max_retries=3,
    
        )
    
    else:
        # Fallback to OpenAI
        if not openai_key:
            raise ValueError("OpenAI API key is required for fallback model")
        return ChatOpenAI(
            api_key=openai_key,
            model="gpt-4",
            temperature=0.3,
            max_tokens=4096,
            timeout=60,
            max_retries=3,
        )


def create_agent(llm, tools, system_prompt, store=None):
    """Create a ReAct agent with tools properly bound to the LLM."""
    try:
        # Ensure tools is a list (not None)
        if tools is None:
            tools = []
        
        # Create the ReAct agent using langgraph.prebuilt
        # The prompt parameter accepts a string that becomes the system message
        react_agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_prompt
        )
        
         
        return react_agent
    except Exception as e:
        logger.error(f"Failed to create ReAct agent: {e}")
        logger.error(f"LLM type: {type(llm)}, Tools count: {len(tools) if tools else 0}")
        raise


def create_agents_with_tools(llm, tools, memory_store=None):
    """Create configured agent instances with MCP tools and memory store."""
    if memory_store is None:
        memory_store = get_memory_store()
    # Planning Agent
    # Build a tools description string to include in prompts so agents know what's available
    if tools:
        try:
            tool_lines = []
            for t in tools:
                # Some tool objects may be dict-like or have attributes
                name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None) or str(t)
                desc = getattr(t, "description", None) or (t.get("description") if isinstance(t, dict) else "")
                tool_lines.append(f"- {name}: {desc}")
            tools_list_text = "\n".join(tool_lines)
            tool_names = ", ".join([ln.split(":",1)[0].strip()[2:] for ln in tool_lines])
        except Exception:
            tools_list_text = "(unable to enumerate tools)"
            tool_names = ""
    else:
        tools_list_text = "(no tools available)"
        tool_names = ""

    planning_system_prompt = f"""
You are a senior software architect with 15+ years of experience. Create detailed, actionable development plans that consider architecture, scalability, and maintainability.

Environment: Sandbox with existing files — you MAY and SHOULD use the available tools to explore and modify the project.

Tools Available:
{tools_list_text}

When you need to inspect or change files, CALL the appropriate tool by name (do not output shell scripts or pseudo-commands). For example, use `read_file`, `list_dir`, or `write_file` where appropriate.

CRITICAL REQUIREMENTS:
1. **Explore First**: Always use tools to understand the existing codebase structure, dependencies, and patterns
2. **Framework-Specific**: Consider the specific framework (React, Vue, Node.js, Python, etc.) and its best practices
3. **Architecture**: Think about component structure, state management, data flow, and scalability
4. **Dependencies**: Identify what libraries/packages are needed and check if they're already installed
5. **File Organization**: Plan the file structure following framework conventions
6. **Integration Points**: Consider how this fits with existing code and APIs

OUTPUT FORMAT (JSON):
{{
  "intent": "Clear description of what the user wants",
  "complexity": "simple|moderate|complex",
  "estimated_time": "brief time estimate",
  "architecture_approach": "MVC|Component-based|Microservices|etc",
  "framework_specific": "React/Vue/Angular specific considerations",
  "steps": [
    "Step 1: Detailed technical description with file paths",
    "Step 2: Implementation approach with specific technologies",
    "Step 3: Integration and testing approach"
  ],
  "files_to_create": ["path/to/file1.js", "path/to/file2.vue"],
  "files_to_modify": ["existing/file.js"],
  "dependencies_needed": ["package1", "package2"],
  "tools_needed": ["tool1", "tool2"],
  "potential_challenges": ["Challenge 1 and mitigation", "Challenge 2 and solution"],
  "testing_strategy": "Unit tests, integration tests, or manual testing approach"
}}

Be specific, technical, and actionable. Include file paths and consider edge cases.
"""

    planning_agent = create_agent(llm, tools, system_prompt=planning_system_prompt)

    # Code Generation Agent
    code_gen_system_prompt = f"""
You are a senior full-stack developer with expertise in modern web frameworks. Generate production-ready, well-structured code that follows industry best practices.

Tools Available:
{tools_list_text}

CODE QUALITY REQUIREMENTS:
1. **Framework Best Practices**: Follow React/Vue/Angular conventions, hooks patterns, component lifecycle
2. **TypeScript/JavaScript**: Proper typing, async/await, error handling, modern ES6+ features
3. **Code Organization**: Clear component structure, separation of concerns, reusable utilities
4. **Performance**: Efficient rendering, lazy loading, memoization where appropriate
5. **Accessibility**: ARIA labels, keyboard navigation, screen reader support
6. **Security**: Input validation, XSS prevention, secure API calls
7. **Error Handling**: Try/catch blocks, user-friendly error messages, graceful degradation
8. **Testing**: Consider testability, include test examples if requested

IMPLEMENTATION RULES:
- Use modern React hooks (useState, useEffect, useContext) over class components
- Implement proper state management (Context API, Redux, or similar)
- Follow component composition patterns over inheritance
- Use semantic HTML and CSS-in-JS or styled-components
- Implement responsive design with mobile-first approach
- Add proper loading states and error boundaries
- Use environment variables for configuration
- Follow RESTful API patterns or GraphQL best practices

OUTPUT REQUIREMENTS:
- Generate complete, runnable code with all imports
- Include comments for complex logic
- Use meaningful variable and function names
- Follow consistent code formatting
- Include error handling and edge cases
- Add TypeScript interfaces/types when applicable
- Provide usage examples in comments

Rules: Use the listed tools to explore the codebase and modify files. When you need to read files, call `read_file`; to list directories, call `list_dir`; to create/update files, call `write_file`. Do NOT output shell scripts or human-facing instructions for manual edits — perform edits via tools.

Output: Return the final code or, when making file changes, perform the change via the appropriate tool and then output the path(s) modified and a brief summary.
"""

    code_gen_agent = create_agent(llm, tools, system_prompt=code_gen_system_prompt)

    # Review Agent
    review_system_prompt = f"""
You are a senior code reviewer with 10+ years of experience. Perform thorough code reviews focusing on quality, security, performance, and maintainability.

Tools Available:
{tools_list_text}

REVIEW CRITERIA - Check for:

**CODE QUALITY:**
- Clean, readable code following language/framework conventions
- Proper naming conventions (camelCase, PascalCase, kebab-case as appropriate)
- Consistent code formatting and indentation
- Appropriate comments for complex logic
- No dead code or unused imports/variables
- Proper separation of concerns

**FUNCTIONAL CORRECTNESS:**
- Logic errors or bugs in the implementation
- Edge cases not handled properly
- Missing error handling and validation
- Incorrect API usage or data flow
- State management issues (race conditions, improper updates)

**SECURITY VULNERABILITIES:**
- XSS (Cross-Site Scripting) vulnerabilities
- SQL injection risks
- Insecure direct object references
- Missing input validation/sanitization
- Exposed sensitive data (API keys, passwords)
- Unsafe use of eval(), innerHTML, or other dangerous functions

**PERFORMANCE ISSUES:**
- Inefficient algorithms (O(n²) where O(n) is possible)
- Unnecessary re-renders in React/Vue
- Missing memoization where appropriate
- Large bundle sizes or excessive dependencies
- Memory leaks (unclosed event listeners, timers)

**MAINTAINABILITY:**
- Code complexity (functions > 50 lines, components with too many responsibilities)
- Lack of reusability/modularity
- Tight coupling between components
- Missing TypeScript types/interfaces
- Inconsistent patterns across the codebase

**FRAMEWORK SPECIFIC:**
- React: Proper hooks usage, key props, effect cleanup
- Vue: Composition API patterns, reactive data handling
- Angular: Dependency injection, change detection strategy
- General: Proper lifecycle management, component communication

**ACCESSIBILITY:**
- Missing alt text for images
- Insufficient color contrast
- Keyboard navigation support
- Screen reader compatibility
- Semantic HTML usage

When reviewing, you MAY call tools to inspect files (e.g. `read_file`) or search code (`search_code`).

OUTPUT FORMAT (JSON):
{{
  "overall_feedback": "Overall assessment (Excellent|Good|Needs Improvement|Major Issues)",
  "issues_found": [
    "Specific issue with file:line reference and severity (Critical/High/Medium/Low)",
    "Another specific issue with technical details"
  ],
  "suggested_improvements": [
    "Specific improvement suggestion with code example if applicable",
    "Another actionable improvement"
  ],
  "security_warnings": [
    "Specific security vulnerability with impact and fix",
    "Another security concern"
  ],
  "performance_concerns": [
    "Performance issue with optimization suggestion",
    "Another performance bottleneck"
  ],
  "maintainability_score": "1-10 with brief justification",
  "estimated_fix_time": "Time estimate for addressing issues"
}}

Be specific, technical, and actionable. Reference exact lines/files when possible. Prioritize critical issues.
"""

    review_agent = create_agent(llm, tools, system_prompt=review_system_prompt)

    # Integrator Agent - React Agent that can use tools for validation
    integrator_system_prompt = f"""
You are an Integration Validator Agent responsible for ensuring code quality, safety, and proper integration.

Tools Available:
{tools_list_text}

Your role:
1. Validate that generated code stays within the project directory boundaries
2. Check that all imports are properly linked and accessible
3. Detect syntax errors and logical issues in the code
4. Identify potential security vulnerabilities
5. Ensure code follows project conventions and best practices
6. Verify that file operations are safe and contained within the sandbox

Validation Checks:
- Directory Safety: Ensure no access to parent directories (..) or system paths (/etc, /home, etc.)
- Import Validation: Check that imported modules exist and are accessible
- Syntax Validation: Parse code for Python syntax errors
- Security Checks: Detect dangerous functions (eval, exec, subprocess, etc.)
- Path Safety: Validate file paths are within project boundaries
- Code Quality: Check for common anti-patterns and issues

Guidelines:
- Use available tools to validate file existence and accessibility
- Check import statements against project structure
- Parse code to detect syntax issues
- Flag potentially dangerous operations
- Provide specific recommendations for fixes

Output Format (JSON):
{{"validation_passed": true/false, "issues": ["critical issue 1", "critical issue 2"], "warnings": ["warning 1", "warning 2"], "recommendations": ["fix suggestion 1", "fix suggestion 2"], "security_concerns": ["security issue 1"], "import_issues": ["import problem 1"], "syntax_errors": ["syntax error 1"]}}

Be thorough in your validation and provide actionable feedback.
"""

    integrator_agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=integrator_system_prompt,
        store=memory_store
    )

    # Architect Agent - React Agent that can use tools
    architect_system_prompt = f"""
You are an Architect Agent responsible for providing project context and explicit file editing guidance.

Tools Available:
{tools_list_text}

Your role:
1. Analyze the project structure and understand the codebase architecture
2. Provide context about existing files, folders, and their relationships
3. Identify which specific files need to be edited for a given task
4. Recommend the exact file paths and explain why they need modification
5. Understand project patterns, conventions, and dependencies

Guidelines:
- Always use available tools to explore the project structure first
- Be explicit about which files to edit and why
- Provide context about how files relate to each other
- Identify potential impact of changes on other parts of the codebase
- Consider the project's architecture and design patterns
- Help other agents understand the project layout

Output Format (JSON):
{{"project_analysis": "brief analysis", "files_to_edit": [{{"file_path": "path", "reason": "why", "type": "create|modify|delete", "dependencies": ["files"]}}], "context": "additional context", "recommendations": ["recommendations"]}}

Always explore the project structure using available tools before making recommendations.
"""

    architect_agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=architect_system_prompt,
        store=memory_store
    )

    return planning_agent, code_gen_agent, review_agent, integrator_agent, architect_agent


async def create_agent_instances(model: str, session_id: str, api_keys: Optional[Dict[str, str]] = None):
    """Create agent instances with local tools for a given session."""
    # Set session context for local tools
    from .utils import get_project_folder
    try:
        project_folder = get_project_folder()
        set_session_context(session_id, project_folder)
    except Exception as e:
        logger.warning(f"Failed to set session context: {e}")
        # Use default project folder
        set_session_context(session_id, "/Users/Apple/Desktop/NextLovable")

    logger.info(f"Using local tools ({len(LOCAL_TOOLS)} tools)")

    # Get the appropriate LLM for the model
    llm = get_model_provider(model, api_keys)

    # Get the global memory store for agent persistence
    memory_store = get_memory_store()

    # Create traditional agents with local tools
    planning_agent, code_gen_agent, review_agent, integrator_agent, architect_agent = create_agents_with_tools(llm, LOCAL_TOOLS, memory_store)

    # Create Copilot-style agent graph for React/Vue development
    try:
        copilot_agent_graph = create_copilot_style_agent_graph(model, api_keys)
        logger.info("✅ Copilot-style agent graph created successfully")
    except Exception as e:
        logger.error(f"Failed to create Copilot-style agent graph: {e}")
        copilot_agent_graph = None

    return {
        'planning_agent': planning_agent,
        'code_gen_agent': code_gen_agent,
        'review_agent': review_agent,
        'integrator_agent': integrator_agent,
        'architect_agent': architect_agent,
        'copilot_agent_graph': copilot_agent_graph,
        'local_tools': LOCAL_TOOLS,
        'memory_store': memory_store
    }


async def create_agent_nodes_with_instances(agent_instances, websocket=None):
    """Create agent node wrappers with the configured agent instances."""
    planning_agent = AgentNode("planning", agent_instances['planning_agent'], websocket)
    code_gen_agent = AgentNode("code_generation", agent_instances['code_gen_agent'], websocket)
    review_agent = AgentNode("review", agent_instances['review_agent'], websocket)
    integrator_agent = AgentNode("integrator", agent_instances['integrator_agent'], websocket)
    architect_agent = AgentNode("architect", agent_instances['architect_agent'], websocket)

    # Create Copilot agent node if available
    copilot_agent = None
    if agent_instances.get('copilot_agent_graph'):
        copilot_agent = AgentNode("copilot", agent_instances['copilot_agent_graph'], websocket)

    nodes = [planning_agent, code_gen_agent, review_agent, integrator_agent, architect_agent]
    if copilot_agent:
        nodes.append(copilot_agent)

    return nodes


class AgentNode:
    """Wrapper for agent executors to provide the expected interface."""
    
    def __init__(self, name: str, agent_executor, websocket=None):
        self.name = name
        self.agent_executor = agent_executor
        self.websocket = websocket
    
    async def _safe_websocket_send(self, message: dict):
        """Safely send a WebSocket message with error handling."""
        if self.websocket:
            try:
                await self.websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                # Continue execution even if WebSocket fails
    
    async def process(self, state):
        """Process the state using the compiled agent graph."""
        try:
            # Extract user_id from session_id (assuming format: user_session or similar)
            user_id = state.session_id.split('_')[0] if '_' in state.session_id else state.session_id
            
            # Set session context for tools
            project_folder = getattr(state, 'project_folder', None)
            if not project_folder:
                # Fallback to get project folder from session context
                try:
                    from .utils import get_project_folder
                    project_folder = get_project_folder()
                except Exception:
                    project_folder = "/Users/Apple/Desktop/NextLovable"
            set_session_context(state.session_id, project_folder)
            
            # Emit real-time event for starting this agent
            await self._safe_websocket_send({
                "type": "progress",
                "data": {"step": self.name, "status": "started", "message": f"Starting {self.name}..."},
                "session_id": state.session_id
            })
            
            if self.name == "planning":
                # Emit planning started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "planning", "status": "analyzing", "message": "Analyzing user request and creating plan..."},
                    "session_id": state.session_id
                })
                
                # Retrieve user profile for personalized planning
                user_profile = {}
                try:
                    user_profile = await get_user_profile(user_id)
                except Exception as e:
                    logger.warning(f"Failed to retrieve user profile for planning: {e}")
                    user_profile = {}
                
                profile_context = ""
                if user_profile:
                    profile_context = f"""
USER PROFILE INFORMATION (use this to personalize your response):
{json.dumps(user_profile, indent=2)}

INSTRUCTIONS: Consider the user's preferences, past experiences, and profile information when creating the development plan. Adapt your approach based on their background and needs.
"""
                
                # Planning agent - analyze request and create plan
                input_text = f"""
                User Request: {state.user_request}
                {profile_context}
                
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please analyze this request and create a structured development plan.
                """
                
                # Emit planning execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "planning", "status": "executing", "message": "Generating development plan..."},
                    "session_id": state.session_id
                })
                
                # Execute with rate limiting and caching
                async def plan_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=input_text)]})
                    messages = result.get("messages", [])
                    return messages[-1].content if messages else ""
                
                output = await plan_request()
                
                # Handle different output types
                try:
                    # Check if output is already a string
                    if isinstance(output, str):
                        # Try to parse as JSON first
                        try:
                            plan_data = json.loads(output)
                            state.current_plan = plan_data
                        except json.JSONDecodeError:
                            # If not JSON, treat as text plan
                            state.current_plan = [output]
                    elif isinstance(output, (list, dict)):
                        # If output is already a structured object, use it directly
                        state.current_plan = output
                    else:
                        # Convert other types to string and wrap in list
                        state.current_plan = [str(output)]
                    
                    # Store this planning experience
                    try:
                        await store_agent_experience(user_id, {
                            "action": "planning",
                            "request": state.user_request,
                            "plan": state.current_plan,
                            "complexity": state.current_plan.get("complexity", "unknown") if isinstance(state.current_plan, dict) else "unknown"
                        }, state.session_id)
                    except Exception as e:
                        logger.warning(f"Failed to store planning experience: {e}")
                    
                except Exception as e:
                    logger.error(f"Error processing planning output: {e}")
                    # Fallback to text plan
                    state.current_plan = [str(output) if output else "Planning failed"]
                
                state.progress_updates.append({
                    "step": "planning",
                    "status": "completed",
                    "message": "Planning completed"
                })
                
            elif self.name == "code_generation":
                # Emit code generation started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "code_generation", "status": "preparing", "message": "Preparing code generation..."},
                    "session_id": state.session_id
                })
                
                # Retrieve relevant past experiences for code generation
                past_experiences = []
                try:
                    past_experiences = await search_user_memories(user_id, state.user_request, "experiences", limit=2)
                except Exception as e:
                    logger.warning(f"Failed to retrieve past experiences for code generation: {e}")
                    past_experiences = []
                
                experience_context = ""
                if past_experiences:
                    experience_context = f"""
PAST SIMILAR REQUESTS (learn from these implementations):
{chr(10).join([f"- {exp['value'].get('user_request', '')[:100]}...: {exp['value'].get('outcome', '')}" for exp in past_experiences])}

INSTRUCTIONS: Use these past experiences to inform your code generation approach and avoid previous mistakes.
"""
                
                # Check if this is a regeneration based on review feedback
                regeneration_context = ""
                if getattr(state, 'needs_regeneration', False) and hasattr(state, 'review_feedback') and state.review_feedback:
                    regeneration_context = f"""
PREVIOUS CODE REVIEW FEEDBACK (IMPROVE BASED ON THIS):
{json.dumps(state.review_feedback, indent=2)}

INSTRUCTIONS: The previous code had issues. Please regenerate the code addressing all the issues found, suggested improvements, and security warnings mentioned in the review feedback above.
"""
                
                # Code generation agent - generate code based on plan
                input_text = f"""
                User Request: {state.user_request}
                Current Plan: {state.current_plan}
                {experience_context}
                {regeneration_context}
                
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please generate the requested code based on the plan above.
                """
                
                 
                # Emit code generation execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "code_generation", "status": "generating", "message": "Regenerating code based on review feedback..." if getattr(state, 'needs_regeneration', False) else "Generating code..."},
                    "session_id": state.session_id
                })
                
                # Use the actual agent with tools for code generation
                async def generate_code_stream(**kwargs):
                    import os
                    from pathlib import Path
                    
                    try:
                        # Get sandbox directory path
                        sandbox_dir = Path(state.project_folder) / "sandboxes" / f"sandbox_{state.session_id}"
                        sandbox_dir.mkdir(exist_ok=True)
                        
                        # Take snapshot of existing files before agent execution
                        existing_files = {}
                        if sandbox_dir.exists():
                            for file_path in sandbox_dir.rglob("*"):
                                if file_path.is_file():
                                    try:
                                        existing_files[str(file_path.relative_to(sandbox_dir))] = file_path.stat().st_mtime
                                    except:
                                        pass
                        
                        # Use the agent executor with tools
                        result = await self.agent_executor.ainvoke({
                            "messages": [HumanMessage(content=input_text)]
                        })
                        
                        # Check which files were created or modified
                        generated_files = {}
                        if sandbox_dir.exists():
                            for file_path in sandbox_dir.rglob("*"):
                                if file_path.is_file():
                                    rel_path = str(file_path.relative_to(sandbox_dir))
                                    try:
                                        current_mtime = file_path.stat().st_mtime
                                        # Check if file is new or was modified
                                        if rel_path not in existing_files or current_mtime > existing_files[rel_path]:
                                            content = file_path.read_text(encoding='utf-8', errors='replace')
                                            if content.strip():  # Only include non-empty files
                                                generated_files[rel_path] = content
                                    except Exception as e:
                                        logger.warning(f"Error reading generated file {file_path}: {e}")
                        
                        # Combine all generated code
                        if generated_files:
                            generated_code_parts = []
                            for file_path, content in generated_files.items():
                                generated_code_parts.append(f"// File: {file_path}\n{content}")
                            generated_code = "\n\n".join(generated_code_parts)
                        else:
                            # Fallback to LLM response if no files were generated
                            if isinstance(result, dict):
                                if "messages" in result and result["messages"]:
                                    last_message = result["messages"][-1]
                                    if hasattr(last_message, 'content'):
                                        generated_code = last_message.content
                                    else:
                                        generated_code = str(last_message)
                                else:
                                    generated_code = str(result)
                            else:
                                generated_code = str(result)
                        
                        # Emit the final code via WebSocket
                        await self._safe_websocket_send({
                            "type": "code_stream",
                            "data": {
                                "partial_code": generated_code,
                                "step": "code_generation",
                                "status": "completed",
                                "generated_files": list(generated_files.keys()) if generated_files else []
                            },
                            "session_id": state.session_id
                        })
                        
                        return generated_code
                        
                    except Exception as e:
                        logger.error(f"Agent execution error: {e}")
                        # Fallback to basic LLM without tools if agent fails
                        try:
                            fallback_llm = get_model_provider(state.model, state.api_keys, streaming=False)
                            result = await fallback_llm.ainvoke([HumanMessage(content=input_text)])
                            return result.content if hasattr(result, 'content') else str(result)
                        except Exception as fallback_error:
                            logger.error(f"Fallback LLM error: {fallback_error}")
                            return f"Error generating code: {str(e)}"
                
                state.generated_code = await generate_code_stream()
                
                # Reset regeneration flag after successful regeneration
                if getattr(state, 'needs_regeneration', False):
                    state.needs_regeneration = False
                    # Update progress to indicate this was a regeneration
                    state.progress_updates.append({
                        "step": "code_generation",
                        "status": "regenerated",
                        "message": "Code regenerated based on review feedback"
                    })
                
                # Store this code generation experience
                try:
                    await store_agent_experience(user_id, {
                        "action": "code_generation",
                        "request": state.user_request,
                        "plan": state.current_plan,
                        "code_length": len(state.generated_code)
                    }, state.session_id)
                except Exception as e:
                    logger.warning(f"Failed to store code generation experience: {e}")
                
                state.progress_updates.append({
                    "step": "code_generation",
                    "status": "completed",
                    "message": "Code generation completed"
                })
                
            elif self.name == "review":
                # Emit review started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "review", "status": "analyzing", "message": "Analyzing generated code for review..."},
                    "session_id": state.session_id
                })
                
                # Retrieve user preferences for code review style
                user_profile = {}
                try:
                    user_profile = await get_user_profile(user_id)
                except Exception as e:
                    logger.warning(f"Failed to retrieve user profile for review: {e}")
                    user_profile = {}
                
                review_preferences = user_profile.get("code_review_preferences", "standard")
                
                # Retrieve past code review experiences
                past_reviews = []
                try:
                    past_reviews = await search_user_memories(user_id, state.generated_code[:100], "experiences", limit=3)
                except Exception as e:
                    logger.warning(f"Failed to retrieve past reviews: {e}")
                    past_reviews = []
                
                review_context = ""
                if past_reviews:
                    review_context = f"""
PAST REVIEW PATTERNS (learn from these):
{chr(10).join([f"- {rev['value'].get('feedback_type', 'General')}: {rev['value'].get('summary', '')}" for rev in past_reviews])}

INSTRUCTIONS: Use these past patterns to inform your review style and focus areas.
"""
                
                # Review agent - review the generated code
                input_text = f"""
                Generated Code: {state.generated_code}
                Original Request: {state.user_request}
                Plan: {state.current_plan}
                
                USER REVIEW PREFERENCES: {review_preferences}
                {review_context}
                
                Please review this code for quality, security, and best practices.
                """
                
                # Check if there's actually code to review
                if not state.generated_code or not state.generated_code.strip():
                    # No code was generated, provide appropriate feedback
                    state.review_feedback = {
                        "overall_feedback": "No code was generated for review. The request may have been for analysis, planning, or a different type of task rather than code generation.",
                        "issues_found": [],
                        "suggested_improvements": [],
                        "security_warnings": []
                    }
                    
                    state.progress_updates.append({
                        "step": "review",
                        "status": "completed",
                        "message": "Review completed - no code to review"
                    })
                else:
                    # There is code to review, proceed with normal review process
                    # Apply token limit for Groq models to prevent 413 errors (reduced for review)
                    prepared_input = prepare_agent_input(input_text, max_input_tokens=1000)
                    
                    # Emit review execution event
                    await self._safe_websocket_send({
                        "type": "progress",
                        "data": {"step": "review", "status": "reviewing", "message": "Reviewing code for quality and best practices..."},
                        "session_id": state.session_id
                    })
                    
                    # Execute with rate limiting and caching
                    async def review_code(**kwargs):
                        result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=input_text)]})
                        messages = result.get("messages", [])
                        return messages[-1].content if messages else ""
                    
                    # Handle different review output types
                    try:
                        review_output = await review_code()
                        
                        # Check if output is already a string
                        if isinstance(review_output, str):
                            # Try to parse as JSON first
                            try:
                                state.review_feedback = json.loads(review_output)
                            except json.JSONDecodeError:
                                # If not JSON, create structured feedback from text
                                state.review_feedback = {
                                    "overall_feedback": review_output,
                                    "issues_found": [],
                                    "suggested_improvements": [],
                                    "security_warnings": []
                                }
                        elif isinstance(review_output, dict):
                            # If output is already a structured object, use it directly
                            state.review_feedback = review_output
                        else:
                            # Convert other types to structured feedback
                            state.review_feedback = {
                                "overall_feedback": str(review_output) if review_output else "Review failed",
                                "issues_found": [],
                                "suggested_improvements": [],
                                "security_warnings": []
                            }
                    except Exception as e:
                        logger.error(f"Error processing review output: {e}")
                        # Fallback to structured feedback
                        state.review_feedback = {
                            "overall_feedback": "Review failed",
                            "issues_found": [],
                            "suggested_improvements": [],
                            "security_warnings": []
                        }
                
                # Check if re-generation is needed based on review feedback
                needs_regeneration = False
                critical_issues = 0
                high_priority_issues = 0

                if isinstance(state.review_feedback, dict):
                    issues_count = len(state.review_feedback.get("issues_found", []))
                    security_warnings = len(state.review_feedback.get("security_warnings", []))
                    performance_concerns = len(state.review_feedback.get("performance_concerns", []))

                    # Count critical/high priority issues
                    for issue in state.review_feedback.get("issues_found", []):
                        issue_str = str(issue).lower()
                        if any(word in issue_str for word in ['critical', 'error', 'broken', 'fails', 'crash']):
                            critical_issues += 1
                        elif any(word in issue_str for word in ['high', 'major', 'significant', 'important']):
                            high_priority_issues += 1

                    overall_feedback = state.review_feedback.get("overall_feedback", "").lower()
                    maintainability_score = state.review_feedback.get("maintainability_score", "")

                    # Extract numeric score if present
                    score_match = None
                    if maintainability_score:
                        import re
                        score_match = re.search(r'(\d+)/10|(\d+) out of 10|score:?\s*(\d+)', maintainability_score.lower())
                        if score_match:
                            score = int(score_match.group(1) or score_match.group(2) or score_match.group(3))
                        else:
                            # Try to extract just the first number
                            score_match = re.search(r'(\d+)', maintainability_score)
                            score = int(score_match.group(1)) if score_match else 5

                    # Trigger re-generation if ANY of these conditions are met:
                    needs_regeneration = (
                        critical_issues > 0 or  # Any critical issues
                        security_warnings > 0 or  # Any security warnings
                        (issues_count + high_priority_issues) > 2 or  # Many issues overall
                        'major' in overall_feedback or 'significant' in overall_feedback or
                        'needs improvement' in overall_feedback or 'poor' in overall_feedback or
                        (score_match and score < 6) or  # Low maintainability score
                        performance_concerns > 1  # Multiple performance issues
                    )
                
                # Set flag for potential re-generation
                state.needs_regeneration = needs_regeneration
                
                # Store this review experience
                try:
                    await store_agent_experience(user_id, {
                        "action": "code_review",
                        "code_length": len(state.generated_code),
                        "feedback_type": "quality_review",
                        "preferences_used": review_preferences,
                        "regeneration_triggered": needs_regeneration
                    }, state.session_id)
                except Exception as e:
                    logger.warning(f"Failed to store review experience: {e}")
                
                state.progress_updates.append({
                    "step": "review",
                    "status": "completed",
                    "message": f"Code review completed{' - Re-generation recommended due to quality issues' if needs_regeneration else ''}"
                })
                
            elif self.name == "code_completion":
                # Emit code completion started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "code_completion", "status": "generating", "message": "Generating code completion..."},
                    "session_id": state.session_id
                })
                
                # Code completion agent - generate code based on context
                input_text = f"""
                User Request: {state.user_request}
                Current Plan: {state.current_plan}
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please provide code completion or generation based on the request and context.
                """
                
                # Apply token limit for Groq models
                prepared_input = prepare_agent_input(input_text, max_input_tokens=1500)
                
                # Execute code completion
                async def complete_code_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=input_text)]})
                    messages = result.get("messages", [])
                    return messages[-1].content if messages else ""
                
                completion_output = await complete_code_request()
                
                # Store the generated code
                if isinstance(completion_output, str) and completion_output.strip():
                    state.generated_code = completion_output.strip()
                else:
                    state.generated_code = str(completion_output) if completion_output else ""
                
                # Store this code completion experience
                try:
                    await store_agent_experience(user_id, {
                        "action": "code_completion",
                        "request": state.user_request,
                        "code_length": len(state.generated_code),
                        "context_used": bool(state.sandbox_context)
                    }, state.session_id)
                except Exception as e:
                    logger.warning(f"Failed to store code completion experience: {e}")
                
                state.progress_updates.append({
                    "step": "code_completion",
                    "status": "completed",
                    "message": "Code completion generated"
                })
                
            elif self.name == "context_analysis":
                # Emit context analysis started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "context_analysis", "status": "analyzing", "message": "Analyzing request context..."},
                    "session_id": state.session_id
                })
                
                # Context analysis agent - analyze the request and context
                input_text = f"""
                User Request: {state.user_request}
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please analyze the request and provide context for code generation.
                """
                
                # Apply token limit
                prepared_input = prepare_agent_input(input_text, max_input_tokens=1000)
                
                # Execute context analysis
                async def analyze_context_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=input_text)]})
                    messages = result.get("messages", [])
                    return messages[-1].content if messages else ""
                
                context_output = await analyze_context_request()
                
                # Store context analysis result (could be used by subsequent agents)
                state.context_analysis = context_output
                
                # Store this context analysis experience
                try:
                    await store_agent_experience(user_id, {
                        "action": "context_analysis",
                        "request": state.user_request,
                        "analysis_length": len(str(context_output))
                    }, state.session_id)
                except Exception as e:
                    logger.warning(f"Failed to store context analysis experience: {e}")
                
                state.progress_updates.append({
                    "step": "context_analysis",
                    "status": "completed",
                    "message": "Context analysis completed"
                })
                
            elif self.name == "refactoring":
                # Emit refactoring started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "refactoring", "status": "refactoring", "message": "Refactoring code..."},
                    "session_id": state.session_id
                })
                
                # Refactoring agent - improve/refactor the generated code
                input_text = f"""
                Generated Code: {state.generated_code}
                User Request: {state.user_request}
                Review Feedback: {state.review_feedback}
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please refactor and improve the generated code based on the review feedback.
                """
                
                # Apply token limit
                prepared_input = prepare_agent_input(input_text, max_input_tokens=1500)
                
                # Execute refactoring
                async def refactor_code_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=input_text)]})
                    messages = result.get("messages", [])
                    return messages[-1].content if messages else ""
                
                refactor_output = await refactor_code_request()
                
                # Update the generated code with refactored version
                if isinstance(refactor_output, str) and refactor_output.strip():
                    state.generated_code = refactor_output.strip()
                elif refactor_output:
                    state.generated_code = str(refactor_output)
                
                # Store this refactoring experience
                try:
                    await store_agent_experience(user_id, {
                        "action": "code_refactoring",
                        "original_code_length": len(state.generated_code),
                        "refactored": bool(refactor_output)
                    }, state.session_id)
                except Exception as e:
                    logger.warning(f"Failed to store refactoring experience: {e}")
                
                state.progress_updates.append({
                    "step": "refactoring",
                    "status": "completed",
                    "message": "Code refactoring completed"
                })
                
            elif self.name == "integrator":
                # Emit integration validation started event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "integration_validation", "status": "validating", "message": "Validating code integration and quality..."},
                    "session_id": state.session_id
                })
                
                # Integrator agent - validate code quality and integration
                input_text = f"""
                Generated Code: {state.generated_code}
                Original Request: {state.user_request}
                Plan: {state.current_plan}
                
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please validate the generated code for quality, safety, and proper integration within the project.
                """
                
                # Apply token limit for Groq models to prevent 413 errors (reduced for integration)
                prepared_input = prepare_agent_input(input_text, max_input_tokens=1000)
                
                # Emit integration validation execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "integration_validation", "status": "executing", "message": "Executing integration validation..."},
                    "session_id": state.session_id
                })
                
                # Execute with rate limiting and caching
                async def validate_integration_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=input_text)]})
                    messages = result.get("messages", [])
                    return messages[-1].content if messages else ""
                
                integration_validation_output = await validate_integration_request()
                
                # Handle different output types for integration validation
                try:
                    # Check if output is already a string
                    if isinstance(integration_validation_output, str):
                        # Try to parse as JSON first
                        try:
                            validation_results = json.loads(integration_validation_output)
                            state.validation_results = validation_results
                        except json.JSONDecodeError:
                            # If not JSON, treat as text validation result
                            state.validation_results = {"overall_feedback": integration_validation_output}
                    elif isinstance(integration_validation_output, (list, dict)):
                        # If output is already a structured object, use it directly
                        state.validation_results = integration_validation_output
                    else:
                        # Convert other types to string and wrap in dict
                        state.validation_results = {"overall_feedback": str(integration_validation_output)}
                    
                    # Store this integration validation experience
                    try:
                        await store_agent_experience(user_id, {
                            "action": "integration_validation",
                            "request": state.user_request,
                            "validation_results": state.validation_results,
                            "complexity": state.validation_results.get("complexity", "unknown") if isinstance(state.validation_results, dict) else "unknown"
                        }, state.session_id)
                    except Exception as e:
                        logger.warning(f"Failed to store integration validation experience: {e}")
                    
                except Exception as e:
                    logger.error(f"Error processing integration validation output: {e}")
                    # Fallback to text validation result
                    state.validation_results = {"overall_feedback": str(integration_validation_output) if integration_validation_output else "Integration validation failed"}
                
                state.progress_updates.append({
                    "step": "integration_validation",
                    "status": "completed",
                    "message": "Integration validation completed"
                })
                
        except Exception as e:
            # Log full traceback for debugging, including ExceptionGroup sub-exceptions if present
            logger.exception(f"Error in {self.name} agent")
            try:
                # If this is an ExceptionGroup (Python 3.11+), log each sub-exception
                if hasattr(e, 'exceptions') and isinstance(e.exceptions, (list, tuple)):
                    for i, sub in enumerate(e.exceptions):
                        logger.exception(f"Sub-exception {i} in ExceptionGroup for {self.name}: {sub}")
            except Exception:
                # Ignore any error while trying to log sub-exceptions
                pass

            state.progress_updates.append({
                "step": self.name,
                "status": "error",
                "message": f"Error: {str(e)}"
            })
        
        return state


class AgentGraph:
    """LangGraph-based agent graph with streaming support."""
    
    def __init__(self, agent_nodes):
        self.agent_nodes = agent_nodes
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """Build the StateGraph with nodes and edges."""
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes for each agent
        for node in self.agent_nodes:
            workflow.add_node(node.name, node.process)
        
        # Check if architect agent is available
        has_architect = any(node.name == "architect" for node in self.agent_nodes)
        has_integrator = any(node.name == "integrator" for node in self.agent_nodes)
        
        if has_architect:
            # Define the flow: architect -> planning -> code_generation -> review -> integrator -> END
            workflow.set_entry_point("architect")
            workflow.add_edge("architect", "planning")
            workflow.add_edge("planning", "code_generation")
            
            # Review -> Code Generation (if regeneration needed) or Integrator/END
            workflow.add_conditional_edges(
                "review",
                lambda state: "code_generation" if getattr(state, 'needs_regeneration', False) else ("integrator" if has_integrator else END)
            )
            
            if has_integrator:
                workflow.add_edge("integrator", END)
        else:
            # Fallback to original flow with iteration: planning -> code_generation -> review -> code_generation (if needed) -> integrator -> END
            workflow.set_entry_point("planning")
            workflow.add_edge("planning", "code_generation")
            
            # Review -> Code Generation (if regeneration needed) or Integrator/END
            workflow.add_conditional_edges(
                "review",
                lambda state: "code_generation" if getattr(state, 'needs_regeneration', False) else ("integrator" if has_integrator else END)
            )
            
            if has_integrator:
                workflow.add_edge("integrator", END)
        
        # Compile the graph
        return workflow.compile()
    
    async def execute(self, state):
        """Execute the agent graph on the given state."""
        # Use ainvoke for synchronous execution (events are emitted via websocket in node functions)
        return await self.graph.ainvoke(state)

 

async def execute_agent_graph(graph, test_data):
    """Execute the agent graph with test data."""
    # Create initial state
    state = AgentState(
        user_request=test_data["user_request"],
        session_id=test_data["session_id"],
        model=test_data.get("model", "groq/mixtral-8x7b-32768"),
        sandbox_context=test_data.get("sandbox_context", {}),
        sandbox_id=test_data.get("sandbox_id", "test-sandbox"),
        available_tools=test_data.get("available_tools", []),
        tool_results=test_data.get("tool_results", [])
    )
    
    # Execute the graph
    result_state = await graph.execute(state)
    
    # Convert back to dictionary format expected by test
    return {
        "generated_code": result_state.get("generated_code", ""),
        "review_feedback": result_state.get("review_feedback", ""),
        "progress_updates": result_state.get("progress_updates", []),
        "current_plan": result_state.get("current_plan", [])
    }

def create_code_completion_agent(llm, tools, memory_store=None):
    """Create a Copilot-style React/Vue code completion agent."""
    if memory_store is None:
        memory_store = get_memory_store()

    system_prompt = """
You are a React/Vue code completion assistant. Provide context-aware completions for JSX/TSX, Vue components, hooks, and modern frontend patterns. Use tools to explore codebase."""

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
        store=memory_store
    )

def create_context_aware_agent(llm, tools, memory_store=None):
    """Create a context-aware agent that understands React/Vue codebase patterns."""
    if memory_store is None:
        memory_store = get_memory_store()

    system_prompt = """
You are a React/Vue codebase assistant. Analyze component architecture, state management, routing, and API patterns. Use tools to understand frontend project structure."""

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
        store=memory_store
    )

def create_refactoring_agent(llm, tools, memory_store=None):
    """Create a React/Vue refactoring agent for frontend code improvements."""
    if memory_store is None:
        memory_store = get_memory_store()

    system_prompt = """
You are a React/Vue refactoring specialist. Convert class to functional components, extract hooks, optimize performance, and improve code maintainability.
- Provide clear explanations of changes
- Consider the impact on component performance
- Suggest modern patterns (hooks, Composition API)
"""

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
        store=memory_store
    )

def create_copilot_style_agent_graph(model: str = "groq-qwen/qwen3-32b", api_keys: Optional[Dict[str, str]] = None):
    """Create a Copilot-style agent graph with multiple specialized agents."""
    # Get LLM and tools
    llm = get_model_provider(model, api_keys)
    memory_store = get_memory_store()

    # Create specialized agents
    code_completion_agent = create_code_completion_agent(llm, LOCAL_TOOLS, memory_store)
    context_agent = create_context_aware_agent(llm, LOCAL_TOOLS, memory_store)
    refactoring_agent = create_refactoring_agent(llm, LOCAL_TOOLS, memory_store)
    planning_agent = create_agents_with_tools(llm, LOCAL_TOOLS, memory_store)[0]  # Get planning agent
    review_agent = create_agents_with_tools(llm, LOCAL_TOOLS, memory_store)[2]    # Get review agent

    # Create agent nodes
    completion_node = AgentNode("code_completion", code_completion_agent)
    context_node = AgentNode("context_analysis", context_agent)
    refactor_node = AgentNode("refactoring", refactoring_agent)
    planning_node = AgentNode("planning", planning_agent)
    review_node = AgentNode("review", review_agent)

    # Create workflow graph
    workflow = StateGraph(AgentState)

    # Add all nodes
    for node in [completion_node, context_node, refactor_node, planning_node, review_node]:
        workflow.add_node(node.name, node.process)

    # Define Copilot-style workflow
    workflow.set_entry_point("context_analysis")

    # Context analysis -> Planning/Code Completion based on request type
    workflow.add_conditional_edges(
        "context_analysis",
        lambda state: "planning" if len(state.user_request) > 200 or any(keyword in state.user_request.lower() for keyword in ["create", "build", "implement", "develop", "architecture", "system"]) else "code_completion"
    )

    # Planning -> Code Completion
    workflow.add_edge("planning", "code_completion")

    # Code Completion -> Review
    workflow.add_edge("code_completion", "review")

    # Review -> Refactoring (if needed) or End
    workflow.add_conditional_edges(
        "review",
        lambda state: "refactoring" if getattr(state, 'needs_refactoring', False) else END
    )

    # Refactoring -> Final Review -> End
    workflow.add_edge("refactoring", "review")

    return workflow.compile()


async def execute_agent_graph_with_websocket_streaming(agent_nodes, initial_data, session_id, websocket):
    """Execute agent nodes in sequence with WebSocket streaming support."""
    from app.agents.agent_graphs import AgentState
    
    logger.info(f"Starting WebSocket streaming execution for session: {session_id}")
    
    # Get the project folder for this session
    try:
        from app.agents.utils import get_project_folder
        project_folder = get_project_folder()
        logger.info(f"🏗️ Using project folder for streaming workflow: {project_folder}")
    except Exception as e:
        logger.warning(f"Failed to get project folder, using fallback: {e}")
        project_folder = "/Users/Apple/Desktop/NextLovable"
    
    # Create initial state
    state = AgentState(
        user_request=initial_data["user_request"],
        session_id=session_id,
        model=initial_data["model"],
        sandbox_context=initial_data["sandbox_context"],
        sandbox_id=initial_data.get("sandbox_id"),
        available_tools=initial_data.get("available_tools", []),
        tool_results=initial_data.get("tool_results", []),
        api_keys=initial_data.get("api_keys", {}),
        project_folder=project_folder
    )
    
    # Execute agents in sequence: planning -> code_generation -> review
    agent_sequence = ["planning", "code_generation", "review"]
    
    for agent_name in agent_sequence:
        # Find the agent node
        agent_node = next((node for node in agent_nodes if node.name == agent_name), None)
        if not agent_node:
            logger.warning(f"Agent {agent_name} not found in agent_nodes")
            continue
            
        logger.info(f"Executing agent: {agent_name}")
        
        try:
            # Execute the agent
            state = await agent_node.process(state)
            
            # Check if review found issues requiring regeneration
            if agent_name == "review" and getattr(state, 'needs_regeneration', False):
                logger.info("Review indicated regeneration needed, looping back to code_generation")
                # Reset the regeneration flag and run code_generation again
                state.needs_regeneration = False
                # Find and execute code_generation again
                code_gen_node = next((node for node in agent_nodes if node.name == "code_generation"), None)
                if code_gen_node:
                    state = await code_gen_node.process(state)
                    
        except Exception as e:
            logger.error(f"Error executing agent {agent_name}: {e}")
            # Continue with next agent despite errors
    
    # Return formatted result
    return {
        "generated_code": state.generated_code,
        "review_feedback": state.review_feedback,
        "plan": state.current_plan,
        "progress_updates": state.progress_updates,
        "session_id": session_id,
        "additional_data": {
            "workflow_type": "traditional_streaming",
            "validation_results": getattr(state, 'validation_results', {})
        }
    }