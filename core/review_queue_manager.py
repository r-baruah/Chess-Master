"""
Review Queue Management System

This module handles:
- Automatic review queue integration for submitted courses
- Status notifications to contributors
- Queue priority system based on contributor reputation
- Review assignment integration with volunteer workload distribution
- Escalation system for delayed reviews
- Anonymous feedback system for reviewer comments
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

from .supabase_client import SupabaseClient
try:
    from .volunteer_system import volunteer_manager
except ImportError:
    volunteer_manager = None
from .redis_state import RedisStateManager as RedisState

logger = logging.getLogger(__name__)

class ReviewStatus(Enum):
    """Review status enumeration"""
    PENDING_REVIEW = "pending_review"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    ESCALATED = "escalated"

class ReviewPriority(Enum):
    """Review priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class ReviewEntry:
    """Review queue entry structure"""
    course_id: str
    contributor_id: str
    status: ReviewStatus
    priority: ReviewPriority
    submitted_at: datetime
    assigned_reviewer: Optional[str] = None
    review_started_at: Optional[datetime] = None
    review_completed_at: Optional[datetime] = None
    feedback: Optional[str] = None
    escalation_count: int = 0
    estimated_completion: Optional[datetime] = None

class ReviewQueueManager:
    """Manages course review queue and status tracking"""
    
    def __init__(self, supabase_client: SupabaseClient, redis_client: RedisState):
        self.supabase = supabase_client
        self.redis = redis_client
        
        # Review configuration
        self.max_review_time = {
            ReviewPriority.LOW: timedelta(days=7),
            ReviewPriority.NORMAL: timedelta(days=5),
            ReviewPriority.HIGH: timedelta(days=3),
            ReviewPriority.URGENT: timedelta(days=1)
        }
        
        self.escalation_thresholds = {
            ReviewPriority.LOW: timedelta(days=10),
            ReviewPriority.NORMAL: timedelta(days=7),
            ReviewPriority.HIGH: timedelta(days=4),
            ReviewPriority.URGENT: timedelta(days=2)
        }
        
        # Reputation-based priority factors
        self.reputation_multipliers = {
            "new_contributor": 1.0,      # 0-2 courses
            "regular_contributor": 1.2,  # 3-9 courses
            "verified_contributor": 1.5, # 10-24 courses
            "expert_contributor": 2.0    # 25+ courses
        }
    
    async def submit_course_for_review(self, course_id: str, contributor_id: str, 
                                     priority_override: Optional[int] = None) -> Dict[str, Any]:
        """Submit course to volunteer review queue with automatic priority calculation"""
        try:
            # Calculate priority based on contributor reputation and course quality
            priority = await self._calculate_review_priority(contributor_id, course_id, priority_override)
            
            # Get estimated completion time
            estimated_completion = datetime.utcnow() + self.max_review_time[priority]
            
            # Create review entry
            review_entry = {
                'course_id': course_id,
                'contributor_id': contributor_id,
                'status': ReviewStatus.PENDING_REVIEW.value,
                'priority': priority.value,
                'submitted_at': datetime.utcnow(),
                'estimated_completion': estimated_completion,
                'escalation_count': 0
            }
            
            # Insert into review queue
            result = await self.supabase.execute_command(
                """
                INSERT INTO review_queue (course_id, contributor_id, status, priority, 
                                        submitted_at, estimated_completion, escalation_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                review_entry['course_id'], review_entry['contributor_id'], 
                review_entry['status'], review_entry['priority'],
                review_entry['submitted_at'], review_entry['estimated_completion'],
                review_entry['escalation_count']
            )
            
            if not result:
                return {
                    "success": False,
                    "message": "Failed to add course to review queue"
                }
            
            # Attempt to assign to available volunteer
            assignment_result = await self._assign_to_volunteer(course_id, priority)
            
            # Update queue position
            queue_position = await self._get_queue_position(course_id)
            
            # Notify contributor about submission
            await self._notify_review_submission(contributor_id, course_id, priority, queue_position)
            
            # Log review submission
            logger.info(f"Course {course_id} submitted for review with priority {priority.name}")
            
            return {
                "success": True,
                "review_id": result[0]["id"],
                "priority": priority.name,
                "queue_position": queue_position,
                "estimated_completion": estimated_completion,
                "assigned_reviewer": assignment_result.get("reviewer_id"),
                "message": "Course successfully submitted for review"
            }
            
        except Exception as e:
            logger.error(f"Failed to submit course {course_id} for review: {e}")
            return {
                "success": False,
                "message": f"Failed to submit for review: {str(e)}"
            }
    
    async def update_review_status(self, course_id: str, status: ReviewStatus, 
                                 reviewer_id: str = None, feedback: str = None,
                                 revision_notes: str = None) -> Dict[str, Any]:
        """Update course review status and notify contributor"""
        try:
            # Get current review entry
            current_review = await self._get_review_by_course(course_id)
            if not current_review:
                return {
                    "success": False,
                    "message": "Review entry not found"
                }
            
            # Prepare update data
            update_data = {
                'status': status.value,
                'updated_at': datetime.utcnow()
            }
            
            # Set completion time for terminal states
            if status in [ReviewStatus.APPROVED, ReviewStatus.REJECTED]:
                update_data['review_completed_at'] = datetime.utcnow()
            elif status == ReviewStatus.UNDER_REVIEW:
                update_data['review_started_at'] = datetime.utcnow()
            
            # Add feedback if provided
            if feedback:
                # Store anonymous feedback
                feedback_id = await self._store_anonymous_feedback(course_id, reviewer_id, feedback)
                update_data['feedback_id'] = feedback_id
            
            # Add revision notes if provided
            if revision_notes:
                update_data['revision_notes'] = revision_notes
            
            # Build update query dynamically
            set_clauses = []
            params = [course_id]  # course_id will be $1
            param_index = 2
            
            for key, value in update_data.items():
                set_clauses.append(f"{key} = ${param_index}")
                params.append(value)
                param_index += 1
            
            query = f"""
                UPDATE review_queue 
                SET {', '.join(set_clauses)}
                WHERE course_id = $1
                RETURNING id
            """
            
            result = await self.supabase.execute_command(query, *params)
            
            if not result:
                return {
                    "success": False,
                    "message": "Failed to update review status"
                }
            
            # Update course status if approved
            if status == ReviewStatus.APPROVED:
                await self.supabase.execute_command(
                    "UPDATE courses SET status = 'approved', approved_at = $1 WHERE id = $2",
                    datetime.utcnow(), course_id
                )
                
                # Trigger course publication workflow
                await self._trigger_course_publication(course_id)
                
            elif status == ReviewStatus.REJECTED:
                await self.supabase.execute_command(
                    "UPDATE courses SET status = 'rejected' WHERE id = $1",
                    course_id
                )
            
            # Notify contributor of status change
            await self._notify_status_change(
                current_review['contributor_id'], 
                course_id, 
                status, 
                feedback, 
                revision_notes
            )
            
            # Log status change
            logger.info(f"Review status updated for course {course_id}: {status.value}")
            
            return {
                "success": True,
                "message": f"Review status updated to {status.value}",
                "previous_status": current_review['status']
            }
            
        except Exception as e:
            logger.error(f"Failed to update review status for course {course_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to update review status: {str(e)}"
            }
    
    async def get_review_status(self, course_id: str) -> Dict[str, Any]:
        """Get current review status for a course"""
        try:
            review = await self._get_review_by_course(course_id)
            
            if not review:
                return {
                    "success": False,
                    "message": "Review entry not found"
                }
            
            # Get queue position if still pending
            queue_position = None
            if review['status'] == ReviewStatus.PENDING_REVIEW.value:
                queue_position = await self._get_queue_position(course_id)
            
            # Get anonymous feedback if available
            feedback = None
            if review.get('feedback_id'):
                feedback = await self._get_anonymous_feedback(review['feedback_id'])
            
            return {
                "success": True,
                "course_id": course_id,
                "status": review['status'],
                "priority": review['priority'],
                "submitted_at": review['submitted_at'],
                "queue_position": queue_position,
                "assigned_reviewer": bool(review.get('assigned_reviewer')),
                "estimated_completion": review.get('estimated_completion'),
                "feedback": feedback,
                "revision_notes": review.get('revision_notes'),
                "escalation_count": review.get('escalation_count', 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get review status for course {course_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to get review status: {str(e)}"
            }
    
    async def get_contributor_dashboard(self, contributor_id: str) -> Dict[str, Any]:
        """Get contributor dashboard showing all submitted courses and their status"""
        try:
            # Get all courses by contributor
            courses_query = """
                SELECT c.id, c.title, c.created_at, c.status as course_status,
                       rq.status as review_status, rq.priority, rq.submitted_at,
                       rq.estimated_completion, rq.escalation_count
                FROM courses c
                LEFT JOIN review_queue rq ON c.id = rq.course_id
                WHERE c.contributor_id = $1
                ORDER BY c.created_at DESC
            """
            
            courses = await self.supabase.execute_query(courses_query, contributor_id)
            
            # Process courses and add queue positions for pending reviews
            dashboard_courses = []
            
            for course in courses:
                course_info = {
                    "course_id": course['id'],
                    "title": course['title'],
                    "created_at": course['created_at'],
                    "course_status": course['course_status'],
                    "review_status": course.get('review_status'),
                    "priority": course.get('priority'),
                    "submitted_at": course.get('submitted_at'),
                    "estimated_completion": course.get('estimated_completion'),
                    "escalation_count": course.get('escalation_count', 0)
                }
                
                # Add queue position for pending reviews
                if course.get('review_status') == ReviewStatus.PENDING_REVIEW.value:
                    course_info['queue_position'] = await self._get_queue_position(course['id'])
                
                # Get feedback if available
                if course.get('review_status') in [ReviewStatus.NEEDS_REVISION.value, ReviewStatus.REJECTED.value]:
                    feedback_result = await self.supabase.execute_query(
                        "SELECT feedback_content FROM anonymous_feedback WHERE course_id = $1 ORDER BY created_at DESC LIMIT 1",
                        course['id']
                    )
                    if feedback_result:
                        course_info['feedback'] = feedback_result[0]['feedback_content']
                
                dashboard_courses.append(course_info)
            
            # Calculate dashboard statistics
            total_courses = len(courses)
            pending_reviews = sum(1 for c in courses if c.get('review_status') == ReviewStatus.PENDING_REVIEW.value)
            under_review = sum(1 for c in courses if c.get('review_status') == ReviewStatus.UNDER_REVIEW.value)
            approved = sum(1 for c in courses if c.get('review_status') == ReviewStatus.APPROVED.value)
            needs_revision = sum(1 for c in courses if c.get('review_status') == ReviewStatus.NEEDS_REVISION.value)
            
            return {
                "success": True,
                "contributor_id": contributor_id,
                "courses": dashboard_courses,
                "statistics": {
                    "total_courses": total_courses,
                    "pending_reviews": pending_reviews,
                    "under_review": under_review,
                    "approved": approved,
                    "needs_revision": needs_revision
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get contributor dashboard for {contributor_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to get dashboard: {str(e)}"
            }
    
    async def escalate_delayed_reviews(self) -> Dict[str, Any]:
        """Check for and escalate delayed reviews"""
        try:
            escalated_count = 0
            
            # Find reviews that have exceeded their escalation threshold
            for priority in ReviewPriority:
                threshold = datetime.utcnow() - self.escalation_thresholds[priority]
                
                delayed_reviews = await self.supabase.execute_query(
                    """
                    SELECT course_id, contributor_id, assigned_reviewer, submitted_at, escalation_count
                    FROM review_queue 
                    WHERE status = $1 AND priority = $2 AND submitted_at < $3
                    """,
                    ReviewStatus.PENDING_REVIEW.value, priority.value, threshold
                )
                
                for review in delayed_reviews:
                    try:
                        # Increase escalation count
                        new_escalation_count = review['escalation_count'] + 1
                        
                        # Update review with escalation
                        await self.supabase.execute_command(
                            """
                            UPDATE review_queue 
                            SET status = $1, escalation_count = $2, updated_at = $3
                            WHERE course_id = $4
                            """,
                            ReviewStatus.ESCALATED.value, new_escalation_count, 
                            datetime.utcnow(), review['course_id']
                        )
                        
                        # Try to reassign to a different volunteer
                        reassignment_result = await volunteer_manager.reassign_course_review(
                            review['course_id'], 
                            review['assigned_reviewer']
                        )
                        
                        # Notify about escalation
                        await self._notify_escalation(
                            review['contributor_id'], 
                            review['course_id'],
                            new_escalation_count
                        )
                        
                        escalated_count += 1
                        logger.info(f"Escalated delayed review for course {review['course_id']}")
                        
                    except Exception as e:
                        logger.error(f"Failed to escalate review for course {review['course_id']}: {e}")
            
            return {
                "success": True,
                "escalated_count": escalated_count,
                "message": f"Processed escalation for {escalated_count} delayed reviews"
            }
            
        except Exception as e:
            logger.error(f"Failed to escalate delayed reviews: {e}")
            return {
                "success": False,
                "message": f"Failed to escalate reviews: {str(e)}"
            }
    
    async def _calculate_review_priority(self, contributor_id: str, course_id: str, 
                                       priority_override: Optional[int] = None) -> ReviewPriority:
        """Calculate review priority based on contributor reputation and course factors"""
        try:
            if priority_override:
                return ReviewPriority(priority_override)
            
            # Get contributor reputation
            reputation_level = await self._get_contributor_reputation(contributor_id)
            
            # Get course quality indicators
            quality_score = await self._assess_course_quality(course_id)
            
            # Calculate base priority
            base_priority = ReviewPriority.NORMAL
            
            # Adjust based on reputation
            reputation_factor = self.reputation_multipliers.get(reputation_level, 1.0)
            
            # Adjust based on quality score (0.0 to 1.0)
            quality_factor = max(0.5, quality_score)  # Minimum 0.5 factor
            
            # Calculate final priority score
            priority_score = base_priority.value * reputation_factor * quality_factor
            
            # Map score to priority level
            if priority_score >= 3.0:
                return ReviewPriority.URGENT
            elif priority_score >= 2.5:
                return ReviewPriority.HIGH
            elif priority_score >= 1.5:
                return ReviewPriority.NORMAL
            else:
                return ReviewPriority.LOW
                
        except Exception as e:
            logger.error(f"Failed to calculate review priority: {e}")
            return ReviewPriority.NORMAL
    
    async def _get_contributor_reputation(self, contributor_id: str) -> str:
        """Get contributor reputation level based on history"""
        try:
            # Count approved courses
            result = await self.supabase.execute_query(
                "SELECT COUNT(*) as approved_count FROM courses WHERE contributor_id = $1 AND status = 'approved'",
                contributor_id
            )
            
            approved_count = result[0]['approved_count'] if result else 0
            
            if approved_count >= 25:
                return "expert_contributor"
            elif approved_count >= 10:
                return "verified_contributor"
            elif approved_count >= 3:
                return "regular_contributor"
            else:
                return "new_contributor"
                
        except Exception as e:
            logger.error(f"Failed to get contributor reputation: {e}")
            return "new_contributor"
    
    async def _assess_course_quality(self, course_id: str) -> float:
        """Assess course quality based on various factors"""
        try:
            quality_score = 1.0  # Base score
            
            # Get course details
            course_result = await self.supabase.execute_query(
                """
                SELECT title, description, category, difficulty_level, estimated_duration
                FROM courses WHERE id = $1
                """,
                course_id
            )
            
            if not course_result:
                return 0.5
            
            course = course_result[0]
            
            # Check title quality (length and content)
            title = course['title'] or ""
            if len(title) >= 20:  # Good length title
                quality_score += 0.1
            if any(word in title.lower() for word in ['master', 'advanced', 'complete', 'comprehensive']):
                quality_score += 0.1
            
            # Check description quality
            description = course['description'] or ""
            if len(description) >= 100:  # Detailed description
                quality_score += 0.15
            
            # Category specified
            if course['category']:
                quality_score += 0.1
            
            # Estimated duration provided
            if course['estimated_duration']:
                quality_score += 0.05
            
            # Check file count and sizes
            files_result = await self.supabase.execute_query(
                "SELECT COUNT(*) as file_count, SUM(file_size) as total_size FROM course_files WHERE course_id = $1",
                course_id
            )
            
            if files_result:
                file_count = files_result[0]['file_count'] or 0
                total_size = files_result[0]['total_size'] or 0
                
                # Reasonable file count
                if 3 <= file_count <= 20:
                    quality_score += 0.1
                elif file_count > 20:
                    quality_score += 0.15
                
                # Substantial content (more than 100MB)
                if total_size > 100 * 1024 * 1024:
                    quality_score += 0.1
            
            # Cap the score at reasonable maximum
            return min(quality_score, 2.0)
            
        except Exception as e:
            logger.error(f"Failed to assess course quality: {e}")
            return 1.0
    
    async def _assign_to_volunteer(self, course_id: str, priority: ReviewPriority) -> Dict[str, Any]:
        """Attempt to assign course to an available volunteer reviewer"""
        try:
            reviewer_id = await volunteer_manager.assign_course_to_reviewer(course_id, priority.value)
            
            if reviewer_id:
                # Update review queue with assignment
                await self.supabase.execute_command(
                    "UPDATE review_queue SET assigned_reviewer = $1, updated_at = $2 WHERE course_id = $3",
                    reviewer_id, datetime.utcnow(), course_id
                )
                
                return {
                    "success": True,
                    "reviewer_id": reviewer_id
                }
            else:
                return {
                    "success": False,
                    "message": "No available reviewers"
                }
                
        except Exception as e:
            logger.error(f"Failed to assign course {course_id} to volunteer: {e}")
            return {
                "success": False,
                "message": f"Assignment failed: {str(e)}"
            }
    
    async def _get_queue_position(self, course_id: str) -> int:
        """Get course position in review queue"""
        try:
            result = await self.supabase.execute_query(
                """
                SELECT COUNT(*) as position
                FROM review_queue 
                WHERE status = $1 
                  AND (priority > (SELECT priority FROM review_queue WHERE course_id = $2)
                       OR (priority = (SELECT priority FROM review_queue WHERE course_id = $2) 
                           AND submitted_at < (SELECT submitted_at FROM review_queue WHERE course_id = $2)))
                """,
                ReviewStatus.PENDING_REVIEW.value, course_id
            )
            
            return result[0]['position'] + 1 if result else 1
            
        except Exception as e:
            logger.error(f"Failed to get queue position for course {course_id}: {e}")
            return 0
    
    async def _get_review_by_course(self, course_id: str) -> Optional[Dict]:
        """Get review entry by course ID"""
        try:
            result = await self.supabase.execute_query(
                "SELECT * FROM review_queue WHERE course_id = $1",
                course_id
            )
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Failed to get review for course {course_id}: {e}")
            return None
    
    async def _store_anonymous_feedback(self, course_id: str, reviewer_id: str, feedback: str) -> str:
        """Store anonymous feedback from reviewer"""
        try:
            feedback_id = str(uuid.uuid4())
            
            await self.supabase.execute_command(
                """
                INSERT INTO anonymous_feedback (id, course_id, reviewer_anonymous_id, 
                                              feedback_content, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                feedback_id, course_id, reviewer_id, feedback, datetime.utcnow()
            )
            
            return feedback_id
            
        except Exception as e:
            logger.error(f"Failed to store anonymous feedback: {e}")
            return None
    
    async def _get_anonymous_feedback(self, feedback_id: str) -> Optional[str]:
        """Get anonymous feedback by ID"""
        try:
            result = await self.supabase.execute_query(
                "SELECT feedback_content FROM anonymous_feedback WHERE id = $1",
                feedback_id
            )
            return result[0]['feedback_content'] if result else None
            
        except Exception as e:
            logger.error(f"Failed to get anonymous feedback {feedback_id}: {e}")
            return None
    
    async def _notify_review_submission(self, contributor_id: str, course_id: str, 
                                      priority: ReviewPriority, queue_position: int):
        """Notify contributor about review submission"""
        try:
            notification_data = {
                "type": "review_submitted",
                "course_id": course_id,
                "priority": priority.name,
                "queue_position": queue_position,
                "message": f"Your course has been submitted for review with {priority.name.lower()} priority. Queue position: #{queue_position}"
            }
            
            # Store notification
            await self.redis.set(
                f"notification:{contributor_id}:{course_id}:submitted",
                json.dumps(notification_data),
                ex=86400 * 7  # Keep for 7 days
            )
            
            logger.info(f"Notification sent to {contributor_id} for course {course_id} submission")
            
        except Exception as e:
            logger.error(f"Failed to send submission notification: {e}")
    
    async def _notify_status_change(self, contributor_id: str, course_id: str, 
                                  status: ReviewStatus, feedback: str = None, 
                                  revision_notes: str = None):
        """Notify contributor about status change"""
        try:
            notification_data = {
                "type": "status_change",
                "course_id": course_id,
                "new_status": status.value,
                "message": self._get_status_message(status),
                "feedback": feedback,
                "revision_notes": revision_notes,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Store notification
            await self.redis.set(
                f"notification:{contributor_id}:{course_id}:status_change",
                json.dumps(notification_data),
                ex=86400 * 30  # Keep for 30 days
            )
            
            logger.info(f"Status change notification sent to {contributor_id} for course {course_id}: {status.value}")
            
        except Exception as e:
            logger.error(f"Failed to send status change notification: {e}")
    
    async def _notify_escalation(self, contributor_id: str, course_id: str, escalation_count: int):
        """Notify contributor about review escalation"""
        try:
            notification_data = {
                "type": "review_escalated",
                "course_id": course_id,
                "escalation_count": escalation_count,
                "message": f"Your course review has been escalated (level {escalation_count}) due to delays. We're working to expedite the process.",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Store notification
            await self.redis.set(
                f"notification:{contributor_id}:{course_id}:escalated",
                json.dumps(notification_data),
                ex=86400 * 14  # Keep for 14 days
            )
            
            logger.info(f"Escalation notification sent to {contributor_id} for course {course_id}")
            
        except Exception as e:
            logger.error(f"Failed to send escalation notification: {e}")
    
    async def _trigger_course_publication(self, course_id: str):
        """Trigger course publication workflow after approval"""
        try:
            # Update course status to published
            await self.supabase.execute_command(
                "UPDATE courses SET status = 'published', published_at = $1 WHERE id = $2",
                datetime.utcnow(), course_id
            )
            
            # Trigger announcement system
            publication_data = {
                "course_id": course_id,
                "action": "publish_course",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.redis.set(
                f"publication_queue:{course_id}",
                json.dumps(publication_data),
                ex=3600  # Keep for 1 hour
            )
            
            logger.info(f"Course publication triggered for {course_id}")
            
        except Exception as e:
            logger.error(f"Failed to trigger course publication: {e}")
    
    def _get_status_message(self, status: ReviewStatus) -> str:
        """Get human-readable status message"""
        messages = {
            ReviewStatus.PENDING_REVIEW: "Your course is waiting for volunteer review.",
            ReviewStatus.UNDER_REVIEW: "Your course is currently being reviewed by a volunteer.",
            ReviewStatus.APPROVED: "Congratulations! Your course has been approved and will be published.",
            ReviewStatus.REJECTED: "Your course has been rejected. Please review the feedback and consider resubmitting.",
            ReviewStatus.NEEDS_REVISION: "Your course needs some revisions. Please review the feedback and resubmit.",
            ReviewStatus.ESCALATED: "Your course review has been escalated for priority handling."
        }
        return messages.get(status, "Status updated.")

# Utility function to check review queue health
async def check_review_queue_health(review_manager: ReviewQueueManager) -> Dict[str, Any]:
    """Check the health of the review queue system"""
    try:
        # Get queue statistics
        stats_query = """
            SELECT status, priority, COUNT(*) as count, 
                   AVG(EXTRACT(EPOCH FROM (NOW() - submitted_at))/3600) as avg_hours_waiting
            FROM review_queue 
            WHERE status IN ('pending_review', 'under_review')
            GROUP BY status, priority
        """
        
        stats = await review_manager.supabase.execute_query(stats_query)
        
        # Calculate health metrics
        total_pending = sum(s['count'] for s in stats if s['status'] == 'pending_review')
        total_under_review = sum(s['count'] for s in stats if s['status'] == 'under_review')
        
        # Check for bottlenecks (items waiting more than expected time)
        bottlenecks = []
        for stat in stats:
            if stat['status'] == 'pending_review':
                expected_hours = {1: 168, 2: 120, 3: 72, 4: 24}  # Expected waiting times in hours
                if stat['avg_hours_waiting'] > expected_hours.get(stat['priority'], 120):
                    bottlenecks.append({
                        'priority': stat['priority'],
                        'avg_waiting_hours': round(stat['avg_hours_waiting'], 1),
                        'count': stat['count']
                    })
        
        return {
            "success": True,
            "total_pending": total_pending,
            "total_under_review": total_under_review,
            "bottlenecks": bottlenecks,
            "queue_healthy": len(bottlenecks) == 0,
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to check review queue health: {e}")
        return {
            "success": False,
            "message": f"Health check failed: {str(e)}"
        }