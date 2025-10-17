# Quick Start - Nginx Setup

## 🚀 Start Everything

```bash
cd /Users/hamzasafri/Desktop/AgentMape
./start_with_nginx.sh
```

Access: `http://localhost:8000`

## 🌐 Expose with Ngrok (Single Tunnel!)

```bash
ngrok http 8000
```

Access via ngrok URL: `https://xxxxx.ngrok.io`

**✅ NO CORS ISSUES!** All services on same domain through nginx.

## 🛑 Stop Everything

```bash
nginx -s stop
./stop_system.sh
```

## 📊 API Endpoints Through Nginx

| Service | URL |
|---------|-----|
| Dashboard | `http://localhost:8000/` |
| Monitor API | `http://localhost:8000/api/monitor/...` |
| Pegasus Provider | `http://localhost:8000/api/pegasus/...` |

## ✅ What Changed

**Before (CORS problems):**
- Dashboard: `https://dashboard-tunnel.ngrok.io`
- Pegasus: `https://pegasus-tunnel.pinggy.link` ← Different domain = CORS!

**After (No CORS):**
- Everything: `https://single-tunnel.ngrok.io/...` ← Same domain = No CORS! ✅

## 🔍 Troubleshooting

**Port 8000 already in use:**
```bash
lsof -i :8000
kill -9 <PID>
```

**Check nginx logs:**
```bash
tail -f /tmp/nginx_mapek_access.log
tail -f /tmp/nginx_mapek_error.log
```

**Nginx won't start:**
```bash
# Test config
nginx -t -c $(pwd)/nginx.conf

# Check what's wrong
nginx -c $(pwd)/nginx.conf
```

## 📋 Full Documentation

See `NGINX_DEPLOYMENT.md` for complete details.
