#!/usr/bin/env python3
"""
Local testing script for ChessMaster bot setup
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_environment():
    """Test environment configuration"""
    logger.info("=== ChessMaster Bot Local Testing ===")
    
    # Check required environment variables
    required_vars = [
        'BOT_TOKEN', 'API_ID', 'API_HASH', 'ADMINS',
        'SUPABASE_URL', 'SUPABASE_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        logger.info("Please create a .env file with the following variables:")
        for var in missing_vars:
            logger.info(f"  {var}=your_value_here")
        return False
    
    logger.info("✅ All required environment variables are set")
    return True

async def test_redis_fallback():
    """Test Redis with fallback"""
    logger.info("Testing Redis connection (with fallback)...")
    
    try:
        from core.redis_state import RedisStateManager
        
        redis_manager = RedisStateManager()
        await redis_manager.initialize()
        
        if redis_manager.use_fallback:
            logger.info("✅ Using in-memory fallback (Redis not available)")
        else:
            logger.info("✅ Redis connection successful")
        
        # Test basic operations
        await redis_manager.cache_set("test_key", "test_value", 10)
        result = await redis_manager.cache_get("test_key")
        
        if result == "test_value":
            logger.info("✅ Cache operations working")
        else:
            logger.warning("⚠️  Cache test failed")
        
        await redis_manager.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Redis test failed: {e}")
        return False

async def test_supabase_connection():
    """Test Supabase connection"""
    logger.info("Testing Supabase connection...")
    
    try:
        from core.supabase_client import SupabaseClient
        
        supabase = SupabaseClient()
        
        # Test basic client initialization
        if not supabase.url or not supabase.key:
            logger.error("❌ Supabase credentials not configured")
            return False
        
        logger.info(f"✅ Supabase URL configured: {supabase.url}")
        logger.info("✅ Supabase key configured")
        
        # Note: We won't test actual connection here since we need DB password
        logger.info("ℹ️  Database connection will be tested when bot starts")
        return True
        
    except Exception as e:
        logger.error(f"❌ Supabase test failed: {e}")
        return False

async def test_core_modules():
    """Test core modules can be imported"""
    logger.info("Testing core module imports...")
    
    modules_to_test = [
        'core.anonymity',
        'core.roles', 
        'core.analytics_engine',
        'core.volunteer_system',
        'core.disaster_recovery_manager'
    ]
    
    success_count = 0
    for module in modules_to_test:
        try:
            __import__(module)
            logger.info(f"✅ {module}")
            success_count += 1
        except Exception as e:
            logger.error(f"❌ {module}: {e}")
    
    if success_count == len(modules_to_test):
        logger.info("✅ All core modules imported successfully")
        return True
    else:
        logger.warning(f"⚠️  {success_count}/{len(modules_to_test)} modules imported successfully")
        return False

async def test_bot_initialization():
    """Test if bot can be initialized"""
    logger.info("Testing bot initialization...")
    
    try:
        # This will test if we can create a bot instance
        from pyrogram import Client
        
        api_id = os.getenv('API_ID')
        api_hash = os.getenv('API_HASH')
        bot_token = os.getenv('BOT_TOKEN')
        
        if not all([api_id, api_hash, bot_token]):
            logger.error("❌ Missing Telegram credentials")
            return False
        
        # Create bot instance (don't start it yet)
        app = Client(
            "test_session",
            api_id=int(api_id),
            api_hash=api_hash,
            bot_token=bot_token,
            workdir="."
        )
        
        logger.info("✅ Bot instance created successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        return False

async def main():
    """Main testing function"""
    logger.info("Starting ChessMaster bot local setup test...")
    
    tests = [
        ("Environment Variables", test_environment),
        ("Redis/Fallback", test_redis_fallback),
        ("Supabase Configuration", test_supabase_connection),
        ("Core Modules", test_core_modules),
        ("Bot Initialization", test_bot_initialization)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n--- Testing {test_name} ---")
        try:
            if await test_func():
                passed += 1
            else:
                logger.error(f"Test '{test_name}' failed")
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
    
    logger.info(f"\n=== Test Results: {passed}/{total} tests passed ===")
    
    if passed == total:
        logger.info("🎉 All tests passed! Your bot is ready for local testing.")
        logger.info("\nNext steps:")
        logger.info("1. Copy .env-example to .env")
        logger.info("2. Fill in any missing values")
        logger.info("3. Run: python bot.py")
    else:
        logger.warning("⚠️  Some tests failed. Please fix the issues before running the bot.")
        
        if passed >= 3:  # If core functionality works
            logger.info("\nYou can still try running the bot with: python bot.py")
            logger.info("Some features may not work properly.")

if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        if Path('.env').exists():
            load_dotenv()
            logger.info("Loaded environment variables from .env file")
        else:
            logger.info("No .env file found, using system environment variables")
    except ImportError:
        logger.warning("python-dotenv not installed, using system environment variables")
    
    asyncio.run(main())
