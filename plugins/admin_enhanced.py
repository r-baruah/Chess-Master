"""
Anonymous Role Management Interface Plugin
Implements AC3: Anonymous Role Management Interface from Story 1.3
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from core.roles import rbac_manager
from core.anonymity import anonymous_manager
from core.volunteer_system import volunteer_manager
from info import ADMINS

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("role_panel") & filters.private)
async def role_management_panel(client: Client, message: Message):
    """Admin interface for role management"""
    try:
        telegram_id = message.from_user.id
        
        # Check if user has role management permissions
        if not await rbac_manager.check_permission(telegram_id, 'manage_roles'):
            await message.reply("❌ You don't have permission to access the role management panel.")
            return
        
        # Get user's role for display
        user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
        user_role = user.get('role', 'unknown') if user else 'unknown'
        
        # Create role management keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👥 View All Users", callback_data="role_view_users"),
                InlineKeyboardButton("🔄 Assign Roles", callback_data="role_assign_menu")
            ],
            [
                InlineKeyboardButton("📊 Role Statistics", callback_data="role_statistics"),
                InlineKeyboardButton("🎯 Volunteer Queue", callback_data="volunteer_queue_stats")
            ],
            [
                InlineKeyboardButton("⚖️ Permission Matrix", callback_data="permission_matrix"),
                InlineKeyboardButton("🔄 Rebalance Workload", callback_data="rebalance_workload")
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="close_panel")
            ]
        ])
        
        panel_text = f"""
🛡️ **Anonymous Role Management Panel**

👤 **Your Role:** `{user_role.title()}`
🔑 **Access Level:** Full Role Management

Select an option below to manage community roles and permissions:

• **View All Users** - List users by role
• **Assign Roles** - Change user roles  
• **Role Statistics** - View role distribution
• **Volunteer Queue** - Manage review assignments
• **Permission Matrix** - View all permissions
• **Rebalance Workload** - Distribute volunteer workload

All operations maintain complete anonymity.
        """
        
        await message.reply(
            panel_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Role panel error: {e}")
        await message.reply("❌ Error accessing role management panel.")

@Client.on_callback_query(filters.regex(r"^role_view_users$"))
async def view_users_by_role(client: Client, callback_query: CallbackQuery):
    """Display users organized by role"""
    try:
        telegram_id = callback_query.from_user.id
        
        if not await rbac_manager.check_permission(telegram_id, 'manage_users'):
            await callback_query.answer("❌ Insufficient permissions", show_alert=True)
            return
        
        # Get role statistics
        role_stats = {}
        roles = ['super_admin', 'admin', 'moderator', 'volunteer_reviewer', 'contributor']
        
        for role in roles:
            users = await rbac_manager.list_users_by_role(role, telegram_id)
            role_stats[role] = len(users)
        
        stats_text = "👥 **User Distribution by Role**\n\n"
        
        for role, count in role_stats.items():
            role_emoji = {
                'super_admin': '👑',
                'admin': '🛡️',
                'moderator': '⚖️',
                'volunteer_reviewer': '📝',
                'contributor': '👤'
            }.get(role, '❓')
            
            stats_text += f"{role_emoji} **{role.replace('_', ' ').title()}:** {count} users\n"
        
        total_users = sum(role_stats.values())
        stats_text += f"\n📊 **Total Community Members:** {total_users}"
        
        # Create back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_role_panel")]
        ])
        
        await callback_query.edit_message_text(
            stats_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"View users error: {e}")
        await callback_query.answer("❌ Error retrieving user data", show_alert=True)

@Client.on_callback_query(filters.regex(r"^role_assign_menu$"))
async def role_assignment_menu(client: Client, callback_query: CallbackQuery):
    """Show role assignment interface"""
    try:
        telegram_id = callback_query.from_user.id
        
        if not await rbac_manager.check_permission(telegram_id, 'manage_roles'):
            await callback_query.answer("❌ Insufficient permissions for role assignment", show_alert=True)
            return
        
        text = """
🔄 **Role Assignment Interface**

To assign a role to a user, use one of these methods:

**Method 1: By Reply**
Reply to a user's message with:
`/assign_role [role_name]`

**Method 2: By User ID**
Use command:
`/assign_role @username [role_name]`

**Available Roles:**
👑 `super_admin` - Full system access
🛡️ `admin` - Community management
⚖️ `moderator` - Content moderation
📝 `volunteer_reviewer` - Course review only
👤 `contributor` - Basic access (default)

⚠️ **Note:** You can only assign roles below your own hierarchy level.
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_role_panel")]
        ])
        
        await callback_query.edit_message_text(
            text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Role assignment menu error: {e}")
        await callback_query.answer("❌ Error loading assignment menu", show_alert=True)

@Client.on_callback_query(filters.regex(r"^volunteer_queue_stats$"))
async def volunteer_queue_statistics(client: Client, callback_query: CallbackQuery):
    """Display volunteer queue and assignment statistics"""
    try:
        telegram_id = callback_query.from_user.id
        
        if not await rbac_manager.check_permission(telegram_id, 'view_analytics'):
            await callback_query.answer("❌ Insufficient permissions", show_alert=True)
            return
        
        # Get assignment statistics
        stats = await volunteer_manager.get_assignment_statistics()
        
        stats_text = f"""
📋 **Volunteer Review System Statistics**

**Current Queue Status:**
⏳ Pending Reviews: `{stats.get('pending_reviews', 0)}`
✅ Completed (30 days): `{stats.get('completed_reviews', 0)}`
❌ Rejected (30 days): `{stats.get('rejected_reviews', 0)}`

**Performance Metrics:**
⏱️ Average Review Time: `{stats.get('avg_review_time_hours', 0)} hours`
👥 Active Reviewers: `{stats.get('active_reviewers', 0)}`
📈 Approval Rate: `{stats.get('approval_rate', 0)}%`

**System Health:**
{'🟢 Healthy' if stats.get('pending_reviews', 0) < 50 else '🟡 Busy' if stats.get('pending_reviews', 0) < 100 else '🔴 Overloaded'}
        """
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Rebalance Now", callback_data="rebalance_workload"),
                InlineKeyboardButton("📊 Detailed Stats", callback_data="detailed_volunteer_stats")
            ],
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_role_panel")]
        ])
        
        await callback_query.edit_message_text(
            stats_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Volunteer queue stats error: {e}")
        await callback_query.answer("❌ Error retrieving statistics", show_alert=True)

@Client.on_callback_query(filters.regex(r"^rebalance_workload$"))
async def rebalance_volunteer_workload(client: Client, callback_query: CallbackQuery):
    """Trigger workload rebalancing across volunteers"""
    try:
        telegram_id = callback_query.from_user.id
        
        if not await rbac_manager.check_permission(telegram_id, 'manage_users'):
            await callback_query.answer("❌ Insufficient permissions for workload management", show_alert=True)
            return
        
        await callback_query.answer("🔄 Rebalancing workload...", show_alert=False)
        
        # Perform rebalancing
        rebalanced = await volunteer_manager.rebalance_workload()
        
        if rebalanced:
            result_text = "✅ **Workload Rebalanced Successfully**\n\n"
            for transfer, count in rebalanced.items():
                result_text += f"📤 Moved {count} reviews: {transfer}\n"
        else:
            result_text = "ℹ️ **No Rebalancing Needed**\n\nWorkload is already well distributed across volunteers."
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 View Updated Stats", callback_data="volunteer_queue_stats")],
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_role_panel")]
        ])
        
        await callback_query.edit_message_text(
            result_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Workload rebalancing error: {e}")
        await callback_query.answer("❌ Error during rebalancing", show_alert=True)

@Client.on_callback_query(filters.regex(r"^permission_matrix$"))
async def show_permission_matrix(client: Client, callback_query: CallbackQuery):
    """Display complete permission matrix"""
    try:
        telegram_id = callback_query.from_user.id
        
        if not await rbac_manager.check_permission(telegram_id, 'view_analytics'):
            await callback_query.answer("❌ Insufficient permissions", show_alert=True)
            return
        
        matrix = await rbac_manager.get_permission_matrix()
        
        matrix_text = "🔐 **Role Permission Matrix**\n\n"
        
        # Permission descriptions
        perm_descriptions = {
            'manage_users': '👥 User Management',
            'manage_roles': '🔄 Role Assignment',
            'approve_courses': '✅ Course Approval',
            'view_analytics': '📊 View Statistics',
            'system_admin': '⚙️ System Administration',
            'manage_channels': '📢 Channel Management',
            'upload_courses': '📤 Upload Courses',
            'view_own_courses': '👀 View Own Content'
        }
        
        for role, permissions in matrix.items():
            role_emoji = {
                'super_admin': '👑',
                'admin': '🛡️',
                'moderator': '⚖️',
                'volunteer_reviewer': '📝',
                'contributor': '👤'
            }.get(role, '❓')
            
            matrix_text += f"\n{role_emoji} **{role.replace('_', ' ').title()}**\n"
            
            for perm, has_access in permissions.items():
                desc = perm_descriptions.get(perm, perm)
                status = "✅" if has_access else "❌"
                matrix_text += f"  {status} {desc}\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Panel", callback_data="back_to_role_panel")]
        ])
        
        await callback_query.edit_message_text(
            matrix_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Permission matrix error: {e}")
        await callback_query.answer("❌ Error loading permission matrix", show_alert=True)

@Client.on_callback_query(filters.regex(r"^back_to_role_panel$"))
async def back_to_role_panel(client: Client, callback_query: CallbackQuery):
    """Return to main role management panel"""
    try:
        # Regenerate the main panel
        telegram_id = callback_query.from_user.id
        user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
        user_role = user.get('role', 'unknown') if user else 'unknown'
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👥 View All Users", callback_data="role_view_users"),
                InlineKeyboardButton("🔄 Assign Roles", callback_data="role_assign_menu")
            ],
            [
                InlineKeyboardButton("📊 Role Statistics", callback_data="role_statistics"),
                InlineKeyboardButton("🎯 Volunteer Queue", callback_data="volunteer_queue_stats")
            ],
            [
                InlineKeyboardButton("⚖️ Permission Matrix", callback_data="permission_matrix"),
                InlineKeyboardButton("🔄 Rebalance Workload", callback_data="rebalance_workload")
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="close_panel")
            ]
        ])
        
        panel_text = f"""
🛡️ **Anonymous Role Management Panel**

👤 **Your Role:** `{user_role.title()}`
🔑 **Access Level:** Full Role Management

Select an option below to manage community roles and permissions:

• **View All Users** - List users by role
• **Assign Roles** - Change user roles  
• **Role Statistics** - View role distribution
• **Volunteer Queue** - Manage review assignments
• **Permission Matrix** - View all permissions
• **Rebalance Workload** - Distribute volunteer workload

All operations maintain complete anonymity.
        """
        
        await callback_query.edit_message_text(
            panel_text,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Back to panel error: {e}")
        await callback_query.answer("❌ Error returning to panel", show_alert=True)

@Client.on_callback_query(filters.regex(r"^close_panel$"))
async def close_role_panel(client: Client, callback_query: CallbackQuery):
    """Close the role management panel"""
    await callback_query.edit_message_text(
        "🛡️ **Role Management Panel Closed**\n\nUse `/role_panel` to reopen.",
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("assign_role") & filters.private)
async def assign_user_role(client: Client, message: Message):
    """Command to assign roles to users"""
    try:
        telegram_id = message.from_user.id
        
        # Check permissions
        if not await rbac_manager.check_permission(telegram_id, 'manage_roles'):
            await message.reply("❌ You don't have permission to assign roles.")
            return
        
        # Parse command arguments
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []
        
        if not args:
            await message.reply(
                "❌ **Invalid usage**\n\n"
                "**Usage:** `/assign_role [role_name]` (reply to a user's message)\n"
                "**Or:** `/assign_role @username [role_name]`\n\n"
                "**Available roles:** super_admin, admin, moderator, volunteer_reviewer, contributor"
            )
            return
        
        target_user = None
        role_name = None
        
        # Check if replying to a message
        if message.reply_to_message and message.reply_to_message.from_user:
            target_telegram_id = message.reply_to_message.from_user.id
            role_name = args[0]
            target_user = await anonymous_manager.get_user_by_telegram_id(target_telegram_id)
        elif len(args) >= 2:
            # Username provided
            username = args[0].replace('@', '')
            role_name = args[1]
            # Note: We can't easily get telegram_id from username without additional API calls
            await message.reply("❌ Username-based role assignment not yet implemented. Please reply to the user's message instead.")
            return
        
        if not target_user:
            await message.reply("❌ Target user not found in the system.")
            return
        
        # Validate role name
        valid_roles = ['super_admin', 'admin', 'moderator', 'volunteer_reviewer', 'contributor']
        if role_name not in valid_roles:
            await message.reply(f"❌ Invalid role. Available roles: {', '.join(valid_roles)}")
            return
        
        # Attempt role assignment
        success = await rbac_manager.assign_role(target_telegram_id, role_name, telegram_id)
        
        if success:
            await message.reply(
                f"✅ **Role Assignment Successful**\n\n"
                f"🎯 **Target:** {target_user.get('anonymous_id', 'Unknown')}\n"
                f"🏷️ **New Role:** {role_name.replace('_', ' ').title()}\n"
                f"⏰ **Assigned:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            await message.reply("❌ Role assignment failed. Check your permissions and role hierarchy.")
            
    except Exception as e:
        logger.error(f"Role assignment error: {e}")
        await message.reply("❌ Error processing role assignment.")

@Client.on_message(filters.command("my_role") & filters.private)
async def show_my_role(client: Client, message: Message):
    """Show user's current role and permissions"""
    try:
        telegram_id = message.from_user.id
        dashboard = await rbac_manager.get_role_dashboard(telegram_id)
        
        if 'error' in dashboard:
            await message.reply("❌ Could not retrieve your role information.")
            return
        
        role = dashboard.get('role', 'unknown')
        permissions = dashboard.get('permissions', {})
        actions = dashboard.get('available_actions', [])
        hierarchy_level = dashboard.get('hierarchy_level', 0)
        
        role_text = f"""
👤 **Your Role Information**

🏷️ **Current Role:** `{role.replace('_', ' ').title()}`
📊 **Hierarchy Level:** `{hierarchy_level}/100`

🔑 **Your Permissions:**
"""
        
        # Show permissions
        perm_descriptions = {
            'manage_users': '👥 Manage Users',
            'manage_roles': '🔄 Assign Roles',
            'approve_courses': '✅ Approve Courses',
            'view_analytics': '📊 View Statistics',
            'system_admin': '⚙️ System Admin',
            'manage_channels': '📢 Manage Channels',
            'upload_courses': '📤 Upload Courses',
            'view_own_courses': '👀 View Own Content'
        }
        
        for perm, has_access in permissions.items():
            desc = perm_descriptions.get(perm, perm)
            status = "✅" if has_access else "❌"
            role_text += f"{status} {desc}\n"
        
        if actions:
            role_text += f"\n🎯 **Available Actions:**\n"
            for action in actions:
                role_text += f"• {action.replace('_', ' ').title()}\n"
        
        await message.reply(role_text, disable_web_page_preview=True)
        
    except Exception as e:
        logger.error(f"My role error: {e}")
        await message.reply("❌ Error retrieving role information.")