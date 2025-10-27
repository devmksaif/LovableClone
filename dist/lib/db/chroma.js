import { GoogleGenerativeAIEmbeddings } from '@langchain/google-genai';
import { HNSW } from 'mememo';
// MeMemo-based vector store implementation for efficient similarity search
class MeMemoVectorStore {
    constructor(embeddings) {
        this.docs = [];
        this.embeddings = embeddings;
        this.index = new HNSW({ distanceFunction: 'cosine' });
    }
    async addDocuments(docs) {
        if (docs.length === 0)
            return;
        // Generate embeddings for all documents
        const texts = docs.map(d => d.pageContent);
        const embeddings = await this.embeddings.embedDocuments(texts);
        // Prepare data for bulk insert
        const keys = [];
        const values = [];
        docs.forEach((doc, i) => {
            const id = doc.metadata?.id || `doc_${Date.now()}_${i}`;
            keys.push(id);
            values.push(embeddings[i]);
            // Store document data
            this.docs.push({
                pageContent: doc.pageContent,
                metadata: doc.metadata || {},
                id
            });
        });
        // Bulk insert into HNSW index
        await this.index.bulkInsert(keys, values);
    }
    async similaritySearchWithScore(query, k = 5) {
        // Generate embedding for query
        const queryEmbedding = await this.embeddings.embedDocuments([query]);
        const qEmb = queryEmbedding[0];
        // Search HNSW index
        const { keys, distances } = await this.index.query(qEmb, k);
        // Map results back to documents with scores
        const results = [];
        keys.forEach((key, i) => {
            const doc = this.docs.find(d => d.id === key);
            if (doc) {
                results.push([{
                        pageContent: doc.pageContent,
                        metadata: doc.metadata
                    }, distances[i]]);
            }
        });
        return results;
    }
}
// Configuration
const EMBEDDING_MODEL = 'text-embedding-004';
const EMBEDDING_DIMENSIONS = 3072; // Google Gemini embedding dimensions
// Storage provider enum for future ChromaDB compatibility
var VectorStorageProvider;
(function (VectorStorageProvider) {
    VectorStorageProvider["MEMORY"] = "memory";
    VectorStorageProvider["CHROMA"] = "chroma";
})(VectorStorageProvider || (VectorStorageProvider = {}));
// Current storage provider - can easily switch to CHROMA later
const CURRENT_STORAGE_PROVIDER = VectorStorageProvider.MEMORY;
// Project storage keys
const STORAGE_KEYS = {
    PROJECT_CODE: (projectId) => `project_${projectId}_code`,
    PROJECT_PROMPTS: (projectId) => `project_${projectId}_prompts`,
    PROJECT_STRUCTURE: (projectId) => `project_${projectId}_structure`,
};
// Unified Vector Store Manager with ChromaDB backward compatibility
class VectorStoreManager {
    constructor() {
        this.store = new Map();
        this.chunkCounts = new Map();
        // Use LangChain's Google Generative AI embeddings - Gemini 3072 dimensions
        this.embeddings = new GoogleGenerativeAIEmbeddings({
            modelName: EMBEDDING_MODEL,
            apiKey: process.env.GEMINI_API_KEY,
        });
    }
    // Get or create a project collection (backward compatible with ChromaDB "collection" concept)
    async getProjectStore(collectionName) {
        if (!this.store.has(collectionName)) {
            this.store.set(collectionName, new MeMemoVectorStore(this.embeddings));
        }
        return this.store.get(collectionName);
    }
    // Initialize collections for a project (no-op for MeMemoVectorStore)
    async initializeProjectCollections(projectId) {
        console.log(`✅ Initialized MeMemo Vector Store collections for project: ${projectId}`);
        // MeMemoVectorStore doesn't require initialization
    }
    // Generate embeddings for text content
    async generateEmbeddings(texts) {
        try {
            const embeddings = await this.embeddings.embedDocuments(texts);
            return embeddings;
        }
        catch (error) {
            console.error('❌ Failed to generate embeddings:', error);
            throw error;
        }
    }
    // Add code chunks to project collection
    async addCodeChunks(projectId, chunks) {
        try {
            if (chunks.length === 0)
                return;
            const collectionName = STORAGE_KEYS.PROJECT_CODE(projectId);
            const store = await this.getProjectStore(collectionName);
            // Add chunks to MeMemo store
            await store.addDocuments(chunks.map(chunk => ({
                pageContent: chunk.content,
                metadata: chunk.metadata,
            })));
            // Track count
            this.chunkCounts.set(collectionName, (this.chunkCounts.get(collectionName) || 0) + chunks.length);
            console.log(`📁 Added ${chunks.length} code chunks to project ${projectId}`);
        }
        catch (error) {
            console.error('❌ Failed to add code chunks:', error);
            throw error;
        }
    }
    // Add prompt chunks to project collection
    async addPromptChunks(projectId, chunks) {
        try {
            if (chunks.length === 0)
                return;
            const collectionName = STORAGE_KEYS.PROJECT_PROMPTS(projectId);
            const store = await this.getProjectStore(collectionName);
            // Add chunks to MeMemo store
            await store.addDocuments(chunks.map(chunk => ({
                pageContent: chunk.content,
                metadata: chunk.metadata,
            })));
            // Track count
            this.chunkCounts.set(collectionName, (this.chunkCounts.get(collectionName) || 0) + chunks.length);
            console.log(`💬 Added ${chunks.length} prompt chunks to project ${projectId}`);
        }
        catch (error) {
            console.error('❌ Failed to add prompt chunks:', error);
            throw error;
        }
    }
    // Add project structure embeddings
    async addStructureChunks(projectId, chunks) {
        try {
            if (chunks.length === 0)
                return;
            const collectionName = STORAGE_KEYS.PROJECT_STRUCTURE(projectId);
            const store = await this.getProjectStore(collectionName);
            // Add chunks to MeMemo store
            await store.addDocuments(chunks.map(chunk => ({
                pageContent: chunk.content,
                metadata: chunk.metadata,
            })));
            // Track count
            this.chunkCounts.set(collectionName, (this.chunkCounts.get(collectionName) || 0) + chunks.length);
            console.log(`🏗️ Added ${chunks.length} structure chunks to project ${projectId}`);
        }
        catch (error) {
            console.error('❌ Failed to add structure chunks:', error);
            throw error;
        }
    }
    // Search for similar code patterns
    async searchCode(projectId, query, nResults = 5) {
        try {
            const collectionName = STORAGE_KEYS.PROJECT_CODE(projectId);
            const store = await this.getProjectStore(collectionName);
            const results = await store.similaritySearchWithScore(query, nResults);
            return results.map(([doc, score]) => ({
                id: doc.metadata.id || `search_${Date.now()}`,
                content: doc.pageContent,
                score: 1 - (score / 2), // Normalize score (MeMemo uses distance, we want similarity)
                metadata: doc.metadata
            }));
        }
        catch (error) {
            console.error('❌ Failed to search code:', error);
            return [];
        }
    }
    // Search across all project collections
    async searchProject(projectId, query, nResults = 10) {
        try {
            const results = [];
            // Search code collection
            const codeResults = await this.searchCode(projectId, query, nResults);
            results.push(...codeResults.map(r => ({ ...r, type: 'code' })));
            // Search prompts collection
            try {
                const promptsCollectionName = STORAGE_KEYS.PROJECT_PROMPTS(projectId);
                const promptsStore = await this.getProjectStore(promptsCollectionName);
                const promptsResults = await promptsStore.similaritySearchWithScore(query, Math.ceil(nResults / 3));
                promptsResults.forEach(([doc, score]) => {
                    results.push({
                        type: 'prompt',
                        id: doc.metadata.id || `prompt_${Date.now()}`,
                        content: doc.pageContent,
                        score: 1 - (score / 2),
                        metadata: doc.metadata
                    });
                });
            }
            catch (error) {
                // Prompts collection might not exist yet - skip
            }
            // Search structure collection
            try {
                const structCollectionName = STORAGE_KEYS.PROJECT_STRUCTURE(projectId);
                const structStore = await this.getProjectStore(structCollectionName);
                const structResults = await structStore.similaritySearchWithScore(query, Math.ceil(nResults / 3));
                structResults.forEach(([doc, score]) => {
                    results.push({
                        type: 'structure',
                        id: doc.metadata.id || `struct_${Date.now()}`,
                        content: doc.pageContent,
                        score: 1 - (score / 2),
                        metadata: doc.metadata
                    });
                });
            }
            catch (error) {
                // Structure collection might not exist yet - skip
            }
            // Sort by score and return top results
            return results.sort((a, b) => b.score - a.score).slice(0, nResults);
        }
        catch (error) {
            console.error('❌ Failed to search project:', error);
            return [];
        }
    }
    // Get project statistics
    async getProjectStats(projectId) {
        try {
            const stats = {
                project_id: projectId,
                total_chunks: 0,
                code_chunks: this.chunkCounts.get(STORAGE_KEYS.PROJECT_CODE(projectId)) || 0,
                prompt_chunks: this.chunkCounts.get(STORAGE_KEYS.PROJECT_PROMPTS(projectId)) || 0,
                structure_chunks: this.chunkCounts.get(STORAGE_KEYS.PROJECT_STRUCTURE(projectId)) || 0,
                dependency_chunks: 0,
                created_at: new Date().toISOString(),
                last_updated: new Date().toISOString()
            };
            stats.total_chunks = stats.code_chunks + stats.prompt_chunks + stats.structure_chunks;
            return stats;
        }
        catch (error) {
            console.error('❌ Failed to get project stats:', error);
            return null;
        }
    }
    // Delete project collections
    async deleteProject(projectId) {
        try {
            // Remove stores from memory
            this.store.delete(STORAGE_KEYS.PROJECT_CODE(projectId));
            this.store.delete(STORAGE_KEYS.PROJECT_PROMPTS(projectId));
            this.store.delete(STORAGE_KEYS.PROJECT_STRUCTURE(projectId));
            // Remove counts
            this.chunkCounts.delete(STORAGE_KEYS.PROJECT_CODE(projectId));
            this.chunkCounts.delete(STORAGE_KEYS.PROJECT_PROMPTS(projectId));
            this.chunkCounts.delete(STORAGE_KEYS.PROJECT_STRUCTURE(projectId));
            console.log(`🗑️ Deleted MeMemo Vector Store collections for project: ${projectId}`);
        }
        catch (error) {
            console.error('❌ Failed to delete project:', error);
            throw error;
        }
    }
    // Health check (always true for MeMemoVectorStore)
    async healthCheck() {
        return true; // MeMemoVectorStore is always available
    }
}
// Backward compatibility - rename class to ChromaDBManager for existing imports
const ChromaDBManager = VectorStoreManager;
// Export singleton instance
export const chromaManager = new VectorStoreManager();
export default chromaManager;
// Utility functions
export function generateChunkId(projectId, filename, lines, type) {
    return `${projectId}_${filename}_${lines[0]}-${lines[1]}_${type}_${Date.now()}`;
}
export function generatePromptId(projectId, sessionId, messageIndex) {
    return `${projectId}_${sessionId}_prompt_${messageIndex}`;
}
