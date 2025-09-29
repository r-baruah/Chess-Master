"""
Real-time Community Dashboard with role-based access and customizable widgets
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from core.analytics_engine import analytics_engine
from core.supabase_client import supabase_client
from core.redis_state import redis_state

logger = logging.getLogger(__name__)

class CommunityDashboard:
    """Real-time dashboard with customizable widgets and role-based access"""
    
    def __init__(self):
        self.active_subscriptions = {}
        self.widget_registry = {
            'community_overview': {'name': 'Community Overview', 'permission': 'view_analytics'},
            'user_growth': {'name': 'User Growth', 'permission': 'view_analytics'},
            'review_queue': {'name': 'Review Queue', 'permission': 'approve_courses'},
            'course_analytics': {'name': 'Course Analytics', 'permission': 'view_analytics'},
            'system_health': {'name': 'System Health', 'permission': 'system_admin'},
            'volunteer_performance': {'name': 'Volunteer Performance', 'permission': 'manage_users'}
        }
    
    async def get_dashboard_config(self, anonymous_id: str, role: str, permissions: Dict) -> Dict[str, Any]:
        """Get personalized dashboard configuration for user"""
        try:
            available_widgets = {}
            for widget_id, config in self.widget_registry.items():
                required_perm = config.get('permission')
                if not required_perm or permissions.get(required_perm, False):
                    available_widgets[widget_id] = config
            
            return {
                'user_role': role,
                'available_widgets': available_widgets,
                'current_layout': self._get_default_layout(role),
                'last_updated': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get dashboard config: {e}")
            return {'error': str(e)}
    
    async def get_widget_data(self, widget_id: str, role: str, timeframe: str = '7d') -> Dict[str, Any]:
        """Get data for specific dashboard widget"""
        try:
            # Check cache first
            cache_key = f"widget:{widget_id}:{role}:{timeframe}"
            cached_data = await redis_state.cache_get(cache_key)
            if cached_data:
                return cached_data
            
            # Generate widget data
            widget_data = await self._generate_widget_data(widget_id, role, timeframe)
            
            # Cache for 5 minutes
            await redis_state.cache_set(cache_key, widget_data, 300)
            return widget_data
            
        except Exception as e:
            logger.error(f"Failed to get widget data for {widget_id}: {e}")
            return {'error': str(e)}
    
    async def _generate_widget_data(self, widget_id: str, role: str, timeframe: str) -> Dict[str, Any]:
        """Generate specific widget data based on widget type"""
        
        if widget_id == 'community_overview':
            overview = await analytics_engine.get_community_overview(timeframe, role)
            return {
                'widget_id': widget_id,
                'title': 'Community Overview',
                'data': {
                    'total_users': overview.get('users', {}).get('total_users', 0),
                    'total_courses': overview.get('courses', {}).get('total_courses', 0),
                    'active_users': overview.get('users', {}).get('active_users', 0),
                    'pending_reviews': overview.get('reviews', {}).get('pending_reviews', 0)
                },
                'last_updated': datetime.utcnow().isoformat()
            }
        
        elif widget_id == 'user_growth':
            user_metrics = await analytics_engine.get_user_metrics(
                datetime.utcnow() - timedelta(days=30), datetime.utcnow()
            )
            return {
                'widget_id': widget_id,
                'title': 'User Growth',
                'data': {
                    'new_users_30d': user_metrics.get('new_users', 0),
                    'role_distribution': user_metrics.get('role_distribution', [])
                },
                'last_updated': datetime.utcnow().isoformat()
            }
        
        elif widget_id == 'review_queue':
            review_metrics = await analytics_engine.get_review_metrics(
                datetime.utcnow() - timedelta(days=7), datetime.utcnow()
            )
            return {
                'widget_id': widget_id,
                'title': 'Review Queue',
                'data': {
                    'pending_count': review_metrics.get('pending_reviews', 0),
                    'avg_review_time': review_metrics.get('avg_review_time_hours', 0),
                    'completed_reviews': review_metrics.get('completed_reviews', 0)
                },
                'urgency_level': 'high' if review_metrics.get('pending_reviews', 0) > 50 else 'normal',
                'last_updated': datetime.utcnow().isoformat()
            }
        
        elif widget_id == 'course_analytics':
            course_metrics = await analytics_engine.get_course_metrics(
                datetime.utcnow() - timedelta(days=30), datetime.utcnow()
            )
            return {
                'widget_id': widget_id,
                'title': 'Course Analytics',
                'data': {
                    'new_courses': course_metrics.get('new_courses', 0),
                    'popular_categories': course_metrics.get('popular_categories', [])[:5],
                    'approval_stats': course_metrics.get('approval_stats', [])
                },
                'last_updated': datetime.utcnow().isoformat()
            }
        
        elif widget_id == 'system_health':
            system_metrics = await analytics_engine.get_system_metrics(
                datetime.utcnow() - timedelta(hours=24), datetime.utcnow()
            )
            return {
                'widget_id': widget_id,
                'title': 'System Health',
                'data': {
                    'channel_health': system_metrics.get('channel_health', []),
                    'system_events': system_metrics.get('system_events', [])
                },
                'health_status': 'healthy',
                'last_updated': datetime.utcnow().isoformat()
            }
        
        elif widget_id == 'volunteer_performance':
            volunteer_metrics = await analytics_engine.get_volunteer_metrics(
                datetime.utcnow() - timedelta(days=7), datetime.utcnow()
            )
            return {
                'widget_id': widget_id,
                'title': 'Volunteer Performance',
                'data': {
                    'active_volunteers': volunteer_metrics.get('active_volunteers', 0),
                    'approval_rate': volunteer_metrics.get('approval_rate', 0),
                    'workload_distribution': volunteer_metrics.get('workload_distribution', [])
                },
                'last_updated': datetime.utcnow().isoformat()
            }
        
        return {'error': 'Unknown widget type'}
    
    async def export_dashboard_data(self, anonymous_id: str, widget_ids: List[str], role: str) -> Dict[str, Any]:
        """Export dashboard data for reports"""
        try:
            export_data = {
                'exported_at': datetime.utcnow().isoformat(),
                'exported_by': anonymous_id,
                'widgets': {}
            }
            
            for widget_id in widget_ids:
                if widget_id in self.widget_registry:
                    widget_data = await self.get_widget_data(widget_id, role)
                    if 'error' not in widget_data:
                        export_data['widgets'][widget_id] = widget_data
            
            # Track export event
            await analytics_engine.track_event(
                anonymous_id, 'dashboard_export', 
                {'widgets_count': len(export_data['widgets'])}
            )
            
            return export_data
            
        except Exception as e:
            logger.error(f"Failed to export dashboard data: {e}")
            return {'error': str(e)}
    
    def _get_default_layout(self, role: str) -> Dict[str, Any]:
        """Get default layout based on user role"""
        if role in ['super_admin', 'admin']:
            return {
                'grid': [
                    ['community_overview', 'system_health'],
                    ['user_growth', 'review_queue'],
                    ['course_analytics', 'volunteer_performance']
                ]
            }
        elif role in ['moderator']:
            return {
                'grid': [
                    ['community_overview', 'review_queue'],
                    ['course_analytics', 'user_growth']
                ]
            }
        elif role in ['volunteer_reviewer']:
            return {
                'grid': [
                    ['review_queue', 'course_analytics']
                ]
            }
        else:
            return {
                'grid': [
                    ['course_analytics']
                ]
            }

# Global instance
community_dashboard = CommunityDashboard()