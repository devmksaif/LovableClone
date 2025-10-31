import { writeFileSync, appendFileSync, existsSync } from 'fs';
import { join } from 'path';

export interface ChatLogEntry {
  timestamp: string;
  sessionId: string;
  eventType: 'user_message' | 'assistant_response' | 'tool_call' | 'error' | 'system_event' | 'progress_update' | 'step_change' | 'file_operation' | 'model_change' | 'sandbox_action';
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
  metadata?: {
    userId?: string;
    model?: string;
    toolName?: string;
    filePath?: string;
    sandboxId?: string;
    duration?: number;
    errorCode?: string;
    stackTrace?: string;
    requestId?: string;
    [key: string]: any;
  };
}

class ChatLogger {
  private logFilePath: string;
  private isClient: boolean;

  constructor() {
    this.logFilePath = join(process.cwd(), 'chat-logs.txt');
    this.isClient = typeof window !== 'undefined';
  }

  private formatTimestamp(): string {
    return new Date().toISOString();
  }

  private formatLogEntry(entry: ChatLogEntry): string {
    const emoji = this.getEmojiForEventType(entry.eventType);
    const levelEmoji = this.getEmojiForLevel(entry.level);
    
    let logLine = `${entry.timestamp} ${emoji} [${entry.level.toUpperCase()}] ${entry.eventType}: ${entry.message}`;
    
    if (entry.metadata) {
      const metadataStr = Object.entries(entry.metadata)
        .filter(([_, value]) => value !== undefined && value !== null)
        .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
        .join(', ');
      
      if (metadataStr) {
        logLine += ` | ${metadataStr}`;
      }
    }

    return logLine;
  }

  private getEmojiForEventType(eventType: string): string {
    const emojiMap: Record<string, string> = {
      'user_message': '👤',
      'assistant_response': '🤖',
      'tool_call': '🔧',
      'error': '❌',
      'system_event': '⚙️',
      'progress_update': '📊',
      'file_operation': '📁',
      'model_change': '🧠',
      'sandbox_action': '🏗️'
    };
    return emojiMap[eventType] || '📝';
  }

  private getEmojiForLevel(level: string): string {
    const emojiMap: Record<string, string> = {
      'info': 'ℹ️',
      'warn': '⚠️',
      'error': '🚨',
      'debug': '🔍'
    };
    return emojiMap[level] || 'ℹ️';
  }

  public log(entry: Omit<ChatLogEntry, 'timestamp'>): void {
    const fullEntry: ChatLogEntry = {
      ...entry,
      timestamp: this.formatTimestamp()
    };

    const logLine = this.formatLogEntry(fullEntry);

    // Log to console for immediate visibility
    console.log(logLine);

    // In client-side, send to API endpoint for server-side logging
    if (this.isClient) {
      this.logToServer(fullEntry);
    } else {
      // Server-side: write directly to file
      this.writeToFile(logLine);
    }
  }

  private async logToServer(entry: ChatLogEntry): Promise<void> {
    try {
      const PYTHON_BACKEND_URL = process.env.NEXT_PUBLIC_PYTHON_BACKEND_URL || 'http://localhost:8000';
      await fetch(`${PYTHON_BACKEND_URL}/api/chat-logs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(entry),
      });
    } catch (error) {
      console.error('Failed to send log to server:', error);
    }
  }

  private writeToFile(logLine: string): void {
    try {
      appendFileSync(this.logFilePath, logLine + '\n', 'utf8');
    } catch (error) {
      console.error('Failed to write to log file:', error);
    }
  }

  // Convenience methods for different log levels
  public info(eventType: ChatLogEntry['eventType'], message: string, sessionId: string, metadata?: ChatLogEntry['metadata']): void {
    this.log({ eventType, level: 'info', message, sessionId, metadata });
  }

  public warn(eventType: ChatLogEntry['eventType'], message: string, sessionId: string, metadata?: ChatLogEntry['metadata']): void {
    this.log({ eventType, level: 'warn', message, sessionId, metadata });
  }

  public error(eventType: ChatLogEntry['eventType'], message: string, sessionId: string, metadata?: ChatLogEntry['metadata']): void {
    this.log({ eventType, level: 'error', message, sessionId, metadata });
  }

  public debug(eventType: ChatLogEntry['eventType'], message: string, sessionId: string, metadata?: ChatLogEntry['metadata']): void {
    this.log({ eventType, level: 'debug', message, sessionId, metadata });
  }

  // Specific logging methods for common events
  public logUserMessage(sessionId: string, message: string, metadata?: any): void {
    this.info('user_message', `User sent message: "${message.substring(0, 100)}${message.length > 100 ? '...' : ''}"`, sessionId, metadata);
  }

  public logAssistantResponse(sessionId: string, response: string, metadata?: any): void {
    this.info('assistant_response', `Assistant responded: "${response.substring(0, 100)}${response.length > 100 ? '...' : ''}"`, sessionId, metadata);
  }

  public logToolCall(sessionId: string, toolName: string, parameters: any, result?: any, duration?: number): void {
    this.info('tool_call', `Tool ${toolName} called`, sessionId, {
      toolName,
      parameters: JSON.stringify(parameters),
      result: result ? JSON.stringify(result).substring(0, 200) : undefined,
      duration
    });
  }

  public logError(sessionId: string, error: Error | string, context?: string): void {
    const errorMessage = error instanceof Error ? error.message : error;
    const stackTrace = error instanceof Error ? error.stack : undefined;
    
    this.error('error', `Error occurred: ${errorMessage}`, sessionId, {
      context,
      stackTrace,
      errorCode: error instanceof Error ? error.name : 'UnknownError'
    });
  }

  // Progress and step logging
  public logProgressUpdate(sessionId: string, progress: any): void {
    this.info('progress_update', `Progress: ${progress.overallProgress}% - Step ${progress.currentStep + 1}: ${progress.steps[progress.currentStep]?.label}`, sessionId, {
      overallProgress: progress.overallProgress,
      currentStep: progress.currentStep,
      currentStepLabel: progress.steps[progress.currentStep]?.label,
      totalSteps: progress.steps.length,
      steps: progress.steps.map((step: any) => ({ id: step.id, status: step.status, label: step.label }))
    });
  }

  public logStepChange(sessionId: string, stepId: string, status: string, label: string): void {
    this.info('step_change', `Step "${label}" ${status}`, sessionId, {
      stepId,
      status,
      label
    });
  }

  public logFileOperation(sessionId: string, operation: string, filePath: string, success: boolean, metadata?: any): void {
    const level = success ? 'info' : 'error';
    this.log({
      eventType: 'file_operation',
      level,
      message: `File operation ${operation} on ${filePath}: ${success ? 'SUCCESS' : 'FAILED'}`,
      sessionId,
      metadata: {
        operation,
        filePath,
        success,
        ...metadata
      }
    });
  }

  public logModelChange(sessionId: string, oldModel: string, newModel: string): void {
    this.info('model_change', `Model changed from ${oldModel} to ${newModel}`, sessionId, {
      oldModel,
      newModel
    });
  }

  public logSandboxAction(sessionId: string, action: string, sandboxId: string, metadata?: any): void {
    this.info('sandbox_action', `Sandbox action: ${action} on ${sandboxId}`, sessionId, {
      action,
      sandboxId,
      ...metadata
    });
  }
}

// Export singleton instance
export const chatLogger = new ChatLogger();