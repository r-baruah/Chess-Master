"""
Advanced User Management Plugin - Large-scale user operations and announcements
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

from core.advanced_user_manager import advanced_user_manager
from core.targeted_announcement_manager import targeted_announcement_manager
from core.anonymity import anonymous_manager
from core.roles import rbac_manager
import logging

logger = logging.getLogger(__name__)

class AdvancedUserManagementPlugin:
    """Plugin for advanced user management and targeted announcements"""
    
    def __init__(self, app: Client):
        self.app = app
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup command and callback handlers"""
        
        @self.app.on_message(filters.command("users") & filters.private)
        async def users_command(client, message: Message):
            """User management command"""
            await self.handle_users_command(message)
        
        @self.app.on_message(filters.command("announce") & filters.private)
        async def announce_command(client, message: Message):
            """Create announcement command"""
            await self.handle_announce_command(message)
        
        @self.app.on_message(filters.command("announcements") & filters.private)
        async def announcements_command(client, message: Message):
            """View announcements command"""
            await self.handle_announcements_command(message)
        
        @self.app.on_callback_query(filters.regex(r"^users_"))
        async def users_callbacks(client, callback: CallbackQuery):
            """Handle user management callbacks"""
            await self.handle_users_callback(callback)
        
        @self.app.on_callback_query(filters.regex(r"^announce_"))
        async def announce_callbacks(client, callback: CallbackQuery):
            """Handle announcement callbacks"""
            await self.handle_announce_callback(callback)
    
    async def handle_users_command(self, message: Message):
        """Handle /users command - user management interface"""
        try:
            user_id = message.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user or not await rbac_manager.check_permission(user['anonymous_id'], 'manage_users'):
                await message.reply("❌ Permission denied. Admin access required.")
                return
            
            # Get quick user statistics
            stats = await self._get_user_stats()
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👥 Browse Users", callback_data="users_browse"),
                    InlineKeyboardButton("🔍 Search Users", callback_data="users_search")
                ],
                [
                    InlineKeyboardButton("📊 User Segments", callback_data="users_segments"),
                    InlineKeyboardButton("⚡ Bulk Operations", callback_data="users_bulk")
                ],
                [
                    InlineKeyboardButton("📈 User Analytics", callback_data="users_analytics"),
                    InlineKeyboardButton("📋 Export Data", callback_data="users_export")
                ]
            ])
            
            stats_text = f"""
👥 **User Management Dashboard**

📊 **Current Statistics:**
• Total Users: {stats.get('total_users', 0)}
• Active Users (7d): {stats.get('active_users', 0)}
• New Users (7d): {stats.get('new_users', 0)}
• Contributors: {stats.get('contributors', 0)}
• Volunteers: {stats.get('volunteers', 0)}

🔧 **Management Tools:**
Select an option below to manage your community:
            """
            
            await message.reply(stats_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Users command error: {e}")
            await message.reply("❌ Error loading user management interface")
    
    async def handle_announce_command(self, message: Message):
        """Handle /announce command - create targeted announcements"""
        try:
            user_id = message.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user or not await rbac_manager.check_permission(user['anonymous_id'], 'manage_users'):
                await message.reply("❌ Permission denied. Admin access required.")
                return
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📢 New Announcement", callback_data="announce_create"),
                    InlineKeyboardButton("📋 Templates", callback_data="announce_templates")
                ],
                [
                    InlineKeyboardButton("🎯 Target Builder", callback_data="announce_targeting"),
                    InlineKeyboardButton("⏰ Schedule", callback_data="announce_schedule")
                ],
                [
                    InlineKeyboardButton("📊 Analytics", callback_data="announce_analytics"),
                    InlineKeyboardButton("📝 My Drafts", callback_data="announce_drafts")
                ]
            ])
            
            await message.reply(
                "📢 **Announcement Center**\n\nCreate and manage targeted community announcements:",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Announce command error: {e}")
            await message.reply("❌ Error loading announcement interface")
    
    async def handle_announcements_command(self, message: Message):
        """Handle /announcements command - view announcement history"""
        try:
            user_id = message.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user:
                await message.reply("❌ User not found")
                return
            
            # Get recent announcements (different view based on permissions)
            if await rbac_manager.check_permission(user['anonymous_id'], 'manage_users'):
                announcements = await self._get_admin_announcements(user['anonymous_id'])
            else:
                announcements = await self._get_user_announcements(user['anonymous_id'])
            
            if not announcements:
                await message.reply("📢 No announcements found")
                return
            
            announcement_text = "📢 **Recent Announcements**\n\n"
            
            for ann in announcements[:5]:  # Show last 5
                status_emoji = self._get_status_emoji(ann['status'])
                announcement_text += f"{status_emoji} **{ann['title']}**\n"
                announcement_text += f"📅 {ann['created_at'][:10]}\n"
                if 'estimated_recipients' in ann:
                    announcement_text += f"👥 {ann['estimated_recipients']} recipients\n"
                announcement_text += "\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 View Analytics", callback_data="announce_view_analytics")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="announcements_refresh")]
            ])
            
            await message.reply(announcement_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Announcements command error: {e}")
            await message.reply("❌ Error loading announcements")
    
    async def handle_users_callback(self, callback: CallbackQuery):
        """Handle user management callbacks"""
        try:
            action = callback.data.replace("users_", "")
            user_id = callback.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user or not await rbac_manager.check_permission(user['anonymous_id'], 'manage_users'):
                await callback.answer("❌ Permission denied", show_alert=True)
                return
            
            if action == "browse":
                await self._handle_browse_users(callback, user)
            elif action == "search":
                await self._handle_search_users(callback, user)
            elif action == "segments":
                await self._handle_user_segments(callback, user)
            elif action == "bulk":
                await self._handle_bulk_operations(callback, user)
            elif action == "analytics":
                await self._handle_user_analytics(callback, user)
            elif action == "export":
                await self._handle_export_users(callback, user)
            
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Users callback error: {e}")
            await callback.answer("❌ Error processing request", show_alert=True)
    
    async def handle_announce_callback(self, callback: CallbackQuery):
        """Handle announcement callbacks"""
        try:
            action = callback.data.replace("announce_", "")
            user_id = callback.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user or not await rbac_manager.check_permission(user['anonymous_id'], 'manage_users'):
                await callback.answer("❌ Permission denied", show_alert=True)
                return
            
            if action == "create":
                await self._handle_create_announcement(callback, user)
            elif action == "templates":
                await self._handle_announcement_templates(callback, user)
            elif action == "targeting":
                await self._handle_targeting_builder(callback, user)
            elif action == "schedule":
                await self._handle_schedule_announcement(callback, user)
            elif action == "analytics":
                await self._handle_announcement_analytics(callback, user)
            elif action == "drafts":
                await self._handle_announcement_drafts(callback, user)
            
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Announce callback error: {e}")
            await callback.answer("❌ Error processing request", show_alert=True)
    
    async def _handle_browse_users(self, callback: CallbackQuery, user: Dict):
        """Handle browse users interface"""
        try:
            # Get first page of users
            users_data = await advanced_user_manager.get_users_paginated(
                page=1, page_size=10, sort_by='created_at', sort_order='DESC'
            )
            
            if 'error' in users_data:
                await callback.message.edit_text(f"❌ Error: {users_data['error']}")
                return
            
            users_list = users_data['users']
            pagination = users_data['pagination']
            
            users_text = f"👥 **Users Browser** (Page {pagination['current_page']}/{pagination['total_pages']})\n\n"
            
            for i, user_info in enumerate(users_list, 1):
                role_emoji = self._get_role_emoji(user_info['role'])
                users_text += f"{role_emoji} **User #{i}**\n"
                users_text += f"🏷️ Role: {user_info['role'].title()}\n"
                users_text += f"📅 Joined: {user_info['created_at'][:10]}\n"
                if user_info.get('last_active'):
                    users_text += f"🕐 Last Active: {user_info['last_active'][:10]}\n"
                users_text += "\n"
            
            # Navigation buttons
            nav_buttons = []
            if pagination['has_prev']:
                nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="users_page_prev"))
            if pagination['has_next']:
                nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data="users_page_next"))
            
            keyboard_rows = []
            if nav_buttons:
                keyboard_rows.append(nav_buttons)
            
            keyboard_rows.extend([
                [
                    InlineKeyboardButton("🎯 Filter Users", callback_data="users_filter"),
                    InlineKeyboardButton("🔍 Search", callback_data="users_search")
                ],
                [InlineKeyboardButton("⬅️ Back to Menu", callback_data="users_menu")]
            ])
            
            keyboard = InlineKeyboardMarkup(keyboard_rows)
            await callback.message.edit_text(users_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Browse users error: {e}")
            await callback.message.edit_text("❌ Error browsing users")
    
    async def _handle_user_segments(self, callback: CallbackQuery, user: Dict):
        """Handle user segmentation interface"""
        try:
            # Define available segments
            segmentation_rules = {
                'new_users': True,
                'power_users': True,
                'at_risk_users': True,
                'contributors': True,
                'volunteers': True
            }
            
            segments = await advanced_user_manager.segment_users(
                segmentation_rules, user['anonymous_id']
            )
            
            if 'error' in segments:
                await callback.message.edit_text(f"❌ Error: {segments['error']}")
                return
            
            segments_text = "📊 **User Segments**\n\n"
            
            segment_labels = {
                'new_users': '🆕 New Users (7 days)',
                'power_users': '⭐ Power Users',
                'at_risk_users': '⚠️ At-Risk Users',
                'contributors': '📚 Contributors',
                'volunteers': '🔍 Volunteers'
            }
            
            for segment_key, users_list in segments.items():
                label = segment_labels.get(segment_key, segment_key.title())
                count = len(users_list)
                segments_text += f"{label}: **{count}** users\n"
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎯 Target Segment", callback_data="announce_target_segment"),
                    InlineKeyboardButton("📊 Segment Analytics", callback_data="users_segment_analytics")
                ],
                [InlineKeyboardButton("⬅️ Back", callback_data="users_menu")]
            ])
            
            await callback.message.edit_text(segments_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"User segments error: {e}")
            await callback.message.edit_text("❌ Error loading user segments")
    
    async def _handle_create_announcement(self, callback: CallbackQuery, user: Dict):
        """Handle create announcement interface"""
        try:
            # Show announcement creation options
            creation_text = """
📢 **Create New Announcement**

Choose your announcement type:

🎯 **Targeting Options:**
• All Users - Broadcast to entire community
• Role-Based - Target specific user roles
• Segment-Based - Target user behavior segments
• Custom List - Upload specific user list

📝 **Message Options:**
• Text Message - Simple text announcement
• Rich Message - Formatted with buttons and media
• Survey - Interactive announcement with responses

⏰ **Delivery Options:**
• Send Immediately - Deliver right away
• Schedule - Set future delivery time
• A/B Testing - Test different versions
            """
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎯 All Users", callback_data="create_announce_all"),
                    InlineKeyboardButton("🏷️ Role-Based", callback_data="create_announce_role")
                ],
                [
                    InlineKeyboardButton("📊 Segment-Based", callback_data="create_announce_segment"),
                    InlineKeyboardButton("📝 Custom List", callback_data="create_announce_custom")
                ],
                [
                    InlineKeyboardButton("📋 Use Template", callback_data="announce_templates"),
                    InlineKeyboardButton("⬅️ Back", callback_data="announce_menu")
                ]
            ])
            
            await callback.message.edit_text(creation_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Create announcement error: {e}")
            await callback.message.edit_text("❌ Error creating announcement interface")
    
    # Helper methods
    async def _get_user_stats(self) -> Dict[str, int]:
        """Get quick user statistics"""
        try:
            # Total users
            total_result = await advanced_user_manager.supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM users"
            )
            
            # Active users (7 days)
            active_cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
            active_result = await advanced_user_manager.supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM users WHERE last_active >= $1",
                active_cutoff
            )
            
            # New users (7 days)
            new_cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
            new_result = await advanced_user_manager.supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM users WHERE created_at >= $1",
                new_cutoff
            )
            
            # Contributors
            contrib_result = await advanced_user_manager.supabase_client.execute_query(
                "SELECT COUNT(DISTINCT anonymous_contributor) as count FROM courses"
            )
            
            # Volunteers
            vol_result = await advanced_user_manager.supabase_client.execute_query(
                "SELECT COUNT(*) as count FROM users WHERE role = 'volunteer_reviewer'"
            )
            
            return {
                'total_users': total_result[0]['count'] if total_result else 0,
                'active_users': active_result[0]['count'] if active_result else 0,
                'new_users': new_result[0]['count'] if new_result else 0,
                'contributors': contrib_result[0]['count'] if contrib_result else 0,
                'volunteers': vol_result[0]['count'] if vol_result else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}
    
    async def _get_admin_announcements(self, anonymous_id: str) -> List[Dict]:
        """Get announcements for admin view"""
        try:
            result = await targeted_announcement_manager.supabase_client.execute_query(
                """
                SELECT id, title, status, estimated_recipients, created_at
                FROM announcements
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            return result or []
        except Exception:
            return []
    
    async def _get_user_announcements(self, anonymous_id: str) -> List[Dict]:
        """Get announcements for regular user view"""
        try:
            # Regular users see announcements they received
            result = await targeted_announcement_manager.supabase_client.execute_query(
                """
                SELECT a.id, a.title, a.created_at
                FROM announcements a
                JOIN announcement_deliveries d ON a.id = d.announcement_id
                WHERE d.recipient_anonymous_id = $1
                ORDER BY a.created_at DESC
                LIMIT 5
                """,
                anonymous_id
            )
            return result or []
        except Exception:
            return []
    
    def _get_status_emoji(self, status: str) -> str:
        """Get emoji for announcement status"""
        status_emojis = {
            'draft': '[DRAFT]',
            'scheduled': '[SCHED]',
            'sending': '[SEND]',
            'sent': '[SENT]',
            'failed': '[FAIL]',
            'cancelled': '[CANCEL]'
        }
        return status_emojis.get(status, '[ANNOUNCE]')
    
    def _get_role_emoji(self, role: str) -> str:
        """Get emoji for user role"""
        role_emojis = {
            'super_admin': '[SUPER]',
            'admin': '[ADMIN]',
            'moderator': '[MOD]',
            'volunteer_reviewer': '[VOL]',
            'contributor': '[USER]'
        }
        return role_emojis.get(role, 'User')

def setup_advanced_user_management_plugin(app: Client):
    """Setup advanced user management plugin"""
    return AdvancedUserManagementPlugin(app)