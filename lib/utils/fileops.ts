import * as fs from 'fs';
import * as path from 'path';
import { z } from 'zod';

// Configuration for safe file operations
const SAFE_DIRECTORIES = [
  './generated',
  './workspace',
  './temp',
];

const ALLOWED_EXTENSIONS = [
  '.ts', '.tsx', '.js', '.jsx', '.json', '.css', '.html', '.md', '.txt',
  '.yaml', '.yml', '.xml', '.sql', '.py', '.rs', '.go', '.java', '.c', '.cpp',
  'Dockerfile', '.gitignore', '.env.example'
];

function isPathSafe(filePath: string): boolean {
  const normalizedPath = path.resolve(filePath);
  const cwd = process.cwd();

  // Check if path is within allowed directories
  const allowed = SAFE_DIRECTORIES.some(dir => {
    const resolvedDir = path.resolve(path.join(cwd, dir));
    return normalizedPath.startsWith(resolvedDir);
  });

  // Check file extension
  const ext = path.extname(filePath);
  const extAllowed = ALLOWED_EXTENSIONS.includes(ext) || ext === '' || filePath.includes('Dockerfile');

  return allowed && extAllowed && !filePath.includes('..');
}

// File read operation
export async function readFile(filePath: string): Promise<{success: boolean, content?: string, error?: string}> {
  try {
    if (!isPathSafe(filePath)) {
      return {success: false, error: 'Path not allowed for security reasons'};
    }

    if (!fs.existsSync(filePath)) {
      return {success: false, error: 'File does not exist'};
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    return {success: true, content};
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error reading file'
    };
  }
}

// File write operation
export async function writeFile(filePath: string, content: string): Promise<{success: boolean, error?: string}> {
  try {
    if (!isPathSafe(filePath)) {
      return {success: false, error: 'Path not allowed for security reasons'};
    }

    // Ensure directory exists
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    fs.writeFileSync(filePath, content, 'utf-8');
    return {success: true};
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error writing file'
    };
  }
}

// File modification (append)
export async function appendToFile(filePath: string, content: string): Promise<{success: boolean, error?: string}> {
  try {
    if (!isPathSafe(filePath)) {
      return {success: false, error: 'Path not allowed for security reasons'};
    }

    fs.appendFileSync(filePath, content, 'utf-8');
    return {success: true};
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error appending to file'
    };
  }
}

// File deletion
export async function deleteFile(filePath: string): Promise<{success: boolean, error?: string}> {
  try {
    if (!isPathSafe(filePath)) {
      return {success: false, error: 'Path not allowed for security reasons'};
    }

    if (!fs.existsSync(filePath)) {
      return {success: false, error: 'File does not exist'};
    }

    // Only allow deletion of generated files
    const isInGenerated = filePath.startsWith(path.resolve('./generated'));
    if (!isInGenerated) {
      return {success: false, error: 'Deletion only allowed for generated files'};
    }

    fs.unlinkSync(filePath);
    return {success: true};
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error deleting file'
    };
  }
}

// List directory
export async function listDirectory(dirPath: string): Promise<{success: boolean, files?: string[], error?: string}> {
  try {
    if (!isPathSafe(dirPath) && !SAFE_DIRECTORIES.some(dir => dirPath.includes(dir))) {
      return {success: false, error: 'Path not allowed for security reasons'};
    }

    if (!fs.existsSync(dirPath)) {
      return {success: false, error: 'Directory does not exist'};
    }

    const files = fs.readdirSync(dirPath);
    return {success: true, files};
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error listing directory'
    };
  }
}

// Check if file exists
export async function fileExists(filePath: string): Promise<boolean> {
  try {
    return fs.existsSync(filePath);
  } catch {
    return false;
  }
}

// Helper function for recursive directory search
function searchDirectory(currentPath: string, pattern: string, matches: Array<{file: string, content: string, line: number}>) {
  try {
    const items = fs.readdirSync(currentPath);

    for (const item of items) {
      const fullPath = path.join(currentPath, item);
      const stat = fs.statSync(fullPath);

      if (stat.isDirectory()) {
        // Skip node_modules and .git
        if (item !== 'node_modules' && item !== '.git' && item !== '.next') {
          searchDirectory(fullPath, pattern, matches);
        }
      } else if (stat.isFile()) {
        // Check if file extension is allowed
        const ext = path.extname(item);
        if (ALLOWED_EXTENSIONS.includes(ext) || ext === '' || item.includes('Dockerfile')) {
          try {
            const content = fs.readFileSync(fullPath, 'utf-8');
            const lines = content.split('\n');

            lines.forEach((line, index) => {
              if (new RegExp(pattern, 'i').test(line)) {
                matches.push({
                  file: fullPath,
                  content: line.trim(),
                  line: index + 1,
                });
              }
            });
          } catch (error) {
            // Skip files that can't be read (binary files, etc.)
            continue;
          }
        }
      }
    }
  } catch (error) {
    // Skip directories we can't read
    return;
  }
}

// Regex file search operation
export async function searchFiles(dirPath: string, pattern: string): Promise<{success: boolean, matches?: Array<{file: string, content: string, line: number}>, error?: string}> {
  try {
    if (!isPathSafe(dirPath) && !SAFE_DIRECTORIES.some(dir => dirPath.includes(dir))) {
      return {success: false, error: 'Path not allowed for security reasons'};
    }

    // Ensure base directory exists
    if (!fs.existsSync(dirPath)) {
      return {success: false, error: 'Directory does not exist'};
    }

    const matches: Array<{file: string, content: string, line: number}> = [];

    searchDirectory(dirPath, pattern, matches);

    return {success: true, matches};
  } catch (error) {
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error during file search'
    };
  }
}

// Schema definitions for tool calls
export const FileReadSchema = z.object({
  filePath: z.string().describe('Path to the file to read'),
});

export const FileWriteSchema = z.object({
  filePath: z.string().describe('Path where to create/modify the file'),
  content: z.string().describe('Content to write to the file'),
});

export const FileAppendSchema = z.object({
  filePath: z.string().describe('Path to the file to append to'),
  content: z.string().describe('Content to append to the file'),
});

export const FileDeleteSchema = z.object({
  filePath: z.string().describe('Path to the file to delete'),
});

export const DirectoryListSchema = z.object({
  dirPath: z.string().describe('Path to the directory to list'),
});

export const FileSearchSchema = z.object({
  dirPath: z.string().describe('Directory to search in'),
  pattern: z.string().describe('Regex pattern to search for (JavaScript regex syntax)'),
});
