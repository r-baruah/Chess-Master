"""
Community Statistics Plugin - Dashboard access and analytics commands
"""
import asyncio
import json
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

from core.analytics_engine import analytics_engine
from core.community_dashboard import community_dashboard
from core.anonymity import anonymous_manager
from core.roles import rbac_manager
import logging

logger = logging.getLogger(__name__)

class CommunityStatsPlugin:
    """Plugin for community analytics and dashboard access"""
    
    def __init__(self, app: Client):
        self.app = app
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup command and callback handlers"""
        
        @self.app.on_message(filters.command("dashboard") & filters.private)
        async def dashboard_command(client, message: Message):
            """Main dashboard command"""
            await self.handle_dashboard_command(message)
        
        @self.app.on_message(filters.command("stats") & filters.private)
        async def stats_command(client, message: Message):
            """Quick stats command"""
            await self.handle_stats_command(message)
        
        @self.app.on_message(filters.command("analytics") & filters.private)
        async def analytics_command(client, message: Message):
            """Analytics report command"""
            await self.handle_analytics_command(message)
        
        @self.app.on_callback_query(filters.regex(r"^dashboard_"))
        async def dashboard_callbacks(client, callback: CallbackQuery):
            """Handle dashboard navigation callbacks"""
            await self.handle_dashboard_callback(callback)
        
        @self.app.on_callback_query(filters.regex(r"^widget_"))
        async def widget_callbacks(client, callback: CallbackQuery):
            """Handle widget interaction callbacks"""
            await self.handle_widget_callback(callback)
    
    async def handle_dashboard_command(self, message: Message):
        """Handle /dashboard command"""
        try:
            user_id = message.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user:
                await message.reply("❌ User not found. Please register first with /start")
                return
            
            # Check permissions
            if not await rbac_manager.check_permission(user['anonymous_id'], 'view_analytics'):
                await message.reply("❌ You don't have permission to access the dashboard")
                return
            
            # Get dashboard configuration
            permissions = await rbac_manager.get_user_permissions(user['anonymous_id'])
            dashboard_config = await community_dashboard.get_dashboard_config(
                user['anonymous_id'], user['role'], permissions.get('permissions', {})
            )
            
            if 'error' in dashboard_config:
                await message.reply(f"❌ Error loading dashboard: {dashboard_config['error']}")
                return
            
            # Create dashboard menu
            keyboard = await self._create_dashboard_menu(dashboard_config['available_widgets'])
            
            dashboard_text = f"""
📊 **Community Dashboard**
🏷️ Role: {user['role'].title()}

**Available Widgets:**
{self._format_widget_list(dashboard_config['available_widgets'])}

📅 Last Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Select a widget to view detailed analytics:
            """
            
            await message.reply(dashboard_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Dashboard command error: {e}")
            await message.reply("❌ Error loading dashboard. Please try again later.")
    
    async def handle_stats_command(self, message: Message):
        """Handle /stats command - quick overview"""
        try:
            user_id = message.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user:
                await message.reply("❌ User not found. Please register first with /start")
                return
            
            # Get basic community overview
            overview = await analytics_engine.get_community_overview('7d', user['role'])
            
            if 'error' in overview:
                await message.reply("❌ Error loading statistics")
                return
            
            # Format quick stats
            stats_text = f"""
📈 **Community Stats (7 days)**

👥 **Users:** {overview.get('users', {}).get('total_users', 0)} total
📚 **Courses:** {overview.get('courses', {}).get('total_courses', 0)} total
✅ **Active Users:** {overview.get('users', {}).get('active_users', 0)}
📝 **Pending Reviews:** {overview.get('reviews', {}).get('pending_reviews', 0)}

📊 Use /dashboard for detailed analytics
            """
            
            # Add action buttons based on role
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Full Dashboard", callback_data="dashboard_open")],
                [InlineKeyboardButton("📋 Generate Report", callback_data="dashboard_report")]
            ])
            
            await message.reply(stats_text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Stats command error: {e}")
            await message.reply("❌ Error loading statistics. Please try again later.")
    
    async def handle_analytics_command(self, message: Message):
        """Handle /analytics command - detailed reports"""
        try:
            user_id = message.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user or not await rbac_manager.check_permission(user['anonymous_id'], 'view_analytics'):
                await message.reply("❌ Permission denied")
                return
            
            # Create analytics menu
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📊 7 Day Report", callback_data="analytics_7d"),
                    InlineKeyboardButton("📈 30 Day Report", callback_data="analytics_30d")
                ],
                [
                    InlineKeyboardButton("👥 User Analytics", callback_data="analytics_users"),
                    InlineKeyboardButton("📚 Course Analytics", callback_data="analytics_courses")
                ],
                [
                    InlineKeyboardButton("🔍 Volunteer Analytics", callback_data="analytics_volunteers"),
                    InlineKeyboardButton("⚙️ System Health", callback_data="analytics_system")
                ]
            ])
            
            await message.reply(
                "📊 **Analytics Center**\n\nChoose the type of report you'd like to generate:",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Analytics command error: {e}")
            await message.reply("❌ Error loading analytics menu")
    
    async def handle_dashboard_callback(self, callback: CallbackQuery):
        """Handle dashboard navigation callbacks"""
        try:
            action = callback.data.replace("dashboard_", "")
            user_id = callback.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user:
                await callback.answer("❌ User not found", show_alert=True)
                return
            
            if action == "open":
                # Redirect to dashboard command
                await callback.answer("Opening dashboard...")
                await self.handle_dashboard_command(callback.message)
                
            elif action == "report":
                await callback.answer("Generating report...")
                report = await analytics_engine.generate_report('community_health', '7d', user['role'])
                
                if 'error' in report:
                    await callback.answer("❌ Error generating report", show_alert=True)
                    return
                
                # Format and send report
                report_text = await self._format_analytics_report(report)
                await callback.message.reply(report_text)
                
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Dashboard callback error: {e}")
            await callback.answer("❌ Error processing request", show_alert=True)
    
    async def handle_widget_callback(self, callback: CallbackQuery):
        """Handle widget interaction callbacks"""
        try:
            widget_id = callback.data.replace("widget_", "")
            user_id = callback.from_user.id
            user = await anonymous_manager.get_user_by_telegram_id(user_id)
            
            if not user:
                await callback.answer("❌ User not found", show_alert=True)
                return
            
            # Get widget data
            widget_data = await community_dashboard.get_widget_data(widget_id, user['role'])
            
            if 'error' in widget_data:
                await callback.answer(f"❌ Error loading widget: {widget_data['error']}", show_alert=True)
                return
            
            # Format widget display
            widget_text = await self._format_widget_display(widget_data)
            
            # Create back button
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"widget_{widget_id}")],
                [InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="dashboard_open")]
            ])
            
            await callback.message.edit_text(widget_text, reply_markup=keyboard)
            await callback.answer("Widget updated")
            
        except Exception as e:
            logger.error(f"Widget callback error: {e}")
            await callback.answer("❌ Error loading widget", show_alert=True)
    
    async def _create_dashboard_menu(self, available_widgets: dict) -> InlineKeyboardMarkup:
        """Create dashboard widget menu"""
        buttons = []
        
        # Create rows of 2 buttons each
        row = []
        for widget_id, config in available_widgets.items():
            button = InlineKeyboardButton(
                f"📊 {config['name']}", 
                callback_data=f"widget_{widget_id}"
            )
            row.append(button)
            
            if len(row) == 2:
                buttons.append(row)
                row = []
        
        # Add remaining buttons
        if row:
            buttons.append(row)
        
        # Add utility buttons
        buttons.append([
            InlineKeyboardButton("📋 Generate Report", callback_data="dashboard_report"),
            InlineKeyboardButton("🔄 Refresh All", callback_data="dashboard_refresh")
        ])
        
        return InlineKeyboardMarkup(buttons)
    
    def _format_widget_list(self, available_widgets: dict) -> str:
        """Format available widgets list"""
        widget_lines = []
        for widget_id, config in available_widgets.items():
            widget_lines.append(f"• {config['name']}")
        return '\n'.join(widget_lines)
    
    async def _format_widget_display(self, widget_data: dict) -> str:
        """Format widget data for display"""
        widget_id = widget_data.get('widget_id', 'unknown')
        title = widget_data.get('title', 'Widget')
        data = widget_data.get('data', {})
        
        if widget_id == 'community_overview':
            return f"""
📊 **{title}**

👥 Total Users: {data.get('total_users', 0)}
📚 Total Courses: {data.get('total_courses', 0)}
✅ Active Users: {data.get('active_users', 0)}
📝 Pending Reviews: {data.get('pending_reviews', 0)}

🕐 Last Updated: {widget_data.get('last_updated', 'Unknown')}
            """
        
        elif widget_id == 'user_growth':
            return f"""
📈 **{title}**

🆕 New Users (30d): {data.get('new_users_30d', 0)}

**Role Distribution:**
{self._format_role_distribution(data.get('role_distribution', []))}

🕐 Last Updated: {widget_data.get('last_updated', 'Unknown')}
            """
        
        elif widget_id == 'review_queue':
            urgency = widget_data.get('urgency_level', 'normal')
            urgency_emoji = '🚨' if urgency == 'high' else '✅'
            
            return f"""
📝 **{title}** {urgency_emoji}

⏳ Pending Reviews: {data.get('pending_count', 0)}
⏱️ Average Review Time: {data.get('avg_review_time', 0):.1f} hours
✅ Completed Reviews: {data.get('completed_reviews', 0)}

🕐 Last Updated: {widget_data.get('last_updated', 'Unknown')}
            """
        
        else:
            # Generic widget display
            text_lines = [f"📊 **{title}**", ""]
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    text_lines.append(f"• {key.replace('_', ' ').title()}: {value}")
                elif isinstance(value, str):
                    text_lines.append(f"• {key.replace('_', ' ').title()}: {value}")
            
            text_lines.append(f"\n🕐 Last Updated: {widget_data.get('last_updated', 'Unknown')}")
            return '\n'.join(text_lines)
    
    def _format_role_distribution(self, role_dist: list) -> str:
        """Format role distribution data"""
        if not role_dist:
            return "No data available"
        
        lines = []
        for role_data in role_dist[:5]:  # Top 5 roles
            role = role_data.get('role', 'unknown').replace('_', ' ').title()
            count = role_data.get('count', 0)
            lines.append(f"• {role}: {count}")
        
        return '\n'.join(lines)
    
    async def _format_analytics_report(self, report: dict) -> str:
        """Format analytics report for display"""
        try:
            summary = report.get('summary', {})
            recommendations = report.get('recommendations', [])
            
            report_text = f"""
📊 **Analytics Report**
📅 Timeframe: {report.get('timeframe', 'Unknown')}
🕐 Generated: {report.get('generated_at', 'Unknown')}

**Summary:**
{chr(10).join([f'• {key.replace("_", " ").title()}: {value}' for key, value in summary.items()])}

**Recommendations:**
{chr(10).join([f'• {rec}' for rec in recommendations[:3]])}

📋 Full data available via dashboard widgets
            """
            
            return report_text
            
        except Exception as e:
            logger.error(f"Error formatting report: {e}")
            return "📊 **Analytics Report**\n\n❌ Error formatting report data"

def setup_community_stats_plugin(app: Client):
    """Setup community stats plugin"""
    return CommunityStatsPlugin(app)