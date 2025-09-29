"""
Review Decision Processing System - AC2: Course Approval/Rejection Workflow
Implements structured review process with standardized quality guidelines and feedback
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager
from core.volunteer_dashboard import volunteer_dashboard

logger = logging.getLogger(__name__)

class ReviewDecision(Enum):
    """Review decision types"""
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    REQUEST_CHANGES = "request_changes"

class ReviewQuality(Enum):
    """Review quality ratings"""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"

@dataclass
class ReviewFeedback:
    """Structured review feedback"""
    decision: ReviewDecision
    quality_rating: ReviewQuality
    feedback_text: str
    improvement_suggestions: List[str]
    category_scores: Dict[str, int]  # 1-5 rating for each category
    estimated_revision_time: Optional[str] = None
    reviewer_notes: Optional[str] = None

class ReviewDecisionProcessor:
    """Enhanced review decision processing with structured workflow"""
    
    def __init__(self):
        self.quality_categories = [
            'content_accuracy',
            'educational_value', 
            'file_quality',
            'organization',
            'appropriateness'
        ]
        
        self.feedback_templates = {
            'quality_issues': {
                'title': 'Content Quality Issues',
                'suggestions': [
                    'Review content accuracy and verify all information',
                    'Enhance educational clarity and structure',
                    'Provide more detailed explanations where needed',
                    'Consider adding examples or practice exercises'
                ]
            },
            'technical_issues': {
                'title': 'Technical Issues',
                'suggestions': [
                    'Check all files are accessible and properly formatted',
                    'Ensure consistent file naming conventions',
                    'Verify media quality and clarity',
                    'Test all links and references'
                ]
            },
            'organization_issues': {
                'title': 'Organization and Structure',
                'suggestions': [
                    'Improve logical flow and progression',
                    'Add clear learning objectives',
                    'Structure content into digestible sections',
                    'Include summary or conclusion'
                ]
            },
            'category_mismatch': {
                'title': 'Category Classification',
                'suggestions': [
                    'Review course categorization for accuracy',
                    'Adjust difficulty level to match content',
                    'Consider splitting into multiple focused courses',
                    'Clarify target audience and prerequisites'
                ]
            }
        }
    
    async def process_review_decision(self, review_id: str, reviewer_id: str, 
                                    feedback: ReviewFeedback) -> Dict[str, Any]:
        """Process comprehensive review decision with structured feedback"""
        try:
            # Get review details
            review_query = """
                SELECT r.*, c.title as course_title, c.id as course_id, 
                       u.anonymous_id as contributor_anonymous_id
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                JOIN users u ON c.contributor_id = u.id
                WHERE r.id = $1 AND r.reviewer_id = $2
            """
            
            review_result = await supabase_client.execute_query(review_query, review_id, reviewer_id)
            if not review_result:
                return {
                    "success": False,
                    "message": "Review not found or access denied"
                }
            
            review = review_result[0]
            course_id = review['course_id']
            
            # Store structured feedback
            feedback_id = await self._store_structured_feedback(
                review_id, 
                course_id, 
                reviewer_id, 
                feedback
            )
            
            # Update review status based on decision
            review_status = await self._update_review_status(
                review_id, 
                course_id, 
                feedback.decision, 
                feedback_id
            )
            
            if not review_status['success']:
                return review_status
            
            # Process decision-specific actions
            decision_result = await self._process_decision_actions(
                course_id, 
                feedback.decision, 
                feedback_id,
                review['contributor_anonymous_id']
            )
            
            # Update reviewer statistics
            await self._update_reviewer_stats(reviewer_id, feedback.decision, feedback.quality_rating)
            
            # Send notifications
            await self._send_decision_notifications(
                review['contributor_anonymous_id'],
                course_id,
                review['course_title'],
                feedback
            )
            
            # Log decision for audit
            await self._log_review_decision(review_id, reviewer_id, feedback)
            
            result = {
                "success": True,
                "review_id": review_id,
                "course_id": course_id,
                "decision": feedback.decision.value,
                "feedback_id": feedback_id,
                "course_status": decision_result.get('course_status'),
                "message": f"Course {feedback.decision.value} successfully"
            }
            
            # Add decision-specific information
            if feedback.decision == ReviewDecision.APPROVED:
                result["publication_triggered"] = decision_result.get('publication_triggered', False)
            elif feedback.decision in [ReviewDecision.NEEDS_REVISION, ReviewDecision.REQUEST_CHANGES]:
                result["revision_guidelines"] = decision_result.get('revision_guidelines')
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process review decision: {e}")
            return {
                "success": False,
                "message": f"Decision processing failed: {str(e)}"
            }
    
    async def generate_review_template(self, course_id: str, reviewer_id: str) -> Dict[str, Any]:
        """Generate pre-filled review template based on course analysis"""
        try:
            # Get course details for analysis
            course_data = await volunteer_dashboard.get_course_for_review(course_id, reviewer_id)
            
            if not course_data.get('success'):
                return {'error': 'Failed to load course data'}
            
            course = course_data['course']
            files = course_data['files']
            
            # Analyze course and generate template scores
            analysis = await self._analyze_course_for_template(course, files)
            
            template = {
                'course_id': course_id,
                'review_template': {
                    'quality_categories': {
                        category: analysis.get(f'{category}_score', 3)
                        for category in self.quality_categories
                    },
                    'suggested_decision': analysis.get('suggested_decision', 'needs_review'),
                    'pre_filled_feedback': analysis.get('template_feedback', ''),
                    'common_issues': analysis.get('potential_issues', []),
                    'estimated_review_time': analysis.get('estimated_time', 60)
                },
                'review_guidelines': course_data.get('review_guidelines', {}),
                'contributor_context': course_data.get('contributor_context', {}),
                'checklist': self._generate_review_checklist(course.get('category', 'general'))
            }
            
            return template
            
        except Exception as e:
            logger.error(f"Failed to generate review template: {e}")
            return {'error': f'Template generation failed: {str(e)}'}
    
    async def get_review_history(self, course_id: str) -> List[Dict]:
        """Get complete review history for a course"""
        try:
            history_query = """
                SELECT r.id as review_id, r.status, r.created_at, r.reviewed_at,
                       rf.quality_rating, rf.feedback_text, rf.improvement_suggestions,
                       rf.category_scores, rf.reviewer_notes,
                       u.anonymous_id as reviewer_anonymous_id,
                       EXTRACT(EPOCH FROM (r.reviewed_at - r.created_at))/3600 as review_duration_hours
                FROM reviews r
                LEFT JOIN review_feedback rf ON r.id = rf.review_id
                LEFT JOIN users u ON r.reviewer_id = u.id
                WHERE r.course_id = $1
                ORDER BY r.created_at DESC
            """
            
            history = await supabase_client.execute_query(history_query, course_id)
            
            # Format history entries
            formatted_history = []
            for entry in history:
                formatted_entry = {
                    'review_id': entry['review_id'],
                    'status': entry['status'],
                    'reviewer_anonymous_id': entry['reviewer_anonymous_id'],
                    'submitted_at': entry['created_at'],
                    'completed_at': entry['reviewed_at'],
                    'review_duration_hours': round(entry.get('review_duration_hours', 0) or 0, 1),
                    'quality_rating': entry.get('quality_rating'),
                    'feedback': {
                        'text': entry.get('feedback_text'),
                        'suggestions': entry.get('improvement_suggestions'),
                        'category_scores': entry.get('category_scores'),
                        'reviewer_notes': entry.get('reviewer_notes')
                    } if entry.get('feedback_text') else None
                }
                formatted_history.append(formatted_entry)
            
            return formatted_history
            
        except Exception as e:
            logger.error(f"Failed to get review history: {e}")
            return []
    
    async def get_reviewer_feedback_stats(self, reviewer_id: str, period_days: int = 30) -> Dict[str, Any]:
        """Get reviewer's feedback statistics and quality metrics"""
        try:
            stats_query = """
                SELECT 
                    COUNT(*) as total_reviews,
                    AVG(CASE 
                        WHEN rf.quality_rating = 'excellent' THEN 5
                        WHEN rf.quality_rating = 'good' THEN 4
                        WHEN rf.quality_rating = 'acceptable' THEN 3
                        WHEN rf.quality_rating = 'poor' THEN 2
                        ELSE 1
                    END) as avg_quality_score,
                    COUNT(*) FILTER (WHERE r.status = 'approved') as approvals,
                    COUNT(*) FILTER (WHERE r.status = 'rejected') as rejections,
                    COUNT(*) FILTER (WHERE r.status = 'needs_revision') as revisions_requested,
                    AVG(array_length(rf.improvement_suggestions, 1)) as avg_suggestions_count,
                    AVG(length(rf.feedback_text)) as avg_feedback_length
                FROM reviews r
                JOIN review_feedback rf ON r.id = rf.review_id
                WHERE r.reviewer_id = $1 
                  AND r.reviewed_at > NOW() - INTERVAL '%s days'
                  AND r.status IN ('approved', 'rejected', 'needs_revision')
            """ % period_days
            
            stats_result = await supabase_client.execute_query(stats_query, reviewer_id)
            
            if not stats_result or not stats_result[0]['total_reviews']:
                return self._get_default_feedback_stats()
            
            stats = stats_result[0]
            
            total_reviews = stats['total_reviews']
            approval_rate = (stats['approvals'] / total_reviews * 100) if total_reviews > 0 else 0
            
            # Calculate feedback quality score
            feedback_quality = self._calculate_feedback_quality(
                stats.get('avg_feedback_length', 0) or 0,
                stats.get('avg_suggestions_count', 0) or 0,
                approval_rate
            )
            
            return {
                'period_days': period_days,
                'review_statistics': {
                    'total_reviews': total_reviews,
                    'approval_rate': round(approval_rate, 1),
                    'average_quality_score': round(stats.get('avg_quality_score', 0) or 0, 1)
                },
                'decision_breakdown': {
                    'approved': stats['approvals'],
                    'rejected': stats['rejections'],
                    'revision_requested': stats['revisions_requested']
                },
                'feedback_quality': {
                    'score': feedback_quality,
                    'avg_feedback_length': round(stats.get('avg_feedback_length', 0) or 0),
                    'avg_suggestions_count': round(stats.get('avg_suggestions_count', 0) or 0, 1),
                    'rating': self._get_feedback_quality_rating(feedback_quality)
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get reviewer feedback stats: {e}")
            return self._get_default_feedback_stats()
    
    async def apply_batch_decision(self, review_ids: List[str], reviewer_id: str,
                                 decision: ReviewDecision, batch_feedback: str,
                                 quality_rating: ReviewQuality = ReviewQuality.GOOD) -> Dict[str, Any]:
        """Apply the same decision to multiple reviews (batch operation for AC5)"""
        try:
            results = {
                'successful': [],
                'failed': [],
                'total_processed': 0,
                'batch_id': str(uuid.uuid4())
            }
            
            # Create batch feedback template
            batch_template = ReviewFeedback(
                decision=decision,
                quality_rating=quality_rating,
                feedback_text=batch_feedback,
                improvement_suggestions=self._get_batch_suggestions(decision),
                category_scores={category: 3 for category in self.quality_categories}  # Default scores
            )
            
            # Process each review in the batch
            for review_id in review_ids:
                try:
                    result = await self.process_review_decision(
                        review_id, 
                        reviewer_id, 
                        batch_template
                    )
                    
                    results['total_processed'] += 1
                    
                    if result['success']:
                        results['successful'].append({
                            'review_id': review_id,
                            'course_id': result.get('course_id'),
                            'status': result.get('decision')
                        })
                    else:
                        results['failed'].append({
                            'review_id': review_id,
                            'error': result.get('message', 'Unknown error')
                        })
                        
                except Exception as e:
                    results['failed'].append({
                        'review_id': review_id,
                        'error': str(e)
                    })
                    results['total_processed'] += 1
            
            # Log batch operation
            await self._log_batch_operation(reviewer_id, results['batch_id'], results)
            
            return {
                'success': True,
                'batch_results': results,
                'message': f"Batch operation completed: {len(results['successful'])} successful, {len(results['failed'])} failed"
            }
            
        except Exception as e:
            logger.error(f"Batch decision processing failed: {e}")
            return {
                'success': False,
                'message': f"Batch processing failed: {str(e)}"
            }
    
    # Private helper methods
    
    async def _store_structured_feedback(self, review_id: str, course_id: str, 
                                       reviewer_id: str, feedback: ReviewFeedback) -> str:
        """Store structured review feedback in database"""
        try:
            feedback_id = str(uuid.uuid4())
            
            # Store in review_feedback table
            feedback_query = """
                INSERT INTO review_feedback (
                    id, review_id, course_id, reviewer_id,
                    decision, quality_rating, feedback_text,
                    improvement_suggestions, category_scores,
                    estimated_revision_time, reviewer_notes,
                    created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
            """
            
            result = await supabase_client.execute_query(
                feedback_query,
                feedback_id, review_id, course_id, reviewer_id,
                feedback.decision.value, feedback.quality_rating.value,
                feedback.feedback_text, feedback.improvement_suggestions,
                feedback.category_scores, feedback.estimated_revision_time,
                feedback.reviewer_notes, datetime.utcnow()
            )
            
            if result:
                return feedback_id
            else:
                raise Exception("Failed to store feedback")
                
        except Exception as e:
            logger.error(f"Failed to store structured feedback: {e}")
            raise
    
    async def _update_review_status(self, review_id: str, course_id: str, 
                                  decision: ReviewDecision, feedback_id: str) -> Dict[str, Any]:
        """Update review and course status based on decision"""
        try:
            # Update review record
            update_query = """
                UPDATE reviews 
                SET status = $1, reviewed_at = $2, feedback_id = $3, updated_at = $4
                WHERE id = $5
                RETURNING id
            """
            
            review_result = await supabase_client.execute_query(
                update_query,
                decision.value, datetime.utcnow(), feedback_id, 
                datetime.utcnow(), review_id
            )
            
            if not review_result:
                return {
                    "success": False,
                    "message": "Failed to update review status"
                }
            
            # Update course status
            course_status_map = {
                ReviewDecision.APPROVED: 'approved',
                ReviewDecision.REJECTED: 'rejected',
                ReviewDecision.NEEDS_REVISION: 'needs_revision',
                ReviewDecision.REQUEST_CHANGES: 'needs_revision'
            }
            
            course_status = course_status_map[decision]
            
            course_update_query = """
                UPDATE courses 
                SET status = $1, updated_at = $2
                WHERE id = $3
                RETURNING id
            """
            
            course_result = await supabase_client.execute_query(
                course_update_query,
                course_status, datetime.utcnow(), course_id
            )
            
            if not course_result:
                return {
                    "success": False,
                    "message": "Failed to update course status"
                }
            
            return {
                "success": True,
                "course_status": course_status
            }
            
        except Exception as e:
            logger.error(f"Failed to update review status: {e}")
            return {
                "success": False,
                "message": str(e)
            }
    
    async def _process_decision_actions(self, course_id: str, decision: ReviewDecision, 
                                      feedback_id: str, contributor_id: str) -> Dict[str, Any]:
        """Process decision-specific actions"""
        try:
            result = {}
            
            if decision == ReviewDecision.APPROVED:
                # Trigger publication workflow
                publication_result = await self._trigger_course_publication(course_id)
                result['publication_triggered'] = publication_result
                result['course_status'] = 'published'
                
            elif decision in [ReviewDecision.NEEDS_REVISION, ReviewDecision.REQUEST_CHANGES]:
                # Generate revision guidelines
                revision_guidelines = await self._generate_revision_guidelines(feedback_id)
                result['revision_guidelines'] = revision_guidelines
                result['course_status'] = 'needs_revision'
                
            elif decision == ReviewDecision.REJECTED:
                # Archive course and provide appeal process
                await self._archive_rejected_course(course_id)
                result['course_status'] = 'rejected'
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process decision actions: {e}")
            return {'error': str(e)}
    
    async def _update_reviewer_stats(self, reviewer_id: str, decision: ReviewDecision, 
                                   quality_rating: ReviewQuality):
        """Update reviewer performance statistics"""
        try:
            # Get or create reviewer stats record
            stats_query = """
                INSERT INTO reviewer_stats (reviewer_id, reviews_completed, decisions, quality_scores, updated_at)
                VALUES ($1, 1, $2, $3, $4)
                ON CONFLICT (reviewer_id)
                DO UPDATE SET
                    reviews_completed = reviewer_stats.reviews_completed + 1,
                    decisions = reviewer_stats.decisions || $2,
                    quality_scores = reviewer_stats.quality_scores || $3,
                    updated_at = $4
            """
            
            decisions_update = {decision.value: 1}
            quality_update = {quality_rating.value: 1}
            
            await supabase_client.execute_command(
                stats_query, 
                reviewer_id, decisions_update, quality_update, datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Failed to update reviewer stats: {e}")
    
    async def _send_decision_notifications(self, contributor_id: str, course_id: str,
                                         course_title: str, feedback: ReviewFeedback):
        """Send decision notifications to contributor"""
        try:
            notification_data = {
                'type': 'review_decision',
                'course_id': course_id,
                'course_title': course_title,
                'decision': feedback.decision.value,
                'quality_rating': feedback.quality_rating.value,
                'feedback_text': feedback.feedback_text,
                'improvement_suggestions': feedback.improvement_suggestions,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Store notification (to be sent via Telegram bot)
            notification_key = f"notification:{contributor_id}:{course_id}:decision"
            
            # This would integrate with the notification system
            logger.info(f"Decision notification prepared for {contributor_id}: {feedback.decision.value}")
            
        except Exception as e:
            logger.error(f"Failed to send decision notification: {e}")
    
    async def _log_review_decision(self, review_id: str, reviewer_id: str, feedback: ReviewFeedback):
        """Log review decision for audit purposes"""
        try:
            audit_query = """
                INSERT INTO review_audit_log (
                    review_id, reviewer_id, decision, quality_rating,
                    feedback_length, suggestions_count, timestamp
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """
            
            await supabase_client.execute_command(
                audit_query,
                review_id, reviewer_id, feedback.decision.value,
                feedback.quality_rating.value, len(feedback.feedback_text),
                len(feedback.improvement_suggestions), datetime.utcnow()
            )
            
            logger.info(f"Review decision logged: {review_id} -> {feedback.decision.value}")
            
        except Exception as e:
            logger.error(f"Failed to log review decision: {e}")
    
    async def _analyze_course_for_template(self, course: Dict, files: List[Dict]) -> Dict[str, Any]:
        """Analyze course to generate review template"""
        try:
            analysis = {}
            
            # Analyze title and description
            title = course.get('title', '')
            description = course.get('description', '')
            
            # Content quality analysis
            if len(title) >= 20 and len(description) >= 100:
                analysis['content_accuracy_score'] = 4
                analysis['educational_value_score'] = 4
            elif len(title) >= 10 and len(description) >= 50:
                analysis['content_accuracy_score'] = 3
                analysis['educational_value_score'] = 3
            else:
                analysis['content_accuracy_score'] = 2
                analysis['educational_value_score'] = 2
            
            # File quality analysis
            file_count = len(files)
            total_size = sum(f.get('file_size', 0) or 0 for f in files)
            
            if file_count >= 5 and total_size > 10 * 1024 * 1024:  # 10MB+
                analysis['file_quality_score'] = 4
                analysis['organization_score'] = 4
            elif file_count >= 3:
                analysis['file_quality_score'] = 3
                analysis['organization_score'] = 3
            else:
                analysis['file_quality_score'] = 2
                analysis['organization_score'] = 2
            
            # Appropriateness (default good unless issues found)
            analysis['appropriateness_score'] = 4
            
            # Suggest decision based on average score
            avg_score = sum(analysis[f'{cat}_score'] for cat in self.quality_categories) / len(self.quality_categories)
            
            if avg_score >= 4:
                analysis['suggested_decision'] = 'approved'
                analysis['template_feedback'] = 'Course meets quality standards and is ready for publication.'
            elif avg_score >= 3:
                analysis['suggested_decision'] = 'approved'
                analysis['template_feedback'] = 'Course is acceptable with minor areas for potential improvement.'
            else:
                analysis['suggested_decision'] = 'needs_revision'
                analysis['template_feedback'] = 'Course requires improvements before publication.'
                analysis['potential_issues'] = [
                    'Content needs more detail',
                    'File quality or quantity insufficient',
                    'Organization could be improved'
                ]
            
            analysis['estimated_time'] = min(60 + file_count * 10, 180)  # 1-3 hours
            
            return analysis
            
        except Exception as e:
            logger.error(f"Course analysis failed: {e}")
            return {'estimated_time': 90}
    
    def _generate_review_checklist(self, category: str) -> List[Dict]:
        """Generate category-specific review checklist"""
        base_checklist = [
            {'item': 'Content accuracy verified', 'category': 'content_accuracy'},
            {'item': 'Educational value present', 'category': 'educational_value'},
            {'item': 'Files accessible and quality', 'category': 'file_quality'},
            {'item': 'Well organized structure', 'category': 'organization'},
            {'item': 'Appropriate for community', 'category': 'appropriateness'}
        ]
        
        category_specific = {
            'tactics': [
                {'item': 'Chess positions accurate', 'category': 'content_accuracy'},
                {'item': 'Solutions verified correct', 'category': 'content_accuracy'},
                {'item': 'Difficulty progression logical', 'category': 'organization'}
            ],
            'openings': [
                {'item': 'Opening theory current', 'category': 'content_accuracy'},
                {'item': 'Move sequences accurate', 'category': 'content_accuracy'},
                {'item': 'Variations complete', 'category': 'educational_value'}
            ],
            'endgames': [
                {'item': 'Endgame principles correct', 'category': 'content_accuracy'},
                {'item': 'Key positions included', 'category': 'educational_value'},
                {'item': 'Practical examples provided', 'category': 'educational_value'}
            ]
        }
        
        checklist = base_checklist.copy()
        if category in category_specific:
            checklist.extend(category_specific[category])
        
        return checklist
    
    def _get_batch_suggestions(self, decision: ReviewDecision) -> List[str]:
        """Get standard suggestions for batch operations"""
        suggestions = {
            ReviewDecision.APPROVED: [
                'Course approved for publication',
                'Meets community quality standards',
                'Thank you for your contribution'
            ],
            ReviewDecision.REJECTED: [
                'Course does not meet minimum quality standards',
                'Please review community guidelines',
                'Consider resubmitting with improvements'
            ],
            ReviewDecision.NEEDS_REVISION: [
                'Course has potential but needs improvements',
                'Please address the feedback provided',
                'Resubmit after making suggested changes'
            ]
        }
        
        return suggestions.get(decision, ['Batch review completed'])
    
    def _calculate_feedback_quality(self, avg_length: float, avg_suggestions: float, approval_rate: float) -> int:
        """Calculate feedback quality score out of 100"""
        # Length component (0-40 points) - adequate length feedback
        if avg_length >= 200:
            length_score = 40
        elif avg_length >= 100:
            length_score = 30
        elif avg_length >= 50:
            length_score = 20
        else:
            length_score = 10
        
        # Suggestions component (0-30 points) - helpful suggestions
        if avg_suggestions >= 3:
            suggestions_score = 30
        elif avg_suggestions >= 2:
            suggestions_score = 25
        elif avg_suggestions >= 1:
            suggestions_score = 15
        else:
            suggestions_score = 5
        
        # Balance component (0-30 points) - balanced approval rate
        if 70 <= approval_rate <= 85:
            balance_score = 30
        elif 60 <= approval_rate < 70 or 85 < approval_rate <= 90:
            balance_score = 25
        elif 50 <= approval_rate < 60 or 90 < approval_rate <= 95:
            balance_score = 15
        else:
            balance_score = 5
        
        return min(100, length_score + suggestions_score + balance_score)
    
    def _get_feedback_quality_rating(self, score: int) -> str:
        """Convert feedback quality score to rating"""
        if score >= 80:
            return 'Excellent'
        elif score >= 65:
            return 'Good'
        elif score >= 50:
            return 'Adequate'
        else:
            return 'Needs Improvement'
    
    def _get_default_feedback_stats(self) -> Dict[str, Any]:
        """Return default feedback stats for new reviewers"""
        return {
            'period_days': 30,
            'review_statistics': {
                'total_reviews': 0,
                'approval_rate': 0,
                'average_quality_score': 0
            },
            'decision_breakdown': {
                'approved': 0,
                'rejected': 0,
                'revision_requested': 0
            },
            'feedback_quality': {
                'score': 0,
                'avg_feedback_length': 0,
                'avg_suggestions_count': 0,
                'rating': 'New Reviewer'
            }
        }
    
    async def _trigger_course_publication(self, course_id: str) -> bool:
        """Trigger course publication workflow"""
        try:
            # Update course to published status
            await supabase_client.execute_command(
                "UPDATE courses SET status = 'published', published_at = $1 WHERE id = $2",
                datetime.utcnow(), course_id
            )
            
            # Queue for announcement (integration point with existing announcement system)
            logger.info(f"Course {course_id} queued for publication")
            return True
            
        except Exception as e:
            logger.error(f"Failed to trigger publication: {e}")
            return False
    
    async def _generate_revision_guidelines(self, feedback_id: str) -> Dict[str, Any]:
        """Generate specific revision guidelines based on feedback"""
        try:
            feedback_query = """
                SELECT improvement_suggestions, category_scores, feedback_text
                FROM review_feedback 
                WHERE id = $1
            """
            
            feedback_result = await supabase_client.execute_query(feedback_query, feedback_id)
            if not feedback_result:
                return {}
            
            feedback_data = feedback_result[0]
            
            # Generate guidelines based on category scores
            low_scores = [
                cat for cat, score in feedback_data.get('category_scores', {}).items()
                if score < 3
            ]
            
            guidelines = {
                'priority_areas': low_scores,
                'improvement_suggestions': feedback_data.get('improvement_suggestions', []),
                'detailed_feedback': feedback_data.get('feedback_text', ''),
                'estimated_revision_time': '2-4 hours',
                'resubmission_tips': [
                    'Address all feedback points before resubmitting',
                    'Test all files and links',
                    'Review content for accuracy and completeness',
                    'Ensure proper organization and flow'
                ]
            }
            
            return guidelines
            
        except Exception as e:
            logger.error(f"Failed to generate revision guidelines: {e}")
            return {}
    
    async def _archive_rejected_course(self, course_id: str):
        """Archive rejected course with appeal process"""
        try:
            await supabase_client.execute_command(
                """
                UPDATE courses 
                SET status = 'rejected', 
                    archived_at = $1,
                    appeal_deadline = $2
                WHERE id = $3
                """,
                datetime.utcnow(),
                datetime.utcnow() + timedelta(days=30),  # 30-day appeal window
                course_id
            )
            
        except Exception as e:
            logger.error(f"Failed to archive rejected course: {e}")
    
    async def _log_batch_operation(self, reviewer_id: str, batch_id: str, results: Dict):
        """Log batch operation for audit"""
        try:
            await supabase_client.execute_command(
                """
                INSERT INTO batch_operations (
                    batch_id, reviewer_id, total_processed, successful_count,
                    failed_count, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """,
                batch_id, reviewer_id, results['total_processed'],
                len(results['successful']), len(results['failed']),
                datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Failed to log batch operation: {e}")

# Global instance
review_processor = ReviewDecisionProcessor()