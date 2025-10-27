import { ChatOpenAI } from '@langchain/openai';
import { ChatGoogleGenerativeAI } from '@langchain/google-genai';
import { ChatGroq } from '@langchain/groq';
import { StateGraph, END, START, Annotation } from '@langchain/langgraph';
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { tool } from '@langchain/core/tools';
import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import {
  readFile,
  writeFile,
  appendToFile,
  deleteFile,
  listDirectory,
  searchFiles,
  FileReadSchema,
  FileWriteSchema,
  FileAppendSchema,
  FileDeleteSchema,
  DirectoryListSchema,
  FileSearchSchema
} from '../utils/fileops';
import { ConversationMemory, getSessionMemory } from '../utils/memory-db';
import { 
  compressContext, 
  summarizeFileContents, 
  estimateTokens,
  shouldCompress,
  smartTruncate
} from '../utils/summarizer';
import { toolLogger } from '../utils/tool-logger';
import { promptOptimizer } from '../utils/prompt-optimizer';

// Import the emit function from the API route
let emitEvent: (sessionId: string, data: any) => void = () => {};
export function setEmitFunction(fn: (sessionId: string, data: any) => void) {
  emitEvent = fn;
}

// Global memory instance for current session
let currentMemory: ConversationMemory | null = null;
let currentProjectFolder: string | null = null;
let sessionToFolderMap = new Map<string, string>(); // Track session -> folder mapping

export function setSessionMemory(sessionId: string) {
  // Initialize tool logger for this session
  toolLogger.setSession(sessionId);
  
  // Check if this session already has a project folder
  if (sessionToFolderMap.has(sessionId)) {
    currentProjectFolder = sessionToFolderMap.get(sessionId)!;
    currentMemory = getSessionMemory(sessionId, currentProjectFolder);
    console.log(`📂 Using existing project folder: ${currentProjectFolder}`);
    return;
  }
  
  // Create NEW project folder for this session (first time only)
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').split('T')[0];
  const sanitizedId = sessionId.replace(/[^a-zA-Z0-9-]/g, '_');
  currentProjectFolder = path.join(process.cwd(), 'generated', `project_${sanitizedId}_${timestamp}`);
  
  // Create the folder if it doesn't exist
  if (!fs.existsSync(currentProjectFolder)) {
    fs.mkdirSync(currentProjectFolder, { recursive: true });
    console.log(`📁 Created NEW project folder: ${currentProjectFolder}`);
  }
  
  // Remember this mapping
  sessionToFolderMap.set(sessionId, currentProjectFolder);
  
  // Create memory with project folder
  currentMemory = getSessionMemory(sessionId, currentProjectFolder);
}

function getMemory(): ConversationMemory {
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

// Get memory statistics for debugging/monitoring
export async function getMemoryStats() {
  const memory = getMemory();
  const messages = await memory.getMessages();
  const fileOps = await memory.getRecentFileOperations();
  const sessionFiles = await memory.getSessionFiles();
  
  return {
    tokenEstimate: await memory.getTokenEstimate(),
    messageCount: messages.length,
    fileOperationCount: fileOps.length,
    sessionFiles: sessionFiles,
  };
}

// Define the state schema for our Lovable-like agent
const AgentState = Annotation.Root({
  messages: Annotation<BaseMessage[]>({
    reducer: (current, update) => [...current, ...update],
    default: () => [],
  }),
  userRequest: Annotation<string>({
    reducer: (_, update) => update,
    default: () => '',
  }),
  plan: Annotation<string[]>({
    reducer: (_, update) => update,
    default: () => [],
  }),
  generatedFiles: Annotation<Record<string, string>>({
    reducer: (current, update) => ({ ...current, ...update }),
    default: () => ({}),
  }),
  currentIteration: Annotation<number>({
    reducer: (_, update) => update,
    default: () => 0,
  }),
  reviewFeedback: Annotation<string>({
    reducer: (_, update) => update,
    default: () => '',
  }),
  isComplete: Annotation<boolean>({
    reducer: (_, update) => update,
    default: () => false,
  }),
  reviewIterations: Annotation<number>({
    reducer: (_, update) => update,
    default: () => 0,
  }),
});

type AgentStateType = typeof AgentState.State;

// Initialize the LLM model with provider selection
function createLLM(model?: string) {
  // Model ID to actual model name mapping
  const getModelName = (modelId: string) => {
    const modelMappings: Record<string, string> = {
      'groq-llama3-8b': 'llama3-8b-8192',
      'groq-mixtral-8x7b': 'mixtral-8x7b-32768',
      'groq-llama-3.1-8b-instant': 'llama-3.1-8b-instant',
      'groq-llama-3.3-70b-versatile': 'llama-3.3-70b-versatile',
      'gemini-2.5-flash': 'gemini-2.5-flash',
      'gemini-2.5-pro': 'gemini-2.5-pro',
    };
    return modelMappings[modelId] || modelId;
  };

  // If a specific model is requested, try to use it
  if (model) {
    const groqApiKey = process.env.GROQ_API_KEY;
    const geminiApiKey = process.env.GEMINI_API_KEY;
    const openRouterApiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY;

    if (model.startsWith('groq-') && groqApiKey) {
      const actualModel = getModelName(model);
      console.log('⚡ Using Groq API (Fastest) - Model:', actualModel);
      return new ChatGroq({
        apiKey: groqApiKey,
        model: actualModel,
        temperature: 0.7,
        maxTokens: 4096,
      });
    } else if (model.startsWith('gemini-') && geminiApiKey) {
      const actualModel = getModelName(model);
      console.log('🤖 Using Google Gemini API - Model:', actualModel);
      return new ChatGoogleGenerativeAI({
        apiKey: geminiApiKey,
        model: actualModel,
        temperature: 0.7,
        maxOutputTokens: 4096,
      });
    } else if (openRouterApiKey) {
      console.log('🔄 Using OpenRouter API - Model:', model);
      const apiBase = process.env.OPENROUTER_API_BASE ?? process.env.OPENAI_API_BASE ?? 'https://openrouter.ai/api/v1';
      return new ChatOpenAI({
        apiKey: openRouterApiKey,
        configuration: {
          baseURL: apiBase,
        },
        model: model,
        temperature: 0.7,
      });
    }
  }

  // Default priority: Groq (fastest) → Gemini (reliable) → OpenRouter (fallback)
  const groqApiKey = process.env.GROQ_API_KEY;
  const geminiApiKey = process.env.GEMINI_API_KEY;
  const openRouterApiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY;

  if (groqApiKey) {
    console.log('⚡ Using Groq API (Fastest)');
    return new ChatGroq({
      apiKey: groqApiKey,
      model: process.env.GROQ_MODEL ?? 'llama3-8b-8192',
      temperature: 0.7,
      maxTokens: 4096,
    });
  } else if (geminiApiKey) {
    console.log('🤖 Using Google Gemini API');
    return new ChatGoogleGenerativeAI({
      apiKey: geminiApiKey,
      model: process.env.GEMINI_MODEL ?? 'gemini-2.5-flash',
      temperature: 0.7,
      maxOutputTokens: 4096,
    });
  } else if (openRouterApiKey) {
    console.log('🔄 Using OpenRouter API');
    const apiBase = process.env.OPENROUTER_API_BASE ?? process.env.OPENAI_API_BASE ?? 'https://openrouter.ai/api/v1';
    return new ChatOpenAI({
      apiKey: openRouterApiKey,
      configuration: {
        baseURL: apiBase,
      },
      model: process.env.OPENAI_MODEL ?? process.env.OPENROUTER_MODEL ?? 'openai/gpt-4o',
      temperature: 0.7,
    });
  } else {
    throw new Error('No API key found. Set GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY/OPENAI_API_KEY');
  }
}

let llm = createLLM();

// File operation tools
const readFileTool = tool(async ({ filePath }) => {
  // Resolve path relative to project folder
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`📖 Reading file: ${fullPath}`);
  const result = await readFile(fullPath);

  if (result.success) {
    getMemory().addFileOperation('read', fullPath);
    return `File content:\n${result.content}`;
  } else {
    return `Error reading file: ${result.error}`;
  }
}, {
  name: 'read_file',
  description: 'Read the contents of a file. Use this to examine existing code or documents.',
  schema: FileReadSchema,
});

const writeFileTool = tool(async ({ filePath, content }) => {
  // Resolve path relative to project folder
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`📝 Writing file: ${fullPath}`);
  const result = await writeFile(fullPath, content);

  if (result.success) {
    const exists = fs.existsSync(fullPath);
    getMemory().addFileOperation(exists ? 'modified' : 'created', fullPath);
    return `File written successfully: ${fullPath}`;
  } else {
    return `Error writing file: ${result.error}`;
  }
}, {
  name: 'write_file',
  description: 'Create or overwrite a file with content. Use this to create new files or completely replace existing ones.',
  schema: FileWriteSchema,
});

const appendToFileTool = tool(async ({ filePath, content }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`📎 Appending to file: ${fullPath}`);
  const result = await appendToFile(fullPath, content);

  if (result.success) {
    getMemory().addFileOperation('modified', fullPath);
    return `Content appended successfully to: ${fullPath}`;
  } else {
    return `Error appending to file: ${result.error}`;
  }
}, {
  name: 'append_to_file',
  description: 'Append content to the end of an existing file. Use this to add to existing files.',
  schema: FileAppendSchema,
});

const deleteFileTool = tool(async ({ filePath }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`🗑️ Deleting file: ${fullPath}`);
  const result = await deleteFile(fullPath);

  if (result.success) {
    getMemory().addFileOperation('deleted', fullPath);
    return `File deleted successfully: ${fullPath}`;
  } else {
    return `Error deleting file: ${result.error}`;
  }
}, {
  name: 'delete_file',
  description: 'Delete a file. Only works on files in the generated directory for security.',
  schema: FileDeleteSchema,
});

const listDirectoryTool = tool(async ({ dirPath }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(dirPath) ? dirPath : path.join(projectFolder, dirPath);
  
  console.log(`📂 Listing directory: ${fullPath}`);
  const result = await listDirectory(fullPath);

  if (result.success && result.files) {
    return `Directory contents:\n${result.files.join('\n')}`;
  } else {
    return `Error listing directory: ${result.error}`;
  }
}, {
  name: 'list_directory',
  description: 'List the contents of a directory. Use this to see what files are available.',
  schema: DirectoryListSchema,
});

const searchFilesTool = tool(async ({ dirPath, pattern }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(dirPath) ? dirPath : path.join(projectFolder, dirPath);
  
  console.log(`🔍 Searching files in ${fullPath} for pattern: ${pattern}`);
  const result = await searchFiles(fullPath, pattern);

  if (result.success && result.matches) {
    const matchesText = result.matches
      .slice(0, 20) // Limit to first 20 matches
      .map(match => `${match.file}:${match.line} - ${match.content}`)
      .join('\n');

    return `${result.matches.length} matches found:\n${matchesText}${result.matches.length > 20 ? '\n... (showing first 20)' : ''}`;
  } else {
    return `Error searching files: ${result.error}`;
  }
}, {
  name: 'search_files',
  description: 'Search for files containing a regex pattern. Use this to find specific code patterns or text.',
  schema: FileSearchSchema,
});

// Advanced code editing tools
const replaceInFileTool = tool(async ({ filePath, searchText, replaceText }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`✏️ Replacing text in file: ${fullPath}`);
  
  try {
    const readResult = await readFile(fullPath);
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const originalContent = readResult.content;
    const newContent = originalContent.replace(new RegExp(searchText, 'g'), replaceText);
    const replacementCount = (originalContent.match(new RegExp(searchText, 'g')) || []).length;

    if (replacementCount === 0) {
      return `No matches found for "${searchText}" in ${fullPath}`;
    }

    const writeResult = await writeFile(fullPath, newContent);
    if (writeResult.success) {
      getMemory().addFileOperation('modified', fullPath);
      return `Replaced ${replacementCount} occurrence(s) of "${searchText}" with "${replaceText}" in ${fullPath}`;
    } else {
      return `Error writing file: ${writeResult.error}`;
    }
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'replace_in_file',
  description: 'Find and replace text in a file using regex. Use this for refactoring or fixing code patterns.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
    searchText: z.string().describe('Text or regex pattern to search for'),
    replaceText: z.string().describe('Text to replace with'),
  }),
});

const insertAtLineTool = tool(async ({ filePath, lineNumber, content }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`📍 Inserting at line ${lineNumber} in: ${fullPath}`);
  
  try {
    const readResult = await readFile(fullPath);
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const lines = readResult.content.split('\n');
    if (lineNumber < 1 || lineNumber > lines.length + 1) {
      return `Error: Line number ${lineNumber} is out of range (file has ${lines.length} lines)`;
    }

    lines.splice(lineNumber - 1, 0, content);
    const newContent = lines.join('\n');

    const writeResult = await writeFile(fullPath, newContent);
    if (writeResult.success) {
      getMemory().addFileOperation('modified', fullPath);
      return `Inserted content at line ${lineNumber} in ${fullPath}`;
    } else {
      return `Error writing file: ${writeResult.error}`;
    }
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'insert_at_line',
  description: 'Insert content at a specific line number in a file. Use this for precise code additions.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
    lineNumber: z.number().describe('Line number where content should be inserted (1-based)'),
    content: z.string().describe('Content to insert'),
  }),
});

const deleteLinesToolDef = tool(async ({ filePath, startLine, endLine }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`✂️ Deleting lines ${startLine}-${endLine} in: ${fullPath}`);
  
  try {
    const readResult = await readFile(fullPath);
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const lines = readResult.content.split('\n');
    if (startLine < 1 || endLine > lines.length || startLine > endLine) {
      return `Error: Invalid line range ${startLine}-${endLine} (file has ${lines.length} lines)`;
    }

    lines.splice(startLine - 1, endLine - startLine + 1);
    const newContent = lines.join('\n');

    const writeResult = await writeFile(fullPath, newContent);
    if (writeResult.success) {
      getMemory().addFileOperation('modified', fullPath);
      return `Deleted lines ${startLine}-${endLine} in ${fullPath}`;
    } else {
      return `Error writing file: ${writeResult.error}`;
    }
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'delete_lines',
  description: 'Delete a range of lines from a file. Use this to remove code blocks.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
    startLine: z.number().describe('Starting line number (1-based, inclusive)'),
    endLine: z.number().describe('Ending line number (1-based, inclusive)'),
  }),
});

const replaceBlockTool = tool(async ({ filePath, startMarker, endMarker, newContent }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`🔄 Replacing block in: ${fullPath}`);
  console.log(`   Start marker: ${startMarker}`);
  console.log(`   End marker: ${endMarker}`);
  
  try {
    const readResult = await readFile(fullPath);
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const content = readResult.content;
    
    // Find start and end positions
    const startIdx = content.indexOf(startMarker);
    if (startIdx === -1) {
      return `Error: Start marker "${startMarker}" not found in ${fullPath}`;
    }

    const endIdx = content.indexOf(endMarker, startIdx + startMarker.length);
    if (endIdx === -1) {
      return `Error: End marker "${endMarker}" not found after start marker in ${fullPath}`;
    }

    // Replace the block (including markers)
    const before = content.substring(0, startIdx);
    const after = content.substring(endIdx + endMarker.length);
    const newFileContent = before + startMarker + '\n' + newContent + '\n' + endMarker + after;

    const writeResult = await writeFile(fullPath, newFileContent);
    if (writeResult.success) {
      getMemory().addFileOperation('modified', fullPath);
      const oldBlock = content.substring(startIdx, endIdx + endMarker.length);
      return `Successfully replaced block in ${fullPath}\nOld block (${oldBlock.split('\n').length} lines) → New block (${newContent.split('\n').length} lines)`;
    } else {
      return `Error writing file: ${writeResult.error}`;
    }
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'replace_block',
  description: 'Replace a block of code between two markers. More efficient than rewriting entire file. Perfect for updating functions, classes, or sections.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
    startMarker: z.string().describe('Unique text that marks the start of the block (e.g., "function myFunc(" or "// START SECTION")'),
    endMarker: z.string().describe('Unique text that marks the end of the block (e.g., "}" or "// END SECTION")'),
    newContent: z.string().describe('New content to replace the block between markers (markers will be preserved)'),
  }),
});

const replaceLineRangeTool = tool(async ({ filePath, startLine, endLine, newContent }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`📝 Replacing lines ${startLine}-${endLine} in: ${fullPath}`);
  
  try {
    const readResult = await readFile(fullPath);
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const lines = readResult.content.split('\n');
    if (startLine < 1 || endLine > lines.length || startLine > endLine) {
      return `Error: Invalid line range ${startLine}-${endLine} (file has ${lines.length} lines)`;
    }

    // Replace the line range
    const before = lines.slice(0, startLine - 1);
    const after = lines.slice(endLine);
    const newLines = newContent.split('\n');
    const newFileLines = [...before, ...newLines, ...after];

    const writeResult = await writeFile(fullPath, newFileLines.join('\n'));
    if (writeResult.success) {
      getMemory().addFileOperation('modified', fullPath);
      const oldLineCount = endLine - startLine + 1;
      const newLineCount = newLines.length;
      return `Replaced lines ${startLine}-${endLine} (${oldLineCount} lines) with new content (${newLineCount} lines) in ${fullPath}`;
    } else {
      return `Error writing file: ${writeResult.error}`;
    }
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'replace_line_range',
  description: 'Replace a specific range of lines with new content. More precise than replace_block. Use when you know exact line numbers.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
    startLine: z.number().describe('Starting line number (1-based, inclusive)'),
    endLine: z.number().describe('Ending line number (1-based, inclusive)'),
    newContent: z.string().describe('New content to replace the specified lines'),
  }),
});

const getFileInfoTool = tool(async ({ filePath }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`ℹ️ Getting file info: ${fullPath}`);
  
  try {
    const stats = fs.statSync(fullPath);
    const readResult = await readFile(fullPath);
    
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const lines = readResult.content.split('\n');
    const extension = path.extname(fullPath);
    
    return JSON.stringify({
      path: fullPath,
      size: stats.size,
      lines: lines.length,
      extension,
      created: stats.birthtime,
      modified: stats.mtime,
      isDirectory: stats.isDirectory(),
    }, null, 2);
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'get_file_info',
  description: 'Get detailed information about a file (size, lines, dates, etc.). Use this to understand file structure.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
  }),
});

const createDirectoryTool = tool(async ({ dirPath }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(dirPath) ? dirPath : path.join(projectFolder, dirPath);
  
  console.log(`📁 Creating directory: ${fullPath}`);
  
  try {
    fs.mkdirSync(fullPath, { recursive: true });
    getMemory().addFileOperation('created', fullPath);
    return `Directory created successfully: ${fullPath}`;
  } catch (error: any) {
    return `Error creating directory: ${error.message}`;
  }
}, {
  name: 'create_directory',
  description: 'Create a new directory (including parent directories if needed). Use this to organize project structure.',
  schema: z.object({
    dirPath: z.string().describe('Path to the directory to create'),
  }),
});

const copyFileTool = tool(async ({ sourcePath, destinationPath }) => {
  const projectFolder = getProjectFolder();
  const fullSourcePath = path.isAbsolute(sourcePath) ? sourcePath : path.join(projectFolder, sourcePath);
  const fullDestPath = path.isAbsolute(destinationPath) ? destinationPath : path.join(projectFolder, destinationPath);
  
  console.log(`📋 Copying file from ${fullSourcePath} to ${fullDestPath}`);
  
  try {
    fs.copyFileSync(fullSourcePath, fullDestPath);
    getMemory().addFileOperation('created', fullDestPath);
    return `File copied successfully from ${fullSourcePath} to ${fullDestPath}`;
  } catch (error: any) {
    return `Error copying file: ${error.message}`;
  }
}, {
  name: 'copy_file',
  description: 'Copy a file to a new location. Use this to duplicate files or create templates.',
  schema: z.object({
    sourcePath: z.string().describe('Source file path'),
    destinationPath: z.string().describe('Destination file path'),
  }),
});

const moveFileTool = tool(async ({ sourcePath, destinationPath }) => {
  const projectFolder = getProjectFolder();
  const fullSourcePath = path.isAbsolute(sourcePath) ? sourcePath : path.join(projectFolder, sourcePath);
  const fullDestPath = path.isAbsolute(destinationPath) ? destinationPath : path.join(projectFolder, destinationPath);
  
  console.log(`🚚 Moving file from ${fullSourcePath} to ${fullDestPath}`);
  
  try {
    fs.renameSync(fullSourcePath, fullDestPath);
    getMemory().addFileOperation('deleted', fullSourcePath);
    getMemory().addFileOperation('created', fullDestPath);
    return `File moved successfully from ${fullSourcePath} to ${fullDestPath}`;
  } catch (error: any) {
    return `Error moving file: ${error.message}`;
  }
}, {
  name: 'move_file',
  description: 'Move or rename a file. Use this to reorganize project structure.',
  schema: z.object({
    sourcePath: z.string().describe('Source file path'),
    destinationPath: z.string().describe('Destination file path'),
  }),
});

const readLinesToolDef = tool(async ({ filePath, startLine, endLine }) => {
  const projectFolder = getProjectFolder();
  const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
  
  console.log(`📖 Reading lines ${startLine}-${endLine} from: ${fullPath}`);
  
  try {
    const readResult = await readFile(fullPath);
    if (!readResult.success || !readResult.content) {
      return `Error: Could not read file ${fullPath}`;
    }

    const lines = readResult.content.split('\n');
    if (startLine < 1 || endLine > lines.length || startLine > endLine) {
      return `Error: Invalid line range ${startLine}-${endLine} (file has ${lines.length} lines)`;
    }

    const selectedLines = lines.slice(startLine - 1, endLine);
    return `Lines ${startLine}-${endLine} of ${fullPath}:\n${selectedLines.join('\n')}`;
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'read_lines',
  description: 'Read a specific range of lines from a file. Use this to examine specific code sections.',
  schema: z.object({
    filePath: z.string().describe('Path to the file'),
    startLine: z.number().describe('Starting line number (1-based, inclusive)'),
    endLine: z.number().describe('Ending line number (1-based, inclusive)'),
  }),
});

const getProjectStructureTool = tool(async ({ maxDepth }) => {
  const projectFolder = getProjectFolder();
  
  console.log(`🗂️ Getting project structure from: ${projectFolder}`);
  
  try {
    const structure: string[] = [];
    
    const traverseDirectory = (dir: string, depth: number, prefix: string = '') => {
      if (depth > maxDepth) return;
      
      const items = fs.readdirSync(dir);
      items.forEach((item, index) => {
        const fullPath = path.join(dir, item);
        const isLast = index === items.length - 1;
        const connector = isLast ? '└── ' : '├── ';
        const relativePath = path.relative(projectFolder, fullPath);
        
        // Skip node_modules and hidden files
        if (item === 'node_modules' || item.startsWith('.')) return;
        
        structure.push(`${prefix}${connector}${item}`);
        
        if (fs.statSync(fullPath).isDirectory()) {
          const newPrefix = prefix + (isLast ? '    ' : '│   ');
          traverseDirectory(fullPath, depth + 1, newPrefix);
        }
      });
    };
    
    traverseDirectory(projectFolder, 0);
    return `Project structure:\n${projectFolder}\n${structure.join('\n')}`;
  } catch (error: any) {
    return `Error: ${error.message}`;
  }
}, {
  name: 'get_project_structure',
  description: 'Get a tree view of the project directory structure. Use this to understand project organization.',
  schema: z.object({
    maxDepth: z.number().default(3).describe('Maximum depth to traverse (default: 3)'),
  }),
});

const executeCommandTool = tool(async ({ command, description }) => {
  console.log(`⚙️ Executing command: ${command}`);
  console.log(`📝 Description: ${description}`);
  
  try {
    const { execSync } = require('child_process');
    const projectFolder = getProjectFolder();
    
    // Execute command in project folder
    const output = execSync(command, {
      cwd: projectFolder,
      encoding: 'utf-8',
      maxBuffer: 1024 * 1024 * 10, // 10MB
      timeout: 30000, // 30 seconds
    });
    
    return `Command executed successfully:\n${output}`;
  } catch (error: any) {
    return `Command failed with error:\n${error.message}\n${error.stdout || ''}\n${error.stderr || ''}`;
  }
}, {
  name: 'execute_command',
  description: 'Execute a shell command in the project directory. Use this for npm install, git operations, building, testing, etc. ALWAYS provide a clear description.',
  schema: z.object({
    command: z.string().describe('Shell command to execute'),
    description: z.string().describe('Clear description of what this command does and why'),
  }),
});

// Create the tools array with all tools
const tools = [
  // Basic file operations
  readFileTool, 
  writeFileTool, 
  appendToFileTool, 
  deleteFileTool, 
  listDirectoryTool, 
  searchFilesTool,
  // Advanced editing tools
  replaceInFileTool,
  insertAtLineTool,
  deleteLinesToolDef,
  replaceBlockTool,        // NEW: Replace content between markers
  replaceLineRangeTool,    // NEW: Replace specific line ranges
  readLinesToolDef,
  // File management
  getFileInfoTool,
  createDirectoryTool,
  copyFileTool,
  moveFileTool,
  // Project tools
  getProjectStructureTool,
  executeCommandTool,
];

// Helper function to wrap tool execution with logging
function wrapToolWithLogging(toolFn: any, toolName: string) {
  return async (...args: any[]) => {
    const callId = toolLogger.startCall(toolName, args[0] || {});
    try {
      const result = await toolFn(...args);
      toolLogger.endCall(callId, result, true);
      return result;
    } catch (error: any) {
      const errorMsg = error.message || String(error);
      toolLogger.endCall(callId, errorMsg, false, errorMsg);
      throw error;
    }
  };
}

// Bind tools to the LLM
const llmWithTools = llm.bindTools(tools);

// Helper: Validate file content
function validateFileContent(filename: string, content: string): { isValid: boolean; reason: string } {
  const trimmed = content.trim();
  
  // Check for placeholders
  if (content.includes('...') || content.toLowerCase().includes('todo') || content.includes('placeholder')) {
    return { isValid: false, reason: 'Contains placeholders or TODO comments' };
  }
  
  // Check for empty or very short files
  if (trimmed.length < 10) {
    return { isValid: false, reason: 'File is too short or empty' };
  }
  
  // File-specific validation
  if (filename.endsWith('.html')) {
    const hasDoctype = trimmed.toLowerCase().includes('<!doctype') || trimmed.toLowerCase().includes('<html');
    const hasClosing = trimmed.endsWith('</html>') || trimmed.endsWith('</body>') || trimmed.endsWith('-->');
    if (!hasDoctype || !hasClosing) {
      return { isValid: false, reason: 'HTML file incomplete - missing doctype or closing tags' };
    }
  } else if (filename.endsWith('.css')) {
    // Count braces
    const openBraces = (content.match(/\{/g) || []).length;
    const closeBraces = (content.match(/\}/g) || []).length;
    if (openBraces !== closeBraces) {
      return { isValid: false, reason: `CSS file incomplete - mismatched braces (${openBraces} open, ${closeBraces} close)` };
    }
  } else if (filename.endsWith('.js') || filename.endsWith('.ts')) {
    // Basic checks
    if (trimmed.includes('// ...') || trimmed.includes('/* ... */')) {
      return { isValid: false, reason: 'JavaScript/TypeScript file contains placeholder comments' };
    }
  } else if (filename.endsWith('.json')) {
    try {
      JSON.parse(content);
    } catch (e) {
      return { isValid: false, reason: 'JSON file is invalid' };
    }
  }
  
  return { isValid: true, reason: '' };
}

// Helper: Auto-fix common file issues
function autoFixIncompleteFile(filename: string, content: string): string {
  let fixed = content.trim();
  
  if (filename.endsWith('.html')) {
    // Ensure proper HTML closing
    if (!fixed.toLowerCase().includes('<!doctype')) {
      fixed = '<!DOCTYPE html>\n' + fixed;
    }
    if (!fixed.includes('<html')) {
      fixed = '<html>\n' + fixed;
    }
    if (!fixed.endsWith('</html>')) {
      if (!fixed.endsWith('</body>')) {
        fixed += '\n</body>';
      }
      fixed += '\n</html>';
    }
  } else if (filename.endsWith('.css')) {
    // Try to balance braces
    const openBraces = (fixed.match(/\{/g) || []).length;
    const closeBraces = (fixed.match(/\}/g) || []).length;
    if (openBraces > closeBraces) {
      fixed += '\n' + '}'.repeat(openBraces - closeBraces);
    }
  } else if (filename.endsWith('.json')) {
    // Try to fix JSON
    try {
      JSON.parse(fixed);
    } catch (e) {
      // Attempt simple fixes
      if (!fixed.endsWith('}') && !fixed.endsWith(']')) {
        if (fixed.includes('{') && !fixed.includes('}')) {
          fixed += '\n}';
        } else if (fixed.includes('[') && !fixed.includes(']')) {
          fixed += '\n]';
        }
      }
    }
  }
  
  return fixed;
}

// Planner Agent: Breaks down user request into actionable steps
async function plannerAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  const memory = getMemory();
  
  // Add user request to memory
  await memory.addMessage('user', state.userRequest);
  
  // Get compressed context from memory
  const contextSummary = await memory.getCompressedContext(state.userRequest);
  const sessionFiles = await memory.getSessionFiles();
  
  // Check if there are existing files - if so, this is a modification request
  const hasExistingFiles = Object.keys(state.generatedFiles).length > 0 || sessionFiles.length > 0;
  
  let systemPrompt = `You are a senior software architect. Analyze the user's request and create a clear plan.

${hasExistingFiles ? `
IMPORTANT: There are EXISTING FILES in this session. The user wants to MODIFY or ENHANCE them.
Session files: ${sessionFiles.length > 0 ? sessionFiles.join(', ') : 'None'}
Current state files: ${Object.keys(state.generatedFiles).join(', ')}

Your plan should focus on MODIFYING these existing files, not creating new random files.
` : `
This is a NEW project. Create a plan to build it from scratch.
`}

${contextSummary ? `\nRECENT CONTEXT:\n${smartTruncate(contextSummary, 800)}` : ''}

OUTPUT FORMAT: Just numbered steps like:
1. Create/Modify [specific file] - [what to do]
2. Update [specific file] - [what to change]
3. Add [feature] to [file]

RULES:
- Maximum 5 steps
- Be SPECIFIC about which files to create/modify
- If modifying, say "Modify" or "Update", not "Create"
- Each step should produce tangible code
- Keep it simple and actionable`;

  // Optimize the system prompt
  systemPrompt = promptOptimizer.optimizeSystemPrompt(systemPrompt, contextSummary || undefined);

  let contextInfo = `User request: ${state.userRequest}`;
  
  if (hasExistingFiles) {
    const allFiles = Array.from(new Set([...sessionFiles, ...Object.keys(state.generatedFiles)]));
    contextInfo += `\n\nEXISTING PROJECT FILES:\n${allFiles.map(f => `- ${f}`).join('\n')}`;
    contextInfo += `\n\nThe user wants to modify/enhance the existing project. Create a plan that works WITH these files.`;
  }

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(contextInfo),
  ];

  const response = await llm.invoke(messages);
  const planText = response.content.toString();

  // Add plan to memory
  await memory.addMessage('assistant', `Plan: ${planText}`);

  // Extract numbered steps - clean them up
  const steps = planText
    .split('\n')
    .filter(line => /^\d+\./.test(line.trim()))
    .map(line => line.trim())
    .slice(0, 5); // Limit to 5 steps maximum

  console.log('📋 Plan created:', steps);
  console.log(`📊 Context tokens: ~${estimateTokens(systemPrompt + contextInfo)}`);

  return {
    plan: steps,
    messages: [new AIMessage(`Plan created:\n${steps.join('\n')}`)],
  };
}

// Executor Agent: Uses tools to read, write, modify files, and execute tasks step by step
async function executorAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  const memory = getMemory();
  const currentStep = state.currentIteration;
  const stepToImplement = state.plan[currentStep];

  if (!stepToImplement) {
    return {
      isComplete: true,
      messages: [new AIMessage('All planned steps have been completed.')],
    };
  }

  // Compress file contents if too large
  const summarizedFiles = await summarizeFileContents(state.generatedFiles, 600);
  
  // Get compressed context
  const recentHistory = await memory.getContextSummary();

  let systemPrompt = `You are an expert software engineer. Generate COMPLETE, WORKING code for the current step.

CRITICAL CONTEXT:
- User's original request: ${smartTruncate(state.userRequest, 200)}
- Current step: ${stepToImplement}
- Step ${currentStep + 1} of ${state.plan.length}

EXISTING FILES IN PROJECT:
${Object.keys(summarizedFiles).length > 0 ? Object.keys(summarizedFiles).map(f => `- ${f}`).join('\n') : '- No files yet'}

${recentHistory ? `RECENT HISTORY:\n${smartTruncate(recentHistory, 400)}\n` : ''}

AVAILABLE TOOLS (use these efficiently):
BASIC: read_file, write_file, append_to_file, delete_file, list_directory, search_files
ADVANCED EDITING: replace_in_file, insert_at_line, delete_lines, read_lines, replace_block, replace_line_range
FILE MANAGEMENT: get_file_info, create_directory, copy_file, move_file
PROJECT: get_project_structure, execute_command

STRATEGY (choose most efficient tool):
1. NEW files → write_file
2. MODIFY files → read_file first, then:
   - replace_block (if you know start/end markers) [MOST EFFICIENT]
   - replace_line_range (if you know line numbers) [VERY EFFICIENT]
   - replace_in_file (for find/replace patterns)
   - insert_at_line, delete_lines (for targeted changes)
3. REFACTOR → replace_in_file with regex
4. ORGANIZE → create_directory, move_file, copy_file
5. DEPENDENCIES → execute_command
6. CHECK → get_project_structure, list_directory, search_files

RULES:
1. Generate COMPLETE, FUNCTIONAL code - not placeholders
2. Use most efficient tool (replace_block > replace_line_range > rewriting file)
3. Make sure new files work WITH existing files (proper linking, imports)
4. Use relative file paths: filename.ext (saved in project folder automatically)
5. For HTML/CSS/JS: ensure files are properly linked
6. Keep context - modify EXISTING files, don't create new random files
7. Use most appropriate tool (don't write_file when should replace_block)

OUTPUT FORMAT:
FILENAME: filename.ext
\`\`\`language
[COMPLETE CODE HERE - NO PLACEHOLDERS]
\`\`\`

You can output multiple files if needed for this step.`;

  // Optimize the system prompt
  systemPrompt = promptOptimizer.optimizeSystemPrompt(systemPrompt, recentHistory || undefined);

  // Include existing file contents for context (compressed)
  let existingFilesContext = '';
  if (Object.keys(summarizedFiles).length > 0) {
    existingFilesContext = '\n\nEXISTING FILE CONTENTS (key sections):\n';
    for (const [filename, content] of Object.entries(summarizedFiles)) {
      existingFilesContext += `\n--- ${filename} ---\n${content}\n`;
    }
  }

  const fullPrompt = systemPrompt + existingFilesContext;
  const promptTokens = estimateTokens(fullPrompt);
  
  console.log(`📊 Executor prompt tokens: ~${promptTokens}`);

  const codeGenMessages = [
    new SystemMessage(fullPrompt),
    new HumanMessage(`Generate COMPLETE code for step: "${stepToImplement}"

Remember:
- This is part of: ${smartTruncate(state.userRequest, 150)}
- ${Object.keys(state.generatedFiles).length > 0 ? 'Files already exist - modify them or create new ones that work with them' : 'Create new files from scratch'}
- Make it FUNCTIONAL and COMPLETE`)
  ];

  try {
    const codeResult = await llm.invoke(codeGenMessages);
    const newFiles = parseGeneratedFiles(codeResult.content.toString());

    console.log(`📁 Step ${currentStep + 1} generated ${Object.keys(newFiles).length} files`);

    // IMMEDIATELY save and validate each generated file
    const validatedFiles: Record<string, string> = {};
    const projectFolder = getProjectFolder();
    
    for (const [filename, content] of Object.entries(newFiles)) {
      // Validate file before saving
      const validation = validateFileContent(filename, content);
      
      if (!validation.isValid) {
        console.warn(`⚠️ File ${filename} failed validation: ${validation.reason}`);
        console.log(`🔄 Attempting to fix ${filename}...`);
        
        // Try to auto-fix common issues
        let fixedContent = content;
        if (validation.reason.includes('incomplete')) {
          fixedContent = autoFixIncompleteFile(filename, content);
        }
        
        // Re-validate
        const revalidation = validateFileContent(filename, fixedContent);
        if (revalidation.isValid) {
          console.log(`✅ Auto-fixed ${filename}`);
          validatedFiles[filename] = fixedContent;
        } else {
          console.error(`❌ Could not fix ${filename}, using original`);
          validatedFiles[filename] = content;
        }
      } else {
        console.log(`✅ ${filename} validated successfully`);
        validatedFiles[filename] = content;
      }
      
      // Save file immediately to disk
      const fullPath = path.isAbsolute(filename) ? filename : path.join(projectFolder, filename);
      const dir = path.dirname(fullPath);
      
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      
      const exists = fs.existsSync(fullPath);
      fs.writeFileSync(fullPath, validatedFiles[filename], 'utf-8');
      console.log(`💾 Saved ${filename} to disk immediately`);
      
      // Track in memory
      memory.addFileOperation(exists ? 'modified' : 'created', fullPath);
    }

    // Merge with existing files (new files overwrite old ones with same name)
    const updatedFiles = { ...state.generatedFiles, ...validatedFiles };

    const completion = `Step ${currentStep + 1} completed. ${Object.keys(validatedFiles).length > 0 ? `Generated/updated ${Object.keys(validatedFiles).length} file(s): ${Object.keys(validatedFiles).join(', ')}` : 'Step required no code changes.'}`;

    // Add completion to memory
    memory.addMessage('assistant', completion);

    return {
      generatedFiles: updatedFiles,
      currentIteration: currentStep + 1,
      messages: [new AIMessage(completion)],
    };

  } catch (error) {
    console.error('Executor error:', error);
    return {
      currentIteration: currentStep + 1,
      messages: [new AIMessage(`Error implementing step: ${error}`)],
    };
  }
}

// Code Reviewer Agent: Reviews generated code and provides feedback
async function reviewerAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  console.log('🔍 Starting detailed file review...');
  
  // Use the same validation function we use during generation
  const fileValidation: Record<string, { isValid: boolean; reason: string }> = {};
  
  for (const [filename, code] of Object.entries(state.generatedFiles)) {
    fileValidation[filename] = validateFileContent(filename, code);
    console.log(`  ${fileValidation[filename].isValid ? '✅' : '❌'} ${filename}: ${fileValidation[filename].reason || 'Valid'}`);
  }

  // Create summary for LLM (use smart truncation)
  const fileSummaries = Object.entries(state.generatedFiles)
    .map(([filename, code]) => {
      const status = fileValidation[filename];
      const preview = code.length > 500 ? 
        `${code.substring(0, 250)}...\n[${code.length} chars total]\n...${code.substring(code.length - 250)}` : 
        code;
      return `${filename} (${status.isValid ? '✅ Valid' : '❌ Invalid: ' + status.reason}):\n\`\`\`\n${preview}\n\`\`\``;
    })
    .join('\n\n');

  const systemPrompt = `You are a code reviewer. Review the project against the original request.

ORIGINAL REQUEST: ${state.userRequest}

FILE VALIDATION RESULTS:
${Object.entries(fileValidation).map(([f, s]) => `- ${f}: ${s.isValid ? '✅ Valid' : '❌ ' + s.reason}`).join('\n')}

Check:
1. Are ALL files needed for the request present?
2. Are files properly linked together (HTML links CSS/JS, imports work, etc.)?
3. Does it fulfill the user's request?
4. Are all files complete and functional (no placeholders)?
5. For UI modifications: Are the existing files actually modified appropriately?

Say "APPROVED" if:
- All files are valid (see validation results above)
- All necessary files exist
- Files work together properly
- Request is fully fulfilled
- No placeholders or TODOs

If something is missing or broken, explain SPECIFICALLY what needs to be fixed in which file.`;

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review the project:\n\n${fileSummaries}\n\nDoes this fulfill: "${state.userRequest}"?`),
  ];

  const response = await llm.invoke(messages);
  const feedback = response.content.toString();

  // Check if all files are actually complete
  const allFilesComplete = Object.values(fileValidation).every(f => f.isValid);
  
  // Only approve if files are complete AND LLM approves AND no major issues mentioned
  const isApproved = allFilesComplete &&
                     feedback.toUpperCase().includes('APPROVED') &&
                     !feedback.toLowerCase().includes('missing') &&
                     !feedback.toLowerCase().includes('not implemented');

  const reviewIter = (state.reviewIterations || 0) + 1;
  const maxReviewIterations = 3; // Prevent infinite loops
  
  console.log(`✅ Review iteration ${reviewIter}: ${isApproved ? 'APPROVED' : 'NEEDS WORK'}`);
  console.log(`📝 Feedback: ${feedback.substring(0, 200)}...`);
  
  if (!allFilesComplete) {
    console.log('⚠️  Some files are incomplete:', 
      Object.entries(fileValidation)
        .filter(([_, s]) => !s.isValid)
        .map(([f, s]) => `${f}: ${s.reason}`)
    );
  }

  // If not approved and under max iterations, we'll retry with feedback
  // If max iterations reached, force completion
  const shouldComplete = isApproved || reviewIter >= maxReviewIterations;
  
  if (reviewIter >= maxReviewIterations && !isApproved) {
    console.log('⚠️  Max review iterations reached, completing anyway');
  }

  return {
    reviewFeedback: feedback,
    isComplete: shouldComplete && state.currentIteration >= state.plan.length,
    reviewIterations: reviewIter,
    messages: [new AIMessage(`Review: ${feedback}`)],
  };
}

// Fixer Agent: Takes reviewer feedback and fixes issues
async function fixerAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  const memory = getMemory();
  
  console.log('🔧 Fixing issues based on review feedback...');
  
  const feedback = state.reviewFeedback;
  
  // Summarize files
  const summarizedFiles = await summarizeFileContents(state.generatedFiles, 600);
  
  let systemPrompt = `You are an expert software engineer fixing code issues.

ORIGINAL REQUEST: ${state.userRequest}

REVIEWER FEEDBACK (ISSUES TO FIX):
${feedback}

CURRENT FILES:
${Object.keys(summarizedFiles).map(f => `- ${f}`).join('\n')}

Your task: Fix the SPECIFIC issues mentioned in the reviewer feedback.

AVAILABLE TOOLS:
- read_file, write_file (for complete rewrites)
- replace_block, replace_line_range (for targeted fixes)
- replace_in_file, insert_at_line, delete_lines (for precise edits)

RULES:
1. Address EACH issue mentioned in the feedback
2. Use the most efficient tool (replace_block > replace_line_range > full rewrite)
3. Make COMPLETE fixes, not placeholders
4. Preserve existing working code
5. Output format: FILENAME: filename.ext followed by code blocks

Fix the issues now.`;

  systemPrompt = promptOptimizer.optimizeSystemPrompt(systemPrompt, feedback);

  let existingFilesContext = '\n\nCURRENT FILE CONTENTS:\n';
  for (const [filename, content] of Object.entries(summarizedFiles)) {
    existingFilesContext += `\n--- ${filename} ---\n${content}\n`;
  }

  const messages = [
    new SystemMessage(systemPrompt + existingFilesContext),
    new HumanMessage(`Fix these issues:\n${feedback}\n\nMake the fixes complete and functional.`)
  ];

  try {
    const fixResult = await llm.invoke(messages);
    const fixedFiles = parseGeneratedFiles(fixResult.content.toString());

    if (Object.keys(fixedFiles).length > 0) {
      console.log(`🔧 Fixed ${Object.keys(fixedFiles).length} files: ${Object.keys(fixedFiles).join(', ')}`);

      // Validate and save fixed files immediately
      const validatedFiles: Record<string, string> = {};
      const projectFolder = getProjectFolder();
      
      for (const [filename, content] of Object.entries(fixedFiles)) {
        const validation = validateFileContent(filename, content);
        
        if (!validation.isValid) {
          console.warn(`⚠️ Fixed file ${filename} still invalid: ${validation.reason}`);
          const fixedContent = autoFixIncompleteFile(filename, content);
          const revalidation = validateFileContent(filename, fixedContent);
          
          if (revalidation.isValid) {
            console.log(`✅ Auto-fixed ${filename}`);
            validatedFiles[filename] = fixedContent;
          } else {
            validatedFiles[filename] = content;
          }
        } else {
          console.log(`✅ ${filename} fixed and validated`);
          validatedFiles[filename] = content;
        }
        
        // Save immediately
        const fullPath = path.isAbsolute(filename) ? filename : path.join(projectFolder, filename);
        const dir = path.dirname(fullPath);
        
        if (!fs.existsSync(dir)) {
          fs.mkdirSync(dir, { recursive: true });
        }
        
        fs.writeFileSync(fullPath, validatedFiles[filename], 'utf-8');
        console.log(`💾 Saved fixed ${filename} to disk`);
        memory.addFileOperation('modified', fullPath);
      }

      // Merge fixed files back into state
      const updatedFiles = { ...state.generatedFiles, ...validatedFiles };

      return {
        generatedFiles: updatedFiles,
        reviewFeedback: '', // Clear feedback so we review again
        messages: [new AIMessage(`Fixed ${Object.keys(validatedFiles).length} files based on review feedback`)],
      };
    } else {
      console.log('⚠️  No fixes generated, proceeding to re-review');
      return {
        reviewFeedback: '', // Clear so we review again
        messages: [new AIMessage('Attempted fixes, proceeding to review')],
      };
    }
  } catch (error) {
    console.error('Fixer error:', error);
    return {
      messages: [new AIMessage(`Error fixing issues: ${error}`)],
    };
  }
}

// Router: Decides next step
function shouldContinue(state: AgentStateType): string {
  // If marked complete, we're done
  if (state.isComplete) {
    return 'end';
  }

  // Start with planning if no plan exists
  if (state.plan.length === 0) {
    return 'planner';
  }

  // If we haven't finished all steps, continue generating
  if (state.currentIteration < state.plan.length) {
    return 'generator';
  }

  // All steps completed, need review
  if (!state.reviewFeedback) {
    return 'reviewer';
  }

  // Review feedback exists - check if approved
  const feedback = state.reviewFeedback.toUpperCase();
  const isApproved = feedback.includes('APPROVED') && 
                     !feedback.toLowerCase().includes('missing') &&
                     !feedback.toLowerCase().includes('not implemented');
  
  if (isApproved) {
    // Approved - we're done!
    return 'end';
  }

  // Not approved - check if we can retry
  const reviewIter = state.reviewIterations || 0;
  if (reviewIter >= 3) {
    // Max iterations reached, force end
    console.log('⚠️  Max review iterations reached in router, ending');
    return 'end';
  }

  // Not approved and can retry - go back to executor to fix issues
  console.log(`🔄 Review not approved (iteration ${reviewIter}), retrying executor to fix issues`);
  
  // Reset current iteration to re-execute all steps with feedback
  return 'fix_issues';
}

// Helper function to parse generated files from LLM output
function parseGeneratedFiles(content: string): Record<string, string> {
  const files: Record<string, string> = {};
  const fileRegex = /FILENAME:\s*(.+?)\n```(\w+)?\n([\s\S]*?)```/g;

  let match;
  while ((match = fileRegex.exec(content)) !== null) {
    const filename = match[1].trim();
    const code = match[3].trim();
    files[filename] = code;
  }

  return files;
}

// Build the workflow graph
export function createLovableAgentGraph() {
  const workflow = new StateGraph(AgentState)
    .addNode('planner', plannerAgent)
    .addNode('generator', executorAgent)
    .addNode('reviewer', reviewerAgent)
    .addNode('fix_issues', fixerAgent)
    .addEdge(START, 'planner')
    .addConditionalEdges('planner', shouldContinue, {
      generator: 'generator',
      end: END,
    })
    .addConditionalEdges('generator', shouldContinue, {
      generator: 'generator',
      reviewer: 'reviewer',
      end: END,
    })
    .addConditionalEdges('reviewer', shouldContinue, {
      fix_issues: 'fix_issues',
      end: END,
    })
    .addConditionalEdges('fix_issues', shouldContinue, {
      reviewer: 'reviewer',
      end: END,
    });

  return workflow.compile();
}

// Streaming versions with real-time updates
async function streamingPlannerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Planning your request...' });

  const result = await plannerAgent(state);

  if (result.plan) {
    emitEvent(sessionId || '', { type: 'plan', plan: result.plan });
  }

  return result;
}

async function streamingCodeGeneratorAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  const currentStep = state.currentIteration;
  const stepToImplement = state.plan[currentStep];

  emitEvent(sessionId || '', {
    type: 'status',
    message: `Generating code for step ${currentStep + 1}: ${stepToImplement?.substring(0, 50)}...`
  });

  const result = await executorAgent(state);

  // Extract and emit chain of thought
  if (result.messages && result.messages.length > 0) {
    const content = result.messages[result.messages.length - 1].content.toString();
    const cotMatch = content.match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
    if (cotMatch) {
      const reasoning = cotMatch[1].trim();
      console.log(`🔍 Real-time COT Step ${currentStep + 1}: ${reasoning.substring(0, 100)}...`);
      emitEvent(sessionId || '', {
        type: 'chain_of_thought',
        step: currentStep + 1,
        reasoning: reasoning
      });
    }
  }

  if (result.generatedFiles && Object.keys(result.generatedFiles).length > 0) {
    const files = Object.keys(result.generatedFiles);
    console.log(`📁 Real-time Files Generated: ${files.join(', ')}`);
    emitEvent(sessionId || '', {
      type: 'files_generated',
      files: files,
      step: currentStep + 1
    });
  }

  return result;
}

async function streamingReviewerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Reviewing generated code...' });

  const result = await reviewerAgent(state);

  if (result.reviewFeedback) {
    console.log(`✅ Real-time Review: ${result.reviewFeedback.substring(0, 100)}...`);
    emitEvent(sessionId || '', { type: 'review', feedback: result.reviewFeedback });
  }

  if (result.isComplete) {
    emitEvent(sessionId || '', { type: 'complete', message: 'Code generation completed successfully!' });
  }

  return result;
}

async function streamingFixerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Fixing issues based on review...' });

  const result = await fixerAgent(state);

  if (result.generatedFiles && Object.keys(result.generatedFiles).length > 0) {
    const files = Object.keys(result.generatedFiles);
    console.log(`🔧 Real-time Fixes Applied: ${files.join(', ')}`);
    emitEvent(sessionId || '', {
      type: 'files_fixed',
      files: files,
    });
  }

  return result;
}

// Streaming agent graph
export function createStreamingLovableAgentGraph(sessionId?: string, model?: string) {
  // Update LLM if a specific model is requested
  if (model) {
    llm = createLLM(model);
  }

  const workflow = new StateGraph(AgentState)
    .addNode('planner', (state) => streamingPlannerAgent(state, sessionId, model))
    .addNode('generator', (state) => streamingCodeGeneratorAgent(state, sessionId, model))
    .addNode('reviewer', (state) => streamingReviewerAgent(state, sessionId, model))
    .addNode('fix_issues', (state) => streamingFixerAgent(state, sessionId, model))
    .addEdge(START, 'planner')
    .addConditionalEdges('planner', shouldContinue, {
      generator: 'generator',
      end: END,
    })
    .addConditionalEdges('generator', shouldContinue, {
      generator: 'generator',
      reviewer: 'reviewer',
      end: END,
    })
    .addConditionalEdges('reviewer', shouldContinue, {
      fix_issues: 'fix_issues',
      end: END,
    })
    .addConditionalEdges('fix_issues', shouldContinue, {
      reviewer: 'reviewer',
      end: END,
    });

  return workflow.compile();
}

// Helper function to save generated files to disk
export function saveGeneratedFiles(files: Record<string, string>, outputDir?: string) {
  const memory = getMemory();
  
  // Use project folder if no output directory specified
  const targetDir = outputDir || getProjectFolder();
  
  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }

  const savedFiles: string[] = [];

  for (const [filename, content] of Object.entries(files)) {
    const fullPath = path.join(targetDir, filename);
    const dir = path.dirname(fullPath);

    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    const exists = fs.existsSync(fullPath);
    fs.writeFileSync(fullPath, content, 'utf-8');
    
    // Track in memory
    memory.addFileOperation(exists ? 'modified' : 'created', fullPath);
    
    savedFiles.push(fullPath);
  }

  return savedFiles;
}

// Export tool logger statistics
export function getToolCallStats() {
  return toolLogger.getStats();
}

export function getToolCallSummary() {
  return toolLogger.getSummary();
}

export function clearToolCallLogs() {
  toolLogger.clear();
}
