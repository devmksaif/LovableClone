// Test script to verify MCP tools are working
const { mcpTools } = require('./lib/mcp/tools');

console.log('🧪 Testing MCP Tools...\n');

// List all available tools
console.log('📋 Available MCP Tools:');
mcpTools.forEach((tool, index) => {
  console.log(`${index + 1}. ${tool.name} - ${tool.description}`);
});

console.log(`\n✅ Total tools available: ${mcpTools.length}`);

// Check for the specific tools we added
const requiredTools = [
  'read_file',
  'write_file', 
  'append_to_file',
  'delete_file',
  'list_directory',
  'search_files',
  'get_file_info',
  'create_directory',
  'copy_file',
  'move_file'
];

console.log('\n🔍 Checking for required tools:');
const availableToolNames = mcpTools.map(tool => tool.name);

requiredTools.forEach(toolName => {
  const isAvailable = availableToolNames.includes(toolName);
  console.log(`${isAvailable ? '✅' : '❌'} ${toolName}`);
});

const missingTools = requiredTools.filter(tool => !availableToolNames.includes(tool));
if (missingTools.length === 0) {
  console.log('\n🎉 All required tools are available!');
} else {
  console.log(`\n⚠️  Missing tools: ${missingTools.join(', ')}`);
}