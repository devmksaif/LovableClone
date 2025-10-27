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
import { getMemory, getProjectFolder } from './utils';
import { toolLogger } from '../utils/tool-logger';
import { searchSimilarCode, getProjectContext } from '../utils/vector-tools';

// File operation tools
export const readFileTool = tool(async ({ filePath }) => {
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

export const writeFileTool = tool(async ({ filePath, content }) => {
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

export const appendToFileTool = tool(async ({ filePath, content }) => {
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

export const deleteFileTool = tool(async ({ filePath }) => {
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

export const listDirectoryTool = tool(async ({ dirPath }) => {
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

export const searchFilesTool = tool(async ({ dirPath, pattern }) => {
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
export const replaceInFileTool = tool(async ({ filePath, searchText, replaceText }) => {
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

export const insertAtLineTool = tool(async ({ filePath, lineNumber, content }) => {
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

export const deleteLinesTool = tool(async ({ filePath, startLine, endLine }) => {
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

export const replaceBlockTool = tool(async ({ filePath, startMarker, endMarker, newContent }) => {
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

export const replaceLineRangeTool = tool(async ({ filePath, startLine, endLine, newContent }) => {
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

export const getFileInfoTool = tool(async ({ filePath }) => {
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

export const createDirectoryTool = tool(async ({ dirPath }) => {
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

export const copyFileTool = tool(async ({ sourcePath, destinationPath }) => {
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

export const moveFileTool = tool(async ({ sourcePath, destinationPath }) => {
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

export const readLinesTool = tool(async ({ filePath, startLine, endLine }) => {
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

export const getProjectStructureTool = tool(async ({ maxDepth }) => {
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

export const executeCommandTool = tool(async ({ command, description }) => {
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

// Vector search tools
export const searchSimilarCodeTool = tool(async ({ query, maxResults }) => {
  const projectId = 'agent_context_project';
  console.log(`🔍 Searching for similar code: "${query}" in project ${projectId}`);

  const result = await searchSimilarCode(query, projectId, maxResults || 5);
  return result;
}, {
  name: 'search_similar_code',
  description: 'Search for similar code examples in the vector database. Use this to find relevant code patterns and implementations.',
  schema: z.object({
    query: z.string().describe('The code or concept to search for'),
    maxResults: z.number().optional().describe('Maximum number of results to return (default: 5)')
  }),
});

export const getProjectContextTool = tool(async () => {
  const projectId = 'agent_context_project';
  console.log(`📊 Getting project context for: ${projectId}`);

  const result = await getProjectContext(projectId);
  return result;
}, {
  name: 'get_project_context',
  description: 'Get comprehensive project statistics and structure information from the vector database.',
  schema: z.object({}),
});

// Create the tools array with all tools
export const tools = [
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
  deleteLinesTool,
  replaceBlockTool,
  replaceLineRangeTool,
  readLinesTool,
  // File management
  getFileInfoTool,
  createDirectoryTool,
  copyFileTool,
  moveFileTool,
  // Project tools
  getProjectStructureTool,
  executeCommandTool,
  // Vector search tools
  searchSimilarCodeTool,
  getProjectContextTool,
];

// Helper function to wrap tool execution with logging
export function wrapToolWithLogging(toolFn: any, toolName: string) {
  return async (...args: any[]) => {
    const input = args[0] || {};
    const callId = toolLogger.startCall(toolName, input);
    try {
      // Support multiple tool shapes returned by `tool()` or custom wrappers.
      // Common possibilities:
      // - a plain function: toolFn(argsObj)
      // - an object with .call(argsObj)
      // - an object with .invoke(argsObj)
      // - an object with .run(argsObj)
      let result: any;

      if (typeof toolFn === 'function') {
        result = await toolFn(input);
      } else if (toolFn && typeof toolFn.call === 'function') {
        result = await toolFn.call(input);
      } else if (toolFn && typeof toolFn.invoke === 'function') {
        result = await toolFn.invoke(input);
      } else if (toolFn && typeof toolFn.run === 'function') {
        result = await toolFn.run(input);
      } else if (toolFn && typeof toolFn.execute === 'function') {
        result = await toolFn.execute(input);
      } else {
        throw new Error('Tool is not callable');
      }

      toolLogger.endCall(callId, result, true);
      return result;
    } catch (error: any) {
      const errorMsg = error?.message || String(error);
      toolLogger.endCall(callId, errorMsg, false, errorMsg);
      throw error;
    }
  };
}