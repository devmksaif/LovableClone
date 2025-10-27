import { prisma } from './prisma';

/**
 * Session Management
 */
export async function getOrCreateSession(sessionId: string, projectFolder: string) {
  let session = await prisma.session.findUnique({
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
    session = await prisma.session.create({
      data: {
        sessionId,
        projectFolder,
      },
      include: {
        conversations: true,
        projects: {
          include: {
            files: true,
          },
        },
      },
    });
  }

  return session;
}

export async function updateSessionFolder(sessionId: string, projectFolder: string) {
  return await prisma.session.update({
    where: { sessionId },
    data: { projectFolder },
  });
}

/**
 * Conversation Management
 */
export async function addConversation(sessionId: string, role: 'user' | 'assistant', content: string) {
  const session = await prisma.session.findUnique({
    where: { sessionId },
  });

  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  return await prisma.conversation.create({
    data: {
      sessionId: session.id,
      role,
      content,
    },
  });
}

export async function getConversations(sessionId: string) {
  const session = await prisma.session.findUnique({
    where: { sessionId },
  });

  if (!session) {
    return [];
  }

  return await prisma.conversation.findMany({
    where: { sessionId: session.id },
    orderBy: { timestamp: 'asc' },
  });
}

export async function getRecentConversations(sessionId: string, limit: number = 10) {
  const session = await prisma.session.findUnique({
    where: { sessionId },
  });

  if (!session) {
    return [];
  }

  return await prisma.conversation.findMany({
    where: { sessionId: session.id },
    orderBy: { timestamp: 'desc' },
    take: limit,
  });
}

/**
 * Project Management
 */
export async function createProject(
  sessionId: string,
  projectFolder: string,
  userRequest: string,
  plan: string[]
) {
  const session = await prisma.session.findUnique({
    where: { sessionId },
  });

  if (!session) {
    throw new Error(`Session not found: ${sessionId}`);
  }

  return await prisma.project.create({
    data: {
      sessionId: session.id,
      projectFolder,
      userRequest,
      plan,
    },
    include: {
      files: true,
    },
  });
}

export async function updateProject(
  projectId: string,
  data: {
    plan?: string[];
    isComplete?: boolean;
  }
) {
  return await prisma.project.update({
    where: { id: projectId },
    data,
  });
}

export async function getProjectsBySession(sessionId: string) {
  const session = await prisma.session.findUnique({
    where: { sessionId },
  });

  if (!session) {
    return [];
  }

  return await prisma.project.findMany({
    where: { sessionId: session.id },
    include: {
      files: true,
    },
    orderBy: { createdAt: 'desc' },
  });
}

export async function getCurrentProject(sessionId: string) {
  const projects = await getProjectsBySession(sessionId);
  return projects[0] || null;
}

/**
 * File Management
 */
export async function addProjectFile(
  projectId: string,
  filename: string,
  content: string,
  operation: 'created' | 'modified' | 'deleted'
) {
  // Check if file already exists
  const existing = await prisma.projectFile.findFirst({
    where: {
      projectId,
      filename,
    },
  });

  if (existing) {
    // Update existing file
    return await prisma.projectFile.update({
      where: { id: existing.id },
      data: {
        content,
        operation,
      },
    });
  }

  // Create new file
  return await prisma.projectFile.create({
    data: {
      projectId,
      filename,
      content,
      operation,
    },
  });
}

export async function getProjectFiles(projectId: string) {
  return await prisma.projectFile.findMany({
    where: { projectId },
    orderBy: { updatedAt: 'desc' },
  });
}

/**
 * File Operations Tracking
 */
export async function trackFileOperation(
  sessionId: string,
  operation: 'created' | 'modified' | 'deleted' | 'read',
  filePath: string
) {
  return await prisma.fileOperation.create({
    data: {
      sessionId,
      operation,
      filePath,
    },
  });
}

export async function getFileOperations(sessionId: string, limit: number = 50) {
  return await prisma.fileOperation.findMany({
    where: { sessionId },
    orderBy: { timestamp: 'desc' },
    take: limit,
  });
}

/**
 * Utility Functions
 */
export async function getSessionStats(sessionId: string) {
  const session = await prisma.session.findUnique({
    where: { sessionId },
    include: {
      _count: {
        select: {
          conversations: true,
          projects: true,
        },
      },
    },
  });

  if (!session) {
    return null;
  }

  const fileOperations = await prisma.fileOperation.count({
    where: { sessionId },
  });

  return {
    sessionId: session.sessionId,
    projectFolder: session.projectFolder,
    conversationCount: session._count.conversations,
    projectCount: session._count.projects,
    fileOperationCount: fileOperations,
    createdAt: session.createdAt,
    updatedAt: session.updatedAt,
  };
}

export async function cleanupOldSessions(daysOld: number = 7) {
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - daysOld);

  return await prisma.session.deleteMany({
    where: {
      updatedAt: {
        lt: cutoffDate,
      },
    },
  });
}
