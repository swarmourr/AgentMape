#!/bin/bash

# MAPE-K System with Nginx Reverse Proxy
# Exposes all services through nginx on port 8000
# Use ONE ngrok tunnel: ngrok http 8000

echo "========================================="
echo "Starting MAPE-K System with Nginx Proxy"
echo "========================================="
echo ""

# Check if nginx is installed
if ! command -v nginx &> /dev/null; then
    echo "❌ Nginx is not installed!"
    echo ""
    echo "Install nginx:"
    echo "  macOS:  brew install nginx"
    echo "  Ubuntu: sudo apt-get install nginx"
    exit 1
fi

# Start all MAPE-K services first
echo "📦 Starting MAPE-K services..."
./start_system.sh

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to start..."
sleep 8

# Check if services are running
echo ""
echo "🔍 Checking services..."
curl -s http://localhost:8085 > /dev/null && echo "  ✅ Dashboard (8085)" || echo "  ❌ Dashboard (8085)"
curl -s http://localhost:8080/health > /dev/null && echo "  ✅ Monitor (8080)" || echo "  ❌ Monitor (8080)"
curl -s http://localhost:8084/health > /dev/null && echo "  ✅ Pegasus Provider (8084)" || echo "  ❌ Pegasus Provider (8084)"

# Start nginx with our config
echo ""
echo "🚀 Starting nginx reverse proxy on port 8000..."
nginx -c "$(pwd)/nginx.conf" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Nginx started successfully"

    # Test nginx
    sleep 2
    if curl -s http://localhost:8000/nginx-health > /dev/null; then
        echo "✅ Nginx health check passed"
    else
        echo "⚠️  Nginx started but health check failed"
    fi
else
    echo "❌ Nginx failed to start"
    echo ""
    echo "Common issues:"
    echo "  - Port 8000 already in use: lsof -i :8000"
    echo "  - Permission denied: try with sudo"
    echo "  - Config error: nginx -t -c $(pwd)/nginx.conf"
    exit 1
fi

echo ""
echo "========================================="
echo "✅ System Ready!"
echo "========================================="
echo ""
echo "🌐 Local access:  http://localhost:8000"
echo ""
echo "📡 To expose via ngrok (single tunnel):"
echo "   ngrok http 8000"
echo ""
echo "🎯 Then access via ngrok URL"
echo "   Example: https://abc123.ngrok.io"
echo "   ✅ NO CORS ISSUES!"
echo ""
echo "📋 Nginx logs:"
echo "   Access: tail -f /tmp/nginx_mapek_access.log"
echo "   Error:  tail -f /tmp/nginx_mapek_error.log"
echo ""
echo "🛑 To stop everything:"
echo "   nginx -s stop && ./stop_system.sh"
echo "========================================="
