from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class UserRequest(BaseModel):
    user_id: Optional[str] = None
    message: str
    session_id: Optional[str] = None
    context: Optional[List[str]] = None

class SandboxContext(BaseModel):
    type: str
    id: str
    project_path: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    user_request: str
    session_id: str
    model: str
    sandbox_context: Dict[str, Any]
    sandbox_id: str

class StreamingChatRequest(BaseModel):
    user_request: str
    session_id: str
    model: str
    sandbox_context: Dict[str, Any]
    sandbox_id: str

class ToolExecutionRequest(BaseModel):
    server_name: str
    tool_name: str
    arguments: Dict[str, Any]
    session_id: str

class ProgressUpdate(BaseModel):
    step: str
    status: str
    message: str
    progress: Optional[float] = None