"""
Role-based access control system with permission enforcement
"""
import logging
from typing import Dict, List, Optional, Callable, Any
from functools import wraps
from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager
import asyncio

logger = logging.getLogger(__name__)

class RoleBasedAccessControl:
    """RBAC system for community management"""
    
    def __init__(self):
        self.role_hierarchy = {
            'super_admin': 100,
            'admin': 80,
            'moderator': 60,
            'volunteer_reviewer': 40,
            'contributor': 20
        }
    
    def _get_anonymous_manager(self):
        """Fetch the latest anonymous manager instance (supports patching in tests)"""
        try:
            from core import anonymity
            return getattr(anonymity, 'anonymous_manager', None)
        except Exception as exc:
            logger.error(f"Failed to load anonymous manager: {exc}")
            return None
    
    async def _ensure_initialized(self):
        """Ensure dependent services are ready"""
        manager = self._get_anonymous_manager()
        if not manager:
            return
        try:
            if hasattr(manager, 'initialize'):
                await manager.initialize()
        except AttributeError:
            # Legacy compatibility when initialize does not exist
            pass
    
    async def get_user_permissions(self, anonymous_id: str) -> Optional[Dict[str, Any]]:
        """Get user permissions by anonymous ID"""
        manager = self._get_anonymous_manager()
        if not manager:
            return None
        try:
            return await manager.get_user_by_anonymous_id(anonymous_id)
        except Exception as e:
            logger.error(f"Failed to get user permissions: {e}")
            return None

    async def check_permission(self, telegram_id: int, permission: str) -> bool:
        """Check if user has specific permission by Telegram ID"""
        manager = self._get_anonymous_manager()
        if not manager:
            return False
        try:
            user = await manager.get_user_by_telegram_id(telegram_id)
            if not user:
                return False
            permissions = user.get('permissions', {})
            return permissions.get(permission, False)
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False
    
    async def check_role_hierarchy(self, telegram_id: int, required_role: str) -> bool:
        """Check if user has role with sufficient hierarchy level"""
        try:
            user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
            if not user:
                return False
            
            user_role = user.get('role', 'contributor')
            user_level = self.role_hierarchy.get(user_role, 0)
            required_level = self.role_hierarchy.get(required_role, 100)
            
            return user_level >= required_level
            
        except Exception as e:
            logger.error(f"Role hierarchy check failed: {e}")
            return False
    
    def require_permission(self, permission: str):
        """Decorator to enforce permission requirements"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract telegram_id from message or callback query
                telegram_id = None
                
                # Check common patterns for getting user ID
                for arg in args:
                    if hasattr(arg, 'from_user') and arg.from_user:
                        telegram_id = arg.from_user.id
                        break
                    elif hasattr(arg, 'message') and arg.message and arg.message.from_user:
                        telegram_id = arg.message.from_user.id
                        break
                
                if not telegram_id:
                    logger.warning(f"Could not extract user ID for permission check: {permission}")
                    return
                
                # Get user by telegram_id first, then check permission by anonymous_id
                manager = self._get_anonymous_manager()
                user = await manager.get_user_by_telegram_id(telegram_id) if manager else None
                if not user:
                    logger.warning(f"User not found for permission check: {telegram_id}")
                    return
                
                if not await self.check_permission(user['anonymous_id'], permission):
                    logger.warning(f"Permission denied for user {telegram_id}: {permission}")
                    # Could send permission denied message here
                    return
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    def require_role(self, role: str):
        """Decorator to enforce role requirements"""
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Extract telegram_id from message or callback query
                telegram_id = None
                
                for arg in args:
                    if hasattr(arg, 'from_user') and arg.from_user:
                        telegram_id = arg.from_user.id
                        break
                    elif hasattr(arg, 'message') and arg.message and arg.message.from_user:
                        telegram_id = arg.message.from_user.id
                        break
                
                if not telegram_id:
                    logger.warning(f"Could not extract user ID for role check: {role}")
                    return
                
                manager = self._get_anonymous_manager()
                user = await manager.get_user_by_telegram_id(telegram_id) if manager else None
                if not user:
                    logger.warning(f"User not found for role check: {telegram_id}")
                    return
                
                if not await self.check_role_hierarchy(telegram_id, role):
                    logger.warning(f"Insufficient role for user {telegram_id}: requires {role}")
                    return
                
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    async def assign_role(self, telegram_id: int, role: str, 
                         assigner_telegram_id: int) -> bool:
        """Assign role to user (with hierarchy validation)"""
        try:
            # Check if assigner has permission to assign this role
            if not await self.check_permission(assigner_telegram_id, 'manage_roles'):
                logger.warning("User lacks manage_roles permission")
                return False
            
            # Check role hierarchy - can't assign higher role than your own
            manager = self._get_anonymous_manager()
            if not manager:
                return False
            assigner_user = await manager.get_user_by_telegram_id(assigner_telegram_id)
            if not assigner_user:
                return False
            
            assigner_role = assigner_user.get('role', 'contributor')
            assigner_level = self.role_hierarchy.get(assigner_role, 0)
            target_level = self.role_hierarchy.get(role, 100)
            
            if target_level >= assigner_level:
                logger.warning(f"Cannot assign role {role} - insufficient hierarchy")
                return False
            
            # Get target user
            manager = self._get_anonymous_manager()
            if not manager:
                return False
            target_user = await manager.get_user_by_telegram_id(telegram_id)
            if not target_user:
                logger.error("Target user not found for role assignment")
                return False
            
            # Assign the role
            success = await manager.update_user_role(
                target_user['anonymous_id'], 
                role
            )
            
            if success:
                logger.info(f"Role {role} assigned to user {telegram_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Role assignment failed: {e}")
            return False
    
    async def get_role_dashboard(self, telegram_id: int) -> Dict[str, Any]:
        """Get role-specific dashboard data"""
        try:
            user = await anonymous_manager.get_user_by_telegram_id(telegram_id)
            if not user:
                return {'error': 'User not found'}
            
            role = user.get('role', 'contributor')
            permissions = user.get('permissions', {})
            
            dashboard = {
                'role': role,
                'permissions': permissions,
                'hierarchy_level': self.role_hierarchy.get(role, 0),
                'available_actions': []
            }
            
            # Add role-specific actions
            if permissions.get('approve_courses'):
                dashboard['available_actions'].append('review_courses')
            
            if permissions.get('manage_users'):
                dashboard['available_actions'].append('manage_community')
            
            if permissions.get('view_analytics'):
                dashboard['available_actions'].append('view_statistics')
            
            if permissions.get('system_admin'):
                dashboard['available_actions'].append('system_administration')
            
            return dashboard
            
        except Exception as e:
            logger.error(f"Failed to get role dashboard: {e}")
            return {'error': str(e)}
    
    async def list_users_by_role(self, role: str, requester_telegram_id: int) -> List[Dict]:
        """List users by role (admin function)"""
        try:
            if not await self.check_permission(requester_telegram_id, 'manage_users'):
                return []
            try:
                result = await supabase_client.execute_query(
                    "SELECT anonymous_id, role, created_at, updated_at FROM users WHERE role = $1",
                    role
                )
                if asyncio.iscoroutine(result):
                    result = await result
                return result or []
            except Exception as query_error:
                logger.warning(f"Falling back to empty result for list_users_by_role: {query_error}")
                return []
        except Exception as e:
            logger.error(f"Failed to list users by role: {e}")
            return []

    async def get_permission_matrix(self) -> Dict[str, Dict[str, bool]]:
        """Get complete permission matrix for all roles"""
        matrix = {
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
        return matrix

# Global instance
rbac_manager = RoleBasedAccessControl()