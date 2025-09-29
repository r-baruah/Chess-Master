"""
Enhanced Course Upload System with Progress Tracking and Session Management

This module provides an improved course upload workflow with:
- Step-by-step guided process
- Progress tracking and status indicators
- Input validation and format verification
- Upload resumption capability
- Session persistence for interrupted uploads
"""

import asyncio
import json
import uuid
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from pyrogram import Client
    from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
    from pyrogram.errors import FloodWait
except ImportError:
    # Mock pyrogram imports for testing
    Client = None
    Message = None
    InlineKeyboardMarkup = None
    InlineKeyboardButton = None
    FloodWait = Exception

from .redis_state import RedisStateManager as RedisState
from .supabase_client import SupabaseClient
from .multi_channel_manager import MultiChannelManager
try:
    from .volunteer_system import volunteer_manager
except ImportError:
    volunteer_manager = None
try:
    from utils import get_size, clean_text
except ImportError:
    # Define fallback functions for validation
    def get_size(size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
    
    def clean_text(text):
        return text.strip() if text else ""

logger = logging.getLogger(__name__)

class UploadStep(Enum):
    """Enumeration of upload process steps"""
    COLLECTING_METADATA = 1
    COLLECTING_CATEGORY_TAGS = 2
    COLLECTING_FILES = 3
    REVIEW_CONFIRMATION = 4
    FINAL_SUBMISSION = 5

class UploadStatus(Enum):
    """Upload session status"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class CourseMetadata:
    """Course metadata structure"""
    title: str
    description: str
    category: Optional[str] = None
    tags: List[str] = None
    difficulty_level: int = 1
    estimated_duration: Optional[int] = None  # in minutes
    prerequisites: List[str] = None

@dataclass
class FileInfo:
    """Course file information"""
    file_id: str
    file_name: str
    file_size: int
    file_type: str
    caption: Optional[str] = None
    message_id: Optional[int] = None
    channel_id: Optional[str] = None

@dataclass
class UploadSession:
    """Upload session data structure"""
    user_id: int
    anonymous_id: Optional[str]
    session_id: str
    status: UploadStatus
    current_step: UploadStep
    total_steps: int = 5
    course_metadata: Optional[CourseMetadata] = None
    files: List[FileInfo] = None
    banner_file_id: Optional[str] = None
    started_at: datetime = None
    updated_at: datetime = None
    resume_token: Optional[str] = None
    validation_errors: List[str] = None
    
    def __post_init__(self):
        if self.files is None:
            self.files = []
        if self.validation_errors is None:
            self.validation_errors = []
        if self.started_at is None:
            self.started_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()

class EnhancedCourseUploader:
    """Enhanced course uploader with session management and progress tracking"""
    
    def __init__(self, supabase_client: SupabaseClient, redis_client: RedisState, 
                 multi_channel_manager: MultiChannelManager):
        self.supabase = supabase_client
        self.redis = redis_client
        self.multi_channel_manager = multi_channel_manager
        self.session_timeout = 3600  # 1 hour
        
        # Course categories and validation rules
        self.valid_categories = [
            "Beginner Chess", "Openings", "Middlegame", "Endgame", 
            "Tactics", "Strategy", "Famous Games", "Master Classes",
            "Chess History", "Chess Psychology", "Analysis Tools"
        ]
        
        self.max_title_length = 100
        self.max_description_length = 500
        self.max_files_per_course = 50
        self.max_file_size = 2 * 1024 * 1024 * 1024  # 2GB per file
        
    async def start_enhanced_upload(self, user_id: int, anonymous_id: str = None) -> Dict[str, Any]:
        """Initialize enhanced course upload process with session management"""
        try:
            # Check if user already has an active session
            existing_session = await self.get_active_session(user_id)
            if existing_session:
                return {
                    "success": False,
                    "message": "You already have an active upload session. Use /resume_upload to continue or /cancel_upload to start over.",
                    "session_id": existing_session.session_id,
                    "current_step": existing_session.current_step.value
                }
            
            # Get or create anonymous ID for the user
            if not anonymous_id:
                anonymous_id = await self._get_user_anonymous_id(user_id)
                if not anonymous_id:
                    anonymous_id = await self._create_user_anonymous_id(user_id)
            
            # Create new upload session
            session = UploadSession(
                user_id=user_id,
                anonymous_id=anonymous_id,
                session_id=str(uuid.uuid4()),
                status=UploadStatus.ACTIVE,
                current_step=UploadStep.COLLECTING_METADATA
            )
            
            # Save session to Redis
            await self._save_session(session)
            
            logger.info(f"Started enhanced upload session {session.session_id} for user {user_id}")
            
            return {
                "success": True,
                "session": session,
                "progress": self._get_progress_info(session),
                "next_step": await self._get_step_instructions(session.current_step)
            }
            
        except Exception as e:
            logger.error(f"Failed to start enhanced upload for user {user_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to initialize upload session: {str(e)}"
            }
    
    async def process_upload_step(self, user_id: int, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process individual upload step with validation and progress tracking"""
        try:
            session = await self.get_active_session(user_id)
            if not session:
                return {
                    "success": False,
                    "message": "No active upload session found. Use /addcourse to start a new upload."
                }
            
            # Process step based on current step
            result = await self._process_step_data(session, step_data)
            
            if not result["success"]:
                return result
            
            # Advance to next step if successful
            if session.current_step.value < session.total_steps:
                session.current_step = UploadStep(session.current_step.value + 1)
                session.updated_at = datetime.utcnow()
                await self._save_session(session)
            
            return {
                "success": True,
                "session": session,
                "progress": self._get_progress_info(session),
                "next_step": await self._get_step_instructions(session.current_step),
                "validation_messages": result.get("validation_messages", [])
            }
            
        except Exception as e:
            logger.error(f"Failed to process upload step for user {user_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to process upload step: {str(e)}"
            }
    
    async def _process_step_data(self, session: UploadSession, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data for the current step"""
        if session.current_step == UploadStep.COLLECTING_METADATA:
            return await self._process_metadata_step(session, step_data)
        elif session.current_step == UploadStep.COLLECTING_CATEGORY_TAGS:
            return await self._process_category_tags_step(session, step_data)
        elif session.current_step == UploadStep.COLLECTING_FILES:
            return await self._process_files_step(session, step_data)
        elif session.current_step == UploadStep.REVIEW_CONFIRMATION:
            return await self._process_review_step(session, step_data)
        elif session.current_step == UploadStep.FINAL_SUBMISSION:
            return await self._process_final_submission(session, step_data)
        else:
            return {"success": False, "message": "Invalid upload step"}
    
    async def _process_metadata_step(self, session: UploadSession, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process course title and description"""
        validation_errors = []
        validation_messages = []
        
        title = clean_text(step_data.get("title", "")).strip()
        description = clean_text(step_data.get("description", "")).strip()
        
        # Validate title
        if not title:
            validation_errors.append("Course title is required")
        elif len(title) > self.max_title_length:
            validation_errors.append(f"Course title must be {self.max_title_length} characters or less")
        elif len(title) < 5:
            validation_errors.append("Course title must be at least 5 characters long")
        
        # Validate description
        if not description:
            validation_errors.append("Course description is required")
        elif len(description) > self.max_description_length:
            validation_errors.append(f"Course description must be {self.max_description_length} characters or less")
        elif len(description) < 20:
            validation_errors.append("Course description must be at least 20 characters long")
        
        # Check for duplicate course titles
        if title:
            existing_course = await self._check_course_title_exists(title)
            if existing_course:
                validation_errors.append("A course with this title already exists. Please choose a different title.")
        
        if validation_errors:
            session.validation_errors = validation_errors
            await self._save_session(session)
            return {
                "success": False,
                "validation_errors": validation_errors,
                "message": "Please fix the validation errors and try again"
            }
        
        # Save metadata
        session.course_metadata = CourseMetadata(title=title, description=description)
        session.validation_errors = []
        
        validation_messages.append(f"✅ Course title: '{title}' (Valid)")
        validation_messages.append(f"✅ Description: {len(description)} characters (Valid)")
        
        return {
            "success": True,
            "validation_messages": validation_messages
        }
    
    async def _process_category_tags_step(self, session: UploadSession, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process course category and tags"""
        validation_errors = []
        validation_messages = []
        
        category = step_data.get("category", "").strip()
        tags = step_data.get("tags", [])
        difficulty_level = step_data.get("difficulty_level", 1)
        estimated_duration = step_data.get("estimated_duration")
        prerequisites = step_data.get("prerequisites", [])
        
        # Validate category
        if category and category not in self.valid_categories:
            validation_errors.append(f"Invalid category. Choose from: {', '.join(self.valid_categories)}")
        
        # Validate tags
        if tags:
            if len(tags) > 10:
                validation_errors.append("Maximum 10 tags allowed")
            for tag in tags:
                if len(tag.strip()) < 2:
                    validation_errors.append(f"Tag '{tag}' is too short (minimum 2 characters)")
                if len(tag.strip()) > 20:
                    validation_errors.append(f"Tag '{tag}' is too long (maximum 20 characters)")
        
        # Validate difficulty level
        if not isinstance(difficulty_level, int) or difficulty_level < 1 or difficulty_level > 5:
            validation_errors.append("Difficulty level must be between 1 and 5")
        
        # Validate estimated duration
        if estimated_duration and (not isinstance(estimated_duration, int) or estimated_duration < 5 or estimated_duration > 600):
            validation_errors.append("Estimated duration must be between 5 and 600 minutes")
        
        if validation_errors:
            session.validation_errors = validation_errors
            await self._save_session(session)
            return {
                "success": False,
                "validation_errors": validation_errors,
                "message": "Please fix the validation errors and try again"
            }
        
        # Update metadata
        if session.course_metadata:
            session.course_metadata.category = category
            session.course_metadata.tags = tags
            session.course_metadata.difficulty_level = difficulty_level
            session.course_metadata.estimated_duration = estimated_duration
            session.course_metadata.prerequisites = prerequisites
        
        session.validation_errors = []
        
        validation_messages.append(f"✅ Category: {category or 'Not specified'}")
        validation_messages.append(f"✅ Tags: {len(tags)} tag(s) added")
        validation_messages.append(f"✅ Difficulty Level: {difficulty_level}/5")
        if estimated_duration:
            validation_messages.append(f"✅ Estimated Duration: {estimated_duration} minutes")
        
        return {
            "success": True,
            "validation_messages": validation_messages
        }
    
    async def _process_files_step(self, session: UploadSession, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process course files with validation"""
        validation_errors = []
        validation_messages = []
        
        files_data = step_data.get("files", [])
        
        # Validate file count
        current_file_count = len(session.files)
        new_file_count = len(files_data)
        total_files = current_file_count + new_file_count
        
        if total_files > self.max_files_per_course:
            validation_errors.append(f"Maximum {self.max_files_per_course} files allowed per course. Current: {current_file_count}, Trying to add: {new_file_count}")
        
        if new_file_count == 0:
            validation_errors.append("No files provided in this step")
        
        # Validate each file
        total_size = sum(file.file_size for file in session.files)
        for file_data in files_data:
            file_info = FileInfo(**file_data)
            
            # Check file size
            if file_info.file_size > self.max_file_size:
                validation_errors.append(f"File '{file_info.file_name}' is too large (max {get_size(self.max_file_size)})")
            
            total_size += file_info.file_size
            
            # Check file name
            if not file_info.file_name or len(file_info.file_name.strip()) < 1:
                validation_errors.append("File name cannot be empty")
            
            # Check for duplicate file names in session
            existing_names = [f.file_name for f in session.files]
            if file_info.file_name in existing_names:
                validation_errors.append(f"Duplicate file name: '{file_info.file_name}'")
        
        # Check total course size (2GB limit)
        if total_size > (2 * 1024 * 1024 * 1024):
            validation_errors.append(f"Total course size exceeds 2GB limit. Current total: {get_size(total_size)}")
        
        if validation_errors:
            session.validation_errors = validation_errors
            await self._save_session(session)
            return {
                "success": False,
                "validation_errors": validation_errors,
                "message": "Please fix the validation errors and try again"
            }
        
        # Add validated files to session
        for file_data in files_data:
            session.files.append(FileInfo(**file_data))
        
        session.validation_errors = []
        
        validation_messages.append(f"✅ Added {new_file_count} file(s) successfully")
        validation_messages.append(f"✅ Total files: {len(session.files)}")
        validation_messages.append(f"✅ Total size: {get_size(total_size)}")
        
        return {
            "success": True,
            "validation_messages": validation_messages
        }
    
    async def _process_review_step(self, session: UploadSession, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process review and confirmation step"""
        action = step_data.get("action")
        
        if action == "confirm":
            return {"success": True, "message": "Course confirmed for submission"}
        elif action == "edit_metadata":
            session.current_step = UploadStep.COLLECTING_METADATA
            await self._save_session(session)
            return {"success": True, "message": "Returning to metadata editing"}
        elif action == "edit_category":
            session.current_step = UploadStep.COLLECTING_CATEGORY_TAGS
            await self._save_session(session)
            return {"success": True, "message": "Returning to category and tags editing"}
        elif action == "edit_files":
            session.current_step = UploadStep.COLLECTING_FILES
            await self._save_session(session)
            return {"success": True, "message": "Returning to files editing"}
        elif action == "add_banner":
            banner_file_id = step_data.get("banner_file_id")
            if banner_file_id:
                session.banner_file_id = banner_file_id
                await self._save_session(session)
                return {"success": True, "message": "Banner image added successfully"}
            else:
                return {"success": False, "message": "No banner image provided"}
        else:
            return {"success": False, "message": "Invalid review action"}
    
    async def _process_final_submission(self, session: UploadSession, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process final course submission"""
        try:
            # Final validation
            if not session.course_metadata:
                return {"success": False, "message": "Course metadata is missing"}
            
            if not session.files:
                return {"success": False, "message": "Course has no files"}
            
            # Create course ID
            course_id = str(uuid.uuid4())
            
            # Submit course for review
            submission_result = await self._submit_course_for_review(session, course_id)
            
            if submission_result["success"]:
                session.status = UploadStatus.COMPLETED
                await self._save_session(session)
                
                # Clean up session after successful submission
                await self._cleanup_session(session.session_id)
            
            return submission_result
            
        except Exception as e:
            logger.error(f"Failed to process final submission: {e}")
            return {"success": False, "message": f"Submission failed: {str(e)}"}
    
    async def get_active_session(self, user_id: int) -> Optional[UploadSession]:
        """Get user's active upload session"""
        try:
            session_key = f"upload_session:{user_id}"
            session_data = await self.redis.get(session_key)
            
            if not session_data:
                return None
            
            session_dict = json.loads(session_data)
            
            # Convert datetime strings back to datetime objects
            session_dict["started_at"] = datetime.fromisoformat(session_dict["started_at"])
            session_dict["updated_at"] = datetime.fromisoformat(session_dict["updated_at"])
            
            # Convert enum values back to enums
            session_dict["status"] = UploadStatus(session_dict["status"])
            session_dict["current_step"] = UploadStep(session_dict["current_step"])
            
            # Convert nested objects
            if session_dict.get("course_metadata"):
                session_dict["course_metadata"] = CourseMetadata(**session_dict["course_metadata"])
            
            if session_dict.get("files"):
                session_dict["files"] = [FileInfo(**f) for f in session_dict["files"]]
            
            return UploadSession(**session_dict)
            
        except Exception as e:
            logger.error(f"Failed to get session for user {user_id}: {e}")
            return None
    
    async def _save_session(self, session: UploadSession):
        """Save upload session to Redis"""
        try:
            session.updated_at = datetime.utcnow()
            
            # Convert to dictionary for JSON serialization
            session_dict = asdict(session)
            
            # Convert datetime objects to ISO strings
            session_dict["started_at"] = session.started_at.isoformat()
            session_dict["updated_at"] = session.updated_at.isoformat()
            
            # Convert enum values to strings
            session_dict["status"] = session.status.value
            session_dict["current_step"] = session.current_step.value
            
            session_key = f"upload_session:{session.user_id}"
            await self.redis.set(session_key, json.dumps(session_dict), ex=self.session_timeout)
            
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise
    
    def _get_progress_info(self, session: UploadSession) -> Dict[str, Any]:
        """Get progress information for the session"""
        progress_percentage = (session.current_step.value / session.total_steps) * 100
        
        return {
            "current_step": session.current_step.value,
            "total_steps": session.total_steps,
            "progress_percentage": int(progress_percentage),
            "status": session.status.value,
            "step_name": session.current_step.name,
            "files_added": len(session.files),
            "has_banner": session.banner_file_id is not None
        }
    
    async def _get_step_instructions(self, step: UploadStep) -> Dict[str, Any]:
        """Get instructions for the current step"""
        instructions = {
            UploadStep.COLLECTING_METADATA: {
                "title": "📝 Step 1: Course Information",
                "description": "Please provide the basic course information",
                "fields": [
                    {"name": "title", "type": "text", "required": True, "placeholder": "Enter course title"},
                    {"name": "description", "type": "textarea", "required": True, "placeholder": "Describe your course"}
                ],
                "next_button": "Continue to Categories & Tags"
            },
            UploadStep.COLLECTING_CATEGORY_TAGS: {
                "title": "🏷️ Step 2: Categories & Tags",
                "description": "Categorize your course and add relevant tags",
                "fields": [
                    {"name": "category", "type": "select", "required": False, "options": self.valid_categories},
                    {"name": "tags", "type": "multi_text", "required": False, "placeholder": "Add tags (press Enter after each)"},
                    {"name": "difficulty_level", "type": "number", "required": True, "min": 1, "max": 5, "default": 1},
                    {"name": "estimated_duration", "type": "number", "required": False, "placeholder": "Duration in minutes"}
                ],
                "next_button": "Continue to File Upload"
            },
            UploadStep.COLLECTING_FILES: {
                "title": "📁 Step 3: Course Files",
                "description": "Upload your course files or provide Telegram message links",
                "fields": [
                    {"name": "files", "type": "files", "required": True, "multiple": True}
                ],
                "next_button": "Review Course",
                "additional_info": f"Maximum {self.max_files_per_course} files, up to {get_size(self.max_file_size)} each"
            },
            UploadStep.REVIEW_CONFIRMATION: {
                "title": "👀 Step 4: Review & Confirm",
                "description": "Review your course details and confirm submission",
                "fields": [],
                "actions": ["confirm", "edit_metadata", "edit_category", "edit_files", "add_banner"],
                "next_button": "Submit Course"
            },
            UploadStep.FINAL_SUBMISSION: {
                "title": "🚀 Step 5: Final Submission",
                "description": "Your course is being processed and submitted for review",
                "fields": [],
                "next_button": "Complete"
            }
        }
        
        return instructions.get(step, {})
    
    async def _get_user_anonymous_id(self, user_id: int) -> Optional[str]:
        """Get user's anonymous ID from database"""
        try:
            # Use REST API instead of raw SQL
            result = self.supabase.client.table('users').select('id').eq('telegram_id', user_id).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get user anonymous ID: {e}")
            return None
    
    async def _create_user_anonymous_id(self, user_id: int) -> str:
        """Create new anonymous ID for user"""
        try:
            anonymous_id = str(uuid.uuid4())
            user_record = {
                'id': anonymous_id,
                'telegram_id': user_id,
                'created_at': datetime.utcnow().isoformat()
            }
            # Use REST API instead of raw SQL
            result = self.supabase.client.table('users').insert([user_record]).execute()
            if not result.data:
                raise Exception("Failed to create user record")
            return anonymous_id
        except Exception as e:
            logger.error(f"Failed to create user anonymous ID: {e}")
            raise
    
    async def _check_course_title_exists(self, title: str) -> bool:
        """Check if course title already exists"""
        try:
            # Use REST API with case-insensitive search
            result = self.supabase.client.table('courses').select('id').ilike('title', title).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Failed to check course title: {e}")
            return False
    
    async def _submit_course_for_review(self, session: UploadSession, course_id: str) -> Dict[str, Any]:
        """Submit completed course for volunteer review"""
        try:
            # Create course record
            course_data = {
                "id": course_id,
                "title": session.course_metadata.title,
                "description": session.course_metadata.description,
                "category": session.course_metadata.category,
                "difficulty_level": session.course_metadata.difficulty_level,
                "estimated_duration": session.course_metadata.estimated_duration,
                "contributor_id": session.anonymous_id,
                "status": "pending_review",
                "banner_link": session.banner_file_id,
                "created_at": datetime.utcnow()
            }
            
            # Insert course using REST API
            course_insert_result = self.supabase.client.table('courses').insert([course_data]).execute()
            if not course_insert_result.data:
                raise Exception("Failed to insert course record")
            
            # Insert course tags using REST API
            if session.course_metadata.tags:
                tag_records = []
                for tag in session.course_metadata.tags:
                    tag_records.append({
                        'id': str(uuid.uuid4()),
                        'course_id': course_id,
                        'tag': tag.strip(),
                        'created_at': datetime.utcnow().isoformat()
                    })
                if tag_records:
                    try:
                        self.supabase.client.table('course_tags').insert(tag_records).execute()
                    except Exception as tag_error:
                        logger.warning(f"Could not insert tags (table may not exist): {tag_error}")
            
            # Insert course files
            successful_files = 0
            failed_files = 0
            
            # Prepare file records for bulk insert
            file_records = []
            for file_info in session.files:
                file_record = {
                    'id': str(uuid.uuid4()),
                    'course_id': course_id,
                    'file_name': file_info.file_name,
                    'file_type': file_info.file_type,
                    'file_size': file_info.file_size,
                    'telegram_file_id': file_info.file_id,
                    'message_link': f"temp://processing/{file_info.file_id}",
                    'created_at': datetime.utcnow().isoformat()
                }
                file_records.append(file_record)
            
            # Bulk insert files using REST API
            if file_records:
                try:
                    file_result = self.supabase.client.table('files').insert(file_records).execute()
                    successful_files = len(file_result.data)
                    failed_files = len(file_records) - successful_files
                except Exception as e:
                    logger.error(f"Failed to insert course files: {e}")
                    successful_files = 0
                    failed_files = len(file_records)
            
            # Add to review queue
            try:
                priority = 2 if failed_files == 0 else 1
                reviewer_id = await volunteer_manager.assign_course_to_reviewer(course_id, priority)
                
                review_record = {
                    'id': str(uuid.uuid4()),
                    'course_id': course_id,
                    'contributor_id': session.anonymous_id,
                    'status': 'pending_review',
                    'priority': priority,
                    'assigned_reviewer': reviewer_id,
                    'created_at': datetime.utcnow().isoformat()
                }
                self.supabase.client.table('review_queue').insert([review_record]).execute()
                
            except Exception as e:
                logger.error(f"Failed to add course to review queue: {e}")
            
            return {
                "success": True,
                "course_id": course_id,
                "successful_files": successful_files,
                "failed_files": failed_files,
                "message": f"Course '{session.course_metadata.title}' submitted successfully for review"
            }
            
        except Exception as e:
            logger.error(f"Failed to submit course for review: {e}")
            return {
                "success": False,
                "message": f"Failed to submit course: {str(e)}"
            }
    
    async def resume_upload(self, user_id: int) -> Dict[str, Any]:
        """Resume an interrupted upload session"""
        try:
            session = await self.get_active_session(user_id)
            
            if not session:
                return {
                    "success": False,
                    "message": "No active upload session found to resume"
                }
            
            if session.status == UploadStatus.COMPLETED:
                return {
                    "success": False,
                    "message": "Upload session is already completed"
                }
            
            # Reactivate session
            session.status = UploadStatus.ACTIVE
            session.updated_at = datetime.utcnow()
            await self._save_session(session)
            
            return {
                "success": True,
                "session": session,
                "progress": self._get_progress_info(session),
                "next_step": await self._get_step_instructions(session.current_step),
                "message": f"Resumed upload session at step {session.current_step.value}: {session.current_step.name}"
            }
            
        except Exception as e:
            logger.error(f"Failed to resume upload for user {user_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to resume upload: {str(e)}"
            }
    
    async def cancel_upload(self, user_id: int) -> Dict[str, Any]:
        """Cancel active upload session"""
        try:
            session = await self.get_active_session(user_id)
            
            if not session:
                return {
                    "success": False,
                    "message": "No active upload session found to cancel"
                }
            
            # Mark session as cancelled and clean up
            session.status = UploadStatus.CANCELLED
            await self._save_session(session)
            await self._cleanup_session(session.session_id)
            
            return {
                "success": True,
                "message": "Upload session cancelled successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to cancel upload for user {user_id}: {e}")
            return {
                "success": False,
                "message": f"Failed to cancel upload: {str(e)}"
            }
    
    async def _cleanup_session(self, session_id: str):
        """Clean up completed or cancelled session"""
        try:
            # Remove from Redis - we can't easily get user_id from session_id, 
            # so we'll let it expire naturally
            pass
        except Exception as e:
            logger.error(f"Failed to cleanup session {session_id}: {e}")
    
    async def get_session_summary(self, session: UploadSession) -> str:
        """Generate a formatted summary of the upload session"""
        if not session.course_metadata:
            return "Course information not yet provided"
        
        summary = f"**📚 Course Summary**\n\n"
        summary += f"**Title:** {session.course_metadata.title}\n"
        summary += f"**Description:** {session.course_metadata.description}\n"
        
        if session.course_metadata.category:
            summary += f"**Category:** {session.course_metadata.category}\n"
        
        if session.course_metadata.tags:
            summary += f"**Tags:** {', '.join(session.course_metadata.tags)}\n"
        
        summary += f"**Difficulty:** {session.course_metadata.difficulty_level}/5\n"
        
        if session.course_metadata.estimated_duration:
            summary += f"**Duration:** {session.course_metadata.estimated_duration} minutes\n"
        
        summary += f"**Files:** {len(session.files)} file(s)\n"
        
        if session.files:
            total_size = sum(f.file_size for f in session.files)
            summary += f"**Total Size:** {get_size(total_size)}\n"
        
        summary += f"**Banner:** {'✅ Added' if session.banner_file_id else '❌ Not added'}\n"
        
        return summary