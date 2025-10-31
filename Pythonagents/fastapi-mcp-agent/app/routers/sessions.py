import logging
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from app.database import get_all_sessions, get_session_by_id, create_session

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/sessions")
async def get_sessions(page: int = 1, pageSize: int = 5):
    """Get paginated sessions."""
    try:
        sessions = await get_all_sessions()

        # Simple pagination
        start_idx = (page - 1) * pageSize
        end_idx = start_idx + pageSize
        paginated_sessions = sessions[start_idx:end_idx]

        return {
            "sessions": paginated_sessions,
            "pagination": {
                "page": page,
                "pageSize": pageSize,
                "totalSessions": len(sessions),
                "totalPages": (len(sessions) + pageSize - 1) // pageSize,
                "hasNextPage": end_idx < len(sessions),
                "hasPrevPage": page > 1
            }
        }
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session."""
    try:
        session = await get_session_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sessions")
async def create_new_session(data: Dict[str, Any]):
    """Create a new session."""
    try:
        session_id = data.get("sessionId", "")
        project_folder = data.get("projectFolder", "")

        if not session_id:
            raise HTTPException(status_code=400, detail="sessionId is required")

        await create_session(session_id, project_folder)

        return {"success": True, "sessionId": session_id}
    except Exception as e:
        logger.error(f"Error creating session: {e}")
        raise HTTPException(status_code=500, detail=str(e))