import { ChatOpenAI } from '@langchain/openai';
import { SystemMessage, HumanMessage } from '@langchain/core/messages';

// Initialize a lightweight model for summarization
const apiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY;
const apiBase = 'https://openrouter.ai/api/v1';

const summarizer = new ChatOpenAI({
  apiKey,
  configuration: {
    baseURL: apiBase,
  },
  model: process.env.OPENROUTER_MODEL , // Use cheaper model for summarization
  temperature: 0.3,
  maxTokens: 500,
});

export interface SummarizedContext {
  summary: string;
  tokensSaved: number;
  originalLength: number;
}

/**
 * Summarize conversation history to reduce token usage
 */
export async function summarizeConversation(
  messages: Array<{ role: string; content: string }>,
  maxMessages: number = 10
): Promise<SummarizedContext> {
  // Keep the most recent messages, summarize older ones
  if (messages.length <= maxMessages) {
    return {
      summary: messages.map(m => `${m.role}: ${m.content}`).join('\n'),
      tokensSaved: 0,
      originalLength: messages.length,
    };
  }

  const recentMessages = messages.slice(-maxMessages);
  const oldMessages = messages.slice(0, -maxMessages);

  const oldMessagesText = oldMessages
    .map(m => `${m.role}: ${m.content}`)
    .join('\n');

  const systemPrompt = `You are a context summarizer. Condense the conversation history into a brief, relevant summary.

Focus on:
1. Key user requests and what was accomplished
2. Important decisions made
3. Files created/modified
4. Current state of the project

Keep it under 200 words. Be concise but preserve critical context.`;

  try {
    const response = await summarizer.invoke([
      new SystemMessage(systemPrompt),
      new HumanMessage(`Summarize this conversation history:\n\n${oldMessagesText}`),
    ]);

    const summary = response.content.toString();
    
    // Estimate tokens saved (rough estimate: 4 chars ≈ 1 token)
    const originalTokens = Math.ceil(oldMessagesText.length / 4);
    const summaryTokens = Math.ceil(summary.length / 4);
    const tokensSaved = originalTokens - summaryTokens;

    return {
      summary,
      tokensSaved,
      originalLength: messages.length,
    };
  } catch (error) {
    console.error('Summarization error:', error);
    // Fallback: just return recent messages
    return {
      summary: recentMessages.map(m => `${m.role}: ${m.content}`).join('\n'),
      tokensSaved: 0,
      originalLength: messages.length,
    };
  }
}

/**
 * Summarize file contents to reduce token usage when passing as context
 */
export async function summarizeFileContents(
  files: Record<string, string>,
  maxFileSize: number = 500
): Promise<Record<string, string>> {
  const summarizedFiles: Record<string, string> = {};

  for (const [filename, content] of Object.entries(files)) {
    // If file is small enough, keep it as-is
    if (content.length <= maxFileSize) {
      summarizedFiles[filename] = content;
      continue;
    }

    // For large files, provide a structure summary
    const lines = content.split('\n');
    const firstLines = lines.slice(0, 10).join('\n');
    const lastLines = lines.slice(-5).join('\n');
    
    const summary = `${firstLines}\n\n... (${lines.length - 15} lines omitted) ...\n\n${lastLines}`;
    summarizedFiles[filename] = summary;
  }

  return summarizedFiles;
}

/**
 * Intelligent context compression for agent prompts
 */
export async function compressContext(options: {
  userRequest: string;
  conversationHistory?: Array<{ role: string; content: string }>;
  existingFiles?: Record<string, string>;
  plan?: string[];
  recentOperations?: string[];
}): Promise<{
  compressedContext: string;
  stats: {
    originalSize: number;
    compressedSize: number;
    compressionRatio: number;
  };
}> {
  const parts: string[] = [];
  let originalSize = 0;

  // 1. User request (always include, high priority)
  parts.push(`USER REQUEST: ${options.userRequest}`);
  originalSize += options.userRequest.length;

  // 2. Conversation history (summarize if long)
  if (options.conversationHistory && options.conversationHistory.length > 0) {
    const { summary, tokensSaved } = await summarizeConversation(
      options.conversationHistory,
      5 // Keep last 5 messages
    );
    
    parts.push(`\nCONVERSATION CONTEXT:\n${summary}`);
    originalSize += options.conversationHistory.reduce(
      (sum, m) => sum + m.content.length,
      0
    );
  }

  // 3. Existing files (summarize large files)
  if (options.existingFiles && Object.keys(options.existingFiles).length > 0) {
    const summarizedFiles = await summarizeFileContents(options.existingFiles, 400);
    
    parts.push(`\nEXISTING FILES:`);
    for (const [filename, content] of Object.entries(summarizedFiles)) {
      parts.push(`\n--- ${filename} ---\n${content}`);
    }
    
    originalSize += Object.values(options.existingFiles).reduce(
      (sum, content) => sum + content.length,
      0
    );
  }

  // 4. Plan (always include if present)
  if (options.plan && options.plan.length > 0) {
    parts.push(`\nPLAN:\n${options.plan.map((s, i) => `${i + 1}. ${s}`).join('\n')}`);
    originalSize += options.plan.join('').length;
  }

  // 5. Recent operations (keep brief)
  if (options.recentOperations && options.recentOperations.length > 0) {
    const recentOps = options.recentOperations.slice(-5);
    parts.push(`\nRECENT OPERATIONS:\n${recentOps.join('\n')}`);
    originalSize += options.recentOperations.join('').length;
  }

  const compressedContext = parts.join('\n');
  const compressedSize = compressedContext.length;
  const compressionRatio = originalSize > 0 
    ? ((originalSize - compressedSize) / originalSize * 100)
    : 0;

  return {
    compressedContext,
    stats: {
      originalSize,
      compressedSize,
      compressionRatio,
    },
  };
}

/**
 * Smart truncation for very long content
 */
export function smartTruncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }

  // Try to truncate at a natural boundary (newline, period, etc.)
  const truncated = text.substring(0, maxLength);
  const lastNewline = truncated.lastIndexOf('\n');
  const lastPeriod = truncated.lastIndexOf('.');
  
  const cutPoint = Math.max(lastNewline, lastPeriod);
  
  if (cutPoint > maxLength * 0.8) {
    return text.substring(0, cutPoint + 1) + '\n... (truncated)';
  }
  
  return truncated + '\n... (truncated)';
}

/**
 * Calculate approximate token count
 */
export function estimateTokens(text: string): number {
  // Rough estimate: ~4 characters per token
  // More accurate for English text
  return Math.ceil(text.length / 4);
}

/**
 * Check if context is getting too large and needs compression
 */
export function shouldCompress(text: string, maxTokens: number = 2000): boolean {
  return estimateTokens(text) > maxTokens;
}
