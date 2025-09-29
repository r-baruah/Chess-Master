#!/usr/bin/env python3
"""
Simple startup test script to identify and fix ChessMaster bot issues
"""
import os
import sys
import asyncio
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_environment():
    """Test environment variables and configurations"""
    logger.info("Testing environment configuration...")
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("✅ Environment variables loaded")
    except ImportError:
        logger.warning("⚠️ python-dotenv not available, using system environment")
    
    # Check critical environment variables
    required_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH', 'SUPABASE_URL', 'SUPABASE_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Missing environment variables: {missing_vars}")
        return False
    else:
        logger.info("✅ All required environment variables present")
        return True

async def test_imports():
    """Test all critical imports"""
    logger.info("Testing module imports...")
    
    try:
        # Test basic imports
        import pyrogram
        logger.info("✅ Pyrogram imported")
        
        import info
        logger.info("✅ Info module imported")
        
        import utils
        logger.info("✅ Utils module imported")
        
        from Script import script
        logger.info("✅ Script module imported")
        
        # Test core modules
        from core.supabase_client import supabase_client
        logger.info("✅ Supabase client imported")
        
        from core.redis_state import redis_state
        logger.info("✅ Redis state imported")
        
        from core.anonymity import anonymous_manager
        logger.info("✅ Anonymity manager imported")
        
        from core.roles import rbac_manager
        logger.info("✅ RBAC manager imported")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        return False

async def test_database_connections():
    """Test database connections with fallback handling"""
    logger.info("Testing database connections...")
    
    try:
        # Test Redis (with fallback)
        from core.redis_state import redis_state
        await redis_state.initialize()
        logger.info("✅ Redis initialized (may use fallback)")
        
        # Test Supabase (skip if credentials are invalid)
        try:
            from core.supabase_client import supabase_client
            await supabase_client.initialize()
            logger.info("✅ Supabase initialized")
        except Exception as e:
            logger.warning(f"⚠️ Supabase connection failed (expected in test): {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database connection error: {e}")
        return False

async def test_plugin_imports():
    """Test plugin imports"""
    logger.info("Testing plugin imports...")
    
    plugin_files = [
        'plugins/commands.py',
        'plugins/inline.py',
        'plugins/course_manager.py',
        'plugins/enhanced_course_manager.py'
    ]
    
    success_count = 0
    
    for plugin in plugin_files:
        if Path(plugin).exists():
            try:
                # Import the plugin module
                module_name = plugin.replace('/', '.').replace('.py', '')
                __import__(module_name)
                logger.info(f"✅ {plugin} imported successfully")
                success_count += 1
            except Exception as e:
                logger.error(f"❌ {plugin} import failed: {e}")
        else:
            logger.warning(f"⚠️ {plugin} not found")
    
    logger.info(f"Plugin import summary: {success_count}/{len(plugin_files)} successful")
    return success_count > 0

async def test_bot_initialization():
    """Test bot class initialization without starting"""
    logger.info("Testing bot initialization...")
    
    try:
        from bot import Bot
        
        # Create bot instance without starting
        bot = Bot()
        logger.info("✅ Bot instance created successfully")
        
        # Test if bot has required attributes
        if hasattr(bot, 'disaster_recovery_service'):
            logger.info("✅ Bot has disaster recovery service attribute")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        return False

async def run_all_tests():
    """Run all startup tests"""
    logger.info("🚀 Starting ChessMaster bot startup tests...")
    
    tests = [
        ("Environment Configuration", test_environment),
        ("Module Imports", test_imports),
        ("Database Connections", test_database_connections),
        ("Plugin Imports", test_plugin_imports),
        ("Bot Initialization", test_bot_initialization)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n--- Running {test_name} Test ---")
        try:
            result = await test_func()
            results[test_name] = result
            if result:
                logger.info(f"✅ {test_name} test passed")
            else:
                logger.error(f"❌ {test_name} test failed")
        except Exception as e:
            logger.error(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("STARTUP TEST SUMMARY")
    logger.info("="*50)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Bot should start successfully.")
        return True
    else:
        logger.error("❌ Some tests failed. Please fix the issues before starting the bot.")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(run_all_tests())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test runner crashed: {e}")
        sys.exit(1)
