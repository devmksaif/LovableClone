import { embedProject } from './lib/utils/project-embeddings';
async function testEmbedding() {
    try {
        console.log('🚀 Testing project embedding with MeMemo vector store...');
        await embedProject('test-project', './src');
        console.log('✅ Project embedding test completed successfully!');
    }
    catch (error) {
        console.error('❌ Project embedding test failed:', error);
    }
}
testEmbedding();
