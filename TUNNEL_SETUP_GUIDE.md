# Tunnel Setup Guide (ngrok/pinggy)

## Problem Solved

This guide fixes the CORS issue when exposing your dashboard via ngrok or pinggy. The problem occurs when:
- Dashboard is served from a tunnel URL (e.g., `https://xyz.pinggy.link`)
- Pegasus Provider runs on localhost:8084
- Browser blocks cross-origin requests due to CORS policy

## Solution Overview

We've implemented:
1. **Proper CORS configuration** in Pegasus Provider Service
2. **Configurable URLs** in dashboard templates
3. **Support for multiple deployment scenarios**

---

## Deployment Scenarios

### Scenario 1: Local Development (Default)

**Setup:**
- Dashboard: http://localhost:5000
- Pegasus Provider: http://localhost:8084
- Monitor: http://localhost:8080

**Configuration:** No changes needed! Everything works out of the box.

```bash
cd /Users/hamzasafri/Desktop/AgentMape
./start_system.sh
```

Open http://localhost:5000 in your browser.

---

### Scenario 2: Dashboard via Tunnel, Pegasus Provider Local

**NOT RECOMMENDED** - This setup has CORS issues that browsers will block.

---

### Scenario 3: Both Dashboard AND Pegasus Provider via Tunnels (RECOMMENDED)

This is the proper way to expose your system publicly.

#### Step 1: Start Your Services Locally

```bash
cd /Users/hamzasafri/Desktop/AgentMape

# Terminal 1: Start Monitor
cd Monitoring && python server_rest.py

# Terminal 2: Start Pegasus Provider
cd PegasusProvider && python pegasus_provider_service.py

# Terminal 3: Start Dashboard
cd Dashboard && python dashboard_server.py
```

#### Step 2: Create Tunnel for Dashboard (Port 5000)

**Using pinggy:**
```bash
ssh -p 443 -R0:localhost:5000 -L4300:localhost:4300 a.pinggy.io
```

You'll get a URL like: `https://xyz-123.a.pinggy.link`

**Using ngrok:**
```bash
ngrok http 5000
```

You'll get a URL like: `https://abc123.ngrok.io`

#### Step 3: Create Tunnel for Pegasus Provider (Port 8084)

**Using pinggy (new terminal):**
```bash
ssh -p 443 -R0:localhost:8084 -L4301:localhost:4301 a.pinggy.io
```

You'll get a URL like: `https://mno-456.a.pinggy.link`

**Using ngrok (new terminal):**
```bash
ngrok http 8084
```

You'll get a URL like: `https://def456.ngrok.io`

#### Step 4: Update Dashboard Configuration

Edit both dashboard template files:

**File 1:** `/Dashboard/templates/dashboard.html`

Find the CONFIG section (around line 1094) and update:

```javascript
const CONFIG = {
    // Update with your Pegasus Provider tunnel URL
    PEGASUS_PROVIDER_URL: 'https://mno-456.a.pinggy.link',  // Your Pegasus Provider tunnel

    REFRESH_INTERVAL: 15000
};
```

**File 2:** `/Dashboard/templates/workflow_details.html`

Find the CONFIG section (around line 402) and update:

```javascript
const CONFIG = {
    // Update with your Pegasus Provider tunnel URL
    PEGASUS_PROVIDER_URL: 'https://mno-456.a.pinggy.link',  // Your Pegasus Provider tunnel

    REFRESH_INTERVAL: 15000
};
```

#### Step 5: Access Your Dashboard

Open your Dashboard tunnel URL in a browser:
- `https://xyz-123.a.pinggy.link` (pinggy)
- `https://abc123.ngrok.io` (ngrok)

**Everything should now work without CORS errors!**

---

## Configuration Quick Reference

### Dashboard.html (Line ~1094)
```javascript
const CONFIG = {
    PEGASUS_PROVIDER_URL: 'http://localhost:8084',  // Local (default)
    // PEGASUS_PROVIDER_URL: 'https://your-tunnel.pinggy.link',  // Tunnel
    REFRESH_INTERVAL: 15000
};
```

### workflow_details.html (Line ~402)
```javascript
const CONFIG = {
    PEGASUS_PROVIDER_URL: 'http://localhost:8084',  // Local (default)
    // PEGASUS_PROVIDER_URL: 'https://your-tunnel.pinggy.link',  // Tunnel
    REFRESH_INTERVAL: 15000
};
```

---

## CORS Configuration (Already Fixed)

The Pegasus Provider Service now has proper CORS configuration:

**File:** `/PegasusProvider/pegasus_provider_service.py` (Line 73)

```python
cors = aiohttp_cors.setup(self.app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=False,  # Must be False with wildcard origin
        expose_headers="*",
        allow_headers="*",
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    )
})
```

**Key Points:**
- `allow_credentials=False` - Required when using wildcard (`*`) origin
- Allows all origins (`*`) - Works with any tunnel URL
- Supports all necessary HTTP methods
- Headers are handled automatically by aiohttp_cors

---

## Troubleshooting

### Error: "CORS policy: No 'Access-Control-Allow-Origin' header"

**Cause:** Pegasus Provider not configured properly or URL mismatch

**Fix:**
1. Verify Pegasus Provider is running: `curl http://localhost:8084/health`
2. Check CONFIG in dashboard templates points to correct URL
3. Restart Pegasus Provider after any code changes

### Error: "net::ERR_CONNECTION_REFUSED"

**Cause:** Service not running or tunnel not active

**Fix:**
1. Check all services are running locally
2. Verify tunnel URLs are active
3. Test tunnel directly: `curl https://your-tunnel-url/health`

### Error: "Failed to fetch" or "SyntaxError: The string did not match expected pattern"

**Cause:** Invalid JSON response, often due to HTML error page

**Fix:**
1. Open browser console (F12) and check Network tab
2. Look at the actual response from failed request
3. Common causes:
   - Tunnel expired (pinggy free tunnels expire)
   - Wrong URL in CONFIG
   - Service crashed

### Workflows Not Showing Root Causes

**Cause:** Pegasus Provider can't reach Monitor

**Fix:**
1. Monitor must be running locally (localhost:8080)
2. Pegasus Provider must be able to reach Monitor
3. If Monitor is also tunneled, update MONITOR_URL in pegasus_provider_service.py

---

## Testing Your Setup

### 1. Test Pegasus Provider Directly

```bash
# Local
curl http://localhost:8084/health

# Via Tunnel
curl https://your-pegasus-tunnel.pinggy.link/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "pegasus_data_provider",
  "timestamp": "2025-10-13T..."
}
```

### 2. Test Dashboard Access

Open browser console (F12) and look for:
```
📡 Using Pegasus Provider URL: https://your-tunnel.pinggy.link
🔍 Loading workflow data for: <workflow_id>
✅ Pegasus response status: 200
```

### 3. Test CORS

In browser console:
```javascript
fetch('https://your-pegasus-tunnel.pinggy.link/health')
  .then(r => r.json())
  .then(d => console.log('✅ CORS working:', d))
  .catch(e => console.error('❌ CORS error:', e));
```

---

## Best Practices

### 1. Use Persistent Tunnels

**Pinggy:**
- Free tunnels expire every 60 minutes
- Consider paid plan for persistent URLs

**ngrok:**
- Free tier gives random URLs each time
- Paid tier allows reserved domains

### 2. Update Configuration Once

When you get new tunnel URLs, update both config sections:
1. `dashboard.html` (line ~1094)
2. `workflow_details.html` (line ~402)

### 3. Keep Monitor Local

Monitor can stay on localhost - only Dashboard and Pegasus Provider need tunnels.

### 4. Security Considerations

- Tunnels expose your services publicly
- Consider adding authentication
- Don't expose sensitive workflows publicly
- Use HTTPS tunnels (default with ngrok/pinggy)

---

## Quick Commands

### Start with Local Access
```bash
cd /Users/hamzasafri/Desktop/AgentMape
./start_system.sh
# Access: http://localhost:5000
```

### Create Tunnels
```bash
# Dashboard tunnel (Terminal 1)
ssh -p 443 -R0:localhost:5000 a.pinggy.io

# Pegasus Provider tunnel (Terminal 2)
ssh -p 443 -R0:localhost:8084 a.pinggy.io
```

### Test Everything
```bash
# Test local services
curl http://localhost:8080/health  # Monitor
curl http://localhost:8084/health  # Pegasus Provider
curl http://localhost:5000         # Dashboard

# Test tunnels
curl https://your-dashboard-tunnel.pinggy.link
curl https://your-pegasus-tunnel.pinggy.link/health
```

---

## Summary

✅ **Fixed:** CORS configuration in Pegasus Provider
✅ **Added:** Configurable URLs in dashboard templates
✅ **Supports:** Multiple deployment scenarios
✅ **Works with:** ngrok, pinggy, and other tunnel services

**For public access:**
1. Create tunnels for BOTH Dashboard (5000) and Pegasus Provider (8084)
2. Update CONFIG in both dashboard template files
3. Access via Dashboard tunnel URL

**No CORS errors!** 🎉
