import 'dotenv/config';
import { HumanMessage } from '@langchain/core/messages';
import { createStreamingLovableAgentGraph, saveGeneratedFiles } from '../lib/agents/agent-core';

async function main() {
  console.log('🚀 Starting Lovable-style code generation agent...\n');

  const userRequest = process.argv[2] || 'Create a  typescript that stress tests an api alot to the point it crashes to test scalability please ';

  console.log(`📝 User Request: ${userRequest}\n`);

  const graph = createStreamingLovableAgentGraph();

  // Run the agent
  const result = await graph.invoke({
    userRequest,
    messages: [new HumanMessage(userRequest)],
  });

  console.log('\n✅ Generation complete!\n');
  console.log('📋 Plan executed:');
  result.plan.forEach((step, i) => {
    console.log(`  ${i + 1}. ${step}`);
  });

  console.log('\n📁 Generated files:');
  Object.keys(result.generatedFiles).forEach(filename => {
    console.log(`  - ${filename}`);
  });

  if (result.reviewFeedback) {
    console.log('\n🔍 Review feedback:');
    console.log(`  ${result.reviewFeedback}`);
  }

  // Save files to disk
  console.log('\n💾 Saving files to ./generated directory...');
  const savedFiles = saveGeneratedFiles(result.generatedFiles);
  console.log(`✅ Saved ${savedFiles.length} files:`);
  savedFiles.forEach(file => console.log(`  - ${file}`));

  console.log('\n🎉 Done!');
}

main().catch(console.error);
