import logging
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import os
import json
from app.database import get_or_create_session, Sandbox
from app.sandbox_service import sandbox_service, SandboxEnvironment, SandboxConfig
from app.websocket_utils import broadcast_sandbox_update, active_websocket_connections
from app.agents.code_intelligence import CodeIntelligenceService
from app.agents.symbol_index import get_symbol_index_service

logger = logging.getLogger(__name__)

router = APIRouter()

def extract_enhanced_metadata(sandbox) -> Dict[str, Any]:
    """Extract enhanced metadata fields for agent context."""
    if not sandbox.metadata:
        return {}
    
    # Ensure metadata is a dictionary, handle cases where it might be a list or None
    metadata = sandbox.metadata
    if not isinstance(metadata, dict):
        logger.warning(f"Sandbox {sandbox.sandboxId} has invalid metadata type: {type(metadata)}, using empty dict")
        return {}
    
    enhanced = {}
    
    # Extract key fields that agents need for context
    if 'project_type' in metadata:
        enhanced['projectType'] = metadata['project_type']
    
    if 'frameworks' in metadata:
        enhanced['frameworks'] = metadata['frameworks']
    
    if 'dependencies' in metadata:
        enhanced['dependencies'] = metadata['dependencies']
    
    if 'file_statistics' in metadata:
        file_stats = metadata['file_statistics']
        enhanced['fileCount'] = file_stats.get('total_files', 0)
    
    if 'size_analysis' in metadata:
        size_analysis = metadata['size_analysis']
        enhanced['totalSize'] = size_analysis.get('total_size_formatted', '0 B')
    
    if 'entry_points' in metadata:
        enhanced['entryPoints'] = metadata['entry_points']
    
    if 'build_tools' in metadata:
        enhanced['buildTools'] = metadata['build_tools']
    
    if 'recent_activity' in metadata:
        enhanced['recentActivity'] = metadata['recent_activity']
    
    return enhanced

class SandboxCreateRequest(BaseModel):
    name: Optional[str] = None
    type: str
    template: Optional[str] = None
    enablePreview: Optional[bool] = False
    metadata: Optional[Dict[str, Any]] = None
    sessionId: Optional[str] = None

class SandboxResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    createdAt: str
    lastActivity: str
    metadata: Optional[Dict[str, Any]] = None

class EnhancedSandboxResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    createdAt: str
    lastActivity: str
    metadata: Optional[Dict[str, Any]] = None
    # Enhanced metadata fields for agent context
    projectType: Optional[str] = None
    frameworks: Optional[List[str]] = None
    dependencies: Optional[Dict[str, Any]] = None
    fileCount: Optional[int] = None
    totalSize: Optional[str] = None
    entryPoints: Optional[List[str]] = None
    buildTools: Optional[List[str]] = None
    recentActivity: Optional[Dict[str, Any]] = None

class DetailedSandboxStatsResponse(BaseModel):
    success: bool
    stats: Dict[str, Any]
    projectStructure: Optional[Dict[str, Any]] = None
    fileStatistics: Optional[Dict[str, Any]] = None
    sizeAnalysis: Optional[Dict[str, Any]] = None

class SandboxUpdateRequest(BaseModel):
    sandboxId: str
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

class ExecuteRequest(BaseModel):
    code: str
    language: str = "javascript"
    fileName: Optional[str] = None
    sandboxId: Optional[str] = None

class ExecuteResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class SaveFileRequest(BaseModel):
    sandboxId: str
    filePath: str
    content: str

class ReadFileRequest(BaseModel):
    sandboxId: str
    filePath: str

class FileResponse(BaseModel):
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None

class StopOthersRequest(BaseModel):
    exceptSandboxId: str

@router.post("/sandbox", response_model=EnhancedSandboxResponse)
async def create_sandbox(request: SandboxCreateRequest):
    """Create a new sandbox with enhanced metadata."""
    try:
        # Use the Python sandbox service to create the sandbox
        environment = await sandbox_service.create_sandbox(
            name=request.name,
            sandbox_type=request.type,
            template=request.template,
            enable_preview=request.enablePreview,
            metadata=request.metadata,
            session_id=request.sessionId
        )

        # Also save to database for persistence
        sandbox = Sandbox(
            sandboxId=environment.id,
            sessionId=request.sessionId,
            name=environment.name,
            type=environment.type,
            status=environment.status,
            projectPath=environment.project_path,
            port=environment.config.port if environment.config else None,
            createdAt=environment.created_at,
            lastActivity=environment.last_activity,
            metadata=environment.metadata
        )
        await sandbox.insert()

        logger.info(f"Created sandbox {environment.id}")

        # Index project files for code intelligence
        try:
            code_intel = CodeIntelligenceService()
            await code_intel.index_project_files(environment.project_path)
            logger.info(f"Indexed project files for sandbox {environment.id}")
        except Exception as e:
            logger.warning(f"Failed to index project files for sandbox {environment.id}: {e}")

        # Build symbol index for fast lookups
        try:
            symbol_index = get_symbol_index_service(environment.project_path)
            index_time = await symbol_index.build_index()
            logger.info(f"Built symbol index for sandbox {environment.id} in {index_time:.2f}s")
        except Exception as e:
            logger.warning(f"Failed to build symbol index for sandbox {environment.id}: {e}")

        # Extract enhanced metadata for better agent context
        enhanced_metadata = extract_enhanced_metadata(sandbox)

        # Broadcast sandbox creation update
        await broadcast_sandbox_update("created", {
            "id": environment.id,
            "name": environment.name or "",
            "type": environment.type,
            "status": environment.status,
            "createdAt": environment.created_at.isoformat(),
            "lastActivity": environment.last_activity.isoformat(),
            "metadata": environment.metadata,
            **enhanced_metadata
        })

        return EnhancedSandboxResponse(
            id=environment.id,
            name=environment.name or "",
            type=environment.type,
            status=environment.status,
            createdAt=environment.created_at.isoformat(),
            lastActivity=environment.last_activity.isoformat(),
            metadata=environment.metadata,
            **enhanced_metadata
        )
    except Exception as e:
        logger.error(f"Failed to create sandbox: {e}")
        raise HTTPException(status_code=500, detail="Failed to create sandbox")

@router.get("/sandbox")
async def get_all_sandboxes(enhanced: bool = Query(False, description="Include enhanced metadata for agent context")):
    """Get all sandboxes with optional enhanced metadata."""
    try:
        sandboxes = await Sandbox.find_all().to_list()

        result = []
        for sandbox in sandboxes:
            sandbox_data = {
                "id": sandbox.sandboxId,
                "name": sandbox.name or "",
                "type": sandbox.type,
                "status": sandbox.status,
                "createdAt": sandbox.createdAt.isoformat(),
                "lastActivity": sandbox.lastActivity.isoformat(),
                "metadata": sandbox.metadata
            }
            
            # Add enhanced metadata if requested
            if enhanced:
                enhanced_metadata = extract_enhanced_metadata(sandbox)
                sandbox_data.update(enhanced_metadata)
            
            result.append(sandbox_data)

        return {"success": True, "sandboxes": result}
    except Exception as e:
        logger.error(f"Failed to get sandboxes: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sandboxes")


@router.get("/sandbox/stats")
async def get_system_stats():
    """Get system-wide sandbox statistics with enhanced metadata"""
    try:
        # Get all sandboxes from database
        sandboxes = await Sandbox.find_all().to_list()

        total_sandboxes = len(sandboxes)
        active_sandboxes = len([s for s in sandboxes if s.status == "running"])
        
        # Enhanced statistics calculation
        total_files = 0
        total_size = 0
        project_types = {}
        frameworks_used = set()
        build_tools_used = set()
        
        for sandbox in sandboxes:
            metadata = sandbox.metadata or {}
            
            # File and size statistics
            file_stats = metadata.get("file_statistics", {})
            size_analysis = metadata.get("size_analysis", {})
            
            total_files += file_stats.get("total_files", 0)
            total_size += size_analysis.get("total_size_bytes", 0)
            
            # Project type distribution
            project_type = metadata.get("project_type", "unknown")
            project_types[project_type] = project_types.get(project_type, 0) + 1
            
            # Frameworks and build tools
            frameworks = metadata.get("frameworks", [])
            build_tools = metadata.get("build_tools", [])
            
            frameworks_used.update(frameworks)
            build_tools_used.update(build_tools)

        return {
            "success": True,
            "stats": {
                "totalSandboxes": total_sandboxes,
                "activeSandboxes": active_sandboxes,
                "totalFiles": total_files,
                "totalSize": total_size,
                "projectTypeDistribution": project_types,
                "frameworksInUse": list(frameworks_used),
                "buildToolsInUse": list(build_tools_used),
                "memoryUsage": "N/A",  # Could be implemented later
                "cpuUsage": "N/A"      # Could be implemented later
            }
        }

    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get system stats")


@router.get("/sandbox/{sandbox_id}/stats")
async def get_sandbox_stats(sandbox_id: str, detailed: bool = Query(False, description="Include detailed project analysis")):
    """Get statistics for a specific sandbox with optional detailed analysis"""
    try:
        # Get sandbox from database
        sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        # Ensure metadata is a dictionary, handle cases where it might be a list or None
        metadata = sandbox.metadata
        if not isinstance(metadata, dict):
            logger.warning(f"Sandbox {sandbox_id} has invalid metadata type: {type(metadata)}, using empty dict")
            metadata = {}
        
        # Basic stats
        stats = {
            "files": metadata.get("file_statistics", {}).get("total_files", 0),
            "size": metadata.get("size_analysis", {}).get("total_size_bytes", 0),
            "lastActivity": sandbox.lastActivity.isoformat() if sandbox.lastActivity else None,
            "status": sandbox.status,
            "type": sandbox.type,
            "projectType": metadata.get("project_type", "unknown"),
            "frameworks": metadata.get("frameworks", []),
            "buildTools": metadata.get("build_tools", []),
            "memoryUsage": "N/A",  # Could be implemented later
            "cpuUsage": "N/A"      # Could be implemented later
        }

        response = {
            "success": True,
            "stats": stats
        }

        # Add detailed information if requested
        if detailed:
            response["projectStructure"] = metadata.get("project_structure", {})
            response["fileStatistics"] = metadata.get("file_statistics", {})
            response["sizeAnalysis"] = metadata.get("size_analysis", {})

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox stats for {sandbox_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox stats")


@router.get("/sandbox/{sandbox_id}")
async def get_sandbox(sandbox_id: str, enhanced: bool = Query(False, description="Include enhanced metadata for agent context")):
    """Get a specific sandbox with optional enhanced metadata."""
    try:
        sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        if enhanced:
            # Return enhanced response with extracted metadata
            enhanced_metadata = extract_enhanced_metadata(sandbox)
            return EnhancedSandboxResponse(
                id=sandbox.sandboxId,
                name=sandbox.name or "",
                type=sandbox.type,
                status=sandbox.status,
                createdAt=sandbox.createdAt.isoformat(),
                lastActivity=sandbox.lastActivity.isoformat(),
                metadata=sandbox.metadata,
                **enhanced_metadata
            )
        else:
            # Return standard response
            return SandboxResponse(
                id=sandbox.sandboxId,
                name=sandbox.name or "",
                type=sandbox.type,
                status=sandbox.status,
                createdAt=sandbox.createdAt.isoformat(),
                lastActivity=sandbox.lastActivity.isoformat(),
                metadata=sandbox.metadata
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox {sandbox_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox")

@router.delete("/sandbox/{sandboxId}")
async def delete_sandbox(sandboxId: str):
    """Delete a sandbox."""
    try:
        # Try to delete from the sandbox service first
        try:
            await sandbox_service.delete_sandbox(sandboxId)
        except ValueError:
            # Sandbox not in memory, that's ok - it might only be in database
            pass
        except Exception as e:
            logger.warning(f"Sandbox service delete failed for {sandboxId}: {e}")
            # Continue with database cleanup even if service delete fails

        # Wait a bit for any remaining processes to terminate
        import asyncio
        await asyncio.sleep(1)

        # Also remove from database
        sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
        if sandbox:
            # Clean up directory if it exists (with better error handling)
            if sandbox.projectPath and os.path.exists(sandbox.projectPath):
                try:
                    import shutil
                    shutil.rmtree(sandbox.projectPath)
                    logger.info(f"Deleted directory {sandbox.projectPath} for sandbox {sandboxId}")
                except OSError as e:
                    if e.errno == 66:  # Directory not empty
                        logger.warning(f"Directory {sandbox.projectPath} not empty, attempting force delete")
                        # Try to force delete by removing files individually
                        try:
                            for root, dirs, files in os.walk(sandbox.projectPath, topdown=False):
                                for name in files:
                                    try:
                                        os.remove(os.path.join(root, name))
                                    except OSError:
                                        pass  # Ignore individual file deletion errors
                                for name in dirs:
                                    try:
                                        os.rmdir(os.path.join(root, name))
                                    except OSError:
                                        pass  # Ignore individual directory deletion errors
                            os.rmdir(sandbox.projectPath)
                            logger.info(f"Force deleted directory {sandbox.projectPath} for sandbox {sandboxId}")
                        except Exception as force_e:
                            logger.error(f"Failed to force delete directory {sandbox.projectPath}: {force_e}")
                            # Don't raise error, just log it - sandbox is still deleted from DB
                    else:
                        logger.error(f"Failed to delete directory {sandbox.projectPath}: {e}")
                        # Don't raise error for directory deletion failures
            
            await sandbox.delete()

        logger.info(f"Deleted sandbox {sandboxId}")
        
        # Broadcast sandbox deletion update
        await broadcast_sandbox_update("deleted", {"id": sandboxId})
        
        return {"success": True, "message": "Sandbox deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete sandbox {sandboxId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete sandbox")

@router.put("/sandbox/{sandbox_id}")
async def update_sandbox_by_id(sandbox_id: str, request: SandboxUpdateRequest):
    """Update a sandbox by ID."""
    # Override the sandboxId in the request with the path parameter
    request.sandboxId = sandbox_id
    return await update_sandbox_body(request)

@router.put("/sandbox")
async def update_sandbox_body(request: SandboxUpdateRequest):
    """Update a sandbox."""
    try:
        sandbox = await Sandbox.find_one(Sandbox.sandboxId == request.sandboxId)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        # Update fields
        if request.name is not None:
            sandbox.name = request.name
        if request.metadata is not None:
            sandbox.metadata = request.metadata
        if request.status is not None:
            sandbox.status = request.status

        await sandbox.save()

        logger.info(f"Updated sandbox {request.sandboxId}")
        
        # Broadcast sandbox update
        await broadcast_sandbox_update("updated", {
            "id": sandbox.sandboxId,
            "name": sandbox.name or "",
            "type": sandbox.type,
            "status": sandbox.status,
            "createdAt": sandbox.createdAt.isoformat(),
            "lastActivity": sandbox.lastActivity.isoformat(),
            "metadata": sandbox.metadata
        })

        return SandboxResponse(
            id=sandbox.sandboxId,
            name=sandbox.name or "",
            type=sandbox.type,
            status=sandbox.status,
            createdAt=sandbox.createdAt.isoformat(),
            lastActivity=sandbox.lastActivity.isoformat(),
            metadata=sandbox.metadata
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update sandbox {request.sandboxId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update sandbox")

@router.post("/sandbox/execute")
async def execute_code_in_sandbox(
    request: ExecuteRequest,
    sandboxId: Optional[str] = Query(None, description="Sandbox ID (alternative to body)")
):
    """Execute code in a sandbox environment."""
    try:
        # Use sandboxId from query parameter if not in body
        sandbox_id = request.sandboxId or sandboxId
        if not sandbox_id:
            raise HTTPException(status_code=400, detail="sandboxId is required")

        logger.info(f"Executing {request.language} code in sandbox {sandbox_id}")

        # For now, we'll use a simple execution approach
        # In a real implementation, this would use the sandbox service
        if request.language.lower() == "javascript":
            # Simple JavaScript execution using Node.js
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(request.code)
                temp_file = f.name

            try:
                result = subprocess.run(
                    ['node', temp_file],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                return ExecuteResponse(
                    success=result.returncode == 0,
                    result={
                        "output": result.stdout,
                        "error": result.stderr,
                        "exitCode": result.returncode,
                        "executionTime": 0  # TODO: measure actual execution time
                    } if result.returncode == 0 else None,
                    error=result.stderr if result.returncode != 0 else None
                )
            finally:
                os.unlink(temp_file)

        else:
            return ExecuteResponse(
                success=False,
                error=f"Language {request.language} not supported yet"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute code: {e}")
        return ExecuteResponse(
            success=False,
            error=str(e)
        )

@router.post("/sandbox/{sandboxId}/files/{filePath:path}")
async def save_file(sandboxId: str, filePath: str, request: Request):
    """Save a file in a sandbox."""
    try:
        content = await request.body()
        content = content.decode('utf-8')

        # Get the sandbox environment, load from database if needed
        environment = sandbox_service.environments.get(sandboxId)
        if not environment:
            # Try to load from database
            db_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            if db_sandbox:
                # Recreate the environment from database
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
                logger.info(f"Loaded sandbox {sandboxId} from database for file save")
            else:
                raise HTTPException(status_code=404, detail="Sandbox not found")

        # Ensure the file path is within the sandbox directory
        full_path = os.path.join(environment.project_path, filePath)
        sandbox_dir = os.path.abspath(environment.project_path)

        if not os.path.abspath(full_path).startswith(sandbox_dir):
            raise HTTPException(status_code=400, detail="Invalid file path")

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Write the file
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Update sandbox metadata after file save
        try:
            await sandbox_service.update_project_metadata(sandboxId)
            logger.info(f"Updated metadata for sandbox {sandboxId} after file save")
        except Exception as e:
            logger.warning(f"Failed to update metadata for sandbox {sandboxId}: {e}")

        logger.info(f"Saved file {filePath} in sandbox {sandboxId}")
        return {"success": True, "message": "File saved successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

@router.get("/sandbox/{sandboxId}/files/{filePath:path}")
async def read_file(sandboxId: str, filePath: str):
    """Read a file from a sandbox."""
    try:
        # Get the sandbox environment, load from database if needed
        environment = sandbox_service.environments.get(sandboxId)
        if not environment:
            # Try to load from database
            db_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            if db_sandbox:
                # Recreate the environment from database
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
                logger.info(f"Loaded sandbox {sandboxId} from database for file read")
            else:
                raise HTTPException(status_code=404, detail="Sandbox not found")

        # Ensure the file path is within the sandbox directory
        full_path = os.path.join(environment.project_path, filePath)
        sandbox_dir = os.path.abspath(environment.project_path)

        if not os.path.abspath(full_path).startswith(sandbox_dir):
            raise HTTPException(status_code=400, detail="Invalid file path")

        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Read the file
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return FileResponse(success=True, content=content)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read file")

@router.get("/sandbox/files/{sandboxId}")
async def list_files(sandboxId: str):
    """List all files in a sandbox."""
    try:
        # Load environment from database if not in memory
        logger.info(f"Current sandboxes in memory: {list(sandbox_service.environments.keys())}")
        if sandboxId:
            logger.info(f"Loading sandbox {sandboxId} from database for files")
            sandbox_doc = await Sandbox.find_one(Sandbox.sandboxId == sandboxId)
            logger.info(f"Sandbox doc found: {sandbox_doc is not None}")
            if sandbox_doc:
                logger.info(f"Sandbox projectPath: {sandbox_doc.projectPath}")
                # Use saved port or find a new available port
                port = sandbox_doc.port
                if not port:
                    port = sandbox_service.find_available_port()
                # Create environment from database
                config = SandboxConfig(sandbox_doc.sandboxId, sandbox_doc.projectPath, port)
                environment = SandboxEnvironment(
                    sandbox_doc.sandboxId,
                    sandbox_doc.name,
                    sandbox_doc.type
                )
                environment.config = config
                environment.project_path = sandbox_doc.projectPath
                environment.metadata = sandbox_doc.metadata or {}
                environment.status = sandbox_doc.status
                environment.created_at = sandbox_doc.createdAt
                environment.last_activity = sandbox_doc.lastActivity
                sandbox_service.environments[sandboxId] = environment
                logger.info(f"Created environment for sandbox {sandboxId}")
            else:
                logger.error(f"Sandbox {sandboxId} not found in database")
                raise HTTPException(status_code=404, detail="Sandbox not found")

        environment = sandbox_service.environments[sandboxId]

        if not environment.project_path or not os.path.exists(environment.project_path):
            raise HTTPException(status_code=404, detail="Sandbox project path not found")

        # Recursively list all files in the sandbox directory
        files = []
        for root, dirs, filenames in os.walk(environment.project_path):
            # Skip node_modules and other common directories
            dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '__pycache__', '.next']]
            for filename in filenames:
                # Get relative path from sandbox root
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, environment.project_path)
                files.append(rel_path)

        return {
            "success": True,
            "files": files
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")

@router.post("/sandbox/{sandbox_id}/stop")
async def stop_sandbox(sandbox_id: str):
    """Stop a specific sandbox"""
    try:
        await sandbox_service.stop_sandbox(sandbox_id)
        return {
            "success": True,
            "message": f"Sandbox {sandbox_id} stopped successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to stop sandbox {sandbox_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop sandbox")

@router.get("/sandbox/{sandbox_id}/context")
async def get_sandbox_context(sandbox_id: str):
    """Get comprehensive context information for agents about a sandbox"""
    try:
        sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        # Ensure metadata is a dictionary, handle cases where it might be a list or None
        metadata = sandbox.metadata
        if not isinstance(metadata, dict):
            logger.warning(f"Sandbox {sandbox_id} has invalid metadata type: {type(metadata)}, using empty dict")
            metadata = {}

        # Helper function to safely get nested dict values
        def safe_get(obj, key, default=None):
            """Safely get a value from a dict, list, or other object."""
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        # Helper function to safely get nested values with multiple keys
        def safe_nested_get(obj, *keys, default=None):
            """Safely get nested values: safe_nested_get(metadata, 'file_statistics', 'total_files', 0)"""
            current = obj
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key, default)
                else:
                    return default
            return current

        # Comprehensive context for agents
        context = {
            "sandbox": {
                "id": sandbox.sandboxId,
                "name": sandbox.name or "",
                "type": sandbox.type,
                "status": sandbox.status,
                "createdAt": sandbox.createdAt.isoformat(),
                "lastActivity": sandbox.lastActivity.isoformat()
            },
            "project": {
                "type": safe_get(metadata, "project_type", "unknown"),
                "frameworks": safe_get(metadata, "frameworks", []),
                "buildTools": safe_get(metadata, "build_tools", []),
                "entryPoints": safe_get(metadata, "entry_points", [])
            },
            "structure": {
                "fileCount": safe_nested_get(metadata, "file_statistics", "file_count", 0),
                "directoryCount": safe_nested_get(metadata, "project_structure", "total_directories", 0),
                "maxDepth": safe_nested_get(metadata, "project_structure", "max_depth", 0),
                "topLevelItems": safe_nested_get(metadata, "project_structure", "top_level_items", [])
            },
            "dependencies": safe_get(metadata, "dependencies", {}),
            "fileTypes": safe_nested_get(metadata, "file_statistics", "file_categories", {}),
            "size": {
                "totalBytes": safe_nested_get(metadata, "size_analysis", "total_size", 0),
                "formatted": safe_nested_get(metadata, "size_analysis", "total_size_formatted", "0 B"),
                "largestFiles": safe_nested_get(metadata, "size_analysis", "largest_files", [])
            },
            "activity": safe_get(metadata, "recent_activity", {}),
            "fileTree": safe_get(metadata, "file_tree", {}),
            "generatedAt": safe_get(metadata, "generated_at"),
            "lastUpdated": safe_get(metadata, "last_updated")
        }

        return {
            "success": True,
            "context": context
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox context for {sandbox_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get sandbox context")

@router.post("/sandbox/{sandbox_id}/refresh-metadata")
async def refresh_sandbox_metadata(sandbox_id: str):
    """Manually refresh metadata for a specific sandbox."""
    try:
        # Check if sandbox exists
        sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")
        
        # Get or create sandbox environment
        environment = sandbox_service.environments.get(sandbox_id)
        if not environment:
            # Create a minimal environment for metadata update
            from app.sandbox_service import SandboxEnvironment
            environment = SandboxEnvironment(sandbox_id, sandbox.name, sandbox.type)
            environment.project_path = sandbox.projectPath or ""
            environment.metadata = sandbox.metadata or {}
            sandbox_service.environments[sandbox_id] = environment
        
        # Trigger metadata update
        await sandbox_service.update_project_metadata(environment)
        
        # Update database with new metadata
        sandbox.metadata = environment.metadata
        await sandbox.save()
        
        # Get updated sandbox data
        updated_sandbox = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
        
        # Broadcast update to connected clients
        await broadcast_sandbox_update("metadata_updated", {
            "id": updated_sandbox.sandboxId,
            "name": updated_sandbox.name or "",
            "type": updated_sandbox.type,
            "status": updated_sandbox.status,
            "createdAt": updated_sandbox.createdAt.isoformat(),
            "lastActivity": updated_sandbox.lastActivity.isoformat(),
            "metadata": updated_sandbox.metadata
        })
        
        return {
            "success": True,
            "message": f"Metadata refreshed successfully for sandbox {sandbox_id}",
            "metadata": updated_sandbox.metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh metadata for sandbox {sandbox_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh sandbox metadata")

@router.post("/sandbox/stop-others")
async def stop_other_sandboxes(request: StopOthersRequest):
    """Stop all sandboxes except the specified one."""
    try:
        except_id = request.exceptSandboxId
        stopped_count = 0

        # Stop all previews except the specified sandbox
        for sandbox_id, environment in sandbox_service.environments.items():
            if sandbox_id != except_id and environment.preview:
                try:
                    await sandbox_service.stop_preview(sandbox_id)
                    stopped_count += 1
                    logger.info(f"Stopped preview for sandbox {sandbox_id}")
                except Exception as e:
                    logger.warning(f"Failed to stop preview for sandbox {sandbox_id}: {e}")

        return {
            "success": True,
            "message": f"Stopped {stopped_count} other sandboxes",
            "stoppedCount": stopped_count
        }

    except Exception as e:
        logger.error(f"Failed to stop other sandboxes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket connections for real-time updates
active_websocket_connections: List[WebSocket] = []

async def websocket_sandbox_updates(websocket: WebSocket):
    """WebSocket endpoint for real-time sandbox updates."""
    await websocket.accept()
    active_websocket_connections.append(websocket)
    logger.info(f"WebSocket connection established. Total connections: {len(active_websocket_connections)}")

    try:
        # Send initial sandbox list
        sandboxes_data = await get_all_sandboxes()
        await websocket.send_json({
            "type": "initial",
            "sandboxes": sandboxes_data
        })

        # Keep connection alive and listen for messages
        while True:
            try:
                # Wait for any message from client (though we mainly send updates)
                data = await websocket.receive_text()
                # Client can send ping messages to keep connection alive
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                # Connection might be closed, break the loop
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket in active_websocket_connections:
            active_websocket_connections.remove(websocket)
        logger.info(f"WebSocket connection closed. Total connections: {len(active_websocket_connections)}")

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