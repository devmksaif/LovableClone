import * as fs from 'fs';
import * as path from 'path';
import { ConversationMemory, getSessionMemory } from '../utils/memory-db';

// Global memory instance for current session
let currentMemory: ConversationMemory | null = null;
let currentProjectFolder: string | null = null;
let sessionToFolderMap = new Map<string, string>();

export function setSessionMemory(sessionId: string) {
  // Check if this session already has a project folder
  if (sessionToFolderMap.has(sessionId)) {
    currentProjectFolder = sessionToFolderMap.get(sessionId)!;
  } else {
    // Create new project folder for this session
    currentProjectFolder = path.join(process.cwd(), 'generated', sessionId);
    if (!fs.existsSync(currentProjectFolder)) {
      fs.mkdirSync(currentProjectFolder, { recursive: true });
    }
    sessionToFolderMap.set(sessionId, currentProjectFolder);
  }

  // Create memory with project folder
  currentMemory = getSessionMemory(sessionId, currentProjectFolder);
}

export function getMemory(): ConversationMemory {
  if (!currentMemory) {
    // Fallback to default session if not set
    const defaultFolder = path.join(process.cwd(), 'generated', 'default_project');
    currentMemory = getSessionMemory('default', defaultFolder);
  }
  return currentMemory;
}

export function getProjectFolder(): string {
  if (!currentProjectFolder) {
    // Fallback to default project folder
    const defaultFolder = path.join(process.cwd(), 'generated', 'default_project');
    if (!fs.existsSync(defaultFolder)) {
      fs.mkdirSync(defaultFolder, { recursive: true });
    }
    currentProjectFolder = defaultFolder;
  }
  return currentProjectFolder;
}

// Helper: Validate file content
export function validateFileContent(filename: string, content: string): { isValid: boolean; reason: string } {
  const trimmed = content.trim();

  // Check for placeholders
  if (content.includes('...') || content.toLowerCase().includes('todo') || content.includes('placeholder')) {
    return { isValid: false, reason: 'Contains placeholders or TODO comments' };
  }

  // Check for empty or very short files
  if (trimmed.length < 10) {
    return { isValid: false, reason: 'File is too short or empty' };
  }

  // Check for incomplete code patterns
  if (filename.endsWith('.ts') || filename.endsWith('.js')) {
    if (!trimmed.includes('export') && !trimmed.includes('function') && !trimmed.includes('class') && !trimmed.includes('const') && !trimmed.includes('let')) {
      return { isValid: false, reason: 'No valid code constructs found' };
    }
  }

  return { isValid: true, reason: 'Valid content' };
}