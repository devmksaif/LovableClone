import { ChatOpenAI } from '@langchain/openai';
import { ChatGoogleGenerativeAI } from '@langchain/google-genai';
import { ChatGroq } from '@langchain/groq';
import { StateGraph, END, START, Annotation } from '@langchain/langgraph';
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import { searchSimilarCode, getProjectContext } from '../../lib/utils/vector-tools';
import 'dotenv/config';

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
});

type AgentStateType = typeof AgentState.State;

// Initialize the LLM model with provider selection
function createLLM() {
  // Priority: Groq (fastest) → Gemini (reliable) → OpenRouter (fallback)
  const groqApiKey = process.env.GROQ_API_KEY;
  const geminiApiKey = process.env.GEMINI_API_KEY;
  const openRouterApiKey = process.env.OPENROUTER_API_KEY ?? process.env.OPENAI_API_KEY;

  if (groqApiKey) {
    console.log('⚡ Using Groq API (Fastest)');
    return new ChatGroq({
      apiKey: groqApiKey,
      model: process.env.GROQ_MODEL ?? 'llama3-8b-8192',
      temperature: 0.7,
      maxTokens: 4096,
    });
  } else if (geminiApiKey) {
    console.log('🤖 Using Google Gemini API');
    return new ChatGoogleGenerativeAI({
      apiKey: geminiApiKey,
      model: process.env.GEMINI_MODEL ?? 'gemini-1.5-pro',
      temperature: 0.7,
      maxOutputTokens: 4096,
    });
  } else if (openRouterApiKey) {
    console.log('🔄 Using OpenRouter API');
    const apiBase = process.env.OPENROUTER_API_BASE ?? process.env.OPENAI_API_BASE ?? 'https://openrouter.ai/api/v1';
    return new ChatOpenAI({
      apiKey: openRouterApiKey,
      configuration: {
        baseURL: apiBase,
      },
      model: process.env.OPENAI_MODEL ?? process.env.OPENROUTER_MODEL ?? 'openai/gpt-4o',
      temperature: 0.7,
    });
  } else {
    throw new Error('No API key found. Set GROQ_API_KEY, GEMINI_API_KEY, or OPENROUTER_API_KEY/OPENAI_API_KEY');
  }
}

const llm = createLLM();

// Planner Agent: Breaks down user request into actionable steps
async function plannerAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  const systemPrompt = `You are a senior software architect. Break down the user's request into clear, actionable steps.
Each step should be specific and focused on a single file or component.

Output format:
1. [Step description]
2. [Step description]
...

Be concise but clear about what needs to be built.`;

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`User request: ${state.userRequest}\n\nCreate a detailed plan with numbered steps.`),
  ];

  const response = await llm.invoke(messages);
  const planText = response.content.toString();
  
  // Extract numbered steps
  const steps = planText
    .split('\n')
    .filter(line => /^\d+\./.test(line.trim()))
    .map(line => line.trim());

  return {
    plan: steps,
    messages: [new AIMessage(`Plan created:\n${planText}`)],
  };
}

// Code Generator Agent: Generates code based on the plan
async function codeGeneratorAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  const currentStep = state.currentIteration;
  const stepToImplement = state.plan[currentStep];

  if (!stepToImplement) {
    return {
      isComplete: true,
      messages: [new AIMessage('All planned steps have been completed.')],
    };
  }

  // Use consistent project ID for vector context
  const projectId = 'agent_context_project';

  // Get vector context for better code generation
  let similarExamples = '';
  let projectContext = '';

  try {
    // Search for similar code examples
    similarExamples = await searchSimilarCode(stepToImplement, projectId, 3);
    console.log(`📚 Found similar examples for step: ${stepToImplement.substring(0, 50)}...`);

    // Get project context
    projectContext = await getProjectContext(projectId);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.log(`⚠️ Vector search unavailable (${errorMessage}) - proceeding without examples`);
    similarExamples = 'Vector search not available - proceeding without examples.';
    projectContext = 'Project context not available.';
  }

  const systemPrompt = `You are an expert full-stack developer. Generate clean, well-documented code.

Rules:
1. Think step by step when generating code and log your chain of thought
2. Generate complete, working code
3. Include comments for complex logic
4. Follow best practices and modern patterns
5. Use TypeScript when applicable
6. Return code in a structured format with filename and content
7. Reference similar examples when applicable to maintain consistency

Output format:
Chain of Thought:
[Your step-by-step reasoning here]

Files:
FILENAME: [relative/path/to/file.ext]
\`\`\`[language]
[code here]
\`\`\`

You can output multiple files if needed.`;

  const contextMessages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Current step to implement: ${stepToImplement}

Full plan context:
${state.plan.join('\n')}

${Object.keys(state.generatedFiles).length > 0 ? `\nAlready generated files:\n${Object.keys(state.generatedFiles).join('\n')}` : ''}

Project Context:
${projectContext}

Similar Code Examples:
${similarExamples}

Generate the code for this step, referencing similar examples when helpful.`),
  ];

  const response = await llm.invoke(contextMessages);
  const content = response.content.toString();

  // Log chain of thought
  const cotMatch = content.match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
  if (cotMatch) {
    console.log(`🔍 Code Generator Chain of Thought (Step ${currentStep + 1}):\n${cotMatch[1].trim()}\n`);
  }

  // Parse generated files from the response
  const files = parseGeneratedFiles(content);

  return {
    generatedFiles: files,
    currentIteration: currentStep + 1,
    messages: [new AIMessage(content)],
  };
}

// Code Reviewer Agent: Reviews generated code and provides feedback
async function reviewerAgent(state: AgentStateType): Promise<Partial<AgentStateType>> {
  const latestFiles = Object.entries(state.generatedFiles)
    .slice(-5) // Review last 5 files
    .map(([filename, code]) => `${filename}:\n\`\`\`\n${code.substring(0, 500)}...\n\`\`\``)
    .join('\n\n');

  const systemPrompt = `You are a code reviewer. Review the generated code for:
1. Correctness
2. Best practices
3. Potential bugs
4. Missing functionality
5. Code quality

Provide constructive feedback. If the code is good, say "APPROVED".
If improvements are needed, be specific about what needs to change.`;

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review this code:\n\n${latestFiles}\n\nOriginal request: ${state.userRequest}`),
  ];

  const response = await llm.invoke(messages);
  const feedback = response.content.toString();

  const isApproved = feedback.toUpperCase().includes('APPROVED');

  return {
    reviewFeedback: feedback,
    isComplete: isApproved && state.currentIteration >= state.plan.length,
    messages: [new AIMessage(`Review: ${feedback}`)],
  };
}

// Router: Decides next step
function shouldContinue(state: AgentStateType): string {
  if (state.isComplete) {
    return 'end';
  }
  
  if (state.plan.length === 0) {
    return 'planner';
  }
  
  if (state.currentIteration < state.plan.length) {
    return 'generator';
  }
  
  if (!state.reviewFeedback) {
    return 'reviewer';
  }
  
  // If reviewed and approved, we're done
  if (state.isComplete) {
    return 'end';
  }
  
  // Otherwise, continue generating
  return 'generator';
}

// Helper function to parse generated files from LLM output
function parseGeneratedFiles(content: string): Record<string, string> {
  const files: Record<string, string> = {};
  const fileRegex = /FILENAME:\s*(.+?)\n```(\w+)?\n([\s\S]*?)```/g;
  
  let match;
  while ((match = fileRegex.exec(content)) !== null) {
    const filename = match[1].trim();
    const code = match[3].trim();
    files[filename] = code;
  }
  
  return files;
}

// Build the workflow graph
export function createLovableAgentGraph() {
  const workflow = new StateGraph(AgentState)
    .addNode('planner', plannerAgent)
    .addNode('generator', codeGeneratorAgent)
    .addNode('reviewer', reviewerAgent)
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
export function saveGeneratedFiles(files: Record<string, string>, outputDir: string = './generated') {
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const savedFiles: string[] = [];
  
  for (const [filename, content] of Object.entries(files)) {
    const fullPath = path.join(outputDir, filename);
    const dir = path.dirname(fullPath);
    
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    
    fs.writeFileSync(fullPath, content, 'utf-8');
    savedFiles.push(fullPath);
  }
  
  return savedFiles;
}
