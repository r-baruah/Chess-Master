"""
System Health Monitor for comprehensive health monitoring and failover triggers
Monitors all system components and triggers automatic recovery procedures
"""
import os
import json
import asyncio
import logging
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import redis.asyncio as redis
from core.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

@dataclass
class HealthMetric:
    """Health metric structure"""
    component: str
    metric_name: str
    value: Any
    status: HealthStatus
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    timestamp: Optional[str] = None
    message: Optional[str] = None

@dataclass
class ComponentHealth:
    """Component health status"""
    component: str
    status: HealthStatus
    metrics: List[HealthMetric]
    last_check: str
    error_count: int = 0
    last_error: Optional[str] = None

class SystemHealthMonitor:
    """Comprehensive system health monitoring and failover management"""
    
    def __init__(self, redis_client: redis.Redis, supabase_client: SupabaseClient, 
                 token_manager=None, channel_manager=None, disaster_recovery=None):
        self.redis = redis_client
        self.supabase = supabase_client
        self.token_manager = token_manager
        self.channel_manager = channel_manager
        self.disaster_recovery = disaster_recovery
        
        self.health_metrics: Dict[str, ComponentHealth] = {}
        self.monitoring_interval = 30  # seconds
        self.monitoring_task: Optional[asyncio.Task] = None
        self.failover_cooldown = 300  # 5 minutes between failovers
        self.last_failover_time: Optional[datetime] = None
        
        # Health thresholds
        self.thresholds = {
            'cpu_usage': {'warning': 80.0, 'critical': 95.0},
            'memory_usage': {'warning': 85.0, 'critical': 95.0},
            'disk_usage': {'warning': 90.0, 'critical': 98.0},
            'response_time': {'warning': 5.0, 'critical': 10.0},
            'error_rate': {'warning': 5.0, 'critical': 15.0}
        }
        
        # Emergency procedures
        self.emergency_procedures: List[Callable] = []
        
    async def initialize(self) -> bool:
        """Initialize system health monitor"""
        try:
            # Register emergency procedures
            self._register_emergency_procedures()
            
            # Start health monitoring
            self.monitoring_task = asyncio.create_task(self._health_monitoring_loop())
            
            logger.info("System health monitor initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize health monitor: {e}")
            return False
            
    def _register_emergency_procedures(self):
        """Register emergency procedures for different failure scenarios"""
        self.emergency_procedures = [
            self._handle_bot_token_failure,
            self._handle_database_failure,
            self._handle_redis_failure,
            self._handle_channel_access_failure,
            self._handle_system_resource_failure
        ]
        
    async def _health_monitoring_loop(self):
        """Main health monitoring loop"""
        while True:
            try:
                logger.debug("Performing system health check")
                
                # Check all system components
                await self._check_bot_health()
                await self._check_database_health()
                await self._check_redis_health()
                await self._check_channel_health()
                await self._check_system_resources()
                
                # Calculate overall system health
                overall_health = self._calculate_overall_health()
                
                # Update health metrics
                await self._update_health_metrics(overall_health)
                
                # Check if emergency procedures are needed
                if overall_health['status'] == HealthStatus.CRITICAL.value:
                    await self._trigger_emergency_procedures(overall_health)
                elif overall_health['status'] == HealthStatus.DEGRADED.value:
                    await self._handle_degraded_performance(overall_health)
                    
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.monitoring_interval)
                
    async def _check_bot_health(self):
        """Check bot token health"""
        try:
            metrics = []
            
            if self.token_manager:
                # Get token manager status
                status = await self.token_manager.get_current_status()
                
                # Check active token health
                if status['active_token']['status']:
                    token_status = status['active_token']['status']
                    health_status = HealthStatus.HEALTHY if token_status == 'healthy' else HealthStatus.CRITICAL
                    
                    metrics.append(HealthMetric(
                        component='bot',
                        metric_name='active_token_status',
                        value=token_status,
                        status=health_status,
                        timestamp=datetime.utcnow().isoformat(),
                        message=f"Active bot status: {token_status}"
                    ))
                    
                # Check backup token availability
                backup_count = status['backup_tokens_count']
                backup_healthy = status['backup_tokens_healthy']
                
                backup_ratio = (backup_healthy / backup_count) if backup_count > 0 else 0
                backup_status = HealthStatus.HEALTHY if backup_ratio >= 0.8 else \
                              HealthStatus.DEGRADED if backup_ratio >= 0.5 else HealthStatus.CRITICAL
                              
                metrics.append(HealthMetric(
                    component='bot',
                    metric_name='backup_tokens_health',
                    value=backup_ratio * 100,
                    status=backup_status,
                    threshold_warning=50.0,
                    threshold_critical=20.0,
                    timestamp=datetime.utcnow().isoformat(),
                    message=f"{backup_healthy}/{backup_count} backup tokens healthy"
                ))
                
                # Check error count
                error_count = status['active_token']['error_count']
                error_status = HealthStatus.HEALTHY if error_count == 0 else \
                              HealthStatus.DEGRADED if error_count < 3 else HealthStatus.CRITICAL
                              
                metrics.append(HealthMetric(
                    component='bot',
                    metric_name='error_count',
                    value=error_count,
                    status=error_status,
                    threshold_warning=3,
                    threshold_critical=5,
                    timestamp=datetime.utcnow().isoformat()
                ))
                
            # Calculate overall bot health
            overall_status = self._calculate_component_status(metrics)
            
            self.health_metrics['bot'] = ComponentHealth(
                component='bot',
                status=overall_status,
                metrics=metrics,
                last_check=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Bot health check failed: {e}")
            self.health_metrics['bot'] = ComponentHealth(
                component='bot',
                status=HealthStatus.UNKNOWN,
                metrics=[],
                last_check=datetime.utcnow().isoformat(),
                error_count=self.health_metrics.get('bot', ComponentHealth('bot', HealthStatus.UNKNOWN, [], '')).error_count + 1,
                last_error=str(e)
            )
            
    async def _check_database_health(self):
        """Check database connectivity and performance"""
        try:
            metrics = []
            
            # Test connection and response time
            start_time = datetime.utcnow()
            async with self.supabase.get_connection() as conn:
                result = await conn.fetchrow("SELECT NOW() as current_time, version() as version")
                
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            # Response time metric
            response_status = HealthStatus.HEALTHY if response_time < self.thresholds['response_time']['warning'] else \
                            HealthStatus.DEGRADED if response_time < self.thresholds['response_time']['critical'] else \
                            HealthStatus.CRITICAL
                            
            metrics.append(HealthMetric(
                component='database',
                metric_name='response_time',
                value=response_time,
                status=response_status,
                threshold_warning=self.thresholds['response_time']['warning'],
                threshold_critical=self.thresholds['response_time']['critical'],
                timestamp=datetime.utcnow().isoformat(),
                message=f"Database response time: {response_time:.2f}s"
            ))
            
            # Check connection pool status
            if hasattr(self.supabase, 'pool') and self.supabase.pool:
                pool = self.supabase.pool
                
                # Connection pool metrics
                pool_size = pool.get_size()
                pool_free = pool.get_idle_size()
                pool_usage = ((pool_size - pool_free) / pool_size) * 100 if pool_size > 0 else 0
                
                pool_status = HealthStatus.HEALTHY if pool_usage < 80 else \
                            HealthStatus.DEGRADED if pool_usage < 95 else HealthStatus.CRITICAL
                            
                metrics.append(HealthMetric(
                    component='database',
                    metric_name='connection_pool_usage',
                    value=pool_usage,
                    status=pool_status,
                    threshold_warning=80.0,
                    threshold_critical=95.0,
                    timestamp=datetime.utcnow().isoformat(),
                    message=f"Connection pool: {pool_size - pool_free}/{pool_size} active"
                ))
                
            overall_status = self._calculate_component_status(metrics)
            
            self.health_metrics['database'] = ComponentHealth(
                component='database',
                status=overall_status,
                metrics=metrics,
                last_check=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            self.health_metrics['database'] = ComponentHealth(
                component='database',
                status=HealthStatus.CRITICAL,
                metrics=[],
                last_check=datetime.utcnow().isoformat(),
                error_count=self.health_metrics.get('database', ComponentHealth('database', HealthStatus.UNKNOWN, [], '')).error_count + 1,
                last_error=str(e)
            )
            
    async def _check_redis_health(self):
        """Check Redis connectivity and performance"""
        try:
            metrics = []
            
            # Test connection and response time
            start_time = datetime.utcnow()
            await self.redis.ping()
            response_time = (datetime.utcnow() - start_time).total_seconds()
            
            response_status = HealthStatus.HEALTHY if response_time < 1.0 else \
                            HealthStatus.DEGRADED if response_time < 3.0 else HealthStatus.CRITICAL
                            
            metrics.append(HealthMetric(
                component='redis',
                metric_name='response_time',
                value=response_time,
                status=response_status,
                threshold_warning=1.0,
                threshold_critical=3.0,
                timestamp=datetime.utcnow().isoformat(),
                message=f"Redis response time: {response_time:.3f}s"
            ))
            
            # Check Redis info
            redis_info = await self.redis.info()
            
            # Memory usage
            used_memory = redis_info.get('used_memory', 0)
            max_memory = redis_info.get('maxmemory', 0)
            
            if max_memory > 0:
                memory_usage = (used_memory / max_memory) * 100
                memory_status = HealthStatus.HEALTHY if memory_usage < 80 else \
                              HealthStatus.DEGRADED if memory_usage < 95 else HealthStatus.CRITICAL
                              
                metrics.append(HealthMetric(
                    component='redis',
                    metric_name='memory_usage',
                    value=memory_usage,
                    status=memory_status,
                    threshold_warning=80.0,
                    threshold_critical=95.0,
                    timestamp=datetime.utcnow().isoformat(),
                    message=f"Redis memory usage: {memory_usage:.1f}%"
                ))
                
            # Connected clients
            connected_clients = redis_info.get('connected_clients', 0)
            max_clients = redis_info.get('maxclients', 10000)
            
            client_usage = (connected_clients / max_clients) * 100
            client_status = HealthStatus.HEALTHY if client_usage < 70 else \
                          HealthStatus.DEGRADED if client_usage < 90 else HealthStatus.CRITICAL
                          
            metrics.append(HealthMetric(
                component='redis',
                metric_name='client_connections',
                value=client_usage,
                status=client_status,
                threshold_warning=70.0,
                threshold_critical=90.0,
                timestamp=datetime.utcnow().isoformat(),
                message=f"Redis clients: {connected_clients}/{max_clients}"
            ))
            
            overall_status = self._calculate_component_status(metrics)
            
            self.health_metrics['redis'] = ComponentHealth(
                component='redis',
                status=overall_status,
                metrics=metrics,
                last_check=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            self.health_metrics['redis'] = ComponentHealth(
                component='redis',
                status=HealthStatus.CRITICAL,
                metrics=[],
                last_check=datetime.utcnow().isoformat(),
                error_count=self.health_metrics.get('redis', ComponentHealth('redis', HealthStatus.UNKNOWN, [], '')).error_count + 1,
                last_error=str(e)
            )
            
    async def _check_channel_health(self):
        """Check channel accessibility and permissions"""
        try:
            metrics = []
            
            if self.channel_manager:
                status = await self.channel_manager.get_permission_status()
                
                # Channel accessibility ratio
                total_channels = status['total_channels']
                verified_channels = status['verified_channels']
                
                if total_channels > 0:
                    accessibility_ratio = (verified_channels / total_channels) * 100
                    accessibility_status = HealthStatus.HEALTHY if accessibility_ratio >= 90 else \
                                         HealthStatus.DEGRADED if accessibility_ratio >= 70 else HealthStatus.CRITICAL
                                         
                    metrics.append(HealthMetric(
                        component='channels',
                        metric_name='accessibility_ratio',
                        value=accessibility_ratio,
                        status=accessibility_status,
                        threshold_warning=70.0,
                        threshold_critical=50.0,
                        timestamp=datetime.utcnow().isoformat(),
                        message=f"Channel accessibility: {verified_channels}/{total_channels} verified"
                    ))
                    
            overall_status = self._calculate_component_status(metrics) if metrics else HealthStatus.UNKNOWN
            
            self.health_metrics['channels'] = ComponentHealth(
                component='channels',
                status=overall_status,
                metrics=metrics,
                last_check=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Channel health check failed: {e}")
            self.health_metrics['channels'] = ComponentHealth(
                component='channels',
                status=HealthStatus.UNKNOWN,
                metrics=[],
                last_check=datetime.utcnow().isoformat(),
                error_count=self.health_metrics.get('channels', ComponentHealth('channels', HealthStatus.UNKNOWN, [], '')).error_count + 1,
                last_error=str(e)
            )
            
    async def _check_system_resources(self):
        """Check system resource usage"""
        try:
            metrics = []
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_status = HealthStatus.HEALTHY if cpu_percent < self.thresholds['cpu_usage']['warning'] else \
                        HealthStatus.DEGRADED if cpu_percent < self.thresholds['cpu_usage']['critical'] else \
                        HealthStatus.CRITICAL
                        
            metrics.append(HealthMetric(
                component='system',
                metric_name='cpu_usage',
                value=cpu_percent,
                status=cpu_status,
                threshold_warning=self.thresholds['cpu_usage']['warning'],
                threshold_critical=self.thresholds['cpu_usage']['critical'],
                timestamp=datetime.utcnow().isoformat(),
                message=f"CPU usage: {cpu_percent:.1f}%"
            ))
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_status = HealthStatus.HEALTHY if memory_percent < self.thresholds['memory_usage']['warning'] else \
                          HealthStatus.DEGRADED if memory_percent < self.thresholds['memory_usage']['critical'] else \
                          HealthStatus.CRITICAL
                          
            metrics.append(HealthMetric(
                component='system',
                metric_name='memory_usage',
                value=memory_percent,
                status=memory_status,
                threshold_warning=self.thresholds['memory_usage']['warning'],
                threshold_critical=self.thresholds['memory_usage']['critical'],
                timestamp=datetime.utcnow().isoformat(),
                message=f"Memory usage: {memory_percent:.1f}%"
            ))
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            disk_status = HealthStatus.HEALTHY if disk_percent < self.thresholds['disk_usage']['warning'] else \
                         HealthStatus.DEGRADED if disk_percent < self.thresholds['disk_usage']['critical'] else \
                         HealthStatus.CRITICAL
                         
            metrics.append(HealthMetric(
                component='system',
                metric_name='disk_usage',
                value=disk_percent,
                status=disk_status,
                threshold_warning=self.thresholds['disk_usage']['warning'],
                threshold_critical=self.thresholds['disk_usage']['critical'],
                timestamp=datetime.utcnow().isoformat(),
                message=f"Disk usage: {disk_percent:.1f}%"
            ))
            
            overall_status = self._calculate_component_status(metrics)
            
            self.health_metrics['system'] = ComponentHealth(
                component='system',
                status=overall_status,
                metrics=metrics,
                last_check=datetime.utcnow().isoformat()
            )
            
        except Exception as e:
            logger.error(f"System resource check failed: {e}")
            self.health_metrics['system'] = ComponentHealth(
                component='system',
                status=HealthStatus.UNKNOWN,
                metrics=[],
                last_check=datetime.utcnow().isoformat(),
                error_count=self.health_metrics.get('system', ComponentHealth('system', HealthStatus.UNKNOWN, [], '')).error_count + 1,
                last_error=str(e)
            )
            
    def _calculate_component_status(self, metrics: List[HealthMetric]) -> HealthStatus:
        """Calculate overall component status from metrics"""
        if not metrics:
            return HealthStatus.UNKNOWN
            
        critical_count = sum(1 for m in metrics if m.status == HealthStatus.CRITICAL)
        degraded_count = sum(1 for m in metrics if m.status == HealthStatus.DEGRADED)
        
        if critical_count > 0:
            return HealthStatus.CRITICAL
        elif degraded_count > 0:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY
            
    def _calculate_overall_health(self) -> Dict:
        """Calculate overall system health"""
        if not self.health_metrics:
            return {
                'status': HealthStatus.UNKNOWN.value,
                'message': 'No health metrics available',
                'timestamp': datetime.utcnow().isoformat()
            }
            
        component_statuses = [component.status for component in self.health_metrics.values()]
        
        critical_components = [name for name, component in self.health_metrics.items() 
                             if component.status == HealthStatus.CRITICAL]
        degraded_components = [name for name, component in self.health_metrics.items() 
                             if component.status == HealthStatus.DEGRADED]
        
        if critical_components:
            status = HealthStatus.CRITICAL
            message = f"Critical issues in components: {', '.join(critical_components)}"
        elif degraded_components:
            status = HealthStatus.DEGRADED  
            message = f"Performance issues in components: {', '.join(degraded_components)}"
        else:
            status = HealthStatus.HEALTHY
            message = "All systems operational"
            
        return {
            'status': status.value,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
            'components': {name: component.status.value for name, component in self.health_metrics.items()},
            'critical_components': critical_components,
            'degraded_components': degraded_components
        }
        
    async def _update_health_metrics(self, overall_health: Dict):
        """Update health metrics in Redis and database"""
        try:
            # Save to Redis
            health_data = {
                'overall_health': overall_health,
                'component_metrics': {
                    name: asdict(component) for name, component in self.health_metrics.items()
                },
                'last_update': datetime.utcnow().isoformat()
            }
            
            await self.redis.setex(
                'system_health',
                300,  # 5 minute TTL
                json.dumps(health_data, default=str)
            )
            
            # Save critical metrics to database
            async with self.supabase.get_connection() as conn:
                await conn.execute("""
                    INSERT INTO system_health_history 
                    (check_time, overall_status, component_data, critical_components, degraded_components)
                    VALUES ($1, $2, $3, $4, $5)
                """, overall_health['timestamp'], overall_health['status'],
                    json.dumps(health_data['component_metrics'], default=str),
                    json.dumps(overall_health['critical_components']),
                    json.dumps(overall_health['degraded_components']))
                    
        except Exception as e:
            logger.error(f"Failed to update health metrics: {e}")
            
    async def _trigger_emergency_procedures(self, overall_health: Dict):
        """Trigger emergency procedures for critical system status"""
        if self._is_failover_on_cooldown():
            logger.warning("Emergency procedures on cooldown, skipping")
            return
            
        logger.critical("🚨 TRIGGERING EMERGENCY PROCEDURES - CRITICAL SYSTEM STATUS")
        
        critical_components = overall_health.get('critical_components', [])
        
        # Execute emergency procedures based on failed components
        for component in critical_components:
            try:
                if component == 'bot' and self.token_manager:
                    await self._handle_bot_token_failure()
                elif component == 'database':
                    await self._handle_database_failure()
                elif component == 'redis':
                    await self._handle_redis_failure()
                elif component == 'channels':
                    await self._handle_channel_access_failure()
                elif component == 'system':
                    await self._handle_system_resource_failure()
                    
            except Exception as e:
                logger.error(f"Emergency procedure failed for {component}: {e}")
                
        # Update failover timestamp
        self.last_failover_time = datetime.utcnow()
        
        # Send critical notifications
        await self._send_critical_notification(overall_health)
        
    async def _handle_degraded_performance(self, overall_health: Dict):
        """Handle degraded performance issues"""
        degraded_components = overall_health.get('degraded_components', [])
        
        logger.warning(f"System performance degraded in components: {degraded_components}")
        
        # Send warning notifications
        await self._send_warning_notification(overall_health)
        
    def _is_failover_on_cooldown(self) -> bool:
        """Check if failover is on cooldown"""
        if not self.last_failover_time:
            return False
            
        return (datetime.utcnow() - self.last_failover_time).total_seconds() < self.failover_cooldown
        
    async def _handle_bot_token_failure(self):
        """Handle bot token failure"""
        try:
            logger.error("Handling bot token failure - initiating failover")
            
            if self.token_manager:
                success = await self.token_manager.failover_to_backup_token()
                if success:
                    logger.info("✅ Bot token failover completed successfully")
                else:
                    logger.error("❌ Bot token failover failed")
                    
        except Exception as e:
            logger.error(f"Bot token failure handler error: {e}")
            
    async def _handle_database_failure(self):
        """Handle database connectivity failure"""
        try:
            logger.error("Handling database failure - attempting reconnection")
            
            # Try to reinitialize database connection
            await self.supabase.initialize()
            logger.info("✅ Database reconnection attempt completed")
            
        except Exception as e:
            logger.error(f"Database failure handler error: {e}")
            
    async def _handle_redis_failure(self):
        """Handle Redis connectivity failure"""
        try:
            logger.error("Handling Redis failure - attempting reconnection")
            
            # Try to reconnect Redis
            await self.redis.ping()
            logger.info("✅ Redis reconnection successful")
            
        except Exception as e:
            logger.error(f"Redis failure handler error: {e}")
            
    async def _handle_channel_access_failure(self):
        """Handle channel access failure"""
        try:
            logger.error("Handling channel access failure")
            
            if self.channel_manager and self.token_manager:
                # Try to resynchronize permissions with current token
                sync_results = await self.channel_manager.synchronize_permissions(self.token_manager)
                logger.info(f"✅ Channel permission resync completed: {sync_results['successful_tokens']}/{sync_results['total_tokens']} successful")
                
        except Exception as e:
            logger.error(f"Channel access failure handler error: {e}")
            
    async def _handle_system_resource_failure(self):
        """Handle system resource exhaustion"""
        try:
            logger.error("Handling system resource failure")
            
            # Log current resource usage for debugging
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            logger.error(f"Resource status - CPU: {cpu_percent:.1f}%, Memory: {memory.percent:.1f}%, Disk: {(disk.used/disk.total)*100:.1f}%")
            
            # Could implement additional cleanup procedures here
            
        except Exception as e:
            logger.error(f"System resource failure handler error: {e}")
            
    async def _send_critical_notification(self, health_data: Dict):
        """Send critical system failure notification"""
        try:
            notification_data = {
                'type': 'critical_system_failure',
                'message': f"🚨 CRITICAL SYSTEM FAILURE: {health_data['message']}",
                'timestamp': health_data['timestamp'],
                'critical_components': health_data['critical_components'],
                'overall_status': health_data['status'],
                'requires_immediate_attention': True
            }
            
            await self.redis.lpush('admin_notifications', json.dumps(notification_data))
            logger.critical(f"Critical notification sent: {health_data['message']}")
            
        except Exception as e:
            logger.error(f"Failed to send critical notification: {e}")
            
    async def _send_warning_notification(self, health_data: Dict):
        """Send system degradation warning notification"""
        try:
            notification_data = {
                'type': 'system_degradation',
                'message': f"⚠️ SYSTEM PERFORMANCE DEGRADED: {health_data['message']}",
                'timestamp': health_data['timestamp'],
                'degraded_components': health_data['degraded_components'],
                'overall_status': health_data['status']
            }
            
            await self.redis.lpush('admin_notifications', json.dumps(notification_data))
            logger.warning(f"Degradation warning sent: {health_data['message']}")
            
        except Exception as e:
            logger.error(f"Failed to send warning notification: {e}")
            
    async def get_system_status(self) -> Dict:
        """Get current comprehensive system status"""
        overall_health = self._calculate_overall_health()
        
        return {
            'overall_health': overall_health,
            'components': {
                name: {
                    'status': component.status.value,
                    'last_check': component.last_check,
                    'error_count': component.error_count,
                    'metrics_count': len(component.metrics)
                }
                for name, component in self.health_metrics.items()
            },
            'monitoring_active': self.monitoring_task is not None and not self.monitoring_task.done(),
            'last_failover': self.last_failover_time.isoformat() if self.last_failover_time else None,
            'failover_cooldown_remaining': max(0, self.failover_cooldown - (datetime.utcnow() - self.last_failover_time).total_seconds()) if self.last_failover_time else 0
        }
        
    async def force_health_check(self) -> Dict:
        """Force immediate health check of all components"""
        logger.info("Forcing immediate health check")
        
        await self._check_bot_health()
        await self._check_database_health()
        await self._check_redis_health()
        await self._check_channel_health()
        await self._check_system_resources()
        
        overall_health = self._calculate_overall_health()
        await self._update_health_metrics(overall_health)
        
        return overall_health
        
    async def shutdown(self):
        """Shutdown health monitor and cleanup"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
                
        logger.info("System health monitor shutdown complete")