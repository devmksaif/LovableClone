import logging
import os
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import asyncio
from datetime import datetime
from app.agents.agent_graphs import create_agent_instances, create_agent_nodes_with_instances
from app.database import get_or_create_session, add_conversation
from app.agents.mcp_integration import process_chat_request
from app.websocket_utils import register_chat_connection, unregister_chat_connection
from app.cache.redis_cache import redis_cache
from app.utils.rate_limiter import RateLimiter
from app.tasks.llm_tasks import process_queued_requests

# ChromaDB integration import
try:
    from app.services.chroma_integration import chroma_integration
    CHROMA_INTEGRATION_AVAILABLE = True
except ImportError:
    CHROMA_INTEGRATION_AVAILABLE = False
 
logger = logging.getLogger(__name__)

def _is_react_vue_request(user_request: str, sandbox_context: Dict[str, Any]) -> bool:
    """Detect if the request is for React/Vue development."""
    # Check user request for React/Vue keywords
    react_vue_keywords = [
        'react', 'vue', 'jsx', 'tsx', 'component', 'hook', 'state', 'props',
        'useState', 'useEffect', 'useContext', 'createApp', 'defineComponent',
        'frontend', 'ui', 'user interface', 'component library'
    ]
    
    user_request_lower = user_request.lower()
    has_react_vue_keywords = any(keyword in user_request_lower for keyword in react_vue_keywords)
    
    # Check sandbox context for React/Vue files
    has_react_vue_files = False
    if sandbox_context and 'files' in sandbox_context:
        files = sandbox_context['files']
        react_vue_extensions = ['.jsx', '.tsx', '.vue', '.js', '.ts']
        has_react_vue_files = any(
            any(file.get('name', '').endswith(ext) for ext in react_vue_extensions)
            for file in files
        )
    
    return has_react_vue_keywords or has_react_vue_files

async def _execute_copilot_workflow(copilot_graph, initial_data: Dict[str, Any], session_id: str, websocket):
    """Execute the Copilot-style agent graph workflow."""
    from app.agents.agent_graphs import AgentState
    
    logger.info(f"🎯 Executing Copilot workflow for session: {session_id}")
    
    # Create initial state
    state = AgentState(
        user_request=initial_data["user_request"],
        session_id=session_id,
        model=initial_data["model"],
        sandbox_context=initial_data["sandbox_context"],
        sandbox_id=initial_data.get("sandbox_id"),
        available_tools=initial_data.get("available_tools", []),
        tool_results=initial_data.get("tool_results", []),
        api_keys=initial_data.get("api_keys", {})
    )
    
    # Send initial progress update
    await safe_websocket_send(websocket, {
        "type": "progress",
        "data": {"step": "copilot_analysis", "status": "starting", "message": "Starting Copilot-style analysis..."},
        "session_id": session_id
    })
    
    try:
        # Execute the Copilot graph
        final_state = await copilot_graph.ainvoke(state)
        
        # Send completion update
        await safe_websocket_send(websocket, {
            "type": "progress",
            "data": {"step": "copilot_complete", "status": "completed", "message": "Copilot analysis completed"},
            "session_id": session_id
        })
        
        # Return formatted result
        return {
            "generated_code": final_state.get("generated_code", ""),
            "review_feedback": final_state.get("review_feedback", {}),
            "plan": final_state.get("current_plan", []),
            "progress_updates": final_state.get("progress_updates", []),
            "session_id": session_id,
            "additional_data": {
                "workflow_type": "copilot",
                "validation_results": final_state.get("validation_results", {})
            }
        }
        
    except Exception as e:
        logger.error(f"Error executing Copilot workflow: {e}")
        await safe_websocket_send(websocket, {
            "type": "error",
            "data": {"message": f"Copilot workflow failed: {str(e)}"},
            "session_id": session_id
        })
        raise
 
router = APIRouter()
 
 

class ChatRequest(BaseModel):
    user_request: str
    session_id: str
    model: str
    sandbox_context: Dict[str, Any]
    sandbox_id: str
    api_keys: Optional[Dict[str, str]] = None

class ChatResponse(BaseModel):
    success: bool
    generated_code: str
    review_feedback: str
    plan: List[str]
    progress_updates: List[Dict[str, Any]]
    session_id: str
    additional_data: Dict[str, Any]

class StreamingChatResponse(BaseModel):
    type: str
    data: Dict[str, Any]
    session_id: str

# Store active WebSocket connections for streaming
active_connections: Dict[str, WebSocket] = {}

async def safe_websocket_send(websocket: WebSocket, message: dict):
    """Safely send a WebSocket message with error handling."""
    try:
        await websocket.send_json(message)
    except Exception as e:
        logger.warning(f"Failed to send WebSocket message: {e}")
        # Continue execution even if WebSocket fails

async def index_message_to_chroma(message: str, role: str, session_id: str, message_index: int = 0):
    """Index a chat message to ChromaDB for semantic search."""
    if not CHROMA_INTEGRATION_AVAILABLE:
        return
    
    try:
        # Use the chroma_integration service to index the chat message
        success = chroma_integration.index_chat_message(
            message=message,
            role=role,
            session_id=session_id,
            message_index=message_index,
            collection_name="chat_history"
        )
        
        if success:
            logger.info(f"Successfully indexed {role} message to ChromaDB for session {session_id}")
        else:
            logger.warning(f"Failed to index {role} message to ChromaDB for session {session_id}")
        
    except Exception as e:
        logger.error(f"Failed to index message to ChromaDB: {e}")
        # Don't raise the exception to avoid breaking chat flow
 
async def execute_agent_graph_with_sse_streaming(nodes, initial_data: Dict[str, Any], session_id: str):
    """Execute agent graph with Server-Sent Events streaming."""
    from app.agents.agent_graphs import AgentState
    
    logger.info(f"Starting SSE streaming execution for session: {initial_data['session_id']}")
    api_keys = initial_data.get('api_keys', {})
    logger.info(f"API keys provided for session {session_id}: {list(api_keys.keys())}")
    
    # Create initial state
    state = AgentState(
        user_request=initial_data["user_request"],
        session_id=session_id,
        model=initial_data["model"],
        sandbox_context=initial_data["sandbox_context"],
        sandbox_id=initial_data["sandbox_id"],
        available_tools=initial_data["available_tools"],
        tool_results=initial_data["tool_results"],
        api_keys=api_keys
    )

    # Use more aggressive rate limiting for chat endpoints
    # Add extra delay to prevent overwhelming the API
    await asyncio.sleep(2)  # 2 second delay between requests

    MAX_REVISIONS = 2
    for revision in range(MAX_REVISIONS):
        for node in nodes:
            yield f"data: {json.dumps({'type': 'progress', 'data': {'step': node.name, 'message': f'Executing {node.name} (round {revision+1})...'}, 'session_id': session_id})}\n\n"
            await asyncio.sleep(0.1)

            state = await node.process(state)

            # If review agent finds critical issues, send them back for revision
            if node.name == "ReviewAgent" and "issues_found" in state.review_feedback:
                if len(state.review_feedback["issues_found"]) > 0 and revision < MAX_REVISIONS - 1:
                    yield f"data: {json.dumps({'type': 'revision', 'data': {'message': 'Issues found — regenerating code.'}, 'session_id': session_id})}\n\n"
                    state.user_request += "\nPlease fix the issues mentioned above."
                    break
        else:
            break

    final_result = {
        "generated_code": state.generated_code,
        "review_feedback": state.review_feedback,
        "plan": state.current_plan,
        "progress_updates": state.progress_updates,
        "session_id": state.session_id
    }

    # Yield final result marker
    yield {"type": "final_result", "data": final_result}

# WebSocket endpoint for real-time chat streaming
async def websocket_chat_streaming(websocket: WebSocket):
    """WebSocket endpoint for real-time chat streaming with agents."""
    await websocket.accept()

    try:
        # First message should contain session_id and chat request data
        initial_data = await websocket.receive_json()
        session_id = initial_data.get('session_id')

        if not session_id:
            await websocket.send_json({
                "type": "error",
                "data": {"message": "session_id is required in initial message"}
            })
            return

        logger.info(f"WebSocket chat connection established for session: {session_id}")
        logger.info(f"Initial data received: {initial_data}")
        
        # Register this WebSocket connection for tool usage notifications
        register_chat_connection(session_id, websocket)

        # Process the chat request from the initial message
        user_request = initial_data.get('user_request')
        model = initial_data.get('model', 'gpt-4')
        sandbox_context = initial_data.get('sandbox_context', {})
        sandbox_id = initial_data.get('sandbox_id')
        api_keys = initial_data.get('api_keys', {})

        if not user_request:
            await websocket.send_json({
                "type": "error",
                "data": {"message": "user_request is required"},
                "session_id": session_id
            })
            return

        logger.info(f"Processing request: user_request='{user_request}', model='{model}', sandbox_id='{sandbox_id}'")

        # Send immediate acknowledgment
        await websocket.send_json({
            "type": "progress",
            "data": {"step": "received", "message": "Request received, processing..."},
            "session_id": session_id
        })

        # Ensure session exists in database
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        sandboxes_dir = os.path.join(project_root, "sandboxes")
        project_path = os.path.join(sandboxes_dir, sandbox_id) if sandbox_id else sandboxes_dir
        await get_or_create_session(session_id, project_path)

        # Store user message
        await add_conversation(session_id, "user", user_request)
        
        # Index user message to ChromaDB for semantic search
        await index_message_to_chroma(user_request, "user", session_id)

        # Process the chat request using MCP integration
        try:
            mcp_result = await process_chat_request(
                user_request,
                session_id,
                model,
                sandbox_context,
                sandbox_id
            )
            
            # Add API keys to the result for agent graph creation
            if api_keys:
                mcp_result["api_keys"] = api_keys
                logger.info(f"🔑 Passing API keys to WebSocket agent graph: {list(api_keys.keys())}")
            
            logger.info(f"MCP result: {mcp_result}")
        except Exception as e:
            # Log full traceback to help diagnose TaskGroup / ExceptionGroup issues
            logger.exception("Failed to process chat request")
            try:
                if hasattr(e, 'exceptions'):
                    for i, sub in enumerate(e.exceptions):
                        logger.exception(f"Sub-exception {i} during process_chat_request: {sub}")
            except Exception:
                pass
            await websocket.send_json({
                "type": "error",
                "data": {"message": f"Failed to process request: {str(e)}"},
                "session_id": session_id
            })
            return

        # Send initial processing event
        await safe_websocket_send(websocket, {
            "type": "progress",
            "data": {"step": "initializing", "message": "Starting processing..."},
            "session_id": session_id
        })

        # Create and execute agent graph with WebSocket streaming
        try:
            # Create agent instances first
            agent_instances = await create_agent_instances(
                model=mcp_result["model"], 
                session_id=session_id, 
                api_keys=mcp_result.get("api_keys", {})
            )
            
            # Detect if this is a React/Vue development request
            is_react_vue_request = _is_react_vue_request(user_request, sandbox_context)
            
            if is_react_vue_request and agent_instances.get('copilot_agent_graph'):
                # Use Copilot-style workflow for React/Vue development
                logger.info("🎯 Using Copilot-style workflow for React/Vue development")
                final_result = await _execute_copilot_workflow(
                    agent_instances['copilot_agent_graph'], mcp_result, session_id, websocket
                )
            else:
                # Use traditional agent workflow
                logger.info("🔄 Using traditional agent workflow")
                agent_nodes = await create_agent_nodes_with_instances(agent_instances, websocket)
                logger.info(f"Created agent nodes: {[node.name for node in agent_nodes]}")
                
                final_result = await execute_agent_graph_with_websocket_streaming(
                    agent_nodes, mcp_result, session_id, websocket
                )
            logger.info(f"Final result: {final_result}")
        except Exception as e:
            # Log full traceback for the graph execution error (could be ExceptionGroup from TaskGroup)
            logger.exception("Failed to execute agent graph")
            try:
                if hasattr(e, 'exceptions'):
                    for i, sub in enumerate(e.exceptions):
                        logger.exception(f"Sub-exception {i} during agent graph execution: {sub}")
            except Exception:
                pass
            await safe_websocket_send(websocket, {
                "type": "error",
                "data": {"message": f"Failed to execute agent: {str(e)}"},
                "session_id": session_id
            })
            return

        # Send final result
        if final_result:
            await safe_websocket_send(websocket, {
                "type": "complete",
                "data": {
                    "generated_code": final_result.get("generated_code", ""),
                    "review_feedback": final_result.get("review_feedback", "")
                },
                "session_id": session_id
            })

            # Store AI response
            ai_response = final_result.get('generated_code', '') or final_result.get('review_feedback', 'Task completed')
            await add_conversation(session_id, "assistant", ai_response)
            
            # Index assistant response to ChromaDB for semantic search
            await index_message_to_chroma(ai_response, "assistant", session_id)
        else:
            # Send a fallback response
            await websocket.send_json({
                "type": "complete",
                "data": {
                    "generated_code": "# Processing completed\nprint('Hello, World!')",
                    "review_feedback": "Basic response generated due to processing issues.",
                    "plan": "Fallback plan",
                    "progress_updates": [],
                    "session_id": session_id
                },
                "session_id": session_id
            })
            await add_conversation(session_id, "assistant", "Processing completed with fallback response.")
            
            # Index fallback assistant response to ChromaDB for semantic search
            await index_message_to_chroma("Processing completed with fallback response.", "assistant", session_id)

        # Keep connection alive for potential follow-up messages
        try:
            while True:
                # Wait for any follow-up messages (though mainly for keep-alive)
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info(f"WebSocket chat disconnected for session: {session_id}")
    except Exception as e:
        # Log full traceback to aid debugging
        logger.exception("WebSocket chat error")
        try:
            if hasattr(e, 'exceptions'):
                for i, sub in enumerate(e.exceptions):
                    logger.exception(f"Sub-exception {i} in WebSocket chat handler: {sub}")
        except Exception:
            pass
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)},
                "session_id": session_id
            })
        except Exception:
            pass
    finally:
        logger.info(f"WebSocket chat connection closed for session: {session_id}")
        # Unregister the WebSocket connection
        unregister_chat_connection(session_id)

async def execute_agent_graph_with_websocket_streaming(nodes, initial_data: Dict[str, Any], session_id: str, websocket: WebSocket):
    """Execute agent graph with WebSocket streaming updates using LangGraph streaming."""
    from app.agents.agent_graphs import AgentState, AgentGraph
    
    logger.info(f"Starting WebSocket streaming execution for session: {initial_data['session_id']}")
    api_keys = initial_data.get('api_keys', {})
    logger.info(f"API keys provided for session {session_id}: {list(api_keys.keys())}")
    
    # Create initial state
    state = AgentState(
        user_request=initial_data["user_request"],
        session_id=session_id,
        model=initial_data["model"],
        sandbox_context=initial_data["sandbox_context"],
        sandbox_id=initial_data["sandbox_id"],
        available_tools=initial_data["available_tools"],
        tool_results=initial_data["tool_results"],
        api_keys=api_keys
    )

    # Create the agent graph
    agent_graph = AgentGraph(nodes)
    
    # Use more aggressive rate limiting for chat endpoints
    # Add extra delay to prevent overwhelming the API
    await asyncio.sleep(2)  # 2 second delay between requests

    MAX_REVISIONS = 2
    for revision in range(MAX_REVISIONS):
        try:
            # Execute the agent graph (events are emitted from within AgentNode.process methods)
            state_dict = await agent_graph.graph.ainvoke(state)
        except Exception as e:
            logger.error(f"Failed to execute agent graph: {e}")
            # Create a fallback state dict with error information
            state_dict = {
                'user_request': state.user_request,
                'session_id': state.session_id,
                'model': state.model,
                'sandbox_context': state.sandbox_context,
                'sandbox_id': state.sandbox_id,
                'available_tools': state.available_tools,
                'tool_results': state.tool_results,
                'api_keys': state.api_keys,
                'generated_code': getattr(state, 'generated_code', ''),
                'review_feedback': getattr(state, 'review_feedback', ''),
                'current_plan': getattr(state, 'current_plan', []),
                'progress_updates': getattr(state, 'progress_updates', []) + [{
                    "step": "execution",
                    "status": "error",
                    "message": f"Graph execution failed: {str(e)}"
                }],
                'conversation_history': getattr(state, 'conversation_history', []),
                'langchain_tools': getattr(state, 'langchain_tools', [])
            }
            break

        # Send node completion events for each agent that ran
        for node_name in ["planning", "code_generation", "review"]:
            await safe_websocket_send(websocket, {
                "type": "node_complete",
                "data": {"node": node_name},
                "session_id": session_id
            })

        # Check if review found issues that need revision
        review_feedback = state_dict.get('review_feedback', '')
        if isinstance(review_feedback, dict):
            if "issues_found" in review_feedback and len(review_feedback["issues_found"]) > 0 and revision < MAX_REVISIONS - 1:
                await safe_websocket_send(websocket, {
                    "type": "progress",
                    "data": {"step": "review", "status": "issues_found", "message": "Issues found — regenerating code."},
                    "session_id": session_id
                })
                # Feed back into the process for re-generation
                state.user_request += "\nPlease fix the issues mentioned above."
                # Update state for next iteration
                state = AgentState(**state_dict)
                continue
        break

    # Ensure review_feedback is always a string for final result
    review_feedback_final = state_dict.get('review_feedback', '')
    if isinstance(review_feedback_final, dict):
        # Convert dict to string representation
        review_feedback_final = str(review_feedback_final)

    final_result = {
        "generated_code": state_dict.get('generated_code', ''),
        "review_feedback": review_feedback_final,
        "plan": state_dict.get('current_plan', []),
        "progress_updates": state_dict.get('progress_updates', []),
        "session_id": state_dict.get('session_id', session_id)
    }

    return final_result