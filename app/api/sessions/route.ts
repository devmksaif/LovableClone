import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '../../../lib/db/prisma';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get('page') || '1');
    const pageSize = parseInt(searchParams.get('pageSize') || '5');

    const skip = (page - 1) * pageSize;

    // Get total count for pagination
    const totalSessions = await prisma.session.count();

    // Get paginated sessions with their conversations and projects
    const sessions = await prisma.session.findMany({
      include: {
        conversations: {
          orderBy: { timestamp: 'desc' },
          take: 5, // Get last 5 messages for preview
        },
        projects: {
          include: {
            files: {
              select: {
                filename: true,
                operation: true,
              },
            },
          },
          orderBy: { createdAt: 'desc' },
          take: 1, // Get latest project
        },
      },
      orderBy: { updatedAt: 'desc' },
      skip,
      take: pageSize,
    });

    const totalPages = Math.ceil(totalSessions / pageSize);

    return NextResponse.json({
      success: true,
      sessions: sessions.map(session => ({
        ...session,
        conversations: session.conversations.reverse(), // Put in chronological order
      })),
      pagination: {
        page,
        pageSize,
        totalSessions,
        totalPages,
        hasNextPage: page < totalPages,
        hasPrevPage: page > 1,
      },
    });
  } catch (error) {
    console.error('Failed to fetch sessions:', error);
    return NextResponse.json(
      {
        error: 'Failed to fetch sessions',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const { projectFolder } = await request.json();

    if (!projectFolder) {
      return NextResponse.json(
        { error: 'projectFolder is required' },
        { status: 400 }
      );
    }

    // Create a new session
    const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    const session = await prisma.session.create({
      data: {
        sessionId,
        projectFolder,
      },
      include: {
        conversations: true,
        projects: true,
      },
    });

    return NextResponse.json({
      success: true,
      session,
    });
  } catch (error) {
    console.error('Failed to create session:', error);
    return NextResponse.json(
      {
        error: 'Failed to create session',
        details: error instanceof Error ? error.message : 'Unknown error',
      },
      { status: 500 }
    );
  }
}