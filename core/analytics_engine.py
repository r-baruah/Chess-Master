"""
Community Analytics Engine - Real-time community health metrics and engagement analytics
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
import json
from core.supabase_client import supabase_client
from core.redis_state import redis_state

logger = logging.getLogger(__name__)

class CommunityAnalyticsEngine:
    """Real-time community analytics with privacy-preserving metrics"""
    
    def __init__(self):
        self.cache_timeout = 300  # 5 minutes cache
        self.metrics_cache = {}
        
    async def get_community_overview(self, timeframe: str = '7d', role: str = 'admin') -> Dict[str, Any]:
        """Generate comprehensive community overview metrics"""
        cache_key = f"overview:{timeframe}:{role}"
        
        # Check cache first
        cached = await redis_state.cache_get(cache_key)
        if cached:
            return json.loads(cached)
        
        end_date = datetime.utcnow()
        days = 7 if timeframe == '7d' else 30 if timeframe == '30d' else 1
        start_date = end_date - timedelta(days=days)
        
        metrics = {
            'users': await self.get_user_metrics(start_date, end_date),
            'courses': await self.get_course_metrics(start_date, end_date),
            'reviews': await self.get_review_metrics(start_date, end_date),
            'volunteers': await self.get_volunteer_metrics(start_date, end_date),
            'system': await self.get_system_metrics(start_date, end_date),
            'engagement': await self.get_engagement_metrics(start_date, end_date),
            'generated_at': datetime.utcnow().isoformat(),
            'timeframe': timeframe
        }
        
        # Apply role-based filtering
        filtered_metrics = self._filter_metrics_by_role(metrics, role)
        
        # Cache results
        await redis_state.cache_set(cache_key, filtered_metrics, self.cache_timeout)
        
        logger.info(f"Generated community overview for {timeframe} with role {role}")
        return filtered_metrics
    
    async def get_user_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get user registration and activity metrics"""
        try:
            # Total users and growth
            total_users = await supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM users"
            )
            
            new_users = await supabase_client.execute_query(
                """
                SELECT COUNT(*) as count 
                FROM users 
                WHERE created_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Active users (users with activity in timeframe)
            active_users = await supabase_client.execute_query(
                """
                SELECT COUNT(DISTINCT anonymous_id) as count
                FROM analytics_events 
                WHERE created_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Role distribution
            role_distribution = await supabase_client.execute_query(
                """
                SELECT role, COUNT(*) as count
                FROM users 
                GROUP BY role
                ORDER BY count DESC
                """
            )
            
            return {
                'total_users': total_users[0]['count'] if total_users else 0,
                'new_users': new_users[0]['count'] if new_users else 0,
                'active_users': active_users[0]['count'] if active_users else 0,
                'role_distribution': role_distribution or []
            }
            
        except Exception as e:
            logger.error(f"Failed to get user metrics: {e}")
            return {'error': str(e)}
    
    async def get_course_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get course upload, approval, and download statistics"""
        try:
            # Course statistics
            total_courses = await supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM courses"
            )
            
            new_courses = await supabase_client.execute_query(
                """
                SELECT COUNT(*) as count
                FROM courses 
                WHERE created_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Approval statistics
            approval_stats = await supabase_client.execute_query(
                """
                SELECT 
                    status,
                    COUNT(*) as count,
                    AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/3600) as avg_hours
                FROM course_submissions
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY status
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Popular categories
            popular_categories = await supabase_client.execute_query(
                """
                SELECT 
                    category,
                    COUNT(*) as course_count,
                    AVG(download_count) as avg_downloads
                FROM courses
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY category
                ORDER BY course_count DESC
                LIMIT 10
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            return {
                'total_courses': total_courses[0]['count'] if total_courses else 0,
                'new_courses': new_courses[0]['count'] if new_courses else 0,
                'approval_stats': approval_stats or [],
                'popular_categories': popular_categories or []
            }
            
        except Exception as e:
            logger.error(f"Failed to get course metrics: {e}")
            return {'error': str(e)}
    
    async def get_review_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get volunteer reviewer performance and workload metrics"""
        try:
            # Review queue statistics
            pending_reviews = await supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM volunteer_reviews WHERE status = 'pending'"
            )
            
            completed_reviews = await supabase_client.execute_query(
                """
                SELECT COUNT(*) as count
                FROM volunteer_reviews 
                WHERE completed_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Average review time
            avg_review_time = await supabase_client.execute_query(
                """
                SELECT AVG(EXTRACT(EPOCH FROM (completed_at - assigned_at))/3600) as avg_hours
                FROM volunteer_reviews
                WHERE completed_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Reviewer performance (anonymous)
            reviewer_stats = await supabase_client.execute_query(
                """
                SELECT 
                    COUNT(*) as reviews_completed,
                    AVG(EXTRACT(EPOCH FROM (completed_at - assigned_at))/3600) as avg_hours,
                    'anonymous' as reviewer_id
                FROM volunteer_reviews
                WHERE completed_at BETWEEN $1 AND $2
                GROUP BY assigned_reviewer
                ORDER BY reviews_completed DESC
                LIMIT 10
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            return {
                'pending_reviews': pending_reviews[0]['count'] if pending_reviews else 0,
                'completed_reviews': completed_reviews[0]['count'] if completed_reviews else 0,
                'avg_review_time_hours': avg_review_time[0]['avg_hours'] if avg_review_time and avg_review_time[0]['avg_hours'] else 0,
                'reviewer_performance': reviewer_stats or []
            }
            
        except Exception as e:
            logger.error(f"Failed to get review metrics: {e}")
            return {'error': str(e)}
    
    async def get_volunteer_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get volunteer reviewer effectiveness and workload distribution"""
        try:
            # Active volunteers
            active_volunteers = await supabase_client.execute_query(
                """
                SELECT COUNT(DISTINCT assigned_reviewer) as count
                FROM volunteer_reviews
                WHERE assigned_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Volunteer workload distribution (anonymous)
            workload_distribution = await supabase_client.execute_query(
                """
                SELECT 
                    COUNT(*) as review_count,
                    'anonymous' as volunteer_id,
                    AVG(EXTRACT(EPOCH FROM (completed_at - assigned_at))/3600) as avg_time_hours
                FROM volunteer_reviews
                WHERE assigned_at BETWEEN $1 AND $2
                GROUP BY assigned_reviewer
                ORDER BY review_count DESC
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Quality metrics
            approval_rate = await supabase_client.execute_query(
                """
                SELECT 
                    COUNT(CASE WHEN status = 'approved' THEN 1 END) * 100.0 / COUNT(*) as approval_rate
                FROM volunteer_reviews
                WHERE completed_at BETWEEN $1 AND $2
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            return {
                'active_volunteers': active_volunteers[0]['count'] if active_volunteers else 0,
                'workload_distribution': workload_distribution or [],
                'approval_rate': approval_rate[0]['approval_rate'] if approval_rate else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get volunteer metrics: {e}")
            return {'error': str(e)}
    
    async def get_system_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get system performance and health metrics"""
        try:
            # Channel health
            channel_health = await supabase_client.execute_query(
                """
                SELECT 
                    channel_id,
                    health_status,
                    last_verified,
                    COUNT(*) as file_count
                FROM multi_channel_files
                GROUP BY channel_id, health_status, last_verified
                ORDER BY file_count DESC
                """
            )
            
            # System events
            system_events = await supabase_client.execute_query(
                """
                SELECT 
                    event_type,
                    COUNT(*) as event_count
                FROM analytics_events
                WHERE created_at BETWEEN $1 AND $2
                    AND event_type IN ('system_error', 'channel_failover', 'bot_restart')
                GROUP BY event_type
                ORDER BY event_count DESC
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            return {
                'channel_health': channel_health or [],
                'system_events': system_events or []
            }
            
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {'error': str(e)}
    
    async def get_engagement_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get community interaction patterns and engagement levels"""
        try:
            # Daily active users trend
            daily_activity = await supabase_client.execute_query(
                """
                SELECT 
                    DATE(created_at) as date,
                    COUNT(DISTINCT anonymous_id) as active_users,
                    COUNT(*) as total_events
                FROM analytics_events
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY DATE(created_at)
                ORDER BY date
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            # Most popular actions
            popular_actions = await supabase_client.execute_query(
                """
                SELECT 
                    event_type,
                    COUNT(*) as event_count
                FROM analytics_events
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY event_type
                ORDER BY event_count DESC
                LIMIT 10
                """,
                start_date.isoformat(), end_date.isoformat()
            )
            
            return {
                'daily_activity': daily_activity or [],
                'popular_actions': popular_actions or []
            }
            
        except Exception as e:
            logger.error(f"Failed to get engagement metrics: {e}")
            return {'error': str(e)}
    
    async def track_event(self, anonymous_id: str, event_type: str, metadata: Dict = None) -> bool:
        """Track community event for analytics"""
        try:
            event_data = {
                'anonymous_id': anonymous_id,
                'event_type': event_type,
                'metadata': metadata or {},
                'created_at': datetime.utcnow().isoformat()
            }
            
            await supabase_client.execute_command(
                """
                INSERT INTO analytics_events (anonymous_id, event_type, metadata, created_at)
                VALUES ($1, $2, $3, $4)
                """,
                anonymous_id, event_type, json.dumps(metadata or {}), event_data['created_at']
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to track event: {e}")
            return False
    
    async def generate_report(self, report_type: str, timeframe: str, role: str) -> Dict[str, Any]:
        """Generate automated reports with role-based data access"""
        try:
            overview = await self.get_community_overview(timeframe, role)
            
            report = {
                'report_type': report_type,
                'timeframe': timeframe,
                'generated_at': datetime.utcnow().isoformat(),
                'generated_for_role': role,
                'summary': self._generate_summary(overview),
                'data': overview,
                'recommendations': await self._generate_recommendations(overview)
            }
            
            # Store report for future reference
            await self._store_report(report)
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return {'error': str(e)}
    
    def _filter_metrics_by_role(self, metrics: Dict, role: str) -> Dict:
        """Filter metrics based on user role permissions"""
        if role in ['super_admin', 'admin']:
            return metrics  # Full access
        
        elif role in ['moderator']:
            # Remove sensitive system metrics
            filtered = metrics.copy()
            if 'system' in filtered:
                filtered['system'] = {'message': 'Limited access'}
            return filtered
        
        elif role in ['volunteer_reviewer']:
            # Only review and course metrics
            return {
                'reviews': metrics.get('reviews', {}),
                'courses': metrics.get('courses', {}),
                'generated_at': metrics.get('generated_at'),
                'timeframe': metrics.get('timeframe')
            }
        
        else:
            # Contributors get very limited view
            return {
                'courses': {
                    'total_courses': metrics.get('courses', {}).get('total_courses', 0)
                },
                'generated_at': metrics.get('generated_at'),
                'timeframe': metrics.get('timeframe')
            }
    
    def _generate_summary(self, overview: Dict) -> Dict[str, str]:
        """Generate human-readable summary of metrics"""
        summary = {}
        
        if 'users' in overview:
            user_data = overview['users']
            summary['user_growth'] = f"{'Positive' if user_data.get('new_users', 0) > 0 else 'Stable'} user growth with {user_data.get('new_users', 0)} new registrations"
        
        if 'courses' in overview:
            course_data = overview['courses']
            summary['course_activity'] = f"{course_data.get('new_courses', 0)} new courses added"
        
        if 'reviews' in overview:
            review_data = overview['reviews']
            avg_time = review_data.get('avg_review_time_hours', 0)
            summary['review_efficiency'] = f"Average review time: {avg_time:.1f} hours"
        
        return summary
    
    async def _generate_recommendations(self, overview: Dict) -> List[str]:
        """Generate actionable recommendations based on metrics"""
        recommendations = []
        
        if 'reviews' in overview:
            pending = overview['reviews'].get('pending_reviews', 0)
            if pending > 50:
                recommendations.append("High review queue detected - consider recruiting more volunteers")
        
        if 'users' in overview:
            active = overview['users'].get('active_users', 0)
            total = overview['users'].get('total_users', 1)
            engagement_rate = (active / total) * 100 if total > 0 else 0
            
            if engagement_rate < 20:
                recommendations.append("Low engagement rate - consider community engagement initiatives")
        
        if not recommendations:
            recommendations.append("Community metrics are healthy - continue current strategies")
        
        return recommendations
    
    async def _store_report(self, report: Dict) -> None:
        """Store generated report for historical tracking"""
        try:
            await supabase_client.execute_command(
                """
                INSERT INTO analytics_reports (report_type, timeframe, role, data, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                report['report_type'],
                report['timeframe'],
                report['generated_for_role'],
                json.dumps(report),
                report['generated_at']
            )
        except Exception as e:
            logger.error(f"Failed to store report: {e}")

# Global instance
analytics_engine = CommunityAnalyticsEngine()