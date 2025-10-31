#!/usr/bin/env node

// Test script for COT Manager functionality
const { cotManager, addCOTEntry, getCOTMessages, addProgressUpdate, processBatchedUpdates, getSessionStats } = require('./lib/utils/cot-manager.ts');

console.log('🧪 Testing COT Manager...\n');

const sessionId = 'test-session-123';

// Test 1: Basic COT entry addition
console.log('Test 1: Adding COT entries');
const entry1 = addCOTEntry(sessionId, 1, 'First reasoning step');
const entry2 = addCOTEntry(sessionId, 2, 'Second reasoning step');
console.log('✅ Added two COT entries');

// Test 2: Duplicate detection
console.log('\nTest 2: Duplicate detection');
const duplicate1 = addCOTEntry(sessionId, 1, 'First reasoning step'); // Should be null
const duplicate2 = addCOTEntry(sessionId, 3, 'First reasoning step'); // Should be null (same reasoning)
console.log('Duplicate 1 result:', duplicate1 ? 'FAILED - should be null' : '✅ Correctly detected duplicate');
console.log('Duplicate 2 result:', duplicate2 ? 'FAILED - should be null' : '✅ Correctly detected duplicate');

// Test 3: Similar but different reasoning
console.log('\nTest 3: Similar but different reasoning');
const entry3 = addCOTEntry(sessionId, 3, 'First reasoning step with variation');
console.log('Similar reasoning result:', entry3 ? '✅ Correctly added different reasoning' : 'FAILED - should not be duplicate');

// Test 4: Progress update throttling
console.log('\nTest 4: Progress update throttling');
let emittedCount = 0;
const mockEmitFunction = (sessionId, data) => {
  emittedCount++;
  console.log(`📡 Emitted progress update ${emittedCount}:`, data.type);
};

// Add multiple rapid progress updates
const shouldEmit1 = addProgressUpdate(sessionId, 'test_progress', { message: 'Update 1' });
const shouldEmit2 = addProgressUpdate(sessionId, 'test_progress', { message: 'Update 2' }); // Should be throttled
const shouldEmit3 = addProgressUpdate(sessionId, 'test_progress', { message: 'Update 3' }); // Should be throttled
const shouldEmit4 = addProgressUpdate(sessionId, 'test_progress', { message: 'Update 4' }, true); // Force emit

console.log('Should emit results:', { shouldEmit1, shouldEmit2, shouldEmit3, shouldEmit4 });

// Process batched updates
setTimeout(() => {
  console.log('\nProcessing batched updates...');
  processBatchedUpdates(sessionId, mockEmitFunction);
  
  // Test 5: Session statistics
  console.log('\nTest 5: Session statistics');
  const stats = getSessionStats(sessionId);
  console.log('Session stats:', stats);
  
  // Test 6: COT Messages conversion
  console.log('\nTest 6: COT Messages conversion');
  const cotMessages = getCOTMessages(sessionId);
  console.log(`Generated ${cotMessages.length} COT messages`);
  cotMessages.forEach((msg, index) => {
    console.log(`  ${index + 1}. ${msg.content.substring(0, 50)}...`);
  });
  
  console.log('\n🎉 COT Manager tests completed!');
  
  // Cleanup
  cotManager.cleanup(sessionId);
  console.log('🧹 Session cleaned up');
  
}, 200);