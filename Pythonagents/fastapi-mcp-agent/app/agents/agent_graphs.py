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
        elif line.startswith("Sandbox Context:") or line.startswith("Review Preferences:"):
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
        "metadata": max_input_tokens * 0.08,     # 8% for metadata
        "session": max_input_tokens * 0.02,      # 2% for session info
        "header": max_input_tokens * 0.1         # 10% for instructions
    }
    
    # Build optimized input
    optimized_parts = []
    
    for section_name in ["header", "user_request", "main_content", "context", "metadata", "session"]:
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
        else:
            logger.warning("ChromaDB not available, using InMemoryStore")
            _memory_store = InMemoryStore()
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
    system_prompt = """You are a Planning Agent responsible for breaking down user requests into actionable steps.

Your role:
1. Analyze the user's request thoroughly
2. Create a detailed, step-by-step plan
3. Identify required tools and resources
4. Consider potential challenges and dependencies
5. Provide clear, actionable tasks for the Code Generation Agent

Guidelines:
- Be specific and detailed in your planning
- Consider the available tools and their capabilities
- Break complex tasks into smaller, manageable steps
- Include error handling and validation steps
- Provide context and rationale for each step

Output your plan as a structured list of actionable steps."""

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
    system_prompt = """You are a Code Generation Agent responsible for implementing the plan created by the Planning Agent.

Your role:
1. Follow the detailed plan provided by the Planning Agent
2. Generate high-quality, working code
3. Use appropriate tools and libraries
4. Implement proper error handling and validation
5. Write clean, maintainable, and well-documented code
6. Test your implementations when possible

Guidelines:
- Follow coding best practices and conventions
- Write comprehensive comments and documentation
- Implement proper error handling
- Use the available tools effectively
- Ensure code is production-ready
- Validate your implementations

Focus on creating robust, efficient, and maintainable solutions."""

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
    system_prompt = """You are a Review Agent responsible for evaluating and improving the code generated by the Code Generation Agent.

Your role:
1. Review the generated code for quality, correctness, and best practices
2. Identify potential issues, bugs, or improvements
3. Suggest optimizations and enhancements
4. Verify that the implementation meets the original requirements
5. Provide constructive feedback and recommendations

Guidelines:
- Focus on code quality, security, and performance
- Check for proper error handling and edge cases
- Verify adherence to coding standards and best practices
- Suggest improvements for maintainability and readability
- Ensure the solution is complete and functional
- Provide specific, actionable feedback

Your goal is to ensure the final output is of the highest quality."""

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
    system_prompt = """You are an Integration Validator Agent responsible for ensuring code quality, safety, and proper integration.

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
    system_prompt = """You are an Architect Agent responsible for providing project context and explicit file editing guidance.

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
 
Always explore the project structure using available tools before making recommendations."""

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
    groq_key = (api_keys.get("groq") if api_keys else None) or os.getenv("GROQ_API_KEY")
    anthropic_key = (api_keys.get("anthropic") if api_keys else None) or os.getenv("ANTHROPIC_API_KEY")
    google_key = (api_keys.get("gemini") if api_keys else None) or os.getenv("GOOGLE_API_KEY")
    openai_key = (api_keys.get("openai") if api_keys else None) or os.getenv("OPENAI_API_KEY")
    openrouter_key = (api_keys.get("openrouter") if api_keys else None) or os.getenv("OPENROUTER_API_KEY")
    
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
            max_tokens=4096,
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
            max_tokens=4096,
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
            max_tokens=4096,
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
            max_tokens=4096,
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
            max_tokens=4096,
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
        
        logger.info(f"Created ReAct agent with {len(tools)} tools: {[getattr(tool, 'name', str(tool)) for tool in tools]}")
        
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
You are a senior architect. Analyze user requests and create development plans.

Environment: Sandbox with existing files — you MAY and SHOULD use the available tools to explore and modify the project.

Tools Available:
{tools_list_text}

When you need to inspect or change files, CALL the appropriate tool by name (do not output shell scripts or pseudo-commands). For example, use `read_file`, `list_dir`, or `write_file` where appropriate.

IMPORTANT: Output your response as plain JSON text (not a tool call). Format:
{{"intent": "brief description", "steps": ["step 1", "step 2"], "tools_needed": ["tool1", "tool2"], "complexity": "simple|moderate|complex"}}
"""

    planning_agent = create_agent(llm, tools, system_prompt=planning_system_prompt)

    # Code Generation Agent
    code_gen_system_prompt = f"""
You are a senior AI developer. Turn plans into high-quality code.

Tools Available:
{tools_list_text}

Rules: Use the listed tools to explore the codebase and modify files. When you need to read files, call `read_file`; to list directories, call `list_dir`; to create/update files, call `write_file`. Do NOT output shell scripts or human-facing instructions for manual edits — perform edits via tools.

Output: Return the final code or, when making file changes, perform the change via the appropriate tool and then output the path(s) modified and a brief summary.
"""

    code_gen_agent = create_agent(llm, tools, system_prompt=code_gen_system_prompt)

    # Review Agent
    review_system_prompt = f"""
You are a code review expert. Review code for quality, security, and best practices.

Tools Available:
{tools_list_text}

When reviewing, you MAY call tools to inspect files (e.g. `read_file`) or search code (`search_code`).

IMPORTANT: Output your response as plain JSON text, not as a tool call. Format:
{{"overall_feedback": "summary", "issues_found": ["issue1", "issue2"], "suggested_improvements": ["improvement1"], "security_warnings": ["warning1"]}}
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
        copilot_agent_graph = create_copilot_style_agent_graph(api_keys)
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
                    profile_context = f"\nUser Profile: {user_profile}"
                
                # Planning agent - analyze request and create plan
                input_text = f"""
                User Request: {state.user_request}
                {profile_context}
                
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please analyze this request and create a structured development plan.
                """
                
                # Apply token limit for Groq models to prevent 413 errors
                prepared_input = prepare_agent_input(input_text, max_input_tokens=2000)
                
                # Emit planning execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "planning", "status": "executing", "message": "Generating development plan..."},
                    "session_id": state.session_id
                })
                
                # Execute with rate limiting and caching
                async def plan_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=prepared_input)]})
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
                    experience_context = f"\nPast Experiences: {[exp['value'].get('action', '') for exp in past_experiences]}"
                
                # Code generation agent - generate code based on plan
                input_text = f"""
                User Request: {state.user_request}
                Current Plan: {state.current_plan}
                {experience_context}
                
                Sandbox Context: {state.sandbox_context}
                Session ID: {state.session_id}
                
                Please generate the requested code based on the plan above.
                """
                
                # Apply token limit for Groq models to prevent 413 errors
                prepared_input = prepare_agent_input(input_text, max_input_tokens=2000)
                
                # Emit code generation execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "code_generation", "status": "generating", "message": "Generating code..."},
                    "session_id": state.session_id
                })
                
                # Use the actual agent with tools for code generation
                async def generate_code_stream(**kwargs):
                    try:
                        # Use the agent executor with tools
                        result = await self.agent_executor.ainvoke({
                            "messages": [HumanMessage(content=prepared_input)]
                        })
                        
                        # Extract the generated code from the agent result
                        if isinstance(result, dict):
                            if "messages" in result and result["messages"]:
                                # Get the last message content
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
                                "status": "completed"
                            },
                            "session_id": state.session_id
                        })
                        
                        return generated_code
                        
                    except Exception as e:
                        logger.error(f"Agent execution error: {e}")
                        # Fallback to basic LLM without tools if agent fails
                        try:
                            fallback_llm = get_model_provider(state.model, state.api_keys, streaming=False)
                            result = await fallback_llm.ainvoke([HumanMessage(content=prepared_input)])
                            return result.content if hasattr(result, 'content') else str(result)
                        except Exception as fallback_error:
                            logger.error(f"Fallback LLM error: {fallback_error}")
                            return f"Error generating code: {str(e)}"
                
                state.generated_code = await generate_code_stream()
                
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
                    review_context = f"\nPast Review Patterns: {[rev['value'].get('feedback_type', '') for rev in past_reviews]}"
                
                # Review agent - review the generated code
                input_text = f"""
                Generated Code: {state.generated_code}
                Original Request: {state.user_request}
                Plan: {state.current_plan}
                
                Review Preferences: {review_preferences}
                {review_context}
                
                Please review this code for quality, security, and best practices.
                """
                
                # Apply token limit for Groq models to prevent 413 errors
                prepared_input = prepare_agent_input(input_text, max_input_tokens=2000)
                
                # Emit review execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "review", "status": "reviewing", "message": "Reviewing code for quality and best practices..."},
                    "session_id": state.session_id
                })
                
                # Execute with rate limiting and caching
                async def review_code(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=prepared_input)]})
                    messages = result.get("messages", [])
                    return messages[-1].content if messages else ""
                
                review_output = await review_code()
                
                # Handle different review output types
                try:
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
                        "overall_feedback": str(review_output) if review_output else "Review failed",
                        "issues_found": [],
                        "suggested_improvements": [],
                        "security_warnings": []
                    }
                
                # Store this review experience
                try:
                    await store_agent_experience(user_id, {
                        "action": "code_review",
                        "code_length": len(state.generated_code),
                        "feedback_type": "quality_review",
                        "preferences_used": review_preferences
                    }, state.session_id)
                except Exception as e:
                    logger.warning(f"Failed to store review experience: {e}")
                
                state.progress_updates.append({
                    "step": "review",
                    "status": "completed",
                    "message": "Code review completed"
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
                
                # Apply token limit for Groq models to prevent 413 errors
                prepared_input = prepare_agent_input(input_text, max_input_tokens=2000)
                
                # Emit integration validation execution event
                await self._safe_websocket_send({
                    "type": "progress",
                    "data": {"step": "integration_validation", "status": "executing", "message": "Executing integration validation..."},
                    "session_id": state.session_id
                })
                
                # Execute with rate limiting and caching
                async def validate_integration_request(**kwargs):
                    result = await self.agent_executor.ainvoke({"messages": [HumanMessage(content=prepared_input)]})
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
            workflow.add_edge("code_generation", "review")
            if has_integrator:
                workflow.add_edge("review", "integrator")
                workflow.add_edge("integrator", END)
            else:
                workflow.add_edge("review", END)
        else:
            # Fallback to original flow: planning -> code_generation -> review -> integrator -> END
            workflow.set_entry_point("planning")
            workflow.add_edge("planning", "code_generation")
            workflow.add_edge("code_generation", "review")
            if has_integrator:
                workflow.add_edge("review", "integrator")
                workflow.add_edge("integrator", END)
            else:
                workflow.add_edge("review", END)
        
        # Compile the graph
        return workflow.compile()
    
    async def execute(self, state):
        """Execute the agent graph on the given state."""
        # Use ainvoke for synchronous execution (events are emitted via websocket in node functions)
        return await self.graph.ainvoke(state)


def create_agent_graph(api_keys: Optional[Dict[str, str]] = None):
    """Create an agent graph with default configuration."""
    # For testing, create a simple graph without MCP tools and without real LLM calls
    import asyncio
    from unittest.mock import MagicMock, AsyncMock
    
    # Create mock agents that return predictable results
    mock_planning_agent = MagicMock()
    mock_planning_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content='{"intent": "Create fibonacci function", "steps": ["Write function"], "tools_needed": [], "complexity": "simple"}')]})
    
    mock_code_gen_agent = MagicMock()
    mock_code_gen_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)")]})
    
    mock_review_agent = MagicMock()
    mock_review_agent.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content='{"overall_feedback": "Good code", "issues_found": [], "suggested_improvements": [], "security_warnings": []}')]})
    
    # Create agent nodes
    planning_node = AgentNode("planning", mock_planning_agent)
    code_gen_node = AgentNode("code_generation", mock_code_gen_agent)
    review_node = AgentNode("review", mock_review_agent)
    
    return AgentGraph([planning_node, code_gen_node, review_node])


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
You are an intelligent React/Vue code completion assistant, similar to GitHub Copilot for frontend development.

Your role is to provide context-aware code suggestions, completions, and improvements for React and Vue.js applications.

Key capabilities:
1. Complete React component code (JSX/TSX)
2. Suggest Vue component implementations
3. Add missing imports for React/Vue libraries
4. Complete hook usage patterns (useState, useEffect, etc.)
5. Suggest component prop interfaces
6. Complete event handlers and state management
7. Provide styling suggestions (CSS modules, styled-components)

Guidelines:
- Analyze React/Vue components and their context
- Use available tools to explore the frontend codebase
- Provide completions that match React/Vue best practices
- Suggest TypeScript interfaces when appropriate
- Complete JSX/TSX syntax properly
- Suggest modern React hooks over class components

Output format for completions:
- Provide the completed React/Vue code
- Include brief explanation of the completion
- Suggest any additional imports needed
- Note if TypeScript types should be added
"""

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
You are a React/Vue codebase-aware development assistant that understands frontend project structure and patterns.

Your capabilities:
1. Analyze React/Vue component architecture and relationships
2. Understand state management patterns (Redux, Zustand, Pinia, Vuex)
3. Identify component hierarchies and data flow
4. Recognize styling approaches (CSS modules, styled-components, Tailwind)
5. Understand routing patterns (React Router, Vue Router)
6. Analyze API integration patterns and data fetching
7. Identify code organization patterns (pages, components, hooks, utils)

Tools to use:
- analyze_react_component: Examine React component structure
- analyze_vue_component: Examine Vue component structure
- read_file: Examine specific component files
- list_dir: Understand project structure
- grep_search: Find patterns across frontend codebase
- semantic_search_codebase: Find similar components
- get_project_structure: Understand overall architecture

Always explore the React/Vue codebase context before making suggestions.
Focus on modern React (hooks) and Vue 3 (Composition API) patterns.
"""

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
You are a React/Vue refactoring specialist that improves frontend code quality and maintainability.

Your tasks:
1. Convert class components to functional components with hooks
2. Migrate Vue 2 Options API to Composition API
3. Extract custom hooks from component logic
4. Optimize re-renders with React.memo and useMemo
5. Improve component composition and reusability
6. Refactor inline styles to CSS modules or styled-components
7. Optimize bundle size by code splitting and lazy loading

Refactoring types:
- Convert class components to functional + hooks
- Extract custom hooks (useAuth, useApi, useForm)
- Memoize expensive computations
- Split large components into smaller ones
- Improve TypeScript usage and type safety
- Optimize conditional rendering patterns
- Add proper error boundaries

React-specific optimizations:
- useCallback for event handlers
- useMemo for expensive calculations
- React.lazy for code splitting
- Proper dependency arrays in useEffect

Vue-specific optimizations:
- Composition API migration
- Computed properties optimization
- Watcher optimization
- Component performance improvements

Always:
- Test your changes don't break functionality
- Follow React/Vue best practices
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

def create_copilot_style_agent_graph(api_keys: Optional[Dict[str, str]] = None):
    """Create a Copilot-style agent graph with multiple specialized agents."""
    # Get LLM and tools
    llm = get_model_provider("groq-qwen/qwen3-32b", api_keys)
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
        lambda state: "planning" if state.get("complexity", "simple") == "complex" else "code_completion"
    )

    # Planning -> Code Completion
    workflow.add_edge("planning", "code_completion")

    # Code Completion -> Review
    workflow.add_edge("code_completion", "review")

    # Review -> Refactoring (if needed) or End
    workflow.add_conditional_edges(
        "review",
        lambda state: "refactoring" if state.get("needs_refactoring", False) else END
    )

    # Refactoring -> Final Review -> End
    workflow.add_edge("refactoring", "review")

    return workflow.compile()