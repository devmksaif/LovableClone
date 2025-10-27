import {
  getOrCreateSession,
  addConversation,
  getConversations,
  getRecentConversations,
  trackFileOperation,
  getFileOperations,
  getSessionStats,
} from '../db/database';
import { compressContext, summarizeConversation } from './summarizer';

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

// Configuration
const MAX_MESSAGES_BEFORE_SUMMARIZATION = 20;
const SUMMARIZATION_INTERVAL_MINUTES = 30;

// In-memory cache for summarized history to avoid repeated DB queries
const summarizationCache = new Map<string, {
  summary: string;
  timestamp: Date;
}>();

export class ConversationMemory {
  private sessionId: string;
  private projectFolder: string;

  constructor(sessionId: string, projectFolder: string) {
    this.sessionId = sessionId;
    this.projectFolder = projectFolder;
    this.initSession();
  }

  private async initSession() {
    await getOrCreateSession(this.sessionId, this.projectFolder);
  }

  // Add a message to memory (now persisted to database)
  async addMessage(role: 'user' | 'assistant', content: string) {
    const message = await addConversation(this.sessionId, role, content);
    
    // Check if we need to summarize
    await this.checkAndSummarize();
    
    return {
      id: message.id,
      role: message.role as 'user' | 'assistant',
      content: message.content,
      timestamp: message.timestamp,
    };
  }

  // Add a file operation to memory (now persisted)
  async addFileOperation(type: 'created' | 'modified' | 'read' | 'deleted', filename: string) {
    const operation = await trackFileOperation(this.sessionId, type, filename);
    
    return {
      type: operation.operation as 'created' | 'modified' | 'read' | 'deleted',
      filename: operation.filePath,
      timestamp: operation.timestamp,
      sessionId: operation.sessionId,
    };
  }

  // Get conversation history from database
  async getMessages(limit?: number): Promise<ConversationMessage[]> {
    const conversations = limit 
      ? await getRecentConversations(this.sessionId, limit)
      : await getConversations(this.sessionId);
    
    return conversations.map(c => ({
      id: c.id,
      role: c.role as 'user' | 'assistant',
      content: c.content,
      timestamp: c.timestamp,
    }));
  }

  // Get recent file operations from database
  async getRecentFileOperations(limit = 10): Promise<FileOperation[]> {
    const operations = await getFileOperations(this.sessionId, limit);
    
    return operations.map(op => ({
      type: op.operation as 'created' | 'modified' | 'read' | 'deleted',
      filename: op.filePath,
      timestamp: op.timestamp,
      sessionId: op.sessionId,
    }));
  }

  // Get all file operations related to a specific file
  async getSessionFiles(): Promise<string[]> {
    const operations = await getFileOperations(this.sessionId, 1000);
    const fileSet = new Set<string>();
    
    operations.forEach(op => {
      if (op.operation !== 'deleted') {
        fileSet.add(op.filePath);
      } else {
        fileSet.delete(op.filePath);
      }
    });
    
    return Array.from(fileSet);
  }

  // Search messages by content
  async searchMessages(query: string): Promise<ConversationMessage[]> {
    const messages = await this.getMessages();
    const lowerQuery = query.toLowerCase();
    
    return messages.filter(msg =>
      msg.content.toLowerCase().includes(lowerQuery)
    );
  }

  // Get a context summary for the agent
  async getContextSummary(): Promise<string | null> {
    const messages = await this.getMessages();
    
    if (messages.length === 0) {
      return null;
    }

    // Check cache first
    const cached = summarizationCache.get(this.sessionId);
    if (cached && messages.length < MAX_MESSAGES_BEFORE_SUMMARIZATION) {
      const age = Date.now() - cached.timestamp.getTime();
      if (age < SUMMARIZATION_INTERVAL_MINUTES * 60 * 1000) {
        return cached.summary;
      }
    }

    const recentMessages = messages.slice(-10);
    const conversationText = recentMessages
      .map(m => `${m.role}: ${m.content}`)
      .join('\n');

    const files = await this.getSessionFiles();
    const filesList = files.length > 0
      ? `\nFiles in project: ${files.join(', ')}`
      : '';

    return `Previous conversation context:\n${conversationText}${filesList}`;
  }

  // Get compressed context for token efficiency
  async getCompressedContext(userRequest: string = ''): Promise<string | null> {
    const messages = await this.getMessages();
    
    if (messages.length === 0) {
      return null;
    }

    // Use cached summary if available and recent
    const cached = summarizationCache.get(this.sessionId);
    if (cached) {
      const age = Date.now() - cached.timestamp.getTime();
      if (age < SUMMARIZATION_INTERVAL_MINUTES * 60 * 1000) {
        return cached.summary;
      }
    }

    // Generate new summary
    const messageArray = messages.map(m => ({ role: m.role, content: m.content }));
    const result = await compressContext({
      userRequest: userRequest || 'Continue working on the project',
      conversationHistory: messageArray,
    });

    const compressed = result.compressedContext;

    // Cache the result
    summarizationCache.set(this.sessionId, {
      summary: compressed,
      timestamp: new Date(),
    });

    return compressed;
  }

  // Check if summarization is needed
  private async checkAndSummarize() {
    const messages = await this.getMessages();
    
    if (messages.length < MAX_MESSAGES_BEFORE_SUMMARIZATION) {
      return;
    }

    const cached = summarizationCache.get(this.sessionId);
    if (cached) {
      const age = Date.now() - cached.timestamp.getTime();
      if (age < SUMMARIZATION_INTERVAL_MINUTES * 60 * 1000) {
        return; // Recent summary exists
      }
    }

    // Generate summary
    await this.summarizeHistory();
  }

  // Summarize conversation history
  private async summarizeHistory() {
    const messages = await this.getMessages();
    
    if (messages.length < 5) {
      return null;
    }

    const messageArray = messages.map(m => ({ role: m.role, content: m.content }));
    const result = await summarizeConversation(messageArray);
    
    // Cache the summary
    summarizationCache.set(this.sessionId, {
      summary: result.summary,
      timestamp: new Date(),
    });

    console.log(`📝 Summarized ${messages.length} messages for session ${this.sessionId}`);
    return result.summary;
  }

  // Get token estimate for current context
  async getTokenEstimate(): Promise<number> {
    const context = await this.getContextSummary();
    if (!context) return 0;
    
    // Rough estimate: ~4 characters per token
    return Math.ceil(context.length / 4);
  }

  // Get session statistics
  async getStats() {
    return await getSessionStats(this.sessionId);
  }

  // Clear session cache (useful for testing or memory management)
  clearCache() {
    summarizationCache.delete(this.sessionId);
  }
}

// Global session memory instances
const sessionMemories = new Map<string, ConversationMemory>();

export function getSessionMemory(sessionId: string, projectFolder: string = ''): ConversationMemory {
  if (!sessionMemories.has(sessionId)) {
    const memory = new ConversationMemory(sessionId, projectFolder);
    sessionMemories.set(sessionId, memory);
  }
  return sessionMemories.get(sessionId)!;
}

// Clean up old sessions periodically
export function setupSessionCleanup(intervalHours: number = 24) {
  setInterval(() => {
    const cutoffTime = Date.now() - (intervalHours * 60 * 60 * 1000);
    
    Array.from(sessionMemories.entries()).forEach(([sessionId, memory]) => {
      memory.getStats().then((stats: any) => {
        if (stats && new Date(stats.updatedAt).getTime() < cutoffTime) {
          sessionMemories.delete(sessionId);
          console.log(`🧹 Cleaned up inactive session: ${sessionId}`);
        }
      });
    });
  }, intervalHours * 60 * 60 * 1000);
}
