"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue, SelectLabel, SelectGroup } from '@/components/ui/select';
import { Loader2, Send, Copy, Check, FileText, Play, Eye, Square, Bot, User, ChevronDown, ChevronUp, Brain, ListChecks, FolderOpen, Zap, Settings, Clock, ArrowDown, RefreshCw, Filter } from 'lucide-react';
import { cn } from '@/lib/utils';
import ModelSelector from './ModelSelector';
import ApiKeySettings from './ApiKeySettings';
import { cotManager, getSessionStats } from '@/lib/utils/cot-manager';
import { chatLogger } from '@/lib/utils/chat-logger';
import { apiClient } from '@/lib/api-client';

interface EventItem {
  id: string;
  type: 'progress' | 'node_complete' | 'tool_usage' | 'file_operation' | 'code_stream' | 'other';
  content: string;
  timestamp: Date;
  data?: any;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  metadata?: {
    codeBlocks?: Array<{
      language: string;
      code: string;
      canApply?: boolean;
      filePath?: string;
    }>;
    suggestions?: string[];
    isHistory?: boolean;
    eventType?: string;
    progressData?: {
      overallProgress: number;
      currentStep: number;
      steps: Array<{
        id: string;
        label: string;
        status: 'pending' | 'running' | 'completed' | 'failed';
        startTime?: number;
        endTime?: number;
        progress?: number;
        message?: string;
      }>;
    };
    planData?: string[];
    filesGenerated?: string[];
    cotId?: string;
    isPartial?: boolean;
    sandboxContext?: {
      id: string;
      projectType?: string;
      frameworks?: string[];
      dependencies?: Record<string, any>;
      fileCount?: number;
      totalSize?: string;
      entryPoints?: string[];
      buildTools?: string[];
      recentActivity?: Record<string, any>;
    };
    enhancedMetadata?: {
      projectStructure?: Record<string, any>;
      fileStatistics?: Record<string, any>;
      sizeAnalysis?: Record<string, any>;
      timestamp?: string;
    };
    toolData?: {
      tool_name: string;
      status: 'start' | 'complete' | 'error';
      description?: string;
      duration?: number;
      error?: string;
    };
    fileData?: {
      operation: string;
      file_path: string;
      status: 'success' | 'error';
      details?: string;
      error?: string;
    };
    // New field for grouped events
    events?: EventItem[];
    hasEvents?: boolean;
  };
}

interface ApiKeyConfig {
  groq: string;
  openai: string;
  gemini: string;
  openrouter: string;
}

interface AIChatPanelProps {
  selectedSandbox?: any;
  currentFile?: string;
  fileContent?: string;
  onApplyCode?: (code: string, filePath?: string) => void;
  onExecuteCode?: (code: string) => void;
  onStartPreview?: (sandboxId: string) => void;
  onStopPreview?: (sandboxId: string) => void;
  className?: string;
  selectedModel?: string;
  onModelChange?: (model: string) => void;
}

export default function AIChatPanel({
  selectedSandbox,
  currentFile,
  fileContent,
  onApplyCode,
  onExecuteCode,
  onStartPreview,
  onStopPreview,
  className,
  selectedModel = 'gemini-2.5-pro',
  onModelChange
}: AIChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [expandedProgress, setExpandedProgress] = useState<Set<string>>(new Set());
  const [expandedSystemMessages, setExpandedSystemMessages] = useState<Set<string>>(new Set());
  const [showSettings, setShowSettings] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKeyConfig>({
    groq: '',
    openai: '',
    gemini: '',
    openrouter: ''
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messageIdCounter = useRef(0);
  const [isAutoScrollEnabled, setIsAutoScrollEnabled] = useState(true);
  const [isNearBottom, setIsNearBottom] = useState(true);
  const [sandboxContext, setSandboxContext] = useState<any>(null);
  const [enhancedMetadata, setEnhancedMetadata] = useState<any>(null);
  const [metadataLastUpdated, setMetadataLastUpdated] = useState<Date | null>(null);
  
  // Event filtering state
  const [eventFilter, setEventFilter] = useState<string>('all');
  
  // State for tracking events for the current assistant message
  const [currentEvents, setCurrentEvents] = useState<EventItem[]>([]);
  const currentAssistantMessageId = useRef<string | null>(null);
  const [showEventDropdown, setShowEventDropdown] = useState(false);

  // Event categorization logic
  const getEventCategory = (eventType?: string) => {
    switch (eventType) {
      case 'file_operation':
        return 'file_operations';
      case 'tool_usage':
        return 'tools';
      case 'progress_update':
      case 'step_progress':
        return 'progress';
      case 'chain_of_thought':
      case 'plan':
      case 'files_generated':
      case 'review':
      case 'status':
      default:
        return 'system';
    }
  };

  // Filter messages based on selected event filter
  const getFilteredMessages = (messages: Message[]) => {
    if (eventFilter === 'all') return messages;
    
    return messages.filter(message => {
      if (message.role !== 'system') return true;
      const eventType = message.metadata?.eventType;
      const category = getEventCategory(eventType);
      return category === eventFilter;
    });
  };

  // Load API keys from localStorage on component mount
  useEffect(() => {
    const loadApiKeys = () => {
      try {
        const savedKeys = localStorage.getItem('api-keys');
        if (savedKeys) {
          const parsedKeys = JSON.parse(savedKeys);
          setApiKeys(parsedKeys);
        }
      } catch (error) {
        console.error('Failed to load API keys from localStorage:', error);
      }
    };
    
    loadApiKeys();
  }, []);
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [messagesPerPage] = useState(20); // Show 20 messages per page
  const [showAllMessages, setShowAllMessages] = useState(false);

  // Enhanced smooth scrolling function
  const scrollToBottom = (behavior: 'smooth' | 'instant' = 'smooth') => {
    if (messagesEndRef.current && isAutoScrollEnabled) {
      messagesEndRef.current.scrollIntoView({ 
        behavior, 
        block: 'end',
        inline: 'nearest'
      });
    }
  };

  // Check if user is near bottom of chat
  const checkScrollPosition = () => {
    if (scrollAreaRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollAreaRef.current;
      const threshold = 100; // pixels from bottom
      const nearBottom = scrollHeight - scrollTop - clientHeight < threshold;
      setIsNearBottom(nearBottom);
      setIsAutoScrollEnabled(nearBottom);
    }
  };

  // Pagination logic with filtering
  const filteredMessages = getFilteredMessages(messages);
  const totalPages = Math.ceil(filteredMessages.length / messagesPerPage);
  const startIndex = showAllMessages ? 0 : (currentPage - 1) * messagesPerPage;
  const endIndex = showAllMessages ? filteredMessages.length : startIndex + messagesPerPage;
  const displayedMessages = filteredMessages.slice(startIndex, endIndex);

  // Fetch enhanced metadata when sandbox changes
  useEffect(() => {
    const fetchEnhancedMetadata = async () => {
      if (selectedSandbox?.id) {
        try {
          const contextResponse = await apiClient.getSandboxContext(selectedSandbox.id);
          if (contextResponse.success && contextResponse.data) {
            setSandboxContext(contextResponse.data);
            setEnhancedMetadata(contextResponse.data.enhancedMetadata);
            setMetadataLastUpdated(new Date());
          }
        } catch (error) {
          console.error('Failed to fetch enhanced metadata:', error);
        }
      }
    };

    fetchEnhancedMetadata();
  }, [selectedSandbox?.id]);

  // Auto-scroll to latest page when new messages arrive
  useEffect(() => {
    if (messages.length > 0 && !showAllMessages) {
      const newTotalPages = Math.ceil(messages.length / messagesPerPage);
      if (currentPage < newTotalPages) {
        setCurrentPage(newTotalPages);
      }
    }
  }, [messages.length, messagesPerPage, currentPage, showAllMessages]);

  // Enhanced useEffect for auto-scrolling
  useEffect(() => {
    if (isAutoScrollEnabled && displayedMessages.length > 0) {
      // Use requestAnimationFrame for smoother scrolling
      requestAnimationFrame(() => {
        scrollToBottom('smooth');
      });
    }
  }, [displayedMessages, isAutoScrollEnabled]);

  // Generate unique message IDs to avoid React key conflicts
  const generateUniqueId = () => {
    messageIdCounter.current += 1;
    return `${Date.now()}-${messageIdCounter.current}`;
  };

  

  // This useEffect is now handled by the enhanced auto-scrolling above

  // Log component mount and sandbox changes
  useEffect(() => {
    if (selectedSandbox) {
      const sessionId = `sandbox-${selectedSandbox.id}`;
      chatLogger.info('system_event', 'AIChatPanel mounted/sandbox changed', sessionId, {
        sandboxId: selectedSandbox.id,
        sandboxType: selectedSandbox.type,
        sandboxStatus: selectedSandbox.status,
        currentFile,
        model: selectedModel
      });
    }
  }, [selectedSandbox, currentFile, selectedModel]);

  // Load chat history when sandbox changes
  useEffect(() => {
    if (selectedSandbox) {
      loadChatHistory(selectedSandbox.id);
    }
    console.log('Selected sandbox changed:', selectedSandbox.id);
  }, [selectedSandbox?.id]);

  const loadChatHistory = async (sandboxId: string) => {
    try {
      const response = await apiClient.get(`/conversations?sandboxId=${sandboxId}`);
      if (response.success && response.data) {
        const conversations = response.data.conversations || [];
        const historyMessages: Message[] = conversations.map((conv: any) => ({
          id: `history-${conv.id}`,
          role: conv.role as 'user' | 'assistant',
          content: conv.content,
          timestamp: new Date(conv.timestamp),
          metadata: {
            isHistory: true
          }
        }));
        
        setMessages(prev => {
          // Remove welcome message and add history + welcome
          const withoutWelcome = prev.filter(msg => msg.id !== 'welcome');
          return [
            
            {
              id: 'welcome',
              role: 'assistant',
              content: `👋 Hi! I'm your AI coding assistant powered by LangGraph streaming agents.

Currently working with your **${selectedSandbox?.type}** sandbox${selectedSandbox?.name ? ` "${selectedSandbox.name}"` : ''}.

I can help you with:
• **Code generation** - Generate components, functions, or entire files
• **Bug fixes** - Debug and fix errors in your code
• **Code explanations** - Understand how your code works
• **Refactoring** - Improve and optimize existing code
• **Testing** - Add tests for your functions
• **Documentation** - Create READMEs and inline comments

Try asking me:
 
- "Fix this error: [paste error message]"
- "Explain what this function does"
- "Add TypeScript types to this code"
- "Write tests for this component"`,
              timestamp: new Date()
            }
            ,
            ...historyMessages
          ];
        });
      }
    } catch (error) {
      console.error('Failed to load chat history:', error);
    }
  };

  const refreshMetadata = async () => {
    if (!selectedSandbox?.id) return;
    
    try {
      // Refresh metadata on the backend
      await apiClient.refreshSandboxMetadata(selectedSandbox.id);
      
      // Fetch updated context
      const contextResponse = await apiClient.getSandboxContext(selectedSandbox.id);
      if (contextResponse.success && contextResponse.data) {
        setSandboxContext(contextResponse.data);
        setEnhancedMetadata(contextResponse.data.enhancedMetadata);
        setMetadataLastUpdated(new Date());
        
        // Add a system message to indicate metadata was refreshed
        const refreshMessage: Message = {
          id: generateUniqueId(),
          role: 'system',
          content: '🔄 Sandbox metadata refreshed successfully. The AI now has updated context about your project.',
          timestamp: new Date(),
          metadata: {
            eventType: 'metadata_refresh',
            sandboxContext: {
               id: selectedSandbox.id,
               projectType: contextResponse.data.enhancedMetadata?.projectType,
               frameworks: contextResponse.data.enhancedMetadata?.frameworks,
               dependencies: contextResponse.data.enhancedMetadata?.dependencies,
               fileCount: contextResponse.data.enhancedMetadata?.fileCount,
               totalSize: contextResponse.data.enhancedMetadata?.totalSize,
               entryPoints: contextResponse.data.enhancedMetadata?.entryPoints,
               buildTools: contextResponse.data.enhancedMetadata?.buildTools,
               recentActivity: contextResponse.data.enhancedMetadata?.recentActivity
             },
            enhancedMetadata: contextResponse.data.enhancedMetadata
          }
        };
        setMessages(prev => [...prev, refreshMessage]);
      }
    } catch (error) {
      console.error('Failed to refresh metadata:', error);
      const errorMessage: Message = {
        id: generateUniqueId(),
        role: 'system',
        content: '❌ Failed to refresh metadata. Please try again.',
        timestamp: new Date(),
        metadata: { eventType: 'error' }
      };
      setMessages(prev => [...prev, errorMessage]);
    }
  };

  // Helper function to add an event to the current assistant message
  const addEventToCurrentMessage = (eventType: EventItem['type'], content: string, data?: any) => {
    if (!currentAssistantMessageId.current) return;

    const newEvent: EventItem = {
      id: generateUniqueId(),
      type: eventType,
      content,
      timestamp: new Date(),
      data
    };

    setCurrentEvents(prev => [...prev, newEvent]);

    // Update the assistant message with the new event
    setMessages(prev => prev.map(msg =>
      msg.id === currentAssistantMessageId.current
        ? {
            ...msg,
            metadata: {
              ...msg.metadata,
              events: [...(msg.metadata?.events || []), newEvent],
              hasEvents: true
            }
          }
        : msg
    ));
  };

  const sendMessage = async () => {
    if (!input.trim() || !selectedSandbox) return;

    const sessionId = `sandbox-${selectedSandbox.id}`;
    
    // Log user message
    chatLogger.logUserMessage(sessionId, input, {
      sandboxId: selectedSandbox.id,
      sandboxType: selectedSandbox.type,
      currentFile,
      model: selectedModel
    });

    const userMessage: Message = {
      id: generateUniqueId(),
      role: 'user',
      content: input,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      // Build context for the streaming agent
      const context = {
        sandboxId: selectedSandbox.id,
        sandboxType: selectedSandbox.type,
        currentFile,
        fileContent,
        projectStructure: selectedSandbox.metadata?.files || [],
        userMessage: input,
        sessionId: `sandbox-${selectedSandbox.id}`
      };

      // Log message processing start
      chatLogger.logStepChange(sessionId, 'message_processing', 'starting', 'Processing user message');

      let assistantMessage = '';
      let currentAssistantId = generateUniqueId();
      
      // Initialize events tracking for this assistant message
      currentAssistantMessageId.current = currentAssistantId;
      setCurrentEvents([]);
      
      setMessages(prev => [...prev, {
        id: currentAssistantId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        metadata: {
          events: [],
          hasEvents: false
        }
      }]);

      const requestStartTime = Date.now();

      // Use WebSocket for streaming request instead of SSE
      const cleanup = await apiClient.postWebSocket(`/ws/chat`, {
        sessionId: `sandbox-${selectedSandbox.id}`,
        user_request: input,
        model: selectedModel,
        sandbox_context: {
          id: selectedSandbox.id,
          type: selectedSandbox.type,
          name: selectedSandbox.name,
          status: selectedSandbox.status,
          metadata: selectedSandbox.metadata,
          currentFile,
          fileContent,
          enhancedMetadata: sandboxContext?.enhancedMetadata || enhancedMetadata,
          projectType: sandboxContext?.projectType,
          frameworks: sandboxContext?.frameworks,
          dependencies: sandboxContext?.dependencies,
          fileCount: sandboxContext?.fileCount,
          totalSize: sandboxContext?.totalSize,
          entryPoints: sandboxContext?.entryPoints,
          buildTools: sandboxContext?.buildTools,
          recentActivity: sandboxContext?.recentActivity
        },
        sandbox_id: selectedSandbox.id,
        api_keys: apiKeys,
        enhanced_context: true,
        metadata_last_updated: metadataLastUpdated?.toISOString()
      }, (event) => {
        // Handle WebSocket events
        console.log('Received WebSocket event:', event);
        
        if (event.type === 'error') {
          console.error('WebSocket error:', event.data?.message || 'WebSocket error');
          // Don't throw here, just log and show error message
          const errorMessage: Message = {
            id: generateUniqueId(),
            role: 'assistant',
            content: 'Sorry, I encountered a WebSocket error. Please try again.',
            timestamp: new Date()
          };
          setMessages(prev => [...prev, errorMessage]);
          setIsLoading(false);
          cleanup();
          return;
        }

        if (event.type === 'progress') {
          console.log('📊 Received progress update:', event);

          // Log progress update
          chatLogger.logStepChange(sessionId, event.data.step, 'running', event.data.message);

          // Add event to current assistant message instead of creating separate message
          const content = typeof event.data.message === 'string' ? event.data.message : String(event.data.message || 'Processing...');
          addEventToCurrentMessage('progress', content, event.data);
        } else if (event.type === 'node_complete') {
          console.log('✅ Node completed:', event);

          // Add event to current assistant message instead of creating separate message
          const content = `Completed: ${typeof event.data.node === 'string' ? event.data.node : String(event.data.node || 'Unknown')}`;
          addEventToCurrentMessage('node_complete', content, event.data);
        } else if (event.type === 'code_stream') {
          console.log('💻 Code streaming:', event);

          // Update the current assistant message with streaming code
          const partialCode = event.data?.partial_code || '';
          setMessages(prev => prev.map(msg =>
            msg.id === currentAssistantId
              ? { 
                  ...msg, 
                  content: partialCode,
                  metadata: {
                    ...msg.metadata,
                    isPartial: true,
                    eventType: 'code_stream'
                  }
                }
              : msg
          ));
        } else if (event.type === 'tool_usage') {
          console.log('🔧 Tool usage:', event);

          const toolData = event.data;
          let content = '';

          if (toolData.status === 'start') {
            content = `🔧 Using tool: ${toolData.tool_name}`;
            if (toolData.description) {
              content += ` - ${toolData.description}`;
            }
          } else if (toolData.status === 'complete') {
            content = `✅ Tool completed: ${toolData.tool_name}`;
            if (toolData.duration) {
              content += ` (${toolData.duration}ms)`;
            }
          } else if (toolData.status === 'error') {
            content = `❌ Tool error: ${toolData.tool_name}`;
            if (toolData.error) {
              content += ` - ${toolData.error}`;
            }
          }

          // Add event to current assistant message instead of creating separate message
          addEventToCurrentMessage('tool_usage', content, toolData);
        } else if (event.type === 'file_operation') {
          console.log('📁 File operation:', event);

          const fileData = event.data;
          let content = '';

          if (fileData.operation === 'read') {
            content = `📖 Reading file: ${fileData.file_path}`;
          } else if (fileData.operation === 'write') {
            content = `✏️ Writing file: ${fileData.file_path}`;
          } else if (fileData.operation === 'create') {
            content = `📝 Creating file: ${fileData.file_path}`;
          } else if (fileData.operation === 'delete') {
            content = `🗑️ Deleting file: ${fileData.file_path}`;
          } else if (fileData.operation === 'modify') {
            content = `🔧 Modifying file: ${fileData.file_path}`;
          } else {
            content = `📁 File operation: ${fileData.operation} on ${fileData.file_path}`;
          }

          if (fileData.status === 'error' && fileData.error) {
            content += ` - Error: ${fileData.error}`;
          } else if (fileData.status === 'success' && fileData.details) {
            content += ` - ${fileData.details}`;
          }

          // Add event to current assistant message instead of creating separate message
          addEventToCurrentMessage('file_operation', content, fileData);
        } else if (event.type === 'complete') {
          console.log('🎉 Generation complete:', event);

          // Update assistant message with final content and mark as complete
          const finalContent = event.data?.generated_code || event.data?.review_feedback || 'Task completed';
          setMessages(prev => prev.map(msg =>
            msg.id === currentAssistantId
              ? { 
                  ...msg, 
                  content: typeof finalContent === 'string' ? finalContent : String(finalContent),
                  metadata: {
                    ...msg.metadata,
                    isPartial: false,
                    eventType: 'complete'
                  }
                }
              : msg
          ));

          // Log completion
          chatLogger.logStepChange(sessionId, 'generation', 'completed', 'Task completed successfully');

          // Clean up WebSocket connection
          cleanup();
        }
      });

      const requestDuration = Date.now() - requestStartTime;

      // Log API response
      if (true) { // API client handles success/error internally
        chatLogger.logStepChange(sessionId, 'api_request', 'completed', 'API request successful');
      }

    } catch (error) {
      console.error('Failed to send message:', error);

      // Log the error
      chatLogger.logError(sessionId, error instanceof Error ? error : String(error), 'sendMessage');

      const errorMessage: Message = {
        id: generateUniqueId(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);

      // Log completion of message processing
      chatLogger.info('system_event', 'Message processing completed', sessionId, {
        isLoading: false
      });
    }
  };

  const copyToClipboard = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch (error) {
      console.error('Failed to copy code:', error);
    }
  };

  const applyCode = (code: string, filePath?: string) => {
    onApplyCode?.(code, filePath || currentFile);
  };

  const executeCode = (code: string) => {
    onExecuteCode?.(code);
  };

  // Toggle system message expansion state
  const toggleSystemMessage = (messageId: string, open?: boolean) => {
    setExpandedSystemMessages(prev => {
      const newSet = new Set(prev);
      const shouldExpand = open !== undefined ? open : !newSet.has(messageId);
      
      if (shouldExpand) {
        newSet.add(messageId);
      } else {
        newSet.delete(messageId);
      }
      return newSet;
    });
  };

  const getSystemMessageIcon = (eventType?: string) => {
    switch (eventType) {
      case 'chain_of_thought':
        return <Brain className="h-4 w-4" />;
      case 'progress_update':
        return <Clock className="h-4 w-4" />;
      case 'plan':
        return <ListChecks className="h-4 w-4" />;
      case 'files_generated':
        return <FolderOpen className="h-4 w-4" />;
      case 'tool_usage':
        return <Zap className="h-4 w-4" />;
      case 'step_progress':
        return <Settings className="h-4 w-4" />;
      default:
        return <Bot className="h-4 w-4" />;
    }
  };



  const getSystemMessageColor = (eventType?: string) => {
    switch (eventType) {
      case 'chain_of_thought':
        return 'border-purple-400 bg-purple-50 dark:bg-purple-950/10';
      case 'progress_update':
        return 'border-blue-400 bg-blue-50 dark:bg-blue-950/10';
      case 'plan':
        return 'border-green-400 bg-green-50 dark:bg-green-950/10';
      case 'files_generated':
        return 'border-orange-400 bg-orange-50 dark:bg-orange-950/10';
      case 'tool_usage':
        return 'border-yellow-400 bg-yellow-50 dark:bg-yellow-950/10';
      case 'step_progress':
        return 'border-indigo-400 bg-indigo-50 dark:bg-indigo-950/10';
      default:
        return 'border-blue-400 bg-blue-50 dark:bg-blue-950/10';
    }
  };

  // Enhanced collapsible system message renderer
  const renderCollapsibleSystemMessage = (
    message: Message,
    title: string,
    content: React.ReactNode,
    defaultExpanded: boolean = false
  ) => {
    const isExpanded = expandedSystemMessages.has(message.id) ?? defaultExpanded;
    const eventType = message.metadata?.eventType;
    const timestamp = new Date(message.timestamp).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });

    return (
      <div className={cn(
        "border rounded-lg overflow-hidden transition-all duration-300 ease-in-out",
        "bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-900/50 dark:to-gray-800/50",
        "border-gray-200 dark:border-gray-700",
        "hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600",
        "transform hover:scale-[1.01] transition-transform duration-200"
      )}>
        <Collapsible
          open={isExpanded}
          onOpenChange={(open) => toggleSystemMessage(message.id, open)}
        >
          <CollapsibleTrigger asChild>
            <button className={cn(
              "w-full p-4 flex items-center justify-between",
              "hover:bg-gray-100 dark:hover:bg-gray-800/70 transition-colors duration-200",
              "focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset",
              "group"
            )}>
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                  "transition-all duration-300 group-hover:scale-110",
                  getSystemMessageColor(eventType)
                )}>
                  {getSystemMessageIcon(eventType)}
                </div>
                <div className="flex-1 text-left min-w-0">
                  <div className="font-medium text-gray-900 dark:text-gray-100 truncate">
                    {title}
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {timestamp}
                    </span>
                    {eventType && (
                      <span className={cn(
                        "px-2 py-0.5 rounded-full text-xs font-medium",
                        "bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300",
                        "transition-colors duration-200"
                      )}>
                        {eventType.replace('_', ' ')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className={cn(
                "flex items-center gap-2 text-gray-500 dark:text-gray-400",
                "transition-all duration-300 group-hover:text-gray-700 dark:group-hover:text-gray-200"
              )}>
                {isExpanded ? (
                  <ChevronUp className="h-5 w-5 transition-transform duration-300 group-hover:scale-110" />
                ) : (
                  <ChevronDown className="h-5 w-5 transition-transform duration-300 group-hover:scale-110" />
                )}
              </div>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="transition-all duration-300 ease-in-out data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0">
            <div className={cn(
              "px-4 pb-4 border-t border-gray-200 dark:border-gray-700",
              "bg-white/50 dark:bg-gray-900/30"
            )}>
              <div className="pt-3">
                {content}
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    );
  };

  // Render events dropdown component
  const renderEventsDropdown = (events: EventItem[]) => {
    if (!events || events.length === 0) return null;

    const getEventIcon = (type: EventItem['type']) => {
      switch (type) {
        case 'progress': return '📊';
        case 'node_complete': return '✅';
        case 'tool_usage': return '🔧';
        case 'file_operation': return '📁';
        case 'code_stream': return '💻';
        default: return '📝';
      }
    };

    const getEventTypeLabel = (type: EventItem['type']) => {
      switch (type) {
        case 'progress': return 'Progress';
        case 'node_complete': return 'Node Complete';
        case 'tool_usage': return 'Tool Usage';
        case 'file_operation': return 'File Operation';
        case 'code_stream': return 'Code Stream';
        default: return 'Event';
      }
    };

    return (
      <Collapsible>
        <CollapsibleTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-between text-xs h-8 mb-2"
          >
            <div className="flex items-center gap-2">
              <Zap className="h-3 w-3" />
              <span>Events ({events.length})</span>
            </div>
            <ChevronDown className="h-3 w-3" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="space-y-1 mb-2">
          {events.map((event) => (
            <div
              key={event.id}
              className="flex items-start gap-2 p-2 text-xs bg-gray-50 dark:bg-gray-800/50 rounded border"
            >
              <span className="flex-shrink-0 mt-0.5">{getEventIcon(event.type)}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant="secondary" className="text-xs px-1 py-0">
                    {getEventTypeLabel(event.type)}
                  </Badge>
                  <span className="text-gray-500 text-xs">
                    {event.timestamp.toLocaleTimeString()}
                  </span>
                </div>
                <div className="text-gray-700 dark:text-gray-300 break-words">
                  {event.content}
                </div>
              </div>
            </div>
          ))}
        </CollapsibleContent>
      </Collapsible>
    );
  };

  const renderMessage = (message: Message) => {
    const isUser = message.role === 'user';
    const isSystem = message.role === 'system';
    const isHistory = message.metadata?.isHistory;

    // Enhanced system messages with collapsible design
    if (isSystem) {
      const eventType = message.metadata?.eventType;
      
      // Chain of Thought messages
      if (eventType === 'chain_of_thought') {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "🧠 Chain of Thought",
              <div className="space-y-2">
                <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                  {message.content}
                </div>
              </div>,
              false // Collapsed by default
            )}
          </div>
        );
      }

      // Progress Update messages
      if (eventType === 'progress_update' && message.metadata?.progressData) {
        const progressData = message.metadata.progressData;
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              `📊 Progress Update (${progressData.overallProgress}%)`,
              <div className="space-y-3">
                <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
                  <div 
                    className="bg-gradient-to-r from-blue-500 to-blue-600 h-3 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${progressData.overallProgress || 0}%` }}
                  ></div>
                </div>
                <div className="text-xs text-gray-600 dark:text-gray-400 text-center">
                  Step {progressData.currentStep || 0} of {progressData.steps?.length || 0}
                </div>
                {progressData.steps && progressData.steps.length > 0 && (
                  <div className="space-y-2">
                    {progressData.steps.map((step, index) => (
                      <div key={step.id || index} className="flex items-center gap-3 p-2 rounded-md bg-gray-50 dark:bg-gray-800/50">
                        <div className={cn(
                          "w-3 h-3 rounded-full flex-shrink-0 transition-all duration-300",
                          step.status === 'completed' && "bg-green-500 shadow-green-500/50 shadow-sm",
                          step.status === 'running' && "bg-blue-500 animate-pulse shadow-blue-500/50 shadow-sm",
                          step.status === 'failed' && "bg-red-500 shadow-red-500/50 shadow-sm",
                          step.status === 'pending' && "bg-gray-400"
                        )} />
                        <div className="flex-1">
                          <span className={cn(
                            "text-sm font-medium",
                            step.status === 'completed' && "text-green-700 dark:text-green-300",
                            step.status === 'running' && "text-blue-700 dark:text-blue-300",
                            step.status === 'failed' && "text-red-700 dark:text-red-300",
                            step.status === 'pending' && "text-gray-600 dark:text-gray-400"
                          )}>
                            {step.label}
                          </span>
                          {step.progress !== undefined && step.progress > 0 && step.progress < 100 && (
                            <span className="ml-2 text-xs text-gray-500">({step.progress}%)</span>
                          )}
                          {step.message && (
                            <div className="text-xs text-gray-500 italic mt-1">{step.message}</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>,
              true // Expanded by default for progress
            )}
          </div>
        );
      }

      // Plan messages
      if (eventType === 'plan' || message.metadata?.planData) {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "📋 Execution Plan",
              <div className="space-y-2">
                {message.metadata?.planData ? (
                  message.metadata.planData.map((step, index) => (
                    <div key={index} className="flex items-start gap-3 p-2 rounded-md bg-gray-50 dark:bg-gray-800/50">
                      <div className="w-6 h-6 rounded-full bg-green-100 dark:bg-green-900/50 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-bold text-green-700 dark:text-green-300">{index + 1}</span>
                      </div>
                      <span className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{step}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                    {message.content}
                  </div>
                )}
              </div>,
              false // Collapsed by default
            )}
          </div>
        );
      }

      // Files Generated messages
      if (eventType === 'files_generated' || message.metadata?.filesGenerated) {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "📁 Files Generated",
              <div className="space-y-2">
                {message.metadata?.filesGenerated ? (
                  message.metadata.filesGenerated.map((file, index) => (
                    <div key={index} className="flex items-center gap-3 p-2 rounded-md bg-gray-50 dark:bg-gray-800/50">
                      <FileText className="h-4 w-4 text-orange-500 flex-shrink-0" />
                      <span className="text-sm text-gray-700 dark:text-gray-300 font-mono">{file}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                    {message.content}
                  </div>
                )}
              </div>,
              true // Expanded by default for files
            )}
          </div>
        );
      }

      // Tool Usage messages
      if (eventType === 'tool_usage') {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "🔧 Tool Usage",
              <div className="space-y-2">
                <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                  {message.content}
                </div>
              </div>,
              false // Collapsed by default
            )}
          </div>
        );
      }

      // Step Progress messages
      if (eventType === 'step_progress') {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "⚙️ Step Progress",
              <div className="space-y-2">
                <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                  {message.content}
                </div>
              </div>,
              false // Collapsed by default
            )}
          </div>
        );
      }

      // Code Review messages
      if (eventType === 'review') {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "📝 Code Review",
              <div className="space-y-2">
                <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                  {message.content}
                </div>
              </div>,
              true // Expanded by default for reviews
            )}
          </div>
        );
      }

      // File Operation messages
      if (eventType === 'file_operation') {
        return (
          <div key={message.id} className="mb-3">
            {renderCollapsibleSystemMessage(
              message,
              "📁 File Operation",
              <div className="space-y-2">
                <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                  {message.content}
                </div>
              </div>,
              false // Collapsed by default
            )}
          </div>
        );
      }

      // Default system messages (status, etc.)
      return (
        <div key={message.id} className="mb-3">
          {renderCollapsibleSystemMessage(
            message,
            message.metadata?.eventType === 'status' ? "📡 Status Update" : "🤖 System Message",
            <div className="space-y-2">
              <div className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words leading-relaxed">
                {message.content}
              </div>
            </div>,
            eventType === 'status' // Status messages expanded by default
          )}
        </div>
      );
    }

    return (
      <div key={message.id} className={cn(
        "flex gap-3 p-4 relative",
        isUser ? "bg-blue-50 dark:bg-blue-950/20" : "bg-white dark:bg-gray-800",
        isHistory && "opacity-75 border-l-4 border-gray-300 dark:border-gray-600"
      )}>
        {isHistory && (
          <div className="absolute -top-2 -left-2 bg-gray-500 text-white text-xs px-2 py-1 rounded-full">
            History
          </div>
        )}
        <div className={cn(
          "w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium flex-shrink-0",
          isUser
            ? "bg-blue-500 text-white"
            : "bg-green-500 text-white"
        )}>
          {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
        </div>
        <div className="flex-1 space-y-3 min-w-0">
          <div className="text-sm text-gray-600 dark:text-gray-400">
            {message.timestamp.toLocaleTimeString()}
          </div>

          <div className="prose prose-sm dark:prose-invert max-w-none">
            {(typeof message.content === 'string' ? message.content : String(message.content || '')).split('\n').map((line, i) => (
              <p key={i} className="mb-2 last:mb-0 whitespace-pre-wrap break-words">{line}</p>
            ))}
          </div>

          {/* Events Dropdown for Assistant Messages */}
          {!isUser && message.metadata?.hasEvents && message.metadata?.events && (
            renderEventsDropdown(message.metadata.events)
          )}

          {/* Code Blocks */}
          {message.metadata?.codeBlocks?.map((block, index) => (
            <Card key={index} className="relative">
              <CardContent className="p-3">
                <div className="flex items-center justify-between mb-2">
                  <Badge variant="outline" className="text-xs">
                    {block.language}
                  </Badge>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => copyToClipboard(block.code)}
                      className="h-6 px-2"
                    >
                      {copiedCode === block.code ? (
                        <Check className="h-3 w-3" />
                      ) : (
                        <Copy className="h-3 w-3" />
                      )}
                    </Button>
                    {block.canApply && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => applyCode(block.code, block.filePath)}
                        className="h-6 px-2"
                      >
                        <FileText className="h-3 w-3 mr-1" />
                        Apply
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => executeCode(block.code)}
                      className="h-6 px-2"
                    >
                      <Play className="h-3 w-3 mr-1" />
                      Run
                    </Button>
                  </div>
                </div>
                <pre className="text-xs overflow-x-auto bg-gray-50 dark:bg-gray-900 p-2 rounded font-mono">
                  <code>{block.code}</code>
                </pre>
              </CardContent>
            </Card>
          ))}

          {/* Action Suggestions */}
          {message.metadata?.suggestions?.map((suggestion, index) => (
            <Button
              key={index}
              size="sm"
              variant="outline"
              onClick={() => setInput(suggestion)}
              className="mr-2 mb-2 text-xs"
            >
              {suggestion}
            </Button>
          ))}
        </div>
      </div>
    );
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleModelChange = (newModel: string) => {
    if (selectedSandbox && onModelChange) {
      const sessionId = `sandbox-${selectedSandbox.id}`;
      chatLogger.logModelChange(sessionId, selectedModel, newModel);
      onModelChange(newModel);
    }
  };

  const handleStartPreview = (sandboxId: string) => {
    const sessionId = `sandbox-${sandboxId}`;
    chatLogger.logSandboxAction(sessionId, 'start_preview', sandboxId, {
      previousStatus: selectedSandbox?.status
    });
    onStartPreview?.(sandboxId);
  };

  const handleStopPreview = (sandboxId: string) => {
    const sessionId = `sandbox-${sandboxId}`;
    chatLogger.logSandboxAction(sessionId, 'stop_preview', sandboxId, {
      previousStatus: selectedSandbox?.status
    });
    onStopPreview?.(sandboxId);
  };

  return (
    <div className={cn(
      "h-[600px] max-h-[600px] flex flex-col bg-white dark:bg-gray-800 transition-all duration-300",
      "border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm overflow-hidden",
      className
    )}>
      {/* Chat Header */}
      <div className="bg-gray-50 dark:bg-gray-700 px-4 py-3 border-b border-gray-200 dark:border-gray-600 rounded-t-lg">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative">
              <Bot className="h-5 w-5 text-blue-600" />
              {isLoading && (
                <div className="absolute -top-1 -right-1 h-2 w-2 bg-green-500 rounded-full animate-pulse" />
              )}
            </div>
            <span className="font-medium">AI Assistant</span>
            {selectedSandbox && (
              <Badge variant="secondary" className="text-xs animate-in fade-in-0 slide-in-from-left-2">
                {selectedSandbox.type}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1">
            {selectedSandbox && (
              <Button
                size="sm"
                variant="outline"
                onClick={refreshMetadata}
                title="Refresh sandbox metadata for better AI context"
                className="text-xs"
              >
                <RefreshCw className="h-3 w-3 mr-1" />
                Refresh Context
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowSettings(!showSettings)}
              className={cn(showSettings && "bg-blue-100 dark:bg-blue-900")}
            >
              <Settings className="h-3 w-3 mr-1" />
              Settings
            </Button>
            {selectedSandbox && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleStartPreview(selectedSandbox.id)}
                  disabled={selectedSandbox.status === 'creating' || selectedSandbox.status === 'running'}
                >
                  <Eye className="h-3 w-3 mr-1" />
                  Start Preview
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleStopPreview(selectedSandbox.id)}
                  disabled={selectedSandbox.status !== 'running'}
                >
                  <Square className="h-3 w-3 mr-1" />
                  Stop Preview
                </Button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Settings Panel */}
      {showSettings && (
        <div className="border-b border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 max-h-96 overflow-y-auto">
          <div className="p-4 space-y-4">
          <ApiKeySettings
            onApiKeysChange={setApiKeys}
            className="max-w-2xl"
          />
          
          {/* Sandbox Context Display */}
          {selectedSandbox && sandboxContext && (
            <div className="max-w-2xl">
              <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
                <Brain className="h-4 w-4" />
                Sandbox Context
                {metadataLastUpdated && (
                  <span className="text-xs text-gray-500">
                    Updated: {new Date(metadataLastUpdated).toLocaleTimeString()}
                  </span>
                )}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="space-y-2">
                  <div>
                    <span className="font-medium">Project Type:</span>{' '}
                    <Badge variant="secondary" className="text-xs">
                      {sandboxContext.enhancedMetadata?.projectType || 'Unknown'}
                    </Badge>
                  </div>
                  {sandboxContext.enhancedMetadata?.frameworks && sandboxContext.enhancedMetadata.frameworks.length > 0 && (
                    <div>
                      <span className="font-medium">Frameworks:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {sandboxContext.enhancedMetadata.frameworks.map((framework: string, index: number) => (
                          <Badge key={index} variant="outline" className="text-xs">
                            {framework}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {sandboxContext.enhancedMetadata?.fileCount && (
                    <div>
                      <span className="font-medium">Files:</span> {sandboxContext.enhancedMetadata.fileCount}
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  {sandboxContext.enhancedMetadata?.totalSize && (
                    <div>
                      <span className="font-medium">Size:</span> {sandboxContext.enhancedMetadata.totalSize}
                    </div>
                  )}
                  {sandboxContext.enhancedMetadata?.entryPoints && sandboxContext.enhancedMetadata.entryPoints.length > 0 && (
                    <div>
                      <span className="font-medium">Entry Points:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {sandboxContext.enhancedMetadata.entryPoints.map((entry: string, index: number) => (
                          <Badge key={index} variant="outline" className="text-xs">
                            {entry}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {sandboxContext.enhancedMetadata?.buildTools && sandboxContext.enhancedMetadata.buildTools.length > 0 && (
                    <div>
                      <span className="font-medium">Build Tools:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {sandboxContext.enhancedMetadata.buildTools.map((tool: string, index: number) => (
                          <Badge key={index} variant="outline" className="text-xs">
                            {tool}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 relative overflow-hidden">
        {/* Pagination Controls */}
        {messages.length > messagesPerPage && (
          <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowAllMessages(!showAllMessages)}
                className="text-xs"
              >
                {showAllMessages ? 'Show Paginated' : 'Show All'}
              </Button>
              {!showAllMessages && (
                <span className="text-xs text-gray-500">
                  Page {currentPage} of {totalPages} ({messages.length} total messages)
                </span>
              )}
            </div>
            {!showAllMessages && totalPages > 1 && (
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  disabled={currentPage === 1}
                  className="h-6 w-6 p-0"
                >
                  <ChevronUp className="h-3 w-3" />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                  disabled={currentPage === totalPages}
                  className="h-6 w-6 p-0"
                >
                  <ChevronDown className="h-3 w-3" />
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Event Filter Dropdown */}
        <div className="flex items-center justify-between px-4 py-2 bg-gray-50 dark:bg-gray-700 border-b border-gray-200 dark:border-gray-600">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-gray-500" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Filter Events:</span>
            <Select value={eventFilter} onValueChange={setEventFilter}>
              <SelectTrigger className="w-48 h-8 text-xs">
                <SelectValue placeholder="Select event type" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Event Categories</SelectLabel>
                  <SelectItem value="all">All Events</SelectItem>
                  <SelectItem value="system">
                    <div className="flex items-center gap-2">
                      <Brain className="h-3 w-3" />
                      System Events
                    </div>
                  </SelectItem>
                  <SelectItem value="file_operations">
                    <div className="flex items-center gap-2">
                      <FolderOpen className="h-3 w-3" />
                      File Operations
                    </div>
                  </SelectItem>
                  <SelectItem value="tools">
                    <div className="flex items-center gap-2">
                      <Zap className="h-3 w-3" />
                      Tool Usage
                    </div>
                  </SelectItem>
                  <SelectItem value="progress">
                    <div className="flex items-center gap-2">
                      <Clock className="h-3 w-3" />
                      Progress Updates
                    </div>
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="text-xs text-gray-500">
            {eventFilter === 'all' ? `${messages.length} total messages` : `${getFilteredMessages(messages).length} filtered messages`}
          </div>
        </div>
        
        <ScrollArea 
          className="h-full"
          ref={scrollAreaRef}
          onScrollCapture={checkScrollPosition}
        >
          <div className="p-4 space-y-4">
             {displayedMessages.map((message, index) => (
               <div 
                 key={message.id}
                 className={cn(
                   "transition-all duration-300 ease-in-out transform",
                   "animate-in slide-in-from-bottom-2 fade-in-0",
                   index === messages.length - 1 && "animate-in slide-in-from-bottom-4 fade-in-0 duration-500",
                   "border-b border-gray-100 dark:border-gray-700 pb-4 last:border-b-0"
                 )}
               >
                 {renderMessage(message)}
               </div>
             ))}
             <div ref={messagesEndRef} className="h-4" />
           </div>
        </ScrollArea>
        
        {/* Scroll to bottom button */}
        {!isNearBottom && messages.length > 0 && (
          <Button
            size="sm"
            variant="secondary"
            className={cn(
              "absolute bottom-4 right-4 z-10 shadow-lg",
              "animate-in slide-in-from-bottom-2 fade-in-0 duration-200",
              "hover:scale-105 transition-transform"
            )}
            onClick={() => {
              setIsAutoScrollEnabled(true);
              scrollToBottom('smooth');
            }}
          >
            <ArrowDown className="h-4 w-4 mr-1" />
            New messages
          </Button>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 dark:border-gray-600 p-4 bg-white dark:bg-gray-800 transition-colors duration-200">
        <div className="mb-3">
          <ModelSelector
            selectedModel={selectedModel}
            onModelChange={handleModelChange}
          />
        </div>
        <div className="flex gap-3 items-end">
          <div className="flex-1 relative">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={selectedSandbox ? "Ask me anything about your code..." : "Select a sandbox to start chatting..."}
              className={cn(
                "min-h-[60px] max-h-[120px] resize-none transition-all duration-200",
                "focus:ring-2 focus:ring-blue-500 focus:border-transparent",
                "border-gray-300 dark:border-gray-600",
                !selectedSandbox && "bg-gray-50 dark:bg-gray-700",
                isLoading && "opacity-75"
              )}
              disabled={!selectedSandbox || isLoading}
            />
            {isLoading && (
              <div className="absolute inset-0 bg-white/50 dark:bg-gray-800/50 flex items-center justify-center rounded-md">
                <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Thinking...
                </div>
              </div>
            )}
          </div>
          <Button
            onClick={sendMessage}
            disabled={!input.trim() || !selectedSandbox || isLoading}
            className={cn(
              "h-[60px] px-4 transition-all duration-200",
              "hover:scale-105 active:scale-95",
              "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
            )}
            size="lg"
          >
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Send className="h-5 w-5" />
            )}
          </Button>
        </div>
        <div className="flex justify-between items-center mt-3">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            Press Enter to send, Shift+Enter for new line
          </div>
          {input.length > 0 && (
            <div className="text-xs text-gray-400 dark:text-gray-500">
              {input.length} characters
            </div>
          )}
        </div>
      </div>
    </div>
  );
}