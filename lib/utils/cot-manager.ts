import { AIMessage } from '@langchain/core/messages';

export interface COTEntry {
  id: string;
  step: string | number;
  reasoning: string;
  timestamp: number;
  isPartial: boolean;
}

export interface ProgressUpdate {
  id: string;
  type: string;
  sessionId: string;
  data: any;
  timestamp: number;
}

/**
 * Chain of Thought Manager with duplicate handling and progress optimization
 */
export class COTManager {
  private cotEntries: Map<string, Set<string>> = new Map(); // sessionId -> Set of reasoning hashes
  private cotMessages: Map<string, COTEntry[]> = new Map(); // sessionId -> COT entries
  private progressQueue: Map<string, ProgressUpdate[]> = new Map(); // sessionId -> progress updates
  private progressThrottle: Map<string, number> = new Map(); // sessionId -> last emit timestamp
  private readonly PROGRESS_THROTTLE_MS = 100; // Minimum time between progress updates
  private readonly MAX_COT_ENTRIES = 50; // Maximum COT entries per session

  /**
   * Add a COT entry with duplicate detection
   */
  addCOTEntry(sessionId: string, step: string | number, reasoning: string, isPartial: boolean = false): COTEntry | null {
    // Create a hash of the reasoning to detect duplicates
    const reasoningHash = this.hashString(reasoning.trim());
    
    // Initialize session data if needed
    if (!this.cotEntries.has(sessionId)) {
      this.cotEntries.set(sessionId, new Set());
      this.cotMessages.set(sessionId, []);
    }

    const sessionHashes = this.cotEntries.get(sessionId)!;
    const sessionMessages = this.cotMessages.get(sessionId)!;

    // Check for duplicates
    if (sessionHashes.has(reasoningHash)) {
      console.log(`🔍 Duplicate COT reasoning detected for session ${sessionId}, skipping...`);
      return null;
    }

    // Add to deduplication set
    sessionHashes.add(reasoningHash);

    // Create COT entry
    const cotEntry: COTEntry = {
      id: `cot-${sessionId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      step,
      reasoning,
      timestamp: Date.now(),
      isPartial
    };

    // Add to messages array
    sessionMessages.push(cotEntry);

    // Maintain maximum entries limit
    if (sessionMessages.length > this.MAX_COT_ENTRIES) {
      const removed = sessionMessages.shift();
      if (removed) {
        const removedHash = this.hashString(removed.reasoning.trim());
        sessionHashes.delete(removedHash);
      }
    }

    console.log(`🧠 Added COT entry for session ${sessionId}, step ${step}: ${reasoning.substring(0, 100)}...`);
    return cotEntry;
  }

  /**
   * Get all COT entries for a session
   */
  getCOTEntries(sessionId: string): COTEntry[] {
    return this.cotMessages.get(sessionId) || [];
  }

  /**
   * Convert COT entries to AI messages for chat display
   */
  getCOTMessages(sessionId: string): AIMessage[] {
    const entries = this.getCOTEntries(sessionId);
    return entries.map(entry => new AIMessage(`🔍 Step ${entry.step}: ${entry.reasoning.trim()}`));
  }

  /**
   * Get unique COT entries (removes duplicates from existing array)
   */
  getUniqueCOTEntries(sessionId: string): COTEntry[] {
    const entries = this.getCOTEntries(sessionId);
    const seen = new Set<string>();
    return entries.filter(entry => {
      const hash = this.hashString(entry.reasoning.trim());
      if (seen.has(hash)) {
        return false;
      }
      seen.add(hash);
      return true;
    });
  }

  /**
   * Add progress update with throttling
   */
  addProgressUpdate(sessionId: string, type: string, data: any, forceEmit: boolean = false): boolean {
    const now = Date.now();
    const lastEmit = this.progressThrottle.get(sessionId) || 0;

    // Check if we should throttle this update
    if (!forceEmit && (now - lastEmit) < this.PROGRESS_THROTTLE_MS) {
      // Queue the update instead of emitting immediately
      if (!this.progressQueue.has(sessionId)) {
        this.progressQueue.set(sessionId, []);
      }
      
      const queue = this.progressQueue.get(sessionId)!;
      const update: ProgressUpdate = {
        id: `progress-${sessionId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        type,
        sessionId,
        data,
        timestamp: now
      };
      
      queue.push(update);
      
      // Limit queue size
      if (queue.length > 10) {
        queue.shift();
      }
      
      return false; // Not emitted immediately
    }

    // Update throttle timestamp
    this.progressThrottle.set(sessionId, now);
    return true; // Can emit immediately
  }

  /**
   * Get and clear queued progress updates
   */
  getQueuedProgressUpdates(sessionId: string): ProgressUpdate[] {
    const queue = this.progressQueue.get(sessionId) || [];
    this.progressQueue.set(sessionId, []);
    return queue;
  }

  /**
   * Batch process queued progress updates
   */
  processBatchedUpdates(sessionId: string, emitFunction: (sessionId: string, data: any) => void): void {
    const updates = this.getQueuedProgressUpdates(sessionId);
    
    if (updates.length === 0) return;

    // Group updates by type
    const groupedUpdates = new Map<string, ProgressUpdate[]>();
    updates.forEach(update => {
      if (!groupedUpdates.has(update.type)) {
        groupedUpdates.set(update.type, []);
      }
      groupedUpdates.get(update.type)!.push(update);
    });

    // Emit batched updates
    groupedUpdates.forEach((typeUpdates, type) => {
      if (typeUpdates.length === 1) {
        // Single update, emit as-is
        emitFunction(sessionId, typeUpdates[0].data);
      } else {
        // Multiple updates of same type, batch them
        const batchedData = {
          type: `batched_${type}`,
          updates: typeUpdates.map(u => u.data),
          count: typeUpdates.length,
          timespan: {
            start: Math.min(...typeUpdates.map(u => u.timestamp)),
            end: Math.max(...typeUpdates.map(u => u.timestamp))
          }
        };
        emitFunction(sessionId, batchedData);
      }
    });

    console.log(`📊 Processed ${updates.length} batched progress updates for session ${sessionId}`);
  }

  /**
   * Clean up session data
   */
  cleanup(sessionId: string): void {
    this.cotEntries.delete(sessionId);
    this.cotMessages.delete(sessionId);
    this.progressQueue.delete(sessionId);
    this.progressThrottle.delete(sessionId);
    console.log(`🧹 Cleaned up COT and progress data for session ${sessionId}`);
  }

  /**
   * Get session statistics
   */
  getSessionStats(sessionId: string): {
    cotCount: number;
    uniqueReasoningCount: number;
    queuedProgressCount: number;
    lastProgressUpdate: number | null;
  } {
    const cotEntries = this.cotMessages.get(sessionId) || [];
    const uniqueHashes = this.cotEntries.get(sessionId) || new Set();
    const queuedUpdates = this.progressQueue.get(sessionId) || [];
    const lastUpdate = this.progressThrottle.get(sessionId) || null;

    return {
      cotCount: cotEntries.length,
      uniqueReasoningCount: uniqueHashes.size,
      queuedProgressCount: queuedUpdates.length,
      lastProgressUpdate: lastUpdate
    };
  }

  /**
   * Simple string hash function for duplicate detection
   */
  private hashString(str: string): string {
    let hash = 0;
    if (str.length === 0) return hash.toString();
    
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    
    return hash.toString();
  }
}

// Global COT manager instance
export const cotManager = new COTManager();

// Helper functions for backward compatibility
export function addCOTEntry(sessionId: string, step: string | number, reasoning: string, isPartial: boolean = false): COTEntry | null {
  return cotManager.addCOTEntry(sessionId, step, reasoning, isPartial);
}

export function getCOTMessages(sessionId: string): AIMessage[] {
  return cotManager.getCOTMessages(sessionId);
}

export function getUniqueCOTEntries(sessionId: string): COTEntry[] {
  return cotManager.getUniqueCOTEntries(sessionId);
}

export function addProgressUpdate(sessionId: string, type: string, data: any, forceEmit: boolean = false): boolean {
  return cotManager.addProgressUpdate(sessionId, type, data, forceEmit);
}

export function processBatchedUpdates(sessionId: string, emitFunction: (sessionId: string, data: any) => void): void {
  cotManager.processBatchedUpdates(sessionId, emitFunction);
}

export function cleanupSession(sessionId: string): void {
  cotManager.cleanup(sessionId);
}

export function getSessionStats(sessionId: string) {
  return cotManager.getSessionStats(sessionId);
}