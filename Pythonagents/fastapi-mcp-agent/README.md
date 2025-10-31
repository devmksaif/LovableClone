# FastAPI MCP Agent

A Python FastAPI application that integrates with the Model Context Protocol (MCP) to provide AI-powered code generation and tool execution capabilities. This system uses agent graphs to orchestrate complex workflows involving multiple AI models and external tools.

## Features

- **MCP Integration**: Connects to external MCP servers for filesystem operations, GitHub integration, and custom tools
- **Agent Graphs**: Orchestrates complex workflows with planning, code generation, and review agents
- **Multi-Model Support**: Supports OpenAI GPT, Anthropic Claude, and Google Gemini models
- **Streaming Responses**: Real-time progress updates via WebSocket connections
- **Sandbox Execution**: Isolated execution environments for code testing

## Project Structure

```
fastapi-mcp-agent/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app with MCP initialization
│   ├── routers/
│   │   ├── __init__.py
│   │   └── chat.py          # Chat endpoints (HTTP + WebSocket)
│   ├── models/
│   │   ├── __init__.py
│   │   └── request.py       # Pydantic models
│   └── agents/
│       ├── __init__.py
│       ├── mcp_integration.py # MCP client and tool management
│       └── agent_graphs.py   # LangChain-based agent orchestration
├── requirements.txt
├── README.md
└── .env.example
```

## Setup Instructions

### Prerequisites

- Python 3.8+
- Node.js 16+ (for MCP servers)
- API keys for your preferred AI models

### Installation

1. **Clone and navigate to the project:**
   ```bash
   git clone <repository-url>
   cd fastapi-mcp-agent
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

### Environment Variables

Create a `.env` file with the following variables:

```env
# AI Model API Keys (at least one required)
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_key

# Optional: GitHub integration
GITHUB_TOKEN=your_github_token

# Server Configuration
PORT=8000
ENVIRONMENT=development

# MCP Server Configuration
MCP_FILESYSTEM_ALLOWED_DIRS=/tmp,/app/sandbox
```

### Running MCP Servers

Install and run MCP servers for additional capabilities:

```bash
# Filesystem operations
npm install -g @modelcontextprotocol/server-filesystem

# GitHub integration (requires GITHUB_TOKEN)
npm install -g @modelcontextprotocol/server-github
```

## Usage

### Starting the Server

```bash
# Development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Endpoints

#### POST /api/chat
Synchronous chat endpoint for code generation requests.

**Request:**
```json
{
  "user_request": "Create a todo app in React",
  "session_id": "session-123",
  "model": "gpt-4",
  "sandbox_context": {
    "type": "react",
    "id": "sandbox-456",
    "project_path": "/app/sandboxes/sandbox-456"
  },
  "sandbox_id": "sandbox-456"
}
```

**Response:**
```json
{
  "success": true,
  "generated_code": "// Generated React todo app code...",
  "review_feedback": "Code looks good, minor suggestions...",
  "plan": ["Analyze requirements", "Generate components", "Add styling"],
  "progress_updates": [...],
  "session_id": "session-123"
}
```

#### WebSocket /api/chat/stream
Real-time streaming endpoint for interactive code generation.

### MCP Tool Integration

The system automatically connects to available MCP servers:

- **Filesystem Server**: File operations (read, write, list directories)
- **GitHub Server**: Repository management and issue tracking
- **Custom Servers**: Extend with additional MCP-compatible tools

### Agent Graph Workflow

1. **Planning Agent**: Analyzes user requests and creates execution plans
2. **Code Generation Agent**: Generates code using specified AI models
3. **Review Agent**: Validates and provides feedback on generated code
4. **Tool Execution**: Uses MCP tools for file operations and external integrations

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
# Install development dependencies
pip install black isort flake8

# Format code
black .
isort .

# Lint code
flake8 .
```

### Adding New MCP Tools

1. Create a new MCP server or use existing ones
2. Update `mcp_integration.py` to include the new server
3. Add tool handling logic in the agent nodes
4. Update the requirements and documentation

## Deployment

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Considerations

- Set `ENVIRONMENT=production` for optimized performance
- Use reverse proxy (nginx) for SSL termination
- Configure proper logging and monitoring
- Set up health checks and auto-scaling
- Secure API keys and environment variables

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

MIT License - see LICENSE file for details

Once the application is running, you can access the API documentation at `http://localhost:8000/docs`. This will provide you with an interactive interface to test the chat-related routes and other functionalities.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.