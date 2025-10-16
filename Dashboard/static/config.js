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

// Auto-detect if we're accessed via tunnel and use same origin for services
if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    // We're accessed via a tunnel, assume services are on the same origin with different ports
    const origin = window.location.origin;
    CONFIG.PEGASUS_PROVIDER_URL = origin.replace(':5000', ':8084');
    CONFIG.MONITOR_URL = origin.replace(':5000', ':8080');
    console.log('🌐 Detected tunnel access');
    console.log('   Pegasus Provider URL:', CONFIG.PEGASUS_PROVIDER_URL);
    console.log('   Monitor URL:', CONFIG.MONITOR_URL);
}
