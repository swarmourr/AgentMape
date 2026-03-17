#!/bin/bash
# ============================================================
# AgentMape MAPE-K System — Unified Restart Script
# Stops all services, restarts them in order, verifies
# inter-service connectivity, then tails all logs
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
PIPELINE_DIR="$SCRIPT_DIR/pipeline_data"

PYTHON="python3.11"

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
CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; BOLD='\033[1m'; RESET='\033[0m'
DIM='\033[2m'

log()  { echo -e "${BOLD}[$(date '+%H:%M:%S')]${RESET} $*"; }
ok()   { echo -e "${GREEN}  ✔${RESET}  $*"; }
warn() { echo -e "${YELLOW}  ⚠${RESET}  $*"; }
err()  { echo -e "${RED}  ✘${RESET}  $*"; }
info() { echo -e "${CYAN}  →${RESET}  $*"; }

# ── Verify python3.11 ────────────────────────────────────────
if ! command -v $PYTHON &>/dev/null; then
    err "python3.11 not found. Please install it first."
    exit 1
fi
info "Using $($PYTHON --version)"
echo ""

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
    local name=$1 url=$2 retries=${3:-20}
    local i=0
    printf "   Waiting for %s" "$name"
    while [ $i -lt $retries ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo ""
            ok "$name is up"
            return 0
        fi
        printf "."
        sleep 1
        i=$((i+1))
    done
    echo ""
    err "$name did not respond at $url after ${retries}s"
    return 1
}

# ── Fetch JSON field from a URL ───────────────────────────────
# Usage: json_field <url> <jq_filter>
# Falls back to grep-based extraction if jq unavailable
json_field() {
    local url=$1 filter=$2
    local body
    body=$(curl -sf "$url" 2>/dev/null || echo "{}")
    if command -v jq &>/dev/null; then
        echo "$body" | jq -r "$filter" 2>/dev/null || echo "n/a"
    else
        # Simple grep fallback for key:"value" patterns
        local key
        key=$(echo "$filter" | tr -d '.[]"')
        echo "$body" | grep -o "\"${key}\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" \
            | head -1 | sed 's/.*: *"//' | tr -d '"' || echo "n/a"
    fi
}

# ── Check if a URL is reachable ───────────────────────────────
is_up() {
    curl -sf "$1" > /dev/null 2>&1
}

# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${CYAN}   AgentMape MAPE-K — Restart System           ${RESET}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo ""

# ── 1. STOP all existing services ────────────────────────────
log "Stopping all services..."

for svc in monitor analyzer planner executor evaluator provider dashboard; do
    kill_pid_file "$LOG_DIR/${svc}.pid"
done

for port in $PORT_MONITOR $PORT_ANALYZER $PORT_PLANNER $PORT_EXECUTOR \
            $PORT_EVALUATOR $PORT_PROVIDER $PORT_DASHBOARD; do
    kill_port "$port"
done

sleep 1
ok "All services stopped"
echo ""

# ── 2. Prepare directories ────────────────────────────────────
mkdir -p "$LOG_DIR"
mkdir -p "$PIPELINE_DIR/planner_output/pending"
mkdir -p "$PIPELINE_DIR/planner_output/processed"
mkdir -p "$PIPELINE_DIR/evaluator_output"

# ── 3. START services in order ───────────────────────────────

start_service() {
    local name=$1 dir=$2 script=$3 logfile=$4 pidfile=$5
    shift 5
    local extra_env=("$@")

    log "Starting $name..."

    local env_prefix=""
    if [ ${#extra_env[@]} -gt 0 ]; then
        env_prefix="${extra_env[*]} "
    fi

    pushd "$SCRIPT_DIR/$dir" > /dev/null
    eval "env $env_prefix $PYTHON $script > \"$logfile\" 2>&1 &"
    local pid=$!
    popd > /dev/null

    echo "$pid" > "$pidfile"
    info "PID: $pid  |  log: $(basename "$logfile")"
}

# ── Monitor (8080) ────────────────────────────────────────────
start_service "Monitor" \
    "Monitoring" "server_rest.py" \
    "$LOG_DIR/monitor.log" "$LOG_DIR/monitor.pid"
wait_healthy "Monitor" "http://localhost:$PORT_MONITOR/health"
echo ""

# ── Pegasus Data Provider (8085) ──────────────────────────────
start_service "Pegasus Data Provider" \
    "PegasusProvider" "pegasus_provider_service.py" \
    "$LOG_DIR/provider.log" "$LOG_DIR/provider.pid" \
    "PEGASUS_PROVIDER_PORT=$PORT_PROVIDER"
wait_healthy "Pegasus Provider" "http://localhost:$PORT_PROVIDER/health"
echo ""

# ── Analyzer (8081) ───────────────────────────────────────────
start_service "Analyzer" \
    "Analyzer" "analyzer_rest.py" \
    "$LOG_DIR/analyzer.log" "$LOG_DIR/analyzer.pid"
wait_healthy "Analyzer" "http://localhost:$PORT_ANALYZER/health"
echo ""

# ── Planner (8082) ────────────────────────────────────────────
start_service "Planner" \
    "Planner" "planner_rest.py" \
    "$LOG_DIR/planner.log" "$LOG_DIR/planner.pid"
wait_healthy "Planner" "http://localhost:$PORT_PLANNER/health"
echo ""

# ── Evaluator (8084) ──────────────────────────────────────────
start_service "Evaluator" \
    "Evaluator" "evaluator_rest.py" \
    "$LOG_DIR/evaluator.log" "$LOG_DIR/evaluator.pid"
wait_healthy "Evaluator" "http://localhost:$PORT_EVALUATOR/health"
echo ""

# ── Dashboard (5000) ──────────────────────────────────────────
start_service "Dashboard" \
    "Dashboard" "dashboard_server.py" \
    "$LOG_DIR/dashboard.log" "$LOG_DIR/dashboard.pid"
wait_healthy "Dashboard" "http://localhost:$PORT_DASHBOARD"
echo ""

# ── 4. SERVICE HEALTH SUMMARY ────────────────────────────────
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo -e "${BOLD}             Service Health Summary            ${RESET}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"

printf "  %-26s %-8s %-12s %s\n" "SERVICE" "PORT" "STATUS" "DETAILS"
printf "  %-26s %-8s %-12s %s\n" "-------" "----" "------" "-------"

print_health_row() {
    local name=$1 port=$2 url=$3 detail_url=$4 detail_filter=$5

    local status detail
    if is_up "$url"; then
        status="${GREEN}UP${RESET}"
        if [ -n "$detail_url" ] && [ -n "$detail_filter" ]; then
            detail=$(json_field "$detail_url" "$detail_filter")
        else
            detail="ok"
        fi
    else
        status="${RED}DOWN${RESET}"
        detail="not responding"
    fi
    printf "  %-26s %-8s " "$name" "$port"
    echo -e "${status}         ${DIM}${detail}${RESET}"
}

print_health_row "Monitor"          $PORT_MONITOR  \
    "http://localhost:$PORT_MONITOR/health"   \
    "http://localhost:$PORT_MONITOR/health"   ".agent_id"

print_health_row "Analyzer"         $PORT_ANALYZER \
    "http://localhost:$PORT_ANALYZER/health"  \
    "http://localhost:$PORT_ANALYZER/health"  ".llm_backend.provider + \" / \" + .llm_backend.model"

print_health_row "Planner"          $PORT_PLANNER  \
    "http://localhost:$PORT_PLANNER/health"   \
    "http://localhost:$PORT_PLANNER/health"   "if .openai_enabled then \"openai enabled\" else \"openai off\" end"

print_health_row "Evaluator"        $PORT_EVALUATOR \
    "http://localhost:$PORT_EVALUATOR/health" \
    "http://localhost:$PORT_EVALUATOR/health" ".aggregation_strategy"

print_health_row "Pegasus Provider" $PORT_PROVIDER  \
    "http://localhost:$PORT_PROVIDER/health"  \
    "http://localhost:$PORT_PROVIDER/health"  ".service"

print_health_row "Dashboard"        $PORT_DASHBOARD \
    "http://localhost:$PORT_DASHBOARD"        "" ""

echo ""

# ── 5. INTER-SERVICE CONNECTIVITY MATRIX ─────────────────────
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo -e "${BOLD}         Inter-Service Connectivity Check      ${RESET}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${DIM}Verifying that each service can reach its upstream dependencies${RESET}"
echo ""

CONN_OK=0
CONN_FAIL=0

check_conn() {
    local from_name=$1 to_name=$2 to_url=$3
    printf "  %-20s → %-20s  " "$from_name" "$to_name"
    if is_up "$to_url"; then
        echo -e "${GREEN}CONNECTED${RESET}"
        CONN_OK=$((CONN_OK+1))
    else
        echo -e "${RED}UNREACHABLE${RESET}  (${to_url})"
        CONN_FAIL=$((CONN_FAIL+1))
    fi
}

# Monitor depends on: Analyzer, Planner
check_conn "Monitor"          "Analyzer"         "http://localhost:$PORT_ANALYZER/health"
check_conn "Monitor"          "Planner"          "http://localhost:$PORT_PLANNER/health"

# Analyzer depends on: Monitor (for file fetching)
check_conn "Analyzer"         "Monitor"          "http://localhost:$PORT_MONITOR/health"

# Planner depends on: Monitor, Analyzer
check_conn "Planner"          "Monitor"          "http://localhost:$PORT_MONITOR/health"
check_conn "Planner"          "Analyzer"         "http://localhost:$PORT_ANALYZER/health"

# Evaluator → pipeline dir (file-based, no HTTP coupling)
printf "  %-20s → %-20s  " "Evaluator" "Pipeline dir"
if [ -d "$PIPELINE_DIR/planner_output/pending" ]; then
    echo -e "${GREEN}CONNECTED${RESET}  (file-based pipeline)"
    CONN_OK=$((CONN_OK+1))
else
    echo -e "${RED}MISSING${RESET}  ($PIPELINE_DIR/planner_output/pending)"
    CONN_FAIL=$((CONN_FAIL+1))
fi

# Dashboard depends on: Monitor, Analyzer, Planner
check_conn "Dashboard"        "Monitor"          "http://localhost:$PORT_MONITOR/health"
check_conn "Dashboard"        "Analyzer"         "http://localhost:$PORT_ANALYZER/health"
check_conn "Dashboard"        "Planner"          "http://localhost:$PORT_PLANNER/health"

# Pegasus Provider depends on: Monitor
check_conn "Pegasus Provider" "Monitor"          "http://localhost:$PORT_MONITOR/health"

# LLM endpoint reachability (OpenAI-compatible)
LLM_BASE="https://ellm.nrp-nautilus.io/v1"
LLM_API_KEY="XUCcJ4cCRL3bUj9qCZKvMmbY5nGDye4P"
printf "  %-20s → %-20s  " "All agents" "LLM endpoint"
if curl -sf -H "Authorization: Bearer $LLM_API_KEY" \
        --max-time 8 "$LLM_BASE/models" > /dev/null 2>&1; then
    echo -e "${GREEN}CONNECTED${RESET}  ($LLM_BASE)"
    CONN_OK=$((CONN_OK+1))
else
    echo -e "${YELLOW}UNREACHABLE${RESET}  ($LLM_BASE)  — LLM calls will fail"
    CONN_FAIL=$((CONN_FAIL+1))
fi

echo ""

# ── Summary bar ───────────────────────────────────────────────
TOTAL=$((CONN_OK + CONN_FAIL))
if [ $CONN_FAIL -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}All $TOTAL connections verified ✔${RESET}"
else
    echo -e "  ${YELLOW}${BOLD}$CONN_OK/$TOTAL connections OK${RESET}  —  ${RED}$CONN_FAIL unreachable${RESET}"
fi
echo ""

# ── 6. PIPELINE DATA STATUS ───────────────────────────────────
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo -e "${BOLD}              Pipeline Data Dirs               ${RESET}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"

show_dir() {
    local label=$1 path=$2
    if [ -d "$path" ]; then
        local count
        count=$(ls -1 "$path" 2>/dev/null | wc -l | tr -d ' ')
        printf "  %-40s %s file(s)\n" "$label" "$count"
    else
        printf "  %-40s ${RED}missing${RESET}\n" "$label"
    fi
}

show_dir "planner_output/pending/"   "$PIPELINE_DIR/planner_output/pending"
show_dir "planner_output/processed/" "$PIPELINE_DIR/planner_output/processed"
show_dir "evaluator_output/"         "$PIPELINE_DIR/evaluator_output"

echo ""

# ── 7. SERVICE URLs ───────────────────────────────────────────
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Service URLs                                  ${RESET}"
echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════${RESET}"
echo ""
echo "  Monitor          →  http://localhost:$PORT_MONITOR"
echo "  Analyzer         →  http://localhost:$PORT_ANALYZER"
echo "  Planner          →  http://localhost:$PORT_PLANNER"
echo "  Evaluator        →  http://localhost:$PORT_EVALUATOR"
echo "  Pegasus Provider →  http://localhost:$PORT_PROVIDER"
echo "  Dashboard        →  http://localhost:$PORT_DASHBOARD"
echo ""
echo "  Logs dir         →  $LOG_DIR"
echo "  Pipeline dir     →  $PIPELINE_DIR"
echo ""
echo "  Stop all         →  ./stop_system.sh"
echo ""

# ── 8. LIVE LOG TAILING ───────────────────────────────────────
echo -e "${BOLD}${CYAN}══════════════ Live Logs ═══════════════════════${RESET}"
echo -e "  (Press ${BOLD}Ctrl-C${RESET} to stop tailing — services keep running)"
echo ""

tail_log() {
    local label=$1 file=$2 color=$3
    # Create log file if it doesn't exist yet
    touch "$file" 2>/dev/null || true
    tail -f "$file" 2>/dev/null | \
        awk -v lbl="$label" -v col="$color" -v rst="$RESET" \
            'BEGIN{OFS=""} { print col "[" lbl "]" rst "  " $0; fflush() }' &
}

tail_log "MONITOR  " "$LOG_DIR/monitor.log"   "$CYAN"
tail_log "ANALYZER " "$LOG_DIR/analyzer.log"  "$GREEN"
tail_log "PLANNER  " "$LOG_DIR/planner.log"   "$YELLOW"
tail_log "EVALUATOR" "$LOG_DIR/evaluator.log" "$RED"
tail_log "PROVIDER " "$LOG_DIR/provider.log"  "$MAGENTA"
tail_log "DASHBOARD" "$LOG_DIR/dashboard.log" "$DIM"

trap 'kill $(jobs -p) 2>/dev/null; echo ""; log "Log tailing stopped. Services still running."; exit 0' INT
wait
