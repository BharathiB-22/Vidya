# ==============================================================================
# vidya-project.ps1
# Vidya project bootstrap - run once per machine after vidya-generic.ps1.
# Owner: Srinivas / Fidelitus Corp
# ==============================================================================

$PROJECT_NAME  = "Vidya"
$PROJECT_ROOT  = "C:\Vidya"
$STACK         = "Python 3.12, FastAPI, Celery, Redis, React 18, TypeScript, Vite, shadcn/ui, Tailwind CSS, PostgreSQL 16, Qdrant, MinIO/S3, Gemini 1.5 Pro / 2.0 Flash, Docker, Kubernetes"
$PHASE_CURRENT = 0

$MODULES = @(
    "core\auth",
    "core\tenants",
    "core\audit-log",
    "core\task-queue",
    "core\notifications",
    "core\storage",
    "core\monitoring",
    "modules\m01-program-advisor",
    "modules\m02-syllabus-gen",
    "modules\m03-course-kit",
    "modules\m05-learning-materials",
    "modules\m06-labs-evaluator",
    "modules\m07-research-supervision",
    "modules\m08-exam-setter",
    "modules\m09-paper-admin",
    "modules\m10-bell-curve"
)

Write-Host ""
Write-Host "VIDYA - PROJECT BOOTSTRAP" -ForegroundColor Cyan
Write-Host "AI Platform - Full University Academic Lifecycle" -ForegroundColor Cyan
Write-Host ""

# 1. Folder structure
Write-Host "[ 1/7 ] Creating folder structure..." -ForegroundColor Yellow

if (-not (Test-Path $PROJECT_ROOT)) {
    New-Item -ItemType Directory -Path $PROJECT_ROOT | Out-Null
}

Set-Location $PROJECT_ROOT

$baseFolders = @(
    "tasks",
    "docs",
    "docs\plans",
    "docs\adr",
    "tests",
    ".claude\skills",
    "backend\app\api\v1\routes",
    "backend\app\models",
    "backend\app\schemas",
    "backend\app\services",
    "backend\app\workers",
    "backend\app\utils",
    "backend\tests",
    "frontend\src\components",
    "frontend\src\pages",
    "frontend\src\hooks",
    "frontend\src\lib",
    "infra\docker",
    "infra\k8s",
    "infra\helm"
)

$moduleFolders = $MODULES | ForEach-Object { "backend\app\$_" }
$allFolders = $baseFolders + $moduleFolders

foreach ($f in $allFolders) {
    $path = Join-Path $PROJECT_ROOT $f
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "Created: $f" -ForegroundColor Green
    } else {
        Write-Host "Exists: $f" -ForegroundColor DarkGray
    }
}

# 2. CLAUDE.md
Write-Host ""
Write-Host "[ 2/7 ] Writing CLAUDE.md..." -ForegroundColor Yellow

$claudeMd = @"
# CLAUDE.md - Vidya
# Extends global CLAUDE.md. Project-specific rules take precedence.
# Owner: Srinivas / Fidelitus Corp

## Stack
$STACK

## Current Phase
Current Phase: $PHASE_CURRENT

Phase 0 = Foundation, Weeks 1 to 6.
Phase 1 = Teach and Prepare.
Phase 2 = Assess and Research.

## PRD Reference
Vidya-PRD.md in project root.
Always read the relevant feature section before building.

## Module Boundaries

One Claude session per module boundary.

### Phase 0 - Core Infrastructure

auth:
backend/app/core/auth/

tenants:
backend/app/core/tenants/

audit-log:
backend/app/core/audit-log/

task-queue:
backend/app/core/task-queue/

notifications:
backend/app/core/notifications/

storage:
backend/app/core/storage/

monitoring:
backend/app/core/monitoring/

### Phase 1 - Teach and Prepare

m01-program:
backend/app/modules/m01-program-advisor/

m02-syllabus:
backend/app/modules/m02-syllabus-gen/

m03-course-kit:
backend/app/modules/m03-course-kit/

m05-learning:
backend/app/modules/m05-learning-materials/

### Phase 2 - Assess and Research

m06-labs:
backend/app/modules/m06-labs-evaluator/

m07-research:
backend/app/modules/m07-research-supervision/

m08-exam:
backend/app/modules/m08-exam-setter/

m09-paper:
backend/app/modules/m09-paper-admin/

m10-bell:
backend/app/modules/m10-bell-curve/

### Special Sessions

debug:
One error and one file per session.

audit:
Read audit logs and AuditLog table queries only.

status:
Read task files, summarise progress, no code changes.

## Non-Negotiable Rules

- AI advises, humans decide.
- Never write code that applies a grade, penalty, or rejection autonomously.
- Every consequential action needs a human ratification step at the database level, not only in the UI.
- Audit log is append-only. No UPDATE or DELETE on the audit_logs table ever.
- Multi-tenant isolation is mandatory.
- Never query across tenant schemas.
- Every query must include tenant_id scoping.
- Async jobs only for AI generation.
- Never block the API thread for AI generation.
- All AI outputs must be logged to AuditLog.
- AuditLog should include model, prompt_hash, output summary, and confidence score.

## Key Config

Fill before first session.

GEMINI_API_KEY = from Google AI Studio or Vertex AI
DATABASE_URL = postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya
REDIS_URL = redis://localhost:6379/0
S3_ENDPOINT = http://localhost:9000
S3_BUCKET = vidya-assets
JWT_SECRET = generate using openssl rand -hex 32
ENVIRONMENT = development
AI_DETECTION_THRESH = 0.75
PLAGIARISM_THRESH = 0.85

## Git

Branches:
main
dev
feature/TASK-XXX

Commit format:
[TASK-XXX] verb: what changed

Never commit to main.
Srinivas reviews every PR before merge.
"@

Set-Content -Path "$PROJECT_ROOT\CLAUDE.md" -Value $claudeMd -Encoding UTF8
Write-Host "CLAUDE.md written. Fill Key Config before first session." -ForegroundColor Green

# 3. TOOLS.md
Write-Host ""
Write-Host "[ 3/7 ] Writing TOOLS.md..." -ForegroundColor Yellow

$toolsMd = @"
# TOOLS.md - Vidya

## Plugins

Install using /plugin inside Claude Code at USER scope.

superpowers:
Brainstorm, write plan, execute plan.

code-simplifier:
Post-implementation cleanup.

context7:
Live API documentation for FastAPI, SQLAlchemy, Celery, React, Gemini.

context-mode:
Context savings for large outputs, if available.

## MCPs

filesystem:
Read project files without pasting.

memory:
Persist decisions, open questions, and schema changes.

sequential-thinking:
Architecture and debugging chains.

## Session Launcher

.\vidya-sessions.ps1 -Session list
.\vidya-sessions.ps1 -Session auth
.\vidya-sessions.ps1 -Session audit
.\vidya-sessions.ps1 -Session debug
.\vidya-sessions.ps1 -Session status

## Docker

docker compose up -d
docker compose logs -f vidya-api
docker compose exec vidya-api bash

## Database

alembic upgrade head
alembic revision --autogenerate -m "desc"

## Tests

cd backend
pytest -v
pytest tests/test_auth.py -v
pytest --cov=app tests/

## Celery

celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app flower
"@

Set-Content -Path "$PROJECT_ROOT\TOOLS.md" -Value $toolsMd -Encoding UTF8
Write-Host "TOOLS.md written." -ForegroundColor Green

# 4. SKILLS.md and task-create skill
Write-Host ""
Write-Host "[ 4/7 ] Writing SKILLS.md and task-create skill..." -ForegroundColor Yellow

$skillsMd = @"
# SKILLS.md - Vidya

Command: task-create
File: .claude/skills/task-create.md
Purpose: Create a new TASK-XXX.md with PDCA workflow.
"@

Set-Content -Path "$PROJECT_ROOT\SKILLS.md" -Value $skillsMd -Encoding UTF8

$taskCreateMd = @"
# Skill: task-create

1. Ask for task title and phase number.
2. Find next TASK number in tasks folder.
3. Create tasks/TASK-XXX-slug.md with PDCA template.
4. Create branch feature/TASK-XXX.
5. Report path and branch name.
"@

Set-Content -Path "$PROJECT_ROOT\.claude\skills\task-create.md" -Value $taskCreateMd -Encoding UTF8
Write-Host "SKILLS.md and task-create skill written." -ForegroundColor Green

# 5. TASK-000 init
Write-Host ""
Write-Host "[ 5/7 ] Creating TASK-000 Repo Init..." -ForegroundColor Yellow

$task000 = @"
# TASK-000: Repo Init - Vidya

## Status
PLANNING

## Phase
0

## Objective
Repository scaffolding, Docker Compose dev environment, GitHub Actions CI pipeline, and coding standards documented.

Exit criteria:
- A new tenant can be provisioned.
- A user can log in.
- An async job can be submitted and polled.
- All tests pass in CI.

## PDCA Log

### Cycle 1

Plan:
Approved: Pending
Do:
Check:
Act:

## Checkpoints

Step: Repo and branch strategy
Status:
Git Commit:
Notes:

Step: Docker Compose stack
Status:
Git Commit:
Notes:

Step: GitHub Actions CI
Status:
Git Commit:
Notes:

Step: Coding standards doc
Status:
Git Commit:
Notes:
"@

Set-Content -Path "$PROJECT_ROOT\tasks\TASK-000-repo-init.md" -Value $task000 -Encoding UTF8
Write-Host "tasks/TASK-000-repo-init.md written." -ForegroundColor Green

# 6. .mcp.json
Write-Host ""
Write-Host "[ 6/7 ] Writing .mcp.json..." -ForegroundColor Yellow

$npmGlobalRoot = (npm root -g 2>$null).Trim()

$mcpJson = @"
{
  "mcpServers": {
    "filesystem": {
      "command": "node",
      "args": ["$npmGlobalRoot\\@modelcontextprotocol\\server-filesystem\\dist\\index.js", "$PROJECT_ROOT"]
    },
    "memory": {
      "command": "node",
      "args": ["$npmGlobalRoot\\@modelcontextprotocol\\server-memory\\dist\\index.js"]
    },
    "sequential-thinking": {
      "command": "node",
      "args": ["$npmGlobalRoot\\@modelcontextprotocol\\server-sequential-thinking\\dist\\index.js"]
    }
  }
}
"@

Set-Content -Path "$PROJECT_ROOT\.mcp.json" -Value $mcpJson -Encoding UTF8
Write-Host ".mcp.json written." -ForegroundColor Green

# 7. docker-compose.yml
Write-Host ""
Write-Host "[ 7/7 ] Writing docker-compose.yml stub..." -ForegroundColor Yellow

$dockerCompose = @"
version: "3.9"

services:
  vidya-api:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - postgres
      - redis
      - minio
      - qdrant

  vidya-worker:
    build: ./backend
    command: celery -A app.workers.celery_app worker -Q celery --loglevel=info
    env_file: .env
    depends_on:
      - redis
      - postgres

  vidya-worker-heavy:
    build: ./backend
    command: celery -A app.workers.celery_app worker -Q celery-heavy --loglevel=info
    env_file: .env
    depends_on:
      - redis
      - postgres

  vidya-frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    env_file: .env

  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: vidya
      POSTGRES_PASSWORD: vidya_dev
      POSTGRES_DB: vidya
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  flower:
    image: mher/flower
    command: celery flower --broker=redis://redis:6379/0 --port=5555
    ports:
      - "5555:5555"
    depends_on:
      - redis

volumes:
  postgres_data:
  minio_data:
  qdrant_data:
"@

Set-Content -Path "$PROJECT_ROOT\docker-compose.yml" -Value $dockerCompose -Encoding UTF8
Write-Host "docker-compose.yml stub written." -ForegroundColor Green

Write-Host ""
Write-Host "VIDYA PROJECT BOOTSTRAP COMPLETE" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Open CLAUDE.md and fill Key Config env vars." -ForegroundColor White
Write-Host "2. Create .env and fill values." -ForegroundColor White
Write-Host "3. Run: .\vidya-sessions.ps1 -Session list" -ForegroundColor White
Write-Host "4. Start first session: .\vidya-sessions.ps1 -Session auth" -ForegroundColor White
Write-Host ""