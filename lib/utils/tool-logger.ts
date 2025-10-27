/**
 * Tool Call Logger
 * Logs all tool invocations with timing and results for debugging and optimization
 */

interface ToolCall {
  toolName: string;
  parameters: any;
  startTime: number;
  endTime?: number;
  duration?: number;
  success: boolean;
  result?: string;
  error?: string;
}

class ToolCallLogger {
  private calls: ToolCall[] = [];
  private sessionId: string = '';

  setSession(sessionId: string) {
    this.sessionId = sessionId;
    this.calls = [];
  }

  startCall(toolName: string, parameters: any): number {
    const callId = this.calls.length;
    this.calls.push({
      toolName,
      parameters,
      startTime: Date.now(),
      success: false,
    });
    
    console.log(`🔧 [TOOL START] ${toolName}`, this.formatParams(parameters));
    return callId;
  }

  endCall(callId: number, result: string, success: boolean = true, error?: string) {
    const call = this.calls[callId];
    if (!call) return;

    call.endTime = Date.now();
    call.duration = call.endTime - call.startTime;
    call.success = success;
    call.result = this.truncateResult(result);
    call.error = error;

    const icon = success ? '✅' : '❌';
    console.log(`${icon} [TOOL END] ${call.toolName} (${call.duration}ms)`);
    
    if (error) {
      console.log(`   Error: ${error}`);
    }
  }

  getStats() {
    const totalCalls = this.calls.length;
    const successfulCalls = this.calls.filter(c => c.success).length;
    const failedCalls = totalCalls - successfulCalls;
    const totalDuration = this.calls.reduce((sum, c) => sum + (c.duration || 0), 0);
    const averageDuration = totalCalls > 0 ? totalDuration / totalCalls : 0;

    const toolUsage = this.calls.reduce((acc, call) => {
      acc[call.toolName] = (acc[call.toolName] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    return {
      totalCalls,
      successfulCalls,
      failedCalls,
      totalDuration,
      averageDuration: Math.round(averageDuration),
      toolUsage,
    };
  }

  getSummary() {
    const stats = this.getStats();
    return `
📊 Tool Call Statistics:
- Total calls: ${stats.totalCalls}
- Successful: ${stats.successfulCalls}
- Failed: ${stats.failedCalls}
- Total time: ${stats.totalDuration}ms
- Average time: ${stats.averageDuration}ms
- Most used: ${Object.entries(stats.toolUsage)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([tool, count]) => `${tool}(${count})`)
      .join(', ')}
    `.trim();
  }

  getCalls() {
    return this.calls;
  }

  clear() {
    this.calls = [];
  }

  private formatParams(params: any): string {
    if (typeof params === 'string') return params;
    const str = JSON.stringify(params, null, 0);
    return str.length > 100 ? str.substring(0, 100) + '...' : str;
  }

  private truncateResult(result: string): string {
    return result.length > 500 ? result.substring(0, 500) + '...' : result;
  }
}

export const toolLogger = new ToolCallLogger();
