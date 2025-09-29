"""
Targeted Announcement System - Large-scale community communication
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import json
import uuid
from enum import Enum
from core.supabase_client import supabase_client
from core.redis_state import redis_state
from core.anonymity import anonymous_manager
from core.roles import rbac_manager
from core.advanced_user_manager import advanced_user_manager

logger = logging.getLogger(__name__)

class AnnouncementStatus(Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TargetedAnnouncementManager:
    """Advanced announcement system for large-scale targeted communication"""
    
    def __init__(self):
        self.batch_size = 100  # Users per batch for delivery
        self.rate_limit_delay = 1  # Seconds between batches
        self.max_concurrent_announcements = 5
    
    async def create_announcement(
        self,
        creator_anonymous_id: str,
        title: str,
        content: str,
        targeting_rules: Dict[str, Any],
        scheduling: Optional[Dict[str, Any]] = None,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create targeted announcement with scheduling and targeting"""
        try:
            # Check permissions
            if not await rbac_manager.check_permission(creator_anonymous_id, 'manage_users'):
                return {'error': 'Permission denied'}
            
            announcement_id = str(uuid.uuid4())
            options = options or {}
            
            # Validate targeting rules
            target_validation = await self._validate_targeting_rules(targeting_rules)
            if 'error' in target_validation:
                return target_validation
            
            # Calculate estimated recipients
            estimated_recipients = await self._estimate_recipients(targeting_rules)
            
            announcement_data = {
                'id': announcement_id,
                'creator_anonymous_id': creator_anonymous_id,
                'title': title,
                'content': content,
                'targeting_rules': targeting_rules,
                'scheduling': scheduling or {'send_immediately': True},
                'options': {
                    'track_engagement': options.get('track_engagement', True),
                    'allow_replies': options.get('allow_replies', False),
                    'priority': options.get('priority', 'normal'),
                    'message_format': options.get('message_format', 'text'),
                    'include_unsubscribe': options.get('include_unsubscribe', True)
                },
                'status': AnnouncementStatus.DRAFT.value,
                'estimated_recipients': estimated_recipients,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            # Store announcement
            await supabase_client.execute_command(
                """
                INSERT INTO announcements (
                    id, creator_anonymous_id, title, content, targeting_rules, 
                    scheduling, options, status, estimated_recipients, 
                    created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                announcement_id, creator_anonymous_id, title, content,
                json.dumps(targeting_rules), json.dumps(announcement_data['scheduling']),
                json.dumps(announcement_data['options']), announcement_data['status'],
                estimated_recipients, announcement_data['created_at'], 
                announcement_data['updated_at']
            )
            
            logger.info(f"Created announcement {announcement_id} with {estimated_recipients} estimated recipients")
            return announcement_data
            
        except Exception as e:
            logger.error(f"Failed to create announcement: {e}")
            return {'error': str(e)}
    
    async def schedule_announcement(
        self,
        announcement_id: str,
        scheduled_time: datetime,
        timezone: str = 'UTC',
        requester_anonymous_id: str = None
    ) -> bool:
        """Schedule announcement for future delivery"""
        try:
            # Check permissions and ownership
            announcement = await self._get_announcement(announcement_id)
            if not announcement:
                return False
            
            if requester_anonymous_id and announcement['creator_anonymous_id'] != requester_anonymous_id:
                if not await rbac_manager.check_permission(requester_anonymous_id, 'manage_users'):
                    return False
            
            # Update scheduling
            scheduling_data = {
                'send_immediately': False,
                'scheduled_time': scheduled_time.isoformat(),
                'timezone': timezone,
                'scheduled_at': datetime.utcnow().isoformat()
            }
            
            await supabase_client.execute_command(
                """
                UPDATE announcements 
                SET scheduling = $2, status = $3, updated_at = $4
                WHERE id = $1
                """,
                announcement_id, json.dumps(scheduling_data),
                AnnouncementStatus.SCHEDULED.value, datetime.utcnow().isoformat()
            )
            
            # Add to scheduling queue
            await redis_state.queue_push('scheduled_announcements', {
                'announcement_id': announcement_id,
                'scheduled_time': scheduled_time.isoformat(),
                'timezone': timezone
            })
            
            logger.info(f"Scheduled announcement {announcement_id} for {scheduled_time}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule announcement: {e}")
            return False
    
    async def send_announcement(
        self,
        announcement_id: str,
        requester_anonymous_id: str = None
    ) -> Dict[str, Any]:
        """Send announcement to targeted recipients"""
        try:
            announcement = await self._get_announcement(announcement_id)
            if not announcement:
                return {'error': 'Announcement not found'}
            
            # Permission check
            if requester_anonymous_id and announcement['creator_anonymous_id'] != requester_anonymous_id:
                if not await rbac_manager.check_permission(requester_anonymous_id, 'manage_users'):
                    return {'error': 'Permission denied'}
            
            # Check if already sending or sent
            if announcement['status'] in [AnnouncementStatus.SENDING.value, AnnouncementStatus.SENT.value]:
                return {'error': f'Announcement is already {announcement["status"]}'}
            
            # Update status to sending
            await self._update_announcement_status(announcement_id, AnnouncementStatus.SENDING.value)
            
            # Get target recipients
            recipients = await self._resolve_targeting_rules(announcement['targeting_rules'])
            
            if not recipients:
                await self._update_announcement_status(announcement_id, AnnouncementStatus.FAILED.value)
                return {'error': 'No recipients found'}
            
            # Start async delivery process
            delivery_task = asyncio.create_task(
                self._deliver_announcement(announcement_id, announcement, recipients)
            )
            
            return {
                'announcement_id': announcement_id,
                'status': 'sending',
                'recipient_count': len(recipients),
                'estimated_completion': (
                    datetime.utcnow() + 
                    timedelta(seconds=len(recipients) // self.batch_size * self.rate_limit_delay)
                ).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to send announcement: {e}")
            return {'error': str(e)}
    
    async def _deliver_announcement(
        self,
        announcement_id: str,
        announcement: Dict[str, Any],
        recipients: List[Dict[str, Any]]
    ):
        """Background task to deliver announcement to all recipients"""
        try:
            delivery_stats = {
                'total_recipients': len(recipients),
                'delivered': 0,
                'failed': 0,
                'delivery_errors': []
            }
            
            # Process recipients in batches
            for i in range(0, len(recipients), self.batch_size):
                batch = recipients[i:i + self.batch_size]
                
                # Process batch
                batch_results = await self._deliver_to_batch(announcement, batch)
                delivery_stats['delivered'] += batch_results['delivered']
                delivery_stats['failed'] += batch_results['failed']
                delivery_stats['delivery_errors'].extend(batch_results['errors'])
                
                # Update progress
                progress = (i + len(batch)) / len(recipients) * 100
                await self._update_delivery_progress(announcement_id, progress, delivery_stats)
                
                # Rate limiting delay
                if i + self.batch_size < len(recipients):
                    await asyncio.sleep(self.rate_limit_delay)
            
            # Mark as completed
            final_status = AnnouncementStatus.SENT.value if delivery_stats['failed'] == 0 else AnnouncementStatus.FAILED.value
            await self._update_announcement_status(announcement_id, final_status)
            
            # Store delivery report
            await self._store_delivery_report(announcement_id, delivery_stats)
            
            logger.info(f"Announcement {announcement_id} delivery completed: {delivery_stats['delivered']} delivered, {delivery_stats['failed']} failed")
            
        except Exception as e:
            logger.error(f"Announcement delivery failed: {e}")
            await self._update_announcement_status(announcement_id, AnnouncementStatus.FAILED.value)
    
    async def _deliver_to_batch(
        self,
        announcement: Dict[str, Any],
        batch: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Deliver announcement to a batch of recipients"""
        batch_stats = {'delivered': 0, 'failed': 0, 'errors': []}
        
        # This would integrate with the actual bot delivery system
        # For now, we'll simulate the delivery and track engagement
        
        for recipient in batch:
            try:
                # Simulate message delivery
                # In real implementation, this would send via Telegram bot
                
                # Track delivery event
                await supabase_client.execute_command(
                    """
                    INSERT INTO announcement_deliveries (
                        announcement_id, recipient_anonymous_id, 
                        delivered_at, status
                    )
                    VALUES ($1, $2, $3, $4)
                    """,
                    announcement['id'], recipient['anonymous_id'],
                    datetime.utcnow().isoformat(), 'delivered'
                )
                
                batch_stats['delivered'] += 1
                
            except Exception as e:
                batch_stats['failed'] += 1
                batch_stats['errors'].append(f"Failed to deliver to {recipient['anonymous_id']}: {str(e)}")
        
        return batch_stats
    
    async def get_announcement_analytics(
        self,
        announcement_id: str,
        requester_anonymous_id: str
    ) -> Dict[str, Any]:
        """Get detailed analytics for announcement performance"""
        try:
            announcement = await self._get_announcement(announcement_id)
            if not announcement:
                return {'error': 'Announcement not found'}
            
            # Permission check
            if announcement['creator_anonymous_id'] != requester_anonymous_id:
                if not await rbac_manager.check_permission(requester_anonymous_id, 'view_analytics'):
                    return {'error': 'Permission denied'}
            
            # Get delivery statistics
            delivery_stats = await supabase_client.execute_query(
                """
                SELECT 
                    status,
                    COUNT(*) as count
                FROM announcement_deliveries
                WHERE announcement_id = $1
                GROUP BY status
                """,
                announcement_id
            )
            
            # Get engagement metrics (if tracking enabled)
            engagement_stats = await supabase_client.execute_query(
                """
                SELECT 
                    event_type,
                    COUNT(*) as count
                FROM analytics_events
                WHERE metadata->>'announcement_id' = $1
                    AND event_type IN ('announcement_opened', 'announcement_clicked', 'announcement_replied')
                GROUP BY event_type
                """,
                announcement_id
            )
            
            # Calculate metrics
            total_delivered = sum(stat['count'] for stat in delivery_stats if stat['status'] == 'delivered')
            total_opened = sum(stat['count'] for stat in engagement_stats if stat['event_type'] == 'announcement_opened')
            
            analytics = {
                'announcement_id': announcement_id,
                'title': announcement['title'],
                'status': announcement['status'],
                'created_at': announcement['created_at'],
                'delivery_stats': {stat['status']: stat['count'] for stat in delivery_stats},
                'engagement_stats': {stat['event_type']: stat['count'] for stat in engagement_stats},
                'performance_metrics': {
                    'delivery_rate': (total_delivered / announcement['estimated_recipients']) * 100 if announcement['estimated_recipients'] > 0 else 0,
                    'open_rate': (total_opened / total_delivered) * 100 if total_delivered > 0 else 0,
                    'total_reach': total_delivered,
                    'engagement_score': self._calculate_engagement_score(engagement_stats)
                },
                'generated_at': datetime.utcnow().isoformat()
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get announcement analytics: {e}")
            return {'error': str(e)}
    
    async def _validate_targeting_rules(self, targeting_rules: Dict[str, Any]) -> Dict[str, Any]:
        """Validate targeting rules before creating announcement"""
        try:
            required_fields = ['target_type']
            
            for field in required_fields:
                if field not in targeting_rules:
                    return {'error': f'Missing required field: {field}'}
            
            target_type = targeting_rules['target_type']
            
            if target_type == 'all_users':
                # No additional validation needed
                pass
            elif target_type == 'role_based':
                if 'roles' not in targeting_rules:
                    return {'error': 'roles field required for role_based targeting'}
            elif target_type == 'segment_based':
                if 'segments' not in targeting_rules:
                    return {'error': 'segments field required for segment_based targeting'}
            elif target_type == 'custom_list':
                if 'anonymous_ids' not in targeting_rules:
                    return {'error': 'anonymous_ids field required for custom_list targeting'}
            else:
                return {'error': f'Invalid target_type: {target_type}'}
            
            return {'valid': True}
            
        except Exception as e:
            return {'error': f'Validation error: {str(e)}'}
    
    async def _estimate_recipients(self, targeting_rules: Dict[str, Any]) -> int:
        """Estimate number of recipients for targeting rules"""
        try:
            target_type = targeting_rules['target_type']
            
            if target_type == 'all_users':
                result = await supabase_client.execute_query("SELECT COUNT(*) as count FROM users")
                return result[0]['count'] if result else 0
            
            elif target_type == 'role_based':
                roles = targeting_rules['roles']
                result = await supabase_client.execute_query(
                    "SELECT COUNT(*) as count FROM users WHERE role = ANY($1)",
                    roles
                )
                return result[0]['count'] if result else 0
            
            elif target_type == 'segment_based':
                # This would use the segmentation logic
                segments = await advanced_user_manager.segment_users(
                    targeting_rules['segments'], 
                    'system'  # System-level operation
                )
                total = 0
                for segment_users in segments.values():
                    total += len(segment_users)
                return total
            
            elif target_type == 'custom_list':
                return len(targeting_rules['anonymous_ids'])
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to estimate recipients: {e}")
            return 0
    
    async def _resolve_targeting_rules(self, targeting_rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Resolve targeting rules to actual user list"""
        try:
            target_type = targeting_rules['target_type']
            recipients = []
            
            if target_type == 'all_users':
                recipients = await supabase_client.execute_query("SELECT * FROM users")
            
            elif target_type == 'role_based':
                roles = targeting_rules['roles']
                recipients = await supabase_client.execute_query(
                    "SELECT * FROM users WHERE role = ANY($1)",
                    roles
                )
            
            elif target_type == 'custom_list':
                anonymous_ids = targeting_rules['anonymous_ids']
                recipients = await supabase_client.execute_query(
                    "SELECT * FROM users WHERE anonymous_id = ANY($1)",
                    anonymous_ids
                )
            
            return recipients
            
        except Exception as e:
            logger.error(f"Failed to resolve targeting rules: {e}")
            return []
    
    # Helper methods
    async def _get_announcement(self, announcement_id: str) -> Optional[Dict[str, Any]]:
        """Get announcement by ID"""
        try:
            result = await supabase_client.execute_query(
                "SELECT * FROM announcements WHERE id = $1",
                announcement_id
            )
            return result[0] if result else None
        except Exception:
            return None
    
    async def _update_announcement_status(self, announcement_id: str, status: str):
        """Update announcement status"""
        await supabase_client.execute_command(
            "UPDATE announcements SET status = $2, updated_at = $3 WHERE id = $1",
            announcement_id, status, datetime.utcnow().isoformat()
        )
    
    async def _update_delivery_progress(self, announcement_id: str, progress: float, stats: Dict):
        """Update delivery progress in real-time"""
        progress_data = {
            'progress_percentage': progress,
            'delivery_stats': stats,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        await redis_state.cache_set(
            f"announcement_progress:{announcement_id}",
            progress_data,
            3600  # Cache for 1 hour
        )
    
    async def _store_delivery_report(self, announcement_id: str, delivery_stats: Dict):
        """Store final delivery report"""
        await supabase_client.execute_command(
            """
            INSERT INTO announcement_reports (
                announcement_id, delivery_stats, generated_at
            )
            VALUES ($1, $2, $3)
            """,
            announcement_id, json.dumps(delivery_stats), datetime.utcnow().isoformat()
        )
    
    def _calculate_engagement_score(self, engagement_stats: List[Dict]) -> float:
        """Calculate overall engagement score"""
        weights = {
            'announcement_opened': 1.0,
            'announcement_clicked': 2.0,
            'announcement_replied': 3.0
        }
        
        total_score = 0
        for stat in engagement_stats:
            event_type = stat['event_type']
            count = stat['count']
            weight = weights.get(event_type, 1.0)
            total_score += count * weight
        
        return total_score

# Global instance
targeted_announcement_manager = TargetedAnnouncementManager()