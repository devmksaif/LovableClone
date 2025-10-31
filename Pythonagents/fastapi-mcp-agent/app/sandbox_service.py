import os
import asyncio
import logging
import shutil
import subprocess
import tempfile
import socket
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import uuid

# ChromaDB integration import
try:
    from app.services.chroma_integration import chroma_integration
    CHROMA_INTEGRATION_AVAILABLE = True
except ImportError:
    CHROMA_INTEGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)

class SandboxConfig:
    def __init__(self, sandbox_id: str, project_path: str, port: int):
        self.id = sandbox_id
        self.project_path = project_path
        self.port = port

class PreviewConfig:
    def __init__(self, url: str, port: int, status: str = "stopped"):
        self.url = url
        self.port = port
        self.status = status

class SandboxEnvironment:
    def __init__(self, sandbox_id: str, name: str = None, sandbox_type: str = "react"):
        self.id = sandbox_id
        self.name = name
        self.type = sandbox_type
        self.status = "creating"
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.metadata: Dict[str, Any] = {}
        self.config: Optional[SandboxConfig] = None
        self.preview: Optional[PreviewConfig] = None
        self.project_path: Optional[str] = None

class SandboxService:
    def __init__(self):
        self.base_path = "/Users/Apple/Desktop/NextLovable/sandboxes"
        self.environments: Dict[str, SandboxEnvironment] = {}
        os.makedirs(self.base_path, exist_ok=True)
        logger.info(f"SandboxService initialized with base path: {self.base_path}")

    def generate_sandbox_id(self) -> str:
        return f"sandbox_{uuid.uuid4().hex[:16]}"

    def find_available_port(self, start_port: int = 30000, max_port: int = 32000) -> int:
        for port in range(start_port, max_port + 1):
            if self.is_port_available(port):
                return port
        raise RuntimeError("No available ports found")

    def is_port_available(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('localhost', port))
                return True
            except OSError:
                return False

    def is_port_listening(self, host: str, port: int) -> bool:
        """Check if a service is actually listening on the given host and port"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)  # 1 second timeout
            try:
                result = sock.connect_ex((host, port))
                return result == 0  # 0 means connection successful
            except socket.error:
                return False

    async def create_sandbox(self, name: str = None, sandbox_type: str = "react",
                           template: str = None, enable_preview: bool = False,
                           metadata: Dict[str, Any] = None, session_id: str = None) -> SandboxEnvironment:

        sandbox_id = self.generate_sandbox_id()
        logger.info(f"Creating sandbox {sandbox_id} of type {sandbox_type}")

        # Create sandbox directory
        sandbox_path = os.path.join(self.base_path, sandbox_id)
        os.makedirs(sandbox_path, exist_ok=True)

        # Find available port
        port = self.find_available_port()

        # Create sandbox config
        config = SandboxConfig(sandbox_id, sandbox_path, port)

        # Generate comprehensive metadata
        generated_metadata = {
            "created_at": datetime.now().isoformat(),
            "sandbox_type": sandbox_type,
            "template": template or "default",
            "port": port,
            "session_id": session_id,
            "project_structure": [],
            "dependencies": {},
            "environment_variables": {},
            "build_status": "pending",
            "last_build_time": None,
            "file_count": 0,
            "total_size_bytes": 0
        }
        
        # Merge with provided metadata
        if metadata:
            generated_metadata.update(metadata)

        # Create environment
        environment = SandboxEnvironment(sandbox_id, name, sandbox_type)
        environment.config = config
        environment.project_path = sandbox_path
        environment.metadata = generated_metadata
        environment.status = "ready"

        # Store environment before initializing (needed for preview start)
        self.environments[sandbox_id] = environment

        # Initialize project structure
        await self.initialize_project_structure(environment, template)
        
        # Update metadata with project structure information
        await self.update_project_metadata(environment)

        # Start preview if requested
        if enable_preview:
            # Stop all other running previews first
            await self.stop_all_other_previews(sandbox_id)
            await self.start_preview(sandbox_id)

        # Index all sandbox files in ChromaDB (excluding node_modules)
        if CHROMA_INTEGRATION_AVAILABLE:
            try:
                await self.index_sandbox_files(environment)
                logger.info(f"Successfully indexed sandbox {sandbox_id} files in ChromaDB")
            except Exception as e:
                logger.warning(f"Failed to index sandbox {sandbox_id} files in ChromaDB: {e}")

        logger.info(f"Sandbox {sandbox_id} created successfully")

        return environment

    async def initialize_project_structure(self, environment: SandboxEnvironment, template: str = None):
        """Initialize project structure based on type"""
        if environment.type == "react":
            await self.initialize_react_project(environment, template)
        elif environment.type == "vue":
            await self.initialize_vue_project(environment, template)
        elif environment.type == "vanilla":
            await self.initialize_vanilla_project(environment, template)
        else:
            await self.initialize_vanilla_project(environment, template)

    async def index_sandbox_files(self, environment: SandboxEnvironment):
        """Index all sandbox files in ChromaDB, excluding node_modules"""
        if not CHROMA_INTEGRATION_AVAILABLE or not environment.project_path:
            return

        try:
            # Index the entire sandbox directory, excluding node_modules
            await chroma_integration.index_directory(
                environment.project_path,
                collection_name=f"sandbox_{environment.id}"
            )
            logger.info(f"Successfully indexed sandbox {environment.id} directory in ChromaDB")
        except Exception as e:
            logger.error(f"Failed to index sandbox {environment.id} directory: {e}")
            raise

    async def initialize_react_project(self, environment: SandboxEnvironment, template: str = None):
        """Initialize a React project with Vite"""
        project_path = environment.project_path

        # Create package.json for Vite + React
        package_json = {
            "name": environment.name or environment.id,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "start": "vite",
                "build": "vite build",
                "preview": "vite preview"
            },
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0"
            },
            "devDependencies": {
                "@types/react": "^18.2.0",
                "@types/react-dom": "^18.2.0",
                "@vitejs/plugin-react": "^4.0.0",
                "vite": "^4.3.0"
            }
        }

        with open(os.path.join(project_path, "package.json"), "w") as f:
            import json
            json.dump(package_json, f, indent=2)

        # Create vite.config.js
        vite_config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: process.env.PORT || 3000
  }
})
"""

        with open(os.path.join(project_path, "vite.config.js"), "w") as f:
            f.write(vite_config)

        # Create index.html
        index_html = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>React + Vite</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

        with open(os.path.join(project_path, "index.html"), "w") as f:
            f.write(index_html)

        # Create src directory and files
        src_path = os.path.join(project_path, "src")
        os.makedirs(src_path, exist_ok=True)

        # Create src/main.jsx
        main_jsx = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
"""

        with open(os.path.join(src_path, "main.jsx"), "w") as f:
            f.write(main_jsx)

        # Create src/App.jsx
        app_jsx = """import React, { useState } from 'react'
import './App.css'

function App() {
  const [count, setCount] = useState(0)

  return (
    <div className="App">
      <header className="App-header">
        <h1>React + Vite Sandbox</h1>
        <p>Edit <code>src/App.jsx</code> and save to reload.</p>
        <div className="card">
          <button onClick={() => setCount((count) => count + 1)}>
            count is {count}
          </button>
          <p>
            Edit <code>src/App.jsx</code> and save to test HMR
          </p>
        </div>
      </header>
    </div>
  )
}

export default App
"""

        with open(os.path.join(src_path, "App.jsx"), "w") as f:
            f.write(app_jsx)

        # Create src/App.css
        app_css = """#root {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  text-align: center;
}

.App {
  text-align: center;
}

.App-header {
  background-color: #f9f9f9;
  padding: 2rem;
  border-radius: 8px;
  margin-bottom: 2rem;
}

.card {
  padding: 2em;
}

button {
  border-radius: 8px;
  border: 1px solid transparent;
  padding: 0.6em 1.2em;
  font-size: 1em;
  font-weight: 500;
  font-family: inherit;
  background-color: #1a1a1a;
  color: white;
  cursor: pointer;
  transition: border-color 0.25s;
}

button:hover {
  border-color: #646cff;
}

button:focus,
button:focus-visible {
  outline: 4px auto -webkit-focus-ring-color;
}
"""

        with open(os.path.join(src_path, "App.css"), "w") as f:
            f.write(app_css)

        # Create src/index.css
        index_css = """body {
  margin: 0;
  display: flex;
  place-items: center;
  min-width: 320px;
  min-height: 100vh;
}

#root {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  text-align: center;
}

code {
  background-color: #f4f4f4;
  padding: 0.2em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}
"""

        with open(os.path.join(src_path, "index.css"), "w") as f:
            f.write(index_css)

    async def initialize_vue_project(self, environment: SandboxEnvironment, template: str = None):
        """Initialize a Vue project with Vite"""
        project_path = environment.project_path

        # Create package.json for Vue + Vite
        package_json = {
            "name": "vue-sandbox",
            "private": True,
            "version": "0.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "start": "vite",
                "build": "vite build",
                "preview": "vite preview"
            },
            "dependencies": {
                "vue": "^3.4.0"
            },
            "devDependencies": {
                "@vitejs/plugin-vue": "^5.0.0",
                "vite": "^5.0.0"
            }
        }

        with open(os.path.join(project_path, "package.json"), "w") as f:
            import json
            json.dump(package_json, f, indent=2)

        # Create vite.config.js
        vite_config = """import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: process.env.PORT || 3000
  }
})
"""

        with open(os.path.join(project_path, "vite.config.js"), "w") as f:
            f.write(vite_config)

        # Create index.html
        index_html = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Vue + Vite</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
"""

        with open(os.path.join(project_path, "index.html"), "w") as f:
            f.write(index_html)

        # Create src directory and files
        src_path = os.path.join(project_path, "src")
        os.makedirs(src_path, exist_ok=True)

        # Create src/main.js
        main_js = """import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
"""

        with open(os.path.join(src_path, "main.js"), "w") as f:
            f.write(main_js)

        # Create src/App.vue
        app_vue = """<template>
  <div id="app">
    <h1>Vue + Vite Sandbox</h1>
    <p>Edit <code>src/App.vue</code> and save to reload.</p>
    <div class="card">
      <button @click="count++">count is {{ count }}</button>
      <p>
        Edit <code>src/App.vue</code> and save to test HMR
      </p>
    </div>
  </div>
</template>

<script>
export default {
  name: 'App',
  data() {
    return {
      count: 0
    }
  }
}
</script>

<style scoped>
#app {
  font-family: Avenir, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}

.card {
  padding: 2em;
}

button {
  font-size: 1em;
  padding: 0.6em 1.2em;
  border: 1px solid #646cff;
  border-radius: 8px;
  background-color: #f9f9f9;
  cursor: pointer;
  transition: border-color 0.25s;
}

button:hover {
  border-color: #646cff;
}
</style>
"""

        with open(os.path.join(src_path, "App.vue"), "w") as f:
            f.write(app_vue)

        # Create src/index.css
        index_css = """body {
  margin: 0;
  display: flex;
  place-items: center;
  min-width: 320px;
  min-height: 100vh;
}

#app {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  text-align: center;
}
"""

        with open(os.path.join(src_path, "index.css"), "w") as f:
            f.write(index_css)

    async def initialize_vanilla_project(self, environment: SandboxEnvironment, template: str = None):
        """Initialize a vanilla JavaScript project"""
        project_path = environment.project_path

        # Create basic HTML structure
        index_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vanilla JS App</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f0f0f0;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello, World!</h1>
        <p>This is a vanilla JavaScript application.</p>
        <div id="app"></div>
    </div>
    <script src="script.js"></script>
</body>
</html>"""

        with open(os.path.join(project_path, "index.html"), "w") as f:
            f.write(index_html)

        # Create basic JavaScript file
        script_js = """// Vanilla JavaScript Application
document.addEventListener('DOMContentLoaded', function() {
    const app = document.getElementById('app');

    // Create a simple interactive element
    const button = document.createElement('button');
    button.textContent = 'Click me!';
    button.style.padding = '10px 20px';
    button.style.backgroundColor = '#007bff';
    button.style.color = 'white';
    button.style.border = 'none';
    button.style.borderRadius = '4px';
    button.style.cursor = 'pointer';

    let clickCount = 0;
    button.addEventListener('click', function() {
        clickCount++;
        const message = document.createElement('p');
        message.textContent = `Button clicked ${clickCount} time(s)!`;
        message.style.marginTop = '10px';
        app.appendChild(message);
    });

    app.appendChild(button);
});"""

        with open(os.path.join(project_path, "script.js"), "w") as f:
            f.write(script_js)

    async def start_preview(self, sandbox_id: str) -> PreviewConfig:
        """Start preview for a sandbox"""
        if sandbox_id not in self.environments:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        environment = self.environments[sandbox_id]

        if not environment.config:
            raise ValueError(f"Sandbox {sandbox_id} has no configuration")

        # Check if the configured port is available, if not find a new one with retry logic
        port = environment.config.port
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not self.is_port_available(port):
                    logger.info(f"Port {port} is not available for {sandbox_id}, trying new port (attempt {retry_count + 1})")
                    port = self.find_available_port()
                    # Update the config with the new port
                    environment.config.port = port
                    retry_count += 1
                    continue
                
                # Try to start the server to see if port is really available
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_socket.bind(('localhost', port))
                test_socket.close()
                break  # Port is available, break out of retry loop
                
            except OSError as e:
                if e.errno == 48:  # Address already in use
                    logger.warning(f"Port {port} already in use (errno 48) for {sandbox_id}, trying new port (attempt {retry_count + 1})")
                    port = self.find_available_port()
                    environment.config.port = port
                    retry_count += 1
                else:
                    raise  # Re-raise other OSError types
        
        if retry_count >= max_retries:
            raise Exception(f"Failed to find available port for sandbox {sandbox_id} after {max_retries} attempts")

        project_path = environment.config.project_path
        preview = PreviewConfig(f"http://localhost:{port}", port, "running")
        environment.preview = preview
        environment.status = "running"

        # Update status in database
        try:
            from app.database import Sandbox
            await Sandbox.find_one(Sandbox.sandboxId == sandbox_id).update({"$set": {"status": "running", "port": port}})
        except Exception as e:
            logger.warning(f"Failed to update sandbox status in database: {e}")

        # Install dependencies and start the development server
        import subprocess
        import threading

        def start_dev_server():
            try:
                os.chdir(project_path)
                
                # Install dependencies
                logger.info(f"Installing dependencies for {sandbox_id}")
                install_success = False
                
                # Try pnpm first if lockfile exists
                if os.path.exists("pnpm-lock.yaml"):
                    try:
                        result = subprocess.run(["pnpm", "install"], check=True, capture_output=True, text=True, timeout=300)
                        logger.info(f"Successfully installed dependencies with pnpm for {sandbox_id}")
                        install_success = True
                    except (subprocess.CalledProcessError, FileNotFoundError) as e:
                        logger.warning(f"pnpm install failed for {sandbox_id}: {e}")
                
                # Try yarn if no pnpm lockfile or pnpm failed
                if not install_success and os.path.exists("yarn.lock"):
                    try:
                        result = subprocess.run(["yarn", "install"], check=True, capture_output=True, text=True, timeout=300)
                        logger.info(f"Successfully installed dependencies with yarn for {sandbox_id}")
                        install_success = True
                    except (subprocess.CalledProcessError, FileNotFoundError) as e:
                        logger.warning(f"yarn install failed for {sandbox_id}: {e}")
                
                # Fall back to npm
                if not install_success:
                    try:
                        result = subprocess.run(["pnpm", "install"], check=True, capture_output=True, text=True, timeout=300)
                        logger.info(f"Successfully installed dependencies with npm for {sandbox_id}")
                        install_success = True
                    except (subprocess.CalledProcessError, FileNotFoundError) as e:
                        logger.error(f"npm install failed for {sandbox_id}: {e}")
                        logger.error(f"stdout: {e.stdout}")
                        logger.error(f"stderr: {e.stderr}")
                        raise Exception(f"Failed to install dependencies: {e}")
                
                if not install_success:
                    raise Exception("All package managers failed to install dependencies")
                
                # Start development server
                logger.info(f"Starting development server for {sandbox_id} on port {port}")
                if environment.type in ["react", "vue"]:
                    # For React and Vue, use the start script which should be configured to use the right port
                    env = os.environ.copy()
                    env["PORT"] = str(port)
                    # Use Popen to start asynchronously
                    process = subprocess.Popen(["pnpm", "start"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    logger.info(f"Started {environment.type} dev server for {sandbox_id} with PID {process.pid}")
                    # Store the process for later cleanup
                    environment.metadata["dev_server_pid"] = process.pid
                else:
                    # For other types, start a simple HTTP server
                    import http.server
                    import socketserver
                    handler = http.server.SimpleHTTPRequestHandler
                    with socketserver.TCPServer(("", port), handler) as httpd:
                        logger.info(f"Serving {sandbox_id} on port {port}")
                        httpd.serve_forever()
                        
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to start dev server for {sandbox_id}: {e}")
                logger.error(f"stdout: {e.stdout}")
                logger.error(f"stderr: {e.stderr}")
            except Exception as e:
                logger.error(f"Failed to start preview server for {sandbox_id}: {e}")

        server_thread = threading.Thread(target=start_dev_server, daemon=True)
        server_thread.start()

        # Wait for the server to be ready by polling the port
        logger.info(f"Waiting for development server to be ready on port {port}")
        max_wait_time = 60  # seconds - increased from 30
        wait_start = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - wait_start < max_wait_time:
            if self.is_port_listening('localhost', port):
                logger.info(f"Development server is ready on port {port} for sandbox {sandbox_id}")
                break
            await asyncio.sleep(0.5)  # Check every 500ms
        else:
            logger.warning(f"Development server for sandbox {sandbox_id} did not become ready within {max_wait_time} seconds")

        logger.info(f"Started preview for sandbox {sandbox_id} on port {port}")
        return preview

    async def get_preview(self, sandbox_id: str) -> Optional[PreviewConfig]:
        """Get preview configuration for a sandbox"""
        if sandbox_id not in self.environments:
            return None

        environment = self.environments[sandbox_id]
        return environment.preview

    async def stop_preview(self, sandbox_id: str):
        """Stop preview for a sandbox"""
        if sandbox_id not in self.environments:
            raise ValueError(f"Sandbox {sandbox_id} not found")

        environment = self.environments[sandbox_id]
        if environment.preview:
            # Kill the development server process if it exists
            if "dev_server_pid" in environment.metadata:
                try:
                    import signal
                    os.kill(environment.metadata["dev_server_pid"], signal.SIGTERM)
                    logger.info(f"Killed dev server process {environment.metadata['dev_server_pid']} for sandbox {sandbox_id}")
                    del environment.metadata["dev_server_pid"]
                except ProcessLookupError:
                    logger.warning(f"Process {environment.metadata['dev_server_pid']} not found for sandbox {sandbox_id}")
                except Exception as e:
                    logger.error(f"Failed to kill dev server process for sandbox {sandbox_id}: {e}")
            
            # Wait for port to be freed
            if environment.config and environment.config.port:
                await self.wait_for_port_free(environment.config.port, sandbox_id)
            
            environment.preview.status = "stopped"
            logger.info(f"Stopped preview for sandbox {sandbox_id}")
        else:
            logger.warning(f"No preview running for sandbox {sandbox_id}")

    async def wait_for_port_free(self, port: int, sandbox_id: str, timeout: int = 10):
        """Wait for a port to be freed after stopping processes"""
        logger.info(f"Waiting for port {port} to be freed for sandbox {sandbox_id}")
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            if not self.is_port_listening('localhost', port):
                logger.info(f"Port {port} is now free for sandbox {sandbox_id}")
                return
            await asyncio.sleep(0.5)
        
        logger.warning(f"Port {port} did not become free within {timeout} seconds for sandbox {sandbox_id}")

    async def stop_all_other_previews(self, except_sandbox_id: str):
        """Stop all previews except for the specified sandbox"""
        stopped_count = 0
        logger.info(f"Stopping all other sandboxes except {except_sandbox_id}")
        
        try:
            from app.database import Sandbox
            # Find all running sandboxes except the current one
            running_sandboxes = await Sandbox.find(Sandbox.status == "running", Sandbox.sandboxId != except_sandbox_id).to_list()
            
            for sandbox in running_sandboxes:
                try:
                    logger.info(f"Stopping sandbox {sandbox.sandboxId} completely")
                    await self.stop_sandbox(sandbox.sandboxId)
                    stopped_count += 1
                    logger.info(f"Stopped sandbox {sandbox.sandboxId} to allow new sandbox {except_sandbox_id}")
                except Exception as e:
                    logger.warning(f"Failed to stop sandbox {sandbox.sandboxId}: {e}")
        
        except Exception as e:
            logger.error(f"Error stopping other sandboxes: {e}")
        
        if stopped_count > 0:
            logger.info(f"Stopped {stopped_count} other sandboxes for {except_sandbox_id}")
        else:
            logger.info(f"No other sandboxes were stopped for {except_sandbox_id}")

    async def stop_sandbox(self, sandbox_id: str):
        """Stop a sandbox (stop processes but keep files)"""
        environment = None
        
        # Try to get environment from memory first
        if sandbox_id in self.environments:
            environment = self.environments[sandbox_id]
        else:
            # If not in memory, try to load from database
            try:
                from app.database import Sandbox
                sandbox_doc = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
                if sandbox_doc:
                    # Create a minimal environment for stopping
                    environment = SandboxEnvironment(sandbox_id, sandbox_doc.name, sandbox_doc.type)
                    environment.status = sandbox_doc.status
                    environment.metadata = sandbox_doc.metadata or {}
                    if sandbox_doc.port:
                        environment.config = SandboxConfig(sandbox_id, sandbox_doc.projectPath or "", sandbox_doc.port)
                    # Add to environments for future reference
                    self.environments[sandbox_id] = environment
                else:
                    raise ValueError(f"Sandbox {sandbox_id} not found in database")
            except Exception as e:
                logger.error(f"Failed to load sandbox {sandbox_id} from database: {e}")
                raise ValueError(f"Sandbox {sandbox_id} not found")

        # Stop preview if running
        if environment.preview and environment.preview.status == "running":
            await self.stop_preview(sandbox_id)

        # Kill any other running processes associated with this sandbox
        if "dev_server_pid" in environment.metadata:
            try:
                import signal
                os.kill(environment.metadata["dev_server_pid"], signal.SIGTERM)
                logger.info(f"Killed dev server process {environment.metadata['dev_server_pid']} for sandbox {sandbox_id}")
                del environment.metadata["dev_server_pid"]
            except ProcessLookupError:
                logger.warning(f"Process {environment.metadata['dev_server_pid']} not found for sandbox {sandbox_id}")
            except Exception as e:
                logger.error(f"Failed to kill dev server process for sandbox {sandbox_id}: {e}")

        # Kill any processes that might be using the sandbox port
        if environment.config and environment.config.port:
            try:
                import subprocess
                # Find processes using the port
                result = subprocess.run(['lsof', '-ti', f':{environment.config.port}'], 
                                      capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                            logger.info(f"Killed process {pid} using port {environment.config.port} for sandbox {sandbox_id}")
                        except (ProcessLookupError, ValueError):
                            pass  # Process might not exist
                        except Exception as e:
                            logger.error(f"Failed to kill process {pid}: {e}")
            except Exception as e:
                logger.warning(f"Failed to find/kill processes using port {environment.config.port}: {e}")

        # Wait for port to be freed
        if environment.config and environment.config.port:
            await self.wait_for_port_free(environment.config.port, sandbox_id)

        # Mark sandbox as stopped
        environment.status = "stopped"
        
        # Update status in database
        try:
            from app.database import Sandbox
            await Sandbox.find_one(Sandbox.sandboxId == sandbox_id).update({"$set": {"status": "stopped", "lastActivity": datetime.utcnow()}})
        except Exception as e:
            logger.warning(f"Failed to update sandbox status in database: {e}")
        
        logger.info(f"Stopped sandbox {sandbox_id}")

    async def delete_sandbox(self, sandbox_id: str):
        """Delete a sandbox"""
        environment = None
        
        # Try to get environment from memory first
        if sandbox_id in self.environments:
            environment = self.environments[sandbox_id]
        else:
            # If not in memory, try to load from database
            try:
                from app.database import Sandbox
                sandbox_doc = await Sandbox.find_one(Sandbox.sandboxId == sandbox_id)
                if sandbox_doc:
                    # Create a minimal environment for deletion
                    from app.sandbox_service import SandboxEnvironment, SandboxConfig
                    environment = SandboxEnvironment(sandbox_id, sandbox_doc.name, sandbox_doc.type)
                    environment.project_path = sandbox_doc.projectPath
                    environment.metadata = sandbox_doc.metadata or {}
                    if sandbox_doc.port:
                        environment.config = SandboxConfig(sandbox_id, sandbox_doc.projectPath or "", sandbox_doc.port)
                    # Add to environments for future reference
                    self.environments[sandbox_id] = environment
                else:
                    raise ValueError(f"Sandbox {sandbox_id} not found in database")
            except Exception as e:
                logger.error(f"Failed to load sandbox {sandbox_id} from database: {e}")
                raise ValueError(f"Sandbox {sandbox_id} not found")

        # Stop the sandbox if it's running
        if environment.status == "running":
            await self.stop_sandbox(sandbox_id)
            
        # Wait a bit for processes to fully terminate
        await asyncio.sleep(1)

        # Clean up directory
        if environment.project_path and os.path.exists(environment.project_path):
            try:
                shutil.rmtree(environment.project_path)
                logger.info(f"Deleted directory {environment.project_path} for sandbox {sandbox_id}")
            except OSError as e:
                if e.errno == 66:  # Directory not empty
                    logger.warning(f"Directory {environment.project_path} not empty, attempting force delete")
                    # Try to force delete by removing files individually
                    try:
                        for root, dirs, files in os.walk(environment.project_path, topdown=False):
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
                        os.rmdir(environment.project_path)
                        logger.info(f"Force deleted directory {environment.project_path} for sandbox {sandbox_id}")
                    except Exception as force_e:
                        logger.error(f"Failed to force delete directory {environment.project_path}: {force_e}")
                        # Don't raise error, continue with cleanup
                else:
                    logger.error(f"Failed to delete directory {environment.project_path}: {e}")
                    # Don't raise error for directory deletion failures

        # Remove from environments
        if sandbox_id in self.environments:
            del self.environments[sandbox_id]

        # Remove from database
        try:
            from app.database import Sandbox
            await Sandbox.find_one(Sandbox.sandboxId == sandbox_id).delete()
            logger.info(f"Deleted sandbox {sandbox_id} from database")
        except Exception as e:
            logger.warning(f"Failed to delete sandbox {sandbox_id} from database: {e}")

        logger.info(f"Deleted sandbox {sandbox_id}")

    def get_all_sandboxes(self) -> List[SandboxEnvironment]:
        """Get all sandboxes"""
        return list(self.environments.values())

    async def update_project_metadata(self, environment: SandboxEnvironment):
        """Update sandbox metadata with comprehensive project information."""
        try:
            # Import the metadata generator
            from app.utils.sandbox_metadata import generate_sandbox_metadata
            
            # Generate comprehensive metadata
            project_metadata = generate_sandbox_metadata(environment.project_path)
            
            # Update environment metadata with generated information
            environment.metadata.update({
                "project_analysis": project_metadata,
                "last_metadata_update": datetime.now().isoformat(),
                "metadata_version": "1.0"
            })
            
            # Update basic stats in the main metadata
            if "file_statistics" in project_metadata:
                environment.metadata["file_count"] = project_metadata["file_statistics"].get("file_count", 0)
                environment.metadata["total_size_bytes"] = project_metadata["file_statistics"].get("total_size", 0)
            
            if "dependencies" in project_metadata:
                environment.metadata["dependencies"] = project_metadata["dependencies"]
            
            if "project_type" in project_metadata:
                environment.metadata["detected_project_type"] = project_metadata["project_type"]
            
            if "frameworks" in project_metadata:
                environment.metadata["frameworks"] = project_metadata["frameworks"]
            
            if "entry_points" in project_metadata:
                environment.metadata["entry_points"] = project_metadata["entry_points"]
            
            logger.info(f"Updated metadata for sandbox {environment.id}")
            
        except Exception as e:
            logger.error(f"Failed to update metadata for sandbox {environment.id}: {e}")
            # Don't fail sandbox creation if metadata generation fails
            environment.metadata["metadata_error"] = str(e)

# Global instance
sandbox_service = SandboxService()