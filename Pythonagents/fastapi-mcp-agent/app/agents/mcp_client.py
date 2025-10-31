#!/usr/bin/env python3
"""
MCP Client using langchain-mcp-adapters for proper MCP tool integration.
"""

import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection
from langchain_core.tools import BaseTool
from .utils import get_project_folder

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPClientManager:
    """Manager for MCP client connections and tool access."""
    
    def __init__(self):
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: List[BaseTool] = []
        self.initialized = False
        self.tools_cache: Optional[List[BaseTool]] = None
        self.cache_timestamp: float = 0
        self.cache_ttl: int = 300  # Cache tools for 5 minutes
    
    async def initialize(self) -> None:
        """Initialize the MCP client with the server."""
        if self.initialized and self.client is not None:
            logger.debug("MCP client already initialized, skipping")
            return
            
        try:
            logger.info("Initializing MCP client...")
            
            # Get the current project folder (sandbox path)
            try:
                project_path = get_project_folder()
                logger.info(f"Setting MCP project path to: {project_path}")
                # Set environment variable for the MCP server
                os.environ["MCP_PROJECT_PATH"] = project_path
            except Exception as e:
                logger.warning(f"Could not get project folder: {e}, using current directory")
                os.environ["MCP_PROJECT_PATH"] = os.getcwd()
            
            # Create stdio connection to the MCP server with proper config
            server_config = {
                "transport": "stdio",
                "command": "python",
                "args": [os.path.join(os.path.dirname(__file__), "..", "..", "mcp_server.py")],  # Absolute path to mcp_server.py
                "cwd": os.environ["MCP_PROJECT_PATH"],
                "env": {
                    **os.environ,
                    "MCP_PROJECT_PATH": os.environ["MCP_PROJECT_PATH"]
                }
            }
            stdio_connection = StdioConnection(server_config)
            
            # Create the MCP client with the connection
            connections = {"mcp_server": stdio_connection}
            self.client = MultiServerMCPClient(connections=connections)
            
            self.initialized = True
            logger.info("MCP client initialized successfully")
            
        except Exception as e:
            logger.warning(f"Failed to initialize MCP client (continuing without MCP): {e}")
            self.client = None
            self.initialized = False
            # Don't re-raise - allow the system to continue without MCP tools
    
    async def get_tools(self) -> List[BaseTool]:
        """Get the available MCP tools with caching and error handling."""
        import time
        
        # Check cache first
        current_time = time.time()
        if (self.tools_cache is not None and 
            current_time - self.cache_timestamp < self.cache_ttl):
            logger.debug(f"Returning cached MCP tools ({len(self.tools_cache)} tools)")
            return self.tools_cache
        
        try:
            if self.client is None:
                await self.initialize()
            
            # Get tools from the MCP client
            self.tools_cache = await self.client.get_tools()
            self.cache_timestamp = current_time
            
            logger.info(f"Loaded {len(self.tools_cache)} MCP tools from server (cached for {self.cache_ttl}s)")
            return self.tools_cache
            
        except Exception as e:
            # Log the error but don't crash - return empty list to allow agent to continue
            logger.warning(f"MCP tools unavailable (continuing without MCP tools): {e}")
            # Cache empty list for a shorter time to retry periodically
            self.tools_cache = []
            self.cache_timestamp = current_time
            self.cache_ttl = 60  # Retry MCP connection every 60 seconds
            return []
    
    async def cleanup(self) -> None:
        """Clean up MCP client connections."""
        if self.client:
            # The MultiServerMCPClient handles cleanup automatically
            self.client = None


# Global MCP client instance
mcp_client_manager = MCPClientManager()


async def get_mcp_tools() -> List[BaseTool]:
    """Get MCP tools for use in agents."""
    try:
        return await mcp_client_manager.get_tools()
    except Exception as e:
        logger.warning(f"MCP tools unavailable (continuing without MCP tools): {e}")
        return []


async def initialize_mcp_client() -> None:
    """Initialize the global MCP client."""
    try:
        await mcp_client_manager.initialize()
    except Exception as e:
        logger.warning(f"MCP client initialization failed (continuing without MCP): {e}")


async def cleanup_mcp_client() -> None:
    """Cleanup the global MCP client."""
    await mcp_client_manager.cleanup()