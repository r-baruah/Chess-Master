"""
Database Schema Updates for Story 1.5 - Volunteer Review and Management System
This script adds all the necessary tables and indexes for the enhanced volunteer system
"""
import logging
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

class VolunteerSystemSchema:
    """Schema updates for volunteer review and management system"""
    
    @staticmethod
    async def create_volunteer_system_tables():
        """Create all tables needed for the volunteer review system"""
        try:
            # Review Feedback table for structured feedback
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS review_feedback (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    review_id UUID REFERENCES reviews(id) ON DELETE CASCADE,
                    course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
                    reviewer_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    decision VARCHAR(50) NOT NULL,
                    quality_rating VARCHAR(50) NOT NULL,
                    feedback_text TEXT,
                    improvement_suggestions JSONB DEFAULT '[]',
                    category_scores JSONB DEFAULT '{}',
                    estimated_revision_time VARCHAR(50),
                    reviewer_notes TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Reviewer Statistics table for performance tracking
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS reviewer_stats (
                    reviewer_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    reviews_completed INTEGER DEFAULT 0,
                    decisions JSONB DEFAULT '{}',
                    quality_scores JSONB DEFAULT '{}',
                    performance_metrics JSONB DEFAULT '{}',
                    recognition_level VARCHAR(50) DEFAULT 'bronze',
                    achievements JSONB DEFAULT '[]',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Anonymous Performance Log for privacy-compliant tracking
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS anonymous_performance_log (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    reviewer_hash VARCHAR(32) NOT NULL,  -- Non-reversible hash
                    review_duration FLOAT NOT NULL,
                    decision VARCHAR(50) NOT NULL,
                    quality_indicators JSONB DEFAULT '{}',
                    course_complexity FLOAT DEFAULT 1.0,
                    completion_date TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Batch Operations log for audit trail
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS batch_operations (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    operation_id UUID UNIQUE NOT NULL,
                    volunteer_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    operation_type VARCHAR(50) NOT NULL,
                    total_courses INTEGER NOT NULL,
                    successful_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    processing_time_seconds FLOAT DEFAULT 0,
                    operation_params JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Custom Review Templates for experienced reviewers
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS custom_review_templates (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    volunteer_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    template_name VARCHAR(255) NOT NULL,
                    template_config JSONB NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Review Queue with enhanced metadata
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS review_queue (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
                    contributor_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    status VARCHAR(50) DEFAULT 'pending_review',
                    priority INTEGER DEFAULT 1,
                    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    estimated_completion TIMESTAMP WITH TIME ZONE,
                    escalation_count INTEGER DEFAULT 0,
                    queue_metadata JSONB DEFAULT '{}',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Anonymous Feedback for contributor notifications
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS anonymous_feedback (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
                    reviewer_anonymous_id VARCHAR(64) NOT NULL,  -- Anonymous reviewer hash
                    feedback_content TEXT NOT NULL,
                    feedback_type VARCHAR(50) DEFAULT 'review',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Review Audit Log for compliance
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS review_audit_log (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    review_id UUID NOT NULL,
                    reviewer_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    decision VARCHAR(50) NOT NULL,
                    quality_rating VARCHAR(50),
                    feedback_length INTEGER DEFAULT 0,
                    suggestions_count INTEGER DEFAULT 0,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Volunteer Preferences for assignment optimization
            await supabase_client.execute_command("""
                CREATE TABLE IF NOT EXISTS volunteer_preferences (
                    volunteer_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    preferred_categories JSONB DEFAULT '[]',
                    max_concurrent_reviews INTEGER DEFAULT 10,
                    preferred_complexity_range JSONB DEFAULT '{"min": 0.5, "max": 2.0}',
                    notification_preferences JSONB DEFAULT '{}',
                    availability_schedule JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            logger.info("Volunteer system tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create volunteer system tables: {e}")
            raise
    
    @staticmethod
    async def create_volunteer_system_indexes():
        """Create performance indexes for volunteer system"""
        try:
            # Review feedback indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_feedback_review_id ON review_feedback(review_id);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_feedback_course_id ON review_feedback(course_id);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_feedback_reviewer_id ON review_feedback(reviewer_id);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_feedback_decision ON review_feedback(decision);"
            )
            
            # Anonymous performance log indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_anon_performance_reviewer_hash ON anonymous_performance_log(reviewer_hash);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_anon_performance_completion_date ON anonymous_performance_log(completion_date);"
            )
            
            # Batch operations indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_batch_operations_volunteer ON batch_operations(volunteer_id);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_batch_operations_type ON batch_operations(operation_type);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_batch_operations_created ON batch_operations(created_at);"
            )
            
            # Review queue indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_queue_status ON review_queue(status);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_queue_priority ON review_queue(priority DESC);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_review_queue_submitted ON review_queue(submitted_at);"
            )
            
            # Custom templates indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_custom_templates_volunteer ON custom_review_templates(volunteer_id);"
            )
            
            # Anonymous feedback indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_anonymous_feedback_course ON anonymous_feedback(course_id);"
            )
            
            # Enhanced reviews table indexes
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_reviews_priority_level ON reviews(priority_level);"
            )
            await supabase_client.execute_command(
                "CREATE INDEX IF NOT EXISTS idx_reviews_status_priority ON reviews(status, priority_level DESC);"
            )
            
            logger.info("Volunteer system indexes created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create volunteer system indexes: {e}")
            raise
    
    @staticmethod
    async def update_existing_tables():
        """Update existing tables with new columns for volunteer system"""
        try:
            # Add priority_level to reviews table if not exists
            await supabase_client.execute_command("""
                ALTER TABLE reviews 
                ADD COLUMN IF NOT EXISTS priority_level INTEGER DEFAULT 1;
            """)
            
            # Add assignment_metadata to reviews table
            await supabase_client.execute_command("""
                ALTER TABLE reviews 
                ADD COLUMN IF NOT EXISTS assignment_metadata JSONB DEFAULT '{}';
            """)
            
            # Add feedback_id to reviews table for linking
            await supabase_client.execute_command("""
                ALTER TABLE reviews 
                ADD COLUMN IF NOT EXISTS feedback_id UUID REFERENCES review_feedback(id) ON DELETE SET NULL;
            """)
            
            # Add preferred_categories to users table for volunteers
            await supabase_client.execute_command("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS preferred_categories JSONB DEFAULT '[]';
            """)
            
            # Add performance_metrics to users table
            await supabase_client.execute_command("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS performance_metrics JSONB DEFAULT '{}';
            """)
            
            # Add complexity metadata to courses
            await supabase_client.execute_command("""
                ALTER TABLE courses 
                ADD COLUMN IF NOT EXISTS difficulty_level VARCHAR(50) DEFAULT 'intermediate';
            """)
            await supabase_client.execute_command("""
                ALTER TABLE courses 
                ADD COLUMN IF NOT EXISTS estimated_duration VARCHAR(50);
            """)
            await supabase_client.execute_command("""
                ALTER TABLE courses 
                ADD COLUMN IF NOT EXISTS published_at TIMESTAMP WITH TIME ZONE;
            """)
            await supabase_client.execute_command("""
                ALTER TABLE courses 
                ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE;
            """)
            await supabase_client.execute_command("""
                ALTER TABLE courses 
                ADD COLUMN IF NOT EXISTS appeal_deadline TIMESTAMP WITH TIME ZONE;
            """)
            
            logger.info("Existing tables updated successfully")
            
        except Exception as e:
            logger.error(f"Failed to update existing tables: {e}")
            raise
    
    @staticmethod
    async def insert_default_volunteer_data():
        """Insert default data for volunteer system"""
        try:
            # Insert default volunteer preferences for existing volunteers
            volunteer_default_prefs = """
                INSERT INTO volunteer_preferences (volunteer_id, preferred_categories, max_concurrent_reviews)
                SELECT u.id, '["general", "tactics", "openings"]'::jsonb, 5
                FROM users u 
                WHERE u.role = 'volunteer_reviewer' 
                  AND NOT EXISTS (
                      SELECT 1 FROM volunteer_preferences vp WHERE vp.volunteer_id = u.id
                  );
            """
            await supabase_client.execute_command(volunteer_default_prefs)
            
            # Insert default reviewer stats for existing volunteers
            reviewer_default_stats = """
                INSERT INTO reviewer_stats (reviewer_id, reviews_completed, recognition_level)
                SELECT u.id, 0, 'bronze'
                FROM users u 
                WHERE u.role = 'volunteer_reviewer'
                  AND NOT EXISTS (
                      SELECT 1 FROM reviewer_stats rs WHERE rs.reviewer_id = u.id
                  );
            """
            await supabase_client.execute_command(reviewer_default_stats)
            
            logger.info("Default volunteer data inserted successfully")
            
        except Exception as e:
            logger.error(f"Failed to insert default volunteer data: {e}")
            raise
    
    @staticmethod
    async def setup_volunteer_triggers():
        """Set up database triggers for volunteer system automation"""
        try:
            # Trigger to update reviewer stats when review is completed
            await supabase_client.execute_command("""
                CREATE OR REPLACE FUNCTION update_reviewer_stats()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.status IN ('approved', 'rejected', 'needs_revision') 
                       AND OLD.status = 'pending' THEN
                        UPDATE reviewer_stats 
                        SET reviews_completed = reviews_completed + 1,
                            updated_at = NOW()
                        WHERE reviewer_id = NEW.reviewer_id;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            await supabase_client.execute_command("""
                DROP TRIGGER IF EXISTS trigger_update_reviewer_stats ON reviews;
                CREATE TRIGGER trigger_update_reviewer_stats
                    AFTER UPDATE ON reviews
                    FOR EACH ROW
                    EXECUTE FUNCTION update_reviewer_stats();
            """)
            
            # Trigger to update template usage count
            await supabase_client.execute_command("""
                CREATE OR REPLACE FUNCTION increment_template_usage()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.operation_type LIKE '%template%' AND NEW.operation_params ? 'template_id' THEN
                        UPDATE custom_review_templates 
                        SET usage_count = usage_count + 1
                        WHERE id = (NEW.operation_params->>'template_id')::uuid;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            await supabase_client.execute_command("""
                DROP TRIGGER IF EXISTS trigger_increment_template_usage ON batch_operations;
                CREATE TRIGGER trigger_increment_template_usage
                    AFTER INSERT ON batch_operations
                    FOR EACH ROW
                    EXECUTE FUNCTION increment_template_usage();
            """)
            
            logger.info("Volunteer system triggers created successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup volunteer triggers: {e}")
            raise

# Function to execute all schema updates
async def setup_volunteer_system_schema():
    """Execute complete schema setup for volunteer system"""
    try:
        schema = VolunteerSystemSchema()
        
        logger.info("Setting up volunteer system database schema...")
        
        # Create new tables
        await schema.create_volunteer_system_tables()
        
        # Create indexes for performance
        await schema.create_volunteer_system_indexes()
        
        # Update existing tables
        await schema.update_existing_tables()
        
        # Insert default data
        await schema.insert_default_volunteer_data()
        
        # Setup automation triggers
        await schema.setup_volunteer_triggers()
        
        logger.info("✅ Volunteer system schema setup completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Volunteer system schema setup failed: {e}")
        return False

if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_volunteer_system_schema())