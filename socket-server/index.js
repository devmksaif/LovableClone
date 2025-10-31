import { createServer } from 'http';
import { Server } from 'socket.io';
import cors from 'cors';
import express from 'express';

const PORT = process.env.SOCKET_PORT || 3002;
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';

// Create HTTP server
const httpServer = createServer();

// Initialize Socket.IO with CORS
const io = new Server(httpServer, {
  cors: {
    origin: [FRONTEND_URL, 'http://localhost:3000', 'http://localhost:3001'],
    methods: ['GET', 'POST'],
    credentials: true
  },
  transports: ['websocket', 'polling']
});

// Store active connections and sessions
const activeConnections = new Map();
const sessionRooms = new Map();

// Socket connection handling
io.on('connection', (socket) => {
  console.log(`🔌 Client connected: ${socket.id}`);
  
  // Store connection info
  activeConnections.set(socket.id, {
    socket,
    sessionId: null,
    connectedAt: new Date()
  });

  // Handle session joining
  socket.on('join-session', (sessionId) => {
    console.log(`👤 Client ${socket.id} joining session: ${sessionId}`);
    
    // Leave previous session if any
    const connection = activeConnections.get(socket.id);
    if (connection && connection.sessionId) {
      socket.leave(connection.sessionId);
      console.log(`👋 Client ${socket.id} left previous session: ${connection.sessionId}`);
    }
    
    // Join new session
    socket.join(sessionId);
    connection.sessionId = sessionId;
    
    // Track session rooms
    if (!sessionRooms.has(sessionId)) {
      sessionRooms.set(sessionId, new Set());
    }
    sessionRooms.get(sessionId).add(socket.id);
    
    console.log(`✅ Client ${socket.id} joined session: ${sessionId}`);
    
    // Notify client of successful join
    socket.emit('session-joined', { sessionId, timestamp: new Date() });
  });

  // Handle session leaving
  socket.on('leave-session', (sessionId) => {
    console.log(`👋 Client ${socket.id} leaving session: ${sessionId}`);
    socket.leave(sessionId);
    
    const connection = activeConnections.get(socket.id);
    if (connection) {
      connection.sessionId = null;
    }
    
    // Remove from session rooms tracking
    if (sessionRooms.has(sessionId)) {
      sessionRooms.get(sessionId).delete(socket.id);
      if (sessionRooms.get(sessionId).size === 0) {
        sessionRooms.delete(sessionId);
      }
    }
    
    socket.emit('session-left', { sessionId, timestamp: new Date() });
  });

  // Handle real-time events from the chat API
  socket.on('stream-event', (data) => {
    const { sessionId, ...eventData } = data;
    if (sessionId) {
      console.log(`📡 Broadcasting event to session ${sessionId}:`, eventData.type);
      socket.to(sessionId).emit('stream-event', eventData);
    }
  });

  // Handle ping/pong for connection health
  socket.on('ping', () => {
    socket.emit('pong', { timestamp: new Date() });
  });

  // Handle disconnection
  socket.on('disconnect', (reason) => {
    console.log(`🔌 Client disconnected: ${socket.id}, reason: ${reason}`);
    
    const connection = activeConnections.get(socket.id);
    if (connection && connection.sessionId) {
      // Remove from session rooms tracking
      const sessionId = connection.sessionId;
      if (sessionRooms.has(sessionId)) {
        sessionRooms.get(sessionId).delete(socket.id);
        if (sessionRooms.get(sessionId).size === 0) {
          sessionRooms.delete(sessionId);
        }
      }
    }
    
    activeConnections.delete(socket.id);
  });
});

// API endpoints for external services to emit events
const app = express();

app.use(express.json());
app.use(cors({
  origin: [FRONTEND_URL, 'http://localhost:3000', 'http://localhost:3001'],
  credentials: true
}));

// Endpoint for Next.js API to emit events
app.post('/emit', (req, res) => {
  const { sessionId, event, data } = req.body;
  
  if (!sessionId || !event) {
    return res.status(400).json({ error: 'sessionId and event are required' });
  }
  
  console.log(`📡 Emitting ${event} to session ${sessionId}`);
  io.to(sessionId).emit(event, data);
  
  res.json({ 
    success: true, 
    sessionId, 
    event,
    clientsInSession: sessionRooms.get(sessionId)?.size || 0
  });
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    uptime: process.uptime(),
    connections: activeConnections.size,
    sessions: sessionRooms.size,
    timestamp: new Date()
  });
});

// Status endpoint
app.get('/status', (req, res) => {
  const sessions = {};
  sessionRooms.forEach((clients, sessionId) => {
    sessions[sessionId] = clients.size;
  });
  
  res.json({
    totalConnections: activeConnections.size,
    activeSessions: sessionRooms.size,
    sessions,
    uptime: process.uptime()
  });
});

// Mount express app on the same server
httpServer.on('request', app);

// Start the server
httpServer.listen(PORT, () => {
  console.log(`🚀 Socket server running on port ${PORT}`);
  console.log(`📡 Accepting connections from: ${FRONTEND_URL}`);
  console.log(`🔗 Health check: http://localhost:${PORT}/health`);
  console.log(`📊 Status: http://localhost:${PORT}/status`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('🛑 Received SIGTERM, shutting down gracefully...');
  httpServer.close(() => {
    console.log('✅ Socket server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('🛑 Received SIGINT, shutting down gracefully...');
  httpServer.close(() => {
    console.log('✅ Socket server closed');
    process.exit(0);
  });
});

export default { io, httpServer };