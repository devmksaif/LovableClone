#!/bin/bash

# Script to run both Next.js frontend and Python FastAPI backend

echo "🚀 Starting NextLovable with Python Backend"

# Kill anything already running on port 8000
echo "🧹 Checking for processes on port 8000..."
pids=($(lsof -ti :8000))
if [ ${#pids[@]} -gt 0 ]; then
    echo "⚠️  Found processes using port 8000: ${pids[@]}"
    kill -9 "${pids[@]}"
    echo "✅ Killed existing processes on port 8000."
else
    echo "✅ Port 8000 is free."
fi

# Check if Python backend dependencies are installed
if [ ! -d "Pythonagents/fastapi-mcp-agent/venv" ]; then
    echo "📦 Setting up Python backend..."
    cd Pythonagents/fastapi-mcp-agent
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ../..
fi

# Start Python backend in background
echo "🐍 Starting Python FastAPI backend on port 8000..."
cd Pythonagents/fastapi-mcp-agent
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ../..

echo "✅ FastAPI backend started (PID: $BACKEND_PID)"
