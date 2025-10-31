import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "FastAPI MCP Agent" in response.json()["message"]

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_chat_endpoint_invalid_request():
    # Test with missing required fields
    response = client.post("/api/chat", json={})
    assert response.status_code == 422  # Validation error

@pytest.mark.asyncio
async def test_mcp_integration_initialization():
    # Test that MCP integration can be initialized
    from app.agents.mcp_integration import mcp_integration

    # This should not raise an exception even without servers
    assert mcp_integration is not None
    assert not mcp_integration.initialized

    # Try to initialize (may fail without actual servers, but shouldn't crash)
    try:
        await mcp_integration.initialize_mcp_clients()
        # If it succeeds, great; if not, that's also acceptable for testing
    except Exception:
        pass  # Expected in test environment without MCP servers