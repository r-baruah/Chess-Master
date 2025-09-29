"""
Channel Permission Manager for automated permission setup and management
Handles channel permissions across multiple bot tokens with synchronization
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pyrogram import Client
from pyrogram.errors import ChannelPrivate, ChatAdminRequired, UserNotParticipant
import redis.asyncio as redis
from core.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

@dataclass
class ChannelInfo:
    """Channel information structure"""
    channel_id: str
    channel_type: str  # log_channel, course_channel, public_channel, support_chat
    title: Optional[str] = None
    username: Optional[str] = None
    permissions_required: Optional[List[str]] = None
    last_verified: Optional[str] = None
    status: str = 'unknown'  # verified, failed, pending
    error_message: Optional[str] = None

@dataclass 
class PermissionTestResult:
    """Permission test result structure"""
    channel_id: str
    permission_type: str
    success: bool
    error_message: Optional[str] = None
    test_time: Optional[str] = None

class ChannelPermissionManager:
    """Manages channel permissions across multiple bot tokens"""
    
    def __init__(self, redis_client: redis.Redis, supabase_client: SupabaseClient):
        self.redis = redis_client
        self.supabase = supabase_client
        self.configured_channels: List[ChannelInfo] = []
        self.permission_check_interval = 300  # 5 minutes
        self.monitoring_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> bool:
        """Initialize channel permission manager"""
        try:
            # Load configured channels
            await self._load_configured_channels()
            
            # Start permission monitoring
            self.monitoring_task = asyncio.create_task(self._permission_monitoring_loop())
            
            logger.info(f"Channel permission manager initialized with {len(self.configured_channels)} channels")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize channel permission manager: {e}")
            return False
            
    async def _load_configured_channels(self):
        """Load configured channels from environment and database"""
        self.configured_channels = []
        
        # Log channel
        log_channel = os.getenv('LOG_CHANNEL')
        if log_channel:
            self.configured_channels.append(ChannelInfo(
                channel_id=log_channel,
                channel_type='log_channel',
                permissions_required=['send_messages', 'delete_messages']
            ))
            
        # Course channels
        course_channels = os.getenv('COURSE_CHANNEL', '').split()
        for channel in course_channels:
            if channel:
                self.configured_channels.append(ChannelInfo(
                    channel_id=channel,
                    channel_type='course_channel',
                    permissions_required=['send_messages', 'delete_messages', 'manage_messages']
                ))
                
        # Public channel
        public_channel = os.getenv('PUBLIC_CHANNEL')
        if public_channel:
            # Convert username to channel ID if needed
            if not public_channel.startswith('-100'):
                public_channel = f"@{public_channel}" if not public_channel.startswith('@') else public_channel
                
            self.configured_channels.append(ChannelInfo(
                channel_id=public_channel,
                channel_type='public_channel',
                permissions_required=['send_messages']
            ))
            
        # Support chat
        support_chat = os.getenv('SUPPORT_CHAT_ID')
        if support_chat:
            if not support_chat.startswith('-100'):
                support_chat = f"@{support_chat}" if not support_chat.startswith('@') else support_chat
                
            self.configured_channels.append(ChannelInfo(
                channel_id=support_chat,
                channel_type='support_chat',
                permissions_required=['send_messages', 'delete_messages']
            ))
            
        # Load additional channels from database
        try:
            async with self.supabase.get_connection() as conn:
                additional_channels = await conn.fetch("""
                    SELECT channel_id, channel_type, required_permissions
                    FROM channel_configs 
                    WHERE status = 'active'
                """)
                
                for row in additional_channels:
                    permissions = json.loads(row['required_permissions']) if row['required_permissions'] else []
                    self.configured_channels.append(ChannelInfo(
                        channel_id=row['channel_id'],
                        channel_type=row['channel_type'],
                        permissions_required=permissions
                    ))
                    
        except Exception as e:
            logger.warning(f"Could not load additional channels from database: {e}")
            
    async def setup_channel_permissions(self, bot_token: str, api_id: int, api_hash: str) -> List[PermissionTestResult]:
        """Setup and verify permissions for all channels with specified bot token"""
        logger.info(f"Setting up channel permissions for bot token")
        
        permission_results = []
        
        # Create temporary client for permission setup
        session_name = f"permission_setup_{datetime.utcnow().timestamp()}"
        client = Client(
            session_name,
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
            in_memory=True
        )
        
        try:
            await client.start()
            me = await client.get_me()
            logger.info(f"Setting up permissions for bot @{me.username}")
            
            for channel_info in self.configured_channels:
                channel_results = await self._test_channel_permissions(client, channel_info)
                permission_results.extend(channel_results)
                
                # Update channel info based on results
                all_success = all(result.success for result in channel_results)
                channel_info.status = 'verified' if all_success else 'failed'
                channel_info.last_verified = datetime.utcnow().isoformat()
                
                if not all_success:
                    failed_results = [r for r in channel_results if not r.success]
                    channel_info.error_message = f"Failed permissions: {[r.permission_type for r in failed_results]}"
                    
        finally:
            await client.stop()
            
        # Save results to database and Redis
        await self._save_permission_results(permission_results, me.username if 'me' in locals() else 'unknown')
        
        return permission_results
        
    async def _test_channel_permissions(self, client: Client, channel_info: ChannelInfo) -> List[PermissionTestResult]:
        """Test specific permissions for a channel"""
        results = []
        test_time = datetime.utcnow().isoformat()
        
        try:
            # First, try to get channel info
            try:
                chat = await client.get_chat(channel_info.channel_id)
                channel_info.title = getattr(chat, 'title', None)
                channel_info.username = getattr(chat, 'username', None)
                
                results.append(PermissionTestResult(
                    channel_id=channel_info.channel_id,
                    permission_type='access',
                    success=True,
                    test_time=test_time
                ))
                
            except Exception as e:
                results.append(PermissionTestResult(
                    channel_id=channel_info.channel_id,
                    permission_type='access',
                    success=False,
                    error_message=str(e),
                    test_time=test_time
                ))
                return results  # Can't test other permissions without access
                
            # Test specific permissions
            if 'send_messages' in channel_info.permissions_required:
                result = await self._test_send_permission(client, channel_info.channel_id, test_time)
                results.append(result)
                
            if 'delete_messages' in channel_info.permissions_required:
                result = await self._test_delete_permission(client, channel_info.channel_id, test_time)
                results.append(result)
                
            if 'manage_messages' in channel_info.permissions_required:
                result = await self._test_manage_permission(client, channel_info.channel_id, test_time)
                results.append(result)
                
        except Exception as e:
            logger.error(f"Error testing permissions for channel {channel_info.channel_id}: {e}")
            results.append(PermissionTestResult(
                channel_id=channel_info.channel_id,
                permission_type='general_error',
                success=False,
                error_message=str(e),
                test_time=test_time
            ))
            
        return results
        
    async def _test_send_permission(self, client: Client, channel_id: str, test_time: str) -> PermissionTestResult:
        """Test send message permission"""
        try:
            test_message = f"🔧 Permission verification test - {datetime.utcnow().strftime('%H:%M:%S')}"
            
            message = await client.send_message(
                channel_id,
                test_message,
                disable_notification=True
            )
            
            # Store message ID for cleanup
            await self.redis.lpush(f"test_messages:{channel_id}", message.id)
            await self.redis.expire(f"test_messages:{channel_id}", 3600)  # 1 hour TTL
            
            return PermissionTestResult(
                channel_id=channel_id,
                permission_type='send_messages',
                success=True,
                test_time=test_time
            )
            
        except Exception as e:
            return PermissionTestResult(
                channel_id=channel_id,
                permission_type='send_messages',
                success=False,
                error_message=str(e),
                test_time=test_time
            )
            
    async def _test_delete_permission(self, client: Client, channel_id: str, test_time: str) -> PermissionTestResult:
        """Test delete message permission"""
        try:
            # Get a test message ID to delete
            test_message_ids = await self.redis.lrange(f"test_messages:{channel_id}", 0, 0)
            
            if test_message_ids:
                message_id = int(test_message_ids[0])
                await client.delete_messages(channel_id, message_id)
                
                # Remove from Redis list
                await self.redis.lrem(f"test_messages:{channel_id}", 1, message_id)
                
                return PermissionTestResult(
                    channel_id=channel_id,
                    permission_type='delete_messages',
                    success=True,
                    test_time=test_time
                )
            else:
                # Send a message specifically for deletion test
                test_message = await client.send_message(
                    channel_id,
                    "🗑️ Delete permission test",
                    disable_notification=True
                )
                
                await client.delete_messages(channel_id, test_message.id)
                
                return PermissionTestResult(
                    channel_id=channel_id,
                    permission_type='delete_messages',
                    success=True,
                    test_time=test_time
                )
                
        except Exception as e:
            return PermissionTestResult(
                channel_id=channel_id,
                permission_type='delete_messages',
                success=False,
                error_message=str(e),
                test_time=test_time
            )
            
    async def _test_manage_permission(self, client: Client, channel_id: str, test_time: str) -> PermissionTestResult:
        """Test message management permissions"""
        try:
            # Test by pinning and unpinning a message
            test_message = await client.send_message(
                channel_id,
                "📌 Management permission test",
                disable_notification=True
            )
            
            # Try to pin the message
            await client.pin_chat_message(channel_id, test_message.id, disable_notification=True)
            
            # Unpin the message
            await client.unpin_chat_message(channel_id, test_message.id)
            
            # Delete the test message
            await client.delete_messages(channel_id, test_message.id)
            
            return PermissionTestResult(
                channel_id=channel_id,
                permission_type='manage_messages',
                success=True,
                test_time=test_time
            )
            
        except Exception as e:
            return PermissionTestResult(
                channel_id=channel_id,
                permission_type='manage_messages',
                success=False,
                error_message=str(e),
                test_time=test_time
            )
            
    async def synchronize_permissions(self, token_manager) -> Dict:
        """Synchronize permissions across all bot tokens"""
        logger.info("Starting permission synchronization across all bot tokens")
        
        sync_results = {
            'total_tokens': 0,
            'successful_tokens': 0,
            'failed_tokens': 0,
            'token_results': [],
            'sync_time': datetime.utcnow().isoformat()
        }
        
        # Get all available tokens from token manager
        all_tokens = []
        if hasattr(token_manager, 'active_token') and token_manager.active_token:
            all_tokens.append(token_manager.active_token)
        if hasattr(token_manager, 'backup_tokens'):
            all_tokens.extend(token_manager.backup_tokens)
            
        sync_results['total_tokens'] = len(all_tokens)
        
        for token_info in all_tokens:
            try:
                permission_results = await self.setup_channel_permissions(
                    token_info.token,
                    token_info.api_id,
                    token_info.api_hash
                )
                
                token_result = {
                    'bot_username': token_info.username,
                    'success': True,
                    'total_permissions_tested': len(permission_results),
                    'successful_permissions': len([r for r in permission_results if r.success]),
                    'failed_permissions': len([r for r in permission_results if not r.success])
                }
                
                sync_results['successful_tokens'] += 1
                
            except Exception as e:
                token_result = {
                    'bot_username': token_info.username,
                    'success': False,
                    'error': str(e)
                }
                sync_results['failed_tokens'] += 1
                
            sync_results['token_results'].append(token_result)
            
        # Save synchronization results
        await self._save_sync_results(sync_results)
        
        logger.info(f"Permission synchronization completed: {sync_results['successful_tokens']}/{sync_results['total_tokens']} tokens successful")
        
        return sync_results
        
    async def verify_channel_access(self, channel_id: str, bot_token: str, api_id: int, api_hash: str) -> Dict:
        """Verify access to a specific channel"""
        verification_result = {
            'channel_id': channel_id,
            'accessible': False,
            'permissions': {},
            'channel_info': {},
            'test_time': datetime.utcnow().isoformat(),
            'error': None
        }
        
        session_name = f"channel_verify_{datetime.utcnow().timestamp()}"
        client = Client(
            session_name,
            api_id=api_id,
            api_hash=api_hash,
            bot_token=bot_token,
            in_memory=True
        )
        
        try:
            await client.start()
            
            # Get channel info
            chat = await client.get_chat(channel_id)
            verification_result['accessible'] = True
            verification_result['channel_info'] = {
                'title': getattr(chat, 'title', None),
                'username': getattr(chat, 'username', None),
                'type': str(chat.type),
                'members_count': getattr(chat, 'members_count', None)
            }
            
            # Test basic permissions
            permissions = {}
            
            # Test send permission
            try:
                test_msg = await client.send_message(
                    channel_id,
                    "🔍 Access verification test",
                    disable_notification=True
                )
                permissions['send_messages'] = True
                
                # Test delete permission
                try:
                    await client.delete_messages(channel_id, test_msg.id)
                    permissions['delete_messages'] = True
                except:
                    permissions['delete_messages'] = False
                    
            except Exception as e:
                permissions['send_messages'] = False
                permissions['delete_messages'] = False
                
            verification_result['permissions'] = permissions
            
        except Exception as e:
            verification_result['error'] = str(e)
            
        finally:
            await client.stop()
            
        return verification_result
        
    async def cleanup_test_messages(self, channel_id: str, bot_token: str, api_id: int, api_hash: str):
        """Cleanup test messages from a channel"""
        try:
            # Get test message IDs from Redis
            test_message_ids = await self.redis.lrange(f"test_messages:{channel_id}", 0, -1)
            
            if not test_message_ids:
                return
                
            session_name = f"cleanup_{datetime.utcnow().timestamp()}"
            client = Client(
                session_name,
                api_id=api_id,
                api_hash=api_hash,
                bot_token=bot_token,
                in_memory=True
            )
            
            await client.start()
            
            # Delete messages in batches
            message_ids = [int(msg_id) for msg_id in test_message_ids]
            
            # Pyrogram can delete up to 100 messages at once
            batch_size = 100
            for i in range(0, len(message_ids), batch_size):
                batch = message_ids[i:i + batch_size]
                try:
                    await client.delete_messages(channel_id, batch)
                    logger.info(f"Cleaned up {len(batch)} test messages from {channel_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup messages batch: {e}")
                    
            await client.stop()
            
            # Clear Redis list
            await self.redis.delete(f"test_messages:{channel_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup test messages: {e}")
            
    async def _permission_monitoring_loop(self):
        """Continuous permission monitoring loop"""
        while True:
            try:
                logger.info("Starting periodic permission verification")
                
                # Get current active token info (assuming token manager integration)
                current_token = await self.redis.get('current_active_token')
                if current_token:
                    token_data = json.loads(current_token)
                    
                    # Verify permissions for critical channels only
                    critical_channels = [ch for ch in self.configured_channels if ch.channel_type in ['log_channel', 'course_channel']]
                    
                    for channel in critical_channels:
                        try:
                            verification = await self.verify_channel_access(
                                channel.channel_id,
                                token_data['token'],
                                token_data['api_id'],
                                token_data['api_hash']
                            )
                            
                            # Update channel status
                            channel.status = 'verified' if verification['accessible'] else 'failed'
                            channel.last_verified = datetime.utcnow().isoformat()
                            
                            if not verification['accessible']:
                                channel.error_message = verification.get('error', 'Access verification failed')
                                logger.warning(f"Channel {channel.channel_id} verification failed: {channel.error_message}")
                                
                        except Exception as e:
                            logger.error(f"Error verifying channel {channel.channel_id}: {e}")
                            
                # Save updated channel status
                await self._save_channel_status()
                
                await asyncio.sleep(self.permission_check_interval)
                
            except Exception as e:
                logger.error(f"Permission monitoring error: {e}")
                await asyncio.sleep(self.permission_check_interval)
                
    async def _save_permission_results(self, results: List[PermissionTestResult], bot_username: str):
        """Save permission test results to database and Redis"""
        try:
            # Save to Redis for quick access
            results_data = {
                'bot_username': bot_username,
                'results': [asdict(result) for result in results],
                'test_time': datetime.utcnow().isoformat()
            }
            
            await self.redis.setex(
                f'permission_results:{bot_username}',
                3600,  # 1 hour TTL
                json.dumps(results_data)
            )
            
            # Save to database
            async with self.supabase.get_connection() as conn:
                for result in results:
                    await conn.execute("""
                        INSERT INTO permission_test_results 
                        (channel_id, permission_type, success, error_message, test_time, bot_username)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, result.channel_id, result.permission_type, result.success, 
                        result.error_message, result.test_time, bot_username)
                        
        except Exception as e:
            logger.error(f"Failed to save permission results: {e}")
            
    async def _save_sync_results(self, sync_results: Dict):
        """Save synchronization results"""
        try:
            await self.redis.setex(
                'permission_sync_results',
                3600,
                json.dumps(sync_results)
            )
            
            async with self.supabase.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO permission_sync_history 
                    (sync_time, total_tokens, successful_tokens, failed_tokens, results_data)
                    VALUES ($1, $2, $3, $4, $5)
                """, sync_results['sync_time'], sync_results['total_tokens'],
                    sync_results['successful_tokens'], sync_results['failed_tokens'],
                    json.dumps(sync_results))
                    
        except Exception as e:
            logger.error(f"Failed to save sync results: {e}")
            
    async def _save_channel_status(self):
        """Save current channel status to Redis and database"""
        try:
            channel_status = {
                'channels': [asdict(channel) for channel in self.configured_channels],
                'last_update': datetime.utcnow().isoformat()
            }
            
            await self.redis.setex(
                'channel_status',
                3600,
                json.dumps(channel_status, default=str)
            )
            
        except Exception as e:
            logger.error(f"Failed to save channel status: {e}")
            
    async def get_permission_status(self) -> Dict:
        """Get current permission status for all channels"""
        return {
            'total_channels': len(self.configured_channels),
            'verified_channels': len([ch for ch in self.configured_channels if ch.status == 'verified']),
            'failed_channels': len([ch for ch in self.configured_channels if ch.status == 'failed']),
            'channels': [asdict(channel) for channel in self.configured_channels],
            'last_check': datetime.utcnow().isoformat()
        }
        
    async def shutdown(self):
        """Shutdown permission manager and cleanup"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
                
        # Cleanup test messages for all channels
        try:
            current_token = await self.redis.get('current_active_token')
            if current_token:
                token_data = json.loads(current_token)
                
                for channel in self.configured_channels:
                    await self.cleanup_test_messages(
                        channel.channel_id,
                        token_data['token'],
                        token_data['api_id'],
                        token_data['api_hash']
                    )
        except Exception as e:
            logger.error(f"Error during permission manager cleanup: {e}")
            
        logger.info("Channel permission manager shutdown complete")