# Vidya — Developer Setup & Session Guide

Owner: Srinivas / Fidelitus Corp
Project: Vidya — AI Platform for the Full University Academic Lifecycle

---

## Files Created

| File | Purpose |
|------|---------|
| `vidya-generic.ps1` | One-time machine bootstrap (Node, Claude CLI, MCP servers, global CLAUDE.md) |
| `vidya-project.ps1` | Vidya project bootstrap (folder structure, CLAUDE.md, docker-compose stub) |
| `vidya-sessions.ps1` | Launch pre-configured Claude Code sessions per module |

---

## Step-by-Step: First Time on a New Machine

### Step 1 — Prerequisites

Install these manually before running any script:

| Tool | Download |
|------|---------|
| Node.js 20+ | https://nodejs.org |
| Git | https://git-scm.com |
| Python 3.12 | https://python.org |
| Docker Desktop | https://docker.com |
| Claude CLI | `npm install -g @anthropic-ai/claude-code` |

### Step 2 — Run the generic bootstrap (once per machine)

Open PowerShell **as Administrator**, then:

```powershell
cd E:\stjosephs
.\vidya-generic.ps1
```

This will:
- Verify all prerequisites are present
- Install `cc-status-line` (context % meter in terminal)
- Install global MCP servers: `filesystem`, `memory`, `sequential-thinking`
- Write `~/.claude/.mcp.json`
- Write `~/.claude/CLAUDE.md` (global rules)
- Write `~/.claude/settings.json` (default model = Sonnet)

**Expected output:** `✓ Vidya generic bootstrap complete.`

---

### Step 3 — Run the project bootstrap (once per machine, per project)

```powershell
cd E:\stjosephs
.\vidya-project.ps1
```

This will:
- Create the `E:\vidya` project directory
- Scaffold all module folders (`backend/app/core/*`, `backend/app/modules/*`, `frontend/src/*`, `infra/*`)
- Write `E:\vidya\CLAUDE.md` (project rules — fill in Key Config before first session)
- Write `E:\vidya\TOOLS.md` (commands cheatsheet)
- Write `E:\vidya\SKILLS.md` + `.claude/skills/task-create.md`
- Create `E:\vidya\tasks\TASK-000-repo-init.md`
- Write `E:\vidya\.mcp.json` (project-scoped MCP)
- Write `E:\vidya\docker-compose.yml` stub

**Expected output:** `✓ Vidya project bootstrap complete.`

---

### Step 4 — Fill in the Key Config

Open `E:\vidya\CLAUDE.md` and fill in the `Key Config` section:

```
GEMINI_API_KEY       = <from Google AI Studio or Vertex AI>
DATABASE_URL         = postgresql+asyncpg://vidya:vidya_dev@localhost:5432/vidya
REDIS_URL            = redis://localhost:6379/0
S3_ENDPOINT          = http://localhost:9000
S3_BUCKET            = vidya-assets
JWT_SECRET           = <run: openssl rand -hex 32>
ENVIRONMENT          = development
AI_DETECTION_THRESH  = 0.75
PLAGIARISM_THRESH    = 0.85
```

Also copy these into a `.env` file at `E:\vidya\.env`.

---

### Step 5 — Install Claude Code plugins (inside Claude Code)

Open Claude Code in `E:\vidya`, then type `/plugin` and install at **USER scope**:

| Plugin | Purpose |
|--------|---------|
| `superpowers` | Brainstorm → Plan → Execute workflow |
| `code-simplifier` | Post-implementation cleanup |
| `context7` | Live API docs (no hallucinated method names) |
| `context-mode` | 98% context savings on large outputs |

---

### Step 6 — Start local services

```powershell
cd C:\vidya
docker compose up -d
```

Verify services are healthy:

```powershell
docker compose ps
```

All services should show `healthy` or `running`.

---

### Step 7 — Open your first session

List all available sessions:

```powershell
cd E:\stjosephs
.\vidya-sessions.ps1 -Session list
```

Start Phase 0 with the auth module:

```powershell
.\vidya-sessions.ps1 -Session auth
```

The prompt is copied to your clipboard automatically. Paste it into Claude Code and begin with:

```
superpowers brainstorm
```

---

## Session Reference

### Phase 0 — Foundation (run in this order)

```powershell
.\vidya-sessions.ps1 -Session auth           # JWT, RBAC, OTP reset
.\vidya-sessions.ps1 -Session tenants        # schema-per-tenant provisioning
.\vidya-sessions.ps1 -Session task-queue     # Celery + Redis async jobs
.\vidya-sessions.ps1 -Session notifications  # in-app + email notifications
.\vidya-sessions.ps1 -Session storage        # MinIO / S3 presigned URLs
.\vidya-sessions.ps1 -Session monitoring     # Prometheus, Grafana, Loki, /healthz
```

### Phase 1 — Teach & Prepare

```powershell
.\vidya-sessions.ps1 -Session m01-program    # M-01 Program Structure Advisor
.\vidya-sessions.ps1 -Session m02-syllabus   # M-02 Syllabus Generator
.\vidya-sessions.ps1 -Session m03-course-kit # M-03 Course Kit Builder
.\vidya-sessions.ps1 -Session m05-learning   # M-05 Learning Material Packager
```

### Phase 2 — Assess & Research

```powershell
.\vidya-sessions.ps1 -Session m06-labs        # M-06 Labs & Assignment Evaluator
.\vidya-sessions.ps1 -Session m07-research    # M-07 Research Supervision
.\vidya-sessions.ps1 -Session m08-exam-setter # M-08 Exam Paper Setter
.\vidya-sessions.ps1 -Session m09-paper-admin # M-09 Paper Administration & Scanning
.\vidya-sessions.ps1 -Session m10-bell-curve  # M-10 Bell Curve Normaliser
```

### Special Sessions

```powershell
.\vidya-sessions.ps1 -Session audit   # Read-only audit log inspection
.\vidya-sessions.ps1 -Session debug   # One-error debug (paste traceback + function)
.\vidya-sessions.ps1 -Session status  # Project progress report (read-only)
```

---

## Session Rules (Non-Negotiable)

| Rule | Detail |
|------|--------|
| **One session = one module** | Never mix module scopes in a single session |
| **Context limit: 50%** | At 50% context → finish unit → `/clear` → new session. Never `/compact`. |
| **PDCA before code** | Claude must present a plan and get your approval before touching any file |
| **AI advises, humans decide** | Never implement autonomous grade/penalty logic. Every consequential action requires a human ratification step at the DB level. |
| **Audit log: append-only** | No UPDATE or DELETE on audit_logs ever |
| **tenant_id on every query** | All DB queries must include tenant_id scoping |
| **Debug = one error, one file** | Paste full traceback + only the function that threw it |

---

## Audit Session — When to Use

Run the `audit` session when you need to:
- Verify that AI decisions are being logged correctly
- Investigate a specific submission flag or grade decision
- Prepare an audit trail for an Institution Admin compliance review
- Confirm a human ratification step was recorded

```powershell
.\vidya-sessions.ps1 -Session audit
```

This session is **read-only**. It will not modify any data or files.

---

## Debug Session — How to Use

1. Run: `.\vidya-sessions.ps1 -Session debug`
2. Paste the **full traceback** (do not truncate)
3. Paste **only** the function or component that threw the error
4. State: what you expected vs. what happened
5. Claude will use `systematic-debugging` before proposing any fix

---

## Status Session — How to Use

Run at the start of each week or before a sprint review:

```powershell
.\vidya-sessions.ps1 -Session status
```

Claude will read all `tasks/TASK-XXX-*.md` files and output a progress table — no code changes, no file writes.

---

## Useful Commands

```powershell
# Docker
docker compose up -d                         # start all services
docker compose logs -f vidya-api             # tail API logs
docker compose exec vidya-api bash           # shell into container

# Database migrations
cd E:\vidya\backend
alembic upgrade head                         # apply all migrations
alembic revision --autogenerate -m "desc"    # generate new migration

# Tests
cd E:\vidya\backend
pytest -v                                    # all tests
pytest tests/test_auth.py -v                # specific module
pytest --cov=app tests/                     # with coverage

# Celery monitor
# Visit http://localhost:5555 after docker compose up
```

---

## Git Workflow

```
main         ← production; never commit directly
dev          ← integration branch; PRs merge here
feature/TASK-XXX  ← one branch per task
```

Commit format: `[TASK-XXX] verb: what changed`
Every PR reviewed by Srinivas before merge.

---

*Vidya v1.0 — Owner: Srinivas / Fidelitus Corp*
