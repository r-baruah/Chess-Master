"""
Anonymous File Forwarder - Story 1.2
Handles anonymous file forwarding while preserving contributor privacy
"""
import logging
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pyrogram import Client
from pyrogram.types import Message
from core.supabase_client import supabase_client
from core.redis_state import redis_state
from core.multi_channel_manager import MultiChannelManager, FileStorageInfo
from core.anonymity import AnonymousIdentityManager

logger = logging.getLogger(__name__)

class AnonymousFileForwarder:
    """Handles anonymous file forwarding while preserving contributor privacy"""
    
    def __init__(self, bot_client: Client):
        self.bot = bot_client
        self.multi_channel_manager = MultiChannelManager(bot_client)
        self.anonymous_id_manager = AnonymousIdentityManager()
        self.rate_limit_window = 3600  # 1 hour
        self.rate_limit_per_user = 50  # Max 50 files per hour per user
        
    async def forward_file_anonymously(self, user_telegram_id: int, file_request: str) -> Optional[Message]:
        """Forward file to user while preserving complete anonymity"""
        try:
            # Check rate limiting
            if not await self._check_rate_limit(user_telegram_id):
                raise Exception("Rate limit exceeded. Please try again later.")
            
            # Parse file request (could be file ID, course name, or search term)
            file_info = await self._resolve_file_request(file_request)
            
            if not file_info:
                raise Exception("File not found or not available")
            
            # Get file from best available channel
            storage_info = await self.multi_channel_manager.get_file_from_best_channel(file_info['course_file_id'])
            
            if not storage_info:
                raise Exception("File temporarily unavailable - trying backup channels")
            
            # Verify file integrity before forwarding
            if not await self.multi_channel_manager.verify_file_integrity(storage_info):
                # Try to find another storage location
                storage_info = await self._find_alternative_storage(file_info['course_file_id'])
                if not storage_info:
                    raise Exception("File verification failed and no backup available")
            
            # Forward file anonymously
            forwarded_message = await self._perform_anonymous_forward(user_telegram_id, storage_info, file_info)
            
            # Log anonymous delivery (without identity correlation)
            await self._log_anonymous_delivery(user_telegram_id, storage_info, file_info, success=True)
            
            # Update rate limiting
            await self._update_rate_limit(user_telegram_id)
            
            return forwarded_message
            
        except Exception as e:
            logger.error(f"Anonymous file forwarding failed: {e}")
            
            # Log failed delivery attempt
            if 'file_info' in locals() and 'storage_info' in locals():
                await self._log_anonymous_delivery(user_telegram_id, storage_info, file_info, success=False, error=str(e))
            
            raise
    
    async def forward_file_by_course_id(self, user_telegram_id: int, course_id: str) -> List[Message]:
        """Forward all files from a course anonymously"""
        try:
            # Check rate limiting (higher limit for course downloads)
            if not await self._check_rate_limit(user_telegram_id, multiplier=5):
                raise Exception("Rate limit exceeded for course downloads")
            
            # Get all files for the course
            course_files = await self._get_course_files(course_id)
            
            if not course_files:
                raise Exception("Course not found or has no files")
            
            forwarded_messages = []
            
            # Forward each file
            for file_info in course_files:
                try:
                    message = await self.forward_file_anonymously(user_telegram_id, file_info['id'])
                    if message:
                        forwarded_messages.append(message)
                        
                        # Small delay between forwards to avoid spam
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Failed to forward file {file_info['file_name']}: {e}")
                    continue
            
            if not forwarded_messages:
                raise Exception("No files could be forwarded from this course")
            
            # Send course summary message
            summary_message = await self.bot.send_message(
                user_telegram_id,
                f"📚 Course Download Complete\n"
                f"Successfully forwarded {len(forwarded_messages)} files\n"
                f"Course ID: {course_id}"
            )
            
            forwarded_messages.append(summary_message)
            return forwarded_messages
            
        except Exception as e:
            logger.error(f"Course file forwarding failed: {e}")
            raise
    
    async def _resolve_file_request(self, file_request: str) -> Optional[Dict]:
        """Resolve file request to actual file information"""
        try:
            # Try different resolution methods
            
            # Method 1: Direct file ID
            if file_request.startswith('file_'):
                return await self._get_file_by_id(file_request)
            
            # Method 2: Course file ID (UUID)
            try:
                # Check if it's a valid UUID
                import uuid
                uuid.UUID(file_request)
                return await self._get_file_by_course_file_id(file_request)
            except ValueError:
                pass
            
            # Method 3: Search by filename
            return await self._search_file_by_name(file_request)
            
        except Exception as e:
            logger.error(f"Failed to resolve file request: {e}")
            return None
    
    async def _get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file by internal file ID"""
        try:
            result = await supabase_client.execute_query(
                """
                SELECT cf.id as course_file_id, cf.file_name, cf.file_type, cf.file_size,
                       c.title as course_title, c.status as course_status
                FROM course_files cf
                JOIN courses c ON cf.course_id = c.id
                WHERE cf.id = $1 AND c.status = 'approved'
                """,
                file_id.replace('file_', '')  # Remove prefix
            )
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to get file by ID: {e}")
            return None
    
    async def _get_file_by_course_file_id(self, course_file_id: str) -> Optional[Dict]:
        """Get file by course file UUID"""
        try:
            result = await supabase_client.execute_query(
                """
                SELECT cf.id as course_file_id, cf.file_name, cf.file_type, cf.file_size,
                       c.title as course_title, c.status as course_status
                FROM course_files cf
                JOIN courses c ON cf.course_id = c.id
                WHERE cf.id = $1 AND c.status = 'approved'
                """,
                course_file_id
            )
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to get file by course file ID: {e}")
            return None
    
    async def _search_file_by_name(self, filename: str) -> Optional[Dict]:
        """Search file by name"""
        try:
            result = await supabase_client.execute_query(
                """
                SELECT cf.id as course_file_id, cf.file_name, cf.file_type, cf.file_size,
                       c.title as course_title, c.status as course_status
                FROM course_files cf
                JOIN courses c ON cf.course_id = c.id
                WHERE cf.file_name ILIKE $1 AND c.status = 'approved'
                ORDER BY cf.created_at DESC
                LIMIT 1
                """,
                f"%{filename}%"
            )
            
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to search file by name: {e}")
            return None
    
    async def _get_course_files(self, course_id: str) -> List[Dict]:
        """Get all files for a course"""
        try:
            result = await supabase_client.execute_query(
                """
                SELECT cf.id, cf.file_name, cf.file_type, cf.file_size,
                       c.title as course_title, c.status as course_status
                FROM course_files cf
                JOIN courses c ON cf.course_id = c.id
                WHERE c.id = $1 AND c.status = 'approved'
                ORDER BY cf.created_at ASC
                """,
                course_id
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get course files: {e}")
            return []
    
    async def _find_alternative_storage(self, course_file_id: str) -> Optional[FileStorageInfo]:
        """Find alternative storage location for file"""
        try:
            # Get all storage locations sorted by channel health
            result = await supabase_client.execute_query(
                """
                SELECT fs.*, c.health_score, c.status as channel_status
                FROM file_storage fs
                JOIN channels c ON fs.channel_id = c.id
                WHERE fs.course_file_id = $1 
                  AND fs.storage_status = 'active'
                  AND c.status = 'active'
                ORDER BY c.health_score DESC, c.priority ASC
                """,
                course_file_id
            )
            
            for storage_row in result:
                storage_info = FileStorageInfo(
                    id=storage_row['id'],
                    course_file_id=storage_row['course_file_id'],
                    channel_id=storage_row['channel_id'],
                    message_id=storage_row['message_id'],
                    message_link=storage_row['message_link'],
                    storage_status=storage_row['storage_status'],
                    file_size=storage_row['file_size'],
                    checksum=storage_row['checksum']
                )
                
                # Test if this storage location works
                if await self.multi_channel_manager.verify_file_integrity(storage_info):
                    return storage_info
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find alternative storage: {e}")
            return None
    
    async def _perform_anonymous_forward(self, user_telegram_id: int, storage_info: FileStorageInfo, 
                                       file_info: Dict) -> Message:
        """Perform the actual anonymous file forwarding"""
        try:
            # Get source channel info
            channel_result = await supabase_client.execute_query(
                "SELECT channel_id FROM channels WHERE id = $1",
                storage_info.channel_id
            )
            
            if not channel_result:
                raise Exception("Source channel not found")
            
            source_channel_id = channel_result[0]['channel_id']
            
            # Create anonymous caption without revealing source
            anonymous_caption = self._create_anonymous_caption(file_info)
            
            # Forward message while stripping identifying information
            forwarded_message = await self.bot.copy_message(
                chat_id=user_telegram_id,
                from_chat_id=source_channel_id,
                message_id=storage_info.message_id,
                caption=anonymous_caption
            )
            
            return forwarded_message
            
        except Exception as e:
            logger.error(f"Anonymous forwarding failed: {e}")
            raise
    
    def _create_anonymous_caption(self, file_info: Dict) -> str:
        """Create anonymous caption without revealing source information"""
        caption = f"📚 **{file_info['file_name']}**"
        
        if file_info.get('course_title'):
            # Anonymize course title if needed
            course_title = file_info['course_title']
            caption += f"\n🎯 Course: {course_title}"
        
        if file_info.get('file_size'):
            size_mb = file_info['file_size'] / (1024 * 1024)
            caption += f"\n📊 Size: {size_mb:.1f} MB"
        
        if file_info.get('file_type'):
            caption += f"\n📎 Type: {file_info['file_type']}"
        
        caption += f"\n\n🔒 **Anonymous Delivery** - Source protected"
        caption += f"\n⏰ Delivered: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
        
        return caption
    
    async def _log_anonymous_delivery(self, user_telegram_id: int, storage_info: FileStorageInfo,
                                    file_info: Dict, success: bool, error: Optional[str] = None):
        """Log anonymous delivery without creating identity correlations"""
        try:
            # Create anonymous hashes
            user_hash = hashlib.sha256(f"user_{user_telegram_id}_{int(time.time() // 86400)}".encode()).hexdigest()[:16]
            file_hash = hashlib.sha256(f"file_{storage_info.course_file_id}".encode()).hexdigest()[:16]
            
            # Log delivery with minimal identifying information
            await supabase_client.execute_command(
                """
                INSERT INTO anonymous_delivery_logs 
                (file_hash, user_hash, channel_used, success, bandwidth_used, delivery_method)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                file_hash, user_hash, storage_info.channel_id, success, 
                file_info.get('file_size', 0), 'copy'
            )
            
            # Update delivery statistics in Redis
            stats_key = f"delivery_stats:{datetime.utcnow().strftime('%Y-%m-%d')}"
            await redis_client.hincrby(stats_key, 'total_deliveries', 1)
            if success:
                await redis_client.hincrby(stats_key, 'successful_deliveries', 1)
            else:
                await redis_client.hincrby(stats_key, 'failed_deliveries', 1)
            
            await redis_client.expire(stats_key, 86400 * 7)  # Keep stats for 7 days
            
        except Exception as e:
            logger.error(f"Failed to log anonymous delivery: {e}")
    
    async def _check_rate_limit(self, user_telegram_id: int, multiplier: int = 1) -> bool:
        """Check if user has exceeded rate limit"""
        try:
            user_key = f"rate_limit:{user_telegram_id}"
            current_count = await redis_client.get(user_key)
            
            if current_count is None:
                return True
            
            current_count = int(current_count)
            limit = self.rate_limit_per_user * multiplier
            
            return current_count < limit
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return True  # Allow on error
    
    async def _update_rate_limit(self, user_telegram_id: int):
        """Update rate limit counter for user"""
        try:
            user_key = f"rate_limit:{user_telegram_id}"
            current_count = await redis_client.get(user_key)
            
            if current_count is None:
                # First request in window
                await redis_client.setex(user_key, self.rate_limit_window, 1)
            else:
                # Increment counter
                await redis_client.incr(user_key)
                
        except Exception as e:
            logger.error(f"Failed to update rate limit: {e}")
    
    async def get_user_rate_limit_status(self, user_telegram_id: int) -> Dict:
        """Get current rate limit status for user"""
        try:
            user_key = f"rate_limit:{user_telegram_id}"
            current_count = await redis_client.get(user_key)
            ttl = await redis_client.ttl(user_key)
            
            if current_count is None:
                return {
                    'requests_used': 0,
                    'requests_remaining': self.rate_limit_per_user,
                    'reset_time_seconds': None
                }
            
            current_count = int(current_count)
            
            return {
                'requests_used': current_count,
                'requests_remaining': max(0, self.rate_limit_per_user - current_count),
                'reset_time_seconds': ttl if ttl > 0 else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {
                'requests_used': 0,
                'requests_remaining': self.rate_limit_per_user,
                'reset_time_seconds': None,
                'error': str(e)
            }
    
    async def get_delivery_statistics(self, days: int = 7) -> Dict:
        """Get anonymous delivery statistics"""
        try:
            # Get statistics from Redis
            stats = {}
            
            for i in range(days):
                date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
                stats_key = f"delivery_stats:{date}"
                
                day_stats = await redis_client.hgetall(stats_key)
                if day_stats:
                    stats[date] = {
                        'total_deliveries': int(day_stats.get('total_deliveries', 0)),
                        'successful_deliveries': int(day_stats.get('successful_deliveries', 0)),
                        'failed_deliveries': int(day_stats.get('failed_deliveries', 0))
                    }
                else:
                    stats[date] = {
                        'total_deliveries': 0,
                        'successful_deliveries': 0,
                        'failed_deliveries': 0
                    }
            
            # Calculate totals
            totals = {
                'total_deliveries': sum(day['total_deliveries'] for day in stats.values()),
                'successful_deliveries': sum(day['successful_deliveries'] for day in stats.values()),
                'failed_deliveries': sum(day['failed_deliveries'] for day in stats.values())
            }
            
            success_rate = 0
            if totals['total_deliveries'] > 0:
                success_rate = (totals['successful_deliveries'] / totals['total_deliveries']) * 100
            
            return {
                'daily_stats': stats,
                'totals': totals,
                'success_rate': round(success_rate, 2),
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Failed to get delivery statistics: {e}")
            return {'error': str(e)}