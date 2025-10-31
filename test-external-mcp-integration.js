import { initializeFilesystemServer, CodeMCPTools, externalMCPClient } from './lib/mcp/mcp-client.js';

async function testExternalMCPIntegration() {
  console.log('🧪 Testing External MCP Integration with Streaming Agents...\n');

  try {
    // Test lazy initialization of filesystem server
    console.log('1. Testing lazy initialization...');
    await initializeFilesystemServer([process.cwd()]);
    console.log('✅ Filesystem server initialized');

    // Test tool execution
    console.log('2. Testing external tool execution...');
    const files = await CodeMCPTools.listDirectory('filesystem', '.');
    console.log('📁 Directory listing:', files.slice(0, 3), '...');

    // Test reading a file
    const content = await CodeMCPTools.readFile('filesystem', 'package.json');
    console.log('📄 Read package.json successfully');

    console.log('✅ External MCP tools working with lazy initialization!');

  } catch (error) {
    console.error('❌ Error testing external MCP integration:', error);
  }
}

// Run the test
testExternalMCPIntegration();