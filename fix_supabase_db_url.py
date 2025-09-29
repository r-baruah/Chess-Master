#!/usr/bin/env python3
"""
Fix Supabase DB URL by testing different connection formats
"""
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

async def test_db_connections():
    """Test different Supabase connection string formats"""
    load_dotenv()
    
    password = "P84aLZK91GCqbsGM"
    project_ref = "fnhxvxuitmyomqogonrj"
    
    # Different possible connection strings for Supabase
    connection_strings = [
        # Standard format
        f"postgresql://postgres:{password}@db.{project_ref}.supabase.co:5432/postgres",
        # With SSL
        f"postgresql://postgres:{password}@db.{project_ref}.supabase.co:5432/postgres?sslmode=require",
        # Pooler format
        f"postgresql://postgres:{password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
        # Pooler with pgbouncer
        f"postgresql://postgres:{password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres?pgbouncer=true",
        # Alternative pooler format
        f"postgresql://postgres.{project_ref}:{password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres",
    ]
    
    print("Testing Supabase DB connection strings...")
    print("=" * 50)
    
    for i, conn_str in enumerate(connection_strings, 1):
        print(f"\n{i}. Testing: {conn_str[:50]}...")
        try:
            conn = await asyncpg.connect(conn_str)
            result = await conn.fetchval("SELECT 1")
            await conn.close()
            
            if result == 1:
                print(f"✅ SUCCESS! Working connection string:")
                print(f"   {conn_str}")
                
                # Update .env-example
                with open('.env-example', 'r') as f:
                    content = f.read()
                
                # Replace the SUPABASE_DB_URL line
                lines = content.split('\n')
                for j, line in enumerate(lines):
                    if line.startswith('SUPABASE_DB_URL='):
                        lines[j] = f'SUPABASE_DB_URL={conn_str}'
                        break
                
                with open('.env-example', 'w') as f:
                    f.write('\n'.join(lines))
                
                print("✅ Updated .env-example with working connection string")
                return True
                
        except Exception as e:
            print(f"❌ Failed: {str(e)[:100]}")
    
    print("\n❌ None of the connection strings worked")
    print("The bot will continue using REST API only mode")
    return False

if __name__ == "__main__":
    asyncio.run(test_db_connections())
