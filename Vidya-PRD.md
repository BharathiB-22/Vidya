# PRD — Vidya
**Version:** 1.0
**Date:** 2026-04-23
**Owner:** Srinivas / Fidelitus Corp
**Status:** Draft

> **Vidya** (Sanskrit: विद्या) — knowledge, learning, science. An end-to-end AI platform for the full university academic lifecycle.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Goals and Success Metrics](#3-goals-and-success-metrics)
4. [Users and Roles](#4-users-and-roles)
5. [Features — Phase 1](#5-features--phase-1)
6. [Features — Phase 2](#6-features--phase-2)
7. [Out of Scope](#7-out-of-scope)
8. [Technical Stack](#8-technical-stack)
9. [Data Model](#9-data-model)
10. [Key User Flows](#10-key-user-flows)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [Open Questions](#12-open-questions)
13. [Phases and Timeline](#13-phases-and-timeline)
14. [Deployment Architecture](#14-deployment-architecture)
15. [Ethical and Compliance Framework](#15-ethical-and-compliance-framework)

---

## 1. Overview

Vidya is a university-agnostic, multi-tenant AI platform that automates and augments the full academic lifecycle — from program design and course planning through content delivery, assessment, research supervision, and outcome reporting. It is deployable as a SaaS instance (cloud-agnostic, any major provider) or on-premises via Docker/Kubernetes, with each university receiving an isolated tenant namespace.

The platform is built around a non-negotiable principle: **AI advises, humans decide.** Every consequential action — approving a program structure, signing off an exam paper, ratifying a grade — passes through a human review gate before taking effect. AI confidence scores and full audit trails accompany every recommendation.

Vidya is designed to be onboarded institution by institution, with a modular architecture that allows a university to start with a single module and expand over time without re-platforming.

---

## 2. Problem Statement

Indian universities face a structural tension: growing student populations, shrinking faculty bandwidth, and rising expectations for accreditation-ready outcome documentation (NBA/NAAC).

Specific pain points the platform addresses:

| Pain Point | Impact |
|------------|--------|
| Faculty spend 40–60% of their time on course prep, not teaching | Reduced teaching quality and research output |
| Assessment integrity is deteriorating — AI-generated submissions, copying | Grade inflation, credential devaluation |
| Classroom delivery is one-size-fits-all | Students who fall behind are invisible until exams |
| Research supervision is inconsistent across guides | Wide variance in research quality and viva standards |
| Exam paper setting is manual, leak-prone, and unbalanced | Poor Bloom's level coverage, fairness issues |
| Evaluation is subjective and evaluator-biased | Bell curve anomalies, student grievances |
| Institutions have no structured analytics across the academic cycle | Leadership flying blind; accreditation reports built manually |

No current solution integrates all of these into a single platform with a unified data layer. Point tools (ChatGPT for notes, Turnitin for plagiarism, LMS for grades) create data silos and do not communicate with each other.

---

## 3. Goals and Success Metrics

### Phase 1 Success (measured 90 days after Phase 1 go-live)

| Goal | Metric | Target |
|------|--------|--------|
| Faculty adoption of AI-generated syllabi | % of active courses with AI-generated syllabus | ≥ 70% |
| Course kit generation speed | Time from course creation to full kit (slides + assignments) | ≤ 3 hours |
| AI detection accuracy | F1 score on AI-content detection in submissions | ≥ 0.90 |
| Platform reliability | API uptime | ≥ 99.5% |
| Faculty satisfaction | Net Promoter Score (NPS) from faculty survey | ≥ 40 |
| Onboarding velocity | Time from contract to first active program on platform | ≤ 2 weeks |

### Phase 2 Success (measured 90 days after Phase 2 go-live)

| Goal | Metric | Target |
|------|--------|--------|
| Exam paper generation adoption | % of exams set via Vidya | ≥ 80% |
| Auto-grading agreement | AI mark agreement with human evaluators (objective sections) | ≥ 93% |
| Bell curve normalisation | % of score distributions flagged and reviewed by Exam Board | 100% |
| Research evaluation coverage | % of research submissions scanned for plagiarism + AI content | 100% |
| Accreditation readiness | CO-PO attainment report auto-generated per semester | Yes |
| Multi-institution scale | Number of institutions live on platform | ≥ 3 |

---

## 4. Users and Roles

### Personas

| Role | Who They Are | Primary Actions |
|------|-------------|-----------------|
| **Super Admin** | Fidelitus Corp (platform operator) | Provision tenants, manage billing, global config |
| **Institution Admin** | University IT / Registrar | Manage faculty/student roster, configure modules, set policies |
| **Dean / Academic Council** | Senior academic leadership | Approve program structures, review analytics dashboard |
| **Faculty** | Course instructors, guides | Generate syllabi, course kits, exam papers; evaluate; supervise research |
| **Student** | Enrolled students | Access learning materials, submit assignments, attend viva, take quizzes |
| **Examination Board** | Exam cell / controller of exams | Review and approve exam papers, ratify bell curve normalisation |
| **Research Guide** | Faculty supervising post-graduate research | Accept/reject research problems, ratify research evaluations and viva reports |

### Scale per Instance

| Entity | Count |
|--------|-------|
| Students | ~10,000 |
| Faculty | ~400 |
| Active Programs | ~40 |
| Courses per Program | ~8–12 per semester |
| Concurrent users (peak) | ~2,000 |

---

## 5. Features — Phase 1

Phase 1 scope: Core platform infrastructure + M-01 through M-03 and M-05.
Timeline: Foundation sprint (6 weeks) + Feature build (20 weeks) = **26 weeks total.**

---

### F-00: Core Platform Infrastructure

**Description:** The shared foundation that all modules depend on. Must be built before any module work begins.

**Components:**
- Multi-tenant architecture — each institution gets an isolated schema/namespace (schema-per-tenant PostgreSQL)
- Role-based access control (RBAC) — roles as defined in Section 4
- Email + password authentication with JWT tokens; password reset via email OTP
- Institution onboarding flow — Super Admin provisions a new tenant with subdomain, admin user, and module config
- Audit log service — every AI recommendation, human decision, and override is written to an immutable audit log with timestamp, user, entity, and confidence score
- Async task queue (Celery + Redis) for all AI generation jobs — jobs are long-running and must not block the API
- Notification service — in-app and email notifications for approvals, flags, and task completions
- Analytics foundation — raw event tables for all user and AI actions (reporting built on top in Phase 2)
- Admin dashboard — tenant management, user management, module enable/disable toggles

**User story:** As a Super Admin, I want to provision a new university instance in under 15 minutes so that onboarding is fast and repeatable.

**Acceptance criteria:**
- [ ] Each tenant has an isolated data namespace; cross-tenant data access is impossible at the database layer
- [ ] All four roles (Admin, Faculty, Student, Board) can log in and see only their permitted views
- [ ] Every AI-generated output is logged to the audit table with: timestamp, user_id, model_used, prompt_hash, output_summary, confidence_score
- [ ] A new tenant can be provisioned via the Super Admin UI without touching code or config files
- [ ] Async jobs (AI generation) return a job ID immediately; client polls status; result available on completion
- [ ] Password reset flow works end-to-end via email OTP
- [ ] All API endpoints are behind authentication; unauthenticated requests return 401

---

### F-01: Program Structure Advisor (M-01)

**Description:** Faculty or Dean inputs a program type (e.g., MSc AIML, MBA, BCA) along with regulatory framework (UGC/AICTE norms), credit structure, and duration. The AI generates a semester-wise course sequence with rationale, elective combinations, prerequisite chains, and an articulation map showing how each course feeds into Programme Outcomes (POs). The Dean/Academic Council approves before the structure is finalised.

**User story:** As a Dean, I want to input a new program's parameters and receive a fully structured semester plan with rationale so that I can present it to the Academic Council in hours rather than weeks.

**Acceptance criteria:**
- [ ] Input form accepts: program name, degree type, duration (semesters), total credits, regulatory body, elective policy
- [ ] System generates: semester-wise course list, credit load per semester, elective options with prerequisites satisfied
- [ ] Each course placement includes a rationale (why this semester, which POs it addresses)
- [ ] Articulation map generated: CO → PO mapping matrix, exportable as PDF
- [ ] Regulatory compliance checked against UGC/AICTE credit norms; violations flagged with specific rule reference
- [ ] Dean can edit any course placement or rationale inline; changes tracked with version history
- [ ] Approval gate: Dean/Admin must explicitly approve before structure status changes to APPROVED
- [ ] Approved structure is locked for editing; a new version must be created for changes (version-controlled)
- [ ] Export: PDF and DOCX of the approved program structure

---

### F-02: Course Plan & Syllabus Generator (M-02)

**Description:** For each approved course, faculty inputs the course name and its Programme Outcomes. The AI generates a complete syllabus: Course Outcomes (COs) mapped to POs with Bloom's taxonomy levels, unit-wise topic breakdown with hours per unit, suggested pedagogy, and auto-curated reference book list. Faculty can edit; the system tracks every version and change rationale.

**User story:** As a Faculty member, I want to generate a complete, CO-PO aligned syllabus for my course so that I spend time refining it rather than building it from scratch.

**Acceptance criteria:**
- [ ] Input: course name, linked program (POs inherited), any custom instructions
- [ ] Output: minimum 4 COs, each tagged with Bloom's level (Remember/Understand/Apply/Analyse/Evaluate/Create), each mapped to ≥1 PO
- [ ] Unit breakdown: minimum 4 units, each with topic list, estimated hours, and suggested pedagogy (lecture, case study, lab, seminar)
- [ ] Reference list: minimum 5 references, sourced from open APIs (OpenLibrary, CrossRef); each with author, title, year, and type (textbook/reference/journal)
- [ ] Faculty can edit any field; edit saves with a change note (optional) and increments version number
- [ ] CO-PO matrix exported as PDF, DOCX, and structured JSON (for downstream modules)
- [ ] Syllabus status workflow: DRAFT → FACULTY_APPROVED → ADMIN_LOCKED
- [ ] Version history visible to faculty; rollback to any prior version supported

---

### F-03: Course Kit Builder (M-03)

**Description:** For each unit in an approved syllabus, the AI generates a complete course kit: multimodal lecture presentations (slides with faculty speaker notes and student handout versions), in-app quizlets embedded at strategic intervals, contextually generated case studies, and classwork/homework question sets with model answers and marking rubrics. Submissions are scanned for AI-generated content where AI is not permitted; flagged submissions go to a faculty review workflow before any penalty is applied. A locked-browser companion app (web) is provided for controlled assessments.

**Sub-feature F-03a: Presentations & Quizlets**

**User story:** As a Faculty member, I want to generate a slide deck for each unit with embedded quizlets so that I can run interactive lectures without manual preparation.

**Acceptance criteria:**
- [ ] Input: unit syllabus (from M-02), any custom tone/depth instructions
- [ ] Output per unit: slide deck (≥8 slides), faculty speaker notes per slide, student handout version (no notes), ≥2 in-app quizlets per deck
- [ ] Quizlets: multiple-choice or short-answer format; answer key stored server-side (not in client)
- [ ] Students access quizlets via a session link on their device (web app); responses logged in real time
- [ ] Quizlet results visible to faculty on their panel during the session; aggregate stats shown (% correct per option)
- [ ] Class participation scores auto-calculated from quizlet responses; stored for later LMS sync (Phase 2)
- [ ] Faculty can regenerate any individual slide or quizlet without regenerating the full deck
- [ ] Export: slide deck as PPTX and PDF; handout as PDF

**Sub-feature F-03b: Assignments, Case Studies & AI Detection**

**User story:** As a Faculty member, I want to generate assignments with model answers and detect AI-generated submissions so that assessment integrity is maintained without manual screening.

**Acceptance criteria:**
- [ ] Case studies generated per unit: contextual to domain, current events option (toggle), adjustable complexity level (UG/PG)
- [ ] Homework and classwork questions generated with: question, expected answer, marking rubric per criterion, Bloom's level tag
- [ ] AI-not-permitted flag configurable per assignment by faculty
- [ ] Submissions to flagged assignments scanned automatically: perplexity score + burstiness score + fine-tuned classifier; overall AI probability score (0–1) with confidence band
- [ ] Threshold configurable per institution (default: flag if AI probability > 0.75)
- [ ] Flagged submission workflow: faculty receives notification → reviews evidence panel (highlighted spans, scores) → decides: dismiss, warn, or escalate
- [ ] System never applies a penalty autonomously; human decision is mandatory before any grade impact
- [ ] Locked-browser web app: timed assessment sessions with watermarking and copy-paste disabled; available for classwork/homework
- [ ] Full audit trail: every submission scan result and faculty decision logged

---

### F-04: Learning Material Packager (M-05)

**Description:** For each course unit, the system auto-curates relevant learning materials — videos, articles, and research papers — from external sources (YouTube, arXiv, NPTEL, MIT OCW, publisher APIs). Materials are ranked by relevance, packaged into a notebook (internal Q&A interface), and made accessible via web and mobile. Faculty-generated notes are added to the same package. Content is version-controlled and updates when the syllabus changes.

**User story:** As a Student, I want to access a curated set of learning materials for each unit and ask questions about them conversationally so that I can study beyond the lecture without searching the internet manually.

**Acceptance criteria:**
- [ ] Sources ingested: YouTube (public videos via API), arXiv (papers via API), NPTEL (public content), MIT OCW (public content); extensible to additional sources
- [ ] Relevance ranking: each item scored by semantic similarity to unit syllabus using embedding model; top-N items selected (N configurable per institution, default 10 per unit)
- [ ] Faculty can add/remove items from the package; additions marked as "Faculty Recommended"
- [ ] Notebook Q&A: students can ask natural-language questions about the packaged material; answers generated via RAG over the package content with source citations
- [ ] Accessible via web app; mobile-responsive; offline reading mode for downloaded PDFs
- [ ] Package auto-updates when the syllabus version changes; students notified of updates
- [ ] Faculty notes (text or PDF upload) included in the package and indexed for Q&A
- [ ] Each material item shows: title, source, type (video/paper/article), relevance score, faculty rating if added manually

---

## 6. Features — Phase 2

Phase 2 scope: M-06 through M-10 + LTI 1.3 LMS integration + SSO/SAML + optional WhatsApp quizlet gateway.
Timeline: **24 weeks**, beginning immediately after Phase 1 go-live.

---

### F-05: Labs & Assignment Evaluator (M-06)

**Description:** Lab submissions and written assignments are auto-evaluated against expected outputs, rubrics, and test cases. Code submissions run through a unit test runner, static analyser, and cross-cohort plagiarism checker. Written submissions are scored by LLM rubric with human-readable justification per criterion. Faculty review and ratify all AI-suggested marks before they are recorded. A full moderation audit trail is maintained.

**User story:** As a Faculty member, I want AI to score student submissions against the rubric and present me with justified marks for ratification so that I spend my time reviewing rather than marking from scratch.

**Acceptance criteria:**
- [ ] Code submissions: executed in sandboxed container against faculty-provided test cases; pass/fail per test case; static analysis (unused imports, complexity score); cross-cohort similarity check (AST-based + token-based)
- [ ] Written submissions: LLM scores each rubric criterion; provides 1–3 sentence justification per criterion; overall score computed as weighted sum
- [ ] Plagiarism check: cosine similarity across all submissions in cohort; flag if similarity > configurable threshold (default 0.85)
- [ ] Faculty review panel: shows student submission alongside AI scores, justifications, plagiarism report, and AI content scan result
- [ ] Faculty can: accept AI score, edit any criterion score, add a comment; each action logged
- [ ] Marks are not written to the grade ledger until faculty explicitly ratifies
- [ ] Confidence level shown per AI score (high/medium/low); low-confidence submissions highlighted for priority review
- [ ] Moderation report exportable per assignment: all submissions, AI scores, human decisions, deltas

---

### F-06: Research Supervision System (M-07)

**Description:** AI assists guides and students across the full research lifecycle — from problem framing through document evaluation and video viva. The system proposes research problems based on faculty expertise and literature gaps. Student-proposed problems are evaluated for novelty, feasibility, and scope. Research documents are checked for format compliance, clarity, plagiarism, and AI-generated content. Video vivas are conducted by the AI, recorded, transcribed, and evaluated — with a report presented to the guide for ratification.

**User story:** As a Research Guide, I want AI to pre-screen research problems and documents so that I spend my supervision time on intellectual guidance rather than format checking and literature review.

**Acceptance criteria:**
- [ ] Problem proposal flow: student submits title + abstract + 3 research questions; system evaluates novelty (literature gap via arXiv/Semantic Scholar search), feasibility (scope vs. program duration), and clarity; outputs structured advisory with ACCEPT/REVISE/REJECT recommendation and reasoning
- [ ] Guide receives notification; must explicitly ACCEPT, REJECT, or request REVISION — system records decision and reasoning
- [ ] AI-proposed problems: system generates 3–5 candidate problems per guide based on their research area (input by guide or inferred from publication list); guide selects one to offer students
- [ ] Document evaluation: checks format compliance (section headers, citation style, word count), clarity score, plagiarism (against CrossRef, internal corpus), AI content probability; full report with highlighted spans
- [ ] Video viva: student accesses a time-limited session link; AI asks 5–10 structured questions based on the research document; follow-up questions generated based on responses; entire session recorded (video + audio)
- [ ] Viva transcript generated via ASR (Whisper or equivalent); AI evaluates responses for coherence, accuracy, and depth; report with timestamps presented to guide
- [ ] Guide ratifies or amends the viva evaluation before it is recorded
- [ ] All research artefacts (problem statement, documents, viva recording, evaluations) stored per student, accessible to guide and student

---

### F-07: Exam Paper Setter (M-08)

**Description:** Faculty inputs exam parameters — course, units to cover, total marks, and complexity distribution across Bloom's levels. The system generates question papers strictly adhering to the scheme of evaluation, with Bloom's level tags per question. Multiple paper variants are generated to reduce leak risk. Model answers and marking schemes are generated alongside. Faculty reviews, edits, and approves; the approved paper is sealed and encrypted until the scheduled release date.

**User story:** As a Faculty member, I want to generate a balanced, Bloom's-compliant exam paper in under 30 minutes so that question paper setting is a review task rather than a creation task.

**Acceptance criteria:**
- [ ] Input form: course (from M-02 syllabus), units to include (multi-select), total marks, marks distribution across Bloom's levels (Remember/Understand/Apply/Analyse/Evaluate/Create), question format (MCQ, short answer, long answer, problem-solving), any special instructions
- [ ] System generates: minimum 2 paper variants (Set A, Set B); each question tagged with Bloom's level, unit, and marks; model answer and marking scheme per question
- [ ] Bloom's level compliance: actual distribution within ±5% of requested distribution; flag if not achievable
- [ ] Faculty can: add, remove, or replace individual questions; edit model answers; reorder questions; re-generate specific sections
- [ ] Approval gate: Faculty submits paper → Examination Board reviews and approves → paper status changes to APPROVED
- [ ] Post-approval: paper sealed with AES-256 encryption; decryption key released automatically at configured exam date/time
- [ ] Sealed paper not accessible to any user (including Faculty who created it) until release
- [ ] Export post-release: question paper as PDF; model answers as separate PDF (for evaluators only, role-gated)
- [ ] Full version history: every edit, approver identity, and timestamp logged

---

### F-08: Paper Administration & Scanning (M-09)

**Description:** Exam papers are administered via the platform (digital) or physically (paper). Physical answer scripts are scanned via standard flatbed or high-speed scanners (TWAIN/WIA drivers — no proprietary hardware). Student IDs are stripped before routing to evaluators (double-blind evaluation). Objective sections are auto-evaluated; subjective sections are presented to faculty digitally with AI-suggested marks and justification. Faculty ratifies; final marks flow to the grade ledger.

**User story:** As an Examination Board member, I want scanned answer scripts to be routed to evaluators with student identity masked so that evaluation is blind and unbiased.

**Acceptance criteria:**
- [ ] Digital exam path: exam delivered via platform's locked-browser interface; responses captured directly; no scanning required
- [ ] Physical paper path: admin uploads scanned PDFs or uses TWAIN/WIA scanner integration (Canon, Epson, HP standard drivers); system ingests and de-skews images
- [ ] Student ID masking: roll number / student name stripped from scan before routing to evaluator; revealed only after all marks are finalised and locked
- [ ] Objective sections (MCQ, fill-in): auto-evaluated against answer key; score computed instantly
- [ ] Subjective sections: faculty evaluator views scanned pages on screen; AI suggests marks per question with justification; faculty annotates digitally (text comment, mark entry)
- [ ] Faculty cannot see student identity during evaluation; identity revealed only after final submission of marks
- [ ] Marks ratification: evaluator submits marks → second evaluator (if double evaluation configured) reviews → Examination Board finalises
- [ ] Final marks written to grade ledger only after Board finalisation
- [ ] Audit trail: every evaluator action, AI suggestion, and override logged with timestamp

---

### F-09: Bell Curve Normaliser (M-10)

**Description:** After all evaluations are finalised, the system analyses score distributions per course and per cohort, flags anomalies (zero inflation, ceiling effects, bimodal distributions), and suggests normalisation parameters to fit institutional grading policy. Cross-faculty comparison surfaces evaluator bias. Moderation recommendations are presented to the Examination Board for ratification.

**User story:** As an Examination Board member, I want AI to surface score distribution anomalies and suggest normalisation parameters so that grading fairness is data-driven rather than arbitrary.

**Acceptance criteria:**
- [ ] Distribution analysis triggered automatically when all marks for a course are finalised
- [ ] Anomalies detected and flagged: zero inflation (>15% scores at 0), ceiling effect (>20% scores at max), bimodal distribution (Hartigan's dip test), excessive skew (|skewness| > 1.5)
- [ ] Normalisation suggestions: linear scaling, percentile mapping, or grade boundary shift; each with projected outcome distribution shown
- [ ] Cross-faculty analysis: where multiple evaluators mark the same paper, mean and variance per evaluator shown; statistically significant outliers flagged
- [ ] Board review panel: shows raw distribution, flagged anomalies, suggested normalisation, projected normalised distribution
- [ ] Board can: accept suggestion, modify parameters, or reject and apply manual normalisation
- [ ] Final normalised marks written to grade ledger only after Board ratification
- [ ] Fairness report generated per semester: all courses, anomalies found, actions taken, exportable as PDF for accreditation records

---

### F-10: LMS Integration — LTI 1.3 (Phase 2 Add-on)

**Description:** Bidirectional integration with major LMS platforms (Moodle, Canvas, Blackboard, Brightspace) via the LTI 1.3 standard. Grade passback (from Vidya to LMS), roster sync (from LMS to Vidya), and deep-link launch (Vidya tools launchable from within LMS).

**User story:** As an Institution Admin, I want Vidya grades to sync automatically to our LMS so that faculty do not maintain two separate gradebooks.

**Acceptance criteria:**
- [ ] LTI 1.3 + Advantage (Names and Roles Provisioning, Assignment and Grade Services) implemented
- [ ] Roster sync: student and faculty lists pulled from LMS on schedule (configurable, default daily)
- [ ] Grade passback: finalised marks pushed to LMS gradebook within 5 minutes of ratification
- [ ] Deep-link launch: Vidya content (course kits, quizlets, material packages) launchable from LMS without re-authentication
- [ ] Supports: Moodle 4.x, Canvas LMS, Blackboard Learn, Brightspace D2L
- [ ] Institution Admin configures LTI credentials via UI; no developer intervention required

---

### F-11: SSO / SAML Authentication (Phase 2 Add-on)

**Description:** Replace email/password login with institutional SSO for universities that use Google Workspace, Microsoft 365, or LDAP/Active Directory.

**Acceptance criteria:**
- [ ] SAML 2.0 SP-initiated and IdP-initiated flows supported
- [ ] Google Workspace and Microsoft Entra ID (Azure AD) tested and documented
- [ ] LDAP/AD connector for on-prem identity providers
- [ ] Fallback to email/password for users not in the IdP
- [ ] Institution Admin configures SSO via UI with step-by-step guide; no code required

---

### F-12: WhatsApp Quizlet Gateway (Phase 2 Optional)

**Description:** Optional add-on replacing the in-app quizlet interface with WhatsApp Business API for institutions that prefer WhatsApp-native interactions. Responses ingested via webhook; class participation scores synced to grade ledger.

**Acceptance criteria:**
- [ ] WhatsApp Business API integration (Meta Cloud API)
- [ ] Students receive quizlet questions via WhatsApp; respond via text or button reply
- [ ] Responses ingested and scored in real time; class participation marks updated
- [ ] In-app quizlet remains the default; WhatsApp is an institution-level toggle
- [ ] Requires institution to provide their own WhatsApp Business Account credentials

---

## 7. Out of Scope

The following are explicitly excluded from both Phase 1 and Phase 2:

| Item | Reason |
|------|--------|
| M-04: Classroom Intelligence (camera sentiment analysis, face recognition) | Significant DPDP compliance risk for biometric data; hardware dependency; deferred to future major version |
| M-11: Exam Hall Anomaly Detection (CCTV-based proctoring) | Partner integration; out of Vidya's core build scope; can be plugged in via API when partner is engaged |
| Native mobile apps (iOS/Android) | Web app is mobile-responsive; native apps add significant build time for interns; deferred post-Phase 2 |
| Custom LLM fine-tuning or model training | Platform uses Gemini API and SOTA models as-is; fine-tuning is an institutional services engagement, not a platform feature |
| Billing and subscription management UI | Handled externally (Stripe or manual invoicing) in Phase 1 and 2; billing module is a future workstream |
| Student counselling / mental health modules | Outside academic lifecycle scope |
| Alumni management | Outside scope |
| ERP / finance system integration | Outside scope |

---

## 8. Technical Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend API** | Python 3.12 + FastAPI | Async-first, intern-friendly, strong AI/ML ecosystem |
| **Task Queue** | Celery + Redis | All AI generation jobs are async; Redis doubles as cache |
| **Frontend** | React 18 + TypeScript + Vite | Modern, well-documented, large community |
| **UI Component Library** | shadcn/ui + Tailwind CSS | Rapid UI development; accessible by default |
| **Primary Database** | PostgreSQL 16 (schema-per-tenant) | Relational integrity; JSON columns for semi-structured data |
| **Vector Database** | Qdrant (self-hosted) | Semantic search for RAG; open-source, Docker-native |
| **Object Storage** | S3-compatible (MinIO for on-prem; AWS S3 / GCS / Azure Blob for cloud) | Cloud-agnostic; presigned URLs for secure file access |
| **Primary LLM** | Google Gemini 1.5 Pro / 2.0 Flash via Vertex AI or Gemini API | Generation, syllabus, rubric scoring, viva Q&A |
| **Embedding Model** | text-embedding-004 (Google) | Semantic similarity, RAG retrieval |
| **AI Detection** | Perplexity + burstiness scoring + fine-tuned RoBERTa (academic corpus) | AI-generated content detection |
| **ASR (Viva)** | OpenAI Whisper (self-hosted) | Viva transcription; no external API dependency |
| **Plagiarism** | Cosine similarity over embeddings (internal corpus) + CrossRef API | Cross-cohort and literature plagiarism |
| **Containerisation** | Docker + Docker Compose (dev) + Kubernetes / Helm (prod) | Cloud-agnostic; runs on GCP/AWS/Azure/on-prem |
| **CI/CD** | GitHub Actions | Automated test, build, and deploy pipelines |
| **Monitoring** | Prometheus + Grafana | Metrics; alerting on error rate, queue depth, API latency |
| **Logging** | Structured JSON logs → Loki (self-hosted) | Searchable logs; no vendor lock-in |
| **Authentication** | JWT (Phase 1) + SAML 2.0 (Phase 2) | Progressive complexity aligned with team capability |
| **Scanner Integration** | TWAIN/WIA via browser-based scanner bridge | Standard drivers; no proprietary hardware |
| **API Design** | REST + OpenAPI 3.1 (auto-generated via FastAPI) | Every module API-first; documented automatically |

---

## 9. Data Model

### Core Entities

#### Tenant (Institution)
```
id              UUID PK
name            TEXT NOT NULL
slug            TEXT UNIQUE NOT NULL        -- subdomain identifier
config          JSONB                       -- module toggles, thresholds, policies
plan_type       ENUM(SAAS, ON_PREM, HYBRID)
created_at      TIMESTAMPTZ
is_active       BOOLEAN DEFAULT TRUE
```

#### User
```
id              UUID PK
tenant_id       UUID FK → Tenant
email           TEXT UNIQUE (per tenant)
password_hash   TEXT
role            ENUM(SUPER_ADMIN, ADMIN, DEAN, FACULTY, STUDENT, BOARD, GUIDE)
full_name       TEXT
identifier      TEXT                        -- student roll number or employee ID
is_active       BOOLEAN DEFAULT TRUE
created_at      TIMESTAMPTZ
last_login_at   TIMESTAMPTZ
```

#### Program
```
id              UUID PK
tenant_id       UUID FK → Tenant
name            TEXT NOT NULL
degree_type     TEXT                        -- MSc, MBA, BCA, etc.
duration_sems   INTEGER
total_credits   INTEGER
regulatory_body ENUM(UGC, AICTE, OTHER)
status          ENUM(DRAFT, APPROVED, ARCHIVED)
approved_by     UUID FK → User
approved_at     TIMESTAMPTZ
version         INTEGER DEFAULT 1
```

#### ProgramOutcome (PO)
```
id              UUID PK
program_id      UUID FK → Program
code            TEXT                        -- e.g. PO1, PO2
description     TEXT
```

#### Course
```
id              UUID PK
program_id      UUID FK → Program
name            TEXT
code            TEXT
semester        INTEGER
credits         INTEGER
is_elective     BOOLEAN DEFAULT FALSE
prerequisites   UUID[]                      -- FK array → Course
status          ENUM(ACTIVE, INACTIVE)
```

#### Syllabus
```
id              UUID PK
course_id       UUID FK → Course
version         INTEGER DEFAULT 1
units           JSONB                       -- array of {unit_no, title, topics[], hours, pedagogy}
references      JSONB                       -- array of {title, author, year, type, url}
status          ENUM(DRAFT, FACULTY_APPROVED, ADMIN_LOCKED)
created_by      UUID FK → User
approved_by     UUID FK → User
approved_at     TIMESTAMPTZ
```

#### CourseOutcome (CO)
```
id              UUID PK
syllabus_id     UUID FK → Syllabus
code            TEXT
description     TEXT
bloom_level     ENUM(REMEMBER, UNDERSTAND, APPLY, ANALYSE, EVALUATE, CREATE)
mapped_po_ids   UUID[]                      -- FK array → ProgramOutcome
```

#### CourseKit
```
id              UUID PK
syllabus_id     UUID FK → Syllabus
unit_number     INTEGER
presentations   JSONB                       -- array of slide objects
quizlets        JSONB                       -- array of {question, options, answer_key, bloom_level}
assignments     JSONB                       -- array of {question, model_answer, rubric, bloom_level}
case_studies    JSONB
version         INTEGER DEFAULT 1
created_at      TIMESTAMPTZ
```

#### Submission
```
id              UUID PK
assignment_ref  JSONB                       -- {kit_id, assignment_index}
student_id      UUID FK → User
content_url     TEXT                        -- object storage path
submitted_at    TIMESTAMPTZ
ai_scan_result  JSONB                       -- {probability, confidence, highlights}
ai_scan_status  ENUM(PENDING, CLEAN, FLAGGED)
ai_score        NUMERIC
human_score     NUMERIC
faculty_note    TEXT
status          ENUM(SUBMITTED, REVIEWED, RATIFIED, PENALISED)
reviewed_by     UUID FK → User
reviewed_at     TIMESTAMPTZ
```

#### LearningMaterial
```
id              UUID PK
syllabus_id     UUID FK → Syllabus
unit_number     INTEGER
source_type     ENUM(YOUTUBE, ARXIV, NPTEL, MIT_OCW, PUBLISHER, FACULTY)
title           TEXT
url             TEXT
relevance_score NUMERIC
is_faculty_added BOOLEAN DEFAULT FALSE
created_at      TIMESTAMPTZ
```

#### ResearchProblem
```
id              UUID PK
tenant_id       UUID FK → Tenant
student_id      UUID FK → User
guide_id        UUID FK → User
title           TEXT
abstract        TEXT
research_questions JSONB
novelty_score   NUMERIC
feasibility_score NUMERIC
ai_recommendation ENUM(ACCEPT, REVISE, REJECT)
ai_reasoning    TEXT
status          ENUM(PENDING, ACCEPTED, REVISION_REQUESTED, REJECTED)
guide_decision  ENUM(ACCEPT, REVISE, REJECT)
guide_note      TEXT
decided_at      TIMESTAMPTZ
```

#### ResearchDocument
```
id              UUID PK
research_problem_id UUID FK → ResearchProblem
version         INTEGER DEFAULT 1
file_url        TEXT
plagiarism_score NUMERIC
ai_content_score NUMERIC
format_score    NUMERIC
clarity_score   NUMERIC
evaluation_report JSONB
status          ENUM(SUBMITTED, EVALUATED, GUIDE_REVIEWED)
submitted_at    TIMESTAMPTZ
```

#### VivaSession
```
id              UUID PK
document_id     UUID FK → ResearchDocument
student_id      UUID FK → User
guide_id        UUID FK → User
scheduled_at    TIMESTAMPTZ
session_token   TEXT UNIQUE
video_url       TEXT
transcript      TEXT
ai_questions    JSONB
ai_evaluation   JSONB                       -- per-question scores and comments
guide_evaluation JSONB
status          ENUM(SCHEDULED, IN_PROGRESS, COMPLETED, GUIDE_RATIFIED)
completed_at    TIMESTAMPTZ
```

#### ExamPaper
```
id              UUID PK
course_id       UUID FK → Course
created_by      UUID FK → User
total_marks     INTEGER
complexity_dist JSONB                       -- {remember:%, understand:%, apply:%, analyse:%, evaluate:%, create:%}
sets            JSONB                       -- array of {set_label, questions[], model_answers[]}
status          ENUM(DRAFT, SUBMITTED, BOARD_APPROVED, SEALED, RELEASED)
approved_by     UUID FK → User
approved_at     TIMESTAMPTZ
sealed_at       TIMESTAMPTZ
release_at      TIMESTAMPTZ
encryption_key_ref TEXT                     -- reference to KMS key; not stored in DB
```

#### ScannedScript
```
id              UUID PK
exam_paper_id   UUID FK → ExamPaper
masked_id       TEXT UNIQUE                 -- random token used during evaluation
student_id      UUID FK → User             -- revealed only after finalisation
scan_url        TEXT
auto_score      NUMERIC                     -- objective sections
ai_suggested_score NUMERIC
human_score     NUMERIC
evaluator_id    UUID FK → User
evaluation_notes JSONB
status          ENUM(PENDING, IN_EVALUATION, MARKS_SUBMITTED, FINALISED)
```

#### ScoreDistribution
```
id              UUID PK
exam_paper_id   UUID FK → ExamPaper
raw_stats       JSONB                       -- {mean, std, skewness, min, max, distribution_array}
anomalies       JSONB                       -- array of {type, severity, description}
normalisation_suggestion JSONB
normalisation_params JSONB                  -- what was actually applied
status          ENUM(PENDING, BOARD_REVIEWED, APPLIED)
reviewed_by     UUID FK → User
reviewed_at     TIMESTAMPTZ
```

#### AuditLog
```
id              UUID PK
tenant_id       UUID FK → Tenant
user_id         UUID FK → User
action          TEXT                        -- e.g. SYLLABUS_GENERATED, SUBMISSION_FLAGGED
entity_type     TEXT
entity_id       UUID
ai_model        TEXT
ai_output       JSONB
confidence_score NUMERIC
human_decision  TEXT
created_at      TIMESTAMPTZ
```

### Key Relationships

```
Tenant ──< User
Tenant ──< Program ──< Course ──< Syllabus ──< CourseOutcome
                                             ──< CourseKit ──< Submission
Program ──< ProgramOutcome
Course  ──< ExamPaper ──< ScannedScript
                       ──< ScoreDistribution
User(student) ──< ResearchProblem ──< ResearchDocument ──< VivaSession
Syllabus ──< LearningMaterial
All entities ──> AuditLog
```

---

## 10. Key User Flows

### Flow 1: Faculty generates a course syllabus (M-02 — Phase 1)

1. Faculty logs in → navigates to **Courses** → selects an approved course
2. Clicks **Generate Syllabus** → form pre-populated with course name and linked POs
3. Optionally adds custom instructions (tone, depth, language)
4. Submits → async job created; Faculty sees "Generating..." status with job ID
5. Job completes (typically 30–90 seconds) → Faculty receives in-app notification
6. Faculty reviews syllabus: COs, Bloom's levels, unit breakdown, references
7. Faculty edits any field inline → each save logged as a new version with optional change note
8. Faculty clicks **Approve Syllabus** → status changes to FACULTY_APPROVED
9. Institution Admin locks the syllabus for the semester → status changes to ADMIN_LOCKED
10. Syllabus becomes available to downstream modules (M-03, M-05, M-08)

---

### Flow 2: Student submits an assignment; AI flags it (M-03 — Phase 1)

1. Faculty publishes an assignment from CourseKit (AI-not-permitted flag ON)
2. Student logs in → navigates to **Assignments** → views assignment details
3. Student uploads submission (PDF or DOCX) via the platform or completes in the locked-browser app
4. System receives submission → async AI scan job triggered
5. Scan completes → result: AI probability 0.83 (above 0.75 threshold) → status: FLAGGED
6. Faculty receives in-app notification: "Submission by [Student Name] flagged for AI content (83% probability)"
7. Faculty opens **Evidence Panel**: highlighted text spans, perplexity score graph, burstiness score, comparison with known AI patterns
8. Faculty makes a decision: **Dismiss** (false positive) / **Warn student** / **Escalate to Admin**
9. Decision logged to AuditLog with faculty ID, timestamp, and reasoning note
10. System updates submission status accordingly; student notified of outcome

---

### Flow 3: Examination Board approves and seals an exam paper (M-08 — Phase 2)

1. Faculty opens **Exam Paper Setter** → selects course, configures parameters (marks, Bloom's distribution, question types)
2. System generates Set A and Set B with model answers → async job (~60–120 seconds)
3. Faculty reviews: checks Bloom's compliance report, edits or replaces questions, reviews model answers
4. Faculty submits paper for Board approval → status: SUBMITTED
5. Examination Board member receives notification; opens paper in read-only review view
6. Board member approves (or returns with comments) → status: BOARD_APPROVED
7. Faculty configures exam date/time for release → clicks **Seal Paper**
8. System encrypts paper with AES-256; decryption key stored in KMS with time-lock policy
9. Status: SEALED — paper inaccessible to all users including the creator
10. At scheduled release time → system auto-decrypts; paper available for distribution; status: RELEASED
11. AuditLog records: who created, who approved, when sealed, when released

---

### Flow 4: Institution Admin onboards a new university (Core Platform)

1. Super Admin logs into Vidya Admin Console
2. Clicks **New Tenant** → enters: institution name, admin email, subdomain slug, plan type, modules to enable
3. System provisions: isolated PostgreSQL schema, admin user account, default config
4. Admin user receives welcome email with temporary password and setup guide link
5. Admin logs in → configures: program list, faculty roster (CSV import), student roster (CSV import)
6. Admin enables modules → configures thresholds (AI detection threshold, plagiarism threshold, normalisation policy)
7. Admin creates first program → assigns Dean → Dean receives notification to begin Program Structure Advisor flow
8. Institution is live within 2 business days of provisioning

---

## 11. Non-Functional Requirements

| Requirement | Target | Notes |
|-------------|--------|-------|
| **API Response Time** | < 2 seconds (p95) for synchronous endpoints | Async job endpoints return job ID immediately; status polling returns in < 200ms |
| **AI Job Completion** | < 120 seconds (p95) for single-module generation jobs | Syllabus, course kit unit, exam paper set; longer jobs show progress indicator |
| **Platform Uptime** | ≥ 99.5% monthly | Measured at API gateway; planned maintenance excluded |
| **Concurrent Users** | 2,000 concurrent users per instance without degradation | Load tested before Phase 1 go-live |
| **Data Isolation** | Zero cross-tenant data leakage | Schema-per-tenant; validated by automated test suite in CI |
| **Encryption at Rest** | AES-256 for all stored files and database sensitive fields | Exam papers use additional KMS-managed time-lock encryption |
| **Encryption in Transit** | TLS 1.3 minimum for all API and web traffic | HSTS enforced |
| **Authentication** | JWT tokens expire in 1 hour; refresh tokens expire in 7 days | Refresh token rotation on every use |
| **Audit Completeness** | 100% of AI decisions and human overrides logged | Audit log is append-only; no update or delete operations |
| **DPDP Act 2023 Compliance** | Data minimisation; purpose limitation; student right to request human review of any AI decision | Privacy notice shown to all users on first login; consent recorded |
| **Data Residency (On-Prem)** | No student data leaves institution network | LLM calls use institution's own Gemini API key; embeddings computed locally or via institution's GCP project |
| **Scalability** | Kubernetes horizontal pod autoscaling; database connection pooling via PgBouncer | Designed for 5x current load without architecture change |
| **Backup** | Daily automated database backups; 30-day retention | Backups tested monthly via restore drill |
| **Accessibility** | WCAG 2.1 Level AA for all web interfaces | Keyboard navigation, screen reader support, colour contrast |
| **Browser Support** | Chrome 120+, Firefox 120+, Safari 17+, Edge 120+ | Mobile browsers (Chrome/Safari on iOS/Android) for student-facing pages |
| **Intern-Safe Architecture** | Each module independently deployable; no circular dependencies between module services | Module boundaries enforced via API contracts; shared code only via internal packages |

---

## 12. Open Questions

| # | Question | Owner | Target Resolution |
|---|----------|-------|-------------------|
| OQ-01 | NotebookLLM in M-05: should this be Google's NotebookLM (external service, data leaves platform) or an internal RAG-based Q&A? On-prem deployments cannot use external NotebookLM. | Srinivas | Before Phase 1 build sprint begins |
| OQ-02 | Scanner integration (M-09 / Phase 2): TWAIN/WIA requires a local bridge application running on the scanning computer. Is a browser-based scanner bridge acceptable, or do institutions prefer a desktop app? | Srinivas + first Phase 2 pilot institution | Before Phase 2 sprint 1 |
| OQ-03 | Video viva storage (M-07): how long should viva recordings be retained? Suggest 3 years (aligned with degree duration) but needs institutional policy input. Storage costs are significant at scale. | Institution Admin (per tenant config) | Before Phase 2 sprint 1 |
| OQ-04 | Gemini API vs Vertex AI: Gemini API (direct) is simpler; Vertex AI provides enterprise controls (VPC, audit, data residency) but more complex setup for interns. Which is the default for SaaS tenants? | Srinivas | Before Foundation sprint begins |
| OQ-05 | Multi-language support: the platform currently assumes English. Indian universities teach in regional languages for some programs. Is regional language support (Hindi, Kannada, Tamil, etc.) in scope for Phase 1, Phase 2, or future? | Srinivas | Before Phase 1 build sprint begins |
| OQ-06 | Pricing model: SaaS tier is per-student, per-institution-flat, or per-module? This affects tenant config complexity and must be decided before the first commercial onboarding. | Srinivas | Before Phase 1 go-live |
| OQ-07 | Research viva: is a live video call (student and AI system in real time) required, or is an async flow acceptable (student records responses to AI questions on their own time)? Real-time adds significant infrastructure complexity. | Srinivas | Before Phase 2 sprint 3 |

---

## 13. Phases and Timeline

### Phase 0: Foundation (Weeks 1–6)

**Goal:** Build the shared infrastructure that all modules depend on. No module features are built in this sprint. Both interns work together under Srinivas's direction to establish architecture patterns, coding standards, and CI/CD before any feature work begins.

| Week | Milestone |
|------|-----------|
| 1 | Repository setup, Docker Compose dev environment, GitHub Actions CI pipeline, coding standards documented |
| 2 | Database schema (core entities), Alembic migrations, PgBouncer connection pooling |
| 3 | Auth service (registration, login, JWT, refresh tokens, RBAC middleware) |
| 4 | Tenant provisioning flow, schema-per-tenant isolation, Super Admin UI |
| 5 | Async task queue (Celery + Redis), notification service, audit log service |
| 6 | Object storage integration (MinIO local, S3-compatible), monitoring (Prometheus + Grafana), load test baseline |

**Exit criteria:** A new tenant can be provisioned; a user can log in; an async job can be submitted and polled; all tests pass in CI.

---

### Phase 1: Teach & Prepare (Weeks 7–26)

**Goal:** Deliver M-01, M-02, M-03, M-05. Each module is a 5-week sprint. One intern owns the backend; the other owns the frontend. Srinivas reviews every PR before merge.

| Sprint | Weeks | Module | Key Deliverable |
|--------|-------|--------|-----------------|
| P1-S1 | 7–11 | M-01 Program Structure Advisor | Program creation, AI structure generation, articulation map, approval gate |
| P1-S2 | 12–16 | M-02 Syllabus Generator | Syllabus generation, CO-PO matrix, version control, export |
| P1-S3 | 17–21 | M-03 Course Kit Builder | Slide generation, in-app quizlets, assignment generation, AI detection workflow |
| P1-S4 | 22–26 | M-05 Learning Material Packager | Source ingestion, relevance ranking, RAG notebook Q&A, offline access |

**Phase 1 go-live:** End of Week 26. First pilot institution onboarded. Faculty NPS survey sent at Week 30 (30 days post go-live).

---

### Phase 2: Assess & Research (Weeks 27–50)

**Goal:** Deliver M-06 through M-10, LTI 1.3, SSO/SAML. Each module is a 4–5 week sprint.

| Sprint | Weeks | Module | Key Deliverable |
|--------|-------|--------|-----------------|
| P2-S1 | 27–31 | M-06 Labs & Assignment Evaluator | Code sandbox, rubric scoring, plagiarism, faculty review panel |
| P2-S2 | 32–36 | M-08 Exam Paper Setter | Paper generation, Bloom's compliance, multi-set, sealing + encryption |
| P2-S3 | 37–41 | M-09 Paper Administration & Scanning | Scanner ingestion, ID masking, digital evaluation, auto-score |
| P2-S4 | 42–46 | M-10 Bell Curve Normaliser | Distribution analysis, anomaly detection, Board review, normalisation |
| P2-S5 | 47–50 | M-07 Research Supervision + LTI 1.3 + SSO | Research lifecycle, video viva, LMS grade sync, SAML auth |

**Phase 2 go-live:** End of Week 50. Full platform available to all pilot institutions.

---

### Summary

| Phase | Scope | Duration | Team |
|-------|-------|----------|------|
| 0 — Foundation | Core infra, auth, multi-tenancy | 6 weeks | 2 interns + Srinivas |
| 1 — Teach & Prepare | M-01, M-02, M-03, M-05 | 20 weeks | 2 interns + Srinivas |
| 2 — Assess & Research | M-06, M-07, M-08, M-09, M-10 + LTI + SSO | 24 weeks | 2 interns + Srinivas |
| **Total** | **9 modules + core platform** | **~50 weeks** | |

---

## 14. Deployment Architecture

### SaaS (Cloud — Multi-Tenant)

```
[Internet]
    │
[CDN / WAF]  ←── Static frontend assets (React build)
    │
[API Gateway / Load Balancer]
    │
┌───────────────────────────────────────────────┐
│  Kubernetes Cluster (any cloud: GCP/AWS/Azure) │
│                                               │
│  [API Pods: FastAPI]  ←── [Celery Worker Pods]│
│         │                        │            │
│  [Redis (Cache + Queue)]         │            │
│         │                        │            │
│  [PostgreSQL (PgBouncer)]  ←─────┘            │
│  [Qdrant Vector DB]                           │
│  [MinIO / S3-compatible Object Store]         │
│  [Prometheus + Grafana]                       │
│  [Loki (Logs)]                                │
└───────────────────────────────────────────────┘
    │
[Gemini API / Vertex AI]  ←── External LLM calls
[Whisper (self-hosted pod)]
[External APIs: arXiv, YouTube, CrossRef]
```

- Each tenant is an isolated PostgreSQL schema within the shared cluster
- Tenant data is logically separated; physical separation (dedicated DB) available for enterprise on-prem

### On-Premises

Same Kubernetes/Helm chart deployed on institution's own servers or private cloud. Differences:
- Object storage: MinIO (bundled in Helm chart)
- LLM: Institution's own Gemini API key pointed at their GCP project (data residency maintained)
- Whisper: runs as a pod in the cluster (no external ASR call)
- All student data remains within institution network

### Multi-Instance Scaling

Each institution can be:
- **Shared SaaS**: schema-per-tenant on shared cluster (cost-effective for smaller institutions)
- **Dedicated SaaS**: dedicated namespace/cluster for larger institutions or those with data sensitivity requirements
- **On-Prem**: full stack on institution hardware

A single Helm chart + environment config file drives all three modes.

---

## 15. Ethical and Compliance Framework

### DPDP Act 2023 (India) Compliance

| Obligation | Implementation |
|-----------|----------------|
| **Purpose Limitation** | Each module collects only the data it needs; no cross-module data aggregation without explicit config |
| **Data Minimisation** | Student biometric data (excluded M-04/M-11) not collected; viva video retained per configurable retention policy |
| **Transparency** | Privacy notice displayed on first login; all AI tools disclosed to students; no hidden surveillance |
| **Consent** | Explicit consent recorded for video viva recording; consent logs stored |
| **Right to Correction** | Students can request correction of AI-generated records via Institution Admin |
| **Right to Human Review** | Students can request human review of any AI-generated grade or flag; this is enforced at the system level — no final decision is made without a human ratification step |
| **Data Fiduciary** | Institution is the Data Fiduciary; Fidelitus Corp is the Data Processor; DPA agreement mandatory before onboarding |
| **Breach Notification** | Automated alerting on anomalous data access; incident response runbook included in operator documentation |

### Human-in-the-Loop Gates (Non-Negotiable)

The following actions **cannot** be completed by the AI system autonomously — a human approval action is required at the database level (not just in the UI):

| Gate | Human Actor |
|------|-------------|
| Program structure approval | Dean / Academic Council |
| Syllabus lock | Institution Admin |
| AI detection flag → penalty | Faculty |
| Exam paper approval | Examination Board |
| Assignment marks ratification | Faculty |
| Research problem accept/reject | Research Guide |
| Viva evaluation ratification | Research Guide |
| Bell curve normalisation application | Examination Board |
| Scanned script marks finalisation | Examination Board |

### AI Transparency

- Every AI-generated output displayed in the UI includes: model name, generation timestamp, confidence score (where applicable)
- Audit log is immutable and accessible to Institution Admins for compliance review
- Faculty are shown AI reasoning (justifications, rubric breakdowns) — not just scores
- Students are informed which aspects of their assessment involved AI assistance

### No Autonomous Adverse Action

The system is prohibited — at the application logic level — from:
- Recording a failing grade without human ratification
- Applying a penalty for AI-detected content without faculty decision
- Rejecting a research problem without guide confirmation
- Taking any action that negatively affects a student's academic record without a logged human decision

---

---

## 16. Kubernetes Resource Specification & Auto-Scaling

### Pod Resource Limits

| Service | Replicas (min→max) | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---------|-------------------|-------------|-----------|----------------|--------------|
| `vidya-api` (FastAPI) | 2 → 10 | 250m | 1000m | 256Mi | 1Gi |
| `vidya-worker` (Celery AI jobs) | 2 → 20 | 500m | 2000m | 512Mi | 2Gi |
| `vidya-worker-heavy` (Celery viva/scan jobs) | 1 → 5 | 1000m | 4000m | 1Gi | 4Gi |
| `vidya-frontend` (React, Nginx) | 2 → 6 | 100m | 250m | 64Mi | 256Mi |
| `redis` | 1 (StatefulSet) | 250m | 500m | 256Mi | 512Mi |
| `qdrant` | 1 → 3 | 500m | 2000m | 1Gi | 4Gi |
| `whisper-asr` | 1 → 4 | 1000m | 4000m | 2Gi | 6Gi |
| `prometheus` | 1 | 250m | 500m | 512Mi | 1Gi |
| `grafana` | 1 | 100m | 250m | 128Mi | 256Mi |
| `loki` | 1 | 250m | 500m | 256Mi | 512Mi |

> PostgreSQL runs outside Kubernetes as a managed service (Cloud SQL / RDS / Azure Database) in SaaS mode, or as a StatefulSet with persistent volume in on-prem mode. PgBouncer runs as a sidecar to `vidya-api`.

---

### Horizontal Pod Autoscaler (HPA) Rules

#### `vidya-api` — scale on CPU
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: vidya-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: vidya-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
```

#### `vidya-worker` — scale on Redis queue depth (KEDA)
```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: vidya-worker-scaledobject
spec:
  scaleTargetRef:
    name: vidya-worker
  minReplicaCount: 2
  maxReplicaCount: 20
  triggers:
    - type: redis
      metadata:
        address: redis:6379
        listName: celery          # default Celery queue
        listLength: "10"          # 1 new worker per 10 queued jobs
```

> **KEDA** (Kubernetes Event-Driven Autoscaling) is used for worker pods — queue depth is a better signal than CPU for AI job workers. Install KEDA as a cluster add-on before deploying workers.

#### `vidya-worker-heavy` — scale on dedicated heavy queue depth
```yaml
# Same KEDA pattern; listName: celery-heavy; listLength: "3"
# Heavy jobs: viva video processing, full course kit generation, batch scan ingestion
# Lower threshold (3 jobs per worker) due to higher per-job resource consumption
```

---

### Node Pool Strategy

| Pool | Machine Type | Purpose | Auto-scale |
|------|-------------|---------|-----------|
| `general` | 4 vCPU / 8GB RAM (e.g. n2-standard-4 / t3.xlarge) | API, frontend, Redis, monitoring | 2 → 10 nodes |
| `ai-worker` | 8 vCPU / 32GB RAM (e.g. n2-standard-8 / m6i.2xlarge) | Celery workers (standard AI jobs) | 1 → 8 nodes |
| `heavy-worker` | 16 vCPU / 64GB RAM (e.g. n2-highmem-16 / r6i.4xlarge) | Celery heavy workers, Whisper ASR, Qdrant | 1 → 4 nodes |

- Node pools are **cloud-agnostic** — equivalent instance types exist on GCP, AWS, and Azure
- On-prem: bare-metal or VM equivalents; same Helm chart, node labels set manually
- **Scale-down delay:** 10 minutes (prevents thrash during bursty exam periods)
- **Scale-up delay:** 0 seconds (immediate response to queue pressure)

---

### Cost-Saving Policies

| Policy | Configuration |
|--------|--------------|
| **Off-peak scale-down** | CronJob scales `vidya-worker` minReplicas to 1 at 22:00 local time; restores to 2 at 07:00 — saves ~60% worker cost overnight |
| **Spot / Preemptible nodes** | AI worker pool uses spot instances (GCP) / spot instances (AWS) — 60–80% cheaper; Celery retries handle preemption gracefully |
| **Qdrant single replica** | Phase 1: single Qdrant pod (data fits in memory); Phase 2: scale to 3 replicas with replication only when vector count exceeds 5M |
| **Whisper on-demand** | Whisper ASR pod scales to 0 when no viva sessions are scheduled (KEDA idle scale-down after 5 min inactivity) |

---

### Health Checks & Restart Policy

All pods define:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 2
```

- Pods failing liveness → automatically restarted by Kubernetes
- Pods failing readiness → removed from load balancer until healthy; no traffic sent
- `restartPolicy: Always` on all Deployments
- PodDisruptionBudget: minimum 1 pod always available during node upgrades/maintenance

---

*End of PRD — Vidya v1.0*
*Owner: Srinivas / Fidelitus Corp*
*Next step: Implementation plan (writing-plans)*
