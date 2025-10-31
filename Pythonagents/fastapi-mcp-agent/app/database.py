import os
import motor.motor_asyncio
from beanie import init_beanie, Document
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017/nextlovable")
client = motor.motor_asyncio.AsyncIOMotorClient(DATABASE_URL)
db = client.nextlovable

# Models
class Conversation(Document):
    sessionId: str
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "conversations"

class File(Document):
    filename: str
    content: str
    operation: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "files"

class Project(Document):
    sessionId: str
    name: str
    files: List[str] = []  # Store file IDs
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "projects"

class Session(Document):
    sessionId: str
    projectFolder: str
    conversations: List[str] = []  # Store conversation IDs
    projects: List[str] = []  # Store project IDs
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "sessions"

class Sandbox(Document):
    sandboxId: str
    sessionId: Optional[str] = None
    name: Optional[str] = None
    type: str  # 'react', 'vue', 'vanilla'
    status: str = "ready"  # 'creating', 'ready', 'running', 'stopped', 'error'
    projectPath: str
    port: Optional[int] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    lastActivity: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None

    class Settings:
        name = "sandboxes"

async def init_database():
    """Initialize the database connection and register models."""
    await init_beanie(database=db, document_models=[Session, Conversation, Project, File, Sandbox])

# Database operations
async def get_or_create_session(session_id: str, project_folder: str) -> Session:
    """Get or create a session."""
    session = await Session.find_one(Session.sessionId == session_id)
    if not session:
        session = Session(
            sessionId=session_id,
            projectFolder=project_folder
        )
        await session.insert()
    return session

async def add_conversation(session_id: str, role: str, content: str) -> Conversation:
    """Add a conversation to a session."""
    conversation = Conversation(
        sessionId=session_id,
        role=role,
        content=content
    )
    await conversation.insert()

    # Update session's updatedAt
    await Session.find_one(Session.sessionId == session_id).update({"$set": {"updatedAt": datetime.utcnow()}})

    return conversation

async def get_conversations(session_id: str) -> List[Conversation]:
    """Get all conversations for a session."""
    conversations = await Conversation.find(Conversation.sessionId == session_id).sort([("timestamp", 1)]).to_list()
    return conversations

async def create_project(session_id: str, name: str) -> Project:
    """Create a new project for a session."""
    project = Project(
        sessionId=session_id,
        name=name
    )
    await project.insert()
    return project

async def get_conversations_by_session(session_id: str) -> List[Dict[str, Any]]:
    """Get conversations for a session formatted for API response."""
    conversations = await Conversation.find(Conversation.sessionId == session_id).sort([("timestamp", 1)]).to_list()
    return [
        {
            "id": str(conv.id),
            "role": conv.role,
            "content": conv.content,
            "timestamp": conv.timestamp.isoformat()
        }
        for conv in conversations
    ]

async def get_all_sessions() -> List[Dict[str, Any]]:
    """Get all sessions formatted for API response."""
    sessions = await Session.find().sort([("createdAt", -1)]).to_list()
    result = []
    for session in sessions:
        conversations = await get_conversations_by_session(session.sessionId)
        projects = await get_projects(session.sessionId)

        result.append({
            "id": str(session.id),
            "sessionId": session.sessionId,
            "projectFolder": session.projectFolder,
            "createdAt": session.createdAt.isoformat(),
            "updatedAt": session.updatedAt.isoformat(),
            "conversations": conversations,
            "projects": [
                {
                    "id": str(p.id),
                    "projectFolder": session.projectFolder,  # Use session's project folder
                    "userRequest": p.name,  # Use project name as user request
                    "plan": [],  # TODO: Add plan field to Project model
                    "isComplete": False,  # TODO: Add completion status
                    "createdAt": p.createdAt.isoformat(),
                    "files": []  # TODO: Add files relationship
                }
                for p in projects
            ]
        })

    return result

async def get_session_by_id(session_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific session by ID."""
    session = await Session.find_one(Session.sessionId == session_id)
    if not session:
        return None

    conversations = await get_conversations_by_session(session.sessionId)
    projects = await get_projects(session.sessionId)

    return {
        "id": str(session.id),
        "sessionId": session.sessionId,
        "projectFolder": session.projectFolder,
        "createdAt": session.createdAt.isoformat(),
        "updatedAt": session.updatedAt.isoformat(),
        "conversations": conversations,
        "projects": [
            {
                "id": str(p.id),
                "projectFolder": session.projectFolder,
                "userRequest": p.name,
                "plan": [],
                "isComplete": False,
                "createdAt": p.createdAt.isoformat(),
                "files": []
            }
            for p in projects
        ]
    }

async def create_session(session_id: str, project_folder: str) -> Session:
    """Create a new session."""
    session = Session(
        sessionId=session_id,
        projectFolder=project_folder
    )
    await session.insert()
    return session

async def get_projects(session_id: str) -> List[Project]:
    """Get all projects for a session."""
    projects = await Project.find(Project.sessionId == session_id).sort([("createdAt", -1)]).to_list()
    return projects