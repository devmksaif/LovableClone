import logging
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.database import get_conversations_by_session, add_conversation

# ChromaDB integration import
try:
    from app.services.chroma_integration import chroma_integration
    CHROMA_INTEGRATION_AVAILABLE = True
except ImportError:
    CHROMA_INTEGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)

router = APIRouter()

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
            logger.info(f"Indexed chat message to ChromaDB: {session_id}_{message_index}_{role}")
        else:
            logger.warning(f"Failed to index chat message to ChromaDB: {session_id}_{message_index}_{role}")
    except Exception as e:
        logger.error(f"Failed to index chat message to ChromaDB: {e}")

@router.post("/chat-logs")
async def add_chat_log(data: Dict[str, Any]):
    """Add a chat log entry."""
    try:
        session_id = data.get("sessionId", "")
        role = data.get("role", "")
        content = data.get("content", "")

        if not session_id or not role or not content:
            raise HTTPException(status_code=400, detail="sessionId, role, and content are required")

        await add_conversation(session_id, role, content)
        
        # Index message to ChromaDB for semantic search
        await index_message_to_chroma(content, role, session_id)

        return {"success": True}
    except Exception as e:
        logger.error(f"Error adding chat log: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat-logs")
async def get_chat_logs(sessionId: str):
    """Get chat logs for a session."""
    try:
        conversations = await get_conversations_by_session(sessionId)

        return {
            "success": True,
            "logs": [
                {
                    "id": conv.get("id", ""),
                    "sessionId": sessionId,
                    "role": conv.get("role", ""),
                    "content": conv.get("content", ""),
                    "timestamp": conv.get("timestamp", ""),
                }
                for conv in conversations
            ]
        }
    except Exception as e:
        logger.error(f"Error getting chat logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))