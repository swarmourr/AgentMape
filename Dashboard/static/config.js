// Dashboard Configuration - Shared across all dashboard pages
// Update these URLs based on your deployment

const CONFIG = {
    // Default: Local development
    PEGASUS_PROVIDER_URL: 'http://localhost:8084',
    MONITOR_URL: 'http://localhost:8080',

    // For ngrok/pinggy: Update with your tunnel URLs, e.g.:
    // PEGASUS_PROVIDER_URL: 'https://your-pegasus-tunnel.ngrok.io',
    // PEGASUS_PROVIDER_URL: 'https://your-pegasus-tunnel.pinggy.link',
    // MONITOR_URL: 'https://your-monitor-tunnel.ngrok.io',

    REFRESH_INTERVAL: 15000
};

// Auto-detect: Only use auto URLs if accessing via localhost
// For ngrok/pinggy tunnels, you MUST manually set URLs above
if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    console.warn('⚠️  Tunnel detected! Please configure URLs manually in config.js');
    console.warn('   Ngrok/Pinggy requires separate tunnels for each service');
    console.warn('   Current Pegasus Provider URL:', CONFIG.PEGASUS_PROVIDER_URL);
    console.warn('   Current Monitor URL:', CONFIG.MONITOR_URL);

    // Don't auto-change URLs for tunnels - user must set them manually
}
