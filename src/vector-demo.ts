#!/usr/bin/env tsx

/**
 * MeMemo Vector Store Demo
 *
 * This script demonstrates:
 * 1. Embedding a project (folder structure + code + prompts)
 * 2. Searching for relevant code snippets using Google Gemini embeddings
 * 3. Contextual retrieval for agent assistance
 *
 * Uses MeMemo HNSW vector store with Google Gemini embeddings (3072 dimensions)
 *
 * Usage:
 * 1. Set environment variables (.env) with GEMINI_API_KEY
 * 2. Run: npx tsx src/vector-demo.ts
 */

import 'dotenv/config';
import { embedProject, embedConversation } from '../lib/utils/project-embeddings';
import { chromaManager } from '../lib/db/chroma';

async function demoProjectEmbedding() {
  console.log('🎯 MeMemo Vector Store Demo');
  console.log('===========================\n');

  const projectId = `demo_project_${Date.now()}`;
  const demoDir = './src'; // Use existing src folder

  try {
    // Step 1: Check vector store is available
    console.log('1. 🔍 Checking vector store health...');
    const isHealthy = await chromaManager.healthCheck();
    if (!isHealthy) {
      console.log('❌ Vector store not available. Please check your configuration.');
      return;
    }
    console.log('✅ Vector store is healthy!\n');

    // Step 2: Embed the project
    console.log(`2. 📁 Embedding project: ${projectId}`);
    console.log(`   Source directory: ${demoDir}`);

    await embedProject(projectId, demoDir);
    console.log('✅ Project embedded successfully!\n');

    // Step 3: Embed conversation (if applicable)
    const sessionId = 'demo_session_123';
    console.log('3. 💬 Embedding conversation history...');
    await embedConversation(projectId, sessionId);
    console.log('✅ Conversation history embedded!\n');

    // Step 4: Get project statistics
    console.log('4. 📊 Project Statistics:');
    const stats = await chromaManager.getProjectStats(projectId);
    if (stats) {
      console.log(`   📋 Total chunks: ${stats.total_chunks}`);
      console.log(`   📝 Code chunks: ${stats.code_chunks}`);
      console.log(`   💬 Prompt chunks: ${stats.prompt_chunks}`);
      console.log(`   🏗️ Structure chunks: ${stats.structure_chunks}`);
    }
    console.log('');

    // Step 5: Demonstrate searches
    console.log('5. 🔍 Search Demonstrations:');
    console.log('');

    const searches = [
      'calculator function',
      'javascript click handler',
      'CSS styling',
      'error handling',
      'function definition'
    ];

    for (const query of searches) {
      console.log(`   Searching for: "${query}"`);

      try {
        const results = await chromaManager.searchCode(projectId, query, 3);

        if (results.length > 0) {
          console.log(`   ✅ Found ${results.length} results:`);
          results.forEach((result, index) => {
            console.log(`      ${index + 1}. ${result.metadata.filename} (${Math.round(result.score * 100)}% match)`);
            console.log(`         ${result.content.substring(0, 80)}...`);
          });
        } else {
          console.log(`   ⚠️ No results found`);
        }
      } catch (error) {
        console.log(`   ❌ Search failed: ${error}`);
      }
      console.log('');
    }

    // Step 6: Context retrieval demo
    console.log('6. 🎭 Context Retrieval Demo:');
    console.log('');

    const contextQueries = [
      'how to handle button clicks in JavaScript',
      'error handling patterns',
      'styling techniques used'
    ];

    for (const query of contextQueries) {
      console.log(`   Query: "${query}"`);

      try {
        const contextResults = await chromaManager.searchProject(projectId, query, 5);

        if (contextResults.length > 0) {
          console.log(`   📄 Retrieved ${contextResults.length} context snippets:`);
          contextResults.forEach((result, index) => {
            console.log(`      ${index + 1}. [${result.type.toUpperCase()}] ${Math.round(result.score * 100)}% relevant`);
            console.log(`         ${result.content.substring(0, 60)}...`);
          });
        } else {
          console.log(`   ⚠️ No context found`);
        }
      } catch (error) {
        console.log(`   ❌ Context retrieval failed: ${error}`);
      }
      console.log('');
    }

    console.log('🎉 Demo completed successfully!');
    console.log('');
    console.log('Next steps:');
    console.log('• Use /api/vector/embed to embed real projects');
    console.log('• Use /api/vector/search to find code snippets');
    console.log('• Use /api/vector/context for agent context retrieval');
    console.log('');
    console.log(`📝 Demo project ID: ${projectId}`);

  } catch (error) {
    console.error('❌ Demo failed:', error);
    console.log('');
    console.log('Troubleshooting:');
    console.log('1. Check your GEMINI_API_KEY in .env file');
    console.log('2. Verify the src/ directory has files to embed');
    console.log('3. Make sure MeMemo vector store is properly configured');
  }
}

// REST API Example URLs
function printApiExamples(projectId: string) {
  console.log('');
  console.log('🚀 API Usage Examples:');
  console.log('');
  console.log('1. Embed a project:');
  console.log(`   POST /api/vector/embed`);
  console.log(`   { "projectId": "${projectId}", "sourceDir": "./your-project", "includeConversation": false }`);
  console.log('');
  console.log('2. Search for code:');
  console.log(`   POST /api/vector/search`);
  console.log(`   { "projectId": "${projectId}", "query": "calculator functions", "nResults": 5 }`);
  console.log('');
  console.log('3. Get agent context:');
  console.log(`   POST /api/vector/context`);
  console.log(`   { "projectId": "${projectId}", "query": "how to handle errors", "maxTokens": 4000 }`);
  console.log('');
}

// Run the demo
if (require.main === module) {
  demoProjectEmbedding()
    .then(() => {
      const projectId = `demo_project_${Date.now()}`;
      printApiExamples(projectId);
    })
    .catch(console.error);
}

export { demoProjectEmbedding };
