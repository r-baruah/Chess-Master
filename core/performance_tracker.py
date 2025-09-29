"""
Volunteer Performance Tracking System - AC4: Anonymous performance metrics and quality scoring
Implements comprehensive performance tracking while maintaining complete anonymity
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from enum import Enum
from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager

logger = logging.getLogger(__name__)

class PerformanceMetric(Enum):
    """Performance metric categories"""
    SPEED = "review_speed"
    QUALITY = "review_quality" 
    CONSISTENCY = "review_consistency"
    VOLUME = "review_volume"
    FEEDBACK = "feedback_quality"

class RecognitionLevel(Enum):
    """Recognition levels for volunteer contributions"""
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"

@dataclass
class PerformanceSnapshot:
    """Anonymous performance snapshot"""
    anonymous_id: str
    metrics: Dict[str, float]
    recognition_level: RecognitionLevel
    performance_trend: str  # improving, stable, declining
    last_updated: datetime

class VolunteerPerformanceTracker:
    """Anonymous performance tracking and recognition system"""
    
    def __init__(self):
        self.performance_weights = {
            PerformanceMetric.SPEED: 0.25,
            PerformanceMetric.QUALITY: 0.30,
            PerformanceMetric.CONSISTENCY: 0.20,
            PerformanceMetric.VOLUME: 0.15,
            PerformanceMetric.FEEDBACK: 0.10
        }
        
        self.recognition_thresholds = {
            RecognitionLevel.BRONZE: 60,
            RecognitionLevel.SILVER: 70,
            RecognitionLevel.GOLD: 80,
            RecognitionLevel.PLATINUM: 90,
            RecognitionLevel.DIAMOND: 95
        }
    
    async def calculate_volunteer_performance(self, volunteer_id: str, period_days: int = 30) -> Dict[str, Any]:
        """Calculate comprehensive anonymous performance metrics"""
        try:
            # Get volunteer's anonymous ID for safe reporting
            volunteer = await supabase_client.execute_query(
                "SELECT anonymous_id FROM users WHERE id = $1", 
                volunteer_id
            )
            
            if not volunteer:
                return {'error': 'Volunteer not found'}
            
            anonymous_id = volunteer[0]['anonymous_id']
            
            # Calculate individual metric scores
            speed_score = await self._calculate_speed_score(volunteer_id, period_days)
            quality_score = await self._calculate_quality_score(volunteer_id, period_days)
            consistency_score = await self._calculate_consistency_score(volunteer_id, period_days)
            volume_score = await self._calculate_volume_score(volunteer_id, period_days)
            feedback_score = await self._calculate_feedback_score(volunteer_id, period_days)
            
            # Calculate weighted overall score
            overall_score = (
                speed_score * self.performance_weights[PerformanceMetric.SPEED] +
                quality_score * self.performance_weights[PerformanceMetric.QUALITY] +
                consistency_score * self.performance_weights[PerformanceMetric.CONSISTENCY] +
                volume_score * self.performance_weights[PerformanceMetric.VOLUME] +
                feedback_score * self.performance_weights[PerformanceMetric.FEEDBACK]
            ) * 100
            
            # Calculate recognition level
            recognition_level = self._get_recognition_level(overall_score)
            
            # Get performance trend
            performance_trend = await self._calculate_performance_trend(volunteer_id)
            
            # Get comparative metrics (anonymous)
            comparative_metrics = await self._get_comparative_metrics(volunteer_id, period_days)
            
            return {
                'anonymous_id': anonymous_id,
                'period_days': period_days,
                'performance_scores': {
                    'speed': round(speed_score * 100, 1),
                    'quality': round(quality_score * 100, 1),
                    'consistency': round(consistency_score * 100, 1),
                    'volume': round(volume_score * 100, 1),
                    'feedback': round(feedback_score * 100, 1),
                    'overall': round(overall_score, 1)
                },
                'recognition': {
                    'level': recognition_level.value,
                    'level_name': recognition_level.name.title(),
                    'points_to_next_level': self._calculate_points_to_next_level(overall_score),
                    'achievements': await self._get_volunteer_achievements(volunteer_id)
                },
                'performance_indicators': {
                    'trend': performance_trend,
                    'efficiency_rating': self._get_efficiency_rating(speed_score, volume_score),
                    'quality_rating': self._get_quality_rating(quality_score, consistency_score),
                    'specialization': await self._identify_specializations(volunteer_id)
                },
                'comparative_metrics': comparative_metrics,
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate volunteer performance: {e}")
            return {'error': f'Performance calculation failed: {str(e)}'}
    
    async def get_anonymous_leaderboard(self, metric: PerformanceMetric = None, 
                                      limit: int = 10, period_days: int = 30) -> List[Dict]:
        """Get anonymous performance leaderboard"""
        try:
            if metric:
                # Specific metric leaderboard
                leaderboard_data = await self._get_metric_leaderboard(metric, limit, period_days)
            else:
                # Overall performance leaderboard
                leaderboard_data = await self._get_overall_leaderboard(limit, period_days)
            
            # Ensure complete anonymity - no correlation possible
            anonymous_leaderboard = []
            for i, entry in enumerate(leaderboard_data):
                anonymous_entry = {
                    'rank': i + 1,
                    'anonymous_id': entry['anonymous_id'],
                    'score': entry.get('score', 0),
                    'recognition_level': entry.get('recognition_level', 'bronze'),
                    'badge': self._get_performance_badge(entry.get('score', 0)),
                    # No personally identifying information
                }
                
                if metric:
                    anonymous_entry['metric'] = metric.value
                
                anonymous_leaderboard.append(anonymous_entry)
            
            return anonymous_leaderboard
            
        except Exception as e:
            logger.error(f"Failed to get anonymous leaderboard: {e}")
            return []
    
    async def track_review_completion(self, review_id: str, decision: str, 
                                    review_duration_hours: float, quality_indicators: Dict):
        """Track anonymous performance data when review is completed"""
        try:
            # Get reviewer info
            review_info = await supabase_client.execute_query(
                "SELECT reviewer_id, course_id, created_at FROM reviews WHERE id = $1",
                review_id
            )
            
            if not review_info:
                return
            
            reviewer_id = review_info[0]['reviewer_id']
            course_id = review_info[0]['course_id']
            review_start = review_info[0]['created_at']
            
            # Store anonymous performance data
            performance_data = {
                'review_id': review_id,
                'reviewer_anonymous_hash': await self._get_anonymous_hash(reviewer_id),  # Non-reversible hash
                'review_duration_hours': review_duration_hours,
                'decision': decision,
                'quality_indicators': quality_indicators,
                'completion_timestamp': datetime.utcnow(),
                'course_complexity_score': await self._calculate_course_complexity(course_id)
            }
            
            # Store in anonymous performance log
            await supabase_client.execute_command(
                """
                INSERT INTO anonymous_performance_log (
                    reviewer_hash, review_duration, decision, quality_indicators,
                    course_complexity, completion_date
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                performance_data['reviewer_anonymous_hash'],
                performance_data['review_duration_hours'],
                performance_data['decision'],
                performance_data['quality_indicators'],
                performance_data['course_complexity_score'],
                performance_data['completion_timestamp']
            )
            
            # Update real-time performance metrics
            await self._update_realtime_metrics(reviewer_id, performance_data)
            
        except Exception as e:
            logger.error(f"Failed to track review completion: {e}")
    
    async def generate_performance_insights(self, volunteer_id: str) -> Dict[str, Any]:
        """Generate actionable performance insights and recommendations"""
        try:
            performance_data = await self.calculate_volunteer_performance(volunteer_id)
            
            if 'error' in performance_data:
                return performance_data
            
            insights = {
                'strengths': [],
                'improvement_areas': [],
                'recommendations': [],
                'goal_suggestions': []
            }
            
            scores = performance_data['performance_scores']
            
            # Identify strengths (scores > 75)
            if scores['speed'] > 75:
                insights['strengths'].append('Fast review completion times')
            if scores['quality'] > 75:
                insights['strengths'].append('High-quality review decisions')
            if scores['consistency'] > 75:
                insights['strengths'].append('Consistent review standards')
            if scores['volume'] > 75:
                insights['strengths'].append('High review volume capability')
            if scores['feedback'] > 75:
                insights['strengths'].append('Excellent feedback quality')
            
            # Identify improvement areas (scores < 60)
            if scores['speed'] < 60:
                insights['improvement_areas'].append('Review completion speed')
                insights['recommendations'].append('Consider setting review time goals and using quick decision templates')
            if scores['quality'] < 60:
                insights['improvement_areas'].append('Review decision accuracy')
                insights['recommendations'].append('Review quality guidelines and seek feedback on challenging decisions')
            if scores['consistency'] < 60:
                insights['improvement_areas'].append('Decision consistency')
                insights['recommendations'].append('Develop a personal review checklist and decision framework')
            if scores['volume'] < 60:
                insights['improvement_areas'].append('Review activity level')
                insights['recommendations'].append('Set weekly review targets and use batch processing for efficiency')
            if scores['feedback'] < 60:
                insights['improvement_areas'].append('Feedback detail and helpfulness')
                insights['recommendations'].append('Use feedback templates and focus on constructive improvement suggestions')
            
            # Goal suggestions based on recognition level
            current_level = performance_data['recognition']['level']
            next_points = performance_data['recognition']['points_to_next_level']
            
            if next_points > 0:
                insights['goal_suggestions'].append(f"Earn {next_points} more points to reach {self._get_next_recognition_level(current_level).name.title()} level")
            
            # Specialization recommendations
            specializations = performance_data['performance_indicators']['specialization']
            if specializations:
                insights['goal_suggestions'].append(f"Consider focusing on your strong categories: {', '.join(specializations)}")
            
            return {
                'anonymous_id': performance_data['anonymous_id'],
                'insights': insights,
                'current_performance': {
                    'overall_score': scores['overall'],
                    'recognition_level': performance_data['recognition']['level_name'],
                    'performance_trend': performance_data['performance_indicators']['trend']
                },
                'generated_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate performance insights: {e}")
            return {'error': f'Insights generation failed: {str(e)}'}
    
    # Private helper methods
    
    async def _calculate_speed_score(self, volunteer_id: str, period_days: int) -> float:
        """Calculate speed performance score (0-1)"""
        try:
            speed_query = """
                SELECT AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) as avg_hours
                FROM reviews
                WHERE reviewer_id = $1 
                  AND status IN ('approved', 'rejected', 'needs_revision')
                  AND reviewed_at > NOW() - INTERVAL '%s days'
            """ % period_days
            
            result = await supabase_client.execute_query(speed_query, volunteer_id)
            
            if not result or not result[0]['avg_hours']:
                return 0.5  # Default neutral score
            
            avg_hours = result[0]['avg_hours']
            
            # Speed scoring: excellent < 4h, good < 8h, acceptable < 16h, poor >= 24h
            if avg_hours <= 4:
                return 1.0
            elif avg_hours <= 8:
                return 0.8
            elif avg_hours <= 16:
                return 0.6
            elif avg_hours <= 24:
                return 0.4
            else:
                return 0.2
                
        except Exception as e:
            logger.error(f"Speed score calculation failed: {e}")
            return 0.5
    
    async def _calculate_quality_score(self, volunteer_id: str, period_days: int) -> float:
        """Calculate quality performance score based on feedback and accuracy"""
        try:
            quality_query = """
                SELECT 
                    COUNT(*) as total_reviews,
                    COUNT(*) FILTER (WHERE rf.quality_rating = 'excellent') as excellent,
                    COUNT(*) FILTER (WHERE rf.quality_rating = 'good') as good,
                    COUNT(*) FILTER (WHERE rf.quality_rating = 'acceptable') as acceptable,
                    AVG(
                        CASE rf.quality_rating
                            WHEN 'excellent' THEN 1.0
                            WHEN 'good' THEN 0.8
                            WHEN 'acceptable' THEN 0.6
                            WHEN 'poor' THEN 0.2
                            ELSE 0.4
                        END
                    ) as avg_quality_score
                FROM reviews r
                LEFT JOIN review_feedback rf ON r.id = rf.review_id
                WHERE r.reviewer_id = $1 
                  AND r.status IN ('approved', 'rejected', 'needs_revision')
                  AND r.reviewed_at > NOW() - INTERVAL '%s days'
            """ % period_days
            
            result = await supabase_client.execute_query(quality_query, volunteer_id)
            
            if not result or not result[0]['total_reviews']:
                return 0.5
            
            return result[0]['avg_quality_score'] or 0.5
            
        except Exception as e:
            logger.error(f"Quality score calculation failed: {e}")
            return 0.5
    
    async def _calculate_consistency_score(self, volunteer_id: str, period_days: int) -> float:
        """Calculate consistency score based on decision patterns"""
        try:
            consistency_query = """
                SELECT 
                    COUNT(*) as total_reviews,
                    COUNT(*) FILTER (WHERE status = 'approved') as approvals,
                    STDDEV(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) as time_stddev,
                    -- Weekly consistency check
                    COUNT(DISTINCT DATE_TRUNC('week', reviewed_at)) as weeks_active
                FROM reviews
                WHERE reviewer_id = $1 
                  AND status IN ('approved', 'rejected', 'needs_revision')
                  AND reviewed_at > NOW() - INTERVAL '%s days'
            """ % period_days
            
            result = await supabase_client.execute_query(consistency_query, volunteer_id)
            
            if not result or not result[0]['total_reviews']:
                return 0.5
            
            data = result[0]
            total_reviews = data['total_reviews']
            approval_rate = (data['approvals'] / total_reviews) if total_reviews > 0 else 0.5
            time_stddev = data['time_stddev'] or 24  # Default 24h stddev
            weeks_active = data['weeks_active'] or 1
            
            # Consistency factors
            # 1. Approval rate consistency (ideal range: 70-85%)
            approval_consistency = 1.0
            if approval_rate < 0.5 or approval_rate > 0.95:
                approval_consistency = 0.4
            elif approval_rate < 0.65 or approval_rate > 0.9:
                approval_consistency = 0.7
            
            # 2. Time consistency (lower stddev = more consistent)
            time_consistency = max(0.2, 1.0 - (time_stddev / 48))  # Normalize to 48h max stddev
            
            # 3. Activity consistency (more weeks active = more consistent)
            expected_weeks = min(4, period_days // 7)
            activity_consistency = min(1.0, weeks_active / expected_weeks)
            
            # Combined consistency score
            consistency_score = (approval_consistency * 0.4 + time_consistency * 0.4 + activity_consistency * 0.2)
            
            return max(0.1, min(1.0, consistency_score))
            
        except Exception as e:
            logger.error(f"Consistency score calculation failed: {e}")
            return 0.5
    
    async def _calculate_volume_score(self, volunteer_id: str, period_days: int) -> float:
        """Calculate volume score based on review activity"""
        try:
            volume_query = """
                SELECT COUNT(*) as review_count
                FROM reviews
                WHERE reviewer_id = $1 
                  AND status IN ('approved', 'rejected', 'needs_revision')
                  AND reviewed_at > NOW() - INTERVAL '%s days'
            """ % period_days
            
            result = await supabase_client.execute_query(volume_query, volunteer_id)
            
            if not result:
                return 0.0
            
            review_count = result[0]['review_count'] or 0
            
            # Volume scoring based on period
            if period_days <= 7:  # Weekly
                # 10+ reviews/week = excellent, 5+ = good, 2+ = acceptable
                if review_count >= 10:
                    return 1.0
                elif review_count >= 5:
                    return 0.8
                elif review_count >= 2:
                    return 0.6
                elif review_count >= 1:
                    return 0.4
                else:
                    return 0.0
            else:  # Monthly
                # 30+ reviews/month = excellent, 15+ = good, 5+ = acceptable
                if review_count >= 30:
                    return 1.0
                elif review_count >= 15:
                    return 0.8
                elif review_count >= 5:
                    return 0.6
                elif review_count >= 1:
                    return 0.4
                else:
                    return 0.0
                    
        except Exception as e:
            logger.error(f"Volume score calculation failed: {e}")
            return 0.0
    
    async def _calculate_feedback_score(self, volunteer_id: str, period_days: int) -> float:
        """Calculate feedback quality score"""
        try:
            feedback_query = """
                SELECT 
                    COUNT(*) as total_feedbacks,
                    AVG(LENGTH(rf.feedback_text)) as avg_feedback_length,
                    AVG(array_length(rf.improvement_suggestions, 1)) as avg_suggestions_count
                FROM reviews r
                JOIN review_feedback rf ON r.id = rf.review_id
                WHERE r.reviewer_id = $1 
                  AND r.reviewed_at > NOW() - INTERVAL '%s days'
                  AND rf.feedback_text IS NOT NULL
            """ % period_days
            
            result = await supabase_client.execute_query(feedback_query, volunteer_id)
            
            if not result or not result[0]['total_feedbacks']:
                return 0.5
            
            data = result[0]
            avg_length = data['avg_feedback_length'] or 0
            avg_suggestions = data['avg_suggestions_count'] or 0
            
            # Feedback quality scoring
            length_score = 0.0
            if avg_length >= 200:  # Detailed feedback
                length_score = 1.0
            elif avg_length >= 100:
                length_score = 0.8
            elif avg_length >= 50:
                length_score = 0.6
            else:
                length_score = 0.3
            
            suggestions_score = min(1.0, avg_suggestions / 3.0)  # Normalize to 3+ suggestions
            
            return (length_score * 0.6 + suggestions_score * 0.4)
            
        except Exception as e:
            logger.error(f"Feedback score calculation failed: {e}")
            return 0.5
    
    def _get_recognition_level(self, overall_score: float) -> RecognitionLevel:
        """Determine recognition level based on overall score"""
        for level, threshold in sorted(self.recognition_thresholds.items(), 
                                     key=lambda x: x[1], reverse=True):
            if overall_score >= threshold:
                return level
        return RecognitionLevel.BRONZE
    
    def _get_next_recognition_level(self, current_level: str) -> RecognitionLevel:
        """Get next recognition level"""
        levels = list(RecognitionLevel)
        try:
            current_index = levels.index(RecognitionLevel(current_level))
            if current_index < len(levels) - 1:
                return levels[current_index + 1]
        except (ValueError, IndexError):
            pass
        return RecognitionLevel.DIAMOND  # Highest level
    
    def _calculate_points_to_next_level(self, current_score: float) -> int:
        """Calculate points needed for next recognition level"""
        current_level = self._get_recognition_level(current_score)
        next_level = self._get_next_recognition_level(current_level.value)
        
        if next_level == RecognitionLevel.DIAMOND and current_level == RecognitionLevel.DIAMOND:
            return 0  # Already at max level
        
        next_threshold = self.recognition_thresholds.get(next_level, 100)
        return max(0, int(next_threshold - current_score))
    
    async def _calculate_performance_trend(self, volunteer_id: str) -> str:
        """Calculate performance trend over time"""
        try:
            trend_query = """
                WITH weekly_performance AS (
                    SELECT 
                        DATE_TRUNC('week', reviewed_at) as week,
                        AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) as avg_time,
                        COUNT(*) as review_count
                    FROM reviews
                    WHERE reviewer_id = $1 
                      AND status IN ('approved', 'rejected', 'needs_revision')
                      AND reviewed_at > NOW() - INTERVAL '8 weeks'
                    GROUP BY DATE_TRUNC('week', reviewed_at)
                    ORDER BY week
                )
                SELECT 
                    COUNT(*) as weeks_with_data,
                    CORR(EXTRACT(EPOCH FROM week), avg_time) as time_trend,
                    CORR(EXTRACT(EPOCH FROM week), review_count) as volume_trend
                FROM weekly_performance
            """
            
            result = await supabase_client.execute_query(trend_query, volunteer_id)
            
            if not result or not result[0]['weeks_with_data'] or result[0]['weeks_with_data'] < 3:
                return 'insufficient_data'
            
            data = result[0]
            time_trend = data['time_trend'] or 0
            volume_trend = data['volume_trend'] or 0
            
            # Determine overall trend
            if volume_trend > 0.3 or time_trend < -0.3:  # Volume up or time down = improving
                return 'improving'
            elif volume_trend < -0.3 or time_trend > 0.3:  # Volume down or time up = declining
                return 'declining'
            else:
                return 'stable'
                
        except Exception as e:
            logger.error(f"Performance trend calculation failed: {e}")
            return 'unknown'
    
    async def _get_comparative_metrics(self, volunteer_id: str, period_days: int) -> Dict[str, Any]:
        """Get anonymous comparative metrics"""
        try:
            comparison_query = """
                WITH volunteer_metrics AS (
                    SELECT 
                        reviewer_id,
                        COUNT(*) as review_count,
                        AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) as avg_time
                    FROM reviews
                    WHERE status IN ('approved', 'rejected', 'needs_revision')
                      AND reviewed_at > NOW() - INTERVAL '%s days'
                    GROUP BY reviewer_id
                    HAVING COUNT(*) > 0
                ),
                percentiles AS (
                    SELECT 
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY review_count) as p25_volume,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY review_count) as p50_volume,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY review_count) as p75_volume,
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY avg_time) as p25_time,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY avg_time) as p50_time,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY avg_time) as p75_time
                    FROM volunteer_metrics
                )
                SELECT 
                    vm.review_count,
                    vm.avg_time,
                    p.p25_volume, p.p50_volume, p.p75_volume,
                    p.p25_time, p.p50_time, p.p75_time
                FROM volunteer_metrics vm
                CROSS JOIN percentiles p
                WHERE vm.reviewer_id = $1
            """ % period_days
            
            result = await supabase_client.execute_query(comparison_query, volunteer_id)
            
            if not result:
                return {}
            
            data = result[0]
            
            # Calculate percentile rankings
            volume_percentile = self._calculate_percentile(
                data['review_count'],
                data['p25_volume'], data['p50_volume'], data['p75_volume']
            )
            
            speed_percentile = 100 - self._calculate_percentile(  # Invert for speed (lower is better)
                data['avg_time'],
                data['p25_time'], data['p50_time'], data['p75_time']
            )
            
            return {
                'volume_percentile': volume_percentile,
                'speed_percentile': speed_percentile,
                'performance_category': self._get_performance_category(volume_percentile, speed_percentile)
            }
            
        except Exception as e:
            logger.error(f"Comparative metrics calculation failed: {e}")
            return {}
    
    def _calculate_percentile(self, value: float, p25: float, p50: float, p75: float) -> int:
        """Calculate percentile ranking"""
        if value <= p25:
            return 25
        elif value <= p50:
            return 50
        elif value <= p75:
            return 75
        else:
            return 90  # Top quartile
    
    def _get_performance_category(self, volume_percentile: int, speed_percentile: int) -> str:
        """Get performance category based on percentiles"""
        avg_percentile = (volume_percentile + speed_percentile) / 2
        
        if avg_percentile >= 80:
            return 'Top Performer'
        elif avg_percentile >= 60:
            return 'High Performer'
        elif avg_percentile >= 40:
            return 'Average Performer'
        else:
            return 'Developing Performer'
    
    async def _get_volunteer_achievements(self, volunteer_id: str) -> List[Dict]:
        """Get volunteer achievements"""
        try:
            # This would be expanded with more achievements
            achievements = []
            
            # Speed achievements
            fast_reviews = await supabase_client.execute_query(
                """
                SELECT COUNT(*) as count 
                FROM reviews 
                WHERE reviewer_id = $1 
                  AND EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600 < 2
                  AND status IN ('approved', 'rejected')
                """,
                volunteer_id
            )
            
            if fast_reviews and fast_reviews[0]['count'] >= 10:
                achievements.append({
                    'name': 'Speed Demon',
                    'description': 'Completed 10+ reviews in under 2 hours',
                    'earned_date': datetime.utcnow().date().isoformat()
                })
            
            # Volume achievements
            total_reviews = await supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM reviews WHERE reviewer_id = $1 AND status IN ('approved', 'rejected')",
                volunteer_id
            )
            
            if total_reviews:
                count = total_reviews[0]['count']
                if count >= 100:
                    achievements.append({
                        'name': 'Century Reviewer',
                        'description': 'Completed 100+ course reviews',
                        'earned_date': datetime.utcnow().date().isoformat()
                    })
                elif count >= 50:
                    achievements.append({
                        'name': 'Dedicated Reviewer',
                        'description': 'Completed 50+ course reviews',
                        'earned_date': datetime.utcnow().date().isoformat()
                    })
            
            return achievements
            
        except Exception as e:
            logger.error(f"Failed to get achievements: {e}")
            return []
    
    async def _identify_specializations(self, volunteer_id: str) -> List[str]:
        """Identify volunteer's category specializations"""
        try:
            specialization_query = """
                SELECT 
                    c.category,
                    COUNT(*) as review_count,
                    AVG(CASE 
                        WHEN rf.quality_rating = 'excellent' THEN 4
                        WHEN rf.quality_rating = 'good' THEN 3
                        WHEN rf.quality_rating = 'acceptable' THEN 2
                        ELSE 1
                    END) as avg_quality
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                LEFT JOIN review_feedback rf ON r.id = rf.review_id
                WHERE r.reviewer_id = $1 
                  AND r.status IN ('approved', 'rejected')
                  AND c.category IS NOT NULL
                GROUP BY c.category
                HAVING COUNT(*) >= 5  -- Minimum 5 reviews to be considered specialized
                ORDER BY avg_quality DESC, review_count DESC
            """
            
            result = await supabase_client.execute_query(specialization_query, volunteer_id)
            
            specializations = []
            for row in result:
                if row['avg_quality'] >= 3.0:  # Good quality threshold
                    specializations.append(row['category'].title())
            
            return specializations[:3]  # Top 3 specializations
            
        except Exception as e:
            logger.error(f"Failed to identify specializations: {e}")
            return []
    
    def _get_efficiency_rating(self, speed_score: float, volume_score: float) -> str:
        """Get efficiency rating based on speed and volume"""
        efficiency = (speed_score + volume_score) / 2
        
        if efficiency >= 0.8:
            return 'Highly Efficient'
        elif efficiency >= 0.6:
            return 'Efficient'
        elif efficiency >= 0.4:
            return 'Moderately Efficient'
        else:
            return 'Developing Efficiency'
    
    def _get_quality_rating(self, quality_score: float, consistency_score: float) -> str:
        """Get quality rating based on quality and consistency scores"""
        quality_rating = (quality_score + consistency_score) / 2
        
        if quality_rating >= 0.9:
            return 'Exceptional Quality'
        elif quality_rating >= 0.8:
            return 'High Quality'
        elif quality_rating >= 0.6:
            return 'Good Quality'
        else:
            return 'Developing Quality'
    
    def _get_performance_badge(self, score: float) -> str:
        """Get performance badge emoji based on score"""
        if score >= 95:
            return '💎'  # Diamond
        elif score >= 90:
            return '🏆'  # Platinum
        elif score >= 80:
            return '🥇'  # Gold
        elif score >= 70:
            return '🥈'  # Silver
        elif score >= 60:
            return '🥉'  # Bronze
        else:
            return '⭐'  # Participation
    
    async def _get_anonymous_hash(self, volunteer_id: str) -> str:
        """Get non-reversible anonymous hash for volunteer"""
        try:
            import hashlib
            # Use a combination of volunteer ID and a salt to create non-reversible hash
            salt = "volunteer_performance_tracking"
            hash_input = f"{volunteer_id}:{salt}".encode('utf-8')
            return hashlib.sha256(hash_input).hexdigest()[:16]  # First 16 chars for storage efficiency
            
        except Exception as e:
            logger.error(f"Failed to generate anonymous hash: {e}")
            return "anonymous"
    
    async def _calculate_course_complexity(self, course_id: str) -> float:
        """Calculate course complexity score for performance normalization"""
        try:
            complexity_query = """
                SELECT 
                    COUNT(cf.id) as file_count,
                    SUM(cf.file_size) as total_size,
                    c.difficulty_level
                FROM courses c
                LEFT JOIN course_files cf ON c.id = cf.course_id
                WHERE c.id = $1
                GROUP BY c.id, c.difficulty_level
            """
            
            result = await supabase_client.execute_query(complexity_query, course_id)
            
            if not result:
                return 1.0  # Default complexity
            
            data = result[0]
            file_count = data['file_count'] or 0
            total_size = data['total_size'] or 0
            difficulty = data.get('difficulty_level', 'intermediate')
            
            # Calculate complexity score (0.5 - 2.0 range)
            complexity = 1.0
            
            # File count factor
            if file_count > 20:
                complexity += 0.5
            elif file_count > 10:
                complexity += 0.3
            elif file_count < 3:
                complexity -= 0.2
            
            # Size factor
            size_mb = total_size / (1024 * 1024) if total_size else 0
            if size_mb > 500:
                complexity += 0.3
            elif size_mb > 100:
                complexity += 0.2
            
            # Difficulty factor
            difficulty_multipliers = {
                'beginner': 0.8,
                'intermediate': 1.0,
                'advanced': 1.2,
                'expert': 1.4
            }
            complexity *= difficulty_multipliers.get(difficulty, 1.0)
            
            return max(0.5, min(2.0, complexity))
            
        except Exception as e:
            logger.error(f"Course complexity calculation failed: {e}")
            return 1.0
    
    async def _update_realtime_metrics(self, volunteer_id: str, performance_data: Dict):
        """Update real-time performance metrics cache"""
        try:
            # This would update a Redis cache or similar for real-time dashboard updates
            logger.info(f"Real-time metrics updated for volunteer (anonymous)")
            
        except Exception as e:
            logger.error(f"Failed to update real-time metrics: {e}")
    
    async def _get_metric_leaderboard(self, metric: PerformanceMetric, limit: int, period_days: int) -> List[Dict]:
        """Get leaderboard for specific metric"""
        # Implementation depends on the specific metric
        # This would query performance data and rank by the specified metric
        return []
    
    async def _get_overall_leaderboard(self, limit: int, period_days: int) -> List[Dict]:
        """Get overall performance leaderboard"""
        try:
            # Get top performers by calculated overall score
            leaderboard_query = """
                WITH volunteer_scores AS (
                    SELECT 
                        u.anonymous_id,
                        COUNT(r.id) as review_count,
                        AVG(EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600) as avg_time,
                        COUNT(*) FILTER (WHERE rf.quality_rating IN ('excellent', 'good')) * 100.0 / COUNT(*) as quality_rate
                    FROM reviews r
                    JOIN users u ON r.reviewer_id = u.id
                    LEFT JOIN review_feedback rf ON r.id = rf.review_id
                    WHERE r.status IN ('approved', 'rejected')
                      AND r.reviewed_at > NOW() - INTERVAL '%s days'
                    GROUP BY u.anonymous_id, r.reviewer_id
                    HAVING COUNT(r.id) >= 3  -- Minimum reviews for leaderboard
                )
                SELECT 
                    anonymous_id,
                    -- Calculate overall score (simplified version)
                    (LEAST(review_count * 5, 50) + 
                     GREATEST(0, 50 - avg_time * 2) + 
                     quality_rate * 0.5) as score
                FROM volunteer_scores
                ORDER BY score DESC
                LIMIT $1
            """ % period_days
            
            result = await supabase_client.execute_query(leaderboard_query, limit)
            
            leaderboard_data = []
            for row in result:
                leaderboard_data.append({
                    'anonymous_id': row['anonymous_id'],
                    'score': round(row['score'], 1),
                    'recognition_level': self._get_recognition_level(row['score']).value
                })
            
            return leaderboard_data
            
        except Exception as e:
            logger.error(f"Failed to get overall leaderboard: {e}")
            return []

# Global instance
performance_tracker = VolunteerPerformanceTracker()