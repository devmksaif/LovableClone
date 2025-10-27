import { NextRequest, NextResponse } from 'next/server';
import { createStreamingLovableAgentGraph, saveGeneratedFiles, setEmitFunction, getToolCallSummary, clearToolCallLogs } from '../../../lib/agents/agent-core';
import { setSessionMemory, getProjectFolder } from '../../../lib/agents/utils';
import { getSessionMemory } from '../../../lib/utils/memory-db';
import { getOrCreateSession, addConversation } from '../../../lib/db/database';
import { HumanMessage } from '@langchain/core/messages';
import * as path from 'path';

// Store for ongoing streams
const activeStreams = new Map();

export async function POST(request: NextRequest) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      try {
        const { userRequest, sessionId, model } = await request.json();

        if (!userRequest) {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ error: 'userRequest is required' })}\n\n`));
          controller.close();
          return;
        }

        if (sessionId) {
          activeStreams.set(sessionId, { controller, isComplete: false });
          // Set the emit function for this session
          setEmitFunction(emitStreamEvent);
        }

        console.log('🚀 Starting agent generation for request:', userRequest);

        // Initialize session memory and create project folder
        setSessionMemory(sessionId || 'default');
        const projectFolder = getProjectFolder();
        
        // Ensure session exists in database before adding messages
        await getOrCreateSession(sessionId || 'default', projectFolder);
        
        const memory = getSessionMemory(sessionId || 'default', projectFolder);
        
        console.log('📁 Project folder:', projectFolder);

        // Save user message to database
        await addConversation(sessionId, 'user', userRequest);

        // Add user message to memory
        await memory.addMessage('user', userRequest);

        // Get conversation context for the agent
        const contextSummary = await memory.getContextSummary();

        console.log('💭 Context from memory:', contextSummary ? 'Available' : 'None');

        // Create the streaming agent graph with context
        const graph = createStreamingLovableAgentGraph(sessionId, model);

        // Run the agent workflow with context
        const result = await graph.invoke({
          userRequest: contextSummary ? `${contextSummary}\n\nNew request: ${userRequest}` : userRequest,
          messages: [new HumanMessage(contextSummary ? `${contextSummary}\n\n${userRequest}` : userRequest)],
        });

        console.log('\n✅ Generation complete!');

        // Extract chain of thought from messages
        const chainOfThought: string[] = [];
        result.messages.forEach((message, index) => {
          if (message.content.toString().includes('Chain of Thought:')) {
            const cotMatch = message.content.toString().match(/Chain of Thought:\s*([\s\S]*?)(?=Files:|FILENAME:|$)/i);
            if (cotMatch) {
              chainOfThought.push(`Step ${Math.floor(index / 2) + 1}: ${cotMatch[1].trim()}`);
            }
          }
        });

        // Save generated files and track in memory
        if (Object.keys(result.generatedFiles).length > 0) {
          saveGeneratedFiles(result.generatedFiles);

          // Track file operations in memory
          for (const filename of Object.keys(result.generatedFiles)) {
            await memory.addFileOperation('created', path.join(projectFolder, filename));
          }
        }

        // Get tool call statistics
        const toolStats = getToolCallSummary();
        console.log('\n' + toolStats);

        const response = {
          success: true,
          plan: result.plan,
          generatedFiles: Object.keys(result.generatedFiles),
          projectFolder: projectFolder,
          chainOfThought,
          reviewFeedback: result.reviewFeedback,
          isComplete: result.isComplete,
          toolStats: toolStats,
          type: 'complete'
        };

        // Add AI response to memory (summarized)
        const aiSummary = `Generated ${Object.keys(result.generatedFiles).length} files following ${result.plan?.length || 0} steps. ${result.reviewFeedback || ''}`;

        // Save AI response to database
        await addConversation(sessionId, 'assistant', aiSummary);

        await memory.addMessage('assistant', aiSummary);

        controller.enqueue(encoder.encode(`data: ${JSON.stringify(response)}\n\n`));
        controller.close();
        
        // Clear tool logs for next request
        clearToolCallLogs();

        if (sessionId) {
          const streamData = activeStreams.get(sessionId);
          if (streamData) {
            streamData.isComplete = true;
            activeStreams.delete(sessionId);
          }
        }

      } catch (error) {
        console.error('Error:', error);
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({
          error: 'Failed to process request',
          details: error instanceof Error ? error.message : String(error),
          type: 'error'
        })}\n\n`));
        controller.close();
      }
    }
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
    },
  });
}

// Function to emit streaming events
function emitStreamEvent(sessionId: string, data: any) {
  const streamData = activeStreams.get(sessionId);
  if (streamData && !streamData.isComplete) {
    const encoder = new TextEncoder();
    streamData.controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
  }
}
