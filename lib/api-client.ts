/**
 * API client that can switch between Next.js backend and Python FastAPI backend
 */

const PYTHON_BACKEND_URL = process.env.NEXT_PUBLIC_PYTHON_BACKEND_URL || 'http://localhost:8000';

export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface EnhancedSandboxMetadata {
  projectType?: string;
  frameworks?: string[];
  dependencies?: Record<string, any>;
  fileCount?: number;
  totalSize?: string;
  entryPoints?: string[];
  buildTools?: string[];
  recentActivity?: Record<string, any>;
  projectStructure?: Record<string, any>;
  fileStatistics?: Record<string, any>;
  sizeAnalysis?: Record<string, any>;
}

export interface SandboxContext {
  id: string;
  type: string;
  name?: string;
  status: string;
  metadata?: Record<string, any>;
  enhancedMetadata?: EnhancedSandboxMetadata;
  currentFile?: string;
  fileContent?: string;
}

export class ApiClient {
  private getBaseUrl(): string {
    return PYTHON_BACKEND_URL;
  }

  private getFullUrl(endpoint: string): string {
    // Add /api prefix if not already present
    const apiEndpoint = endpoint.startsWith('/api') ? endpoint : `/api${endpoint}`;
    return `${this.getBaseUrl()}${apiEndpoint}`;
  }

  async get<T = any>(endpoint: string): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(this.getFullUrl(endpoint));
      const data = await response.json();

      if (!response.ok) {
        return { success: false, error: data.error || 'Request failed' };
      }

      return { success: true, data };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }

  async post<T = any>(endpoint: string, body?: any): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(this.getFullUrl(endpoint), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await response.json();

      if (!response.ok) {
        return { success: false, error: data.error || 'Request failed' };
      }

      return { success: true, data };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }

  async put<T = any>(endpoint: string, body?: any): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(this.getFullUrl(endpoint), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: body ? JSON.stringify(body) : undefined,
      });

      const data = await response.json();
      return { success: response.ok, data: response.ok ? data : undefined, error: response.ok ? undefined : data.error || 'Request failed' };
    } catch (error) {
      console.error('API put error:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }

  async delete<T = any>(endpoint: string): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(this.getFullUrl(endpoint), {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data = await response.json();
      return { success: response.ok, data: response.ok ? data : undefined, error: response.ok ? undefined : data.error || 'Request failed' };
    } catch (error) {
      console.error('API delete error:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }

  async saveFile<T = any>(endpoint: string, content: string): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(this.getFullUrl(endpoint), {
        method: 'POST',
        headers: {
          'Content-Type': 'text/plain',
        },
        body: content,
      });

      const data = await response.json();
      return { success: response.ok, data: response.ok ? data : undefined, error: response.ok ? undefined : data.error || 'Request failed' };
    } catch (error) {
      console.error('API saveFile error:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }

  async readFile<T = any>(endpoint: string): Promise<ApiResponse<T>> {
    try {
      const response = await fetch(this.getFullUrl(endpoint));
      const data = await response.json();
      
      return { success: response.ok, data: response.ok ? data : undefined, error: response.ok ? undefined : data.error || 'Request failed' };
    } catch (error) {
      console.error('API readFile error:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }

  // Streaming POST request for chat
  async postStream(endpoint: string, body: any, onEvent: (event: any) => void): Promise<void> {
    try {
      const response = await fetch(this.getFullUrl(endpoint), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        onEvent({ type: 'error', data: { message: errorData.error || 'Request failed' } });
        return;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        onEvent({ type: 'error', data: { message: 'No response body' } });
        return;
      }

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const eventData = JSON.parse(line.slice(6));
              onEvent(eventData);
            } catch (e) {
              // Skip invalid JSON
              console.warn('Invalid SSE data:', line);
            }
          }
        }
      }
    } catch (error) {
      onEvent({
        type: 'error',
        data: { message: error instanceof Error ? error.message : 'Unknown error' }
      });
    }
  }

  // Fetch enhanced sandbox metadata
  async getEnhancedSandboxMetadata(sandboxId: string): Promise<ApiResponse<EnhancedSandboxMetadata>> {
    return this.get(`/api/sandbox/${sandboxId}?enhanced=true`);
  }

  // Refresh sandbox metadata
  async refreshSandboxMetadata(sandboxId: string): Promise<ApiResponse<any>> {
    return this.post(`/api/sandbox/${sandboxId}/refresh-metadata`);
  }

  // Get sandbox context for agents
  async getSandboxContext(sandboxId: string): Promise<ApiResponse<SandboxContext>> {
    return this.get(`/api/sandbox/${sandboxId}/context`);
  }

  // WebSocket streaming for chat
  async postWebSocket(endpoint: string, body: any, onEvent: (event: any) => void): Promise<() => void> {
    try {
      // Convert endpoint to WebSocket URL for Python backend
      const wsUrl = `${this.getBaseUrl().replace('http', 'ws')}${endpoint}`;

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connection opened');
        // Send initial message with session_id and enhanced metadata
        const initialMessage = {
          session_id: body.sessionId || 'default-session',
          ...body,
          // Include enhanced metadata context if available
          enhanced_context: body.sandbox_context?.enhancedMetadata || null,
          metadata_timestamp: new Date().toISOString()
        };
        ws.send(JSON.stringify(initialMessage));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Handle enhanced metadata events
          if (data.type === 'metadata_updated' || data.type === 'sandbox_context') {
            data.enhancedMetadata = data.metadata || data.enhancedMetadata;
            data.timestamp = new Date().toISOString();
          }
          
          // Add context information to all events
          if (data.type && !data.context) {
            data.context = {
              timestamp: new Date().toISOString(),
              enhanced: true
            };
          }
          
          onEvent(data);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
          onEvent({ type: 'error', message: 'Failed to parse message' });
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        onEvent({
          type: 'error',
          data: { message: 'WebSocket connection error' }
        });
      };

      ws.onclose = () => {
        console.log('WebSocket connection closed');
      };

      // Return cleanup function
      return () => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
        }
      };
    } catch (error) {
      onEvent({
        type: 'error',
        data: { message: error instanceof Error ? error.message : 'WebSocket initialization error' }
      });
      return () => {}; // Return empty cleanup function
    }
  }
}

export const apiClient = new ApiClient();
  