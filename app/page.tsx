'use client';

import { useState, useRef, useEffect } from 'react';
import { ChatSidebar } from '../components/ChatSidebar';
import ModelSelector from '../components/ModelSelector';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface AgentResponse {
  success: boolean;
  plan: string[];
  generatedFiles: string[];
  chainOfThought: string[];
  reviewFeedback: string;
  isComplete: boolean;
  error?: string;
}

function Button({ children, type = 'button', disabled, onClick }: {
  children: React.ReactNode;
  type?: 'button' | 'submit';
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors`}
    >
      {children}
    </button>
  );
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white border border-gray-200 rounded-lg shadow-sm ${className}`}>
      {children}
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center py-4">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      <span className="ml-2 text-gray-600">Generating with real-time chain of thought...</span>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center space-x-1 p-4">
      <div className="flex space-x-1">
        <div className="h-2 w-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
        <div className="h-2 w-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
        <div className="h-2 w-2 bg-blue-400 rounded-full animate-bounce"></div>
      </div>
      <span className="text-sm text-blue-600 ml-2">Agent is thinking...</span>
    </div>
  );
}

function MessageList({ messages }: { messages: Message[] }) {
  return (
    <>
      {messages.map((message) => (
        <div
          key={message.id}
          className={`p-4 rounded-lg ${
            message.role === 'user'
              ? 'bg-blue-50 ml-12 border-l-4 border-blue-500'
              : 'bg-gray-50 mr-12 border-l-4 border-gray-500'
          }`}
        >
          {message.role === 'user' ? '👤 You:' : '🤖 Agent:'}
          <div className="mt-1 whitespace-pre-wrap">{message.content}</div>
          <div className="text-xs text-gray-500 mt-2">
            {message.timestamp.toLocaleTimeString()}
          </div>
        </div>
      ))}
    </>
  );
}

 
export default function HomePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [chainOfThought, setChainOfThought] = useState<string[]>([]);
  const [currentPlan, setCurrentPlan] = useState<string[]>([]);
  const [generatedFiles, setGeneratedFiles] = useState<string[]>([]);
  const [reviewFeedback, setReviewFeedback] = useState('');
  const [streamingAssistantId, setStreamingAssistantId] = useState<string | null>(null);
  const [projectFolder, setProjectFolder] = useState<string>('');

  // Model selection
  const [selectedModel, setSelectedModel] = useState<string>('gemini-2.5-flash');

  // Session management
  const [sessionId, setSessionId] = useState<string>(() =>
    `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  );
  const [currentProjectTitle, setCurrentProjectTitle] = useState<string>('New Project');

  // Sidebar state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSessionSelect = async (newSessionId: string) => {
    if (newSessionId === sessionId) return;

    try {
      // Load the session data
      const response = await fetch(`/api/sessions/${newSessionId}`);
      if (!response.ok) {
        throw new Error('Failed to load session');
      }

      const data = await response.json();
      const session = data.session;

      // Update state with loaded session
      setSessionId(newSessionId);
      setProjectFolder(session.projectFolder);

      // Convert conversations to messages format
      const loadedMessages: Message[] = session.conversations.map((conv: any) => ({
        id: conv.id,
        role: conv.role as 'user' | 'assistant',
        content: conv.content,
        timestamp: new Date(conv.timestamp),
      }));

      setMessages(loadedMessages);

      // Update project title
      if (session.projects.length > 0) {
        const latestProject = session.projects[0];
        setCurrentProjectTitle(latestProject.userRequest.length > 40
          ? latestProject.userRequest.substring(0, 40) + '...'
          : latestProject.userRequest
        );
      } else {
        setCurrentProjectTitle('New Project');
      }

      // Clear current state
      setChainOfThought([]);
      setCurrentPlan([]);
      setGeneratedFiles([]);
      setReviewFeedback('');
      setStreamingAssistantId(null);
      setIsLoading(false);

    } catch (error) {
      console.error('Failed to load session:', error);
      // Could show an error toast here
    }
  };

  const handleNewProject = async () => {
    // Generate a new session ID
    const newSessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    try {
      // Create new session in database
      const response = await fetch('/api/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          projectFolder: `project_${Date.now()}`,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create new session');
      }

      // Switch to the new session
      setSessionId(newSessionId);
      setMessages([]);
      setCurrentProjectTitle('New Project');
      setProjectFolder(`project_${Date.now()}`);
      setChainOfThought([]);
      setCurrentPlan([]);
      setGeneratedFiles([]);
      setReviewFeedback('');
      setStreamingAssistantId(null);
      setIsLoading(false);

    } catch (error) {
      console.error('Failed to create new project:', error);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMessage.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: currentMessage,
      timestamp: new Date(),
    };

    // Create initial assistant message that will be updated with chain of thought
    const assistantMessageId = (Date.now() + 1).toString();
    const initialAssistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage, initialAssistantMessage]);
    setStreamingAssistantId(assistantMessageId);
    setCurrentMessage('');
    setIsLoading(true);
    setChainOfThought([]);
    setCurrentPlan([]);
    setGeneratedFiles([]);
    setReviewFeedback('');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          userRequest: userMessage.content,
          sessionId,
          model: selectedModel,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body reader');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let cotSteps: string[] = [];

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');

        // Process complete messages
        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'complete') {
                // Handle final completion
                const agentContent = [
                  `📋 **Plan Created:**\n${data.plan.map((step: string, i: number) => `${i + 1}. ${step}`).join('\n')}`,
                  data.chainOfThought.length > 0 ? `🔍 **Chain of Thought:**\n${data.chainOfThought.join('\n\n---\n\n')}` : '',
                  data.generatedFiles.length > 0 ? `📁 **Generated Files:**\n${data.generatedFiles.map((filename: string) => `- ${filename}`).join('\n')}` : '',
                  data.reviewFeedback ? `✅ **Review:** ${data.reviewFeedback}` : '',
                ].filter(Boolean).join('\n\n');

                // Update the final assistant message
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantMessageId
                    ? { ...msg, content: agentContent }
                    : msg
                ));

                setChainOfThought(data.chainOfThought);
                setCurrentPlan(data.plan);
                setGeneratedFiles(data.generatedFiles);
                setReviewFeedback(data.reviewFeedback);
                setProjectFolder(data.projectFolder || '');
                setStreamingAssistantId(null);
                setIsLoading(false);
                reader.releaseLock();
                return;
              } else {
                // Handle real-time updates and build in-chat chain of thought
                if (data.type === 'status') {
                  console.log('📊 Real-time Status:', data.message);
                  // Update assistant message with status
                  setMessages(prev => prev.map(msg =>
                    msg.id === assistantMessageId
                      ? { ...msg, content: `${msg.content}\n\n💭 ${data.message}`.trim() }
                      : msg
                  ));
                } else if (data.type === 'plan') {
                  setCurrentPlan(data.plan);
                  console.log('📋 Real-time Plan received:', data.plan.length, 'steps');
                } else if (data.type === 'chain_of_thought') {
                  cotSteps.push(`Step ${data.step}: ${data.reasoning}`);
                  setChainOfThought([...cotSteps]);

                  // Update assistant message with chain of thought
                  const cotContent = cotSteps.map(step =>
                    `🔍 **${step.split(':')[0]}**\n${step.split(':').slice(1).join(':').trim()}`
                  ).join('\n\n');

                  setMessages(prev => prev.map(msg =>
                    msg.id === assistantMessageId
                      ? { ...msg, content: cotContent }
                      : msg
                  ));

                  console.log('🔍 Real-time Chain of Thought - Step', data.step, ':', data.reasoning.substring(0, 100) + '...');
                } else if (data.type === 'files_generated') {
                  setGeneratedFiles((prev: string[]) => [...prev, ...data.files]);
                  console.log('📁 Real-time Files Generated:', data.files.join(', '));
                } else if (data.type === 'review') {
                  setReviewFeedback(data.feedback);
                  console.log('✅ Real-time Review:', data.feedback.substring(0, 100) + '...');
                }
              }
            } catch (parseError) {
              console.error('Failed to parse streaming data:', parseError);
            }
          }
        }

        buffer = lines[lines.length - 1];
      }

      // If we reach here, close the stream
      setStreamingAssistantId(null);
      setIsLoading(false);

    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `❌ Error: ${error instanceof Error ? error.message : 'Network error'}`,
        timestamp: new Date(),
      };

      if (streamingAssistantId) {
        // Replace the streaming message with the error
        setMessages(prev => prev.map(msg =>
          msg.id === streamingAssistantId ? errorMessage : msg
        ));
      } else {
        setMessages(prev => [...prev, errorMessage]);
      }

      setStreamingAssistantId(null);
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Chat Sidebar - Collapsible overlay */}
      <ChatSidebar
        currentSessionId={sessionId}
        onSessionSelect={handleSessionSelect}
        onNewProject={handleNewProject}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      {/* Main Content - Full Width */}
      <div className={`flex-1 flex flex-col min-w-0 transition-all duration-300 ${isSidebarCollapsed ? 'ml-12' : 'ml-0'}`}>
        {/* Chat Interface - Full Width */}
        <div className="flex-1 flex flex-col bg-white border border-gray-200 overflow-hidden">
          {/* Chat Header */}
          <div className="border-b border-gray-200 p-4 bg-gray-50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setIsSidebarCollapsed(false)}
                  className="p-2 hover:bg-gray-200 rounded-lg transition-colors"
                  title="Open sidebar"
                >
                  ☰
                </button>
                <div>
                  <h1 className="text-2xl font-semibold text-gray-800">
                    🤖 LangGraph Code Agent
                  </h1>
                  <p className="text-sm text-gray-600 mt-1">
                    Powered by OpenRouter AI • Real-time chain of thought reasoning
                  </p>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm font-medium text-gray-800">📁 Current Project:</div>
                <div className="text-xs text-gray-600 font-mono mt-1">{currentProjectTitle}</div>
                {projectFolder && (
                  <div className="text-xs text-gray-500 mt-1">Folder: {projectFolder}</div>
                )}
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center py-12">
                <div className="text-6xl mb-6">💬</div>
                <h2 className="text-2xl font-semibold text-gray-800 mb-2">How can I help you build today?</h2>
                <p className="text-gray-600 max-w-md">
                  Describe what you want to build and I'll generate the code for you with real-time reasoning.
                </p>
                <div className="mt-6 text-sm text-gray-500">
                  Example: "Create a TypeScript function that calculates factorial with unit tests"
                </div>
              </div>
            )}

            <div className="space-y-6">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                      message.role === 'user'
                        ? 'bg-blue-600 text-white ml-12'
                        : 'bg-gray-100 text-gray-800 mr-12'
                    }`}
                  >
                    <div className="whitespace-pre-wrap text-sm leading-relaxed">
                      {message.content}
                    </div>
                    <div className={`text-xs mt-2 ${
                      message.role === 'user' ? 'text-blue-100' : 'text-gray-500'
                    }`}>
                      {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-2xl px-4 py-3 mr-12">
                    <LoadingSpinner />
                  </div>
                </div>
              )}
            </div>
            <div ref={messagesEndRef} />
          </div>

          <div className="border-t border-gray-200 p-4">
            <form onSubmit={handleSubmit} className="flex items-end gap-3">
              <div className="flex-1">
                <ModelSelector
                  selectedModel={selectedModel}
                  onModelChange={setSelectedModel}
                  className="mb-3"
                />
                <div className="relative">
                  <textarea
                    value={currentMessage}
                    onChange={(e) => setCurrentMessage(e.target.value)}
                    placeholder="Describe what you want to build..."
                    className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none min-h-[44px] max-h-32"
                    disabled={isLoading}
                    rows={1}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSubmit(e);
                      }
                    }}
                  />
                  <button
                    type="submit"
                    disabled={isLoading || !currentMessage.trim()}
                    className="absolute right-2 top-2 p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                  >
                    {isLoading ? '⏳' : '🚀'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
