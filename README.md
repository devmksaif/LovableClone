# NextLovable — LangGraph Multi-Provider AI Agent

This project demonstrates a complete LangGraph-based multi-agent system with MongoDB persistence, ChromaDB vector storage, and support for multiple AI providers (Google Gemini and OpenRouter).

## Features

- 🤖 **Multi-Agent System**: LangGraph workflow with planner → executor → reviewer → fixer auto-iteration
- 💾 **Persistent Storage**: MongoDB with Prisma for conversations and project data
- 🧠 **Vector Memory**: ChromaDB integration for long-term project context and code search
- 🔄 **Auto-Iteration**: Automatic retry and fix cycles when code generation fails
- 🎯 **18 Advanced Tools**: File operations, validation, optimization, and more
- 📱 **Chat Interface**: Modern UI with project management and session persistence

## Quick Start

1. **Install dependencies:**
   ```bash
   pnpm install
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Start MongoDB** (if using local instance):
   ```bash
   mongod
   ```

4. **Run the application:**
   ```bash
   pnpm run dev
   ```

## API Providers

The system automatically selects the best available AI provider:

### Primary: Google Gemini (Recommended)
- **Environment Variable**: `GEMINI_API_KEY`
- **Get API Key**: Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
- **Advantages**: No rate limiting, high quality, cost-effective
- **Default Model**: `gemini-1.5-pro`

### Fallback: OpenRouter
- **Environment Variable**: `OPENROUTER_API_KEY`
- **Get API Key**: Visit [OpenRouter](https://openrouter.ai/keys)
- **Note**: May experience rate limiting with free tier

### Provider Selection Logic
1. If `GEMINI_API_KEY` is set → Uses Google Gemini
2. Else if `OPENROUTER_API_KEY` is set → Uses OpenRouter
3. Otherwise → Throws error requiring API key

## Environment Variables

```bash
# AI Provider (choose one)
GEMINI_API_KEY=your-gemini-api-key-here
# OR
OPENROUTER_API_KEY=your-openrouter-key-here

# Database
DATABASE_URL="mongodb://localhost:27017/nextlovable"

# Optional overrides
GEMINI_MODEL=gemini-1.5-pro
OPENROUTER_MODEL=openai/gpt-4o
```

## Architecture

- **Frontend**: Next.js 14 with React and Tailwind CSS
- **Backend**: Next.js API routes with streaming responses
- **Database**: MongoDB with Prisma ORM
- **Vector Store**: ChromaDB with LangChain integration
- **AI Framework**: LangChain + LangGraph for agent orchestration
- **State Management**: Custom memory system with conversation persistence

## Development

```bash
# Install dependencies
pnpm install

# Run in development mode
pnpm run dev

# Build for production
pnpm run build

# Run linting
pnpm run lint
```

## Project Structure

```
├── app/                    # Next.js app directory
│   ├── api/               # API routes
│   │   ├── chat/         # Main chat endpoint
│   │   └── sessions/     # Session management
│   └── page.tsx          # Main chat interface
├── components/            # React components
│   └── ChatSidebar.tsx   # Project management sidebar
├── lib/                   # Core libraries
│   ├── agents/           # LangGraph agent definitions
│   ├── db/               # Database utilities
│   └── utils/            # Helper functions
├── prisma/                # Database schema
└── src/                   # Source code
    └── agents/           # Agent implementations
```

