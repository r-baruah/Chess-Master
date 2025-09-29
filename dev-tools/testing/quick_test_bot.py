#!/usr/bin/env python3
"""
Quick test script to start and test the bot locally
"""
import asyncio
import logging
import sys
from datetime import datetime

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Setup logging to avoid Unicode issues
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

async def test_bot_startup():
    """Test bot startup and basic functionality"""
    try:
        print("=== ChessMaster Bot Quick Test ===")
        print(f"Test started at: {datetime.now()}")
        
        # Import the bot
        from bot import Bot
        
        # Create bot instance
        bot = Bot()
        print("[OK] Bot instance created successfully")
        
        # Start the bot
        print("Starting bot...")
        await bot.start()
        print("[OK] Bot started successfully!")
        
        # Get bot info
        me = await bot.get_me()
        if me:
            print(f"[OK] Bot info: @{me.username} ({me.first_name})")
            print(f"[OK] Bot ID: {me.id}")
        
        # Test for 5 seconds
        print("Testing bot for 5 seconds...")
        await asyncio.sleep(5)
        
        # Stop the bot
        print("Stopping bot...")
        await bot.stop_custom()
        print("[OK] Bot stopped successfully!")
        
        print("=== Test completed successfully! ===")
        return True
        
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")
        logging.error(f"Test error: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    print("Starting ChessMaster bot quick test...")
    
    try:
        success = asyncio.run(test_bot_startup())
        if success:
            print("\n[SUCCESS] Bot is working correctly!")
            print("You can now run: python bot.py")
        else:
            print("\n[FAILED] Bot has issues that need to be fixed")
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"\nTest crashed: {e}")
        logging.error(f"Test crash: {e}", exc_info=True)
