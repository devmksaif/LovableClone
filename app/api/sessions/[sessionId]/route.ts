import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '../../../../lib/db/prisma';

interface RouteParams {
  params: {
    sessionId: string;
  };
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { sessionId } = params;

    if (!sessionId) {
      return NextResponse.json(
        { error: 'sessionId is required' },
        { status: 400 }
      );
    }

    // Get the session with all conversations
    const session = await prisma.session.findUnique({
      where: { sessionId },
      include: {
        conversations: {
          orderBy: { timestamp: 'asc' },
        },
        projects: {
          include: {
            files: true,
          },
          orderBy: { createdAt: 'desc' },
        },
      },
    });

    if (!session) {
      return NextResponse.json(
        { error: 'Session not found' },
        { status: 404 }
      );
    }

    return NextResponse.json({
      success: true,
      session,
    });
  } catch (error) {
    console.error('Failed to fetch session:', error);
    return NextResponse.json(
      {
        error: 'Failed to fetch session',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}