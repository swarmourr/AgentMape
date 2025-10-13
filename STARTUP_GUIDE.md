# MAPE-K Autonomous System - Startup Guide

## Architecture Overview

The system now uses **separated architecture**:

- **Monitor Agent (Port 8080)**: Workflow discovery and tracking
- **Pegasus Provider Service (Port 8084)**: Real-time Pegasus WMS data
- **Analyzer Agent (Port 8081)**: Root cause analysis
- **Planner Agent (Port 8082)**: Repair plan generation
- **Executor Agent (Port 8083)**: Repair execution
- **Dashboard (Port 5000)**: Web UI

## Prerequisites

```bash
# Install system dependencies
pip install aiohttp aiohttp-cors tinydb pyyaml
```

## Quick Start

### Option 1: Automated Startup (Recommended)

```bash
cd /Users/hamzasafri/Desktop/AgentMape

# Make scripts executable
chmod +x start_system.sh stop_system.sh

# Start all services
./start_system.sh

# To stop all services
./stop_system.sh
```

### Option 2: Manual Startup

Start each service in a separate terminal:

**Terminal 1 - Monitor Agent:**
```bash
cd /Users/hamzasafri/Desktop/AgentMape/Monitoring
pip install -r requirements.txt
python server_rest.py
```

**Terminal 2 - Pegasus Provider Service:**
```bash
cd /Users/hamzasafri/Desktop/AgentMape/PegasusProvider
pip install -r requirements.txt
python pegasus_provider_service.py
```

**Terminal 3 - Analyzer Agent:**
```bash
cd /Users/hamzasafri/Desktop/AgentMape/Analyzer
python analyzer_agent.py
```

**Terminal 4 - Planner Agent:**
```bash
cd /Users/hamzasafri/Desktop/AgentMape/Planner
python planner_agent.py
```

**Terminal 5 - Executor Agent:**
```bash
cd /Users/hamzasafri/Desktop/AgentMape/Executor
python executor_agent.py
```

**Terminal 6 - Dashboard:**
```bash
cd /Users/hamzasafri/Desktop/AgentMape/Dashboard
python dashboard_app.py
```

## Verify Services

```bash
# Check all services are healthy
curl http://localhost:8080/health  # Monitor
curl http://localhost:8084/health  # Pegasus Provider
curl http://localhost:8081/health  # Analyzer
curl http://localhost:8082/health  # Planner
curl http://localhost:8083/health  # Executor
curl http://localhost:5000         # Dashboard
```

## Access Dashboard

Open browser: **http://localhost:5000**

## Key Features

### Pegasus Provider Service (NEW!)

The dedicated Pegasus data provider executes real-time Pegasus WMS commands:

**API Endpoints:**
- `GET /api/workflows/{id}/status` - Pegasus status
- `GET /api/workflows/{id}/analyzer` - Root cause analysis
- `GET /api/workflows/{id}/statistics` - Performance metrics
- `GET /api/workflows/{id}/jobs` - Workflow jobs/DAG structure
- `GET /api/workflows/{id}/full` - Combined analysis
- `POST /api/workflows/batch` - Batch query multiple workflows

**Example Usage:**
```bash
# Get root cause analysis for workflow
curl http://localhost:8084/api/workflows/WORKFLOW_ID/analyzer

# Get full analysis (status + analyzer + statistics)
curl http://localhost:8084/api/workflows/WORKFLOW_ID/full

# Get workflow jobs/DAG structure
curl http://localhost:8084/api/workflows/WORKFLOW_ID/jobs

# Batch query multiple workflows
curl -X POST http://localhost:8084/api/workflows/batch \
  -H "Content-Type: application/json" \
  -d '{"workflow_ids": ["id1", "id2"], "query_type": "analyzer"}'

# Clear cache
curl -X DELETE http://localhost:8084/api/cache
```

### Dashboard Features

- **All-Time Workflow View**: Shows all workflows including historical
- **Root Cause Detection**: Distinguishes root causes (red) from cascade errors (orange)
- **Real-time Pegasus Data**: Live data from pegasus-analyzer, pegasus-status
- **Pipeline Visualization**: Track workflow through MAPE-K pipeline
- **Agent Network Graph**: Visualize agent communication

## Troubleshooting

### Dashboard shows "Error loading workflow data"

1. **Install aiohttp-cors:**
   ```bash
   pip install aiohttp-cors
   ```

2. **Restart Monitor and Pegasus Provider:**
   ```bash
   # If using automated startup
   ./stop_system.sh
   ./start_system.sh

   # If manual, restart those terminals
   ```

3. **Check browser console** (F12) for specific errors

4. **Verify workflow exists:**
   ```bash
   # List all workflows
   curl http://localhost:8080/api/workflows/all | python -m json.tool

   # Check specific workflow
   curl http://localhost:8080/api/workflows/WORKFLOW_ID/status
   ```

### Service won't start

1. **Check if port is already in use:**
   ```bash
   lsof -i :8080  # Monitor
   lsof -i :8084  # Pegasus Provider
   lsof -i :5000  # Dashboard
   ```

2. **Check logs:**
   ```bash
   tail -f logs/monitor.log
   tail -f logs/pegasus_provider.log
   tail -f logs/dashboard.log
   ```

### No root causes showing

1. **Verify Pegasus commands are available:**
   ```bash
   which pegasus-status
   which pegasus-analyzer
   ```

2. **Test Pegasus Provider directly:**
   ```bash
   curl http://localhost:8084/api/workflows/WORKFLOW_ID/analyzer
   ```

3. **Check cache:**
   ```bash
   curl http://localhost:8084/api/cache/stats
   ```

## Architecture Benefits

### Why Separate Pegasus Provider?

1. **Separation of Concerns**: Monitor focuses on tracking, Provider focuses on data
2. **Scalability**: Can scale Provider independently for heavy Pegasus queries
3. **Reusability**: Other services can use Provider without going through Monitor
4. **Caching**: Dedicated caching layer prevents excessive Pegasus command execution
5. **Maintainability**: Easier to update Pegasus integration in one place

### Data Flow

```
Dashboard (5000)
    ↓
    ├─→ Monitor (8080) ────→ Workflow tracking, discovery
    └─→ Pegasus Provider (8084) ─→ Real-time Pegasus data
                                    ├─→ pegasus-status
                                    ├─→ pegasus-analyzer (ROOT CAUSES!)
                                    └─→ pegasus-statistics
```

## Environment Variables

```bash
# Pegasus Provider
export PEGASUS_PROVIDER_PORT=8084
export MONITOR_URL=http://localhost:8080

# Monitor
export MONITOR_PORT=8080
```

## Performance Tips

1. **Cache TTL**: Pegasus Provider caches results for 10 seconds
2. **Batch Queries**: Use `/api/workflows/batch` for multiple workflows
3. **Verbose Mode**: Set `?verbose=false` on analyzer endpoint for faster responses
4. **Concurrent Requests**: Provider handles parallel workflow queries efficiently

## Next Steps

1. Start the system using `./start_system.sh`
2. Open dashboard at http://localhost:5000
3. Click on a failed workflow to see root cause analysis
4. Observe agent pipeline as it processes workflow repairs
