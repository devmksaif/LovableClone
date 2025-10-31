#!/bin/bash
"""
Enhanced Sandbox and Agent Graph Test Runner
Run the comprehensive test suite for sandbox verification and agent graph testing.
"""

# Set your Groq API key here
export GROQ_API_KEY="your_groq_api_key_here"

# Change to the correct directory
cd /Users/Apple/Desktop/NextLovable/Pythonagents/fastapi-mcp-agent

echo "🚀 Starting Enhanced Sandbox and Agent Graph Tests"
echo "=================================================="
echo "Model: groq/qwen-2.5-32b"
echo "API Key: ${GROQ_API_KEY:0:10}..."
echo "=================================================="

# Run the test
python test_sandbox_verification.py

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 ALL TESTS PASSED!"
    echo "✅ Sandbox security verified"
    echo "✅ Agent graph working correctly"
    echo "✅ Rate limiting functional"
else
    echo ""
    echo "❌ TESTS FAILED!"
    echo "Please check the output above for details"
    exit 1
fi