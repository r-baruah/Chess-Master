"""
Disaster Recovery Integration Service
Coordinates all disaster recovery components and provides unified interface
"""
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import redis.asyncio as redis
from core.supabase_client import SupabaseClient
from core.multi_bot_token_manager import MultiBotTokenManager
from core.disaster_recovery_manager import DisasterRecoveryManager
from core.channel_permission_manager import ChannelPermissionManager
from core.system_health_monitor import SystemHealthMonitor

logger = logging.getLogger(__name__)

class DisasterRecoveryService:
    """Central service for disaster recovery and high availability management"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.supabase_client: Optional[SupabaseClient] = None
        
        # Core components
        self.token_manager: Optional[MultiBotTokenManager] = None
        self.disaster_recovery: Optional[DisasterRecoveryManager] = None
        self.channel_manager: Optional[ChannelPermissionManager] = None
        self.health_monitor: Optional[SystemHealthMonitor] = None
        
        self.initialized = False
        self.background_tasks: List[asyncio.Task] = []
        
    async def initialize(self) -> bool:
        """Initialize disaster recovery service and all components"""
        try:
            logger.info("🚀 Initializing Disaster Recovery Service...")
            
            # Initialize database connections
            await self._initialize_connections()
            
            # Initialize core components
            await self._initialize_components()
            
            # Setup database schemas
            await self._setup_database_schemas()
            
            # Start background services
            await self._start_background_services()
            
            self.initialized = True
            logger.info("✅ Disaster Recovery Service initialized successfully")
            
            # Perform initial health check
            await self.perform_system_health_check()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Disaster Recovery Service: {e}")
            await self.shutdown()
            return False
            
    async def _initialize_connections(self):
        """Initialize database and Redis connections"""
        # Initialize Redis
        redis_config = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'db': int(os.getenv('REDIS_DB', 0)),
            'decode_responses': True
        }
        
        if os.getenv('REDIS_PASSWORD'):
            redis_config['password'] = os.getenv('REDIS_PASSWORD')
            
        self.redis_client = redis.Redis(**redis_config)
        await self.redis_client.ping()
        logger.info("✅ Redis connection established")
        
        # Initialize Supabase
        self.supabase_client = SupabaseClient()
        await self.supabase_client.initialize()
        logger.info("✅ Supabase connection established")
        
    async def _initialize_components(self):
        """Initialize all disaster recovery components"""
        # Token manager
        self.token_manager = MultiBotTokenManager(self.redis_client, self.supabase_client)
        await self.token_manager.initialize_tokens()
        logger.info("✅ Multi-bot token manager initialized")
        
        # Disaster recovery manager
        self.disaster_recovery = DisasterRecoveryManager(self.redis_client, self.supabase_client)
        await self.disaster_recovery.initialize()
        logger.info("✅ Disaster recovery manager initialized")
        
        # Channel permission manager
        self.channel_manager = ChannelPermissionManager(self.redis_client, self.supabase_client)
        await self.channel_manager.initialize()
        logger.info("✅ Channel permission manager initialized")
        
        # System health monitor (pass other components for integration)
        self.health_monitor = SystemHealthMonitor(
            self.redis_client, 
            self.supabase_client,
            self.token_manager,
            self.channel_manager,
            self.disaster_recovery
        )
        await self.health_monitor.initialize()
        logger.info("✅ System health monitor initialized")
        
    async def _setup_database_schemas(self):
        """Setup database schemas for disaster recovery"""
        try:
            # Read and execute schema file
            schema_path = os.path.join(os.path.dirname(__file__), '..', 'database', 'disaster_recovery_schema.sql')
            
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    schema_sql = f.read()
                    
                async with self.supabase_client.get_connection() as conn:
                    # Execute schema in parts (split by semicolon)
                    statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]
                    
                    for statement in statements:
                        try:
                            await conn.execute(statement)
                        except Exception as e:
                            # Log but don't fail on schema errors (might already exist)
                            logger.debug(f"Schema statement info: {e}")
                            
                logger.info("✅ Database schemas initialized")
            else:
                logger.warning("Schema file not found, skipping database setup")
                
        except Exception as e:
            logger.error(f"Failed to setup database schemas: {e}")
            # Don't raise - service can work without perfect schema setup
            
    async def _start_background_services(self):
        """Start background monitoring and maintenance services"""
        # Create background task for periodic recovery package creation
        recovery_task = asyncio.create_task(self._periodic_recovery_package_creation())
        self.background_tasks.append(recovery_task)
        
        # Create background task for cleanup operations
        cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self.background_tasks.append(cleanup_task)
        
        logger.info("✅ Background services started")
        
    async def _periodic_recovery_package_creation(self):
        """Create recovery packages periodically"""
        while True:
            try:
                # Create recovery package every 6 hours
                await asyncio.sleep(6 * 3600)
                
                logger.info("Creating periodic recovery package...")
                package = await self.disaster_recovery.create_recovery_package()
                logger.info(f"Recovery package created: {package['package_id']}")
                
            except Exception as e:
                logger.error(f"Error in periodic recovery package creation: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour on error
                
    async def _periodic_cleanup(self):
        """Perform periodic cleanup operations"""
        while True:
            try:
                # Run cleanup every 24 hours
                await asyncio.sleep(24 * 3600)
                
                logger.info("Running periodic cleanup...")
                await self._cleanup_old_data()
                logger.info("Periodic cleanup completed")
                
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(3600)  # Retry in 1 hour on error
                
    async def _cleanup_old_data(self):
        """Clean up old monitoring data and recovery packages"""
        try:
            async with self.supabase_client.get_connection() as conn:
                # Clean up old health history (keep 7 days)
                await conn.execute("""
                    DELETE FROM system_health_history 
                    WHERE created_at < NOW() - INTERVAL '7 days'
                """)
                
                # Clean up old permission test results (keep 3 days)
                await conn.execute("""
                    DELETE FROM permission_test_results 
                    WHERE created_at < NOW() - INTERVAL '3 days'
                """)
                
                # Clean up expired recovery packages
                await conn.execute("""
                    DELETE FROM recovery_packages 
                    WHERE expires_at IS NOT NULL AND expires_at < NOW()
                """)
                
                # Clean up old failover events (keep 30 days)
                await conn.execute("""
                    DELETE FROM failover_events 
                    WHERE event_time < NOW() - INTERVAL '30 days'
                """)
                
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
            
    # Public API methods
    
    async def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        if not self.initialized:
            return {'status': 'not_initialized', 'message': 'Service not initialized'}
            
        try:
            # Get status from all components
            health_status = await self.health_monitor.get_system_status()
            token_status = await self.token_manager.get_current_status()
            permission_status = await self.channel_manager.get_permission_status()
            
            return {
                'overall_status': health_status['overall_health']['status'],
                'last_check': health_status['overall_health']['timestamp'],
                'components': {
                    'health_monitor': health_status,
                    'token_manager': token_status,
                    'channel_permissions': permission_status
                },
                'service_initialized': self.initialized,
                'background_tasks_running': len([t for t in self.background_tasks if not t.done()])
            }
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def perform_system_health_check(self) -> Dict:
        """Perform immediate comprehensive system health check"""
        if not self.health_monitor:
            return {'status': 'error', 'message': 'Health monitor not initialized'}
            
        try:
            logger.info("🔍 Performing comprehensive system health check...")
            health_status = await self.health_monitor.force_health_check()
            
            # Also perform permission check
            if self.channel_manager and self.token_manager:
                sync_results = await self.channel_manager.synchronize_permissions(self.token_manager)
                health_status['permission_sync'] = sync_results
                
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def create_recovery_package(self) -> Dict:
        """Create emergency recovery package"""
        if not self.disaster_recovery:
            return {'status': 'error', 'message': 'Disaster recovery manager not initialized'}
            
        try:
            logger.info("📦 Creating emergency recovery package...")
            package = await self.disaster_recovery.create_recovery_package()
            return {'status': 'success', 'package': package}
            
        except Exception as e:
            logger.error(f"Failed to create recovery package: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def execute_emergency_recovery(self, recovery_package: Dict) -> Dict:
        """Execute emergency recovery from package"""
        if not self.disaster_recovery:
            return {'status': 'error', 'message': 'Disaster recovery manager not initialized'}
            
        try:
            logger.info("🚨 Executing emergency recovery...")
            success = await self.disaster_recovery.execute_emergency_recovery(recovery_package)
            
            if success:
                # Reinitialize components after recovery
                await self._initialize_components()
                return {'status': 'success', 'message': 'Emergency recovery completed successfully'}
            else:
                return {'status': 'error', 'message': 'Emergency recovery failed'}
                
        except Exception as e:
            logger.error(f"Emergency recovery execution failed: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def trigger_bot_failover(self) -> Dict:
        """Manually trigger bot token failover"""
        if not self.token_manager:
            return {'status': 'error', 'message': 'Token manager not initialized'}
            
        try:
            logger.info("🔄 Triggering manual bot failover...")
            success = await self.token_manager.failover_to_backup_token()
            
            if success:
                return {'status': 'success', 'message': 'Bot failover completed successfully'}
            else:
                return {'status': 'error', 'message': 'Bot failover failed - no healthy backup tokens available'}
                
        except Exception as e:
            logger.error(f"Manual failover failed: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def sync_channel_permissions(self) -> Dict:
        """Manually synchronize channel permissions across all tokens"""
        if not self.channel_manager or not self.token_manager:
            return {'status': 'error', 'message': 'Channel or token manager not initialized'}
            
        try:
            logger.info("🔧 Synchronizing channel permissions...")
            sync_results = await self.channel_manager.synchronize_permissions(self.token_manager)
            return {'status': 'success', 'sync_results': sync_results}
            
        except Exception as e:
            logger.error(f"Permission sync failed: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def get_recent_events(self, hours: int = 24) -> Dict:
        """Get recent system events and alerts"""
        try:
            events = {
                'health_events': [],
                'failover_events': [],
                'permission_events': [],
                'recovery_events': []
            }
            
            # Get from database
            async with self.supabase_client.get_connection() as conn:
                # Recent failover events
                failover_events = await conn.fetch("""
                    SELECT * FROM failover_events 
                    WHERE event_time > NOW() - INTERVAL '%s hours'
                    ORDER BY event_time DESC
                    LIMIT 50
                """, hours)
                
                events['failover_events'] = [dict(row) for row in failover_events]
                
                # Recent health status changes
                health_events = await conn.fetch("""
                    SELECT * FROM system_health_history 
                    WHERE check_time > NOW() - INTERVAL '%s hours'
                    AND (overall_status = 'critical' OR overall_status = 'degraded')
                    ORDER BY check_time DESC
                    LIMIT 50
                """, hours)
                
                events['health_events'] = [dict(row) for row in health_events]
                
            # Get from Redis
            notifications = await self.redis_client.lrange('admin_notifications', 0, 49)
            events['recent_notifications'] = [json.loads(notif) for notif in notifications]
            
            return {'status': 'success', 'events': events}
            
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def get_performance_metrics(self) -> Dict:
        """Get system performance metrics and statistics"""
        try:
            metrics = {}
            
            async with self.supabase_client.get_connection() as conn:
                # System uptime and availability
                uptime_data = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_checks,
                        COUNT(*) FILTER (WHERE overall_status = 'healthy') as healthy_checks,
                        COUNT(*) FILTER (WHERE overall_status = 'degraded') as degraded_checks,
                        COUNT(*) FILTER (WHERE overall_status = 'critical') as critical_checks
                    FROM system_health_history 
                    WHERE check_time > NOW() - INTERVAL '24 hours'
                """)
                
                if uptime_data:
                    total = uptime_data['total_checks']
                    if total > 0:
                        metrics['availability_24h'] = {
                            'healthy_percentage': (uptime_data['healthy_checks'] / total) * 100,
                            'degraded_percentage': (uptime_data['degraded_checks'] / total) * 100,
                            'critical_percentage': (uptime_data['critical_checks'] / total) * 100
                        }
                        
                # Failover statistics
                failover_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_failovers,
                        COUNT(*) FILTER (WHERE success = true) as successful_failovers,
                        AVG(recovery_time_seconds) FILTER (WHERE success = true) as avg_recovery_time
                    FROM failover_events 
                    WHERE event_time > NOW() - INTERVAL '7 days'
                """)
                
                if failover_stats:
                    metrics['failover_stats_7d'] = dict(failover_stats)
                    
                # Bot token health
                token_health = await conn.fetchrow("""
                    SELECT * FROM bot_tokens_health_summary
                """)
                
                if token_health:
                    metrics['token_health'] = dict(token_health)
                    
            return {'status': 'success', 'metrics': metrics}
            
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {'status': 'error', 'message': str(e)}
            
    async def shutdown(self):
        """Shutdown disaster recovery service and all components"""
        logger.info("🛑 Shutting down Disaster Recovery Service...")
        
        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
            
        # Wait for tasks to complete cancellation
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
        # Shutdown components
        if self.health_monitor:
            await self.health_monitor.shutdown()
            
        if self.token_manager:
            await self.token_manager.shutdown()
            
        if self.channel_manager:
            await self.channel_manager.shutdown()
            
        # Close connections
        if self.redis_client:
            await self.redis_client.close()
            
        if self.supabase_client:
            await self.supabase_client.close()
            
        self.initialized = False
        logger.info("✅ Disaster Recovery Service shutdown complete")

# Global instance
disaster_recovery_service = DisasterRecoveryService()

async def get_disaster_recovery_service() -> DisasterRecoveryService:
    """Get the global disaster recovery service instance"""
    if not disaster_recovery_service.initialized:
        await disaster_recovery_service.initialize()
    return disaster_recovery_service