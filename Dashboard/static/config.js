// Dashboard Configuration - Shared across all dashboard pages
// Dashboard acts as reverse proxy - all services through same origin!

const CONFIG = {
    // Dashboard proxies requests to other services
    // Works for: localhost:8085, ngrok, or any deployment
    // No CORS issues! All APIs accessed through same domain
    PEGASUS_PROVIDER_URL: window.location.origin + '/api/pegasus',
    MONITOR_URL: window.location.origin + '/api/monitor',

    REFRESH_INTERVAL: 15000
};

// Debug logging
console.log('🔧 MAPE-K Dashboard Configuration:');
console.log('   Origin:', window.location.origin);
console.log('   Pegasus Provider URL:', CONFIG.PEGASUS_PROVIDER_URL);
console.log('   Monitor URL:', CONFIG.MONITOR_URL);
console.log('   ✅ Using Dashboard as reverse proxy - no CORS issues!');
