import logging
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from app.database import get_conversations_by_session

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/conversations")
async def get_conversations(sandboxId: str):
    """Get conversations for a sandbox (derived from session)."""
    try:
        # Derive sessionId from sandboxId (same logic as Next.js)
        session_id = f"sandbox-{sandboxId}"

        conversations = await get_conversations_by_session(session_id)

        # Format response to match Next.js expectations
        return {
            "success": True,
            "conversations": [
                {
                    "id": conv.get("id", ""),
                    "role": conv.get("role", ""),
                    "content": conv.get("content", ""),
                    "timestamp": conv.get("timestamp", ""),
                }
                for conv in conversations
            ]
        }
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))