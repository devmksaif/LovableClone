/**
 * Prompt Optimizer
 * Optimizes prompts before sending to AI to reduce token usage and improve clarity
 */

import { estimateTokens, smartTruncate } from './summarizer';

interface PromptOptimizationResult {
  optimizedPrompt: string;
  originalTokens: number;
  optimizedTokens: number;
  savings: number;
  savingsPercent: number;
}

export class PromptOptimizer {
  private maxTokens: number;

  constructor(maxTokens: number = 4000) {
    this.maxTokens = maxTokens;
  }

  /**
   * Optimize a prompt by removing redundancy and compressing content
   */
  optimize(prompt: string, context?: string): PromptOptimizationResult {
    const originalTokens = estimateTokens(prompt);
    
    let optimized = prompt;

    // 1. Remove excessive whitespace
    optimized = this.removeExcessiveWhitespace(optimized);

    // 2. Deduplicate repeated instructions
    optimized = this.deduplicateInstructions(optimized);

    // 3. Compress file listings
    optimized = this.compressFileLists(optimized);

    // 4. Remove redundant phrases
    optimized = this.removeRedundantPhrases(optimized);

    // 5. If still too long, truncate intelligently
    if (estimateTokens(optimized) > this.maxTokens) {
      optimized = this.intelligentTruncate(optimized, context);
    }

    const optimizedTokens = estimateTokens(optimized);
    const savings = originalTokens - optimizedTokens;
    const savingsPercent = originalTokens > 0 ? (savings / originalTokens) * 100 : 0;

    if (savings > 50) {
      console.log(`🎯 Prompt optimized: ${originalTokens} → ${optimizedTokens} tokens (${Math.round(savingsPercent)}% reduction)`);
    }

    return {
      optimizedPrompt: optimized,
      originalTokens,
      optimizedTokens,
      savings,
      savingsPercent,
    };
  }

  private removeExcessiveWhitespace(text: string): string {
    return text
      .split('\n')
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .join('\n')
      .replace(/\n{3,}/g, '\n\n'); // Max 2 consecutive newlines
  }

  private deduplicateInstructions(text: string): string {
    const lines = text.split('\n');
    const seen = new Set<string>();
    const result: string[] = [];

    for (const line of lines) {
      const normalized = line.toLowerCase().trim();
      
      // Skip if we've seen this exact instruction
      if (normalized.length > 20 && seen.has(normalized)) {
        continue;
      }
      
      seen.add(normalized);
      result.push(line);
    }

    return result.join('\n');
  }

  private compressFileLists(text: string): string {
    // Compress long file lists
    const fileListPattern = /(?:EXISTING FILES|Session files|Current state files):\s*\n((?:[-•]\s*[^\n]+\n?)+)/gi;
    
    return text.replace(fileListPattern, (match, fileList) => {
      const files = fileList
        .split('\n')
        .filter((l: string) => l.trim().length > 0);
      
      if (files.length > 10) {
        const first5 = files.slice(0, 5).join('\n');
        const last3 = files.slice(-3).join('\n');
        return `${match.split(':')[0]}:\n${first5}\n... (${files.length - 8} more files)\n${last3}`;
      }
      
      return match;
    });
  }

  private removeRedundantPhrases(text: string): string {
    // Remove common redundant phrases
    const redundantPhrases = [
      /Please note that /gi,
      /It is important to /gi,
      /You should be aware that /gi,
      /Keep in mind that /gi,
      /Remember to /gi,
      /Make sure to /gi,
      /Don't forget to /gi,
      /Be sure to /gi,
    ];

    let result = text;
    for (const phrase of redundantPhrases) {
      result = result.replace(phrase, '');
    }

    return result;
  }

  private intelligentTruncate(text: string, context?: string): string {
    // Priority sections (keep these)
    const sections = text.split('\n\n');
    const priority: string[] = [];
    const medium: string[] = [];
    const low: string[] = [];

    for (const section of sections) {
      const lower = section.toLowerCase();
      
      if (
        lower.includes('critical') ||
        lower.includes('important') ||
        lower.includes('rules:') ||
        lower.includes('current step')
      ) {
        priority.push(section);
      } else if (
        lower.includes('existing files') ||
        lower.includes('available tools') ||
        lower.includes('context')
      ) {
        medium.push(section);
      } else {
        low.push(section);
      }
    }

    // Rebuild with priority
    let result = priority.join('\n\n');
    let currentTokens = estimateTokens(result);

    // Add medium priority sections if space allows
    for (const section of medium) {
      const sectionTokens = estimateTokens(section);
      if (currentTokens + sectionTokens < this.maxTokens * 0.9) {
        result += '\n\n' + section;
        currentTokens += sectionTokens;
      } else {
        // Truncate section
        const truncated = smartTruncate(section, 200);
        result += '\n\n' + truncated;
        break;
      }
    }

    return result;
  }

  /**
   * Optimize system prompt specifically
   */
  optimizeSystemPrompt(systemPrompt: string, contextSummary?: string): string {
    const { optimizedPrompt } = this.optimize(systemPrompt, contextSummary);
    return optimizedPrompt;
  }

  /**
   * Optimize file content before including in prompt
   */
  optimizeFileContent(filePath: string, content: string, maxLines: number = 50): string {
    const lines = content.split('\n');
    
    if (lines.length <= maxLines) {
      return content;
    }

    // Show first and last portions
    const firstLines = lines.slice(0, Math.floor(maxLines / 2));
    const lastLines = lines.slice(-Math.floor(maxLines / 2));
    
    return `${firstLines.join('\n')}\n... (${lines.length - maxLines} lines omitted) ...\n${lastLines.join('\n')}`;
  }

  /**
   * Batch optimize multiple prompts
   */
  batchOptimize(prompts: string[]): string[] {
    return prompts.map(p => this.optimize(p).optimizedPrompt);
  }
}

export const promptOptimizer = new PromptOptimizer(4000);
