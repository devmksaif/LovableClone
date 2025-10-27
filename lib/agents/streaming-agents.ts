import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages';
import { toolLogger } from '../utils/tool-logger';
import { promptOptimizer } from '../utils/prompt-optimizer';
import { compressContext, summarizeFileContents, estimateTokens, shouldCompress, smartTruncate } from '../utils/summarizer';
import { getMemory, getProjectFolder } from './utils';
import { llm, createLLM } from './model-providers';
import { tools, wrapToolWithLogging } from './tools';
import { AgentStateType } from './agent-core';
import * as path from 'path';

// Import the emit function from the API route
let emitEvent: (sessionId: string, data: any) => void = () => {};
export function setEmitFunction(fn: (sessionId: string, data: any) => void) {
  emitEvent = fn;
}

// Bind tools to the LLM
const llmWithTools = llm.bindTools(tools);

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

// Streaming Planner Agent: Breaks down user request into actionable steps
export async function streamingPlannerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Planning your request...' });

  const memory = getMemory();

  // Add user request to memory
  await memory.addMessage('user', state.userRequest);

  // Get compressed context from memory
  const contextSummary = await memory.getCompressedContext(state.userRequest);
  const sessionFiles = await memory.getSessionFiles();

  // Check if there are existing files - if so, this is a modification request
  const hasExistingFiles = Object.keys(state.generatedFiles).length > 0 || sessionFiles.length > 0;

  let systemPrompt = `You are a senior software architect. Analyze the user's request and create a clear plan.

${hasExistingFiles ? `
IMPORTANT: There are EXISTING FILES in this session. The user wants to MODIFY or ENHANCE them.
Session files: ${sessionFiles.length > 0 ? sessionFiles.join(', ') : 'None'}
Current state files: ${Object.keys(state.generatedFiles).join(', ')}

Your plan should focus on MODIFYING these existing files, not creating new random files.
` : `
This is a NEW project. Create a plan to build it from scratch.
`}

${contextSummary ? `\nRECENT CONTEXT:\n${smartTruncate(contextSummary, 800)}` : ''}

OUTPUT FORMAT: Just numbered steps like:
1. Create/Modify [specific file] - [what to do]
2. Update [specific file] - [what to change]
3. Add [feature] to [file]

RULES:
- Maximum 5 steps
- Be SPECIFIC about which files to create/modify
- If modifying, say "Modify" or "Update", not "Create"
- Each step should produce tangible code
- Keep it simple and actionable`;

  // Optimize the system prompt
  systemPrompt = promptOptimizer.optimizeSystemPrompt(systemPrompt, contextSummary || undefined);

  let contextInfo = `User request: ${state.userRequest}`;

  if (hasExistingFiles) {
    const allFiles = Array.from(new Set([...sessionFiles, ...Object.keys(state.generatedFiles)]));
    contextInfo += `\n\nEXISTING PROJECT FILES:\n${allFiles.map(f => `- ${f}`).join('\n')}`;
    contextInfo += `\n\nThe user wants to modify/enhance the existing project. Create a plan that works WITH these files.`;
  }

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(contextInfo),
  ];

  // Use model-specific LLM if provided, otherwise use global llm
  const llmToUse = model ? createLLM(model) : llm;
  const response = await llmToUse.invoke(messages);
  const planText = response.content.toString();

  // Add plan to memory
  await memory.addMessage('assistant', `Planning: ${planText.substring(0, 200)}...`);

  // Parse the plan into steps
  const planSteps = planText
    .split('\n')
    .filter(line => /^\d+\./.test(line.trim()))
    .map(line => line.replace(/^\d+\.\s*/, '').trim())
    .filter(step => step.length > 0)
    .slice(0, 5); // Limit to 5 steps

  console.log(`📋 Generated plan with ${planSteps.length} steps:`, planSteps);

  // Emit plan to client
  emitEvent(sessionId || '', { type: 'plan', plan: planSteps });

  return {
    plan: planSteps,
    messages: [new AIMessage(`Planning completed. Created ${planSteps.length} steps to implement your request.`)],
  };
}

// Streaming Code Generator Agent: Implements each step of the plan
export async function streamingCodeGeneratorAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  const currentStep = state.currentIteration;
  const stepToImplement = state.plan[currentStep];

  emitEvent(sessionId || '', {
    type: 'status',
    message: `Generating code for step ${currentStep + 1}: ${stepToImplement?.substring(0, 50)}...`
  });

  if (!stepToImplement) {
    console.log('⚠️  No step to implement at iteration', currentStep);
    return { isComplete: true };
  }

  const memory = getMemory();
  const contextSummary = await memory.getCompressedContext(state.userRequest);
  const sessionFiles = await memory.getSessionFiles();

  // Get existing files for context
  const existingFiles = { ...state.generatedFiles };
  for (const file of sessionFiles) {
    try {
      const content = await import('fs').then(fs => fs.readFileSync(file, 'utf-8'));
      existingFiles[file] = content;
    } catch (error) {
      console.warn(`Could not read existing file ${file}:`, error);
    }
  }

  const systemPrompt = `You are an expert software engineer. Implement the specified step using the available tools.

IMPORTANT RULES:
- Use the provided tools to create/modify files
- Each tool call should be purposeful and targeted
- Read existing files first to understand the current state
- Make incremental, testable changes
- Include proper imports and dependencies
- Follow the existing code style and patterns
- Test your changes by reading the files back

${contextSummary ? `CONTEXT:\n${smartTruncate(contextSummary, 600)}\n\n` : ''}

AVAILABLE TOOLS:
- read_file: Read existing files
- write_file: Create new files or replace entire files
- append_to_file: Add content to existing files
- replace_in_file: Find and replace text patterns
- insert_at_line: Insert content at specific line numbers
- replace_block: Replace content between markers
- replace_line_range: Replace specific line ranges
- search_files: Find code patterns across files
- execute_command: Run shell commands (npm, git, etc.)

OUTPUT FORMAT:
Chain of Thought: [Your reasoning process]
Files: [List of files you'll create/modify]
[Then use the appropriate tools to implement the changes]

TOOL USAGE:
- Use tools by calling them directly in your response
- Each tool call should be a separate function call with proper JSON arguments
- Tools will automatically execute and provide results
- Format: Call tools like normal function calls with the tool name and arguments
- Example: write_file({ "filePath": "index.html", "content": "<html>...</html>" })`;

  const userPrompt = `Implement this step: "${stepToImplement}"

Existing project files: ${Object.keys(existingFiles).join(', ') || 'None'}

${state.reviewFeedback ? `Previous review feedback to address: ${state.reviewFeedback}` : ''}`;

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(userPrompt),
  ];

  // Use model-specific LLM if provided, otherwise use global llmWithTools
  const llmToUse = model ? createLLM(model) : llm;
  const llmWithToolsToUse = model ? llmToUse.bindTools(tools) : llmWithTools;
  const response = await llmWithToolsToUse.invoke(messages);

  // Extract generated files from tool calls or response content
  const generatedFiles: Record<string, string> = {};
  let chainOfThought = '';

  if (response.tool_calls && response.tool_calls.length > 0) {
    for (const toolCall of response.tool_calls) {
      console.log(`🔧 Tool called: ${toolCall.name}`, toolCall.args);
      if (toolCall.name === 'write_file' || toolCall.name === 'append_to_file') {
        try {
          const args = toolCall.args as any;
          if (args.filePath && args.content) {
            generatedFiles[args.filePath] = args.content;
          }
        } catch (error) {
          console.warn('Could not parse tool call arguments:', error);
        }
      }
    }
    console.log(`📊 Processed ${response.tool_calls.length} tool calls`);
  } else {
    // Fallback: parse files from response content
    const newFiles = parseGeneratedFiles(response.content.toString());
    Object.assign(generatedFiles, newFiles);
  }

  // Extract chain of thought from response
  const content = response.content.toString();
  const cotMatch = content.match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
  if (cotMatch) {
    chainOfThought = cotMatch[1].trim();
  }

  // Add to memory
  await memory.addMessage('assistant', `Step ${currentStep + 1}: ${chainOfThought.substring(0, 200)}...`);

  // Emit real-time updates
  if (chainOfThought) {
    console.log(`🔍 Real-time COT Step ${currentStep + 1}: ${chainOfThought.substring(0, 100)}...`);
    emitEvent(sessionId || '', {
      type: 'chain_of_thought',
      step: currentStep + 1,
      reasoning: chainOfThought
    });
  }

  if (Object.keys(generatedFiles).length > 0) {
    const files = Object.keys(generatedFiles);
    console.log(`📁 Real-time Files Generated: ${files.join(', ')}`);
    emitEvent(sessionId || '', {
      type: 'files_generated',
      files: files,
      step: currentStep + 1
    });
  }

  return {
    generatedFiles,
    currentIteration: currentStep + 1,
    messages: [new AIMessage(`Step ${currentStep + 1} completed. ${Object.keys(generatedFiles).length} files updated.`)],
  };
}

// Streaming Reviewer Agent: Reviews the generated code for quality and completeness
export async function streamingReviewerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Reviewing generated code...' });

  const memory = getMemory();
  const allFiles = { ...state.generatedFiles };

  // Read current state of all files - try multiple resolution strategies
  // 1) If filePath is absolute or exists under project folder, use it
  // 2) Otherwise try to find a matching basename in session files tracked in memory
  // 3) Fallback to the content already present in state.generatedFiles
  const sessionFiles = await memory.getSessionFiles();
  for (const filePath of Object.keys(allFiles)) {
    try {
      const fs = await import('fs');
      const projectFolder = getProjectFolder();

      // Candidate 1: absolute path or projectFolder + filePath
      const candidate = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
      if (fs.existsSync(candidate)) {
        allFiles[filePath] = fs.readFileSync(candidate, 'utf-8');
        continue;
      }

      // Candidate 2: look up by basename in sessionFiles recorded in memory
      const base = path.basename(filePath);
      const match = sessionFiles.find(f => path.basename(f) === base);
      if (match && fs.existsSync(match)) {
        allFiles[filePath] = fs.readFileSync(match, 'utf-8');
        continue;
      }

      // Candidate 3: attempt a recursive scan under project folder for a matching basename (best-effort)
      let found = null as string | null;
      try {
        const walk = (dir: string) => {
          const entries = fs.readdirSync(dir, { withFileTypes: true });
          for (const ent of entries) {
            const p = path.join(dir, ent.name);
            if (ent.isDirectory()) {
              walk(p);
              if (found) return;
            } else if (ent.isFile() && path.basename(p) === base) {
              found = p;
              return;
            }
          }
        };
        if (fs.existsSync(projectFolder)) walk(projectFolder);
      } catch (err) {
        // ignore scanning errors
      }

      if (found && fs.existsSync(found)) {
        allFiles[filePath] = fs.readFileSync(found, 'utf-8');
        continue;
      }

      // If none of the above succeeded, leave the content as-is and warn
      console.warn(`Could not locate file ${filePath} under project folder; using in-memory content if available.`);
    } catch (error) {
      console.warn(`Could not read file ${filePath} for review:`, error);
    }
  }

  const systemPrompt = `You are a senior code reviewer. Review the generated code for quality, completeness, and correctness.

EVALUATION CRITERIA:
- Code quality and best practices
- Proper imports and dependencies
- Error handling and edge cases
- TypeScript types (if applicable)
- Code organization and readability
- Completeness of implementation
- Integration with existing codebase

OUTPUT FORMAT:
APPROVED or NEEDS IMPROVEMENT

If NEEDS IMPROVEMENT, provide specific, actionable feedback.
If APPROVED, confirm the implementation is complete and ready.

Be constructive and specific in your feedback.`;

  const codeSummary = Object.entries(allFiles)
    .map(([file, content]) => `=== ${file} ===\n${content.substring(0, 500)}${content.length > 500 ? '\n... (truncated)' : ''}`)
    .join('\n\n');

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review the following generated code:\n\n${codeSummary}`),
  ];

  // Use model-specific LLM if provided, otherwise use global llm
  const llmToUse = model ? createLLM(model) : llm;
  const response = await llmToUse.invoke(messages);
  const feedback = response.content.toString().trim();

  const isApproved = feedback.toUpperCase().includes('APPROVED') &&
                     !feedback.toLowerCase().includes('missing') &&
                     !feedback.toLowerCase().includes('not implemented');

  console.log(`🔍 Review result: ${isApproved ? 'APPROVED' : 'NEEDS IMPROVEMENT'}`);
  console.log(`📝 Feedback: ${feedback.substring(0, 100)}...`);

  // Add to memory
  await memory.addMessage('assistant', `Review: ${feedback.substring(0, 200)}...`);

  // Emit review results
  emitEvent(sessionId || '', { type: 'review', feedback: feedback });

  if (isApproved) {
    emitEvent(sessionId || '', { type: 'complete', message: 'Code generation completed successfully!' });
  }

  return {
    reviewFeedback: feedback,
    isComplete: isApproved,
    reviewIterations: (state.reviewIterations || 0) + 1,
  };
}

// Streaming Fixer Agent: Addresses review feedback by fixing issues
export async function streamingFixerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Fixing issues based on review...' });

  const memory = getMemory();
  const contextSummary = await memory.getCompressedContext(state.userRequest);

  const systemPrompt = `You are an expert software engineer. Fix the issues identified in the review feedback.

INSTRUCTIONS:
- Address each point in the review feedback
- Make targeted fixes using the available tools
- Test your changes by reading files back
- Ensure the fixes are complete and correct
- Maintain code quality and consistency

${contextSummary ? `CONTEXT:\n${smartTruncate(contextSummary, 400)}\n\n` : ''}

Use the same tools as before to implement fixes.`;

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review feedback to address: ${state.reviewFeedback}

Current files: ${Object.keys(state.generatedFiles).join(', ')}

Please fix the identified issues.`),
  ];

  // Use model-specific LLM if provided, otherwise use global llmWithTools
  const llmToUse = model ? createLLM(model) : llm;
  const llmWithToolsToUse = model ? llmToUse.bindTools(tools) : llmWithTools;
  const response = await llmWithToolsToUse.invoke(messages);

  // Extract fixed files from tool calls or response content
  const generatedFiles: Record<string, string> = {};

  if (response.tool_calls && response.tool_calls.length > 0) {
    for (const toolCall of response.tool_calls) {
      console.log(`🔧 Tool called: ${toolCall.name}`, toolCall.args);
      if (toolCall.name === 'write_file' || toolCall.name === 'append_to_file') {
        try {
          const args = toolCall.args as any;
          if (args.filePath && args.content) {
            generatedFiles[args.filePath] = args.content;
          }
        } catch (error) {
          console.warn('Could not parse tool call arguments:', error);
        }
      }
    }
  } else {
    // Fallback: parse files from response content
    const fixedFiles = parseGeneratedFiles(response.content.toString());
    Object.assign(generatedFiles, fixedFiles);
  }

  // Add to memory
  await memory.addMessage('assistant', `Fixed issues based on review feedback. Updated ${Object.keys(generatedFiles).length} files.`);

  // Emit fixes
  if (Object.keys(generatedFiles).length > 0) {
    const files = Object.keys(generatedFiles);
    console.log(`🔧 Real-time Fixes Applied: ${files.join(', ')}`);
    emitEvent(sessionId || '', {
      type: 'files_fixed',
      files: files,
    });
  }

  return {
    generatedFiles,
    currentIteration: 0, // Reset to re-run all steps with fixes
    messages: [new AIMessage(`Applied fixes for review feedback. ${Object.keys(generatedFiles).length} files updated.`)],
  };
}

// Helper function to determine if we should continue the workflow
export function shouldContinue(state: AgentStateType): string {
  // Defensive logging to help debug branch routing issues
  try {
    const planLen = Array.isArray(state.plan) ? state.plan.length : 0;
    const currentIt = typeof state.currentIteration === 'number' ? state.currentIteration : 0;
    const reviewIter = typeof state.reviewIterations === 'number' ? state.reviewIterations : 0;
    const feedback = state.reviewFeedback || '';

    console.log('shouldContinue check', {
      isComplete: state.isComplete,
      planLength: planLen,
      currentIteration: currentIt,
      hasReviewFeedback: !!feedback,
      reviewIterations: reviewIter,
    });

    // If marked complete, we're done
    if (state.isComplete) {
      console.log('shouldContinue -> end (isComplete)');
      return 'end';
    }

    // Start with planning if no plan exists
    if (planLen === 0) {
      console.log('shouldContinue -> planner (no plan)');
      return 'planner';
    }

    // If we haven't finished all steps, continue generating
    if (currentIt < planLen) {
      console.log('shouldContinue -> generator (still steps left)');
      return 'generator';
    }

    // All steps completed, need review
    if (!feedback) {
      console.log('shouldContinue -> reviewer (awaiting review)');
      return 'reviewer';
    }

    // Review feedback exists - check if approved
    const up = feedback.toUpperCase();
    const isApproved = up.includes('APPROVED') && !feedback.toLowerCase().includes('missing') && !feedback.toLowerCase().includes('not implemented');

    if (isApproved) {
      // Approved - we're done!
      console.log('shouldContinue -> end (approved)');
      return 'end';
    }

    // Not approved - check if we can retry
    if (reviewIter >= 3) {
      // Max iterations reached, force end
      console.log('⚠️  Max review iterations reached in router, ending');
      return 'end';
    }

    // Not approved and can retry - go back to executor to fix issues
    console.log(`🔄 Review not approved (iteration ${reviewIter}), retrying executor to fix issues`);
    return 'fix_issues';
  } catch (err) {
    console.error('Error in shouldContinue:', err);
    // Safe fallback
    return 'end';
  }
}