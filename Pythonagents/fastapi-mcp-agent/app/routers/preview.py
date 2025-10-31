import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
from app.sandbox_service import sandbox_service
from app.websocket_utils import broadcast_sandbox_update

logger = logging.getLogger(__name__)

router = APIRouter()

class PreviewResponse(BaseModel):
    success: bool
    preview: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

class PreviewConfig(BaseModel):
    sandboxId: str
    port: int
    url: str
    status: str
    lastActivity: str
    securityHeaders: Dict[str, str]

# Mock preview storage - in a real implementation, this would be persistent
previews = {}

@router.get("/sandbox/preview")
async def get_preview(sandboxId: str = Query(..., description="Sandbox ID")):
    """Get preview status for a sandbox."""
    try:
        # Check if sandbox exists in service, if not try to load from database
        if sandboxId not in sandbox_service.environments:
            # Try to load from database
            from app.database import Sandbox
            db_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            if db_sandbox:
                # Recreate the environment from database
                from app.sandbox_service import SandboxEnvironment, SandboxConfig
                environment = SandboxEnvironment(sandboxId, db_sandbox.name, db_sandbox.type)
                environment.status = db_sandbox.status
                environment.project_path = db_sandbox.projectPath
                environment.metadata = db_sandbox.metadata or {}
                # Use saved port or find a new available port
                port = db_sandbox.port
                if not port:
                    port = sandbox_service.find_available_port()
                environment.config = SandboxConfig(sandboxId, db_sandbox.projectPath, port)
                sandbox_service.environments[sandboxId] = environment
                logger.info(f"Loaded sandbox {sandboxId} from database for preview status")
            else:
                return {"success": False, "error": "Preview not found"}

        preview = await sandbox_service.get_preview(sandboxId)
        if not preview:
            return {"success": False, "error": "Preview not found"}

        # Generate iframe HTML for the frontend
        preview_id = f"preview_{sandboxId}"
        iframe_html = f'''<iframe
          id="sandbox-preview-{preview_id}"
          src="{preview.url}"
          sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
          allow="camera; microphone; geolocation"
          allowfullscreen
          style="width: 100%; height: 100%; border: none; border-radius: 8px;"
          title="Sandbox Preview"
          loading="lazy"
        ></iframe>'''

        return {
            "success": True,
            "preview": {
                **preview,
                "iframeHtml": iframe_html
            }
        }
    except Exception as e:
        logger.error(f"Failed to get preview for sandbox {sandboxId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get preview status")

@router.post("/sandbox/preview")
async def start_preview(sandboxId: str = Query(..., description="Sandbox ID")):
    """Start preview for a sandbox."""
    try:
        # Check if sandbox exists in service, if not try to load from database
        if sandboxId not in sandbox_service.environments:
            # Try to load from database
            from app.database import Sandbox
            db_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            if db_sandbox:
                # Recreate the environment from database
                from app.sandbox_service import SandboxEnvironment, SandboxConfig
                environment = SandboxEnvironment(sandboxId, db_sandbox.name, db_sandbox.type)
                environment.status = db_sandbox.status
                environment.project_path = db_sandbox.projectPath
                environment.metadata = db_sandbox.metadata or {}
                # Use saved port or find a new available port
                port = db_sandbox.port
                if not port:
                    port = sandbox_service.find_available_port()
                environment.config = SandboxConfig(sandboxId, db_sandbox.projectPath, port)
                sandbox_service.environments[sandboxId] = environment
                logger.info(f"Loaded sandbox {sandboxId} from database for preview")
            else:
                raise ValueError(f"Sandbox {sandboxId} not found")

        # Stop all other running sandboxes before starting this preview
        await sandbox_service.stop_all_other_previews(sandboxId)

        preview = await sandbox_service.start_preview(sandboxId)

        # Generate iframe HTML for the frontend
        preview_id = f"preview_{sandboxId}"
        iframe_html = f'''<iframe
          id="sandbox-preview-{preview_id}"
          src="{preview.url}"
          sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
          allow="camera; microphone; geolocation"
          allowfullscreen
          style="width: 100%; height: 100%; border: none; border-radius: 8px;"
          title="Sandbox Preview"
          loading="lazy"
        ></iframe>'''

        logger.info(f"Started preview for sandbox {sandboxId}")
        
        # Broadcast sandbox update with preview info
        await broadcast_sandbox_update("updated", {
            "id": sandboxId,
            "status": "running",
            "preview": {
                "port": preview.port,
                "url": preview.url,
                "status": preview.status,
                "lastActivity": datetime.now().isoformat()
            }
        })
        
        return {
            "success": True,
            "preview": {
                "sandboxId": sandboxId,
                "port": preview.port,
                "url": preview.url,
                "status": preview.status,
                "lastActivity": datetime.now().isoformat(),
                "iframeHtml": iframe_html,
                "securityHeaders": {
                    "X-Frame-Options": "SAMEORIGIN",
                    "X-Content-Type-Options": "nosniff",
                    "X-XSS-Protection": "1; mode=block"
                }
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start preview for sandbox {sandboxId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start preview")

@router.put("/sandbox/preview")
async def restart_preview(sandboxId: str = Query(..., description="Sandbox ID")):
    """Restart preview for a sandbox."""
    try:
        # Check if sandbox exists in service, if not try to load from database
        if sandboxId not in sandbox_service.environments:
            # Try to load from database
            from app.database import Sandbox
            db_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            if db_sandbox:
                # Recreate the environment from database
                from app.sandbox_service import SandboxEnvironment, SandboxConfig
                environment = SandboxEnvironment(sandboxId, db_sandbox.name, db_sandbox.type)
                environment.status = db_sandbox.status
                environment.project_path = db_sandbox.projectPath
                environment.metadata = db_sandbox.metadata or {}
                # Use saved port or find a new available port
                port = db_sandbox.port
                if not port:
                    port = sandbox_service.find_available_port()
                environment.config = SandboxConfig(sandboxId, db_sandbox.projectPath, port)
                sandbox_service.environments[sandboxId] = environment
                logger.info(f"Loaded sandbox {sandboxId} from database for preview restart")
            else:
                raise ValueError(f"Sandbox {sandboxId} not found")

        # For now, just start the preview again (restart functionality)
        preview = await sandbox_service.start_preview(sandboxId)

        logger.info(f"Restarted preview for sandbox {sandboxId}")
        return {
            "success": True,
            "preview": {
                "sandboxId": sandboxId,
                "port": preview.port,
                "url": preview.url,
                "status": preview.status,
                "lastActivity": datetime.now().isoformat(),
                "securityHeaders": {
                    "X-Frame-Options": "SAMEORIGIN",
                    "X-Content-Type-Options": "nosniff",
                    "X-XSS-Protection": "1; mode=block"
                }
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restart preview for sandbox {sandboxId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to restart preview")
       

@router.delete("/sandbox/preview")
async def stop_preview(sandboxId: str = Query(..., description="Sandbox ID")):
    """Stop preview for a sandbox."""
    try:
        # Check if sandbox exists in service, if not try to load from database
        if sandboxId not in sandbox_service.environments:
            # Try to load from database
            from app.database import Sandbox
            db_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            if db_sandbox:
                # Recreate the environment from database
                from app.sandbox_service import SandboxEnvironment, SandboxConfig
                environment = SandboxEnvironment(sandboxId, db_sandbox.name, db_sandbox.type)
                environment.status = db_sandbox.status
                environment.project_path = db_sandbox.projectPath
                environment.metadata = db_sandbox.metadata or {}
                # Use saved port or find a new available port
                port = db_sandbox.port
                if not port:
                    port = sandbox_service.find_available_port()
                environment.config = SandboxConfig(sandboxId, db_sandbox.projectPath, port)
                sandbox_service.environments[sandboxId] = environment
                logger.info(f"Loaded sandbox {sandboxId} from database for preview stop")
            else:
                raise ValueError(f"Sandbox {sandboxId} not found")

        await sandbox_service.stop_preview(sandboxId)

        logger.info(f"Stopped preview for sandbox {sandboxId}")
        
        # Broadcast sandbox update with stopped preview
        await broadcast_sandbox_update("updated", {
            "id": sandboxId,
            "status": "stopped",
            "preview": None
        })
        
        return {
            "success": True,
            "message": "Preview stopped successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to stop preview for sandbox {sandboxId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop preview")