import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';
import { chromaManager, generateChunkId } from '../db/chroma';
// Supported languages and their file extensions
const SUPPORTED_LANGUAGES = {
    typescript: ['.ts', '.tsx'],
    javascript: ['.js', '.jsx'],
    python: ['.py'],
    java: ['.java'],
    csharp: ['.cs'],
    go: ['.go'],
    rust: ['.rs'],
    cpp: ['.cpp', '.cc', '.cxx'],
    c: ['.c', '.h'],
    php: ['.php'],
    ruby: ['.rb'],
    swift: ['.swift'],
    kotlin: ['.kt'],
    scala: ['.scala'],
    json: ['.json'],
    yaml: ['.yaml', '.yml'],
    xml: ['.xml'],
    html: ['.html'],
    css: ['.css', '.scss', '.sass'],
    markdown: ['.md'],
    dockerfile: ['Dockerfile', '.dockerfile'],
    shell: ['.sh', '.bash', '.zsh'],
    sql: ['.sql'],
    makefile: ['Makefile', 'makefile']
};
// Code separators for semantic chunking
const CODE_SEPARATORS = {
    typescript: /\b(class|function|interface|type|const|let|var|export|import|if|for|while|switch|try|catch)\b/g,
    javascript: /\b(class|function|const|let|var|export|import|if|for|while|switch|try|catch)\b/g,
    python: /\b(class|def|if|for|while|try|except|with|import|from)\b/g,
    java: /\b(class|interface|public|private|protected|static|final|void|String|int|boolean)\b/g,
    go: /\b(func|type|struct|interface|package|import|var|const|if|for|switch|select)\b/g,
    rust: /\b(fn|struct|enum|impl|trait|let|const|fn|if|for|while|match|use)\b/g,
    php: /\b(class|function|public|private|protected|static|final|abstract|interface)\b/g,
    csharp: /\b(class|interface|public|private|protected|static|void|string|int|bool|using|namespace)\b/g
};
export class ProjectEmbeddingService {
    constructor(projectId, sourceDir = './generated') {
        this.projectId = projectId;
        this.sourceDir = sourceDir;
    }
    // Main method to embed entire project
    async embedProject() {
        console.log(`🎯 Starting project embedding for: ${this.projectId}`);
        try {
            // Initialize ChromaDB collections
            await chromaManager.initializeProjectCollections(this.projectId);
            // Scan and process all files
            const files = await this.scanProjectFiles();
            console.log(`📂 Found ${files.length} files in project`);
            // Process different types of content
            const codeChunks = await this.processCodeFiles(files);
            const structureChunks = await this.createStructureEmbeddings(files);
            // Store in ChromaDB
            await chromaManager.addCodeChunks(this.projectId, codeChunks);
            await chromaManager.addStructureChunks(this.projectId, structureChunks);
            console.log(`✅ Successfully embedded project: ${this.projectId}`);
        }
        catch (error) {
            console.error('❌ Failed to embed project:', error);
            throw error;
        }
    }
    // Scan all files in the project directory
    async scanProjectFiles() {
        const files = [];
        const self = this;
        function scanDirectory(dirPath) {
            try {
                const items = fs.readdirSync(dirPath);
                for (const item of items) {
                    const fullPath = path.join(dirPath, item);
                    const stat = fs.statSync(fullPath);
                    if (stat.isDirectory()) {
                        // Skip common directories
                        if (!['node_modules', '.git', '.next', 'dist', 'build', 'target'].includes(item)) {
                            scanDirectory(fullPath);
                        }
                    }
                    else if (stat.isFile()) {
                        const ext = path.extname(item);
                        const language = self.detectLanguage(ext);
                        if (language && stat.size < 1024 * 1024) { // Skip files > 1MB
                            try {
                                const content = fs.readFileSync(fullPath, 'utf-8');
                                files.push({
                                    filename: path.relative(self.sourceDir, fullPath),
                                    content,
                                    language,
                                    size: stat.size,
                                    lastModified: stat.mtime
                                });
                            }
                            catch (error) {
                                // Skip binary or unreadable files
                                continue;
                            }
                        }
                    }
                }
            }
            catch (error) {
                console.warn(`⚠️ Could not scan directory: ${dirPath}`);
            }
        }
        scanDirectory(this.sourceDir);
        return files;
    }
    // Detect programming language from file extension
    detectLanguage(extension) {
        for (const [language, extensions] of Object.entries(SUPPORTED_LANGUAGES)) {
            if (extensions.some(ext => extension === ext || extension.toLowerCase() === ext)) {
                return language;
            }
        }
        return null;
    }
    // Process code files and create semantic chunks
    async processCodeFiles(files) {
        const chunks = [];
        for (const file of files) {
            const fileChunks = await this.createCodeChunks(file);
            chunks.push(...fileChunks);
        }
        return chunks;
    }
    // Create semantic code chunks
    async createCodeChunks(file) {
        const chunks = [];
        const lines = file.content.split('\n');
        const separators = CODE_SEPARATORS[file.language];
        if (!separators) {
            // Simple line-based chunking for unsupported languages
            return this.createLineBasedChunks(file);
        }
        // Find semantic boundaries
        const boundaries = [0];
        let currentIndex = 0;
        separators.lastIndex = 0; // Reset regex state
        let match;
        while ((match = separators.exec(file.content)) !== null) {
            const lineStart = file.content.substr(0, match.index).split('\n').length - 1;
            if (lineStart - currentIndex > 5) { // Minimum chunk size
                boundaries.push(lineStart);
                currentIndex = lineStart;
                if (boundaries.length >= 10)
                    break; // Limit chunks per file
            }
        }
        boundaries.push(lines.length);
        // Create chunks between boundaries
        for (let i = 0; i < boundaries.length - 1; i++) {
            const startLine = boundaries[i];
            const endLine = boundaries[i + 1];
            const chunkContent = lines.slice(startLine, endLine).join('\n');
            if (chunkContent.trim().length > 50) { // Skip very small chunks
                const chunkId = generateChunkId(this.projectId, file.filename, [startLine, endLine], 'code');
                const contentHash = crypto.createHash('sha256').update(chunkContent).digest('hex');
                const metadata = {
                    project_id: this.projectId,
                    type: 'code',
                    filename: file.filename,
                    language: file.language,
                    lines_start: startLine,
                    lines_end: endLine,
                    dependencies: this.extractDependencies(chunkContent, file.language),
                    parent_functions: this.extractParentFunctions(chunkContent, file.language),
                    content_hash: contentHash,
                    timestamp: new Date().toISOString()
                };
                chunks.push({
                    id: chunkId,
                    content: chunkContent.trim(),
                    metadata
                });
            }
        }
        return chunks;
    }
    // Fallback line-based chunking for unsupported languages
    createLineBasedChunks(file) {
        const chunks = [];
        const lines = file.content.split('\n');
        const chunkSize = 20; // Lines per chunk
        for (let i = 0; i < lines.length; i += chunkSize) {
            const chunkLines = lines.slice(i, i + chunkSize);
            const chunkContent = chunkLines.join('\n');
            if (chunkContent.trim().length > 0) {
                const chunkId = generateChunkId(this.projectId, file.filename, [i, i + chunkSize], 'code');
                const contentHash = crypto.createHash('sha256').update(chunkContent).digest('hex');
                const metadata = {
                    project_id: this.projectId,
                    type: 'code',
                    filename: file.filename,
                    language: file.language,
                    lines_start: i,
                    lines_end: i + chunkSize,
                    dependencies: this.extractDependencies(chunkContent, file.language),
                    parent_functions: this.extractParentFunctions(chunkContent, file.language),
                    content_hash: contentHash,
                    timestamp: new Date().toISOString()
                };
                chunks.push({
                    id: chunkId,
                    content: chunkContent.trim(),
                    metadata
                });
            }
        }
        return chunks;
    }
    // Extract dependencies from code
    extractDependencies(content, language) {
        const imports = [];
        try {
            if (['typescript', 'javascript'].includes(language)) {
                const importMatches = content.match(/import\s+.*?\s+from\s+['"](.+?)['"]/g) || [];
                const requireMatches = content.match(/require\s*\(\s*['"](.+?)['"]\s*\)/g) || [];
                [...importMatches, ...requireMatches].forEach(match => {
                    if (/^['"`]/.test(match)) {
                        const dep = match.match(/['"](.+?)['"]/)?.[1];
                        if (dep && !dep.startsWith('.'))
                            imports.push(dep.split('/')[0]);
                    }
                });
            }
            else if (language === 'python') {
                const matches = content.match(/^(?:from\s+(.+?)\s+import|import\s+(.+))/gm) || [];
                matches.forEach(match => {
                    const dep = (match.includes('from') ? match.split('from')[1].split('import')[0] : match.split('import')[1]).trim().split('.')[0];
                    if (!dep.startsWith('.'))
                        imports.push(dep);
                });
            }
            else if (language === 'go') {
                const matches = content.match(/^\s*import\s*\(/gm) && content.match(/(?:"([^"]+)")/g) || [];
                matches.forEach(match => {
                    const dep = match.replace(/"/g, '');
                    if (!dep.startsWith('./'))
                        imports.push(dep.split('/')[1]);
                });
            }
        }
        catch (error) {
            // Skip dependency extraction errors
        }
        return imports.length > 0 ? imports.slice(0, 3).join(', ') : null; // Limit to 3 deps
    }
    // Extract parent function/class context
    extractParentFunctions(content, language) {
        const functions = [];
        try {
            if (['typescript', 'javascript'].includes(language)) {
                // Extract function and class names
                const funcMatches = content.match(/\b(function|class|const|let|var)\s+(\w+)/g) || [];
                funcMatches.forEach(match => {
                    const parts = match.split(/\s+/);
                    if (parts.length >= 3)
                        functions.push(parts[2]);
                });
                // Arrow functions and methods
                const arrowMatches = content.match(/(\w+)\s*=>/g) || [];
                arrowMatches.forEach(match => {
                    functions.push(match.split('=>')[0].trim());
                });
            }
            else if (language === 'python') {
                const matches = content.match(/\b(?:def|class)\s+(\w+)/g) || [];
                matches.forEach(match => {
                    functions.push(match.split(/\s+/)[1]);
                });
            }
            else if (language === 'java') {
                const matches = content.match(/\b(?:public|private|protected|static|final|class|interface|void|String|int|boolean)\s+\w+/g) || [];
                matches.forEach(match => {
                    const words = match.split(/\s+/);
                    if (words.length >= 2)
                        functions.push(words[words.length - 1]);
                });
            }
        }
        catch (error) {
            // Skip function extraction errors
        }
        return functions.length > 0 ? functions.slice(0, 3).join(', ') : null;
    }
    // Create project structure embeddings
    async createStructureEmbeddings(files) {
        const chunks = [];
        // Directory structure
        const dirStructure = this.buildDirectoryTree(files);
        chunks.push({
            id: `structure_dirs_${this.projectId}_${Date.now()}`,
            content: `Project directory structure:\n${dirStructure}`,
            metadata: {
                project_id: this.projectId,
                type: 'structure',
                filename: 'DIRECTORY_STRUCTURE',
                language: 'structure',
                timestamp: new Date().toISOString()
            }
        });
        // File types summary
        const fileTypes = this.summarizeFileTypes(files);
        chunks.push({
            id: `structure_types_${this.projectId}_${Date.now()}`,
            content: `File types in project:\n${fileTypes}`,
            metadata: {
                project_id: this.projectId,
                type: 'structure',
                filename: 'FILE_TYPES',
                language: 'structure',
                timestamp: new Date().toISOString()
            }
        });
        return chunks;
    }
    // Build ASCII directory tree
    buildDirectoryTree(files) {
        const tree = {};
        files.forEach(file => {
            const dir = path.dirname(file.filename);
            if (!tree[dir])
                tree[dir] = [];
            tree[dir].push(file);
        });
        let result = '';
        const sortedDirs = Object.keys(tree).sort();
        sortedDirs.forEach(dir => {
            result += `${dir}/\n`;
            tree[dir].forEach(file => {
                result += `  └── ${path.basename(file.filename)} (${file.language}, ${(file.content.length / 1024).toFixed(1)}KB)\n`;
            });
        });
        return result;
    }
    // Summarize file types
    summarizeFileTypes(files) {
        const summary = {};
        files.forEach(file => {
            if (!summary[file.language]) {
                summary[file.language] = { count: 0, totalSize: 0 };
            }
            summary[file.language].count++;
            summary[file.language].totalSize += file.size;
        });
        let result = '';
        Object.entries(summary).forEach(([lang, stats]) => {
            result += `${lang}: ${stats.count} files (${(stats.totalSize / 1024).toFixed(1)}KB total)\n`;
        });
        return result;
    }
    // Embed conversation history
    async embedConversation(sessionId) {
        try {
            const { getSessionMemory } = await import('./memory');
            const memory = getSessionMemory(sessionId);
            const messages = memory.getMessages(); // Get last 10 messages
            const recentMessages = messages.slice(-10);
            if (recentMessages.length === 0)
                return;
            // Create prompt chunks
            const promptChunks = recentMessages.map((msg, index) => ({
                id: `conversation_${this.projectId}_${sessionId}_${index}`,
                content: `${msg.role}: ${msg.content}`,
                metadata: {
                    project_id: this.projectId,
                    session_id: sessionId,
                    type: 'prompt',
                    message_index: index,
                    role: msg.role,
                    timestamp: msg.timestamp.toISOString()
                }
            }));
            await chromaManager.addPromptChunks(this.projectId, promptChunks);
            console.log(`💬 Embedded ${promptChunks.length} conversation messages for project ${this.projectId}`);
        }
        catch (error) {
            console.error('❌ Failed to embed conversation:', error);
        }
    }
}
// Export utility function to embed a project
export async function embedProject(projectId, sourceDir = './generated') {
    const embedder = new ProjectEmbeddingService(projectId, sourceDir);
    await embedder.embedProject();
}
// Export utility function to embed conversation
export async function embedConversation(projectId, sessionId) {
    const embedder = new ProjectEmbeddingService(projectId);
    await embedder.embedConversation(sessionId);
}
