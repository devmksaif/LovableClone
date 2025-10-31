const { initializeMCPTools, globalToolSchemas } = require('./lib/agents/streaming-agents.ts');

async function testStreamingAgentsIntegration() {
  console.log('🧪 Testing Streaming Agents MCP Integration...\n');

  try {
    console.log('1. Initializing MCP tools...');
    await initializeMCPTools();

    console.log('✅ MCP tools initialized successfully');
    console.log(`📊 Total available tools: ${globalToolSchemas.length}`);

    // Show breakdown of internal vs external tools
    const internalTools = globalToolSchemas.filter(t => !t.function.name.includes(':'));
    const externalTools = globalToolSchemas.filter(t => t.function.name.includes(':'));

    console.log(`🔧 Internal MCP tools: ${internalTools.length}`);
    console.log(`🌐 External MCP tools: ${externalTools.length}`);

    console.log('\n📋 Sample Internal Tools:');
    internalTools.slice(0, 3).forEach(tool => {
      console.log(`  - ${tool.function.name}: ${tool.function.description.substring(0, 50)}...`);
    });

    console.log('\n📋 Sample External Tools:');
    externalTools.slice(0, 3).forEach(tool => {
      console.log(`  - ${tool.function.name}: ${tool.function.description.substring(0, 50)}...`);
    });

    console.log('\n🎉 Streaming agents are now integrated with external MCP file editing tools!');

  } catch (error) {
    console.error('❌ Failed to test streaming agents integration:', error);
  }
}

testStreamingAgentsIntegration();