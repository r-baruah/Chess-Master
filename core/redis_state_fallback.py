"""
Redis state management system with in-memory fallback for testing
"""
import os
import json
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RedisStateManagerWithFallback:
    """Redis-based state management with in-memory fallback"""
    
    def __init__(self):
        self.redis_client: Optional[Any] = None
        self.fallback_storage: Dict[str, Any] = {}
        self.use_fallback = True  # Default to fallback for testing
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
            import redis.asyncio as redis
            self.redis_client = redis.Redis(**self.config)
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection initialized successfully")
            self.use_fallback = False
            
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory fallback: {e}")
            self.use_fallback = True
            self.fallback_storage = {}
    
    def _is_expired(self, item):
        """Check if fallback item is expired"""
        if 'expires_at' in item:
            return datetime.now() > item['expires_at']
        return False
    
    def _cleanup_expired(self):
        """Clean up expired items from fallback storage"""
        expired_keys = [
            key for key, value in self.fallback_storage.items() 
            if isinstance(value, dict) and self._is_expired(value)
        ]
        for key in expired_keys:
            del self.fallback_storage[key]
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client and not self.use_fallback:
            await self.redis_client.close()
            logger.info("Redis connection closed")
    
    # User session management
    async def set_user_session(self, telegram_id: int, session_data: Dict, ttl: int = 3600):
        """Set user session data with TTL"""
        try:
            key = f"user_session:{telegram_id}"
            if self.use_fallback:
                self.fallback_storage[key] = {
                    'data': session_data,
                    'expires_at': datetime.now() + timedelta(seconds=ttl)
                }
                logger.debug(f"User session set for {telegram_id} (fallback)")
            else:
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
            key = f"user_session:{telegram_id}"
            if self.use_fallback:
                self._cleanup_expired()
                item = self.fallback_storage.get(key)
                if item and not self._is_expired(item):
                    return item['data']
                return None
            else:
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
            else:
                await self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete user session: {e}")
    
    # Cache management
    async def cache_set(self, key: str, value: Any, ttl: int = 300):
        """Set cache value with TTL"""
        try:
            if self.use_fallback:
                self.fallback_storage[f"cache:{key}"] = {
                    'data': value,
                    'expires_at': datetime.now() + timedelta(seconds=ttl)
                }
            else:
                await self.redis_client.setex(
                    f"cache:{key}", 
                    ttl, 
                    json.dumps(value, default=str)
                )
        except Exception as e:
            logger.error(f"Failed to set cache: {e}")
    
    async def cache_get(self, key: str) -> Optional[Any]:
        """Get cache value"""
        try:
            cache_key = f"cache:{key}"
            if self.use_fallback:
                self._cleanup_expired()
                item = self.fallback_storage.get(cache_key)
                if item and not self._is_expired(item):
                    return item['data']
                return None
            else:
                data = await self.redis_client.get(cache_key)
                return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to get cache: {e}")
            return None
    
    async def cache_delete(self, key: str):
        """Delete cache value"""
        try:
            cache_key = f"cache:{key}"
            if self.use_fallback:
                self.fallback_storage.pop(cache_key, None)
            else:
                await self.redis_client.delete(cache_key)
        except Exception as e:
            logger.error(f"Failed to delete cache: {e}")
    
    # List operations
    async def list_push(self, key: str, value: Any):
        """Push value to list"""
        try:
            if self.use_fallback:
                if key not in self.fallback_storage:
                    self.fallback_storage[key] = []
                if isinstance(self.fallback_storage[key], list):
                    self.fallback_storage[key].append(value)
            else:
                await self.redis_client.lpush(key, json.dumps(value, default=str))
        except Exception as e:
            logger.error(f"Failed to push to list: {e}")
    
    async def list_pop(self, key: str) -> Optional[Any]:
        """Pop value from list"""
        try:
            if self.use_fallback:
                if key in self.fallback_storage and isinstance(self.fallback_storage[key], list):
                    if self.fallback_storage[key]:
                        return self.fallback_storage[key].pop()
                return None
            else:
                data = await self.redis_client.lpop(key)
                return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Failed to pop from list: {e}")
            return None
    
    async def list_length(self, key: str) -> int:
        """Get list length"""
        try:
            if self.use_fallback:
                if key in self.fallback_storage and isinstance(self.fallback_storage[key], list):
                    return len(self.fallback_storage[key])
                return 0
            else:
                return await self.redis_client.llen(key)
        except Exception as e:
            logger.error(f"Failed to get list length: {e}")
            return 0
    
    # Health check
    async def health_check(self) -> bool:
        """Check Redis health"""
        try:
            if self.use_fallback:
                return True  # Fallback is always "healthy"
            else:
                await self.redis_client.ping()
                return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

# Global instance with fallback support
redis_state = RedisStateManagerWithFallback()
