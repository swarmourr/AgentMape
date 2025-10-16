// Dashboard Configuration
// Change these URLs based on your deployment

const CONFIG = {
    // For local development
    //PEGASUS_PROVIDER_URL: 'http://localhost:8084',

    // For ngrok/pinggy tunnel - uncomment and update with your tunnel URL
    PEGASUS_PROVIDER_URL: 'https://jvred-149-165-153-107.a.free.pinggy.link',
    // PEGASUS_PROVIDER_URL: 'https://your-tunnel-url.pinggy.link',

    MONITOR_URL: 'http://localhost:8080',

    // Auto-refresh interval (milliseconds)
    REFRESH_INTERVAL: 15000
};

// Make config available globally
window.DASHBOARD_CONFIG = CONFIG;
