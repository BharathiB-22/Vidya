# VIDYA — Implemented Architecture (Viva Reference)

Derived by reading the codebase (`main.py` router wiring, module models, cross-module
imports, `pyproject.toml`, frontend routes). Not from documentation.

**Measured size:** 13 business modules, 12 core packages, ~64 database tables,
~570 API endpoints, 24 Celery background tasks, 310 React `.tsx` files (81 pages).

> **Correction to note before viva:** `CLAUDE.md` in the repo root documents only
> M01–M10 and does **not** mention `m11_sis`, `m_academics`, or `m04_assignments`.
> The docs are stale. This document reflects the code.

---

# PART 1 — MODULE INVENTORY

Evidence key: `EP` = API endpoints, `LOC` = Python lines, `T` = test files.

---

## M_ACADEMICS — Academic Structure  *(unnumbered in code, but load-bearing)*

- **Purpose:** Defines the institution's academic skeleton — who teaches what, to whom, when.
- **Size:** 46 EP · 6,331 LOC · 13 tables · 3 T
- **Tables:** `acad_departments`, `acad_programs`, `acad_batches`, `acad_semesters`,
  `acad_sections`, `acad_enrollments`, `subject_assignments`, `usn_sequence_counters`,
  `faculty_program_assignments`, `faculty_role_grants`, `dean_program_assignments`,
  `faculty_code_counters`, `elective_registrations`
- **Features:** Department→Program→Batch→Semester→Section hierarchy; student enrollment;
  faculty-to-subject assignment; USN (roll number) auto-generation; faculty code
  generation; role grants (GUIDE/EVALUATOR); Dean and Faculty program scoping
  (`dean_scope.py`, `faculty_scope.py`, `curriculum_scope.py`, `class_roster.py`);
  elective registration.
- **Integrates with:** imports M01, M11. **Imported by 11 packages** (77 references) —
  M01, M02, M03, M05, M06, M08, M09, M11, auth, onboarding, timetable.
- **Status:** **Fully implemented.**

## M11 — SIS (Student Information System)

- **Purpose:** The student record of truth — attendance through to graduation certificate.
- **Size:** **188 EP · 24,584 LOC · 79 files · 33 tables · 20 T** — largest module.
- **Sub-systems (each has router+service+repository+schemas):** attendance, marks,
  hall tickets, exam scheduling, results, transcripts, graduation, lifecycle,
  enrollment, directory, bulk import, bulk ops, rollover, search, capacity,
  validation, governance, self-service (`me_router`, `student_subjects_router`).
- **Notable tables:** `sis_student_profiles`, `sis_faculty_profiles`,
  `sis_attendance_sessions/records`, `sis_marks_components/entries`,
  `sis_hall_ticket_batches/eligibility`, `sis_exam_centers/sessions/schedules/invigilation`,
  `sis_grading_policies/bands`, `sis_result_declarations`, `sis_semester_results`,
  `sis_subject_results`, `sis_grace_marks_log`, `sis_transcripts` (+ semester/subject
  lines, verification log), `sis_graduation_audits/candidates/overrides/certificates`,
  `public_transcript_index`, `public_graduation_index`.
- **Features:** attendance capture with edit window; internal marks setup/entry/lock;
  hall-ticket eligibility + batch issue; exam centre & invigilation planning; grading
  policy bands; result declaration; grace marks; transcript generation with **public
  QR verification** (`/verify`); graduation audit → candidate → certificate with
  **public certificate verification**; student lifecycle history; bulk CSV import
  batches; semester rollover; global search.
- **Integrates with:** imports M01, M02, M_ACADEMICS. **Most-depended-on module —
  157 references** from auth, onboarding, M03, M05, M_ACADEMICS, workers.
- **Status:** **Fully implemented.** Best-tested module in the repo.

## M01 — Program Advisor

- **Purpose:** Curriculum definition — programs, courses, outcomes, prerequisites.
- **Size:** 35 EP · 6,608 LOC · 5 tables · 8 T
- **Tables:** `programs`, `program_outcomes`, `elective_baskets`, `courses`,
  `course_prerequisites`
- **Features:** Program CRUD; Program Outcomes (POs); course catalogue with
  auto course-code generation (`course_codes.py`); prerequisite chains; elective
  baskets; credit structure; AI-assisted program structure suggestion
  (`ai_provider.py`, worker `program_structure.py`); PDF/DOCX export (`program_export.py`).
- **Integrates with:** imports M02, M_ACADEMICS. Imported by M02, M03, M05, M08, M11, M_ACADEMICS.
- **Status:** **Fully implemented.** (AI = advisory only.)

## M02 — Syllabus

- **Purpose:** Per-course syllabus with outcomes and CO–PO mapping.
- **Size:** 32 EP · 9,940 LOC · 5 tables · 7 T
- **Tables:** `syllabi`, `course_outcomes`, `co_po_mappings`, `syllabus_units`,
  `syllabus_references`
- **Features:** AI syllabus generation (worker `syllabus_generation.py`); Course
  Outcomes (COs); **CO→PO mapping matrix** (NBA/NAAC accreditation artefact); unit
  breakdown with teaching hours; reference enrichment via **CrossRef + OpenLibrary**
  APIs (`reference_enrichment.py`); Board approval gate; PDF export.
- **Integrates with:** imports M01, M_ACADEMICS. Imported by M01, M03, M05, M06, M08, M11.
- **Status:** **Fully implemented.**

## M03 — Course Kit

- **Purpose:** Teaching material generation from an approved syllabus.
- **Size:** 34 EP · 5,009 LOC · 3 tables · 6 T
- **Tables:** `course_kits`, `kit_slides`, `kit_assignments`
- **Features:** AI slide-deck generation per unit (min slides configurable,
  `M03_MIN_SLIDES_PER_UNIT`); UG/PG complexity setting; assignment drafting;
  **PPTX/DOCX export** via `python-pptx`/`python-docx` (`course_kit_export.py`).
- **Integrates with:** imports M01, M02, M11, M_ACADEMICS.
- **Status:** **Fully implemented.**

## M04 — Assignments

- **Purpose:** Coursework assignment lifecycle (issue → submit → grade).
- **Size:** 22 EP · 2,436 LOC · 2 tables · 0 T
- **Tables:** `assignments`, `assignment_submissions`
- **Features:** Assignment creation, student submission, faculty grading panel.
- **Integrates with:** imports M09 only.
- **Status:** **Partially implemented** — functional and UI-wired, but **no test
  files** and the thinnest module of the coursework set. Undocumented in `CLAUDE.md`.

## M05 — Learning Materials

- **Purpose:** Curated learning packages + RAG-based student Q&A.
- **Size:** 15 EP · 3,993 LOC · 4 tables · 9 T
- **Tables:** `learning_packages`, `package_items`, `package_qa_sessions`, `package_qa_messages`
- **Features:** Package curation (`curate_learning_package.py`); **vector indexing into
  Qdrant** (`index_package_rag.py`, `embedder.py`); retrieval-augmented Q&A chat
  (`rag_service.py`, frontend `NotebookQA.tsx`).
- **Integrates with:** imports M01, M02, M11, M_ACADEMICS.
- **Status:** **Fully implemented.** Only module using the vector DB.

## M06 — Labs Evaluator

- **Purpose:** Lab/practical submission evaluation with integrity checks.
- **Size:** 28 EP · 4,560 LOC · 5 tables · 2 T
- **Tables:** `lab_assignments`, `lab_submissions`, `lab_evaluations`, `grade_ledger`,
  `evaluator_assignments`
- **Features:** Code execution in a **sandboxed subprocess** (10s timeout,
  `M06_CODE_TIMEOUT_SECONDS`, output capped); **AI-content detection**
  (`ai_scan.py`, threshold 0.75); **plagiarism via cosine similarity** (threshold 0.85);
  AI rubric scoring (`rubric_scorer.py`); `grade_ledger` = human ratification record;
  `lab_evaluations` stores `confidence_level` + **`prompt_hash`**.
- **Integrates with:** imports M02, M_ACADEMICS. Imported by M07.
- **Status:** **Fully implemented.**

## M07 — Research Supervision

- **Purpose:** PG research guidance — problem, document, viva.
- **Size:** 28 EP · 3,974 LOC · 3 tables · 1 T
- **Tables:** `research_problems`, `research_documents`, `viva_sessions`
- **Features:** AI research-problem generation (`problem_generator.py`); novelty
  search; document evaluation (`document_eval.py`); **viva session engine**
  (`viva_engine.py`, `process_viva_session.py`) with Whisper transcription endpoint
  (`M07_WHISPER_ENDPOINT` — **blank = mock transcription in dev**); AI-content
  threshold 0.75; max viva 45 min.
- **Integrates with:** imports M06.
- **Status:** **Partially implemented** — full code path, but transcription is
  mocked unless a Whisper endpoint is configured; 1 test file.

## M08 — Exam Setter

- **Purpose:** Question paper generation with Bloom's taxonomy compliance.
- **Size:** 36 EP · 7,513 LOC · 5 tables · 2 T
- **Tables:** `exam_papers`, `exam_questions`, `blooms_compliance_reports`,
  `question_bank`, `internal_marks_summary`
- **Features:** AI question generation from syllabus units (`question_generator.py`)
  tagged with **CO code + Bloom level** (REMEMBER→CREATE); MCQ/SHORT/LONG/PROBLEM_SOLVING;
  **A/B set membership** for parallel papers; model answers + marking schemes;
  **Bloom's compliance report**; question bank reuse; per-question regeneration
  (`regenerate_exam_question.py`); PDF export (`pdf_exporter.py`); paper release
  (`release_exam_paper.py`); board exams blocked from being MCQ-only.
- **Integrates with:** imports M01, M02, M_ACADEMICS. Imported by M09.
- **Status:** **Fully implemented.**

## M09 — Paper Admin

- **Purpose:** Exam conduct, evaluation and moderation — the exam back office.
- **Size:** **103 EP · 16,403 LOC · 31 files · 16 tables · 10 T** — 2nd largest.
- **Tables:** `evaluation_assignments`, `exam_mark_audit`, `scanned_script_batches`,
  `scanned_scripts`, `script_evaluations`, `script_moderation_reviews`,
  `exam_score_ledger`, `exam_board_sessions`, `exam_board_course_approvals`,
  `sis_revaluation_requests`, `sis_revaluation_evaluations`, `digital_exam_sessions`,
  `digital_exam_attempts`, `digital_exam_responses`, `ocr_review_queue`,
  `ocr_threshold_config`
- **Features:** answer-script scanning + batch intake; **OCR** (`ocr_scanned_script.py`)
  with quality detection (`detect_scan_quality.py`) and a **human OCR review queue**
  with configurable thresholds; AI script scoring (`script_scorer.py`,
  `score_scanned_script.py`); evaluator allocation; **double evaluation + comparison**;
  moderation review; **exam board sessions with per-course approval**; revaluation
  requests; **digital (online) exam sessions/attempts/responses**; exam analytics;
  compliance reporting; `exam_score_ledger` + `exam_mark_audit` = ratification trail.
- **Integrates with:** imports M08, M_ACADEMICS. Imported by M04.
- **Status:** **Fully implemented.**

## M10 — Bell Curve

- **Purpose:** Statistical mark normalisation, human-ratified.
- **Size:** 12 EP · 2,775 LOC · 3 tables · 1 T
- **Tables:** `bell_curve_analyses`, `bell_curve_decisions`, `bell_curve_normalized_scores`
- **Features:** score distribution analysis (`analyse_score_distribution.py`);
  proposed normalised scores; **explicit ratify step** (`bell_curve_decisions`,
  frontend `BellCurveRatifyPage.tsx`); PDF report (`report_builder.py`);
  fairness report.
- **Integrates with:** **zero cross-module imports** — fully standalone; consumes
  scores via its own tables/API.
- **Status:** **Partially implemented** — complete feature path and UI, but 1 test
  file and the weakest integration wiring.

---

# PART 2 — CORE PACKAGES (Phase 0 infrastructure)

| Package | EP | LOC | What it does |
|---|---|---|---|
| `auth` | 35 | 3,784 | Login, JWT, roles, first-login, admin + platform auth |
| `onboarding` | 25 | 4,840 | Institution/user bulk onboarding |
| `timetable` | 24 | 1,726 | Period/slot scheduling |
| `tenants` | 12 | 1,607 | **Schema-per-tenant** provisioning + migration runner |
| `governance` | 8 | 2,230 | Board approval gates |
| `calendar` | 8 | 637 | Academic calendar |
| `storage` | 5 | 1,126 | MinIO/S3 presigned upload/download |
| `monitoring` | 4 | 1,248 | Health, metrics, request middleware |
| `audit_log` | 3 | 994 | **Append-only** audit trail |
| `notifications` | 3 | 718 | Email/notification dispatch |
| `rate_limiting.py` | — | — | Request throttling |
| `security_headers.py` | — | — | Security response headers |

**Roles implemented:** `ADMIN`, `DEAN`, `FACULTY`, `STUDENT`, `BOARD` (base tenant roles)
+ `GUIDE`, `EVALUATOR` (grants via `faculty_role_grants`). 7 total.

**AuditLog columns:** `event_type`, `actor_user_id`, `actor_role`, `tenant_id`,
`schema_name`, `target_entity`, `target_id`, `metadata` (JSONB), `ip_address`,
`user_agent`, `created_at`.

---

# PART 3 — ANSWERS TO YOUR SIX QUESTIONS

## 1. Overall module hierarchy (in dependency order)

Built from actual `from app.modules.*` imports — **not a linear M01→M11 chain**.

```
LAYER 0  INFRASTRUCTURE      tenants · auth · audit_log · storage · monitoring
                             notifications · rate_limiting · security_headers

LAYER 1  FOUNDATION          M_ACADEMICS  <-->  M11_SIS
         (core ERP/SIS)      (structure)        (student records)
                             ^ 77 refs          ^ 157 refs

LAYER 2  CURRICULUM          M01 Program Advisor  <-->  M02 Syllabus

LAYER 3  TEACHING            M03 Course Kit · M05 Learning Materials · M04 Assignments

LAYER 4  ASSESSMENT          M06 Labs · M08 Exam Setter · M07 Research (-> M06)

LAYER 5  EXAM ADMIN          M09 Paper Admin (-> M08)

LAYER 6  ANALYTICS           M10 Bell Curve (standalone)
```

**Actual dependency edges (verified by grep):**

| Module | Imports |
|---|---|
| M_ACADEMICS | M01, M11 |
| M11_SIS | M01, M02, M_ACADEMICS |
| M01 | M02, M_ACADEMICS |
| M02 | M01, M_ACADEMICS |
| M03 | M01, M02, M11, M_ACADEMICS |
| M04 | M09 |
| M05 | M01, M02, M11, M_ACADEMICS |
| M06 | M02, M_ACADEMICS |
| M07 | M06 |
| M08 | M01, M02, M_ACADEMICS |
| M09 | M08, M_ACADEMICS |
| M10 | *(none)* |

**Most-depended-on:** M11 (157) > M_ACADEMICS (77) > M09 (73) > M01 (45) > M02 (41).

## 2. End-to-end workflow of the platform

```
ADMIN sets up institution
   -> tenants: provision schema        (core/tenants)
   -> onboarding: bulk import users    (core/onboarding)
   -> M_ACADEMICS: Dept > Program > Batch > Semester > Section
   -> M11_SIS: student & faculty profiles, USN generation
   -> M_ACADEMICS: assign faculty to subjects
   -> core/timetable + core/calendar: schedule

FACULTY / BOARD build curriculum
   -> M01: define Program, POs, Courses, prerequisites, credits
   -> M02: generate Syllabus (AI) -> COs -> CO-PO mapping -> units
   -> core/governance: BOARD approves syllabus   [GATE]
   -> M03: generate Course Kit slides from approved syllabus
   -> M05: curate Learning Package -> index into Qdrant

DELIVERY
   -> M11_SIS: attendance sessions + records
   -> M04: assignments issued -> submitted -> graded
   -> M06: lab submissions -> sandboxed run + AI scan + plagiarism -> grade_ledger
   -> M05: students ask questions -> RAG answers
   -> M07: (PG) research problem -> document eval -> viva session

ASSESSMENT
   -> M11_SIS: internal marks components -> entry -> LOCK
   -> M08: generate Question Paper (AI) -> Bloom compliance -> A/B sets -> release
   -> M11_SIS: hall ticket eligibility -> issue; exam centres + invigilation

EVALUATION
   -> M09: scan scripts -> OCR -> quality check -> human OCR review queue
   -> M09: AI score suggestion -> evaluator allocation -> double evaluation
   -> M09: moderation -> exam board session -> per-course approval  [GATE]
   -> M10: bell curve analysis -> proposed normalisation -> RATIFY  [GATE]

RESULTS
   -> M11_SIS: grading policy bands -> result declaration -> semester results
   -> M11_SIS: transcript -> PDF + QR -> public /verify
   -> M11_SIS: graduation audit -> candidate -> certificate -> public verify

Every AI output + every consequential action -> core/audit_log (append-only)
```

## 3. Which module is the foundation (core ERP/SIS)?

**M11_SIS together with M_ACADEMICS.** Not M01.

Evidence:
- M11_SIS: 188 endpoints, 24,584 LOC, 79 files, 33 tables, **157 inbound references** — every count is the highest in the repo.
- M_ACADEMICS: imported by 11 different packages including `auth`, `onboarding` and `timetable` — i.e. even the infrastructure layer depends on it.
- They are **mutually dependent** (`M_ACADEMICS -> M11`, `M11 -> M_ACADEMICS`), which is what makes them a single foundation layer rather than two stacked ones.

**Say it like this:** *M_ACADEMICS is the skeleton (structure: who teaches what, to whom). M11_SIS is the bloodstream (records: attendance, marks, results, transcripts). Everything else is built on top of those two.*

## 4. Which modules are AI-powered?

Modules with an actual LLM call in code (`ai_provider.py` / generator / scorer):

| Module | AI feature | File |
|---|---|---|
| M01 | Program structure suggestion | `ai_provider.py` |
| M02 | Syllabus + CO generation | `ai_provider.py` |
| M03 | Slide/course-kit generation | `ai_provider.py` |
| M05 | RAG embeddings + Q&A | `rag_service.py`, `embedder.py` |
| M06 | Rubric scoring, AI-content scan | `rubric_scorer.py`, `ai_scan.py` |
| M07 | Problem gen, doc eval, viva | `problem_generator.py`, `document_eval.py`, `viva_engine.py` |
| M08 | Question generation | `question_generator.py` |
| M09 | Answer-script scoring, OCR | `script_scorer.py` |

**Not AI-powered:** M_ACADEMICS, M11_SIS, M04, M10 — these are deterministic ERP/statistics.
(M10 is statistics, not AI. Be precise about this; faculty may probe it.)

**Provider config (`app/config.py`):**
```
AI_PROVIDER = "gemini" | "groq" | "deepseek" | "fallback"    default: "fallback"
   fallback = try Gemini -> Groq -> DeepSeek, stop at first success
GEMINI_MODEL   = gemini-2.0-flash
GROQ_MODEL     = llama-3.3-70b-versatile
DEEPSEEK_MODEL = deepseek-chat
```
Groq and DeepSeek are called through the **OpenAI-compatible** endpoint (`openai` SDK).
With **no API key**, generators fall back to deterministic templates
(`_Q_TEMPLATES` in M08, heuristic scoring in M06) — the system degrades, it does not crash.

**Governing rule (enforced in code):** AI advises, humans decide. Every AI score
lands in a ledger (`grade_ledger`, `exam_score_ledger`, `bell_curve_decisions`)
that requires a human ratification row before it counts.

## 5. Which modules are production-ready?

Judged on: endpoints + tables + tests + frontend wiring + absence of stubs.
*(I did not execute the test suite — this is a code-surface assessment.)*

**Production-ready (fully implemented, tested, UI-wired):**
- **M11_SIS** — 20 test files, largest surface
- **M_ACADEMICS** — foundation, universally consumed
- **M01 Program Advisor** — 8 test files
- **M02 Syllabus** — 7 test files
- **M03 Course Kit** — 6 test files
- **M05 Learning Materials** — 9 test files
- **M09 Paper Admin** — 10 test files
- **core:** auth (13 T), onboarding (14 T), tenants, audit_log, storage, monitoring

**Functional but thin on tests (demo-ready, not hardened):**
- **M08 Exam Setter** — 2 T against 36 EP / 7.5k LOC
- **M06 Labs Evaluator** — 2 T against 28 EP

**Partially implemented:**
- **M04 Assignments** — 0 test files
- **M07 Research Supervision** — 1 T; **viva transcription is mocked** unless `M07_WHISPER_ENDPOINT` is set
- **M10 Bell Curve** — 1 T; zero cross-module integration

**Planned / not in code:** nothing. Every module in `CLAUDE.md` exists, plus two it
never documented.

**Known technical debt (be honest if asked):**
- 3 `TODO`s in `core/storage/service.py` — `actor_role` hardcoded instead of read from user context.
- Elective credits have two sources of truth (slot vs option) — accepted debt.

## 6. Simple explanation for your viva

> **"Vidya is a multi-tenant academic ERP with AI assistance layered on top."**
>
> Multiple colleges run on one deployment. Each college gets its **own PostgreSQL
> schema**, so no college can ever see another's data — isolation is enforced at the
> database level, not just in application code.
>
> At the base sit two modules: **M_ACADEMICS**, which stores the academic structure
> — departments, programs, batches, semesters, sections, and which faculty teaches
> which subject — and **M11_SIS**, the student information system holding attendance,
> marks, results, transcripts and graduation records. Every other module reads from
> these two. That's why M11 is referenced 157 times across the codebase.
>
> On top of that foundation, the workflow follows how a real college actually runs.
> **M01** defines the program and courses. **M02** generates the syllabus using AI and
> maps Course Outcomes to Program Outcomes — that's the NBA/NAAC accreditation
> requirement. The Board approves it. **M03** turns the approved syllabus into slides;
> **M05** turns it into a searchable learning package students can ask questions
> against using RAG. **M04** and **M06** handle assignments and lab work — M06
> runs student code in a sandbox and checks for AI-generated content and plagiarism.
> **M08** generates question papers tagged by Bloom's taxonomy level. **M09** handles
> the exam back office: scanning answer scripts, OCR, AI-assisted scoring, double
> evaluation and moderation. **M10** does bell-curve normalisation. Results flow back
> into **M11**, which issues transcripts and degree certificates with QR codes anyone
> can verify publicly.
>
> The design rule throughout is **"AI advises, humans decide."** The AI never
> finalises a grade. It writes a suggestion, with its confidence score and a hash of
> the prompt used, into a ledger table. A human must then create a ratification
> record before that mark counts. Anything slow — AI generation, OCR, PDF building —
> runs on **Celery background workers** through **Redis**, so the API never blocks.
> Everything consequential is written to an **append-only audit log**.

---

# PART 4 — DIAGRAMS

All drawn from the implementation. Whiteboard-friendly.

---

## DIAGRAM 1 — Overall Workflow

```
   +-------------------------------------------------------------+
   |                        USER (browser)                        |
   +-------------------------------+-----------------------------+
                                   | 1. credentials
                                   v
   +-------------------------------------------------------------+
   |            LOGIN        core/auth  (LoginPage.tsx)           |
   +-------------------------------+-----------------------------+
                                   | 2. verify -> issue JWT
                                   v
   +-------------------------------------------------------------+
   |   ROLE AUTHENTICATION      core/auth + AuthGuard.tsx         |
   |   JWT carries: user_id · tenant_id · role                    |
   |   Roles: ADMIN DEAN FACULTY STUDENT BOARD GUIDE EVALUATOR    |
   +-------------------------------+-----------------------------+
                                   | 3. resolve tenant
                                   v
   +-------------------------------------------------------------+
   |   TENANT RESOLUTION        core/tenants                      |
   |   tenant_id  ->  SET search_path = <tenant_schema>           |
   |   (every query is scoped from here on)                       |
   +-------------------------------+-----------------------------+
                                   | 4. role -> nav tree
                                   v
   +-------------------------------------------------------------+
   |   WORKSPACE SELECTION      Sidebar.tsx                       |
   |   My Teaching · Research Supervision · Analytics ·           |
   |   My Department · Curriculum · Academic Governance ·         |
   |   Academic Operations · Examinations                         |
   +---+------------+------------+-----------+--------------+-----+
       |            |            |           |              |
       v            v            v           v              v
   +-------+   +---------+  +---------+  +--------+  +-----------+
   |M_ACAD |   |M01 M02  |  |M03 M04  |  |M06 M07 |  |M09 M10    |
   |M11 SIS|   |Curric.  |  |M05 Teach|  |M08 Asmt|  |Exam/Anlys |
   +---+---+   +----+----+  +----+----+  +---+----+  +-----+-----+
       |            |            |           |             |
       +------------+------+-----+-----------+-------------+
                           |
              +------------+------------+
              |                         |
              v                         v
   +---------------------+   +--------------------------+
   |  FastAPI ROUTER     |   |  Is it slow / AI work?   |
   |  (sync response)    |   |  yes -> enqueue          |
   +----------+----------+   +-------------+------------+
              |                            | 5. task -> Redis
              v                            v
   +---------------------+   +--------------------------+
   |  PostgreSQL         |   |  Redis (broker)          |
   |  tenant schema      |   +-------------+------------+
   |  ~64 tables         |                 |
   +----------+----------+                 v
              |              +--------------------------+
              |              |  Celery Worker (heavy)   |
              |              |  24 tasks                |
              |              +-------------+------------+
              |                            | 6. prompt
              |                            v
              |              +--------------------------+
              |              |  AI SERVICE              |
              |              |  Gemini -> Groq ->       |
              |              |  DeepSeek (fallback)     |
              |              +-------------+------------+
              |                            | 7. suggestion
              |                            v
              |              +--------------------------+
              |              |  Write result + PDF      |
              |              |  reportlab / pptx / docx |
              |              +------+-------------+-----+
              |                     |             |
              |                     v             v
              |            +-------------+  +-----------+
              |            | PostgreSQL  |  |  MinIO/S3 |
              |            | (ledger)    |  |  (file)   |
              |            +------+------+  +-----+-----+
              |                   |               |
              +-------------------+-------+-------+
                                          |
                                          v
                        +---------------------------------+
                        |  HUMAN RATIFICATION  [GATE]     |
                        |  grade_ledger /                 |
                        |  exam_score_ledger /            |
                        |  bell_curve_decisions           |
                        +----------------+----------------+
                                         |
                                         v
                        +---------------------------------+
                        |  core/audit_log (APPEND-ONLY)   |
                        |  actor · event · prompt_hash ·  |
                        |  confidence · target            |
                        +----------------+----------------+
                                         |
                                         v
                        +---------------------------------+
                        |  OUTPUT to USER                 |
                        |  screen · PDF · PPTX · QR-verif |
                        +---------------------------------+
```

### What it represents
The full request path for one user action, from login to a durable, audited output.

### Why designed this way
Three decisions drive the shape:
1. **Tenant resolution happens immediately after auth**, before any module runs — that is what makes multi-tenant isolation structural rather than something each module must remember.
2. **The path forks at "is it slow?"** — fast reads answer synchronously; AI/OCR/PDF go to Redis+Celery so the API thread never blocks.
3. **AI output cannot exit to the user as a decision.** It must pass a human ratification gate and land in the audit log first.

### How to explain it in viva
> "A user logs in, and auth issues a JWT carrying their user ID, tenant ID and role. The tenant ID immediately sets the PostgreSQL search_path, so from that point every query is automatically scoped to their college's schema. Their role determines which workspace they see in the sidebar. When they act, if it's a fast read, FastAPI answers straight from Postgres. If it's AI generation or OCR, it goes onto Redis, a Celery worker picks it up, calls the LLM, and writes the result plus a PDF to MinIO. Crucially, that AI result is only a suggestion — a human has to ratify it in a ledger table before it counts, and the whole thing is written to an append-only audit log."

### Likely faculty questions
**Q: Why not call the AI directly in the API request?**
A: LLM generation takes 10–60 seconds. Holding the API thread would exhaust the worker pool under load and the browser would time out. Celery lets us return a task ID immediately and let the client poll.

**Q: What if the AI service is down?**
A: `AI_PROVIDER=fallback` tries Gemini, then Groq, then DeepSeek. If all fail, generators fall back to deterministic templates. The system degrades but doesn't crash.

**Q: Where exactly is multi-tenancy enforced?**
A: At the database level — schema-per-tenant with `search_path` set per request, provisioned by `core/tenants`. Not by a `WHERE tenant_id = ?` that a developer could forget.

**Q: What stops the AI from awarding a grade?**
A: The AI writes to `lab_evaluations`/`script_evaluations` — suggestion tables. Marks only count when a human inserts a row into `grade_ledger` or `exam_score_ledger`. Separate tables, separate write paths.

---

## DIAGRAM 2 — System Architecture

```
+=============================================================+
|  USERS                                                      |
|  ADMIN · DEAN · FACULTY · STUDENT · BOARD · GUIDE · EVALUATOR|
+==============================+==============================+
                               | HTTPS
                               v
+=============================================================+
|  FRONTEND        React 18 + TypeScript + Vite               |
|  shadcn/ui + Tailwind · 310 .tsx files · 81 pages           |
|  AuthGuard.tsx · Sidebar.tsx (role-based workspaces)        |
+==============================+==============================+
                               | REST / JSON + JWT
                               v
+=============================================================+
|  API GATEWAY     FastAPI (app/main.py)                      |
|  Middleware: SecurityHeaders · Monitoring · RateLimiter ·CORS|
+==============================+==============================+
                               |
                               v
+=============================================================+
|  CORE / INFRASTRUCTURE LAYER                                |
|  auth · tenants · audit_log · storage · monitoring ·        |
|  notifications · onboarding · calendar · timetable ·        |
|  governance                                                 |
+==============================+==============================+
                               |
                               v
+=============================================================+
|  BUSINESS MODULES                       (~570 endpoints)    |
|                                                             |
|  FOUNDATION : M_ACADEMICS <--> M11_SIS                      |
|  CURRICULUM : M01 <--> M02                                  |
|  TEACHING   : M03 · M04 · M05                               |
|  ASSESSMENT : M06 · M07 · M08                               |
|  EXAM ADMIN : M09                                           |
|  ANALYTICS  : M10                                           |
+---+------------------+---------------+---------------+------+
    |                  |               |               |
    v                  v               v               v
+---------+      +----------+    +---------+    +-------------+
|PostgreSQL|     | MinIO/S3 |    |  Redis  |    |   Qdrant    |
|    16    |     |          |    |         |    |             |
|schema-per|     |vidya-    |    |broker + |    |vector store |
|-tenant   |     |assets    |    |cache    |    |(M05 RAG)    |
|~64 tables|     |PDF/PPTX  |    |         |    |             |
+---------+      +----------+    +----+----+    +------+------+
                                      |                ^
                                      v                |
                            +--------------------+     |
                            |  CELERY WORKERS    |     |
                            |  heavy queue       |-----+
                            |  24 tasks          |
                            +---------+----------+
                                      |
                     +----------------+----------------+
                     v                                 v
        +-------------------------+      +--------------------------+
        |  AI SERVICES            |      |  PDF / DOC GENERATION    |
        |  Gemini 2.0 Flash       |      |  reportlab (PDF)         |
        |  Groq llama-3.3-70b     |      |  python-pptx (slides)    |
        |  DeepSeek chat          |      |  python-docx (docs)      |
        |  (google-genai / openai)|      |  + QR verification codes |
        +-------------------------+      +------------+-------------+
                                                      |
                                                      v
                                          +--------------------------+
                                          |  OUTPUT -> MinIO -> USER |
                                          +--------------------------+

  EXTERNAL APIs: CrossRef + OpenLibrary (M02 reference enrichment)
                 Whisper endpoint (M07 viva transcription, optional)
```

### One line per component

| Component | One-line role |
|---|---|
| **React + TypeScript** | Role-aware UI; 81 pages, workspace chosen by JWT role. |
| **Vite** | Dev server and production bundler for the frontend. |
| **shadcn/ui + Tailwind** | Component library and styling system. |
| **FastAPI** | Async Python API; validates, authenticates, routes to modules. |
| **Middleware stack** | Security headers, request metrics, rate limiting, CORS. |
| **Core layer** | Cross-cutting services every module needs (auth, tenancy, audit, files). |
| **Business modules** | The 13 academic domains — the actual product logic. |
| **PostgreSQL 16** | System of record; one schema per college = hard isolation. |
| **MinIO / S3** | Object storage for PDFs, slides, scanned scripts, certificates. |
| **Redis** | Celery message broker and cache. |
| **Celery workers** | Run the 24 slow jobs off the API thread. |
| **Qdrant** | Vector database; stores M05 embeddings for RAG retrieval. |
| **AI services** | Gemini → Groq → DeepSeek fallback chain for all generation. |
| **reportlab / pptx / docx** | Produce PDFs, slide decks and documents. |
| **CrossRef / OpenLibrary** | External bibliographic APIs enriching syllabus references. |
| **Audit log** | Append-only record of every consequential and AI action. |

### What it represents
The deployable components and what talks to what.

### Why designed this way
Layered so each tier has one job and can scale independently: the API scales on request volume, workers scale on AI volume. Storage is split by data shape — relational facts in Postgres, large binaries in MinIO, embeddings in Qdrant, transient queue state in Redis. Using the right store for each is why no single database becomes the bottleneck.

### How to explain it in viva
> "It's a layered architecture. React talks to FastAPI over REST with a JWT. FastAPI runs middleware, then hands off to the core layer — auth, tenancy, audit — and then into whichever business module handles that domain. Persistence is split four ways by data type: PostgreSQL for records with a schema per college, MinIO for files, Redis for the job queue, Qdrant for vector embeddings. Anything slow is handed to Celery workers, which call the LLM and generate PDFs, and the finished file goes to MinIO for the user to download."

### Likely faculty questions
**Q: Why four different data stores?**
A: Each is right for one shape of data. Relational integrity needs Postgres. A 50 MB scanned script in a BLOB column would wreck query performance, so it goes to MinIO. Vector similarity search is what Qdrant exists for. Redis is in-memory for queue latency.

**Q: Why schema-per-tenant rather than a tenant_id column?**
A: A shared table relies on every developer remembering a `WHERE tenant_id` filter — one omission leaks another college's data. Separate schemas make isolation the database's job. Backup and restore per college also becomes trivial.

**Q: Why FastAPI over Django/Flask?**
A: Native async suits an I/O-bound workload (DB, S3, LLM calls), and Pydantic gives request/response validation plus auto-generated OpenAPI docs.

**Q: How does the frontend know a job finished?**
A: The endpoint returns a task ID immediately; the client polls task status until the worker writes the result.

---

## DIAGRAM 3 — Data Flow Diagrams

### Level 0 DFD (Context Diagram)

```
  +-----------+                                     +-----------+
  |  ADMIN    |                                     |  FACULTY  |
  |(External  |                                     |(External  |
  | Entity)   |                                     | Entity)   |
  +-----+-----+                                     +-----+-----+
        |                                                 |
        | institution, users,                syllabus,    |
        | program structure                  marks,       |
        |                                    attendance   |
        v                                                 v
  +=============================================================+
  |                                                             |
  |                   0.  VIDYA PLATFORM                        |
  |                                                             |
  |    (multi-tenant academic ERP with AI assistance)           |
  |                                                             |
  +=============================================================+
        ^                    ^                       ^
        |                    |                       |
        | submissions,       | approvals,            | scores,
        | queries            | ratifications         | scripts
        |                    |                       |
        | results,           | reports,              | allocations
        | transcripts        | analytics             |
        v                    v                       v
  +-----------+       +-----------+           +-------------+
  |  STUDENT  |       |   BOARD   |           |  EVALUATOR  |
  |(External  |       |  / DEAN   |           |  / GUIDE    |
  | Entity)   |       |(External) |           | (External)  |
  +-----------+       +-----------+           +-------------+

        +--------------------+        +--------------------+
        |  AI SERVICE        |        |  CROSSREF /        |
        |  (External Entity) |        |  OPENLIBRARY       |
        |  Gemini/Groq/      |        |  (External Entity) |
        |  DeepSeek          |        |                    |
        +---------+----------+        +---------+----------+
                  ^  |                          ^  |
       prompt     |  | suggestion,   query      |  | citation
                  |  v confidence               |  v metadata
        +=========================================================+
        |              0.  VIDYA PLATFORM                         |
        +=========================================================+
                            |
                            | verification request / result
                            v
                   +----------------------+
                   |  PUBLIC VERIFIER     |
                   |  (External Entity)   |
                   |  employer scanning   |
                   |  transcript QR code  |
                   +----------------------+
```

**External entities:** Admin, Faculty, Student, Board/Dean, Evaluator/Guide,
AI Service, CrossRef/OpenLibrary, Public Verifier.
*(Public Verifier is real — `/verify` and the certificate verify router are
unauthenticated public endpoints backed by `public_transcript_index` and
`public_graduation_index`.)*

### Level 1 DFD

```
 ADMIN                                                    FACULTY
   |                                                          |
   | institution + users                     syllabus request |
   v                                                          v
 +--------------------+                        +-------------------------+
 | 1.0 ONBOARD &      |                        | 3.0 BUILD CURRICULUM    |
 |     STRUCTURE      |                        |     (M01, M02)          |
 |  (tenants,         |                        |                         |
 |   onboarding,      |                        |                         |
 |   M_ACADEMICS)     |                        |                         |
 +---+-----------+----+                        +---+-------------+-------+
     |           |                                 |             ^
     v           v                                 v             | AI draft
 +=========+ +=========+                       +=========+  +----+--------+
 | D1      | | D2      |                       | D3      |  | AI SERVICE  |
 | tenant  | | acad_*  |<----------------------| syllabi |  +-------------+
 | schemas | | (struct)|      reads structure  | courses |
 +=========+ +====+====+                       +====+====+
                  |                                 |
                  | roster                          | approved syllabus
                  v                                 v
 +--------------------+                     +-------------------------+
 | 2.0 ENROL &        |                     | 4.0 GENERATE MATERIAL   |
 |     PROFILE        |                     |     (M03, M05)          |
 |     (M11_SIS)      |                     +-----+-------------+-----+
 +---+----------------+                           |             |
     |                                            v             v
     v                                       +=========+   +=========+
 +=========+                                 | D4      |   | D5      |
 | D6      |                                 |course_  |   | Qdrant  |
 | sis_    |                                 | kits    |   | vectors |
 | student |                                 +=========+   +=========+
 | profiles|                                       |             |
 +====+====+                                       v             v
      |                                        STUDENT  <----  RAG Q&A
      | student identity
      v
 +--------------------+   attendance,   +=========+
 | 5.0 DELIVER &      |   marks         | D7      |
 |     ASSESS         |---------------->| sis_    |
 |  (M04, M06, M07,   |                 | marks,  |
 |   M11 attendance)  |<----------------| attend  |
 +---+----------------+   roster        +=========+
     |
     | submissions
     v
 +=========+       AI scan / plagiarism / rubric
 | D8      |<--------------------------------------> AI SERVICE
 | lab_    |
 | submis- |       +=========+
 | sions   |------>| D9      |  human ratification only
 +=========+       | grade_  |
                   | ledger  |
                   +=========+
                        |
                        v
 +--------------------+     +=========+
 | 6.0 SET PAPER      |---->| D10     |
 |     (M08)          |     | exam_   |<----> AI SERVICE (question gen)
 +---------+----------+     | papers  |
           |                +=========+
           | released paper
           v
 +--------------------+     +=========+
 | 7.0 CONDUCT &      |---->| D11     |
 |     EVALUATE       |     | scanned |<----> AI SERVICE (OCR + scoring)
 |     (M09)          |     | scripts |
 +---------+----------+     +=========+
           |                     |
           | scores              | AI suggestion
           v                     v
 +--------------------+     +=========+
 | 8.0 MODERATE &     |     | D12     |
 |     NORMALISE      |---->| exam_   |  <-- BOARD ratifies here
 |     (M09 board,    |     | score_  |
 |      M10 bell)     |     | ledger  |
 +---------+----------+     +=========+
           |                     ^
           |                     | BOARD / DEAN
           v
 +--------------------+     +=========+
 | 9.0 DECLARE &      |---->| D13     |
 |     CERTIFY        |     | results,|
 |     (M11 results,  |     |transcr.,|
 |      transcript,   |     |gradua-  |
 |      graduation)   |     | tion    |
 +---------+----------+     +=========+
           |                     |
           | transcript + QR     v
           v                +=========+
       STUDENT              | D14     |
           |                | public_ |
           |                | *_index |
           v                +=========+
    PUBLIC VERIFIER <------------+

 ALL PROCESSES ------------------> +=========+
                                   | D15     |
                                   | audit_  |  APPEND-ONLY
                                   | logs    |
                                   +=========+
```

**Processes:** 1.0 Onboard & Structure · 2.0 Enrol & Profile · 3.0 Build Curriculum ·
4.0 Generate Material · 5.0 Deliver & Assess · 6.0 Set Paper · 7.0 Conduct & Evaluate ·
8.0 Moderate & Normalise · 9.0 Declare & Certify

**Data stores:** D1 tenant schemas · D2 `acad_*` · D3 `syllabi`/`courses` ·
D4 `course_kits` · D5 Qdrant vectors · D6 `sis_student_profiles` ·
D7 `sis_marks`/`sis_attendance` · D8 `lab_submissions` · D9 `grade_ledger` ·
D10 `exam_papers` · D11 `scanned_scripts` · D12 `exam_score_ledger` ·
D13 `results`/`transcripts`/`graduation` · D14 `public_*_index` · D15 `audit_logs`

### What it represents
Level 0 shows Vidya as one process and who exchanges data with it. Level 1 decomposes that into nine processes with the actual data stores between them.

### Why designed this way
The process boundaries follow the module boundaries in code, so the DFD is verifiable, not decorative. Note two deliberate features: **the AI service is an external entity, not a process** — we don't own it and it holds no state; and **D9/D12 (the ledgers) are separate stores from D8/D11 (the suggestions)**. That separation is the "humans decide" rule expressed in data.

### How to explain it in viva
> "At Level 0 the whole platform is one process, and around it sit the people who use it — admin, faculty, student, board, evaluator — plus three external systems: the LLM provider, CrossRef for citations, and the public verifier who scans a QR on a transcript. At Level 1 I've broken that into nine processes following my actual module boundaries. Data flows left to right: structure is created first, then curriculum, then materials, then assessment, then evaluation, then results. The important detail is that AI suggestions and ratified marks live in different data stores — D8 and D11 are what the AI wrote, D9 and D12 are what a human approved. Only the ledgers feed the results process."

### Likely faculty questions
**Q: Why is the AI service an external entity and not a process?**
A: A process transforms data inside the system boundary. The LLM is a third-party service outside our trust and deployment boundary — we send a prompt and receive a suggestion. Modelling it as external also makes the dependency explicit.

**Q: What is the Public Verifier — you invented that?**
A: No — it's implemented. `/verify` and the certificate verification router are unauthenticated public endpoints backed by `public_transcript_index` and `public_graduation_index`. An employer scans the QR on a transcript and confirms it's genuine without logging in.

**Q: Why is `grade_ledger` a separate data store from `lab_submissions`?**
A: That's the human-ratification requirement made physical. The AI can write a suggestion but has no path to the ledger. Only a human action inserts there, and only the ledger counts toward results.

**Q: Where's the audit log in the DFD?**
A: D15 — every process writes to it, append-only. I've drawn it once rather than nine arrows to keep it readable.

---

## DIAGRAM 4 — Module Interaction

**Your prompt assumed M01→M02→...→M11 as a chain. The code isn't a chain** — it's
hub-and-spoke around the foundation. This is the real graph.

```
                    +===============================+
                    |     FOUNDATION LAYER          |
                    |                               |
                    |  M_ACADEMICS <-------> M11_SIS|
                    |  (structure)          (records)|
                    |   77 refs             157 refs |
                    +===============================+
                       ^   ^   ^   ^   ^   ^   ^
                       |   |   |   |   |   |   |
        +--------------+   |   |   |   |   |   +--------------+
        |          +-------+   |   |   |   +-------+          |
        |          |           |   |   |           |          |
   +----+----+ +---+----+  +---+---+---+--+  +-----+----+ +---+---+
   |   M01   | |  M02   |  | M03  M05     |  | M06  M08 | |  M09  |
   | Program |<>|Syllabus|  | Kit  Learn  |  | Labs Exam| | Paper |
   | Advisor | |        |  |              |  |          | | Admin |
   +----+----+ +---+----+  +------+-------+  +----+-----+ +---+---+
        ^          ^              ^               ^           ^
        |          |              |               |           |
        +----------+--------------+               |           |
             M03, M05, M08, M11                   |           |
             all read M01 + M02                   |           |
                                                  |           |
                                        M07 ------+           |
                                     (imports M06 only)       |
                                                              |
                                        M04 ------------------+
                                     (imports M09 only)

                    +---------------+
                    |     M10       |   ZERO cross-module imports
                    |  Bell Curve   |   (standalone; consumes scores
                    +---------------+    via its own tables/API)
```

**Dependency edges, verified by `grep "from app.modules."`:**

```
  M_ACADEMICS  --> M01, M11
  M11_SIS      --> M01, M02, M_ACADEMICS
  M01          --> M02, M_ACADEMICS
  M02          --> M01, M_ACADEMICS
  M03          --> M01, M02, M11, M_ACADEMICS
  M04          --> M09
  M05          --> M01, M02, M11, M_ACADEMICS
  M06          --> M02, M_ACADEMICS
  M07          --> M06
  M08          --> M01, M02, M_ACADEMICS
  M09          --> M08, M_ACADEMICS
  M10          --> (none)
```

**Inbound reference counts (how much each module is depended on):**

```
  M11_SIS      ############################  157
  M_ACADEMICS  ##############                 77
  M09          #############                  73
  M01          ########                       45
  M02          #######                        41
  M08          ####                           26
  M05          ####                           26
  M06          ####                           24
  M10          ##                             13
  M07          ##                             13
  M04          ##                             10
  M03          ##                             10
```

**Reading the graph:**
- **Bidirectional pairs:** M_ACADEMICS↔M11, M01↔M02. Each pair is one cohesive layer.
- **Fan-in hubs:** M11 and M_ACADEMICS — everything reads them, they read almost nothing above.
- **Leaf/consumer modules:** M03, M05 (read curriculum + records, nobody reads them), M04, M07, M10.
- **Chains:** M02→M03 (syllabus→slides), M08→M09 (paper→evaluation), M06→M07 (lab eval reused for research eval).
- **M10 is fully decoupled** — deliberate, since normalisation is a policy step, not a data dependency.

### What it represents
Which modules import which, and therefore which can change without breaking others.

### Why designed this way
Dependencies point **downward toward the foundation**. Modules read structure and records from M_ACADEMICS/M11; the foundation doesn't reach up into teaching or exam logic. That keeps the blast radius of a change small — a change to M03's slide generator can't break the SIS. The two bidirectional pairs are the deliberate exceptions, where the domains are genuinely mutually defining (a program has semesters; a semester belongs to a program).

### How to explain it in viva
> "This isn't a linear chain — it's hub-and-spoke. M_ACADEMICS and M11_SIS form the foundation, and everything else depends on them: M11 is imported 157 times across the codebase, M_ACADEMICS 77. Above them, M01 and M02 form the curriculum layer, which the teaching and assessment modules read. Dependencies point downward — the SIS never imports the exam modules — so I can change how slides are generated without any risk to student records. M07 only depends on M06 because it reuses the evaluation engine, and M10 has zero cross-module imports because normalisation is a self-contained statistical step."

### Likely faculty questions
**Q: Isn't M_ACADEMICS ↔ M11 a circular dependency? That's a design flaw.**
A: It's mutual at package level but not at import-time — Python resolves it because the imports are inside functions and type-checking blocks rather than executing at module load. Conceptually they're one foundation layer split by responsibility: structure versus records. Merging them would give one unmaintainable 31,000-line module; splitting them further would mean constant cross-calls anyway. If I were hardening it, I'd extract the shared types into a fourth package to break the cycle formally.

**Q: Why does M04 only depend on M09?**
A: M04 reuses the evaluation-assignment machinery already built in M09 rather than duplicating it. It's the thinnest module and honestly the least developed — no test files yet.

**Q: Why is M10 isolated?**
A: Bell curve normalisation only needs a set of scores and returns proposed adjustments. Coupling it to the exam modules would buy nothing and make it harder to test. It reads scores through its own tables and API.

**Q: Which module would you refactor first?**
A: M09 — 103 endpoints and 16 tables in one module is doing too much. Digital exams, OCR review and the exam board are three separable concerns that could each be their own module.

---

# PART 5 — NUMBERS TO MEMORISE

```
  13 business modules        12 core packages
 ~64 database tables        ~570 API endpoints
  24 Celery heavy tasks     310 React .tsx files (81 pages)
   7 roles                    4 data stores (Postgres/MinIO/Redis/Qdrant)
   3 AI providers (Gemini -> Groq -> DeepSeek fallback)

  Biggest module:   M11_SIS   188 endpoints · 24,584 LOC · 79 files · 33 tables
  Second:           M09       103 endpoints · 16,403 LOC · 31 files · 16 tables
  Most depended on: M11_SIS   157 inbound references

  Thresholds (config.py):  AI content 0.75 · plagiarism 0.85 · code sandbox 10s
```

**Three sentences if you only get one minute:**
1. Vidya is a multi-tenant academic ERP — each college gets its own PostgreSQL schema, so isolation is enforced by the database, not by application code.
2. M_ACADEMICS and M11_SIS are the foundation — structure and student records — and all eleven other modules are built on them; M11 is referenced 157 times.
3. AI assists at eight points — syllabus, slides, RAG, lab scoring, research, questions, script scoring, OCR — but it never decides: every AI output is a suggestion in a ledger that a human must ratify, and everything is written to an append-only audit log.
