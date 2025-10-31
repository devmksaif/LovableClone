import { createServer } from 'http';
import { parse } from 'url';
import next from 'next';

const dev = process.env.NODE_ENV !== 'production';
const hostname = 'localhost';
const port = parseInt(process.env.PORT || '3001', 10);

// Initialize Next.js
const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const httpServer = createServer((req, res) => {
    const parsedUrl = parse(req.url || '/', true);
    handle(req, res, parsedUrl);
  });

  // Cleanup function (no sandbox cleanup needed since using Python backend)
  const cleanup = async () => {
    console.log('🧹 Shutting down Next.js server...');
    // No sandbox cleanup needed - handled by Python backend
    console.log('🧹 Server cleanup completed');

    // Close HTTP server gracefully
    httpServer.close((err) => {
      if (err) {
        console.error('❌ Error closing HTTP server:', err);
        process.exit(1);
      }
      console.log('✅ HTTP server closed');
      process.exit(0);
    });

    // Force exit after 10 seconds if graceful shutdown fails
    setTimeout(() => {
      console.log('⚠️  Forced shutdown after timeout');
      process.exit(1);
    }, 10000);
  };

  // Handle process termination signals
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);
  process.on('SIGUSR2', cleanup); // For nodemon restarts

  // Handle uncaught exceptions
  process.on('uncaughtException', (error) => {
    console.error('❌ Uncaught Exception:', error);
    cleanup();
  });

  process.on('unhandledRejection', (reason, promise) => {
    console.error('❌ Unhandled Rejection at:', promise, 'reason:', reason);
    cleanup();
  });

  httpServer.listen(port, () => {
    console.log(`> Ready on http://${hostname}:${port}`);
    console.log(`> Socket.IO server initialized on path: /api/socket`);
  });
});