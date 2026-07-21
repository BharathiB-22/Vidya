# CLAUDE1.md — VIDYA AI: Complete Product Knowledge

> **Purpose of this file.** This is the single onboarding document for the VIDYA AI
> platform. A brand-new Claude session (or engineer) should be able to read *only*
> this file and understand the entire product: what it is, who uses it, how it is
> built, how every module works, and — most importantly — **why** it is built this
> way. It is descriptive, not prescriptive; for the engineering rulebook (what you
> must and must not do when changing code) read **INSTRUCTIONS.md**.
>
> **Running example.** Throughout this document we use a fictional tenant,
> **ABC University**, to make the abstractions concrete.
>
> Stack: Python 3.12 · FastAPI · Celery · Redis · React 18 + TypeScript + Vite ·
> shadcn/ui + Tailwind · PostgreSQL 16 · Qdrant · MinIO/S3 · Gemini / Groq /
> DeepSeek · Docker · Kubernetes.

---

## 1. Vision of VIDYA AI

VIDYA AI is an **AI-assisted ERP for the full university academic lifecycle** —
from designing a programme and its syllabus, through teaching and course kits,
to examinations, evaluation, results, and research supervision.

The product has one non-negotiable philosophy that shapes every design decision:

> **AI advises, humans decide.**

The AI drafts, suggests, analyses, and flags. It **never** applies a grade, a
penalty, a rejection, a seal, or a release on its own. Every consequential
transition has an explicit **human ratification step recorded at the database
level**, not merely in the UI. This is why the codebase is full of "gates" —
status transitions that only a specific human role can perform.

Why this matters: universities are accountable institutions. A wrong autonomous
decision (a wrongly rejected paper, an auto-applied penalty) is not a bug, it is
an institutional-trust failure. Making the human the decision-maker — and logging
that decision immutably — is what lets an institution adopt AI without ceding
authority.

Secondary principles that follow from the vision:

- **Offline-first ERP.** VIDYA models the *administration* of examinations, not
  online test-taking. Digital/online exam-taking surfaces were intentionally
  removed from the UI (backend retained for possible future use).
- **Multi-tenant SaaS.** Many universities share one deployment; none can ever
  see another's data.
- **Everything is auditable.** All AI outputs and all consequential human actions
  are written to an append-only audit log.

---

## 2. Multi-Tenant Architecture

### 2.1 Why multi-tenant

One VIDYA deployment serves many institutions. ABC University and (say) XYZ
Institute log into the same application, hit the same API, but must be perfectly
isolated: no query may ever return another tenant's row. VIDYA achieves this with
**schema-per-tenant** isolation in a single PostgreSQL database.

### 2.2 Schema-per-tenant design

- **`public` schema** — platform-global data that is *not* tenant-specific:
  - `public.tenants` — one row per institution (slug, `schema_name`,
    `is_active`, `status`, `governance_type`, branding).
  - `public.platform_users`, `public.platform_refresh_tokens`,
    `public.platform_otp_codes` — the **Super Admin / platform** identity plane.
  - `public.platform_branding` — VIDYA product branding.
  - `public.task_jobs` — the async job ledger for Celery (shared, tenant-tagged).
  - `public.refresh_token_index` — maps a refresh token to its tenant schema.

- **`tenant_<slug>` schema** — one schema per institution holding *all* that
  institution's academic data. ABC University lives in, e.g.,
  `tenant_abc_university`. Every academic table (`users`, `acad_programs`,
  `courses`, `syllabuses`, `exam_papers`, …) exists **once per tenant schema**.

Migrations are therefore split into two trees:

- `backend/alembic/public_versions/` — the `public` schema history.
- `backend/alembic/tenant_versions/` — the per-tenant-schema history (applied to
  *every* tenant schema). Tenant revisions are named like `0093ten`.

The two are driven by an env var: `ALEMBIC_TARGET=public|tenant`. The canonical
runner is `python -m app.db.migrate public` / `tenant <schema>` / `tenant --all`
(see §12 and INSTRUCTIONS.md). On API startup an auto-migration hook
(`app/core/tenants/migration_runner.run_all_tenant_migrations`) brings tenant
schemas to head; failures are logged, non-fatal.

### 2.3 How a request resolves its tenant

1. A user logs in against their tenant; the JWT carries the user and the tenant
   `schema_name`.
2. `get_tenant_context_dep` produces `db_info = {db, schema_name, tenant_id}`.
3. Before any tenant query the session runs `SET search_path TO <schema>, public`.
4. All ORM tenant tables are declared **without** a `schema=` kwarg, so they
   resolve against whatever `search_path` is currently set — i.e. the caller's
   tenant. This is the mechanism that makes one model definition serve every
   tenant while staying isolated.

> **Isolation is mandatory.** Never query across tenant schemas. Every tenant
> query is scoped by the active `search_path`; cross-tenant joins are forbidden.

---

## 3. Identity & Access: Roles vs Workspaces vs Responsibilities

This is the single most important mental model in VIDYA and the most common source
of confusion. There are **three** distinct concepts.

### 3.1 Role — *what you fundamentally are*

`users.role` is one of the `TenantRole` enum values (tenant schema):

`ADMIN · DEAN · FACULTY · STUDENT · BOARD · GUIDE · EVALUATOR`

Plus the platform-level **Super Admin** (`public.platform_users`, outside any
tenant). A user has exactly **one** base role — their identity.

### 3.2 Workspace — *the hat you are wearing right now*

Some users legitimately act in more than one capacity. A **Dean** is, in
practice, a senior Faculty member with extra governance authority. So VIDYA lets a
user *switch workspace*: the frontend sends an `X-Active-Workspace` header, which
resolves to an **`active_role`**, and the backend derives:

```
viewing_role = active_role (if a valid workspace was sent) else base role
```

`viewing_role` — never `role` — governs **both** permission checks and data
scoping. A Dean acting in the **Faculty** workspace is treated *exactly* as
Faculty: they pass Faculty gates and fail Dean-only gates. `role` remains the base
identity, used only for `/me` and audit attribution.

**Security contract:** a requested workspace is honoured only if the user actually
holds it (base role or an active grant). An un-entitled request fails **safe** to
the base role (never elevates, never 403s an in-flight session).

### 3.3 Responsibility — *an extra duty you can be granted*

Beyond a base role, a user can hold **responsibilities** via
`faculty_role_grants` (tenant table: `faculty_user_id`, `role_code`,
`is_active`). A single Faculty account can be granted **GUIDE**, **EVALUATOR**,
**BOARD**, or **DEAN** responsibilities — **no separate accounts**. Access for a
responsibility is driven by *active grants*, not by a hardcoded `users.role`
check.

Two dependency helpers encode the distinction:

- `require_roles(*roles)` — checks the **viewing_role** (the active workspace).
- `require_responsibility(*roles)` — passes if the user holds the role as a base
  role **or** an active grant. Grants are a **cross-workspace overlay**: a GUIDE
  grant is honoured regardless of the current workspace.

> **The rule to remember:** **GUIDE and EVALUATOR are responsibilities, not
> workspaces and not separate accounts.** A Faculty member becomes a research
> Guide or a script Evaluator by being *granted* that responsibility, and does
> the work from within their Faculty identity.

### Why three concepts and not one flat role list?

A university person is not one thing. Prof. Rao teaches (Faculty), guides two PhD
students (Guide), evaluates end-sem scripts (Evaluator), and sits on the
examination Board (Board). Modelling each as a *separate login* would fragment
their work and their audit trail. Modelling each as a *base role* would force a
choice. VIDYA instead keeps **one identity** (Faculty), lets them **switch
workspace** where authority genuinely differs (Dean/Faculty), and layers
**responsibilities** as grants for the extra duties. One person, one account, one
coherent audit trail.

---

## 4. Every User Role

For ABC University, imagine these people:

| Role | Example (ABC) | What they are | Primary powers |
|------|---------------|---------------|----------------|
| **Super Admin** | VIDYA platform operator | Platform owner, lives in `public` — *not* a tenant user | Provision/suspend tenants, platform branding, cross-tenant operations. Bypasses tenant RBAC by design. |
| **Admin** | ABC IT/Exam Cell admin | Tenant super-user | Manage users, run onboarding/SIS imports, unrestricted within the tenant. |
| **Dean** | Dean of Engineering | Faculty **plus** governance over the programmes they govern | Everything Faculty can do (in Faculty workspace) **plus** approve internal papers, lock internal marks, monitor evaluation, govern their department's programmes/syllabus. Department-scoped. |
| **Faculty** | Subject teacher | The teaching workhorse | Create/teach courses they're *assigned*, build syllabus/course-kits, set internal papers, take attendance, submit internal marks, evaluate assigned scripts. |
| **Board** | Examination Board member | The examination authority | Owns **semester (Board) papers**: review, approve/return, seal, release; script review; bell-curve ratification. **Never appears in the Faculty Directory.** |
| **Student** | Enrolled student | The learner | View own subjects, syllabus, course kits, learning materials, timetable, results, submit assignments/labs, do research work. |
| **Guide** | Research supervisor | A **responsibility** (grant) | Supervise research problems, documents, and vivas for assigned students. |
| **Evaluator** | Script evaluator | A **responsibility** (grant) | Evaluate assigned answer scripts / evaluation assignments (M09). |

**GovernanceType (display only):** a tenant sets `governance_type` = `BOARD` or
`UNIVERSITY_MEMBERS`. This changes only the *label* shown in the UI ("Board" vs
"University Members"); the **role, permissions, endpoints, and workflow are
identical** — the `TenantRole.BOARD` role backs both. ABC University calls it
"Board"; another tenant might call the same authority "University Members".

### Dean = Faculty + governance (why it's not a separate stack)

The Dean does not get a parallel set of teaching features. In the **Faculty
workspace** a Dean *is* Faculty (same code paths, same ownership rules). In the
**Dean workspace** they gain governance gates (approve internal papers, lock
marks, department oversight). This keeps one implementation of "teaching" and
avoids drift between "Faculty teaching" and "Dean teaching".

---

## 5. Faculty Responsibilities

A Faculty member at ABC is responsible for:

1. **Course planning** for assigned subjects (syllabus, course kit, learning
   materials).
2. **Internal assessment** — setting IA/MSE/CIE papers (Internal workflow),
   entering internal marks, submitting them for Dean lock.
3. **Attendance** for their sections (within the configurable edit window).
4. **Board-paper contribution** — drafting semester papers for Board review
   (when acting on Board-owned papers).
5. **Evaluation** — evaluating scripts they are assigned as Evaluator.
6. **Research supervision** — guiding students when granted the Guide
   responsibility.

Everything a Faculty may act on is bounded by **subject assignment** (see §8).
A Faculty can only set papers, edit syllabus, or view analytics for courses they
are *actively assigned to teach*.

---

## 6. Governance Structure

Governance = the authority layer above individual teaching:

- **Board** (or "University Members") — owns **semester examinations**: approves,
  seals, and releases official papers; reviews scripts; ratifies bell curves.
- **Dean** — owns **a department/programme set**: approves **internal** papers,
  locks internal marks, and monitors evaluation and syllabus for governed
  programmes. Scope comes from `get_dean_program_ids` (the programmes a Dean
  governs).
- **Admin** — owns the **tenant**: users, onboarding, configuration.

The `app/core/governance/` module and `m_academics/dean_scope.py` encode who
governs what. Governance is deliberately **separate from teaching**: the person
who *creates* content is rarely the person who *ratifies* it — separation of
duties is the point.

---

## 7. Directories: Faculty vs Governance

VIDYA maintains two people-directories, and the distinction is a hard rule:

- **Faculty Directory** — the teaching staff who can be assigned subjects. This is
  the pool subject-allocation draws from. **Board users never appear here.** A
  Board member is a governance authority, not a teaching-assignment candidate;
  listing them for subject allocation would blur the separation of duties.
- **Governance Directory** — Deans / Board / governance authorities and their
  scope (which programmes a Dean governs, Board membership). This is where
  responsibility grants and governance scope are administered.

Why keep them apart: subject allocation must only ever pick from people who
*teach*; governance oversight must only ever pick from people with *authority*.
Two directories make the wrong pick structurally impossible.

---

## 8. The Academic Backbone: Ownership, Allocation, Departments

Module: **`m_academics`** (shared academic spine) + **`m01_program_advisor`**
(programme/course catalogue).

### 8.1 Programmes, courses, departments

- **`acad_programs`** — an academic programme (e.g. "B.E. Computer Science" at
  ABC). A programme belongs to a department/governance scope
  (`acad_program_id` links users and courses to a programme).
- **`courses`** (m01) — a course/subject within a programme (`program_id`,
  `acad_program_id`, `code`, `title`, `semester`).
- **`acad_semesters` / `acad_sections`** — the term and the class sections a
  course is delivered to.

**Department ownership** is expressed through the programme: a Dean governs a set
of `acad_program_id`s (`get_dean_program_ids`), and everything under those
programmes (courses, syllabus, internal papers) falls in that Dean's scope.

### 8.2 Subject allocation (the ownership oracle)

- **`subject_assignments`** — the single source of truth for *who teaches what*:
  `(faculty_user_id, course_id, semester_id, is_active, PRIMARY/CO_FACULTY)`.
- The predicate **`faculty_teaches_course(faculty_user_id, course_id)`**
  (`m_academics/faculty_scope.py`) answers "does this faculty teach this course?"
  by looking up an **active** assignment. It is **role-agnostic**: assignment —
  not `users.role` — decides ownership.

Every module that a Faculty can reach by id (syllabus, course-kit, learning
package, **exam paper**, attendance analytics) gates reads/writes through this
same predicate. Answering the ownership question **in one place** is what stops
the next endpoint from leaking the way a previous one did.

### 8.3 Course ownership at a glance

| Actor | May act on… | Enforced by |
|-------|-------------|-------------|
| Faculty | courses they hold an **active `subject_assignment`** for | `faculty_teaches_course` |
| Dean | courses under **programmes they govern** | `get_dean_program_ids` / `dean_scope` |
| Admin | all courses in the tenant | role check |
| Board | **semester papers** (not course-teaching) | workflow ownership (see §11) |

> **Why assignment-based ownership.** Titles change; teaching duties change every
> term. Tying "can edit this course" to an *active assignment row* (not to a
> role or a name) means the moment a Faculty stops teaching a subject, they stop
> being able to change it — automatically, with no cleanup.

---

## 9. Module Reference

Each module below lists: **Purpose · Owner · Users · Workflow · Backend module ·
Frontend pages · Important APIs · DB tables · Dependencies.** Modules whose
internals are covered in depth this session (M08) are documented to table/endpoint
precision; for others the backend module path is the authoritative place to read
exact names.

### 9.0 Core infrastructure (`app/core/*`)

| Core module | Purpose | Key data / notes |
|-------------|---------|------------------|
| **auth** | Login, JWT, RBAC, workspaces, responsibility grants, OTP reset | `public.platform_users`, tenant `users`, `refresh_tokens`, `otp_codes`, `faculty_role_grants`; `require_roles`, `require_responsibility`, `viewing_role` |
| **tenants** | Schema-per-tenant provisioning + auto-migration | `public.tenants`; `provisioner.py`, `migration_runner.py` |
| **audit_log** | Append-only record of AI outputs + consequential human actions | `audit_logs` (append-only — **never** UPDATE/DELETE); `AuditService.log(event, actor, target, metadata)` |
| **task-queue** (`app/workers`) | Celery async jobs (AI generation, releases) | `public.task_jobs`; heavy queue; `TaskJobPublicRepository` |
| **notifications** | In-app + email notifications | tenant notification tables |
| **storage** | MinIO/S3 object storage (presigned URLs, sealed blobs) | `get_storage_client`, `ensure_bucket_exists` |
| **monitoring** | `/healthz`, Prometheus/Grafana/Loki | — |
| **onboarding** | Institution/user onboarding, SIS import bootstrap | onboarding service/router |
| **governance** | Governance authority + scope (Board/Dean) | governance tables; `GovernanceType` |
| **calendar / timetable** | Academic calendar + class timetable | calendar/timetable tables |

**AI + async rule:** all AI generation runs on the Celery **heavy** queue via a
`public.task_jobs` record — **never** block the API thread for AI. All AI outputs
are logged to the audit log with `model`, `prompt_hash`, output summary, and
(where applicable) confidence.

---

### 9.1 M01 — Program Structure Advisor

- **Purpose:** design and hold the programme/course catalogue; advise on
  structure and course codes.
- **Owner:** Admin / Dean (governance); AI advises.
- **Users:** Admin, Dean, Faculty (read), Student (read).
- **Workflow:** Programme drafted → courses defined → approved/published. Programme
  approval gates downstream (only APPROVED programmes appear when creating papers).
- **Backend:** `app/modules/m01_program_advisor/` (`models.py`, `service.py`,
  `course_codes.py`, `ai_provider.py`).
- **Frontend:** `ProgramListPage`, `ProgramDetailPage`, `CourseDialog`,
  `ApprovalPanel`, `ProgramStatusBadge`.
- **APIs:** programme CRUD + approval; course CRUD; `listPrograms`, `listCourses`.
- **DB tables:** `acad_programs`, `programs`, `courses`, course-outcome links.
- **Dependencies:** feeds every other academic module (courses are referenced by
  syllabus, course-kit, exams, SIS).

### 9.2 M02 — Syllabus Generator

- **Purpose:** AI-assisted syllabus authoring (units, topics, hours, Course
  Outcomes) governed by the Board/Dean.
- **Owner:** the Board owns the *syllabus* (Phase A governance invariant); Faculty
  author, governance approves.
- **Users:** Faculty (author), Dean/Board (approve), Student (read).
- **Workflow:** DRAFT → (AI generate units/COs) → submit → **approve gate** →
  LOCKED/APPROVED. There is **no reject/return**; the approve gate is the single
  invariant. Exam generation reads the latest **LOCKED/APPROVED** syllabus.
- **Backend:** `app/modules/m02_syllabus/` (`models.py`, `ai_provider.py`).
- **Frontend:** `SyllabusListPage`, `SyllabusDetailPage`,
  `SyllabusApprovalPanel`, `SyllabusStatusBadge`.
- **APIs:** `listSyllabuses`, `getSyllabus`, generate, approve.
- **DB tables:** `syllabuses` (JSONB `units`, versioned), `course_outcomes`.
- **Dependencies:** M01 (course); consumed by M08 (units + COs drive paper
  generation), M03, M05.

### 9.3 M03 — Course Kit Builder

- **Purpose:** build the teaching kit (lesson plans, execution docs, lab
  experiments) per course.
- **Owner:** Faculty (kits stay with Faculty even in the Board-MVP model).
- **Users:** Faculty (author), Dean (compliance view), Student (read).
- **Workflow:** per-type gates — e.g. lab kit = experiments only; execution docs
  can be approved empty. AI drafts; Faculty finalises.
- **Backend:** `app/modules/m03_course_kit/`.
- **Frontend:** `CourseKitListPage`, `CourseKitDetailPage`, `CourseKitPanel`,
  `CourseKitTab`, `CourseKitStatusBadge`, dean `CourseKitCompliancePage`.
- **DB tables:** course-kit + kit-version tables.
- **Dependencies:** M01/M02; ownership via `faculty_teaches_course`.

### 9.4 M04 — Assignments / Coursework

- **Purpose:** faculty-set assignments and student submissions/coursework.
- **Users:** Faculty (create/grade), Student (submit).
- **Backend:** `app/modules/m04_assignments/`.
- **Frontend:** `assignments/*` (Faculty), `student/.../AssignmentsTab`,
  `StudentAssignmentListPage`, `StudentAssignmentSubmitPage`.
- **Dependencies:** M01 (course), attendance/marks feed analytics.

### 9.5 M05 — Learning Material Packager

- **Purpose:** package and (RAG-)index learning materials for a course.
- **Owner:** Faculty; Student consumes.
- **Backend:** `app/modules/m05_learning_materials/` (RAG service, Qdrant index).
- **Frontend:** `LearningPackageListPage`, `LearningPackage`,
  `LearningMaterialsTab`, student `LearningMaterialsPage`, `PackageStatusBadge`.
- **DB tables:** learning-package tables; vectors in **Qdrant**.
- **Dependencies:** M01/M02; storage (MinIO); Qdrant.

### 9.6 M06 — Labs & Assignment Evaluator

- **Purpose:** AI-assisted evaluation of lab/assignment submissions (advisory
  scores + rubric); human ratifies.
- **Owner:** Faculty.
- **Users:** Faculty (review/ratify), Student (submit/view result).
- **Backend:** `app/modules/m06_labs_evaluator/` (`report_export.py`).
- **Frontend:** `LabAssignmentListPage`, `LabAssignmentDetailPage`,
  `LabReviewForm`, `SubmissionRow`, `StudentLabListPage`, `StudentSubmitPage`.
- **Dependencies:** storage; AI provider; **AI never applies a grade** — Faculty
  ratifies.

### 9.7 M07 — Research Supervision

- **Purpose:** supervise research problems, documents, and vivas.
- **Owner:** Guide (responsibility) + Dean oversight.
- **Users:** Faculty/**Guide**, Dean, Student.
- **Workflow:** problem defined → student works → document review → viva →
  ratify. Guide access is via the **GUIDE responsibility grant**.
- **Backend:** `app/modules/m07_research_supervision/` (`problem_generator.py`,
  `viva_engine.py`).
- **Frontend:** `ResearchProblemListPage`, `ResearchProblemDetailPage`,
  `ResearchDocumentPage`, `VivaRatifyPage`, student `StudentResearchPage`,
  `StudentVivaPage`.
- **Dependencies:** auth grants (GUIDE); storage.

### 9.8 M08 — Exam Paper Setter  *(documented in depth — see §11)*

- **Purpose:** create question papers (AI-generated or manual), run the
  Internal/Board approval workflow, seal + auto-release, and manage internal
  marks + a reusable question bank.
- **Owner:** **Internal papers → Faculty (reviewed by Dean); Semester papers →
  Board.**
- **Users:** Faculty, Dean, Board, Admin (+ Student for released exports).
- **Backend:** `app/modules/m08_exam_setter/` — `models.py`, `schemas.py`,
  `service.py`, `repository.py`, `router.py`, `question_generator.py`,
  `blooms_analyser.py`, `paper_sealer.py`, `pdf_exporter.py`; workers
  `app/workers/heavy/generate_exam_paper.py`, `regenerate_exam_question.py`,
  `release_exam_paper.py`.
- **Frontend:** `ExamPaperCreatePage`, `ExamPaperListPage`,
  `ExamPaperEditorPage`, `BoardReviewPage`, `DeanReviewPage`,
  `InternalExamReleasePage`.
- **DB tables:** `exam_papers`, `exam_questions`, `blooms_compliance_reports`,
  `question_bank`, `internal_marks_summary`.
- **Dependencies:** M01 (course), M02 (units + COs), task-queue (generation +
  release), storage (sealed blob), audit log; M09 (double-evaluation flags).

### 9.9 M09 — Paper Administration & Scanning

- **Purpose:** scanned answer-script administration, evaluator assignment,
  double-evaluation, OCR review, score ledger.
- **Owner:** Board/Admin (governance) + **Evaluator** (responsibility).
- **Users:** Board, Admin, Faculty/**Evaluator**, Dean (monitoring).
- **Backend:** `app/modules/m09_paper_admin/`.
- **Frontend:** `ScriptListPage`, `ScriptUploadPage`, `BoardScriptReviewPage`,
  `ScoreLedgerPage`, `ScriptEvaluationPanel`, `MyScriptsPage`,
  `DoubleEvaluationComparisonPage`, `EvaluatorDashboardPage`,
  `OCRReviewQueuePage`, evaluation-assignment pages.
- **Dependencies:** M08 (`exam_papers.double_evaluation_enabled`,
  `discrepancy_threshold_pct`); storage; audit log.

### 9.10 M10 — Bell Curve Normaliser

- **Purpose:** advisory grade normalisation with a fairness report; **human
  ratifies** the curve.
- **Owner:** Dean/Board/Admin.
- **Backend:** `app/modules/m10_bell_curve/` (`report_builder.py`).
- **Frontend:** `BellCurveListPage`, `BellCurveAnalysisPage`,
  `BellCurveRatifyPage`, `FairnessReportPage`.
- **Dependencies:** results (M11); **AI/curve is advisory — a human ratifies**.

### 9.11 M11 — SIS (Student Information System)

- **Purpose:** the student/faculty records backbone — enrolment, sections,
  results, transcripts, graduation, hall tickets, imports, semester rollover.
- **Owner:** Admin.
- **Users:** Admin, Dean, Faculty, Student.
- **Backend:** `app/modules/m11_sis/` (`validation_service.py`,
  `hallticket_service.py`, transcript/graduation workers).
- **Frontend:** `sis/*` (attendance dashboard, profiles, import history, semester
  rollover, exam sessions), `SemesterResultsPage`, `AcademicProgressPage`,
  transcripts.
- **Dependencies:** every academic module writes into or reads from SIS records.

---

## 10. Directory / Ownership recap (one page)

- **Who can teach a course** → an **active `subject_assignments`** row →
  `faculty_teaches_course`.
- **Who governs a programme** → `get_dean_program_ids` (Dean scope).
- **Who owns a paper** → **workflow** (`exam_workflow`): Internal → creating
  Faculty (Dean reviews); Board → the Board.
- **Faculty Directory** = teaching pool (no Board members).
- **Governance Directory** = Deans/Board + scope + responsibility grants.

---

## 11. Examination Workflow (end to end)

Module **M08**. This is the most gate-heavy part of VIDYA and the clearest
expression of "AI advises, humans decide". Everything below is enforced in the
**service layer** and mirrored in the repository.

### 11.1 The two workflows (`exam_papers.exam_workflow`)

| | **INTERNAL** | **BOARD_EXAM** |
|---|---|---|
| Example (ABC) | IA 1, MSE 2, CIE 1, Assignment | Mid Semester, End Semester, Supplementary, Improvement |
| Owner | the **creating Faculty** | the **Board** |
| Reviewer | the **Dean** (department-scoped) | the **Board** |
| Gates | Faculty submit → **Dean** approve/return | Faculty submit → [Scrutinizer] → **Board** approve/return → **Board** seal → release |
| Never sees | Board terminology in the UI | INTERNAL papers |

> **Terminology invariant (critical):** the backend *reuses* the generic
> `SUBMITTED` / `BOARD_APPROVED` / `BOARD_RETURNED` states for **both** workflows
> for storage compatibility. But the **UI must never expose Board terminology for
> an INTERNAL paper**. Internal papers render as **"Submitted to Dean" / "Dean
> Approved" / "Dean Returned"** (see `frontend/src/lib/examStatus.ts:
> examStatusLabel`). Board terminology appears only on BOARD_EXAM papers.

> **Workflow isolation invariant:** the Board must only ever see
> `workflow = BOARD_EXAM`; the Dean must only ever see `workflow = INTERNAL`.
> There is no overlap. Enforced in every list/decision endpoint
> (`list_board_pending`, `list_dean_pending`, `board_decide`, `dean_decide`,
> `list_all` forces BOARD_EXAM for BOARD role) and guarded in the UI
> (`BoardReviewPage` refuses INTERNAL papers).

### 11.2 Paper status lifecycle (`ExamPaperStatus`)

`DRAFT → GENERATING → GENERATED → SUBMITTED → BOARD_APPROVED → SEALED → RELEASED`
with `BOARD_RETURNED` (returned for edits) and `FAILED` (generation failed) as
side states.

**Human gates (only a human endpoint may cross these):**
- `submit_for_review()` → **SUBMITTED** (Gate 1).
- `board_decide()` / `dean_decide()` → **BOARD_APPROVED / BOARD_RETURNED**
  (Gate 2). Board for semester, Dean for internal — each guards the other's
  workflow out.
- `faculty_approve()` (INTERNAL only) → BOARD_APPROVED, self-approve path.
- `seal()` → **SEALED** (Gate 3, Board/Faculty as applicable).
- Celery tasks may only advance to **GENERATED** (generation) or **RELEASED**
  (timed release). **No Celery task ever advances a human gate.**

### 11.3 The paper blueprint (how questions are specified)

A paper's question plan can come from three sources, in **generation priority**:

`section_config (Part A/B/C)` > `blueprint (per-unit)` > `question_format (flat)`

- **Blueprint** (`exam_papers.blueprint`, JSONB) is the current primary model:
  per unit, a list of `{count, marks}` rows — e.g. *Unit 1: 3×2, 2×5, 1×10; Unit
  2: 2×2, 1×8*. Total marks is **derived** from the blueprint. The blueprint
  drives AI generation *exactly* (the prompt instructs the model to produce each
  `count`×`marks` line on the right unit; the offline mock generator produces
  exactly those questions keyed to that unit's topics) and is the **target plan**
  for manual papers.
- `section_config` remains for Part A/B/C papers (Board section structure).
- `question_format` (MCQ/short/long/problem counts) is retained for backward
  compatibility.

### 11.4 AI paper generation (optional)

`creation_mode = "AI"` dispatches `generate_exam_paper` on the Celery **heavy**
queue:

1. Load paper → set GENERATING.
2. Fetch the latest LOCKED/APPROVED **syllabus units** + **course outcomes**
   (M02) and course info (M01).
3. `question_generator.generate_questions(...)` with the blueprint / section /
   format, Bloom targets, COs — Gemini → Groq → DeepSeek fallback, then a
   **syllabus-aware mock** if no keys/all providers fail (the mock still honours
   the blueprint).
4. Bulk-write `exam_questions`; compute CO/unit coverage + Bloom's compliance
   (`blooms_compliance_reports`); set **GENERATED**.
5. Audit `EXAM_PAPER_GENERATION_COMPLETED`. On failure → back to DRAFT/FAILED,
   audit failure.

AI generation is **optional** and **advisory**: it drafts; Faculty then freely
edit before submitting.

### 11.5 Manual paper creation

`creation_mode = "MANUAL"` skips Celery/LLM entirely: the paper lands directly in
**GENERATED** as an empty, editable paper. The manual builder
(`ExamPaperEditorPage`) supports: **Add Question**, **Edit**, **Delete**,
**Duplicate** (copy inserted right after the original), **Move Up / Move Down**,
and **drag-and-drop reorder** — coexisting. A **Paper Validation** panel gives an
advisory pre-submission summary (total marks, unit coverage, CO mapping, Bloom's,
every question has marks + text). Manual editing is **always available** —
regardless of AI mode.

### 11.6 Dean approval flow (INTERNAL)

`/exams/dean/pending` (`DeanReviewPage`) lists **INTERNAL + SUBMITTED** papers,
**department-scoped** for a DEAN (only programmes they govern). Dean **Approve** →
Dean Approved; **Return** (comment required) → Dean Returned; Faculty edits the
same paper and resubmits. `dean_decide()` guards `exam_workflow == INTERNAL`.

### 11.7 Board approval flow (BOARD_EXAM)

`/exams/board/pending` → `BoardReviewPage` lists **BOARD_EXAM + SUBMITTED** papers
with model answers. Optional **Scrutinizer** (Gate 1.5, second-faculty reviewer).
Board **Approve/Return** (comment on return) via `board_decide()` (guards
`BOARD_EXAM`). On approval, questions are promoted into the **question bank**
(`is_approved=true`) for reuse.

### 11.8 Seal & Release

- **Seal (Gate 3):** an approved paper is AES/Fernet-encrypted
  (`paper_sealer.py`), the blob stored in S3, and status → **SEALED**. While
  sealed, questions and model answers are **inaccessible via the API** (enforced
  at the service layer). A timed `release_exam_paper` Celery task is scheduled at
  `release_at`.
- **Release:** the Celery task (or a Board force-release) transitions **SEALED →
  RELEASED**. Only then can papers be exported (`/export/pdf`, `/export/questions`
  for students; `/export/answers` for Faculty/Board/Admin only).

Why seal/release exists: an approved exam paper is a secret until the exam moment.
Encrypting it and gating access until a scheduled time is how VIDYA guarantees no
one — not even Faculty — can read a sealed paper early, while still automating the
release.

### 11.9 Internal Marks

`internal_marks_summary` (one row per student/course/year/semester):

`PENDING → FACULTY_SUBMITTED (Faculty submits, total computed) → DEAN_LOCKED (Dean
locks; immutable thereafter)`.

Pages: `InternalExamReleasePage` (course picker + marks table). Faculty submit,
Dean lock. After DEAN_LOCKED no further edits (service-enforced). This mirrors the
same two-gate, human-ratified pattern as papers.

### 11.10 Student visibility

Students never see draft/sealed content. They see only **released** question
papers (no model answers), their own **internal/semester results** (after lock),
and their subjects/syllabus/course-kits/learning-materials/timetable. Model
answers and correct options are **never** exposed to students.

### 11.11 Important M08 APIs (representative)

```
POST   /exams                              create (AI queue or MANUAL)
GET    /exams | /exams/all | /exams/{id}   list (role/workflow-scoped) / detail
GET    /exams/{id}/questions               questions (no answers; 403 if SEALED)
POST   /exams/{id}/questions               add manual question
POST   /exams/{id}/questions/{qid}/duplicate
PUT    /exams/{id}/questions/reorder
PATCH/DELETE /exams/{id}/questions/{qid}
POST   /exams/{id}/questions/{qid}/regenerate
POST   /exams/{id}/submit                  Gate 1
POST   /exams/{id}/faculty-approve         Gate 1 (INTERNAL self-approve)
POST   /exams/{id}/dean-decision           Gate 2 (INTERNAL)
POST   /exams/{id}/board-decision          Gate 2 (BOARD_EXAM)
POST   /exams/{id}/assign-scrutinizer | /scrutinize   Gate 1.5
POST   /exams/{id}/seal | /release         Gate 3 + release
GET    /exams/board/pending | /exams/dean/pending
GET    /exams/{id}/blooms | /coverage
GET    /exams/question-bank/{course_id}
POST   /exams/internal-marks | /{id}/submit | /{id}/lock
GET    /exams/{id}/export/pdf | /export/questions | /export/answers
```

---

## 12. Cross-cutting workflows

### 12.1 Syllabus workflow
DRAFT → AI-generate units/COs → submit → **approve gate** → LOCKED/APPROVED. Board
owns; no reject/return. Feeds M08 generation.

### 12.2 Course planning
Assigned Faculty build syllabus (M02) → course kit (M03) → learning materials
(M05) → assessments (M04/M08) for the courses they hold active assignments for.

### 12.3 Attendance
Faculty record attendance per section within a **configurable edit window**
(SIS/`m_academics`). Dashboard: `sis/attendance/FacultyAttendanceDashboard`,
`AttendanceTab`, `AttendanceStatusBadge`. Section access is gated by
`faculty_teaches_in_section`.

### 12.4 Research
Guide (responsibility) supervises research problems/documents/vivas (M07);
students submit and defend; ratification is human.

### 12.5 Analytics
Per-subject/section analytics (`AnalyticsTab`), fairness reports (M10), score
ledgers (M09), academic progress (M11). Analytics are **advisory**; they inform
human decisions, they don't make them.

---

## 13. Why the system works this way (summary)

- **Gates everywhere** because AI advises and humans decide — every consequential
  transition is a human action recorded in the database.
- **Schema-per-tenant** because institutional data isolation must be structural,
  not a `WHERE tenant_id=` you can forget.
- **Roles + Workspaces + Responsibilities** because a real academic is many things
  at once, and one identity with switchable hats keeps their work and audit trail
  coherent.
- **Assignment-based ownership** because "who may edit this course" must track the
  living fact of *who teaches it this term*, not a title.
- **Two directories** because subject allocation and governance must draw from
  structurally different pools (teachers vs authorities).
- **Workflow-owned papers** because internal assessment (Faculty→Dean) and
  semester examination (Board) are genuinely different institutional processes,
  and the UI must never blur them.
- **Seal/Release + append-only audit** because exam integrity and accountability
  are the product's reason to exist.

> New session: if you remember only one sentence — **VIDYA is a multi-tenant,
> gate-driven academic ERP where AI advises and a specific human role ratifies
> every consequential action, and ownership is decided by live assignment, not by
> title.**
