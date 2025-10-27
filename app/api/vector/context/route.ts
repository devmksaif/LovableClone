import { NextRequest, NextResponse } from 'next/server';
import { chromaManager } from '../../../../lib/db/chroma';

export async function POST(request: NextRequest) {
  try {
    const { projectId, query, context = 'code', maxTokens = 4000 } = await request.json();

    if (!projectId || !query) {
      return NextResponse.json(
        { error: 'projectId and query are required' },
        { status: 400 }
      );
    }

    console.log(`🎭 Getting context for query: "${query}" in project ${projectId}`);

    let relevantSnippets: Array<{
      type: string;
      content: string;
      score: number;
      metadata: any;
    }> = [];

    // Get relevant snippets based on context type
    switch (context) {
      case 'code':
        const codeResults = await chromaManager.searchCode(projectId, query, 5);
        relevantSnippets = codeResults.map(r => ({ ...r, type: 'code' }));
        break;

      case 'conversation':
        // Search only prompts collection using the new vector store manager
        try {
          const promptsResults = await chromaManager.searchCode(projectId, query, 5);
          relevantSnippets = promptsResults
            .filter(r => r.metadata.type === 'prompt')
            .map(r => ({ ...r, type: 'conversation' }));
        } catch (error) {
          console.log('No conversation data available');
        }
        break;

      case 'all':
      default:
        relevantSnippets = await chromaManager.searchProject(projectId, query, 10);
    }

    // Build contextual response with token limit
    const contextBlocks: string[] = [];
    let currentTokens = 0;

    for (const snippet of relevantSnippets.slice(0, 5)) { // Limit to top 5
      // Estimate tokens (rough: 4 chars = 1 token)
      const estimatedTokens = Math.ceil(snippet.content.length / 4);
      if (currentTokens + estimatedTokens > maxTokens) break;

      let block = '';
      switch (snippet.type) {
        case 'code':
          block = `### ${snippet.metadata.filename} (lines ${snippet.metadata.lines_start}-${snippet.metadata.lines_end})\n\`\`\`${snippet.metadata.language}\n${snippet.content}\n\`\`\``;
          break;
        case 'prompt':
          block = `### Historical Context:\n${snippet.content}`;
          break;
        case 'structure':
          block = `### Project Structure:\n${snippet.content}`;
          break;
        default:
          block = `### Related Content:\n${snippet.content}`;
      }

      contextBlocks.push(block);
      currentTokens += estimatedTokens;
    }

    const contextualResponse = contextBlocks.length > 0
      ? contextBlocks.join('\n\n---\n\n')
      : 'No relevant context found for the query.';

    console.log(`✅ Built context with ${contextBlocks.length} blocks, ~${currentTokens} tokens`);

    return NextResponse.json({
      success: true,
      projectId,
      query,
      context: contextualResponse,
      sourcesFound: relevantSnippets.length,
      blocksUsed: contextBlocks.length,
      estimatedTokens: currentTokens
    });

  } catch (error) {
    console.error('❌ Context retrieval error:', error);
    return NextResponse.json(
      {
        error: 'Failed to retrieve context',
        details: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    );
  }
}

// GET endpoint for context assistance
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('query');
  const projectId = searchParams.get('projectId');

  if (!query || !projectId) {
    return NextResponse.json({
      suggestion: 'Try: /api/vector/context?projectId=your_project&query=function+calculator',
      examples: [
        'find authentication patterns',
        'show error handling code',
        'find similar functions',
        'show data models',
        'find API endpoints'
      ]
    });
  }

  try {
    const results = await chromaManager.searchProject(projectId, query, 3);

    const quickContext = results.map(result => ({
      type: result.type,
      filename: result.metadata.filename || 'Unknown',
      preview: result.content.substring(0, 100) + '...',
      score: Math.round(result.score * 100) + '%'
    }));

    return NextResponse.json({
      success: true,
      projectId,
      query,
      sampleContext: quickContext,
      totalResults: results.length
    });

  } catch (error) {
    return NextResponse.json(
      {
        error: 'Context preview failed',
        suggestion: 'Try using POST method for full context retrieval'
      },
      { status: 400 }
    );
  }
}
