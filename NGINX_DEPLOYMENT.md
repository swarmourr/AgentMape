# MAPE-K System - Nginx Reverse Proxy Deployment

This guide shows how to expose all MAPE-K services through a **single nginx reverse proxy** on port 8000, eliminating CORS issues when using ngrok or deploying to cloud.

## Architecture

```
                    ┌──────────────────┐
                    │   Ngrok Tunnel   │
                    │  (one tunnel!)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   Nginx :8000    │
                    │  Reverse Proxy   │
                    └────────┬─────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐      ┌───────▼──────┐   ┌───────▼──────┐
    │Dashboard│      │   Monitor    │   │   Pegasus    │
    │  :8085  │      │    :8080     │   │  Provider    │
    └─────────┘      └──────────────┘   │    :8084     │
                                         └──────────────┘
```

## Benefits

✅ **No CORS issues** - All services on same domain
✅ **Single ngrok tunnel** - One URL for everything
✅ **Simpler deployment** - One entry point
✅ **Better security** - Internal services not exposed directly

## URL Mapping

| Service | Internal Port | Nginx Path | Example |
|---------|--------------|------------|---------|
| Dashboard | 8085 | `/` | `http://localhost:8000/` |
| Monitor API | 8080 | `/api/monitor/*` | `http://localhost:8000/api/monitor/workflows/all` |
| Pegasus Provider | 8084 | `/api/pegasus/*` | `http://localhost:8000/api/pegasus/workflows/{id}/jobs` |
| Analyzer | 8081 | `/api/analyzer/*` | `http://localhost:8000/api/analyzer/...` |
| Planner | 8082 | `/api/planner/*` | `http://localhost:8000/api/planner/...` |
| Executor | 8083 | `/api/executor/*` | `http://localhost:8000/api/executor/...` |

## Setup Instructions

### 1. Install Nginx (if not installed)

**macOS:**
```bash
brew install nginx
```

**Ubuntu/Debian:**
```bash
sudo apt-get install nginx
```

**CentOS/RHEL:**
```bash
sudo yum install nginx
```

### 2. Start MAPE-K Services

```bash
cd /Users/hamzasafri/Desktop/AgentMape
./start_system.sh
```

Wait for all services to start (check logs/health endpoints).

### 3. Start Nginx with Custom Config

```bash
# From the AgentMape directory
nginx -c "$(pwd)/nginx.conf"
```

**Verify nginx is running:**
```bash
curl http://localhost:8000/nginx-health
# Should return: "Nginx OK"
```

### 4. Test Locally

Open browser: `http://localhost:8000`

You should see the dashboard and all data loading without CORS errors!

### 5. Expose via Ngrok (Optional)

**Single tunnel for everything:**
```bash
ngrok http 8000
```

You'll get a URL like: `https://abc123.ngrok.io`

Access your dashboard at that URL - **No CORS issues!** ✅

## Configuration

The system automatically uses nginx paths via `Dashboard/static/config.js`:

```javascript
const CONFIG = {
    PEGASUS_PROVIDER_URL: window.location.origin + '/api/pegasus',
    MONITOR_URL: window.location.origin + '/api/monitor',
    REFRESH_INTERVAL: 15000
};
```

This works for:
- `http://localhost:8000` (local)
- `https://your-tunnel.ngrok.io` (ngrok)
- `https://your-domain.com` (production)

## Managing Nginx

**Check if nginx is running:**
```bash
ps aux | grep nginx
```

**View nginx logs:**
```bash
tail -f /tmp/nginx_mapek_access.log
tail -f /tmp/nginx_mapek_error.log
```

**Stop nginx:**
```bash
nginx -s stop
```

**Reload configuration (after changes):**
```bash
nginx -s reload
```

**Test configuration:**
```bash
nginx -t -c $(pwd)/nginx.conf
```

## Stopping Everything

```bash
# Stop MAPE-K services
./stop_system.sh

# Stop nginx
nginx -s stop
```

## Troubleshooting

### Nginx won't start

**Error: "Address already in use"**
```bash
# Check what's using port 8000
lsof -i :8000

# Kill it or change nginx port in nginx.conf
```

**Error: "nginx: [emerg] bind() to 0.0.0.0:8000 failed"**
```bash
# Try with sudo (if needed)
sudo nginx -c $(pwd)/nginx.conf
```

### Services not responding

**Check if all services are running:**
```bash
curl http://localhost:8085/  # Dashboard
curl http://localhost:8080/health  # Monitor
curl http://localhost:8084/health  # Pegasus Provider
```

**Check nginx logs:**
```bash
tail -20 /tmp/nginx_mapek_error.log
```

### Dashboard loads but no data

**Test nginx routing:**
```bash
# Should return JSON (not 404)
curl http://localhost:8000/api/monitor/workflows/all
curl http://localhost:8000/api/pegasus/health
```

**Check browser console** (F12) for errors

## Production Deployment

For production, modify `nginx.conf`:

1. Change `listen 8000` to `listen 80` (HTTP) or `listen 443 ssl` (HTTPS)
2. Add SSL certificates if using HTTPS
3. Change `server_name localhost` to your domain
4. Consider adding authentication
5. Set up proper logging paths

## Cloud Deployment

For cloud (AWS, Azure, GCP, etc.):

1. Deploy all services on same VM/instance
2. Run nginx with this config
3. Open port 8000 (or 80/443) in security group/firewall
4. Access via public IP or domain name
5. **No need for ngrok/pinggy in production!**

---

**Ready to deploy!** 🚀

Access via: `http://localhost:8000` (local) or your ngrok URL (public)
