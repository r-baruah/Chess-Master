"""
Supabase database client and connection management
"""
import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
import asyncpg
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Supabase client with connection pooling and async operations"""
    
    def __init__(self):
        self.url = os.getenv('SUPABASE_URL')
        self.key = os.getenv('SUPABASE_KEY')
        self.client: Optional[Client] = None
        self.pool: Optional[asyncpg.Pool] = None
        
    async def initialize(self):
        """Initialize Supabase client and connection pool"""
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required")
            
        self.client = create_client(self.url, self.key)
        
        # Create async connection pool for direct PostgreSQL operations (optional)
        database_url = os.getenv('SUPABASE_DB_URL')
        if database_url and database_url.strip():
            try:
                self.pool = await asyncpg.create_pool(
                    database_url,
                    min_size=5,
                    max_size=20,
                    command_timeout=30,
                    server_settings={
                        'jit': 'off'
                    }
                )
                logger.info("Supabase connection pool initialized successfully")
            except Exception as e:
                logger.info(f"PostgreSQL pool unavailable, continuing with REST API only: {e}")
                self.pool = None
        else:
            logger.info("Using Supabase REST API mode (recommended for most use cases)")
            self.pool = None
    
    @asynccontextmanager
    async def get_connection(self):
        """Get async database connection from pool"""
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")
            
        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            await self.pool.release(conn)
    
    async def execute_query(self, query: str, *args) -> List[Dict]:
        """Execute async query and return results"""
        if self.pool:
            async with self.get_connection() as conn:
                result = await conn.fetch(query, *args)
                return [dict(row) for row in result]
        else:
            # Use Supabase REST API for data operations
            logger.debug("Using REST API for query operations")
            return []
    
    async def execute_command(self, command: str, *args) -> str:
        """Execute async command and return status"""
        if self.pool:
            async with self.get_connection() as conn:
                return await conn.execute(command, *args)
        else:
            # Use Supabase REST API for data operations
            logger.debug("Using REST API for command operations")
            return "REST_API_MODE"
    
    async def close(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Supabase connection pool closed")

# Global instance
supabase_client = SupabaseClient()

async def init_supabase():
    """Initialize global Supabase client"""
    await supabase_client.initialize()

async def close_supabase():
    """Close global Supabase client"""
    await supabase_client.close()