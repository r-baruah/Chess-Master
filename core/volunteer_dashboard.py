"""
Volunteer Dashboard System - AC1: Comprehensive dashboard with priority sorting and statistics
Implements real-time dashboard for volunteer reviewers with course preview and batch operations
"""
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager
from core.volunteer_system import volunteer_manager
from core.redis_state import redis_state

logger = logging.getLogger(__name__)

class VolunteerDashboard:
    """Enhanced volunteer dashboard with comprehensive review tools"""
    
    def __init__(self):
        self.dashboard_cache_ttl = 300  # 5 minutes
        
    async def get_volunteer_dashboard(self, volunteer_id: str) -> Dict[str, Any]:
        """Generate comprehensive volunteer dashboard with pending reviews and statistics"""
        try:
            # Get volunteer user info
            volunteer_query = """
                SELECT u.id, u.anonymous_id, u.role, u.permissions, u.created_at,
                       COUNT(r.id) FILTER (WHERE r.status = 'pending') as current_workload,
                       COUNT(r.id) FILTER (WHERE r.status IN ('approved', 'rejected') AND r.reviewed_at > NOW() - INTERVAL '7 days') as reviews_this_week,
                       COUNT(r.id) FILTER (WHERE r.status IN ('approved', 'rejected') AND r.reviewed_at > NOW() - INTERVAL '30 days') as reviews_this_month,
                       AVG(EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600) FILTER (WHERE r.status IN ('approved', 'rejected')) as avg_review_time_hours,
                       COUNT(r.id) FILTER (WHERE r.status = 'approved') * 100.0 / NULLIF(COUNT(r.id) FILTER (WHERE r.status IN ('approved', 'rejected')), 0) as approval_rate
                FROM users u
                LEFT JOIN reviews r ON u.id = r.reviewer_id
                WHERE u.id = $1
                GROUP BY u.id, u.anonymous_id, u.role, u.permissions, u.created_at
            """
            
            volunteer_result = await supabase_client.execute_query(volunteer_query, volunteer_id)
            if not volunteer_result:
                return {'error': 'Volunteer not found'}
            
            volunteer = volunteer_result[0]
            
            # Get pending review queue with priority sorting
            pending_reviews = await self.get_pending_reviews_with_priority(volunteer_id)

            # Get pending notifications from Redis
            recent_notifications = await redis_state.redis_client.lrange(
                f"volunteer_notifications:{volunteer['anonymous_id']}",
                0,
                19
            )
            formatted_notifications = [json.loads(item) for item in recent_notifications]
            assignment_alerts = await redis_state.redis_client.keys(
                f"volunteer_assignment_notice:{volunteer['anonymous_id']}:*"
            )
            assignment_highlights = []
            for alert_key in assignment_alerts:
                data = await redis_state.redis_client.get(alert_key)
                if data:
                    assignment_highlights.append(json.loads(data))
            
            # Get recent activity
            recent_activity = await self.get_volunteer_recent_activity(volunteer_id, limit=10)
            
            # Calculate performance metrics
            performance_metrics = await self.calculate_performance_metrics(volunteer_id)
            
            # Get queue statistics
            queue_stats = await self.get_volunteer_queue_statistics(volunteer_id)
            
            dashboard = {
                'volunteer_info': {
                    'anonymous_id': volunteer['anonymous_id'],
                    'role': volunteer['role'],
                    'permissions': volunteer['permissions'],
                    'joined_date': volunteer['created_at'],
                    'current_workload': volunteer['current_workload'] or 0,
                    'reviews_this_week': volunteer['reviews_this_week'] or 0,
                    'reviews_this_month': volunteer['reviews_this_month'] or 0,
                    'avg_review_time_hours': round(volunteer['avg_review_time_hours'] or 24, 1),
                    'approval_rate': round(volunteer['approval_rate'] or 0, 1)
                },
                'pending_queue': {
                    'total_pending': len(pending_reviews),
                    'high_priority': len([r for r in pending_reviews if r.get('priority_level', 1) > 2]),
                    'urgent_priority': len([r for r in pending_reviews if r.get('priority_level', 1) > 3]),
                    'reviews': pending_reviews[:10],  # Show top 10 priority items
                    'estimated_completion_time': self.calculate_estimated_completion(pending_reviews)
                },
                'performance_metrics': performance_metrics,
                'queue_statistics': queue_stats,
                'notifications': formatted_notifications,
                'assignment_highlights': assignment_highlights,
                'recent_activity': recent_activity,
                'dashboard_updated_at': datetime.utcnow().isoformat()
            }
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Failed to generate volunteer dashboard: {e}")
            return {'error': f'Dashboard generation failed: {str(e)}'}
    
    async def get_pending_reviews_with_priority(self, volunteer_id: str) -> List[Dict]:
        """Get pending reviews with priority sorting and course metadata"""
        try:
            reviews_query = """
                SELECT r.id as review_id, r.priority_level, r.created_at as assigned_at,
                       c.id as course_id, c.title, c.description, c.banner_link,
                       u.anonymous_id as contributor_anonymous_id,
                       COUNT(cf.id) as file_count,
                       SUM(cf.file_size) as total_size,
                       EXTRACT(EPOCH FROM (NOW() - r.created_at))/3600 as hours_waiting,
                       CASE 
                           WHEN r.priority_level > 3 THEN 'URGENT'
                           WHEN r.priority_level > 2 THEN 'HIGH' 
                           WHEN r.priority_level > 1 THEN 'MEDIUM'
                           ELSE 'LOW'
                       END as priority_label
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                JOIN users u ON c.contributor_id = u.id
                LEFT JOIN course_files cf ON c.id = cf.course_id
                WHERE r.reviewer_id = $1 AND r.status = 'pending'
                GROUP BY r.id, r.priority_level, r.created_at, c.id, c.title, c.description, 
                         c.banner_link, u.anonymous_id
                ORDER BY r.priority_level DESC, r.created_at ASC
            """
            
            reviews = await supabase_client.execute_query(reviews_query, volunteer_id)
            
            # Enrich with additional metadata
            enriched_reviews = []
            for review in reviews:
                # Add urgency indicator based on waiting time
                hours_waiting = review.get('hours_waiting', 0)
                urgency_factor = 'NORMAL'
                if hours_waiting > 72:  # 3 days
                    urgency_factor = 'OVERDUE'
                elif hours_waiting > 24:  # 1 day
                    urgency_factor = 'URGENT'
                
                # Format file size
                total_size = review.get('total_size', 0) or 0
                size_display = self.format_file_size(total_size)
                
                enriched_review = {
                    **review,
                    'urgency_factor': urgency_factor,
                    'hours_waiting': round(hours_waiting, 1),
                    'size_display': size_display,
                    'estimated_review_time': self.estimate_review_time(
                        review.get('file_count', 0), 
                        total_size,
                        review.get('priority_level', 1)
                    )
                }
                enriched_reviews.append(enriched_review)
            
            return enriched_reviews
            
        except Exception as e:
            logger.error(f"Failed to get pending reviews: {e}")
            return []
    
    async def get_course_for_review(self, course_id: str, volunteer_id: str) -> Dict[str, Any]:
        """Get complete course data for review interface with all metadata and files"""
        try:
            # Verify volunteer has access to this review
            access_check = await supabase_client.execute_query(
                "SELECT 1 FROM reviews WHERE course_id = $1 AND reviewer_id = $2",
                course_id, volunteer_id
            )
            
            if not access_check:
                return {'error': 'Access denied to this review'}
            
            # Get course with all metadata
            course_query = """
                SELECT c.*, u.anonymous_id as contributor_anonymous_id,
                       r.id as review_id, r.priority_level, r.created_at as assigned_at,
                       EXTRACT(EPOCH FROM (NOW() - r.created_at))/3600 as hours_waiting
                FROM courses c
                JOIN users u ON c.contributor_id = u.id
                JOIN reviews r ON c.id = r.course_id
                WHERE c.id = $1 AND r.reviewer_id = $2
            """
            
            course_result = await supabase_client.execute_query(course_query, course_id, volunteer_id)
            if not course_result:
                return {'error': 'Course not found'}
            
            course = course_result[0]
            
            # Get all course files with metadata
            files_query = """
                SELECT cf.*, 
                       CASE 
                           WHEN cf.file_type LIKE 'image%' THEN 'image'
                           WHEN cf.file_type LIKE 'video%' THEN 'video'
                           WHEN cf.file_type LIKE 'application/pdf' THEN 'document'
                           ELSE 'other'
                       END as file_category
                FROM course_files cf
                WHERE cf.course_id = $1
                ORDER BY cf.created_at ASC
            """
            
            files = await supabase_client.execute_query(files_query, course_id)
            
            # Get review guidelines for this course type/category
            review_guidelines = await self.get_review_guidelines(course.get('category', 'general'))
            
            # Get contributor history for context
            contributor_stats = await self.get_contributor_history(course['contributor_anonymous_id'])
            
            return {
                'success': True,
                'course': {
                    **course,
                    'hours_waiting': round(course.get('hours_waiting', 0), 1),
                    'priority_label': self.get_priority_label(course.get('priority_level', 1))
                },
                'files': files,
                'file_summary': {
                    'total_count': len(files),
                    'total_size': sum(f.get('file_size', 0) or 0 for f in files),
                    'file_types': list(set(f.get('file_category', 'other') for f in files))
                },
                'review_guidelines': review_guidelines,
                'contributor_context': contributor_stats,
                'estimated_review_time': self.estimate_review_time(
                    len(files),
                    sum(f.get('file_size', 0) or 0 for f in files),
                    course.get('priority_level', 1)
                )
            }
            
        except Exception as e:
            logger.error(f"Failed to get course for review {course_id}: {e}")
            return {'error': f'Failed to load course: {str(e)}'}
    
    async def get_volunteer_recent_activity(self, volunteer_id: str, limit: int = 10) -> List[Dict]:
        """Get volunteer's recent review activity"""
        try:
            activity_query = """
                SELECT r.id as review_id, r.status, r.reviewed_at, r.created_at,
                       c.title as course_title, c.id as course_id,
                       EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600 as review_duration_hours
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                WHERE r.reviewer_id = $1 AND r.status IN ('approved', 'rejected', 'needs_revision')
                ORDER BY r.reviewed_at DESC
                LIMIT $2
            """
            
            activities = await supabase_client.execute_query(activity_query, volunteer_id, limit)
            
            # Format activity items
            formatted_activities = []
            for activity in activities:
                formatted_activity = {
                    'review_id': activity['review_id'],
                    'course_id': activity['course_id'],
                    'course_title': activity['course_title'],
                    'action': activity['status'].title(),
                    'completed_at': activity['reviewed_at'],
                    'duration_hours': round(activity.get('review_duration_hours', 0) or 0, 1),
                    'action_color': self.get_action_color(activity['status'])
                }
                formatted_activities.append(formatted_activity)
            
            return formatted_activities
            
        except Exception as e:
            logger.error(f"Failed to get recent activity: {e}")
            return []
    
    async def calculate_performance_metrics(self, volunteer_id: str) -> Dict[str, Any]:
        """Calculate comprehensive volunteer performance metrics"""
        try:
            metrics_query = """
                SELECT 
                    -- Last 30 days metrics
                    COUNT(*) FILTER (WHERE r.reviewed_at > NOW() - INTERVAL '30 days' AND r.status IN ('approved', 'rejected')) as reviews_30d,
                    COUNT(*) FILTER (WHERE r.reviewed_at > NOW() - INTERVAL '30 days' AND r.status = 'approved') as approvals_30d,
                    AVG(EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600) FILTER (WHERE r.reviewed_at > NOW() - INTERVAL '30 days') as avg_time_30d,
                    
                    -- All time metrics  
                    COUNT(*) FILTER (WHERE r.status IN ('approved', 'rejected')) as total_reviews,
                    COUNT(*) FILTER (WHERE r.status = 'approved') as total_approvals,
                    AVG(EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600) FILTER (WHERE r.status IN ('approved', 'rejected')) as avg_time_all,
                    MIN(r.reviewed_at) as first_review,
                    
                    -- Speed percentiles
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600) 
                        FILTER (WHERE r.status IN ('approved', 'rejected')) as median_review_time
                FROM reviews r
                WHERE r.reviewer_id = $1
            """
            
            metrics_result = await supabase_client.execute_query(metrics_query, volunteer_id)
            if not metrics_result:
                return self.get_default_metrics()
            
            metrics = metrics_result[0]
            
            # Calculate approval rates
            approval_rate_30d = 0
            if metrics.get('reviews_30d', 0) > 0:
                approval_rate_30d = (metrics.get('approvals_30d', 0) / metrics['reviews_30d']) * 100
            
            approval_rate_all = 0
            if metrics.get('total_reviews', 0) > 0:
                approval_rate_all = (metrics.get('total_approvals', 0) / metrics['total_reviews']) * 100
            
            # Calculate activity level
            reviews_30d = metrics.get('reviews_30d', 0)
            activity_level = self.get_activity_level(reviews_30d)
            
            # Calculate efficiency score (based on speed and consistency)
            efficiency_score = self.calculate_efficiency_score(
                metrics.get('avg_time_30d', 24),
                metrics.get('reviews_30d', 0),
                approval_rate_30d
            )
            
            return {
                'last_30_days': {
                    'reviews_completed': reviews_30d,
                    'approval_rate': round(approval_rate_30d, 1),
                    'avg_review_time_hours': round(metrics.get('avg_time_30d', 0) or 0, 1),
                    'activity_level': activity_level
                },
                'all_time': {
                    'total_reviews': metrics.get('total_reviews', 0),
                    'approval_rate': round(approval_rate_all, 1),
                    'avg_review_time_hours': round(metrics.get('avg_time_all', 0) or 0, 1),
                    'median_review_time_hours': round(metrics.get('median_review_time', 0) or 0, 1),
                    'first_review_date': metrics.get('first_review')
                },
                'performance_indicators': {
                    'efficiency_score': efficiency_score,
                    'reviewer_level': self.get_reviewer_level(metrics.get('total_reviews', 0)),
                    'speed_rating': self.get_speed_rating(metrics.get('avg_time_30d', 24)),
                    'consistency_rating': self.get_consistency_rating(approval_rate_30d, approval_rate_all)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate performance metrics: {e}")
            return self.get_default_metrics()
    
    async def get_volunteer_queue_statistics(self, volunteer_id: str) -> Dict[str, Any]:
        """Get detailed queue statistics for volunteer"""
        try:
            queue_stats_query = """
                SELECT 
                    COUNT(*) as total_pending,
                    COUNT(*) FILTER (WHERE priority_level > 3) as urgent,
                    COUNT(*) FILTER (WHERE priority_level > 2) as high_priority,
                    COUNT(*) FILTER (WHERE priority_level <= 2) as normal_priority,
                    AVG(EXTRACT(EPOCH FROM (NOW() - created_at))/3600) as avg_waiting_hours,
                    MAX(EXTRACT(EPOCH FROM (NOW() - created_at))/3600) as max_waiting_hours,
                    COUNT(*) FILTER (WHERE EXTRACT(EPOCH FROM (NOW() - created_at))/3600 > 24) as overdue_count
                FROM reviews
                WHERE reviewer_id = $1 AND status = 'pending'
            """
            
            stats_result = await supabase_client.execute_query(queue_stats_query, volunteer_id)
            if not stats_result:
                return {}
            
            stats = stats_result[0]
            
            # Get workload comparison with other volunteers
            workload_comparison = await self.get_workload_comparison(volunteer_id)
            
            return {
                'queue_breakdown': {
                    'total_pending': stats.get('total_pending', 0),
                    'urgent': stats.get('urgent', 0),
                    'high_priority': stats.get('high_priority', 0),
                    'normal_priority': stats.get('normal_priority', 0)
                },
                'timing_stats': {
                    'avg_waiting_hours': round(stats.get('avg_waiting_hours', 0) or 0, 1),
                    'max_waiting_hours': round(stats.get('max_waiting_hours', 0) or 0, 1),
                    'overdue_items': stats.get('overdue_count', 0)
                },
                'workload_comparison': workload_comparison
            }
            
        except Exception as e:
            logger.error(f"Failed to get queue statistics: {e}")
            return {}
    
    # Helper methods
    
    def calculate_estimated_completion(self, pending_reviews: List[Dict]) -> Dict[str, Any]:
        """Calculate estimated completion time for pending queue"""
        if not pending_reviews:
            return {'hours': 0, 'display': 'No pending reviews'}
        
        total_estimated_hours = sum(
            review.get('estimated_review_time', 2) for review in pending_reviews
        )
        
        # Account for parallelization (can work on multiple at once)
        if len(pending_reviews) > 1:
            total_estimated_hours *= 0.8  # 20% efficiency gain from batch processing
        
        return {
            'hours': round(total_estimated_hours, 1),
            'display': f"{round(total_estimated_hours, 1)} hours" if total_estimated_hours < 24 else f"{round(total_estimated_hours/24, 1)} days"
        }
    
    def estimate_review_time(self, file_count: int, total_size: int, priority: int) -> float:
        """Estimate review time based on course complexity"""
        base_time = 1.0  # 1 hour base
        
        # File count factor
        if file_count > 10:
            base_time += (file_count - 10) * 0.2
        elif file_count > 5:
            base_time += (file_count - 5) * 0.3
        
        # Size factor (every 100MB adds time)
        size_mb = total_size / (1024 * 1024) if total_size else 0
        base_time += size_mb / 100 * 0.5
        
        # Priority factor (higher priority = more thorough review)
        if priority > 3:
            base_time *= 1.5
        elif priority > 2:
            base_time *= 1.2
        
        return round(min(base_time, 8.0), 1)  # Cap at 8 hours
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        if not size_bytes:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{round(size_bytes, 1)} {unit}"
            size_bytes /= 1024
        return f"{round(size_bytes, 1)} TB"
    
    def get_priority_label(self, priority_level: int) -> str:
        """Convert priority level to label"""
        labels = {4: 'URGENT', 3: 'HIGH', 2: 'MEDIUM', 1: 'LOW'}
        return labels.get(priority_level, 'LOW')
    
    def get_action_color(self, status: str) -> str:
        """Get color code for activity status"""
        colors = {
            'approved': 'green',
            'rejected': 'red',
            'needs_revision': 'orange'
        }
        return colors.get(status, 'gray')
    
    def get_activity_level(self, reviews_30d: int) -> str:
        """Determine activity level based on 30-day reviews"""
        if reviews_30d >= 20:
            return 'Very Active'
        elif reviews_30d >= 10:
            return 'Active'
        elif reviews_30d >= 5:
            return 'Moderate'
        elif reviews_30d > 0:
            return 'Light'
        else:
            return 'Inactive'
    
    def calculate_efficiency_score(self, avg_time: float, reviews_count: int, approval_rate: float) -> int:
        """Calculate efficiency score out of 100"""
        if not reviews_count:
            return 0
        
        # Speed component (0-40 points) - faster is better
        speed_score = max(0, 40 - (avg_time - 2) * 2) if avg_time > 2 else 40
        
        # Volume component (0-30 points) - more reviews is better
        volume_score = min(30, reviews_count * 1.5)
        
        # Quality component (0-30 points) - balanced approval rate is better
        if 70 <= approval_rate <= 90:
            quality_score = 30
        elif 60 <= approval_rate < 70 or 90 < approval_rate <= 95:
            quality_score = 25
        elif approval_rate < 60 or approval_rate > 95:
            quality_score = 15
        else:
            quality_score = 20
        
        return min(100, int(speed_score + volume_score + quality_score))
    
    def get_reviewer_level(self, total_reviews: int) -> str:
        """Get reviewer level based on total reviews"""
        if total_reviews >= 100:
            return 'Expert'
        elif total_reviews >= 50:
            return 'Advanced'
        elif total_reviews >= 20:
            return 'Experienced'
        elif total_reviews >= 5:
            return 'Active'
        else:
            return 'New'
    
    def get_speed_rating(self, avg_time: float) -> str:
        """Get speed rating based on average review time"""
        if avg_time <= 2:
            return 'Very Fast'
        elif avg_time <= 4:
            return 'Fast'
        elif avg_time <= 8:
            return 'Average'
        elif avg_time <= 16:
            return 'Slow'
        else:
            return 'Very Slow'
    
    def get_consistency_rating(self, rate_30d: float, rate_all: float) -> str:
        """Get consistency rating comparing recent vs all-time rates"""
        if abs(rate_30d - rate_all) <= 5:
            return 'Very Consistent'
        elif abs(rate_30d - rate_all) <= 10:
            return 'Consistent'
        elif abs(rate_30d - rate_all) <= 20:
            return 'Somewhat Variable'
        else:
            return 'Variable'
    
    def get_default_metrics(self) -> Dict[str, Any]:
        """Return default metrics for new reviewers"""
        return {
            'last_30_days': {
                'reviews_completed': 0,
                'approval_rate': 0,
                'avg_review_time_hours': 0,
                'activity_level': 'New'
            },
            'all_time': {
                'total_reviews': 0,
                'approval_rate': 0,
                'avg_review_time_hours': 0,
                'median_review_time_hours': 0,
                'first_review_date': None
            },
            'performance_indicators': {
                'efficiency_score': 0,
                'reviewer_level': 'New',
                'speed_rating': 'Unrated',
                'consistency_rating': 'Unrated'
            }
        }
    
    async def get_review_guidelines(self, category: str) -> Dict[str, Any]:
        """Get review guidelines for specific course category"""
        try:
            guidelines = {
                'general': {
                    'checklist': [
                        'Content accuracy and educational value',
                        'File accessibility and quality',
                        'Appropriate difficulty level',
                        'Clear learning objectives',
                        'No inappropriate content'
                    ],
                    'time_estimate': '1-2 hours',
                    'focus_areas': ['Content Quality', 'Technical Review', 'Community Standards']
                },
                'tactics': {
                    'checklist': [
                        'Chess position accuracy',
                        'Solution correctness', 
                        'Progressive difficulty',
                        'Clear explanations',
                        'Tactical theme consistency'
                    ],
                    'time_estimate': '2-3 hours',
                    'focus_areas': ['Position Accuracy', 'Educational Value', 'Puzzle Quality']
                },
                'openings': {
                    'checklist': [
                        'Opening theory accuracy',
                        'Move sequence correctness',
                        'Variation completeness',
                        'Strategic explanations',
                        'Current theoretical relevance'
                    ],
                    'time_estimate': '2-4 hours',
                    'focus_areas': ['Theoretical Accuracy', 'Practical Value', 'Currency']
                }
            }
            
            return guidelines.get(category, guidelines['general'])
            
        except Exception as e:
            logger.error(f"Failed to get review guidelines: {e}")
            return guidelines.get('general', {})
    
    async def get_contributor_history(self, contributor_anonymous_id: str) -> Dict[str, Any]:
        """Get contributor's historical statistics for review context"""
        try:
            history_query = """
                SELECT 
                    COUNT(*) as total_submissions,
                    COUNT(*) FILTER (WHERE status = 'approved') as approved_count,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected_count,
                    AVG(rating) FILTER (WHERE rating IS NOT NULL) as avg_rating,
                    MIN(created_at) as first_submission
                FROM courses c
                JOIN users u ON c.contributor_id = u.id
                WHERE u.anonymous_id = $1
            """
            
            history_result = await supabase_client.execute_query(history_query, contributor_anonymous_id)
            if not history_result:
                return {'reputation': 'New Contributor'}
            
            history = history_result[0]
            
            total_submissions = history.get('total_submissions', 0)
            approved_count = history.get('approved_count', 0)
            
            # Calculate reputation
            if approved_count >= 25:
                reputation = 'Expert Contributor'
            elif approved_count >= 10:
                reputation = 'Verified Contributor'  
            elif approved_count >= 3:
                reputation = 'Regular Contributor'
            else:
                reputation = 'New Contributor'
            
            approval_rate = 0
            if total_submissions > 0:
                approval_rate = (approved_count / total_submissions) * 100
            
            return {
                'reputation': reputation,
                'total_submissions': total_submissions,
                'approval_rate': round(approval_rate, 1),
                'avg_rating': round(history.get('avg_rating', 0) or 0, 1),
                'first_submission': history.get('first_submission')
            }
            
        except Exception as e:
            logger.error(f"Failed to get contributor history: {e}")
            return {'reputation': 'Unknown'}
    
    async def get_workload_comparison(self, volunteer_id: str) -> Dict[str, Any]:
        """Compare volunteer's workload with other volunteers"""
        try:
            comparison_query = """
                WITH volunteer_workloads AS (
                    SELECT reviewer_id,
                           COUNT(*) FILTER (WHERE status = 'pending') as pending_count
                    FROM reviews
                    WHERE reviewer_id IS NOT NULL
                    GROUP BY reviewer_id
                )
                SELECT 
                    AVG(pending_count) as avg_workload,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pending_count) as median_workload,
                    MAX(pending_count) as max_workload,
                    MIN(pending_count) as min_workload,
                    (SELECT pending_count FROM volunteer_workloads WHERE reviewer_id = $1) as my_workload
                FROM volunteer_workloads
            """
            
            comparison_result = await supabase_client.execute_query(comparison_query, volunteer_id)
            if not comparison_result:
                return {}
            
            comparison = comparison_result[0]
            
            my_workload = comparison.get('my_workload', 0) or 0
            avg_workload = comparison.get('avg_workload', 0) or 0
            
            if avg_workload > 0:
                workload_ratio = my_workload / avg_workload
                if workload_ratio > 1.5:
                    workload_status = 'Above Average'
                elif workload_ratio > 1.2:
                    workload_status = 'Moderate'
                elif workload_ratio < 0.5:
                    workload_status = 'Light Load'
                else:
                    workload_status = 'Average'
            else:
                workload_status = 'No Data'
            
            return {
                'my_workload': my_workload,
                'avg_workload': round(avg_workload, 1),
                'median_workload': comparison.get('median_workload', 0) or 0,
                'workload_status': workload_status,
                'percentile': self.calculate_workload_percentile(
                    my_workload, 
                    comparison.get('min_workload', 0) or 0,
                    comparison.get('max_workload', 0) or 0
                )
            }
            
        except Exception as e:
            logger.error(f"Failed to get workload comparison: {e}")
            return {}
    
    def calculate_workload_percentile(self, my_workload: int, min_workload: int, max_workload: int) -> int:
        """Calculate workload percentile"""
        if max_workload == min_workload:
            return 50
        
        percentile = ((my_workload - min_workload) / (max_workload - min_workload)) * 100
        return max(0, min(100, int(percentile)))

# Global instance
volunteer_dashboard = VolunteerDashboard()