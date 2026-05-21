# Vidya Onboarding Walkthrough

**Owner:** Srinivas / Fidelitus Corp  
**Last updated:** 2026-05-21  
**Applies to:** Tenant admins and new users

---

## Overview

This document walks through the end-to-end onboarding flow for a new institution on Vidya. It covers the full path from tenant creation to a live faculty/student session.

---

## 1. Tenant Provisioning (Super Admin)

1. Log in to the Super Admin portal at `/admin/login` using SUPER_ADMIN credentials.
2. Go to **Tenants → New tenant**.
3. Fill in institution name and slug (e.g. `my-university`). The slug becomes part of every API request header and cannot be changed later.
4. Submit. Vidya will:
   - Create an isolated PostgreSQL schema (`tenant_<slug>`)
   - Run Alembic migrations for that schema
   - Seed an ADMIN user with email and temporary password as entered

**Expected result:** Tenant status shows `ACTIVE`. Admin credentials are ready.

---

## 2. First Admin Login and Password Setup

1. Open the tenant login page at `/login`.
2. Enter the institution slug, the seeded admin email, and the temporary password.
3. On successful login, Vidya detects that `password_changed_at` is null and automatically redirects to `/first-login`.
4. Enter the temporary password as **Temporary password**, choose a new permanent password, confirm, and submit.
5. On success: Vidya sets `password_changed_at`, revokes all refresh tokens, and redirects to `/dashboard`.

**Security properties:**
- The admin cannot access any other page until the password is set.
- All existing sessions are invalidated after the change.
- The temporary password used for seeding is no longer valid.

**If forced-login redirect loops:** Clear `vidya_token` from localStorage and reload.

---

## 3. Dashboard and Onboarding Checklist

After first login, the ADMIN dashboard shows a **Getting started** checklist:

| Step | Condition |
|------|-----------|
| Sign in to Vidya | Always done |
| Set your permanent password | Done when `first_login = false` |
| Add faculty and students | Links to `/users` |
| Review institution settings | Links to `/settings` |

The checklist disappears once all items are complete.

---

## 4. Adding Users

1. Go to **Administration → Users** in the sidebar.
2. Click **Add user**.
3. Fill in: full name, email, temporary password, role, identifier (optional).
4. Click **Create user**.

**Roles and their access:**

| Role | Typical user | Access |
|------|-------------|--------|
| `ADMIN` | IT admin / principal | All modules + user management |
| `DEAN` | Academic dean | Programs, analytics, bell curve |
| `FACULTY` | Lecturer | Programs, course kits, labs, research, exams |
| `STUDENT` | Student | My labs, my research |
| `BOARD` | External examiner | Exam papers, scripts, bell curve |
| `GUIDE` | Research supervisor | Research supervision |

**After creation:** The new user's account has `password_changed_at = null`, so they will be prompted to set a permanent password on first login.

---

## 5. Managing Users

From the **Users** page:
- Filter by role or search by name/email/identifier.
- Click **Edit** on any row to change the user's name, role, or active status.
- Deactivating a user (`is_active = false`) prevents login immediately.

**Audit trail:** Every create, update, deactivate, and role change is logged to the audit log with the acting user's ID.

---

## 6. Institution Settings

Go to **Administration → Settings** to review:
- Institution slug and schema name (read-only)
- Your own account profile (name, email, role)
- Change your password at any time

---

## 7. Role-Specific First Sessions

### Faculty
1. Log in → set permanent password → redirected to dashboard.
2. Dashboard shows: Programs, Course Kits, Lab Assignments, Research, Exam Papers.
3. Start with **Programs** to define the academic structure.

### Student
1. Log in → set permanent password → redirected to dashboard.
2. Dashboard shows: **My Labs**, **My Research**.
3. Labs and research projects appear once faculty publishes them.

### Board member
1. Log in → set permanent password → redirected to dashboard.
2. Dashboard shows: Exam Papers, Scripts, Bell Curve.
3. Exam papers submitted for review appear in **Exam Papers**.

---

## 8. QA Checklist (Manual Validation)

### Pre-flight
- [ ] KIND cluster is running: `powershell -ExecutionPolicy Bypass -File infra\scripts\kind-smoke.ps1`
- [ ] API is healthy: `kind-port-forward.ps1 -Service api` → `http://localhost:8080/docs`

### Tenant creation
- [ ] Super admin login works at `/admin/login`
- [ ] New tenant creates successfully with status `ACTIVE`
- [ ] Seeded admin credentials are noted

### First-login flow
- [ ] Admin logs in with temporary password
- [ ] Redirected to `/first-login` (not dashboard)
- [ ] Cannot navigate to `/dashboard` while on `/first-login`
- [ ] Password change succeeds with correct current password
- [ ] Wrong current password returns error (no redirect)
- [ ] After success: redirected to `/dashboard`
- [ ] Sidebar no longer shows "Set your permanent password" banner

### User management
- [ ] Users page loads at `/users` for ADMIN
- [ ] `/users` returns 403 for FACULTY/STUDENT roles
- [ ] Create user form validates password length (≥8 chars)
- [ ] Created user appears in table immediately
- [ ] Edit user: role change persists
- [ ] Edit user: deactivate → user cannot log in

### Settings
- [ ] Settings page loads at `/settings` for ADMIN
- [ ] Institution slug and schema shown correctly
- [ ] Change password works from settings page
- [ ] Wrong current password shows error in-place (no redirect)

### Onboarding checklist
- [ ] ADMIN dashboard shows checklist after first login
- [ ] "Set your permanent password" is checked after password change
- [ ] Checklist disappears when all 4 items are done (password changed, users added, settings reviewed)

### Role navigation
- [ ] STUDENT sees only "My Labs" and "My Research" in sidebar
- [ ] BOARD sees Exam Papers, Scripts, Bell Curve
- [ ] GUIDE sees Research in sidebar
- [ ] DEAN sees Programs, Analytics (no labs or student sections)
- [ ] No broken links in sidebar for any role

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Stuck on `/first-login` after password change | Token not refreshed | Clear `vidya_token` from localStorage, log in again |
| `/users` returns 403 | Token is for FACULTY role | Log in as ADMIN |
| "Current password is incorrect" on first-login page | Wrong temporary password | Check seeded credentials in tenant creation record |
| Onboarding checklist stuck showing | `firstLogin` not updated | Call `/auth/me` manually or refresh page |
| Sidebar shows "Set your permanent password" after changing | Stale auth context | Log out and log back in |
