import { StateGraph, END, START, Annotation } from '@langchain/langgraph';
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { toolLogger } from '../utils/tool-logger';
import { promptOptimizer } from '../utils/prompt-optimizer';
import { compressContext, summarizeFileContents, estimateTokens, shouldCompress, smartTruncate } from '../utils/summarizer';
import { getMemory, getProjectFolder } from './utils';
import { llm } from './model-providers';
import { tools, wrapToolWithLogging } from './tools';
import { streamingPlannerAgent, streamingCodeGeneratorAgent, streamingReviewerAgent, streamingFixerAgent, shouldContinue } from './streaming-agents';
import { plannerAgent, codeGeneratorAgent, reviewerAgent } from './agents';
import * as fs from 'fs';
import * as path from 'path';

// Import the emit function from the API route
let emitEvent: (sessionId: string, data: any) => void = () => {};
export function setEmitFunction(fn: (sessionId: string, data: any) => void) {
  emitEvent = fn;
}

// Define the state schema for our Lovable-like agent
const AgentState = Annotation.Root({
  messages: Annotation<BaseMessage[]>({
    reducer: (current, update) => [...current, ...update],
    default: () => [],
  }),
  userRequest: Annotation<string>({
    reducer: (_, update) => update,
    default: () => '',
  }),
  plan: Annotation<string[]>({
    reducer: (_, update) => update,
    default: () => [],
  }),
  generatedFiles: Annotation<Record<string, string>>({
    reducer: (current, update) => ({ ...current, ...update }),
    default: () => ({}),
  }),
  currentIteration: Annotation<number>({
    reducer: (_, update) => update,
    default: () => 0,
  }),
  reviewFeedback: Annotation<string>({
    reducer: (_, update) => update,
    default: () => '',
  }),
  isComplete: Annotation<boolean>({
    reducer: (_, update) => update,
    default: () => false,
  }),
  reviewIterations: Annotation<number>({
    reducer: (_, update) => update,
    default: () => 0,
  }),
});

export type AgentStateType = typeof AgentState.State;

// Streaming agent graph
export function createStreamingLovableAgentGraph(sessionId?: string, model?: string) {
  // Update LLM if a specific model is requested
  if (model) {
    const { createLLM } = require('./model-providers');
    const { llm: newLlm } = require('./model-providers');
    // This is a bit of a hack - we need to update the module-level llm
    // In a real refactor, we'd pass llm as a parameter
  }

  const workflow = new StateGraph(AgentState)
    .addNode('planner', (state) => streamingPlannerAgent(state, sessionId, model))
    .addNode('generator', (state) => streamingCodeGeneratorAgent(state, sessionId, model))
    .addNode('reviewer', (state) => streamingReviewerAgent(state, sessionId, model))
    .addNode('fix_issues', (state) => streamingFixerAgent(state, sessionId, model))
    .addEdge(START, 'planner')
    .addConditionalEdges('planner', shouldContinue, {
      planner: 'planner',
      generator: 'generator',
      end: END,
    })
    .addConditionalEdges('generator', shouldContinue, {
      generator: 'generator',
      reviewer: 'reviewer',
      end: END,
    })
    .addConditionalEdges('reviewer', shouldContinue, {
      fix_issues: 'fix_issues',
      end: END,
    })
    .addConditionalEdges('fix_issues', shouldContinue, {
      reviewer: 'reviewer',
      end: END,
    });

  return workflow.compile();
}

// Non-streaming agent graph
export function createLovableAgentGraph(sessionId?: string, model?: string) {
  const workflow = new StateGraph(AgentState)
    .addNode('planner', (state) => plannerAgent(state, sessionId, model))
    .addNode('generator', (state) => codeGeneratorAgent(state, sessionId, model))
    .addNode('reviewer', (state) => reviewerAgent(state, sessionId, model))
    .addEdge(START, 'planner')
    .addConditionalEdges('planner', shouldContinue, {
      generator: 'generator',
      end: END,
    })
    .addConditionalEdges('generator', shouldContinue, {
      generator: 'generator',
      reviewer: 'reviewer',
      end: END,
    })
    .addConditionalEdges('reviewer', shouldContinue, {
      generator: 'generator',
      end: END,
    });

  return workflow.compile();
}

// Helper function to save generated files to disk
export function saveGeneratedFiles(files: Record<string, string>, outputDir?: string) {
  const memory = getMemory();

  // Use project folder if no output directory specified
  const targetDir = outputDir || getProjectFolder();

  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }

  const savedFiles: string[] = [];

  for (const [filename, content] of Object.entries(files)) {
    const fullPath = path.join(targetDir, filename);
    const dir = path.dirname(fullPath);

    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    const exists = fs.existsSync(fullPath);
    fs.writeFileSync(fullPath, content, 'utf-8');

    // Track in memory
    memory.addFileOperation(exists ? 'modified' : 'created', fullPath);

    savedFiles.push(fullPath);
  }

  return savedFiles;
}

// Export tool logger statistics
export function getToolCallStats() {
  return toolLogger.getStats();
}

export function getToolCallSummary() {
  return toolLogger.getSummary();
}

export function clearToolCallLogs() {
  toolLogger.clear();
}

// Get memory statistics for debugging/monitoring
export async function getMemoryStats() {
  const memory = getMemory();
  const messages = await memory.getMessages();
  const fileOps = await memory.getRecentFileOperations();
  const sessionFiles = await memory.getSessionFiles();

  return {
    tokenEstimate: await memory.getTokenEstimate(),
    messageCount: messages.length,
    fileOperationCount: fileOps.length,
    sessionFiles: sessionFiles,
  };
}