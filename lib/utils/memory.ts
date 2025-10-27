interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface FileOperation {
  type: 'created' | 'modified' | 'read' | 'deleted';
  filename: string;
  timestamp: Date;
  sessionId: string;
}

interface SessionMemory {
  sessionId: string;
  messages: ConversationMessage[];
  fileOperations: FileOperation[];
  createdAt: Date;
  lastActive: Date;
  summarizedHistory?: string; // Compressed conversation history
  lastSummarizedAt?: Date;
}

// In-memory storage (extendable to database later)
const sessions = new Map<string, SessionMemory>();

// Configuration
const MAX_MESSAGES_BEFORE_SUMMARIZATION = 20;
const SUMMARIZATION_INTERVAL_MINUTES = 30;

export class ConversationMemory {
  private sessionId: string;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
    this.initSession();
  }

  private initSession() {
    if (!sessions.has(this.sessionId)) {
      sessions.set(this.sessionId, {
        sessionId: this.sessionId,
        messages: [],
        fileOperations: [],
        createdAt: new Date(),
        lastActive: new Date(),
      });
    } else {
      const session = sessions.get(this.sessionId)!;
      session.lastActive = new Date();
      sessions.set(this.sessionId, session);
    }
  }

  // Add a message to memory
  addMessage(role: 'user' | 'assistant', content: string) {
    const message: ConversationMessage = {
      id: Date.now().toString(),
      role,
      content,
      timestamp: new Date(),
    };

    const session = sessions.get(this.sessionId)!;
    session.messages.push(message);
    session.lastActive = new Date();
    sessions.set(this.sessionId, session);

    return message;
  }

  // Add a file operation to memory
  addFileOperation(type: FileOperation['type'], filename: string) {
    const operation: FileOperation = {
      type,
      filename,
      timestamp: new Date(),
      sessionId: this.sessionId,
    };

    const session = sessions.get(this.sessionId)!;
    session.fileOperations.push(operation);
    sessions.set(this.sessionId, session);

    return operation;
  }

  // Get conversation history
  getMessages(limit?: number): ConversationMessage[] {
    const session = sessions.get(this.sessionId);
    if (!session) return [];

    const messages = session.messages;
    return limit ? messages.slice(-limit) : messages;
  }

  // Get recent file operations
  getRecentFileOperations(limit = 10): FileOperation[] {
    const session = sessions.get(this.sessionId);
    if (!session) return [];

    return session.fileOperations.slice(-limit);
  }

  // Get all files created/modified in this session
  getSessionFiles(): string[] {
    const session = sessions.get(this.sessionId);
    if (!session) return [];

    const fileSet = new Set<string>();
    session.fileOperations.forEach(op => {
      if (op.type !== 'deleted') {
        fileSet.add(op.filename);
      }
    });

    return Array.from(fileSet);
  }

  // Search messages by content
  searchMessages(query: string): ConversationMessage[] {
    const session = sessions.get(this.sessionId);
    if (!session) return [];

    const lowerQuery = query.toLowerCase();
    return session.messages.filter(msg =>
      msg.content.toLowerCase().includes(lowerQuery)
    );
  }

  // Get context summary for new requests
  getContextSummary(): string {
    const session = sessions.get(this.sessionId);
    if (!session) return '';

    const recentMessages = session.messages.slice(-4); // Last 4 messages
    const recentFiles = this.getSessionFiles();

    let summary = '';

    // Include summarized history if available
    if (session.summarizedHistory) {
      summary += `Previous context (summarized):\n${session.summarizedHistory}\n\n`;
    }

    if (recentMessages.length > 0) {
      summary += `Recent conversation (${recentMessages.length} messages):\n`;
      recentMessages.forEach((msg, idx) => {
        summary += `${idx + 1}. ${msg.role}: ${msg.content.substring(0, 100)}${msg.content.length > 100 ? '...' : ''}\n`;
      });
      summary += '\n';
    }

    if (recentFiles.length > 0) {
      summary += `Files created/modified in this session:\n${recentFiles.join('\n')}\n\n`;
    }

    return summary;
  }

  // Get compressed context (for token efficiency)
  async getCompressedContext(maxTokens: number = 2000): Promise<string> {
    const session = sessions.get(this.sessionId);
    if (!session) return '';

    // Check if we need to create/update summarization
    const shouldSummarize = 
      session.messages.length > MAX_MESSAGES_BEFORE_SUMMARIZATION &&
      (!session.lastSummarizedAt ||
        Date.now() - session.lastSummarizedAt.getTime() > SUMMARIZATION_INTERVAL_MINUTES * 60 * 1000);

    if (shouldSummarize) {
      await this.summarizeHistory();
    }

    return this.getContextSummary();
  }

  // Summarize conversation history to save tokens
  private async summarizeHistory(): Promise<void> {
    const session = sessions.get(this.sessionId);
    if (!session || session.messages.length < 10) return;

    // Import summarizer (dynamic to avoid circular dependencies)
    const { summarizeConversation } = await import('./summarizer');

    // Keep last 5 messages fresh, summarize the rest
    const messagesToSummarize = session.messages.slice(0, -5);
    
    if (messagesToSummarize.length === 0) return;

    const { summary } = await summarizeConversation(
      messagesToSummarize.map(m => ({ role: m.role, content: m.content })),
      0 // Summarize all
    );

    session.summarizedHistory = summary;
    session.lastSummarizedAt = new Date();
    
    // Remove old messages, keep only recent ones
    session.messages = session.messages.slice(-5);
    
    sessions.set(this.sessionId, session);

    console.log(`📊 Summarized ${messagesToSummarize.length} messages for session ${this.sessionId}`);
  }

  // Get token estimate for context
  getTokenEstimate(): number {
    const context = this.getContextSummary();
    // Rough estimate: 4 chars ≈ 1 token
    return Math.ceil(context.length / 4);
  }

  // Get all active sessions (for debugging/stats)
  static getAllSessions(): SessionMemory[] {
    return Array.from(sessions.values());
  }

  static getSessionCount(): number {
    return sessions.size;
  }

  // Cleanup old sessions (older than 24 hours)
  static cleanupOldSessions() {
    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
    const toDelete: string[] = [];

    sessions.forEach((session, id) => {
      if (session.lastActive < oneDayAgo) {
        toDelete.push(id);
      }
    });

    toDelete.forEach(id => sessions.delete(id));
    return toDelete.length;
  }
}

// Utility to create/get memory instance
export function getSessionMemory(sessionId: string): ConversationMemory {
  return new ConversationMemory(sessionId);
}
