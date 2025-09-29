"""
Bulk Operations Module - REST API Implementation
Handles bulk course uploads and other batch operations using Supabase REST API
"""
import asyncio
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager

logger = logging.getLogger(__name__)

@dataclass
class BulkCourseData:
    """Bulk course upload data structure"""
    title: str
    description: str
    category: str
    tags: List[str]
    files: List[Dict[str, Any]]
    metadata: Dict[str, Any]

@dataclass
class BulkUploadResult:
    """Result of bulk upload operation"""
    batch_id: str
    total_courses: int
    successful_uploads: int
    failed_uploads: int
    processing_time: float
    course_ids: List[str]
    errors: List[Dict[str, Any]]

class BulkOperationsManager:
    """Manages bulk operations using Supabase REST API"""
    
    def __init__(self):
        self.max_batch_size = 100  # Maximum courses per batch
        self.chunk_size = 10      # Process in chunks for performance
    
    async def initialize(self):
        """Initialize Supabase client if needed"""
        if not hasattr(supabase_client, 'client') or supabase_client.client is None:
            await supabase_client.initialize()
        
        # Initialize anonymous manager if needed
        if hasattr(anonymous_manager, 'initialize'):
            await anonymous_manager.initialize()
    
    async def get_anonymous_id_from_telegram(self, telegram_id: int) -> str:
        """Convert Telegram ID to anonymous ID for bulk operations"""
        try:
            user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
            if not user:
                # Create new anonymous user
                user = await anonymous_manager.create_anonymous_user(telegram_id)
            return user['anonymous_id']
        except Exception as e:
            logger.error(f"Failed to get anonymous ID for Telegram user {telegram_id}: {e}")
            raise
        
    async def bulk_upload_courses(
        self, 
        courses: List[BulkCourseData], 
        contributor_anonymous_id: str,
        batch_metadata: Dict[str, Any] = None
    ) -> BulkUploadResult:
        """
        Upload multiple courses in bulk using Supabase REST API
        """
        start_time = datetime.now()
        batch_id = str(uuid.uuid4())
        
        if len(courses) > self.max_batch_size:
            raise ValueError(f"Batch size exceeds maximum of {self.max_batch_size} courses")
        
        # Ensure Supabase client is initialized
        await self.initialize()
        
        logger.info(f"Starting bulk upload of {len(courses)} courses for contributor {contributor_anonymous_id}")
        
        course_ids = []
        successful_uploads = 0
        failed_uploads = 0
        errors = []
        
        # Process courses in chunks for better performance
        for chunk_start in range(0, len(courses), self.chunk_size):
            chunk_end = min(chunk_start + self.chunk_size, len(courses))
            chunk = courses[chunk_start:chunk_end]
            
            logger.info(f"Processing chunk {chunk_start//self.chunk_size + 1}: courses {chunk_start+1}-{chunk_end}")
            
            # Process chunk
            chunk_results = await self._process_course_chunk(
                chunk, contributor_anonymous_id, batch_id, chunk_start
            )
            
            successful_uploads += chunk_results['successful']
            failed_uploads += chunk_results['failed']
            course_ids.extend(chunk_results['course_ids'])
            errors.extend(chunk_results['errors'])
            
            # Small delay between chunks to avoid overwhelming the API
            if chunk_end < len(courses):
                await asyncio.sleep(0.5)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Log batch operation
        await self._log_bulk_operation(
            batch_id=batch_id,
            operation_type="bulk_course_upload",
            contributor_id=contributor_anonymous_id,
            total_items=len(courses),
            successful_items=successful_uploads,
            failed_items=failed_uploads,
            processing_time=processing_time,
            metadata=batch_metadata or {}
        )
        
        logger.info(f"Bulk upload completed: {successful_uploads} successful, {failed_uploads} failed")
        
        return BulkUploadResult(
            batch_id=batch_id,
            total_courses=len(courses),
            successful_uploads=successful_uploads,
            failed_uploads=failed_uploads,
            processing_time=processing_time,
            course_ids=course_ids,
            errors=errors
        )
    
    async def _process_course_chunk(
        self, 
        courses: List[BulkCourseData], 
        contributor_id: str, 
        batch_id: str,
        start_index: int
    ) -> Dict[str, Any]:
        """Process a chunk of courses using REST API"""
        
        successful = 0
        failed = 0
        course_ids = []
        errors = []
        
        # Prepare course data for batch insert
        course_records = []
        
        for i, course in enumerate(courses):
            try:
                course_id = str(uuid.uuid4())
                current_time = datetime.utcnow().isoformat()
                
                # Prepare course record
                course_record = {
                    'id': course_id,
                    'title': course.title,
                    'description': course.description,
                    'category': course.category,
                    'anonymous_contributor': contributor_id,
                    'status': 'pending_review',
                    'file_attachments': course.files,  # JSON field
                    'tags': course.tags,  # JSON field
                    'metadata': {
                        **course.metadata,
                        'batch_id': batch_id,
                        'batch_index': start_index + i
                    },
                    'created_at': current_time,
                    'updated_at': current_time
                }
                
                course_records.append(course_record)
                course_ids.append(course_id)
                
                # Files and tags are stored as JSON in the course record itself
                
                successful += 1
                
            except Exception as e:
                failed += 1
                error_info = {
                    'course_index': start_index + i,
                    'course_title': course.title if hasattr(course, 'title') else 'Unknown',
                    'error': str(e),
                    'error_type': type(e).__name__
                }
                errors.append(error_info)
                logger.error(f"Failed to prepare course {start_index + i}: {e}")
        
        # Bulk insert using Supabase REST API
        if course_records:
            try:
                # Insert courses (using the existing table structure)
                insert_result = supabase_client.client.table('courses').insert(course_records).execute()
                logger.info(f"Successfully inserted {len(course_records)} courses")
                
                # Note: Files are stored as JSON in file_attachments field, no separate files table needed
                # Note: Tags are stored as JSON in tags field, no separate course_tags table needed
                
            except Exception as insert_error:
                logger.error(f"Bulk insert failed: {insert_error}")
                # Mark all courses in this chunk as failed
                for i in range(len(course_records)):
                    errors.append({
                        'course_index': start_index + i,
                        'course_title': course_records[i]['title'],
                        'error': str(insert_error),
                        'error_type': 'bulk_insert_error'
                    })
                failed = len(course_records)
                successful = 0
                course_ids = []
        
        return {
            'successful': successful,
            'failed': failed,
            'course_ids': course_ids,
            'errors': errors
        }
    
    async def _log_bulk_operation(
        self,
        batch_id: str,
        operation_type: str,
        contributor_id: str,
        total_items: int,
        successful_items: int,
        failed_items: int,
        processing_time: float,
        metadata: Dict[str, Any]
    ):
        """Log bulk operation for tracking and analytics"""
        try:
            log_record = {
                'id': str(uuid.uuid4()),
                'batch_id': batch_id,
                'operation_type': operation_type,
                'contributor_anonymous_id': contributor_id,
                'total_items': total_items,
                'successful_items': successful_items,
                'failed_items': failed_items,
                'processing_time_seconds': processing_time,
                'metadata': metadata,
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Insert log record into batch_operations table (closest match)
            batch_record = {
                'operation_id': str(uuid.uuid4()),  # Convert UUID to string
                'operation_type': operation_type,
                'total_courses': total_items,
                'successful_count': successful_items,
                'failed_count': failed_items,
                'processing_time_seconds': processing_time,
                'operation_params': {
                    **metadata,
                    'batch_id': batch_id,
                    'contributor_id': contributor_id
                },
                'created_at': datetime.utcnow().isoformat()
            }
            supabase_client.client.table('batch_operations').insert([batch_record]).execute()
            logger.info(f"Logged bulk operation {batch_id}")
            
        except Exception as e:
            logger.error(f"Failed to log bulk operation: {e}")
    
    async def get_bulk_operation_status(self, batch_id: str) -> Dict[str, Any]:
        """Get status of a bulk operation"""
        try:
            # Ensure Supabase client is initialized
            await self.initialize()
            # Get bulk operation log from batch_operations table
            log_result = supabase_client.client.table('batch_operations').select('*').contains('operation_params', {'batch_id': batch_id}).execute()
            
            if not log_result.data:
                return {'success': False, 'message': 'Batch operation not found'}
            
            operation_log = log_result.data[0]
            
            # Get courses created in this batch
            courses_result = supabase_client.client.table('courses').select('id, title, status').contains('metadata', {'batch_id': batch_id}).execute()
            
            courses_by_status = {}
            for course in courses_result.data:
                status = course['status']
                if status not in courses_by_status:
                    courses_by_status[status] = []
                courses_by_status[status].append({
                    'id': course['id'],
                    'title': course['title']
                })
            
            return {
                'success': True,
                'batch_id': batch_id,
                'operation_type': operation_log['operation_type'],
                'total_items': operation_log['total_courses'],  # Correct field name
                'successful_items': operation_log['successful_count'],  # Correct field name
                'failed_items': operation_log['failed_count'],  # Correct field name
                'processing_time': operation_log['processing_time_seconds'],
                'courses_by_status': courses_by_status,
                'created_at': operation_log['created_at']
            }
            
        except Exception as e:
            logger.error(f"Failed to get bulk operation status: {e}")
            return {'success': False, 'message': f'Error retrieving status: {str(e)}'}
    
    async def bulk_update_course_status(self, course_ids: List[str], new_status: str, reviewer_id: str = None) -> Dict[str, Any]:
        """Bulk update course status"""
        try:
            # Ensure Supabase client is initialized
            await self.initialize()
            update_data = {
                'status': new_status,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            if reviewer_id:
                update_data['reviewer_id'] = reviewer_id
                update_data['reviewed_at'] = datetime.utcnow().isoformat()
            
            # Supabase REST API bulk update
            result = supabase_client.client.table('courses').update(update_data).in_('id', course_ids).execute()
            
            updated_count = len(result.data)
            
            logger.info(f"Bulk updated {updated_count} courses to status '{new_status}'")
            
            return {
                'success': True,
                'updated_count': updated_count,
                'course_ids': course_ids,
                'new_status': new_status
            }
            
        except Exception as e:
            logger.error(f"Bulk update failed: {e}")
            return {
                'success': False,
                'message': f'Bulk update failed: {str(e)}'
            }
    
    async def bulk_delete_courses(self, course_ids: List[str], admin_id: str) -> Dict[str, Any]:
        """Bulk delete courses (admin only)"""
        try:
            # Ensure Supabase client is initialized
            await self.initialize()
            # Verify admin permissions
            admin_user = await anonymous_manager.get_user_by_anonymous_id(admin_id)
            if not admin_user or not admin_user.get('permissions', {}).get('manage_users', False):
                return {'success': False, 'message': 'Insufficient permissions for bulk delete'}
            
            # Files and tags are stored as JSON in the course record, no separate deletion needed
            
            # Delete courses
            result = supabase_client.client.table('courses').delete().in_('id', course_ids).execute()
            
            deleted_count = len(result.data)
            
            logger.info(f"Bulk deleted {deleted_count} courses by admin {admin_id}")
            
            return {
                'success': True,
                'deleted_count': deleted_count,
                'course_ids': course_ids
            }
            
        except Exception as e:
            logger.error(f"Bulk delete failed: {e}")
            return {
                'success': False,
                'message': f'Bulk delete failed: {str(e)}'
            }

# Global instance
bulk_operations_manager = BulkOperationsManager()
