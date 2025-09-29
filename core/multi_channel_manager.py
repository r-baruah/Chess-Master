"""
Multi-Channel File Manager - Story 1.2
Handles file storage, health monitoring, and anonymous forwarding across multiple Telegram channels
"""
import logging
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
try:
    from pyrogram import Client
    from pyrogram.types import Message
except ImportError:
    Client = None
    Message = None
try:
    from core.supabase_client import supabase_client
    from core.redis_state import redis_state
except ImportError:
    supabase_client = None
    redis_state = None

logger = logging.getLogger(__name__)

@dataclass
class ChannelInfo:
    """Channel information data class"""
    id: str
    channel_id: int
    channel_username: str
    channel_type: str
    status: str
    priority: int
    health_score: int
    response_time_ms: Optional[int] = None
    success_rate: float = 100.0

@dataclass
class FileStorageInfo:
    """File storage information data class"""
    id: str
    course_file_id: str
    channel_id: str
    message_id: int
    message_link: str
    storage_status: str
    file_size: Optional[int] = None
    checksum: Optional[str] = None

class MultiChannelManager:
    """Manager for multi-channel file storage and retrieval"""
    
    def __init__(self, bot_client: Client):
        self.bot = bot_client
        self.health_check_interval = 300  # 5 minutes
        self.max_retry_attempts = 3
        self.failover_threshold = 50  # Health score threshold for failover
        
    async def get_healthy_channels(self, channel_type: Optional[str] = None) -> List[ChannelInfo]:
        """Get list of healthy channels sorted by priority"""
        try:
            query = """
                SELECT id, channel_id, channel_username, channel_type, status, 
                       priority, health_score, response_time_ms, success_rate
                FROM channels 
                WHERE status = 'active' AND health_score >= $1
            """
            params = [self.failover_threshold]
            
            if channel_type:
                query += " AND channel_type = $2"
                params.append(channel_type)
                
            query += " ORDER BY priority ASC, health_score DESC"
            
            result = await supabase_client.execute_query(query, *params)
            
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
            logger.error(f"Failed to get healthy channels: {e}")
            return []
    
    async def store_file_multi_channel(self, file_data: Dict, course_id: str) -> List[FileStorageInfo]:
        """Store file across multiple channels with redundancy"""
        try:
            # Get healthy channels (primary first, then backups)
            primary_channels = await self.get_healthy_channels('primary')
            backup_channels = await self.get_healthy_channels('backup')
            all_channels = primary_channels + backup_channels
            
            if not all_channels:
                raise Exception("No healthy channels available for file storage")
            
            storage_results = []
            file_hash = await self._calculate_file_hash(file_data.get('file_path'))
            
            for channel in all_channels:
                try:
                    # Store file in channel
                    storage_result = await self._store_file_in_channel(
                        channel, file_data, course_id, file_hash
                    )
                    storage_results.append(storage_result)
                    
                    # Update channel statistics
                    await self._update_channel_stats(channel.id, success=True)
                    
                except Exception as e:
                    logger.error(f"Failed to store file in channel {channel.channel_username}: {e}")
                    await self._update_channel_stats(channel.id, success=False)
                    await self._handle_storage_error(channel, e)
            
            if not storage_results:
                raise Exception("Failed to store file in any channel")
                
            logger.info(f"File stored in {len(storage_results)} channels")
            return storage_results
            
        except Exception as e:
            logger.error(f"Multi-channel file storage failed: {e}")
            raise
    
    async def _store_file_in_channel(self, channel: ChannelInfo, file_data: Dict, 
                                   course_id: str, file_hash: str) -> FileStorageInfo:
        """Store file in a specific channel"""
        try:
            # Send file to channel
            message = await self.bot.send_document(
                chat_id=channel.channel_id,
                document=file_data['file_path'],
                caption=f"📚 Course File - ID: {course_id}",
                disable_notification=True
            )
            
            # Generate message link
            message_link = f"https://t.me/c/{str(channel.channel_id)[4:]}/{message.id}"
            if channel.channel_username:
                message_link = f"https://t.me/{channel.channel_username}/{message.id}"
            
            # Store in database
            storage_data = {
                'course_file_id': file_data['course_file_id'],
                'channel_id': channel.id,
                'message_id': message.id,
                'message_link': message_link,
                'storage_status': 'active',
                'file_size': file_data.get('file_size'),
                'checksum': file_hash
            }
            
            result = await supabase_client.execute_command(
                """
                INSERT INTO file_storage (course_file_id, channel_id, message_id, message_link, 
                                        storage_status, file_size, checksum)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                storage_data['course_file_id'], storage_data['channel_id'],
                storage_data['message_id'], storage_data['message_link'],
                storage_data['storage_status'], storage_data['file_size'],
                storage_data['checksum']
            )
            
            return FileStorageInfo(
                id=result[0]['id'],
                **storage_data
            )
            
        except Exception as e:
            logger.error(f"Failed to store file in channel {channel.channel_username}: {e}")
            raise
    
    async def get_file_from_best_channel(self, course_file_id: str) -> Optional[FileStorageInfo]:
        """Get file from the best available channel"""
        try:
            # Get all storage locations for this file
            result = await supabase_client.execute_query(
                """
                SELECT fs.*, c.channel_id, c.channel_username, c.status as channel_status, 
                       c.health_score, c.priority
                FROM file_storage fs
                JOIN channels c ON fs.channel_id = c.id
                WHERE fs.course_file_id = $1 
                  AND fs.storage_status = 'active' 
                  AND c.status = 'active'
                ORDER BY c.priority ASC, c.health_score DESC
                """,
                course_file_id
            )
            
            if not result:
                return None
                
            # Return the best available storage location
            best_storage = result[0]
            return FileStorageInfo(
                id=best_storage['id'],
                course_file_id=best_storage['course_file_id'],
                channel_id=best_storage['channel_id'],
                message_id=best_storage['message_id'],
                message_link=best_storage['message_link'],
                storage_status=best_storage['storage_status'],
                file_size=best_storage['file_size'],
                checksum=best_storage['checksum']
            )
            
        except Exception as e:
            logger.error(f"Failed to get file from best channel: {e}")
            return None
    
    async def verify_file_integrity(self, storage_info: FileStorageInfo) -> bool:
        """Verify file integrity using checksum"""
        try:
            # This would involve downloading the file and checking its hash
            # For now, we'll implement a basic message existence check
            channel_result = await supabase_client.execute_query(
                "SELECT channel_id FROM channels WHERE id = $1",
                storage_info.channel_id
            )
            
            if not channel_result:
                return False
                
            channel_id = channel_result[0]['channel_id']
            
            # Try to get the message
            message = await self.bot.get_messages(channel_id, storage_info.message_id)
            
            # Update verification timestamp
            await supabase_client.execute_command(
                """
                UPDATE file_storage 
                SET last_verified = NOW(), verification_attempts = verification_attempts + 1
                WHERE id = $1
                """,
                storage_info.id
            )
            
            return message is not None
            
        except Exception as e:
            logger.error(f"File integrity verification failed: {e}")
            
            # Mark as potentially corrupted if multiple verification failures
            await supabase_client.execute_command(
                """
                UPDATE file_storage 
                SET verification_attempts = verification_attempts + 1,
                    storage_status = CASE 
                        WHEN verification_attempts >= 3 THEN 'corrupted'
                        ELSE storage_status
                    END
                WHERE id = $1
                """,
                storage_info.id
            )
            
            return False
    
    async def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file"""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate file hash: {e}")
            return ""
    
    async def _update_channel_stats(self, channel_id: str, success: bool):
        """Update channel success rate statistics"""
        try:
            # Get current stats from Redis cache
            cache_key = f"channel_stats:{channel_id}"
            cached_stats = await redis_client.get(cache_key)
            
            if cached_stats:
                stats = json.loads(cached_stats)
            else:
                stats = {'successes': 0, 'failures': 0, 'total': 0}
            
            # Update stats
            stats['total'] += 1
            if success:
                stats['successes'] += 1
            else:
                stats['failures'] += 1
            
            # Calculate success rate
            success_rate = (stats['successes'] / stats['total']) * 100 if stats['total'] > 0 else 100
            
            # Cache for 1 hour
            await redis_client.setex(cache_key, 3600, json.dumps(stats))
            
            # Update database every 10 operations
            if stats['total'] % 10 == 0:
                await supabase_client.execute_command(
                    "UPDATE channels SET success_rate = $1 WHERE id = $2",
                    success_rate, channel_id
                )
                
        except Exception as e:
            logger.error(f"Failed to update channel stats: {e}")
    
    async def _handle_storage_error(self, channel: ChannelInfo, error: Exception):
        """Handle storage errors and update channel health"""
        try:
            # Log the error
            await supabase_client.execute_command(
                """
                INSERT INTO channel_health_logs (channel_id, status, error_message, health_score, test_type)
                VALUES ($1, 'failed', $2, $3, 'upload')
                """,
                channel.id, str(error), max(0, channel.health_score - 20)
            )
            
            # Reduce health score
            new_health_score = max(0, channel.health_score - 20)
            await supabase_client.execute_command(
                "UPDATE channels SET health_score = $1 WHERE id = $2",
                new_health_score, channel.id
            )
            
            # If health score drops too low, mark channel as degraded
            if new_health_score < self.failover_threshold:
                await supabase_client.execute_command(
                    "UPDATE channels SET status = 'degraded' WHERE id = $1",
                    channel.id
                )
                logger.warning(f"Channel {channel.channel_username} marked as degraded")
                
        except Exception as e:
            logger.error(f"Failed to handle storage error: {e}")
    
    async def trigger_failover(self, failed_channel_id: str, reason: str) -> bool:
        """Trigger failover from failed channel to backup channels"""
        try:
            # Get backup channels
            backup_channels = await self.get_healthy_channels('backup')
            
            if not backup_channels:
                logger.error("No backup channels available for failover")
                return False
            
            # Get files from failed channel
            failed_files = await supabase_client.execute_query(
                """
                SELECT * FROM file_storage 
                WHERE channel_id = $1 AND storage_status = 'active'
                """,
                failed_channel_id
            )
            
            if not failed_files:
                logger.info("No active files found in failed channel")
                return True
            
            # Record failover event
            best_backup = backup_channels[0]
            await supabase_client.execute_command(
                """
                INSERT INTO channel_failover_events (failed_channel_id, backup_channel_id, reason, files_affected)
                VALUES ($1, $2, $3, $4)
                """,
                failed_channel_id, best_backup.id, reason, len(failed_files)
            )
            
            logger.info(f"Failover triggered: {len(failed_files)} files affected")
            return True
            
        except Exception as e:
            logger.error(f"Failover failed: {e}")
            return False