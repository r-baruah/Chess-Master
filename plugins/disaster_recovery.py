"""
Disaster Recovery Admin Plugin
Telegram admin interface for disaster recovery management
"""
import asyncio
import json
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS
from utils import temp
from core.disaster_recovery_service import get_disaster_recovery_service
import logging

logger = logging.getLogger(__name__)

# Admin command: Disaster Recovery Status
@Client.on_message(filters.command("drstatus") & filters.user(ADMINS))
async def disaster_recovery_status(client: Client, message: Message):
    """Get disaster recovery system status"""
    try:
        status_msg = await message.reply("🔍 Getting disaster recovery status...")
        
        service = await get_disaster_recovery_service()
        status = await service.get_system_status()
        
        # Format status message
        overall_status = status.get('overall_status', 'unknown').upper()
        status_emoji = {
            'HEALTHY': '✅',
            'DEGRADED': '⚠️',
            'CRITICAL': '🚨',
            'UNKNOWN': '❓'
        }.get(overall_status, '❓')
        
        text = f"""
🛡️ **DISASTER RECOVERY STATUS**

**Overall Status:** {status_emoji} {overall_status}
**Last Check:** {status.get('last_check', 'N/A')}
**Service Active:** {'✅' if status.get('service_initialized') else '❌'}
**Background Tasks:** {status.get('background_tasks_running', 0)} running

"""
        
        # Add component details
        components = status.get('components', {})
        
        if 'token_manager' in components:
            tokens = components['token_manager']
            active = tokens.get('active_token', {})
            text += f"""**🤖 Bot Tokens:**
• Active: @{active.get('username', 'unknown')} ({active.get('status', 'unknown')})
• Errors: {active.get('error_count', 0)}
• Backups: {tokens.get('backup_tokens_healthy', 0)}/{tokens.get('backup_tokens_count', 0)} healthy

"""
        
        if 'channel_permissions' in components:
            channels = components['channel_permissions']
            text += f"""**📺 Channel Permissions:**
• Total Channels: {channels.get('total_channels', 0)}
• Verified: {channels.get('verified_channels', 0)}
• Failed: {channels.get('failed_channels', 0)}

"""
        
        # Add action buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Health Check", callback_data="dr_health_check"),
                InlineKeyboardButton("📊 Metrics", callback_data="dr_metrics")
            ],
            [
                InlineKeyboardButton("🔄 Bot Failover", callback_data="dr_failover"),
                InlineKeyboardButton("🔧 Sync Permissions", callback_data="dr_sync_perms")
            ],
            [
                InlineKeyboardButton("📦 Create Backup", callback_data="dr_create_backup"),
                InlineKeyboardButton("📜 Recent Events", callback_data="dr_events")
            ]
        ])
        
        await status_msg.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in disaster recovery status: {e}")
        await message.reply(f"❌ Error getting disaster recovery status: {e}")

# Health check callback
@Client.on_callback_query(filters.regex("^dr_health_check$"))
async def health_check_callback(client: Client, callback_query: CallbackQuery):
    """Perform system health check"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        await callback_query.answer("🔍 Performing health check...")
        await callback_query.message.edit("🔍 Performing comprehensive health check...")
        
        service = await get_disaster_recovery_service()
        result = await service.perform_system_health_check()
        
        status_emoji = {
            'healthy': '✅',
            'degraded': '⚠️',
            'critical': '🚨',
            'unknown': '❓'
        }.get(result.get('status', 'unknown').lower(), '❓')
        
        text = f"""
🔍 **HEALTH CHECK RESULTS**

**Status:** {status_emoji} {result.get('status', 'unknown').upper()}
**Time:** {result.get('timestamp', 'N/A')}
**Message:** {result.get('message', 'N/A')}

"""
        
        if result.get('components'):
            text += "**Component Status:**\\n"
            for component, status in result['components'].items():
                comp_emoji = '✅' if status == 'healthy' else '⚠️' if status == 'degraded' else '❌'
                text += f"• {component}: {comp_emoji} {status}\\n"
            
        # Back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Status", callback_data="dr_back_status")]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in health check callback: {e}")
        await callback_query.message.edit(f"❌ Health check failed: {e}")

# Metrics callback
@Client.on_callback_query(filters.regex("^dr_metrics$"))
async def metrics_callback(client: Client, callback_query: CallbackQuery):
    """Show system metrics"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        await callback_query.answer("📊 Getting metrics...")
        await callback_query.message.edit("📊 Loading system metrics...")
        
        service = await get_disaster_recovery_service()
        result = await service.get_performance_metrics()
        
        if result['status'] != 'success':
            await callback_query.message.edit(f"❌ Failed to get metrics: {result.get('message', 'Unknown error')}")
            return
            
        metrics = result['metrics']
        text = "📊 **SYSTEM METRICS**\\n\\n"
        
        # Availability metrics
        if 'availability_24h' in metrics:
            avail = metrics['availability_24h']
            text += f"""**24-Hour Availability:**
• Healthy: {avail['healthy_percentage']:.1f}%
• Degraded: {avail['degraded_percentage']:.1f}%
• Critical: {avail['critical_percentage']:.1f}%

"""
        
        # Failover stats
        if 'failover_stats_7d' in metrics:
            failover = metrics['failover_stats_7d']
            text += f"""**7-Day Failover Stats:**
• Total: {failover.get('total_failovers', 0)}
• Successful: {failover.get('successful_failovers', 0)}
"""
            if failover.get('avg_recovery_time'):
                text += f"• Avg Recovery: {float(failover['avg_recovery_time']):.1f}s\\n"
            text += "\\n"
        
        # Token health
        if 'token_health' in metrics:
            tokens = metrics['token_health']
            text += f"""**Token Health:**
• Total: {tokens.get('total_tokens', 0)}
• Healthy: {tokens.get('healthy_tokens', 0)}
• Degraded: {tokens.get('degraded_tokens', 0)}
• Failed: {tokens.get('failed_tokens', 0)}
"""
        
        # Back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Status", callback_data="dr_back_status")]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in metrics callback: {e}")
        await callback_query.message.edit(f"❌ Failed to get metrics: {e}")

# Bot failover callback
@Client.on_callback_query(filters.regex("^dr_failover$"))
async def failover_callback(client: Client, callback_query: CallbackQuery):
    """Trigger bot failover"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        # Confirmation step
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm Failover", callback_data="dr_failover_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="dr_back_status")
            ]
        ])
        
        text = """
⚠️ **BOT TOKEN FAILOVER**

This will switch to a backup bot token and restart services.

**Warning:** This may cause a brief service interruption.

Are you sure you want to proceed?
"""
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in failover callback: {e}")
        await callback_query.message.edit(f"❌ Error: {e}")

# Failover confirmation callback
@Client.on_callback_query(filters.regex("^dr_failover_confirm$"))
async def failover_confirm_callback(client: Client, callback_query: CallbackQuery):
    """Confirm and execute failover"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        await callback_query.answer("🔄 Triggering failover...")
        await callback_query.message.edit("🔄 Executing bot token failover...")
        
        service = await get_disaster_recovery_service()
        result = await service.trigger_bot_failover()
        
        if result['status'] == 'success':
            text = "✅ **FAILOVER SUCCESSFUL**\\n\\nBot token failover completed successfully!"
        else:
            text = f"❌ **FAILOVER FAILED**\\n\\n{result.get('message', 'Unknown error')}"
            
        # Back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Status", callback_data="dr_back_status")]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in failover confirm callback: {e}")
        await callback_query.message.edit(f"❌ Failover failed: {e}")

# Sync permissions callback
@Client.on_callback_query(filters.regex("^dr_sync_perms$"))
async def sync_permissions_callback(client: Client, callback_query: CallbackQuery):
    """Synchronize channel permissions"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        await callback_query.answer("🔧 Syncing permissions...")
        await callback_query.message.edit("🔧 Synchronizing channel permissions...")
        
        service = await get_disaster_recovery_service()
        result = await service.sync_channel_permissions()
        
        if result['status'] == 'success':
            sync_results = result['sync_results']
            text = f"""
✅ **PERMISSIONS SYNCHRONIZED**

**Results:**
• Tokens Processed: {sync_results['total_tokens']}
• Successful: {sync_results['successful_tokens']}
• Failed: {sync_results['failed_tokens']}

Sync completed at {sync_results['sync_time']}
"""
        else:
            text = f"❌ **SYNC FAILED**\\n\\n{result.get('message', 'Unknown error')}"
            
        # Back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Status", callback_data="dr_back_status")]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in sync permissions callback: {e}")
        await callback_query.message.edit(f"❌ Permission sync failed: {e}")

# Create backup callback
@Client.on_callback_query(filters.regex("^dr_create_backup$"))
async def create_backup_callback(client: Client, callback_query: CallbackQuery):
    """Create recovery package"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        await callback_query.answer("📦 Creating backup...")
        await callback_query.message.edit("📦 Creating disaster recovery package...")
        
        service = await get_disaster_recovery_service()
        result = await service.create_recovery_package()
        
        if result['status'] == 'success':
            package = result['package']
            text = f"""
📦 **RECOVERY PACKAGE CREATED**

**Package ID:** `{package['package_id']}`
**Created:** {package['timestamp']}
**Checksum:** `{package['checksum'][:16]}...`

Package has been saved to backup locations.
"""
        else:
            text = f"❌ **BACKUP FAILED**\\n\\n{result.get('message', 'Unknown error')}"
            
        # Back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Status", callback_data="dr_back_status")]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in create backup callback: {e}")
        await callback_query.message.edit(f"❌ Backup creation failed: {e}")

# Recent events callback
@Client.on_callback_query(filters.regex("^dr_events$"))
async def events_callback(client: Client, callback_query: CallbackQuery):
    """Show recent events"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    try:
        await callback_query.answer("📜 Getting events...")
        await callback_query.message.edit("📜 Loading recent events...")
        
        service = await get_disaster_recovery_service()
        result = await service.get_recent_events(24)  # Last 24 hours
        
        if result['status'] != 'success':
            await callback_query.message.edit(f"❌ Failed to get events: {result.get('message', 'Unknown error')}")
            return
            
        events = result['events']
        text = "📜 **RECENT EVENTS (24H)**\\n\\n"
        
        # Recent notifications
        notifications = events.get('recent_notifications', [])[:5]  # Show last 5
        if notifications:
            text += "**Recent Notifications:**\\n"
            for notif in notifications:
                type_emoji = {
                    'critical_system_failure': '🚨',
                    'failover_success': '✅',
                    'system_degradation': '⚠️',
                    'recovery_success': '✅',
                    'recovery_failure': '❌'
                }.get(notif.get('type'), 'ℹ️')
                
                timestamp = notif.get('timestamp', 'N/A')
                if timestamp != 'N/A':
                    # Format timestamp
                    try:
                        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp = dt.strftime('%H:%M')
                    except:
                        pass
                        
                message = notif.get('message', 'No message')[:50]
                if len(notif.get('message', '')) > 50:
                    message += '...'
                    
                text += f"• {type_emoji} {timestamp} - {message}\\n"
                
        # Failover events
        failover_events = events.get('failover_events', [])[:3]  # Show last 3
        if failover_events:
            text += "\\n**Failover Events:**\\n"
            for event in failover_events:
                status_icon = '✅' if event['success'] else '❌'
                event_time = event.get('event_time', 'N/A')
                if event_time != 'N/A':
                    try:
                        dt = datetime.fromisoformat(str(event_time).replace('Z', '+00:00'))
                        event_time = dt.strftime('%H:%M')
                    except:
                        pass
                        
                text += f"• {status_icon} {event_time} - {event['event_type']}\\n"
                
        if not notifications and not failover_events:
            text += "No recent events found."
            
        # Back button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Status", callback_data="dr_back_status")]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in events callback: {e}")
        await callback_query.message.edit(f"❌ Failed to get events: {e}")

# Back to status callback
@Client.on_callback_query(filters.regex("^dr_back_status$"))
async def back_status_callback(client: Client, callback_query: CallbackQuery):
    """Go back to main status"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    # Re-run the status command
    await disaster_recovery_status_callback(callback_query)

async def disaster_recovery_status_callback(callback_query: CallbackQuery):
    """Helper function to refresh status"""
    try:
        await callback_query.message.edit("🔍 Refreshing disaster recovery status...")
        
        service = await get_disaster_recovery_service()
        status = await service.get_system_status()
        
        # Format status message (same as command)
        overall_status = status.get('overall_status', 'unknown').upper()
        status_emoji = {
            'HEALTHY': '✅',
            'DEGRADED': '⚠️',
            'CRITICAL': '🚨',
            'UNKNOWN': '❓'
        }.get(overall_status, '❓')
        
        text = f"""
🛡️ **DISASTER RECOVERY STATUS**

**Overall Status:** {status_emoji} {overall_status}
**Last Check:** {status.get('last_check', 'N/A')}
**Service Active:** {'✅' if status.get('service_initialized') else '❌'}
**Background Tasks:** {status.get('background_tasks_running', 0)} running

"""
        
        # Add component details
        components = status.get('components', {})
        
        if 'token_manager' in components:
            tokens = components['token_manager']
            active = tokens.get('active_token', {})
            text += f"""**🤖 Bot Tokens:**
• Active: @{active.get('username', 'unknown')} ({active.get('status', 'unknown')})
• Errors: {active.get('error_count', 0)}
• Backups: {tokens.get('backup_tokens_healthy', 0)}/{tokens.get('backup_tokens_count', 0)} healthy

"""
        
        if 'channel_permissions' in components:
            channels = components['channel_permissions']
            text += f"""**📺 Channel Permissions:**
• Total Channels: {channels.get('total_channels', 0)}
• Verified: {channels.get('verified_channels', 0)}
• Failed: {channels.get('failed_channels', 0)}

"""
        
        # Add action buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Health Check", callback_data="dr_health_check"),
                InlineKeyboardButton("📊 Metrics", callback_data="dr_metrics")
            ],
            [
                InlineKeyboardButton("🔄 Bot Failover", callback_data="dr_failover"),
                InlineKeyboardButton("🔧 Sync Permissions", callback_data="dr_sync_perms")
            ],
            [
                InlineKeyboardButton("📦 Create Backup", callback_data="dr_create_backup"),
                InlineKeyboardButton("📜 Recent Events", callback_data="dr_events")
            ]
        ])
        
        await callback_query.message.edit(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error refreshing status: {e}")
        await callback_query.message.edit(f"❌ Error refreshing status: {e}")

# Emergency recovery command (requires confirmation)
@Client.on_message(filters.command("emergency_recovery") & filters.user(ADMINS))
async def emergency_recovery_command(client: Client, message: Message):
    """Emergency recovery command"""
    try:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚨 CONFIRM EMERGENCY", callback_data="emergency_recovery_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="emergency_recovery_cancel")
            ]
        ])
        
        text = """
🚨 **EMERGENCY RECOVERY MODE**

⚠️ **WARNING:** This will attempt to recover the system from the latest backup.

**This action will:**
• Stop current services
• Restore from latest recovery package
• Restart all components
• May cause service interruption

**Only use in case of system failure!**

Are you absolutely sure?
"""
        
        await message.reply(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error in emergency recovery command: {e}")
        await message.reply(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("^emergency_recovery_"))
async def emergency_recovery_callbacks(client: Client, callback_query: CallbackQuery):
    """Handle emergency recovery callbacks"""
    if callback_query.from_user.id not in ADMINS:
        await callback_query.answer("❌ Unauthorized", show_alert=True)
        return
        
    if callback_query.data == "emergency_recovery_cancel":
        await callback_query.message.edit("❌ Emergency recovery cancelled.")
        return
        
    if callback_query.data == "emergency_recovery_confirm":
        try:
            await callback_query.answer("🚨 Initiating emergency recovery...")
            await callback_query.message.edit("🚨 **INITIATING EMERGENCY RECOVERY**\\n\\nThis may take several minutes...")
            
            # Note: In a real scenario, you'd load the latest recovery package
            # For now, just show that the system is available
            await callback_query.message.edit("""
🚨 **EMERGENCY RECOVERY NOTICE**

Emergency recovery system is operational but requires a recovery package file.

Use the `/drstatus` command to:
1. Create a current backup package
2. Monitor system health
3. Perform targeted recovery actions

For full emergency recovery, use the CLI tool:
`python disaster_recovery_cli.py restore-backup <package_file>`
""")
            
        except Exception as e:
            logger.error(f"Error in emergency recovery: {e}")
            await callback_query.message.edit(f"❌ Emergency recovery failed: {e}")

# Help command for disaster recovery
@Client.on_message(filters.command("drhelp") & filters.user(ADMINS))
async def disaster_recovery_help(client: Client, message: Message):
    """Disaster recovery help"""
    text = """
🛡️ **DISASTER RECOVERY HELP**

**Available Commands:**
• `/drstatus` - Get system status with controls
• `/emergency_recovery` - Emergency system recovery
• `/drhelp` - Show this help

**CLI Tool:**
Use `python disaster_recovery_cli.py` for advanced operations:

• `status` - Get detailed status
• `health-check` - Perform health check
• `create-backup` - Create recovery package
• `restore-backup <file>` - Restore from package
• `failover` - Trigger bot failover
• `sync-permissions` - Sync channel permissions
• `events` - Show recent events
• `metrics` - Show performance metrics

**System Components:**
🤖 **Multi-Bot Tokens** - Automatic failover
📺 **Channel Permissions** - Cross-token sync
🔍 **Health Monitoring** - Continuous checks
📦 **Backup & Recovery** - Emergency restore
🚨 **Failover System** - Automatic recovery

For detailed information, check the documentation.
"""
    
    await message.reply(text)