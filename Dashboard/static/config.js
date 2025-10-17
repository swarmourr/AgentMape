// Dashboard Configuration - Shared across all dashboard pages
// Update these URLs based on your deployment

const CONFIG = {
    // Using nginx reverse proxy - all services through same origin
    // Works for: localhost:8000, ngrok, or cloud deployment
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
console.log('   ✅ Using nginx reverse proxy - no CORS issues!');
