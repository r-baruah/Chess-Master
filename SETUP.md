# ChessMaster Development Setup Guide

## 🎯 Quick Start

This guide will help you set up the development environment for the ChessMaster Community Platform Enhancement project.

## 📋 Prerequisites

### Required Software
- **Python 3.9+** (with asyncio support)
- **Git** (for version control)
- **Docker & Docker Compose** (for containerized development)
- **Redis** (local or Docker instance)

### Required Accounts & Services
- **Supabase Account** - Free tier sufficient for development
- **Telegram Bot Token** - From [@BotFather](https://t.me/BotFather)
- **Multiple Telegram Channels** - For file hosting and backups
- **GitHub Account** - For repository access

## 🛠️ Environment Setup

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/ChessMaster.git
cd ChessMaster
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)  
source venv/bin/activate
```

### 3. Install Dependencies
```bash
# Install Python packages
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

### 4. Setup Supabase Project

#### Create Supabase Project
1. Visit [supabase.com](https://supabase.com)
2. Create new project
3. Note your Project URL and anon key

#### Setup Database Schema
```bash
# Run database migrations
python setup/migrate_to_supabase.py
```

### 5. Configure Environment Variables
Create `.env` file from template:
```bash
cp .env-example .env
```

Edit `.env` with your configuration:
```env
# Bot Configuration
BOT_TOKEN=your_bot_token_here
API_ID=your_api_id
API_HASH=your_api_hash

# Supabase Configuration  
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_anon_key_here

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Channel Configuration
PRIMARY_CHANNEL_ID=-1001234567890
BACKUP_CHANNEL_1=-1001234567891  
BACKUP_CHANNEL_2=-1001234567892

# Admin Configuration
ADMINS=123456789,987654321
LOG_CHANNEL=-1001234567893
```

### 6. Setup Development Channels

#### Create Telegram Channels
1. Create primary course storage channel
2. Create 2-3 backup channels  
3. Create log channel for development
4. Add your bot as admin to all channels

#### Configure Channel Permissions
```bash
# Verify bot has proper permissions
python setup/verify_channels.py
```

### 7. Start Development Services

#### Using Docker Compose (Recommended)
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f bot
```

#### Manual Setup
```bash
# Start Redis
redis-server

# Start bot (in separate terminal)
python bot.py
```

## 🧪 Development Workflow

### Running Tests
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_anonymous_id.py

# Run with coverage
python -m pytest --cov=. --cov-report=html
```

### Database Migrations
```bash
# Create new migration
python manage.py create_migration "description"

# Apply migrations
python manage.py migrate

# Rollback migration  
python manage.py rollback
```

### Code Quality
```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

## 📁 Project Structure

```
ChessMaster/
├── bot.py                    # Main bot file
├── core/                     # Core functionality
│   ├── anonymity.py         # Anonymous ID management
│   ├── roles.py             # Role-based access control
│   └── supabase_client.py   # Database connection
├── plugins/                  # Bot plugins  
│   ├── commands.py          # Command handlers
│   ├── course_manager.py    # Course management
│   └── admin.py             # Admin functions
├── database/                 # Database operations
│   ├── models.py            # Data models
│   ├── courses.py           # Course operations  
│   └── users.py             # User management
├── docs/                     # Documentation
│   ├── prd.md               # Product Requirements
│   ├── stories/             # User stories
│   └── api/                 # API documentation
├── tests/                    # Test files
├── setup/                    # Setup scripts
└── requirements.txt          # Dependencies
```

## 🐛 Troubleshooting

### Common Issues

#### Bot Not Responding
```bash
# Check bot token
python -c "from pyrogram import Client; print('Token valid')"

# Check permissions
python setup/verify_bot_permissions.py
```

#### Database Connection Issues  
```bash
# Test Supabase connection
python -c "from core.supabase_client import get_client; print('Connected')"

# Check table creation
python setup/verify_database.py
```

#### Channel Access Problems
```bash
# Verify channel permissions
python setup/check_channel_access.py

# Test file upload
python setup/test_file_storage.py
```

### Getting Help

1. **Check Logs**: Review bot and database logs for errors
2. **Run Diagnostics**: Use provided diagnostic scripts
3. **GitHub Issues**: Open issue with error details and logs
4. **Documentation**: Check docs/ folder for detailed guides

## 🚀 Production Deployment

### Environment Setup
```bash
# Build production image
docker build -t chessmaster:latest .

# Deploy with production config
docker-compose -f docker-compose.prod.yml up -d
```

### Health Monitoring
```bash
# Check system health
curl http://localhost:8080/health

# View metrics
curl http://localhost:8080/metrics
```

## 📚 Additional Resources

- **[PRD Documentation](./docs/prd.md)** - Complete product requirements
- **[Story Documentation](./docs/stories/)** - Detailed user stories  
- **[API Documentation](./docs/api/)** - Integration guides
- **[Development Roadmap](./docs/development-roadmap.md)** - Implementation timeline

---

**Ready to Develop**: Environment configured, services running, tests passing ✅