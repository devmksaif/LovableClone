// Simple test to verify socket functionality
// Run with: node test-socket.js

const io = require('socket.io-client');

console.log('🧪 Testing Socket.IO connection...');

const socket = io('http://localhost:3000', {
  path: '/api/socket',
  transports: ['websocket', 'polling']
});

socket.on('connect', () => {
  console.log('✅ Connected to Socket.IO server');

  // Join a test session
  const testSessionId = 'test-session-123';
  console.log(`👤 Joining session: ${testSessionId}`);
  socket.emit('join-session', testSessionId);

  // Listen for events
  socket.on('status', (data) => {
    console.log('📊 Received status event:', data);
  });

  socket.on('chain_of_thought', (data) => {
    console.log('🔍 Received chain of thought:', data.step, data.reasoning.substring(0, 50) + '...');
  });

  socket.on('progress_update', (data) => {
    console.log('📈 Received progress update:', data.tracker?.overallProgress + '%');
  });

  socket.on('file_operation', (data) => {
    console.log('📁 Received file operation:', data.operation, data.fileName);
  });

  socket.on('tool_usage', (data) => {
    console.log('🔧 Received tool usage:', data.toolName, data.success ? 'success' : 'failed');
  });

  // Test disconnect after 5 seconds
  setTimeout(() => {
    console.log('👋 Leaving session and disconnecting...');
    socket.emit('leave-session', testSessionId);
    socket.disconnect();
    console.log('✅ Test completed');
    process.exit(0);
  }, 5000);
});

socket.on('connect_error', (error) => {
  console.error('❌ Connection failed:', error.message);
  process.exit(1);
});

socket.on('disconnect', () => {
  console.log('🔌 Disconnected from server');
});