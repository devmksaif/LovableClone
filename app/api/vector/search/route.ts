import { NextRequest, NextResponse } from 'next/server';
import { chromaManager } from '../../../../lib/db/chroma';

export async function POST(request: NextRequest) {
  try {
    const { projectId, query, nResults = 10 } = await request.json();

    if (!projectId || !query) {
      return NextResponse.json(
        { error: 'projectId and query are required' },
        { status: 400 }
      );
    }

    console.log(`🔍 Searching project ${projectId} for: "${query}"`);

    // Search across all collections in the project
    const results = await chromaManager.searchProject(projectId, query, nResults);

    console.log(`✅ Found ${results.length} relevant results`);

    return NextResponse.json({
      success: true,
      projectId,
      query,
      results,
      count: results.length
    });

  } catch (error) {
    console.error('❌ Vector search error:', error);
    return NextResponse.json(
      {
        error: 'Failed to search vector database',
        details: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    );
  }
}

// GET endpoint for project search stats
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const projectId = searchParams.get('projectId');

    if (!projectId) {
      return NextResponse.json(
        { error: 'projectId is required' },
        { status: 400 }
      );
    }

    const stats = await chromaManager.getProjectStats(projectId);

    return NextResponse.json({
      success: true,
      projectId,
      stats,
      indexed: stats !== null
    });

  } catch (error) {
    console.error('❌ Stats retrieval error:', error);
    return NextResponse.json(
      {
        error: 'Failed to get project stats',
        details: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    );
  }
}
