# AgentMape

**Autonomous Self-Healing System for Pegasus Scientific Workflows**

AgentMape is an intelligent workflow management system based on the **MAPE-K architecture** (Monitor, Analyze, Plan, Execute, Knowledge). It automatically detects workflow failures, diagnoses root causes using AI, generates repair plans, and can execute fixes autonomously.

## Overview

AgentMape implements a closed-loop autonomic computing cycle that monitors Pegasus workflows, analyzes failures using Large Language Models (LLMs), generates executable repair plans, and learns from successful repairs.

```
┌─────────────┐
│   Monitor   │ ──> Detects workflow failures (held/failed jobs)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Analyze   │ ──> Diagnoses root cause using LLM + pegasus-analyzer
└──────┬──────┘
       │
       ↓
┌─────────────┐
│    Plan     │ ──> Generates executable repair plan with LLM
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Execute   │ ──> Executes approved repair commands
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  Knowledge  │ ──> Learns from successful repairs
└─────────────┘
```

## Core Components

### 1. Monitor Agent
- **Port:** 8080
- **Location:** [Monitoring/](Monitoring/)
- **Purpose:** Continuously monitors Pegasus workflows
- **Capabilities:**
  - Detects held/failed/running workflow states
  - Tracks workflow statistics
  - Triggers analysis when failures occur
  - WebSocket + REST API interfaces
  - Auto-pushes failures to Analyzer

### 2. Analyzer Agent
- **Port:** 8081
- **Location:** [Analyzer/](Analyzer/)
- **Purpose:** Root cause analysis using AI
- **Capabilities:**
  - Runs `pegasus-analyzer` on failed workflows
  - Sends logs to Ollama LLM (glm-4.6:cloud model)
  - Extracts structured problem diagnosis
  - Identifies error levels (replica, site, transformation catalogs)
  - Sends analysis results to Planner via webhook
  - Catalog-aware (detects embedded vs. separate catalogs)

### 3. Planner Agent
- **Port:** 8082
- **Location:** [Planner/](Planner/)
- **Purpose:** Generates executable repair plans
- **Capabilities:**
  - Receives analysis from Analyzer
  - Generates repair plans using LLM (llama3:latest)
  - Creates bash/Pegasus commands to fix issues
  - Risk assessment (low/medium/high)
  - Auto-approves low-risk plans (confidence > 0.75)
  - Catalog-aware repairs (text vs YAML catalogs)
  - Includes rollback strategies

### 4. Dashboard
- **Port:** 8085
- **Location:** [Dashboard/](Dashboard/)
- **Purpose:** Real-time monitoring UI
- **Capabilities:**
  - Displays status of all agents (Monitor, Analyzer, Planner)
  - Shows workflow statistics (Running, Failed, Held, Success)
  - Lists recent workflows
  - Auto-refreshes every 3 seconds
  - Terminal-style interface with colors

### 5. Workflow Validator
- **Location:** [WorkflowValidator/](WorkflowValidator/)
- **Purpose:** Pre-submission workflow validation
- **Capabilities:**
  - Validates YAML workflows
  - Generates YAML from Python descriptors
  - Python syntax validation
  - Security checks
  - Path integrity validation
  - LLM-assisted analysis
  - Supports generator scripts

### 6. Pegasus Provider
- **Location:** [PegasusProvider/](PegasusProvider/)
- **Purpose:** Pegasus command execution service
- **Capabilities:**
  - Provides Pegasus integrity checks
  - Command execution interface

## Quick Start

### Installation

```bash
# Clone the repository
cd AgentMape

# Install dependencies for each component
pip install -r Monitoring/requirements.txt
pip install -r Analyzer/requirements.txt
pip install -r Planner/requirements.txt
pip install -r Dashboard/requirements.txt
pip install -r WorkflowValidator/requirements.txt
```

### Starting the System

**Option 1: Use the startup script**
```bash
./start_system.sh
```

**Option 2: Start agents individually**
```bash
# Terminal 1: Monitor
cd Monitoring
python server_rest.py

# Terminal 2: Analyzer
cd Analyzer
python analyzer_rest.py

# Terminal 3: Planner
cd Planner
python planner_rest.py

# Terminal 4: Dashboard
cd Dashboard
python dashboard_server.py
```

### Access the Dashboard

Open your browser and navigate to:
```
http://localhost:8085
```

## Workflow Example

### Scenario: Missing Input File

1. **Monitor** detects a held workflow (`condor_q` shows held job)
2. **Monitor** pushes failure to **Analyzer**
3. **Analyzer**:
   - Runs `pegasus-analyzer` on workflow directory
   - Gets error: `"Input file 'data.csv' not found"`
   - Sends logs to Ollama LLM
   - LLM identifies: "Missing replica catalog entry"
   - Sends structured analysis to **Planner**
4. **Planner**:
   - Receives analysis with catalog info
   - Generates plan with LLM:
     ```bash
     Step 1: cp /workflow/rc.txt /workflow/rc.txt.backup
     Step 2: echo 'data.csv file:///data/input.csv local' >> /workflow/rc.txt
     Step 3: pegasus-run /workflow/dir
     ```
   - Risk: LOW, Confidence: 0.92
   - Auto-approves for execution
5. **Executor** (planned): Executes the repair commands
6. Workflow resumes successfully

## Key Technologies

- **Python** - All agents implemented in Python
- **Flask** - REST API framework
- **WebSocket** - Real-time Monitor communication
- **Ollama** - LLM backend (via Pinggy tunnel)
  - Analyzer: `glm-4.6:cloud`
  - Planner: `llama3:latest`
- **TinyDB** - Lightweight database for agents
- **Pegasus WMS** - Workflow management system
- **HTCondor** - Job scheduling system

## Intelligence Features

### Catalog Awareness
The system understands Pegasus catalog types:
- **Text catalogs** (`rc.txt`, `tc.txt`) - Uses `echo` commands
- **YAML catalogs** (embedded) - Uses `yq` commands
- **XML catalogs** - Uses `xmlstarlet` commands

### Risk Assessment
Plans are automatically categorized:
- **Low risk:** Auto-execute (e.g., add replica entry)
- **Medium risk:** Notify + require approval (e.g., increase memory)
- **High risk:** Manual review required (e.g., dangerous commands)

### Safety Features
- Dangerous command detection (`rm -rf`, `dd`)
- Confidence threshold validation
- Rollback strategies required
- Command syntax verification

## Configuration

Each agent has a JSON configuration file:

- `Monitoring/monitor_config.json` - Monitor settings and ports
- `Analyzer/analyzer_config.json` - Analyzer + Ollama configuration
- `Planner/planner_config.json` - Planner + Ollama configuration
- `WorkflowValidator/validator_config.json` - Validator settings

Example configuration (Monitor):
```json
{
    "http_port": 8080,
    "mcp_port": 8765,
    "analyzer_url": "http://localhost:8081",
    "planner_url": "http://localhost:8082",
    "monitor_interval": 60,
    "auto_analysis_enabled": true
}
```

## API Endpoints

### Monitor Agent (Port 8080)
- `GET /health` - Health check
- `GET /api/workflows` - List workflows
- `GET /api/workflows/{id}` - Get workflow details
- `POST /api/workflows/{id}/analyze` - Trigger analysis

### Analyzer Agent (Port 8081)
- `GET /health` - Health check
- `POST /api/analyze` - Manually trigger analysis
- `GET /api/analyses` - List all analyses
- `GET /api/analyses/{id}` - Get specific analysis

### Planner Agent (Port 8082)
- `GET /health` - Health check
- `POST /api/create-plan` - Manually create plan
- `GET /api/plans` - List all plans
- `GET /api/plans/{id}` - Get specific plan
- `POST /api/plans/{id}/approve` - Approve plan

### Dashboard (Port 8085)
- `GET /` - Dashboard UI
- `GET /api/data` - All data (agents + workflows)
- `GET /api/agents` - Agent status only
- `GET /api/workflows` - Workflow statistics

## Workflow Validator Usage

```bash
# Validate YAML workflow
python WorkflowValidator/cli.py workflow.yml

# Generate YAML from Python descriptor
python WorkflowValidator/cli.py workflow_descriptor.py

# Validate with custom workflow directory
python WorkflowValidator/cli.py orchestrator.py --workflow-dir /path/to/workflow/

# Validate generator scripts
python WorkflowValidator/cli.py generate.py --from-generator --workflow-args 'production 4'
```

## Project Structure

```
AgentMape/
├── Monitoring/          # Monitor agent (workflow detection)
├── Analyzer/            # Analyzer agent (root cause analysis)
├── Planner/             # Planner agent (repair plan generation)
├── Dashboard/           # Real-time monitoring dashboard
├── WorkflowValidator/   # Workflow validation tool
├── PegasusProvider/     # Pegasus command execution service
├── start_system.sh      # System startup script
├── stop_system.sh       # System shutdown script
└── README.md            # This file
```

## Development Status

**✅ Implemented:**
- Monitor agent with workflow detection
- Analyzer agent with LLM-powered diagnosis
- Planner agent with LLM-powered repair generation
- Real-time Dashboard
- Workflow Validator

**🚧 Planned:**
- Executor agent (automatic repair execution)
- Knowledge base (learning from repairs)
- Feedback loop improvements

## Troubleshooting

### Agents showing "Unhealthy" in Dashboard
1. Verify agent is running: `curl http://localhost:PORT/health`
2. Check agent logs in their respective directories
3. Verify port configuration in config files

### Ollama Connection Issues
- Check `ollama_url` in `analyzer_config.json` and `planner_config.json`
- Verify Pinggy tunnel is active
- Test Ollama endpoint: `curl [ollama_url]/api/generate`

### No Workflows Detected
- Ensure Monitor is configured with correct Pegasus workflow directory
- Check HTCondor is running: `condor_q`
- Verify workflow is submitted to HTCondor

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly with real Pegasus workflows
5. Submit a pull request

## License

[Add your license information here]

## Contact

[Add contact information here]

---

**AgentMape** - Bringing autonomous intelligence to scientific workflow management
