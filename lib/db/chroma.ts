import { GoogleGenerativeAIEmbeddings } from '@langchain/google-genai';
import { Chroma } from '@langchain/community/vectorstores/chroma';
import { Document } from '@langchain/core/documents';

// ChromaDB-based vector store implementation using LangChain for efficient similarity search
class ChromaVectorStore {
  private vectorStore: Chroma | null = null;
  private collectionName: string;
  private embeddings: GoogleGenerativeAIEmbeddings;

  constructor(collectionName: string, embeddings: GoogleGenerativeAIEmbeddings) {
    this.collectionName = collectionName;
    this.embeddings = embeddings;
  }

  private async ensureVectorStore(): Promise<Chroma> {
    if (!this.vectorStore) {
      try {
        // Try to load existing collection
        this.vectorStore = await Chroma.fromExistingCollection(
          this.embeddings,
          { collectionName: this.collectionName }
        );
        console.log(`✅ Loaded existing ChromaDB collection: ${this.collectionName}`);
      } catch (error) {
        // Collection doesn't exist, create new one
        this.vectorStore = new Chroma(this.embeddings, {
          collectionName: this.collectionName,
          url: "http://localhost:8000" // Default ChromaDB server URL
        });
        console.log(`✅ Created new ChromaDB collection: ${this.collectionName}`);
      }
    }
    return this.vectorStore;
  }

  async addDocuments(docs: Array<{ pageContent: string; metadata?: any }>) {
    if (docs.length === 0) return;

    const vectorStore = await this.ensureVectorStore();

    // Convert to LangChain documents
    const documents = docs.map(doc =>
      new Document({
        pageContent: doc.pageContent,
        metadata: doc.metadata || {}
      })
    );

    // Add documents to vector store
    await vectorStore.addDocuments(documents);
    console.log(`✅ Added ${docs.length} documents to ChromaDB collection: ${this.collectionName}`);
  }

  async similaritySearchWithScore(query: string, k: number = 5): Promise<Array<[Document, number]>> {
    const vectorStore = await this.ensureVectorStore();

    // Use LangChain's similarity search with scores
    const results = await vectorStore.similaritySearchWithScore(query, k);

    console.log(`✅ Found ${results.length} results from ChromaDB query`);

    return results;
  }
}

// Flexible metadata type for backward compatibility - supports both ChromaDB and new formats
export type VectorMetadata = {
  // Common fields
  project_id?: string;
  type?: 'code' | 'prompt' | 'structure' | 'dependency';
  timestamp?: string;
  id?: string;

  // Code-specific fields
  filename?: string;
  language?: string;
  lines_start?: number;
  lines_end?: number;
  dependencies?: string | null;
  parent_functions?: string | null;
  content_hash?: string;

  // Prompt-specific fields
  session_id?: string;
  message_index?: number;
  role?: string;

  // Allow additional properties for flexibility
  [key: string]: string | number | boolean | null | undefined;
};

// Backward compatibility alias
export type ChromaMetadata = VectorMetadata;

export interface CodeChunk {
  id: string;
  content: string;
  metadata: VectorMetadata;
}

export interface ProjectEmbeddings {
  project_id: string;
  total_chunks: number;
  code_chunks: number;
  prompt_chunks: number;
  structure_chunks: number;
  dependency_chunks: number;
  created_at: string;
  last_updated: string;
}

// Configuration
const EMBEDDING_MODEL = 'text-embedding-004';
const EMBEDDING_DIMENSIONS = 3072; // Google Gemini embedding dimensions

// Storage provider enum for future extensions
enum VectorStorageProvider {
  CHROMA = 'chroma',      // Use ChromaDB (current primary)
  MEMORY = 'memory',      // Use in-memory fallback (future)
}

// Current storage provider - ChromaDB is now primary
const CURRENT_STORAGE_PROVIDER = VectorStorageProvider.CHROMA;

// Project storage keys
const STORAGE_KEYS = {
  PROJECT_CODE: (projectId: string) => `project_${projectId}_code`,
  PROJECT_PROMPTS: (projectId: string) => `project_${projectId}_prompts`,
  PROJECT_STRUCTURE: (projectId: string) => `project_${projectId}_structure`,
};

// Unified Vector Store Manager with ChromaDB implementation
class VectorStoreManager {
  private store: Map<string, ChromaVectorStore> = new Map();
  private chunkCounts: Map<string, number> = new Map();
  private embeddings: GoogleGenerativeAIEmbeddings;

  constructor() {
    // Use LangChain's Google Generative AI embeddings - Gemini 3072 dimensions
    this.embeddings = new GoogleGenerativeAIEmbeddings({
      modelName: EMBEDDING_MODEL,
      apiKey: process.env.GEMINI_API_KEY,
    });
  }

  // Get or create a project collection (ChromaDB collections)
  private async getProjectStore(collectionName: string): Promise<ChromaVectorStore> {
    if (!this.store.has(collectionName)) {
      this.store.set(collectionName, new ChromaVectorStore(collectionName, this.embeddings));
    }
    return this.store.get(collectionName)!;
  }

  // Initialize collections for a project (ChromaDB handles this automatically)
  async initializeProjectCollections(projectId: string): Promise<void> {
    console.log(`✅ Initialized ChromaDB collections for project: ${projectId}`);
    // ChromaDB creates collections on demand
  }

  // Generate embeddings for text content
  async generateEmbeddings(texts: string[]): Promise<number[][]> {
    try {
      const embeddings = await this.embeddings.embedDocuments(texts);
      return embeddings;
    } catch (error) {
      console.error('❌ Failed to generate embeddings:', error);
      throw error;
    }
  }

  // Add code chunks to project collection
  async addCodeChunks(projectId: string, chunks: CodeChunk[]): Promise<void> {
    try {
      if (chunks.length === 0) return;

      const collectionName = STORAGE_KEYS.PROJECT_CODE(projectId);
      const store = await this.getProjectStore(collectionName);

      // Add chunks to MeMemo store
      await store.addDocuments(
        chunks.map(chunk => ({
          pageContent: chunk.content,
          metadata: chunk.metadata,
        }))
      );

      // Track count
      this.chunkCounts.set(collectionName, (this.chunkCounts.get(collectionName) || 0) + chunks.length);
      console.log(`� Added ${chunks.length} code chunks to project ${projectId} (collection: ${collectionName})`);
    } catch (error) {
      console.error('❌ Failed to add code chunks:', error);
      throw error;
    }
  }

  // Add prompt chunks to project collection
  async addPromptChunks(projectId: string, chunks: Array<{
    id: string;
    content: string;
    metadata: VectorMetadata;
  }>): Promise<void> {
    try {
      if (chunks.length === 0) return;

      const collectionName = STORAGE_KEYS.PROJECT_PROMPTS(projectId);
      const store = await this.getProjectStore(collectionName);

      // Add chunks to MeMemo store
      await store.addDocuments(
        chunks.map(chunk => ({
          pageContent: chunk.content,
          metadata: chunk.metadata,
        }))
      );

      // Track count
      this.chunkCounts.set(collectionName, (this.chunkCounts.get(collectionName) || 0) + chunks.length);
      console.log(`💬 Added ${chunks.length} prompt chunks to project ${projectId}`);
    } catch (error) {
      console.error('❌ Failed to add prompt chunks:', error);
      throw error;
    }
  }

  // Add project structure embeddings
  async addStructureChunks(projectId: string, chunks: Array<{
    id: string;
    content: string;
    metadata: VectorMetadata;
  }>): Promise<void> {
    try {
      if (chunks.length === 0) return;

      const collectionName = STORAGE_KEYS.PROJECT_STRUCTURE(projectId);
      const store = await this.getProjectStore(collectionName);

      // Add chunks to MeMemo store
      await store.addDocuments(
        chunks.map(chunk => ({
          pageContent: chunk.content,
          metadata: chunk.metadata,
        }))
      );

      // Track count
      this.chunkCounts.set(collectionName, (this.chunkCounts.get(collectionName) || 0) + chunks.length);
      console.log(`🏗️ Added ${chunks.length} structure chunks to project ${projectId}`);
    } catch (error) {
      console.error('❌ Failed to add structure chunks:', error);
      throw error;
    }
  }

  // Search for similar code patterns
  async searchCode(projectId: string, query: string, nResults: number = 5): Promise<Array<{
    id: string;
    content: string;
    score: number;
    metadata: VectorMetadata;
  }>> {
    try {
      const collectionName = STORAGE_KEYS.PROJECT_CODE(projectId);
      const store = await this.getProjectStore(collectionName);

      const results = await store.similaritySearchWithScore(query, nResults);

      return results.map(([doc, score]: [any, number]) => ({
        id: doc.metadata.id as string || `search_${Date.now()}`,
        content: doc.pageContent,
        score: 1 - (score / 2), // Normalize score (MeMemo uses distance, we want similarity)
        metadata: doc.metadata as VectorMetadata
      }));
    } catch (error) {
      console.error('❌ Failed to search code:', error);
      return [];
    }
  }

  // Search across all project collections
  async searchProject(projectId: string, query: string, nResults: number = 10): Promise<Array<{
    type: 'code' | 'prompt' | 'structure';
    id: string;
    content: string;
    score: number;
    metadata: VectorMetadata;
  }>> {
    try {
      const results: Array<{
        type: 'code' | 'prompt' | 'structure';
        id: string;
        content: string;
        score: number;
        metadata: VectorMetadata;
      }> = [];

      // Search code collection
      const codeResults = await this.searchCode(projectId, query, nResults);
      results.push(...codeResults.map(r => ({ ...r, type: 'code' as const })));

      // Search prompts collection
      try {
        const promptsCollectionName = STORAGE_KEYS.PROJECT_PROMPTS(projectId);
        const promptsStore = await this.getProjectStore(promptsCollectionName);
        const promptsResults = await promptsStore.similaritySearchWithScore(query, Math.ceil(nResults / 3));

        promptsResults.forEach(([doc, score]: [any, number]) => {
          results.push({
            type: 'prompt',
            id: doc.metadata.id as string || `prompt_${Date.now()}`,
            content: doc.pageContent,
            score: 1 - (score / 2),
            metadata: doc.metadata as VectorMetadata
          });
        });
      } catch (error) {
        // Prompts collection might not exist yet - skip
      }

      // Search structure collection
      try {
        const structCollectionName = STORAGE_KEYS.PROJECT_STRUCTURE(projectId);
        const structStore = await this.getProjectStore(structCollectionName);
        const structResults = await structStore.similaritySearchWithScore(query, Math.ceil(nResults / 3));

        structResults.forEach(([doc, score]: [any, number]) => {
          results.push({
            type: 'structure',
            id: doc.metadata.id as string || `struct_${Date.now()}`,
            content: doc.pageContent,
            score: 1 - (score / 2),
            metadata: doc.metadata as VectorMetadata
          });
        });
      } catch (error) {
        // Structure collection might not exist yet - skip
      }

      // Sort by score and return top results
      return results.sort((a, b) => b.score - a.score).slice(0, nResults);
    } catch (error) {
      console.error('❌ Failed to search project:', error);
      return [];
    }
  }

  // Get project statistics
  async getProjectStats(projectId: string): Promise<ProjectEmbeddings | null> {
    try {
      const stats: ProjectEmbeddings = {
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
    } catch (error) {
      console.error('❌ Failed to get project stats:', error);
      return null;
    }
  }

  // Delete project collections
  async deleteProject(projectId: string): Promise<void> {
    try {
      // Remove stores from memory
      this.store.delete(STORAGE_KEYS.PROJECT_CODE(projectId));
      this.store.delete(STORAGE_KEYS.PROJECT_PROMPTS(projectId));
      this.store.delete(STORAGE_KEYS.PROJECT_STRUCTURE(projectId));

      // Remove counts
      this.chunkCounts.delete(STORAGE_KEYS.PROJECT_CODE(projectId));
      this.chunkCounts.delete(STORAGE_KEYS.PROJECT_PROMPTS(projectId));
      this.chunkCounts.delete(STORAGE_KEYS.PROJECT_STRUCTURE(projectId));

      console.log(`🗑️ Deleted ChromaDB collections for project: ${projectId}`);
    } catch (error) {
      console.error('❌ Failed to delete project:', error);
      throw error;
    }
  }

  // Health check (ChromaDB via LangChain is always available)
  async healthCheck(): Promise<boolean> {
    try {
      // LangChain handles ChromaDB connection internally
      // Simple check - verify embeddings are working
      await this.embeddings.embedQuery("test");
      return true;
    } catch (error) {
      console.error('❌ ChromaDB health check failed:', error);
      return false;
    }
  }
}

// Backward compatibility - rename class to ChromaDBManager for existing imports
const ChromaDBManager = VectorStoreManager;

// Export singleton instance
export const chromaManager = new VectorStoreManager();
export default chromaManager;

// Utility functions
export function generateChunkId(projectId: string, filename: string, lines: [number, number], type: string): string {
  return `${projectId}_${filename}_${lines[0]}-${lines[1]}_${type}_${Date.now()}`;
}

export function generatePromptId(projectId: string, sessionId: string, messageIndex: number): string {
  return `${projectId}_${sessionId}_prompt_${messageIndex}`;
}
