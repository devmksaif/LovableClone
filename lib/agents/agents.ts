import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { toolLogger } from '../utils/tool-logger';
import { promptOptimizer } from '../utils/prompt-optimizer';
import { compressContext, summarizeFileContents, estimateTokens, shouldCompress, smartTruncate } from '../utils/summarizer';
import { getMemory, getProjectFolder } from './utils';
import { llm, createLLM } from './model-providers';
import { tools, wrapToolWithLogging } from './tools';
import { AgentStateType } from './agent-core';
import { searchSimilarCode, getProjectContext } from '../utils/vector-tools';

// Non-streaming Planner Agent
export async function plannerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
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

  // Use model-specific LLM if provided, otherwise use global llm
  const llmToUse = model ? createLLM(model) : llm;
  const response = await llmToUse.invoke(messages);
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

// Non-streaming Code Generator Agent
export async function codeGeneratorAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
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

Similar examples from codebase:
${similarExamples}

Project context:
${projectContext}

Current iteration: ${currentStep + 1}/${state.plan.length}`),
  ];

  // Use model-specific LLM if provided, otherwise use global llm
  const llmToUse = model ? createLLM(model) : llm;
  const response = await llmToUse.invoke(contextMessages);
  const generatedContent = response.content.toString();

  // Parse the generated content to extract files
  const files = parseGeneratedFiles(generatedContent);

  return {
    generatedFiles: files,
    currentIteration: currentStep + 1,
    messages: [new AIMessage(`Generated code for step ${currentStep + 1}:\n${generatedContent}`)],
  };
}

// Non-streaming Reviewer Agent
export async function reviewerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  const generatedFiles = state.generatedFiles;

  if (Object.keys(generatedFiles).length === 0) {
    return {
      isComplete: true,
      messages: [new AIMessage('No files to review.')],
    };
  }

  const systemPrompt = `You are a senior code reviewer. Analyze the generated code for:
1. Syntax errors and type issues
2. Logic errors or bugs
3. Security vulnerabilities
4. Performance issues
5. Code quality and best practices
6. Missing functionality
7. Integration issues

Be thorough but constructive. If you find issues, provide specific recommendations for fixes.

Output format:
ISSUES FOUND:
- [Issue 1 with specific details]
- [Issue 2 with specific details]

RECOMMENDATIONS:
- [Specific fix for issue 1]
- [Specific fix for issue 2]

If no issues found, say "CODE REVIEW PASSED"`;

  const fileContents = Object.entries(generatedFiles)
    .map(([filename, content]) => `File: ${filename}\n\`\`\`\n${content}\n\`\`\``)
    .join('\n\n');

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review the following generated code:

${fileContents}

User request: ${state.userRequest}
Plan: ${state.plan.join('\n')}`),
  ];

  // Use model-specific LLM if provided, otherwise use global llm
  const llmToUse = model ? createLLM(model) : llm;
  const response = await llmToUse.invoke(messages);
  const reviewContent = response.content.toString();

  const hasIssues = !reviewContent.toLowerCase().includes('code review passed');

  return {
    reviewFeedback: reviewContent,
    reviewIterations: state.reviewIterations + 1,
    messages: [new AIMessage(`Code review completed:\n${reviewContent}`)],
  };
}

// Helper functions (copied from original)

function parseGeneratedFiles(content: string): Record<string, string> {
  const files: Record<string, string> = {};
  const fileRegex = /FILENAME:\s*([^\n]+)\n```[\w]*\n([\s\S]*?)```/g;

  let match;
  while ((match = fileRegex.exec(content)) !== null) {
    const filename = match[1].trim();
    const fileContent = match[2].trim();
    files[filename] = fileContent;
  }

  return files;
}