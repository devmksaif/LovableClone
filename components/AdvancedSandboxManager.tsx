"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Loader2, Play, RefreshCw, Code, Eye, FileText, Settings, Plus, Trash2,
  Square, Edit, Download, Upload, Copy, Search, Filter, MoreVertical,
  Terminal, GitBranch, Zap, Save, FolderOpen, FilePlus,
  Globe, Cpu, MemoryStick, HardDrive, Clock, CheckCircle, XCircle,
  AlertCircle, Info, Star, StarOff, Share, Link, ExternalLink,
  X, Database
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { SandboxService, FileService, socketService, Sandbox, SystemStats } from '@/services';
 
import AIChatPanel from './AIChatPanel';

interface ExecutionResult {
  output: string;
  error: string;
  exitCode: number;
  executionTime: number;
  timestamp: Date;
}

interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  lastModified?: Date;
  content?: string;
}

interface Template {
  id: string;
  name: string;
  description: string;
  type: 'react' | 'vue';
  category: string;
  tags: string[];
  files: FileItem[];
}

const SANDBOX_TEMPLATES: Template[] = [
  {
    id: 'react-basic',
    name: 'React Basic',
    description: 'A simple React application with basic components',
    type: 'react',
    category: 'frontend',
    tags: ['react', 'basic', 'components'],
    files: []
  },
  {
    id: 'vue-basic',
    name: 'Vue Basic',
    description: 'A simple Vue.js application',
    type: 'vue',
    category: 'frontend',
    tags: ['vue', 'basic'],
    files: []
  }
];

export default function AdvancedSandboxManager() {
  // Core state
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [selectedSandbox, setSelectedSandbox] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');

  // Create sandbox state
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newSandboxName, setNewSandboxName] = useState('');
  const [newSandboxType, setNewSandboxType] = useState<'react' | 'vue'>('react');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [creating, setCreating] = useState(false);

  // File management state
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileItem | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [savingFile, setSavingFile] = useState(false);
  const [fileSearch, setFileSearch] = useState('');

  // Preview state
  const [showPreview, setShowPreview] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [startingPreview, setStartingPreview] = useState(false);

  // Execution state
  const [code, setCode] = useState(`// Welcome to Advanced Sandbox Manager!
// Write your JavaScript code here

function greet(name) {
  return \`Hello, \${name}! Welcome to your advanced sandbox environment.\`;
}

console.log(greet('Developer'));

// Try modern JavaScript features
const numbers = [1, 2, 3, 4, 5];
const doubled = numbers.map(n => n * 2);
console.log('Doubled numbers:', doubled);

// Async example
async function fetchData() {
  return new Promise(resolve => {
    setTimeout(() => resolve('Advanced sandbox data loaded!'), 1000);
  });
}

fetchData().then(data => console.log(data));`);
  const [executing, setExecuting] = useState(false);
  const [executionResults, setExecutionResults] = useState<ExecutionResult[]>([]);

  // Model selection state
  const [selectedModel, setSelectedModel] = useState<string>('gemini-2.5-flash');

  // UI state
  const [activeTab, setActiveTab] = useState('sandboxes');
  const [showTerminal, setShowTerminal] = useState(false);
  const [terminalOutput, setTerminalOutput] = useState('');

  // Bulk actions state
  const [selectedSandboxes, setSelectedSandboxes] = useState<Set<string>>(new Set());
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [realtimeUpdates, setRealtimeUpdates] = useState<Sandbox[]>([]);

  // Search and filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  // Edit sandbox state
  const [editingSandbox, setEditingSandbox] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  // Stats and monitoring
  const [systemStats, setSystemStats] = useState<SystemStats>({
    totalSandboxes: 0,
    runningSandboxes: 0,
    totalFiles: 0,
    storageUsed: '0 MB'
  });

  // Load initial data
  useEffect(() => {
    loadSandboxes();
    loadSystemStats();
  }, []);

  // Load files when sandbox changes
  useEffect(() => {
    if (selectedSandbox) {
      loadFiles();
      loadSandboxStats();
    }
  }, [selectedSandbox]);

  // Load file content when file changes
  useEffect(() => {
    if (selectedFile) {
      loadFileContent(selectedFile);
    }
  }, [selectedFile]);

  // WebSocket connection for real-time updates
  useEffect(() => {
    socketService.connect('ws://localhost:8000/ws/sandbox-updates', {
      onOpen: () => {
        console.log('WebSocket connected for sandbox updates');
        setWsConnected(true);
      },
      onMessage: (data: any) => {
        handleRealtimeUpdate(data);
      },
      onClose: () => {
        console.log('WebSocket disconnected');
        setWsConnected(false);
      },
      onError: (error: Event) => {
        console.error('WebSocket error:', error);
        setWsConnected(false);
      }
    });

    return () => {
      socketService.disconnect();
    };
  }, []);

  const handleRealtimeUpdate = (data: any) => {
    console.log('Received WebSocket update:', data);
    
    if (data.type === 'created') {
      // Add new sandbox to the list
      const newSandbox = {
        ...data.sandbox,
        createdAt: new Date(data.sandbox.createdAt || data.timestamp),
        lastActivity: new Date(data.sandbox.lastActivity || data.timestamp)
      };
      setSandboxes(prev => [...prev, newSandbox]);
    } else if (data.type === 'updated') {
      // Update existing sandbox
      setSandboxes(prev => prev.map(sandbox => 
        sandbox.id === data.sandbox.id 
          ? { 
              ...sandbox, 
              ...data.sandbox,
              createdAt: new Date(data.sandbox.createdAt || sandbox.createdAt),
              lastActivity: new Date(data.sandbox.lastActivity || data.timestamp)
            }
          : sandbox
      ));
    } else if (data.type === 'deleted') {
      // Remove sandbox from the list
      setSandboxes(prev => prev.filter(sandbox => sandbox.id !== data.sandbox.id));
      setSelectedSandboxes(prev => {
        const newSet = new Set(prev);
        newSet.delete(data.sandbox.id);
        return newSet;
      });
      // Clear selection if the deleted sandbox was selected
      if (selectedSandbox === data.sandbox.id) {
        setSelectedSandbox('');
      }
    } else if (data.type === 'initial') {
      // Handle initial data load
      const sandboxesArray = Array.isArray(data.sandboxes) ? data.sandboxes : data.sandboxes?.sandboxes || [];
      const formattedSandboxes = sandboxesArray.map((sandbox: any) => ({
        ...sandbox,
        createdAt: new Date(sandbox.createdAt),
        lastActivity: new Date(sandbox.lastActivity)
      }));
      setSandboxes(formattedSandboxes);
    }
  };

  const loadSandboxes = async () => {
    try {
      setLoading(true);
      const response = await SandboxService.getSandboxes();

      if (response.success && response.data && response.data.sandboxes) {
        const formattedSandboxes = response.data.sandboxes.map((sandbox: any) => ({
          ...sandbox,
          id: sandbox.id || '',
          name: sandbox.name,
          type: sandbox.type || 'react',
          status: sandbox.status || 'ready',
          createdAt: new Date(sandbox.createdAt),
          lastActivity: new Date(sandbox.lastActivity),
          metadata: sandbox.metadata,
          preview: sandbox.preview,
          stats: sandbox.stats
        })) as Sandbox[];
        setSandboxes(formattedSandboxes);

        // Auto-select first sandbox if none selected
        if (formattedSandboxes.length > 0 && !selectedSandbox) {
          setSelectedSandbox(formattedSandboxes[0].id);
        }
      } else {
        setError(response.error || 'Failed to load sandboxes');
      }
    } catch (error) {
      console.error('Failed to load sandboxes:', error);
      setError('Failed to load sandboxes');
    } finally {
      setLoading(false);
    }
  };

  const loadSystemStats = async () => {
    try {
      const response = await SandboxService.getSystemStats();

      if (response.success && response.data) {
        setSystemStats(response.data);
      }
    } catch (error) {
      console.warn('Failed to load system stats:', error);
    }
  };

  const loadFiles = async () => {
    if (!selectedSandbox) return;

    setLoadingFiles(true);
    try {
      const response = await FileService.getFiles(selectedSandbox);

      if (response.success && response.data) {
        const fileItems: FileItem[] = response.data.files.map((file: any) => ({
          name: file.name || file,
          path: file.path || file,
          type: file.type || 'file',
          size: file.size,
          lastModified: file.lastModified ? new Date(file.lastModified) : undefined
        }));
        setFiles(fileItems);

        // Auto-select first file if available
        if (fileItems.length > 0 && !selectedFile) {
          setSelectedFile(fileItems[0]);
        }
      }
    } catch (error) {
      console.error('Failed to load files:', error);
      setError('Failed to load files');
    } finally {
      setLoadingFiles(false);
    }
  };

  const loadFileContent = async (file: FileItem) => {
    if (!selectedSandbox) return;

    try {
      const response = await FileService.getFileContent(selectedSandbox, file.path);

      if (response.success && response.data) {
        setFileContent(response.data.content);
      } else {
        setFileContent(`// Error loading file: ${response.error}`);
      }
    } catch (error) {
      console.error('Failed to load file content:', error);
      setFileContent(`// Error loading file: ${error}`);
    }
  };

  const loadSandboxStats = async () => {
    if (!selectedSandbox) return;

    try {
      const response = await SandboxService.getSandboxStats(selectedSandbox);

      if (response.success && response.data && response.data.stats) {
        const stats = response.data.stats;
        setSandboxes(prev => prev.map(sandbox =>
          sandbox.id === selectedSandbox
            ? { ...sandbox, stats }
            : sandbox
        ));
      }
    } catch (error) {
      console.warn('Failed to load sandbox stats:', error);
    }
  };

  const createSandbox = async () => {
    if (!newSandboxName.trim()) {
      setError('Sandbox name is required');
      return;
    }

    setCreating(true);
    setError('');

    try {
      const response = await SandboxService.createSandbox({
        name: newSandboxName,
        type: newSandboxType,
        template: selectedTemplate || undefined
      });

      if (response.success && response.data) {
        const sandbox = response.data;
        setSandboxes(prev => [...prev, {
          ...sandbox,
          createdAt: new Date(sandbox.createdAt),
          lastActivity: new Date(sandbox.lastActivity)
        }]);
        setSelectedSandbox(sandbox.id);
        setShowCreateDialog(false);
        setNewSandboxName('');
        setSelectedTemplate('');
        loadSystemStats();
      } else {
        setError(response.error || 'Failed to create sandbox');
      }
    } catch (error) {
      console.error('Failed to create sandbox:', error);
      setError('Failed to create sandbox');
    } finally {
      setCreating(false);
    }
  };

  const updateSandbox = async (sandboxId: string, updates: Partial<Sandbox>) => {
    try {
      const response = await SandboxService.updateSandbox(sandboxId, updates);

      if (response.success && response.data) {
        const sandbox = response.data;
        setSandboxes(prev => prev.map(s =>
          s.id === sandboxId ? { ...sandbox, createdAt: new Date(sandbox.createdAt), lastActivity: new Date(sandbox.lastActivity) } : s
        ));
        setEditingSandbox(null);
        setEditName('');
      } else {
        setError(response.error || 'Failed to update sandbox');
      }
    } catch (error) {
      console.error('Failed to update sandbox:', error);
      setError('Failed to update sandbox');
    }
  };

  const deleteSandbox = async (sandboxId: string) => {
    if (!confirm('Are you sure you want to delete this sandbox? This action cannot be undone.')) {
      return;
    }

    try {
      const response = await SandboxService.deleteSandbox(sandboxId);

      if (response.success) {
        setSandboxes(prev => prev.filter(sandbox => sandbox.id !== sandboxId));
        if (selectedSandbox === sandboxId) {
          setSelectedSandbox('');
          setSelectedFile(null);
          setFileContent('');
        }
        loadSystemStats();
      } else {
        setError(response.error || 'Failed to delete sandbox');
      }
    } catch (error) {
      console.error('Failed to delete sandbox:', error);
      setError('Failed to delete sandbox');
    }
  };

  const startPreview = async (sandboxId: string) => {
    setStartingPreview(true);
    try {
      const response = await SandboxService.startPreview(sandboxId);

      if (response.success && response.data && response.data.preview) {
        const preview = response.data.preview;
        setShowPreview(true);
        setPreviewHtml(preview.iframeHtml || '');

        // Update sandbox status
        setSandboxes(prev => prev.map(sandbox =>
          sandbox.id === sandboxId
            ? {
                ...sandbox,
                status: 'running',
                preview: {
                  url: preview.url,
                  port: 3000, // Default port
                  status: 'running',
                  iframeHtml: preview.iframeHtml
                }
              }
            : sandbox
        ));

        loadSystemStats();
      } else {
        setError(response.error || 'Failed to start preview');
      }
    } catch (error) {
      console.error('Failed to start preview:', error);
      setError('Failed to start preview');
    } finally {
      setStartingPreview(false);
    }
  };

  const stopPreview = async (sandboxId: string) => {
    try {
      const response = await SandboxService.stopPreview(sandboxId);

      if (response.success) {
        setShowPreview(false);
        setPreviewHtml('');

        // Update sandbox status
        setSandboxes(prev => prev.map(sandbox =>
          sandbox.id === sandboxId
            ? { ...sandbox, status: 'ready', preview: undefined }
            : sandbox
        ));

        loadSystemStats();
      } else {
        setError(response.error || 'Failed to stop preview');
      }
    } catch (error) {
      console.error('Failed to stop preview:', error);
      setError('Failed to stop preview');
    }
  };

  const stopSandbox = async (sandboxId: string) => {
    try {
      const response = await fetch(`/api/sandbox/${sandboxId}/stop`, {
        method: 'POST'
      });

      const data = await response.json();

      if (data.success) {
        // Update sandbox status to stopped
        setSandboxes(prev => prev.map(sandbox =>
          sandbox.id === sandboxId
            ? { ...sandbox, status: 'stopped', preview: undefined }
            : sandbox
        ));

        loadSystemStats();
      } else {
        setError(data.error || 'Failed to stop sandbox');
      }
    } catch (error) {
      console.error('Failed to stop sandbox:', error);
      setError('Failed to stop sandbox');
    }
  };

  // Bulk action handlers
  const handleSelectAll = () => {
    const filteredSandboxes = getFilteredSandboxes();
    if (selectedSandboxes.size === filteredSandboxes.length) {
      setSelectedSandboxes(new Set());
    } else {
      setSelectedSandboxes(new Set(filteredSandboxes.map(s => s.id)));
    }
  };

  const handleSelectSandbox = (sandboxId: string) => {
    setSelectedSandboxes(prev => {
      const newSet = new Set(prev);
      if (newSet.has(sandboxId)) {
        newSet.delete(sandboxId);
      } else {
        newSet.add(sandboxId);
      }
      return newSet;
    });
  };

  const bulkDelete = async () => {
    if (selectedSandboxes.size === 0) return;

    if (!confirm(`Are you sure you want to delete ${selectedSandboxes.size} sandbox(es)? This action cannot be undone.`)) {
      return;
    }

    setBulkActionLoading(true);
    setError('');
    
    try {
      const deletePromises = Array.from(selectedSandboxes).map(async (sandboxId) => {
        const response = await fetch(`/api/sandbox/${sandboxId}`, {
          method: 'DELETE'
        });
        return { sandboxId, response: await response.json() };
      });

      const results = await Promise.all(deletePromises);
      const failed = results.filter(r => !r.response.success);

      if (failed.length > 0) {
        setError(`Failed to delete ${failed.length} sandbox(es)`);
      } else {
        // Clear selection after successful bulk delete
        setSelectedSandboxes(new Set());
        // The WebSocket will handle updating the UI automatically
        console.log(`Successfully deleted ${selectedSandboxes.size} sandboxes`);
      }
    } catch (error) {
      console.error('Bulk delete failed:', error);
      setError('Bulk delete failed');
    } finally {
      setBulkActionLoading(false);
    }
  };

  const bulkStop = async () => {
    if (selectedSandboxes.size === 0) return;

    setBulkActionLoading(true);
    setError('');
    
    try {
      const stopPromises = Array.from(selectedSandboxes).map(async (sandboxId) => {
        const response = await fetch(`/api/sandbox/${sandboxId}/stop`, {
          method: 'POST'
        });
        return { sandboxId, response: await response.json() };
      });

      const results = await Promise.all(stopPromises);
      const failed = results.filter(r => !r.response.success);

      if (failed.length > 0) {
        setError(`Failed to stop ${failed.length} sandbox(es)`);
      } else {
        // The WebSocket will handle updating the UI automatically
        console.log(`Successfully stopped ${selectedSandboxes.size} sandboxes`);
      }
    } catch (error) {
      console.error('Bulk stop failed:', error);
      setError('Bulk stop failed');
    } finally {
      setBulkActionLoading(false);
    }
  };

  const getFilteredSandboxes = () => {
    return sandboxes.filter(sandbox => {
      const matchesSearch = !searchQuery || 
        sandbox.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        sandbox.id.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesStatus = statusFilter === 'all' || sandbox.status === statusFilter;
      const matchesType = typeFilter === 'all' || sandbox.type === typeFilter;
      
      return matchesSearch && matchesStatus && matchesType;
    });
  };

  const saveFile = async () => {
    if (!selectedSandbox || !selectedFile) return;

    setSavingFile(true);
    try {
      const response = await FileService.saveFile(selectedSandbox, selectedFile.path, fileContent);

      if (response.success) {
        // Update file's last modified time
        setFiles(prev => prev.map(file =>
          file.path === selectedFile.path
            ? { ...file, lastModified: new Date() }
            : file
        ));
        loadSandboxStats();
      } else {
        setError(response.error || 'Failed to save file');
      }
    } catch (error) {
      console.error('Failed to save file:', error);
      setError('Failed to save file');
    } finally {
      setSavingFile(false);
    }
  };

  const executeCode = async () => {
    if (!selectedSandbox) {
      setError('Please select a sandbox first');
      return;
    }

    setExecuting(true);
    try {
      const codeToExecute = selectedFile ? fileContent : code;
      const response = await SandboxService.executeCode(selectedSandbox, codeToExecute);

      if (response.success && response.data) {
        const result: ExecutionResult = {
          output: response.data.output,
          error: response.data.error,
          exitCode: response.data.exitCode,
          executionTime: 0, // Not provided by service
          timestamp: new Date()
        };
        setExecutionResults(prev => [result, ...prev.slice(0, 9)]); // Keep last 10 results
      } else {
        setError(response.error || 'Failed to execute code');
      }
    } catch (error) {
      console.error('Failed to execute code:', error);
      setError('Failed to execute code');
    } finally {
      setExecuting(false);
    }
  };

  const getLanguageFromFile = (filePath: string): string => {
    const ext = filePath.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'js': return 'javascript';
      case 'ts': return 'typescript';
      case 'py': return 'python';
      case 'java': return 'java';
      case 'cpp': case 'cc': case 'cxx': return 'cpp';
      case 'c': return 'c';
      case 'go': return 'go';
      case 'rs': return 'rust';
      case 'php': return 'php';
      case 'rb': return 'ruby';
      default: return 'javascript';
    }
  };

  const filteredSandboxes = sandboxes.filter(sandbox => {
    const matchesSearch = !searchQuery ||
      sandbox.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      sandbox.type.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = statusFilter === 'all' || sandbox.status === statusFilter;
    const matchesType = typeFilter === 'all' || sandbox.type === typeFilter;

    return matchesSearch && matchesStatus && matchesType;
  });

  const selectedSandboxData = sandboxes.find(s => s.id === selectedSandbox);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'bg-green-500';
      case 'ready': return 'bg-blue-500';
      case 'creating': return 'bg-yellow-500';
      case 'stopped': return 'bg-gray-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return <CheckCircle className="h-4 w-4" />;
      case 'ready': return <Info className="h-4 w-4" />;
      case 'creating': return <Loader2 className="h-4 w-4 animate-spin" />;
      case 'stopped': return <Square className="h-4 w-4" />;
      case 'error': return <XCircle className="h-4 w-4" />;
      default: return <AlertCircle className="h-4 w-4" />;
    }
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Advanced Sandbox Manager
            </h1>
            <Badge variant="secondary" className="flex items-center gap-1">
              <Database className="h-3 w-3" />
              {systemStats.totalSandboxes} Sandboxes
            </Badge>
            <Badge variant="outline" className="flex items-center gap-1">
              <Globe className="h-3 w-3" />
              {systemStats.runningSandboxes} Running
            </Badge>
            <Badge 
              variant={wsConnected ? "default" : "destructive"} 
              className="flex items-center gap-1"
            >
              <div className={cn(
                "h-2 w-2 rounded-full",
                wsConnected ? "bg-green-500" : "bg-red-500"
              )} />
              {wsConnected ? "Live" : "Offline"}
            </Badge>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setActiveTab('sandboxes')}
              title="Manage Sandboxes"
            >
              <Database className="h-4 w-4" />
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={() => loadSandboxes()}
              disabled={loading}
            >
              <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>

            <Button onClick={() => setShowCreateDialog(!showCreateDialog)}>
              <Plus className="h-4 w-4 mr-2" />
              New Sandbox
            </Button>
          </div>

          {showCreateDialog && (
            <Card className="p-4 mt-4">
              <h3 className="font-medium mb-4">Create New Sandbox</h3>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Sandbox Name</label>
                  <Input
                    placeholder="Enter sandbox name"
                    value={newSandboxName}
                    onChange={(e) => setNewSandboxName(e.target.value)}
                  />
                </div>

                <div>
                  <label className="text-sm font-medium">Type</label>
                  <Select value={newSandboxType} onValueChange={(value: any) => setNewSandboxType(value)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="react">React</SelectItem>
                      <SelectItem value="vue">Vue.js</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="text-sm font-medium">Template (Optional)</label>
                  <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
                    <SelectTrigger>
                      <SelectValue placeholder="Choose a template" />
                    </SelectTrigger>
                    <SelectContent>
                      {SANDBOX_TEMPLATES.filter(t => t.type === newSandboxType).map(template => (
                        <SelectItem key={template.id} value={template.id}>
                          {template.name} - {template.description}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex gap-2 pt-4">
                  <Button
                    onClick={createSandbox}
                    disabled={creating || !newSandboxName.trim()}
                    className="flex-1"
                  >
                    {creating ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <Plus className="h-4 w-4 mr-2" />
                        Create Sandbox
                      </>
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setShowCreateDialog(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive" className="m-4 mx-6 mb-0">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar Navigation */}
        <div className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Navigation
            </h2>
          </div>

          <nav className="flex-1 p-4">
            <div className="space-y-2">
              <button
                onClick={() => setActiveTab('sandboxes')}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors",
                  activeTab === 'sandboxes'
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400"
                    : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                )}
              >
                <Database className="h-5 w-5" />
                Sandboxes
              </button>

              <button
                onClick={() => setActiveTab('overview')}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors",
                  activeTab === 'overview'
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400"
                    : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                )}
              >
                <Info className="h-5 w-5" />
                Overview
              </button>

              <button
                onClick={() => setActiveTab('files')}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors",
                  activeTab === 'files'
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400"
                    : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                )}
              >
                <FileText className="h-5 w-5" />
                Files
              </button>

              <button
                onClick={() => setActiveTab('code')}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors",
                  activeTab === 'code'
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400"
                    : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                )}
              >
                <Code className="h-5 w-5" />
                Code
              </button>

              <button
                onClick={() => setActiveTab('preview')}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors",
                  activeTab === 'preview'
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400"
                    : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-700"
                )}
              >
                <Globe className="h-5 w-5" />
                Preview
              </button>
            </div>
          </nav>

          {/* Sandbox Info in Sidebar */}
          {selectedSandboxData && (
            <div className="p-4 border-t border-gray-200 dark:border-gray-700">
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    Current Sandbox
                  </p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {selectedSandboxData.name || selectedSandboxData.id}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <div className={cn(
                    "h-2 w-2 rounded-full",
                    getStatusColor(selectedSandboxData.status)
                  )} />
                  <span className="text-xs text-gray-600 dark:text-gray-400 capitalize">
                    {selectedSandboxData.status}
                  </span>
                </div>

                <div className="text-xs text-gray-500 dark:text-gray-400">
                  {selectedSandboxData.type.toUpperCase()}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col">
          {selectedSandboxData ? (
            <div className="flex-1 flex flex-col">
              {/* Content Header */}
              <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white capitalize">
                    {activeTab}
                  </h2>

                  {activeTab === 'sandboxes' && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadSandboxes()}
                        disabled={loading}
                      >
                        <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
                      </Button>
                    </div>
                  )}
                </div>
              </div>

              {/* Content Body */}
              <div className="flex-1 overflow-hidden">
                {activeTab === 'sandboxes' && (
                  <div className="h-full flex flex-col">
                    {/* Search and Filters */}
                    <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                      <div className="space-y-4">
                        <div className="flex items-center gap-4">
                          <Input
                            placeholder="Search sandboxes..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="flex-1"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => loadSandboxes()}
                            disabled={loading}
                          >
                            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
                          </Button>
                        </div>

                        <div className="flex gap-2">
                          <Select value={statusFilter} onValueChange={setStatusFilter}>
                            <SelectTrigger className="flex-1">
                              <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All Status</SelectItem>
                              <SelectItem value="running">Running</SelectItem>
                              <SelectItem value="ready">Ready</SelectItem>
                              <SelectItem value="creating">Creating</SelectItem>
                              <SelectItem value="stopped">Stopped</SelectItem>
                              <SelectItem value="error">Error</SelectItem>
                            </SelectContent>
                          </Select>

                          <Select value={typeFilter} onValueChange={setTypeFilter}>
                            <SelectTrigger className="flex-1">
                              <SelectValue placeholder="Type" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All Types</SelectItem>
                              <SelectItem value="react">React</SelectItem>
                              <SelectItem value="vue">Vue</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>

                        {/* Bulk Actions */}
                        {filteredSandboxes.length > 0 && (
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={selectedSandboxes.size === filteredSandboxes.length && filteredSandboxes.length > 0}
                                onChange={handleSelectAll}
                                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                              />
                              <span className="text-sm text-gray-700 dark:text-gray-300">
                                Select All ({filteredSandboxes.length})
                              </span>
                            </div>

                            {selectedSandboxes.size > 0 && (
                              <div className="flex items-center gap-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-md border border-blue-200 dark:border-blue-800">
                                <span className="text-sm text-blue-700 dark:text-blue-300">
                                  {selectedSandboxes.size} selected
                                </span>
                                <div className="flex gap-1 ml-auto">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={bulkStop}
                                    disabled={bulkActionLoading}
                                    className="h-7 px-2 text-xs"
                                  >
                                    <Square className="h-3 w-3 mr-1" />
                                    Stop
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="destructive"
                                    onClick={bulkDelete}
                                    disabled={bulkActionLoading}
                                    className="h-7 px-2 text-xs"
                                  >
                                    <Trash2 className="h-3 w-3 mr-1" />
                                    Delete
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Sandboxes List */}
                    <ScrollArea className="flex-1">
                      <div className="p-6">
                        {loading ? (
                          <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin" />
                            <span className="ml-2">Loading sandboxes...</span>
                          </div>
                        ) : filteredSandboxes.length === 0 ? (
                          <div className="text-center py-8 text-gray-500">
                            <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p>No sandboxes found</p>
                            <p className="text-sm">Create your first sandbox to get started</p>
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {filteredSandboxes.map((sandbox) => (
                              <Card
                                key={sandbox.id}
                                className={cn(
                                  "cursor-pointer transition-all hover:shadow-md",
                                  selectedSandbox === sandbox.id ? "ring-2 ring-blue-500" : "hover:bg-gray-50 dark:hover:bg-gray-800",
                                  selectedSandboxes.has(sandbox.id) ? "ring-2 ring-green-500 bg-green-50 dark:bg-green-900/20" : ""
                                )}
                                onClick={(e) => {
                                  // Don't select sandbox if clicking on checkbox or buttons
                                  if ((e.target as HTMLElement).closest('input[type="checkbox"], button')) {
                                    return;
                                  }
                                  setSelectedSandbox(sandbox.id);
                                }}
                              >
                                <CardContent className="p-4">
                                  <div className="flex items-start gap-3">
                                    <input
                                      type="checkbox"
                                      checked={selectedSandboxes.has(sandbox.id)}
                                      onChange={() => handleSelectSandbox(sandbox.id)}
                                      className="mt-1 h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
                                    />
                                    <div className="flex-1 min-w-0">
                                      {editingSandbox === sandbox.id ? (
                                        <div className="space-y-2">
                                          <Input
                                            value={editName}
                                            onChange={(e) => setEditName(e.target.value)}
                                            placeholder="Enter sandbox name"
                                            className="text-sm"
                                          />
                                          <div className="flex gap-1">
                                            <Button
                                              size="sm"
                                              onClick={() => updateSandbox(sandbox.id, { name: editName })}
                                              className="h-6 px-2 text-xs"
                                            >
                                              Save
                                            </Button>
                                            <Button
                                              size="sm"
                                              variant="outline"
                                              onClick={() => {
                                                setEditingSandbox(null);
                                                setEditName('');
                                              }}
                                              className="h-6 px-2 text-xs"
                                            >
                                              Cancel
                                            </Button>
                                          </div>
                                        </div>
                                      ) : (
                                        <>
                                          <h3 className="font-medium text-sm truncate">
                                            {sandbox.name || `${sandbox.type} Sandbox`}
                                          </h3>
                                          <p className="text-xs text-gray-500">
                                            {new Date(sandbox.createdAt).toLocaleDateString()}
                                          </p>
                                        </>
                                      )}
                                    </div>

                                    <div className="flex gap-1">
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => {
                                          setEditingSandbox(sandbox.id);
                                          setEditName(sandbox.name || '');
                                        }}
                                      >
                                        <Edit className="h-3 w-3" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => startPreview(sandbox.id)}
                                      >
                                        <Eye className="h-3 w-3" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => stopPreview(sandbox.id)}
                                      >
                                        <Square className="h-3 w-3" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => stopSandbox(sandbox.id)}
                                        title="Stop Sandbox"
                                      >
                                        <X className="h-3 w-3" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => deleteSandbox(sandbox.id)}
                                        className="text-red-600"
                                      >
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </div>

                                  <div className="flex items-center justify-between mt-3">
                                    <Badge
                                      variant="secondary"
                                      className={cn("text-xs flex items-center gap-1", getStatusColor(sandbox.status))}
                                    >
                                      {getStatusIcon(sandbox.status)}
                                      {sandbox.status}
                                    </Badge>

                                    <div className="text-xs text-gray-500">
                                      {sandbox.stats?.files || 0} files
                                    </div>
                                  </div>

                                  {sandbox.preview && (
                                    <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                                      <div className="flex items-center gap-1 text-xs text-gray-500">
                                        <Globe className="h-3 w-3" />
                                        <span className="truncate">{sandbox.preview.url}</span>
                                      </div>
                                    </div>
                                  )}
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        )}
                      </div>
                    </ScrollArea>
                  </div>
                )}

                {activeTab === 'overview' && (
                  <div className="p-6">
                    <div className="grid grid-cols-2 gap-6 h-full">
                      {/* Sandbox Info */}
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2">
                            <Database className="h-5 w-5" />
                            Sandbox Information
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <label className="text-sm font-medium text-gray-500">Name</label>
                              <p className="text-sm">{selectedSandboxData.name || 'Unnamed'}</p>
                            </div>
                            <div>
                              <label className="text-sm font-medium text-gray-500">Type</label>
                              <p className="text-sm capitalize">{selectedSandboxData.type}</p>
                            </div>
                            <div>
                              <label className="text-sm font-medium text-gray-500">Status</label>
                              <Badge className={cn("text-xs", getStatusColor(selectedSandboxData.status))}>
                                {selectedSandboxData.status}
                              </Badge>
                            </div>
                            <div>
                              <label className="text-sm font-medium text-gray-500">Created</label>
                              <p className="text-sm">{new Date(selectedSandboxData.createdAt).toLocaleDateString()}</p>
                            </div>
                          </div>

                          {selectedSandboxData.preview && (
                            <div className="pt-4 border-t">
                              <label className="text-sm font-medium text-gray-500">Preview URL</label>
                              <div className="flex items-center gap-2 mt-1">
                                <code className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded flex-1">
                                  {selectedSandboxData.preview.url}
                                </code>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => window.open(selectedSandboxData.preview?.url, '_blank')}
                                >
                                  <ExternalLink className="h-3 w-3" />
                                </Button>
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>

                      {/* Quick Actions */}
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2">
                            <Zap className="h-5 w-5" />
                            Quick Actions
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="grid grid-cols-3 gap-3">
                            <Button
                              onClick={() => startPreview(selectedSandboxData.id)}
                              disabled={selectedSandboxData.status === 'running' || startingPreview}
                              className="h-auto py-3 flex flex-col items-center gap-2"
                            >
                              <Eye className="h-5 w-5" />
                              <span className="text-xs">Start Preview</span>
                            </Button>

                            <Button
                              onClick={() => stopPreview(selectedSandboxData.id)}
                              disabled={selectedSandboxData.status !== 'running'}
                              variant="outline"
                              className="h-auto py-3 flex flex-col items-center gap-2"
                            >
                              <Square className="h-5 w-5" />
                              <span className="text-xs">Stop Preview</span>
                            </Button>

                            <Button
                              onClick={() => stopSandbox(selectedSandboxData.id)}
                              disabled={selectedSandboxData.status === 'stopped' || selectedSandboxData.status === 'creating'}
                              variant="outline"
                              className="h-auto py-3 flex flex-col items-center gap-2"
                            >
                              <X className="h-5 w-5" />
                              <span className="text-xs">Stop Sandbox</span>
                            </Button>

                            <Button
                              onClick={() => setActiveTab('files')}
                              variant="outline"
                              className="h-auto py-3 flex flex-col items-center gap-2"
                            >
                              <FileText className="h-5 w-5" />
                              <span className="text-xs">Manage Files</span>
                            </Button>

                            <Button
                              onClick={() => setActiveTab('code')}
                              variant="outline"
                              className="h-auto py-3 flex flex-col items-center gap-2"
                            >
                              <Code className="h-5 w-5" />
                              <span className="text-xs">Write Code</span>
                            </Button>
                          </div>
                        </CardContent>
                      </Card>

                      {/* Stats */}
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2">
                            <Cpu className="h-5 w-5" />
                            Statistics
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-4">
                            <div className="flex justify-between items-center">
                              <span className="text-sm text-gray-500">Files</span>
                              <span className="font-medium">{selectedSandboxData.stats?.files || 0}</span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-sm text-gray-500">Size</span>
                              <span className="font-medium">{selectedSandboxData.stats?.size || '0 B'}</span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-sm text-gray-500">Last Modified</span>
                              <span className="font-medium text-xs">
                                {selectedSandboxData.stats?.lastModified
                                  ? new Date(selectedSandboxData.stats.lastModified).toLocaleDateString()
                                  : 'Never'
                                }
                              </span>
                            </div>
                          </div>
                        </CardContent>
                      </Card>

                      {/* Activity Log */}
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2">
                            <Clock className="h-5 w-5" />
                            Recent Activity
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                            <div className="flex items-center gap-2">
                              <CheckCircle className="h-3 w-3 text-green-500" />
                              <span>Sandbox created</span>
                              <span className="text-xs ml-auto">
                                {new Date(selectedSandboxData.createdAt).toLocaleDateString()}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <Info className="h-3 w-3 text-blue-500" />
                              <span>Last activity</span>
                              <span className="text-xs ml-auto">
                                {new Date(selectedSandboxData.lastActivity).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  </div>
                )}

                {activeTab === 'files' && (
                  <div className="h-full flex flex-col">
                    {/* File Toolbar */}
                    <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                          <h3 className="font-medium">Files</h3>
                          <Input
                            placeholder="Search files..."
                            value={fileSearch}
                            onChange={(e) => setFileSearch(e.target.value)}
                            className="w-64"
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => loadFiles()}
                            disabled={loadingFiles}
                          >
                            <RefreshCw className={cn("h-4 w-4", loadingFiles && "animate-spin")} />
                          </Button>
                          <Button variant="outline" size="sm">
                            <Upload className="h-4 w-4 mr-2" />
                            Upload
                          </Button>
                          <Button variant="outline" size="sm">
                            <FilePlus className="h-4 w-4 mr-2" />
                            New File
                          </Button>
                        </div>
                      </div>
                    </div>

                    {/* Files List and Editor */}
                    <div className="flex-1 flex">
                      {/* Files List */}
                      <div className="w-[28rem] bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700">
                        <ScrollArea className="h-full">
                          <div className="p-4">
                            {loadingFiles ? (
                              <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-5 w-5 animate-spin" />
                                <span className="ml-2">Loading files...</span>
                              </div>
                            ) : (
                              <div className="space-y-1">
                                {files
                                  .filter(file =>
                                    !fileSearch ||
                                    file.name.toLowerCase().includes(fileSearch.toLowerCase())
                                  )
                                  .map((file) => (
                                    <div
                                      key={file.path}
                                      className={cn(
                                        "flex items-center gap-2 p-2 rounded cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700",
                                        selectedFile?.path === file.path && "bg-blue-50 dark:bg-blue-900/20"
                                      )}
                                      onClick={() => setSelectedFile(file)}
                                    >
                                      <FileText className="h-4 w-4 text-gray-400" />
                                      <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate">{file.name}</p>
                                        <p className="text-xs text-gray-500">
                                          {file.size ? `${(file.size / 1024).toFixed(1)} KB` : '0 B'}
                                        </p>
                                      </div>
                                    </div>
                                  ))
                                }
                              </div>
                            )}
                          </div>
                        </ScrollArea>
                      </div>

                      {/* File Editor */}
                      <div className="flex-1 flex flex-col">
                        {selectedFile ? (
                          <>
                            <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-3">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-4">
                                  <h4 className="font-medium">{selectedFile.name}</h4>
                                  <Badge variant="outline" className="text-xs">
                                    {getLanguageFromFile(selectedFile.path)}
                                  </Badge>
                                </div>
                                <Button
                                  onClick={saveFile}
                                  disabled={savingFile}
                                  size="sm"
                                >
                                  {savingFile ? (
                                    <>
                                      <Loader2 className="h-3 w-3 mr-2 animate-spin" />
                                      Saving...
                                    </>
                                  ) : (
                                    <>
                                      <Save className="h-3 w-3 mr-2" />
                                      Save
                                    </>
                                  )}
                                </Button>
                              </div>
                            </div>

                            <Textarea
                              value={fileContent}
                              onChange={(e) => setFileContent(e.target.value)}
                              className="flex-1 font-mono text-sm p-4 border-0 rounded-none resize-none"
                              placeholder="File content will appear here..."
                            />
                          </>
                        ) : (
                          <div className="flex-1 flex items-center justify-center text-gray-500">
                            <div className="text-center">
                              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                              <p>Select a file to edit</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'code' && (
                  <div className="h-full flex flex-col">
                    <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-3">
                      <div className="flex items-center justify-between">
                        <h3 className="font-medium">Code Execution</h3>
                        <div className="flex items-center gap-2">
                          <Button
                            onClick={executeCode}
                            disabled={executing}
                          >
                            {executing ? (
                              <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Running...
                              </>
                            ) : (
                              <>
                                <Play className="h-4 w-4 mr-2" />
                                Run Code
                              </>
                            )}
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => setShowTerminal(!showTerminal)}
                          >
                            <Terminal className="h-4 w-4 mr-2" />
                            Terminal
                          </Button>
                        </div>
                      </div>
                    </div>

                    <div className="flex-1 flex">
                      <div className="flex-1 flex flex-col">
                        <Textarea
                          value={selectedFile ? fileContent : code}
                          onChange={(e) => selectedFile ? setFileContent(e.target.value) : setCode(e.target.value)}
                          className="flex-1 font-mono text-sm p-4 border-0 rounded-none resize-none"
                          placeholder={selectedFile ? "Edit file content..." : "// Write your code here..."}
                          disabled={!selectedSandbox}
                        />

                        {showTerminal && (
                          <div className="h-32 border-t border-gray-200 dark:border-gray-700 bg-black text-green-400 p-4 font-mono text-sm">
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-white">Terminal Output</span>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setTerminalOutput('')}
                                className="text-white hover:bg-gray-800"
                              >
                                Clear
                              </Button>
                            </div>
                            <ScrollArea className="h-full">
                              <pre className="whitespace-pre-wrap">{terminalOutput || 'No output yet...'}</pre>
                            </ScrollArea>
                          </div>
                        )}
                      </div>

                      {executionResults.length > 0 && (
                        <div className="w-96 border-l border-gray-200 dark:border-gray-700 flex flex-col">
                          <div className="bg-white dark:bg-gray-800 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                            <div className="flex items-center justify-between">
                              <span className="text-sm font-medium">Execution Results</span>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setExecutionResults([])}
                              >
                                Clear
                              </Button>
                            </div>
                          </div>
                          <ScrollArea className="flex-1">
                            <div className="p-4 space-y-4">
                              {executionResults.map((result, index) => (
                                <Card key={index} className="p-3">
                                  <div className="flex items-center justify-between mb-2">
                                    <Badge variant={result.exitCode === 0 ? "default" : "destructive"}>
                                      Exit Code: {result.exitCode}
                                    </Badge>
                                    <span className="text-xs text-gray-500">
                                      {result.timestamp.toLocaleTimeString()}
                                    </span>
                                  </div>
                                  <div className="space-y-2">
                                    {result.output && (
                                      <div>
                                        <label className="text-xs font-medium text-gray-500">Output</label>
                                        <pre className="text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded mt-1 whitespace-pre-wrap">
                                          {result.output}
                                        </pre>
                                      </div>
                                    )}
                                    {result.error && (
                                      <div>
                                        <label className="text-xs font-medium text-red-500">Error</label>
                                        <pre className="text-xs bg-red-50 dark:bg-red-900/20 p-2 rounded mt-1 whitespace-pre-wrap text-red-600">
                                          {result.error}
                                        </pre>
                                      </div>
                                    )}
                                    <div className="text-xs text-gray-500">
                                      Execution time: {result.executionTime}ms
                                    </div>
                                  </div>
                                </Card>
                              ))}
                            </div>
                          </ScrollArea>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {activeTab === 'preview' && (
                  <div className="h-full flex">
                    {/* Chat Panel - Left side */}
                    <div className="w-2/3 border-r border-gray-200 dark:border-gray-700 flex flex-col">
                      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3">
                        <h3 className="font-medium text-sm">AI Assistant</h3>
                      </div>
                      <div className="flex-1">
                        <AIChatPanel
                          selectedSandbox={selectedSandboxData}
                          currentFile={selectedFile?.path}
                          fileContent={fileContent}
                          onApplyCode={async (code: string, filePath?: string) => {
                            if (!selectedSandbox) return;

                            const targetPath = filePath || selectedFile?.path;
                            if (!targetPath) return;

                            try {
                              const response = await FileService.saveFile(selectedSandbox, targetPath, code);

                              if (response.success) {
                                // If we're saving to the currently selected file, update the local state
                                if (selectedFile && targetPath === selectedFile.path) {
                                  setFileContent(code);
                                }
                                // Refresh files list to show updated content
                                loadFiles();
                              } else {
                                console.error('Failed to save file:', response.error);
                              }
                            } catch (error) {
                              console.error('Error saving file:', error);
                            }
                          }}
                          onExecuteCode={async () => {
                            // Execute the current code/file content
                            await executeCode();
                          }}
                          onStartPreview={async () => {
                            // Start preview for the selected sandbox
                            if (selectedSandbox) {
                              await startPreview(selectedSandbox);
                            }
                          }}
                          onStopPreview={async (sandboxId: string) => {
                            // Implement stop preview functionality
                            try {
                              const response = await fetch(`/api/sandbox/preview?sandboxId=${sandboxId}`, {
                                method: 'DELETE'
                              });
                              if (response.ok) {
                                setSandboxes(prev => prev.map(s =>
                                  s.id === sandboxId
                                    ? { ...s, status: 'ready', preview: undefined }
                                    : s
                                ));
                                loadSystemStats();
                              }
                            } catch (error) {
                              console.error('Failed to stop preview:', error);
                            }
                          }}
                          selectedModel={selectedModel}
                          onModelChange={setSelectedModel}
                          className="h-full border-0 rounded-none"
                        />
                      </div>
                    </div>

                    {/* Preview Area - Right side */}
                    <div className="flex-1 flex flex-col">
                      <div className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-3">
                        <div className="flex items-center justify-between">
                          <h3 className="font-medium">Live Preview</h3>
                          <div className="flex items-center gap-2">
                            {selectedSandboxData.preview?.url && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => selectedSandboxData.preview && window.open(selectedSandboxData.preview.url, '_blank')}
                              >
                                <ExternalLink className="h-4 w-4 mr-2" />
                                Open in New Tab
                              </Button>
                            )}
                            <Button
                              onClick={() => startPreview(selectedSandboxData.id)}
                              disabled={selectedSandboxData.status === 'running' || startingPreview}
                            >
                              {startingPreview ? (
                                <>
                                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                  Starting...
                                </>
                              ) : (
                                <>
                                  <Eye className="h-4 w-4 mr-2" />
                                  Start Preview
                                </>
                              )}
                            </Button>
                            <Button
                              variant="outline"
                              onClick={() => stopPreview(selectedSandboxData.id)}
                              disabled={selectedSandboxData.status !== 'running'}
                            >
                              <Square className="h-4 w-4 mr-2" />
                              Stop Preview
                            </Button>
                          </div>
                        </div>
                      </div>

                      <div className="flex-1 bg-white dark:bg-gray-950 p-4">
                        {previewHtml ? (
                          <div
                            dangerouslySetInnerHTML={{ __html: previewHtml }}
                            className="w-full h-full rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700"
                          />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center text-gray-400">
                            <div className="text-center">
                              <Eye className="h-12 w-12 mx-auto mb-4 opacity-50" />
                              <p>Click "Start Preview" to see your sandbox in action</p>
                              {selectedSandboxData.status === 'running' && (
                                <p className="text-sm mt-2">Sandbox is running, preview should load shortly...</p>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <Database className="h-16 w-16 mx-auto mb-4 opacity-50" />
                <h3 className="text-lg font-medium mb-2">No Sandbox Selected</h3>
                <p>Select a sandbox from the sidebar to get started</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}