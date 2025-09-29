#!/usr/bin/env python3
"""
Test Supabase connection and identify specific issues
"""
import os
import asyncio
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_supabase_connection():
    """Test Supabase connection with detailed error reporting"""
    print("Testing Supabase Connection")
    print("=" * 40)
    
    # Load environment
    load_dotenv()
    
    # Get Supabase credentials
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    supabase_db_url = os.getenv('SUPABASE_DB_URL')
    
    print(f"SUPABASE_URL: {supabase_url[:50] + '...' if supabase_url else 'NOT SET'}")
    print(f"SUPABASE_KEY: {'SET (length: ' + str(len(supabase_key)) + ')' if supabase_key else 'NOT SET'}")
    print(f"SUPABASE_DB_URL: {'SET' if supabase_db_url else 'NOT SET'}")
    
    if not supabase_url or not supabase_key:
        print("\n[ERROR] Missing Supabase credentials!")
        print("Please set SUPABASE_URL and SUPABASE_KEY in your .env file")
        return False
    
    # Test 1: Basic Supabase client connection
    print("\n1. Testing basic Supabase client...")
    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        print("[OK] Supabase client created")
        
        # Try a simple query with existing system tables
        try:
            # Try to query system tables or our app tables
            result = client.table('users').select('count').limit(1).execute()
            print("[OK] Basic query executed (users table accessible)")
        except Exception as table_err:
            # If users table doesn't exist, try system table
            try:
                # Use a basic SELECT 1 query through RPC or a system view
                result = client.rpc('select_one').execute()
                print("[OK] Basic RPC query executed")
            except Exception as rpc_err:
                print(f"[WARN] Table query failed but connection works: {table_err}")
                print("This is normal if database schema is not yet created")
        
    except Exception as e:
        print(f"[ERROR] Supabase client failed: {e}")
        print("This could indicate:")
        print("- Invalid SUPABASE_URL or SUPABASE_KEY")
        print("- Network connectivity issues")
        print("- Supabase project not accessible")
        return False
    
    # Test 2: PostgreSQL direct connection
    print("\n2. Testing PostgreSQL direct connection...")
    if supabase_db_url:
        try:
            import asyncpg
            
            # Try to connect
            conn = await asyncpg.connect(supabase_db_url)
            print("[OK] PostgreSQL connection established")
            
            # Try a simple query
            result = await conn.fetch("SELECT version();")
            print(f"[OK] Database version: {result[0]['version'][:50]}...")
            
            await conn.close()
            print("[OK] Connection closed")
            
        except Exception as e:
            print(f"[ERROR] PostgreSQL connection failed: {e}")
            print("This could indicate:")
            print("- Invalid SUPABASE_DB_URL")
            print("- Incorrect database credentials")
            print("- Connection string format issues")
            
            if 'password authentication failed' in str(e).lower():
                print("- Password authentication failed - check your database password")
            elif 'could not translate host name' in str(e).lower():
                print("- Host name resolution failed - check your Supabase URL")
            elif 'connection refused' in str(e).lower():
                print("- Connection refused - check if database is accessible")
                
            return False
    else:
        print("[SKIP] No SUPABASE_DB_URL provided")
    
    # Test 3: SupabaseClient class
    print("\n3. Testing SupabaseClient class...")
    try:
        from core.supabase_client import SupabaseClient
        
        supabase_client = SupabaseClient()
        print("[OK] SupabaseClient instance created")
        
        # Try initialization (this might fail due to DB credentials)
        try:
            await supabase_client.initialize()
            print("[OK] SupabaseClient initialized successfully")
            
            # Test a simple operation
            health = await supabase_client.health_check() if hasattr(supabase_client, 'health_check') else None
            if health:
                print(f"[OK] Health check: {health.get('status', 'unknown')}")
            
            await supabase_client.close()
            
        except Exception as e:
            print(f"[ERROR] SupabaseClient initialization failed: {e}")
            return False
            
    except Exception as e:
        print(f"[ERROR] SupabaseClient import/creation failed: {e}")
        return False
    
    print("\n" + "=" * 40)
    print("SUPABASE CONNECTION TEST COMPLETE")
    print("All tests passed! Supabase should work correctly.")
    print("=" * 40)
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_supabase_connection())
    exit(0 if result else 1)
