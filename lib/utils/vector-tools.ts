import { chromaManager } from '../db/chroma';

/**
 * Tool for searching similar code examples from vector store
 */
export async function searchSimilarCode(query: string, projectId: string, maxResults: number = 5): Promise<string> {
  try {
    console.log(`🔍 Searching for similar code: "${query}" in project ${projectId}`);

    const results = await chromaManager.searchCode(projectId, query, maxResults);

    if (results.length === 0) {
      return 'No similar code examples found.';
    }

    const examples = results.map((result, index) => {
      const filename = result.metadata.filename || 'unknown';
      const score = Math.round(result.score * 100);
      const content = result.content.length > 300
        ? result.content.substring(0, 300) + '...'
        : result.content;

      return `Example ${index + 1} (${score}% match - ${filename}):
\`\`\`
${content}
\`\`\``;
    }).join('\n\n');

    return `Found ${results.length} similar code examples:\n\n${examples}`;
  } catch (error) {
    console.error('❌ Vector search failed:', error);
    return 'Error searching for similar code examples.';
  }
}

/**
 * Tool for getting project context and structure
 */
export async function getProjectContext(projectId: string): Promise<string> {
  try {
    console.log(`📊 Getting project context for: ${projectId}`);

    const stats = await chromaManager.getProjectStats(projectId);

    if (!stats) {
      return 'No project context available.';
    }

    return `Project Statistics:
- Total chunks: ${stats.total_chunks}
- Code chunks: ${stats.code_chunks}
- Structure chunks: ${stats.structure_chunks}
- Prompt chunks: ${stats.prompt_chunks}
- Dependency chunks: ${stats.dependency_chunks}
- Created: ${stats.created_at}
- Last updated: ${stats.last_updated}`;
  } catch (error) {
    console.error('❌ Failed to get project context:', error);
    return 'Error retrieving project context.';
  }
}