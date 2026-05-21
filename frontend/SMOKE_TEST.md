# Vidya Frontend — Manual Smoke Test Guide

Version: H-06 (Frontend Productization)
Last updated: 2026-05-21

---

## Prerequisites

- Backend API running at `http://localhost:8000`
- Frontend dev server running: `npm run dev` → `http://localhost:5173`
- At least one tenant provisioned (e.g., slug `test-uni`)
- One user per role seeded: ADMIN, DEAN, FACULTY, STUDENT, BOARD, GUIDE

---

## 1. Authentication

### 1.1 Login
- [ ] Navigate to `/login`
- [ ] Enter a bad slug → sign in → expect error banner (not a crash)
- [ ] Enter correct slug + wrong password → expect "Invalid credentials" error
- [ ] Enter correct credentials for any role → expect redirect to `/dashboard`
- [ ] After login, browser back button does not return to `/login`

### 1.2 Logout
- [ ] Click avatar in top-right → dropdown opens
- [ ] Click **Sign out** → redirected to `/login`
- [ ] Navigating back to `/dashboard` after logout → redirected to `/login`

### 1.3 Session persistence
- [ ] Log in, close tab, reopen at `/dashboard` → still authenticated (no re-login)
- [ ] Clear localStorage → navigating to any protected route redirects to `/login`

---

## 2. Role-Based Dashboard

Login with each role and verify the dashboard cards shown:

| Role    | Expected cards |
|---------|----------------|
| ADMIN   | All 9 cards |
| DEAN    | Programs, Course Kits, Bell Curve, Dashboard only (no Labs, Scripts) |
| FACULTY | Programs, Course Kits, Lab Assignments, Research, Exam Papers |
| STUDENT | My Labs, My Research only |
| BOARD   | Exam Papers, Scripts, Bell Curve |
| GUIDE   | Research only |

- [ ] Each card navigates to the correct route on click
- [ ] Time-of-day greeting changes (morning / afternoon / evening)
- [ ] No "undefined" or raw IDs appear in the greeting

---

## 3. Navigation & App Shell

### 3.1 Sidebar
- [ ] Sidebar visible on desktop (lg+); items match role (FACULTY vs STUDENT etc.)
- [ ] Sidebar hidden on mobile; hamburger icon visible top-left
- [ ] Tapping hamburger → sidebar slides in from left
- [ ] Tapping backdrop → sidebar closes
- [ ] Tapping any nav link → sidebar closes on mobile; navigates correctly
- [ ] Active link highlighted in indigo
- [ ] Institution name shown in sidebar header (prettified slug, not raw)

### 3.2 Topbar
- [ ] Breadcrumbs appear for nested routes (e.g., `Programs > Detail` on `/programs/:id`)
- [ ] Breadcrumb segment links navigate to parent (e.g., clicking "Programs" goes to `/programs`)
- [ ] No breadcrumbs on `/dashboard` (single-segment)
- [ ] UUIDs in URL show as "Detail" in breadcrumbs (not the raw UUID)
- [ ] User name and role chip visible in top-right
- [ ] Role chip colour matches role (purple=ADMIN, blue=FACULTY, green=STUDENT, etc.)

### 3.3 Mobile responsiveness
- [ ] At 375px (iPhone SE): sidebar hidden, hamburger visible, content scrollable
- [ ] At 768px (iPad): sidebar visible, breadcrumbs visible
- [ ] No horizontal overflow on any major page
- [ ] Topbar avatar accessible on mobile

---

## 4. Notifications

### 4.1 Bell icon
- [ ] Bell icon in topbar always visible
- [ ] When unread notifications exist: red badge with count appears
- [ ] Badge shows "99+" when count > 99
- [ ] Clicking bell opens notifications drawer from the right

### 4.2 Drawer
- [ ] Notifications listed; unread items have indigo highlight + dot indicator
- [ ] Timestamp shows as relative time ("5m ago", "2h ago", "3d ago")
- [ ] **Mark all read** button visible when unread count > 0
- [ ] Clicking **Mark all read** clears the dot indicators and badge
- [ ] Clicking backdrop (outside drawer) closes it
- [ ] Pressing Escape closes it
- [ ] Empty state shown when no notifications exist

---

## 5. Role Guards

Test that unauthorised roles see the "Access Restricted" page (not a crash or blank):

| Route | Allowed roles | Test with |
|-------|---------------|-----------|
| `/programs` | FACULTY, DEAN, ADMIN | Login as STUDENT |
| `/labs` | FACULTY, ADMIN | Login as STUDENT or BOARD |
| `/student/labs` | STUDENT, ADMIN | Login as FACULTY |
| `/research/problems` | FACULTY, ADMIN, GUIDE | Login as STUDENT |
| `/exams` | FACULTY, ADMIN, BOARD | Login as STUDENT |
| `/scripts` | ADMIN, BOARD | Login as FACULTY |
| `/bell-curve` | DEAN, ADMIN, BOARD | Login as FACULTY |

- [ ] Blocked user sees **Access Restricted** page with shield icon
- [ ] Sidebar and topbar still visible (not a full-page error)
- [ ] "Go to Dashboard" button navigates correctly

---

## 6. M01 – Programs (FACULTY / DEAN / ADMIN)

- [ ] `/programs` → list loads with status filter chips
- [ ] Filter by status (Draft, Generating, etc.) → list updates
- [ ] Click **New Program** → create dialog opens
- [ ] Fill title, department, degree → submit → new row appears
- [ ] Click a program row → navigates to `/programs/:id`
- [ ] Program detail: can view program structure, courses, outcomes
- [ ] **Generate with AI** button → spinner shows → AI content populates

---

## 7. M02 – Syllabuses (FACULTY / DEAN / ADMIN)

- [ ] `/syllabuses` → list loads
- [ ] Click a syllabus → detail page shows units and COs
- [ ] Can add/edit a unit inline

---

## 8. M03 – Course Kits (FACULTY / DEAN / ADMIN)

- [ ] `/course-kits` → list loads
- [ ] Click a kit → detail page with slides, quizlets, assignments
- [ ] Upload or generate a slide → appears in the list

---

## 9. M05 – Learning Packages (FACULTY / DEAN / ADMIN)

- [ ] `/learning-packages` → list loads
- [ ] Click a package → navigate to detail
- [ ] `/learning-packages/:id/curate` → curate view loads for FACULTY

---

## 10. M06 – Lab Assignments (FACULTY / ADMIN)

### Faculty flow
- [ ] `/labs` → list loads with status filter
- [ ] Click **New Assignment** → dialog opens
- [ ] Fill title, type (Written/Code) → create → navigates to detail
- [ ] On list: DRAFT row has **Publish** button → click → toast "Assignment published." appears
- [ ] PUBLISHED row has **Close** button → click → toast "Assignment closed." appears

### Student flow (login as STUDENT)
- [ ] `/student/labs` → published assignments visible
- [ ] Click an assignment → submit page loads
- [ ] Submit a written response → submit button works
- [ ] `/student/submissions/:id/result` → result page loads after evaluation

---

## 11. M07 – Research Supervision (FACULTY / GUIDE / ADMIN)

- [ ] `/research/problems` → problem list loads
- [ ] Create a research problem → appears in list
- [ ] `/research/documents/:id` → document page loads
- [ ] `/research/vivas/:id` → viva ratify page loads (FACULTY / ADMIN)
- [ ] Student: `/student/research` → student research page loads
- [ ] `/student/viva/:token` → viva join page loads (STUDENT)

---

## 12. M08 – Exam Papers (FACULTY / ADMIN / BOARD)

- [ ] `/exams` → list with status filter chips
- [ ] Click **New Exam Paper** → create page loads
- [ ] Fill title, type, marks → submit → navigates to editor
- [ ] Editor: question blocks render, can add questions
- [ ] BOARD: `/exams/:id/review` → board review panel loads
- [ ] `/exams/board/pending` → shows papers awaiting board review

---

## 13. M09 – Scanned Scripts (ADMIN / BOARD)

- [ ] `/scripts` → script list loads
- [ ] `/scripts/upload` → upload page loads, can select files
- [ ] `/scripts/:scriptId/evaluate` → evaluator panel loads
- [ ] `/scripts/board` → board script review page loads (BOARD)

---

## 14. M10 – Bell Curve (DEAN / ADMIN / BOARD)

- [ ] `/bell-curve` → analysis list loads
- [ ] Advisory banner visible (blue "Advisory only" box)
- [ ] ADMIN / BOARD: **New Analysis** button visible; click → trigger panel slides open
- [ ] Trigger panel shows a `<select>` with sealed exam papers (not a raw UUID input)
- [ ] Select a paper → click **Trigger** → new analysis row appears
- [ ] Click an analysis card → navigates to `/bell-curve/:id`
- [ ] BOARD: **Ratify** button visible on READY / BOARD_REVIEWED analyses
- [ ] `/bell-curve/reports` → fairness report page loads
- [ ] `/bell-curve/:id/ratify` → ratify page loads (BOARD only)
- [ ] FACULTY trying to access `/bell-curve` → Access Restricted page

---

## 15. Super Admin Console

### 15.1 Login
- [ ] Navigate to `/admin/login` → separate login form (no tenant slug field)
- [ ] Wrong credentials → error banner
- [ ] Correct super-admin credentials → redirected to `/admin/tenants`

### 15.2 Tenant list
- [ ] Shared admin header visible with "Vidya Admin Console" and **Sign out**
- [ ] Tenant count shown in subtitle (e.g., "3 institutions · 2 active")
- [ ] Status badges correct (PROVISIONING/ACTIVE/FAILED)
- [ ] **Sort A–Z** checkbox sorts tenant names alphabetically
- [ ] **Show inactive** checkbox toggles inactive tenants
- [ ] Error fetching → PageError with **Retry** button

### 15.3 Tenant create
- [ ] Click **New Tenant** → create page loads (same admin header)
- [ ] Type password < 8 chars → "Minimum 8 characters" hint appears inline
- [ ] Type password missing uppercase → hint updates correctly
- [ ] Valid password → green "Password looks good." message
- [ ] Submit with invalid password → button disabled (no server round-trip)
- [ ] Submit valid form → provisioning starts → redirected to tenant detail

### 15.4 Tenant detail
- [ ] Detail page: all info rows populated (slug, schema, status, active)
- [ ] PROVISIONING status: spinner icon in badge; page auto-refreshes every 3 s
- [ ] FAILED status: red alert box with **Retry provisioning** button
- [ ] Click **Deactivate** → **confirmation dialog** appears ("All users will be locked out")
- [ ] Cancel → dialog closes, no change
- [ ] Confirm → toast "Tenant deactivated." appears; "Activate" button appears
- [ ] Click **Activate** → confirmation dialog → confirm → toast "Tenant activated."

### 15.5 Admin sign out
- [ ] Click **Sign out** in admin header → redirected to `/admin/login`
- [ ] Navigating back to `/admin/tenants` → redirected to `/admin/login`

---

## 16. Error / Loading / Empty States

- [ ] Simulate network offline → list pages show PageError with Retry button
- [ ] Retry button refetches and shows data if network restored
- [ ] Empty database tenant → programs list shows `BookOpen` icon + "No programs found."
- [ ] Loading state: spinner + "Loading…" text (not blank screen, not raw "undefined")
- [ ] Toast notifications: appear bottom-right, auto-dismiss in ~3.5 s
- [ ] Confirm dialogs: overlay darkens background, Cancel and Confirm buttons present

---

## 17. Checklist Summary

Run through this checklist on each release candidate:

- [ ] Login/logout for all 6 roles
- [ ] Dashboard cards correct per role
- [ ] Sidebar filtering correct per role
- [ ] Breadcrumbs appear on nested pages
- [ ] Notifications drawer opens and mark-all-read works
- [ ] Role guards block unauthorised pages (show Access Restricted, not blank)
- [ ] Admin console tenant CRUD with confirmation dialogs
- [ ] Toast appears on publish/close lab, activate/deactivate tenant
- [ ] Mobile: sidebar opens/closes; no layout breakage at 375px
- [ ] Build passes (`npm run build`) with 0 type errors
