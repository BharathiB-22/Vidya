# Vidya — Final QA Checklist

**Owner:** Srinivas / Fidelitus Corp
**Last updated:** 2026-05-23
**Use for:** Manual validation before first external demo and before staging deploy

Instructions:
- Work through each section in order.
- Check boxes as you go.
- Any ✗ item blocks the milestone it belongs to.
- Use the KIND cluster at `http://vidya.127.0.0.1.nip.io:9080` unless noted.

---

## Pre-flight

- [ ] KIND cluster running: `kubectl get pods -n vidya-system` → 10/10 Running
- [ ] API healthy: `curl http://vidya.127.0.0.1.nip.io:9080/api/healthz` → `{"status":"ok"}`
- [ ] API ready: `curl http://vidya.127.0.0.1.nip.io:9080/api/ready` → `{"db":"healthy","redis":"healthy","s3":"healthy"}`
- [ ] Frontend loads: navigate to `http://vidya.127.0.0.1.nip.io:9080` → login page visible

---

## Section 1 — Authentication

### 1.1 Tenant Login

- [ ] `/login` renders institution slug field, email, password
- [ ] Valid slug + valid credentials → redirect to `/dashboard` or `/first-login`
- [ ] Invalid password → 401 error shown inline (no redirect)
- [ ] Non-existent slug → error shown inline
- [ ] Login rate limit: 6th attempt in 1 minute → 429 response (verify in dev tools Network tab)
- [ ] Login sets `vidya_token` in localStorage

### 1.2 First Login — Forced Password Change

- [ ] Admin with `password_changed_at = null` → redirected to `/first-login` after login
- [ ] Cannot navigate to `/dashboard` while on `/first-login` (browser back blocked by guard)
- [ ] Wrong current password → error shown, no redirect
- [ ] Password below minimum complexity → validation error shown
- [ ] Correct current + strong new password → success → redirect to `/dashboard`
- [ ] Sidebar no longer shows amber "Set your permanent password" banner
- [ ] Old token (from before password change) is invalid → 401 if replayed

### 1.3 Logout

- [ ] Profile menu → Log out → clears `vidya_token` from localStorage
- [ ] After logout, navigating to `/dashboard` redirects to `/login`
- [ ] Refresh token revoked server-side (replay of old access token → 401)

### 1.4 Token Refresh

- [ ] Short-lived access token expires → auto-refresh uses refresh token → session continues without visible interruption
- [ ] Refresh token reuse: replaying an already-used refresh token → 401 + all sessions revoked

### 1.5 Password Reset

- [ ] `/login` shows "Forgot password?" link
- [ ] Entering email → OTP sent (check email or logs)
- [ ] Correct OTP → allowed to set new password
- [ ] OTP rate limit: 4th request in 15 minutes → 429
- [ ] Expired OTP → rejected
- [ ] After reset: old password no longer works; new password works

### 1.6 Super Admin Login

- [ ] `/admin/login` accepts Super Admin credentials only
- [ ] Tenant user credentials → rejected on `/admin/login`
- [ ] Super Admin JWT works on `/api/platform/` endpoints
- [ ] Super Admin JWT rejected on tenant-scoped endpoints (403)

---

## Section 2 — RBAC

### 2.1 Route Protection (Frontend)

- [ ] ADMIN: can access `/users`, `/settings`, `/programs`, all module routes
- [ ] DEAN: can access `/programs`, `/bell-curve`; redirected from `/users`, `/labs`
- [ ] FACULTY: can access `/programs`, `/labs`, `/research/problems`, `/exams`; blocked from `/users`, `/settings`, `/bell-curve`
- [ ] STUDENT: can access `/student/labs`, `/student/research`; blocked from `/programs`, `/users`, `/labs`
- [ ] BOARD: can access `/exams`, `/scripts`, `/bell-curve`; blocked from `/users`, `/labs`, `/research/problems`
- [ ] GUIDE: can access `/research/problems`; blocked from `/users`, `/exams`, `/bell-curve`
- [ ] Blocked routes show UnauthorizedPage (not a blank screen or 404)

### 2.2 API Enforcement (Independent of Frontend)

Use curl or Postman with tokens for different roles:

- [ ] FACULTY token on `GET /api/users` → 403
- [ ] STUDENT token on `GET /api/programs` → 403
- [ ] BOARD token on `GET /api/users` → 403
- [ ] Token with no `Authorization` header → 401 (not 422)
- [ ] Expired JWT → 401
- [ ] Tampered JWT (modified payload) → 401

### 2.3 Cross-Tenant Isolation

- [ ] Institution A token sent to Institution B endpoints (different `X-Tenant-Slug` header) → 403 `TENANT_MISMATCH`
- [ ] Institution A ADMIN cannot list Institution B's users
- [ ] Super Admin token works without `X-Tenant-Slug` (SUPER_ADMIN exemption)

### 2.4 Null Byte / Injection Rejection

- [ ] Tenant slug containing null byte (`\x00`) → 400 or 404 (not 500)
- [ ] Tenant slug with SQL metacharacters → safe response (no 500)

---

## Section 3 — Tenant Onboarding

### 3.1 Tenant Provisioning (Super Admin)

- [ ] `/admin/tenants` lists all tenants with status chips
- [ ] New tenant form: slug is URL-safe validated (no spaces, no uppercase, no special chars)
- [ ] Valid submission → tenant moves PROVISIONING → ACTIVE within 30 seconds
- [ ] ACTIVE tenant: admin can log in with seeded credentials
- [ ] Failed tenant: status shows FAILED; retry button available
- [ ] Retry: FAILED → PROVISIONING → ACTIVE (when DB is reachable)

### 3.2 Admin Onboarding Checklist

- [ ] After first login + password change: onboarding checklist visible on dashboard
- [ ] Item 2 (Set password) checked after password change
- [ ] Item 3 (Add users) checked after first user created in `/users`
- [ ] Item 4 (Review settings) checked after visiting `/settings`
- [ ] All 4 checked → checklist disappears

### 3.3 User Management

- [ ] Create user: all 6 roles creatable
- [ ] Created user with null `password_changed_at` → forced to `/first-login` on first login
- [ ] Edit user: role change persists immediately
- [ ] Deactivate user: `is_active = false` → subsequent login returns 401
- [ ] Reactivate user: subsequent login succeeds
- [ ] Search by name, email, or identifier works

---

## Section 4 — AI Flows

### 4.1 Async Generation Pattern

- [ ] Triggering AI generation → immediate response with job_id (not a spinner that blocks the page)
- [ ] AIGeneratingBanner appears while job is PENDING or RUNNING
- [ ] Banner disappears and result renders when job reaches COMPLETED status
- [ ] If job FAILS → error message shown inline (not a blank state)
- [ ] Navigating away from the page during generation and back → banner re-appears and result renders on completion

### 4.2 Program Generation (M01)

- [ ] New program form → Generate with AI → async job dispatched
- [ ] Completed: semester-wise course list with credit allocation rendered
- [ ] Each course shows rationale (why this semester, which POs)
- [ ] Regulatory compliance flags shown if any violation detected
- [ ] Submit for approval → status changes to PENDING_APPROVAL
- [ ] Dean approves → status APPROVED; program locked for further edit
- [ ] Audit log entry written: model, prompt_hash, confidence_score

### 4.3 Syllabus Generation (M02)

- [ ] Generate syllabus for a course → async job → CO-PO matrix rendered
- [ ] Minimum 4 COs; each has Bloom's level tag
- [ ] Minimum 4 units; each has topic list, hours, pedagogy
- [ ] Reference list: minimum 5 entries with author, title, year, type
- [ ] Edit a CO inline → version incremented
- [ ] Status workflow: DRAFT → FACULTY_APPROVED → ADMIN_LOCKED
- [ ] Export CO-PO matrix as PDF (download triggered)

### 4.4 Course Kit Generation (M03)

- [ ] Generate course kit → async job → slides + quizlets + questions rendered
- [ ] Slide deck: ≥8 slides with speaker notes visible to faculty
- [ ] Quizlets: at least 2 per deck, answer key not in client HTML
- [ ] Regenerate single slide → only that slide updates, rest unchanged
- [ ] AI-detection flag configurable per assignment

### 4.5 Lab Evaluation (M06)

- [ ] Student submits lab → submission queued for AI evaluation
- [ ] Faculty review panel: AI score per rubric criterion + justification visible
- [ ] Faculty clicks Ratify → mark recorded; student sees result
- [ ] Faculty clicks Override → manual mark form appears; enter mark → saved
- [ ] System never records a mark without faculty action (verify: lab result is PENDING until faculty acts)

### 4.6 Human Gates (All Modules)

- [ ] Program: status does not advance to APPROVED without Dean explicit action
- [ ] Exam paper: status does not advance to BOARD_APPROVED without Board explicit action
- [ ] Lab score: no mark recorded without faculty Ratify or Override
- [ ] Bell curve: no score update without Dean/Board ratification
- [ ] Research viva: no viva outcome recorded without Guide/Faculty ratification

---

## Section 5 — Notifications

- [ ] Bell icon in topbar shows unread count badge
- [ ] Clicking bell → notification drawer slides in
- [ ] Drawer lists notifications with timestamp and read state
- [ ] Mark all read → badge clears, all items show as read
- [ ] New async job completion → notification appears in drawer (no page refresh needed)
- [ ] Approval request notification links to the relevant page
- [ ] Notification API: `GET /notifications?page=1&page_size=10` → 200 with items array

---

## Section 6 — Mobile Responsiveness

Test at 375px viewport width (Pixel 5 / iPhone SE dimensions) or use browser DevTools mobile emulation.

- [ ] Login page renders correctly: logo, form fields, submit button all visible without horizontal scroll
- [ ] Dashboard renders: title, role subtitle, tiles visible; no overflow
- [ ] Sidebar closed by default on mobile; hamburger button visible in topbar
- [ ] Hamburger tap → sidebar slides in; overlay covers main content
- [ ] Tap overlay or X → sidebar closes
- [ ] Navigation via sidebar works on mobile (tap a nav item → sidebar closes, page navigates)
- [ ] Programs list page: table or cards visible without horizontal scroll
- [ ] Forms (create user, create program) are usable at 375px width
- [ ] Notification drawer usable on mobile (full-width, scrollable)
- [ ] Bell curve analysis page: charts readable on mobile
- [ ] No horizontal overflow on any page (check with DevTools → scrollWidth = clientWidth)

---

## Section 7 — Multi-Tenant Isolation

### 7.1 Data Isolation

- [ ] Provision two tenants: `tenant-a` and `tenant-b`
- [ ] Create a program in `tenant-a` as Admin
- [ ] Log in as `tenant-b` Admin → `/programs` returns empty list (not `tenant-a` programs)
- [ ] Confirm in psql: `SELECT * FROM tenant_a.programs;` → rows exist; `SELECT * FROM tenant_b.programs;` → empty
- [ ] `search_path` is set to `tenant_<slug>` on every transaction (not just on login)

### 7.2 API Isolation

- [ ] `tenant-a` access token + `X-Tenant-Slug: tenant-b` header → 403 `TENANT_MISMATCH`
- [ ] `tenant-b` access token + `X-Tenant-Slug: tenant-a` header → 403 `TENANT_MISMATCH`
- [ ] Correct tenant slug + correct token → 200

### 7.3 Audit Log Isolation

- [ ] Audit log entries created in `tenant-a` are not visible from `tenant-b`
- [ ] `audit_logs` table: attempt `UPDATE audit_logs SET action = 'TAMPERED'` in psql → trigger blocks it
- [ ] Attempt `DELETE FROM audit_logs WHERE id = 1` → trigger blocks it

---

## Section 8 — Observability (Local Stack)

- [ ] Prometheus at `http://localhost:9090` → Targets page shows `prometheus (1/1 up)`
- [ ] Grafana at `http://localhost:3001` (admin/admin) → login succeeds
- [ ] Grafana → Dashboards → API Golden Signals → panels load (may show no data if no traffic)
- [ ] Grafana → Dashboards → Celery Health → panels load
- [ ] Grafana → Dashboards → Dependency Health → panels load
- [ ] Grafana → Explore → Loki → query `{job="vidya-api"}` → log lines appear after API traffic
- [ ] Prometheus alert rules page shows 7 rules in 3 groups (vidya.api, vidya.celery, vidya.kubernetes)

---

## Section 9 — Backup and Restore

- [ ] `infra/scripts/backup-postgres.sh` runs without error in docker-compose context
- [ ] Backup file created with `.sha256` manifest
- [ ] Restore drill: `infra/scripts/restore-drill.sh` → 3 human gates prompt correctly
- [ ] Post-restore smoke: API `/healthz` and `/ready` return healthy
- [ ] `audit_logs` table NOT cleared during restore (verify row count pre/post)

---

## Section 10 — CI/CD Pipeline

- [ ] `git push` to feature branch → CI workflow triggers in GitHub Actions
- [ ] CI checks: ruff lint, tsc type-check, pip-audit (HIGH/CRITICAL fail), npm audit (production), pytest, helm lint — all PASS
- [ ] PR merge → CD workflow triggers: migration dry-run, build, push to ghcr.io
- [ ] Staging deploy gate: `workflow_dispatch` required (not automatic) → staging pipeline does not auto-deploy

---

## Sign-off

| Section | Reviewer | Date | Result |
|---------|----------|------|--------|
| 1 Authentication | | | |
| 2 RBAC | | | |
| 3 Tenant Onboarding | | | |
| 4 AI Flows | | | |
| 5 Notifications | | | |
| 6 Mobile Responsiveness | | | |
| 7 Multi-Tenant Isolation | | | |
| 8 Observability | | | |
| 9 Backup and Restore | | | |
| 10 CI/CD Pipeline | | | |

**All sections PASS — cleared for external demo / staging deploy**

Reviewer: ___________
Date: ___________
