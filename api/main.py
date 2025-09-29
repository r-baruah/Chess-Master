"""
RESTful API System - Comprehensive API endpoints for external integrations
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import jwt
import json
from pydantic import BaseModel, Field
import uuid

from core.supabase_client import supabase_client
from core.anonymity import anonymous_manager
from core.roles import rbac_manager
from core.analytics_engine import analytics_engine
from core.advanced_user_manager import advanced_user_manager
from core.targeted_announcement_manager import targeted_announcement_manager

logger = logging.getLogger(__name__)

# Pydantic Models for API
class CourseUpload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    category: str = Field(..., min_length=1, max_length=50)
    tags: List[str] = Field(default=[], max_items=10)
    files: List[Dict[str, Any]] = Field(..., min_items=1)
    metadata: Optional[Dict[str, Any]] = Field(default={})

class BulkCourseUpload(BaseModel):
    courses: List[CourseUpload] = Field(..., min_items=1, max_items=50)
    anonymous_contributor_id: str
    bulk_upload_metadata: Dict[str, Any] = Field(default={})

class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    targeting_rules: Dict[str, Any]
    scheduling: Optional[Dict[str, Any]] = Field(default={'send_immediately': True})
    options: Optional[Dict[str, Any]] = Field(default={})

class UserSearch(BaseModel):
    search_criteria: Dict[str, Any]
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)

class BulkUserOperation(BaseModel):
    operation: str = Field(..., pattern="^(update_role|update_permissions|bulk_message)$")
    user_list: List[str] = Field(..., min_items=1, max_items=100)
    operation_params: Dict[str, Any]

class APIKey(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    permissions: List[str] = Field(..., min_items=1)
    expires_at: Optional[datetime] = None
    rate_limit: Optional[int] = Field(default=1000, ge=1, le=10000)

# FastAPI App
app = FastAPI(
    title="ChessMaster Community API",
    description="RESTful API for ChessMaster community platform with role-based access control",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

class APIManager:
    """Manages API authentication, rate limiting, and versioning"""
    
    def __init__(self):
        self.jwt_secret = "your-jwt-secret-key"  # Should be from environment
        self.jwt_algorithm = "HS256"
        self.rate_limits = {}
        self.api_keys = {}
    
    async def authenticate_request(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
        """Authenticate API request and return user context"""
        try:
            token = credentials.credentials
            
            # Decode JWT token
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            
            # Get user information
            anonymous_id = payload.get('anonymous_id')
            if not anonymous_id:
                raise HTTPException(status_code=401, detail="Invalid token")
            
            # Verify user exists and get permissions
            user = await anonymous_manager.get_user_by_anonymous_id(anonymous_id)
            if not user:
                raise HTTPException(status_code=401, detail="User not found")
            
            return {
                'anonymous_id': anonymous_id,
                'role': user['role'],
                'permissions': user.get('permissions', {}),
                'token_type': payload.get('type', 'user')
            }
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")
    
    async def check_permission(self, user_context: Dict, required_permission: str) -> bool:
        """Check if user has required permission"""
        return user_context['permissions'].get(required_permission, False)
    
    async def check_rate_limit(self, user_id: str, endpoint: str, limit: int = 100) -> bool:
        """Check API rate limiting"""
        current_time = datetime.utcnow()
        key = f"{user_id}:{endpoint}:{current_time.hour}"
        
        if key not in self.rate_limits:
            self.rate_limits[key] = 0
        
        self.rate_limits[key] += 1
        
        # Clean old entries
        if len(self.rate_limits) > 10000:
            old_keys = [k for k in self.rate_limits.keys() 
                       if int(k.split(':')[-1]) < current_time.hour - 1]
            for old_key in old_keys:
                del self.rate_limits[old_key]
        
        return self.rate_limits[key] <= limit
    
    def generate_api_token(self, anonymous_id: str, permissions: List[str], expires_in: int = 3600) -> str:
        """Generate JWT token for API access"""
        payload = {
            'anonymous_id': anonymous_id,
            'permissions': permissions,
            'type': 'api_key',
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow()
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

# Global API manager
api_manager = APIManager()

# Dependency functions
async def get_authenticated_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    return await api_manager.authenticate_request(credentials)

def require_permission(permission: str):
    """Dependency factory for permission requirements"""
    async def _check_permission(user_context: Dict = Depends(get_authenticated_user)):
        if not await api_manager.check_permission(user_context, permission):
            raise HTTPException(status_code=403, detail=f"Permission '{permission}' required")
        return user_context
    return _check_permission

# Course Management Endpoints
@app.post("/api/v1/courses/upload", response_model=Dict[str, Any])
async def upload_course(
    course_data: CourseUpload,
    background_tasks: BackgroundTasks,
    user_context: Dict = Depends(require_permission('upload_courses'))
):
    """Upload a single course"""
    try:
        # Process course upload
        course_submission = {
            'id': str(uuid.uuid4()),
            'title': course_data.title,
            'description': course_data.description,
            'category': course_data.category,
            'tags': course_data.tags,
            'anonymous_contributor': user_context['anonymous_id'],
            'file_attachments': course_data.files,
            'metadata': course_data.metadata,
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Store in database
        await supabase_client.execute_command(
            """
            INSERT INTO course_submissions (
                id, title, description, category, anonymous_contributor,
                file_attachments, metadata, status, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            course_submission['id'], course_submission['title'], 
            course_submission['description'], course_submission['category'],
            course_submission['anonymous_contributor'], 
            json.dumps(course_submission['file_attachments']),
            json.dumps(course_submission['metadata']),
            course_submission['status'], course_submission['created_at']
        )
        
        # Track analytics event
        background_tasks.add_task(
            analytics_engine.track_event,
            user_context['anonymous_id'],
            'api_course_upload',
            {'course_id': course_submission['id'], 'via_api': True}
        )
        
        return {
            'success': True,
            'course_id': course_submission['id'],
            'status': 'submitted_for_review',
            'message': 'Course uploaded successfully and queued for review'
        }
        
    except Exception as e:
        logger.error(f"Course upload API error: {e}")
        raise HTTPException(status_code=500, detail="Course upload failed")

@app.post("/api/v1/courses/bulk-upload", response_model=Dict[str, Any])
async def bulk_upload_courses(
    bulk_data: BulkCourseUpload,
    background_tasks: BackgroundTasks,
    user_context: Dict = Depends(require_permission('upload_courses'))
):
    """Bulk course upload with progress tracking"""
    try:
        # Validate contributor ID matches authenticated user
        if bulk_data.anonymous_contributor_id != user_context['anonymous_id']:
            # Allow admins to upload on behalf of others
            if not user_context['permissions'].get('manage_users', False):
                raise HTTPException(status_code=403, detail="Cannot upload for other users")
        
        # Import bulk operations manager
        from core.bulk_operations import bulk_operations_manager, BulkCourseData
        
        # Convert to BulkCourseData objects
        course_data_list = []
        for course in bulk_data.courses:
            course_data = BulkCourseData(
                title=course.title,
                description=course.description,
                category=course.category,
                tags=course.tags if hasattr(course, 'tags') else [],
                files=course.files,
                metadata=course.metadata
            )
            course_data_list.append(course_data)
        
        # Execute bulk upload using REST API
        result = await bulk_operations_manager.bulk_upload_courses(
            courses=course_data_list,
            contributor_anonymous_id=bulk_data.anonymous_contributor_id,
            batch_metadata=getattr(bulk_data, 'bulk_upload_metadata', {})
        )
        
        # Format results for API response
        processed_courses = [
            {
                'course_id': course_id,
                'title': course_data_list[i].title if i < len(course_data_list) else 'Unknown',
                'status': 'queued_for_review'
            }
            for i, course_id in enumerate(result.course_ids)
        ]
        
        failed_courses = [
            {
                'title': error.get('course_title', 'Unknown'),
                'error': error['error']
            }
            for error in result.errors
        ]
        
        batch_id = result.batch_id
        
        # Track batch upload event
        background_tasks.add_task(
            analytics_engine.track_event,
            user_context['anonymous_id'],
            'api_bulk_upload',
            {
                'batch_id': batch_id,
                'total_courses': len(bulk_data.courses),
                'successful': len(processed_courses),
                'failed': len(failed_courses)
            }
        )
        
        return {
            'success': True,
            'batch_id': batch_id,
            'courses_processed': len(processed_courses),
            'courses_failed': len(failed_courses),
            'processed_courses': processed_courses,
            'failed_courses': failed_courses,
            'message': f'Bulk upload completed: {len(processed_courses)} successful, {len(failed_courses)} failed'
        }
        
    except Exception as e:
        logger.error(f"Bulk upload API error: {e}")
        raise HTTPException(status_code=500, detail="Bulk upload failed")

# User Management Endpoints
@app.get("/api/v1/users/search", response_model=Dict[str, Any])
async def search_users_api(
    search_request: UserSearch,
    user_context: Dict = Depends(require_permission('manage_users'))
):
    """Search users with advanced criteria"""
    try:
        # Rate limiting check
        if not await api_manager.check_rate_limit(user_context['anonymous_id'], 'user_search', 50):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        search_results = await advanced_user_manager.search_users(
            search_request.search_criteria,
            user_context['anonymous_id']
        )
        
        if 'error' in search_results:
            raise HTTPException(status_code=400, detail=search_results['error'])
        
        return {
            'success': True,
            'results': search_results,
            'api_version': '1.0'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User search API error: {e}")
        raise HTTPException(status_code=500, detail="User search failed")

@app.post("/api/v1/users/bulk-operation", response_model=Dict[str, Any])
async def bulk_user_operation_api(
    operation_request: BulkUserOperation,
    background_tasks: BackgroundTasks,
    user_context: Dict = Depends(require_permission('manage_users'))
):
    """Perform bulk operations on users"""
    try:
        # Additional permission checks based on operation
        if operation_request.operation == 'update_role' and not user_context['permissions'].get('manage_roles', False):
            raise HTTPException(status_code=403, detail="Role management permission required")
        
        results = await advanced_user_manager.bulk_user_operations(
            operation_request.operation,
            operation_request.user_list,
            operation_request.operation_params,
            user_context['anonymous_id']
        )
        
        if 'error' in results:
            raise HTTPException(status_code=400, detail=results['error'])
        
        # Track bulk operation
        background_tasks.add_task(
            analytics_engine.track_event,
            user_context['anonymous_id'],
            'api_bulk_user_operation',
            {
                'operation': operation_request.operation,
                'user_count': len(operation_request.user_list),
                'success_rate': (results['successful'] / results['total_users']) * 100
            }
        )
        
        return {
            'success': True,
            'operation_results': results,
            'api_version': '1.0'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk user operation API error: {e}")
        raise HTTPException(status_code=500, detail="Bulk operation failed")

# Analytics Endpoints
@app.get("/api/v1/analytics/community-health", response_model=Dict[str, Any])
async def get_community_analytics_api(
    timeframe: str = "7d",
    metrics: Optional[str] = None,
    user_context: Dict = Depends(require_permission('view_analytics'))
):
    """Get community health metrics"""
    try:
        # Parse requested metrics
        requested_metrics = metrics.split(',') if metrics else None
        
        overview = await analytics_engine.get_community_overview(timeframe, user_context['role'])
        
        if 'error' in overview:
            raise HTTPException(status_code=500, detail="Analytics unavailable")
        
        # Filter metrics if specific ones requested
        if requested_metrics:
            filtered_overview = {}
            for metric in requested_metrics:
                if metric in overview:
                    filtered_overview[metric] = overview[metric]
            overview = filtered_overview
        
        return {
            'success': True,
            'community_health': overview,
            'api_version': '1.0',
            'generated_at': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analytics API error: {e}")
        raise HTTPException(status_code=500, detail="Analytics retrieval failed")

# Announcement Endpoints
@app.post("/api/v1/announcements/create", response_model=Dict[str, Any])
async def create_announcement_api(
    announcement_request: AnnouncementCreate,
    background_tasks: BackgroundTasks,
    user_context: Dict = Depends(require_permission('manage_users'))
):
    """Create targeted announcement"""
    try:
        announcement = await targeted_announcement_manager.create_announcement(
            user_context['anonymous_id'],
            announcement_request.title,
            announcement_request.content,
            announcement_request.targeting_rules,
            announcement_request.scheduling,
            announcement_request.options
        )
        
        if 'error' in announcement:
            raise HTTPException(status_code=400, detail=announcement['error'])
        
        # Auto-send if immediate delivery requested
        if announcement_request.scheduling.get('send_immediately', False):
            background_tasks.add_task(
                targeted_announcement_manager.send_announcement,
                announcement['id'],
                user_context['anonymous_id']
            )
        
        return {
            'success': True,
            'announcement': announcement,
            'api_version': '1.0'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Announcement API error: {e}")
        raise HTTPException(status_code=500, detail="Announcement creation failed")

# API Key Management
@app.post("/api/v1/auth/create-api-key", response_model=Dict[str, Any])
async def create_api_key(
    api_key_request: APIKey,
    user_context: Dict = Depends(require_permission('system_admin'))
):
    """Create new API key for external integrations"""
    try:
        # Generate API token
        token = api_manager.generate_api_token(
            user_context['anonymous_id'],
            api_key_request.permissions,
            expires_in=86400 * 30 if not api_key_request.expires_at else int(
                (api_key_request.expires_at - datetime.utcnow()).total_seconds()
            )
        )
        
        # Store API key metadata
        api_key_id = str(uuid.uuid4())
        await supabase_client.execute_command(
            """
            INSERT INTO api_keys (
                id, name, creator_anonymous_id, permissions, 
                rate_limit, expires_at, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            api_key_id, api_key_request.name, user_context['anonymous_id'],
            json.dumps(api_key_request.permissions), api_key_request.rate_limit,
            api_key_request.expires_at.isoformat() if api_key_request.expires_at else None,
            datetime.utcnow().isoformat()
        )
        
        return {
            'success': True,
            'api_key_id': api_key_id,
            'token': token,
            'permissions': api_key_request.permissions,
            'rate_limit': api_key_request.rate_limit,
            'message': 'API key created successfully. Store the token securely.'
        }
        
    except Exception as e:
        logger.error(f"API key creation error: {e}")
        raise HTTPException(status_code=500, detail="API key creation failed")

# Health Check
@app.get("/api/v1/health")
async def health_check():
    """API health check endpoint"""
    try:
        # Check database connectivity
        db_health = await supabase_client.execute_query("SELECT 1 as status")
        db_status = "healthy" if db_health else "unhealthy"
        
        return {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0',
            'database': db_status,
            'services': {
                'authentication': 'healthy',
                'api_endpoints': 'healthy',
                'rate_limiting': 'healthy'
            }
        }
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse(
            status_code=503,
            content={
                'status': 'unhealthy',
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e)
            }
        )

# Error Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'success': False,
            'error': exc.detail,
            'status_code': exc.status_code,
            'timestamp': datetime.utcnow().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled API exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            'success': False,
            'error': 'Internal server error',
            'status_code': 500,
            'timestamp': datetime.utcnow().isoformat()
        }
    )

# Startup/Shutdown Events
@app.on_event("startup")
async def startup_event():
    """Initialize API services on startup"""
    logger.info("ChessMaster API starting up...")
    # Initialize any necessary services

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on API shutdown"""
    logger.info("ChessMaster API shutting down...")
    # Cleanup resources

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)