"""
Enhanced Course Manager Plugin with Story 1.4 Features

This plugin integrates:
- Enhanced course upload workflow with progress tracking
- Session management and resumption capability
- Integration with review queue system
- Status tracking and notifications
- Improved user experience with step-by-step guidance
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from pyrogram import Client, filters
    from pyrogram.types import (
        InlineKeyboardButton, InlineKeyboardMarkup, 
        ForceReply, CallbackQuery, Message
    )
    from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified
except ImportError:
    # Mock pyrogram for testing
    Client = None
    filters = None
    InlineKeyboardButton = None
    InlineKeyboardMarkup = None
    ForceReply = None
    CallbackQuery = None
    Message = None
    FloodWait = Exception
    UserIsBlocked = Exception
    MessageNotModified = Exception

from info import ADMINS, CUSTOM_FILE_CAPTION, PUBLIC_CHANNEL
from utils import temp, get_size, get_file_id, clean_text
from Script import script

# Import new enhanced components
from core.enhanced_course_uploader import EnhancedCourseUploader, UploadStep, UploadStatus
from core.review_queue_manager import ReviewQueueManager, ReviewStatus
from core.course_metadata_manager import CourseMetadataManager, DifficultyLevel, CourseType
from core.supabase_client import supabase_client
from core.redis_state import redis_state
from core.multi_channel_manager import MultiChannelManager
from core.volunteer_system import volunteer_manager

logger = logging.getLogger(__name__)

# Initialize enhanced components
enhanced_uploader = None
review_manager = None
metadata_manager = None
multi_channel_manager = None

def initialize_enhanced_components(bot_client):
    """Initialize enhanced course management components"""
    global enhanced_uploader, review_manager, metadata_manager, multi_channel_manager
    
    try:
        enhanced_uploader = EnhancedCourseUploader(supabase_client, redis_state, None)
        review_manager = ReviewQueueManager(supabase_client, redis_state)
        metadata_manager = CourseMetadataManager(supabase_client, redis_state)
        multi_channel_manager = MultiChannelManager(bot_client)
        
        logger.info("Enhanced course management components initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize enhanced components: {e}")

# Enhanced Course Upload Commands

@Client.on_message(filters.command(["bulkupload", "bulk_upload"]) & filters.private & filters.user(ADMINS))
async def start_bulk_course_upload(client, message):
    """Start bulk course upload workflow"""
    try:
        user_id = message.from_user.id
        
        # Initialize bulk upload session
        session_data = {
            'status': 'selecting_method',
            'courses': [],
            'method': None,
            'started_at': datetime.utcnow().isoformat(),
            'user_id': user_id
        }
        
        await redis_state.set(f"bulk_upload_session:{user_id}", json.dumps(session_data), ex=3600)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Upload Files", callback_data="bulk_method_files")],
            [InlineKeyboardButton("🔗 Message Links", callback_data="bulk_method_links")],
            [InlineKeyboardButton("📋 JSON Format", callback_data="bulk_method_json")],
            [InlineKeyboardButton("❌ Cancel", callback_data="bulk_cancel")]
        ])
        
        await message.reply_text(
            "🚀 **Chess Course Bulk Upload**\n\n"
            "📋 Upload 2-100 courses at once\n"
            "📁 Each course supports multiple files (PDFs, PGN, videos)\n"
            "⏱️ Processing time: ~2-5 seconds per course\n"
            "🎯 All courses enter review queue automatically\n\n"
            "**Choose your upload method:**",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Failed to start bulk upload: {e}")
        await message.reply_text("❌ Failed to start bulk upload. Please try again.")

@Client.on_message(filters.command(["bulk_help", "bulkhelp"]) & filters.private)
async def show_bulk_help(client, message):
    """Show bulk upload help and available commands"""
    try:
        help_text = (
            "🚀 **Bulk Upload System Help**\n\n"
            "**Available Commands:**\n"
            "• `/bulkupload` - Start bulk course upload\n"
            "• `/batch_status <id>` - Check batch upload status\n"
            "• `/bulk_help` - Show this help message\n\n"
            "**Upload Methods:**\n"
            "📤 **File Upload** - Send files directly to bot\n"
            "🔗 **Message Links** - Provide Telegram message links\n"
            "📋 **JSON Format** - Send structured JSON data\n\n"
            "**Limits:**\n"
            "• 2-100 courses per batch\n"
            "• Up to 50 files per course\n"
            "• Max 2GB per file\n"
            "• Session expires in 1 hour\n\n"
            "**Support:**\n"
            "• All uploaded courses enter review queue\n"
            "• Get notifications on approval/rejection\n"
            "• Track progress with batch ID\n"
            "• Resume interrupted uploads\n\n"
            "💡 **Tip:** Start with `/bulkupload` and follow the guided process!"
        )
        
        await message.reply_text(help_text)
        
    except Exception as e:
        logger.error(f"Failed to show bulk help: {e}")
        await message.reply_text("❌ Error showing help. Please try again.")

@Client.on_message(filters.command(["batch_status", "bulkstatus"]) & filters.private)
async def check_batch_status(client, message):
    """Check status of a bulk upload batch"""
    try:
        # Extract batch ID from command
        command_parts = message.text.split()
        if len(command_parts) < 2:
            return await message.reply_text(
                "📊 **Batch Status Check**\n\n"
                "Usage: `/batch_status <batch_id>`\n\n"
                "Example: `/batch_status 3828826e-b841-46f9`\n\n"
                "💡 Get your batch ID from the bulk upload completion message."
            )
        
        batch_id = command_parts[1]
        
        # Import bulk operations
        from core.bulk_operations import bulk_operations_manager
        
        # Get batch status
        status = await bulk_operations_manager.get_bulk_operation_status(batch_id)
        
        if not status['success']:
            return await message.reply_text(
                f"❌ **Batch Not Found**\n\n"
                f"Batch ID: `{batch_id}`\n\n"
                f"This batch doesn't exist or has expired.\n"
                f"Batch data is kept for 30 days."
            )
        
        # Format status message
        status_msg = (
            f"📊 **Batch Status Report**\n\n"
            f"🆔 **Batch ID:** `{batch_id}`\n"
            f"📅 **Created:** {status['created_at']}\n"
            f"🎯 **Operation:** {status['operation_type']}\n\n"
            f"📈 **Results:**\n"
            f"✅ Successful: {status['successful_items']}\n"
            f"❌ Failed: {status['failed_items']}\n"
            f"📚 Total: {status['total_items']}\n"
            f"⏱️ Processing time: {status['processing_time']:.2f}s\n\n"
        )
        
        # Add course status breakdown
        if status.get('courses_by_status'):
            status_msg += "📋 **Course Status:**\n"
            for course_status, courses in status['courses_by_status'].items():
                status_msg += f"🔸 {course_status.upper()}: {len(courses)} courses\n"
        
        await message.reply_text(status_msg)
        
    except Exception as e:
        logger.error(f"Failed to check batch status: {e}")
        await message.reply_text("❌ Failed to check batch status. Please try again.")

@Client.on_message(filters.command(["addcourse", "newcourse"]) & filters.private & filters.user(ADMINS))
async def start_enhanced_course_upload(client, message):
    """Start the enhanced course upload workflow with progress tracking"""
    try:
        if not enhanced_uploader:
            return await message.reply_text("⚠️ Enhanced upload system not initialized. Please contact support.")
        
        user_id = message.from_user.id
        
        # Check for existing active session
        existing_session = await enhanced_uploader.get_active_session(user_id)
        if existing_session:
            return await handle_existing_session(message, existing_session)
        
        # Start new enhanced upload session
        result = await enhanced_uploader.start_enhanced_upload(user_id)
        
        if not result["success"]:
            return await message.reply_text(f"❌ Failed to start upload: {result['message']}")
        
        # Show welcome message and first step
        session = result["session"]
        progress = result["progress"]
        next_step = result["next_step"]
        
        welcome_text = (
            "🚀 **Enhanced Course Upload System**\n\n"
            "Welcome to the new streamlined course upload process! "
            "This system will guide you through each step with progress tracking "
            "and validation to ensure your course meets quality standards.\n\n"
            f"**Progress:** {progress['progress_percentage']}% complete\n"
            f"**Step {progress['current_step']}/{progress['total_steps']}:** {next_step['title']}\n\n"
            f"{next_step['description']}\n\n"
            "Let's start by providing your course information:"
        )
        
        buttons = [
            [InlineKeyboardButton("📝 Start Course Upload", callback_data=f"enhanced_upload_step_{session.session_id}")]
        ]
        
        await message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        logger.error(f"Enhanced upload start error: {e}")
        await message.reply_text(f"❌ Error starting upload: {str(e)}")

@Client.on_message(filters.command(["resume", "resume_upload"]) & filters.private & filters.user(ADMINS))
async def resume_course_upload(client, message):
    """Resume an interrupted course upload session"""
    try:
        if not enhanced_uploader:
            return await message.reply_text("⚠️ Enhanced upload system not initialized.")
        
        user_id = message.from_user.id
        
        # Try to resume session
        result = await enhanced_uploader.resume_upload(user_id)
        
        if not result["success"]:
            return await message.reply_text(f"❌ {result['message']}")
        
        session = result["session"]
        progress = result["progress"]
        next_step = result["next_step"]
        
        resume_text = (
            f"🔄 **Upload Session Resumed**\n\n"
            f"Welcome back! Your upload session has been restored.\n\n"
            f"**Progress:** {progress['progress_percentage']}% complete\n"
            f"**Current Step:** {progress['current_step']}/{progress['total_steps']} - {next_step['title']}\n\n"
            f"{next_step['description']}\n\n"
            f"**Session Info:**\n"
            f"• Files added: {progress['files_added']}\n"
            f"• Banner: {'✅' if progress['has_banner'] else '❌'}\n"
        )
        
        buttons = [
            [InlineKeyboardButton("▶️ Continue Upload", callback_data=f"enhanced_upload_step_{session.session_id}")],
            [InlineKeyboardButton("❌ Cancel Upload", callback_data=f"enhanced_upload_cancel_{session.session_id}")]
        ]
        
        await message.reply_text(resume_text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        logger.error(f"Resume upload error: {e}")
        await message.reply_text(f"❌ Error resuming upload: {str(e)}")

@Client.on_message(filters.command(["cancel_upload", "abort"]) & filters.private & filters.user(ADMINS))
async def cancel_course_upload(client, message):
    """Cancel active course upload session"""
    try:
        if not enhanced_uploader:
            return await message.reply_text("⚠️ Enhanced upload system not initialized.")
        
        user_id = message.from_user.id
        
        # Cancel session
        result = await enhanced_uploader.cancel_upload(user_id)
        
        if result["success"]:
            await message.reply_text("✅ Upload session cancelled successfully.")
        else:
            await message.reply_text(f"❌ {result['message']}")
        
    except Exception as e:
        logger.error(f"Cancel upload error: {e}")
        await message.reply_text(f"❌ Error cancelling upload: {str(e)}")

# Enhanced Session Handling

async def handle_existing_session(message: Message, session):
    """Handle user with existing upload session"""
    try:
        progress = enhanced_uploader._get_progress_info(session)
        next_step = await enhanced_uploader._get_step_instructions(session.current_step)
        
        status_text = (
            f"📋 **Active Upload Session Found**\n\n"
            f"You have an active course upload in progress:\n\n"
            f"**Progress:** {progress['progress_percentage']}% complete\n"
            f"**Current Step:** {progress['current_step']}/{progress['total_steps']} - {next_step['title']}\n"
            f"**Status:** {session.status.value.title()}\n\n"
            "What would you like to do?"
        )
        
        buttons = [
            [InlineKeyboardButton("▶️ Continue Upload", callback_data=f"enhanced_upload_step_{session.session_id}")],
            [InlineKeyboardButton("🔄 Start Over", callback_data=f"enhanced_upload_restart_{session.session_id}")],
            [InlineKeyboardButton("❌ Cancel Session", callback_data=f"enhanced_upload_cancel_{session.session_id}")]
        ]
        
        await message.reply_text(status_text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        logger.error(f"Handle existing session error: {e}")
        await message.reply_text("❌ Error handling existing session.")

# Enhanced Callback Handlers

@Client.on_callback_query(filters.regex(r"^enhanced_upload_step_"))
async def handle_upload_step(client, callback_query):
    """Handle enhanced upload step progression"""
    try:
        session_id = callback_query.data.split("_")[-1]
        user_id = callback_query.from_user.id
        
        # Get active session
        session = await enhanced_uploader.get_active_session(user_id)
        if not session or session.session_id != session_id:
            return await callback_query.answer("❌ Session not found or expired.", show_alert=True)
        
        # Get current step instructions
        step_instructions = await enhanced_uploader._get_step_instructions(session.current_step)
        progress = enhanced_uploader._get_progress_info(session)
        
        # Generate step interface
        step_text = await generate_step_interface(session, step_instructions, progress)
        
        # Create appropriate buttons for the step
        buttons = await create_step_buttons(session, step_instructions)
        
        try:
            await callback_query.message.edit_text(step_text, reply_markup=InlineKeyboardMarkup(buttons))
        except MessageNotModified:
            pass
        
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Upload step handler error: {e}")
        await callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)

@Client.on_callback_query(filters.regex(r"^enhanced_upload_cancel_"))
async def handle_upload_cancel(client, callback_query):
    """Handle upload session cancellation"""
    try:
        session_id = callback_query.data.split("_")[-1]
        user_id = callback_query.from_user.id
        
        # Cancel session
        result = await enhanced_uploader.cancel_upload(user_id)
        
        if result["success"]:
            await callback_query.message.edit_text("✅ Upload session cancelled successfully.")
        else:
            await callback_query.message.edit_text(f"❌ {result['message']}")
        
        await callback_query.answer("Session cancelled", show_alert=False)
        
    except Exception as e:
        logger.error(f"Upload cancel handler error: {e}")
        await callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)

@Client.on_callback_query(filters.regex(r"^enhanced_upload_restart_"))
async def handle_upload_restart(client, callback_query):
    """Handle upload session restart"""
    try:
        user_id = callback_query.from_user.id
        
        # Cancel existing session
        await enhanced_uploader.cancel_upload(user_id)
        
        # Start new session
        result = await enhanced_uploader.start_enhanced_upload(user_id)
        
        if result["success"]:
            session = result["session"]
            next_step = result["next_step"]
            progress = result["progress"]
            
            restart_text = (
                f"🚀 **New Upload Session Started**\n\n"
                f"Previous session cancelled. Starting fresh!\n\n"
                f"**Step 1/{progress['total_steps']}:** {next_step['title']}\n\n"
                f"{next_step['description']}"
            )
            
            buttons = [
                [InlineKeyboardButton("📝 Start Upload", callback_data=f"enhanced_upload_step_{session.session_id}")]
            ]
            
            await callback_query.message.edit_text(restart_text, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await callback_query.message.edit_text(f"❌ Failed to start new session: {result['message']}")
        
        await callback_query.answer("New session started", show_alert=False)
        
    except Exception as e:
        logger.error(f"Upload restart handler error: {e}")
        await callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)

# Step Interface Generation

async def generate_step_interface(session, step_instructions: Dict, progress: Dict) -> str:
    """Generate interface text for current upload step"""
    try:
        step_text = (
            f"🎯 **{step_instructions.get('title', 'Upload Step')}**\n\n"
            f"**Progress:** {progress['progress_percentage']}% "
            f"({'●' * (progress['progress_percentage'] // 20)}{'○' * (5 - progress['progress_percentage'] // 20)})\n"
            f"**Step {progress['current_step']}/{progress['total_steps']}**\n\n"
        )
        
        step_text += f"{step_instructions.get('description', 'Please follow the instructions.')}\n\n"
        
        # Add step-specific information
        if session.current_step == UploadStep.COLLECTING_METADATA:
            step_text += "**Required Information:**\n"
            step_text += "• Course Title (5-200 characters)\n"
            step_text += "• Course Description (20-2000 characters)\n\n"
            step_text += "Please provide your course title and description using the form below."
            
        elif session.current_step == UploadStep.COLLECTING_CATEGORY_TAGS:
            step_text += "**Category Options:**\n"
            categories = enhanced_uploader.valid_categories
            for i, category in enumerate(categories[:5], 1):
                step_text += f"{i}. {category}\n"
            if len(categories) > 5:
                step_text += f"... and {len(categories) - 5} more\n"
            step_text += "\n**Tags:** Add relevant keywords to help users find your course.\n"
            
        elif session.current_step == UploadStep.COLLECTING_FILES:
            step_text += "**File Upload Options:**\n"
            step_text += "• Upload files directly\n"
            step_text += "• Provide Telegram message links\n"
            step_text += "• Batch file upload\n\n"
            step_text += f"**Current Files:** {progress.get('files_added', 0)}\n"
            step_text += f"**Maximum:** {enhanced_uploader.max_files_per_course} files per course\n"
            
        elif session.current_step == UploadStep.REVIEW_CONFIRMATION:
            # Show course summary
            if session.course_metadata:
                step_text += "**Course Summary:**\n"
                step_text += await enhanced_uploader.get_session_summary(session)
                step_text += "\n\n**Ready to submit for review?**"
            
        elif session.current_step == UploadStep.FINAL_SUBMISSION:
            step_text += "🚀 **Submitting your course for review...**\n\n"
            step_text += "Your course is being processed and will be assigned to a volunteer reviewer."
        
        # Add validation errors if any
        if hasattr(session, 'validation_errors') and session.validation_errors:
            step_text += "\n\n⚠️ **Please fix these issues:**\n"
            for error in session.validation_errors:
                step_text += f"• {error}\n"
        
        return step_text
        
    except Exception as e:
        logger.error(f"Step interface generation error: {e}")
        return "❌ Error generating step interface."

async def create_step_buttons(session, step_instructions: Dict) -> List[List[InlineKeyboardButton]]:
    """Create appropriate buttons for current upload step"""
    buttons = []
    
    try:
        if session.current_step == UploadStep.COLLECTING_METADATA:
            buttons = [
                [InlineKeyboardButton("📝 Enter Course Info", callback_data=f"enhanced_form_metadata_{session.session_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"enhanced_upload_cancel_{session.session_id}")]
            ]
            
        elif session.current_step == UploadStep.COLLECTING_CATEGORY_TAGS:
            buttons = [
                [InlineKeyboardButton("🏷️ Select Category", callback_data=f"enhanced_form_category_{session.session_id}")],
                [InlineKeyboardButton("🏷️ Add Tags", callback_data=f"enhanced_form_tags_{session.session_id}")],
                [InlineKeyboardButton("⏭️ Skip Tags", callback_data=f"enhanced_skip_tags_{session.session_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"enhanced_upload_cancel_{session.session_id}")]
            ]
            
        elif session.current_step == UploadStep.COLLECTING_FILES:
            buttons = [
                [InlineKeyboardButton("📁 Upload Files", callback_data=f"enhanced_form_files_{session.session_id}")],
                [InlineKeyboardButton("🔗 Message Links", callback_data=f"enhanced_form_links_{session.session_id}")],
                [InlineKeyboardButton("📋 View Files", callback_data=f"enhanced_view_files_{session.session_id}")],
                [InlineKeyboardButton("⏭️ Continue", callback_data=f"enhanced_next_step_{session.session_id}") if session.files else None],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"enhanced_upload_cancel_{session.session_id}")]
            ]
            buttons = [row for row in buttons if all(row)]  # Remove None buttons
            
        elif session.current_step == UploadStep.REVIEW_CONFIRMATION:
            buttons = [
                [InlineKeyboardButton("✅ Submit for Review", callback_data=f"enhanced_submit_{session.session_id}")],
                [InlineKeyboardButton("✏️ Edit Metadata", callback_data=f"enhanced_edit_metadata_{session.session_id}")],
                [InlineKeyboardButton("🏷️ Edit Categories", callback_data=f"enhanced_edit_category_{session.session_id}")],
                [InlineKeyboardButton("📁 Edit Files", callback_data=f"enhanced_edit_files_{session.session_id}")],
                [InlineKeyboardButton("🖼️ Add Banner", callback_data=f"enhanced_add_banner_{session.session_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"enhanced_upload_cancel_{session.session_id}")]
            ]
            
        elif session.current_step == UploadStep.FINAL_SUBMISSION:
            buttons = [
                [InlineKeyboardButton("📊 View Status", callback_data=f"enhanced_view_status_{session.session_id}")]
            ]
        
        # Add navigation buttons
        if session.current_step.value > 1 and session.current_step != UploadStep.FINAL_SUBMISSION:
            buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=f"enhanced_prev_step_{session.session_id}")])
        
        return buttons
        
    except Exception as e:
        logger.error(f"Button creation error: {e}")
        return [[InlineKeyboardButton("❌ Error", callback_data="error")]]

# Course Status and Dashboard Commands

@Client.on_message(filters.command(["mystatus", "course_status"]) & filters.private & filters.user(ADMINS))
async def show_course_status_dashboard(client, message):
    """Show contributor's course status dashboard"""
    try:
        if not review_manager:
            return await message.reply_text("⚠️ Review system not initialized.")
        
        user_id = message.from_user.id
        
        # Get user's anonymous ID
        user_result = await supabase_client.execute_query(
            "SELECT id FROM users WHERE telegram_id = $1", user_id
        )
        
        if not user_result:
            return await message.reply_text("❌ User not found in system.")
        
        contributor_id = user_result[0]["id"]
        
        # Get dashboard data
        dashboard = await review_manager.get_contributor_dashboard(contributor_id)
        
        if not dashboard["success"]:
            return await message.reply_text(f"❌ Failed to get dashboard: {dashboard['message']}")
        
        # Generate dashboard text
        dashboard_text = generate_dashboard_text(dashboard)
        
        # Create action buttons
        buttons = [
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"dashboard_refresh_{contributor_id}")],
            [InlineKeyboardButton("📈 Statistics", callback_data=f"dashboard_stats_{contributor_id}")],
            [InlineKeyboardButton("🆕 New Course", callback_data="start_new_course")]
        ]
        
        await message.reply_text(dashboard_text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        await message.reply_text(f"❌ Error loading dashboard: {str(e)}")

def generate_dashboard_text(dashboard: Dict) -> str:
    """Generate formatted dashboard text"""
    try:
        stats = dashboard["statistics"]
        courses = dashboard["courses"]
        
        dashboard_text = (
            "📊 **Your Course Dashboard**\n\n"
            f"**📈 Statistics:**\n"
            f"• Total Courses: {stats['total_courses']}\n"
            f"• Pending Reviews: {stats['pending_reviews']}\n"
            f"• Under Review: {stats['under_review']}\n"
            f"• Approved: {stats['approved']}\n"
            f"• Need Revision: {stats['needs_revision']}\n\n"
        )
        
        if courses:
            dashboard_text += "**📚 Recent Courses:**\n"
            for course in courses[:5]:  # Show latest 5 courses
                status_emoji = {
                    "pending_review": "⏳",
                    "under_review": "👀",
                    "approved": "✅",
                    "rejected": "❌",
                    "needs_revision": "✏️"
                }.get(course.get("review_status", "unknown"), "❓")
                
                dashboard_text += f"{status_emoji} **{course['title'][:30]}{'...' if len(course['title']) > 30 else ''}**\n"
                dashboard_text += f"   Status: {course.get('review_status', 'unknown').replace('_', ' ').title()}\n"
                
                if course.get('queue_position'):
                    dashboard_text += f"   Queue Position: #{course['queue_position']}\n"
                
                dashboard_text += "\n"
        else:
            dashboard_text += "**📚 No courses found.**\n\nUse /addcourse to create your first course!\n"
        
        return dashboard_text
        
    except Exception as e:
        logger.error(f"Dashboard text generation error: {e}")
        return "❌ Error generating dashboard."

# Enhanced Search with Metadata

@Client.on_message(filters.command(["search", "find"]) & filters.text & filters.incoming)
async def enhanced_course_search(client, message):
    """Enhanced course search with metadata filtering"""
    try:
        if not metadata_manager:
            # Fallback to basic search
            return await basic_course_search(client, message)
        
        if len(message.command) < 2:
            return await message.reply_text(
                "🔍 **Enhanced Course Search**\n\n"
                "**Usage:** `/search <query>`\n\n"
                "**Examples:**\n"
                "• `/search chess openings`\n"
                "• `/search beginner tactics`\n"
                "• `/search sicilian defense`\n\n"
                "**Filters available:**\n"
                "• Category, difficulty, tags, duration"
            )
        
        query = " ".join(message.command[1:])
        
        # Perform enhanced search
        search_result = await metadata_manager.search_courses_advanced(query, limit=10)
        
        if not search_result["success"]:
            return await message.reply_text(f"❌ Search failed: {search_result['message']}")
        
        results = search_result["results"]
        
        if not results:
            return await message.reply_text(f"🔍 No courses found for '{query}'")
        
        # Generate search results text
        search_text = f"🔍 **Search Results for '{query}'**\n\n"
        search_text += f"Found {search_result['total_results']} course(s):\n\n"
        
        buttons = []
        
        for i, course in enumerate(results[:5], 1):
            # Course info
            title = course.get('title', 'Unknown')
            category = course.get('category', 'Uncategorized')
            difficulty = course.get('difficulty_level', 1)
            tags = course.get('tags', [])
            
            search_text += f"**{i}. {title}**\n"
            search_text += f"   📂 {category} • ⭐ Level {difficulty}\n"
            
            if tags:
                search_text += f"   🏷️ {', '.join(tags[:3])}{'...' if len(tags) > 3 else ''}\n"
            
            search_text += "\n"
            
            # Add course button
            buttons.append([
                InlineKeyboardButton(
                    text=f"📚 {title[:25]}{'...' if len(title) > 25 else ''}",
                    callback_data=f"enhanced_course_{course['course_id']}"
                )
            ])
        
        # Add more results button if available
        if search_result['total_results'] > 5:
            buttons.append([
                InlineKeyboardButton(
                    text=f"📄 Show More ({search_result['total_results'] - 5} remaining)",
                    callback_data=f"enhanced_search_more_{query}"
                )
            ])
        
        await message.reply_text(search_text, reply_markup=InlineKeyboardMarkup(buttons))
        
    except Exception as e:
        logger.error(f"Enhanced search error: {e}")
        await message.reply_text(f"❌ Search error: {str(e)}")

# Fallback to basic search if enhanced search is not available
async def basic_course_search(client, message):
    """Fallback to basic course search functionality"""
    # This would be the existing search functionality
    # Implementation kept from the original course_manager.py
    pass

# Review Status Tracking

@Client.on_callback_query(filters.regex(r"^enhanced_course_"))
async def show_enhanced_course_info(client, callback_query):
    """Show detailed course information with status tracking"""
    try:
        course_id = callback_query.data.split("_")[2]
        
        # Get course metadata
        if metadata_manager:
            metadata_result = await metadata_manager.get_course_metadata(course_id)
            if metadata_result["success"]:
                metadata = metadata_result["metadata"]
                
                # Get review status
                review_status = await review_manager.get_review_status(course_id)
                
                # Generate course info text
                course_text = generate_enhanced_course_info(metadata, review_status)
                
                # Create action buttons
                buttons = await create_course_action_buttons(course_id, metadata, review_status)
                
                try:
                    await callback_query.message.edit_text(course_text, reply_markup=InlineKeyboardMarkup(buttons))
                except MessageNotModified:
                    pass
                
                await callback_query.answer()
                return
        
        # Fallback to basic course info
        await callback_query.answer("Course info not available", show_alert=True)
        
    except Exception as e:
        logger.error(f"Enhanced course info error: {e}")
        await callback_query.answer(f"Error: {str(e)}", show_alert=True)

def generate_enhanced_course_info(metadata: Dict, review_status: Dict) -> str:
    """Generate detailed course information text"""
    try:
        course_text = f"📚 **{metadata['title']}**\n\n"
        course_text += f"**Description:**\n{metadata['description'][:200]}{'...' if len(metadata['description']) > 200 else ''}\n\n"
        
        # Metadata information
        if metadata.get('category'):
            course_text += f"📂 **Category:** {metadata['category']}\n"
        
        course_text += f"⭐ **Difficulty:** Level {metadata.get('difficulty_level', 1)}/5\n"
        
        if metadata.get('estimated_duration'):
            hours = metadata['estimated_duration'] // 60
            minutes = metadata['estimated_duration'] % 60
            duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            course_text += f"⏱️ **Duration:** ~{duration_str}\n"
        
        if metadata.get('tags'):
            course_text += f"🏷️ **Tags:** {', '.join(metadata['tags'][:5])}\n"
        
        # Review status information
        if review_status and review_status["success"]:
            course_text += f"\n**📋 Review Status:**\n"
            status = review_status['status'].replace('_', ' ').title()
            course_text += f"Status: {status}\n"
            
            if review_status.get('queue_position'):
                course_text += f"Queue Position: #{review_status['queue_position']}\n"
            
            if review_status.get('estimated_completion'):
                completion_date = review_status['estimated_completion']
                course_text += f"Expected Approval: {completion_date.strftime('%Y-%m-%d')}\n"
        
        course_text += f"\n**📅 Created:** {metadata.get('created_at', '').split('T')[0] if metadata.get('created_at') else 'Unknown'}\n"
        
        return course_text
        
    except Exception as e:
        logger.error(f"Course info generation error: {e}")
        return "❌ Error generating course information."

async def create_course_action_buttons(course_id: str, metadata: Dict, review_status: Dict) -> List[List[InlineKeyboardButton]]:
    """Create action buttons for course based on status"""
    buttons = []
    
    try:
        # Basic action buttons
        buttons.append([
            InlineKeyboardButton("📁 View Files", callback_data=f"course_files_{course_id}"),
            InlineKeyboardButton("📊 Statistics", callback_data=f"course_stats_{course_id}")
        ])
        
        # Status-specific buttons
        if review_status and review_status["success"]:
            status = review_status["status"]
            
            if status == "approved":
                buttons.append([
                    InlineKeyboardButton("⬇️ Download", callback_data=f"sendall_{course_id}"),
                    InlineKeyboardButton("🔗 Share", callback_data=f"share_course_{course_id}")
                ])
            elif status == "needs_revision":
                buttons.append([
                    InlineKeyboardButton("✏️ Revise Course", callback_data=f"revise_course_{course_id}"),
                    InlineKeyboardButton("💬 View Feedback", callback_data=f"course_feedback_{course_id}")
                ])
        
        # Recommendations
        buttons.append([
            InlineKeyboardButton("🎯 Similar Courses", callback_data=f"recommendations_{course_id}")
        ])
        
        # Back button
        buttons.append([
            InlineKeyboardButton("🔙 Back to Search", callback_data="back_to_search")
        ])
        
        return buttons
        
    except Exception as e:
        logger.error(f"Button creation error: {e}")
        return [[InlineKeyboardButton("❌ Error", callback_data="error")]]

# Bulk Upload Callback Handlers

@Client.on_callback_query(filters.regex(r"^bulk_method_"))
async def handle_bulk_method_selection(client, callback_query):
    """Handle bulk upload method selection"""
    try:
        user_id = callback_query.from_user.id
        method = callback_query.data.split("_")[-1]  # files, links, or json
        
        # Get session data
        session_data = await redis_state.get(f"bulk_upload_session:{user_id}")
        if not session_data:
            return await callback_query.answer("❌ Session expired. Please start again with /bulkupload", show_alert=True)
        
        session = json.loads(session_data)
        session['method'] = method
        session['status'] = 'collecting_input'
        
        # Save updated session
        await redis_state.set(f"bulk_upload_session:{user_id}", json.dumps(session), ex=3600)
        
        # Show instructions based on method
        if method == "files":
            instructions = (
                "📤 **File Upload Method**\n\n"
                "Send your course files in this format:\n\n"
                "**For each course, send:**\n"
                "1. Course title (as text message)\n"
                "2. Course description (as text message)\n"
                "3. Category (e.g., 'Openings', 'Endgame', 'Tactics')\n"
                "4. Files (PDFs, PGN, videos)\n"
                "5. Type `---` to separate courses\n\n"
                "**When finished, type:** `PROCESS`\n"
                "**To cancel, type:** `CANCEL`"
            )
        elif method == "links":
            instructions = (
                "🔗 **Message Links Method**\n\n"
                "Send course data in this format:\n\n"
                "```\n"
                "Title: Chess Openings Masterclass\n"
                "Description: Complete guide to chess openings\n"
                "Category: Openings\n"
                "Tags: beginner, openings, theory\n"
                "Files: https://t.me/channel/123, https://t.me/channel/124\n"
                "---\n"
                "Title: Endgame Techniques\n"
                "Description: Essential endgame patterns\n"
                "Category: Endgame\n"
                "Tags: intermediate, endgame\n"
                "Files: https://t.me/channel/125\n"
                "```\n\n"
                "**When finished, type:** `PROCESS`\n"
                "**To cancel, type:** `CANCEL`"
            )
        else:  # json
            instructions = (
                "📋 **JSON Format Method**\n\n"
                "Send course data as JSON:\n\n"
                "```json\n"
                "[\n"
                "  {\n"
                "    \"title\": \"Chess Openings Masterclass\",\n"
                "    \"description\": \"Complete guide to chess openings\",\n"
                "    \"category\": \"Openings\",\n"
                "    \"tags\": [\"beginner\", \"openings\"],\n"
                "    \"files\": [\n"
                "      {\"file_name\": \"lesson1.pdf\", \"file_size\": 1024000, \"telegram_file_id\": \"xyz123\"}\n"
                "    ]\n"
                "  }\n"
                "]\n"
                "```\n\n"
                "**To cancel, type:** `CANCEL`"
            )
        
        await callback_query.edit_message_text(instructions)
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Failed to handle method selection: {e}")
        await callback_query.answer("❌ Error processing selection", show_alert=True)

@Client.on_callback_query(filters.regex(r"^bulk_cancel$"))
async def handle_bulk_cancel(client, callback_query):
    """Handle bulk upload cancellation"""
    try:
        user_id = callback_query.from_user.id
        
        # Clear session
        await redis_state.delete(f"bulk_upload_session:{user_id}")
        
        await callback_query.edit_message_text(
            "❌ **Bulk Upload Cancelled**\n\n"
            "You can start again anytime with `/bulkupload`"
        )
        await callback_query.answer()
        
    except Exception as e:
        logger.error(f"Failed to cancel bulk upload: {e}")
        await callback_query.answer("❌ Error cancelling upload", show_alert=True)

# Bulk Upload Input Handler
@Client.on_message(filters.text & filters.private & ~filters.command([]))
async def handle_bulk_upload_input(client, message):
    """Handle bulk upload input from users"""
    try:
        user_id = message.from_user.id
        
        # Check if user has active bulk upload session
        session_data = await redis_state.get(f"bulk_upload_session:{user_id}")
        if not session_data:
            return  # Not in bulk upload mode
        
        session = json.loads(session_data)
        if session['status'] != 'collecting_input':
            return  # Not collecting input
        
        text = message.text.strip()
        
        # Handle control commands
        if text.upper() == "CANCEL":
            await redis_state.delete(f"bulk_upload_session:{user_id}")
            return await message.reply_text("❌ Bulk upload cancelled.")
        
        if text.upper() == "PROCESS":
            return await process_bulk_upload(client, message, session)
        
        # Add input to session
        if 'input_buffer' not in session:
            session['input_buffer'] = []
        
        session['input_buffer'].append({
            'text': text,
            'timestamp': datetime.utcnow().isoformat(),
            'message_id': message.id
        })
        
        # Save updated session
        await redis_state.set(f"bulk_upload_session:{user_id}", json.dumps(session), ex=3600)
        
        # Acknowledge receipt
        await message.reply_text(f"✅ Input received ({len(session['input_buffer'])} items). Type `PROCESS` when ready or `CANCEL` to abort.")
        
    except Exception as e:
        logger.error(f"Failed to handle bulk input: {e}")
        await message.reply_text("❌ Error processing input. Please try again.")

async def process_bulk_upload(client, message, session):
    """Process the collected bulk upload input"""
    try:
        user_id = message.from_user.id
        
        # Import bulk operations and anonymous manager
        from core.bulk_operations import bulk_operations_manager, BulkCourseData
        from core.anonymity import anonymous_manager
        
        # Get user's anonymous ID
        user = await anonymous_manager.get_user_by_telegram_id(user_id)
        if not user:
            user = await anonymous_manager.create_user(user_id)
        contributor_id = user['id']
        
        # Parse input based on method
        input_buffer = session.get('input_buffer', [])
        if not input_buffer:
            return await message.reply_text("❌ No course data provided.")
        
        courses = await parse_bulk_input(session['method'], input_buffer)
        if not courses:
            return await message.reply_text("❌ Failed to parse course data. Please check the format.")
        
        # Show processing message
        progress_msg = await message.reply_text(
            f"⚙️ **Processing Bulk Upload**\n\n"
            f"📚 Courses to process: {len(courses)}\n"
            f"🔄 Status: Starting...\n\n"
            f"Please wait..."
        )
        
        # Execute bulk upload
        result = await bulk_operations_manager.bulk_upload_courses(
            courses=courses,
            contributor_anonymous_id=contributor_id,
            batch_metadata={
                'source': 'telegram_bulk',
                'method': session['method'],
                'user_id': user_id
            }
        )
        
        # Clear session
        await redis_state.delete(f"bulk_upload_session:{user_id}")
        
        # Send results
        success_msg = (
            f"🎉 **Bulk Upload Complete!**\n\n"
            f"📊 **Results:**\n"
            f"✅ Successful: {result.successful_uploads}\n"
            f"❌ Failed: {result.failed_uploads}\n"
            f"⏱️ Processing time: {result.processing_time:.2f}s\n"
            f"🆔 Batch ID: `{result.batch_id}`\n\n"
            f"🔍 **Next Steps:**\n"
            f"• Courses are now in review queue\n"
            f"• Check status: `/batch_status {result.batch_id}`\n"
            f"• View your courses: `/my_courses`\n\n"
        )
        
        if result.errors:
            success_msg += f"❌ **Errors ({len(result.errors)}):**\n"
            for error in result.errors[:3]:  # Show first 3 errors
                success_msg += f"• {error.get('course_title', 'Unknown')}: {error['error']}\n"
            if len(result.errors) > 3:
                success_msg += f"• ... and {len(result.errors) - 3} more errors\n"
        
        await progress_msg.edit_text(success_msg)
        
    except Exception as e:
        logger.error(f"Failed to process bulk upload: {e}")
        await message.reply_text(f"❌ Bulk upload failed: {str(e)}")

async def parse_bulk_input(method, input_buffer):
    """Parse bulk input based on the selected method"""
    try:
        courses = []
        
        if method == "links":
            # Parse message link format
            current_course = {}
            for item in input_buffer:
                text = item['text']
                if text == "---":
                    if current_course.get('title'):
                        courses.append(create_course_from_dict(current_course))
                    current_course = {}
                    continue
                
                # Parse field: value format
                if ":" in text:
                    field, value = text.split(":", 1)
                    field = field.strip().lower()
                    value = value.strip()
                    
                    if field == "title":
                        current_course['title'] = value
                    elif field == "description":
                        current_course['description'] = value
                    elif field == "category":
                        current_course['category'] = value
                    elif field == "tags":
                        current_course['tags'] = [tag.strip() for tag in value.split(",")]
                    elif field == "files":
                        # Parse file links
                        file_links = [link.strip() for link in value.split(",")]
                        current_course['files'] = [
                            {"file_name": f"file_{i}", "message_link": link, "file_size": 0}
                            for i, link in enumerate(file_links)
                        ]
            
            # Add last course
            if current_course.get('title'):
                courses.append(create_course_from_dict(current_course))
        
        elif method == "json":
            # Parse JSON format
            try:
                all_text = "\n".join([item['text'] for item in input_buffer])
                course_data = json.loads(all_text)
                for course_dict in course_data:
                    courses.append(create_course_from_dict(course_dict))
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error: {e}")
                return []
        
        return courses
        
    except Exception as e:
        logger.error(f"Failed to parse bulk input: {e}")
        return []

def create_course_from_dict(course_dict):
    """Create BulkCourseData from dictionary"""
    from core.bulk_operations import BulkCourseData
    return BulkCourseData(
        title=course_dict.get('title', 'Untitled Course'),
        description=course_dict.get('description', 'No description provided'),
        category=course_dict.get('category', 'General'),
        tags=course_dict.get('tags', []),
        files=course_dict.get('files', []),
        metadata=course_dict.get('metadata', {})
    )

# Startup initialization
@Client.on_message(filters.command("init_enhanced") & filters.private & filters.user(ADMINS))
async def initialize_enhanced_system(client, message):
    """Initialize enhanced course management system"""
    try:
        initialize_enhanced_components(client)
        
        # Run database migration if needed
        from database.migrations.enhanced_course_workflow_schema import migrate_database
        migration_result = await migrate_database(supabase_client)
        
        if migration_result["success"]:
            await message.reply_text(
                "✅ **Enhanced Course System Initialized**\n\n"
                "**New Features Available:**\n"
                "• Enhanced upload workflow with progress tracking\n"
                "• Session management and resumption\n"
                "• Advanced metadata and search\n"
                "• Review queue and status tracking\n"
                "• Course relationships and recommendations\n\n"
                "Use `/addcourse` to try the new upload system!"
            )
        else:
            await message.reply_text(f"⚠️ System initialized but migration failed: {migration_result['message']}")
        
    except Exception as e:
        logger.error(f"Enhanced system initialization error: {e}")
        await message.reply_text(f"❌ Initialization failed: {str(e)}")

# Export initialization function for bot startup
__all__ = ["initialize_enhanced_components"]