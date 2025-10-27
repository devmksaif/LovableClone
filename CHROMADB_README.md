# 🚀 ChromaDB Vector Store Integration

## Overview

This integration adds ChromaDB vector database to your AI code generation system, enabling semantic search and long-term memory for project code, documentation, and conversation history.

## 🏗️ Architecture

### Key Components
- **ChromaDB**: Vector database for semantic embeddings
- **Google Gemini Embeddings**: text-embedding-004 (3072 dimensions) for code and text
- **Project Embeddings**: Automated project structure and code analysis
- **API Endpoints**: REST APIs for embedding, searching, and context retrieval

### Data Types Stored
1. **Code Embeddings**: Function definitions, classes, imports, syntax chunks
2. **Prompt Embeddings**: User requests, AI responses, conversation history
3. **Structure Embeddings**: Folder trees, dependency graphs, file metadata

## 🚀 Quick Start

### 1. Configure Environment
```bash
# Add to .env
GEMINI_API_KEY=your_gemini_api_key_here
```
**Note:** No ChromaDB server setup required - uses local file storage!

### 2. Optional: ChromaDB Server (if you prefer server mode)
```bash
# Start ChromaDB locally with Docker
docker run -p 8000:8000 chromadb/chroma:0.4.24

# Add to .env for server mode
CHROMADB_HOST=localhost
CHROMADB_PORT=8000
```

### 3. Run Demo
```bash
npx tsx src/vector-demo.ts
```

## 📚 API Endpoints

### POST `/api/vector/embed`
**Embed a project into vector store**
```json
{
  "projectId": "my_project_123",
  "sourceDir": "./my-app",
  "includeConversation": true,
  "sessionId": "session_456"
}
```

### POST `/api/vector/search`
**Search for code snippets**
```json
{
  "projectId": "my_project_123",
  "query": "function calculator",
  "nResults": 5
}
```

### POST `/api/vector/context`
**Get context for AI agent**
```json
{
  "projectId": "my_project_123",
  "query": "error handling patterns",
  "context": "all",
  "maxTokens": 3000
}
```

## 🔧 Integration Examples

### JavaScript/Node.js
```javascript
// Embed a project
const embedResponse = await fetch('/api/vector/embed', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    projectId: 'my-react-app',
    sourceDir: './src'
  })
});

// Search for patterns
const searchResponse = await fetch('/api/vector/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    projectId: 'my-react-app',
    query: 'useState hooks'
  })
});
```

### cURL Examples
```bash
# Embed project
curl -X POST http://localhost:3000/api/vector/embed \
  -H "Content-Type: application/json" \
  -d '{"projectId": "my-app", "sourceDir": "./app"}'

# Search code
curl -X POST http://localhost:3000/api/vector/search \
  -H "Content-Type: application/json" \
  -d '{"projectId": "my-app", "query": "function handleClick"}'
```

## 🧠 Semantic Search Capabilities

### Code Search
- **Functions**: Find similar function implementations
- **Components**: Locate React/Angular/Vue components
- **Patterns**: Discover error handling, authentication, etc.
- **APIs**: Find database queries, HTTP endpoints

### Context Retrieval
- **Historical**: "What was the plan for the login feature?"
- **Patterns**: "Show me similar error handling code"
- **Dependencies**: "What libraries does this project use?"
- **Architecture**: "How is the data flow structured?"

## 🎯 Advanced Features

### Intelligent Chunking
- **Language-aware**: Respects syntax boundaries by language
- **Semantic**: Breaks at function/class definitions, imports, etc.
- **Smart sizing**: Optimal 512-1024 tokens per chunk
- **Metadata-rich**: Includes file paths, line numbers, dependencies

### Multi-Modal Embeddings
- **Code chunks**: Syntax-highlighted with language context
- **Conversations**: User prompts + agent reasoning
- **Project structure**: Directory trees and dependency graphs
- **Documentation**: Comments, docstrings, README files

## 💾 Data Management

### Collection Strategy
- **Per-project collections**: `project_{id}_code`, `project_{id}_prompts`
- **Incremental updates**: Only re-embed changed files
- **Cleanup**: Automatic deletion of old/unnecessary embeddings
- **Health monitoring**: Connection status and statistics

### Statistics Tracking
```json
{
  "project_id": "my_react_app",
  "total_chunks": 147,
  "code_chunks": 89,
  "prompt_chunks": 45,
  "structure_chunks": 13,
  "created_at": "2024-01-15T10:30:00Z",
  "last_updated": "2024-01-15T16:45:00Z"
}
```

## 🔄 Agent Integration

### Enhanced AI Memory
The AI agent can now:
1. **Search codebase**: "Find all error handling functions"
2. **Reference history**: "What did we plan for user authentication?"
3. **Learn patterns**: "Use the same validation logic as the signup form"
4. **Build iteratively**: "Add login functionality like we did for signup"

### Workflow Enhancement
```javascript
// Agent workflow with vector search
async function generateCode(userRequest, projectId) {
  // 1. Search for relevant code patterns
  const similarCode = await searchSimilarCode(projectId, userRequest);

  // 2. Retrieve conversation context
  const context = await getRelevantContext(projectId, userRequest);

  // 3. Build enhanced prompt
  const enhancedPrompt = `${context}\n\nExisting patterns:\n${similarCode}\n\nNew request: ${userRequest}`;

  // 4. Generate code
  return await generateWithContext(enhancedPrompt);
}
```

## 🛠️ Development Workflow

### 1. Project Onboarding
```javascript
// Embed existing projects
await embedProject('my-app-v1', './existing-app');
await embedConversation('my-app-v1', 'session-history');

// The agent now understands your codebase
```

### 2. Iterative Development
```javascript
// Agent remembers context
"Add user profile page" ->
✅ Knows: Existing user components, auth patterns, styling conventions
✅ Generates: Consistent with existing code, follows established patterns
```

### 3. Knowledge Transfer
```javascript
// Cross-project learning
"Build a dashboard like I did for project X" ->
✅ Retrieves: Dashboard patterns from project X embeddings
✅ Adapts: Applies same architecture to current project
```

## 🔍 Search Examples

### Developer Queries
```javascript
// Find specific functionality
"authentication components"
→ Returns: Auth.tsx, Login.jsx, useAuth hook

// Pattern discovery
"error boundaries"
→ Returns: React error boundary implementations

// Style consistency
"button styling patterns"
→ Returns: CSS modules, Tailwind classes used
```

### Agent Reasoning
```javascript
// Internal thought process
"I need to add a new API endpoint"
→ Searches: "API route patterns" in codebase
→ Finds: Existing route files and middleware usage
→ Generates: Consistent with existing API structure
```

## 🚀 Production Deployment

### Scaling Considerations
- **Database choice**: ChromaDB for development, Pinecone/Weaviate for scale
- **Embedding model**: Can upgrade to larger models (text-embedding-3-large)
- **Caching**: Add Redis for query result caching
- **Async processing**: Queue embedding jobs for large projects

### Monitoring & Analytics
- **Usage tracking**: API call volumes, popular searches
- **Performance**: Query response times, embedding generation time
- **Quality metrics**: Search result relevance, agent improvement
- **Error tracking**: Failed embeddings, connection issues

## 🎉 Key Benefits

### For Developers
- **10x faster**: Find existing patterns instantly
- **Consistent**: Reuse established conventions
- **Quality**: Reference proven solutions
- **Learning**: Understand codebase through semantic search

### For AI Agents
- **Context aware**: Remembers project-specific details
- **User aligned**: Learns individual preferences and patterns
- **Efficient**: Uses token space for relevant context only
- **Iterative**: Builds upon existing code and decisions

### For Organizations
- **Knowledge capture**: Embed institutional knowledge
- **Team consistency**: Standardized patterns across teams
- **Speed**: New developers onboard faster with searchable code
- **Scalability**: Grow codebase while maintaining quality

## 🔗 API Reference

### /api/vector/embed
```typescript
POST {projectId: string, sourceDir?: string, includeConversation?: boolean}
→ {success: boolean, statistics?: ProjectStats}
```

### /api/vector/search
```typescript
POST {projectId: string, query: string, nResults?: number}
→ {results: Array<SearchResult>}
```

### /api/vector/context
```typescript
POST {projectId: string, query: string, context?: string, maxTokens?: number}
→ {context: string, sourcesFound: number}
```

## 🐛 Troubleshooting

### Common Issues
1. **ChromaDB connection**: Ensure running on correct host/port
2. **OpenAI API**: Check key validity and rate limits
3. **Large projects**: Use chunking or incremental embedding
4. **Memory issues**: Monitor vector database size

### Debugging Commands
```bash
# Health check
curl http://localhost:3000/api/vector/embed

# Test search
curl "http://localhost:3000/api/vector/context?projectId=test&query=function"

# View project stats
curl "http://localhost:3000/api/vector/search?projectId=test"
```

This ChromaDB integration transforms your code generation agent from stateless scripts to a true AI code assistant with full project understanding and long-term memory! 🎯🚀
