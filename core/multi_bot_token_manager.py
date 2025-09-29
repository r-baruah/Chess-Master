"""
Multi-Bot Token Manager for disaster recovery and high availability
Handles multiple bot tokens with automatic failover capabilities
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pyrogram import Client
import redis.asyncio as redis
from core.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

@dataclass
class BotTokenInfo:
    """Bot token information structure"""
    token: str
    api_id: int
    api_hash: str
    bot_id: Optional[int] = None
    username: Optional[str] = None
    status: str = 'unknown'  # healthy, degraded, failed, unknown
    last_check: Optional[str] = None
    performance_metrics: Optional[Dict] = None
    error_count: int = 0
    last_error: Optional[str] = None

class MultiBotTokenManager:
    """Manages multiple bot tokens with automatic failover"""
    
    def __init__(self, redis_client: redis.Redis, supabase_client: SupabaseClient):
        self.redis = redis_client
        self.supabase = supabase_client
        self.active_token: Optional[BotTokenInfo] = None
        self.backup_tokens: List[BotTokenInfo] = []
        self.health_check_interval = 30  # seconds
        self.max_error_count = 5
        self.health_check_task: Optional[asyncio.Task] = None
        
    async def initialize_tokens(self) -> bool:
        """Initialize and validate all bot tokens"""
        try:
            tokens = await self._load_bot_tokens()
            
            if not tokens:
                logger.error("No bot tokens configured")
                return False
                
            validated_tokens = []
            
            for token_config in tokens:
                token_info = await self._validate_token(token_config)
                if token_info:
                    validated_tokens.append(token_info)
                    
            if not validated_tokens:
                logger.error("No valid bot tokens found")
                return False
                
            # Set first valid token as active
            self.active_token = validated_tokens[0]
            self.backup_tokens = validated_tokens[1:] if len(validated_tokens) > 1 else []
            
            await self._save_token_status()
            logger.info(f"Initialized {len(validated_tokens)} bot tokens")
            
            # Start health monitoring
            self.health_check_task = asyncio.create_task(self._health_monitoring_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize tokens: {e}")
            return False
            
    async def _load_bot_tokens(self) -> List[Dict]:
        """Load bot token configurations from environment and database"""
        tokens = []
        
        # Primary token from environment
        primary_token = {
            'token': os.getenv('BOT_TOKEN'),
            'api_id': int(os.getenv('API_ID', 0)),
            'api_hash': os.getenv('API_HASH', '')
        }
        
        if primary_token['token'] and primary_token['api_id'] and primary_token['api_hash']:
            tokens.append(primary_token)
            
        # Additional tokens from database
        try:
            async with self.supabase.get_connection() as conn:
                backup_tokens = await conn.fetch("""
                    SELECT token, api_id, api_hash 
                    FROM bot_tokens 
                    WHERE status = 'active' 
                    ORDER BY priority DESC
                """)
                
                for row in backup_tokens:
                    tokens.append({
                        'token': row['token'],
                        'api_id': row['api_id'],
                        'api_hash': row['api_hash']
                    })
                    
        except Exception as e:
            logger.warning(f"Could not load backup tokens from database: {e}")
            
        return tokens
        
    async def _validate_token(self, token_config: Dict) -> Optional[BotTokenInfo]:
        """Validate a bot token and return token info"""
        try:
            token_info = BotTokenInfo(
                token=token_config['token'],
                api_id=token_config['api_id'],
                api_hash=token_config['api_hash']
            )
            
            # Test token with temporary client
            session_name = f"temp_validation_{datetime.utcnow().timestamp()}"
            client = Client(
                session_name,
                api_id=token_info.api_id,
                api_hash=token_info.api_hash,
                bot_token=token_info.token,
                in_memory=True
            )
            
            await client.start()
            me = await client.get_me()
            await client.stop()
            
            token_info.bot_id = me.id
            token_info.username = me.username
            token_info.status = 'healthy'
            token_info.last_check = datetime.utcnow().isoformat()
            
            logger.info(f"Validated bot token for @{me.username}")
            return token_info
            
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None
            
    async def perform_health_check(self, token_info: BotTokenInfo) -> bool:
        """Perform comprehensive health check on a bot token"""
        try:
            session_name = f"health_check_{token_info.bot_id}_{datetime.utcnow().timestamp()}"
            client = Client(
                session_name,
                api_id=token_info.api_id,
                api_hash=token_info.api_hash,
                bot_token=token_info.token,
                in_memory=True
            )
            
            start_time = datetime.utcnow()
            await client.start()
            
            # Basic functionality test
            me = await client.get_me()
            
            # Test channel access if configured
            test_results = await self._test_channel_access(client)
            
            await client.stop()
            
            # Calculate performance metrics
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            token_info.status = 'healthy' if test_results['success'] else 'degraded'
            token_info.last_check = datetime.utcnow().isoformat()
            token_info.performance_metrics = {
                'response_time': response_time,
                'channel_access': test_results
            }
            token_info.error_count = 0
            token_info.last_error = None
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed for bot {token_info.username}: {e}")
            
            token_info.status = 'failed'
            token_info.error_count += 1
            token_info.last_error = str(e)
            token_info.last_check = datetime.utcnow().isoformat()
            
            return False
            
    async def _test_channel_access(self, client: Client) -> Dict:
        """Test access to configured channels"""
        test_results = {
            'success': True,
            'tested_channels': 0,
            'successful_channels': 0,
            'errors': []
        }
        
        try:
            # Get configured channels from environment
            course_channels = os.getenv('COURSE_CHANNEL', '').split()
            
            for channel in course_channels[:3]:  # Test first 3 channels only
                if not channel:
                    continue
                    
                try:
                    test_results['tested_channels'] += 1
                    chat = await client.get_chat(channel)
                    test_results['successful_channels'] += 1
                    
                except Exception as e:
                    test_results['errors'].append(f"Channel {channel}: {str(e)}")
                    test_results['success'] = False
                    
        except Exception as e:
            test_results['errors'].append(f"Channel access test failed: {str(e)}")
            test_results['success'] = False
            
        return test_results
        
    async def failover_to_backup_token(self) -> bool:
        """Perform failover to backup bot token"""
        if not self.backup_tokens:
            logger.critical("No backup tokens available for failover!")
            await self._notify_critical_failure("No backup tokens available")
            return False
            
        logger.warning(f"Initiating failover from bot @{self.active_token.username}")
        
        # Mark current token as failed
        self.active_token.status = 'failed'
        
        # Try backup tokens in order
        for backup_token in self.backup_tokens[:]:
            logger.info(f"Attempting failover to bot @{backup_token.username}")
            
            if await self.perform_health_check(backup_token):
                # Promote backup to active
                failed_token = self.active_token
                self.active_token = backup_token
                self.backup_tokens.remove(backup_token)
                self.backup_tokens.append(failed_token)
                
                logger.info(f"Failover successful to bot @{backup_token.username}")
                
                # Update configuration and notify
                await self._save_token_status()
                await self._update_active_configuration()
                await self._notify_failover_success(backup_token.username)
                
                return True
                
        logger.critical("All backup tokens failed! Manual intervention required.")
        await self._notify_critical_failure("All backup tokens failed")
        return False
        
    async def _health_monitoring_loop(self):
        """Continuous health monitoring loop"""
        while True:
            try:
                if self.active_token:
                    healthy = await self.perform_health_check(self.active_token)
                    
                    if not healthy and self.active_token.error_count >= self.max_error_count:
                        logger.warning("Active token failed health check, initiating failover")
                        await self.failover_to_backup_token()
                        
                    # Also check backup tokens periodically
                    for backup_token in self.backup_tokens:
                        if backup_token.status == 'failed':
                            # Try to restore failed tokens
                            await self.perform_health_check(backup_token)
                            
                await self._save_token_status()
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.health_check_interval)
                
    async def _save_token_status(self):
        """Save current token status to Redis and database"""
        try:
            # Save to Redis for quick access
            status_data = {
                'active_token': asdict(self.active_token) if self.active_token else None,
                'backup_tokens': [asdict(token) for token in self.backup_tokens],
                'last_update': datetime.utcnow().isoformat()
            }
            
            await self.redis.setex(
                'bot_tokens_status',
                3600,  # 1 hour TTL
                json.dumps(status_data, default=str)
            )
            
            # Also save to database for persistence
            async with self.supabase.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO system_status (component, status_data, updated_at)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (component) 
                    DO UPDATE SET status_data = $2, updated_at = $3
                """, 'bot_tokens', json.dumps(status_data, default=str), datetime.utcnow())
                
        except Exception as e:
            logger.error(f"Failed to save token status: {e}")
            
    async def _update_active_configuration(self):
        """Update environment configuration with active token"""
        try:
            if self.active_token:
                # Update runtime environment (doesn't persist)
                os.environ['BOT_TOKEN'] = self.active_token.token
                os.environ['API_ID'] = str(self.active_token.api_id)
                os.environ['API_HASH'] = self.active_token.api_hash
                
                logger.info("Updated runtime configuration with active token")
                
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            
    async def _notify_failover_success(self, new_bot_username: str):
        """Notify administrators of successful failover"""
        try:
            notification_data = {
                'type': 'failover_success',
                'message': f"🔄 Bot failover successful to @{new_bot_username}",
                'timestamp': datetime.utcnow().isoformat(),
                'active_bot': new_bot_username
            }
            
            await self.redis.lpush('admin_notifications', json.dumps(notification_data))
            logger.info(f"Failover notification sent for @{new_bot_username}")
            
        except Exception as e:
            logger.error(f"Failed to send failover notification: {e}")
            
    async def _notify_critical_failure(self, error_message: str):
        """Notify administrators of critical system failure"""
        try:
            notification_data = {
                'type': 'critical_failure',
                'message': f"🚨 CRITICAL: Bot system failure - {error_message}",
                'timestamp': datetime.utcnow().isoformat(),
                'requires_manual_intervention': True
            }
            
            await self.redis.lpush('admin_notifications', json.dumps(notification_data))
            logger.critical(f"Critical failure notification sent: {error_message}")
            
        except Exception as e:
            logger.error(f"Failed to send critical failure notification: {e}")
            
    async def get_current_status(self) -> Dict:
        """Get current token manager status"""
        return {
            'active_token': {
                'username': self.active_token.username if self.active_token else None,
                'status': self.active_token.status if self.active_token else None,
                'last_check': self.active_token.last_check if self.active_token else None,
                'error_count': self.active_token.error_count if self.active_token else 0
            },
            'backup_tokens_count': len(self.backup_tokens),
            'backup_tokens_healthy': len([t for t in self.backup_tokens if t.status == 'healthy']),
            'monitoring_active': self.health_check_task is not None and not self.health_check_task.done()
        }
        
    async def shutdown(self):
        """Shutdown token manager and cleanup"""
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass
                
        logger.info("Multi-bot token manager shutdown complete")