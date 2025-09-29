"""
Redis state management system replacing in-memory temp storage
"""
import os
import json
import logging
import redis.asyncio as redis
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RedisStateManager:
    """Redis-based state management for persistent sessions"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.fallback_storage: Dict[str, Any] = {}  # In-memory fallback
        self.use_fallback = False
        self.config = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'db': int(os.getenv('REDIS_DB', 0)),
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True,
            'health_check_interval': 30
        }
    
    async def initialize(self):
        """Initialize Redis connection with fallback"""
        try:
            self.redis_client = redis.Redis(**self.config)
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection initialized successfully")
            self.use_fallback = False
            
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory fallback: {e}")
            self.use_fallback = True
            self.fallback_storage = {}
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")
    
    # User session management
    async def set_user_session(self, telegram_id: int, session_data: Dict, ttl: int = 3600):
        """Set user session data with TTL"""
        try:
            key = f"user_session:{telegram_id}"
            if self.use_fallback:
                self.fallback_storage[key] = session_data
                logger.debug(f"User session set for {telegram_id} (fallback)")
                return
                
            await self.redis_client.setex(
                key, 
                ttl, 
                json.dumps(session_data, default=str)
            )
            logger.debug(f"User session set for {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to set user session: {e}")
    
    async def get_user_session(self, telegram_id: int) -> Optional[Dict]:
        """Get user session data"""
        try:
            if self.use_fallback:
                key = f"user_session:{telegram_id}"
                return self.fallback_storage.get(key)
            
            key = f"user_session:{telegram_id}"
            data = await self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get user session: {e}")
            return None
    
    async def delete_user_session(self, telegram_id: int):
        """Delete user session"""
        try:
            key = f"user_session:{telegram_id}"
            if self.use_fallback:
                self.fallback_storage.pop(key, None)
                logger.debug(f"User session deleted for {telegram_id} (fallback)")
                return
                
            await self.redis_client.delete(key)
            logger.debug(f"User session deleted for {telegram_id}")
        except Exception as e:
            logger.error(f"Failed to delete user session: {e}")
    
    # Bot state management
    async def set_bot_state(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set bot state value"""
        try:
            full_key = f"bot_state:{key}"
            serialized_value = json.dumps(value, default=str)
            
            if ttl:
                await self.redis_client.setex(full_key, ttl, serialized_value)
            else:
                await self.redis_client.set(full_key, serialized_value)
            
            logger.debug(f"Bot state set: {key}")
        except Exception as e:
            logger.error(f"Failed to set bot state: {e}")
    
    async def get_bot_state(self, key: str, default: Any = None) -> Any:
        """Get bot state value"""
        try:
            full_key = f"bot_state:{key}"
            if self.use_fallback:
                return self.fallback_storage.get(full_key, default)
                
            data = await self.redis_client.get(full_key)
            return json.loads(data) if data else default
        except Exception as e:
            logger.error(f"Failed to get bot state: {e}")
            return default
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Generic get method for compatibility"""
        return await self.get_bot_state(key, default)
    
    async def delete_bot_state(self, key: str):
        """Delete bot state value"""
        try:
            full_key = f"bot_state:{key}"
            await self.redis_client.delete(full_key)
        except Exception as e:
            logger.error(f"Failed to delete bot state: {e}")
    
    # Cache management
    async def cache_set(self, key: str, value: Any, ttl: int = 300):
        """Set cache value with TTL (default 5 minutes)"""
        try:
            full_key = f"cache:{key}"
            await self.redis_client.setex(
                full_key, 
                ttl, 
                json.dumps(value, default=str)
            )
            logger.debug(f"Cache set: {key}")
        except Exception as e:
            logger.error(f"Failed to set cache: {e}")
    
    async def cache_get(self, key: str) -> Any:
        """Get cached value"""
        try:
            full_key = f"cache:{key}"
            data = await self.redis_client.get(full_key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get cache: {e}")
            return None
    
    async def cache_delete(self, key: str):
        """Delete cached value"""
        try:
            full_key = f"cache:{key}"
            await self.redis_client.delete(full_key)
        except Exception as e:
            logger.error(f"Failed to delete cache: {e}")
    
    # List operations for queues
    async def queue_push(self, queue_name: str, item: Any):
        """Push item to queue (list)"""
        try:
            key = f"queue:{queue_name}"
            await self.redis_client.lpush(key, json.dumps(item, default=str))
            logger.debug(f"Item pushed to queue: {queue_name}")
        except Exception as e:
            logger.error(f"Failed to push to queue: {e}")
    
    async def queue_pop(self, queue_name: str) -> Optional[Any]:
        """Pop item from queue"""
        try:
            key = f"queue:{queue_name}"
            data = await self.redis_client.rpop(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to pop from queue: {e}")
            return None
    
    async def queue_length(self, queue_name: str) -> int:
        """Get queue length"""
        try:
            key = f"queue:{queue_name}"
            return await self.redis_client.llen(key)
        except Exception as e:
            logger.error(f"Failed to get queue length: {e}")
            return 0
    
    # Set operations for collections
    async def set_add(self, set_name: str, member: str):
        """Add member to set"""
        try:
            key = f"set:{set_name}"
            await self.redis_client.sadd(key, member)
        except Exception as e:
            logger.error(f"Failed to add to set: {e}")
    
    async def set_remove(self, set_name: str, member: str):
        """Remove member from set"""
        try:
            key = f"set:{set_name}"
            await self.redis_client.srem(key, member)
        except Exception as e:
            logger.error(f"Failed to remove from set: {e}")
    
    async def set_members(self, set_name: str) -> List[str]:
        """Get all set members"""
        try:
            key = f"set:{set_name}"
            return list(await self.redis_client.smembers(key))
        except Exception as e:
            logger.error(f"Failed to get set members: {e}")
            return []
    
    async def set_contains(self, set_name: str, member: str) -> bool:
        """Check if set contains member"""
        try:
            key = f"set:{set_name}"
            return await self.redis_client.sismember(key, member)
        except Exception as e:
            logger.error(f"Failed to check set membership: {e}")
            return False
    
    # Statistics and counters
    async def increment_counter(self, counter_name: str, amount: int = 1) -> int:
        """Increment counter"""
        try:
            key = f"counter:{counter_name}"
            return await self.redis_client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment counter: {e}")
            return 0
    
    async def get_counter(self, counter_name: str) -> int:
        """Get counter value"""
        try:
            key = f"counter:{counter_name}"
            value = await self.redis_client.get(key)
            return int(value) if value else 0
        except Exception as e:
            logger.error(f"Failed to get counter: {e}")
            return 0
    
    async def reset_counter(self, counter_name: str):
        """Reset counter to 0"""
        try:
            key = f"counter:{counter_name}"
            await self.redis_client.set(key, 0)
        except Exception as e:
            logger.error(f"Failed to reset counter: {e}")
    
    # Health and maintenance
    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check"""
        try:
            start_time = datetime.now()
            
            # Test basic operations
            await self.redis_client.ping()
            
            # Test set/get
            test_key = "health_check_test"
            await self.redis_client.setex(test_key, 10, "test_value")
            test_value = await self.redis_client.get(test_key)
            await self.redis_client.delete(test_key)
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                'status': 'healthy',
                'response_time_ms': response_time,
                'test_successful': test_value == "test_value",
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def cleanup_expired_keys(self, pattern: str = "*"):
        """Cleanup expired keys (maintenance task)"""
        try:
            # Get Redis info
            info = await self.redis_client.info()
            expired_keys = info.get('expired_keys', 0)
            
            logger.info(f"Redis cleanup: {expired_keys} keys expired")
            return expired_keys
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired keys: {e}")
            return 0

# Global instance
redis_state = RedisStateManager()

# Compatibility layer for existing temp.py usage
class TempCompatibility:
    """Compatibility layer for existing temp.py usage"""
    
    def __init__(self):
        self.BOT = None
        self.ME = None
        self.U_NAME = None
        self.B_NAME = None
        self._banned_users = set()
        self._banned_chats = set()
        self._premium_users = set()
    
    @property
    async def BANNED_USERS(self):
        """Get banned users from Redis"""
        return await redis_state.set_members("banned_users")
    
    @BANNED_USERS.setter
    async def BANNED_USERS(self, users: List[int]):
        """Set banned users in Redis"""
        # Clear existing set
        key = "set:banned_users"
        await redis_state.redis_client.delete(key)
        
        # Add new users
        for user in users:
            await redis_state.set_add("banned_users", str(user))
    
    @property
    async def BANNED_CHATS(self):
        """Get banned chats from Redis"""
        return await redis_state.set_members("banned_chats")
    
    @BANNED_CHATS.setter
    async def BANNED_CHATS(self, chats: List[int]):
        """Set banned chats in Redis"""
        key = "set:banned_chats"
        await redis_state.redis_client.delete(key)
        
        for chat in chats:
            await redis_state.set_add("banned_chats", str(chat))
    
    @property
    async def PREMIUM_USERS(self):
        """Get premium users from Redis"""
        return await redis_state.set_members("premium_users")
    
    @PREMIUM_USERS.setter
    async def PREMIUM_USERS(self, users: List[int]):
        """Set premium users in Redis"""
        key = "set:premium_users"
        await redis_state.redis_client.delete(key)
        
        for user in users:
            await redis_state.set_add("premium_users", str(user))

# Global compatibility instance
temp = TempCompatibility()