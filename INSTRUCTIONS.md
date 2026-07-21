# INSTRUCTIONS.md — VIDYA AI Engineering Rulebook

> **Status: permanent.** These are the architectural rules all future development
> must follow. They exist because VIDYA is a live, multi-tenant, accountable
> academic ERP: a careless change can leak a tenant, break a human-decision gate,
> or corrupt an exam workflow. Read **CLAUDE1.md** first for *what the product is*;
> this file is *how you are allowed to change it*.
>
> Precedence: `CLAUDE.md` (repo root, checked in) is authoritative for phase/config
> and always wins on conflicts. This file extends it with engineering discipline.

---

## 1. Prime Directives (never violate)

1. **AI advises, humans decide.** Never write code that autonomously applies a
   grade, penalty, rejection, approval, seal, or release. Every consequential
   action needs a **human ratification step at the database level**, not only in
   the UI.
2. **Audit log is append-only.** Never `UPDATE` or `DELETE` on `audit_logs`. Log
   every AI output (with `model`, `prompt_hash`, output summary, confidence) and
   every consequential human action.
3. **Multi-tenant isolation is mandatory.** Never query across tenant schemas.
   Every tenant query runs under the caller's `search_path`; tenant tables carry
   **no `schema=` kwarg**. Never join across tenants.
4. **Never break RBAC.** Permission checks go through `require_roles` /
   `require_responsibility` on the **viewing_role**. Never invent an ad-hoc role
   check that bypasses them.
5. **Never bypass ownership validation.** Course/paper/section access is gated by
   `faculty_teaches_course` / `dean_scope` / workflow ownership. Do not add a
   by-id read/write endpoint without the matching ownership guard.
6. **Never bypass subject-assignment validation.** A Faculty may only act on
   courses they hold an **active `subject_assignments`** row for. Assignment — not
   `users.role` — is the ownership oracle.
7. **Never commit automatically. Never push automatically.** Commit/push only when
   the user explicitly asks. Never commit to `main`/`master`.

---

## 2. Change-Safety Rules (don't break what works)

- **Never redesign working modules unnecessarily.** If it works and is not the
  task, leave it. Refactors are a separate, explicitly-scheduled task.
- **Always verify the existing implementation before coding.** Read the module
  (models, service, repository, router; the frontend page + api client + types)
  *before* changing it. Do not assume an API shape — confirm it.
- **Extend existing APIs; do not replace them.** Add optional parameters / new
  endpoints. Do not change or remove an existing endpoint's contract that other
  code depends on.
- **Preserve backward compatibility.** New request fields are optional with sane
  defaults; new response fields are additive. Existing rows must keep working
  (e.g. `question_format` stayed optional when `blueprint` was added).
- **Avoid unnecessary migrations.** Reuse existing columns/JSONB where it fits.
  Add a column only when the data genuinely has no home.
- **Keep migrations additive whenever possible.** Prefer nullable additive columns
  with server defaults and backfill. Avoid destructive DDL on live tables.
- **Never modify historical migrations.** Once a revision is applied anywhere, it
  is immutable. Fix forward with a new revision; schema-vs-version drift in legacy
  schemas is a separate maintenance task, never an in-place edit.
- **Manual editing must always be available.** AI generation is *optional*; every
  AI-produced artifact must remain fully human-editable.
- **Always provide a manual testing checklist** with any behavioural change, and
  **do not run automated test suites / DB / Docker unless asked** — the user tests
  manually. Report the files changed and the manual steps, then wait.
- **Always document new workflows** (update CLAUDE1.md / the relevant module doc).

---

## 3. Domain Invariants (the rules the product depends on)

These encode institutional truth; breaking one is a product bug, not a style nit.

- **Guide and Evaluator are responsibilities, not workspaces and not separate
  accounts.** Grant them via `faculty_role_grants`; gate them with
  `require_responsibility`. Never create a parallel login for them.
- **Dean behaves like Faculty plus governance permissions.** In the Faculty
  workspace a Dean *is* Faculty (same code paths); Dean-only powers live behind
  Dean gates. Do not fork "Dean teaching" from "Faculty teaching".
- **Board users never appear in the Faculty Directory.** The Faculty Directory is
  the subject-allocation pool; Board is a governance authority.
- **Internal papers belong to Faculty and are reviewed only by the Dean.** Never
  route an INTERNAL paper to the Board.
- **Semester (Board) papers belong to the Board.** Never route a BOARD_EXAM paper
  to the Dean.
- **Workflow isolation:** Board sees only `BOARD_EXAM`; Dean sees only `INTERNAL`.
  No list/filter/permission may create overlap.
- **Never expose Board terminology for INTERNAL papers in the UI.** Internal =
  "Submitted to Dean / Dean Approved / Dean Returned" (via
  `examStatusLabel(status, workflow)`), even though the stored state reuses the
  generic `BOARD_*` enum values.
- **AI generation is optional; the AI never crosses a human gate.** Celery tasks
  may only reach `GENERATED` or `RELEASED`. Sealing, approving, releasing-by-hand,
  and locking are human endpoints only.
- **Sealed papers are inaccessible.** Never return questions/model-answers for a
  `SEALED` paper. Never expose model answers or correct options to students.
- **GovernanceType is display-only** ("Board" vs "University Members"): same role,
  permissions, endpoints, workflow. Never branch behaviour on it.

---

## 4. Backend Architecture Conventions

### 4.1 Layering: router → service → repository → database
- **Router** is pure HTTP glue: parse request, resolve `db_info`
  (`get_tenant_context_dep`), call the service, translate errors, audit-log.
- **Service** holds *all* business logic and enforces every gate/ownership rule.
  Errors are a typed exception carrying `code`, `message`, `status_code`
  (e.g. `ExamServiceError`) that the router maps to an `HTTPException` with
  `detail={"error": code, "message": message}`.
- **Repository** owns data access (SQLAlchemy `select/update/insert`); no business
  logic. Public-schema access (`public.task_jobs`) uses `AsyncSessionLocal()` and
  a dedicated repo (`TaskJobPublicRepository`), never the tenant session.
- **Database:** models in `models.py`; tenant tables declared **without** `schema=`.

Do not let business logic leak into routers or repositories, and do not let SQL
leak into services beyond what a repository method exposes.

### 4.2 Models
- Enums stored as VARCHAR: `Column(Enum(SomeEnum, native_enum=False), ...)`.
- Tenant-schema tables: no `schema=` kwarg. Public tables:
  `__table_args__ = {"schema": "public"}`.
- New columns: prefer `nullable=True` (or `server_default` + backfill) so existing
  rows and running processes keep working.
- Index foreign-key/lookup/status columns.

### 4.3 Async & AI
- **Async jobs only for AI generation.** Never block the API thread for AI. Create
  a `public.task_jobs` row (`TaskJobPublicRepository.create`) and dispatch on the
  Celery **heavy** queue. Poll via `/jobs/{job_id}`.
- All AI outputs → audit log with model + prompt_hash + summary (+ confidence).
- Provider fallback pattern: Gemini → Groq → DeepSeek → syllabus-aware **mock**
  (mock must remain structurally valid and honour the requested plan).

### 4.4 RBAC & ownership in code
- `require_roles(*roles)` — checks `viewing_role` (active workspace).
- `require_responsibility(*roles)` — base role **or** active grant (cross-workspace
  overlay).
- Ownership predicates live in `m_academics/*_scope.py`
  (`faculty_teaches_course`, `faculty_teaches_in_section`,
  `get_dean_program_ids`). Reuse them — don't re-derive ownership per endpoint.
- Never trust a client-sent role/workspace to elevate; un-entitled workspace
  requests fail **safe** to the base role.

### 4.5 Audit
- Use `AuditService.log(event_type, actor_user_id, actor_role, tenant_id,
  schema_name, target_entity, target_id, metadata=...)` for every consequential
  action. `actor_role` = base `role` (attribution); gating uses `viewing_role`.

---

## 5. Frontend Conventions

- **Stack:** React 18 + TypeScript + Vite + shadcn/ui + Tailwind + TanStack Query.
- **Separation of responsibilities:** the frontend renders and orchestrates; it
  **never** re-implements a backend rule as the source of truth. Client-side
  checks (e.g. the Paper Validation panel) are **advisory** — the backend still
  enforces. Never rely on hiding a button for security.
- **Structure:**
  - API clients in `src/lib/api/<module>.ts` (thin wrappers over the axios `api`).
  - Types in `src/types/<module>.ts` (mirror backend response shapes).
  - Pages in `src/pages/…`; shared shell in `src/components/shell/*`.
  - Route gating via `<AuthGuard allowedRoles={[...]}>` in `App.tsx`.
- **Workspace:** send the active workspace via the `X-Active-Workspace` header;
  render workspace-aware labels (never show Board terms on INTERNAL papers).
- **Status/label helpers** are centralised (e.g. `src/lib/examStatus.ts`); reuse
  them instead of re-declaring status→label/colour maps per page.
- **Data fetching:** TanStack Query with stable `queryKey`s; invalidate the right
  keys after mutations. Poll only where a backend job is in flight.
- **Type-clean:** `npm run typecheck` must pass for every file you touch. A
  pre-existing unrelated error elsewhere is not yours to fix silently — flag it.

---

## 6. Migration Conventions

- **Two trees:** `alembic/public_versions/` and `alembic/tenant_versions/`.
  Choose the right one; academic/tenant tables → tenant tree.
- **Naming:** tenant revisions `NNNNten` (e.g. `0093ten`), a short slug filename,
  a clear docstring stating *what* and *why* and confirming it's additive.
- **`down_revision`** must chain to the current single head (no accidental
  branches — verify with `grep down_revision`).
- **Additive & nullable** by default; backfill with `op.execute(UPDATE …)` when
  existing rows need a value. Avoid enum-type migrations (statuses are VARCHAR via
  `native_enum=False`, so new states need no DDL).
- **Run** with `python -m app.db.migrate tenant --all` (all active tenants) or
  `tenant <schema>` / `public`. Verify per-schema `alembic_version` and column
  presence after running. **Do not run migrations without being asked.**
- **Never edit an applied revision.** Fix forward.

---

## 7. API Conventions

- **Schema naming (Pydantic):** `*Create` (create body), `*Update` (partial
  update), `*Request` (workflow action), `*Response`, `*ListResponse`
  (`{items, total, offset, limit}`).
- **New optional fields** with defaults for backward compatibility; validate with
  `@model_validator` / `@field_validator`.
- **Errors:** service raises typed error → router returns
  `HTTPException(status_code, detail={"error": code, "message": msg})`.
- **RBAC per route** via `Depends(require_roles(...))` / `require_responsibility`.
- **Extend, don't replace:** add a query param or a new route rather than changing
  an existing contract (e.g. `workflow` param added to `/exams/all`; a new
  `/questions/{id}/duplicate` route rather than overloading an existing one).
- **Route ordering:** register specific paths so they aren't shadowed by
  parameterised ones.

---

## 8. Naming & Folder Conventions

- **Backend module:** `app/modules/mNN_<name>/` with `models.py`, `schemas.py`,
  `service.py`, `repository.py`, `router.py`, and module-specific helpers
  (`*_generator.py`, `*_analyser.py`, `ai_provider.py`). Workers in
  `app/workers/heavy/`. Core infra in `app/core/<name>/`.
- **One session = one module boundary** (per `CLAUDE.md`). Don't sprawl a change
  across unrelated modules; if you must touch a shared spine (`m_academics`,
  `auth`), do it deliberately and minimally.
- **Frontend:** `pages/`, `components/<domain>/`, `lib/api/`, `types/`, `hooks/`.
- **Names match the domain and the surrounding code** — mirror existing idioms,
  comment density, and naming rather than importing a new style.

---

## 9. Testing Conventions

- **Manual-first.** Implement, then provide a concrete **manual testing
  checklist** (what to click, expected vs actual, per role/workflow). **Do not run
  pytest / DB / Docker verification runs unless explicitly asked** — the user
  verifies manually.
- **Compile-level verification is allowed and expected** when asked to "verify":
  `python -m py_compile` for changed backend files, `npm run typecheck` for the
  frontend, and migration-chain/head checks — none of which need a live DB.
- When a bug is found during testing, **fix only that issue** — no opportunistic
  refactoring or feature additions in fix-only mode.

---

## 10. Documentation Conventions

- **Document new workflows** in CLAUDE1.md (and inline module docstrings) —
  purpose, owner, users, workflow, backend module, frontend pages, key APIs, DB
  tables, dependencies, and **why**.
- Keep **CLAUDE1.md** (product knowledge) and **INSTRUCTIONS.md** (rules) current
  as behaviour changes. A new Claude session should be able to onboard from
  CLAUDE1.md alone.
- Prefer explaining **why** a rule exists, not only what it is — a rule whose
  rationale is understood is a rule that survives refactors.

---

## 11. Git & Delivery

- Branch: `feature/TASK-XXX`; never commit to `main`/`master`.
- Commit format: `[TASK-XXX] verb: what changed`; end messages with the required
  `Co-Authored-By` trailer.
- **Never commit, never push, never open a PR automatically.** Present the diff;
  the user reviews (Srinivas reviews every PR before merge) and decides.
- Never skip hooks or bypass signing unless explicitly asked.

---

## 12. Pre-flight checklist (before writing any code)

1. Read the target module end-to-end (models → service → repo → router; page →
   api → types). **Verify** the current contract; don't assume.
2. Confirm the change is additive/backward-compatible; if not, stop and confirm
   scope with the user.
3. Check RBAC + ownership: which `require_*` gate and which ownership predicate
   applies? Reuse them.
4. Decide: does this need a migration? If yes, is it additive/nullable and in the
   right tree, chained to head?
5. Does it touch a domain invariant (§3)? If so, preserve it explicitly and note
   it in the testing checklist.
6. Implement in the correct layer. Keep frontend advisory, backend authoritative.
7. Verify at compile level (py_compile / typecheck / migration head). Do **not**
   run test suites/DB/Docker unless asked.
8. Write the manual testing checklist. **Do not commit or push.** Wait for review.
