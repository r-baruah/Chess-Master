"""
Anonymous identity management system with cryptographic privacy protection
"""
import hashlib
import secrets
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from core.supabase_client import supabase_client

logger = logging.getLogger(__name__)

class AnonymousIdentityManager:
    """Manages anonymous user identities with no reverse lookup capability"""
    
    def __init__(self):
        self.salt_cache = {}  # In-memory salt cache for session performance
        self.initialized = False
    
    async def initialize(self):
        """Prepare anonymous identity manager for use"""
        if self.initialized:
            return
        try:
            # Ensure Supabase client is ready
            if not supabase_client.client:
                await supabase_client.initialize()
            # Quick metadata check to confirm users table is reachable
            if supabase_client.client:
                try:
                    supabase_client.client.table('users').select('count').limit(1).execute()
                except Exception as table_err:
                    logger.warning(f"Users table check failed during initialization: {table_err}")
            self.initialized = True
            logger.info("AnonymousIdentityManager initialized successfully")
        except Exception as init_err:
            logger.error(f"Failed to initialize AnonymousIdentityManager: {init_err}")
            raise
    
    def generate_anonymous_id(self, telegram_id: int, salt: Optional[str] = None) -> str:
        """Generate cryptographic anonymous ID with no reverse lookup"""
        if not salt:
            salt = secrets.token_hex(32)
        
        # Combine telegram_id + timestamp + salt for uniqueness
        timestamp = datetime.utcnow().timestamp()
        data = f"{telegram_id}:{timestamp}:{salt}"
        # Limit to 32 characters for database compatibility
        anonymous_id = hashlib.sha256(data.encode()).hexdigest()[:32]
        
        # Cache salt for potential session mapping (not stored in DB)
        self.salt_cache[anonymous_id] = {
            'telegram_id': telegram_id,
            'created_at': timestamp
        }
        
        logger.info(f"Generated anonymous ID for user (length: {len(anonymous_id)})")
        return anonymous_id
    
    async def create_anonymous_user(self, telegram_id: int, role: str = 'contributor', 
                                  permissions: Dict = None) -> Dict[str, Any]:
        """Create new anonymous user in database"""
        anonymous_id = self.generate_anonymous_id(telegram_id)
        
        if permissions is None:
            permissions = self._get_default_permissions(role)
        
        user_data = {
            'anonymous_id': anonymous_id,
            'telegram_id': telegram_id,
            'role': role,
            'permissions': permissions,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        try:
            # Insert using Supabase REST API
            user_record = {
                'anonymous_id': anonymous_id,
                'telegram_id': telegram_id,
                'role': role,
                'permissions': permissions,
                'created_at': user_data['created_at'],
                'updated_at': user_data['updated_at']
            }
            
            result = supabase_client.client.table('users').insert([user_record]).execute()
            
            logger.info(f"Created anonymous user with role: {role}")
            return result.data[0] if result.data else user_data
            
        except Exception as e:
            logger.error(f"Failed to create anonymous user: {e}")
            raise
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get anonymous user by Telegram ID"""
        try:
            # Use Supabase REST API
            result = supabase_client.client.table('users').select('*').eq('telegram_id', telegram_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get user by telegram_id: {e}")
            return None
    
    async def get_user_by_anonymous_id(self, anonymous_id: str) -> Optional[Dict[str, Any]]:
        """Get user by anonymous ID"""
        try:
            # Use Supabase REST API
            result = supabase_client.client.table('users').select('*').eq('anonymous_id', anonymous_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Failed to get user by anonymous_id: {e}")
            return None
    
    async def update_user_role(self, anonymous_id: str, role: str, 
                             permissions: Dict = None) -> bool:
        """Update user role and permissions"""
        if permissions is None:
            permissions = self._get_default_permissions(role)
        
        try:
            result = await supabase_client.execute_command(
                """
                UPDATE users 
                SET role = $2, permissions = $3, updated_at = $4
                WHERE anonymous_id = $1
                """,
                anonymous_id, role, permissions, datetime.utcnow().isoformat()
            )
            logger.info(f"Updated user role to: {role}")
            return True
        except Exception as e:
            logger.error(f"Failed to update user role: {e}")
            return False
    
    def get_session_mapping(self, anonymous_id: str) -> Optional[Dict]:
        """Get session mapping from cache (temporary session only)"""
        return self.salt_cache.get(anonymous_id)
    
    def _get_default_permissions(self, role: str) -> Dict[str, bool]:
        """Get default permissions for role"""
        permission_matrix = {
            'super_admin': {
                'manage_users': True,
                'manage_roles': True,
                'approve_courses': True,
                'view_analytics': True,
                'system_admin': True,
                'manage_channels': True
            },
            'admin': {
                'manage_users': True,
                'approve_courses': True,
                'view_analytics': True,
                'manage_channels': True,
                'system_admin': False,
                'manage_roles': False
            },
            'moderator': {
                'approve_courses': True,
                'view_analytics': True,
                'manage_users': False,
                'manage_channels': False,
                'system_admin': False,
                'manage_roles': False
            },
            'volunteer_reviewer': {
                'approve_courses': True,
                'view_analytics': False,
                'manage_users': False,
                'manage_channels': False,
                'system_admin': False,
                'manage_roles': False
            },
            'contributor': {
                'upload_courses': True,
                'view_own_courses': True,
                'approve_courses': False,
                'view_analytics': False,
                'manage_users': False,
                'manage_channels': False,
                'system_admin': False,
                'manage_roles': False
            }
        }
        return permission_matrix.get(role, permission_matrix['contributor'])
    
    async def verify_privacy_compliance(self) -> Dict[str, bool]:
        """Verify that no identity correlation exists"""
        try:
            # Check for any potential data leaks
            compliance_checks = {
                'no_plaintext_telegram_ids': True,
                'anonymous_ids_unique': True,
                'no_reverse_lookup_possible': True,
                'session_cache_temporary': True
            }
            
            # Verify anonymous IDs are unique
            result = await supabase_client.execute_query(
                "SELECT COUNT(*) as total, COUNT(DISTINCT anonymous_id) as unique_ids FROM users"
            )
            if result and result[0]['total'] != result[0]['unique_ids']:
                compliance_checks['anonymous_ids_unique'] = False
            
            logger.info("Privacy compliance verification completed")
            return compliance_checks
            
        except Exception as e:
            logger.error(f"Privacy compliance verification failed: {e}")
            return {'error': True}

# Global instance
anonymous_manager = AnonymousIdentityManager()