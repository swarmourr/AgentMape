# Simple Ngrok Setup (No Nginx Required!)

The Dashboard now acts as a **built-in reverse proxy** - no nginx installation needed!

## 🚀 Quick Start

### 1. Start all services:
```bash
cd /Users/hamzasafri/Desktop/AgentMape
./start_system.sh
```

### 2. Expose Dashboard via ngrok (single tunnel):
```bash
ngrok http 8085
```

### 3. Access via ngrok URL:
```
https://xxxxx.ngrok.io
```

**✅ NO CORS ISSUES!** Everything works through one tunnel.

## 🎯 How It Works

The Dashboard server (port 8085) now proxies requests to other services:

```
Browser
  ↓
https://your-tunnel.ngrok.io  (Dashboard)
  ↓
  ├── /                    → Dashboard UI
  ├── /api/monitor/*       → Monitor (8080)
  └── /api/pegasus/*       → Pegasus Provider (8084)
```

## 📊 URL Examples

| What | URL |
|------|-----|
| Dashboard | `https://xxxxx.ngrok.io/` |
| Workflow Details | `https://xxxxx.ngrok.io/workflow/abc123` |
| Monitor API | `https://xxxxx.ngrok.io/api/monitor/workflows/all` |
| Pegasus API | `https://xxxxx.ngrok.io/api/pegasus/workflows/{id}/jobs` |

## ✅ Benefits

- **No nginx installation required** ✅
- **Single ngrok tunnel** ✅
- **No CORS issues** ✅
- **Works on any OS** ✅
- **Simple setup** ✅

## 🔧 Configuration

The Dashboard automatically proxies requests. No configuration needed!

Check `Dashboard/static/config.js`:
```javascript
const CONFIG = {
    PEGASUS_PROVIDER_URL: window.location.origin + '/api/pegasus',
    MONITOR_URL: window.location.origin + '/api/monitor',
    REFRESH_INTERVAL: 15000
};
```

This works for:
- `http://localhost:8085` (local)
- `https://xxxxx.ngrok.io` (ngrok)
- `https://your-domain.com` (production)

## 🛑 Stopping

```bash
./stop_system.sh
```

Then stop ngrok (Ctrl+C in ngrok terminal)

## 🌐 Cloud Deployment

For production deployment, just:

1. Deploy all services on same server
2. Expose Dashboard port (8085) through firewall/load balancer
3. Access via your domain
4. Dashboard proxies all API requests automatically

**No nginx, no CORS configuration needed!**

## 🔍 Troubleshooting

### Dashboard not proxying?

Check logs in Dashboard terminal - you should see:
```
╔══════════════════════════════════════════════════════════════════════════════╗
║                     🎯 MAPE-K DASHBOARD SERVER                               ║
║                   (with built-in reverse proxy!)                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
```

### Still getting CORS errors?

Make sure you're accessing via ngrok URL, not multiple different URLs.

### Services not responding?

Check all services are running:
```bash
curl http://localhost:8085/  # Dashboard
curl http://localhost:8080/health  # Monitor
curl http://localhost:8084/health  # Pegasus Provider
```

---

**That's it!** Simple, no nginx needed. 🎉
