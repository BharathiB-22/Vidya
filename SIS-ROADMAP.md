# VIDYA AI — Student Information System (SIS) Product Roadmap

**Version:** 1.0  
**Date:** 2026-05-30  
**Owner:** Srinivas / Fidelitus Corp  
**Status:** Draft — Architecture Only (no implementation yet)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Inventory](#2-current-state-inventory)
3. [SIS Architecture](#3-sis-architecture)
4. [Database Domain Model](#4-database-domain-model)
5. [Module Breakdown](#5-module-breakdown)
6. [API Breakdown](#6-api-breakdown)
7. [RBAC Matrix](#7-rbac-matrix)
8. [Workflow Diagrams](#8-workflow-diagrams)
9. [AI Module Integrations](#9-ai-module-integrations)
10. [Multi-Tenant Considerations](#10-multi-tenant-considerations)
11. [AI Opportunities Inside SIS](#11-ai-opportunities-inside-sis)
12. [MVP vs Enterprise Features](#12-mvp-vs-enterprise-features)
13. [Phase Roadmap](#13-phase-roadmap)

---

## 1. Executive Summary

VIDYA AI today is an AI-first course delivery and assessment platform. The modules built (M01–M08) cover program design, syllabus generation, course content, learning materials, lab evaluation, and exam setting. What is missing is the **operational backbone** that ties students to programs, tracks their academic journey through semesters, records attendance and marks, and produces the graduation-level records a university depends on.

The Student Information System (SIS) is that backbone. It does not replace the AI modules; it provides the data substrate they operate on. Without SIS, M06 has no authoritative student list to evaluate against, M08 has no enrollment data to generate hall tickets from, and M10 has no semester result set to apply bell-curve normalisation to.

**Design principle:** SIS is the system of record. AI modules are the intelligence layer on top of it. Every SIS entity (student, enrollment, course registration, attendance record, internal mark, result) must exist in an auditable, human-ratified state before any AI module reads it.

---

## 2. Current State Inventory

### What Is Already Built (Foundation to Build On)

| Layer | What Exists | Key Tables / Files |
|-------|------------|-------------------|
| Academic structure | Departments, Programs, Batches, Semesters, Sections, Enrollments | `m_academics/models.py` — `acad_departments`, `acad_programs`, `acad_batches`, `acad_semesters`, `acad_sections`, `acad_enrollments` |
| Faculty-course link | SubjectAssignment — faculty owns a course in a semester | `m_academics/models.py` — `subject_assignments` |
| Auth / RBAC | JWT auth, role enum, tenant isolation, platform_users table | `core/auth/` |
| Multi-tenant | Schema-per-tenant, search_path injection | `core/tenants/` |
| Audit log | Immutable append-only audit_logs | `core/audit-log/` |
| Program advisor | Programs, courses (M01 definition layer) | `m01_program_advisor/` |
| Courses | Course entity with CO-PO mapping | Shared via `courses` table (FK in subject_assignments) |
| Exam setting | Question banks, sealed papers, hall tickets (stub) | `m08_exam_setter/` |
| Results / bell curve | Score normalisation, grade sheets | `m09_paper_admin/`, `m10_bell_curve/` |

### What Is Missing (SIS Gap)

The following domains have **no tables or APIs** yet:

- Student lifecycle (admission → graduation)
- Student profile (USN, photo, guardian, address)
- Course registration per student per semester
- Attendance (entry, aggregation, shortage rules)
- Internal assessment marks ledger
- Examination scheduling and hall tickets (full implementation)
- GPA / CGPA calculation engine
- Certificate generation
- Faculty profile and workload ledger
- Student portal
- Parent portal
- Timetable management
- Fee management

---

## 3. SIS Architecture

### 3.1 Layered Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                                  │
│  Student Portal  │  Faculty Portal  │  Admin Console  │  Parent App │
│  (React 18, shadcn/ui, Tailwind, Vite)                              │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ HTTPS / JWT
┌───────────────────────────▼──────────────────────────────────────────┐
│  API GATEWAY (FastAPI)                                               │
│  /sis/v1/*  routes  │  Auth middleware  │  Tenant resolver           │
│  Rate limiting  │  Request audit  │  CORS                           │
└──────┬──────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────────┐
│  SIS SERVICE LAYER (FastAPI routers + service classes)              │
│                                                                      │
│  ┌──────────┐ ┌────────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │ Lifecycle│ │ Attendance │ │  Marks    │ │    Registration    │  │
│  │ Service  │ │  Service   │ │  Service  │ │    Service         │  │
│  └──────────┘ └────────────┘ └───────────┘ └────────────────────┘  │
│  ┌──────────┐ ┌────────────┐ ┌───────────┐ ┌────────────────────┐  │
│  │  Results │ │ Timetable  │ │Certificate│ │   Notification     │  │
│  │  Service │ │  Service   │ │  Service  │ │    Service         │  │
│  └──────────┘ └────────────┘ └───────────┘ └────────────────────┘  │
└──────┬──────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                          │
│  PostgreSQL 16 (schema-per-tenant)  │  Redis (cache + sessions)     │
│  Qdrant (semantic search — future)  │  MinIO/S3 (files, certs)      │
└──────┬──────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────────┐
│  AI MODULE INTEGRATION BUS                                           │
│  M01 ←── Program structure  │  M06 ←── Evaluated marks             │
│  M02 ←── Syllabus           │  M08 ←── Hall tickets, schedules     │
│  M03 ←── Course kit         │  M09 ←── Scripts, results            │
│  M05 ←── Learning packages  │  M10 ←── Bell curve input            │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Ownership Rules

| Domain | Owner | Consumers |
|--------|-------|-----------|
| Student enrollment record | SIS | M06, M08, M09, M10 |
| Course registration | SIS | M03, M05, M06, M08 |
| Attendance | SIS (faculty entry) | SIS analytics, notification service |
| Internal marks | SIS (faculty entry, M06 feeds) | M09, M10 |
| Exam schedule | SIS (exam cell) | M08 (paper sealing), M09 |
| Results | SIS (computed from M09/M10 output) | Student portal, certificates |
| Program / course definitions | M01 / M02 | SIS (structural reference) |
| AI-generated content | M03 / M05 | M06 (rubrics), M08 (Q-bank) |

### 3.3 Module Naming Convention

SIS modules use prefix `sis_` in table names and `m_sis_` in Python package names to avoid collision with existing `acad_` and `m0x_` prefixes.

---

## 4. Database Domain Model

> All tables live inside the tenant schema. Every FK relationship is within the same schema. No cross-tenant JOINs are ever permitted.

### 4.1 Entity Relationship Overview

```
acad_departments
    └── acad_programs  (already built)
            └── acad_batches
                    └── acad_semesters
                            └── acad_sections
                                    └── acad_enrollments ─── sis_students (1:1 link via student_id)

sis_students
    ├── sis_student_profiles
    ├── sis_guardians
    ├── sis_admission_records
    └── sis_lifecycle_events

sis_course_registrations   (student ✕ course ✕ semester)
    ├── sis_attendance_sessions
    │       └── sis_attendance_entries
    ├── sis_internal_marks
    └── sis_exam_registrations
            └── sis_hall_tickets

sis_exam_schedules         (exam cell planned)
    └── sis_hall_tickets

sis_results                (semester-level computed)
    └── sis_result_details (per-course)

sis_timetable_slots        (section ✕ course ✕ time ✕ room)

sis_faculty_profiles       (extends platform_users for faculty)
sis_faculty_workload       (faculty ✕ course ✕ semester)

sis_certificates           (bonafide, TC, provisional, degree)
sis_fee_accounts           (future phase)
```

### 4.2 Core Table Definitions

#### `sis_students`
```
id                  UUID PK
user_id             UUID FK → platform_users.id (nullable — student may not yet have login)
usn                 VARCHAR(20) UNIQUE          -- University Seat Number
roll_number         VARCHAR(20)
admission_number    VARCHAR(30) UNIQUE
admission_year      SMALLINT
current_semester    SMALLINT
current_section_id  UUID FK → acad_sections.id
program_id          UUID FK → acad_programs.id
batch_id            UUID FK → acad_batches.id
status              ENUM(ACTIVE, DETAINED, DISCONTINUED, GRADUATED, ALUMNI)
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

#### `sis_student_profiles`
```
id                  UUID PK
student_id          UUID FK → sis_students.id UNIQUE
first_name          VARCHAR(100)
last_name           VARCHAR(100)
date_of_birth       DATE
gender              ENUM(MALE, FEMALE, OTHER, PREFER_NOT_TO_SAY)
nationality         VARCHAR(50)
blood_group         VARCHAR(5)
category            ENUM(GEN, OBC, SC, ST, EWS, OTHER)
mobile              VARCHAR(20)
email               VARCHAR(255)
address_permanent   JSONB           -- {line1, line2, city, state, pincode}
address_current     JSONB
photo_url           TEXT            -- MinIO/S3 path
aadhar_hash         VARCHAR(64)     -- hashed, never plain
created_at          TIMESTAMPTZ
updated_at          TIMESTAMPTZ
```

#### `sis_guardians`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
relationship        ENUM(FATHER, MOTHER, GUARDIAN, SPOUSE)
name                VARCHAR(200)
mobile              VARCHAR(20)
email               VARCHAR(255)
occupation          VARCHAR(100)
annual_income       INTEGER
is_primary          BOOLEAN         -- one primary per student
```

#### `sis_admission_records`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
admission_date      DATE
admission_type      ENUM(FRESH, LATERAL, TRANSFER)
previous_institution VARCHAR(300)
previous_qualification VARCHAR(100)
entrance_exam       VARCHAR(50)
rank                INTEGER
quota               ENUM(MERIT, MANAGEMENT, NRI, LATERAL)
documents_verified  BOOLEAN DEFAULT FALSE
verified_by         UUID            -- platform_users.id
verified_at         TIMESTAMPTZ
```

#### `sis_lifecycle_events`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
event_type          ENUM(ADMITTED, ENROLLED, PROMOTED, DETAINED, DISCONTINUED, 
                         READMITTED, SEMESTER_REGISTERED, GRADUATED, ALUMNI)
event_date          DATE
from_semester       SMALLINT
to_semester         SMALLINT
remarks             TEXT
performed_by        UUID            -- platform_users.id (human gate)
ratified_by         UUID            -- dean or admin (second human gate for promotions)
created_at          TIMESTAMPTZ
```

#### `sis_course_registrations`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
course_id           UUID FK → courses.id
semester_id         UUID FK → acad_semesters.id
registration_type   ENUM(REGULAR, ELECTIVE, BACKLOG, AUDIT)
status              ENUM(REGISTERED, DROPPED, COMPLETED, FAILED)
registered_at       TIMESTAMPTZ
dropped_at          TIMESTAMPTZ
registered_by       UUID
```

#### `sis_attendance_sessions`
```
id                  UUID PK
course_id           UUID FK → courses.id
section_id          UUID FK → acad_sections.id
semester_id         UUID FK → acad_semesters.id
faculty_user_id     UUID
session_date        DATE
session_number      SMALLINT        -- 1st or 2nd hour of same course on same day
topic_covered       TEXT
created_at          TIMESTAMPTZ
```

#### `sis_attendance_entries`
```
id                  UUID PK
session_id          UUID FK → sis_attendance_sessions.id
student_id          UUID FK → sis_students.id
status              ENUM(PRESENT, ABSENT, LATE, MEDICAL_LEAVE, DUTY_LEAVE)
marked_by           UUID
marked_at           TIMESTAMPTZ
override_by         UUID            -- HOD/Dean manual override
override_reason     TEXT
UNIQUE (session_id, student_id)
```

#### `sis_attendance_summary` (materialized view / computed)
```
student_id          UUID
course_id           UUID
semester_id         UUID
total_sessions      INTEGER
attended            INTEGER
percentage          NUMERIC(5,2)
is_shortage         BOOLEAN         -- below institution threshold (default 75%)
detention_risk      BOOLEAN         -- below hard minimum (default 65%)
last_computed_at    TIMESTAMPTZ
```

#### `sis_internal_marks`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
course_id           UUID FK → courses.id
semester_id         UUID FK → acad_semesters.id
component           ENUM(ASSIGNMENT, QUIZ, MIDTERM, LAB, PROJECT, VIVA, OTHER)
component_number    SMALLINT        -- Assignment 1, Assignment 2, etc.
marks_obtained      NUMERIC(6,2)
max_marks           NUMERIC(6,2)
entered_by          UUID
ratified_by         UUID            -- HOD ratification gate
ratified_at         TIMESTAMPTZ
source              ENUM(MANUAL, M06_LABS, M07_RESEARCH, M08_EXAM)
source_reference_id UUID            -- FK to the AI module's record
created_at          TIMESTAMPTZ
UNIQUE (student_id, course_id, semester_id, component, component_number)
```

#### `sis_exam_schedules`
```
id                  UUID PK
semester_id         UUID FK → acad_semesters.id
course_id           UUID FK → courses.id
exam_type           ENUM(INTERNAL, END_SEM, SUPPLEMENTARY, REVALUATION)
scheduled_date      DATE
start_time          TIME
end_time            TIME
venue               VARCHAR(200)
duration_minutes    SMALLINT
total_marks         NUMERIC(6,2)
paper_id            UUID            -- FK → m08_exam_papers.id (nullable until paper sealed)
status              ENUM(SCHEDULED, PAPER_READY, COMPLETED, CANCELLED)
```

#### `sis_hall_tickets`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
exam_schedule_id    UUID FK → sis_exam_schedules.id
hall_ticket_number  VARCHAR(30) UNIQUE
seat_number         VARCHAR(20)
issued_at           TIMESTAMPTZ
is_eligible         BOOLEAN         -- computed: attendance + fee clearance
ineligible_reason   TEXT
generated_by        UUID
pdf_url             TEXT            -- MinIO path
```

#### `sis_results`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
semester_id         UUID FK → acad_semesters.id
total_credits       NUMERIC(5,2)
earned_credits      NUMERIC(5,2)
sgpa                NUMERIC(4,2)
cgpa                NUMERIC(4,2)    -- cumulative, recomputed each semester
class_awarded       ENUM(DISTINCTION, FIRST, SECOND, PASS, FAIL, WITHHELD)
result_status       ENUM(PASS, FAIL, FAIL_DETAINED, PENDING_REVALUATION)
declared_at         TIMESTAMPTZ
declared_by         UUID
is_published        BOOLEAN DEFAULT FALSE
published_at        TIMESTAMPTZ
published_by        UUID
```

#### `sis_result_details`
```
id                  UUID PK
result_id           UUID FK → sis_results.id
course_id           UUID FK → courses.id
internal_marks      NUMERIC(6,2)    -- from sis_internal_marks consolidation
end_sem_marks       NUMERIC(6,2)    -- from M09/M10 pipeline
total_marks         NUMERIC(6,2)
max_marks           NUMERIC(6,2)
grade               VARCHAR(5)      -- A+, A, B+, B, C, D, F
grade_points        NUMERIC(4,2)
credits             NUMERIC(4,2)
credit_points       NUMERIC(6,2)
is_backlog          BOOLEAN
pass_fail           ENUM(PASS, FAIL)
```

#### `sis_timetable_slots`
```
id                  UUID PK
section_id          UUID FK → acad_sections.id
course_id           UUID FK → courses.id
faculty_user_id     UUID
room                VARCHAR(50)
day_of_week         SMALLINT        -- 1=Monday, 7=Sunday
period_number       SMALLINT        -- 1..8
start_time          TIME
end_time            TIME
slot_type           ENUM(LECTURE, LAB, TUTORIAL, SEMINAR)
semester_id         UUID FK → acad_semesters.id
effective_from      DATE
effective_to        DATE
UNIQUE (section_id, day_of_week, period_number, effective_from)
UNIQUE (room, day_of_week, period_number, effective_from)     -- clash guard
UNIQUE (faculty_user_id, day_of_week, period_number, effective_from) -- clash guard
```

#### `sis_faculty_profiles`
```
id                  UUID PK
user_id             UUID FK → platform_users.id UNIQUE
employee_id         VARCHAR(30) UNIQUE
designation         VARCHAR(100)    -- Assistant Prof, Associate Prof, Professor
qualification       TEXT
specialisation      TEXT
date_of_joining     DATE
department_id       UUID FK → acad_departments.id
is_hod              BOOLEAN DEFAULT FALSE
max_weekly_hours    SMALLINT DEFAULT 16
```

#### `sis_faculty_workload`
```
id                  UUID PK
faculty_user_id     UUID
semester_id         UUID FK → acad_semesters.id
course_id           UUID FK → courses.id
weekly_hours        SMALLINT
is_active           BOOLEAN
-- Derived total hours per faculty per semester computed by service layer
```

#### `sis_certificates`
```
id                  UUID PK
student_id          UUID FK → sis_students.id
certificate_type    ENUM(BONAFIDE, STUDY, TRANSFER, PROVISIONAL, DEGREE, MIGRATION, CHARACTER)
requested_at        TIMESTAMPTZ
requested_by        UUID            -- student or admin
purpose             TEXT
approved_by         UUID            -- registrar / admin
approved_at         TIMESTAMPTZ
serial_number       VARCHAR(50) UNIQUE
pdf_url             TEXT
status              ENUM(REQUESTED, APPROVED, GENERATED, ISSUED, REJECTED)
```

#### `sis_fee_accounts` (Phase 3 — placeholder only)
```
id                  UUID PK
student_id          UUID FK → sis_students.id
semester_id         UUID FK → acad_semesters.id
fee_structure_id    UUID
total_amount        NUMERIC(10,2)
paid_amount         NUMERIC(10,2)
due_date            DATE
status              ENUM(PENDING, PARTIAL, PAID, OVERDUE, WAIVED)
```

---

## 5. Module Breakdown

### SIS-01: Student Lifecycle Management

**Purpose:** Manage the student's complete journey from admission application to alumni status.

**Sub-modules:**
- `SIS-01A` Admission — capture application, document upload, quota assignment, verification workflow
- `SIS-01B` Enrollment — convert admitted applicant to enrolled student; assign USN, section, mentor
- `SIS-01C` Semester Registration — student registers for courses each semester; HOD approves
- `SIS-01D` Promotion — end-of-year promotion decision; dual human gate (Faculty Council + Dean)
- `SIS-01E` Detention — automatic detention flag based on attendance/marks thresholds; HOD ratifies
- `SIS-01F` Discontinuation / Readmission — voluntary TC or academic discontinuation; re-entry flow
- `SIS-01G` Graduation — degree completion check; provisional certificate trigger
- `SIS-01H` Alumni — post-graduation status; alumni portal access

**Human Gates:**
- Admission verification: Admin
- Promotion/Detention: Faculty Council → Dean (two-step)
- Graduation: Registrar → Academic Council

**Key Invariant:** A student's `status` field in `sis_students` can only move forward along the lifecycle DAG. No backward status transitions without a `sis_lifecycle_events` record and a human ratifier recorded.

---

### SIS-02: Student Profile Management

**Purpose:** Maintain authoritative demographic and academic identity for every student.

**Sub-modules:**
- `SIS-02A` Personal profile — name, DOB, gender, contact, photo
- `SIS-02B` Guardian management — primary and secondary guardians
- `SIS-02C` Document vault — Aadhar (hashed), PAN, marksheets, certificates (MinIO)
- `SIS-02D` Mentor assignment — assign a faculty mentor to each student

**Privacy Rules:**
- Aadhar number stored as SHA-256 hash only, never plaintext
- Photo stored in MinIO with signed URL access, not CDN-public
- Guardian contact visible to Admin, Dean, HOD, Faculty (mentor only), Parent role — not other students

---

### SIS-03: Academic Structure (Extends Existing)

**Purpose:** Extend the existing `m_academics` structure with schools, rooms, and academic year calendar.

**New entities on top of existing:**
- `sis_schools` — grouping of departments (Faculty of Engineering, Faculty of Science)
- `sis_rooms` — classrooms and labs with capacity and projector/lab flags
- `sis_academic_calendar` — institution-wide event calendar (semester start, holidays, exam windows)
- `sis_academic_year` — links an academic year to all its batches

**Note:** `acad_departments`, `acad_programs`, `acad_batches`, `acad_semesters`, `acad_sections` already exist. SIS-03 only adds the missing layers above and beside them.

---

### SIS-04: Course Registration

**Purpose:** Allow students to register for courses each semester, manage electives, handle add/drop and backlog.

**Flows:**
1. **Regular Registration** — Admin opens registration window; students pick electives; system validates credit limits, prerequisites, section strength cap
2. **Elective Selection** — preference-ranked selection with auto-allocation if oversubscribed
3. **Add/Drop Window** — 7-day window post-semester start; faculty head approval
4. **Backlog Registration** — student registers for a failed course alongside regular courses; flagged separately in marks ledger
5. **Fee Clearance Gate** — registration blocked if fee dues exist (Phase 3)

**Validation Rules:**
- Total credits per semester must be within institution-defined band (min/max)
- Prerequisite courses must be PASS in `sis_result_details`
- Section strength cap enforced at `acad_sections.max_strength`

---

### SIS-05: Attendance Management

**Purpose:** Daily faculty attendance entry; aggregate computation; shortage alerting; detention determination.

**Flows:**
1. **Faculty marks attendance** — session-level (each hour separately); mobile-first UI; present/absent/late/leave
2. **Attendance aggregation** — `sis_attendance_summary` recomputed after every entry; Redis cache with 5-min TTL
3. **Shortage alert** — student and guardian notified when percentage drops below warning threshold (configurable, default 80%)
4. **Detention trigger** — HOD notified when student drops below hard minimum (default 65%); HOD must ratify detention
5. **Reports** — per-student (course-wise), per-course (class list), department roll-up, monthly summary

**Attendance Formula:**
```
percentage = (attended / total_sessions) * 100
shortage    = percentage < institution.attendance_warning_threshold   (default 80%)
detention   = percentage < institution.attendance_detention_threshold (default 65%)
```

**Human Gate:** Detention is flagged by the system; it is **not applied automatically**. HOD must open the detention record, review, and ratify. System writes the ratified record to `sis_lifecycle_events`.

**Override Flow:** Faculty HOD can mark DUTY_LEAVE for inter-college events retroactively; requires reason text; audit-logged.

---

### SIS-06: Internal Assessment

**Purpose:** Record, consolidate, and ratify all internal marks (assignments, quizzes, midterms, labs, projects).

**Components tracked:**
| Component | Typical Max | Source |
|-----------|------------|--------|
| Assignment 1, 2 | 10 each | Manual entry or M06 feed |
| Quiz 1, 2 | 5 each | Manual entry |
| Mid-term 1, 2 | 30 each | Manual entry |
| Lab Internal | 25 | M06 Labs Evaluator feed |
| Project/Mini-project | 50 | Manual or M06 feed |
| Seminar/Viva | 25 | Manual or M07 Research feed |

**Consolidation Rules:**
- Best-of-N averaging rules configurable per institution (e.g., best 2 of 3 assignments)
- Consolidated internal marks = weighted sum defined per course by HOD
- Consolidated marks visible to student only after HOD ratification

**Human Gate:** Faculty enters marks → HOD reviews and ratifies → marks locked; any correction requires a new HOD ratification with reason

**AI Feed Contract:**
- M06 writes evaluated marks to `sis_internal_marks` with `source=M06_LABS` and `source_reference_id`
- M06 marks have `ratified_by=NULL` until faculty/HOD reviews them — they are advisory until ratified
- Same contract for M07 (research viva) and M08 (internal exam)

---

### SIS-07: Examination Management

**Purpose:** Manage end-semester exam scheduling, hall ticket generation, and post-exam administration.

**Sub-modules:**
- `SIS-07A` Exam Schedule — exam cell creates schedule; published to student portal
- `SIS-07B` Eligibility Check — automatic: attendance >= threshold AND no fee dues AND registered for course
- `SIS-07C` Hall Ticket Generation — batch-generated PDFs with student photo, USN, seat number; stored in MinIO
- `SIS-07D` Revaluation — student applies; registrar opens; evaluator re-marks; result amended
- `SIS-07E` Supplementary Exams — failed students re-register; separate schedule; results stored as `is_backlog=True`

**Integration with M08:**
- When exam schedule is created and paper is sealed in M08, `sis_exam_schedules.paper_id` is populated
- Hall ticket eligible flag is computed from `sis_attendance_summary` + fee status
- M08 exam paper barcode = `hall_ticket_number` for traceability in M09 script evaluation

---

### SIS-08: Results and Analytics

**Purpose:** Compute GPA/CGPA from finalised marks; produce semester result sheets; generate analytics.

**Computation Pipeline:**
```
M09 finalised script marks (end-sem)
        +
SIS-06 consolidated internal marks
        |
        ▼
sis_result_details (per course, per student)
        |
        ▼  apply grading table (institution-specific grade boundaries)
sis_results (semester-level SGPA + cumulative CGPA)
        |
        ▼  Dean/Exam Board publishes
Student portal shows result
```

**Grading Table (configurable per institution):**
| Marks Range | Grade | Grade Points |
|------------|-------|-------------|
| 90–100 | O | 10 |
| 80–89 | A+ | 9 |
| 70–79 | A | 8 |
| 60–69 | B+ | 7 |
| 55–59 | B | 6 |
| 50–54 | C | 5 |
| 45–49 | D | 4 |
| < 45 | F | 0 |

**SGPA Formula:**
```
SGPA = Σ(grade_points × credits) / Σ(credits)  [for the semester]
CGPA = Σ(grade_points × credits) / Σ(credits)  [cumulative across all semesters]
```

**Analytics Dashboards:**
- Per-student: semester progression chart, CGPA trend, backlog count
- Per-course: class average, pass %, grade distribution histogram, Bloom's-level attainment
- Per-department: batch rank list, department toppers, CO-PO attainment matrix (NBA/NAAC ready)
- Institutional: cross-department comparison, year-over-year trends

**Human Gate:** Results are computed by the system, reviewed by Exam Board, and published only after explicit `is_published=True` action by Dean/Registrar. Computed != Published.

---

### SIS-09: Certificate Management

**Purpose:** Generate institution-stamped certificates on request.

**Certificate Types and Approvers:**

| Certificate | Requested By | Approved By | Contains |
|-------------|-------------|-------------|---------|
| Bonafide | Student | Admin | name, USN, program, semester, purpose |
| Study Certificate | Student | Admin | full academic history |
| Transfer Certificate (TC) | Student / Admin | Registrar + Dean | conduct, dues clearance, last semester |
| Migration Certificate | Student | Registrar | marks, university, year |
| Provisional Degree | Student (on graduation) | Dean | degree name, class, date |
| Degree Certificate | Student (convocation) | Vice Chancellor | formal degree |
| Character Certificate | Student | Dean | conduct record |

**Generation:** Jinja2 HTML template → Weasyprint → PDF → MinIO → signed URL valid 48h  
**Serial Number:** `{INSTITUTION_CODE}-{YEAR}-{TYPE_CODE}-{SEQUENCE}` — globally unique within tenant

---

### SIS-10: Faculty Management

**Purpose:** Maintain faculty profiles, department assignments, course allocations, and workload compliance.

**Sub-modules:**
- `SIS-10A` Faculty profile — designation, qualification, joining date, photo
- `SIS-10B` Department assignment — which department a faculty belongs to; HOD flag
- `SIS-10C` Subject allocation — HOD assigns courses to faculty per semester via `subject_assignments` (already exists)
- `SIS-10D` Workload tracking — total weekly teaching hours across all assigned courses; alert if exceeds UGC limit (16 hrs/week)
- `SIS-10E` Leave management (MVP stub) — leave requests affect attendance marking availability

**UGC Workload Rules:**
- Assistant Professor: max 16 hours/week lecture + 2 hours/week tutorial
- HOD: max 14 hours/week (2 hours admin credit)
- Professor: max 14 hours/week

---

### SIS-11: Student Portal

**Purpose:** Single-window web interface for students to access all academic information.

**Pages / Features:**
| Page | Contents |
|------|---------|
| Dashboard | Today's timetable, pending assignments, attendance at-a-glance, result summary |
| Attendance | Course-wise attendance percentage, session-level log, shortage alerts |
| Course Registration | Open window: pick electives, view credit count, submit |
| Learning | Links to M05 packages per course; RAG Q&A |
| Assignments | List from M03/M06; submit; view evaluated marks after ratification |
| Exam | Hall ticket download, exam schedule, results |
| Internal Marks | Component-wise marks (visible after HOD ratification) |
| Results | SGPA/CGPA, grade sheets, rank in section/batch |
| Certificates | Request certificate; download PDF when approved |
| Timetable | Weekly timetable grid |
| Profile | View personal details; change password |

---

### SIS-12: Parent Portal

**Purpose:** Read-only guardian visibility into attendance, marks, and exam information.

**Access Rules:**
- Parent logs in with separate credentials tied to `sis_guardians.email`
- Can only see data for students they are listed as primary or secondary guardian for
- Cannot see other students or cohort data

**Features:**
| Feature | Detail |
|---------|--------|
| Attendance | Current percentage per course, shortage flag |
| Internal Marks | Only after HOD ratification |
| Exam Schedule | Upcoming exams |
| Results | Published results only |
| Notifications | Push/email for shortage alerts, results declared |
| Fee Status | Phase 3 |

---

### SIS-13: Notifications Engine

**Purpose:** Deliver timely alerts to the right stakeholders through the right channel.

**Notification Types:**
| Trigger | Recipients | Channels |
|---------|-----------|---------|
| Attendance below 80% | Student + Primary Guardian | In-app + Email |
| Attendance below 65% (detention risk) | Student + Guardian + HOD | In-app + Email + SMS |
| Internal marks entered | Student | In-app |
| Results published | Student + Guardian | In-app + Email |
| Hall ticket ready | Student | In-app + Email |
| Certificate approved | Student | In-app + Email |
| Assignment due tomorrow | Student | In-app |
| Course registration window open | All students in batch | In-app + Email |
| Exam schedule published | Students + Faculty | In-app + Email |

**Channels:**
- **In-app** — polling endpoint; React toast system; unread badge count
- **Email** — existing notification service (FastAPI background task → SMTP)
- **SMS** — Twilio or MSG91 (Phase 2; configurable per institution)
- **WhatsApp** — Phase 3; optional add-on

---

### SIS-14: Timetable Management

**Purpose:** Generate and manage class timetables with conflict detection.

**Constraints Enforced:**
- No faculty double-booking across sections at the same time
- No room double-booking
- No section has two courses in the same period
- Lab sessions must be consecutive double or triple periods
- Faculty weekly hours must not exceed workload limit after scheduling

**Generation Modes:**
- Manual entry by Admin — drag-and-drop grid UI
- AI-assisted suggestion (Phase 3) — constraint satisfaction with optimization

**Clash Detection:** On every INSERT or UPDATE to `sis_timetable_slots`, a service-layer validation check runs all three UNIQUE constraints before committing.

---

### SIS-15: Fee Management (Phase 3)

**Purpose:** Track fee collection, generate receipts, manage scholarships, and enforce fee-clearance gates.

**Scope for Phase 3:**
- Fee structures per program per semester
- Online payment gateway integration (Razorpay / PayU)
- Scholarship and concession records
- Due reminders
- Clearance certificate generation
- Gates: exam registration blocked if fee due (configurable)

> Fee management is explicitly out of scope for SIS Phase 1 and 2. The `sis_fee_accounts` table will be created as a placeholder in Phase 2 so that gate checks can be wired up, but the collection and receipt flows are Phase 3.

---

## 6. API Breakdown

All SIS endpoints live under `/sis/v1/` prefix. All require JWT. All are tenant-scoped.

### 6.1 Student Lifecycle APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/students` | Create student (admission) | Admin |
| GET | `/sis/v1/students` | List students with filters | Admin, Dean, HOD |
| GET | `/sis/v1/students/{id}` | Get student detail | Admin, Dean, HOD, Faculty (own section), Student (self) |
| PATCH | `/sis/v1/students/{id}` | Update profile | Admin |
| POST | `/sis/v1/students/{id}/lifecycle` | Record lifecycle event | Admin, Dean |
| GET | `/sis/v1/students/{id}/lifecycle` | Get lifecycle history | Admin, Dean |
| POST | `/sis/v1/students/bulk-import` | CSV import (onboarding) | Admin |

### 6.2 Course Registration APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| GET | `/sis/v1/registration/window` | Get current open registration window | Student |
| POST | `/sis/v1/registration/register` | Student registers for courses | Student |
| DELETE | `/sis/v1/registration/{id}` | Drop a course (within window) | Student |
| GET | `/sis/v1/registration/my-courses` | Student's registered courses | Student |
| GET | `/sis/v1/registration/course/{course_id}/students` | Roster for a course | Faculty, HOD |
| PATCH | `/sis/v1/registration/{id}/approve` | Approve add/drop | HOD |

### 6.3 Attendance APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/attendance/sessions` | Create attendance session | Faculty |
| POST | `/sis/v1/attendance/sessions/{id}/mark` | Bulk mark attendance | Faculty |
| GET | `/sis/v1/attendance/my-summary` | Student's own attendance summary | Student |
| GET | `/sis/v1/attendance/course/{course_id}/summary` | Course attendance summary | Faculty, HOD |
| GET | `/sis/v1/attendance/shortages` | List shortage students | HOD, Dean |
| POST | `/sis/v1/attendance/entries/{id}/override` | Manual override with reason | HOD |
| GET | `/sis/v1/attendance/reports/department` | Department roll-up | Dean, HOD |

### 6.4 Internal Marks APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/marks/entry` | Enter marks for a component | Faculty |
| GET | `/sis/v1/marks/course/{course_id}` | View all marks for course | Faculty, HOD |
| GET | `/sis/v1/marks/my-marks` | Student's own internal marks | Student |
| POST | `/sis/v1/marks/{id}/ratify` | HOD ratification | HOD |
| GET | `/sis/v1/marks/consolidated/{semester_id}/{course_id}` | Consolidated marks sheet | HOD, Dean |

### 6.5 Examination APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/exam/schedules` | Create exam schedule | Admin (Exam Cell) |
| GET | `/sis/v1/exam/schedules` | List exam schedules | All authenticated |
| POST | `/sis/v1/exam/hall-tickets/generate` | Batch generate hall tickets | Admin |
| GET | `/sis/v1/exam/hall-tickets/my` | Download my hall ticket | Student |
| GET | `/sis/v1/exam/hall-tickets/{student_id}` | Get student's hall ticket | Admin, Faculty |
| POST | `/sis/v1/exam/revaluation/apply` | Apply for revaluation | Student |
| PATCH | `/sis/v1/exam/revaluation/{id}/process` | Process revaluation | Evaluator |

### 6.6 Results APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/results/compute/{semester_id}` | Trigger result computation | Admin (Exam Board) |
| GET | `/sis/v1/results/my-results` | Student's results | Student |
| GET | `/sis/v1/results/{student_id}` | Student's results (staff view) | Faculty, HOD, Dean |
| POST | `/sis/v1/results/{semester_id}/publish` | Publish results | Dean |
| GET | `/sis/v1/results/analytics/department` | Department analytics | Dean, Board Member |
| GET | `/sis/v1/results/rank-list/{semester_id}` | Rank list for batch | Dean, HOD |

### 6.7 Certificate APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/certificates/request` | Request a certificate | Student, Admin |
| GET | `/sis/v1/certificates/my-certificates` | My certificate requests | Student |
| POST | `/sis/v1/certificates/{id}/approve` | Approve and generate | Admin, Dean |
| GET | `/sis/v1/certificates/{id}/download` | Download PDF | Student, Admin |

### 6.8 Timetable APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/timetable/slots` | Create timetable slot | Admin, HOD |
| GET | `/sis/v1/timetable/section/{section_id}` | Section timetable | All |
| GET | `/sis/v1/timetable/faculty/{user_id}` | Faculty timetable | Faculty, HOD |
| GET | `/sis/v1/timetable/room/{room_id}` | Room timetable | Admin |
| DELETE | `/sis/v1/timetable/slots/{id}` | Delete slot | Admin, HOD |
| GET | `/sis/v1/timetable/clash-check` | Check for clashes before save | Admin, HOD |

### 6.9 Faculty Management APIs

| Method | Path | Description | Access |
|--------|------|-------------|--------|
| POST | `/sis/v1/faculty/profiles` | Create faculty profile | Admin |
| GET | `/sis/v1/faculty/profiles` | List faculty | Admin, Dean, HOD |
| GET | `/sis/v1/faculty/profiles/{user_id}` | Get faculty profile | Admin, Dean, HOD, Faculty (self) |
| GET | `/sis/v1/faculty/workload/{user_id}/{semester_id}` | Faculty workload report | Admin, HOD |
| GET | `/sis/v1/faculty/workload/department/{dept_id}` | Department workload | HOD, Dean |

---

## 7. RBAC Matrix

### Legend
`✓` = Full access | `R` = Read-only | `O` = Own records only | `—` = No access | `*` = With approval/ratification step

| Permission Domain | Super Admin | Tenant Admin | Dean | HOD | Faculty | Student | Parent | Board Member | Evaluator | Guide |
|-----------------|:-----------:|:------------:|:----:|:---:|:-------:|:-------:|:------:|:------------:|:---------:|:-----:|
| **Tenant Management** |
| Provision tenant | ✓ | — | — | — | — | — | — | — | — | — |
| Configure modules | ✓ | ✓ | — | — | — | — | — | — | — | — |
| Manage users | ✓ | ✓ | — | — | — | — | — | — | — | — |
| **Academic Structure** |
| Create/edit departments | ✓ | ✓ | — | — | — | — | — | — | — | — |
| Create/edit programs | ✓ | ✓ | ✓ | — | — | — | — | — | — | — |
| Create/edit batches & semesters | ✓ | ✓ | ✓ | — | — | — | — | — | — | — |
| Create/edit sections | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — |
| View academic structure | ✓ | ✓ | ✓ | ✓ | R | R | — | R | — | — |
| **Student Management** |
| Create student (admission) | ✓ | ✓ | — | — | — | — | — | — | — | — |
| Edit student profile | ✓ | ✓ | — | — | — | O | — | — | — | — |
| View all students | ✓ | ✓ | ✓ | ✓(dept) | R(section) | O | O(ward) | R | — | R(supervisee) |
| Bulk CSV import | ✓ | ✓ | — | — | — | — | — | — | — | — |
| Record lifecycle event | ✓ | ✓ | ✓* | — | — | — | — | — | — | — |
| Ratify promotion/detention | — | — | ✓ | ✓* | — | — | — | — | — | — |
| **Course Registration** |
| Open/close registration window | ✓ | ✓ | ✓ | — | — | — | — | — | — | — |
| Register for courses | — | — | — | — | — | ✓ | — | — | — | — |
| Drop course (within window) | — | — | — | — | — | ✓ | — | — | — | — |
| Approve add/drop | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — |
| View course roster | ✓ | ✓ | ✓ | ✓ | ✓(own) | — | — | — | — | — |
| **Attendance** |
| Create session & mark attendance | — | — | — | — | ✓(own) | — | — | — | — | — |
| Override attendance | — | — | ✓ | ✓ | — | — | — | — | — | — |
| View own attendance | — | — | — | — | — | ✓ | — | — | — | — |
| View ward's attendance | — | — | — | — | — | — | ✓ | — | — | — |
| View course/dept attendance | ✓ | ✓ | ✓ | ✓(dept) | R(own) | — | — | — | — | — |
| Ratify detention | — | — | ✓ | ✓ | — | — | — | — | — | — |
| **Internal Marks** |
| Enter marks | — | — | — | — | ✓(own) | — | — | — | — | — |
| Ratify marks | — | — | — | ✓ | — | — | — | — | — | — |
| View own marks (post-ratification) | — | — | — | — | — | ✓ | ✓(ward) | — | — | — |
| View all marks in course | ✓ | ✓ | ✓ | ✓(dept) | R(own) | — | — | — | — | — |
| **Examination** |
| Create exam schedule | — | ✓ | ✓ | — | — | — | — | — | — | — |
| Generate hall tickets | — | ✓ | — | — | — | — | — | — | — | — |
| Download own hall ticket | — | — | — | — | — | ✓ | — | — | — | — |
| Process revaluation | — | ✓ | — | — | — | — | — | — | ✓ | — |
| Approve supplementary exam reg | — | ✓ | ✓ | — | — | — | — | — | — | — |
| **Results** |
| Trigger result computation | — | ✓ | ✓ | — | — | — | — | — | — | — |
| Review computed results | — | — | — | — | — | — | — | ✓ | — | — |
| Publish results | — | — | ✓ | — | — | — | — | — | — | — |
| View own results (post-publish) | — | — | — | — | — | ✓ | ✓(ward) | — | — | — |
| View department analytics | ✓ | ✓ | ✓ | ✓(dept) | — | — | — | ✓ | — | — |
| View rank list | ✓ | ✓ | ✓ | ✓(dept) | — | — | — | ✓ | — | — |
| **Certificates** |
| Request certificate | — | ✓ | — | — | — | ✓ | — | — | — | — |
| Approve & generate | — | ✓ | ✓(select types) | — | — | — | — | — | — | — |
| Download own certificate | — | — | — | — | — | ✓ | — | — | — | — |
| **Timetable** |
| Create/edit timetable | — | ✓ | — | ✓ | — | — | — | — | — | — |
| View own timetable | — | — | — | — | ✓ | ✓ | — | — | — | — |
| **Faculty Management** |
| Create faculty profile | ✓ | ✓ | — | — | — | — | — | — | — | — |
| Assign courses to faculty | — | ✓ | — | ✓ | — | — | — | — | — | — |
| View workload report | ✓ | ✓ | ✓ | ✓(dept) | O | — | — | — | — | — |
| **AI Module Actions** |
| Trigger M01 program generation | — | — | ✓ | — | — | — | — | — | — | — |
| Trigger M02 syllabus generation | — | — | — | — | ✓ | — | — | — | — | — |
| Trigger M03 course kit generation | — | — | — | — | ✓ | — | — | — | — | — |
| View M05 learning packages | — | — | — | — | ✓ | ✓ | — | — | — | — |
| Ratify M06 evaluated marks | — | — | — | ✓ | ✓(own) | — | — | — | — | — |
| Approve M08 exam papers | — | — | — | — | — | — | — | ✓ | — | — |
| Approve M09 scripts | — | — | — | — | — | — | — | — | ✓ | — |
| Approve M10 bell curve | — | — | ✓ | — | — | — | — | ✓ | — | — |

---

## 8. Workflow Diagrams

### 8.1 Student Admission to Active Enrollment

```
Admin creates student record (SIS-01A)
        │
        ▼
Documents verified by Admin (SIS-02C)
        │
        ▼
Section and USN assigned (SIS-01B)
        │
        ▼
Student user account created (email OTP invite)
        │
        ▼
Course registration window opens (SIS-04)
        │
        ▼ (student self-registers or Admin bulk-registers)
Course registrations confirmed
        │
        ▼
Status: ACTIVE in sis_students
        │
        ▼
M05 packages auto-linked to student's registered courses
```

### 8.2 Semester Attendance Lifecycle

```
Faculty opens session (session_date, course, section)
        │
        ▼
Faculty marks attendance entry per student (PRESENT/ABSENT/LATE/LEAVE)
        │
        ▼
Service recomputes sis_attendance_summary for affected students
        │
        ▼ (if percentage < 80%)
System triggers in-app + email notification → student + guardian
        │
        ▼ (if percentage < 65%)
System triggers HOD alert
        │
        ▼ (HOD reviews)
HOD ratifies detention flag → sis_lifecycle_events entry
        │
        ▼
Hall ticket generation: attendance check gate runs
  ──── PASS ─────► hall ticket generated
  ──── FAIL ─────► is_eligible=False, reason recorded, Admin can override
```

### 8.3 Internal Marks to Result Pipeline

```
[Internal Marks]                    [End Semester]
Faculty enters component marks      Exam scheduled (SIS-07A)
        │                                   │
        ▼                                   ▼
M06/M08 feeds marks via API         M08 paper sealed
(source=M06_LABS, ratified=NULL)            │
        │                                   ▼
HOD ratifies internal marks         M09 script evaluation (scan + AI score)
        │                                   │
        ▼                                   ▼
Consolidated internal marks         M09 Evaluator ratifies marks
(sis_internal_marks)                        │
        │                                   ▼
        └──────────────┬────────────────────┘
                       ▼
              sis_result_details created
              (internal + end_sem combined)
                       │
                       ▼
              Apply grading table → grade + grade_points
                       │
                       ▼
              sis_results: SGPA + CGPA computed
                       │
                       ▼
              Exam Board reviews → Dean publishes
                       │
                       ▼
              Student portal shows result
              Guardian notified
```

### 8.4 Promotion / Detention Decision

```
End of academic year
        │
        ▼
System flags students with:
  - Any F grade count > threshold (e.g., > 2 subjects)
  - Attendance detention in any course
        │
        ▼
Faculty Council reviews flagged list (read-only recommendations)
        │
        ▼
HOD submits promotion/detention recommendation per student
        │
        ▼ (HUMAN GATE 1)
Dean reviews and ratifies each decision
        │
        ▼
sis_lifecycle_events record created (PROMOTED or DETAINED)
  - promoted_by = HOD
  - ratified_by = Dean
        │
        ▼
Student's current_semester incremented (PROMOTED)
OR student status = DETAINED (DETAINED)
        │
        ▼
Student and guardian notified
```

---

## 9. AI Module Integrations

### Integration Architecture Pattern

Every AI module integration follows a **contract**:
1. SIS owns the authoritative record
2. AI module writes a **draft/advisory** row via internal API with `ratified_by=NULL`
3. A human (faculty/HOD/board) **explicitly ratifies** the draft before it affects the student's record
4. Audit log records both the AI write and the human ratification separately

### 9.1 M01 Program Structure Advisor → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Program definition (name, credits, degree_type, duration) | M01 → SIS | Dean approves program in M01 |
| Course list (code, name, POs, credit) | M01 → SIS | Dean approves |
| Semester-course mapping | M01 → SIS | Dean approves |

**SIS action:** Populates `acad_programs` and `courses` (already exists). No separate migration needed; the approved M01 program becomes the canonical SIS program.

### 9.2 M02 Syllabus Generator → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| CO list per course | M02 → SIS | Faculty approves syllabus |
| Unit-topic mapping | M02 → SIS | Faculty approves |
| Bloom's level per CO | M02 → SIS | Faculty approves |

**SIS action:** SIS reads CO-PO matrix for NBA/NAAC CO attainment reporting. Stored in existing M02 tables; SIS queries via internal service call.

### 9.3 M03 Course Kit Builder → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Assignment list (per course, per unit) | M03 → SIS | Faculty publishes kit |
| Assignment due dates | M03 → SIS | Faculty sets schedule |
| Assignment marks schema (max marks per component) | M03 → SIS | Faculty configures |

**SIS action:** `sis_internal_marks` component schema is seeded from M03 assignment definitions. Students see assignments in student portal from M03 feed. Submission triggers M06 evaluation.

### 9.4 M05 Learning Material Packager → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Package availability per course | M05 → SIS | Admin publishes package |
| Q&A capability endpoint | M05 provides | Student portal calls |

**SIS action:** Student portal `Learning` page links to M05 packages for each registered course. The link is established via `course_id` — SIS tells M05 which courses a student is registered for; M05 returns available packages.

### 9.5 M06 Labs & Assignment Evaluator → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Student roster (for submission tracking) | SIS → M06 | On course registration |
| Evaluated marks (component-level) | M06 → SIS | Faculty ratifies in M06 |
| AI detection flags | M06 → SIS | Auto-scan on submission |

**SIS action:** M06 calls `POST /sis/v1/marks/entry` with `source=M06_LABS` and sets `ratified_by=NULL`. Faculty/HOD ratification in SIS (`POST /sis/v1/marks/{id}/ratify`) makes the mark official.

### 9.6 M08 Exam Setter → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Exam schedule (date, time, duration, course) | SIS → M08 | Exam cell creates schedule |
| Sealed paper ID | M08 → SIS | Board approves paper in M08 |
| Hall ticket number / barcode | SIS → M08 | Hall ticket generated |

**SIS action:** When Exam Board seals a paper in M08, SIS `sis_exam_schedules.paper_id` is updated. Hall ticket barcode = `sis_hall_tickets.hall_ticket_number`, which M09 uses for script identity.

### 9.7 M09 Paper Administration → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Script evaluation result (marks per question) | M09 → SIS | Evaluator ratifies in M09 |
| Total end-sem marks | M09 → SIS | Evaluator ratifies |

**SIS action:** M09 calls `POST /sis/v1/marks/entry` with `source=M09_SCRIPTS`, `component=END_SEM`. Exam Board ratification in SIS publishes the mark to result computation.

### 9.8 M10 Bell Curve Normaliser → SIS

| Data Flow | Direction | Trigger |
|-----------|-----------|---------|
| Raw end-sem score distribution | SIS → M10 | Exam Board triggers normalisation |
| Normalised marks | M10 → SIS | Board approves in M10 |

**SIS action:** SIS triggers normalisation by passing the `semester_id` + `course_id` score array to M10. M10 returns normalised marks with advisory flag. Board approves in M10 → SIS updates `sis_result_details.end_sem_marks` and recomputes grades.

### Future Integrations

| Module | Integration | Status |
|--------|------------|--------|
| M09 Script Evaluation | Script identity via hall ticket; marks feed to SIS | Current |
| Plagiarism Engine | Submission scan results annotated in M06 | Phase 2 |
| AI Study Tutor | Student Q&A on their own performance data | Phase 3 |
| Placement Portal | CGPA export, skills profile export | Phase 3 |
| LTI 1.3 LMS | SIS enrollment sync to Moodle/Canvas | Phase 2 |

---

## 10. Multi-Tenant Considerations

### 10.1 Isolation Model (Unchanged from Current)

- Schema-per-tenant in PostgreSQL
- `search_path` injected at connection begin via SQLAlchemy event
- All SIS tables exist within the tenant schema — no cross-schema JOINs
- `tenant_id` is enforced at the resolver layer before any DB call; it is not a column in every table (schema isolation provides the boundary)

### 10.2 Tenant-Configurable Parameters

Each tenant (`institutions` table in public schema) gains SIS configuration:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `attendance_warning_threshold` | 80% | Notification trigger |
| `attendance_detention_threshold` | 65% | Detention flag trigger |
| `grading_scale` | 10-point | Can be configured to 4-point GPA |
| `max_backlog_subjects` | 3 | Max failed subjects before discontinuation |
| `semester_credit_min` | 15 | Minimum credits student must register |
| `semester_credit_max` | 30 | Maximum credits allowed |
| `registration_add_drop_days` | 7 | Days after semester start for add/drop |
| `fee_gate_enabled` | false | Phase 3 — block registration on fee dues |
| `sms_provider` | null | Twilio / MSG91 config (Phase 2) |

### 10.3 Scaling Considerations

| Concern | Approach |
|---------|---------|
| Attendance computation at scale (10k students × 6 courses × 5 days/week) | Materialised summary recomputed async via Celery after every session close; Redis caches current percentages with 5-min TTL |
| Hall ticket batch generation (10k PDFs) | Celery batch job; progress tracked via existing task queue; admin polls status |
| Result computation (all students × all courses in one semester) | Single Celery task; idempotent; can be re-triggered; progress logged |
| Student portal read load | Redis cache for attendance summary, results, timetable; invalidated on write |
| Parent portal | Same data as student portal, scoped via guardian relationship; no extra storage |

### 10.4 Data Residency

Universities that require on-premises deployment (common in India under UGC data norms) can self-host the full stack via Docker Compose or Helm chart with no cloud dependency. MinIO replaces S3; local SMTP replaces SES. This is already supported by the existing stack.

---

## 11. AI Opportunities Inside SIS

These are future AI features that sit **inside SIS operations**, distinct from the existing AI content modules.

| Opportunity | Module | Description | Human Gate |
|-------------|--------|-------------|------------|
| **Attendance Prediction** | SIS-05 | Predict which students will fall below threshold 2 weeks in advance; proactive alert | Faculty/advisor reviews prediction, decides intervention |
| **At-Risk Student Detection** | SIS-08 | Early warning system: combine attendance + internal marks trend to flag academically at-risk students | HOD reviews alert; mentor is notified |
| **Timetable Optimisation** | SIS-14 | AI constraint-satisfaction engine to generate clash-free timetables optimising for faculty workload balance and room utilisation | Admin reviews and publishes; AI never auto-publishes |
| **Elective Recommendation** | SIS-04 | Based on student's CGPA profile, CO-PO gaps, and career goals, suggest elective combinations | Student sees suggestions; decides themselves |
| **CO-PO Attainment Analytics** | SIS-08 | Automatically compute CO-PO attainment matrix from results; flag underperforming outcomes for curriculum review | Dean/NBA committee reviews report |
| **Promotion Decision Support** | SIS-01 | AI summarises each borderline student's full academic record and produces a recommendation | Faculty Council sees recommendation; humans decide |
| **Certificate Fraud Detection** | SIS-09 | ML model detects statistical anomalies in certificate serial number requests (duplicate attempts) | Admin is flagged; never blocked automatically |
| **Fee Defaulter Prediction** | SIS-15 | Predict likelihood of fee default based on payment history patterns | Finance officer reviews list; takes action |
| **Natural Language Query** | Cross-SIS | "Show me all students in Section A with attendance below 75% and mid-term marks below 40%" → NL to SQL | Admin/HOD verified before actioning |

---

## 12. MVP vs Enterprise Features

### MVP (SIS Phase 1 — Minimum Viable for University Go-Live)

A university can operate with only these SIS capabilities on day one:

| Feature | Modules | Priority |
|---------|---------|---------|
| Student profile creation & USN assignment | SIS-01, SIS-02 | P0 |
| Academic structure (schools/depts/programs/batches) | SIS-03 | P0 |
| Course registration (regular, no electives) | SIS-04 | P0 |
| Attendance marking & student view | SIS-05 | P0 |
| Internal marks entry & ratification | SIS-06 | P0 |
| Exam schedule creation | SIS-07A | P0 |
| Hall ticket generation | SIS-07B/C | P0 |
| SGPA/CGPA computation & result publication | SIS-08 | P0 |
| Bonafide certificate generation | SIS-09 | P0 |
| Faculty profile & subject allocation | SIS-10 | P0 |
| Student portal (attendance, marks, results) | SIS-11 | P0 |
| Email notifications (shortage, results) | SIS-13 | P0 |

**Excluded from MVP:**
- Parent portal (SIS-12) — Phase 2
- SMS notifications — Phase 2
- Timetable management (SIS-14) — Phase 2
- Fee management (SIS-15) — Phase 3
- AI opportunities listed in Section 11 — Phase 3
- Revaluation workflow — Phase 2
- Supplementary exam full flow — Phase 2
- Alumni portal — Phase 3

### Enterprise Features (Phase 2 & 3)

| Feature | Phase | Description |
|---------|-------|-------------|
| Parent portal | 2 | Guardian attendance/marks visibility |
| SMS & WhatsApp notifications | 2 | Twilio/MSG91 integration |
| Timetable management with clash detection | 2 | Full grid UI, room allocation |
| Revaluation & supplementary exam flow | 2 | Student appeal, re-evaluation |
| LTI 1.3 sync | 2 | Push enrollments to Moodle/Canvas |
| CO-PO attainment analytics (NBA/NAAC) | 2 | Automated accreditation reports |
| AI at-risk prediction | 2 | Attendance + marks early warning |
| Elective recommendation engine | 2 | AI suggests electives |
| Fee management | 3 | Full collection, receipts, scholarships |
| Alumni portal | 3 | Post-graduation access |
| Placement portal | 3 | CGPA export, recruitment integration |
| NL query engine | 3 | "Show me students below 75%" |
| AI timetable optimisation | 3 | Constraint satisfaction scheduler |
| Mobile app (React Native) | 3 | Student + parent native apps |
| WhatsApp bot | 3 | Attendance alerts, result queries |
| Offline PWA | 3 | Student portal works without internet |

---

## 13. Phase Roadmap

### Phase 1 — SIS Core (Weeks 1–16)

**Goal:** One live university can run its full semester operations on VIDYA SIS without any spreadsheets.

| Sprint | Weeks | Deliverables |
|--------|-------|-------------|
| **S1: Foundation** | 1–2 | `sis_students`, `sis_student_profiles`, `sis_guardians`, `sis_admission_records`, bulk CSV import, student portal auth |
| **S2: Lifecycle** | 3–4 | `sis_lifecycle_events`, promotion/detention workflow, status machine, lifecycle audit trail |
| **S3: Registration** | 5–6 | `sis_course_registrations`, registration window, add/drop, prerequisite validation, student registration UI |
| **S4: Attendance** | 7–8 | `sis_attendance_sessions`, `sis_attendance_entries`, summary computation, shortage notifications, faculty attendance UI |
| **S5: Marks** | 9–10 | `sis_internal_marks`, component entry, HOD ratification, M06 feed contract, marks portal |
| **S6: Exam & Hall Tickets** | 11–12 | `sis_exam_schedules`, `sis_hall_tickets`, eligibility computation, PDF generation, exam portal |
| **S7: Results** | 13–14 | `sis_results`, `sis_result_details`, SGPA/CGPA computation, grading table, result publication, rank lists |
| **S8: Certificates & Faculty** | 15–16 | Certificate generation (5 types), faculty profiles, workload tracking, student portal polish |

**Acceptance Criteria for Phase 1 Completion:**
- [ ] 500 students onboarded via CSV import in < 30 minutes
- [ ] Faculty can mark attendance for 60-student section in < 5 minutes
- [ ] Results for one semester computed and published in < 2 minutes
- [ ] Hall tickets for all eligible students generated in < 10 minutes
- [ ] Zero cross-tenant data leakage on penetration test
- [ ] Student portal loads in < 2 seconds (P95)

### Phase 2 — SIS Extended (Weeks 17–32)

**Goal:** Full operational completeness including parent visibility, mobile-ready, and accreditation reporting.

| Sprint | Weeks | Deliverables |
|--------|-------|-------------|
| **S9: Parent Portal** | 17–18 | Guardian login, attendance/marks view, notifications |
| **S10: Timetable** | 19–20 | Timetable grid UI, clash detection, room management |
| **S11: Advanced Exam** | 21–22 | Revaluation workflow, supplementary exam registration, revised result pipeline |
| **S12: Notifications** | 23–24 | SMS (Twilio), WhatsApp stub, notification preference settings |
| **S13: AI Risk Detection** | 25–26 | Attendance + marks at-risk model, early warning dashboard |
| **S14: CO-PO Analytics** | 27–28 | CO attainment computation from results, NBA/NAAC report export |
| **S15: LTI + SSO** | 29–30 | LTI 1.3 enrollment sync, SAML SSO for university IdP |
| **S16: Performance Hardening** | 31–32 | Load testing at 2000 concurrent users, Redis cache tuning, query optimisation |

### Phase 3 — SIS Enterprise (Weeks 33–52)

**Goal:** Full ERP-grade platform with fee management, placement, alumni, and AI intelligence layer.

| Block | Weeks | Deliverables |
|-------|-------|-------------|
| **Fee Management** | 33–38 | Fee structures, Razorpay gateway, receipts, scholarships, clearance gates |
| **Placement & Alumni** | 39–42 | CGPA export, skills profile, alumni portal, recruiter access |
| **AI Intelligence Layer** | 43–46 | NL query engine, timetable optimisation AI, elective recommender |
| **Mobile** | 47–50 | React Native app (student + parent), push notifications |
| **WhatsApp & Offline** | 51–52 | WhatsApp bot for alerts/queries, PWA offline mode |

---

### Integration Readiness Checklist (Before SIS Phase 1 Sprint 1 Starts)

- [ ] Confirm `m_academics` existing tables are stable (no breaking migrations planned)
- [ ] M01 approved program → SIS program sync contract documented and tested
- [ ] M06 marks feed API contract agreed with M06 team
- [ ] M08 paper seal → SIS exam schedule update contract agreed with M08 team
- [ ] M09 result feed contract agreed with M09 team
- [ ] M10 normalised marks → SIS update contract agreed with M10 team
- [ ] `platform_users` table confirmed as the single source of truth for all user identities
- [ ] Tenant config table extended with SIS-specific parameters (attendance thresholds, grading scale)
- [ ] Certificate PDF template designs approved by institution
- [ ] Grading scale configured per institution before any result computation

---

*Document Owner: Srinivas / Fidelitus Corp*  
*Last Updated: 2026-05-30*  
*Next Review: Before SIS Phase 1 Sprint 1 kickoff*
