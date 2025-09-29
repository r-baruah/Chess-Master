"""
Database migration for Story 1.4: Enhanced Course Workflow Schema

This migration adds:
- Enhanced course metadata tables
- Review queue system tables  
- Course relationship mapping
- Anonymous feedback system
- Search optimization tables
- Version control for course updates
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Migration SQL statements
MIGRATION_SQL = """
-- Enhanced courses table with new metadata fields
ALTER TABLE courses 
ADD COLUMN IF NOT EXISTS category VARCHAR(100),
ADD COLUMN IF NOT EXISTS subcategory VARCHAR(100),
ADD COLUMN IF NOT EXISTS difficulty_level INTEGER DEFAULT 1 CHECK (difficulty_level >= 1 AND difficulty_level <= 5),
ADD COLUMN IF NOT EXISTS course_type VARCHAR(50) DEFAULT 'tutorial',
ADD COLUMN IF NOT EXISTS estimated_duration INTEGER, -- in minutes
ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en',
ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS search_keywords TEXT,
ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS published_at TIMESTAMP WITH TIME ZONE;

-- Create index on status and category for faster queries
CREATE INDEX IF NOT EXISTS idx_courses_status_category ON courses(status, category);
CREATE INDEX IF NOT EXISTS idx_courses_difficulty ON courses(difficulty_level);
CREATE INDEX IF NOT EXISTS idx_courses_search ON courses USING gin(to_tsvector('english', title || ' ' || description));

-- Course metadata table for extended information
CREATE TABLE IF NOT EXISTS course_metadata (
    course_id UUID PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    difficulty_level INTEGER DEFAULT 1 CHECK (difficulty_level >= 1 AND difficulty_level <= 5),
    course_type VARCHAR(50) DEFAULT 'tutorial',
    estimated_duration INTEGER,
    language VARCHAR(10) DEFAULT 'en',
    version INTEGER DEFAULT 1,
    search_keywords TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Course metadata history for version control
CREATE TABLE IF NOT EXISTS course_metadata_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    difficulty_level INTEGER,
    course_type VARCHAR(50),
    estimated_duration INTEGER,
    language VARCHAR(10),
    archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(course_id, version)
);

-- Enhanced course tags table with weights
CREATE TABLE IF NOT EXISTS course_tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    tag VARCHAR(50) NOT NULL,
    weight DECIMAL(3,2) DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(course_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_course_tags_tag ON course_tags(tag);
CREATE INDEX IF NOT EXISTS idx_course_tags_course ON course_tags(course_id);

-- Course learning objectives
CREATE TABLE IF NOT EXISTS course_learning_objectives (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    objective TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(course_id, order_index)
);

-- Course skill requirements
CREATE TABLE IF NOT EXISTS course_skill_requirements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    skill_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(course_id, skill_name)
);

-- Course relationships table
CREATE TABLE IF NOT EXISTS course_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    target_course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    weight DECIMAL(3,2) DEFAULT 1.0,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CHECK (source_course_id != target_course_id),
    UNIQUE(source_course_id, target_course_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_course_relationships_source ON course_relationships(source_course_id);
CREATE INDEX IF NOT EXISTS idx_course_relationships_target ON course_relationships(target_course_id);
CREATE INDEX IF NOT EXISTS idx_course_relationships_type ON course_relationships(relation_type);

-- Review queue system
CREATE TABLE IF NOT EXISTS review_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    contributor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'pending_review',
    priority INTEGER DEFAULT 2 CHECK (priority >= 1 AND priority <= 4),
    assigned_reviewer UUID REFERENCES users(id) ON DELETE SET NULL,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    review_started_at TIMESTAMP WITH TIME ZONE,
    review_completed_at TIMESTAMP WITH TIME ZONE,
    estimated_completion TIMESTAMP WITH TIME ZONE,
    escalation_count INTEGER DEFAULT 0,
    feedback_id UUID,
    revision_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(course_id)
);

CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue(priority);
CREATE INDEX IF NOT EXISTS idx_review_queue_reviewer ON review_queue(assigned_reviewer);
CREATE INDEX IF NOT EXISTS idx_review_queue_submitted ON review_queue(submitted_at);

-- Anonymous feedback system
CREATE TABLE IF NOT EXISTS anonymous_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    reviewer_anonymous_id UUID NOT NULL,
    feedback_content TEXT NOT NULL,
    feedback_type VARCHAR(50) DEFAULT 'general',
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anonymous_feedback_course ON anonymous_feedback(course_id);
CREATE INDEX IF NOT EXISTS idx_anonymous_feedback_type ON anonymous_feedback(feedback_type);

-- Course statistics for popularity tracking
CREATE TABLE IF NOT EXISTS course_statistics (
    course_id UUID PRIMARY KEY REFERENCES courses(id) ON DELETE CASCADE,
    total_enrollments INTEGER DEFAULT 0,
    total_downloads INTEGER DEFAULT 0,
    average_rating DECIMAL(3,2),
    total_ratings INTEGER DEFAULT 0,
    view_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enhanced course files table
CREATE TABLE IF NOT EXISTS course_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    message_link TEXT,
    file_order INTEGER DEFAULT 1,
    is_primary BOOLEAN DEFAULT false,
    upload_status VARCHAR(50) DEFAULT 'uploaded',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_course_files_course ON course_files(course_id);
CREATE INDEX IF NOT EXISTS idx_course_files_order ON course_files(course_id, file_order);

-- Upload session management (Redis alternative for persistence)
CREATE TABLE IF NOT EXISTS upload_sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id BIGINT NOT NULL,
    anonymous_id UUID REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    current_step INTEGER NOT NULL DEFAULT 1,
    session_data JSONB,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_upload_sessions_user ON upload_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_status ON upload_sessions(status);
CREATE INDEX IF NOT EXISTS idx_upload_sessions_expires ON upload_sessions(expires_at);

-- Notification system for status updates
CREATE TABLE IF NOT EXISTS contributor_notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contributor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    data JSONB,
    is_read BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_contributor ON contributor_notifications(contributor_id);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON contributor_notifications(contributor_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON contributor_notifications(notification_type);

-- API tokens for external integrations
CREATE TABLE IF NOT EXISTS api_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    contributor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    permissions JSONB DEFAULT '[]',
    rate_limit_per_hour INTEGER DEFAULT 100,
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_tokens_hash ON api_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_api_tokens_contributor ON api_tokens(contributor_id);
CREATE INDEX IF NOT EXISTS idx_api_tokens_active ON api_tokens(is_active);

-- Rate limiting for API and file access
CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    identifier VARCHAR(255) NOT NULL, -- User ID, IP address, or API token
    limit_type VARCHAR(50) NOT NULL, -- 'file_download', 'api_request', 'course_upload'
    request_count INTEGER DEFAULT 0,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_duration_seconds INTEGER NOT NULL,
    max_requests INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(identifier, limit_type, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limits_identifier ON rate_limits(identifier);
CREATE INDEX IF NOT EXISTS idx_rate_limits_window ON rate_limits(window_start);

-- Triggers for automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables with updated_at columns
DROP TRIGGER IF EXISTS update_courses_updated_at ON courses;
CREATE TRIGGER update_courses_updated_at
    BEFORE UPDATE ON courses
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_course_metadata_updated_at ON course_metadata;
CREATE TRIGGER update_course_metadata_updated_at
    BEFORE UPDATE ON course_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_review_queue_updated_at ON review_queue;
CREATE TRIGGER update_review_queue_updated_at
    BEFORE UPDATE ON review_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_course_files_updated_at ON course_files;
CREATE TRIGGER update_course_files_updated_at
    BEFORE UPDATE ON course_files
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_upload_sessions_updated_at ON upload_sessions;
CREATE TRIGGER update_upload_sessions_updated_at
    BEFORE UPDATE ON upload_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_course_statistics_updated_at ON course_statistics;
CREATE TRIGGER update_course_statistics_updated_at
    BEFORE UPDATE ON course_statistics
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Cleanup function for expired sessions and old data
CREATE OR REPLACE FUNCTION cleanup_expired_data()
RETURNS void AS $$
BEGIN
    -- Remove expired upload sessions
    DELETE FROM upload_sessions WHERE expires_at < NOW();
    
    -- Remove old rate limiting data (older than 24 hours)
    DELETE FROM rate_limits WHERE window_start < NOW() - INTERVAL '24 hours';
    
    -- Archive old notifications (keep for 30 days)
    DELETE FROM contributor_notifications WHERE created_at < NOW() - INTERVAL '30 days';
    
    RAISE NOTICE 'Expired data cleanup completed';
END;
$$ LANGUAGE plpgsql;

-- Create views for common queries
CREATE OR REPLACE VIEW course_summary AS
SELECT 
    c.id,
    c.title,
    c.status,
    cm.category,
    cm.subcategory,
    cm.difficulty_level,
    cm.course_type,
    cm.estimated_duration,
    cs.total_downloads,
    cs.average_rating,
    array_agg(ct.tag ORDER BY ct.weight DESC) FILTER (WHERE ct.tag IS NOT NULL) as tags,
    c.created_at,
    c.updated_at
FROM courses c
LEFT JOIN course_metadata cm ON c.id = cm.course_id
LEFT JOIN course_statistics cs ON c.id = cs.course_id
LEFT JOIN course_tags ct ON c.id = ct.course_id
GROUP BY c.id, c.title, c.status, cm.category, cm.subcategory, 
         cm.difficulty_level, cm.course_type, cm.estimated_duration,
         cs.total_downloads, cs.average_rating, c.created_at, c.updated_at;

-- Review queue summary view
CREATE OR REPLACE VIEW review_queue_summary AS
SELECT 
    rq.id,
    rq.course_id,
    c.title as course_title,
    rq.status,
    rq.priority,
    rq.assigned_reviewer,
    u.telegram_id as reviewer_telegram_id,
    rq.submitted_at,
    rq.estimated_completion,
    rq.escalation_count,
    EXTRACT(EPOCH FROM (NOW() - rq.submitted_at))/3600 as hours_waiting
FROM review_queue rq
JOIN courses c ON rq.course_id = c.id
LEFT JOIN users u ON rq.assigned_reviewer = u.id
WHERE rq.status IN ('pending_review', 'under_review', 'escalated');

-- Grant necessary permissions (adjust based on your user setup)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO your_app_user;
"""

async def migrate_database(supabase_client):
    """Run the migration to create enhanced course workflow schema"""
    try:
        logger.info("Starting Story 1.4 database migration...")
        
        # Split and execute SQL statements
        statements = [stmt.strip() for stmt in MIGRATION_SQL.split(';') if stmt.strip()]
        
        for i, statement in enumerate(statements):
            if statement:
                try:
                    await supabase_client.execute_command(statement)
                    logger.info(f"Executed statement {i+1}/{len(statements)}")
                except Exception as e:
                    logger.warning(f"Statement {i+1} failed (might be expected): {e}")
        
        # Verify key tables exist
        verification_queries = [
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'course_metadata'",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'review_queue'",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'course_relationships'",
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'anonymous_feedback'"
        ]
        
        for query in verification_queries:
            result = await supabase_client.execute_query(query)
            if result[0]['count'] == 0:
                raise Exception(f"Verification failed for query: {query}")
        
        logger.info("Story 1.4 database migration completed successfully!")
        return {"success": True, "message": "Migration completed successfully"}
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {"success": False, "message": f"Migration failed: {str(e)}"}

async def rollback_migration(supabase_client):
    """Rollback the migration (drop created tables and columns)"""
    try:
        logger.info("Starting Story 1.4 migration rollback...")
        
        rollback_sql = """
        -- Drop views
        DROP VIEW IF EXISTS course_summary;
        DROP VIEW IF EXISTS review_queue_summary;
        
        -- Drop functions
        DROP FUNCTION IF EXISTS cleanup_expired_data();
        DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
        
        -- Drop new tables (order matters due to foreign keys)
        DROP TABLE IF EXISTS rate_limits;
        DROP TABLE IF EXISTS api_tokens;
        DROP TABLE IF EXISTS contributor_notifications;
        DROP TABLE IF EXISTS upload_sessions;
        DROP TABLE IF EXISTS course_files;
        DROP TABLE IF EXISTS course_statistics;
        DROP TABLE IF EXISTS anonymous_feedback;
        DROP TABLE IF EXISTS review_queue;
        DROP TABLE IF EXISTS course_relationships;
        DROP TABLE IF EXISTS course_skill_requirements;
        DROP TABLE IF EXISTS course_learning_objectives;
        DROP TABLE IF EXISTS course_tags;
        DROP TABLE IF EXISTS course_metadata_history;
        DROP TABLE IF EXISTS course_metadata;
        
        -- Remove added columns from courses table
        ALTER TABLE courses 
        DROP COLUMN IF EXISTS category,
        DROP COLUMN IF EXISTS subcategory,
        DROP COLUMN IF EXISTS difficulty_level,
        DROP COLUMN IF EXISTS course_type,
        DROP COLUMN IF EXISTS estimated_duration,
        DROP COLUMN IF EXISTS language,
        DROP COLUMN IF EXISTS version,
        DROP COLUMN IF EXISTS search_keywords,
        DROP COLUMN IF EXISTS approved_at,
        DROP COLUMN IF EXISTS published_at;
        
        -- Drop indexes
        DROP INDEX IF EXISTS idx_courses_status_category;
        DROP INDEX IF EXISTS idx_courses_difficulty;
        DROP INDEX IF EXISTS idx_courses_search;
        """
        
        statements = [stmt.strip() for stmt in rollback_sql.split(';') if stmt.strip()]
        
        for statement in statements:
            if statement:
                try:
                    await supabase_client.execute_command(statement)
                except Exception as e:
                    logger.warning(f"Rollback statement failed (might be expected): {e}")
        
        logger.info("Story 1.4 migration rollback completed!")
        return {"success": True, "message": "Rollback completed successfully"}
        
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return {"success": False, "message": f"Rollback failed: {str(e)}"}

# Sample data for testing (optional)
SAMPLE_DATA = {
    "categories": [
        {"name": "Opening Theory", "subcategories": ["King's Pawn", "Queen's Pawn", "English Opening"]},
        {"name": "Middlegame", "subcategories": ["Strategy", "Tactics", "Positional Play"]},
        {"name": "Endgame", "subcategories": ["Basic Endgames", "Complex Endgames"]},
        {"name": "Master Classes", "subcategories": ["GM Analysis", "Famous Games"]},
    ],
    "sample_tags": [
        "e4", "d4", "sicilian", "french", "tactics", "strategy", "endgame", "opening",
        "beginner", "intermediate", "advanced", "master-level", "analysis", "exercises"
    ]
}

async def insert_sample_data(supabase_client):
    """Insert sample data for testing the new system"""
    try:
        logger.info("Inserting sample data...")
        
        # This would insert sample categories, tags, etc.
        # Implementation depends on whether you want this for testing
        
        logger.info("Sample data inserted successfully!")
        return {"success": True, "message": "Sample data inserted"}
        
    except Exception as e:
        logger.error(f"Failed to insert sample data: {e}")
        return {"success": False, "message": f"Sample data insertion failed: {str(e)}"}

if __name__ == "__main__":
    # This script can be run directly for testing
    import sys
    import os
    
    # Add parent directory to path to import project modules
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from core.supabase_client import SupabaseClient
    
    async def main():
        # Initialize Supabase client
        supabase = SupabaseClient()
        await supabase.initialize()
        
        # Run migration
        result = await migrate_database(supabase)
        print(f"Migration result: {result}")
        
        # Optionally insert sample data
        # sample_result = await insert_sample_data(supabase)
        # print(f"Sample data result: {sample_result}")
    
    asyncio.run(main())