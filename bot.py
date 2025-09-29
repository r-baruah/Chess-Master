import sys
import glob
import importlib
import importlib.util
import logging
import logging.config
import pytz
import asyncio
from pathlib import Path
from datetime import datetime
from os import environ

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from aiohttp import web

# Get logging configurations
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

from pyrogram import Client, idle
from core.supabase_client import supabase_client
from core.redis_state import redis_state
from core.anonymity import anonymous_manager
from info import *
from utils import temp

# Import disaster recovery service
from core.disaster_recovery_service import get_disaster_recovery_service

ppath = "plugins/*.py"
files = glob.glob(ppath)

loop = asyncio.get_event_loop()

# --- AIOHTTP Web Server Setup ---
async def handle_hello(request):
    """A simple handler to respond with Hello, World!."""
    logging.info("HTTP GET request received on /")
    return web.Response(text="Hello, World!")

async def start_web_server(port):
    app = web.Application()
    app.router.add_get("/", handle_hello)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    try:
        await site.start()
        logging.info(f"Web server started successfully on port {port}")
    except Exception as e:
        logging.error(f"Error starting web server: {e}")
        # Depending on the error, you might want to raise it or handle it
        # For now, just logging it.
# --- End AIOHTTP Web Server Setup ---

class Bot(Client):
    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5
        )
        self.disaster_recovery_service = None

    async def start(self):
        await super().start()
        me = await self.get_me()
        if me:
            logging.info(f"Pyrogram client initialized. Bot ID: {me.id}, Username: @{me.username}")
            temp.BOT = self
            temp.ME = me.id
            temp.U_NAME = me.username
            temp.B_NAME = me.first_name
        else:
            logging.error("Failed to get bot details (self.get_me() returned None). Check API_ID, API_HASH, BOT_TOKEN.")
            # You might want to stop the bot here or handle this more gracefully
            return # Prevent further execution if bot details are not fetched
        
        print(f"Bot Started as {me.first_name}")
        
        # Initialize core services
        try:
            await supabase_client.initialize()
            await redis_state.initialize()
            await anonymous_manager.initialize()
            logging.info("Core services initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize core services: {e}")
            return
        
        # Load banned users and chats from Supabase
        try:
            # For now, initialize empty lists - implement banned user loading later
            temp.BANNED_USERS = []
            temp.BANNED_CHATS = []
            logging.info("Banned users/chats loaded (placeholder)")
        except Exception as e:
            logging.warning(f"Failed to load banned users/chats: {e}")
            temp.BANNED_USERS = []
            temp.BANNED_CHATS = []
        
        # Load premium users if premium feature is enabled
        if PREMIUM_ENABLED:
            try:
                # For now, initialize empty list - implement premium user loading later
                temp.PREMIUM_USERS = []
                logging.info("Premium users loaded (placeholder)")
            except Exception as e:
                logging.warning(f"Failed to load premium users: {e}")
                temp.PREMIUM_USERS = []
        
        # Send startup message to log channel
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz)
        time_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        start_msg = f"<b>Chess Courses Bot Started!\n\nTime: {time_str}</b>"
        
        try:
            if LOG_CHANNEL and LOG_CHANNEL != 0:
                try:
                    # LOG_CHANNEL already contains the correct format (e.g., -1003163635353)
                    await self.send_message(chat_id=LOG_CHANNEL, text=start_msg)
                    logging.info(f"Startup message sent to LOG_CHANNEL: {LOG_CHANNEL}")
                except Exception as send_error:
                    logging.warning(f"Failed to send to LOG_CHANNEL {LOG_CHANNEL}: {send_error}")
                    # Try to get more info about the channel access
                    try:
                        chat_info = await self.get_chat(LOG_CHANNEL)
                        logging.info(f"Channel exists but send failed: {chat_info.title if hasattr(chat_info, 'title') else 'Unknown'}")
                    except Exception as info_error:
                        logging.warning(f"Cannot access LOG_CHANNEL {LOG_CHANNEL}: {info_error}")
                        logging.info("Check: 1) Bot is added to channel, 2) Bot has admin rights, 3) Channel ID is correct")
            else:
                logging.info("No valid LOG_CHANNEL configured, skipping startup message")
        except Exception as e:
            # Log the error but continue bot operation
            logging.error(f"Failed to send startup message: {e}. The bot will continue to run.")
            print(f"[Startup Log Info] Startup message skipped due to channel issues. Bot is continuing normally.")
        
        print("Loading plugins...")
        for name in files:
            with open(name) as a:
                patt = Path(a.name)
                plugin_name = patt.stem.replace(".py", "")
                plugins_dir = Path(f"plugins/{plugin_name}.py")
                import_path = f"plugins.{plugin_name}"
                
                spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
                load = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(load)
                
                sys.modules[f"plugins.{plugin_name}"] = load
                print(f"Successfully Imported {plugin_name}")
                
        print("Bot plugins loaded!")
        
        # Initialize disaster recovery system
        print("Initializing disaster recovery system...")
        try:
            self.disaster_recovery_service = await get_disaster_recovery_service()
            print("Disaster recovery system initialized successfully!")
            logging.info("Disaster recovery system operational")
        except Exception as e:
            print(f"Warning: Disaster recovery system failed to initialize: {e}")
            logging.warning(f"Disaster recovery system initialization failed: {e}")
            # Continue bot operation even if disaster recovery fails - this is acceptable for now
            self.disaster_recovery_service = None

    async def stop_custom(self, *args):
        logging.info("Executing custom stop actions...")
        
        # Shutdown disaster recovery system
        if self.disaster_recovery_service:
            try:
                print("Shutting down disaster recovery system...")
                await self.disaster_recovery_service.shutdown()
                print("Disaster recovery system shutdown complete")
            except Exception as e:
                logging.error(f"Error shutting down disaster recovery system: {e}")
        
        # Shutdown core services
        try:
            print("Shutting down core services...")
            await redis_state.close()
            await supabase_client.close()
            print("Core services shutdown complete")
        except Exception as e:
            logging.error(f"Error shutting down core services: {e}")
        
        await super().stop()
        logging.info("Pyrogram client stopped.")
        print("Bot Stopped Gracefully!")

bot = Bot()

async def main_start():
    web_server_port = int(environ.get("PORT", "8080"))
    # Start the web server as a background task
    web_task = asyncio.create_task(start_web_server(port=web_server_port))

    logging.info("Attempting to connect and start Pyrogram bot client...")
    try:
        await bot.start() # This starts the client and loads plugins as per __init__
        logging.info("Pyrogram bot client has started.")
        print("Pyrogram Bot and Web Server should be running.")
        await idle() # This keeps the bot running and processing updates
    except Exception as e:
        logging.error(f"An error occurred during bot startup or idle: {e}", exc_info=True)
    finally:
        logging.info("Bot idle() has been exited or an error occurred. Stopping bot...")
        await bot.stop_custom()
        if not web_task.done():
            web_task.cancel()
            try:
                await web_task
            except asyncio.CancelledError:
                logging.info("Web server task cancelled.")
        logging.info("Application shutdown complete.")

if __name__ == "__main__":
    try:
        loop.run_until_complete(main_start())
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received, initiating graceful shutdown...")
    # The finally block in main_start() will handle the shutdown
    print("Application has been shut down from __main__.") 