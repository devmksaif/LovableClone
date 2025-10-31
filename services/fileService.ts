import { apiClient, ApiResponse } from '@/lib/api-client';

export interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size?: number;
  lastModified?: Date;
  content?: string;
}

export class FileService {
  /**
   * Get all files in a sandbox
   */
  static async getFiles(sandboxId: string): Promise<ApiResponse<{ files: FileItem[] }>> {
    return apiClient.get(`/sandbox/files/${sandboxId}`);
  }

  /**
   * Get file content
   */
  static async getFileContent(sandboxId: string, filePath: string): Promise<ApiResponse<{ content: string }>> {
    return apiClient.readFile(`/sandbox/${sandboxId}/files/${encodeURIComponent(filePath)}`);
  }

  /**
   * Save file content
   */
  static async saveFile(sandboxId: string, filePath: string, content: string): Promise<ApiResponse<void>> {
    return apiClient.post(`/sandbox/${sandboxId}/files/${encodeURIComponent(filePath)}`, content);
  }

  /**
   * Create a new file
   */
  static async createFile(sandboxId: string, filePath: string, content: string = ''): Promise<ApiResponse<void>> {
    return this.saveFile(sandboxId, filePath, content);
  }

  /**
   * Delete a file
   */
  static async deleteFile(sandboxId: string, filePath: string): Promise<ApiResponse<void>> {
    return apiClient.delete(`/sandbox/${sandboxId}/files/${encodeURIComponent(filePath)}`);
  }

  /**
   * Upload a file
   */
  static async uploadFile(sandboxId: string, file: File, path: string): Promise<ApiResponse<void>> {
    const PYTHON_BACKEND_URL = process.env.NEXT_PUBLIC_PYTHON_BACKEND_URL || 'http://localhost:8000';
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', path);

    const response = await fetch(`${PYTHON_BACKEND_URL}/api/sandbox/${sandboxId}/upload`, {
      method: 'POST',
      body: formData
    });
    const data = await response.json();
    return {
      success: response.ok,
      data: response.ok ? data : undefined,
      error: response.ok ? undefined : data.error || 'Request failed'
    };
  }
}