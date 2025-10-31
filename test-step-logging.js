const { chatLogger } = require('./lib/utils/chat-logger.ts');

async function testStepLogging() {
  console.log('Testing step-based logging system...');
  
  const sessionId = 'test-session-' + Date.now();
  
  try {
    // Test progress update logging
    console.log('1. Testing progress update logging...');
    chatLogger.logProgressUpdate(sessionId, {
      overallProgress: 25,
      currentStep: 0,
      steps: [
        { id: 'planning', status: 'completed', label: 'Planning your request' },
        { id: 'generating', status: 'running', label: 'Generating code' },
        { id: 'reviewing', status: 'pending', label: 'Reviewing code quality' }
      ]
    });

    // Test step change logging
    console.log('2. Testing step change logging...');
    chatLogger.logStepChange(sessionId, 'planning', 'completed', 'Planning your request');
    chatLogger.logStepChange(sessionId, 'generating', 'running', 'Generating code');
    
    // Test user message logging
    console.log('3. Testing user message logging...');
    chatLogger.logUserMessage(sessionId, 'Create a React component for user authentication', {
      sandboxId: 'test-sandbox-123',
      currentFile: 'src/components/Auth.tsx'
    });

    // Test tool call logging
    console.log('4. Testing tool call logging...');
    chatLogger.logToolCall(sessionId, 'write_file', 
      { filePath: 'src/components/Auth.tsx', content: 'export default function Auth() { return <div>Auth</div>; }' },
      { success: true },
      150
    );

    console.log('✅ All logging tests completed successfully!');
    console.log('📝 Check chat-logs.txt for the logged events');
    
  } catch (error) {
    console.error('❌ Error during testing:', error);
  }
}

testStepLogging();