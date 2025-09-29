"""
Channel Health Monitor - Story 1.2
Monitors channel health, performs regular health checks, and manages automatic failover
"""
import logging
import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pyrogram import Client
from pyrogram.errors import ChannelInvalid, ChatAdminRequired, FloodWait
from core.supabase_client import supabase_client
from core.redis_state import redis_state
from core.multi_channel_manager import ChannelInfo

logger = logging.getLogger(__name__)

class ChannelHealthMonitor:
    """Monitors and manages channel health with automatic failover capabilities"""
    
    def __init__(self, bot_client: Client):
        self.bot = bot_client
        self.check_interval = 300  # 5 minutes
        self.health_threshold = 50  # Below this triggers failover
        self.max_response_time = 30000  # 30 seconds in ms
        self.monitoring_active = False
        
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        if self.monitoring_active:
            logger.info("Health monitoring already active")
            return
            
        self.monitoring_active = True
        logger.info("Starting channel health monitoring")
        
        while self.monitoring_active:
            try:
                await self.perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.monitoring_active = False
        logger.info("Health monitoring stopped")
    
    async def perform_health_checks(self):
        """Perform health checks on all channels"""
        try:
            # Get all active channels
            channels = await self._get_all_channels()
            
            if not channels:
                logger.warning("No channels found for health monitoring")
                return
            
            health_results = []
            
            for channel in channels:
                try:
                    health_result = await self.check_channel_health(channel)
                    health_results.append(health_result)
                    
                    # Small delay to avoid rate limiting
                    await asyncio.sleep(1)
                    
                except FloodWait as e:
                    logger.warning(f"Rate limited, waiting {e.value} seconds")
                    await asyncio.sleep(e.value)
                    
                except Exception as e:
                    logger.error(f"Health check failed for channel {channel.channel_username}: {e}")
                    await self._record_health_check(channel.id, 'failed', 0, str(e))
            
            # Process health results and trigger failovers if needed
            await self._process_health_results(health_results)
            
            logger.info(f"Completed health checks for {len(channels)} channels")
            
        except Exception as e:
            logger.error(f"Health check batch failed: {e}")
    
    async def check_channel_health(self, channel: ChannelInfo) -> Dict:
        """Perform comprehensive health check on a single channel"""
        start_time = time.time()
        health_result = {
            'channel_id': channel.id,
            'channel_username': channel.channel_username,
            'tests': {}
        }
        
        try:
            # Test 1: Basic channel access
            access_result = await self._test_channel_access(channel)
            health_result['tests']['access'] = access_result
            
            # Test 2: Message sending capability (if permitted)
            send_result = await self._test_message_sending(channel)
            health_result['tests']['send'] = send_result
            
            # Test 3: Permission verification
            permission_result = await self._test_channel_permissions(channel)
            health_result['tests']['permissions'] = permission_result
            
            # Calculate overall health score
            response_time = int((time.time() - start_time) * 1000)
            health_score = self._calculate_health_score(health_result['tests'], response_time)
            
            # Update channel health in database
            await self._update_channel_health(
                channel.id, health_score, response_time, 'active' if health_score >= self.health_threshold else 'degraded'
            )
            
            # Record detailed health check
            await self._record_health_check(channel.id, 'success', health_score, None, response_time)
            
            health_result['health_score'] = health_score
            health_result['response_time'] = response_time
            health_result['status'] = 'healthy' if health_score >= self.health_threshold else 'degraded'
            
            return health_result
            
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            await self._update_channel_health(channel.id, 0, response_time, 'failed')
            await self._record_health_check(channel.id, 'failed', 0, str(e), response_time)
            
            health_result['health_score'] = 0
            health_result['response_time'] = response_time
            health_result['status'] = 'failed'
            health_result['error'] = str(e)
            
            return health_result
    
    async def _test_channel_access(self, channel: ChannelInfo) -> Dict:
        """Test basic channel access"""
        try:
            chat = await self.bot.get_chat(channel.channel_id)
            return {
                'success': True,
                'chat_type': str(chat.type),
                'member_count': getattr(chat, 'members_count', 0)
            }
        except ChannelInvalid:
            return {'success': False, 'error': 'Channel invalid or inaccessible'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _test_message_sending(self, channel: ChannelInfo) -> Dict:
        """Test message sending capability"""
        try:
            # Send a test message
            test_message = await self.bot.send_message(
                channel.channel_id, 
                "🔍 Health Check - This message will be deleted",
                disable_notification=True
            )
            
            # Immediately delete the test message
            await self.bot.delete_messages(channel.channel_id, test_message.id)
            
            return {'success': True, 'can_send': True, 'can_delete': True}
            
        except ChatAdminRequired:
            return {'success': False, 'error': 'Admin permissions required'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _test_channel_permissions(self, channel: ChannelInfo) -> Dict:
        """Test channel permissions"""
        try:
            # Get chat member info for the bot
            chat_member = await self.bot.get_chat_member(channel.channel_id, "me")
            
            permissions = {
                'can_post_messages': getattr(chat_member.privileges, 'can_post_messages', False) if chat_member.privileges else False,
                'can_delete_messages': getattr(chat_member.privileges, 'can_delete_messages', False) if chat_member.privileges else False,
                'can_edit_messages': getattr(chat_member.privileges, 'can_edit_messages', False) if chat_member.privileges else False,
                'status': str(chat_member.status) if chat_member.status else 'unknown'
            }
            
            return {'success': True, 'permissions': permissions}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _calculate_health_score(self, test_results: Dict, response_time: int) -> int:
        """Calculate overall health score based on test results"""
        base_score = 100
        
        # Deduct points for failed tests
        if not test_results.get('access', {}).get('success', False):
            base_score -= 50  # Channel inaccessible
            
        if not test_results.get('send', {}).get('success', True):  # Default True if not tested
            base_score -= 30  # Cannot send messages
            
        if not test_results.get('permissions', {}).get('success', True):  # Default True if not tested
            base_score -= 20  # Permission issues
        
        # Deduct points for slow response time
        if response_time > self.max_response_time:
            base_score -= 30  # Very slow response
        elif response_time > self.max_response_time // 2:
            base_score -= 15  # Slow response
        
        return max(0, min(100, base_score))
    
    async def _update_channel_health(self, channel_id: str, health_score: int, 
                                   response_time: int, status: str):
        """Update channel health in database"""
        try:
            await supabase_client.execute_command(
                """
                UPDATE channels 
                SET health_score = $1, response_time_ms = $2, status = $3, 
                    last_health_check = NOW()
                WHERE id = $4
                """,
                health_score, response_time, status, channel_id
            )
            
            # Cache health status in Redis
            cache_key = f"channel_health:{channel_id}"
            health_data = {
                'health_score': health_score,
                'response_time_ms': response_time,
                'status': status,
                'last_check': datetime.utcnow().isoformat()
            }
            await redis_client.setex(cache_key, 600, json.dumps(health_data))  # Cache for 10 minutes
            
        except Exception as e:
            logger.error(f"Failed to update channel health: {e}")
    
    async def _record_health_check(self, channel_id: str, status: str, health_score: int, 
                                 error_message: Optional[str] = None, response_time: Optional[int] = None):
        """Record detailed health check results"""
        try:
            await supabase_client.execute_command(
                """
                INSERT INTO channel_health_logs (channel_id, status, health_score, error_message, response_time_ms)
                VALUES ($1, $2, $3, $4, $5)
                """,
                channel_id, status, health_score, error_message, response_time
            )
        except Exception as e:
            logger.error(f"Failed to record health check: {e}")
    
    async def _get_all_channels(self) -> List[ChannelInfo]:
        """Get all channels for monitoring"""
        try:
            result = await supabase_client.execute_query(
                """
                SELECT id, channel_id, channel_username, channel_type, status, 
                       priority, health_score, response_time_ms, success_rate
                FROM channels 
                WHERE status IN ('active', 'degraded')
                ORDER BY priority ASC
                """
            )
            
            return [ChannelInfo(
                id=row['id'],
                channel_id=row['channel_id'],
                channel_username=row['channel_username'],
                channel_type=row['channel_type'],
                status=row['status'],
                priority=row['priority'],
                health_score=row['health_score'],
                response_time_ms=row['response_time_ms'],
                success_rate=row['success_rate']
            ) for row in result]
            
        except Exception as e:
            logger.error(f"Failed to get channels for monitoring: {e}")
            return []
    
    async def _process_health_results(self, health_results: List[Dict]):
        """Process health check results and trigger necessary actions"""
        try:
            failed_channels = []
            degraded_channels = []
            
            for result in health_results:
                if result['status'] == 'failed':
                    failed_channels.append(result)
                elif result['status'] == 'degraded':
                    degraded_channels.append(result)
            
            # Handle failed channels
            for failed_channel in failed_channels:
                await self._handle_channel_failure(
                    failed_channel['channel_id'], 
                    failed_channel.get('error', 'Health check failed')
                )
            
            # Send alerts for degraded channels
            for degraded_channel in degraded_channels:
                await self._send_degraded_alert(degraded_channel)
            
            # Update monitoring statistics
            await self._update_monitoring_stats(len(health_results), len(failed_channels), len(degraded_channels))
            
        except Exception as e:
            logger.error(f"Failed to process health results: {e}")
    
    async def _handle_channel_failure(self, channel_id: str, reason: str):
        """Handle channel failure and trigger failover if needed"""
        try:
            # Mark channel as failed
            await supabase_client.execute_command(
                "UPDATE channels SET status = 'failed' WHERE id = $1",
                channel_id
            )
            
            # Check if this channel has active files that need failover
            active_files = await supabase_client.execute_query(
                """
                SELECT COUNT(*) as file_count 
                FROM file_storage 
                WHERE channel_id = $1 AND storage_status = 'active'
                """,
                channel_id
            )
            
            if active_files and active_files[0]['file_count'] > 0:
                logger.warning(f"Channel failure affects {active_files[0]['file_count']} active files")
                
                # Trigger failover (this would be handled by MultiChannelManager)
                from core.multi_channel_manager import MultiChannelManager
                multi_channel_manager = MultiChannelManager(self.bot)
                await multi_channel_manager.trigger_failover(channel_id, reason)
            
            # Send failure alert
            await self._send_failure_alert(channel_id, reason)
            
        except Exception as e:
            logger.error(f"Failed to handle channel failure: {e}")
    
    async def _send_failure_alert(self, channel_id: str, reason: str):
        """Send alert for channel failure"""
        try:
            # Get channel info
            channel_info = await supabase_client.execute_query(
                "SELECT channel_username, channel_type FROM channels WHERE id = $1",
                channel_id
            )
            
            if channel_info:
                alert_message = (
                    f"🚨 **Channel Failure Alert**\n"
                    f"Channel: {channel_info[0]['channel_username']}\n"
                    f"Type: {channel_info[0]['channel_type']}\n"
                    f"Reason: {reason}\n"
                    f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
                
                # Store alert in cache for admin retrieval
                alert_key = f"channel_alert:{channel_id}:{int(time.time())}"
                await redis_client.setex(alert_key, 86400, alert_message)  # Store for 24 hours
                
                logger.error(alert_message)
                
        except Exception as e:
            logger.error(f"Failed to send failure alert: {e}")
    
    async def _send_degraded_alert(self, channel_result: Dict):
        """Send alert for degraded channel"""
        try:
            alert_message = (
                f"⚠️ **Channel Degraded Alert**\n"
                f"Channel: {channel_result['channel_username']}\n"
                f"Health Score: {channel_result['health_score']}\n"
                f"Response Time: {channel_result['response_time']}ms\n"
                f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            
            # Store alert in cache
            alert_key = f"channel_degraded:{channel_result['channel_id']}:{int(time.time())}"
            await redis_client.setex(alert_key, 3600, alert_message)  # Store for 1 hour
            
            logger.warning(alert_message)
            
        except Exception as e:
            logger.error(f"Failed to send degraded alert: {e}")
    
    async def _update_monitoring_stats(self, total_checks: int, failed_count: int, degraded_count: int):
        """Update monitoring statistics"""
        try:
            stats = {
                'last_check': datetime.utcnow().isoformat(),
                'total_channels': total_checks,
                'failed_channels': failed_count,
                'degraded_channels': degraded_count,
                'healthy_channels': total_checks - failed_count - degraded_count
            }
            
            await redis_client.setex('monitoring_stats', 3600, json.dumps(stats))
            
        except Exception as e:
            logger.error(f"Failed to update monitoring stats: {e}")
    
    async def get_monitoring_status(self) -> Dict:
        """Get current monitoring status"""
        try:
            stats = await redis_client.get('monitoring_stats')
            if stats:
                return json.loads(stats)
            return {'status': 'no_data'}
        except Exception as e:
            logger.error(f"Failed to get monitoring status: {e}")
            return {'status': 'error', 'error': str(e)}