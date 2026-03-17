#!/bin/bash
# ============================================================
# AgentMape MAPE-K System — Unified Restart Script
# Stops all services, restarts them in order, tails all logs
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PIPELINE_DIR="$SCRIPT_DIR/pipeline_data"

# ── Port assignments ─────────────────────────────────────────
PORT_MONITOR=8080
PORT_ANALYZER=8081
PORT_PLANNER=8082
PORT_EXECUTOR=8083
PORT_EVALUATOR=8084
PORT_PROVIDER=8085   # moved from 8084 to avoid conflict with Evaluator
PORT_DASHBOARD=5000

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${BOLD}[$(date '+%H:%M:%S')]${RESET} $*"; }
ok()   { echo -e "${GREEN}  ✔${RESET}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
err()  { echo -e "${RED}  ✘${RESET}  $*"; }

# ── Kill a process listening on a port ───────────────────────
kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        warn "Killed process(es) on port $port: $pids"
    fi
}

# ── Kill by PID file ─────────────────────────────────────────
kill_pid_file() {
    local pidfile=$1
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            warn "Killed PID $pid (from $(basename "$pidfile"))"
        fi
        rm -f "$pidfile"
    fi
}

# ── Wait for HTTP health endpoint ────────────────────────────
wait_healthy() {
    local name=$1 url=$2 retries=${3:-15}
    local i=0
    while [ $i -lt $retries ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            ok "$name is healthy"
            return 0
        fi
        sleep 1
        i=$((i+1))
    done
    err "$name did not respond at $url after ${retries}s"
    return 1
}

# ── Python executable ─────────────────────────────────────────
if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}${CYAN}  AgentMape MAPE-K — Restart System     ${RESET}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo ""

# ── 1. STOP all existing services ────────────────────────────
log "Stopping all services..."

for pidfile in monitor analyzer planner executor evaluator provider dashboard; do
    kill_pid_file "$LOG_DIR/${pidfile}.pid"
done

kill_port $PORT_MONITOR
kill_port $PORT_ANALYZER
kill_port $PORT_PLANNER
kill_port $PORT_EXECUTOR
kill_port $PORT_EVALUATOR
kill_port $PORT_PROVIDER
kill_port $PORT_DASHBOARD

sleep 1
ok "All services stopped"

# ── 2. Prepare directories ────────────────────────────────────
mkdir -p "$LOG_DIR"
mkdir -p "$PIPELINE_DIR/planner_output/pending"
mkdir -p "$PIPELINE_DIR/planner_output/processed"
mkdir -p "$PIPELINE_DIR/evaluator_output"

# ── 3. START services in order ───────────────────────────────

start_service() {
    local name=$1       # display name
    local dir=$2        # subdirectory under SCRIPT_DIR
    local script=$3     # python script filename
    local logfile=$4    # log file path
    local pidfile=$5    # pid file path
    shift 5
    local extra_env=("$@")   # optional KEY=VALUE env overrides

    log "Starting $name..."

    local cmd="$PYTHON $script"
    if [ ${#extra_env[@]} -gt 0 ]; then
        env_prefix="${extra_env[*]} "
    else
        env_prefix=""
    fi

    pushd "$SCRIPT_DIR/$dir" > /dev/null
    eval "env $env_prefix $PYTHON $script > \"$logfile\" 2>&1 &"
    local pid=$!
    popd > /dev/null

    echo "$pid" > "$pidfile"
    echo "   PID: $pid  |  log: $logfile"
}

# Monitor (8080)
start_service "Monitor" \
    "Monitoring" "server_rest.py" \
    "$LOG_DIR/monitor.log" "$LOG_DIR/monitor.pid"

wait_healthy "Monitor (8080)" "http://localhost:$PORT_MONITOR/health" 20
echo ""

# Pegasus Data Provider (8085)
start_service "Pegasus Data Provider" \
    "PegasusProvider" "pegasus_provider_service.py" \
    "$LOG_DIR/provider.log" "$LOG_DIR/provider.pid" \
    "PEGASUS_PROVIDER_PORT=$PORT_PROVIDER"

wait_healthy "Pegasus Provider (8085)" "http://localhost:$PORT_PROVIDER/health" 20
echo ""

# Analyzer (8081)
start_service "Analyzer" \
    "Analyzer" "analyzer_rest.py" \
    "$LOG_DIR/analyzer.log" "$LOG_DIR/analyzer.pid"

wait_healthy "Analyzer (8081)" "http://localhost:$PORT_ANALYZER/health" 20
echo ""

# Planner (8082)
start_service "Planner" \
    "Planner" "planner_rest.py" \
    "$LOG_DIR/planner.log" "$LOG_DIR/planner.pid"

wait_healthy "Planner (8082)" "http://localhost:$PORT_PLANNER/health" 20
echo ""

# Evaluator (8084)
start_service "Evaluator" \
    "Evaluator" "evaluator_rest.py" \
    "$LOG_DIR/evaluator.log" "$LOG_DIR/evaluator.pid"

wait_healthy "Evaluator (8084)" "http://localhost:$PORT_EVALUATOR/health" 20
echo ""

# Dashboard (5000)
start_service "Dashboard" \
    "Dashboard" "dashboard_server.py" \
    "$LOG_DIR/dashboard.log" "$LOG_DIR/dashboard.pid"

wait_healthy "Dashboard (5000)" "http://localhost:$PORT_DASHBOARD" 20
echo ""

# ── 4. Final health summary ───────────────────────────────────
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}         System Health Check            ${RESET}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}"

check() {
    local label=$1 url=$2
    if curl -sf "$url" > /dev/null 2>&1; then
        ok  "$label"
    else
        err "$label  ← not responding"
    fi
}

check "Monitor          http://localhost:$PORT_MONITOR"   "http://localhost:$PORT_MONITOR/health"
check "Analyzer         http://localhost:$PORT_ANALYZER"  "http://localhost:$PORT_ANALYZER/health"
check "Planner          http://localhost:$PORT_PLANNER"   "http://localhost:$PORT_PLANNER/health"
check "Evaluator        http://localhost:$PORT_EVALUATOR" "http://localhost:$PORT_EVALUATOR/health"
check "Pegasus Provider http://localhost:$PORT_PROVIDER"  "http://localhost:$PORT_PROVIDER/health"
check "Dashboard        http://localhost:$PORT_DASHBOARD" "http://localhost:$PORT_DASHBOARD"

echo ""
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Log files in: $LOG_DIR  ${RESET}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo ""
echo "  monitor.log      → Monitor agent"
echo "  analyzer.log     → Analyzer agent"
echo "  planner.log      → Planner + model results"
echo "  evaluator.log    → LLM Council Evaluator"
echo "  provider.log     → Pegasus Data Provider"
echo "  dashboard.log    → Web dashboard"
echo ""

# ── 5. Tail logs — all services interleaved ───────────────────
# Use a label prefix per log file via tail -f + awk
echo -e "${BOLD}${CYAN}════════════ Live Logs ═════════════════${RESET}"
echo -e "(Press ${BOLD}Ctrl-C${RESET} to stop tailing — services keep running)"
echo ""

tail_log() {
    local label=$1 file=$2 color=$3
    tail -f "$file" 2>/dev/null | \
        awk -v lbl="$label" -v col="$color" -v rst="${RESET}" \
            '{ print col "[" lbl "]" rst " " $0; fflush() }' &
}

tail_log "MONITOR  " "$LOG_DIR/monitor.log"   "${CYAN}"
tail_log "ANALYZER " "$LOG_DIR/analyzer.log"  "${GREEN}"
tail_log "PLANNER  " "$LOG_DIR/planner.log"   "${YELLOW}"
tail_log "EVALUATOR" "$LOG_DIR/evaluator.log" "${RED}"
tail_log "PROVIDER " "$LOG_DIR/provider.log"  "\033[0;35m"
tail_log "DASHBOARD" "$LOG_DIR/dashboard.log" "\033[0;36m"

# Trap Ctrl-C to kill tail processes cleanly
trap 'kill $(jobs -p) 2>/dev/null; echo ""; log "Log tailing stopped. Services still running."; exit 0' INT
wait
