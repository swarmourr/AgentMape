#!/bin/bash

# MAPE-K Autonomous System Startup Script
# Starts all components in correct order

echo "=================================="
echo "Starting MAPE-K Autonomous System"
echo "=================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found. Creating..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Create log directory
mkdir -p logs

# Start Monitor Agent (Port 8080)
echo ""
echo "🔍 Starting Monitor Agent (port 8080)..."
cd Monitoring
python server_rest.py > ../logs/monitor.log 2>&1 &
MONITOR_PID=$!
echo "   Monitor PID: $MONITOR_PID"
cd ..

# Wait for Monitor to be ready
sleep 3
echo "   Checking Monitor health..."
curl -s http://localhost:8080/health > /dev/null && echo "   ✅ Monitor is healthy" || echo "   ❌ Monitor failed to start"

# Start Pegasus Data Provider (Port 8084)
echo ""
echo "📊 Starting Pegasus Data Provider (port 8084)..."
cd PegasusProvider
python pegasus_provider_service.py > ../logs/pegasus_provider.log 2>&1 &
PROVIDER_PID=$!
echo "   Provider PID: $PROVIDER_PID"
cd ..

# Wait for Provider to be ready
sleep 3
echo "   Checking Provider health..."
curl -s http://localhost:8084/health > /dev/null && echo "   ✅ Provider is healthy" || echo "   ❌ Provider failed to start"

# Start Analyzer Agent (Port 8081)
echo ""
echo "🔬 Starting Analyzer Agent (port 8081)..."
cd Analyzer
python analyzer_agent.py > ../logs/analyzer.log 2>&1 &
ANALYZER_PID=$!
echo "   Analyzer PID: $ANALYZER_PID"
cd ..

sleep 2

# Start Planner Agent (Port 8082)
echo ""
echo "📋 Starting Planner Agent (port 8082)..."
cd Planner
python planner_agent.py > ../logs/planner.log 2>&1 &
PLANNER_PID=$!
echo "   Planner PID: $PLANNER_PID"
cd ..

sleep 2

# Start Executor Agent (Port 8083)
echo ""
echo "⚙️  Starting Executor Agent (port 8083)..."
cd Executor
python executor_agent.py > ../logs/executor.log 2>&1 &
EXECUTOR_PID=$!
echo "   Executor PID: $EXECUTOR_PID"
cd ..

sleep 2

# Start Dashboard (Port 5000)
echo ""
echo "📊 Starting Dashboard (port 5000)..."
cd Dashboard
python dashboard_server.py > ../logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "   Dashboard PID: $DASHBOARD_PID"
cd ..

sleep 3

# Final health check
echo ""
echo "=================================="
echo "🏥 System Health Check"
echo "=================================="

check_service() {
    local name=$1
    local url=$2
    if curl -s "$url" > /dev/null 2>&1; then
        echo "✅ $name"
    else
        echo "❌ $name (not responding)"
    fi
}

check_service "Monitor (8080)        " "http://localhost:8080/health"
check_service "Pegasus Provider (8084)" "http://localhost:8084/health"
check_service "Analyzer (8081)       " "http://localhost:8081/health"
check_service "Planner (8082)        " "http://localhost:8082/health"
check_service "Executor (8083)       " "http://localhost:8083/health"
check_service "Dashboard (5000)      " "http://localhost:5000"

echo ""
echo "=================================="
echo "📝 Service URLs"
echo "=================================="
echo "Monitor:          http://localhost:8080"
echo "Pegasus Provider: http://localhost:8084"
echo "Dashboard:        http://localhost:5000"
echo ""
echo "Logs: tail -f logs/*.log"
echo ""
echo "To stop all services: ./stop_system.sh"
echo "=================================="

# Save PIDs for stop script
echo "$MONITOR_PID" > logs/monitor.pid
echo "$PROVIDER_PID" > logs/provider.pid
echo "$ANALYZER_PID" > logs/analyzer.pid
echo "$PLANNER_PID" > logs/planner.pid
echo "$EXECUTOR_PID" > logs/executor.pid
echo "$DASHBOARD_PID" > logs/dashboard.pid

echo ""
echo "🚀 System started! Access dashboard at http://localhost:5000"
