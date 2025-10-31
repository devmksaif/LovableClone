export interface WebSocketMessage {
  type: 'created' | 'updated' | 'deleted' | 'initial';
  sandbox?: any;
  sandboxes?: any[];
  timestamp?: string;
}

export interface WebSocketCallbacks {
  onOpen?: () => void;
  onMessage?: (data: WebSocketMessage) => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

export class SocketService {
  private ws: WebSocket | null = null;
  private isConnected = false;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private callbacks: WebSocketCallbacks = {};

  /**
   * Connect to WebSocket
   */
  connect(url: string = 'ws://localhost:8000/ws/sandbox-updates', callbacks: WebSocketCallbacks = {}): void {
    if (this.ws && this.isConnected) {
      console.log('WebSocket already connected');
      return;
    }

    this.callbacks = callbacks;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.callbacks.onOpen?.();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.callbacks.onMessage?.(data);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
          this.callbacks.onError?.(event);
        }
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.isConnected = false;
        this.callbacks.onClose?.();
        this.attemptReconnect(url);
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.callbacks.onError?.(error);
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      this.callbacks.onError?.(error as Event);
    }
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.isConnected = false;
    }
  }

  /**
   * Send a message through WebSocket
   */
  send(data: any): void {
    if (this.ws && this.isConnected) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn('WebSocket is not connected');
    }
  }

  /**
   * Check if WebSocket is connected
   */
  isWebSocketConnected(): boolean {
    return this.isConnected;
  }

  /**
   * Get WebSocket instance
   */
  getWebSocket(): WebSocket | null {
    return this.ws;
  }

  /**
   * Attempt to reconnect to WebSocket
   */
  private attemptReconnect(url: string): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff

    console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => {
      this.connect(url, this.callbacks);
    }, delay);
  }

  /**
   * Update callbacks
   */
  updateCallbacks(callbacks: Partial<WebSocketCallbacks>): void {
    this.callbacks = { ...this.callbacks, ...callbacks };
  }
}

// Singleton instance for global use
export const socketService = new SocketService();