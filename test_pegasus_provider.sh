#!/bin/bash

# Pegasus Provider Diagnostic Script
# Tests if the provider can retrieve workflow data

echo "=================================="
echo "Pegasus Provider Diagnostic Test"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
MONITOR_URL="http://localhost:8080"
PROVIDER_URL="http://localhost:8084"

# Test 1: Check if services are running
echo "1️⃣  Checking if services are running..."
echo ""

# Check Monitor
echo -n "   Monitor (8080): "
if curl -s "$MONITOR_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo ""
    echo "❌ Monitor is not running. Start it first:"
    echo "   cd Monitoring && python server_rest.py"
    exit 1
fi

# Check Pegasus Provider
echo -n "   Pegasus Provider (8084): "
if curl -s "$PROVIDER_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo ""
    echo "❌ Pegasus Provider is not running. Start it first:"
    echo "   cd PegasusProvider && python pegasus_provider_service.py"
    exit 1
fi

echo ""

# Test 2: Get workflows from Monitor
echo "2️⃣  Getting workflows from Monitor..."
echo ""

WORKFLOWS_JSON=$(curl -s "$MONITOR_URL/api/workflows/all")
WORKFLOW_COUNT=$(echo "$WORKFLOWS_JSON" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('workflows', [])))" 2>/dev/null || echo "0")

echo "   Found $WORKFLOW_COUNT workflow(s) in Monitor"

if [ "$WORKFLOW_COUNT" -eq "0" ]; then
    echo ""
    echo -e "${YELLOW}⚠️  No workflows found in Monitor database${NC}"
    echo ""
    echo "This could mean:"
    echo "  • No workflows have been registered yet"
    echo "  • Monitor just started and hasn't discovered workflows"
    echo ""
    echo "To test with a specific workflow, set WORKFLOW_ID manually:"
    echo "  export WORKFLOW_ID='your-workflow-id'"
    echo "  ./test_pegasus_provider.sh"
    exit 0
fi

echo ""

# Test 3: Get first workflow and test with Pegasus Provider
echo "3️⃣  Testing Pegasus Provider with first workflow..."
echo ""

# Get first workflow ID
WORKFLOW_ID=$(echo "$WORKFLOWS_JSON" | python3 -c "import sys, json; workflows=json.load(sys.stdin).get('workflows', []); print(workflows[0]['workflow_id'] if workflows else '')" 2>/dev/null)

if [ -z "$WORKFLOW_ID" ]; then
    echo -e "${RED}❌ Could not extract workflow ID${NC}"
    exit 1
fi

echo "   Testing with workflow: $WORKFLOW_ID"
echo ""

# Test 3a: Get workflow status from Monitor
echo "   📡 Querying Monitor for workflow details..."
MONITOR_RESPONSE=$(curl -s "$MONITOR_URL/api/workflows/$WORKFLOW_ID/status")
echo "$MONITOR_RESPONSE" | python3 -m json.tool > /tmp/monitor_response.json 2>/dev/null

# Check if submit directory exists
SUBMIT_DIR=$(echo "$MONITOR_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('iwd', ''))" 2>/dev/null)

echo -n "   Submit directory: "
if [ -n "$SUBMIT_DIR" ]; then
    echo -e "${GREEN}$SUBMIT_DIR${NC}"
else
    echo -e "${RED}NOT FOUND${NC}"
    echo ""
    echo "❌ Monitor doesn't have submit directory for this workflow"
    echo ""
    echo "Monitor response saved to: /tmp/monitor_response.json"
    exit 1
fi

echo ""

# Test 3b: Check if submit directory exists on filesystem
echo "   📁 Checking if submit directory exists..."
if [ -d "$SUBMIT_DIR" ]; then
    echo -e "   ${GREEN}✓ Directory exists${NC}"
else
    echo -e "   ${RED}✗ Directory does not exist${NC}"
    echo ""
    echo "⚠️  Submit directory doesn't exist on this system"
    echo "   This workflow may have been cleaned up or is on a different machine"
    exit 1
fi

echo ""

# Test 3c: Test pegasus-status command directly
echo "   ⚙️  Testing pegasus-status command directly..."
if command -v pegasus-status &> /dev/null; then
    echo "   ✓ pegasus-status found in PATH"

    # Try to run pegasus-status
    if pegasus-status "$SUBMIT_DIR" > /tmp/pegasus_status_output.txt 2>&1; then
        echo -e "   ${GREEN}✓ pegasus-status executed successfully${NC}"
        echo ""
        echo "   Output preview:"
        head -5 /tmp/pegasus_status_output.txt | sed 's/^/      /'
    else
        echo -e "   ${RED}✗ pegasus-status failed${NC}"
        echo ""
        echo "   Error:"
        head -5 /tmp/pegasus_status_output.txt | sed 's/^/      /'
        exit 1
    fi
else
    echo -e "   ${RED}✗ pegasus-status not found in PATH${NC}"
    echo ""
    echo "❌ Pegasus WMS tools are not installed or not in PATH"
    echo ""
    echo "Make sure Pegasus WMS is installed and available:"
    echo "   which pegasus-status"
    exit 1
fi

echo ""

# Test 4: Query Pegasus Provider
echo "4️⃣  Testing Pegasus Provider API..."
echo ""

# Test jobs endpoint
echo "   📋 Testing /api/workflows/{id}/jobs endpoint..."
JOBS_RESPONSE=$(curl -s "$PROVIDER_URL/api/workflows/$WORKFLOW_ID/jobs")
echo "$JOBS_RESPONSE" | python3 -m json.tool > /tmp/provider_jobs_response.json 2>/dev/null

JOBS_SUCCESS=$(echo "$JOBS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)

if [ "$JOBS_SUCCESS" = "True" ]; then
    JOB_COUNT=$(echo "$JOBS_RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('jobs', [])))" 2>/dev/null)
    echo -e "   ${GREEN}✓ Success - Found $JOB_COUNT jobs${NC}"
else
    echo -e "   ${RED}✗ Failed${NC}"
    ERROR_MSG=$(echo "$JOBS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null)
    echo "   Error: $ERROR_MSG"
fi

echo ""

# Test full analysis endpoint
echo "   📊 Testing /api/workflows/{id}/full endpoint..."
FULL_RESPONSE=$(curl -s "$PROVIDER_URL/api/workflows/$WORKFLOW_ID/full")
echo "$FULL_RESPONSE" | python3 -m json.tool > /tmp/provider_full_response.json 2>/dev/null

echo "   Response saved to: /tmp/provider_full_response.json"
echo ""

# Check if response has data
HAS_STATUS=$(echo "$FULL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print('status' in data)" 2>/dev/null)
HAS_ANALYZER=$(echo "$FULL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print('analyzer' in data)" 2>/dev/null)
HAS_STATS=$(echo "$FULL_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print('statistics' in data)" 2>/dev/null)

echo "   Response contains:"
if [ "$HAS_STATUS" = "True" ]; then
    echo -e "      ${GREEN}✓${NC} status"
else
    echo -e "      ${RED}✗${NC} status"
fi

if [ "$HAS_ANALYZER" = "True" ]; then
    echo -e "      ${GREEN}✓${NC} analyzer"
else
    echo -e "      ${RED}✗${NC} analyzer"
fi

if [ "$HAS_STATS" = "True" ]; then
    echo -e "      ${GREEN}✓${NC} statistics"
else
    echo -e "      ${RED}✗${NC} statistics"
fi

echo ""
echo "=================================="
echo "✅ Diagnostic Complete"
echo "=================================="
echo ""
echo "Next steps:"
echo "  1. Check Pegasus Provider logs:"
echo "     tail -f logs/pegasus_provider.log"
echo ""
echo "  2. View saved responses:"
echo "     cat /tmp/monitor_response.json"
echo "     cat /tmp/provider_jobs_response.json"
echo "     cat /tmp/provider_full_response.json"
echo ""
echo "  3. Test in browser:"
echo "     Open: http://localhost:5000/workflow/$WORKFLOW_ID"
echo ""
