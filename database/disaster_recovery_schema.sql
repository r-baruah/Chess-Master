-- Database schema for Story 1.6: Disaster Recovery and Multi-Bot Resilience
-- This file contains all necessary tables for the disaster recovery system

-- Bot tokens table for multi-bot token management
CREATE TABLE IF NOT EXISTS bot_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(255) NOT NULL UNIQUE,
    api_id INTEGER NOT NULL,
    api_hash VARCHAR(255) NOT NULL,
    bot_id BIGINT,
    username VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    priority INTEGER DEFAULT 0,
    performance_metrics JSONB,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_check TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Channel configurations for permission management
CREATE TABLE IF NOT EXISTS channel_configs (
    id SERIAL PRIMARY KEY,
    channel_id VARCHAR(255) NOT NULL,
    channel_type VARCHAR(100) NOT NULL,
    title VARCHAR(255),
    username VARCHAR(255),
    required_permissions JSONB,
    status VARCHAR(50) DEFAULT 'active',
    last_verified TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(channel_id, channel_type)
);

-- Permission test results for tracking channel access
CREATE TABLE IF NOT EXISTS permission_test_results (
    id SERIAL PRIMARY KEY,
    channel_id VARCHAR(255) NOT NULL,
    permission_type VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    test_time TIMESTAMP WITH TIME ZONE NOT NULL,
    bot_username VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Permission synchronization history
CREATE TABLE IF NOT EXISTS permission_sync_history (
    id SERIAL PRIMARY KEY,
    sync_time TIMESTAMP WITH TIME ZONE NOT NULL,
    total_tokens INTEGER NOT NULL,
    successful_tokens INTEGER NOT NULL,
    failed_tokens INTEGER NOT NULL,
    results_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System status tracking for various components
CREATE TABLE IF NOT EXISTS system_status (
    component VARCHAR(100) PRIMARY KEY,
    status_data JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System health monitoring history
CREATE TABLE IF NOT EXISTS system_health_history (
    id SERIAL PRIMARY KEY,
    check_time TIMESTAMP WITH TIME ZONE NOT NULL,
    overall_status VARCHAR(50) NOT NULL,
    component_data JSONB,
    critical_components JSONB,
    degraded_components JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Disaster recovery package tracking
CREATE TABLE IF NOT EXISTS recovery_packages (
    id SERIAL PRIMARY KEY,
    package_id VARCHAR(255) NOT NULL UNIQUE,
    package_data JSONB NOT NULL,
    checksum VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Admin settings for disaster recovery configuration
CREATE TABLE IF NOT EXISTS admin_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(255) NOT NULL UNIQUE,
    setting_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Failover events log
CREATE TABLE IF NOT EXISTS failover_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    from_component VARCHAR(255),
    to_component VARCHAR(255),
    reason TEXT,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    recovery_time_seconds NUMERIC(10,3),
    event_time TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_bot_tokens_status ON bot_tokens(status);
CREATE INDEX IF NOT EXISTS idx_bot_tokens_priority ON bot_tokens(priority DESC);
CREATE INDEX IF NOT EXISTS idx_channel_configs_type ON channel_configs(channel_type);
CREATE INDEX IF NOT EXISTS idx_channel_configs_status ON channel_configs(status);
CREATE INDEX IF NOT EXISTS idx_permission_test_results_channel ON permission_test_results(channel_id);
CREATE INDEX IF NOT EXISTS idx_permission_test_results_time ON permission_test_results(test_time DESC);
CREATE INDEX IF NOT EXISTS idx_system_health_history_time ON system_health_history(check_time DESC);
CREATE INDEX IF NOT EXISTS idx_system_health_history_status ON system_health_history(overall_status);
CREATE INDEX IF NOT EXISTS idx_failover_events_time ON failover_events(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_failover_events_type ON failover_events(event_type);

-- Insert default admin settings for disaster recovery
INSERT INTO admin_settings (setting_key, setting_value, description) 
VALUES 
    ('disaster_recovery_enabled', 'true', 'Enable disaster recovery features'),
    ('health_check_interval', '30', 'Health check interval in seconds'),
    ('failover_cooldown', '300', 'Cooldown period between failovers in seconds'),
    ('backup_retention_days', '30', 'Number of days to retain recovery packages'),
    ('notification_channels', '[]', 'Channels for disaster recovery notifications')
ON CONFLICT (setting_key) DO NOTHING;

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to relevant tables
DROP TRIGGER IF EXISTS update_bot_tokens_updated_at ON bot_tokens;
CREATE TRIGGER update_bot_tokens_updated_at BEFORE UPDATE ON bot_tokens FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_channel_configs_updated_at ON channel_configs;
CREATE TRIGGER update_channel_configs_updated_at BEFORE UPDATE ON channel_configs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_admin_settings_updated_at ON admin_settings;
CREATE TRIGGER update_admin_settings_updated_at BEFORE UPDATE ON admin_settings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create a view for system health overview
CREATE OR REPLACE VIEW system_health_overview AS
SELECT 
    h.check_time,
    h.overall_status,
    h.critical_components,
    h.degraded_components,
    COUNT(*) OVER (PARTITION BY h.overall_status) as status_count,
    LAG(h.overall_status) OVER (ORDER BY h.check_time) as previous_status,
    CASE 
        WHEN LAG(h.overall_status) OVER (ORDER BY h.check_time) != h.overall_status 
        THEN true 
        ELSE false 
    END as status_changed
FROM system_health_history h
ORDER BY h.check_time DESC;

-- Create a view for bot token health summary
CREATE OR REPLACE VIEW bot_tokens_health_summary AS
SELECT 
    count(*) as total_tokens,
    count(*) FILTER (WHERE status = 'active') as active_tokens,
    count(*) FILTER (WHERE status = 'healthy') as healthy_tokens,
    count(*) FILTER (WHERE status = 'degraded') as degraded_tokens,
    count(*) FILTER (WHERE status = 'failed') as failed_tokens,
    avg(error_count) as avg_error_count,
    max(last_check) as latest_check
FROM bot_tokens;

-- Create a view for recent failover events summary
CREATE OR REPLACE VIEW recent_failover_summary AS
SELECT 
    event_type,
    count(*) as event_count,
    count(*) FILTER (WHERE success = true) as successful_events,
    count(*) FILTER (WHERE success = false) as failed_events,
    avg(recovery_time_seconds) FILTER (WHERE success = true) as avg_recovery_time,
    max(event_time) as latest_event
FROM failover_events 
WHERE event_time > NOW() - INTERVAL '24 hours'
GROUP BY event_type
ORDER BY event_count DESC;