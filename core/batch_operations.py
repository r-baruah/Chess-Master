"""
Batch Operations Manager - AC5: Multi-course operations for experienced reviewers
Implements bulk approval, batch feedback, and advanced filtering for efficient course management
"""
import logging
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from enum import Enum
from core.supabase_client import supabase_client
from core.review_processor import review_processor, ReviewDecision, ReviewQuality, ReviewFeedback
from core.volunteer_dashboard import volunteer_dashboard
from core.performance_tracker import performance_tracker

logger = logging.getLogger(__name__)

class BatchOperation(Enum):
    """Batch operation types"""
    BULK_APPROVE = "bulk_approve"
    BULK_REJECT = "bulk_reject"  
    BULK_REVISION = "bulk_revision"
    BATCH_FEEDBACK = "batch_feedback"
    QUICK_REVIEW = "quick_review"

class FilterCriteria(Enum):
    """Available filter criteria for batch operations"""
    CATEGORY = "category"
    PRIORITY = "priority"
    CONTRIBUTOR = "contributor"
    FILE_COUNT = "file_count"
    SIZE_RANGE = "size_range"
    WAITING_TIME = "waiting_time"
    COMPLEXITY = "complexity"

@dataclass
class BatchFilter:
    """Batch operation filter configuration"""
    criteria: FilterCriteria
    operator: str  # eq, gt, lt, in, range
    value: Any
    
@dataclass
class BatchOperationResult:
    """Result of batch operation"""
    operation_id: str
    operation_type: BatchOperation
    total_selected: int
    successful: int
    failed: int
    skipped: int
    processing_time_seconds: float
    detailed_results: List[Dict]

class BatchOperationsManager:
    """Advanced batch operations for experienced volunteer reviewers"""
    
    def __init__(self):
        self.max_batch_size = 50  # Maximum courses per batch operation
        self.min_reviewer_level = 'experienced'  # Minimum level for batch operations
        
        self.quick_review_templates = {
            'standard_approval': {
                'decision': ReviewDecision.APPROVED,
                'feedback': 'Course meets community standards and is approved for publication.',
                'suggestions': ['Good quality content', 'Well organized', 'Appropriate for target audience'],
                'quality_rating': ReviewQuality.GOOD
            },
            'quality_issues': {
                'decision': ReviewDecision.NEEDS_REVISION,
                'feedback': 'Course requires improvements before publication.',
                'suggestions': ['Review content accuracy', 'Improve file organization', 'Add more detailed descriptions'],
                'quality_rating': ReviewQuality.ACCEPTABLE
            },
            'content_rejection': {
                'decision': ReviewDecision.REJECTED,
                'feedback': 'Course does not meet minimum quality standards.',
                'suggestions': ['Content lacks educational value', 'Poor file quality', 'Inappropriate for community'],
                'quality_rating': ReviewQuality.POOR
            }
        }
    
    async def execute_batch_operation(self, volunteer_id: str, operation_type: BatchOperation,
                                    course_ids: List[str] = None, filters: List[BatchFilter] = None,
                                    operation_params: Dict[str, Any] = None) -> BatchOperationResult:
        """Execute batch operation with comprehensive validation and processing"""
        try:
            start_time = datetime.utcnow()
            operation_id = str(uuid.uuid4())
            
            # Validate reviewer permissions for batch operations
            if not await self._validate_batch_permissions(volunteer_id):
                return BatchOperationResult(
                    operation_id=operation_id,
                    operation_type=operation_type,
                    total_selected=0, successful=0, failed=0, skipped=0,
                    processing_time_seconds=0,
                    detailed_results=[{'error': 'Insufficient permissions for batch operations'}]
                )
            
            # Get target courses (either from course_ids or filters)
            if course_ids:
                target_courses = await self._get_courses_by_ids(course_ids, volunteer_id)
            else:
                target_courses = await self._get_filtered_courses(filters, volunteer_id)
            
            # Validate batch size
            if len(target_courses) > self.max_batch_size:
                target_courses = target_courses[:self.max_batch_size]
                logger.warning(f"Batch size limited to {self.max_batch_size} courses")
            
            # Execute the specific batch operation
            if operation_type == BatchOperation.BULK_APPROVE:
                result = await self._execute_bulk_approve(volunteer_id, target_courses, operation_params)
            elif operation_type == BatchOperation.BULK_REJECT:
                result = await self._execute_bulk_reject(volunteer_id, target_courses, operation_params)
            elif operation_type == BatchOperation.BULK_REVISION:
                result = await self._execute_bulk_revision(volunteer_id, target_courses, operation_params)
            elif operation_type == BatchOperation.BATCH_FEEDBACK:
                result = await self._execute_batch_feedback(volunteer_id, target_courses, operation_params)
            elif operation_type == BatchOperation.QUICK_REVIEW:
                result = await self._execute_quick_review(volunteer_id, target_courses, operation_params)
            else:
                raise ValueError(f"Unsupported batch operation: {operation_type}")
            
            # Calculate processing time
            end_time = datetime.utcnow()
            processing_time = (end_time - start_time).total_seconds()
            
            # Create comprehensive result
            batch_result = BatchOperationResult(
                operation_id=operation_id,
                operation_type=operation_type,
                total_selected=len(target_courses),
                successful=len(result['successful']),
                failed=len(result['failed']),
                skipped=result.get('skipped', 0),
                processing_time_seconds=processing_time,
                detailed_results=result['detailed_results']
            )
            
            # Log batch operation
            await self._log_batch_operation(volunteer_id, batch_result, operation_params)
            
            # Update performance metrics
            await performance_tracker.track_review_completion(
                operation_id, 
                'batch_operation',
                processing_time / 3600,  # Convert to hours
                {'batch_size': len(target_courses), 'operation_type': operation_type.value}
            )
            
            return batch_result
            
        except Exception as e:
            logger.error(f"Batch operation failed: {e}")
            return BatchOperationResult(
                operation_id=operation_id or str(uuid.uuid4()),
                operation_type=operation_type,
                total_selected=0, successful=0, failed=0, skipped=0,
                processing_time_seconds=0,
                detailed_results=[{'error': f'Batch operation failed: {str(e)}'}]
            )
    
    async def get_batch_candidates(self, volunteer_id: str, filters: List[BatchFilter] = None,
                                 max_results: int = 100) -> Dict[str, Any]:
        """Get courses eligible for batch operations with advanced filtering"""
        try:
            # Validate reviewer permissions
            if not await self._validate_batch_permissions(volunteer_id):
                return {'error': 'Insufficient permissions for batch operations'}
            
            # Get filtered courses
            candidates = await self._get_filtered_courses(filters or [], volunteer_id, max_results)
            
            # Categorize candidates by potential batch operations
            categorized_candidates = {
                'bulk_approvable': [],
                'needs_attention': [],
                'quick_rejectable': [],
                'requires_individual_review': []
            }
            
            for course in candidates:
                category = await self._categorize_for_batch_operation(course)
                categorized_candidates[category].append({
                    'course_id': course['course_id'],
                    'title': course['title'],
                    'category': course.get('category'),
                    'priority': course.get('priority_level'),
                    'waiting_hours': course.get('hours_waiting'),
                    'file_count': course.get('file_count'),
                    'contributor_reputation': course.get('contributor_reputation'),
                    'complexity_score': course.get('complexity_score'),
                    'suggested_action': self._suggest_batch_action(course)
                })
            
            # Generate batch operation suggestions
            suggestions = await self._generate_batch_suggestions(categorized_candidates, volunteer_id)
            
            return {
                'total_candidates': len(candidates),
                'categorized_candidates': categorized_candidates,
                'batch_suggestions': suggestions,
                'available_templates': list(self.quick_review_templates.keys()),
                'filters_applied': [f.criteria.value for f in (filters or [])],
                'max_batch_size': self.max_batch_size
            }
            
        except Exception as e:
            logger.error(f"Failed to get batch candidates: {e}")
            return {'error': f'Failed to get candidates: {str(e)}'}
    
    async def create_custom_review_template(self, volunteer_id: str, template_name: str,
                                          template_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create custom review template for batch operations"""
        try:
            # Validate reviewer permissions
            if not await self._validate_batch_permissions(volunteer_id):
                return {'error': 'Insufficient permissions'}
            
            # Validate template configuration
            required_fields = ['decision', 'feedback', 'suggestions', 'quality_rating']
            if not all(field in template_config for field in required_fields):
                return {'error': f'Template must include: {", ".join(required_fields)}'}
            
            # Store custom template
            template_id = await self._store_custom_template(volunteer_id, template_name, template_config)
            
            return {
                'success': True,
                'template_id': template_id,
                'template_name': template_name,
                'message': 'Custom review template created successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to create custom template: {e}")
            return {'error': f'Template creation failed: {str(e)}'}
    
    async def get_batch_operation_history(self, volunteer_id: str, days: int = 30,
                                        limit: int = 50) -> List[Dict]:
        """Get volunteer's batch operation history"""
        try:
            history_query = """
                SELECT 
                    bo.operation_id,
                    bo.operation_type,
                    bo.total_courses,
                    bo.successful_count,
                    bo.failed_count,
                    bo.processing_time_seconds,
                    bo.created_at,
                    bo.operation_params
                FROM batch_operations bo
                WHERE bo.volunteer_id = $1
                  AND bo.created_at > NOW() - INTERVAL '%s days'
                ORDER BY bo.created_at DESC
                LIMIT $2
            """ % days
            
            history = await supabase_client.execute_query(history_query, volunteer_id, limit)
            
            # Format history entries
            formatted_history = []
            for entry in history:
                formatted_entry = {
                    'operation_id': entry['operation_id'],
                    'operation_type': entry['operation_type'],
                    'summary': {
                        'total_courses': entry['total_courses'],
                        'successful': entry['successful_count'],
                        'failed': entry['failed_count'],
                        'success_rate': round((entry['successful_count'] / entry['total_courses']) * 100, 1) if entry['total_courses'] > 0 else 0
                    },
                    'performance': {
                        'processing_time_seconds': entry['processing_time_seconds'],
                        'average_time_per_course': round(entry['processing_time_seconds'] / entry['total_courses'], 2) if entry['total_courses'] > 0 else 0
                    },
                    'created_at': entry['created_at'],
                    'operation_params': entry.get('operation_params')
                }
                formatted_history.append(formatted_entry)
            
            return formatted_history
            
        except Exception as e:
            logger.error(f"Failed to get batch operation history: {e}")
            return []
    
    async def analyze_batch_efficiency(self, volunteer_id: str, operation_types: List[BatchOperation] = None,
                                     period_days: int = 30) -> Dict[str, Any]:
        """Analyze volunteer's batch operation efficiency"""
        try:
            # Get batch operation statistics
            efficiency_query = """
                SELECT 
                    operation_type,
                    COUNT(*) as operation_count,
                    SUM(total_courses) as total_courses_processed,
                    SUM(successful_count) as total_successful,
                    AVG(processing_time_seconds) as avg_processing_time,
                    AVG(successful_count * 1.0 / total_courses) as avg_success_rate
                FROM batch_operations
                WHERE volunteer_id = $1
                  AND created_at > NOW() - INTERVAL '%s days'
                GROUP BY operation_type
                ORDER BY operation_count DESC
            """ % period_days
            
            stats = await supabase_client.execute_query(efficiency_query, volunteer_id)
            
            # Calculate efficiency metrics
            efficiency_analysis = {
                'period_days': period_days,
                'operation_statistics': [],
                'overall_metrics': {
                    'total_operations': 0,
                    'total_courses_processed': 0,
                    'overall_success_rate': 0,
                    'time_savings_vs_individual': 0
                },
                'recommendations': []
            }
            
            total_operations = 0
            total_courses = 0
            total_successful = 0
            
            for stat in stats:
                operation_analysis = {
                    'operation_type': stat['operation_type'],
                    'operation_count': stat['operation_count'],
                    'courses_processed': stat['total_courses_processed'],
                    'success_rate': round(stat['avg_success_rate'] * 100, 1),
                    'avg_processing_time_seconds': round(stat['avg_processing_time'], 1),
                    'efficiency_score': self._calculate_operation_efficiency(stat)
                }
                efficiency_analysis['operation_statistics'].append(operation_analysis)
                
                total_operations += stat['operation_count']
                total_courses += stat['total_courses_processed']
                total_successful += stat['total_successful']
            
            # Calculate overall metrics
            if total_operations > 0:
                efficiency_analysis['overall_metrics']['total_operations'] = total_operations
                efficiency_analysis['overall_metrics']['total_courses_processed'] = total_courses
                efficiency_analysis['overall_metrics']['overall_success_rate'] = round((total_successful / total_courses) * 100, 1) if total_courses > 0 else 0
                
                # Estimate time savings vs individual review
                avg_individual_review_time = 45 * 60  # 45 minutes in seconds
                total_individual_time = total_courses * avg_individual_review_time
                actual_batch_time = sum(s['avg_processing_time'] * s['operation_count'] for s in stats)
                time_savings = total_individual_time - actual_batch_time
                efficiency_analysis['overall_metrics']['time_savings_vs_individual'] = round(time_savings / 3600, 1)  # Convert to hours
            
            # Generate recommendations
            efficiency_analysis['recommendations'] = await self._generate_efficiency_recommendations(stats)
            
            return efficiency_analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze batch efficiency: {e}")
            return {'error': f'Efficiency analysis failed: {str(e)}'}
    
    # Private helper methods
    
    async def _validate_batch_permissions(self, volunteer_id: str) -> bool:
        """Validate if volunteer has permissions for batch operations"""
        try:
            # Check reviewer level and performance
            performance_data = await performance_tracker.calculate_volunteer_performance(volunteer_id)
            
            if 'error' in performance_data:
                return False
            
            # Check minimum requirements
            reviewer_level = performance_data['performance_indicators']['reviewer_level']
            overall_score = performance_data['performance_scores']['overall']
            reviews_completed = performance_data.get('all_time', {}).get('total_reviews', 0)
            
            # Requirements for batch operations
            level_requirements = {
                'New': False,
                'Active': False,
                'Experienced': True,
                'Advanced': True,
                'Expert': True
            }
            
            has_level_permission = level_requirements.get(reviewer_level, False)
            has_minimum_score = overall_score >= 60  # Minimum 60% performance score
            has_minimum_reviews = reviews_completed >= 20  # Minimum 20 completed reviews
            
            return has_level_permission and has_minimum_score and has_minimum_reviews
            
        except Exception as e:
            logger.error(f"Batch permission validation failed: {e}")
            return False
    
    async def _get_courses_by_ids(self, course_ids: List[str], volunteer_id: str) -> List[Dict]:
        """Get specific courses by IDs (with reviewer assignment validation)"""
        try:
            courses_query = """
                SELECT r.id as review_id, r.course_id, r.priority_level,
                       c.title, c.category, c.description,
                       COUNT(cf.id) as file_count,
                       SUM(cf.file_size) as total_size,
                       EXTRACT(EPOCH FROM (NOW() - r.created_at))/3600 as hours_waiting,
                       u.anonymous_id as contributor_anonymous_id
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                JOIN users u ON c.contributor_id = u.id
                LEFT JOIN course_files cf ON c.id = cf.course_id
                WHERE r.reviewer_id = $1 
                  AND r.status = 'pending'
                  AND r.course_id = ANY($2::uuid[])
                GROUP BY r.id, r.course_id, r.priority_level, c.title, c.category, 
                         c.description, u.anonymous_id
                ORDER BY r.priority_level DESC, r.created_at ASC
            """
            
            courses = await supabase_client.execute_query(courses_query, volunteer_id, course_ids)
            return courses or []
            
        except Exception as e:
            logger.error(f"Failed to get courses by IDs: {e}")
            return []
    
    async def _get_filtered_courses(self, filters: List[BatchFilter], volunteer_id: str, 
                                  limit: int = 100) -> List[Dict]:
        """Get courses based on filter criteria"""
        try:
            # Build dynamic query based on filters
            base_query = """
                SELECT r.id as review_id, r.course_id, r.priority_level,
                       c.title, c.category, c.description,
                       COUNT(cf.id) as file_count,
                       SUM(cf.file_size) as total_size,
                       EXTRACT(EPOCH FROM (NOW() - r.created_at))/3600 as hours_waiting,
                       u.anonymous_id as contributor_anonymous_id
                FROM reviews r
                JOIN courses c ON r.course_id = c.id
                JOIN users u ON c.contributor_id = u.id
                LEFT JOIN course_files cf ON c.id = cf.course_id
                WHERE r.reviewer_id = $1 AND r.status = 'pending'
            """
            
            # Add filter conditions
            conditions = []
            params = [volunteer_id]
            param_index = 2
            
            for filter_item in filters:
                condition, param_value = self._build_filter_condition(filter_item, param_index)
                if condition:
                    conditions.append(condition)
                    if param_value is not None:
                        params.append(param_value)
                        param_index += 1
            
            if conditions:
                base_query += " AND " + " AND ".join(conditions)
            
            base_query += """
                GROUP BY r.id, r.course_id, r.priority_level, c.title, c.category, 
                         c.description, u.anonymous_id
                ORDER BY r.priority_level DESC, r.created_at ASC
                LIMIT $%d
            """ % param_index
            
            params.append(limit)
            
            courses = await supabase_client.execute_query(base_query, *params)
            return courses or []
            
        except Exception as e:
            logger.error(f"Failed to get filtered courses: {e}")
            return []
    
    def _build_filter_condition(self, filter_item: BatchFilter, param_index: int) -> Tuple[str, Any]:
        """Build SQL condition for filter criteria"""
        try:
            criteria = filter_item.criteria
            operator = filter_item.operator
            value = filter_item.value
            
            if criteria == FilterCriteria.CATEGORY:
                if operator == 'eq':
                    return f"c.category = ${param_index}", value
                elif operator == 'in':
                    return f"c.category = ANY(${param_index}::text[])", value
                    
            elif criteria == FilterCriteria.PRIORITY:
                if operator == 'eq':
                    return f"r.priority_level = ${param_index}", value
                elif operator == 'gt':
                    return f"r.priority_level > ${param_index}", value
                elif operator == 'lt':
                    return f"r.priority_level < ${param_index}", value
                    
            elif criteria == FilterCriteria.WAITING_TIME:
                if operator == 'gt':
                    return f"EXTRACT(EPOCH FROM (NOW() - r.created_at))/3600 > ${param_index}", value
                elif operator == 'lt':
                    return f"EXTRACT(EPOCH FROM (NOW() - r.created_at))/3600 < ${param_index}", value
                    
            elif criteria == FilterCriteria.FILE_COUNT:
                if operator == 'gt':
                    return "COUNT(cf.id) > $%d" % param_index, value
                elif operator == 'lt':
                    return "COUNT(cf.id) < $%d" % param_index, value
                elif operator == 'range':
                    min_val, max_val = value
                    return f"COUNT(cf.id) BETWEEN {min_val} AND {max_val}", None
            
            return "", None
            
        except Exception as e:
            logger.error(f"Failed to build filter condition: {e}")
            return "", None
    
    async def _execute_bulk_approve(self, volunteer_id: str, courses: List[Dict], 
                                  params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute bulk approval operation"""
        try:
            results = {'successful': [], 'failed': [], 'detailed_results': []}
            
            # Create feedback template for bulk approval
            feedback_template = ReviewFeedback(
                decision=ReviewDecision.APPROVED,
                quality_rating=ReviewQuality.GOOD,
                feedback_text=params.get('feedback', 'Courses meet community standards and are approved for publication.'),
                improvement_suggestions=params.get('suggestions', ['Good quality content', 'Meets community standards']),
                category_scores={cat: 4 for cat in ['content_accuracy', 'educational_value', 'file_quality', 'organization', 'appropriateness']}
            )
            
            # Process each course
            for course in courses:
                try:
                    result = await review_processor.process_review_decision(
                        course['review_id'],
                        volunteer_id,
                        feedback_template
                    )
                    
                    if result['success']:
                        results['successful'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'approved',
                            'message': 'Successfully approved'
                        })
                    else:
                        results['failed'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'failed',
                            'error': result.get('message', 'Unknown error')
                        })
                        
                except Exception as e:
                    results['failed'].append(course['course_id'])
                    results['detailed_results'].append({
                        'course_id': course['course_id'],
                        'title': course['title'],
                        'status': 'failed',
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Bulk approve operation failed: {e}")
            return {'successful': [], 'failed': [], 'detailed_results': [{'error': str(e)}]}
    
    async def _execute_bulk_reject(self, volunteer_id: str, courses: List[Dict], 
                                 params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute bulk rejection operation"""
        try:
            results = {'successful': [], 'failed': [], 'detailed_results': []}
            
            # Create feedback template for bulk rejection
            feedback_template = ReviewFeedback(
                decision=ReviewDecision.REJECTED,
                quality_rating=ReviewQuality.POOR,
                feedback_text=params.get('feedback', 'Courses do not meet minimum quality standards.'),
                improvement_suggestions=params.get('suggestions', ['Review content quality', 'Improve organization', 'Address technical issues']),
                category_scores={cat: 2 for cat in ['content_accuracy', 'educational_value', 'file_quality', 'organization', 'appropriateness']}
            )
            
            # Process each course
            for course in courses:
                try:
                    result = await review_processor.process_review_decision(
                        course['review_id'],
                        volunteer_id,
                        feedback_template
                    )
                    
                    if result['success']:
                        results['successful'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'rejected',
                            'message': 'Successfully rejected'
                        })
                    else:
                        results['failed'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'failed',
                            'error': result.get('message', 'Unknown error')
                        })
                        
                except Exception as e:
                    results['failed'].append(course['course_id'])
                    results['detailed_results'].append({
                        'course_id': course['course_id'],
                        'title': course['title'],
                        'status': 'failed',
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Bulk reject operation failed: {e}")
            return {'successful': [], 'failed': [], 'detailed_results': [{'error': str(e)}]}
    
    async def _execute_bulk_revision(self, volunteer_id: str, courses: List[Dict], 
                                   params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute bulk revision request operation"""
        try:
            results = {'successful': [], 'failed': [], 'detailed_results': []}
            
            # Create feedback template for bulk revision
            feedback_template = ReviewFeedback(
                decision=ReviewDecision.NEEDS_REVISION,
                quality_rating=ReviewQuality.ACCEPTABLE,
                feedback_text=params.get('feedback', 'Courses require improvements before publication.'),
                improvement_suggestions=params.get('suggestions', ['Address content issues', 'Improve file quality', 'Enhance organization']),
                category_scores={cat: 3 for cat in ['content_accuracy', 'educational_value', 'file_quality', 'organization', 'appropriateness']}
            )
            
            # Process each course
            for course in courses:
                try:
                    result = await review_processor.process_review_decision(
                        course['review_id'],
                        volunteer_id,
                        feedback_template
                    )
                    
                    if result['success']:
                        results['successful'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'needs_revision',
                            'message': 'Revision requested'
                        })
                    else:
                        results['failed'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'failed',
                            'error': result.get('message', 'Unknown error')
                        })
                        
                except Exception as e:
                    results['failed'].append(course['course_id'])
                    results['detailed_results'].append({
                        'course_id': course['course_id'],
                        'title': course['title'],
                        'status': 'failed',
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Bulk revision operation failed: {e}")
            return {'successful': [], 'failed': [], 'detailed_results': [{'error': str(e)}]}
    
    async def _execute_batch_feedback(self, volunteer_id: str, courses: List[Dict], 
                                    params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute batch feedback application"""
        # Similar to other operations but applies custom feedback to multiple courses
        pass
    
    async def _execute_quick_review(self, volunteer_id: str, courses: List[Dict], 
                                  params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute quick review using predefined templates"""
        try:
            template_name = params.get('template', 'standard_approval')
            template = self.quick_review_templates.get(template_name)
            
            if not template:
                return {'successful': [], 'failed': [], 'detailed_results': [{'error': 'Invalid template'}]}
            
            results = {'successful': [], 'failed': [], 'detailed_results': []}
            
            # Create feedback from template
            feedback_template = ReviewFeedback(
                decision=template['decision'],
                quality_rating=template['quality_rating'],
                feedback_text=template['feedback'],
                improvement_suggestions=template['suggestions'],
                category_scores={cat: 3 for cat in ['content_accuracy', 'educational_value', 'file_quality', 'organization', 'appropriateness']}
            )
            
            # Process each course quickly
            for course in courses:
                try:
                    result = await review_processor.process_review_decision(
                        course['review_id'],
                        volunteer_id,
                        feedback_template
                    )
                    
                    if result['success']:
                        results['successful'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': result['decision'],
                            'message': f'Quick review completed using {template_name} template'
                        })
                    else:
                        results['failed'].append(course['course_id'])
                        results['detailed_results'].append({
                            'course_id': course['course_id'],
                            'title': course['title'],
                            'status': 'failed',
                            'error': result.get('message', 'Unknown error')
                        })
                        
                except Exception as e:
                    results['failed'].append(course['course_id'])
                    results['detailed_results'].append({
                        'course_id': course['course_id'],
                        'title': course['title'],
                        'status': 'failed',
                        'error': str(e)
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Quick review operation failed: {e}")
            return {'successful': [], 'failed': [], 'detailed_results': [{'error': str(e)}]}
    
    async def _categorize_for_batch_operation(self, course: Dict) -> str:
        """Categorize course for appropriate batch operation"""
        try:
            file_count = course.get('file_count', 0)
            waiting_hours = course.get('hours_waiting', 0)
            contributor_reputation = course.get('contributor_reputation', 'new')
            
            # Simple categorization logic
            if (file_count >= 5 and waiting_hours > 48 and 
                contributor_reputation in ['verified', 'expert']):
                return 'bulk_approvable'
            elif file_count < 2 or waiting_hours > 168:  # 1 week
                return 'needs_attention'
            elif file_count < 3 and contributor_reputation == 'new':
                return 'quick_rejectable'
            else:
                return 'requires_individual_review'
                
        except Exception as e:
            logger.error(f"Course categorization failed: {e}")
            return 'requires_individual_review'
    
    def _suggest_batch_action(self, course: Dict) -> str:
        """Suggest appropriate batch action for course"""
        try:
            category = self._categorize_for_batch_operation(course)
            
            suggestions = {
                'bulk_approvable': 'Consider for bulk approval',
                'needs_attention': 'Requires individual review',
                'quick_rejectable': 'Consider for quick rejection',
                'requires_individual_review': 'Individual review recommended'
            }
            
            return suggestions.get(category, 'Individual review recommended')
            
        except Exception as e:
            logger.error(f"Batch action suggestion failed: {e}")
            return 'Individual review recommended'
    
    async def _generate_batch_suggestions(self, categorized_candidates: Dict, volunteer_id: str) -> List[Dict]:
        """Generate intelligent batch operation suggestions"""
        try:
            suggestions = []
            
            # Bulk approval suggestion
            bulk_approvable = categorized_candidates.get('bulk_approvable', [])
            if len(bulk_approvable) >= 3:
                suggestions.append({
                    'operation_type': 'bulk_approve',
                    'candidates': len(bulk_approvable),
                    'estimated_time_savings': f"{len(bulk_approvable) * 30} minutes",
                    'description': f"Bulk approve {len(bulk_approvable)} high-quality courses from verified contributors"
                })
            
            # Quick rejection suggestion
            quick_rejectable = categorized_candidates.get('quick_rejectable', [])
            if len(quick_rejectable) >= 2:
                suggestions.append({
                    'operation_type': 'bulk_reject',
                    'candidates': len(quick_rejectable),
                    'estimated_time_savings': f"{len(quick_rejectable) * 20} minutes",
                    'description': f"Quick reject {len(quick_rejectable)} low-quality submissions"
                })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to generate batch suggestions: {e}")
            return []
    
    async def _store_custom_template(self, volunteer_id: str, template_name: str, 
                                   template_config: Dict[str, Any]) -> str:
        """Store custom review template"""
        try:
            template_id = str(uuid.uuid4())
            
            await supabase_client.execute_command(
                """
                INSERT INTO custom_review_templates (
                    id, volunteer_id, template_name, template_config, created_at
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                template_id, volunteer_id, template_name, template_config, datetime.utcnow()
            )
            
            return template_id
            
        except Exception as e:
            logger.error(f"Failed to store custom template: {e}")
            raise
    
    async def _log_batch_operation(self, volunteer_id: str, result: BatchOperationResult, 
                                 params: Dict[str, Any]):
        """Log batch operation for audit and analytics"""
        try:
            await supabase_client.execute_command(
                """
                INSERT INTO batch_operations (
                    operation_id, volunteer_id, operation_type, total_courses,
                    successful_count, failed_count, processing_time_seconds,
                    operation_params, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                result.operation_id, volunteer_id, result.operation_type.value,
                result.total_selected, result.successful, result.failed,
                result.processing_time_seconds, params, datetime.utcnow()
            )
            
        except Exception as e:
            logger.error(f"Failed to log batch operation: {e}")
    
    def _calculate_operation_efficiency(self, operation_stats: Dict) -> float:
        """Calculate efficiency score for batch operation type"""
        try:
            success_rate = operation_stats['avg_success_rate']
            avg_time = operation_stats['avg_processing_time']
            course_count = operation_stats['total_courses_processed']
            
            # Efficiency based on success rate, speed, and volume
            efficiency_score = (success_rate * 40 +  # 40% weight on success
                              (1 / max(avg_time / 60, 1)) * 30 +  # 30% weight on speed
                              min(course_count / 10, 10) * 30)  # 30% weight on volume
            
            return round(min(100, efficiency_score), 1)
            
        except Exception as e:
            logger.error(f"Efficiency calculation failed: {e}")
            return 0.0
    
    async def _generate_efficiency_recommendations(self, stats: List[Dict]) -> List[str]:
        """Generate efficiency improvement recommendations"""
        try:
            recommendations = []
            
            for stat in stats:
                operation_type = stat['operation_type']
                success_rate = stat['avg_success_rate']
                avg_time = stat['avg_processing_time']
                
                if success_rate < 0.8:
                    recommendations.append(f"Improve {operation_type} accuracy - consider more selective criteria")
                
                if avg_time > 300:  # 5 minutes
                    recommendations.append(f"Optimize {operation_type} speed - consider using quick review templates")
                
                if stat['operation_count'] < 5:
                    recommendations.append(f"Increase usage of {operation_type} for better efficiency")
            
            if not recommendations:
                recommendations.append("Excellent batch operation performance - keep up the great work!")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Failed to generate efficiency recommendations: {e}")
            return ["Unable to generate recommendations"]

# Global instance
batch_operations_manager = BatchOperationsManager()