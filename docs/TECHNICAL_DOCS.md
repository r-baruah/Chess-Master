# ChessMaster Bot - Technical Documentation

## Project Overview

ChessMaster is a sophisticated Telegram bot built with Python and Pyrogram for managing and distributing chess educational courses. The system allows administrators to upload multi-file courses and automatically share them with users through a streamlined interface featuring token verification, premium subscriptions, and advanced search capabilities.

## Architecture Overview

### System Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram API  │◄──►│   ChessMaster   │◄──►│     MongoDB     │
│                 │    │      Bot        │    │   Database      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Web Server    │
                       │   (aiohttp)     │
                       └─────────────────┘
```

### Core Architecture Layers

1. **Presentation Layer**: Telegram bot interface with inline keyboards and commands
2. **Application Layer**: Business logic distributed across plugins
3. **Data Access Layer**: MongoDB with Motor async driver
4. **Infrastructure Layer**: Docker, logging, and deployment configurations

## Technical Stack

### Core Dependencies

| Component | Version | Purpose |
|-----------|---------|---------|
| **Pyrogram** | 2.0.106 | Telegram Bot API framework |
| **Motor** | 3.2.0 | Asynchronous MongoDB driver |
| **aiohttp** | 3.8.5 | Web server for health checks |
| **pymongo** | 4.5.0 | MongoDB operations |
| **python-dotenv** | 1.0.0 | Environment variable management |

### Development Dependencies

- **tgcrypto**: Telegram encryption utilities
- **marshmallow**: Data validation and serialization
- **aiofiles**: Asynchronous file operations
- **pytz**: Timezone handling

## Project Structure

```
ChessMaster/
├── bot.py                 # Main application entry point
├── info.py                # Configuration and environment variables
├── Script.py              # Message templates and UI text
├── utils.py               # Utility functions and helpers
├── logging.conf           # Logging configuration
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker container configuration
├── docker-compose.yml     # Multi-container orchestration
├── render.yaml            # Render deployment configuration
├── app.json               # Heroku deployment configuration
├── LICENSE                # Project license
├── README.md              # User-facing documentation
│
├── database/              # Data access layer
│   ├── courses_db.py      # Course CRUD operations
│   ├── users_chats_db.py  # User and chat management
│   ├── token_db.py        # Token verification system
│   ├── url_shortener.py   # URL shortening utilities
│   ├── multi_db.py        # Database redundancy support
│   ├── db_helpers.py      # Database connection helpers
│   └── token_verification.py # Token validation logic
│
└── plugins/               # Business logic layer
    ├── commands.py        # Core bot commands and handlers
    ├── course_manager.py  # Course creation and management
    ├── inline.py          # Inline search functionality
    ├── premium.py         # Premium user management
    └── token_commands.py  # Token-related commands
```

## Database Schema

### Collections Overview

The application uses MongoDB with the following main collections:

#### 1. Courses Collection (`courses`)
```javascript
{
  "_id": ObjectId("..."),
  "course_id": "uuid-string",           // Unique course identifier
  "course_name": "Advanced Chess Tactics",
  "added_by": 123456789,                // Admin user ID
  "added_on": ISODate("2024-01-15T10:30:00Z"),
  "file_count": 5,                      // Number of files in course
  "banner_id": "file_id_string",         // Telegram file ID for banner
  "total_size": 104857600,              // Total size in bytes
  "premium_only": false                 // Premium access requirement
}
```

#### 2. Course Files Collection (`course_files`)
```javascript
{
  "_id": ObjectId("..."),
  "course_id": "uuid-string",
  "file_id": "telegram_file_id",
  "file_name": "Chapter 1 - Opening Principles.pdf",
  "file_size": 20971520,                // File size in bytes
  "caption": "Chapter 1 content with custom formatting",
  "file_order": 1                       // Display order
}
```

#### 3. Users Collection (`users`)
```javascript
{
  "_id": 123456789,                     // Telegram user ID
  "first_name": "John",
  "username": "john_chess",
  "is_premium": true,
  "premium_expiry": ISODate("2024-12-31T23:59:59Z"),
  "join_date": ISODate("2024-01-01T00:00:00Z"),
  "last_active": ISODate("2024-01-15T10:30:00Z"),
  "verified_tokens": ["token123", "token456"]
}
```

#### 4. Verification Tokens Collection (`verification_tokens`)
```javascript
{
  "_id": ObjectId("..."),
  "token_code": "ABC123XYZ",
  "created_by": 123456789,
  "created_at": ISODate("2024-01-15T10:00:00Z"),
  "max_uses": 100,
  "current_uses": 23,
  "expires_at": ISODate("2024-02-15T10:00:00Z"),
  "is_active": true,
  "description": "January batch access"
}
```

### Database Operations

#### Connection Management
```python
# From database/db_helpers.py
from motor.motor_asyncio import AsyncIOMotorClient

def get_mongo_client(uri: str) -> AsyncIOMotorClient:
    return AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
```

#### Key Operations

**Course Management:**
- `save_course(course_data)`: Insert new course document
- `get_course_by_id(course_id)`: Retrieve course by UUID
- `search_courses(query)`: Fuzzy search by course name
- `delete_course(course_id)`: Remove course and associated files

**File Management:**
- `save_course_file(file_data)`: Store file metadata
- `get_course_files(course_id)`: Retrieve all files for a course

## Core Modules Analysis

### 1. Main Application (`bot.py`)

**Responsibilities:**
- Initialize Pyrogram client with configuration
- Load and manage plugins dynamically
- Handle application startup and shutdown
- Provide web server for health checks
- Manage user session and global state

**Key Classes:**
```python
class Bot(Client):
    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5
        )
```

**Startup Sequence:**
1. Initialize Pyrogram client
2. Load banned users and premium users
3. Send startup notification to log channel
4. Load plugins dynamically
5. Start web server for health monitoring

### 2. Configuration Management (`info.py`)

**Environment Variables:**
```python
# Bot Configuration
BOT_TOKEN = environ.get('BOT_TOKEN')
API_ID = int(environ.get('API_ID'))
API_HASH = environ.get('API_HASH')

# Database Configuration
DATABASE_URI = environ.get('DATABASE_URI')
DATABASE_NAME = environ.get('DATABASE_NAME', "chess_courses_bot")

# Feature Flags
PREMIUM_ENABLED = environ.get('PREMIUM_ENABLED', 'False').lower() == 'true'
TOKEN_VERIFICATION_ENABLED = environ.get('TOKEN_VERIFICATION_ENABLED', 'False').lower() == 'true'
SHORTENER_ENABLED = environ.get('SHORTENER_ENABLED', 'False').lower() == 'true'
```

### 3. Command Handler (`plugins/commands.py`)

**Command Routing:**
- `/start`: Welcome message with deep link handling
- `/help`: Interactive help with category selection
- `/stats`: Administrative statistics (admin only)
- `/broadcast`: Mass messaging to all users (admin only)

**Deep Link Processing:**
```python
if param.startswith('course_'):
    course_id = param.split('_')[1]
    # Process course download with verification checks
```

**Callback Query Handling:**
- `course_action_*`: Course management actions
- `broadcast_*`: Broadcast confirmation flow
- `premium_info`: Premium status display

### 4. Course Management (`plugins/course_manager.py`)

**Course Creation Workflow:**

1. **Initialization**: `/addcourse` command starts conversation
2. **Name Collection**: Bot prompts for course name
3. **Link Collection**: Admin provides Telegram message links
4. **File Processing**: Bot fetches files from provided links
5. **Banner Addition**: Optional banner image collection
6. **Confirmation**: Review and publish course

**State Management:**
```python
# Conversation states
WAITING_COURSE_NAME = 1
WAITING_COURSE_LINKS = 2
WAITING_BANNER = 3
CONFIRM_COURSE = 4
```

**Link Processing Logic:**
```python
link_pattern = r"https?://t\.me/(?:c/)?(\S+)/(\d+)"
found_links = re.findall(link_pattern, message.text)
```

### 5. Inline Search (`plugins/inline.py`)

**Inline Query Handling:**
```python
@Client.on_inline_query()
async def answer_inline_query(client, inline_query):
    query = inline_query.query.strip()
    if not query:
        return await inline_query.answer([])
```

**Search Results:**
- Returns up to 50 course results
- Displays course name, file count, and size
- Provides direct download buttons

### 6. Premium System (`plugins/premium.py`)

**Premium Features:**
- Access to exclusive courses
- Priority customer support
- Faster download speeds
- Advanced search options

**Premium User Management:**
```python
async def set_premium_user(user_id, days):
    expiry_date = datetime.now() + timedelta(days=days)
    await db.update_user(user_id, {
        "is_premium": True,
        "premium_expiry": expiry_date
    })
```

### 7. Token System (`plugins/token_commands.py`)

**Token Lifecycle:**
1. **Creation**: Admin generates tokens with usage limits
2. **Distribution**: Tokens shared with users
3. **Verification**: Users verify access with `/token` command
4. **Tracking**: Usage monitoring and expiration

**Token Structure:**
```python
token_doc = {
    "token_code": code,
    "created_by": admin_id,
    "max_uses": max_uses,
    "expires_at": expiry_date,
    "is_active": True
}
```

## Data Flow Architecture

### Course Upload Flow

```
Admin Command → Link Collection → File Fetching → Banner Addition → Database Storage → Public Announcement
     ↓              ↓              ↓              ↓              ↓              ↓
/addcourse    Message Links   Telegram API   Photo Upload   MongoDB Insert   Channel Post
```

### User Download Flow

```
User Request → Token Check → Premium Check → File Retrieval → Telegram Send
     ↓            ↓            ↓            ↓            ↓
   /start      Database      Database    MongoDB       API Call
course_XXX    Lookup        Lookup       Query         send_cached_media
```

### Search Flow

```
Query Input → Text Processing → Database Search → Result Formatting → Inline Display
     ↓            ↓              ↓              ↓              ↓
Inline Query   Fuzzy Match    MongoDB       Template       Telegram API
               Regex         Aggregation    Rendering      Results
```

## API Integration Points

### Telegram Bot API

**Key Methods Used:**
- `send_message()`: Text communication
- `send_photo()`: Image display
- `send_cached_media()`: File distribution
- `get_messages()`: Link resolution
- `get_me()`: Bot identity verification

### MongoDB Operations

**Connection Pattern:**
```python
client = AsyncIOMotorClient(uri)
db = client[database_name]
collection = db[collection_name]
```

**Query Patterns:**
- Point queries: `find_one({'course_id': course_id})`
- Range queries: `find({'course_name': regex})`
- Aggregation: `count_documents(filter)`

## Deployment Architecture

### Containerization (Docker)

**Dockerfile Structure:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

**Multi-Container Setup:**
```yaml
# docker-compose.yml
version: '3.8'
services:
  chessmaster:
    build: .
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - DATABASE_URI=${DATABASE_URI}
    ports:
      - "8080:8080"
```

### Cloud Deployment Options

#### Render Deployment
- **render.yaml**: Infrastructure as Code
- **Health checks**: Web server endpoint monitoring
- **Environment management**: Secure variable storage

#### Heroku Deployment
- **app.json**: Heroku-specific configuration
- **Procfile**: Process definitions
- **Buildpacks**: Python runtime configuration

## Security Considerations

### Access Control
- **Admin verification**: User ID whitelist in `ADMINS`
- **Token verification**: Time-limited access codes
- **Premium gating**: Subscription-based content restrictions

### Data Protection
- **Environment variables**: Sensitive data externalized
- **Input validation**: Regex pattern matching for links
- **Rate limiting**: Built-in FloodWait handling

### Privacy Measures
- **Minimal data collection**: Only necessary user information
- **Opt-in premium features**: No forced data sharing
- **Transparent token usage**: Clear usage tracking

## Monitoring and Logging

### Logging Configuration

**Structured Logging:**
```python
# logging.conf
[loggers]
keys=root,chessmaster

[handlers]
keys=consoleHandler,fileHandler

[formatters]
keys=simpleFormatter,detailedFormatter
```

**Log Levels:**
- **INFO**: Normal operations and user interactions
- **WARNING**: Non-critical issues (rate limits, etc.)
- **ERROR**: Critical failures requiring attention
- **DEBUG**: Detailed debugging information

### Health Monitoring

**Web Server Endpoint:**
```python
async def handle_hello(request):
    return web.Response(text="Hello, World!")
```

**Database Health Checks:**
- Connection pool monitoring
- Query performance tracking
- Storage usage monitoring

## Performance Optimization

### Database Optimizations
- **Indexing**: Compound indexes on frequently queried fields
- **Pagination**: Cursor-based result limiting
- **Async operations**: Non-blocking database calls

### Caching Strategies
- **File metadata**: Cached course file information
- **User state**: In-memory session management
- **Search results**: Temporary result caching

### Resource Management
- **Connection pooling**: MongoDB connection reuse
- **Memory management**: Efficient file handling
- **Rate limiting**: Telegram API compliance

## Development Guidelines

### Code Style
- **PEP 8 compliance**: Standard Python formatting
- **Type hints**: Optional but encouraged
- **Docstrings**: Comprehensive function documentation

### Error Handling
```python
try:
    # Operation
    result = await risky_operation()
except SpecificError as e:
    logger.error(f"Specific error: {e}")
    await handle_error_gracefully()
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    await fallback_procedure()
```

### Testing Strategy
- **Unit tests**: Individual function testing
- **Integration tests**: Database and API interaction
- **Manual testing**: Telegram bot interaction verification

## Maintenance Procedures

### Regular Tasks
1. **Database cleanup**: Remove expired tokens and inactive users
2. **Log rotation**: Archive old log files
3. **Dependency updates**: Keep packages current and secure
4. **Performance monitoring**: Track response times and resource usage

### Backup Strategy
- **Database dumps**: Regular MongoDB exports
- **Configuration backups**: Environment variable documentation
- **Code versioning**: Git-based version control

## Troubleshooting Guide

### Common Issues

**Bot Not Responding:**
1. Check bot token validity
2. Verify API credentials
3. Review network connectivity
4. Check log files for errors

**Database Connection Issues:**
1. Verify MongoDB URI format
2. Check network access to database
3. Validate authentication credentials
4. Monitor connection pool limits

**File Upload Problems:**
1. Confirm bot has channel access
2. Check file size limits
3. Verify message link formats
4. Review Telegram API rate limits

### Debug Commands
```bash
# Check bot status
curl http://localhost:8080

# View recent logs
tail -f logs/bot.log

# Database connection test
python -c "from database.db_helpers import get_mongo_client; print('Connected' if get_mongo_client(uri) else 'Failed')"
```

## Future Enhancements

### Planned Features
- **Advanced analytics**: Usage statistics and reporting
- **Multi-language support**: Internationalization framework
- **Webhook integration**: Real-time notification system
- **Advanced caching**: Redis integration for performance
- **Mobile app**: Native mobile application companion

### Technical Improvements
- **Microservices architecture**: Component separation
- **API versioning**: RESTful API for external integrations
- **Automated testing**: Comprehensive test suite
- **CI/CD pipeline**: Automated deployment and testing

---

## Contributing

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Submit a pull request

### Code Review Process
- All changes require review
- Maintain code quality standards
- Update documentation for new features
- Test thoroughly before merging

### Documentation Updates
- Keep README.md user-focused
- Update this technical document for architectural changes
- Maintain changelog for version releases

---

*This technical documentation is maintained alongside the codebase. Please update it when making significant architectural changes.*
