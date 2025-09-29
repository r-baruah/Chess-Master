#!/usr/bin/env python3
"""
Simple bot test without complex dependencies
"""
import os
import asyncio
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_bot_creation():
    """Test basic bot creation without full initialization"""
    try:
        # Test if we can create a basic Pyrogram client
        from pyrogram import Client
        from info import SESSION, API_ID, API_HASH, BOT_TOKEN
        
        logger.info("Creating basic Pyrogram client...")
        
        # Create a basic client
        bot = Client(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5
        )
        
        logger.info("✅ Bot client created successfully")
        logger.info(f"Session: {SESSION}")
        logger.info(f"API ID: {API_ID}")
        logger.info(f"Bot Token: {BOT_TOKEN[:20]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Bot creation failed: {e}")
        return False

async def test_core_services():
    """Test core services initialization"""
    try:
        # Test Redis state (with fallback)
        from core.redis_state import redis_state
        await redis_state.initialize()
        logger.info("✅ Redis state initialized (may use fallback)")
        
        # Test anonymity manager
        from core.anonymity import anonymous_manager
        test_id = anonymous_manager.generate_anonymous_id(12345)
        logger.info(f"✅ Anonymity manager working (test ID: {test_id[:16]}...)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Core services test failed: {e}")
        return False

async def main():
    """Main test function"""
    logger.info("🧪 Running simplified bot tests...")
    
    # Test 1: Bot creation
    logger.info("\n--- Test 1: Bot Creation ---")
    bot_test = await test_bot_creation()
    
    # Test 2: Core services
    logger.info("\n--- Test 2: Core Services ---")
    core_test = await test_core_services()
    
    # Summary
    logger.info("\n" + "="*40)
    logger.info("TEST SUMMARY")
    logger.info("="*40)
    logger.info(f"Bot Creation: {'✅ PASS' if bot_test else '❌ FAIL'}")
    logger.info(f"Core Services: {'✅ PASS' if core_test else '❌ FAIL'}")
    
    if bot_test and core_test:
        logger.info("\n🎉 Basic bot functionality is working!")
        logger.info("You can now try starting the bot with: python bot.py")
        return True
    else:
        logger.info("\n❌ Some basic tests failed. Check the errors above.")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("Test interrupted")
        exit(1)
    except Exception as e:
        logger.error(f"Test crashed: {e}")
        exit(1)
