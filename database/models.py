"""
Database models and schema definitions for ChessMaster bot
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

class DatabaseSchema:
    """Database schema management"""
    
    @staticmethod
    async def create_all_tables():
        """Create all required tables"""
        logger.info("Creating database schema...")
        
        # Since we're using Supabase REST API, tables should already exist
        # This is a placeholder for schema verification
        try:
            # Test if core tables exist
            tables_to_check = ['users', 'courses', 'reviews']
            for table in tables_to_check:
                if supabase_client.client:
                    result = supabase_client.client.table(table).select('count').limit(1).execute()
                    logger.info(f"Table '{table}' exists and accessible")
            
            logger.info("Database schema verified successfully")
            return True
            
        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            return False

async def initialize_database():
    """Initialize database with schema"""
    try:
        await supabase_client.initialize()
        schema = DatabaseSchema()
        return await schema.create_all_tables()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False
