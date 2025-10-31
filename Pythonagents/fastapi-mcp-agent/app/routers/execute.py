import logging
import os
import subprocess
import tempfile
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

router = APIRouter()

class ExecuteRequest(BaseModel):
    code: str
    language: str
    fileName: Optional[str] = None

class ExecuteResponse(BaseModel):
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# In-memory storage for sandbox execution environments
execution_envs: Dict[str, Dict[str, Any]] = {}

@router.post("/execute/{sandbox_id}", response_model=ExecuteResponse)
async def execute_code(
    request: ExecuteRequest,
    sandbox_id: str = Path(..., title="Sandbox ID")
):
    """Execute code in a sandbox environment."""
    try:
        logger.info(f"Executing {request.language} code in sandbox {sandbox_id}")

        # Create execution environment for sandbox if it doesn't exist
        if sandbox_id not in execution_envs:
            execution_envs[sandbox_id] = {
                "working_dir": f"/tmp/sandbox_{sandbox_id}",
                "files": {}
            }
            os.makedirs(execution_envs[sandbox_id]["working_dir"], exist_ok=True)

        env = execution_envs[sandbox_id]

        if request.language.lower() == "python":
            return await execute_python_code(request.code, env)
        elif request.language.lower() == "javascript":
            return await execute_javascript_code(request.code, env)
        elif request.language.lower() == "typescript":
            return await execute_typescript_code(request.code, env)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported language: {request.language}")

    except Exception as e:
        logger.error(f"Failed to execute code in sandbox {sandbox_id}: {e}")
        return ExecuteResponse(success=False, error=str(e))

@router.get("/execute/{sandbox_id}")
async def get_execution_file(
    sandbox_id: str = Path(..., title="Sandbox ID"),
    filePath: str = None
):
    """Get file content from sandbox execution environment."""
    try:
        if not filePath:
            raise HTTPException(status_code=400, detail="filePath parameter is required")

        if sandbox_id not in execution_envs:
            raise HTTPException(status_code=404, detail="Sandbox execution environment not found")

        env = execution_envs[sandbox_id]
        full_path = os.path.join(env["working_dir"], filePath)

        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")

        with open(full_path, 'r') as f:
            content = f.read()

        return {
            "success": True,
            "content": content,
            "filePath": filePath
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file from sandbox {sandbox_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file")

async def execute_python_code(code: str, env: Dict[str, Any]) -> ExecuteResponse:
    """Execute Python code."""
    try:
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', dir=env["working_dir"], delete=False) as f:
            f.write(code)
            temp_file = f.name

        # Execute the code
        result = subprocess.run(
            ['python3', temp_file],
            capture_output=True,
            text=True,
            cwd=env["working_dir"],
            timeout=30
        )

        # Clean up temp file
        os.unlink(temp_file)

        return ExecuteResponse(
            success=result.returncode == 0,
            result={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        )

    except subprocess.TimeoutExpired:
        return ExecuteResponse(success=False, error="Code execution timed out")
    except Exception as e:
        return ExecuteResponse(success=False, error=f"Execution error: {str(e)}")

async def execute_javascript_code(code: str, env: Dict[str, Any]) -> ExecuteResponse:
    """Execute JavaScript code."""
    try:
        # Create a temporary file for the code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', dir=env["working_dir"], delete=False) as f:
            f.write(code)
            temp_file = f.name

        # Execute the code using Node.js
        result = subprocess.run(
            ['node', temp_file],
            capture_output=True,
            text=True,
            cwd=env["working_dir"],
            timeout=30
        )

        # Clean up temp file
        os.unlink(temp_file)

        return ExecuteResponse(
            success=result.returncode == 0,
            result={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        )

    except subprocess.TimeoutExpired:
        return ExecuteResponse(success=False, error="Code execution timed out")
    except FileNotFoundError:
        return ExecuteResponse(success=False, error="Node.js not found. Please install Node.js to execute JavaScript code.")
    except Exception as e:
        return ExecuteResponse(success=False, error=f"Execution error: {str(e)}")

async def execute_typescript_code(code: str, env: Dict[str, Any]) -> ExecuteResponse:
    """Execute TypeScript code by compiling to JavaScript first."""
    try:
        # Create a temporary file for the TypeScript code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', dir=env["working_dir"], delete=False) as f:
            f.write(code)
            temp_file = f.name

        # Compile TypeScript to JavaScript
        js_file = temp_file.replace('.ts', '.js')
        compile_result = subprocess.run(
            ['npx', 'tsc', '--target', 'ES2020', '--module', 'commonjs', temp_file, '--outFile', js_file],
            capture_output=True,
            text=True,
            cwd=env["working_dir"],
            timeout=30
        )

        if compile_result.returncode != 0:
            os.unlink(temp_file)
            return ExecuteResponse(
                success=False,
                error=f"TypeScript compilation failed: {compile_result.stderr}"
            )

        # Execute the compiled JavaScript
        result = subprocess.run(
            ['node', js_file],
            capture_output=True,
            text=True,
            cwd=env["working_dir"],
            timeout=30
        )

        # Clean up temp files
        os.unlink(temp_file)
        if os.path.exists(js_file):
            os.unlink(js_file)

        return ExecuteResponse(
            success=result.returncode == 0,
            result={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        )

    except subprocess.TimeoutExpired:
        return ExecuteResponse(success=False, error="Code execution timed out")
    except FileNotFoundError:
        return ExecuteResponse(success=False, error="TypeScript compiler (tsc) not found. Please install TypeScript globally.")
    except Exception as e:
        return ExecuteResponse(success=False, error=f"Execution error: {str(e)}")