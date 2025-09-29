import asyncio
import logging
import re
import uuid
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    InlineQueryResultArticle, InputTextMessageContent,
    InlineQueryResultPhoto
)
from pyrogram.errors import FloodWait, UserIsBlocked

from typing import Any, Dict, List, Optional

from core.course_metadata_manager import CourseMetadataManager
from core.anonymous_file_forwarder import AnonymousFileForwarder
from core.redis_state import redis_state
from core.supabase_client import supabase_client
from utils import temp, get_size, get_shortlink
from info import ADMINS, CUSTOM_FILE_CAPTION, SHORTENER_ENABLED
from Script import script

logger = logging.getLogger(__name__)

# Lazy singletons reused across handlers
metadata_manager: CourseMetadataManager | None = None
file_forwarder: AnonymousFileForwarder | None = None

async def _ensure_services(client: Client) -> None:
    """Ensure inline plugin service dependencies are initialized."""
    global metadata_manager, file_forwarder

    if metadata_manager is None:
        metadata_manager = CourseMetadataManager(supabase_client, redis_state)

    if file_forwarder is None:
        file_forwarder = AnonymousFileForwarder(client)


async def _search_courses(query: str, limit: int = 20) -> Dict[str, Any]:
    if metadata_manager is None:
        raise RuntimeError("Metadata manager not initialized")

    filters: Dict[str, Any] = {}
    result = await metadata_manager.search_courses_advanced(query, filters, limit=limit)
    if not result["success"]:
        logger.error("Inline search failed: %s", result.get("message"))
        return {"results": [], "total_results": 0}

    courses = result.get("results", [])
    total_results = result.get("total_results", len(courses))

    normalized_courses = []
    for item in courses:
        normalized_courses.append({
            "id": item.get("course_id"),
            "title": item.get("title") or item.get("course_name"),
            "description": item.get("description"),
            "file_count": item.get("file_count", 0),
            "total_size": item.get("total_size", 0),
            "banner_link": item.get("banner_link"),
            "metadata": item
        })

    return {
        "results": normalized_courses,
        "total_results": total_results
    }


async def _get_course_details(course_id: str) -> Optional[Dict[str, Any]]:
    if metadata_manager is None:
        raise RuntimeError("Metadata manager not initialized")

    metadata = await metadata_manager.get_course_metadata(course_id)
    if not metadata.get("success"):
        return None

    return metadata.get("metadata")


async def _get_course_assets(course_id: str) -> Dict[str, Any]:
    if metadata_manager is None:
        raise RuntimeError("Metadata manager not initialized")

    files = await metadata_manager.get_course_files(course_id)
    metadata = await metadata_manager.get_course_metadata(course_id)

    return {
        "metadata": metadata.get("metadata") if metadata.get("success") else None,
        "files": files or []
    }

@Client.on_inline_query()
async def inline_search(client, query):
    """Handle inline queries for course search."""
    # Get search query
    search_text = query.query.strip()
    
    # If query is empty, suggest how to use inline search
    if not search_text:
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    title="Search for Chess Courses",
                    description="Type a course name to search",
                    input_message_content=InputTextMessageContent(
                        "**How to use inline search:**\n"
                        "Type @yourbotname followed by your search query to find chess courses.\n\n"
                        "Example: @yourbotname opening strategies"
                    ),
                    thumb_url="https://i.imgur.com/ede5DtC.png"
                )
            ],
            cache_time=5
        )
        return
    
    # Ensure services initialized
    await _ensure_services(client)

    # Search for courses
    search_payload = await _search_courses(search_text, limit=20)
    courses = search_payload["results"]
    
    if not courses:
        # No results found
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    title="No courses found",
                    description=f"No chess courses matching '{search_text}'",
                    input_message_content=InputTextMessageContent(
                        f"No chess courses found for query: **{search_text}**"
                    ),
                    thumb_url="https://i.imgur.com/ede5DtC.png"
                )
            ],
            cache_time=5
        )
        return
    
    # Convert courses to inline results
    results = []
    for course in courses:
        metadata = course.get('metadata', {})
        course_id = course['id']
        course_name = metadata.get('title') or course.get('title') or 'Course'
        file_count = metadata.get('file_count') or course.get('file_count', 0)
        total_size = metadata.get('total_size_bytes') or course.get('total_size', 0)
        banner_link = metadata.get('banner_link') or course.get('banner_link')
        
        # Create deep link for course
        bot_username = (await client.get_me()).username
        deep_link = f"https://t.me/{bot_username}?start=course_{course_id}"
        
        # Use URL shortener if enabled
        if SHORTENER_ENABLED:
            deep_link = await get_shortlink(deep_link)
        
        # Create description and message content
        description = f"{file_count} files • {get_size(total_size)}"
        message_content = InputTextMessageContent(
            f"**📚 {course_name}**\n\n"
            f"Files: {file_count}\n"
            f"Total Size: {get_size(total_size)}\n\n"
            f"Use the button below to access this course."
        )
        
        # Create reply markup with download button
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ Download Course", url=deep_link)]
        ])
        
        # If course has a banner, use photo result
        if banner_link:
            try:
                # Add as photo result if banner exists
                results.append(
                    InlineQueryResultPhoto(
                        photo_url=banner_link,
                        thumb_url=banner_link,
                        title=course_name,
                        description=description,
                        caption=f"**📚 {course_name}**\n\n"
                                f"Files: {file_count}\n"
                                f"Total Size: {get_size(total_size)}",
                        reply_markup=reply_markup
                    )
                )
            except Exception as e:
                # Fallback to article if there's an issue with the photo
                logger.error(f"Error creating photo result: {e}")
                results.append(
                    InlineQueryResultArticle(
                        title=course_name,
                        description=description,
                        input_message_content=message_content,
                        reply_markup=reply_markup,
                        thumb_url="https://i.imgur.com/ede5DtC.png"
                    )
                )
        else:
            # Use article result for courses without banner
            results.append(
                InlineQueryResultArticle(
                    title=course_name,
                    description=description,
                    input_message_content=message_content,
                    reply_markup=reply_markup,
                    thumb_url="https://i.imgur.com/ede5DtC.png"
                )
            )
    
    # Answer the query with results
    await query.answer(
        results=results,
        cache_time=300  # Cache for 5 minutes
    )

@Client.on_message(filters.command("course") & filters.regex(r"_([0-9a-f-]+)$"))
async def get_course_from_deeplink(client, message):
    """Handle deep links for courses."""
    course_id = message.command[1].split("_")[1]
    
    # Get course details
    # Ensure services initialized
    await _ensure_services(client)

    # Get course assets
    assets = await _get_course_assets(course_id)
    metadata = assets.get("metadata") or {}
    files = assets.get("files", [])

    if not metadata:
        return await message.reply_text("Course not found or has been removed.")

    if not files:
        return await message.reply_text("No files found for this course.")
    
    # Create file list message
    text = f"**📚 {metadata.get('title', 'Course')}**\n\n"
    text += f"Total Files: {len(files)}\n"
    total_size = sum(file.get('file_size', 0) for file in files)
    text += f"Total Size: {get_size(total_size)}\n\n"
    text += "Select a file to download:"
    
    # Create buttons for files
    buttons = []
    for file in files:
        buttons.append([
            InlineKeyboardButton(
                text=f"{file.get('file_name', 'Course File')} ({get_size(file.get('file_size', 0))})",
                callback_data=f"file_{file.get('id') or file.get('file_id')}"
            )
        ])
    
    # Add a button to send all files
    buttons.append([
        InlineKeyboardButton(
            text="📦 Download All Files",
            callback_data=f"sendall_{course_id}"
        )
    ])
    
    # If course has banner, send as photo
    banner_link = metadata.get('banner_link')
    if banner_link:
        try:
            await client.send_photo(
                chat_id=message.chat.id,
                photo=banner_link,
                caption=text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception:
            # Fallback to text message if photo fails
            await message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
    else:
        # Send as text message
        await message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

@Client.on_callback_query(filters.regex(r"^file_"))
async def send_file_callback(client, callback_query):
    """Send a specific file from a course."""
    file_id = callback_query.data.split("_")[1]
    
    try:
        # Send the file using cached media
        await callback_query.answer("Sending file...")
        await client.send_cached_media(
            chat_id=callback_query.message.chat.id,
            file_id=file_id,
            caption=CUSTOM_FILE_CAPTION
        )
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await callback_query.answer("Failed to send file. Please try again later.", show_alert=True) 