// Utility to emit events to the separate socket server
const SOCKET_SERVER_URL = process.env.SOCKET_SERVER_URL || 'http://localhost:3002';

export async function emitToSocketServer(sessionId: string, event: string, data: any) {
  try {
    const response = await fetch(`${SOCKET_SERVER_URL}/emit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sessionId,
        event,
        data
      })
    });

    if (!response.ok) {
      throw new Error(`Socket server responded with status: ${response.status}`);
    }

    const result = await response.json();
    console.log(`📡 Successfully emitted ${event} to session ${sessionId}, clients: ${result.clientsInSession}`);
    return result;
  } catch (error) {
    console.error(`❌ Failed to emit ${event} to socket server:`, error);
    throw error;
  }
}

export async function getSocketServerStatus() {
  try {
    const response = await fetch(`${SOCKET_SERVER_URL}/status`);
    if (!response.ok) {
      throw new Error(`Socket server status check failed: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error('❌ Failed to get socket server status:', error);
    throw error;
  }
}

export async function checkSocketServerHealth() {
  try {
    const response = await fetch(`${SOCKET_SERVER_URL}/health`);
    if (!response.ok) {
      throw new Error(`Socket server health check failed: ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error('❌ Socket server health check failed:', error);
    throw error;
  }
}