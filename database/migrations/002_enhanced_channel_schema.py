"""
Enhanced Channel Schema Migration - Story 1.2
Implements multi-channel file management with health monitoring and failover capabilities
"""
import logging
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

class EnhancedChannelSchemaMigration:
    """Migration to enhance channel schema for multi-channel file management"""
    
    @staticmethod
    async def upgrade():
        """Apply enhanced channel schema changes"""
        try:
            # Enhanced channels table with new columns
            await supabase_client.execute_command("""
                -- Drop existing channels table if it's basic
                DROP TABLE IF EXISTS channels CASCADE;
                
                -- Create enhanced channels table
                CREATE TABLE channels (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    channel_id BIGINT UNIQUE NOT NULL,
                    channel_username VARCHAR(100),
                    channel_type VARCHAR(20) NOT NULL CHECK (channel_type IN ('primary', 'backup', 'archive')),
                    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'degraded', 'failed', 'maintenance')),
                    priority INTEGER DEFAULT 100, -- Lower number = higher priority
                    capacity_limit BIGINT DEFAULT NULL, -- Max files (if applicable)
                    current_files INTEGER DEFAULT 0,
                    last_health_check TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    health_score INTEGER DEFAULT 100 CHECK (health_score >= 0 AND health_score <= 100),
                    response_time_ms INTEGER DEFAULT NULL,
                    success_rate DECIMAL(5,2) DEFAULT 100.00,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # File storage tracking table
            await supabase_client.execute_command("""
                CREATE TABLE file_storage (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    course_file_id UUID REFERENCES course_files(id) ON DELETE CASCADE,
                    channel_id UUID REFERENCES channels(id) ON DELETE CASCADE,
                    message_id BIGINT NOT NULL,
                    message_link TEXT NOT NULL,
                    storage_status VARCHAR(20) DEFAULT 'active' CHECK (storage_status IN ('active', 'corrupted', 'missing', 'archived')),
                    file_size BIGINT,
                    checksum VARCHAR(64),
                    verification_attempts INTEGER DEFAULT 0,
                    last_verified TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    stored_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(course_file_id, channel_id)
                );
            """)
            
            # Channel health logs for monitoring
            await supabase_client.execute_command("""
                CREATE TABLE channel_health_logs (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    channel_id UUID REFERENCES channels(id) ON DELETE CASCADE,
                    check_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    status VARCHAR(20) NOT NULL,
                    response_time_ms INTEGER,
                    error_message TEXT,
                    health_score INTEGER,
                    test_type VARCHAR(50) DEFAULT 'basic' CHECK (test_type IN ('basic', 'upload', 'download', 'permissions'))
                );
            """)
            
            # Anonymous delivery logs (without identity correlation)
            await supabase_client.execute_command("""
                CREATE TABLE anonymous_delivery_logs (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    file_hash VARCHAR(64) NOT NULL, -- File identifier without revealing source
                    delivery_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    channel_used UUID REFERENCES channels(id),
                    success BOOLEAN NOT NULL,
                    user_hash VARCHAR(64), -- Anonymous user identifier
                    bandwidth_used BIGINT,
                    delivery_method VARCHAR(50) DEFAULT 'forward' CHECK (delivery_method IN ('forward', 'copy', 'download'))
                );
            """)
            
            # Channel failover events
            await supabase_client.execute_command("""
                CREATE TABLE channel_failover_events (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    failed_channel_id UUID REFERENCES channels(id),
                    backup_channel_id UUID REFERENCES channels(id),
                    failover_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    reason TEXT,
                    files_affected INTEGER DEFAULT 0,
                    recovery_time_seconds INTEGER
                );
            """)
            
            logger.info("Enhanced channel schema created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create enhanced channel schema: {e}")
            raise
    
    @staticmethod
    async def create_indexes():
        """Create performance indexes for enhanced schema"""
        try:
            # Channel indexes
            await supabase_client.execute_command("""
                CREATE INDEX IF NOT EXISTS idx_channels_type_status ON channels(channel_type, status);
                CREATE INDEX IF NOT EXISTS idx_channels_priority ON channels(priority) WHERE status = 'active';
                CREATE INDEX IF NOT EXISTS idx_channels_health_score ON channels(health_score);
                CREATE INDEX IF NOT EXISTS idx_channels_last_health_check ON channels(last_health_check);
            """)
            
            # File storage indexes
            await supabase_client.execute_command("""
                CREATE INDEX IF NOT EXISTS idx_file_storage_course_file ON file_storage(course_file_id);
                CREATE INDEX IF NOT EXISTS idx_file_storage_channel ON file_storage(channel_id);
                CREATE INDEX IF NOT EXISTS idx_file_storage_status ON file_storage(storage_status);
                CREATE INDEX IF NOT EXISTS idx_file_storage_checksum ON file_storage(checksum);
            """)
            
            # Health log indexes
            await supabase_client.execute_command("""
                CREATE INDEX IF NOT EXISTS idx_health_logs_channel_time ON channel_health_logs(channel_id, check_time DESC);
                CREATE INDEX IF NOT EXISTS idx_health_logs_status ON channel_health_logs(status);
            """)
            
            # Anonymous delivery indexes
            await supabase_client.execute_command("""
                CREATE INDEX IF NOT EXISTS idx_anonymous_delivery_time ON anonymous_delivery_logs(delivery_time DESC);
                CREATE INDEX IF NOT EXISTS idx_anonymous_delivery_success ON anonymous_delivery_logs(success);
                CREATE INDEX IF NOT EXISTS idx_anonymous_delivery_file_hash ON anonymous_delivery_logs(file_hash);
            """)
            
            # Failover event indexes
            await supabase_client.execute_command("""
                CREATE INDEX IF NOT EXISTS idx_failover_events_time ON channel_failover_events(failover_time DESC);
                CREATE INDEX IF NOT EXISTS idx_failover_events_failed_channel ON channel_failover_events(failed_channel_id);
            """)
            
            logger.info("Enhanced channel indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create enhanced channel indexes: {e}")
            raise
    
    @staticmethod
    async def setup_triggers():
        """Setup database triggers for automatic health monitoring"""
        try:
            # Trigger to update channel updated_at timestamp
            await supabase_client.execute_command("""
                CREATE OR REPLACE FUNCTION update_channel_timestamp()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                
                DROP TRIGGER IF EXISTS trigger_update_channel_timestamp ON channels;
                CREATE TRIGGER trigger_update_channel_timestamp
                    BEFORE UPDATE ON channels
                    FOR EACH ROW EXECUTE FUNCTION update_channel_timestamp();
            """)
            
            # Trigger to update current_files count
            await supabase_client.execute_command("""
                CREATE OR REPLACE FUNCTION update_channel_file_count()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF TG_OP = 'INSERT' THEN
                        UPDATE channels 
                        SET current_files = current_files + 1 
                        WHERE id = NEW.channel_id;
                        RETURN NEW;
                    ELSIF TG_OP = 'DELETE' THEN
                        UPDATE channels 
                        SET current_files = current_files - 1 
                        WHERE id = OLD.channel_id AND current_files > 0;
                        RETURN OLD;
                    END IF;
                    RETURN NULL;
                END;
                $$ LANGUAGE plpgsql;
                
                DROP TRIGGER IF EXISTS trigger_update_file_count_insert ON file_storage;
                DROP TRIGGER IF EXISTS trigger_update_file_count_delete ON file_storage;
                
                CREATE TRIGGER trigger_update_file_count_insert
                    AFTER INSERT ON file_storage
                    FOR EACH ROW EXECUTE FUNCTION update_channel_file_count();
                    
                CREATE TRIGGER trigger_update_file_count_delete
                    AFTER DELETE ON file_storage
                    FOR EACH ROW EXECUTE FUNCTION update_channel_file_count();
            """)
            
            logger.info("Database triggers created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create database triggers: {e}")
            raise
    
    @staticmethod
    async def insert_default_channels():
        """Insert default channel configurations"""
        try:
            # This would typically be configured via environment variables
            # For now, creating placeholders that can be updated via admin interface
            default_channels = [
                {
                    'channel_id': -1001000000001,  # Placeholder - to be updated
                    'channel_username': 'primary_courses',
                    'channel_type': 'primary',
                    'priority': 1
                },
                {
                    'channel_id': -1001000000002,  # Placeholder - to be updated  
                    'channel_username': 'backup_courses_1',
                    'channel_type': 'backup',
                    'priority': 2
                },
                {
                    'channel_id': -1001000000003,  # Placeholder - to be updated
                    'channel_username': 'backup_courses_2', 
                    'channel_type': 'backup',
                    'priority': 3
                }
            ]
            
            for channel_data in default_channels:
                await supabase_client.execute_command(
                    """
                    INSERT INTO channels (channel_id, channel_username, channel_type, priority)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (channel_id) DO UPDATE SET
                    channel_username = $2, channel_type = $3, priority = $4
                    """,
                    channel_data['channel_id'],
                    channel_data['channel_username'],
                    channel_data['channel_type'], 
                    channel_data['priority']
                )
            
            logger.info("Default channels inserted successfully")
            
        except Exception as e:
            logger.error(f"Failed to insert default channels: {e}")
            raise

# Helper function to run migration
async def run_enhanced_channel_migration():
    """Run the enhanced channel schema migration"""
    migration = EnhancedChannelSchemaMigration()
    await migration.upgrade()
    await migration.create_indexes()
    await migration.setup_triggers()
    await migration.insert_default_channels()
    logger.info("Enhanced channel migration completed successfully")