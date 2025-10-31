import { Server as NetServer } from 'http';
import { NextApiResponse } from 'next';
import { Server as ServerIO } from 'socket.io';

export type NextApiResponseServerIo = NextApiResponse & {
  socket: any & {
    server: NetServer & {
      io: ServerIO;
    };
  };
};

export const initSocket = (httpServer: NetServer) => {
  const io = new ServerIO(httpServer, {
    path: '/api/socket',
    cors: {
      origin: '*',
      methods: ['GET', 'POST'],
    },
  });

  // Store active connections
  const activeConnections = new Map<string, any>();

  io.on('connection', (socket) => {
    console.log('🔌 Client connected:', socket.id);

    socket.on('join-session', (sessionId: string) => {
      console.log(`👤 Client ${socket.id} joined session: ${sessionId}`);
      socket.join(sessionId);
      activeConnections.set(socket.id, { sessionId, socket });
    });

    socket.on('leave-session', (sessionId: string) => {
      console.log(`👋 Client ${socket.id} left session: ${sessionId}`);
      socket.leave(sessionId);
    });

    socket.on('disconnect', () => {
      console.log('🔌 Client disconnected:', socket.id);
      activeConnections.delete(socket.id);
    });
  });

  // Function to emit events to specific sessions
  const emitToSession = (sessionId: string, event: string, data: any) => {
    io.to(sessionId).emit(event, data);
  };

  // Function to emit events to all connected clients
  const emitToAll = (event: string, data: any) => {
    io.emit(event, data);
  };

  return {
    io,
    emitToSession,
    emitToAll,
    getActiveConnections: () => activeConnections,
  };
};