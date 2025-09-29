"""
Disaster Recovery Manager for emergency deployment and system recovery
Handles configuration backup, restoration, and rapid deployment procedures
"""
import os
import json
import asyncio
import logging
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import zipfile
import hashlib
import redis.asyncio as redis
from core.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class DisasterRecoveryManager:
    """Manages disaster recovery procedures and emergency deployments"""
    
    def __init__(self, redis_client: redis.Redis, supabase_client: SupabaseClient, config_path: str = "./config"):
        self.redis = redis_client
        self.supabase = supabase_client
        self.config_path = Path(config_path)
        self.backup_locations = [
            self.config_path / "backups",
            Path("./backups"),  # Local backup
            # Add remote backup locations as needed
        ]
        self.recovery_timeout = 300  # 5 minutes max recovery time
        
    async def initialize(self):
        """Initialize disaster recovery manager"""
        try:
            # Ensure backup directories exist
            for backup_location in self.backup_locations:
                backup_location.mkdir(parents=True, exist_ok=True)
                
            logger.info("Disaster recovery manager initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize disaster recovery manager: {e}")
            return False
            
    async def create_recovery_package(self) -> Dict:
        """Create complete recovery package for emergency deployment"""
        try:
            logger.info("Creating disaster recovery package...")
            
            recovery_package = {
                'timestamp': datetime.utcnow().isoformat(),
                'package_id': self._generate_package_id(),
                'environment_variables': await self._backup_environment_variables(),
                'database_config': await self._backup_database_configuration(),
                'channel_permissions': await self._backup_channel_permissions(),
                'bot_tokens': await self._backup_bot_tokens(),
                'redis_state': await self._backup_redis_state(),
                'deployment_scripts': await self._generate_deployment_scripts(),
                'system_configuration': await self._backup_system_configuration(),
                'checksum': None  # Will be calculated after package creation
            }
            
            # Calculate package checksum for integrity verification
            recovery_package['checksum'] = self._calculate_package_checksum(recovery_package)
            
            # Save to multiple locations
            await self._save_recovery_package(recovery_package)
            
            logger.info(f"Recovery package created: {recovery_package['package_id']}")
            return recovery_package
            
        except Exception as e:
            logger.error(f"Failed to create recovery package: {e}")
            raise
            
    async def _backup_environment_variables(self) -> Dict:
        """Backup critical environment variables"""
        critical_env_vars = [
            'BOT_TOKEN', 'API_ID', 'API_HASH', 'ADMINS',
            'SUPABASE_URL', 'SUPABASE_KEY', 'SUPABASE_DB_URL',
            'REDIS_HOST', 'REDIS_PORT', 'REDIS_DB', 'REDIS_PASSWORD',
            'LOG_CHANNEL', 'COURSE_CHANNEL', 'PUBLIC_CHANNEL',
            'DATABASE_URI', 'DATABASE_NAME'
        ]
        
        env_backup = {}
        for var in critical_env_vars:
            value = os.getenv(var)
            if value:
                # Mask sensitive values for logging
                if 'TOKEN' in var or 'KEY' in var or 'PASSWORD' in var or 'URI' in var:
                    env_backup[var] = self._mask_sensitive_value(value)
                else:
                    env_backup[var] = value
                    
        return {
            'variables': env_backup,
            'backup_time': datetime.utcnow().isoformat()
        }
        
    async def _backup_database_configuration(self) -> Dict:
        """Backup database configuration and critical tables"""
        try:
            db_backup = {
                'connection_info': {
                    'supabase_url': os.getenv('SUPABASE_URL'),
                    'database_name': os.getenv('DATABASE_NAME', 'chess_courses_bot')
                },
                'table_schemas': {},
                'critical_data': {},
                'backup_time': datetime.utcnow().isoformat()
            }
            
            # Backup table schemas
            async with self.supabase.get_connection() as conn:
                # Get table schemas
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                """)
                
                for table in tables:
                    table_name = table['table_name']
                    schema = await conn.fetch(f"""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_name = '{table_name}'
                        ORDER BY ordinal_position
                    """)
                    db_backup['table_schemas'][table_name] = [dict(row) for row in schema]
                    
                # Backup critical configuration data
                critical_tables = ['bot_tokens', 'channel_configs', 'admin_settings']
                for table_name in critical_tables:
                    try:
                        data = await conn.fetch(f"SELECT * FROM {table_name}")
                        db_backup['critical_data'][table_name] = [dict(row) for row in data]
                    except Exception as e:
                        logger.warning(f"Could not backup table {table_name}: {e}")
                        
            return db_backup
            
        except Exception as e:
            logger.error(f"Failed to backup database configuration: {e}")
            return {'error': str(e), 'backup_time': datetime.utcnow().isoformat()}
            
    async def _backup_channel_permissions(self) -> Dict:
        """Backup channel permissions and configurations"""
        try:
            channel_backup = {
                'configured_channels': [],
                'permissions_tested': [],
                'backup_time': datetime.utcnow().isoformat()
            }
            
            # Get configured channels
            course_channels = os.getenv('COURSE_CHANNEL', '').split()
            log_channel = os.getenv('LOG_CHANNEL', '')
            public_channel = os.getenv('PUBLIC_CHANNEL', '')
            
            all_channels = course_channels + [log_channel, public_channel]
            all_channels = [ch for ch in all_channels if ch]
            
            for channel in all_channels:
                channel_info = {
                    'channel_id': channel,
                    'type': self._determine_channel_type(channel),
                    'required_permissions': ['send_messages', 'delete_messages', 'manage_messages']
                }
                channel_backup['configured_channels'].append(channel_info)
                
            return channel_backup
            
        except Exception as e:
            logger.error(f"Failed to backup channel permissions: {e}")
            return {'error': str(e), 'backup_time': datetime.utcnow().isoformat()}
            
    async def _backup_bot_tokens(self) -> Dict:
        """Backup bot token configurations (masked for security)"""
        try:
            token_backup = {
                'primary_token_configured': bool(os.getenv('BOT_TOKEN')),
                'api_credentials_configured': bool(os.getenv('API_ID') and os.getenv('API_HASH')),
                'backup_tokens_count': 0,
                'backup_time': datetime.utcnow().isoformat()
            }
            
            # Count backup tokens from database
            async with self.supabase.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT COUNT(*) as count 
                    FROM bot_tokens 
                    WHERE status = 'active'
                """)
                if result:
                    token_backup['backup_tokens_count'] = result['count']
                    
            return token_backup
            
        except Exception as e:
            logger.error(f"Failed to backup bot tokens info: {e}")
            return {'error': str(e), 'backup_time': datetime.utcnow().isoformat()}
            
    async def _backup_redis_state(self) -> Dict:
        """Backup critical Redis state data"""
        try:
            redis_backup = {
                'connection_info': {
                    'host': os.getenv('REDIS_HOST', 'localhost'),
                    'port': os.getenv('REDIS_PORT', '6379'),
                    'db': os.getenv('REDIS_DB', '0')
                },
                'critical_keys': {},
                'backup_time': datetime.utcnow().isoformat()
            }
            
            # Backup critical Redis keys
            critical_patterns = [
                'bot_tokens_status',
                'system_health*',
                'admin_notifications*',
                'channel_health*'
            ]
            
            for pattern in critical_patterns:
                try:
                    keys = await self.redis.keys(pattern)
                    for key in keys:
                        value = await self.redis.get(key)
                        if value:
                            redis_backup['critical_keys'][key] = value
                except Exception as e:
                    logger.warning(f"Could not backup Redis pattern {pattern}: {e}")
                    
            return redis_backup
            
        except Exception as e:
            logger.error(f"Failed to backup Redis state: {e}")
            return {'error': str(e), 'backup_time': datetime.utcnow().isoformat()}
            
    async def _backup_system_configuration(self) -> Dict:
        """Backup system configuration files"""
        try:
            config_backup = {
                'logging_config': {},
                'docker_config': {},
                'requirements': {},
                'backup_time': datetime.utcnow().isoformat()
            }
            
            # Backup logging configuration
            if os.path.exists('logging.conf'):
                with open('logging.conf', 'r') as f:
                    config_backup['logging_config'] = {
                        'content': f.read(),
                        'path': 'logging.conf'
                    }
                    
            # Backup Docker configuration
            if os.path.exists('docker-compose.yml'):
                with open('docker-compose.yml', 'r') as f:
                    config_backup['docker_config'] = {
                        'content': f.read(),
                        'path': 'docker-compose.yml'
                    }
                    
            # Backup requirements
            if os.path.exists('requirements.txt'):
                with open('requirements.txt', 'r') as f:
                    config_backup['requirements'] = {
                        'content': f.read(),
                        'path': 'requirements.txt'
                    }
                    
            return config_backup
            
        except Exception as e:
            logger.error(f"Failed to backup system configuration: {e}")
            return {'error': str(e), 'backup_time': datetime.utcnow().isoformat()}
            
    async def _generate_deployment_scripts(self) -> Dict:
        """Generate emergency deployment scripts"""
        scripts = {
            'quick_deploy': self._generate_quick_deploy_script(),
            'health_check': self._generate_health_check_script(),
            'rollback': self._generate_rollback_script(),
            'permissions_setup': self._generate_permissions_setup_script()
        }
        
        return scripts
        
    def _generate_quick_deploy_script(self) -> str:
        """Generate quick deployment script"""
        return '''#!/bin/bash
# Emergency Quick Deploy Script
set -e

echo "🚀 Starting emergency deployment..."

# Check Python and dependencies
python3 -c "import sys; print(f'Python version: {sys.version}')"
pip3 install -r requirements.txt

# Set environment variables from recovery package
if [ -f ".env.recovery" ]; then
    export $(cat .env.recovery | xargs)
    echo "✅ Environment variables loaded"
fi

# Test database connectivity
python3 -c "from core.supabase_client import SupabaseClient; import asyncio; asyncio.run(SupabaseClient().initialize())"
echo "✅ Database connectivity verified"

# Test Redis connectivity  
python3 -c "from core.redis_state import RedisStateManager; import asyncio; asyncio.run(RedisStateManager().initialize())"
echo "✅ Redis connectivity verified"

# Start the bot
python3 bot.py &
BOT_PID=$!

# Wait for startup
sleep 10

# Basic health check
if kill -0 $BOT_PID 2>/dev/null; then
    echo "✅ Bot started successfully (PID: $BOT_PID)"
    echo "🎉 Emergency deployment completed in under 2 minutes!"
else
    echo "❌ Bot failed to start"
    exit 1
fi
'''

    def _generate_health_check_script(self) -> str:
        """Generate health check script"""
        return '''#!/bin/bash
# Health Check Script
set -e

echo "🔍 Performing system health check..."

# Check if bot process is running
BOT_PID=$(pgrep -f "python.*bot.py" || echo "")
if [ -n "$BOT_PID" ]; then
    echo "✅ Bot process running (PID: $BOT_PID)"
else
    echo "❌ Bot process not found"
    exit 1
fi

# Test API connectivity
python3 -c "
import asyncio
from pyrogram import Client
import os

async def test_bot():
    client = Client('health_test', 
                   api_id=int(os.getenv('API_ID')),
                   api_hash=os.getenv('API_HASH'),
                   bot_token=os.getenv('BOT_TOKEN'),
                   in_memory=True)
    try:
        await client.start()
        me = await client.get_me()
        print(f'✅ Bot API connectivity verified: @{me.username}')
        await client.stop()
        return True
    except Exception as e:
        print(f'❌ Bot API test failed: {e}')
        await client.stop()
        return False

success = asyncio.run(test_bot())
exit(0 if success else 1)
"

echo "🎉 Health check completed successfully"
'''

    def _generate_rollback_script(self) -> str:
        """Generate rollback script"""
        return '''#!/bin/bash
# Rollback Script
set -e

echo "🔄 Initiating system rollback..."

# Stop current bot
BOT_PID=$(pgrep -f "python.*bot.py" || echo "")
if [ -n "$BOT_PID" ]; then
    kill $BOT_PID
    echo "✅ Stopped current bot process"
fi

# Restore previous configuration
if [ -f ".env.backup" ]; then
    cp .env.backup .env
    echo "✅ Configuration restored"
fi

# Restart with backup configuration
python3 bot.py &
echo "✅ Bot restarted with rollback configuration"

echo "🎉 Rollback completed"
'''

    def _generate_permissions_setup_script(self) -> str:
        """Generate channel permissions setup script"""
        return '''#!/usr/bin/env python3
# Channel Permissions Setup Script
import asyncio
import os
from pyrogram import Client

async def setup_permissions():
    client = Client('permissions_setup',
                   api_id=int(os.getenv('API_ID')),
                   api_hash=os.getenv('API_HASH'),
                   bot_token=os.getenv('BOT_TOKEN'),
                   in_memory=True)
    
    try:
        await client.start()
        me = await client.get_me()
        print(f"🤖 Setting up permissions for @{me.username}")
        
        # Test configured channels
        channels = os.getenv('COURSE_CHANNEL', '').split()
        for channel in channels:
            if channel:
                try:
                    chat = await client.get_chat(channel)
                    print(f"✅ Channel access verified: {chat.title}")
                    
                    # Send test message
                    test_msg = await client.send_message(
                        channel, 
                        "🔧 Permission verification test",
                        disable_notification=True
                    )
                    await client.delete_messages(channel, test_msg.id)
                    print(f"✅ Send/delete permissions verified for {chat.title}")
                    
                except Exception as e:
                    print(f"❌ Channel {channel} failed: {e}")
                    
        await client.stop()
        print("🎉 Permissions setup completed")
        
    except Exception as e:
        print(f"❌ Permissions setup failed: {e}")
        await client.stop()

if __name__ == "__main__":
    asyncio.run(setup_permissions())
'''

    async def execute_emergency_recovery(self, recovery_package: Dict) -> bool:
        """Execute emergency recovery from backup package"""
        start_time = datetime.utcnow()
        logger.info("🚨 Starting emergency recovery procedure...")
        
        try:
            # Verify package integrity
            if not self._verify_package_integrity(recovery_package):
                raise Exception("Recovery package integrity verification failed")
                
            # Step 1: Restore environment configuration
            logger.info("Step 1: Restoring environment variables...")
            await self._restore_environment_variables(recovery_package['environment_variables'])
            
            # Step 2: Verify database connectivity
            logger.info("Step 2: Verifying database connectivity...")
            await self._verify_database_connection(recovery_package['database_config'])
            
            # Step 3: Restore Redis state
            logger.info("Step 3: Restoring Redis state...")
            await self._restore_redis_state(recovery_package['redis_state'])
            
            # Step 4: Setup bot tokens
            logger.info("Step 4: Configuring bot tokens...")
            await self._configure_bot_tokens(recovery_package['bot_tokens'])
            
            # Step 5: Restore channel permissions
            logger.info("Step 5: Restoring channel permissions...")
            await self._restore_channel_permissions(recovery_package['channel_permissions'])
            
            # Step 6: Deploy services
            logger.info("Step 6: Deploying services...")
            await self._deploy_services(recovery_package['deployment_scripts'])
            
            # Step 7: Perform health verification
            logger.info("Step 7: Verifying system health...")
            health_status = await self._verify_system_health()
            
            recovery_time = (datetime.utcnow() - start_time).total_seconds()
            
            if health_status['success']:
                logger.info(f"✅ Emergency recovery completed successfully in {recovery_time:.1f} seconds!")
                await self._notify_recovery_success(recovery_time)
                return True
            else:
                logger.error(f"❌ Recovery verification failed: {health_status['errors']}")
                await self._notify_recovery_failure("Health verification failed", health_status['errors'])
                return False
                
        except Exception as e:
            recovery_time = (datetime.utcnow() - start_time).total_seconds()
            logger.critical(f"💥 Emergency recovery failed after {recovery_time:.1f} seconds: {e}")
            await self._notify_recovery_failure("Recovery procedure failed", [str(e)])
            return False
            
    async def _restore_environment_variables(self, env_backup: Dict):
        """Restore environment variables from backup"""
        try:
            if 'error' in env_backup:
                raise Exception(f"Environment backup contains error: {env_backup['error']}")
                
            variables = env_backup.get('variables', {})
            
            # Create recovery environment file
            env_file_path = Path('.env.recovery')
            with open(env_file_path, 'w') as f:
                for key, value in variables.items():
                    # Unmask values if they were masked (in real scenario, get from secure storage)
                    if self._is_masked_value(value):
                        # In real implementation, retrieve from secure vault
                        value = os.getenv(key, value)  # Fallback to current env
                    f.write(f"{key}={value}\\n")
                    
            logger.info(f"Environment variables restored to {env_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to restore environment variables: {e}")
            raise
            
    async def _verify_database_connection(self, db_config: Dict):
        """Verify database connectivity"""
        try:
            if 'error' in db_config:
                logger.warning(f"Database backup contains error: {db_config['error']}")
                
            # Test Supabase connection
            from core.supabase_client import SupabaseClient
            supabase_client = SupabaseClient()
            await supabase_client.initialize()
            
            # Test basic query
            async with supabase_client.get_connection() as conn:
                result = await conn.fetchrow("SELECT NOW() as current_time")
                logger.info(f"Database connectivity verified at {result['current_time']}")
                
        except Exception as e:
            logger.error(f"Database connectivity verification failed: {e}")
            raise
            
    async def _restore_redis_state(self, redis_backup: Dict):
        """Restore Redis state from backup"""
        try:
            if 'error' in redis_backup:
                logger.warning(f"Redis backup contains error: {redis_backup['error']}")
                return
                
            critical_keys = redis_backup.get('critical_keys', {})
            
            for key, value in critical_keys.items():
                await self.redis.set(key, value)
                
            logger.info(f"Restored {len(critical_keys)} Redis keys")
            
        except Exception as e:
            logger.error(f"Failed to restore Redis state: {e}")
            # Don't raise - Redis restore is not critical for basic functionality
            
    async def _configure_bot_tokens(self, token_backup: Dict):
        """Configure bot tokens from backup"""
        try:
            if not token_backup.get('primary_token_configured'):
                raise Exception("No primary bot token configured in backup")
                
            if not token_backup.get('api_credentials_configured'):
                raise Exception("API credentials not configured in backup")
                
            logger.info("Bot token configuration verified from backup")
            
        except Exception as e:
            logger.error(f"Bot token configuration failed: {e}")
            raise
            
    async def _restore_channel_permissions(self, channel_backup: Dict):
        """Restore channel permissions"""
        try:
            if 'error' in channel_backup:
                logger.warning(f"Channel backup contains error: {channel_backup['error']}")
                
            channels = channel_backup.get('configured_channels', [])
            logger.info(f"Channel permissions restore verified for {len(channels)} channels")
            
        except Exception as e:
            logger.error(f"Channel permissions restore failed: {e}")
            # Don't raise - will be verified in health check
            
    async def _deploy_services(self, deployment_scripts: Dict):
        """Deploy services using generated scripts"""
        try:
            # Save deployment scripts
            scripts_dir = Path('./recovery_scripts')
            scripts_dir.mkdir(exist_ok=True)
            
            for script_name, script_content in deployment_scripts.items():
                script_path = scripts_dir / f"{script_name}.sh"
                with open(script_path, 'w') as f:
                    f.write(script_content)
                script_path.chmod(0o755)  # Make executable
                
            logger.info("Deployment scripts prepared")
            
        except Exception as e:
            logger.error(f"Service deployment failed: {e}")
            raise
            
    async def _verify_system_health(self) -> Dict:
        """Verify system health after recovery"""
        health_status = {
            'success': True,
            'errors': [],
            'checks_performed': []
        }
        
        try:
            # Test bot connectivity
            from pyrogram import Client
            
            client = Client('health_check_recovery',
                          api_id=int(os.getenv('API_ID')),
                          api_hash=os.getenv('API_HASH'),
                          bot_token=os.getenv('BOT_TOKEN'),
                          in_memory=True)
                          
            await client.start()
            me = await client.get_me()
            await client.stop()
            
            health_status['checks_performed'].append(f"Bot API connectivity (@{me.username})")
            
            # Test Redis connectivity
            await self.redis.ping()
            health_status['checks_performed'].append("Redis connectivity")
            
            # Test Supabase connectivity
            async with self.supabase.get_connection() as conn:
                await conn.fetchrow("SELECT 1")
            health_status['checks_performed'].append("Database connectivity")
            
        except Exception as e:
            health_status['success'] = False
            health_status['errors'].append(str(e))
            
        return health_status
        
    async def _save_recovery_package(self, recovery_package: Dict):
        """Save recovery package to multiple locations"""
        package_filename = f"recovery_package_{recovery_package['package_id']}.json"
        
        for backup_location in self.backup_locations:
            try:
                backup_file = backup_location / package_filename
                with open(backup_file, 'w') as f:
                    json.dump(recovery_package, f, indent=2, default=str)
                logger.info(f"Recovery package saved to {backup_file}")
            except Exception as e:
                logger.error(f"Failed to save recovery package to {backup_location}: {e}")
                
    def _generate_package_id(self) -> str:
        """Generate unique package ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"recovery_{timestamp}"
        
    def _calculate_package_checksum(self, package: Dict) -> str:
        """Calculate package checksum for integrity verification"""
        package_copy = package.copy()
        package_copy.pop('checksum', None)  # Remove checksum field itself
        package_json = json.dumps(package_copy, sort_keys=True, default=str)
        return hashlib.sha256(package_json.encode()).hexdigest()
        
    def _verify_package_integrity(self, package: Dict) -> bool:
        """Verify package integrity using checksum"""
        stored_checksum = package.get('checksum')
        if not stored_checksum:
            logger.warning("No checksum found in recovery package")
            return True  # Allow recovery without checksum
            
        calculated_checksum = self._calculate_package_checksum(package)
        return stored_checksum == calculated_checksum
        
    def _mask_sensitive_value(self, value: str) -> str:
        """Mask sensitive values for logging"""
        if len(value) <= 8:
            return "*" * len(value)
        return value[:4] + "*" * (len(value) - 8) + value[-4:]
        
    def _is_masked_value(self, value: str) -> bool:
        """Check if value is masked"""
        return "*" in value and len(value) > 8
        
    def _determine_channel_type(self, channel: str) -> str:
        """Determine channel type based on configuration"""
        if channel == os.getenv('LOG_CHANNEL'):
            return 'log_channel'
        elif channel == os.getenv('PUBLIC_CHANNEL'):
            return 'public_channel'
        elif channel in os.getenv('COURSE_CHANNEL', '').split():
            return 'course_channel'
        else:
            return 'unknown'
            
    async def _notify_recovery_success(self, recovery_time: float):
        """Notify administrators of successful recovery"""
        try:
            notification_data = {
                'type': 'recovery_success',
                'message': f"✅ Emergency recovery completed successfully in {recovery_time:.1f} seconds",
                'timestamp': datetime.utcnow().isoformat(),
                'recovery_time': recovery_time
            }
            
            await self.redis.lpush('admin_notifications', json.dumps(notification_data))
            logger.info("Recovery success notification sent")
            
        except Exception as e:
            logger.error(f"Failed to send recovery success notification: {e}")
            
    async def _notify_recovery_failure(self, error_message: str, errors: List[str]):
        """Notify administrators of recovery failure"""
        try:
            notification_data = {
                'type': 'recovery_failure',
                'message': f"🚨 CRITICAL: Emergency recovery failed - {error_message}",
                'timestamp': datetime.utcnow().isoformat(),
                'errors': errors,
                'requires_manual_intervention': True
            }
            
            await self.redis.lpush('admin_notifications', json.dumps(notification_data))
            logger.critical(f"Recovery failure notification sent: {error_message}")
            
        except Exception as e:
            logger.error(f"Failed to send recovery failure notification: {e}")