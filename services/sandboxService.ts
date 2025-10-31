import { apiClient, ApiResponse } from '@/lib/api-client';

export interface Sandbox {
  id: string;
  name?: string;
  type: 'react' | 'vue';
  status: 'creating' | 'ready' | 'running' | 'stopped' | 'error';
  createdAt: Date;
  lastActivity: Date;
  metadata?: Record<string, any>;
  preview?: {
    url: string;
    port: number;
    status: string;
    iframeHtml?: string;
  };
  stats?: {
    files: number;
    size: string;
    lastModified: Date;
  };
}

export interface SystemStats {
  totalSandboxes: number;
  runningSandboxes: number;
  totalFiles: number;
  storageUsed: string;
}

export interface CreateSandboxRequest {
  name: string;
  type: 'react' | 'vue';
  template?: string;
}

export interface UpdateSandboxRequest {
  name?: string;
  [key: string]: any;
}

export class SandboxService {
  /**
   * Get all sandboxes
   */
  static async getSandboxes(): Promise<ApiResponse<{ sandboxes: Sandbox[] }>> {
    return apiClient.get('/sandbox');
  }

  /**
   * Create a new sandbox
   */
  static async createSandbox(request: CreateSandboxRequest): Promise<ApiResponse<Sandbox>> {
    return apiClient.post('/sandbox', request);
  }

  /**
   * Update an existing sandbox
   */
  static async updateSandbox(sandboxId: string, updates: UpdateSandboxRequest): Promise<ApiResponse<Sandbox>> {
    return apiClient.put(`/sandbox/${sandboxId}`, updates);
  }

  /**
   * Delete a sandbox
   */
  static async deleteSandbox(sandboxId: string): Promise<ApiResponse<void>> {
    return apiClient.delete(`/sandbox/${sandboxId}`);
  }

  /**
   * Start preview for a sandbox
   */
  static async startPreview(sandboxId: string): Promise<ApiResponse<{ preview: { url: string; iframeHtml?: string } }>> {
    return apiClient.post(`/sandbox/preview?sandboxId=${sandboxId}`);
  }

  /**
   * Stop preview for a sandbox
   */
  static async stopPreview(sandboxId: string): Promise<ApiResponse<void>> {
    return apiClient.delete(`/sandbox/preview?sandboxId=${sandboxId}`);
  }

  /**
   * Stop a sandbox
   */
  static async stopSandbox(sandboxId: string): Promise<ApiResponse<void>> {
    return apiClient.post(`/sandbox/${sandboxId}/stop`);
  }

  /**
   * Get sandbox statistics
   */
  static async getSandboxStats(sandboxId: string): Promise<ApiResponse<{ stats: any }>> {
    return apiClient.get(`/sandbox/${sandboxId}/stats`);
  }

  /**
   * Get system statistics
   */
  static async getSystemStats(): Promise<ApiResponse<SystemStats>> {
    return apiClient.get('/sandbox/stats');
  }

  /**
   * Execute code in a sandbox
   */
  static async executeCode(sandboxId: string, code: string): Promise<ApiResponse<{ output: string; error: string; exitCode: number }>> {
    return apiClient.post('/sandbox/execute', { sandboxId, code });
  }

  /**
   * Bulk stop multiple sandboxes
   */
  static async bulkStopSandboxes(sandboxIds: string[]): Promise<ApiResponse<void>[]> {
    const stopPromises = sandboxIds.map(async (sandboxId) => {
      return apiClient.post(`/sandbox/${sandboxId}/stop`);
    });

    return Promise.all(stopPromises);
  }
}