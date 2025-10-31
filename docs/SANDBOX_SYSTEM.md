# Sandbox Environment System

This document explains how to use the sandboxed environment system for running React, Vue, and vanilla JavaScript applications in isolated containers, similar to Lovable.

## Overview

The sandbox system provides:
- **Isolated Execution**: Each sandbox runs in its own isolated environment
- **File System Isolation**: Secure file operations within sandbox boundaries
- **Live Preview**: Real-time preview of applications with hot reload
- **Code Execution**: Safe execution of JavaScript code in isolated containers
- **React App Builder**: Generate complete React applications with routing, state management, and styling

## Architecture

### Core Components

1. **SandboxManager** (`lib/sandbox/sandbox-manager.ts`)
   - Creates and manages sandboxed environments
   - Handles port allocation and resource management
   - Provides file system operations within sandboxes

2. **SandboxExecutionService** (`lib/sandbox/execution-service.ts`)
   - Executes code in isolated environments
   - Supports multiple languages (JavaScript, TypeScript, Python)
   - Implements security checks and timeouts

3. **ReactAppBuilder** (`lib/sandbox/react-builder.ts`)
   - Generates complete React applications
   - Supports routing, state management (Redux), and styling
   - Creates modern, responsive applications

4. **SandboxPreviewService** (`lib/sandbox/preview-service.ts`)
   - Manages development servers for live previews
   - Generates secure iframe containers
   - Handles port management and server lifecycle

5. **FileSystemIsolationService** (`lib/sandbox/file-system-isolation.ts`)
   - Provides secure file operations within sandboxes
   - Implements size limits and path restrictions
   - Manages sandbox cleanup and resource management

### API Endpoints

#### Sandbox Management (`/api/sandbox`)
- `GET /api/sandbox` - List all active sandboxes
- `POST /api/sandbox` - Create a new sandbox
- `GET /api/sandbox/:id` - Get sandbox details
- `DELETE /api/sandbox/:id` - Delete a sandbox

#### Preview Management (`/api/sandbox/preview`)
- `POST /api/sandbox/preview?sandboxId=:id` - Start preview server
- `DELETE /api/sandbox/preview?sandboxId=:id` - Stop preview server
- `GET /api/sandbox/preview?sandboxId=:id` - Get preview information

#### Code Execution (`/api/sandbox/execute`)
- `POST /api/sandbox/execute?sandboxId=:id` - Execute code in sandbox
- `GET /api/sandbox/execute?sandboxId=:id` - Get sandbox files
- `PUT /api/sandbox/execute?sandboxId=:id` - Update file in sandbox

## Usage Examples

### 1. Creating a Sandbox

```typescript
// Create a React sandbox
const response = await fetch('/api/sandbox', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    type: 'react',
    enablePreview: true,
    metadata: {
      userId: 'user123',
      sessionId: 'session456'
    }
  }),
});

const data = await response.json();
console.log('Sandbox created:', data.sandbox);
```

### 2. Executing Code

```typescript
// Execute JavaScript code in sandbox
const response = await fetch('/api/sandbox/execute?sandboxId=sandbox123', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    code: `
      function greet(name) {
        return \`Hello, \${name}!\`;
      }
      console.log(greet('World'));
    `,
    language: 'javascript',
    timeout: 30000
  }),
});

const data = await response.json();
console.log('Execution result:', data.result);
```

### 3. Building a React App

```typescript
// Build a complete React application
const response = await fetch('/api/sandbox', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    type: 'react',
    enablePreview: true,
    config: {
      name: 'My React App',
      description: 'A beautiful React application',
      features: {
        routing: true,
        stateManagement: true,
        styling: true,
        apiIntegration: false
      }
    }
  }),
});

const data = await response.json();
console.log('React app created:', data.sandbox);
```

### 4. Starting a Preview

```typescript
// Start live preview
const response = await fetch('/api/sandbox/preview?sandboxId=sandbox123', {
  method: 'POST',
});

const data = await response.json();
console.log('Preview started:', data.preview);
```

## Demo Components

### SandboxDemo Component

The `SandboxDemo` component provides a complete interface for:
- Creating and managing sandboxes
- Executing code in isolated environments
- Managing files within sandboxes
- Viewing live previews

Usage:
```tsx
import SandboxDemo from '@/components/SandboxDemo';

function App() {
  return <SandboxDemo />;
}
```

### ReactAppBuilderDemo Component

The `ReactAppBuilderDemo` component demonstrates:
- Building complete React applications
- Configuring app features (routing, state management, styling)
- Live preview of generated applications
- Code preview of generated files

Usage:
```tsx
import ReactAppBuilderDemo from '@/components/ReactAppBuilderDemo';

function App() {
  return <ReactAppBuilderDemo />;
}
```

## Security Features

### Isolation
- Each sandbox runs in its own isolated environment
- File system operations are restricted to sandbox directories
- Network access is controlled and limited
- Code execution has timeouts and resource limits

### Resource Management
- Memory limits prevent excessive resource usage
- Disk space quotas for each sandbox
- Automatic cleanup of inactive sandboxes
- Port management to prevent conflicts

### Code Execution Safety
- Sandboxed JavaScript execution
- Prevention of dangerous operations
- Timeout protection for long-running code
- Error handling and recovery

## Configuration

### Environment Variables
```bash
# Sandbox configuration
SANDBOX_TIMEOUT=30000
SANDBOX_MEMORY_LIMIT=512
SANDBOX_DISK_QUOTA=100MB
SANDBOX_MAX_FILES=1000

# Preview configuration
PREVIEW_PORT_RANGE=3000-4000
PREVIEW_TIMEOUT=60000
```

### Sandbox Limits
- Maximum 10 active sandboxes per user
- 30-second timeout for code execution
- 100MB disk quota per sandbox
- 512MB memory limit per sandbox

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   - The sandbox system automatically finds available ports
   - If conflicts persist, restart the socket server

2. **Sandbox Creation Fails**
   - Check disk space and memory availability
   - Verify file system permissions
   - Review server logs for detailed error messages

3. **Preview Not Loading**
   - Ensure the preview server started successfully
   - Check browser console for iframe security errors
   - Verify sandbox status is 'running'

4. **Code Execution Timeouts**
   - Increase timeout in execution request
   - Optimize code for better performance
   - Check for infinite loops or blocking operations

### Debug Commands

```bash
# Check active sandboxes
curl http://localhost:3001/api/sessions

# Get sandbox details
curl http://localhost:3001/api/sandbox/:id

# Check preview status
curl http://localhost:3001/api/sandbox/preview?sandboxId=:id
```

## Best Practices

1. **Resource Management**
   - Clean up unused sandboxes regularly
   - Monitor resource usage and limits
   - Use appropriate timeouts for operations

2. **Security**
   - Never expose sandbox IDs in public URLs
   - Validate all user inputs
   - Use authentication for production deployments

3. **Performance**
   - Batch file operations when possible
   - Use streaming for large files
   - Implement caching for frequently accessed data

4. **Error Handling**
   - Always handle API errors gracefully
   - Provide meaningful error messages to users
   - Implement retry mechanisms for transient failures

## Next Steps

The sandbox system provides a solid foundation for building applications like Lovable. You can extend it by:

1. **Adding More Languages**: Support for Python, Go, Rust, etc.
2. **Database Integration**: Add database sandboxes for full-stack applications
3. **Collaboration Features**: Multi-user editing and real-time collaboration
4. **Deployment**: One-click deployment to cloud providers
5. **AI Integration**: Code generation and optimization using AI

## Conclusion

This sandbox environment system provides a secure, scalable foundation for running and building web applications in isolated environments. It combines the power of containerization with the simplicity of web-based development, making it perfect for educational platforms, prototyping tools, and collaborative development environments.