"""
Volunteer Review Panel Plugin
Implements volunteer reviewer interface for course approval workflow
Integrates with AC2: Permission Enforcement System and AC5: Volunteer Assignment Distribution
"""
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from core.roles import rbac_manager
from core.volunteer_system import volunteer_manager
from core.anonymity import anonymous_manager
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("review_panel") & filters.private)
async def volunteer_review_panel(client: Client, message: Message):
    """Main review panel for volunteer reviewers"""
    try:
        telegram_id = message.from_user.id
        
        # Check if user has course review permissions
        if not await rbac_manager.check_permission(telegram_id, 'approve_courses'):
            await message.reply("❌ You don't have permission to access the review panel.")
            return
        
        # Get user info
        user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await message.reply("❌ User not found in system.")
            return
        
        # Get review queue for this volunteer
        review_queue = await volunteer_manager.get_volunteer_queue(user['id'])
        
        # Create panel keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 My Queue", callback_data="review_my_queue"),
                InlineKeyboardButton("📊 My Stats", callback_data="review_my_stats")
            ],
            [
                InlineKeyboardButton("🔄 Refresh Queue", callback_data="review_refresh_queue"),
                InlineKeyboardButton("❓ Review Guide", callback_data="review_guide")
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="close_review_panel")
            ]
        ])
        
        pending_count = len(review_queue)
        
        panel_text = f"""
📝 **Volunteer Review Panel**

👤 **Reviewer:** `{user.get('anonymous_id', 'Unknown')}`
🏷️ **Role:** `{user.get('role', 'Unknown').replace('_', ' ').title()}`

📋 **Current Queue Status:**
⏳ Pending Reviews: `{pending_count}`
🎯 Priority Reviews: `{sum(1 for r in review_queue if r.get('priority_level', 1) > 1)}`

Select an option to manage your review assignments:
        """
        
        await message.reply(
            panel_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Review panel error: {e}")
        await message.reply("❌ Error accessing review panel.")

@Client.on_callback_query(filters.regex(r"^review_my_queue$"))
async def show_review_queue(client: Client, callback_query: CallbackQuery):
    """Display volunteer's current review queue"""
    try:
        telegram_id = callback_query.from_user.id
        
        # Get user and their queue
        user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await callback_query.answer("❌ User not found", show_alert=True)
            return
        
        review_queue = await volunteer_manager.get_volunteer_queue(user['id'])
        
        if not review_queue:
            queue_text = """
📋 **Your Review Queue**

✅ **Queue is empty!** 

No pending reviews at the moment. New courses will be automatically assigned based on workload distribution.

🎯 Check back later or wait for notifications when new courses arrive.
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="review_refresh_queue")],
                [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_review_panel")]
            ])
            
        else:
            queue_text = f"📋 **Your Review Queue ({len(review_queue)} items)**\n\n"
            
            # Show up to 5 items in the queue
            for i, review in enumerate(review_queue[:5]):
                priority_emoji = "🔥" if review.get('priority_level', 1) > 1 else "📝"
                days_waiting = (datetime.now() - review['created_at']).days if review.get('created_at') else 0
                
                queue_text += f"{priority_emoji} **{review.get('title', 'Untitled Course')}**\n"
                queue_text += f"   📁 Files: {review.get('file_count', 0)}\n"
                queue_text += f"   ⏰ Waiting: {days_waiting} days\n"
                queue_text += f"   🆔 Review ID: `{review['review_id']}`\n\n"
            
            if len(review_queue) > 5:
                queue_text += f"... and {len(review_queue) - 5} more items\n\n"
            
            queue_text += "Select a review to start:"
            
            # Create keyboard with review options
            keyboard_buttons = []
            for review in review_queue[:3]:  # Show top 3 as buttons
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        f"📝 Review: {review.get('title', 'Course')[:20]}...", 
                        callback_data=f"start_review_{review['review_id']}"
                    )
                ])
            
            keyboard_buttons.extend([
                [InlineKeyboardButton("🔄 Refresh Queue", callback_data="review_refresh_queue")],
                [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_review_panel")]
            ])
            
            keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        await callback_query.edit_message_text(
            queue_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Show queue error: {e}")
        await callback_query.answer("❌ Error loading queue", show_alert=True)

@Client.on_callback_query(filters.regex(r"^start_review_(.+)$"))
async def start_course_review(client: Client, callback_query: CallbackQuery):
    """Start reviewing a specific course"""
    try:
        review_id = callback_query.matches[0].group(1)
        telegram_id = callback_query.from_user.id
        
        # Get review details
        review_query = """
            SELECT r.*, c.title, c.description, c.banner_link, c.id as course_id
            FROM reviews r
            JOIN courses c ON r.course_id = c.id
            WHERE r.id = $1 AND r.reviewer_id = (
                SELECT id FROM users WHERE telegram_id = $2
            )
        """
        
        review_result = await supabase_client.execute_query(review_query, review_id, telegram_id)
        
        if not review_result:
            await callback_query.answer("❌ Review not found or not assigned to you", show_alert=True)
            return
        
        review = review_result[0]
        course_id = review['course_id']
        
        # Get course files
        try:
            files_query = "SELECT COUNT(*) as file_count FROM course_files WHERE course_id = $1"
            files_result = await supabase_client.execute_query(files_query, course_id)
            file_count = files_result[0]['file_count'] if files_result else 0
        except Exception as e:
            logger.error(f"Error fetching course files count: {e}")
            file_count = 0
        
        review_text = f"""
📝 **Course Review Details**

📚 **Title:** {review['title']}
📄 **Description:** {review.get('description', 'No description provided')[:200]}...
🆔 **Course ID:** `{course_id}`
📁 **Files:** {file_count} items
🔥 **Priority:** {'High' if review.get('priority_level', 1) > 1 else 'Normal'}

**Review Checklist:**
✅ Content quality and accuracy
✅ File completeness and accessibility  
✅ Appropriate categorization
✅ No inappropriate content
✅ Educational value

Choose your action:
        """
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve Course", callback_data=f"approve_course_{review_id}"),
                InlineKeyboardButton("❌ Reject Course", callback_data=f"reject_course_{review_id}")
            ],
            [
                InlineKeyboardButton("📁 View Files", callback_data=f"view_course_files_{course_id}"),
                InlineKeyboardButton("🔗 View Banner", callback_data=f"view_banner_{course_id}")
            ],
            [
                InlineKeyboardButton("📝 Add Comments", callback_data=f"add_review_comments_{review_id}"),
                InlineKeyboardButton("⏸️ Skip for Now", callback_data="review_my_queue")
            ],
            [InlineKeyboardButton("🔙 Back to Queue", callback_data="review_my_queue")]
        ])
        
        await callback_query.edit_message_text(
            review_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Start review error: {e}")
        await callback_query.answer("❌ Error starting review", show_alert=True)

@Client.on_callback_query(filters.regex(r"^approve_course_(.+)$"))
async def approve_course_review(client: Client, callback_query: CallbackQuery):
    """Approve a course after review"""
    try:
        review_id = callback_query.matches[0].group(1)
        telegram_id = callback_query.from_user.id
        
        # Check permissions
        if not await rbac_manager.check_permission(telegram_id, 'approve_courses'):
            await callback_query.answer("❌ Insufficient permissions", show_alert=True)
            return
        
        # Update review status
        update_query = """
            UPDATE reviews 
            SET status = 'approved', reviewed_at = NOW(), comments = COALESCE(comments, '') || 'APPROVED by volunteer reviewer'
            WHERE id = $1 AND reviewer_id = (
                SELECT id FROM users WHERE telegram_id = $2
            )
            RETURNING course_id
        """
        
        result = await supabase_client.execute_query(update_query, review_id, telegram_id)
        
        if not result:
            await callback_query.answer("❌ Review not found", show_alert=True)
            return
        
        course_id = result[0]['course_id']
        
        # Update course status to approved
        await supabase_client.execute_command(
            "UPDATE courses SET status = 'approved', updated_at = NOW() WHERE id = $1",
            course_id
        )
        
        success_text = f"""
✅ **Course Approved Successfully**

🎉 The course has been approved and will be available to the community.

🆔 **Review ID:** `{review_id}`
⏰ **Approved at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Thank you for your contribution to maintaining course quality!
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Back to Queue", callback_data="review_my_queue")],
            [InlineKeyboardButton("📊 My Stats", callback_data="review_my_stats")]
        ])
        
        await callback_query.edit_message_text(
            success_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
        # Log the approval
        logger.info(f"Course {course_id} approved by reviewer {telegram_id}")
        
    except Exception as e:
        logger.error(f"Course approval error: {e}")
        await callback_query.answer("❌ Error approving course", show_alert=True)

@Client.on_callback_query(filters.regex(r"^reject_course_(.+)$"))
async def reject_course_review(client: Client, callback_query: CallbackQuery):
    """Reject a course after review"""
    try:
        review_id = callback_query.matches[0].group(1)
        telegram_id = callback_query.from_user.id
        
        # Check permissions  
        if not await rbac_manager.check_permission(telegram_id, 'approve_courses'):
            await callback_query.answer("❌ Insufficient permissions", show_alert=True)
            return
        
        reject_text = f"""
❌ **Course Rejection**

You are about to reject this course. Please provide a reason for rejection:

🔸 Quality issues
🔸 Inappropriate content  
🔸 Missing files
🔸 Wrong category
🔸 Other reasons

Type your rejection reason as a reply to this message, or use the quick options below:
        """
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔸 Quality Issues", callback_data=f"reject_reason_{review_id}_quality"),
                InlineKeyboardButton("🔸 Wrong Category", callback_data=f"reject_reason_{review_id}_category")
            ],
            [
                InlineKeyboardButton("🔸 Missing Files", callback_data=f"reject_reason_{review_id}_files"),
                InlineKeyboardButton("🔸 Inappropriate", callback_data=f"reject_reason_{review_id}_inappropriate")
            ],
            [
                InlineKeyboardButton("✏️ Custom Reason", callback_data=f"reject_custom_{review_id}"),
                InlineKeyboardButton("🔙 Cancel", callback_data=f"start_review_{review_id}")
            ]
        ])
        
        await callback_query.edit_message_text(
            reject_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Course rejection error: {e}")
        await callback_query.answer("❌ Error processing rejection", show_alert=True)

@Client.on_callback_query(filters.regex(r"^reject_reason_(.+)_(.+)$"))
async def process_course_rejection(client: Client, callback_query: CallbackQuery):
    """Process course rejection with reason"""
    try:
        review_id = callback_query.matches[0].group(1)
        reason_code = callback_query.matches[0].group(2)
        telegram_id = callback_query.from_user.id
        
        # Map reason codes to descriptions
        rejection_reasons = {
            'quality': 'Course quality does not meet community standards',
            'category': 'Course is incorrectly categorized or filed',
            'files': 'Course has missing or inaccessible files', 
            'inappropriate': 'Course contains inappropriate or off-topic content'
        }
        
        rejection_reason = rejection_reasons.get(reason_code, 'Course rejected by reviewer')
        
        # Update review status
        update_query = """
            UPDATE reviews 
            SET status = 'rejected', reviewed_at = NOW(), comments = $3
            WHERE id = $1 AND reviewer_id = (
                SELECT id FROM users WHERE telegram_id = $2
            )
            RETURNING course_id
        """
        
        result = await supabase_client.execute_query(update_query, review_id, telegram_id, rejection_reason)
        
        if not result:
            await callback_query.answer("❌ Review not found", show_alert=True)
            return
        
        course_id = result[0]['course_id']
        
        # Update course status to rejected
        await supabase_client.execute_command(
            "UPDATE courses SET status = 'rejected', updated_at = NOW() WHERE id = $1",
            course_id
        )
        
        success_text = f"""
❌ **Course Rejected**

The course has been rejected and removed from the review queue.

🆔 **Review ID:** `{review_id}`
📝 **Reason:** {rejection_reason}
⏰ **Rejected at:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

The contributor will be notified with feedback for improvement.
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Back to Queue", callback_data="review_my_queue")],
            [InlineKeyboardButton("📊 My Stats", callback_data="review_my_stats")]
        ])
        
        await callback_query.edit_message_text(
            success_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
        # Log the rejection
        logger.info(f"Course {course_id} rejected by reviewer {telegram_id}: {rejection_reason}")
        
    except Exception as e:
        logger.error(f"Course rejection processing error: {e}")
        await callback_query.answer("❌ Error processing rejection", show_alert=True)

@Client.on_callback_query(filters.regex(r"^review_my_stats$"))
async def show_reviewer_stats(client: Client, callback_query: CallbackQuery):
    """Show personal reviewer statistics"""
    try:
        telegram_id = callback_query.from_user.id
        
        # Get user ID
        user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await callback_query.answer("❌ User not found", show_alert=True)
            return
        
        # Get reviewer statistics
        stats_query = """
            SELECT 
                COUNT(*) FILTER (WHERE status = 'pending') as pending_reviews,
                COUNT(*) FILTER (WHERE status = 'approved') as approved_reviews,
                COUNT(*) FILTER (WHERE status = 'rejected') as rejected_reviews,
                AVG(EXTRACT(EPOCH FROM (reviewed_at - created_at))/3600) FILTER (WHERE status IN ('approved', 'rejected')) as avg_review_time_hours,
                MIN(created_at) as first_review_date
            FROM reviews
            WHERE reviewer_id = $1
        """
        
        stats = await supabase_client.execute_query(stats_query, user['id'])
        
        if stats:
            stat_data = stats[0]
            
            total_completed = (stat_data.get('approved_reviews', 0) or 0) + (stat_data.get('rejected_reviews', 0) or 0)
            approval_rate = 0
            if total_completed > 0:
                approval_rate = round(((stat_data.get('approved_reviews', 0) or 0) / total_completed) * 100, 1)
            
            avg_time = stat_data.get('avg_review_time_hours', 0)
            avg_time_display = f"{round(avg_time, 1)} hours" if avg_time else "N/A"
            
            first_review = stat_data.get('first_review_date')
            days_active = 0
            if first_review:
                days_active = (datetime.now().date() - first_review.date()).days
            
            stats_text = f"""
📊 **Your Review Statistics**

📋 **Review Activity:**
⏳ Pending: `{stat_data.get('pending_reviews', 0)}`
✅ Approved: `{stat_data.get('approved_reviews', 0)}`
❌ Rejected: `{stat_data.get('rejected_reviews', 0)}`
📈 Total Completed: `{total_completed}`

⚡ **Performance Metrics:**
🎯 Approval Rate: `{approval_rate}%`
⏱️ Average Review Time: `{avg_time_display}`
🗓️ Days Active: `{days_active} days`

🏆 **Reviewer Level:** {'Expert' if total_completed > 50 else 'Advanced' if total_completed > 20 else 'Active' if total_completed > 5 else 'New'}
            """
        else:
            stats_text = """
📊 **Your Review Statistics**

📋 **Review Activity:**
No review activity found.

🎯 Complete your first course review to see statistics here!
            """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 View Queue", callback_data="review_my_queue")],
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_review_panel")]
        ])
        
        await callback_query.edit_message_text(
            stats_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Show reviewer stats error: {e}")
        await callback_query.answer("❌ Error loading statistics", show_alert=True)

@Client.on_callback_query(filters.regex(r"^back_to_review_panel$"))
async def back_to_review_panel(client: Client, callback_query: CallbackQuery):
    """Return to main review panel"""
    try:
        telegram_id = callback_query.from_user.id
        
        # Get user info
        user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
        if not user:
            await callback_query.answer("❌ User not found", show_alert=True)
            return
        
        # Get review queue for this volunteer
        review_queue = await volunteer_manager.get_volunteer_queue(user['id'])
        
        # Create panel keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 My Queue", callback_data="review_my_queue"),
                InlineKeyboardButton("📊 My Stats", callback_data="review_my_stats")
            ],
            [
                InlineKeyboardButton("🔄 Refresh Queue", callback_data="review_refresh_queue"),
                InlineKeyboardButton("❓ Review Guide", callback_data="review_guide")
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="close_review_panel")
            ]
        ])
        
        pending_count = len(review_queue)
        
        panel_text = f"""
📝 **Volunteer Review Panel**

👤 **Reviewer:** `{user.get('anonymous_id', 'Unknown')}`
🏷️ **Role:** `{user.get('role', 'Unknown').replace('_', ' ').title()}`

📋 **Current Queue Status:**
⏳ Pending Reviews: `{pending_count}`
🎯 Priority Reviews: `{sum(1 for r in review_queue if r.get('priority_level', 1) > 1)}`

Select an option to manage your review assignments:
        """
        
        await callback_query.edit_message_text(
            panel_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Back to review panel error: {e}")
        await callback_query.answer("❌ Error returning to panel", show_alert=True)

@Client.on_callback_query(filters.regex(r"^close_review_panel$"))
async def close_review_panel(client: Client, callback_query: CallbackQuery):
    """Close the review panel"""
    await callback_query.edit_message_text(
        "📝 **Review Panel Closed**\n\nUse `/review_panel` to reopen your volunteer dashboard.",
        disable_web_page_preview=True
    )