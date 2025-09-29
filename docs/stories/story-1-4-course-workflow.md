# Story 1.4: Contributor Course Workflow Enhancement

**Epic**: ChessMaster Community Platform Enhancement  
**Story ID**: CM-004  
**Priority**: Medium  
**Estimated Effort**: 1.5 weeks  
**Dependencies**: Story 1.1 (Infrastructure), Story 1.2 (File Management), Story 1.3 (RBAC)

## User Story
As a **course contributor**,  
I want **streamlined anonymous course upload with volunteer review integration**,  
so that **I can easily share educational content while maintaining quality standards and privacy**.

## Acceptance Criteria

### AC1: Enhanced Course Upload Workflow
- [ ] Improved `/addcourse` command with guided step-by-step process
- [ ] Progress tracking and status indicators throughout upload process
- [ ] Input validation and format verification for all course components
- [ ] Upload resumption capability if process is interrupted
- [ ] Batch file upload support with progress indicators

### AC2: Automatic Review Queue Integration
- [ ] Courses automatically queued for volunteer review after submission
- [ ] Status notifications sent to contributors about review progress
- [ ] Queue priority system based on contributor reputation and course type
- [ ] Review assignment integration with volunteer workload distribution
- [ ] Escalation system for delayed reviews

### AC3: Review Status Tracking System
- [ ] Real-time status updates for contributors on course review progress
- [ ] Anonymous feedback system for volunteer reviewer comments
- [ ] Status change notifications (submitted, under review, approved, rejected)
- [ ] Contributor dashboard showing all submitted courses and their status
- [ ] Revision request and resubmission workflow

### AC4: Future Integration API Endpoints
- [ ] RESTful API endpoints for external course upload systems
- [ ] Bulk upload capabilities maintaining anonymity and review workflows
- [ ] API authentication using anonymous tokens and rate limiting
- [ ] Webhook support for external system notifications
- [ ] API documentation and integration examples

### AC5: Course Metadata Management System
- [ ] Enhanced categorization system with tags and difficulty levels
- [ ] Course relationship mapping (prerequisites, sequences, related content)
- [ ] Metadata validation and standardization
- [ ] Search optimization with indexed course attributes
- [ ] Version control for course updates and revisions

## Integration Verification

### IV1: Current Workflow Compatibility
**Test**: Existing single-course upload workflow continues with enhancements
- [ ] All existing `/addcourse` functionality preserved
- [ ] Current admin course management commands work without modification
- [ ] File upload and storage processes integrate with multi-channel system
- [ ] Course approval notifications work with enhanced review system
- [ ] No disruption to existing user experience during transition

### IV2: Automated Announcement Integration
**Test**: Approved courses trigger existing announcement system
- [ ] Course publication announcements sent to configured channels
- [ ] Announcement content includes enhanced metadata and categorization
- [ ] Anonymous contributor attribution preserved in announcements
- [ ] Announcement timing coordinated with course availability
- [ ] Existing announcement formatting and style maintained

### IV3: Anonymous Attribution Protection
**Test**: Course metadata stored with complete privacy protection
- [ ] No traceability from published courses to contributor identities
- [ ] Anonymous ID system integrated with course attribution
- [ ] Review feedback delivered without revealing reviewer identity
- [ ] Course statistics and analytics preserve contributor anonymity
- [ ] API endpoints maintain anonymity for external integrations

## Technical Implementation Notes

### Enhanced Course Upload Flow
```python
class EnhancedCourseUploader:
    def __init__(self, supabase_client, redis_client, channel_manager):
        self.supabase = supabase_client
        self.redis = redis_client
        self.channels = channel_manager
        
    async def start_course_upload(self, user_id: int, anonymous_id: str):
        """Initialize enhanced course upload process"""
        upload_session = {
            'user_id': user_id,
            'anonymous_id': anonymous_id,
            'status': 'collecting_metadata',
            'step': 1,
            'total_steps': 5,
            'course_data': {},
            'files': [],
            'started_at': datetime.utcnow().isoformat()
        }
        
        session_key = f"course_upload:{user_id}"
        await self.redis.setex(session_key, 3600, json.dumps(upload_session))
        
        return await self.show_upload_progress(user_id, upload_session)
        
    async def process_upload_step(self, user_id: int, step_data: dict):
        """Process individual upload step with validation"""
        session = await self.get_upload_session(user_id)
        
        if session['step'] == 1:  # Course title and description
            validated_data = await self.validate_course_metadata(step_data)
            session['course_data'].update(validated_data)
            
        elif session['step'] == 2:  # Category and tags
            session['course_data']['categories'] = step_data['categories']
            session['course_data']['tags'] = step_data['tags']
            
        elif session['step'] == 3:  # Files upload
            files = await self.process_course_files(step_data['files'])
            session['files'].extend(files)
            
        elif session['step'] == 4:  # Review and confirm
            return await self.show_course_preview(user_id, session)
            
        elif session['step'] == 5:  # Final submission
            return await self.submit_for_review(user_id, session)
            
        # Update session and continue
        session['step'] += 1
        await self.update_upload_session(user_id, session)
        return await self.show_upload_progress(user_id, session)
```

### Review Queue Integration
```python
class ReviewQueueManager:
    async def submit_course_for_review(self, course_id: str, anonymous_id: str):
        """Submit course to volunteer review queue"""
        review_entry = {
            'course_id': course_id,
            'contributor_id': anonymous_id,
            'status': 'pending_review',
            'priority': await self.calculate_priority(anonymous_id),
            'submitted_at': datetime.utcnow().isoformat(),
            'assigned_reviewer': None
        }
        
        # Add to review queue
        result = await self.supabase.table('reviews').insert(review_entry).execute()
        
        # Assign to available volunteer
        reviewer_id = await self.volunteer_manager.assign_course_to_reviewer(course_id)
        
        # Notify contributor
        await self.notify_review_submission(anonymous_id, course_id)
        
        return result.data[0]
        
    async def update_review_status(self, course_id: str, status: str, feedback: str = None):
        """Update course review status and notify contributor"""
        review = await self.get_review_by_course(course_id)
        
        update_data = {
            'status': status,
            'reviewed_at': datetime.utcnow().isoformat()
        }
        
        if feedback:
            update_data['feedback'] = feedback
            
        await self.supabase.table('reviews').update(update_data).eq('course_id', course_id).execute()
        
        # Notify contributor of status change
        await self.notify_status_change(review['contributor_id'], course_id, status, feedback)
```

### API Integration Framework
```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer

app = FastAPI(title="ChessMaster Course API")
security = HTTPBearer()

@app.post("/api/v1/courses/bulk-upload")
async def bulk_upload_courses(
    courses_data: List[CourseUploadRequest],
    token: str = Depends(security)
):
    """Bulk course upload endpoint for external integrations"""
    # Validate API token and get anonymous contributor ID
    anonymous_id = await validate_api_token(token)
    
    results = []
    for course_data in courses_data:
        try:
            # Process course with same validation as manual upload
            course_id = await process_external_course_upload(course_data, anonymous_id)
            results.append({
                'status': 'success',
                'course_id': course_id,
                'review_queue_position': await get_queue_position(course_id)
            })
        except Exception as e:
            results.append({
                'status': 'error',
                'error': str(e),
                'course_data': course_data.title
            })
    
    return {'uploaded_courses': results}
```

### Course Metadata Schema
```sql
-- Enhanced courses table
ALTER TABLE courses ADD COLUMN IF NOT EXISTS category VARCHAR(100);
ALTER TABLE courses ADD COLUMN IF NOT EXISTS tags TEXT[];
ALTER TABLE courses ADD COLUMN IF NOT EXISTS difficulty_level INTEGER DEFAULT 1;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS prerequisites TEXT[];
ALTER TABLE courses ADD COLUMN IF NOT EXISTS estimated_duration INTEGER; -- in minutes
ALTER TABLE courses ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS parent_course_id UUID REFERENCES courses(id);

-- Course tags table for better organization
CREATE TABLE IF NOT EXISTS course_tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    course_id UUID REFERENCES courses(id) ON DELETE CASCADE,
    tag VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Definition of Done
- [ ] All acceptance criteria completed and tested
- [ ] Integration verification tests pass
- [ ] Enhanced upload workflow operational with progress tracking
- [ ] Review queue integration working with volunteer assignment
- [ ] API endpoints documented and tested for external integrations
- [ ] Course metadata system operational with search optimization
- [ ] Performance benchmarks met for upload and review processes
- [ ] Anonymous attribution verified throughout all workflows

## Dependencies
- Story 1.1: Anonymous ID system and Supabase integration
- Story 1.2: Multi-channel file management for course files
- Story 1.3: Role-based access control for contributor permissions
- Volunteer assignment system from role management

## Risks and Mitigation
- **Upload Process Interruption**: Session persistence and resumption capability
- **Review Queue Bottlenecks**: Volunteer workload balancing and escalation
- **API Security**: Token-based authentication and rate limiting
- **Metadata Consistency**: Validation and standardization systems

---

**Next Story**: Story 1.5 - Volunteer Review and Management System

---

## Dev Agent Record

### Tasks Completed
- [x] **Task 1: Enhanced Course Upload Workflow (AC1)**
  - [x] Created `EnhancedCourseUploader` class with step-by-step guided process
  - [x] Implemented progress tracking and session management
  - [x] Added comprehensive input validation for all course components
  - [x] Built upload resumption capability with Redis persistence
  - [x] Added batch file upload support with progress indicators

- [x] **Task 2: Automatic Review Queue Integration (AC2)**
  - [x] Created `ReviewQueueManager` for automatic review queue management
  - [x] Implemented contributor reputation-based priority system
  - [x] Added review assignment integration with volunteer system
  - [x] Built escalation system for delayed reviews
  - [x] Added status notifications for contributors

- [x] **Task 3: Review Status Tracking System (AC3)**
  - [x] Implemented real-time status tracking for contributors
  - [x] Created anonymous feedback system for reviewer comments
  - [x] Built contributor dashboard with course status overview
  - [x] Added revision request and resubmission workflow
  - [x] Implemented status change notifications

- [x] **Task 4: Future Integration API Endpoints (AC4)**
  - [x] Created FastAPI-based `course_api.py` with RESTful endpoints
  - [x] Implemented bulk upload capabilities with anonymity preservation
  - [x] Added API authentication with anonymous tokens and rate limiting
  - [x] Built webhook support for external system notifications
  - [x] Created comprehensive API documentation structure

- [x] **Task 5: Course Metadata Management System (AC5)**
  - [x] Created `CourseMetadataManager` with enhanced categorization
  - [x] Implemented course relationship mapping (prerequisites, sequences, related)
  - [x] Added metadata validation and standardization
  - [x] Built search optimization with indexed attributes
  - [x] Implemented version control for course updates and revisions

### Debug Log References
- Enhanced course upload workflow tested with session persistence
- Review queue integration verified with priority calculation
- API endpoints tested for authentication and rate limiting
- Database migration successfully creates all required tables
- Course metadata validation working with comprehensive error handling

### Completion Notes
- All acceptance criteria have been implemented and tested
- Database schema enhanced with new tables for metadata, reviews, and relationships
- API endpoints ready for external integrations with proper authentication
- Enhanced plugin integrates seamlessly with existing course management
- Session management enables upload resumption and progress tracking

### File List
**New Files Created:**
- `core/enhanced_course_uploader.py` - Main enhanced upload workflow system
- `core/review_queue_manager.py` - Review queue and status tracking
- `core/course_metadata_manager.py` - Metadata management and search
- `core/course_api.py` - RESTful API for external integrations  
- `database/migrations/enhanced_course_workflow_schema.py` - Database migration
- `plugins/enhanced_course_manager.py` - Enhanced course management plugin
- `tests/test_story_1_4_enhanced_course_workflow.py` - Comprehensive test suite

**Files Modified:**
- `docs/stories/story-1-4-course-workflow.md` - Updated with completion status

### Change Log
- **2024-01-XX**: Implemented enhanced course upload workflow with session management
- **2024-01-XX**: Created review queue system with priority-based assignment
- **2024-01-XX**: Built comprehensive metadata management with relationships
- **2024-01-XX**: Developed RESTful API for external integrations
- **2024-01-XX**: Created database migration with all required tables
- **2024-01-XX**: Integrated enhanced plugin with existing course management
- **2024-01-XX**: Added comprehensive test coverage for all components

### Status
**Ready for Review** - All tasks completed, tested, and documented