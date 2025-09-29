"""
Volunteer Assignment Distribution System for Course Review Management
Implements AC5: Volunteer Assignment Distribution System from Story 1.3
"""
import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager
from core.redis_state import redis_state

logger = logging.getLogger(__name__)

class VolunteerAssignmentManager:
    """Manages volunteer reviewer assignment and workload distribution"""
    
    def __init__(self):
        self.assignment_weights = {
            'workload_factor': 0.6,      # 60% weight to current workload
            'performance_factor': 0.3,    # 30% weight to performance score
            'availability_factor': 0.1    # 10% weight to availability
        }
    
    async def get_available_volunteers(self) -> List[Dict[str, Any]]:
        """Get list of available volunteer reviewers with their metrics"""
        try:
            # Get all volunteer reviewers
            volunteers_query = """
                SELECT u.id, u.anonymous_id, u.role, u.permissions,
                       COUNT(r.id) FILTER (WHERE r.status = 'pending') as current_workload,
                       COUNT(r.id) FILTER (WHERE r.status = 'completed' AND r.reviewed_at > NOW() - INTERVAL '30 days') as reviews_last_30_days,
                       AVG(EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600) as avg_review_time_hours
                FROM users u
                LEFT JOIN reviews r ON u.id = r.reviewer_id
                WHERE u.role = 'volunteer_reviewer' 
                AND u.permissions->>'approve_courses' = 'true'
                GROUP BY u.id, u.anonymous_id, u.role, u.permissions
            """
            
            volunteers = await supabase_client.execute_query(volunteers_query)
            
            # Calculate performance scores
            enriched_volunteers = []
            for volunteer in volunteers:
                performance_score = await self._calculate_performance_score(volunteer)
                volunteer['performance_score'] = performance_score
                volunteer['availability_score'] = await self._calculate_availability_score(volunteer)
                enriched_volunteers.append(volunteer)
            
            return enriched_volunteers
            
        except Exception as e:
            logger.error(f"Failed to get available volunteers: {e}")
            return []
    
    async def _calculate_performance_score(self, volunteer: Dict) -> float:
        """Calculate performance score based on review metrics"""
        try:
            # Base score starts at 50
            score = 50.0
            
            # Bonus for recent activity (up to +30 points)
            reviews_last_30_days = volunteer.get('reviews_last_30_days', 0)
            if reviews_last_30_days > 0:
                activity_bonus = min(30, reviews_last_30_days * 2)  # 2 points per review, max 30
                score += activity_bonus
            
            # Penalty for slow review times (up to -20 points)
            avg_review_time = volunteer.get('avg_review_time_hours', 24)
            if avg_review_time:
                if avg_review_time > 48:  # Slower than 48 hours
                    time_penalty = min(20, (avg_review_time - 48) / 2)
                    score -= time_penalty
                elif avg_review_time < 24:  # Faster than 24 hours gets bonus
                    time_bonus = min(20, (24 - avg_review_time) / 2)
                    score += time_bonus
            
            # Ensure score stays within bounds
            return max(0, min(100, score))
            
        except Exception as e:
            logger.error(f"Error calculating performance score: {e}")
            return 50.0  # Default neutral score
    
    async def _calculate_availability_score(self, volunteer: Dict) -> float:
        """Calculate availability score based on current workload"""
        try:
            current_workload = volunteer.get('current_workload', 0)
            
            # Maximum recommended workload per volunteer
            max_workload = 10
            
            if current_workload >= max_workload:
                return 0.0  # No availability
            elif current_workload == 0:
                return 100.0  # Full availability
            else:
                # Linear decrease based on current workload
                return 100.0 * (1 - current_workload / max_workload)
                
        except Exception as e:
            logger.error(f"Error calculating availability score: {e}")
            return 50.0
    
    async def assign_course_to_reviewer(self, course_id: str, priority_level: int = 1, 
                                       preferred_categories: List[str] = None) -> Optional[str]:
        """
        Enhanced assignment with category preferences, load balancing and anonymous distribution
        Returns reviewer_id if successful, None if no volunteers available
        """
        try:
            volunteers = await self.get_available_volunteers()
            
            if not volunteers:
                logger.warning("No volunteer reviewers available")
                return None
            
            # Get course metadata for enhanced matching
            course_metadata = await self._get_course_metadata(course_id)
            
            # Filter out volunteers with no availability
            available_volunteers = [v for v in volunteers if v['availability_score'] > 0]
            
            if not available_volunteers:
                logger.warning("All volunteers at maximum workload")
                # Try workload rebalancing before giving up
                rebalance_result = await self.rebalance_workload()
                if rebalance_result:
                    # Retry after rebalancing
                    available_volunteers = [v for v in volunteers if v['availability_score'] > 0]
                
                if not available_volunteers:
                    return None
            
            # Enhanced assignment scoring with category preferences and load balancing
            scored_volunteers = []
            for volunteer in available_volunteers:
                assignment_score = await self._calculate_enhanced_assignment_score(
                    volunteer, 
                    course_metadata, 
                    priority_level,
                    preferred_categories
                )
                scored_volunteers.append({
                    **volunteer,
                    'assignment_score': assignment_score
                })
            
            # Sort by assignment score (highest first)
            scored_volunteers.sort(key=lambda v: v['assignment_score'], reverse=True)
            
            # Advanced selection with fairness consideration
            selected_volunteer = await self._select_volunteer_with_fairness(scored_volunteers)
            reviewer_id = selected_volunteer['id']
            
            # Create review assignment with enhanced metadata
            success = await self._create_review_assignment(
                course_id, 
                reviewer_id, 
                priority_level,
                selected_volunteer['anonymous_id'],
                course_metadata
            )
            
            if success:
                logger.info(f"Course {course_id} assigned to reviewer {selected_volunteer['anonymous_id']} "
                          f"(score: {selected_volunteer['assignment_score']:.2f})")
                return reviewer_id
            else:
                logger.error("Failed to create review assignment")
                return None
                
        except Exception as e:
            logger.error(f"Enhanced course assignment failed: {e}")
            return None
    
    def _calculate_assignment_score(self, volunteer: Dict) -> float:
        """Calculate weighted assignment score for volunteer selection"""
        try:
            workload_score = 100 - (volunteer['current_workload'] * 10)  # Less workload = higher score
            performance_score = volunteer['performance_score']
            availability_score = volunteer['availability_score']
            
            # Apply weights
            final_score = (
                workload_score * self.assignment_weights['workload_factor'] +
                performance_score * self.assignment_weights['performance_factor'] +
                availability_score * self.assignment_weights['availability_factor']
            )
            
            return max(0, min(100, final_score))
            
        except Exception as e:
            logger.error(f"Error calculating assignment score: {e}")
            return 0.0
    
    async def _create_review_assignment(self, course_id: str, reviewer_id: str, 
                                      priority_level: int, reviewer_anonymous_id: str, 
                                      course_metadata: Dict = None) -> bool:
        """Create enhanced review assignment with metadata"""
        try:
            assignment_query = """
                INSERT INTO reviews (course_id, reviewer_id, status, priority_level, 
                                   assignment_metadata, created_at)
                VALUES ($1, $2, 'pending', $3, $4, NOW())
                RETURNING id
            """
            
            # Include assignment metadata for analytics and fairness tracking
            assignment_metadata = {
                'assignment_method': 'automated',
                'course_category': course_metadata.get('category') if course_metadata else None,
                'workload_at_assignment': await self._get_volunteer_current_workload(reviewer_id),
                'assignment_timestamp': datetime.utcnow().isoformat(),
                'priority_level': priority_level,
                'channel': course_metadata.get('primary_channel') if course_metadata else None
            }
            
            result = await supabase_client.execute_query(
                assignment_query, 
                course_id, 
                reviewer_id, 
                priority_level,
                assignment_metadata
            )
            
            if result:
                review_id = result[0]['id']
                # Send enhanced notification to volunteer
                await self._notify_volunteer_assignment(reviewer_anonymous_id, course_id, review_id, assignment_metadata)
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to create enhanced review assignment: {e}")
            return False
    
    async def _get_course_metadata(self, course_id: str) -> Dict:
        """Get course metadata for enhanced assignment matching"""
        try:
            metadata_query = """
                SELECT c.category, c.difficulty_level, c.estimated_duration,
                       COUNT(cf.id) as file_count,
                       SUM(cf.file_size) as total_size,
                       cm.primary_channel_id as primary_channel,
                       u.anonymous_id as contributor_anonymous_id,
                       -- Get contributor reputation
                       COUNT(c2.id) FILTER (WHERE c2.status = 'approved') as contributor_approved_courses
                FROM courses c
                JOIN users u ON c.contributor_id = u.id
                LEFT JOIN course_files cf ON c.id = cf.course_id
                LEFT JOIN courses c2 ON c2.contributor_id = c.contributor_id
                LEFT JOIN course_channel_mapping cm ON c.id = cm.course_id AND cm.is_primary = TRUE
                WHERE c.id = $1
                GROUP BY c.id, c.category, c.difficulty_level, c.estimated_duration, u.anonymous_id, cm.primary_channel_id
            """
            
            result = await supabase_client.execute_query(metadata_query, course_id)
            if result:
                return result[0]
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get course metadata: {e}")
            return {}
    
    async def _calculate_enhanced_assignment_score(self, volunteer: Dict, course_metadata: Dict,
                                                 priority_level: int, preferred_categories: List[str] = None) -> float:
        """Calculate enhanced assignment score with category matching and fairness"""
        try:
            base_score = self._calculate_assignment_score(volunteer)
            
            # Category expertise bonus (up to +20 points)
            category_bonus = 0
            course_category = course_metadata.get('category')
            volunteer_preferences = volunteer.get('preferred_categories', [])
            
            if course_category and volunteer_preferences:
                if course_category in volunteer_preferences:
                    category_bonus = 20
                elif any(cat in volunteer_preferences for cat in (preferred_categories or [])):
                    category_bonus = 10
            
            # Experience bonus for specific course types (up to +15 points)
            experience_bonus = await self._calculate_experience_bonus(volunteer['id'], course_category)
            
            # Priority handling bonus (up to +10 points)
            priority_bonus = 0
            if priority_level > 2:  # High priority
                # Prefer volunteers with good speed ratings
                avg_review_time = volunteer.get('avg_review_time_hours', 24)
                if avg_review_time < 12:  # Fast reviewers
                    priority_bonus = 10
                elif avg_review_time < 24:
                    priority_bonus = 5
            
            # Fairness adjustment (up to ±10 points)
            fairness_adjustment = await self._calculate_fairness_adjustment(volunteer['id'])
            
            # Course complexity handling (up to +10 points)
            complexity_bonus = self._calculate_complexity_bonus(volunteer, course_metadata)
            
            final_score = (base_score + category_bonus + experience_bonus + 
                         priority_bonus + fairness_adjustment + complexity_bonus)
            
            return max(0, min(150, final_score))  # Cap at 150 points
            
        except Exception as e:
            logger.error(f"Error calculating enhanced assignment score: {e}")
            return 0.0
    
    async def _calculate_experience_bonus(self, volunteer_id: str, category: str) -> float:
        """Calculate experience bonus for specific category"""
        try:
            if not category:
                return 0
            
            experience_query = """
                SELECT COUNT(*) as category_reviews,
                       AVG(rf.quality_rating) as avg_quality
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                LEFT JOIN review_feedback rf ON r.id = rf.review_id
                WHERE r.reviewer_id = $1 AND c.category = $2 
                  AND r.status IN ('approved', 'rejected')
            """
            
            result = await supabase_client.execute_query(experience_query, volunteer_id, category)
            
            if result and result[0]['category_reviews']:
                category_reviews = result[0]['category_reviews']
                avg_quality = result[0]['avg_quality'] or 'good'
                
                # Base experience bonus
                experience_bonus = min(category_reviews * 2, 10)  # 2 points per review, max 10
                
                # Quality multiplier
                quality_multipliers = {
                    'excellent': 1.5,
                    'good': 1.2,
                    'acceptable': 1.0,
                    'poor': 0.8
                }
                
                experience_bonus *= quality_multipliers.get(avg_quality, 1.0)
                
                return min(15, experience_bonus)
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to calculate experience bonus: {e}")
            return 0
    
    async def _calculate_fairness_adjustment(self, volunteer_id: str) -> float:
        """Calculate fairness adjustment to promote equal distribution"""
        try:
            # Get recent assignment history (last 7 days)
            fairness_query = """
                SELECT 
                    COUNT(*) FILTER (WHERE r.created_at > NOW() - INTERVAL '7 days') as recent_assignments,
                    COUNT(*) FILTER (WHERE r.created_at > NOW() - INTERVAL '24 hours') as assignments_today
                FROM reviews r
                WHERE r.reviewer_id = $1
            """
            
            result = await supabase_client.execute_query(fairness_query, volunteer_id)
            
            if result:
                recent_assignments = result[0]['recent_assignments'] or 0
                assignments_today = result[0]['assignments_today'] or 0
                
                # Fairness adjustment - favor volunteers with fewer recent assignments
                fairness_adjustment = 0
                
                # Recent assignments penalty
                if recent_assignments > 10:  # Very active recently
                    fairness_adjustment -= 10
                elif recent_assignments > 5:  # Moderately active
                    fairness_adjustment -= 5
                elif recent_assignments < 2:  # Less active, give bonus
                    fairness_adjustment += 5
                
                # Daily assignment penalty
                if assignments_today > 3:
                    fairness_adjustment -= 5
                elif assignments_today == 0:
                    fairness_adjustment += 3
                
                return fairness_adjustment
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to calculate fairness adjustment: {e}")
            return 0
    
    def _calculate_complexity_bonus(self, volunteer: Dict, course_metadata: Dict) -> float:
        """Calculate bonus for handling complex courses"""
        try:
            complexity_bonus = 0
            
            # File count complexity
            file_count = course_metadata.get('file_count', 0)
            if file_count > 10:
                # Prefer experienced reviewers for complex courses
                total_reviews = volunteer.get('reviews_last_30_days', 0)
                if total_reviews > 15:  # Experienced reviewer
                    complexity_bonus += 5
                elif total_reviews > 5:
                    complexity_bonus += 2
            
            # File size complexity
            total_size = course_metadata.get('total_size', 0)
            if total_size and total_size > 100 * 1024 * 1024:  # > 100MB
                avg_review_time = volunteer.get('avg_review_time_hours', 24)
                if avg_review_time < 16:  # Efficient reviewer
                    complexity_bonus += 5
            
            # Contributor reputation factor
            contributor_approved = course_metadata.get('contributor_approved_courses', 0)
            if contributor_approved < 3:  # New contributor - needs experienced reviewer
                performance_score = volunteer.get('performance_score', 50)
                if performance_score > 80:
                    complexity_bonus += 5
                elif performance_score > 60:
                    complexity_bonus += 2
            
            return min(10, complexity_bonus)
            
        except Exception as e:
            logger.error(f"Failed to calculate complexity bonus: {e}")
            return 0
    
    async def _select_volunteer_with_fairness(self, scored_volunteers: List[Dict]) -> Dict:
        """Select volunteer with fairness consideration"""
        try:
            if not scored_volunteers:
                raise ValueError("No volunteers available")
            
            # If there's a clear leader (>10 point difference), select them
            if len(scored_volunteers) == 1 or (scored_volunteers[0]['assignment_score'] - scored_volunteers[1]['assignment_score']) > 10:
                return scored_volunteers[0]
            
            # Otherwise, use weighted random selection from top candidates
            top_candidates = []
            max_score = scored_volunteers[0]['assignment_score']
            
            # Include all candidates within 10 points of the max
            for volunteer in scored_volunteers:
                if volunteer['assignment_score'] >= max_score - 10:
                    top_candidates.append(volunteer)
                else:
                    break
            
            # Weighted random selection
            import random
            weights = [candidate['assignment_score'] for candidate in top_candidates]
            selected = random.choices(top_candidates, weights=weights, k=1)[0]
            
            logger.info(f"Selected volunteer from {len(top_candidates)} top candidates using weighted selection")
            return selected
            
        except Exception as e:
            logger.error(f"Volunteer selection with fairness failed: {e}")
            return scored_volunteers[0] if scored_volunteers else None
    
    async def _get_volunteer_current_workload(self, volunteer_id: str) -> int:
        """Get current workload count for volunteer"""
        try:
            result = await supabase_client.execute_query(
                "SELECT COUNT(*) as workload FROM reviews WHERE reviewer_id = $1 AND status = 'pending'",
                volunteer_id
            )
            return result[0]['workload'] if result else 0
            
        except Exception as e:
            logger.error(f"Failed to get volunteer workload: {e}")
            return 0
    
    async def _notify_volunteer_assignment(
        self,
        reviewer_anonymous_id: str,
        course_id: str,
        review_id: str,
        assignment_metadata: Dict[str, Any]
    ):
        """Send assignment notification to volunteer with Redis persistence"""
        try:
            if not reviewer_anonymous_id:
                logger.warning("Cannot notify volunteer without anonymous id")
                return

            notification = {
                "type": "assignment",
                "review_id": review_id,
                "course_id": course_id,
                "priority_level": assignment_metadata.get("priority_level"),
                "assigned_at": assignment_metadata.get("assignment_timestamp"),
                "channel": assignment_metadata.get("channel"),
                "message": (
                    "You have been assigned a new course review. "
                    f"Course ID: {course_id}, Review ID: {review_id}"
                )
            }

            await redis_state.redis_client.lpush(
                f"volunteer_notifications:{reviewer_anonymous_id}",
                json.dumps(notification)
            )

            # Store recent notifications for dashboard summary (trim to last 20)
            await redis_state.redis_client.ltrim(
                f"volunteer_notifications:{reviewer_anonymous_id}",
                0,
                19
            )

            # Temporary assignment cache for quick dashboard highlight
            await redis_state.redis_client.setex(
                f"volunteer_assignment_notice:{reviewer_anonymous_id}:{review_id}",
                3600,
                json.dumps(notification)
            )

            logger.info(
                "Volunteer %s notified for review %s (course %s)",
                reviewer_anonymous_id,
                review_id,
                course_id
            )

        except Exception as e:
            logger.error(f"Failed to notify volunteer: {e}")
    
    async def get_volunteer_queue(self, reviewer_id: str) -> List[Dict]:
        """Get pending review queue for specific volunteer"""
        try:
            queue_query = """
                SELECT r.id as review_id, c.id as course_id, c.title, c.description,
                       r.priority_level, r.created_at, 
                       COUNT(cf.id) as file_count
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                LEFT JOIN course_files cf ON c.id = cf.course_id
                WHERE r.reviewer_id = $1 AND r.status = 'pending'
                GROUP BY r.id, c.id, c.title, c.description, r.priority_level, r.created_at
                ORDER BY r.priority_level DESC, r.created_at ASC
            """
            
            queue = await supabase_client.execute_query(queue_query, reviewer_id)
            return queue or []
            
        except Exception as e:
            logger.error(f"Failed to get volunteer queue: {e}")
            return []
    
    async def get_assignment_statistics(self) -> Dict[str, Any]:
        """Get volunteer assignment and performance statistics"""
        try:
            stats_query = """
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_reviews,
                    COUNT(*) FILTER (WHERE status = 'completed') as completed_reviews,
                    COUNT(*) FILTER (WHERE status = 'rejected') as rejected_reviews,
                    AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) FILTER (WHERE status = 'completed') as avg_review_time_hours,
                    COUNT(DISTINCT reviewer_id) as active_reviewers
                FROM reviews
                WHERE created_at > NOW() - INTERVAL '30 days'
            """
            
            stats = await supabase_client.execute_query(stats_query)
            
            if stats:
                stat_data = stats[0]
                return {
                    'pending_reviews': stat_data.get('pending_reviews', 0),
                    'completed_reviews': stat_data.get('completed_reviews', 0),
                    'rejected_reviews': stat_data.get('rejected_reviews', 0),
                    'avg_review_time_hours': round(stat_data.get('avg_review_time_hours', 0) or 0, 2),
                    'active_reviewers': stat_data.get('active_reviewers', 0),
                    'approval_rate': self._calculate_approval_rate(stat_data)
                }
            
            return {
                'pending_reviews': 0,
                'completed_reviews': 0,
                'rejected_reviews': 0,
                'avg_review_time_hours': 0,
                'active_reviewers': 0,
                'approval_rate': 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get assignment statistics: {e}")
            return {}
    
    def _calculate_approval_rate(self, stats: Dict) -> float:
        """Calculate approval rate from statistics"""
        completed = stats.get('completed_reviews', 0)
        rejected = stats.get('rejected_reviews', 0)
        total_decisions = completed + rejected
        
        if total_decisions == 0:
            return 0.0
        
        return round((completed / total_decisions) * 100, 2)
    
    async def rebalance_workload(self) -> Dict[str, int]:
        """Rebalance pending reviews across volunteers if needed"""
        try:
            # Get volunteers with their current workload
            volunteers = await self.get_available_volunteers()
            
            if len(volunteers) < 2:
                return {}  # Need at least 2 volunteers to rebalance
            
            # Calculate average workload
            total_workload = sum(v['current_workload'] for v in volunteers)
            avg_workload = total_workload / len(volunteers)
            
            # Find volunteers with excessive workload (>150% of average)
            overloaded = [v for v in volunteers if v['current_workload'] > avg_workload * 1.5]
            underloaded = [v for v in volunteers if v['current_workload'] < avg_workload * 0.5]
            
            rebalanced = {}
            
            for overloaded_volunteer in overloaded:
                if not underloaded:
                    break
                
                # Move some reviews to underloaded volunteers
                excess_reviews = int(overloaded_volunteer['current_workload'] - avg_workload)
                
                for target_volunteer in underloaded[:]:
                    if excess_reviews <= 0:
                        break
                    
                    # Move reviews
                    moved_count = await self._move_pending_reviews(
                        overloaded_volunteer['id'], 
                        target_volunteer['id'], 
                        min(excess_reviews, 3)  # Move max 3 at a time
                    )
                    
                    if moved_count > 0:
                        excess_reviews -= moved_count
                        rebalanced[f"{overloaded_volunteer['anonymous_id']} -> {target_volunteer['anonymous_id']}"] = moved_count
                        
                        # Update target workload
                        target_volunteer['current_workload'] += moved_count
                        if target_volunteer['current_workload'] >= avg_workload * 0.8:
                            underloaded.remove(target_volunteer)
            
            return rebalanced
            
        except Exception as e:
            logger.error(f"Workload rebalancing failed: {e}")
            return {}
    
    async def _move_pending_reviews(self, from_reviewer_id: str, to_reviewer_id: str, count: int) -> int:
        """Move pending reviews between volunteers"""
        try:
            move_query = """
                UPDATE reviews 
                SET reviewer_id = $2, updated_at = NOW()
                WHERE id IN (
                    SELECT id FROM reviews 
                    WHERE reviewer_id = $1 AND status = 'pending'
                    ORDER BY priority_level DESC, created_at ASC
                    LIMIT $3
                )
            """
            
            await supabase_client.execute_command(move_query, from_reviewer_id, to_reviewer_id, count)
            return count
            
        except Exception as e:
            logger.error(f"Failed to move reviews: {e}")
            return 0

# Global instance
volunteer_manager = VolunteerAssignmentManager()