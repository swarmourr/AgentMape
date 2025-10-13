# Architecture Changes - Pegasus Provider Service

## Summary

Separated Pegasus WMS data access into a dedicated microservice for better architecture.

## What Changed

### Before (Monolithic)
```
Monitor Agent (Port 8080)
├── Workflow discovery/tracking
├── Database management
├── Agent coordination
└── Pegasus command execution ❌ (mixed concerns)
```

### After (Microservices)
```
Monitor Agent (Port 8080)
├── Workflow discovery/tracking
├── Database management
└── Agent coordination

Pegasus Provider Service (Port 8084) ✅ NEW!
├── Pegasus command execution
├── Result caching (10s TTL)
├── Batch queries
└── Real-time data access
```

## Files Changed

### 1. Created: `/PegasusProvider/pegasus_provider_service.py`
- Standalone service for Pegasus WMS data
- Runs on port 8084
- Queries Monitor for workflow submit directories
- Executes pegasus commands in isolation
- Provides CORS support for dashboard

### 2. Updated: `/Dashboard/templates/dashboard.html`
- Changed: `localhost:8080` → `localhost:8084` for Pegasus data
- Line 1889: Now queries PegasusProvider for analyzer data

### 3. Updated: `/Dashboard/templates/workflow_details.html`
- Changed: `localhost:8080` → `localhost:8084` for Pegasus data
- Line 442: Now queries PegasusProvider for full analysis

### 4. Created: `/PegasusProvider/requirements.txt`
- aiohttp>=3.8.0
- aiohttp-cors>=0.7.0

### 5. Created: `/Monitoring/requirements.txt`
- Added aiohttp-cors for CORS support
- Added other Monitor dependencies

### 6. Created: `/start_system.sh`
- Automated startup script for all services
- Health checks for each component

### 7. Created: `/stop_system.sh`
- Graceful shutdown for all services

### 8. Created: `/STARTUP_GUIDE.md`
- Complete documentation for starting the system
- Troubleshooting guide

## API Endpoints

### Pegasus Provider Service (Port 8084)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/info` | GET | Service metadata |
| `/api/workflows/{id}/status` | GET | Pegasus status |
| `/api/workflows/{id}/analyzer` | GET | Root cause analysis |
| `/api/workflows/{id}/statistics` | GET | Performance metrics |
| `/api/workflows/{id}/full` | GET | Combined analysis |
| `/api/workflows/batch` | POST | Batch query |
| `/api/cache` | DELETE | Clear cache |
| `/api/cache/stats` | GET | Cache statistics |

## Benefits

### 1. Separation of Concerns
- Monitor: Workflow lifecycle management
- Provider: Data access layer

### 2. Scalability
- Can scale Provider independently
- Handle heavy Pegasus queries without affecting Monitor

### 3. Reusability
- Any service can use Provider API
- Not locked to Monitor

### 4. Performance
- Dedicated caching layer (10s TTL)
- Prevents duplicate command execution
- Batch query support for multiple workflows

### 5. Maintainability
- Single source of truth for Pegasus integration
- Easier to update command parsing
- Clear API contracts

## Data Flow

```
User Browser
    ↓
Dashboard (5000)
    ↓
    ├─→ Monitor API (8080)
    │       ↓
    │   [Workflow Database]
    │   [Agent Coordination]
    │
    └─→ Pegasus Provider API (8084)
            ↓
        [Command Cache]
            ↓
        Pegasus WMS Commands:
        ├─→ pegasus-status
        ├─→ pegasus-analyzer ← ROOT CAUSE DETECTION
        └─→ pegasus-statistics
```

## Migration Path

### Step 1: ✅ Created PegasusProviderService
- Standalone service with full API

### Step 2: ✅ Updated Dashboard
- Points to PegasusProvider (port 8084)

### Step 3: ✅ Added Dependencies
- aiohttp-cors for CORS support

### Step 4: ⏳ Testing (Next)
- Start all services
- Verify dashboard loads
- Verify root causes display

### Step 5: Optional Cleanup (Future)
- Remove Pegasus endpoints from Monitor
- Monitor focuses purely on workflow tracking

## Key Design Decisions

### Why Query Monitor for Submit Directories?
```python
async def get_workflow_submit_dir(self, workflow_id: str):
    """Query Monitor to get workflow submit directory"""
    # This keeps separation - we don't store workflow data
```

**Rationale**: Provider remains stateless, Monitor is single source of truth for workflow metadata.

### Why 10-Second Cache?
- Workflows change state slowly
- Prevents hammering Pegasus commands
- Fresh enough for real-time monitoring

### Why CORS Support?
- Dashboard (port 5000) needs to access Provider (port 8084)
- Browser security requires explicit CORS headers

## Testing the New Architecture

```bash
# 1. Start all services
./start_system.sh

# 2. Verify Provider is running
curl http://localhost:8084/health

# 3. Test with real workflow
curl http://localhost:8084/api/workflows/WORKFLOW_ID/analyzer

# 4. Check cache
curl http://localhost:8084/api/cache/stats

# 5. Open dashboard
open http://localhost:5000
```

## Rollback Plan

If issues arise, can temporarily revert by:

1. Change dashboard URLs back to port 8080
2. Don't start PegasusProviderService
3. Use Monitor's existing Pegasus endpoints

However, the new architecture is **strongly recommended** for all the benefits listed above.
