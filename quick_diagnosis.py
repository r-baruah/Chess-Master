#!/usr/bin/env python3
"""
Quick diagnosis script to identify immediate issues
"""
import os
import sys
import traceback

def test_basic_imports():
    """Test basic imports without asyncio complexity"""
    print("=" * 50)
    print("QUICK DIAGNOSIS - CHESSMASTER BOT")
    print("=" * 50)
    
    # 1. Test environment loading
    print("\n1. Testing environment loading...")
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("[OK] dotenv loaded")
    except Exception as e:
        print(f"[WARN] dotenv failed: {e}")
    
    # 2. Check critical env vars
    print("\n2. Checking environment variables...")
    critical_vars = ['BOT_TOKEN', 'API_ID', 'API_HASH']
    for var in critical_vars:
        value = os.getenv(var)
        if value:
            print(f"[OK] {var}: {'*' * min(len(value), 4)}...")
        else:
            print(f"[MISSING] {var}: NOT SET")
    
    # 3. Test core imports
    print("\n3. Testing critical imports...")
    try:
        import pyrogram
        print("[OK] pyrogram imported")
    except Exception as e:
        print(f"[ERROR] pyrogram failed: {e}")
        
    try:
        import info
        print("[OK] info imported")
        print(f"   API_ID: {getattr(info, 'API_ID', 'MISSING')}")
        print(f"   BOT_TOKEN: {'SET' if getattr(info, 'BOT_TOKEN', '') else 'MISSING'}")
    except Exception as e:
        print(f"[ERROR] info import failed: {e}")
        traceback.print_exc()
        
    try:
        from Script import script
        print("[OK] Script imported")
    except Exception as e:
        print(f"[ERROR] Script import failed: {e}")
        traceback.print_exc()
    
    # 4. Test Supabase import only
    print("\n4. Testing Supabase import...")
    try:
        import supabase
        print("[OK] supabase package available")
    except Exception as e:
        print(f"[ERROR] supabase package failed: {e}")
        
    try:
        from core.supabase_client import SupabaseClient
        print("[OK] SupabaseClient imported")
    except Exception as e:
        print(f"[ERROR] SupabaseClient failed: {e}")
        traceback.print_exc()
    
    # 5. Test Redis import only
    print("\n5. Testing Redis import...")
    try:
        import redis.asyncio as redis
        print("[OK] redis.asyncio available")
    except Exception as e:
        print(f"[ERROR] redis.asyncio failed: {e}")
        
    try:
        from core.redis_state import RedisStateManager
        print("[OK] RedisStateManager imported")
    except Exception as e:
        print(f"[ERROR] RedisStateManager failed: {e}")
        traceback.print_exc()
    
    # 6. Test Bot class import
    print("\n6. Testing Bot class...")
    try:
        from bot import Bot
        print("[OK] Bot class imported")
    except Exception as e:
        print(f"[ERROR] Bot class failed: {e}")
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("DIAGNOSIS COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    test_basic_imports()
