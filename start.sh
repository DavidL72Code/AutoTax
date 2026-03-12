#!/bin/bash

# Receipt Automation Dashboard - Start Script
# Run from project root so api.py finds python-service/app
cd "$(dirname "$0")"

echo "🚀 Starting Receipt Automation Dashboard..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check if dependencies are installed
echo "📦 Checking dependencies..."
if ! python3 -c "import fastapi, google.generativeai" 2>/dev/null; then
    echo "📥 Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Start API server in background
echo "🔧 Starting API server on http://localhost:8000..."
PYTHONPATH=python-service python3 -m uvicorn app.api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for API to start
sleep 3

# Start web server in background
echo "🌐 Starting web server on http://localhost:3000..."
python3 -m http.server 3000 &
WEB_PID=$!

# Wait for web server to start
sleep 2

echo ""
echo "✅ Dashboard is ready!"
echo ""
echo "📊 Open your browser to: http://localhost:3000"
echo "🔌 API running at: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop all servers..."
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping servers..."
    kill $API_PID 2>/dev/null
    kill $WEB_PID 2>/dev/null
    echo "✅ Servers stopped. Goodbye!"
    exit 0
}

# Register cleanup function
trap cleanup SIGINT SIGTERM

# Wait for user to press Ctrl+C
wait
