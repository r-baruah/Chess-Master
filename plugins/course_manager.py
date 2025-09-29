import logging
import asyncio
import time
import random
import uuid
import re
from datetime import datetime
import pyrogram
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified

from info import ADMINS, CUSTOM_FILE_CAPTION, PUBLIC_CHANNEL
from core.supabase_client import supabase_client
from utils import temp, get_size, get_file_id, clean_text
from Script import script
from core.multi_channel_manager import MultiChannelManager
from core.anonymous_file_forwarder import AnonymousFileForwarder
from core.supabase_client import supabase_client
from core.volunteer_system import volunteer_manager

logger = logging.getLogger(__name__)

# Initialize multi-channel components
multi_channel_manager = None
anonymous_forwarder = None

def initialize_multi_channel_components(bot_client):
    """Initialize multi-channel components when bot is ready"""
    global multi_channel_manager, anonymous_forwarder
    multi_channel_manager = MultiChannelManager(bot_client)
    anonymous_forwarder = AnonymousFileForwarder(bot_client)

# States for course creation conversation
WAITING_COURSE_NAME = 1
WAITING_COURSE_LINKS = 2 # Changed from 3 to 2, as WAITING_COURSE_FILES is removed
WAITING_BANNER = 3       # Changed from 4 to 3
CONFIRM_COURSE = 4       # Changed from 5 to 4

# Store conversation states for users
user_states = {}

@Client.on_message(filters.command(["addcourse", "addcourselinks"]) & filters.private & filters.user(ADMINS))
async def add_course_command(client, message):
    """Start course creation process using message links."""
    await message.reply_text(
        "Okay, let's add a new course! 📚\n\n"
        "**First, what is the name of this course?**\n"
        "Please send the full course name as your next message.",
        reply_markup=ForceReply(True)
    )
    user_states[message.from_user.id] = WAITING_COURSE_NAME
    # Initialize course data, ensuring it's clean for a new course
    temp.CURRENT_COURSES[message.from_user.id] = {
        "course_name": None, # Will be set in the next step
        "files": [],
        "links": [],
        "banner": None,
        "using_links": True # Default to new method
    }

@Client.on_message(filters.private & filters.reply & filters.user(ADMINS))
async def handle_course_replies(client, message):
    """Handle replies during course creation conversation."""
    user_id = message.from_user.id
    
    if user_id not in user_states or user_id not in temp.CURRENT_COURSES:
        # If user is not in a state or no course data, ignore or guide them
        # For now, just returning to avoid errors if user replies randomly
        return
        
    state = user_states[user_id]
    
    if state == WAITING_COURSE_NAME:
        course_name = clean_text(message.text)
        if not course_name:
            return await message.reply_text("Hmm, that doesn't look like a valid course name. Please try again.")
            
        temp.CURRENT_COURSES[user_id]["course_name"] = course_name
        
        await message.reply_text(
            f"Great! The course will be named: **'{course_name}'**.\n\n"
            "Now, please send me the **Telegram message links** for all the files in this course. "
            "You can send one link per message, or multiple links in a single message (each on a new line).\n\n"
            "**Format:** `https://t.me/c/channel_id/message_id` or `https://t.me/channel_username/message_id`\n\n"
            "Type /done when you've sent all the links.",
            disable_web_page_preview=True
        )
        user_states[user_id] = WAITING_COURSE_LINKS
            
    elif state == WAITING_COURSE_LINKS:
        if not message.text:
            return await message.reply_text("That doesn't look like a message link. Please send valid links or type /done.")

        # Regex to find all Telegram message links in the message text
        link_pattern = r"https?://t\.me/(?:c/)?(\S+)/(\d+)" # Made channel part more general
        found_links = re.findall(link_pattern, message.text)
        
        if not found_links:
            return await message.reply_text(
                "I couldn't find any valid Telegram message links in your message. Please use the correct format:\n"
                "`https://t.me/c/channel_id/message_id` or `https://t.me/channel_username/message_id`\n\n"
                "Or type /done if you've finished adding links.",
                disable_web_page_preview=True
            )
            
        added_count = 0
        for channel_identifier, message_id_str in found_links:
            try:
                message_id = int(message_id_str)
                # If channel_identifier is numeric (private channel ID) and doesn't start with -100, add it
                # Otherwise, it's a public channel username or already formatted private ID
                if channel_identifier.isdigit() and not channel_identifier.startswith("-100"):
                    actual_channel_id = f"-100{channel_identifier}"
                else:
                    actual_channel_id = channel_identifier
                    
                if "links" not in temp.CURRENT_COURSES[user_id]: # Should have been initialized
                    temp.CURRENT_COURSES[user_id]["links"] = []
                    
                temp.CURRENT_COURSES[user_id]["links"].append({
                    "channel_id": actual_channel_id,
                    "message_id": message_id
                })
                added_count += 1
            except ValueError:
                await message.reply_text(f"Warning: Skipping invalid message ID format in link: .../{channel_identifier}/{message_id_str}")
                continue
        
        if added_count > 0:
            total_links = len(temp.CURRENT_COURSES[user_id].get("links", []))
            await message.reply_text(
                f"Added {added_count} new message link(s). ✅\n"
                f"Total links for this course so far: **{total_links}**\n\n"
                "Keep sending links or type /done when finished."
            )
        # If no valid links were added from this message, but some were found by regex, user might be confused.
        # The earlier message "I couldn't find any valid Telegram message links..." handles the case where regex finds nothing.
        
    elif state == WAITING_BANNER:
        if message.photo:
            photo_id = message.photo.file_id
            temp.CURRENT_COURSES[user_id]["banner"] = photo_id
            await message.reply_text("Banner image received! 👍")
            await confirm_course(client, message, user_id) # Proceed to confirmation
            user_states[user_id] = CONFIRM_COURSE
        else:
            await message.reply_text("That's not a photo. Please send a photo for the banner, or type /skip to use a default.")
            
    elif state == CONFIRM_COURSE:
        response = message.text.lower()
        
        if response in ["yes", "y", "confirm", "3", "confirm and publish"]:
            await publish_course(client, message, user_id)
            if user_id in temp.CURRENT_COURSES: del temp.CURRENT_COURSES[user_id]
            if user_id in user_states: del user_states[user_id]
        elif response in ["no", "n", "cancel", "4"]:
            await message.reply_text("Course creation cancelled. ❌")
            if user_id in temp.CURRENT_COURSES: del temp.CURRENT_COURSES[user_id]
            if user_id in user_states: del user_states[user_id]
        elif response in ["1", "add banner", "banner"]:
            await message.reply_text(
                "Okay, please send a photo to use as the course banner.",
                reply_markup=ForceReply(True)
            )
            user_states[user_id] = WAITING_BANNER
        elif response in ["2", "modify name", "edit name"]:
            await message.reply_text(
                "What should the new course name be?",
                reply_markup=ForceReply(True)
            )
            # Revert to WAITING_COURSE_NAME but keep current data
            # The 'using_links': True flag will be preserved.
            temp.CURRENT_COURSES[user_id]['course_name'] = None # Clear to allow re-entry
            user_states[user_id] = WAITING_COURSE_NAME
        else:
            await message.reply_text(
                "Please choose one of the options from the confirmation message (e.g., type 'yes' or '1')."
            )

@Client.on_message(filters.command("done") & filters.private & filters.user(ADMINS))
async def done_collecting_links(client, message):
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id] != WAITING_COURSE_LINKS:
        return await message.reply_text("It seems you're not currently adding course links. Use /addcourse to start.")
        
    if user_id not in temp.CURRENT_COURSES or not temp.CURRENT_COURSES[user_id].get("links"):
        return await message.reply_text("You haven't added any message links yet. Please send some links or use /cancel if you wish to stop.")
        
    course_data = temp.CURRENT_COURSES[user_id]
    
    processing_msg = await message.reply_text("Processing message links... This might take a moment. ⏳")
    
    fetched_files_info = []
    success_count = 0
    failed_count = 0
    
    for link_data in course_data["links"]:
        try:
            # Ensure channel_id is correctly formatted (integer for private, string for public)
            chat_id_to_fetch = link_data["channel_id"]
            if isinstance(chat_id_to_fetch, str) and chat_id_to_fetch.startswith("-100") and chat_id_to_fetch[4:].isdigit():
                 chat_id_to_fetch = int(chat_id_to_fetch)
            elif isinstance(chat_id_to_fetch, str) and chat_id_to_fetch.isdigit(): # A public channel ID as string
                 chat_id_to_fetch = int(chat_id_to_fetch)


            fetched_message = await client.get_messages(
                chat_id=chat_id_to_fetch, 
                message_ids=link_data["message_id"]
            )
            
            if fetched_message and fetched_message.media:
                file_obj, file_id = get_file_id(fetched_message)
                if file_id:
                    fetched_files_info.append({
                        "file_id": file_id,
                        "file_name": getattr(file_obj, "file_name", f"File from {link_data['message_id']}"),
                        "file_size": getattr(file_obj, "file_size", 0),
                        "caption": fetched_message.caption, # Or use CUSTOM_FILE_CAPTION later
                        "message_id": fetched_message.id # Original message_id from source channel
                    })
                    success_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Could not get file_id from fetched message: chat={chat_id_to_fetch}, msg_id={link_data['message_id']}")
            else:
                failed_count += 1
                logger.warning(f"Fetched message has no media or message not found: chat={chat_id_to_fetch}, msg_id={link_data['message_id']}")
        except FloodWait as e:
            logger.warning(f"FloodWait: Sleeping for {e.x} seconds while fetching links.")
            await processing_msg.edit_text(f"Hit a small delay, waiting for {e.x}s. Processing will resume...")
            await asyncio.sleep(e.x)
            # Optionally, retry this specific link or just count as failed for now
            failed_count +=1 # Count as failed for now
        except Exception as e:
            logger.error(f"Error fetching message (chat_id: {link_data['channel_id']}, message_id: {link_data['message_id']}): {e}")
            failed_count += 1
            continue
            
    await processing_msg.delete() # Delete the "Processing..." message

    if success_count == 0:
        return await message.reply_text(
            "Oh no! I couldn't fetch any valid files from the links you provided. 🙁\n"
            "Please check the links and ensure the bot has access to the channel(s).\n"
            "You can try adding links again or /cancel."
        )
        
    temp.CURRENT_COURSES[user_id]["files"] = fetched_files_info # Store successfully fetched file details
    
    await message.reply_text(
        f"Great! I successfully processed **{success_count}** file(s) from the links. 🎉"
        + (f" ({failed_count} link(s) could not be processed.)" if failed_count > 0 else "")
        + "\n\nNext, would you like to add a **banner image** for this course? This image will be shown in announcements.\n\n"
        "Please send the image now, or type /skip to use a default banner.",
        disable_web_page_preview=True
    )
    user_states[user_id] = WAITING_BANNER

@Client.on_message(filters.command("skip") & filters.private & filters.user(ADMINS))
async def skip_banner(client, message):
    user_id = message.from_user.id
    
    if user_id not in user_states or user_states[user_id] != WAITING_BANNER:
        # User is not in the correct state to skip a banner
        return await message.reply_text("It doesn't look like you're at the banner step. Use /addcourse to start a new course.")
        
    if user_id in temp.CURRENT_COURSES:
        temp.CURRENT_COURSES[user_id]["banner"] = None
        await message.reply_text("Okay, we'll use a default banner. 👍")
        await confirm_course(client, message, user_id)
        user_states[user_id] = CONFIRM_COURSE
    else:
        # This case should ideally not be reached if state is WAITING_BANNER
        await message.reply_text("Something went wrong, no course data found. Please start over with /addcourse.")

@Client.on_callback_query(filters.regex(r"^course_action_"))
async def course_action_callback(client, callback_query):
    action = callback_query.data.split("_")[2] # e.g. "confirm", "cancel"
    user_id = callback_query.from_user.id
    message = callback_query.message # The message where the inline keyboard is

    if user_id not in temp.CURRENT_COURSES or user_id not in user_states:
        return await callback_query.answer("This action is no longer valid or has expired.", show_alert=True)

    if action == "cancel":
        if user_id in temp.CURRENT_COURSES: del temp.CURRENT_COURSES[user_id]
        if user_id in user_states: del user_states[user_id]
        await message.edit_text("Course creation cancelled. ❌")
        
    elif action == "confirm":
        await message.edit_text("Publishing course, please wait... 🚀")
        await publish_course(client, message, user_id) # Pass message for replies
        if user_id in temp.CURRENT_COURSES: del temp.CURRENT_COURSES[user_id]
        if user_id in user_states: del user_states[user_id]
            
    elif action == "banner":
        await message.reply_text( # Reply to the original message, not edit
            "Okay, please send a photo to use as the course banner.",
            reply_markup=ForceReply(True)
        )
        user_states[user_id] = WAITING_BANNER
        await callback_query.answer() # Answer the callback
        
    elif action == "edit_name":
        await message.reply_text( # Reply to the original message
            "What should the new course name be?",
            reply_markup=ForceReply(True)
        )
        temp.CURRENT_COURSES[user_id]['course_name'] = None # Clear to allow re-entry
        user_states[user_id] = WAITING_COURSE_NAME
        await callback_query.answer() # Answer the callback

async def confirm_course(client, message_or_callback_query, user_id):
    """Show course summary and ask for confirmation."""
    if user_id not in temp.CURRENT_COURSES:
        reply_target = message_or_callback_query.message if isinstance(message_or_callback_query, CallbackQuery) else message_or_callback_query
        return await reply_target.reply_text("No course data found. Please start over with /addcourse.")
        
    course_data = temp.CURRENT_COURSES[user_id]
    
    course_name = course_data.get("course_name", "Not Set Yet")
    # Files are now fetched info, not raw links
    file_count = len(course_data.get("files", [])) 
    total_size = sum(file_info.get("file_size", 0) for file_info in course_data.get("files", []))
    
    has_banner = course_data.get("banner") is not None
    
    text = script.CHECK_COURSE.format(
        course_name=course_name,
        file_count=file_count
    )
    text += f"\n<b>Total Size:</b> {get_size(total_size)}"
    text += f"\n<b>Banner Image:</b> {'✅ Added' if has_banner else '❌ Not Added (will use default)'}"
    text += "\n\n**Is this correct?**"
    
    buttons = [
        [
            InlineKeyboardButton("🖼️ Change Banner" if has_banner else "🖼️ Add Banner", callback_data="course_action_banner"),
            InlineKeyboardButton("✏️ Edit Name", callback_data="course_action_edit_name")
        ],
        [
            InlineKeyboardButton("✅ Confirm & Publish", callback_data="course_action_confirm"),
            InlineKeyboardButton("❌ Cancel Process", callback_data="course_action_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    reply_target = message_or_callback_query.message if isinstance(message_or_callback_query, CallbackQuery) else message_or_callback_query
    if isinstance(message_or_callback_query, CallbackQuery) and message_or_callback_query.message.text != text : # Avoid MessageNotModified
         await reply_target.edit_text(text, reply_markup=reply_markup)
    else:
         await reply_target.reply_text(text, reply_markup=reply_markup)


async def publish_course(client, message_or_callback_query, user_id):
    """Publish the course to the database and announcement channel with multi-channel storage."""
    reply_target = message_or_callback_query.message if isinstance(message_or_callback_query, CallbackQuery) else message_or_callback_query

    if user_id not in temp.CURRENT_COURSES or not temp.CURRENT_COURSES[user_id].get("files"):
        return await reply_target.reply_text("Course data is incomplete (no files found). Please start over with /addcourse.")
        
    course_data = temp.CURRENT_COURSES[user_id]
    course_id = str(uuid.uuid4()) # Generate unique course ID
    
    # First save course to database
    course_doc = {
        "id": course_id,  # Use UUID as primary key
        "title": course_data.get("course_name", "Untitled Course"),
        "description": f"Course with {len(course_data.get('files', []))} files",
        "banner_link": course_data.get("banner"), # This is a file_id
        "status": "pending_review",  # Default status for new courses
        "contributor_id": None  # Will be set based on user's anonymous ID
    }
    
    # Get user's anonymous ID for attribution
    try:
        user_result = await supabase_client.execute_query(
            "SELECT id FROM users WHERE telegram_id = $1", user_id
        )
        if user_result:
            course_doc["contributor_id"] = user_result[0]["id"]
    except Exception as e:
        logger.warning(f"Could not get user's anonymous ID: {e}")
    
    # Save course to Supabase
    try:
        course_result = await supabase_client.execute_command(
            """
            INSERT INTO courses (id, title, description, banner_link, contributor_id, status)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            course_doc["id"], course_doc["title"], course_doc["description"],
            course_doc["banner_link"], course_doc["contributor_id"], course_doc["status"]
        )
        
        if not course_result:
            return await reply_target.reply_text("Failed to save course to database. Please try again or contact support. ⚠️")
            
    except Exception as e:
        logger.error(f"Failed to save course: {e}")
        return await reply_target.reply_text("Failed to save course to database. Please try again or contact support. ⚠️")
    
    # Process and store each file with multi-channel redundancy
    processing_msg = await reply_target.reply_text("📤 Uploading files to multi-channel storage... This may take a moment.")
    
    successful_files = 0
    failed_files = 0
    
    for i, file_info in enumerate(course_data.get("files", [])):
        try:
            # Create course file record
            file_record = {
                "course_id": course_id,
                "file_name": file_info["file_name"],
                "file_type": file_info.get("file_type", "unknown"),
                "file_size": file_info["file_size"],
                "message_link": f"temp://processing/{file_info['file_id']}"  # Temporary link
            }
            
            # Save file record to get UUID
            file_result = await supabase_client.execute_command(
                """
                INSERT INTO course_files (id, course_id, file_name, file_type, file_size, message_link)
                VALUES (uuid_generate_v4(), $1, $2, $3, $4, $5)
                RETURNING id
                """,
                file_record["course_id"], file_record["file_name"], 
                file_record["file_type"], file_record["file_size"], file_record["message_link"]
            )
            
            course_file_id = file_result[0]["id"]
            
            # If we have multi-channel manager, store file across channels
            if multi_channel_manager:
                try:
                    # Prepare file data for multi-channel storage
                    file_data = {
                        "course_file_id": course_file_id,
                        "file_path": file_info["file_id"],  # This would be the original file
                        "file_size": file_info["file_size"],
                        "file_name": file_info["file_name"]
                    }
                    
                    # Store across multiple channels
                    storage_results = await multi_channel_manager.store_file_multi_channel(file_data, course_id)
                    
                    if storage_results:
                        # Update course file with primary message link
                        primary_link = storage_results[0].message_link
                        await supabase_client.execute_command(
                            "UPDATE course_files SET message_link = $1 WHERE id = $2",
                            primary_link, course_file_id
                        )
                        successful_files += 1
                        logger.info(f"File {file_info['file_name']} stored in {len(storage_results)} channels")
                    else:
                        raise Exception("No channels available for storage")
                        
                except Exception as e:
                    logger.error(f"Multi-channel storage failed for {file_info['file_name']}: {e}")
                    failed_files += 1
                    # Keep the file record but mark it as failed storage
                    await supabase_client.execute_command(
                        "UPDATE course_files SET message_link = $1 WHERE id = $2",
                        f"error://storage_failed/{file_info['file_id']}", course_file_id
                    )
            else:
                # Fallback to legacy storage method
                await save_course_file({
                    "course_id": course_id,
                    "file_id": file_info["file_id"],
                    "file_name": file_info["file_name"],
                    "file_size": file_info["file_size"],
                    "caption": file_info.get("caption") or CUSTOM_FILE_CAPTION.format(
                        file_name=file_info["file_name"], 
                        course_name=course_doc["title"]
                    ),
                    "file_order": i + 1 
                })
                successful_files += 1
            
            # Update progress
            if (i + 1) % 3 == 0:  # Update every 3 files
                try:
                    await processing_msg.edit_text(
                        f"📤 Processing files: {i + 1}/{len(course_data.get('files', []))} complete..."
                    )
                except MessageNotModified:
                    pass
            
        except Exception as e:
            logger.error(f"Failed to process file {file_info.get('file_name', 'unknown')}: {e}")
            failed_files += 1
    
    await processing_msg.delete()
    
    # Report results
    result_text = f"✅ Course **{course_doc['title']}** submitted successfully!\n\n"
    result_text += f"📊 **Upload Summary:**\n"
    result_text += f"• Successful: {successful_files} files\n"
    
    if failed_files > 0:
        result_text += f"• Failed: {failed_files} files\n"
        result_text += f"⚠️ Some files may need manual re-upload.\n\n"
    
    if multi_channel_manager:
        result_text += "🔒 **Multi-Channel Storage:** Files stored with redundancy across backup channels\n"
        result_text += "🌐 **Anonymous Access:** Files can be accessed anonymously by users\n\n"
    
    # Assign to volunteer reviewer for quality control
    try:
        priority_level = 2 if failed_files == 0 else 1  # Higher priority if no file failures
        reviewer_id = await volunteer_manager.assign_course_to_reviewer(course_id, priority_level)
        
        if reviewer_id:
            result_text += f"🎯 **Quality Control:** Assigned to volunteer reviewer for approval\n"
            result_text += f"📋 **Status:** Pending Review (Priority: {'High' if priority_level > 1 else 'Normal'})\n"
        else:
            result_text += f"⚠️ **No reviewers available** - Course queued for manual review\n"
            result_text += f"📋 **Status:** Awaiting Reviewer Assignment\n"
    except Exception as e:
        logger.error(f"Failed to assign course to reviewer: {e}")
        result_text += f"📋 **Status:** Submitted - Manual Review Required\n"
    
    result_text += f"🆔 Course ID: `{course_id}`\n"
    
    await reply_target.reply_text(result_text)
    
    # Announce course if successful
    if successful_files > 0:
        await announce_course(client, course_id, course_data)
    
async def announce_course(client, course_id, course_data): # Added client here
    if not PUBLIC_CHANNEL:
        logger.warning("PUBLIC_CHANNEL not set. Cannot announce course.")
        return
        
    course_name = course_data.get("course_name", "Untitled Course")
    banner_id = course_data.get("banner") # This is a file_id
    
    caption = script.COURSE_ADDED.format(course_name=course_name)
    buttons = [[
        InlineKeyboardButton("⬇️ Download Now", url=f"https://t.me/{temp.U_NAME}?start=course_{course_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(buttons)
    
    try:
        if banner_id:
            await client.send_photo(
                chat_id=PUBLIC_CHANNEL,
                photo=banner_id, # Send the photo using its file_id
                caption=caption,
                reply_markup=reply_markup
            )
        else:
            # Consider a default placeholder image if no banner is provided
            # For now, just sending text
            await client.send_message(
                chat_id=PUBLIC_CHANNEL,
                text=caption,
                reply_markup=reply_markup,
                disable_web_page_preview=True # Good for messages without explicit images
            )
        logger.info(f"Course '{course_name}' announced successfully to {PUBLIC_CHANNEL}.")
    except Exception as e:
        logger.error(f"Error announcing course '{course_name}' to {PUBLIC_CHANNEL}: {e}")
        # Notify admins about the failure
        for admin_id in ADMINS:
            try:
                await client.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ **Announcement Failed** ⚠️\nCould not announce course '{course_name}' to public channel {PUBLIC_CHANNEL}.\nError: {e}"
                )
            except Exception as admin_notify_err:
                logger.error(f"Failed to notify admin {admin_id} about announcement error: {admin_notify_err}")

@Client.on_message(filters.command("search") & filters.text & filters.incoming)
async def search_courses_command(client, message):
    """Search for courses using text query."""
    if len(message.command) < 2:
        return await message.reply_text("Please provide a search query. Example: /search chess openings")
    
    query = " ".join(message.command[1:])
    
    # Search courses using Supabase
    try:
        search_query = """
            SELECT c.id as course_id, c.title as course_name, 
                   COUNT(cf.id) as file_count
            FROM courses c
            LEFT JOIN course_files cf ON c.id = cf.course_id
            WHERE c.status = 'approved' 
              AND (c.title ILIKE $1 OR c.description ILIKE $1 OR c.category ILIKE $1)
            GROUP BY c.id, c.title
            ORDER BY c.updated_at DESC
            LIMIT 20
        """
        courses = await supabase_client.execute_query(search_query, f"%{query}%")
        total = len(courses)
    except Exception as e:
        logger.error(f"Search error: {e}")
        courses, total = [], 0
    
    if not courses:
        return await message.reply_text(f"No courses found for '{query}'")
    
    text = f"**🔍 Search Results for '{query}'**\n\n"
    
    for i, course in enumerate(courses, 1):
        course_id = course['course_id']
        course_name = course['course_name']
        file_count = course['file_count']
        text += f"{i}. **{course_name}** - {file_count} files\n"
        
        # Add inline button for this course
        if i == len(courses): # Only add total at the end
            text += f"\nFound {total} results."
    
    # Create buttons for each course
    buttons = []
    for course in courses:
        buttons.append([
            InlineKeyboardButton(
                text=f"📚 {course['course_name']}",
                callback_data=f"course_{course['course_id']}"
            )
        ])
    
    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex(r"^course_([0-9a-f-]+)$")) # Ensure this regex is specific enough
async def course_callback(client, callback_query):
    """Handle course selection callback from search or other lists."""
    course_id = callback_query.data.split("_")[1]
    
    # Get course details
    try:
        course_query = "SELECT id, title, description FROM courses WHERE id = $1 AND status = 'approved'"
        course_result = await supabase_client.execute_query(course_query, course_id)
        if not course_result:
            return await callback_query.answer("Sorry, this course could not be found. It might have been removed.", show_alert=True)
        course = {"course_name": course_result[0]["title"], "description": course_result[0]["description"]}
        
        # Get course files
        files_query = """
            SELECT file_id, file_name, file_size, message_link 
            FROM course_files 
            WHERE course_id = $1 
            ORDER BY created_at
        """
        files = await supabase_client.execute_query(files_query, course_id)
    except Exception as e:
        logger.error(f"Error loading course {course_id}: {e}")
        return await callback_query.answer("Error loading course details.", show_alert=True)
    if not files:
        return await callback_query.answer("This course currently has no files. Please check back later.", show_alert=True)
    
    text = f"**📚 {course['course_name']}**\n\n"
    text += f"Total Files: {len(files)}\n"
    text += f"Total Size: {get_size(sum(f.get('file_size', 0) for f in files))}\n\n"
    text += "You can download individual files or all at once:"
    
    buttons = []
    # Limited to 5 individual files to prevent overly long messages, can be paginated later if needed
    for file_doc in files[:5]: 
        buttons.append([
            InlineKeyboardButton(
                text=f"{file_doc['file_name']} ({get_size(file_doc.get('file_size', 0))})",
                callback_data=f"sendfile_{file_doc.get('file_id', file_doc.get('message_link', ''))}" # Use file_id or message_link
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="📦 Download All Files",
            callback_data=f"sendall_{course_id}"
        )
    ])
    buttons.append([InlineKeyboardButton("🔙 Back to Search (Not Impl.)", callback_data="search_again_placeholder")])


    try:
        await callback_query.message.edit_text( # Edit if possible
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except MessageNotModified:
        pass
    except Exception as e: # Fallback to reply if edit fails for some reason
        logger.error(f"Error editing message for course callback: {e}")
        await callback_query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    await callback_query.answer()

@Client.on_callback_query(filters.regex(r"^sendfile_")) # Enhanced callback for single file with anonymous forwarding
async def send_single_file_callback(client, callback_query):
    """Send single file using anonymous forwarding system"""
    file_identifier = callback_query.data.split("_", 1)[1]
    user_id = callback_query.from_user.id
    
    try:
        await callback_query.answer("Preparing file for anonymous delivery...", show_alert=False)
        
        # Use anonymous forwarder if available
        if anonymous_forwarder:
            try:
                # Check rate limiting
                rate_status = await anonymous_forwarder.get_user_rate_limit_status(user_id)
                if rate_status['requests_remaining'] <= 0:
                    return await callback_query.answer(
                        f"Rate limit exceeded. Try again in {rate_status.get('reset_time_seconds', 'a few')} seconds.", 
                        show_alert=True
                    )
                
                # Forward file anonymously
                forwarded_message = await anonymous_forwarder.forward_file_anonymously(user_id, file_identifier)
                
                if forwarded_message:
                    await callback_query.answer("✅ File delivered anonymously!", show_alert=False)
                    
                    # Send rate limit info
                    updated_status = await anonymous_forwarder.get_user_rate_limit_status(user_id)
                    await client.send_message(
                        user_id,
                        f"📊 **Rate Limit Status**\n"
                        f"Remaining requests: {updated_status['requests_remaining']}\n"
                        f"Reset in: {updated_status.get('reset_time_seconds', 'Unknown')} seconds",
                        reply_to_message_id=forwarded_message.id
                    )
                else:
                    await callback_query.answer("Failed to deliver file. Please try again.", show_alert=True)
                    
            except Exception as e:
                logger.error(f"Anonymous forwarding failed: {e}")
                await callback_query.answer(f"File delivery failed: {str(e)}", show_alert=True)
                
        else:
            # Fallback to direct sending (legacy method)
            await client.send_cached_media(
                chat_id=callback_query.message.chat.id,
                file_id=file_identifier,
            )
            await callback_query.answer("File sent (legacy mode)", show_alert=False)
            
    except Exception as e:
        logger.error(f"Error in send_single_file_callback: {e}")
        await callback_query.answer(f"Could not send the file: {e}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^sendall_([0-9a-f-]+)$"))
async def send_all_files_callback(client, callback_query):
    """Send all course files using anonymous forwarding system"""
    course_id = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    try:
        # Check if course exists
        course_result = await supabase_client.execute_query(
            "SELECT title FROM courses WHERE id = $1 AND status = 'approved'",
            course_id
        )
        
        if not course_result:
            return await callback_query.answer("Course not found or not approved.", show_alert=True)
        
        course_title = course_result[0]['title']
        
        # Use anonymous forwarder if available
        if anonymous_forwarder:
            try:
                # Check rate limiting for course downloads (higher limit)
                rate_status = await anonymous_forwarder.get_user_rate_limit_status(user_id)
                if rate_status['requests_remaining'] < 5:  # Need at least 5 requests for course download
                    return await callback_query.answer(
                        f"Insufficient rate limit for course download. Try again in {rate_status.get('reset_time_seconds', 'a few')} seconds.", 
                        show_alert=True
                    )
                
                await callback_query.answer("Preparing anonymous course delivery...", show_alert=False)
                
                # Forward all course files anonymously
                forwarded_messages = await anonymous_forwarder.forward_file_by_course_id(user_id, course_id)
                
                if forwarded_messages:
                    # Send completion summary
                    updated_status = await anonymous_forwarder.get_user_rate_limit_status(user_id)
                    await client.send_message(
                        user_id,
                        f"🎉 **Course Download Complete**\n"
                        f"Course: **{course_title}**\n"
                        f"Files delivered: {len(forwarded_messages) - 1}\n\n"  # -1 for summary message
                        f"📊 **Rate Limit Status**\n"
                        f"Remaining requests: {updated_status['requests_remaining']}\n"
                        f"Reset in: {updated_status.get('reset_time_seconds', 'Unknown')} seconds\n\n"
                        f"🔒 All files delivered with **complete anonymity** - source channels protected."
                    )
                else:
                    await callback_query.message.reply_text("❌ No files could be delivered from this course.")
                    
            except Exception as e:
                logger.error(f"Anonymous course forwarding failed: {e}")
                await callback_query.message.reply_text(f"❌ Course delivery failed: {str(e)}")
                
        else:
            # Fallback to legacy method using Supabase
            try:
                course_query = "SELECT title FROM courses WHERE id = $1 AND status = 'approved'"
                course_result = await supabase_client.execute_query(course_query, course_id)
                if not course_result:
                    return await callback_query.answer("Course not found.", show_alert=True)
                course = {"course_name": course_result[0]["title"]}
                
                files_query = "SELECT file_id, file_name, file_size FROM course_files WHERE course_id = $1"
                files = await supabase_client.execute_query(files_query, course_id)
            except Exception as e:
                logger.error(f"Error loading course for fallback: {e}")
                return await callback_query.answer("Error loading course.", show_alert=True)
            if not files:
                return await callback_query.answer("No files found for this course.", show_alert=True)
            
            await callback_query.answer("Sending all files (legacy mode)...", show_alert=False)
            status_message = await callback_query.message.reply_text(
                f"Preparing to send {len(files)} files for '{course['course_name']}'..."
            )
            
            sent_count = 0
            failed_send_count = 0
            for file_doc in files:
                try:
                    caption_to_use = file_doc.get("caption", CUSTOM_FILE_CAPTION.format(
                        file_name=file_doc["file_name"], 
                        course_name=course["course_name"]
                    ))
                    await client.send_cached_media(
                        chat_id=callback_query.message.chat.id,
                        file_id=file_doc['file_id'],
                        caption=caption_to_use 
                    )
                    sent_count += 1
                    if sent_count % 5 == 0 and sent_count < len(files):
                        try:
                            await status_message.edit_text(
                                f"Sent {sent_count}/{len(files)} files for '{course['course_name']}'..."
                            )
                        except MessageNotModified:
                            pass
                    await asyncio.sleep(1)
                except FloodWait as e:
                    logger.warning(f"FloodWait: Sleeping for {e.x} seconds during send_all for course {course_id}.")
                    await status_message.edit_text(f"Delay encountered, waiting {e.x}s. Will resume sending...")
                    await asyncio.sleep(e.x)
                    failed_send_count += 1
                except Exception as e:
                    logger.error(f"Error sending file {file_doc['file_name']} for course {course_id}: {e}")
                    failed_send_count += 1
            
            final_status_text = f"✅ Successfully sent {sent_count} files for '{course['course_name']}'."
            if failed_send_count > 0:
                final_status_text += f" ({failed_send_count} file(s) failed to send.)"
            
            await status_message.edit_text(final_status_text)
            
    except Exception as e:
        logger.error(f"Error in send_all_files_callback: {e}")
        await callback_query.answer(f"Could not process course download: {e}", show_alert=True)