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

// Helper function to get comprehensive tool list for prompts
function getToolDefinitions(): string {
  return `
AVAILABLE TOOLS:
- read_file: Read the contents of a file. Use this to examine existing code or documents. Parameters: { filePath: string }
- write_file: Create new files or replace entire files. Parameters: { filePath: string, content: string }
- append_to_file: Add content to the end of an existing file. Parameters: { filePath: string, content: string }
- delete_file: Delete a file from the filesystem. Parameters: { filePath: string }
- list_directory: List the contents of a directory. Use this to see what files are available. Parameters: { dirPath: string }
- search_files: Search for files containing a regex pattern. Use this to find specific code patterns or text. Parameters: { dirPath: string, pattern: string }
- replace_in_file: Find and replace text in a file using regex. Use this for refactoring or fixing code patterns. Parameters: { filePath: string, searchText: string, replaceText: string }
- insert_at_line: Insert content at a specific line number in a file. Use this for precise code additions. Parameters: { filePath: string, lineNumber: number, content: string }
- delete_lines: Delete a range of lines from a file. Use this to remove code blocks. Parameters: { filePath: string, startLine: number, endLine: number }
- replace_block: Replace a block of code between two markers. More efficient than rewriting entire file. Perfect for updating functions, classes, or sections. Parameters: { filePath: string, startMarker: string, endMarker: string, newContent: string }
- replace_line_range: Replace a specific range of lines with new content. More precise than replace_block. Use when you know exact line numbers. Parameters: { filePath: string, startLine: number, endLine: number, newContent: string }
- read_lines: Read a specific range of lines from a file. Use this to examine specific code sections. Parameters: { filePath: string, startLine: number, endLine: number }
- get_file_info: Get detailed information about a file (size, lines, dates, etc.). Use this to understand file structure. Parameters: { filePath: string }
- create_directory: Create a new directory (including parent directories if needed). Use this to organize project structure. Parameters: { dirPath: string }
- copy_file: Copy a file to a new location. Use this to duplicate files or create templates. Parameters: { sourcePath: string, destinationPath: string }
- move_file: Move or rename a file. Use this to reorganize project structure. Parameters: { sourcePath: string, destinationPath: string }
- get_project_structure: Get a tree view of the project directory structure. Use this to understand project organization. Parameters: { maxDepth?: number }
- execute_command: Execute a shell command in the project directory. Use this for npm install, git operations, building, testing, etc. ALWAYS provide a clear description. Parameters: { command: string, description: string }
- search_similar_code: Search for similar code examples in the vector database. Use this to find relevant code patterns and implementations. Parameters: { query: string, maxResults?: number }
- get_project_context: Get comprehensive project statistics and structure information from the vector database. Parameters: {}

TOOL USAGE GUIDELINES:
- Use tools by calling them directly in your response
- Each tool call should be a separate function call with proper JSON arguments
- Tools will automatically execute and provide results
- Format: Call tools like normal function calls with the tool name and arguments
- Example: write_file({ "filePath": "index.html", "content": "<html>...</html>" })
- Always read files first to understand current state before making changes
- Use search_files to find existing code patterns before implementing new ones
- Test your changes by reading files back to verify correctness
- Use execute_command for npm, git, build, and test operations`;
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

${getToolDefinitions()}

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
  const stream = await llmToUse.stream(messages);

  let planText = '';
  let chainOfThought = '';
  const cotMessages: AIMessage[] = []; // Collect COT messages for chat

  // Process the streaming response
  for await (const chunk of stream) {
    const chunkContent = chunk.content;
    if (chunkContent) {
      planText += chunkContent;

      // Extract chain of thought from the accumulating content
      const cotMatch = planText.match(/Chain of Thought:\s*([\s\S]*?)(?=\d+\.|$)/i);
      if (cotMatch) {
        const newCot = cotMatch[1].trim();
        if (newCot !== chainOfThought) {
          const previousLength = chainOfThought.length;
          chainOfThought = newCot;

          // Emit real-time chain of thought updates
          const newReasoning = chainOfThought.substring(previousLength);
          if (newReasoning.trim()) {
            console.log(`🔍 Real-time Planner COT: ${newReasoning.substring(0, 100)}${newReasoning.length > 100 ? '...' : ''}`);
            
            // Add to chat messages immediately for real-time display
            cotMessages.push(new AIMessage(`🔍 ${newReasoning.trim()}`));
            
            emitEvent(sessionId || '', {
              type: 'chain_of_thought',
              step: 'planner',
              reasoning: chainOfThought.length > 500 ? chainOfThought.substring(0, 500) + '...' : chainOfThought,
              isPartial: true,
            });
          }
        }
      }
    }
  }

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

  // Emit real-time messages for chat display
  if (cotMessages.length > 0) {
    cotMessages.forEach((message) => {
      emitEvent(sessionId || '', {
        type: 'agent_message',
        content: message.content.toString(),
        timestamp: new Date().toISOString(),
      });
    });
  }

  return {
    plan: planSteps,
    messages: cotMessages.length > 0 ? cotMessages : (planText ? [new AIMessage(`Planning: ${planText.substring(0, 500)}${planText.length > 500 ? '...' : ''}`)] : []), // Include real-time planning reasoning in chat
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

${getToolDefinitions()}

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
  const llmToUse = model ? createLLM(model, true) : createLLM(undefined, true); // Enable streaming
  const llmWithToolsToUse = model ? llmToUse.bindTools(tools) : llmWithTools;

  // Stream the response for real-time chain of thought
  const stream = await llmWithToolsToUse.stream(messages);

  // Extract generated files from tool calls or response content
  const generatedFiles: Record<string, string> = {};
  let chainOfThought = '';
  let fullContent = '';
  let currentCotChunk = '';
  const cotMessages: AIMessage[] = []; // Collect COT messages for chat

  // Process the streaming response
  for await (const chunk of stream) {
    const chunkContent = chunk.content;
    if (chunkContent) {
      fullContent += chunkContent;
      currentCotChunk += chunkContent;

      // Extract chain of thought from the accumulating content
      const cotMatch = fullContent.match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
      if (cotMatch) {
        const newCot = cotMatch[1].trim();
        if (newCot !== chainOfThought) {
          const previousLength = chainOfThought.length;
          chainOfThought = newCot;

          // Emit real-time chain of thought updates (truncated like Gemini)
          const newReasoning = chainOfThought.substring(previousLength);
          if (newReasoning.trim()) {
            console.log(`🔍 Real-time COT Step ${currentStep + 1}: ${newReasoning.substring(0, 100)}${newReasoning.length > 100 ? '...' : ''}`);
            
            // Add to chat messages immediately for real-time display
            cotMessages.push(new AIMessage(`🔍 ${newReasoning.trim()}`));
            
            emitEvent(sessionId || '', {
              type: 'chain_of_thought',
              step: currentStep + 1,
              reasoning: chainOfThought.length > 500 ? chainOfThought.substring(0, 500) + '...' : chainOfThought,
              isPartial: true, // Indicate this is a streaming update
            });
          }
        }
      }
    }

    // Handle tool calls in streaming (if any)
    if (chunk.tool_calls && chunk.tool_calls.length > 0) {
      for (const toolCall of chunk.tool_calls) {
        console.log(`🔧 Tool called: ${toolCall.name}`, toolCall.args);

        try {
          // Find the tool function
          const tool = tools.find(t => t.name === toolCall.name);
          if (tool) {
            // Execute the tool with logging wrapper
            const wrappedTool = wrapToolWithLogging(tool, toolCall.name);
            const result = await wrappedTool(toolCall.args);
            console.log(`✅ Tool ${toolCall.name} executed successfully:`, result);

            // Handle specific tool results
            if (toolCall.name === 'read_file') {
              // Store read file content for later use
              const args = toolCall.args as any;
              if (args.filePath && typeof result === 'string') {
                generatedFiles[args.filePath] = result;
              }
            } else if (toolCall.name === 'write_file' || toolCall.name === 'append_to_file') {
              // Extract file content from tool call args for generated files
              const args = toolCall.args as any;
              if (args.filePath && args.content) {
                generatedFiles[args.filePath] = args.content;
              }
            }
          } else {
            console.warn(`⚠️ Tool ${toolCall.name} not found in tools array`);
          }
        } catch (error) {
          console.error(`❌ Tool ${toolCall.name} execution failed:`, error);
          // Continue processing other tools even if one fails
        }
      }
    }
  }

  // Final processing after streaming is complete
  console.log(`📊 Processed streaming response`);

  // Extract final chain of thought
  const finalCotMatch = fullContent.match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
  if (finalCotMatch) {
    chainOfThought = finalCotMatch[1].trim();
  }

  // Fallback: parse files from accumulated content if no tool calls generated files
  if (Object.keys(generatedFiles).length === 0) {
    const newFiles = parseGeneratedFiles(fullContent);
    Object.assign(generatedFiles, newFiles);
  }

  // Add to memory
  await memory.addMessage('assistant', `Step ${currentStep + 1}: ${chainOfThought.substring(0, 200)}...`);

  // Emit final chain of thought (complete)
  if (chainOfThought) {
    emitEvent(sessionId || '', {
      type: 'chain_of_thought',
      step: currentStep + 1,
      reasoning: chainOfThought.length > 1000 ? chainOfThought.substring(0, 1000) + '...' : chainOfThought,
      isPartial: false, // This is the final complete reasoning
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

  // Emit real-time messages for chat display
  if (cotMessages.length > 0) {
    cotMessages.forEach((message) => {
      emitEvent(sessionId || '', {
        type: 'agent_message',
        content: message.content.toString(),
        timestamp: new Date().toISOString(),
      });
    });
  }

  return {
    generatedFiles,
    currentIteration: currentStep + 1,
    messages: cotMessages.length > 0 ? cotMessages : (chainOfThought ? [new AIMessage(chainOfThought)] : []), // Include real-time Chain of Thought messages in chat
  };
}

// Streaming Reviewer Agent: Reviews the generated code for quality and completeness
export async function streamingReviewerAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Reviewing generated code...' });

  const memory = getMemory();
  const allFiles = { ...state.generatedFiles };

  // Read current state of all files using tools
  const projectFolder = getProjectFolder();

  // Use tools to read the actual file contents
  for (const filePath of Object.keys(allFiles)) {
    try {
      // Try to read the file using the read_file tool
      const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);

      // Import the tool and call it directly
      const { readFileTool } = await import('./tools');
      const result = await readFileTool.invoke({ filePath: fullPath });

      if (result && typeof result === 'string' && result.startsWith('File content:')) {
        // Extract the actual content from the tool response
        allFiles[filePath] = result.replace('File content:\n', '');
      } else {
        console.warn(`Could not read file ${filePath} using tool; using in-memory content`);
      }
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

${getToolDefinitions()}

OUTPUT FORMAT:
Chain of Thought: [Your step-by-step analysis]
APPROVED or NEEDS IMPROVEMENT

If NEEDS IMPROVEMENT, provide specific, actionable feedback.
If APPROVED, confirm the implementation is complete and ready.

Be constructive and specific in your feedback.`;

  const codeSummary = Object.entries(allFiles)
    .map(([file, content]) => `=== ${file} ===\n${content}`)
    .join('\n\n');

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review the following generated code:\n\n${codeSummary}`),
  ];

  // Use model-specific LLM if provided, otherwise use global llmWithTools
  const llmToUse = model ? createLLM(model, true) : createLLM(undefined, true); // Enable streaming
  const llmWithToolsToUse = model ? llmToUse.bindTools(tools) : llmWithTools;

  // Stream the response for real-time chain of thought
  const stream = await llmWithToolsToUse.stream(messages);

  let chainOfThought = '';
  let fullContent = '';
  let reviewResult = '';
  const cotMessages: AIMessage[] = []; // Collect COT messages for chat

  // Process the streaming response
  for await (const chunk of stream) {
    const chunkContent = chunk.content;
    if (chunkContent) {
      fullContent += chunkContent;

      // Extract chain of thought from the accumulating content
      const cotMatch = fullContent.match(/Chain of Thought:\s*([\s\S]*?)(?=APPROVED|NEEDS IMPROVEMENT|$)/i);
      if (cotMatch) {
        const newCot = cotMatch[1].trim();
        if (newCot !== chainOfThought) {
          const previousLength = chainOfThought.length;
          chainOfThought = newCot;

          // Emit real-time chain of thought updates
          const newReasoning = chainOfThought.substring(previousLength);
          if (newReasoning.trim()) {
            console.log(`🔍 Real-time COT (Review): ${newReasoning.substring(0, 100)}${newReasoning.length > 100 ? '...' : ''}`);

            // Add to chat messages immediately for real-time display
            cotMessages.push(new AIMessage(`🔍 ${newReasoning.trim()}`));

            emitEvent(sessionId || '', {
              type: 'chain_of_thought',
              step: 'review',
              reasoning: chainOfThought.length > 500 ? chainOfThought.substring(0, 500) + '...' : chainOfThought,
              isPartial: true, // Indicate this is a streaming update
            });
          }
        }
      }

      // Check for final result
      if (fullContent.includes('APPROVED') || fullContent.includes('NEEDS IMPROVEMENT')) {
        reviewResult = fullContent;
        break; // We have the complete review
      }
    }
  }

  // Extract the final feedback from the complete response
  const feedback = reviewResult || fullContent;

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
    messages: cotMessages, // Include COT messages in chat
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

${getToolDefinitions()}

Use the same tools as before to implement fixes.`;

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Review feedback to address: ${state.reviewFeedback}

Current files: ${Object.keys(state.generatedFiles).join(', ')}

Please fix the identified issues.`),
  ];

  // Use model-specific LLM if provided, otherwise use global llmWithTools
  const llmToUse = model ? createLLM(model, true) : createLLM(undefined, true); // Enable streaming
  const llmWithToolsToUse = model ? llmToUse.bindTools(tools) : llmWithTools;

  // Stream the response for real-time chain of thought
  const stream = await llmWithToolsToUse.stream(messages);

  // Extract fixed files from tool calls or response content
  const generatedFiles: Record<string, string> = {};
  let fullContent = '';
  let chainOfThought = '';
  const cotMessages: AIMessage[] = []; // Collect COT messages for chat

  // Process the streaming response
  for await (const chunk of stream) {
    const chunkContent = chunk.content;
    if (chunkContent) {
      fullContent += chunkContent;

      // Extract chain of thought from the accumulating content
      const cotMatch = fullContent.match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
      if (cotMatch) {
        const newCot = cotMatch[1].trim();
        if (newCot !== chainOfThought) {
          const previousLength = chainOfThought.length;
          chainOfThought = newCot;

          // Emit real-time chain of thought updates
          const newReasoning = chainOfThought.substring(previousLength);
          if (newReasoning.trim()) {
            console.log(`🔍 Real-time Fixer COT: ${newReasoning.substring(0, 100)}${newReasoning.length > 100 ? '...' : ''}`);
            
            // Add to chat messages immediately for real-time display
            cotMessages.push(new AIMessage(`🔍 ${newReasoning.trim()}`));
            
            emitEvent(sessionId || '', {
              type: 'chain_of_thought',
              step: 'fixer',
              reasoning: chainOfThought.length > 500 ? chainOfThought.substring(0, 500) + '...' : chainOfThought,
              isPartial: true,
            });
          }
        }
      }
    }

    // Handle tool calls in streaming (if any)
    if (chunk.tool_calls && chunk.tool_calls.length > 0) {
      for (const toolCall of chunk.tool_calls) {
        console.log(`🔧 Tool called: ${toolCall.name}`, toolCall.args);

        try {
          // Find the tool function
          const tool = tools.find(t => t.name === toolCall.name);
          if (tool) {
            // Execute the tool with logging wrapper
            const wrappedTool = wrapToolWithLogging(tool, toolCall.name);
            const result = await wrappedTool(toolCall.args);
            console.log(`✅ Tool ${toolCall.name} executed successfully:`, result);

            // Handle specific tool results
            if (toolCall.name === 'read_file') {
              // Store read file content for later use
              const args = toolCall.args as any;
              if (args.filePath && typeof result === 'string') {
                generatedFiles[args.filePath] = result;
              }
            } else if (toolCall.name === 'write_file' || toolCall.name === 'append_to_file') {
              // Extract file content from tool call args for generated files
              const args = toolCall.args as any;
              if (args.filePath && args.content) {
                generatedFiles[args.filePath] = args.content;
              }
            }
          } else {
            console.warn(`⚠️ Tool ${toolCall.name} not found in tools array`);
          }
        } catch (error) {
          console.error(`❌ Tool ${toolCall.name} execution failed:`, error);
          // Continue processing other tools even if one fails
        }
      }
    }
  }

  // Final processing after streaming is complete
  console.log(`📊 Processed streaming fixer response`);

  // Fallback: parse files from accumulated content if no tool calls generated files
  if (Object.keys(generatedFiles).length === 0) {
    const fixedFiles = parseGeneratedFiles(fullContent);
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

  // Emit real-time messages for chat display
  if (cotMessages.length > 0) {
    cotMessages.forEach((message) => {
      emitEvent(sessionId || '', {
        type: 'agent_message',
        content: message.content.toString(),
        timestamp: new Date().toISOString(),
      });
    });
  }

  return {
    generatedFiles,
    currentIteration: state.plan.length, // Keep at plan length
    reviewFeedback: '', // Clear feedback so shouldContinue goes to completion check
    messages: cotMessages.length > 0 ? cotMessages : (fullContent ? [new AIMessage(`Fixing issues: ${fullContent.substring(0, 500)}${fullContent.length > 500 ? '...' : ''}`)] : []), // Include real-time fix reasoning in chat
  };
}

// Streaming Completion Agent: Ensures generated code is complete and functional
export async function streamingCompletionAgent(state: AgentStateType, sessionId?: string, model?: string): Promise<Partial<AgentStateType>> {
  emitEvent(sessionId || '', { type: 'status', message: 'Ensuring code completeness...' });

  const memory = getMemory();
  const allFiles = { ...state.generatedFiles };

  // Read current state of all files
  const sessionFiles = await memory.getSessionFiles();
  for (const filePath of Object.keys(allFiles)) {
    try {
      const fs = await import('fs');
      const projectFolder = getProjectFolder();

      // Try to read the actual file content
      const candidate = path.isAbsolute(filePath) ? filePath : path.join(projectFolder, filePath);
      if (fs.existsSync(candidate)) {
        allFiles[filePath] = fs.readFileSync(candidate, 'utf-8');
        continue;
      }

      // Try to find by basename in session files
      const base = path.basename(filePath);
      const match = sessionFiles.find(f => path.basename(f) === base);
      if (match && fs.existsSync(match)) {
        allFiles[filePath] = fs.readFileSync(match, 'utf-8');
        continue;
      }
    } catch (error) {
      console.warn(`Could not read file ${filePath} for completion check:`, error);
    }
  }

  const systemPrompt = `You are an expert software engineer specializing in code completion and validation. Your task is to ensure the generated code is COMPLETE and FUNCTIONAL.

COMPLETENESS CHECKS:
1. **Function Definitions**: All functions must have complete implementations (not just signatures)
2. **Imports & Dependencies**: All required imports must be present
3. **Class Methods**: All class methods must be implemented
4. **Error Handling**: Basic error handling where appropriate
5. **Return Statements**: Functions that should return values must do so
6. **Variable Declarations**: All variables must be properly declared
7. **Syntax Validation**: Code must be syntactically correct
8. **Integration Points**: Code must properly integrate with existing codebase

${getToolDefinitions()}

OUTPUT FORMAT:
Chain of Thought: [Your analysis of what's missing/incomplete]
Completion Status: COMPLETE or INCOMPLETE

If INCOMPLETE, provide specific fixes using the available tools.
If COMPLETE, confirm the code is ready for review.

Be thorough - incomplete code is worse than no code!`;

  const codeSummary = Object.entries(allFiles)
    .map(([file, content]) => `=== ${file} ===\n${content}`)
    .join('\n\n');

  const messages = [
    new SystemMessage(systemPrompt),
    new HumanMessage(`Analyze and complete the following generated code:\n\n${codeSummary}

Ensure all implementations are complete and functional. Fix any missing parts, incomplete functions, or integration issues.`),
  ];

  // Use model-specific LLM if provided, otherwise use global llmWithTools
  const llmToUse = model ? createLLM(model, true) : createLLM(undefined, true);
  const llmWithToolsToUse = model ? llmToUse.bindTools(tools) : llmWithTools;

  // Stream the response for real-time updates
  const stream = await llmWithToolsToUse.stream(messages);

  // Extract completed files from tool calls or response content
  const completedFiles: Record<string, string> = {};
  let chainOfThought = '';
  let fullContent = '';
  let completionStatus = 'INCOMPLETE';
  const cotMessages: AIMessage[] = []; // Collect COT messages for chat

  // Process the streaming response
  for await (const chunk of stream) {
    const chunkContent = chunk.content;
    if (chunkContent) {
      fullContent += chunkContent;

      // Extract completion status
      const statusMatch = fullContent.match(/Completion Status:\s*(COMPLETE|INCOMPLETE)/i);
      if (statusMatch) {
        completionStatus = statusMatch[1].toUpperCase();
      }

      // Extract chain of thought from the accumulating content
      const cotMatch = fullContent.match(/Chain of Thought:\s*([\s\S]*?)(?=Completion Status:|$)/i);
      if (cotMatch) {
        const newCot = cotMatch[1].trim();
        if (newCot !== chainOfThought) {
          const previousLength = chainOfThought.length;
          chainOfThought = newCot;

          // Emit real-time chain of thought updates
          const newReasoning = chainOfThought.substring(previousLength);
          if (newReasoning.trim()) {
            console.log(`🔍 Real-time Completion COT: ${newReasoning.substring(0, 100)}${newReasoning.length > 100 ? '...' : ''}`);
            
            // Add to chat messages immediately for real-time display
            cotMessages.push(new AIMessage(`🔍 ${newReasoning.trim()}`));
            
            emitEvent(sessionId || '', {
              type: 'chain_of_thought',
              step: 'completion',
              reasoning: chainOfThought.length > 500 ? chainOfThought.substring(0, 500) + '...' : chainOfThought,
              isPartial: true,
            });
          }
        }
      }
    }

    // Handle tool calls in streaming
    if (chunk.tool_calls && chunk.tool_calls.length > 0) {
      for (const toolCall of chunk.tool_calls) {
        console.log(`🔧 Completion Tool called: ${toolCall.name}`, toolCall.args);

        try {
          const tool = tools.find(t => t.name === toolCall.name);
          if (tool) {
            const wrappedTool = wrapToolWithLogging(tool, toolCall.name);
            const result = await wrappedTool(toolCall.args);
            console.log(`✅ Completion Tool ${toolCall.name} executed successfully:`, result);

            // Handle specific tool results
            if (toolCall.name === 'read_file') {
              const args = toolCall.args as any;
              if (args.filePath && typeof result === 'string') {
                completedFiles[args.filePath] = result;
              }
            } else if (toolCall.name === 'write_file' || toolCall.name === 'append_to_file') {
              const args = toolCall.args as any;
              if (args.filePath && args.content) {
                completedFiles[args.filePath] = args.content;
              }
            }
          } else {
            console.warn(`⚠️ Completion Tool ${toolCall.name} not found`);
          }
        } catch (error) {
          console.error(`❌ Completion Tool ${toolCall.name} execution failed:`, error);
        }
      }
    }
  }

  // Final processing
  console.log(`📊 Completion check result: ${completionStatus}`);

  // Fallback: parse files from content if no tool calls
  if (Object.keys(completedFiles).length === 0) {
    const newFiles = parseGeneratedFiles(fullContent);
    Object.assign(completedFiles, newFiles);
  }

  // Add to memory
  await memory.addMessage('assistant', `Completion check: ${completionStatus}. ${chainOfThought.substring(0, 200)}...`);

  // Emit completion results
  emitEvent(sessionId || '', {
    type: 'completion_check',
    status: completionStatus,
    reasoning: chainOfThought,
    filesCompleted: Object.keys(completedFiles)
  });

  if (completionStatus === 'COMPLETE') {
    emitEvent(sessionId || '', { type: 'status', message: 'Code completion verified - proceeding to review...' });
  }

  // Emit real-time messages for chat display
  if (cotMessages.length > 0) {
    cotMessages.forEach((message) => {
      emitEvent(sessionId || '', {
        type: 'agent_message',
        content: message.content.toString(),
        timestamp: new Date().toISOString(),
      });
    });
  }

  return {
    generatedFiles: completedFiles,
    messages: cotMessages.length > 0 ? cotMessages : (chainOfThought ? [new AIMessage(`Completion Analysis: ${chainOfThought}`)] : []), // Include real-time completion reasoning in chat
  };
}
 

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

    // Defensive guard: if we've looped through reviews too many times, stop to avoid
    // LangGraph recursion/looping issues. Emit an event for diagnostics.
    if (reviewIter >= 10) {
      console.warn(`⚠️ Excessive review iterations (${reviewIter}), forcing end to avoid recursion`);
      try {
        emitEvent && emitEvent('', {
          type: 'diagnostic',
          message: `Exceeded review iteration limit (${reviewIter}), ending workflow to prevent infinite loop.`,
        });
      } catch (e) {
        // ignore
      }
      return 'end';
    }

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

    // All steps completed - if no review feedback yet, go to completion check
    // But if we're already in completion and have no feedback, we need to proceed to review
    // This handles the case where completion agent found issues and we need to review
    if (!feedback) {
      // Check if we've been through completion already by looking at currentIteration
      // If currentIteration equals plan length, we've completed generation
      // If we have generatedFiles but no feedback, we should go to reviewer
      const hasGeneratedFiles = Object.keys(state.generatedFiles || {}).length > 0;
      if (hasGeneratedFiles && currentIt >= planLen) {
        console.log('shouldContinue -> reviewer (generation complete, ready for review)');
        return 'reviewer';
      } else {
        console.log('shouldContinue -> completion (all steps done, checking completeness)');
        return 'completion';
      }
    }

    // If we have review feedback but are still in completion node, go to reviewer
    // This handles the case where completion agent provided feedback and we need review
    if (feedback && currentIt >= planLen) {
      console.log('shouldContinue -> reviewer (completion done, proceeding to review)');
      return 'reviewer';
    }

    // Review feedback exists - check if approved
    const up = feedback.toUpperCase();
    const isApproved = up.includes('APPROVED') &&
                       !feedback.toLowerCase().includes('missing') &&
                       !feedback.toLowerCase().includes('not implemented');

    if (isApproved) {
      // Approved - we're done!
      console.log('shouldContinue -> end (approved)');
      return 'end';
    }

    // Not approved - check if we can retry
    if (reviewIter >= 3) {
      // Max iterations reached, force end
      console.log('⚠️ Max review iterations reached, ending');
      return 'end';
    }

    // Not approved and can retry - go to fix_issues
    console.log(`🔄 Review not approved (iteration ${reviewIter}), going to fix_issues`);
    return 'fix_issues';

  } catch (err) {
    console.error('Error in shouldContinue:', err);
    // Safe fallback - end the workflow rather than crash
    return 'end';
  }
}