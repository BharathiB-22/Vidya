# ==============================================================================
# vidya-sessions.ps1
# Launch pre-configured Claude Code sessions for each Vidya module.
# Owner: Srinivas / Fidelitus Corp
# ==============================================================================

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet(
        "auth",
        "tenants",
        "task-queue",
        "notifications",
        "storage",
        "monitoring",
        "m01-program",
        "m02-syllabus",
        "m03-course-kit",
        "m05-learning",
        "m06-labs",
        "m07-research",
        "m08-exam-setter",
        "m09-paper-admin",
        "m10-bell-curve",
        "audit",
        "debug",
        "status",
        "list"
    )]
    [string]$Session
)

$PROJECT_ROOT = "C:\Vidya"
$HAIKU  = "claude-haiku-4-5-20251001"
$SONNET = "claude-sonnet-4-6"

$sessions = @{}

# Phase 0 - Foundation

$sessions["auth"] = @{
    model = $SONNET
    task  = "TASK-001"
    label = "Phase 0 - Auth Service"
    scope = "backend/app/core/auth/"
    prompt = @'
Stack: Python 3.12, FastAPI, PostgreSQL 16, JWT, Alembic
Task file: tasks/TASK-001-auth.md
Module scope: backend/app/core/auth/ ONLY.

Key facts:
- JWT access tokens expire in 1 hour.
- Refresh tokens expire in 7 days.
- Refresh token rotation on every use.
- Invalidate old refresh token after refresh.
- Password reset via 6-digit email OTP.
- OTP valid for 10 minutes.
- RBAC roles: SUPER_ADMIN, ADMIN, DEAN, FACULTY, STUDENT, BOARD, GUIDE.
- Unauthenticated requests return 401.
- Role mismatch returns 403.
- Schema-per-tenant: every query must include tenant_id.

Use context7 for FastAPI security, python-jose JWT, and passlib.
PDCA: present plan before touching any file.
'@
}

$sessions["tenants"] = @{
    model = $SONNET
    task  = "TASK-002"
    label = "Phase 0 - Tenant Provisioning"
    scope = "backend/app/core/tenants/"
    prompt = @'
Stack: Python 3.12, FastAPI, PostgreSQL 16, Alembic
Task file: tasks/TASK-002-tenants.md
Module scope: backend/app/core/tenants/ ONLY.

Key facts:
- Schema-per-tenant isolation in PostgreSQL.
- Cross-tenant access must be impossible at DB layer.
- Super Admin provisions new tenant.
- Required fields: name, slug, admin email, plan_type, module config.
- Provisioning creates isolated schema.
- Provisioning creates admin user record.
- Provisioning creates default JSONB config.
- New admin receives welcome email with temporary password.
- Target: new tenant provisioned in less than 15 minutes via UI.

Use context7 for SQLAlchemy async and Alembic multi-schema.
PDCA: present plan before touching any file.
'@
}

$sessions["task-queue"] = @{
    model = $SONNET
    task  = "TASK-003"
    label = "Phase 0 - Async Task Queue"
    scope = "backend/app/core/task-queue/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Redis
Task file: tasks/TASK-003-task-queue.md
Module scope: backend/app/core/task-queue/ ONLY.

Key facts:
- All AI generation jobs are async.
- Never block the API thread for AI generation.
- Job submission returns job_id immediately.
- Client polls /jobs/{job_id}/status.
- Queues: celery for standard AI jobs.
- Queues: celery-heavy for viva and batch scans.
- Job states: PENDING, IN_PROGRESS, COMPLETED, FAILED.
- Retry policy: 3 retries with exponential backoff for transient failures.

Use context7 for Celery task routing and Redis result backend.
PDCA: present plan before touching any file.
'@
}

$sessions["notifications"] = @{
    model = $HAIKU
    task  = "TASK-004"
    label = "Phase 0 - Notification Service"
    scope = "backend/app/core/notifications/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Redis
Task file: tasks/TASK-004-notifications.md
Module scope: backend/app/core/notifications/ ONLY.

Key facts:
- Support in-app notifications stored in DB.
- Support email notifications.
- Frontend can poll notifications.
- Trigger events: AI job completed, submission flagged, approval required, task assigned.
- Email via SMTP configurable per tenant.
- In-app delivery via SSE or polling endpoint.
- Notification fields: user_id, type, title, body, is_read, created_at.

Use context7 for FastAPI background tasks and email libraries.
PDCA: present plan before touching any file.
'@
}

$sessions["storage"] = @{
    model = $HAIKU
    task  = "TASK-005"
    label = "Phase 0 - Object Storage"
    scope = "backend/app/core/storage/"
    prompt = @'
Stack: Python 3.12, FastAPI, MinIO local, S3-compatible production, boto3
Task file: tasks/TASK-005-storage.md
Module scope: backend/app/core/storage/ ONLY.

Key facts:
- Use S3-compatible interface.
- MinIO for local development.
- AWS S3, GCS, or Azure Blob in production.
- Use presigned URLs for secure file access.
- Never expose raw storage paths in API responses.
- Buckets: vidya-submissions, vidya-assets, vidya-exam-papers.
- Exam paper bucket: server-side encryption enforced.
- Exam paper object ACL must always be private.

Use context7 for boto3 S3 presigned URLs.
PDCA: present plan before touching any file.
'@
}

$sessions["monitoring"] = @{
    model = $HAIKU
    task  = "TASK-006"
    label = "Phase 0 - Monitoring and Logging"
    scope = "backend/app/core/monitoring/"
    prompt = @'
Stack: Python 3.12, FastAPI, Prometheus, Grafana, Loki, structlog
Task file: tasks/TASK-006-monitoring.md
Module scope: backend/app/core/monitoring/ ONLY.

Key facts:
- Prometheus metrics: request latency p50, p95, p99.
- Prometheus metrics: error rate, queue depth, AI job duration.
- Structured JSON logs to Loki.
- No free-text logs.
- Every log line must be parseable JSON.
- /healthz returns 200 if API can reach DB and Redis.
- /ready returns 200 when app is ready to serve traffic.
- Alert thresholds:
  - API error rate greater than 1 percent.
  - Queue depth greater than 100 jobs.
  - p95 latency greater than 2 seconds.

Use context7 for prometheus-fastapi-instrumentator and structlog.
PDCA: present plan before touching any file.
'@
}

# Phase 1 - Teach and Prepare

$sessions["m01-program"] = @{
    model = $SONNET
    task  = "TASK-010"
    label = "Phase 1 - M-01 Program Structure Advisor"
    scope = "backend/app/modules/m01-program-advisor/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Google Gemini 1.5 Pro, PostgreSQL 16
Task file: tasks/TASK-010-m01-program.md
Module scope: backend/app/modules/m01-program-advisor/ ONLY.

Key facts:
- Dean inputs: program name, degree type, duration in semesters, total credits, regulatory body, elective policy.
- AI generates semester-wise course list.
- AI generates credit load and electives.
- AI generates prerequisite chains.
- AI generates CO to PO articulation map.
- Regulatory compliance checks against UGC or AICTE credit norms.
- Violations must be flagged with rule reference.
- Approval gate: Dean explicitly approves.
- Status becomes APPROVED after Dean approval.
- Structure locked after approval.
- Locked structure cannot be edited directly.
- Create new version for changes.
- Export approved structure as PDF and DOCX.
- AI advises, Dean decides.
- No autonomous approval.

Use context7 for Gemini API, reportlab PDF, and python-docx.
PDCA: present plan before touching any file.
'@
}

$sessions["m02-syllabus"] = @{
    model = $SONNET
    task  = "TASK-011"
    label = "Phase 1 - M-02 Syllabus Generator"
    scope = "backend/app/modules/m02-syllabus-gen/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Google Gemini 1.5 Pro, PostgreSQL 16
Task file: tasks/TASK-011-m02-syllabus.md
Module scope: backend/app/modules/m02-syllabus-gen/ ONLY.

Key facts:
- Input: course name, linked program, optional custom instructions.
- POs inherited from linked program.
- Output minimum 4 COs.
- Each CO must be Bloom-tagged.
- Each CO mapped to at least 1 PO.
- Output minimum 4 units.
- Units include topics, hours, and pedagogy.
- Output minimum 5 references.
- References from OpenLibrary or CrossRef APIs.
- Never invent references.
- Every edit saves a new version.
- Optional change note supported.
- Rollback supported.
- Workflow: DRAFT, FACULTY_APPROVED, ADMIN_LOCKED.
- CO-PO matrix export: PDF, DOCX, structured JSON.
- Downstream modules: M-03 and M-08.
- Bloom levels: REMEMBER, UNDERSTAND, APPLY, ANALYSE, EVALUATE, CREATE.

Use context7 for Gemini API, CrossRef API, and python-docx.
PDCA: present plan before touching any file.
'@
}

$sessions["m03-course-kit"] = @{
    model = $SONNET
    task  = "TASK-012"
    label = "Phase 1 - M-03 Course Kit Builder"
    scope = "backend/app/modules/m03-course-kit/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Google Gemini 1.5 Pro, PostgreSQL 16
Task file: tasks/TASK-012-m03-course-kit.md
Module scope: backend/app/modules/m03-course-kit/ ONLY.

Key facts:
- Per unit generate at least 8 slides.
- Slides include faculty speaker notes.
- Slides include student handout.
- Generate at least 2 quizlets per unit.
- Generate assignments with rubrics.
- Generate case studies.
- Quizlet answer keys stored server-side only.
- Never send answer keys to client.
- AI detection for submissions uses perplexity, burstiness, and RoBERTa classifier.
- AI probability range: 0 to 1.
- Default flag threshold: 0.75.
- Threshold configurable per institution.
- Flagged workflow: faculty reviews evidence panel.
- Faculty decision: Dismiss, Warn, Escalate.
- System never applies penalty autonomously.
- Locked-browser web app for controlled assessments.
- Copy-paste disabled.
- Watermarked assessment environment.
- Full audit trail required.
- Every scan result and faculty decision logged to AuditLog.
- Export: PPTX and PDF for slides.
- Export: PDF for handout.

Use context7 for Gemini API, python-pptx, and transformers RoBERTa.
PDCA: present plan before touching any file.
'@
}

$sessions["m05-learning"] = @{
    model = $SONNET
    task  = "TASK-013"
    label = "Phase 1 - M-05 Learning Material Packager"
    scope = "backend/app/modules/m05-learning-materials/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Qdrant, Google text-embedding-004, PostgreSQL 16
Task file: tasks/TASK-013-m05-learning.md
Module scope: backend/app/modules/m05-learning-materials/ ONLY.

Key facts:
- Sources: YouTube Data API v3.
- Sources: arXiv API.
- Sources: NPTEL public content.
- Sources: MIT OCW.
- Relevance ranking by semantic similarity to unit syllabus.
- Use text-embedding-004.
- Top-N per unit default is 10.
- RAG notebook Q and A.
- Student asks question.
- Answer generated over package content.
- Answers require source citations.
- Faculty can add or remove items.
- Faculty additions marked Faculty Recommended.
- Package auto-updates when syllabus version changes.
- Students notified on package update.
- Mobile responsive.
- Offline reading mode for downloaded PDFs.

Use context7 for qdrant-client, google-generativeai embeddings, and arXiv API.
PDCA: present plan before touching any file.
'@
}

# Phase 2 - Assess and Research

$sessions["m06-labs"] = @{
    model = $SONNET
    task  = "TASK-020"
    label = "Phase 2 - M-06 Labs and Assignment Evaluator"
    scope = "backend/app/modules/m06-labs-evaluator/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Google Gemini 1.5 Pro, PostgreSQL 16
Task file: tasks/TASK-020-m06-labs.md
Module scope: backend/app/modules/m06-labs-evaluator/ ONLY.

Key facts:
- Code submissions run in sandboxed container.
- Execute against faculty test cases.
- Use AST and token similarity for cross-cohort plagiarism check.
- Written submissions scored by LLM per rubric criterion.
- Each rubric score includes 1 to 3 sentence justification.
- Weighted sum gives overall score.
- Plagiarism threshold: cosine similarity greater than 0.85.
- Threshold configurable.
- Faculty review panel shows AI scores, justifications, and plagiarism report.
- Faculty can accept or edit.
- Marks not written to grade ledger until faculty explicitly ratifies.
- AI score confidence: high, medium, low.
- Low confidence is priority review flag.
- Moderation report exportable per assignment.

Use context7 for Gemini API, Docker SDK sandbox, and sentence-transformers.
PDCA: present plan before touching any file.
'@
}

$sessions["m07-research"] = @{
    model = $SONNET
    task  = "TASK-021"
    label = "Phase 2 - M-07 Research Supervision System"
    scope = "backend/app/modules/m07-research-supervision/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Gemini 1.5 Pro, Whisper self-hosted, arXiv API, PostgreSQL 16
Task file: tasks/TASK-021-m07-research.md
Module scope: backend/app/modules/m07-research-supervision/ ONLY.

Key facts:
- Student submits title, abstract, and 3 research questions.
- AI evaluates novelty using arXiv or Semantic Scholar.
- AI evaluates feasibility and clarity.
- AI recommendation: ACCEPT, REVISE, or REJECT.
- Guide must explicitly accept, reject, or request revision.
- AI recommendation is advisory only.
- Document evaluation includes format compliance.
- Document evaluation includes clarity score.
- Document evaluation includes plagiarism using CrossRef and internal checks.
- Document evaluation includes AI content probability.
- Video viva uses time-limited session link.
- AI asks 5 to 10 structured questions.
- Follow-ups based on responses.
- Session recorded.
- ASR via Whisper self-hosted pod.
- No external ASR API call.
- Guide ratifies viva evaluation before it is recorded.
- No autonomous academic decisions.

Use context7 for Whisper, arXiv API, and Gemini API.
PDCA: present plan before touching any file.
'@
}

$sessions["m08-exam-setter"] = @{
    model = $SONNET
    task  = "TASK-022"
    label = "Phase 2 - M-08 Exam Paper Setter"
    scope = "backend/app/modules/m08-exam-setter/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Gemini 1.5 Pro, AES-256 encryption, KMS, PostgreSQL 16
Task file: tasks/TASK-022-m08-exam-setter.md
Module scope: backend/app/modules/m08-exam-setter/ ONLY.

Key facts:
- Input: course, units multi-select, total marks, Bloom distribution, question format.
- Output minimum 2 paper variants: Set A and Set B.
- Include model answers.
- Include marking scheme.
- Bloom compliance: actual distribution within plus or minus 5 percent of requested.
- Flag if distribution is not achievable.
- Approval gate: Faculty submits.
- Examination Board approves.
- Status becomes BOARD_APPROVED.
- Post-approval paper sealed with AES-256.
- Decryption key stored in KMS with time-lock policy.
- Sealed paper inaccessible to all users including creator until release time.
- Release: system auto-decrypts at scheduled date and time.
- Status becomes RELEASED.
- Store encryption key reference only.
- Key itself lives in KMS only.

Use context7 for cryptography AES and Gemini API.
PDCA: present plan before touching any file.
'@
}

$sessions["m09-paper-admin"] = @{
    model = $SONNET
    task  = "TASK-023"
    label = "Phase 2 - M-09 Paper Administration and Scanning"
    scope = "backend/app/modules/m09-paper-admin/"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, Gemini 1.5 Pro, TWAIN/WIA bridge, PostgreSQL 16
Task file: tasks/TASK-023-m09-paper-admin.md
Module scope: backend/app/modules/m09-paper-admin/ ONLY.

Key facts:
- Physical paper path supports admin uploaded scanned PDFs.
- Physical paper path supports TWAIN/WIA browser bridge.
- Student ID masking required.
- Roll number and name stripped before routing to evaluator.
- Identity revealed only after all marks are finalised and locked.
- Objective sections MCQ auto-evaluated against answer key.
- Subjective sections: evaluator sees scanned pages.
- Subjective sections: evaluator sees AI suggested marks and justification.
- Evaluator annotates digitally.
- Double evaluation configurable.
- Second evaluator reviews before Examination Board finalises.
- Final marks written to grade ledger only after Board finalisation.

Use context7 for PyMuPDF PDF ingestion, Gemini API vision, and PIL de-skew.
PDCA: present plan before touching any file.
'@
}

$sessions["m10-bell-curve"] = @{
    model = $SONNET
    task  = "TASK-024"
    label = "Phase 2 - M-10 Bell Curve Normaliser"
    scope = "backend/app/modules/m10-bell-curve/"
    prompt = @'
Stack: Python 3.12, FastAPI, scipy, numpy, Gemini 1.5 Pro, PostgreSQL 16
Task file: tasks/TASK-024-m10-bell-curve.md
Module scope: backend/app/modules/m10-bell-curve/ ONLY.

Key facts:
- Trigger automatically when all marks for a course are finalised.
- Detect zero inflation greater than 15 percent at 0.
- Detect ceiling effect greater than 20 percent at max.
- Detect bimodal distribution using Hartigan dip test.
- Detect excessive skew where absolute skewness greater than 1.5.
- Normalisation suggestions: linear scaling.
- Normalisation suggestions: percentile mapping.
- Normalisation suggestions: grade boundary shift.
- Cross-faculty analysis: mean and variance per evaluator.
- Flag statistically significant outliers.
- Board review panel shows raw distribution, anomalies, suggested normalisation, projected outcome.
- Board can accept, modify, or reject.
- Applied only after Board ratification.
- Fairness report generated per semester.
- Fairness report exportable as PDF for accreditation.

Use context7 for scipy.stats, numpy, and reportlab.
PDCA: present plan before touching any file.
'@
}

# Special Sessions

$sessions["audit"] = @{
    model = $SONNET
    task  = "N/A"
    label = "Audit Log Inspector read-only"
    scope = "AuditLog table read-only"
    prompt = @'
Stack: Python 3.12, FastAPI, PostgreSQL 16
Session type: AUDIT. Read-only inspection of audit_log table.

Rules:
- READ ONLY.
- Do not write, modify, or delete any data.
- The audit_log table is append-only by design.
- Never suggest UPDATE or DELETE.
- Useful queries:
  SELECT * FROM audit_logs WHERE tenant_id = :tid ORDER BY created_at DESC LIMIT 50;
  SELECT * FROM audit_logs WHERE entity_type = 'Submission' AND action = 'AI_FLAG' ORDER BY created_at DESC;
  SELECT * FROM audit_logs WHERE user_id = :uid ORDER BY created_at DESC;
- Fields:
  id, tenant_id, user_id, action, entity_type, entity_id, ai_model,
  ai_output JSONB, confidence_score, human_decision, created_at.
- If a missing audit entry is found, report it.
- Do not insert compensating records.

Report findings only.
Do not touch any file or table.
'@
}

$sessions["debug"] = @{
    model = $SONNET
    task  = "TASK-???"
    label = "Debug Session"
    scope = "one error, one file"
    prompt = @'
Stack: Python 3.12, FastAPI, Celery, PostgreSQL 16, React 18 TypeScript
Session type: DEBUG. One error, one file, one session.

Instructions:
1. Paste the full traceback. Do not truncate.
2. Paste only the function or component that threw the error.
3. State what you expected versus what happened.

Known Vidya gotchas:
- tenant_id missing from query can cause cross-tenant leak or empty result.
- Celery task result not found can mean result backend TTL issue.
- JWT refresh without rotation means old token is still valid.
- Audit log insert failure often means missing confidence_score or null entity_id.
- Gemini API 429 means concurrent request limit or missing backoff.
- AES-sealed exam paper accessed before release_at should return 403, not 404.

Use systematic-debugging before proposing any fix.
'@
}

$sessions["status"] = @{
    model = $HAIKU
    task  = "N/A"
    label = "Project Status Report read-only"
    scope = "tasks folder read-only"
    prompt = @'
Stack: Vidya - Python 3.12 FastAPI and React 18 TypeScript
Session type: STATUS. Read-only project progress summary.

Instructions:
1. Read all files in tasks directory.
2. For each TASK file, extract Status, Phase, Objective, and last PDCA cycle state.
3. Output a markdown table:
   Task | Phase | Status | Objective one line | Last PDCA State
4. Highlight tasks that are BLOCKED.
5. Highlight tasks with no activity in the last cycle.
6. Summarise complete, in progress, and not started work.
7. Do not modify any file.
8. Do not write code.
9. Read and report only.

After the table, list open questions from CLAUDE.md or task files.
'@
}

# List mode
if ($Session -eq "list") {
    Write-Host ""
    Write-Host "VIDYA - Available Sessions" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "Phase 0 - Foundation" -ForegroundColor Yellow
    foreach ($key in @("auth","tenants","task-queue","notifications","storage","monitoring")) {
        $s = $sessions[$key]
        $tag = if ($s.model -like "*haiku*") { "Haiku" } else { "Sonnet" }
        Write-Host ("  {0,-20} {1,-50} [{2}]" -f $key, $s.label, $tag)
    }

    Write-Host ""
    Write-Host "Phase 1 - Teach and Prepare" -ForegroundColor Yellow
    foreach ($key in @("m01-program","m02-syllabus","m03-course-kit","m05-learning")) {
        $s = $sessions[$key]
        Write-Host ("  {0,-20} {1,-50} [Sonnet]" -f $key, $s.label)
    }

    Write-Host ""
    Write-Host "Phase 2 - Assess and Research" -ForegroundColor Yellow
    foreach ($key in @("m06-labs","m07-research","m08-exam-setter","m09-paper-admin","m10-bell-curve")) {
        $s = $sessions[$key]
        Write-Host ("  {0,-20} {1,-50} [Sonnet]" -f $key, $s.label)
    }

    Write-Host ""
    Write-Host "Special" -ForegroundColor Yellow
    foreach ($key in @("audit","debug","status")) {
        $s = $sessions[$key]
        $tag = if ($s.model -like "*haiku*") { "Haiku" } else { "Sonnet" }
        Write-Host ("  {0,-20} {1,-50} [{2}]" -f $key, $s.label, $tag)
    }

    Write-Host ""
    Write-Host "Usage: .\vidya-sessions.ps1 -Session <name>" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# Launch session
$s = $sessions[$Session]

Write-Host ""
Write-Host "Session: $($s.label)" -ForegroundColor Cyan
Write-Host "Model  : $($s.model)" -ForegroundColor Cyan
Write-Host "Task   : $($s.task)" -ForegroundColor Cyan
Write-Host "Scope  : $($s.scope)" -ForegroundColor Cyan
Write-Host ""

if ($Session -eq "audit") {
    Write-Host "AUDIT MODE: read-only. Do not modify data or files." -ForegroundColor Yellow
}
if ($Session -eq "status") {
    Write-Host "STATUS MODE: read-only. Report only. No code changes." -ForegroundColor Yellow
}
if ($Session -eq "debug") {
    Write-Host "DEBUG MODE: paste full traceback and one function only." -ForegroundColor Yellow
}

Write-Host ""
Write-Host $s.prompt -ForegroundColor White
Write-Host ""

$s.prompt | Set-Clipboard
Write-Host "Prompt copied to clipboard." -ForegroundColor Green
Write-Host "Paste it in Claude Code, then type: superpowers brainstorm" -ForegroundColor Cyan
Write-Host ""

Set-Location $PROJECT_ROOT
$env:ANTHROPIC_MODEL = $s.model
claude --model $s.model