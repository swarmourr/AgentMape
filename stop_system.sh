#!/bin/bash

# MAPE-K Autonomous System Stop Script

echo "=================================="
echo "Stopping MAPE-K Autonomous System"
echo "=================================="

stop_service() {
    local name=$1
    local pid_file=$2

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo "🛑 Stopping $name (PID: $pid)..."
            kill $pid
            rm "$pid_file"
        else
            echo "⚠️  $name was not running"
            rm "$pid_file"
        fi
    else
        echo "⚠️  No PID file found for $name"
    fi
}

stop_service "Monitor" "logs/monitor.pid"
stop_service "Pegasus Provider" "logs/provider.pid"
stop_service "Analyzer" "logs/analyzer.pid"
stop_service "Planner" "logs/planner.pid"
stop_service "Executor" "logs/executor.pid"
stop_service "Dashboard" "logs/dashboard.pid"

echo ""
echo "✅ All services stopped"
echo "=================================="
