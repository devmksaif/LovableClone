import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from app.routers import chat, sandbox, models, execute, conversations, chat_logs, sessions, vector, preview, project_context
from app.agents.mcp_integration import initialize_mcp_clients
from app.database import init_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting FastAPI MCP Agent...")

    # Initialize database
    try:
        await init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        # Continue startup even if database fails

    # Initialize MCP clients and external tools
    try:
        await initialize_mcp_clients()
        logger.info("MCP clients initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MCP clients: {e}")
        # Continue startup even if MCP fails

    yield

    # Shutdown
    logger.info("Shutting down FastAPI MCP Agent...")

# Create FastAPI app with lifespan
app = FastAPI(
    title="FastAPI MCP Agent",
    description="AI Agent with MCP (Model Context Protocol) integration for code generation and tool execution",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware for direct frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js development server
        "http://127.0.0.1:3000",  # Alternative localhost
        "https://your-frontend-domain.com"  # Production domain
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add trusted host middleware (configure for production)
if os.getenv("ENVIRONMENT") == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["yourdomain.com"]  # Replace with actual domain
    )

# Include routers
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(sandbox.router, prefix="/api", tags=["sandbox"])
app.include_router(models.router, prefix="/api", tags=["models"])
app.include_router(execute.router, prefix="/api", tags=["execute"])
app.include_router(conversations.router, prefix="/api", tags=["conversations"])
app.include_router(chat_logs.router, prefix="/api", tags=["chat-logs"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(vector.router, prefix="/api", tags=["vector"])
app.include_router(preview.router, prefix="/api", tags=["preview"])
app.include_router(project_context.router, prefix="/api", tags=["project"])

# Include WebSocket endpoint directly (without /api prefix)
from app.routers.sandbox import websocket_sandbox_updates
from app.routers.chat import websocket_chat_streaming

app.add_websocket_route("/ws/sandbox-updates", websocket_sandbox_updates)
app.add_websocket_route("/ws/chat", websocket_chat_streaming)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to the FastAPI MCP Agent!",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True if os.getenv("ENVIRONMENT") != "production" else False,
        log_level="info"
    )