# Vidya — End-to-End Demo Script

**Owner:** Srinivas / Fidelitus Corp
**Last updated:** 2026-05-23
**Duration:** ~20 minutes
**Audience:** Prospective institution clients, accreditation reviewers, investors

---

## Pre-Demo Setup Checklist

Before starting, verify the following are running:

```powershell
# 1. KIND cluster health
kubectl get pods -n vidya-system
# Expected: 10/10 Running

# 2. Ingress reachable
curl http://vidya.127.0.0.1.nip.io:9080/api/healthz
# Expected: {"status":"ok"}

# 3. Frontend reachable
curl -s -o /dev/null -w "%{http_code}" http://vidya.127.0.0.1.nip.io:9080
# Expected: 200
```

**Required demo accounts (smoke-university tenant):**

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@fidelitus.com | (from values.dev.secret.yaml) |
| Institution Admin | admin@smoke-university.edu | (set at provisioning) |
| Dean | dean@smoke-university.edu | (created via /users) |
| Faculty | faculty@smoke-university.edu | (created via /users) |
| Student | student@smoke-university.edu | (created via /users) |
| Board | board@smoke-university.edu | (created via /users) |

Open two browser windows:
- **Window A** — for the main demo flow
- **Window B** — for role-switching (faculty → dean → board)

---

## Demo Flow

### Act 1 — Onboarding a New Institution (2 minutes)

**Window A → navigate to: `http://vidya.127.0.0.1.nip.io:9080/admin/login`**

#### Step 1.1 — Super Admin Login
1. Enter Super Admin credentials → click **Sign in**

**Expected:** Redirected to `/admin/tenants` — tenant list showing `smoke-university` as ACTIVE.

**Talking point:**
> "This is the Fidelitus operator portal. We provision a new university from here. The institution
> gets its own completely isolated database schema — no shared tables, no cross-tenant queries
> are physically possible at the database layer."

#### Step 1.2 — Show Tenant Detail
1. Click on `smoke-university` row → `/admin/tenants/:id`

**Expected:** Tenant detail shows slug, schema name, status, creation date.

**Talking point:**
> "The slug identifies this institution across every API call via the X-Tenant-Slug header.
> Schema name maps to the PostgreSQL schema — every table query is scoped to this schema automatically."

#### Step 1.3 — Provision a new tenant (optional, if time permits)
1. Click **New tenant** → fill in institution name, slug, admin email, temporary password
2. Click **Create** → watch status flip PROVISIONING → ACTIVE

**Talking point:**
> "Under 15 seconds from form submit to a fully-provisioned university instance — schema created,
> migrations applied, admin user seeded. No DevOps involvement required after the initial deployment."

---

### Act 2 — Admin Onboarding Flow (3 minutes)

**Window A → navigate to: `http://vidya.127.0.0.1.nip.io:9080/login`**

#### Step 2.1 — Admin First Login
1. Enter slug: `smoke-university`, email, temporary password → **Sign in**

**Expected:** Redirected to `/first-login` — NOT the dashboard.

**Talking point:**
> "The first-login guard is enforced server-side. The admin cannot access any other page —
> not even the dashboard — until they set a permanent password. This is a security invariant,
> not just a UI nudge."

2. Enter temporary password → new password → confirm → **Set password**

**Expected:** Redirect to `/dashboard`. Onboarding checklist visible.

#### Step 2.2 — Onboarding Checklist
Point out the Getting started checklist:
- [x] Sign in to Vidya
- [x] Set your permanent password
- [ ] Add faculty and students
- [ ] Review institution settings

**Talking point:**
> "The checklist drives the admin through the minimum viable setup. Once all four items are
> done, it disappears. We want admins in productive use within minutes."

#### Step 2.3 — Add Users
1. Sidebar → Administration → **Users** → `/users`
2. Click **Add user** → create a faculty user: name, email, temporary password, role = FACULTY
3. Create a student user: role = STUDENT

**Expected:** Both users appear in the table immediately.

**Talking point:**
> "Every user creation is logged to the immutable audit log — who created it, when, with what role.
> The audit log cannot be updated or deleted — not even by the database administrator."

#### Step 2.4 — Settings
1. Sidebar → Administration → **Settings** → `/settings`
2. Show institution slug, schema name, change password form

**Talking point:**
> "Settings gives the admin a central view of institution identity. The slug is read-only after
> provisioning — it's the permanent identifier that scopes every database row."

---

### Act 3 — Faculty: AI-Powered Program Design (4 minutes)

**Window A → log out → log in as faculty**

#### Step 3.1 — Faculty Dashboard
Navigate to `/dashboard`.

**Talking point:**
> "Faculty see a focused view — Build courses, set exams, evaluate labs. No student data,
> no admin controls. RBAC is enforced at the route level and at the API level independently."

#### Step 3.2 — Create a Program
1. Sidebar → **Programs** → click **New program**
2. Fill in: name = "MSc AIML", degree type = "Masters", duration = 4 semesters, credits = 90,
   regulatory body = "UGC", elective policy = "3 electives per semester"
3. Click **Generate with AI**

**Expected:** AIGeneratingBanner appears — "Generating program structure…"

**Talking point:**
> "The generation job runs asynchronously in Celery — the API thread is never blocked.
> A job ID is returned immediately; the frontend polls for completion. In production this
> generates in 15–40 seconds depending on the program complexity."

4. Wait for completion → semester-wise course list renders

**Expected:** 4 semesters, course list with credit allocation, CO-PO articulation map.

**Talking point:**
> "The AI produces a complete semester plan with regulatory compliance checks against UGC norms.
> Violations are flagged with specific rule references. Every AI output includes a confidence score
> and is logged to the audit log with the model name and a hash of the prompt."

#### Step 3.3 — Submit for Dean Approval
1. Review the structure → click **Submit for approval**

**Expected:** Status changes to PENDING_APPROVAL. Notification sent to Dean.

**Talking point:**
> "The AI generated this. But it cannot be used until the Dean explicitly approves it.
> This is the core principle: AI advises, humans decide."

---

### Act 4 — Dean: Approve the Program (2 minutes)

**Window B → log in as dean**

#### Step 4.1 — Dean Dashboard
Navigate to `/programs` — the submitted program appears.

#### Step 4.2 — Approve Program Structure
1. Open the program → review semester plan
2. Edit one course placement inline (demonstrate edit capability)
3. Click **Approve**

**Expected:** Status changes to APPROVED. Faculty notified.

**Talking point:**
> "The Dean can edit before approving. Every edit is version-tracked — the full history of who
> changed what, when, and why is preserved. After approval the structure is locked; a new version
> must be created for any changes."

---

### Act 5 — Faculty: Syllabus and Course Kit (3 minutes)

**Window A → back to faculty**

#### Step 5.1 — Generate Syllabus
1. Sidebar → syllabuses or via program detail → click **Generate syllabus** for a course
2. Wait for AI generation

**Expected:** Course Outcomes with Bloom's taxonomy tags, unit breakdown with hours and pedagogy,
reference book list.

**Talking point:**
> "The syllabus is CO-PO mapped — every Course Outcome traces back to the Programme Outcomes
> from the approved program structure. The reference list is sourced from OpenLibrary and CrossRef.
> Faculty can export the CO-PO matrix as PDF, DOCX, or JSON."

#### Step 5.2 — Generate Course Kit
1. Navigate to `/course-kits` → select a unit → **Generate course kit**
2. Show the generated output: slides, quizlets, case study, assignment questions

**Talking point:**
> "A complete course kit — slides with speaker notes, in-app quizlets, case study, and homework
> questions with model answers and rubric — ready in minutes. Faculty regenerate individual
> slides without touching the rest."

---

### Act 6 — Student and Labs (2 minutes)

**Window B → log in as student**

#### Step 6.1 — Student Dashboard and Labs
1. Navigate to `/dashboard` → show simplified sidebar (My Labs, My Research only)
2. Go to `/student/labs` → open a lab assignment

**Talking point:**
> "The student sees exactly what they need and nothing more. RBAC is enforced identically
> on the frontend and the backend — a student JWT cannot reach faculty or admin API endpoints."

#### Step 6.2 — Submit Lab
1. Submit a lab answer (text or upload)

**Expected:** Submission queued. Student sees "Under review" status.

**Window A → back to faculty → `/labs`**

3. Open the submission review panel → show AI scoring per rubric criterion

**Talking point:**
> "The AI evaluates the submission against the rubric and provides per-criterion justification.
> The faculty sees the AI score and reasoning — then ratifies or overrides. No grade is recorded
> until the faculty clicks Ratify. The AI never touches the gradebook autonomously."

---

### Act 7 — Observability (2 minutes)

**Open new tab → `http://localhost:3001` (Grafana)**

#### Step 7.1 — Grafana Dashboards
1. Show the API golden signals dashboard: request rate, error rate, latency p50/p95/p99
2. Show the Celery health dashboard: task queue depth, completed/failed tasks

**Talking point:**
> "Every API request is tracked in Prometheus. We have custom `vidya_` metrics for request rate,
> auth failures, and Celery queue depth. Seven PrometheusRule alerts are pre-configured —
> including a `VidyaBackupStale` alert if no backup completes within 25 hours."

#### Step 7.2 — Log Search (Loki)
1. Grafana Explore → Loki → query for recent error logs

**Talking point:**
> "Structured JSON logs with PII masking — passwords, tokens, and emails are stripped before
> any log line is written. Log search available in Grafana for the on-call engineer."

---

### Act 8 — Closing Summary (2 minutes)

Return to a browser showing the main dashboard.

**Talking point — What we just demonstrated:**
> "In 20 minutes we saw: tenant provisioned → admin onboarded → users created →
> program generated by AI → approved by Dean → syllabus generated → course kit built →
> student submitted a lab → faculty ratified the grade → all of it observable in Grafana.
>
> The platform is multi-tenant from the database up — not just partitioned by a column,
> but physically isolated in separate PostgreSQL schemas. A query from institution A cannot
> reach institution B's data, full stop.
>
> Every consequential action — approve a program, ratify a grade, seal an exam paper —
> requires a human decision. The AI generates options. Humans decide outcomes."

**Key numbers to cite:**
- 10 modules implemented (M01–M10)
- 121 auth regression tests passing
- 58 Playwright E2E tests passing
- p95 latency: 27 ms at 1 VU, 66 ms at 10 VU sustained
- 0 cross-tenant data leaks (57 RBAC hardening tests)
- Onboarding time: under 15 seconds per institution

---

## Appendix — Screen Flow Summary

```
/admin/login
  → /admin/tenants                (tenant list)
  → /admin/tenants/new            (provision)
  → /admin/tenants/:id            (detail + retry)

/login
  → /first-login                  (forced password change)
  → /dashboard                    (role-aware tiles + onboarding checklist)
  → /users                        (ADMIN: create / edit users)
  → /settings                     (ADMIN: institution identity)
  → /programs                     (FACULTY/DEAN: program list)
  → /programs/:id                 (generate / approve / version history)
  → /syllabuses/:id               (generate / edit / export)
  → /course-kits/:id              (generate / slides / quizlets)
  → /labs                         (FACULTY: assignment list)
  → /labs/review/:submissionId    (AI scoring panel + ratify)
  → /student/labs                 (STUDENT: my assignments)
  → /student/labs/:id             (submit)
  → /exams                        (FACULTY/BOARD: exam papers)
  → /exams/:id                    (edit / seal)
  → /exams/:id/review             (BOARD: approve)
  → /scripts                      (BOARD: uploaded scripts)
  → /scripts/:id/evaluate         (AI scoring + ratify per question)
  → /bell-curve/:id/ratify        (DEAN/BOARD: normalisation gate)
  → /research/problems            (FACULTY/GUIDE: supervision)
  → /student/research             (STUDENT: submit problem)
```
