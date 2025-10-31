from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import os

from app.services.project_context import ProjectContextService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/project", tags=["project"])

class ProjectContextRequest(BaseModel):
    project_path: str
    max_depth: Optional[int] = 3
    include_file_contents: Optional[bool] = True

class ProjectContextResponse(BaseModel):
    success: bool
    context: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/context", response_model=ProjectContextResponse)
async def get_project_context(request: ProjectContextRequest):
    """
    Get comprehensive project context including directory structure, app type, and metadata.
    
    This endpoint analyzes a project directory and returns:
    - Directory structure (up to specified depth)
    - Detected application type (React, Next.js, FastAPI, etc.)
    - Technologies used
    - Package information
    - Configuration files
    - Entry points
    - File statistics
    - Architectural patterns
    - Key file contents (optional)
    """
    try:
        # Validate project path exists
        if not os.path.exists(request.project_path):
            raise HTTPException(status_code=400, detail=f"Project path does not exist: {request.project_path}")
        
        if not os.path.isdir(request.project_path):
            raise HTTPException(status_code=400, detail=f"Project path is not a directory: {request.project_path}")
        
        # Initialize project context service
        context_service = ProjectContextService(request.project_path)
        
        # Gather full context
        context = await context_service.gather_full_context(
            max_depth=request.max_depth,
            include_file_contents=request.include_file_contents
        )
        
        return ProjectContextResponse(
            success=True,
            context=context
        )
        
    except Exception as e:
        logger.error(f"Error getting project context: {e}")
        return ProjectContextResponse(
            success=False,
            error=str(e)
        )

@router.get("/structure")
async def get_project_structure(
    project_path: str = Query(..., description="Path to the project directory"),
    max_depth: int = Query(3, description="Maximum depth to traverse")
):
    """
    Get just the directory structure of a project.
    """
    try:
        if not os.path.exists(project_path):
            raise HTTPException(status_code=400, detail=f"Project path does not exist: {project_path}")
        
        context_service = ProjectContextService(project_path)
        structure = await context_service._get_directory_structure(max_depth)
        
        return {
            "success": True,
            "project_path": project_path,
            "structure": structure
        }
        
    except Exception as e:
        logger.error(f"Error getting project structure: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/app-type")
async def detect_app_type(
    project_path: str = Query(..., description="Path to the project directory")
):
    """
    Detect the type of application (React, Next.js, FastAPI, etc.).
    """
    try:
        if not os.path.exists(project_path):
            raise HTTPException(status_code=400, detail=f"Project path does not exist: {project_path}")
        
        context_service = ProjectContextService(project_path)
        app_type = await context_service._detect_app_type()
        technologies = await context_service._detect_technologies()
        
        return {
            "success": True,
            "project_path": project_path,
            "app_type": app_type,
            "technologies": technologies
        }
        
    except Exception as e:
        logger.error(f"Error detecting app type: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/package-info")
async def get_package_info(
    project_path: str = Query(..., description="Path to the project directory")
):
    """
    Get package information from package.json, requirements.txt, etc.
    """
    try:
        if not os.path.exists(project_path):
            raise HTTPException(status_code=400, detail=f"Project path does not exist: {project_path}")
        
        context_service = ProjectContextService(project_path)
        package_info = await context_service._get_package_info()
        
        return {
            "success": True,
            "project_path": project_path,
            "package_info": package_info
        }
        
    except Exception as e:
        logger.error(f"Error getting package info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_project_stats(
    project_path: str = Query(..., description="Path to the project directory")
):
    """
    Get file statistics for the project.
    """
    try:
        if not os.path.exists(project_path):
            raise HTTPException(status_code=400, detail=f"Project path does not exist: {project_path}")
        
        context_service = ProjectContextService(project_path)
        stats = await context_service._get_file_statistics()
        
        return {
            "success": True,
            "project_path": project_path,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting project stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))