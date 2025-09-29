import logging
import random
import asyncio
import datetime
import aiofiles
import aiofiles.os
import re
import uuid
import pytz
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply, Message, CallbackQuery
from pyrogram.errors import ChatAdminRequired, FloodWait, UserIsBlocked, InputUserDeactivated, MessageNotModified

from info import ADMINS, LOG_CHANNEL, SUPPORT_CHAT_ID, CUSTOM_FILE_CAPTION, OWNER_USERNAME, DEVELOPER_LINK, OWNER_LINK, PUBLIC_CHANNEL, TOKEN_VERIFICATION_ENABLED, PREMIUM_ENABLED, PICS
from core.supabase_client import supabase_client
from utils import temp, get_size, extract_user_id, extract_course_id, send_all_files, check_premium_user, check_token_required, get_shortlink
from Script import script
from core.roles import rbac_manager
from core.anonymity import anonymous_manager

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    logger.info(f"/start command received from user {message.from_user.id} in chat {message.chat.id}")
    if message.chat.type in ['group', 'supergroup']:
        # If command is used in a group
        buttons = [[
            InlineKeyboardButton('🚀 Start a Chat with Me', url=f'https://t.me/{temp.U_NAME}?start=group_start'),
            InlineKeyboardButton('🔍 Search Courses Here', switch_inline_query_current_chat='')
        ],[
            InlineKeyboardButton('💬 Support', url=f'https://t.me/{SUPPORT_CHAT_ID}'),
            InlineKeyboardButton('ℹ️ Help', callback_data='help_group') # Differentiate help for groups if needed
        ]]
        # Try to send with photo, fallback to text if photo fails
        try:
            if PICS and PICS[0] != 'https://example.com/chess_banner.jpg':
                await message.reply_photo(
                    photo=random.choice(PICS),
                    caption=script.START_TXT.format(message.from_user.mention if message.from_user else "Hey there"),
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                await message.reply_text(
                    text=script.START_TXT.format(message.from_user.mention if message.from_user else "Hey there"),
                    reply_markup=InlineKeyboardMarkup(buttons),
                    disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"Failed to send group start photo, falling back to text: {e}")
            await message.reply_text(
                text=script.START_TXT.format(message.from_user.mention if message.from_user else "Hey there"),
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=True
            )
        return

    # Add user to database if not exists using Supabase
    try:
        user_check = await supabase_client.execute_query(
            "SELECT id FROM users WHERE telegram_id = $1", message.from_user.id
        )
        if not user_check:
            await supabase_client.execute_command(
                "INSERT INTO users (telegram_id, first_name, anonymous_id) VALUES ($1, $2, uuid_generate_v4()) ON CONFLICT DO NOTHING",
                message.from_user.id, message.from_user.first_name
            )
            # Add timestamp to log message
            tz = pytz.timezone('Asia/Kolkata')
            now = datetime.datetime.now(tz)
            time_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
            if LOG_CHANNEL and LOG_CHANNEL != 0:
                await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(message.from_user.id, message.from_user.mention, time_str))
    except Exception as e:
        logger.error(f"Error adding user to database: {e}")

    # Command used in private chat
    if len(message.command) > 1:
        # Process deep link parameters
        param = message.command[1]
        
        if param.startswith('course_'):
            # Handle course download links
            course_id = param.split('_')[1]
            # Get course details from Supabase
            try:
                course_result = await supabase_client.execute_query(
                    "SELECT id, title, description, status FROM courses WHERE id = $1", course_id
                )
                if not course_result or course_result[0]['status'] != 'approved':
                    await message.reply_text(script.COURSE_NOT_FOUND)
                    return
                course = {"course_name": course_result[0]["title"], "description": course_result[0]["description"]}
            except Exception as e:
                logger.error(f"Error fetching course {course_id}: {e}")
                await message.reply_text("Error loading course details.")
                return
            
            # Check token verification
            if TOKEN_VERIFICATION_ENABLED:
                needs_verification = await check_token_required(message.from_user.id)
                if needs_verification and message.from_user.id not in ADMINS:
                    verification_text = (
                        "⚠️ **Token Verification Required** ⚠️\n\n"
                        "To access this course, you need to verify your token first.\n\n"
                        "Please use the command:\n"
                        "/token YOUR_TOKEN_HERE\n\n"
                        "If you don't have a token, please contact an administrator."
                    )
                    verification_buttons = [[
                        InlineKeyboardButton("Contact Admin", url=f"https://t.me/{OWNER_USERNAME}")
                    ]]
                    await message.reply_text(
                        verification_text,
                        reply_markup=InlineKeyboardMarkup(verification_buttons)
                    )
                    return
            
            # Check premium requirements if applicable
            if PREMIUM_ENABLED and course.get('premium_only', False):
                is_premium = await check_premium_user(message.from_user.id)
                if not is_premium and message.from_user.id not in ADMINS:
                    premium_text = (
                        "💎 **Premium Content** 💎\n\n"
                        f"The course '{course['course_name']}' is available exclusively for premium users.\n\n"
                        "Upgrade to premium to access this and other premium courses!\n\n"
                        "Use /premium to learn more about premium benefits."
                    )
                    premium_buttons = [[
                        InlineKeyboardButton("Get Premium", callback_data="premium_info")
                    ]]
                    await message.reply_text(
                        premium_text,
                        reply_markup=InlineKeyboardMarkup(premium_buttons)
                    )
                    return
                
            # Get course files from Supabase
            try:
                course_files = await supabase_client.execute_query(
                    "SELECT file_id, file_name, file_size FROM course_files WHERE course_id = $1 ORDER BY created_at",
                    course_id
                )
            except Exception as e:
                logger.error(f"Error fetching course files for {course_id}: {e}")
                course_files = []
            
            if not course_files:
                await message.reply_text("No files found for this course.")
                return
                
            # Send welcome message with course info
            welcome_text = f"<b>Fantastic! You're about to dive into the {course['course_name']} course!</b>\n\nI'll send over all the course materials in just a moment. Get ready to learn! 🚀"
            await message.reply_text(welcome_text)
            
            # Send all course files
            await send_all_files(client, message.chat.id, course_id, course_files)
            
            # Send a message after all files are sent
            complete_text = f"<b>✅ All files for {course['course_name']} have been sent!</b>\n\nI hope you find it valuable. Happy learning!\n\nReady for more? You can always browse other courses or check out our updates channel."
            buttons = [[
                InlineKeyboardButton('🔍 Browse More Courses', switch_inline_query_current_chat=''),
                InlineKeyboardButton('📢 Updates Channel', url=f"https://t.me/{PUBLIC_CHANNEL}")
            ]]
            await message.reply_text(complete_text, reply_markup=InlineKeyboardMarkup(buttons))
            return
        
        elif param == 'premium':
            # Handle premium information
            if PREMIUM_ENABLED:
                await message.reply_text(
                    "💎 **Premium Access** 💎\n\n"
                    "Upgrade to Premium to unlock these exclusive benefits:\n\n"
                    "• Access to premium-only courses\n"
                    "• Priority customer support\n"
                    "• Faster downloads\n"
                    "• No daily download limits\n\n"
                    "Use the /premium command to check your current status or learn more about our premium plans."
                )
                return
    
    # Regular start command
    buttons = [[
        InlineKeyboardButton('➕ Add to Group', url=f'http://t.me/{temp.U_NAME}?startgroup=true'),
        InlineKeyboardButton('🔍 Search', switch_inline_query_current_chat='')
    ]]
    
    # Add premium button if enabled
    if PREMIUM_ENABLED:
        buttons.append([InlineKeyboardButton('💎 Premium', callback_data='premium_info')])
        
    buttons.append([
        InlineKeyboardButton('ℹ️ Help', callback_data='help'),
        InlineKeyboardButton('📜 About', callback_data='about')
    ])
    
    # Choose a random banner image from PICS
    reply_markup = InlineKeyboardMarkup(buttons)
    
    # Try to send with photo, fallback to text if photo fails
    try:
        if PICS and PICS[0] != 'https://example.com/chess_banner.jpg':
            await message.reply_photo(
                photo=random.choice(PICS),
                caption=script.START_TXT.format(message.from_user.mention),
                reply_markup=reply_markup
            )
        else:
            # No valid photos configured, send text message
            await message.reply_text(
                text=script.START_TXT.format(message.from_user.mention),
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Failed to send photo, falling back to text: {e}")
        await message.reply_text(
            text=script.START_TXT.format(message.from_user.mention),
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

@Client.on_message(filters.command("help"))
async def help(client, message):
    buttons = [[
        InlineKeyboardButton('Course Help', callback_data='course_help'),
        InlineKeyboardButton('Search Help', callback_data='search_help')
    ]]
    
    # Add premium help if enabled
    if PREMIUM_ENABLED:
        buttons.append([InlineKeyboardButton('Premium Help', callback_data='premium_help')])
        
    # Add token verification help if enabled
    if TOKEN_VERIFICATION_ENABLED:
        buttons.append([InlineKeyboardButton('Token Help', callback_data='token_help')])
        
    buttons.append([
        InlineKeyboardButton('🔙 Back', callback_data='start'),
        InlineKeyboardButton('🔄 Close', callback_data='close_data')
    ])
    
    await message.reply_text(
        text=script.HELP_TXT.format(message.from_user.mention if message.from_user else "Dear user"),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("about"))
async def about(client, message):
    buttons = [[
        InlineKeyboardButton('🔙 Back', callback_data='help'),
        InlineKeyboardButton('🔄 Close', callback_data='close_data')
    ]]
    await message.reply_text(
        text=script.ABOUT_TXT.format(temp.U_NAME, temp.B_NAME, temp.U_NAME),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("stats") & filters.private)
@rbac_manager.require_permission('view_analytics')
async def stats(client, message):
    """Show bot statistics including file, user, and chat counts."""
    
    # Get user and chat counts from Supabase
    try:
        user_count_result = await supabase_client.execute_query("SELECT COUNT(*) as count FROM users")
        user_count = user_count_result[0]['count'] if user_count_result else 0
        
        chat_count_result = await supabase_client.execute_query("SELECT COUNT(DISTINCT telegram_id) as count FROM users")
        chat_count = chat_count_result[0]['count'] if chat_count_result else 0
        
        # Get course and file counts
        courses_count_result = await supabase_client.execute_query("SELECT COUNT(*) as count FROM courses WHERE status = 'approved'")
        total_courses = courses_count_result[0]['count'] if courses_count_result else 0
        
        # Get premium user count if enabled
        premium_count = 0
        if PREMIUM_ENABLED:
            premium_result = await supabase_client.execute_query("SELECT COUNT(*) as count FROM users WHERE role = 'premium'")
            premium_count = premium_result[0]['count'] if premium_result else 0
        
        # Calculate storage stats
        storage_result = await supabase_client.execute_query("SELECT SUM(file_size) as total_size FROM course_files")
        used_storage = storage_result[0]['total_size'] if storage_result and storage_result[0]['total_size'] else 0
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        user_count, chat_count, total_courses, premium_count, used_storage = 0, 0, 0, 0, 0
    free_storage = "Unlimited"  # MongoDB Atlas handles storage limits differently
    
    # Create stats message
    stats_text = script.STATUS_TXT.format(
        total_courses, 
        user_count, 
        chat_count, 
        get_size(used_storage), 
        free_storage
    )
    
    # Add premium stats if enabled
    if PREMIUM_ENABLED:
        stats_text += f"\n\n<b>Premium Users:</b> {premium_count}"
    
    await message.reply_text(
        stats_text,
        parse_mode='html'
    )

@Client.on_message(filters.command("course") & filters.private)
@rbac_manager.require_permission('manage_users')
async def old_course_command_alias(client, message):
    """Alias for /addcourse. Guides admin to use the new link-based system."""
    logger.info(f"User {message.from_user.id} used /course, redirecting to /addcourse info.")
    await message.reply_text(
        "Hi Admin! 👋\n\n" 
        "To add a new course, please use the `/addcourse` command. "
        "This will start the process of adding a course using **message links**.\n\n" 
        "Just type /addcourse and I'll guide you through it!"
    )

@Client.on_message(filters.command("broadcast") & filters.private)
@rbac_manager.require_permission('manage_users')
async def broadcast(client, message):
    """Broadcast a message to all users."""
    if len(message.command) < 2:
        return await message.reply_text("Please provide a message to broadcast.")
        
    # Get broadcast message
    broadcast_msg = message.text.split(None, 1)[1]
    
    # Send confirmation
    confirmation = await message.reply_text(
        text="📢 **Confirm Broadcast** 📢\n\nYou are about to send the following message to ALL users. This action cannot be undone.\n\n`{}`\n\nAre you absolutely sure you want to proceed?".format(broadcast_msg),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Send Now!", callback_data="broadcast_confirm"),
                InlineKeyboardButton("❌ No, Cancel", callback_data="broadcast_cancel")
            ]
        ])
    )
    
    # Store broadcast message for later use
    temp.BROADCAST_MSG = broadcast_msg

@Client.on_callback_query(filters.regex("^broadcast_"))
async def broadcast_callback(client, callback_query):
    """Handle broadcast confirmation callback."""
    action = callback_query.data.split("_")[1]
    
    if action == "cancel":
        await callback_query.message.edit_text("Broadcast cancelled.")
        return
        
    if action == "confirm":
        # Start broadcasting
        broadcast_msg = temp.BROADCAST_MSG
        await callback_query.message.edit_text("Broadcasting message...")
        
        async def send_msg(user_id):
            try:
                await client.send_message(user_id, broadcast_msg)
                return True
            except UserIsBlocked:
                await supabase_client.execute_command(
                    "UPDATE users SET is_banned = true, ban_reason = $2 WHERE telegram_id = $1",
                    user_id, "User blocked the bot"
                )
                return False
            except InputUserDeactivated:
                await supabase_client.execute_command(
                    "UPDATE users SET is_banned = true, ban_reason = $2 WHERE telegram_id = $1",
                    user_id, "User account deleted"
                )
                return False
            except Exception as e:
                logger.error(f"Error in broadcast: {e}")
                return False
        
        # Get all users
        # Get all users from Supabase
        try:
            users_result = await supabase_client.execute_query("SELECT telegram_id FROM users")
            users = [{"_id": row["telegram_id"]} for row in users_result]
        except Exception as e:
            logger.error(f"Error fetching users for broadcast: {e}")
            users = []
        success = 0
        failed = 0
        
        # Progress updates
        start_time = datetime.datetime.now()
        status_msg = await callback_query.message.edit_text(
            text=f"Broadcasting in progress...\n\nSuccess: {success}\nFailed: {failed}"
        )
        update_interval = 5  # Update status message every 5 seconds
        last_update_time = start_time
        
        for user in users:
            result = await send_msg(user["_id"])
            if result:
                success += 1
            else:
                failed += 1
                
            # Update status message periodically
            now = datetime.datetime.now()
            if (now - last_update_time).total_seconds() >= update_interval:
                await status_msg.edit_text(
                    text=f"Broadcasting in progress...\n\nSuccess: {success}\nFailed: {failed}"
                )
                last_update_time = now
                
        # Final update
        end_time = datetime.datetime.now()
        time_taken = (end_time - start_time).total_seconds()
        await status_msg.edit_text(
            text=f"✅ Broadcast Completed!\n\nSuccess: {success}\nFailed: {failed}\nTime taken: {time_taken:.2f} seconds"
        )

@Client.on_callback_query()
async def cb_handler(client, query):
    """Handle all callback queries."""
    data = query.data
    
    if data == "help":
        buttons = [[
            InlineKeyboardButton('Course Help', callback_data='course_help'),
            InlineKeyboardButton('Search Help', callback_data='search_help')
        ]]
        
        # Add premium help if enabled
        if PREMIUM_ENABLED:
            buttons.append([InlineKeyboardButton('Premium Help', callback_data='premium_help')])
            
        # Add token verification help if enabled
        if TOKEN_VERIFICATION_ENABLED:
            buttons.append([InlineKeyboardButton('Token Help', callback_data='token_help')])
            
        buttons.append([
            InlineKeyboardButton('🔙 Back', callback_data='start'),
            InlineKeyboardButton('🔄 Close', callback_data='close_data')
        ])
        
        await query.message.edit_text(
            text=script.HELP_TXT.format(query.from_user.mention),
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    elif data == "about":
        buttons = [[
            InlineKeyboardButton('🔙 Back', callback_data='help'),
            InlineKeyboardButton('🔄 Close', callback_data='close_data')
        ]]
        await query.message.edit_text(
            text=script.ABOUT_TXT.format(temp.U_NAME, temp.B_NAME, temp.U_NAME),
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    elif data == "start":
        buttons = [[
            InlineKeyboardButton('➕ Add to Group', url=f'http://t.me/{temp.U_NAME}?startgroup=true'),
            InlineKeyboardButton('🔍 Search', switch_inline_query_current_chat='')
        ]]
        
        # Add premium button if enabled
        if PREMIUM_ENABLED:
            buttons.append([InlineKeyboardButton('💎 Premium', callback_data='premium_info')])
            
        buttons.append([
            InlineKeyboardButton('ℹ️ Help', callback_data='help'),
            InlineKeyboardButton('📜 About', callback_data='about')
        ])
        
        await query.message.edit_text(
            text=script.START_TXT.format(query.from_user.mention),
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    elif data == "course_help":
        buttons = [[InlineKeyboardButton('🔙 Back', callback_data='help')]]
        await query.message.edit_text(
            text=script.COURSE_HELP,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    elif data == "search_help":
        buttons = [[InlineKeyboardButton('🔙 Back', callback_data='help')]]
        await query.message.edit_text(
            text=script.SEARCH_HELP,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    
    elif data == "premium_help":
        buttons = [[InlineKeyboardButton('🔙 Back', callback_data='help')]]
        await query.message.edit_text(
            text=script.PREMIUM_HELP,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    elif data == "token_help":
        buttons = [[InlineKeyboardButton('🔙 Back', callback_data='help')]]
        await query.message.edit_text(
            text=script.TOKEN_HELP,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        
    elif data == "premium_info":
        # Show premium information
        if PREMIUM_ENABLED:
            user_id = query.from_user.id
            try:
                user_result = await supabase_client.execute_query(
                    "SELECT role FROM users WHERE telegram_id = $1", user_id
                )
                user = {"is_premium": user_result[0]["role"] == "premium"} if user_result else {"is_premium": False}
            except Exception as e:
                logger.error(f"Error checking premium status: {e}")
                user = {"is_premium": False}
            is_premium = user and user.get("is_premium", False)
            
            if is_premium:
                expiry = user.get("premium_expiry")
                if expiry:
                    now = datetime.datetime.now()
                    if expiry > now:
                        time_left = expiry - now
                        days = time_left.days
                        hours, remainder = divmod(time_left.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        
                        premium_text = (
                            "**✨ You have an active Premium subscription!**\n\n"
                            f"Your premium status will expire in:\n"
                            f"**{days}** days, **{hours}** hours, and **{minutes}** minutes.\n\n"
                            "Benefits of Premium:\n"
                            "• Priority access to all courses\n"
                            "• Faster downloads\n"
                            "• No download limitations\n"
                            "• Advanced search options\n"
                            "• Premium support\n\n"
                            "Thank you for supporting us!"
                        )
                    else:
                        premium_text = (
                            "**❌ Your Premium subscription has expired.**\n\n"
                            "Would you like to renew it?\n\n"
                            "Contact the administrator to renew your premium subscription."
                        )
                else:
                    premium_text = (
                        "**✨ You have an unlimited Premium subscription!**\n\n"
                        "Benefits of Premium:\n"
                        "• Priority access to all courses\n"
                        "• Faster downloads\n"
                        "• No download limitations\n"
                        "• Advanced search options\n"
                        "• Premium support\n\n"
                        "Thank you for supporting us!"
                    )
            else:
                premium_text = (
                    "**💎 Premium Features**\n\n"
                    "Upgrade to Premium to unlock these benefits:\n\n"
                    "• Priority access to all courses\n"
                    "• Faster downloads\n"
                    "• No download limitations\n"
                    "• Advanced search options\n"
                    "• Premium support\n\n"
                    "Contact the administrator to purchase a premium subscription."
                )
            
            buttons = [[
                InlineKeyboardButton("Contact Admin", url=f"https://t.me/{OWNER_USERNAME}"),
                InlineKeyboardButton("🔙 Back", callback_data="start")
            ]]
            
            await query.message.edit_text(
                premium_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                disable_web_page_preview=True
            )
        else:
            # Premium is disabled
            await query.answer("Premium features are currently disabled.", show_alert=True)
            
    elif data == "close_data":
        await query.message.delete()
        
    else:
        await query.answer("Feature not implemented yet.", show_alert=True) 