# ChessMaster Owner & Developer Guide

This document captures the technical blueprint behind the ChessMaster Community Bot. Keep it close—it’s the single source of truth for architecture, flows, features, and operational practices.

---

## 1. System Overview

### 1.1 Purpose
- Deliver a privacy-first platform for sharing and reviewing chess courses.
- Support anonymous contributors, volunteer reviewers, and large-scale course distribution.
- Provide admins with full visibility and control while preserving member privacy.

### 1.2 Key Goals
- **Anonymous contributions** → No real identities stored.
- **Scalable uploads** → Single and bulk (100+) course submissions.
- **Quality control** → Volunteer review workflow with detailed feedback.
- **Community analytics** → Track reviewer performance, course adoption, system health.
- **Resilience** → Supabase/Postgres backend, Redis caching, multi-bot token failover.

---

## 2. Architecture

### 2.1 High-Level Components

- **Telegram Bot (Pyrogram)** – Entry point for all user interactions.
- **Supabase (Postgres + REST)** – Primary database (courses, users, roles, logs, analytics).
- **Redis** – Optional cache for sessions and queues (falls back to in-memory if absent).
- **Telegram Channels** – File storage (private) and announcements (public).
- **Volunteer Review System** – Review queue, feedback handling, analytics.
- **Bulk Operations Engine** – Handles large course batches via REST.

### 2.2 Data Flow Summaries

#### Single Upload
1. Contributor runs `/addcourse`.
2. Guided wizard collects metadata, message links, and optional banner.
3. Files stored in private channel, metadata in Supabase.
4. Course enters review queue → reviewer approves or requests changes.
5. Approved courses published to public channels and searchable.

#### Bulk Upload
1. Contributor runs `/bulkupload` → chooses method (files/links/JSON).
2. Bot collects submissions → transforms into `BulkCourseData` records.
3. `bulk_operations.py` inserts courses via Supabase REST API.
4. Batch metadata logged (success/failure per course).
5. Review queue assignment triggered (priority based on upload quality).

#### Review Workflow
1. Reviewers call `/review_queue` to view assignments.
2. `/review_course <id>` displays course metadata, files, contributor notes.
3. Reviewer approves/rejects → optional feedback stored.
4. Bot notifies contributor and updates course status.
5. Analytics updated (reviewer response time, throughput, decisions).

---

## 3. Modules & Responsibilities

### Core Modules
- `core/anonymity.py` – Anonymous ID generation/storage (REST-based now).
- `core/bulk_operations.py` – Bulk upload engine with Supabase REST.
- `core/enhanced_course_uploader.py` – Single upload wizard (resume support).
- `core/review_queue_manager.py` – Review assignments, prioritization.
- `core/supabase_client.py` – REST client + optional SQL pool (disabled by default).
- `core/volunteer_system.py` – Reviewer statistics, scheduling, incentives.

### Plugins (Telegram command handlers)
- `plugins/enhanced_course_manager.py`
  - `/addcourse`, `/bulkupload`, `/batch_status`, `/bulk_help`
  - Bulk upload session management (Redis + JSON)
  - User-facing instructions and confirmations
- `plugins/volunteer_panel.py`
  - Review assignments, scheduling commands
  - Volunteer performance dashboards
- Additional plugins may manage announcements, analytics, premium features.

### Docs & Infra
- `docs/prd.md` – Original Product Requirement Document.
- `docs/OWNER_TECH_GUIDE.md` – This guide (owner/developer reference).
- `docs/TECHNICAL_DOCS.md` – Additional technical references (if present).

---

## 4. Data Model (Supabase)

### Key Tables (selected)
- `users`
  - `anonymous_id` (varchar(32))
  - `telegram_id` (bigint)
  - `role`, `permissions` (JSONB)
  - `created_at`, `updated_at`

- `courses`
  - `id` (UUID)
  - `title`, `description`, `category`
  - `tags` (JSONB), `file_attachments` (JSONB)
  - `anonymous_contributor`, `status`
  - `metadata` (JSONB)
  - `created_at`, `updated_at`

- `course_submissions`
  - Pending submissions awaiting review (bulk operation staging area).

- `review_queue`
  - `course_id`, `contributor_id`
  - `status`, `priority`, `assigned_reviewer`
  - Timestamps for workflow metrics.

- `batch_operations`
  - Bulk upload logs (total items, success/failed counts, metadata).

- `reviewer_stats`
  - Historical performance, recognition levels, achievements.

> **Note:** Supabase REST handles insert/update/delete operations. Direct SQL pool is optional (disabled in REST-only mode).

---

## 5. Identity & Privacy Model

- `anonymous_id` generated via SHA-256 hash (first 32 chars).
- No reverse lookup; salts are random per generation.
- Telegram IDs stored but not exposed to other community members.
- Anonymous mapping cached temporarily in `anonymous_manager.salt_cache` for session continuity.
- All submissions and reviews reference `anonymous_id` only.

---

## 6. Bulk Operations Engine (`core/bulk_operations.py`)

### Responsibilities
- Accept `BulkCourseData` objects.
- Convert message links/JSON into standard course records.
- Insert courses via Supabase REST:
  - `courses` table for metadata (with `file_attachments` JSON).
  - `batch_operations` log entries for audit.
- Assign courses to review queue automatically.
- Provide status updates and error logs to contributors.

### Flow
1. `/bulkupload` collects data (method selection handled in `enhanced_course_manager.py`).
2. `parse_bulk_input` normalizes input per course.
3. `bulk_upload_courses` batches into chunks (default: 10).
4. Supabase REST handles batch insert; errors logged per course.
5. `get_bulk_operation_status(batch_id)` aggregates metrics for `/batch_status`.

### Key Points
- Works in REST-only mode; no direct SQL required.
- Handles message link transformation (extract Telegram file references in future automation).
- Supports metadata enrichment (batch ID, source, timestamps).
- Assumes file links remain available via bot’s channel permissions.

---

## 7. Review Workflow (`core/enhanced_course_uploader.py`, `core/review_queue_manager.py`)

### Single Upload Workflow
- `/addcourse` → guided steps stored in Redis session
- Metadata validation (title length, description requirements, duplicates)
- Review step allows editing metadata/files before final submission
- `submit_course_for_review` writes to `courses` + `review_queue`

### Review Queue Mechanics
- Priority determined by upload quality (number of files, errors) and batch success rate
- Reviewer assignment via `volunteer_system` (round-robin + performance weighting)
- Reviewers receive course summary, attachments, and contributor note (if provided)
- Review actions sync back to Supabase; notifications sent to contributors

### Reviewer Stats
- `reviewer_stats` table tracks counts, decisions, response time
- Recognition levels (Bronze, Silver, Gold, etc.) based on metrics
- Used for volunteer motivation and scheduling

---

## 8. Disaster Recovery & Ops

### Multi-Bot Failover
- `core/disaster_recovery_service.py` manages hot-swap tokens.
- Environment variable `BOT_TOKENS` can include primary and backup tokens.
- Heartbeat tasks monitor connectivity; auto-switch if primary fails.
- Redis/in-memory ensures state is persisted during failover.

### Health Monitoring
- Commands (e.g., `/system_health`) check:
  - Supabase REST response
  - Redis connectivity (fallback warning)
  - Telegram channel access (private + public)
  - Review queue backlog
  - Batch operation alerts

### Backups & Logs
- Supabase provides automatic backups.
- Batch operations, review actions, and admin commands logged in Postgres.
- `LOG_CHANNEL` captures runtime exceptions and notifications.

---

## 9. Developer Notes

### Key Files to Know
- `bot.py` – Pyrogram client; loads plugins and services.
- `core/supabase_client.py`
  - `initialize()` sets REST client; SQL pool optional.
  - REST-only mode is default (no direct DB URL necessary).
- `plugins/enhanced_course_manager.py`
  - Command handlers for uploads, batch status, help.
  - Uses Redis for session state (`bulk_upload_session:{user_id}`).
- `core/anonymity.py`
  - Restored to REST usage (no raw SQL).
  - `generate_anonymous_id` ensures 32-char limit.

### Coding Standards
- Async/await for I/O bound operations (Supabase, Redis).
- Prefer REST API access: `.client.table('...').insert/update/select().execute()`.
- Handle Redis optionality: try/except fallback to in-memory structures.
- Log with `logger` module; surface critical failures to `LOG_CHANNEL`.

### Extensibility
- Web Dashboard: Leverage Supabase row-level security and Next.js/React.
- Additional Integrations: `core/api/main.py` exposes endpoints; update README accordingly.
- Analytics: Expand `core/analytics_engine.py` for more dashboards.

---

## 10. Operational Checklist

### Before Launch
- Ensure channels (private/public) grant full admin rights to the bot.
- Populate `.env` with Supabase keys; leave `SUPABASE_DB_URL` empty for REST mode.
- Test `/bulkupload` with a 3-course sample batch.
- Simulate review flow with test reviewer accounts.
- Verify announcements reach public channel and inline search reflects approved courses.

### Maintenance
- Monitor Supabase usage and API limits (especially during heavy bulk operations).
- Review Redis (if used) for memory health; falling back to in-memory is acceptable but limited.
- Keep `requirements.txt` minimal and up to date.
- Schedule periodic Supabase backup exports (though automatic backups exist).

### Incident Response
- If Supabase REST fails → bot catches and logs, retry logic in bulk operations.
- If Redis unavailable → fallback storage ensures the bot remains operational.
- Multi-bot failover: switch environment variable `BOT_TOKENS` order or rotate tokens via `/manage_tokens` command.
- Render deployment: if container fails health check, inspect `render.yaml`, confirm environment variables, and review Render event logs for stack traces.

---

## 11. Future Enhancements (Ideas)
- **CI/CD Pipeline** – automated tests for commands, REST calls, and review logic.
- **Web Dashboard** – viewer for analytics, batch operations, and reviewer performance.
- **Reviewer Incentives** – badges, activity scores exposed to volunteers.
- **Advanced Search** – GraphQL/REST API for external consumers (mobile app, web aggregator).
- **Course Collections** – curated lists, seasonal campaigns, multi-language support.

---

## 12. Quick Reference

- Run bot: `python bot.py`
- Smoke test: `python quick_bot_status_check.py`
- Bulk test: use `/bulkupload` in a private chat; check `/batch_status`
- Supabase console: https://app.supabase.com | Project ID: `fnhxvxuitmyomqogonrj`
- Redis: optional; if not running, bot logs warning and uses in-memory fallback.


**This document should be kept alongside environment credentials and Supabase access. Update it whenever architecture or flows change.**
