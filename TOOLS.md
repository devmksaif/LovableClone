# Lovable Agent Tools Documentation

The Lovable agents now have access to **18 powerful tools** for code generation, editing, and project management, with intelligent logging and prompt optimization.

## 🆕 Latest Additions

### **replace_block** ⚡ NEW - MOST EFFICIENT
- **Purpose**: Replace code between two unique markers
- **Use cases**: Update functions, classes, or marked sections without rewriting entire file
- **Parameters**: `filePath`, `startMarker`, `endMarker`, `newContent`
- **Why use it**: 10x faster than read+write, preserves file structure, surgical precision
- **Example**: Replace function body by marking start `function myFunc(` and end `}`

### **replace_line_range** ⚡ NEW - VERY EFFICIENT
- **Purpose**: Replace specific lines by line numbers
- **Use cases**: Update known code sections, replace imports, modify specific blocks
- **Parameters**: `filePath`, `startLine`, `endLine`, `newContent`
- **Why use it**: Fast, precise, no need to read entire file first
- **Example**: Replace lines 10-25 with new implementation

## 🔧 Basic File Operations

### 1. **read_file**
- **Purpose**: Read the contents of a file
- **Use cases**: Examine existing code, check file contents before modifying
- **Parameters**: `filePath` (string)

### 2. **write_file**
- **Purpose**: Create or completely overwrite a file
- **Use cases**: Create new files, replace entire file contents
- **Parameters**: `filePath` (string), `content` (string)

### 3. **append_to_file**
- **Purpose**: Add content to the end of an existing file
- **Use cases**: Add new code sections, append logs
- **Parameters**: `filePath` (string), `content` (string)

### 4. **delete_file**
- **Purpose**: Delete a file (restricted to generated directory)
- **Use cases**: Remove unnecessary files, clean up
- **Parameters**: `filePath` (string)

### 5. **list_directory**
- **Purpose**: List all files and directories in a path
- **Use cases**: Explore project structure, check what files exist
- **Parameters**: `dirPath` (string)

### 6. **search_files**
- **Purpose**: Search for text patterns across files using regex
- **Use cases**: Find specific code patterns, locate functions/variables
- **Parameters**: `dirPath` (string), `pattern` (string)

---

## ✏️ Advanced Code Editing Tools

### 7. **replace_in_file**
- **Purpose**: Find and replace text using regex patterns
- **Use cases**: Refactor variable names, update import paths, fix bugs across file
- **Parameters**: `filePath` (string), `searchText` (string), `replaceText` (string)
- **Example**: Replace all occurrences of `oldFunction` with `newFunction`

### 8. **insert_at_line**
- **Purpose**: Insert content at a specific line number
- **Use cases**: Add new functions, insert imports, add code blocks
- **Parameters**: `filePath` (string), `lineNumber` (number), `content` (string)
- **Note**: Line numbers are 1-based

### 9. **delete_lines**
- **Purpose**: Remove a range of lines from a file
- **Use cases**: Remove obsolete code, delete unused functions
- **Parameters**: `filePath` (string), `startLine` (number), `endLine` (number)
- **Note**: Both line numbers are inclusive

### 10. **read_lines**
- **Purpose**: Read specific lines from a file
- **Use cases**: Examine code sections without reading entire file
- **Parameters**: `filePath` (string), `startLine` (number), `endLine` (number)

---

## 📁 File Management Tools

### 11. **get_file_info**
- **Purpose**: Get detailed metadata about a file
- **Returns**: Size, line count, extension, creation date, modification date
- **Use cases**: Check file size before processing, verify file exists
- **Parameters**: `filePath` (string)

### 12. **create_directory**
- **Purpose**: Create directories (recursively creates parent dirs)
- **Use cases**: Organize project structure, create folder hierarchies
- **Parameters**: `dirPath` (string)

### 13. **copy_file**
- **Purpose**: Duplicate a file to a new location
- **Use cases**: Create templates, backup files, duplicate components
- **Parameters**: `sourcePath` (string), `destinationPath` (string)

### 14. **move_file**
- **Purpose**: Move or rename a file
- **Use cases**: Reorganize project, rename files
- **Parameters**: `sourcePath` (string), `destinationPath` (string)

---

## 🗂️ Project Management Tools

### 15. **get_project_structure**
- **Purpose**: Generate a tree view of the project directory
- **Use cases**: Understand project organization, visualize file hierarchy
- **Parameters**: `maxDepth` (number, default: 3)
- **Output**: Tree structure with └── and ├── connectors

### 16. **execute_command**
- **Purpose**: Run shell commands in the project directory
- **Use cases**: 
  - Install dependencies: `npm install package-name`
  - Build projects: `npm run build`
  - Run tests: `npm test`
  - Git operations: `git init`, `git add .`
  - Initialize projects: `npx create-react-app .`
- **Parameters**: `command` (string), `description` (string - required!)
- **Timeout**: 30 seconds
- **Security**: Runs in project folder only

---

## 🎯 Agent Strategy Guidelines

### Tool Efficiency Ranking (Use in This Order):
1. **replace_block** - Best for functions, classes, marked sections (FASTEST ⚡)
2. **replace_line_range** - Best when you know line numbers (VERY FAST ⚡)
3. **replace_in_file** - Best for find/replace patterns (FAST)
4. **insert_at_line** / **delete_lines** - Best for targeted additions/removals
5. **write_file** - Only for NEW files or complete rewrites

### When Creating NEW Projects:
1. Use `write_file` for all new files
2. Use `create_directory` to organize structure
3. Use `execute_command` for dependencies (`npm install`)

### When MODIFYING Existing Projects:
1. Use `read_file` or `read_lines` first to see current content
2. Use `replace_in_file` for targeted changes (best for refactoring)
3. Use `insert_at_line` to add new code sections
4. Use `delete_lines` to remove obsolete code
5. Use `search_files` to find what needs changing

### When REFACTORING:
1. Use `get_project_structure` to understand layout
2. Use `search_files` to find all occurrences
3. Use `replace_in_file` with regex for bulk changes
4. Use `move_file` to reorganize
5. Use `execute_command` to run tests after changes

### When DEBUGGING:
1. Use `get_file_info` to check file details
2. Use `read_lines` to examine specific sections
3. Use `search_files` to locate error sources
4. Use `execute_command` to run diagnostics

---

## 🚀 Performance Tips

- **Read strategically**: Use `read_lines` instead of `read_file` for large files
- **Search smart**: Use specific regex patterns with `search_files` (limited to 20 results)
- **Edit precisely**: Use `replace_in_file` or `insert_at_line` instead of rewriting entire files
- **Structure first**: Use `get_project_structure` before making major changes
- **Test as you go**: Use `execute_command` to run tests after each significant change

---

## 🔒 Security Notes

- File operations are restricted to the project folder
- `delete_file` only works in the generated directory
- Commands execute with 30-second timeout
- Hidden files (starting with `.`) are skipped in structure views
- `node_modules` is automatically excluded from directory traversals

---

## 🆕 New Features & Optimizations

### 📊 Tool Call Logging
Every tool invocation is now automatically logged with:
- Tool name and parameters
- Execution time (milliseconds)
- Success/failure status
- Results preview

**Statistics provided:**
- Total calls per request
- Success/failure rates
- Average execution time
- Most frequently used tools

**Benefits:**
- Debug tool usage patterns
- Optimize agent performance
- Track what agents actually do
- Identify bottlenecks

### 🎯 Prompt Optimization
All prompts are automatically optimized before sending to AI:
- **Removes excessive whitespace** - Reduces token waste
- **Deduplicates instructions** - No repeated rules
- **Compresses file lists** - Shows first 5, last 3 if >10 files
- **Removes redundant phrases** - "Please note that", "Make sure to", etc.
- **Intelligent truncation** - Keeps critical sections, compresses context

**Typical savings: 15-30% token reduction per request**

### ⚡ Performance Improvements
1. **Block replacement > Full file rewrite** - 10x faster edits
2. **Line range replacement** - No need to parse entire file
3. **Compressed prompts** - Lower latency, cheaper API calls
4. **Smart context** - Only relevant history included

### 📈 Efficiency Metrics
After each request, you'll see:
```
📊 Tool Call Statistics:
- Total calls: 12
- Successful: 11
- Failed: 1
- Total time: 3250ms
- Average time: 271ms
- Most used: write_file(5), read_file(3), replace_block(2)
```

This helps you understand:
- How agents work internally
- Which tools are most valuable
- Where optimization opportunities exist
- Performance bottlenecks
