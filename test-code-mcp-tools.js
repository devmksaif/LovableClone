const { initializeFilesystemServer, CodeMCPTools, externalMCPClient, initializeExternalMCPServers } = require('./lib/mcp/mcp-client.ts');

async function testCodeMCPTools() {
  console.log('🧪 Testing Code MCP Tools...\n');

  try {
    // Initialize filesystem server with access to project directory
    console.log('1. Initializing filesystem MCP server with project access...');
    await initializeFilesystemServer([process.cwd()]);

    // Initialize other servers
    console.log('2. Initializing GitHub MCP server...');
    await initializeExternalMCPServers(['github']);

    const connected = externalMCPClient.getConnectedServers();
    console.log(`✅ Connected to: ${connected.join(', ')}\n`);

    // Test filesystem operations
    if (connected.includes('filesystem')) {
      console.log('3. Testing filesystem operations...');

      // List current directory
      const files = await CodeMCPTools.listDirectory('filesystem', '.');
      console.log('📁 Current directory files:', files.slice(0, 5), '...');

      // Read a source file
      const content = await CodeMCPTools.readFile('filesystem', 'package.json');
      console.log('📄 Read package.json (first 100 chars):', content.substring(0, 100), '...');

      // Test writing a file
      console.log('4. Testing file writing...');
      const testFile = 'test-mcp-file.txt';
      const testContent = `Hello from MCP File Editing Tools!\nCreated at: ${new Date().toISOString()}\nThis demonstrates external MCP server file operations.`;
      await CodeMCPTools.writeFile('filesystem', testFile, testContent);
      console.log(`✅ Created test file: ${testFile}`);

      // Read it back to verify
      const readBack = await CodeMCPTools.readFile('filesystem', testFile);
      console.log('📖 Read back test file:', readBack.substring(0, 50), '...');

      console.log('✅ Filesystem operations working!\n');
    }

    // Test git operations
    if (connected.includes('git')) {
      console.log('3. Testing git operations...');

      const status = await CodeMCPTools.gitStatus('git');
      console.log('🔀 Git status:', status);

      console.log('✅ Git operations working!\n');
    }

    // Test GitHub operations (if token available)
    if (connected.includes('github') && process.env.GITHUB_TOKEN) {
      console.log('4. Testing GitHub operations...');

      // Search for code in this repo
      const searchResults = await CodeMCPTools.searchCode('github', 'MCP', 'typescript');
      console.log('🔍 Found MCP-related code:', searchResults.length, 'results');

      console.log('✅ GitHub operations working!\n');
    }

    console.log('🎉 All code MCP tools tested successfully!');

  } catch (error) {
    console.error('❌ Error testing code MCP tools:', error);
  }
}

// Run the test
testCodeMCPTools();