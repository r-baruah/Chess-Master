#!/usr/bin/env python3
"""
Check and create necessary database schema for ChessMaster bot
"""
import os
import asyncio
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_and_create_schema():
    """Check existing schema and create missing tables"""
    print("Database Schema Setup")
    print("=" * 40)
    
    # Load environment
    load_dotenv()
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    if not supabase_url or not supabase_key:
        print("[ERROR] Missing Supabase credentials!")
        return False
    
    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        print("[OK] Supabase client connected")
        
        # Check existing tables
        print("\n1. Checking existing tables...")
        
        # List of tables we need
        required_tables = ['users', 'courses', 'files', 'channels', 'reviews', 'roles']
        existing_tables = []
        
        for table in required_tables:
            try:
                result = client.table(table).select('*').limit(1).execute()
                existing_tables.append(table)
                print(f"[OK] Table '{table}' exists")
            except Exception as e:
                if 'could not find' in str(e).lower() or '404' in str(e):
                    print(f"[MISSING] Table '{table}' not found")
                else:
                    print(f"[ERROR] Error checking table '{table}': {e}")
        
        print(f"\nExisting tables: {existing_tables}")
        missing_tables = [t for t in required_tables if t not in existing_tables]
        print(f"Missing tables: {missing_tables}")
        
        # Create schema using SQL
        if missing_tables:
            print(f"\n2. Creating missing tables...")
            
            # Basic schema SQL
            schema_sql = """
            -- Users table for anonymous identity management
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                anonymous_id VARCHAR(64) UNIQUE NOT NULL,
                telegram_id BIGINT UNIQUE NOT NULL,
                role VARCHAR(50) DEFAULT 'contributor',
                permissions JSONB DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Courses table for educational content
            CREATE TABLE IF NOT EXISTS courses (
                id SERIAL PRIMARY KEY,
                anonymous_id VARCHAR(64) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(100),
                tags TEXT[],
                status VARCHAR(50) DEFAULT 'pending',
                review_status VARCHAR(50) DEFAULT 'pending',
                reviewer_id VARCHAR(64),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                FOREIGN KEY (anonymous_id) REFERENCES users(anonymous_id)
            );

            -- Files table for course content
            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                course_id INTEGER NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_type VARCHAR(50),
                file_size BIGINT,
                telegram_file_id VARCHAR(255),
                message_link TEXT,
                channel_id BIGINT,
                backup_links JSONB DEFAULT '[]',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            );

            -- Channels table for multi-channel management
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel_id BIGINT UNIQUE NOT NULL,
                channel_name VARCHAR(255),
                channel_type VARCHAR(50) DEFAULT 'primary',
                is_active BOOLEAN DEFAULT true,
                health_status VARCHAR(50) DEFAULT 'healthy',
                last_check TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );

            -- Reviews table for volunteer workflow
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                course_id INTEGER NOT NULL,
                reviewer_id VARCHAR(64) NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                feedback TEXT,
                review_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                FOREIGN KEY (reviewer_id) REFERENCES users(anonymous_id)
            );

            -- Create indexes for performance
            CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
            CREATE INDEX IF NOT EXISTS idx_users_anonymous_id ON users(anonymous_id);
            CREATE INDEX IF NOT EXISTS idx_courses_anonymous_id ON courses(anonymous_id);
            CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status);
            CREATE INDEX IF NOT EXISTS idx_files_course_id ON files(course_id);
            CREATE INDEX IF NOT EXISTS idx_reviews_course_id ON reviews(course_id);
            """
            
            # Try to execute schema using RPC
            try:
                # Split into individual statements for execution
                statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
                
                for i, statement in enumerate(statements):
                    if statement:
                        try:
                            # Use a custom RPC function or PostgREST
                            print(f"[INFO] Executing schema statement {i+1}/{len(statements)}")
                            
                            # For now, we'll output the SQL that needs to be run manually
                            print(f"[SQL] {statement[:100]}...")
                            
                        except Exception as e:
                            print(f"[ERROR] Failed to execute statement {i+1}: {e}")
                
                print("\n[INFO] Schema SQL generated. Please run this manually in your Supabase SQL editor:")
                print("=" * 60)
                print(schema_sql)
                print("=" * 60)
                
            except Exception as e:
                print(f"[ERROR] Schema creation failed: {e}")
                return False
        else:
            print("\n[OK] All required tables exist!")
        
        # Test basic operations
        print("\n3. Testing basic operations...")
        
        try:
            # Test users table
            user_count = client.table('users').select('id').execute()
            print(f"[OK] Users table: {len(user_count.data)} records")
            
            # Test courses table
            course_count = client.table('courses').select('id').execute()
            print(f"[OK] Courses table: {len(course_count.data)} records")
            
        except Exception as e:
            print(f"[ERROR] Basic operations test failed: {e}")
            return False
        
        print("\n" + "=" * 40)
        print("SCHEMA CHECK COMPLETE")
        print("=" * 40)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Schema check failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(check_and_create_schema())
    exit(0 if result else 1)
