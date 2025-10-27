#!/usr/bin/env tsx

/**
 * Test the Lovable agent with vector context integration
 */

import 'dotenv/config';
import { createLovableAgentGraph, saveGeneratedFiles } from '../lib/agents/agent-core';
import { embedProject } from '../lib/utils/project-embeddings';

async function testAgentWithVectorContext() {
  console.log('🧪 Testing Lovable Agent with Vector Context Integration');
  console.log('======================================================\n');

  try {
    // Step 1: Embed the current project for vector context
    console.log('1. 📁 Embedding current project for vector context...');
    const projectId = 'agent_context_project'; // Use consistent project ID
    await embedProject(projectId, './src');
    console.log('✅ Project embedded for context\n');

    // Step 2: Create and run the agent
    console.log('2. 🤖 Creating agent with vector context...');
    const agent = createLovableAgentGraph();

    const initialState = {
      messages: [],
      userRequest: 'Create a simple calculator web application with HTML, CSS, and JavaScript. Include basic operations like add, subtract, multiply, and divide.',
      plan: [],
      generatedFiles: {},
      currentIteration: 0,
      reviewFeedback: '',
      isComplete: false,
    };

    console.log('3. 🚀 Running agent workflow...');
    console.log(`Request: ${initialState.userRequest}\n`);

    const result = await agent.invoke(initialState);

    // Step 3: Display results
    console.log('4. 📊 Results:');
    console.log(`   Plan steps: ${result.plan.length}`);
    console.log(`   Generated files: ${Object.keys(result.generatedFiles).length}`);
    console.log(`   Iterations: ${result.currentIteration}`);
    console.log(`   Complete: ${result.isComplete}`);
    console.log(`   Review feedback: ${result.reviewFeedback || 'None'}\n`);

    // Step 4: Save generated files
    if (Object.keys(result.generatedFiles).length > 0) {
      console.log('5. 💾 Saving generated files...');
      const savedFiles = saveGeneratedFiles(result.generatedFiles, './generated');
      console.log(`✅ Saved ${savedFiles.length} files:`);
      savedFiles.forEach(file => console.log(`   - ${file}`));
    }

    console.log('\n🎉 Test completed successfully!');
    console.log('The agent now uses vector context for better code generation.');

  } catch (error) {
    console.error('❌ Test failed:', error);
    console.log('\nTroubleshooting:');
    console.log('1. Check your API keys in .env');
    console.log('2. Ensure vector store is working (run vector-demo.ts first)');
    console.log('3. Check that src/ directory has files to embed');
  }
}

// Run the test
if (require.main === module) {
  testAgentWithVectorContext().catch(console.error);
}

export { testAgentWithVectorContext };