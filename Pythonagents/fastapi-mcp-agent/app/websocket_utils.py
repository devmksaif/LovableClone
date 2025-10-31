import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# WebSocket connections for real-time updates
active_websocket_connections: List[WebSocket] = []

# Store active chat WebSocket connections with session IDs
active_chat_connections: Dict[str, WebSocket] = {}

async def broadcast_sandbox_update(update_type: str, sandbox_data: Dict[str, Any]):
    """Broadcast sandbox update to all connected WebSocket clients."""
    message = {
        "type": update_type,
        "timestamp": datetime.now().isoformat(),
        "sandbox": sandbox_data
    }

    disconnected_clients = []
    for websocket in active_websocket_connections:
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send update to WebSocket client: {e}")
            disconnected_clients.append(websocket)

    # Remove disconnected clients
    for client in disconnected_clients:
        if client in active_websocket_connections:
            active_websocket_connections.remove(client)

async def broadcast_tool_usage(tool_name: str, event_type: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """Broadcast tool usage events to WebSocket clients."""
    message = {
        "type": "tool_usage",
        "event_type": event_type,  # 'start', 'progress', 'complete', 'error'
        "tool_name": tool_name,
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "data": data
    }

    # Send to specific session if provided
    if session_id and session_id in active_chat_connections:
        try:
            await active_chat_connections[session_id].send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send tool usage update to session {session_id}: {e}")
            # Remove disconnected session
            if session_id in active_chat_connections:
                del active_chat_connections[session_id]
    else:
        # Broadcast to all connections if no specific session
        disconnected_clients = []
        for websocket in active_websocket_connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send tool usage update to WebSocket client: {e}")
                disconnected_clients.append(websocket)

        # Remove disconnected clients
        for client in disconnected_clients:
            if client in active_websocket_connections:
                active_websocket_connections.remove(client)

async def broadcast_file_operation(operation_type: str, file_path: str, data: Dict[str, Any], session_id: Optional[str] = None):
    """Broadcast file operation events to WebSocket clients."""
    message = {
        "type": "file_operation",
        "operation_type": operation_type,  # 'create', 'modify', 'delete', 'move'
        "file_path": file_path,
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id,
        "data": data
    }

    # Send to specific session if provided
    if session_id and session_id in active_chat_connections:
        try:
            await active_chat_connections[session_id].send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send file operation update to session {session_id}: {e}")
            # Remove disconnected session
            if session_id in active_chat_connections:
                del active_chat_connections[session_id]
    else:
        # Broadcast to all connections if no specific session
        disconnected_clients = []
        for websocket in active_websocket_connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send file operation update to WebSocket client: {e}")
                disconnected_clients.append(websocket)

        # Remove disconnected clients
        for client in disconnected_clients:
            if client in active_websocket_connections:
                active_websocket_connections.remove(client)

def register_chat_connection(session_id: str, websocket: WebSocket):
    """Register a chat WebSocket connection with session ID."""
    active_chat_connections[session_id] = websocket
    logger.info(f"Registered chat WebSocket for session: {session_id}")

def unregister_chat_connection(session_id: str):
    """Unregister a chat WebSocket connection."""
    if session_id in active_chat_connections:
        del active_chat_connections[session_id]
        logger.info(f"Unregistered chat WebSocket for session: {session_id}")