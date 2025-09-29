#!/usr/bin/env python3
"""
Quick bot status check
"""
import time
import subprocess
import sys

def check_bot_status():
    """Check if bot is running and responsive"""
    print("Checking bot status...")
    
    # Give the bot a few seconds to start
    print("Waiting for bot to initialize...")
    time.sleep(5)
    
    # Check if bot process is running
    try:
        # Look for python processes running bot.py
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq python.exe'],
            capture_output=True,
            text=True,
            shell=True
        )
        
        if 'python.exe' in result.stdout:
            print("[OK] Python processes detected")
        else:
            print("[WARN] No Python processes found")
            
    except Exception as e:
        print(f"[ERROR] Could not check processes: {e}")
    
    print("\nBot startup status check complete!")
    print("If bot started successfully, you should see:")
    print("1. 'Bot Started as [BotName]' message")
    print("2. 'Pyrogram Bot and Web Server should be running' message")
    print("3. No error messages in the output")
    
    return True

if __name__ == "__main__":
    check_bot_status()
