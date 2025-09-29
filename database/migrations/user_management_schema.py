"""
User Management and Announcements Database Schema Migration
"""
import asyncio
import logging
from datetime import datetime
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

async def create_user_management_tables():
    """Create user management and announcement related tables"""
    
    # Announcements Table
    announcements_table = """
    CREATE TABLE IF NOT EXISTS announcements (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        creator_anonymous_id TEXT NOT NULL REFERENCES users(anonymous_id),
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        targeting_rules JSONB NOT NULL DEFAULT '{}',
        scheduling JSONB NOT NULL DEFAULT '{}',
        options JSONB NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'draft' 
            CHECK (status IN ('draft', 'scheduled', 'sending', 'sent', 'failed', 'cancelled')),
        estimated_recipients INTEGER DEFAULT 0,
        actual_recipients INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        sent_at TIMESTAMPTZ NULL,
        
        INDEX idx_announcements_creator (creator_anonymous_id),
        INDEX idx_announcements_status (status),
        INDEX idx_announcements_created_at (created_at)
    );
    """
    
    # Announcement Deliveries Table
    announcement_deliveries_table = """
    CREATE TABLE IF NOT EXISTS announcement_deliveries (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        announcement_id UUID NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
        recipient_anonymous_id TEXT NOT NULL REFERENCES users(anonymous_id),
        status TEXT NOT NULL DEFAULT 'pending' 
            CHECK (status IN ('pending', 'delivered', 'failed', 'bounced')),
        delivered_at TIMESTAMPTZ NULL,
        opened_at TIMESTAMPTZ NULL,
        clicked_at TIMESTAMPTZ NULL,
        error_message TEXT NULL,
        delivery_metadata JSONB DEFAULT '{}',
        
        INDEX idx_announcement_deliveries_announcement (announcement_id),
        INDEX idx_announcement_deliveries_recipient (recipient_anonymous_id),
        INDEX idx_announcement_deliveries_status (status),
        UNIQUE(announcement_id, recipient_anonymous_id)
    );
    """
    
    # Announcement Reports Table
    announcement_reports_table = """
    CREATE TABLE IF NOT EXISTS announcement_reports (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        announcement_id UUID NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
        delivery_stats JSONB NOT NULL DEFAULT '{}',
        engagement_stats JSONB DEFAULT '{}',
        performance_metrics JSONB DEFAULT '{}',
        generated_at TIMESTAMPTZ DEFAULT NOW(),
        
        INDEX idx_announcement_reports_announcement (announcement_id),
        INDEX idx_announcement_reports_generated_at (generated_at)
    );
    """
    
    # Announcement Templates Table
    announcement_templates_table = """
    CREATE TABLE IF NOT EXISTS announcement_templates (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        category TEXT NOT NULL DEFAULT 'general',
        title_template TEXT NOT NULL,
        content_template TEXT NOT NULL,
        default_targeting JSONB DEFAULT '{}',
        default_options JSONB DEFAULT '{}',
        creator_anonymous_id TEXT NOT NULL REFERENCES users(anonymous_id),
        is_public BOOLEAN DEFAULT false,
        usage_count INTEGER DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        
        INDEX idx_announcement_templates_category (category),
        INDEX idx_announcement_templates_creator (creator_anonymous_id),
        INDEX idx_announcement_templates_public (is_public)
    );
    """
    
    # User Activity Logs Table (Enhanced)
    user_activity_logs_table = """
    CREATE TABLE IF NOT EXISTS user_activity_logs (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        anonymous_id TEXT NOT NULL REFERENCES users(anonymous_id),
        activity_type TEXT NOT NULL,
        activity_details JSONB DEFAULT '{}',
        ip_address INET NULL,
        user_agent TEXT NULL,
        session_id TEXT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        
        INDEX idx_user_activity_logs_anonymous_id (anonymous_id),
        INDEX idx_user_activity_logs_type (activity_type),
        INDEX idx_user_activity_logs_created_at (created_at),
        INDEX idx_user_activity_logs_session (session_id)
    );
    """
    
    # User Preferences Table
    user_preferences_table = """
    CREATE TABLE IF NOT EXISTS user_preferences (
        anonymous_id TEXT PRIMARY KEY REFERENCES users(anonymous_id),
        notification_settings JSONB DEFAULT '{
            "announcements": true,
            "course_updates": true,
            "review_notifications": true,
            "weekly_digest": true
        }',
        communication_frequency TEXT DEFAULT 'normal' 
            CHECK (communication_frequency IN ('minimal', 'normal', 'frequent')),
        preferred_language TEXT DEFAULT 'en',
        timezone TEXT DEFAULT 'UTC',
        opt_out_from_analytics BOOLEAN DEFAULT false,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    
    # User Segments Table (for caching segment results)
    user_segments_table = """
    CREATE TABLE IF NOT EXISTS user_segments (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        segment_name TEXT NOT NULL,
        segment_rules JSONB NOT NULL,
        user_count INTEGER DEFAULT 0,
        last_calculated TIMESTAMPTZ DEFAULT NOW(),
        is_active BOOLEAN DEFAULT true,
        created_by TEXT NOT NULL REFERENCES users(anonymous_id),
        
        INDEX idx_user_segments_name (segment_name),
        INDEX idx_user_segments_active (is_active),
        INDEX idx_user_segments_calculated (last_calculated)
    );
    """
    
    # User Segment Memberships Table
    user_segment_memberships_table = """
    CREATE TABLE IF NOT EXISTS user_segment_memberships (
        segment_id UUID NOT NULL REFERENCES user_segments(id) ON DELETE CASCADE,
        anonymous_id TEXT NOT NULL REFERENCES users(anonymous_id),
        added_at TIMESTAMPTZ DEFAULT NOW(),
        
        PRIMARY KEY (segment_id, anonymous_id),
        INDEX idx_user_segment_memberships_user (anonymous_id)
    );
    """
    
    # Bulk Operations Log Table
    bulk_operations_log_table = """
    CREATE TABLE IF NOT EXISTS bulk_operations_log (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        operation_type TEXT NOT NULL,
        operator_anonymous_id TEXT NOT NULL REFERENCES users(anonymous_id),
        target_count INTEGER NOT NULL,
        successful_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        operation_parameters JSONB DEFAULT '{}',
        results JSONB DEFAULT '{}',
        started_at TIMESTAMPTZ DEFAULT NOW(),
        completed_at TIMESTAMPTZ NULL,
        status TEXT DEFAULT 'running' 
            CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
        
        INDEX idx_bulk_operations_type (operation_type),
        INDEX idx_bulk_operations_operator (operator_anonymous_id),
        INDEX idx_bulk_operations_started_at (started_at)
    );
    """
    
    try:
        # Execute table creation commands
        tables = [
            announcements_table,
            announcement_deliveries_table,
            announcement_reports_table,
            announcement_templates_table,
            user_activity_logs_table,
            user_preferences_table,
            user_segments_table,
            user_segment_memberships_table,
            bulk_operations_log_table
        ]
        
        for table_sql in tables:
            await supabase_client.execute_command(table_sql)
            logger.info(f"Created/verified table from SQL")
        
        # Create additional indexes for performance
        additional_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_announcements_targeting ON announcements USING GIN(targeting_rules);",
            "CREATE INDEX IF NOT EXISTS idx_announcement_deliveries_timing ON announcement_deliveries(delivered_at, opened_at);",
            "CREATE INDEX IF NOT EXISTS idx_user_activity_comprehensive ON user_activity_logs(anonymous_id, activity_type, created_at);",
            "CREATE INDEX IF NOT EXISTS idx_user_preferences_notifications ON user_preferences USING GIN(notification_settings);",
        ]
        
        for index_sql in additional_indexes:
            try:
                await supabase_client.execute_command(index_sql)
            except Exception as e:
                logger.warning(f"Index creation warning: {e}")
        
        logger.info("User management database schema migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create user management tables: {e}")
        return False

async def create_announcement_templates():
    """Create default announcement templates"""
    try:
        default_templates = [
            {
                'name': 'Welcome New Users',
                'description': 'Welcome message for new community members',
                'category': 'welcome',
                'title_template': 'Welcome to ChessMaster Community!',
                'content_template': '''🎉 Welcome to our chess learning community!

We're excited to have you here. Here's what you can do:

📚 Browse and download chess courses
🔍 Get your courses reviewed by volunteers
📊 Track your learning progress
🤝 Connect with fellow chess enthusiasts

Start exploring and happy learning! ♟️''',
                'default_targeting': {'target_type': 'segment_based', 'segments': {'new_users': True}},
                'is_public': True
            },
            {
                'name': 'Course Approval Notification',
                'description': 'Notify contributors when their course is approved',
                'category': 'course_management',
                'title_template': '✅ Your Course "{course_title}" has been Approved!',
                'content_template': '''Great news! Your chess course has been approved and is now available to the community.

📚 Course: {course_title}
✅ Status: Approved
👥 Now available to: All community members

Thank you for contributing to our chess learning community! Keep sharing your knowledge.

📊 Track your course performance in your dashboard.''',
                'default_targeting': {'target_type': 'custom_list'},
                'is_public': True
            },
            {
                'name': 'Weekly Community Update',
                'description': 'Weekly digest of community activity and highlights',
                'category': 'updates',
                'title_template': '📊 Weekly Community Digest - {week_date}',
                'content_template': '''📈 This Week in ChessMaster Community:

👥 New Members: {new_users_count}
📚 New Courses: {new_courses_count}
✅ Courses Approved: {approved_courses_count}
🔍 Reviews Completed: {reviews_completed_count}

🏆 Top Categories This Week:
{top_categories}

🎯 Featured Course: {featured_course}

Keep learning and contributing! ♟️''',
                'default_targeting': {'target_type': 'all_users'},
                'is_public': True
            },
            {
                'name': 'Volunteer Recruitment',
                'description': 'Invite active users to become volunteer reviewers',
                'category': 'recruitment',
                'title_template': '🔍 Become a Volunteer Reviewer',
                'content_template': '''We've noticed your active participation in our community!

Would you like to help improve course quality by becoming a volunteer reviewer?

🔍 As a reviewer, you'll:
• Help maintain high-quality content standards
• Get early access to new courses
• Contribute to community growth
• Gain reviewer recognition

⏱️ Estimated time: 2-3 hours per week
🎯 Perfect for: Experienced chess players

Interested? Reply to this message or contact an admin!''',
                'default_targeting': {'target_type': 'segment_based', 'segments': {'power_users': True}},
                'is_public': True
            }
        ]
        
        system_user_id = 'system'  # Placeholder for system-created templates
        
        for template in default_templates:
            await supabase_client.execute_command(
                """
                INSERT INTO announcement_templates (
                    name, description, category, title_template, 
                    content_template, default_targeting, default_options,
                    creator_anonymous_id, is_public
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT DO NOTHING
                """,
                template['name'], template['description'], template['category'],
                template['title_template'], template['content_template'],
                json.dumps(template['default_targeting']), json.dumps({}),
                system_user_id, template['is_public']
            )
        
        logger.info("Default announcement templates created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create announcement templates: {e}")
        return False

async def setup_user_preferences():
    """Setup default user preferences for existing users"""
    try:
        # Add default preferences for existing users who don't have them
        await supabase_client.execute_command(
            """
            INSERT INTO user_preferences (anonymous_id)
            SELECT anonymous_id FROM users 
            WHERE anonymous_id NOT IN (SELECT anonymous_id FROM user_preferences)
            """
        )
        
        logger.info("Default user preferences setup completed")
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup user preferences: {e}")
        return False

async def run_user_management_migration():
    """Run the complete user management migration"""
    logger.info("Starting user management database migration...")
    
    # Create tables
    if not await create_user_management_tables():
        logger.error("Failed to create user management tables")
        return False
    
    # Create default templates
    if not await create_announcement_templates():
        logger.error("Failed to create announcement templates")
        return False
    
    # Setup user preferences
    if not await setup_user_preferences():
        logger.error("Failed to setup user preferences")
        return False
    
    logger.info("User management database migration completed successfully")
    return True

if __name__ == "__main__":
    asyncio.run(run_user_management_migration())