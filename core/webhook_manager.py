"""
Webhook System for External Integrations and Event-Driven Architecture
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import json
import aiohttp
import hashlib
import hmac
from dataclasses import dataclass
from enum import Enum
import uuid

from core.supabase_client import supabase_client
from core.redis_state import redis_state
from core.analytics_engine import analytics_engine

logger = logging.getLogger(__name__)

class WebhookEvent(Enum):
    """Supported webhook events"""
    COURSE_UPLOADED = "course.uploaded"
    COURSE_APPROVED = "course.approved" 
    COURSE_REJECTED = "course.rejected"
    USER_REGISTERED = "user.registered"
    USER_ROLE_CHANGED = "user.role_changed"
    ANNOUNCEMENT_SENT = "announcement.sent"
    REVIEW_COMPLETED = "review.completed"
    SYSTEM_ALERT = "system.alert"
    COMMUNITY_MILESTONE = "community.milestone"

@dataclass
class WebhookEndpoint:
    """Webhook endpoint configuration"""
    id: str
    url: str
    events: List[str]
    secret: str
    active: bool = True
    retry_count: int = 3
    timeout: int = 30
    headers: Dict[str, str] = None
    filters: Dict[str, Any] = None
    created_by: str = ""
    created_at: datetime = None

class WebhookManager:
    """Manages webhook endpoints and event delivery"""
    
    def __init__(self):
        self.endpoints: Dict[str, WebhookEndpoint] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.delivery_queue = "webhook_deliveries"
        self.retry_queue = "webhook_retries"
        self.max_retry_attempts = 3
        self.retry_delays = [60, 300, 900]  # 1min, 5min, 15min
    
    async def register_endpoint(
        self, 
        url: str, 
        events: List[str], 
        secret: str = None,
        creator_anonymous_id: str = None,
        filters: Dict[str, Any] = None,
        headers: Dict[str, str] = None
    ) -> str:
        """Register new webhook endpoint"""
        try:
            endpoint_id = str(uuid.uuid4())
            
            # Generate secret if not provided
            if not secret:
                secret = hashlib.sha256(f"{endpoint_id}{datetime.utcnow()}".encode()).hexdigest()
            
            endpoint = WebhookEndpoint(
                id=endpoint_id,
                url=url,
                events=events,
                secret=secret,
                headers=headers or {},
                filters=filters or {},
                created_by=creator_anonymous_id or "system",
                created_at=datetime.utcnow()
            )
            
            # Store in database
            await supabase_client.execute_command(
                """
                INSERT INTO webhook_endpoints (
                    id, url, events, secret, active, retry_count, timeout,
                    headers, filters, created_by, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                endpoint_id, url, json.dumps(events), secret, True, 3, 30,
                json.dumps(headers or {}), json.dumps(filters or {}),
                creator_anonymous_id or "system", datetime.utcnow().isoformat()
            )
            
            # Cache endpoint
            self.endpoints[endpoint_id] = endpoint
            
            logger.info(f"Registered webhook endpoint {endpoint_id} for events: {events}")
            return endpoint_id
            
        except Exception as e:
            logger.error(f"Failed to register webhook endpoint: {e}")
            raise
    
    async def unregister_endpoint(self, endpoint_id: str, requester_anonymous_id: str = None) -> bool:
        """Unregister webhook endpoint"""
        try:
            # Check if endpoint exists and user has permission
            endpoint = await self._get_endpoint(endpoint_id)
            if not endpoint:
                return False
            
            if requester_anonymous_id and endpoint.created_by != requester_anonymous_id:
                # Check if user has admin permissions
                from core.roles import rbac_manager
                if not await rbac_manager.check_permission(requester_anonymous_id, 'system_admin'):
                    return False
            
            # Deactivate endpoint
            await supabase_client.execute_command(
                "UPDATE webhook_endpoints SET active = false WHERE id = $1",
                endpoint_id
            )
            
            # Remove from cache
            if endpoint_id in self.endpoints:
                del self.endpoints[endpoint_id]
            
            logger.info(f"Unregistered webhook endpoint {endpoint_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister webhook endpoint: {e}")
            return False
    
    async def trigger_event(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        source: str = "system"
    ) -> Dict[str, Any]:
        """Trigger webhook event for all registered endpoints"""
        try:
            if not isinstance(event_type, str):
                event_type = event_type.value if hasattr(event_type, 'value') else str(event_type)
            
            event_id = str(uuid.uuid4())
            event_data = {
                'id': event_id,
                'event': event_type,
                'data': data,
                'source': source,
                'timestamp': datetime.utcnow().isoformat(),
                'version': '1.0'
            }
            
            # Get matching endpoints
            matching_endpoints = await self._get_matching_endpoints(event_type, data)
            
            delivery_results = {
                'event_id': event_id,
                'event_type': event_type,
                'endpoints_matched': len(matching_endpoints),
                'deliveries_queued': 0,
                'deliveries_failed': 0
            }
            
            # Queue deliveries
            for endpoint in matching_endpoints:
                try:
                    delivery_task = {
                        'delivery_id': str(uuid.uuid4()),
                        'event_id': event_id,
                        'endpoint_id': endpoint.id,
                        'event_data': event_data,
                        'attempt': 1,
                        'max_attempts': endpoint.retry_count,
                        'created_at': datetime.utcnow().isoformat()
                    }
                    
                    await redis_state.queue_push(self.delivery_queue, delivery_task)
                    delivery_results['deliveries_queued'] += 1
                    
                except Exception as e:
                    logger.error(f"Failed to queue delivery for endpoint {endpoint.id}: {e}")
                    delivery_results['deliveries_failed'] += 1
            
            # Store event
            await supabase_client.execute_command(
                """
                INSERT INTO webhook_events (
                    id, event_type, event_data, source, created_at,
                    endpoints_matched, deliveries_queued
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                event_id, event_type, json.dumps(event_data), source,
                datetime.utcnow().isoformat(), delivery_results['endpoints_matched'],
                delivery_results['deliveries_queued']
            )
            
            # Track analytics event
            await analytics_engine.track_event(
                'system', 'webhook_triggered',
                {'event_type': event_type, 'endpoints': len(matching_endpoints)}
            )
            
            logger.info(f"Triggered webhook event {event_type} for {len(matching_endpoints)} endpoints")
            return delivery_results
            
        except Exception as e:
            logger.error(f"Failed to trigger webhook event: {e}")
            return {'error': str(e)}
    
    async def process_delivery_queue(self):
        """Background task to process webhook deliveries"""
        while True:
            try:
                # Get delivery task from queue
                delivery_task = await redis_state.queue_pop(self.delivery_queue)
                if not delivery_task:
                    await asyncio.sleep(1)
                    continue
                
                # Process delivery
                await self._deliver_webhook(delivery_task)
                
            except Exception as e:
                logger.error(f"Webhook delivery processing error: {e}")
                await asyncio.sleep(5)
    
    async def _deliver_webhook(self, delivery_task: Dict[str, Any]):
        """Deliver webhook to endpoint"""
        try:
            endpoint = await self._get_endpoint(delivery_task['endpoint_id'])
            if not endpoint or not endpoint.active:
                logger.warning(f"Endpoint {delivery_task['endpoint_id']} not found or inactive")
                return
            
            event_data = delivery_task['event_data']
            
            # Create signature for verification
            signature = self._create_signature(json.dumps(event_data), endpoint.secret)
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'X-Webhook-Signature': signature,
                'X-Webhook-Event': event_data['event'],
                'X-Webhook-Delivery': delivery_task['delivery_id'],
                'User-Agent': 'ChessMaster-Webhooks/1.0'
            }
            headers.update(endpoint.headers)
            
            # Make HTTP request
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=endpoint.timeout)) as session:
                start_time = datetime.utcnow()
                
                async with session.post(
                    endpoint.url,
                    json=event_data,
                    headers=headers
                ) as response:
                    end_time = datetime.utcnow()
                    response_time = (end_time - start_time).total_seconds()
                    
                    success = 200 <= response.status < 300
                    response_body = await response.text()
                    
                    # Store delivery result
                    await self._store_delivery_result(
                        delivery_task, endpoint, success, response.status,
                        response_body, response_time
                    )
                    
                    if success:
                        logger.info(f"Webhook delivered successfully to {endpoint.url}")
                    else:
                        logger.warning(f"Webhook delivery failed to {endpoint.url}: {response.status}")
                        await self._handle_delivery_failure(delivery_task, endpoint)
        
        except asyncio.TimeoutError:
            logger.warning(f"Webhook delivery timeout to endpoint {delivery_task['endpoint_id']}")
            await self._handle_delivery_failure(delivery_task, endpoint, "timeout")
        except Exception as e:
            logger.error(f"Webhook delivery error: {e}")
            await self._handle_delivery_failure(delivery_task, endpoint, str(e))
    
    async def _handle_delivery_failure(
        self, 
        delivery_task: Dict[str, Any], 
        endpoint: WebhookEndpoint, 
        error: str = None
    ):
        """Handle failed webhook delivery with retry logic"""
        try:
            attempt = delivery_task.get('attempt', 1)
            
            if attempt < endpoint.retry_count:
                # Schedule retry
                retry_delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
                retry_task = delivery_task.copy()
                retry_task['attempt'] = attempt + 1
                retry_task['retry_after'] = (datetime.utcnow() + timedelta(seconds=retry_delay)).isoformat()
                retry_task['last_error'] = error
                
                await redis_state.queue_push(self.retry_queue, retry_task)
                logger.info(f"Scheduled webhook retry {attempt + 1} for endpoint {endpoint.id}")
            else:
                # Max retries reached
                logger.error(f"Webhook delivery failed permanently for endpoint {endpoint.id}")
                
                # Store permanent failure
                await supabase_client.execute_command(
                    """
                    INSERT INTO webhook_delivery_failures (
                        delivery_id, endpoint_id, event_id, 
                        final_error, attempts, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    delivery_task['delivery_id'], endpoint.id, delivery_task['event_id'],
                    error or "Unknown error", attempt, datetime.utcnow().isoformat()
                )
                
        except Exception as e:
            logger.error(f"Error handling delivery failure: {e}")
    
    async def get_webhook_analytics(
        self, 
        endpoint_id: str = None, 
        timeframe: str = '24h',
        requester_anonymous_id: str = None
    ) -> Dict[str, Any]:
        """Get webhook delivery analytics"""
        try:
            # Permission check
            from core.roles import rbac_manager
            if requester_anonymous_id and not await rbac_manager.check_permission(requester_anonymous_id, 'view_analytics'):
                return {'error': 'Permission denied'}
            
            hours = 24 if timeframe == '24h' else 168 if timeframe == '7d' else 24
            start_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            
            # Base query conditions
            where_conditions = ["created_at >= $1"]
            params = [start_time]
            
            if endpoint_id:
                where_conditions.append("endpoint_id = $2")
                params.append(endpoint_id)
            
            where_clause = " AND ".join(where_conditions)
            
            # Get delivery statistics
            delivery_stats = await supabase_client.execute_query(
                f"""
                SELECT 
                    COUNT(*) as total_deliveries,
                    COUNT(CASE WHEN success = true THEN 1 END) as successful_deliveries,
                    COUNT(CASE WHEN success = false THEN 1 END) as failed_deliveries,
                    AVG(response_time_ms) as avg_response_time,
                    MAX(response_time_ms) as max_response_time
                FROM webhook_deliveries
                WHERE {where_clause}
                """,
                *params
            )
            
            # Get event type distribution
            event_stats = await supabase_client.execute_query(
                f"""
                SELECT 
                    event_type,
                    COUNT(*) as event_count
                FROM webhook_events
                WHERE created_at >= $1
                GROUP BY event_type
                ORDER BY event_count DESC
                """,
                start_time
            )
            
            # Get endpoint performance (if not filtered by endpoint)
            endpoint_stats = []
            if not endpoint_id:
                endpoint_stats = await supabase_client.execute_query(
                    f"""
                    SELECT 
                        we.id,
                        we.url,
                        COUNT(wd.id) as deliveries,
                        COUNT(CASE WHEN wd.success = true THEN 1 END) as successful,
                        AVG(wd.response_time_ms) as avg_response_time
                    FROM webhook_endpoints we
                    LEFT JOIN webhook_deliveries wd ON we.id = wd.endpoint_id 
                        AND wd.created_at >= $1
                    WHERE we.active = true
                    GROUP BY we.id, we.url
                    ORDER BY deliveries DESC
                    """,
                    start_time
                )
            
            analytics = {
                'timeframe': timeframe,
                'delivery_summary': delivery_stats[0] if delivery_stats else {},
                'event_distribution': event_stats or [],
                'endpoint_performance': endpoint_stats,
                'generated_at': datetime.utcnow().isoformat()
            }
            
            return analytics
            
        except Exception as e:
            logger.error(f"Failed to get webhook analytics: {e}")
            return {'error': str(e)}
    
    # Helper methods
    async def _get_endpoint(self, endpoint_id: str) -> Optional[WebhookEndpoint]:
        """Get webhook endpoint by ID"""
        if endpoint_id in self.endpoints:
            return self.endpoints[endpoint_id]
        
        try:
            result = await supabase_client.execute_query(
                "SELECT * FROM webhook_endpoints WHERE id = $1 AND active = true",
                endpoint_id
            )
            
            if result:
                endpoint_data = result[0]
                endpoint = WebhookEndpoint(
                    id=endpoint_data['id'],
                    url=endpoint_data['url'],
                    events=json.loads(endpoint_data['events']),
                    secret=endpoint_data['secret'],
                    active=endpoint_data['active'],
                    retry_count=endpoint_data.get('retry_count', 3),
                    timeout=endpoint_data.get('timeout', 30),
                    headers=json.loads(endpoint_data.get('headers', '{}')),
                    filters=json.loads(endpoint_data.get('filters', '{}')),
                    created_by=endpoint_data['created_by']
                )
                
                self.endpoints[endpoint_id] = endpoint
                return endpoint
            
        except Exception as e:
            logger.error(f"Failed to get endpoint {endpoint_id}: {e}")
        
        return None
    
    async def _get_matching_endpoints(self, event_type: str, data: Dict[str, Any]) -> List[WebhookEndpoint]:
        """Get endpoints that match the event type and filters"""
        try:
            # Get all active endpoints that listen for this event type
            results = await supabase_client.execute_query(
                """
                SELECT * FROM webhook_endpoints 
                WHERE active = true AND events::jsonb ? $1
                """,
                event_type
            )
            
            matching_endpoints = []
            
            for endpoint_data in results:
                endpoint = WebhookEndpoint(
                    id=endpoint_data['id'],
                    url=endpoint_data['url'],
                    events=json.loads(endpoint_data['events']),
                    secret=endpoint_data['secret'],
                    active=endpoint_data['active'],
                    retry_count=endpoint_data.get('retry_count', 3),
                    timeout=endpoint_data.get('timeout', 30),
                    headers=json.loads(endpoint_data.get('headers', '{}')),
                    filters=json.loads(endpoint_data.get('filters', '{}')),
                    created_by=endpoint_data['created_by']
                )
                
                # Check if data matches endpoint filters
                if self._matches_filters(data, endpoint.filters):
                    matching_endpoints.append(endpoint)
                    self.endpoints[endpoint.id] = endpoint
            
            return matching_endpoints
            
        except Exception as e:
            logger.error(f"Failed to get matching endpoints: {e}")
            return []
    
    def _matches_filters(self, data: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if event data matches endpoint filters"""
        if not filters:
            return True
        
        try:
            for filter_key, filter_value in filters.items():
                data_value = data.get(filter_key)
                
                if isinstance(filter_value, list):
                    if data_value not in filter_value:
                        return False
                elif isinstance(filter_value, dict):
                    # Complex filter matching (e.g., ranges, patterns)
                    if 'min' in filter_value and data_value < filter_value['min']:
                        return False
                    if 'max' in filter_value and data_value > filter_value['max']:
                        return False
                else:
                    if data_value != filter_value:
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Filter matching error: {e}")
            return False
    
    def _create_signature(self, payload: str, secret: str) -> str:
        """Create HMAC signature for webhook verification"""
        return hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _store_delivery_result(
        self,
        delivery_task: Dict[str, Any],
        endpoint: WebhookEndpoint,
        success: bool,
        status_code: int,
        response_body: str,
        response_time: float
    ):
        """Store webhook delivery result"""
        try:
            await supabase_client.execute_command(
                """
                INSERT INTO webhook_deliveries (
                    id, event_id, endpoint_id, success, status_code,
                    response_body, response_time_ms, attempt, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                delivery_task['delivery_id'], delivery_task['event_id'],
                endpoint.id, success, status_code, response_body[:1000],  # Limit response body
                int(response_time * 1000), delivery_task.get('attempt', 1),
                datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Failed to store delivery result: {e}")

# Global webhook manager
webhook_manager = WebhookManager()

# Convenience functions for common events
async def trigger_course_uploaded(course_data: Dict[str, Any]):
    """Trigger course uploaded webhook event"""
    return await webhook_manager.trigger_event(
        WebhookEvent.COURSE_UPLOADED,
        {
            'course_id': course_data.get('id'),
            'title': course_data.get('title'),
            'category': course_data.get('category'),
            'contributor': course_data.get('anonymous_contributor'),
            'uploaded_at': course_data.get('created_at')
        },
        'course_system'
    )

async def trigger_user_registered(user_data: Dict[str, Any]):
    """Trigger user registered webhook event"""
    return await webhook_manager.trigger_event(
        WebhookEvent.USER_REGISTERED,
        {
            'user_id': user_data.get('anonymous_id'),
            'role': user_data.get('role'),
            'registered_at': user_data.get('created_at')
        },
        'user_system'
    )

async def trigger_announcement_sent(announcement_data: Dict[str, Any]):
    """Trigger announcement sent webhook event"""
    return await webhook_manager.trigger_event(
        WebhookEvent.ANNOUNCEMENT_SENT,
        {
            'announcement_id': announcement_data.get('id'),
            'title': announcement_data.get('title'),
            'recipient_count': announcement_data.get('actual_recipients', 0),
            'sent_at': announcement_data.get('sent_at')
        },
        'announcement_system'
    )