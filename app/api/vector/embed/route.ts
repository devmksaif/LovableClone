import { NextRequest, NextResponse } from 'next/server';
import { embedProject, embedConversation } from '../../../../lib/utils/project-embeddings';
import { chromaManager } from '../../../../lib/db/chroma';

export async function POST(request: NextRequest) {
  try {
    const { projectId, sourceDir = './generated', includeConversation = false, sessionId } = await request.json();

    if (!projectId) {
      return NextResponse.json(
        { error: 'projectId is required' },
        { status: 400 }
      );
    }

    console.log(`🎯 Starting embedding process for project: ${projectId}`);

    // Check ChromaDB health
    const isHealthy = await chromaManager.healthCheck();
    if (!isHealthy) {
      return NextResponse.json(
        {
          error: 'Vector database is not available',
          suggestion: 'Make sure ChromaDB is running and accessible'
        },
        { status: 503 }
      );
    }

    // Embed the project files
    await embedProject(projectId, sourceDir);

    // Optionally embed conversation history
    if (includeConversation && sessionId) {
      await embedConversation(projectId, sessionId);
    }

    // Get final statistics
    const stats = await chromaManager.getProjectStats(projectId);

    console.log(`✅ Successfully embedded project: ${projectId}`);

    return NextResponse.json({
      success: true,
      projectId,
      sourceDir,
      statistics: stats,
      includedConversation: includeConversation
    });

  } catch (error) {
    console.error('❌ Embedding error:', error);
    return NextResponse.json(
      {
        error: 'Failed to embed project',
        details: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  try {
    // General health check for embedding system
    const isHealthy = await chromaManager.healthCheck();

    return NextResponse.json({
      success: true,
      system: 'ChromaDB Vector Store',
      status: isHealthy ? 'healthy' : 'unhealthy',
      version: '1.0.0',
      provider: 'Google Gemini text-embedding-004 (3072 dimensions)',
      supportedOperations: [
        'embed-project',
        'search-code',
        'search-conversation',
        'cross-collection-search'
      ]
    });

  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        system: 'ChromaDB Vector Store',
        status: 'error',
        error: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    );
  }
}
