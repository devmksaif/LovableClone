'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { io, Socket } from 'socket.io-client';

interface SocketContextType {
  socket: Socket | null;
  isConnected: boolean;
  joinSession: (sessionId: string) => void;
  leaveSession: (sessionId: string) => void;
}

const SocketContext = createContext<SocketContextType>({
  socket: null,
  isConnected: false,
  joinSession: () => {},
  leaveSession: () => {},
});

export function SocketProvider({ children }: { children: React.ReactNode }) {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // Initialize socket connection to separate socket server
    const socketInstance = io(process.env.NODE_ENV === 'production' ? '' : 'http://localhost:3002', {
      transports: ['websocket', 'polling'],
    });

    socketInstance.on('connect', () => {
      console.log('🔌 Connected to socket server');
      setIsConnected(true);
    });

    socketInstance.on('disconnect', () => {
      console.log('🔌 Disconnected from socket server');
      setIsConnected(false);
    });

    socketInstance.on('connect_error', (error) => {
      console.error('🔌 Socket connection error:', error);
    });

    setSocket(socketInstance);

    return () => {
      socketInstance.disconnect();
    };
  }, []);

  const joinSession = (sessionId: string) => {
    if (socket && isConnected) {
      socket.emit('join-session', sessionId);
    }
  };

  const leaveSession = (sessionId: string) => {
    if (socket && isConnected) {
      socket.emit('leave-session', sessionId);
    }
  };

  return (
    <SocketContext.Provider value={{ socket, isConnected, joinSession, leaveSession }}>
      {children}
    </SocketContext.Provider>
  );
}

export function useSocket() {
  const context = useContext(SocketContext);
  if (!context) {
    throw new Error('useSocket must be used within a SocketProvider');
  }
  return context;
}