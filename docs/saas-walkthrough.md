# Vidya — SaaS Role Walkthrough

**Owner:** Srinivas / Fidelitus Corp
**Last updated:** 2026-05-23
**Applies to:** All roles — Super Admin, Institution Admin, Dean, Faculty, Student, Board, Guide

---

## Overview

Vidya is a multi-tenant AI platform for the full university academic lifecycle. Each institution
is an isolated tenant; users log in through the shared login page and are routed to their own
data namespace automatically.

This document describes every role's end-to-end flow in the live application.

---

## 1. Platform Architecture — Tenant Model

```
Fidelitus Corp (operator)
  └── Super Admin Portal  →  /admin/tenants
        provisions tenant
  └── Tenant Schema       →  PostgreSQL schema per institution
        isolated user table, programs, syllabuses, …
  └── Tenant Login        →  /login  (slug selects the schema)
        Admin / Dean / Faculty / Student / Board / Guide
```

Each tenant receives:
- An isolated PostgreSQL schema (`tenant_<slug>`)
- A seeded ADMIN user with a temporary password
- Full module access configured at provisioning time

---

## 2. Super Admin / Onboarding Flow

**Entry point:** `/admin/login` — Fidelitus Corp credentials only

### Step 1 — Tenant List
`/admin/tenants` shows all provisioned institutions: name, slug, status (PROVISIONING / ACTIVE / FAILED), created date.

### Step 2 — Create New Tenant
`/admin/tenants/new` — fill in:
- Institution name (display)
- Slug (URL-safe identifier, permanent — becomes the `X-Tenant-Slug` header value)
- Admin email and temporary password

On submit:
1. Backend creates the PostgreSQL schema
2. Runs Alembic migrations for that schema
3. Seeds the ADMIN user with the temporary password
4. Dispatches a welcome email (Celery fire-and-forget)

Expected result: tenant status changes from PROVISIONING → ACTIVE within seconds.

### Step 3 — Retry Failed Tenants
If provisioning fails (DB unreachable, migration error), the tenant enters FAILED status.
`POST /tenants/{id}/retry` re-runs provisioning. Available in the tenant detail page.

### Talking point
> "An entire institution — schema, migrations, admin seed — is provisioned in under 15 seconds. No manual database work, no SSH access required."

---

## 3. Admin Flow (Institution Admin)

**Entry point:** `/login` → institution slug + admin email + temporary password

**Sidebar sections:** Dashboard · Programs · Course Kits · Lab Assignments · Research · Exam Papers · Scripts · Bell Curve · Administration (Users, Settings)

### 3.1 First Login — Forced Password Change

On first login, the backend detects `password_changed_at = null` and redirects to `/first-login`.
The admin cannot navigate to any other page until a permanent password is set.

Actions on `/first-login`:
1. Enter temporary password (current)
2. Enter new permanent password (complexity: uppercase + lowercase + digit + special char)
3. Confirm new password → submit

On success:
- `password_changed_at` is set
- All refresh tokens are revoked (forces re-login on all devices)
- Redirect to `/dashboard`

### 3.2 Dashboard — Onboarding Checklist

After first login, the ADMIN dashboard shows a **Getting started** checklist:

| Step | Completion condition |
|------|----------------------|
| Sign in to Vidya | Always done |
| Set your permanent password | `firstLogin = false` |
| Add faculty and students | After first user created via `/users` |
| Review institution settings | After visiting `/settings` |

The checklist disappears when all 4 items are complete.

### 3.3 User Management — `/users`

ADMIN-only. Shows all institution users with role chip, active status, and identifier.

**Create user:** Name, email, temporary password, role (ADMIN / DEAN / FACULTY / STUDENT / BOARD / GUIDE), identifier (optional).
- Created users have `password_changed_at = null` → they will be forced to set a password on first login.

**Edit user:** Change name, role, or active status inline. Deactivating a user blocks login immediately.

**Audit trail:** Every create, edit, deactivate is logged to the audit log.

### 3.4 Settings — `/settings`

- Institution slug and schema name (read-only — never changes after provisioning)
- Own profile (name, email, role)
- Change password at any time

### 3.5 Cross-Module Admin Visibility

Admins see all sidebar sections and can view/act on any module without role restrictions, making
the Admin the operational fallback for every area.

---

## 4. Dean Flow

**Entry point:** `/login` → institution slug + dean credentials

**Sidebar sections:** Dashboard · Programs · Course Kits · Bell Curve

### 4.1 Dashboard

Shows a dean-specific subtitle and role-appropriate tiles. The dean sees programs pending their
approval at a glance.

### 4.2 Programs — `/programs`

The dean can view all programs. Programs submitted by faculty with status DRAFT or PENDING_APPROVAL
are visible here.

**Dean action — Approve program structure:**
1. Open program → `/programs/:id`
2. Review AI-generated semester plan, course list, CO-PO articulation map
3. Edit any course placement or rationale inline (changes tracked with version history)
4. Click **Approve** — status changes to APPROVED; structure is locked for further editing

> Non-negotiable rule: The dean's approval is mandatory before a program structure is used downstream
> for syllabus generation. The AI generates; the dean decides.

### 4.3 Bell Curve — `/bell-curve`

The dean sees normalisation reports for all exams:
- `/bell-curve` — list of all exams with normalisation jobs
- `/bell-curve/:id` — distribution analysis (histogram, percentile bands, fairness flags)
- `/bell-curve/:id/ratify` — Dean/Board gate: review and ratify or reject the normalisation

> Non-negotiable rule: The AI proposes a normalised score distribution; the dean ratifies before
> any student record is updated.

---

## 5. Faculty Flow

**Entry point:** `/login` → institution slug + faculty credentials

**Sidebar sections:** Dashboard · Programs · Course Kits · Lab Assignments · Research · Exam Papers

### 5.1 Dashboard

Faculty dashboard shows: "Build courses, set exams, evaluate labs" subtitle and quick-access tiles
for active programs, pending course kits, and unreviewed lab submissions.

### 5.2 Programs — `/programs` and `/programs/:id`

Faculty creates and manages academic programs.

**Create program:**
1. Click **New program** → fill in: program name, degree type, duration (semesters), total credits,
   regulatory body (UGC/AICTE), elective policy
2. Click **Generate with AI** — a Celery async job is dispatched
3. Poll status (auto-refreshes) → on completion, the semester-wise course plan appears
4. Edit any course placement inline
5. Submit for Dean approval

**AI output includes:**
- Semester-wise course sequence with credit load
- Elective combinations with prerequisite chains
- CO-PO articulation map
- Regulatory compliance check (UGC/AICTE norms; violations flagged)

### 5.3 Syllabuses — `/syllabuses` and `/syllabuses/:id`

For each approved course in a program, faculty generates a syllabus.

**Generate syllabus:**
1. Select program → select course → click **Generate syllabus**
2. AI generates: Course Outcomes (COs with Bloom's levels), unit breakdown with hours and pedagogy,
   reference book list (≥5 references from OpenLibrary/CrossRef)
3. Edit any CO or unit inline; each edit saves with a version increment
4. Set status: DRAFT → FACULTY_APPROVED → (Admin locks as ADMIN_LOCKED)

**Exports:** CO-PO matrix as PDF, DOCX, and structured JSON (used downstream by M03, M05).

### 5.4 Course Kits — `/course-kits` and `/course-kits/:id`

For each approved syllabus unit, faculty generates a complete course kit.

**Generate course kit:**
1. Select syllabus → click **Generate course kit**
2. AI generates per unit:
   - Slide deck (≥8 slides) with faculty speaker notes and student handout version
   - In-app quizlets (≥2 per deck, MCQ or short-answer)
   - Case study (contextual, adjustable complexity)
   - Homework and classwork questions with model answers and Bloom's level tags
3. Faculty can regenerate any individual slide or quizlet without regenerating the full deck
4. Exports: PPTX and PDF slide deck, handout PDF

### 5.5 Learning Packages — `/learning-packages`

Faculty curates external learning resources for each course unit.

**Curate learning package:**
1. Select unit → AI auto-ranks YouTube, arXiv, NPTEL, MIT OCW items by semantic similarity to syllabus
2. Faculty adds/removes items; additions marked "Faculty Recommended"
3. Faculty notes (text or PDF upload) are indexed for student Q&A

**Faculty curation page:** `/learning-packages/:id/curate`

### 5.6 Lab Assignments — `/labs` and `/labs/:id`

Faculty creates lab assignments and reviews submitted student work.

**Create assignment:**
1. New lab → fill in: title, description, rubric criteria, AI-detection flag (on/off), deadline

**Review submissions:**
- `/labs/review/:submissionId` — full AI scoring panel:
  - Rubric scores per criterion with AI justification
  - AI-detection probability (0–1) with confidence band
  - Highlighted suspicious spans (if AI flag enabled)
  - Faculty decision: **Ratify** (accept AI score), **Override** (set manual marks), **Escalate**

> Non-negotiable rule: The system never applies a grade or penalty autonomously. Faculty must
> explicitly ratify or override before any mark is recorded.

### 5.7 Research — `/research/problems`

Faculty (acting as GUIDE) manages post-graduate research supervision.

**Research lifecycle:**
1. Student submits a research problem statement (from student portal)
2. Guide/Faculty: accept or reject on `/research/problems` (human gate 1)
3. Student uploads research document
4. System scans for plagiarism and AI content → faculty reviews `/research/documents/:id`
5. Async viva scheduled — student receives a token link (`/student/viva/:token`)
6. Faculty/Guide ratifies viva report on `/research/vivas/:id` (human gate 2)

### 5.8 Exam Papers — `/exams`

Faculty creates and manages exam papers.

**Create exam paper:**
1. `/exams/create` → fill in: course, exam type, Bloom's distribution targets
2. AI generates questions per Bloom's level (Remember → Create) with mark allocation
3. Faculty edits inline; version history maintained
4. Faculty seals the paper (Fernet AES encryption, irreversible)
5. Paper submitted to Board for review

---

## 6. Student Flow

**Entry point:** `/login` → institution slug + student credentials

**Sidebar sections:** Dashboard · My Labs · My Research

### 6.1 Dashboard

Student sees a simplified view: welcome message, role subtitle ("Access labs and research materials").

### 6.2 My Labs — `/student/labs` and `/student/labs/:id`

Students see all assigned lab exercises.

**Submit lab:**
1. Open lab → read instructions → upload submission or write in-browser
2. Submit → system queues AI evaluation (rubric scoring, AI-detection scan)
3. Result available at `/student/submissions/:submissionId/result`:
   - Marks per rubric criterion (after faculty ratification)
   - Feedback from faculty
   - AI-detection result if flagged

### 6.3 My Research — `/student/research`

Students submit and track their research projects.

**Research submission:**
1. Submit research problem statement → awaits guide acceptance
2. On acceptance: upload research document, track evaluation status
3. On viva invitation: access viva at `/student/viva/:token` — async, token-gated session

### 6.4 Learning Materials

Students access curated learning packages created by faculty:
- `/learning-packages/:id` — view materials, ask Q&A questions (RAG over package content)
- Offline reading mode for downloaded PDFs

---

## 7. Board and Guide Flow

**Entry point:** `/login` → institution slug + board/guide credentials

### Board Sidebar: Dashboard · Exam Papers · Scripts · Bell Curve
### Guide Sidebar: Dashboard · Research

### 7.1 Board — Exam Paper Review

`/exams/board/pending` → list of sealed papers awaiting review.

**Board review flow:**
1. Open paper → `/exams/:id/review`
2. Decrypt and view question list, Bloom's distribution chart, mark allocation
3. Approve or return with comments (human gate)

> Non-negotiable: no exam paper can be administered until the Board approves it.

### 7.2 Board — Script Evaluation

`/scripts` → list of uploaded answer scripts per exam.

**Evaluate script:**
1. Upload scanned scripts at `/scripts/upload`
2. Board review panel at `/scripts/:scriptId/evaluate`:
   - AI scores each answer against the rubric
   - Board member views AI justification per question
   - Board ratifies or overrides each score
3. `/scripts/board` — moderation view: cross-evaluator agreement scores

### 7.3 Bell Curve — Ratification

Dean and Board share access to bell curve analysis:
- `/bell-curve` — list all normalisation jobs
- `/bell-curve/:id` — histogram, percentile bands, fairness flags
- `/bell-curve/:id/ratify` — ratify or reject proposed normalisation (Board gate)
- `/bell-curve/reports` — CO-PO attainment report (auto-generated per semester, exportable)

### 7.4 Guide — Research Supervision

GUIDE role sees `/research/problems` only. Workflow is the same as faculty research flow above.

---

## 8. AI Workflow — Cross-Cutting Pattern

Every AI generation in Vidya follows the same async pattern:

```
1. User triggers generation (button click)
2. API dispatches Celery task → returns job_id immediately (non-blocking)
3. Frontend polls /jobs/:id every 3 s (AIGeneratingBanner spins)
4. On completion: result renders inline; banner dismissed
5. Human reviews and either ratifies or edits
6. Human explicit action (Approve / Ratify / Seal) moves status forward
```

**AI outputs always include:**
- Confidence score (0–1)
- Model used and prompt_hash
- Output summary — all logged to the append-only `audit_logs` table

**Human gates that must be passed before any consequential state change:**

| Module | Gate | Actor |
|--------|------|-------|
| Program structure | APPROVED status | Dean |
| Syllabus | FACULTY_APPROVED → ADMIN_LOCKED | Faculty → Admin |
| Lab evaluation | Ratify / Override | Faculty |
| Exam paper | Board approval | Board |
| Script evaluation | Score ratification per question | Board |
| Research evaluation | Accept problem + viva ratification | Guide/Faculty |
| Bell curve normalisation | Ratify normalisation | Dean or Board |

> The AI advises. Humans decide. This is non-negotiable in every module.

---

## 9. Notifications

All users receive in-app notifications for async job completions and approval requests:

- Bell icon in the top bar (shows unread count)
- Notification drawer (slide-in) with mark-all-read
- Email notifications dispatched via Celery for critical events (approval requests, viva invitations)

---

## 10. Role Navigation Reference

| Sidebar Section | ADMIN | DEAN | FACULTY | STUDENT | BOARD | GUIDE |
|----------------|-------|------|---------|---------|-------|-------|
| Dashboard | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Programs | ✓ | ✓ | ✓ | — | — | — |
| Course Kits | ✓ | ✓ | ✓ | — | — | — |
| Lab Assignments | ✓ | — | ✓ | — | — | — |
| Research | ✓ | — | ✓ | — | — | ✓ |
| Exam Papers | ✓ | — | ✓ | — | ✓ | — |
| Scripts | ✓ | — | — | — | ✓ | — |
| Bell Curve | ✓ | ✓ | — | — | ✓ | — |
| My Labs | — | — | — | ✓ | — | — |
| My Research | — | — | — | ✓ | — | — |
| Users | ✓ | — | — | — | — | — |
| Settings | ✓ | — | — | — | — | — |
