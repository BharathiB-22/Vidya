# VIDYA AI — Super Admin User Manual

**Product:** VIDYA AI Enterprise Academic Platform (University ERP SaaS)
**Module:** Super Admin Platform Console
**Vendor:** SherpaVector Pvt. Ltd.
**Audience:** Super Admins, Operations Team, New Administrators
**Document Type:** Operational User Manual
**Version:** 1.0 · July 2026

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Login (Super Admin Portal)](#2-login-super-admin-portal)
3. [Console Layout & Navigation](#3-console-layout--navigation)
4. [Dashboard](#4-dashboard)
5. [Tenants (University List)](#5-tenants-university-list)
6. [Create Tenant (Provision University)](#6-create-tenant-provision-university)
7. [Tenant Detail](#7-tenant-detail)
8. [Edit Tenant](#8-edit-tenant)
9. [Suspend / Activate / Archive Tenant](#9-suspend--activate--archive-tenant)
10. [Delete Tenant (Soft Delete)](#10-delete-tenant-soft-delete)
11. [Deleted Tenants (Restore & Permanent Delete)](#11-deleted-tenants-restore--permanent-delete)
12. [Monitoring](#12-monitoring)
13. [Platform Health](#13-platform-health)
14. [Audit Logs](#14-audit-logs)
15. [Tenant Migrations](#15-tenant-migrations)
16. [Platform Branding](#16-platform-branding)
17. [Settings](#17-settings)
18. [My Profile](#18-my-profile)
19. [Sign Out](#19-sign-out)
20. [Features Not Yet Available](#20-features-not-yet-available)

---

## 1. Introduction

The Super Admin Platform Console is the top-level administrative interface of VIDYA AI. It is a **separate portal** from the university (tenant) application, with its own login page, its own authentication tokens, and its own dark-themed interface ("Platform Console").

A Super Admin is the **platform owner**. From this console you can:

- Provision new universities (tenants), each with a fully isolated PostgreSQL schema
- Manage the tenant lifecycle: activate, deactivate, archive, reactivate, soft-delete, restore, permanently delete
- Edit tenant identity and branding (name, contact email, logo, colors)
- Monitor platform health, background jobs, and AI provider status
- Review the append-only audit log across all tenants
- Manage tenant database schema migrations
- Configure platform-level branding
- View the (read-only) platform configuration
- Manage your own Super Admin account and sessions

> **Important:** The Super Admin console manages the **platform**. Day-to-day university administration (users, roles, students, faculty, academics) is done by each university's own Admin inside the tenant portal, not from this console.

---

## 2. Login (Super Admin Portal)

**Purpose:** Authenticate as a Super Admin and enter the Platform Console.

[Screenshot – Super Admin Login Page]

**Navigation:** `https://<your-domain>/admin/login`

**Description:**
A dedicated login page branded "Super Admin Portal". The left panel shows platform capabilities; the right panel contains the sign-in form with email/password fields and a Google Sign-In option. Login is rate-limited to **5 attempts per minute** per client.

**Steps:**

1. Open `/admin/login` in your browser.
2. Enter your **Admin Email**.
3. Enter your **Password**. Use the eye icon to show/hide the value.
4. (Optional) Tick **Remember me**.
5. Click **Sign in**.
6. Alternatively, click **Sign in with Google** to authenticate with a Google account (available only when Google Sign-In is configured for the deployment).

**Buttons and actions:**

| Control | Action |
|---|---|
| Sign in | Submits email + password to the platform login API |
| Sign in with Google | Opens the Google identity prompt and logs in with the returned credential |
| Show/Hide password (eye icon) | Toggles password visibility |
| Remember me | Checkbox (UI preference) |
| Forgot password? | **Partially Implemented** — the button is displayed but is not wired to a flow in the UI. Backend password-reset endpoints (`request` / `verify` / `confirm`) exist. |
| Two-Factor Authentication field / Resend code | **Partially Implemented** — the 6-digit code field is displayed but is **not connected** to the login submission; 2FA is not enforced by the backend. |

**Expected result:**
On success you are redirected to `/admin/dashboard`. An access token is stored in the browser (`vidya_admin_token`) — this token store is separate from tenant-user logins. The login is recorded in the audit log as `PLATFORM_LOGIN_SUCCESS` (failures as `PLATFORM_LOGIN_FAILURE`).

**Notes:**
- Access tokens expire after the configured period (visible under Settings → Security); refresh tokens keep sessions alive.
- All `/admin/*` console routes are protected by an admin auth guard; opening them without a valid token returns you to the login page.

**Warnings:**
- More than 5 login attempts within a minute are rejected by rate limiting. Wait a minute and retry.

---

## 3. Console Layout & Navigation

**Purpose:** Orient new administrators in the console shell.

[Screenshot – Admin Shell with Sidebar and Topbar]

**Description:**
Every console page shares the same shell:

- **Sidebar (left)** — SherpaVector brand header, then three navigation sections:
  - **Platform:** Dashboard, Tenants, Deleted Tenants, Create Tenant
  - **Operations:** Monitoring, Platform Health, Audit Logs, Tenant Migrations
  - **Administration:** Branding, Settings, My Profile
  - Plus a **Sign out** entry and a footer identifying the signed-in role (Super Admin · Platform Owner).
- **Topbar** — breadcrumb ("Platform Console › <page>"), a search box and a notification bell (**both decorative — not functional**), and a Super Admin identity chip.
- **Main area** — the current page.

On small screens the sidebar collapses behind a hamburger button.

---

## 4. Dashboard

**Purpose:** At-a-glance platform overview and quick entry points.

[Screenshot – Admin Dashboard]

**Navigation:** Sidebar → Platform → **Dashboard** (`/admin/dashboard`)

**Description:**
The landing page after login. Shows a greeting, the total number of registered universities, four KPI cards, the five most recent universities, quick actions, and a platform status banner.

**Screen contents:**

| Element | Meaning |
|---|---|
| Total Universities | Count of all tenants returned by the registry |
| Active Tenants | Tenants currently active (users can log in) |
| Pending Setup | Tenants still in `PROVISIONING` state |
| Platform Health | "OK" when no tenant is in `FAILED` state; otherwise shows the failed count |
| Recent Universities table | Last five tenants: name, slug, status badge, created date, active flag. Clicking a row opens its detail page. |
| Quick Actions | Create University, View All Tenants, Platform Health, Audit Logs |
| Platform status card | Green "All systems operational" or red "Provisioning errors" with a **View failed tenants** shortcut |

**Steps (typical morning check):**

1. Log in; you land on the Dashboard.
2. Confirm the Platform Health card reads **OK**.
3. If it shows failures, click **View failed tenants** and follow the retry procedure in [Section 7](#7-tenant-detail).

**Expected result:** Current platform counts within a few seconds of page load.

**Notes:** Tenant statuses shown here: `ACTIVE`, `PROVISIONING`, `FAILED`, `INACTIVE`, `ARCHIVED`, `DELETED`, `PERMANENTLY_DELETED`.

---

## 5. Tenants (University List)

**Purpose:** Central registry of all universities with lifecycle actions on each row.

[Screenshot – Tenant List Page]

**Navigation:** Sidebar → Platform → **Tenants** (`/admin/tenants`)

**Description:**
A searchable, filterable table of all tenants. Stat cards across the top show Total Universities, Active Tenants, Inactive/Archived, Platform Health, and (when enabled) Deleted Tenants. Each row shows Institution (name + slug), Status badge, Contact email, Created date, and per-row action buttons.

**Steps — find a tenant:**

1. Open **Tenants**.
2. Type a name or slug into the **Search by name or slug…** box; the list filters as you type.
3. Optionally toggle:
   - **Sort A–Z** — alphabetical ordering
   - **Show inactive / archived** — include `INACTIVE` and `ARCHIVED` tenants (on by default)
   - **Show deleted** — additionally show soft-deleted tenants (rows appear dimmed)
4. Click a row to open the tenant's detail page.

**Buttons and actions (per row):**

| Button | Availability | Action |
|---|---|---|
| Edit | Any non-deleted tenant | Opens the Edit University dialog (see [Section 8](#8-edit-tenant)) |
| Deactivate | Active tenants | Sets status to `INACTIVE` after confirmation |
| Archive | Non-archived, non-deleted tenants | Sets status to `ARCHIVED` after confirmation |
| Reactivate | Archived or inactive tenants (not `FAILED`/`PROVISIONING`) | Sets status back to `ACTIVE` |
| Delete | Any non-deleted tenant | Opens the type-to-confirm soft-delete dialog (see [Section 10](#10-delete-tenant-soft-delete)) |
| New University (header) | Always | Opens the Create Tenant form |

**Expected result:** Actions apply immediately; a toast confirms the outcome ("Tenant deactivated.", "Tenant archived.", etc.) and the list refreshes.

**Notes:** Stat card counts exclude deleted tenants so numbers reflect live institutions.

---

## 6. Create Tenant (Provision University)

**Purpose:** Provision a new university with an isolated database schema and a seeded admin account.

[Screenshot – Provision University Form]

**Navigation:** Sidebar → Platform → **Create Tenant** (`/admin/tenants/new`), or **New University** on the Tenants page, or **Create University** on the Dashboard.

**Description:**
A two-column screen. The left panel lists what provisioning creates:

- Isolated PostgreSQL schema
- Tenant record with branding
- Admin account seeded
- First-login password change enforced
- Action logged to audit trail

The right panel is the form, in three sections: Institution, Admin account, and Branding & contact (optional).

**Steps:**

1. **University name** — 3–100 characters. The Institution ID (slug) and schema name are derived from this name automatically.
2. **Admin account:**
   - Full name of the first university administrator.
   - Email — becomes the admin's login.
   - Temporary password — must contain at least 8 characters with an uppercase letter, a lowercase letter, a digit, and a special character. Inline validation shows what's missing.
3. **Branding & contact (optional):**
   - Contact email (defaults to the admin email if left blank)
   - University logo URL
   - Primary and secondary brand colors (color picker or hex code, e.g. `#2563eb`)
4. Click **Provision university**.

**Buttons and actions:**

| Button | Action |
|---|---|
| Provision university | Submits the form; disabled while the password is invalid or provisioning is running |
| Cancel | Returns to the tenant list |
| ← (back arrow) | Returns to the tenant list |

**Expected result:**
A green **"University provisioned"** success screen showing copyable fields:

- University name
- **Institution ID (slug)** — users enter this at login
- Admin email
- Temporary password

Each field has a copy-to-clipboard button. Buttons let you **View tenant detail**, **Open login page** (tenant portal in a new tab), or go **Back to tenant list**. The event is logged as `TENANT_PROVISIONED`.

**Notes:**
- If a tenant with the same derived slug already exists, provisioning is rejected — choose a distinct name.
- The seeded admin **must change the temporary password on first login**.

**Warnings:**
- The temporary password is displayed **only on this success screen**. Copy it and hand it to the university admin through a secure channel before leaving the page.
- If provisioning fails mid-way, the tenant is saved with status `FAILED`; use **Retry provisioning** from its detail page rather than creating a duplicate.

---

## 7. Tenant Detail

**Purpose:** Inspect one tenant and run lifecycle actions against it.

[Screenshot – Tenant Detail Page]

**Navigation:** Tenants list → click a row (`/admin/tenants/{id}`)

**Description:**
Shows an info card (Institution name, Slug, Schema name, Status, Contact email, Provisioned timestamp) and an Actions card. While a tenant is `PROVISIONING`, the page auto-refreshes every 3 seconds until provisioning settles.

**Buttons and actions:**

| Action | Shown when | Effect |
|---|---|---|
| Edit | Always | Dialog to change name and contact email (slug is read-only) |
| Retry provisioning | Status is `FAILED` | Re-runs schema creation / admin seeding on the same tenant record |
| Deactivate | Tenant is active | Locks out all tenant users (status `INACTIVE`) |
| Activate | Tenant inactive (not archived) | Re-enables login |
| Archive | Not archived | Hides tenant from active workspaces; data preserved |
| Reactivate | Archived or inactive | Restores full access (status `ACTIVE`) |

Every action opens a confirmation dialog first.

**Steps — recover a FAILED tenant:**

1. Open the failed tenant (Dashboard → View failed tenants, or Tenants list).
2. Read the red "Provisioning failed" panel.
3. Click **Retry provisioning**.
4. Wait for the toast "Provisioning retried — tenant is now ACTIVE."

**Expected result:** Status changes are reflected immediately on the badge and logged to the audit trail (`TENANT_DEACTIVATED`, `TENANT_ARCHIVED`, `TENANT_REACTIVATED`, `TENANT_UPDATED`, `TENANT_PROVISIONED`).

**Warnings:**
- Deactivating locks out **all users** of that university immediately.

---

## 8. Edit Tenant

**Purpose:** Update tenant identity and branding.

[Screenshot – Edit University Dialog]

**Navigation:** Tenants list → **Edit** on a row, or Tenant Detail → **Edit**.

**Description:**
A modal dialog. The list-page version edits name, contact email, logo URL, and primary/secondary colors; the detail-page version edits name and contact email only. In both, the **slug is read-only** and status can only be changed via the lifecycle buttons, not by editing.

**Steps:**

1. Click **Edit** on the tenant.
2. Change any of: University name (3–100 chars), Contact email, Logo URL, Primary color, Secondary color (hex codes such as `#10b981`; a color-picker swatch is provided).
3. Click **Save changes**.

**Expected result:** Toast "Tenant updated."; the list refreshes; event `TENANT_UPDATED` is written to the audit log. Only changed fields are sent.

**Notes:** Colors must be valid hex codes (`#abc` or `#2563eb`); invalid values are rejected by the server.

---

## 9. Suspend / Activate / Archive Tenant

**Purpose:** Control whether a university's users can log in, without touching data.

[Screenshot – Lifecycle Confirmation Dialog]

**Navigation:** Tenants list row buttons, or Tenant Detail → Actions.

**Description:**
Three reversible lifecycle states:

| State | Meaning | User access |
|---|---|---|
| `ACTIVE` | Normal operation | Allowed |
| `INACTIVE` (Deactivate) | Suspended | Blocked |
| `ARCHIVED` | Hidden from active workspaces; long-term parked | Blocked |

**Steps — suspend a university:**

1. Locate the tenant on the Tenants page.
2. Click **Deactivate**.
3. Read the confirmation ("Users at "X" will no longer be able to log in.") and confirm.

**Steps — resume service:**

1. Enable **Show inactive / archived** if the tenant is hidden.
2. Click **Reactivate** on the row and confirm.

**Expected result:** Immediate effect, success toast, and a corresponding audit event.

**Notes:**
- Archive **never** drops the database schema; data is fully preserved and the tenant can be reactivated at any time.
- You cannot set `PROVISIONING`, `FAILED`, `DELETED`, or `PERMANENTLY_DELETED` from the edit/lifecycle path — those states are managed by their dedicated flows.

---

## 10. Delete Tenant (Soft Delete)

**Purpose:** Remove a tenant from operation while preserving its data and audit history.

[Screenshot – Delete Tenant Confirmation Dialog]

**Navigation:** Tenants list → **Delete** on a row.

**Description:**
A high-friction, type-to-confirm dialog. The warning banner states:

- Tenant data may be deleted or become inaccessible
- All users at the institution lose access immediately
- The tenant schema is **not dropped**; the tenant is marked `DELETED`
- Only use this for test or demo tenants

**Steps:**

1. Click **Delete** on the tenant row.
2. Review the warning and the tenant identity (name + slug) shown in the dialog.
3. Type the tenant's **exact slug** into the confirmation field. The **Delete tenant** button stays disabled until the text matches.
4. Click **Delete tenant**.

**Expected result:** Toast "Tenant deleted."; the tenant disappears from the active list and moves to **Deleted Tenants**. Event `TENANT_DELETED` is logged. The server independently verifies the confirmation slug and rejects mismatches.

**Warnings:**
- All users of the university are locked out immediately.
- This is a **soft** delete — recoverable via Restore — but treat it as a production-impacting action.

---

## 11. Deleted Tenants (Restore & Permanent Delete)

**Purpose:** Manage soft-deleted tenants: bring them back or retire them permanently.

[Screenshot – Deleted Tenants Page]

**Navigation:** Sidebar → Platform → **Deleted Tenants** (`/admin/deleted-tenants`)

**Description:**
Lists all tenants in `DELETED` status with columns: Institution, Deleted Date, Deleted By, Schema, Actions. A banner reminds you that schemas are intact, restore is available, and Permanent Delete preserves audit logs and does **not** drop the schema. Includes a search box and Refresh button.

**Steps — restore a tenant:**

1. Open **Deleted Tenants**.
2. Find the tenant (search by name or slug).
3. Click **Restore** and confirm.
4. The tenant returns in **INACTIVE** status. Go to the Tenants page and click **Reactivate** to re-enable user logins.

**Steps — permanently delete a tenant:**

1. Click **Permanent Delete** on the row.
2. Read the warning: the action cannot be undone; audit records are preserved for compliance; the schema is NOT dropped; the row is marked `PERMANENTLY_DELETED`; restore becomes unavailable.
3. Type the exact slug to enable the **Permanently delete** button.
4. Click **Permanently delete**.

**Expected result:**
- Restore → toast "Tenant restored to INACTIVE status." and event `TENANT_RESTORED`.
- Permanent delete → toast "Tenant permanently deleted. Audit records are preserved." and event `TENANT_PERMANENTLY_DELETED`. The tenant vanishes from all application lists.

**Warnings:**
- **Permanent Delete is irreversible in the application.** Only tenants already in `DELETED` state can be permanently deleted, and only with an exact slug match.

---

## 12. Monitoring

**Purpose:** Live operational overview: service connectivity, tenant counts, background jobs, AI providers, and recent platform events.

[Screenshot – Platform Monitoring Page]

**Navigation:** Sidebar → Operations → **Monitoring** (`/admin/monitoring`)

**Description:**
Auto-refreshes every 30 seconds (manual **Refresh** button available). Sections:

1. **Platform Health** — connectivity cards for PostgreSQL (db), Redis, S3/MinIO (s3), and Qdrant, each with a healthy/unhealthy/skipped badge and latency; plus an API Server card.
2. **Tenant Statistics** — Total, Active, Inactive, Archived, Provisioning, Failed counts (excludes deleted).
3. **Background Jobs** — Completed / Pending / Running / Failed bars with the number of tasks submitted in the last 24 hours and the all-time total.
4. **AI Services** — one card per provider showing configured state ("Ready" / "Not configured"), the model name, and which provider is currently **Active**.
5. **Recent System Activity** — the latest platform-level audit events (tenant provisioned/updated/deleted, platform logins, etc.) with relative timestamps.

**Steps:**

1. Open **Monitoring**.
2. Scan the header: "All systems operational" (green) vs "Degraded — check service health".
3. If a service card is red, note its error message and escalate/fix the underlying service; use **Platform Health** for deeper diagnostics.

**Expected result:** A current snapshot with a "Updated HH:MM:SS" timestamp.

**Notes:** "Skipped" means the service is not configured in this environment — it is not an error.

---

## 13. Platform Health

**Purpose:** Detailed diagnostics for troubleshooting — infrastructure, Celery workers, task queues, and AI providers.

[Screenshot – Platform Health Page]

**Navigation:** Sidebar → Operations → **Platform Health** (`/admin/health`)

**Description:**
Deeper than Monitoring. Sections:

1. **System Diagnostics** — Database, Redis, S3 storage, Qdrant vector DB, and the API itself, with latency color-coding.
2. **Worker Diagnostics** — Celery workers (light `celery` queue and `celery-heavy` AI queue) checked via broker broadcast ping. A hint shows the local dev command to start a worker. Worker warnings are non-critical.
3. **Queue Diagnostics** — Pending / Running / Completed / Failed KPIs, per-queue pending/running breakdown, workers online, tasks in the last 24h, and failed (24h) count.
4. **AI Diagnostics** — provider cards (Ready / Not configured, active flag, model). For unconfigured providers the page names the environment key to set (e.g. `GROQ_API_KEY`). API keys are never displayed.

**Steps:**

1. Open **Platform Health**.
2. Click **Run Checks** to re-run diagnostics on demand.
3. Read the overall banner: "All systems operational" or "Degraded — one or more services need attention".
4. Drill into whichever card is red; the error message string is shown on the card.

**Expected result:** A full diagnostic snapshot with a "Last checked" time.

**Notes:** If AI generation jobs sit in "Pending", check Worker Diagnostics — no workers online means nothing will consume the queue.

---

## 14. Audit Logs

**Purpose:** Query the append-only, platform-wide audit trail for compliance and investigation.

[Screenshot – Audit Logs Page]

**Navigation:** Sidebar → Operations → **Audit Logs** (`/admin/audit-logs`)

**Description:**
Header describes it accurately: "Complete event history across all tenants — append-only, tamper-proof." Contents:

- **KPI cards:** Total Events, Tenant Events, Login Events, AI Events, Security Events.
- **Filter bar:** Tenant (dropdown of all tenants), Event Type (grouped dropdown covering Authentication, Tenant Management, Users, Programs, Syllabuses, Course Kits, Learning Packages, Labs, Research, Exams, Scripts & Bell Curve, SIS, and Storage events), From date, To date. **Apply Filters** / **Reset** buttons.
- **Results table:** Timestamp, Tenant, User (role + shortened user id), Action, Entity (+ shortened target id), Status badge (SUCCESS / FAILED / WARNING / ACTION), paginated 50 per page.
- **Recent Activity panel (right):** live feed of the 20 most recent events, refreshed every 60 seconds.

**Steps — investigate an incident:**

1. Open **Audit Logs**.
2. Pick the affected **Tenant** from the dropdown.
3. Pick an **Event Type** (e.g. *Auth Login Failure*) or leave "All Event Types".
4. Set the **From**/**To** date range.
5. Click **Apply Filters**.
6. Page through results with the ‹ / › controls; the footer shows "Showing X–Y of N events".

**Expected result:** A filtered, timestamped event list suitable for audit evidence.

**Notes:**
- The audit table is **append-only**: no update or delete operations exist anywhere in the application, and records survive even tenant permanent deletion.
- This console view is **read-only**; there is no export button on this screen.

---

## 15. Tenant Migrations

**Purpose:** Verify every tenant schema is on the latest database migration and re-run failed migrations.

[Screenshot – Tenant Migrations Page]

**Navigation:** Sidebar → Operations → **Tenant Migrations** (`/admin/tenant-migrations`)

**Description:**
One row per non-deleted tenant: Tenant (name + schema), Current version (revision id), Latest version (head revision), Status badge (**Up to date / Pending / Failed / Unknown**), Last migration time, and Actions. Rows with a failed migration expose the error message.

**Steps:**

1. Open **Tenant Migrations** after deploying a release containing database migrations.
2. Confirm each tenant shows **Up to date**.
3. For a **Pending** or **Failed** tenant, click **Retry** on the row. This runs the pending migrations for that single tenant schema immediately.
4. Re-check the status badge and the Last migration timestamp.

**Expected result:** All tenants converge on the head revision; the retry response reports from/to revisions or the failure error.

**Warnings:** Migrations alter tenant schemas. Run retries during a low-traffic window when possible and investigate errors before retrying repeatedly.

---

## 16. Platform Branding

**Purpose:** Configure the platform-wide identity shown on login pages and throughout the console.

[Screenshot – Platform Branding Page]

**Navigation:** Sidebar → Administration → **Branding** (`/admin/branding`)

**Description:**
An editable form with a live preview. Sections:

| Section | Fields |
|---|---|
| Platform Identity | Platform Name, Company Name |
| Support Contact | Support Email, Support Phone |
| Logo & Favicon | Logo URL (with thumbnail preview), Favicon URL |
| Brand Colors | Primary Color, Accent Color (picker + hex input) |

The right column shows a **Live Preview** (mock header + buttons using your colors/logo) and lists where branding is applied: Super Admin login page, platform console header, tenant portal login pages, and email templates (if configured).

**Steps:**

1. Open **Branding**.
2. Edit any field; the preview updates as you type.
3. Click **Save Branding**.

**Expected result:** Toast "Branding saved successfully.", the button flashes "Saved!", and the "Last updated" timestamp refreshes. Only changed fields are transmitted.

**Notes:** This is **platform** branding. Each university's own logo/colors are set per-tenant (Create/Edit Tenant), and universities can manage their branding from their Institution Settings panel.

---

## 17. Settings

**Purpose:** Read-only view of the live platform configuration — no secrets displayed.

[Screenshot – Platform Settings Page]

**Navigation:** Sidebar → Administration → **Settings** (`/admin/settings`)

**Description:**
Six cards:

1. **Platform Profile** — platform name, company, support email, environment badge (Development / Staging / Production), build version.
2. **Platform Branding** — current logo and colors (summary; edit on the Branding page).
3. **AI Providers** — provider strategy, then per-provider rows for **Gemini**, **Groq**, and **DeepSeek**: model name, Enabled/Disabled, and Key set / No key. Fallback order is Gemini → Groq → DeepSeek. Providers are enabled/disabled via environment variables (`AI_*_ENABLED`); API keys are never shown.
4. **Storage** — provider (MinIO or AWS S3), endpoint, bucket, region, TLS/SSL flag, max upload size (MB).
5. **Security** — JWT authentication, role-based access control, multi-tenant isolation, audit logging, soft-delete protection (all architectural constants), plus access-token expiry (minutes), refresh-token expiry (days), and email notification status with the SMTP from-address.
6. **System Actions** — shortcuts: Refresh Configuration, Platform Monitoring, Audit Logs.

**Steps:**

1. Open **Settings**.
2. Verify the environment badge matches the deployment you think you're on.
3. Use **Refresh** to reload after changing backend environment variables.

**Expected result:** A current, secrets-free configuration snapshot.

**Notes:** Nothing on this screen is editable. Configuration changes are made via deployment environment variables/Helm values, not the UI.

---

## 18. My Profile

**Purpose:** Manage your own Super Admin account and security.

[Screenshot – My Profile Page]

**Navigation:** Sidebar → Administration → **My Profile** (`/admin/profile`)

**Description:**
Four cards:

1. **Account Info** — avatar (or initials), full name, email, Super Admin + Active badges, joined date, last login. **Edit profile** reveals fields for Display name and Avatar URL.
2. **Security** — count of active sessions, last login time, role badge, and a reminder that changing your password terminates all other sessions.
3. **Change Email** — new email + **current password** required. After a change you must use the new email for future logins.
4. **Change Password** — current password, new password (with a live strength meter: Weak → Very Strong), and confirmation. Mismatched confirmations are flagged inline.

**Steps — change your password:**

1. Open **My Profile** → Change Password card.
2. Enter your current password.
3. Enter and confirm the new password; aim for a "Strong" or better rating.
4. Click **Change Password**.

**Expected result:** Toast "Password changed. All other sessions terminated." and a green confirmation panel.

**Warnings:**
- Changing email or password affects your login immediately.
- Password change revokes every other active session — expect other devices to be signed out.

---

## 19. Sign Out

**Purpose:** End the console session securely.

[Screenshot – Sidebar Sign Out]

**Navigation:** Sidebar → **Sign out**

**Steps:**

1. Click **Sign out** at the bottom of the sidebar navigation.

**Expected result:** The stored admin token is removed from the browser and you are returned to the login page. Logout events are audit-logged (`PLATFORM_LOGOUT`; a logout-all API also exists and logs `PLATFORM_LOGOUT_ALL`).

---

## 20. Features Not Yet Available

To keep expectations accurate, the following are **not** implemented in the Super Admin console today:

| Feature | Status |
|---|---|
| Subscription / billing management | Not implemented — no plans, invoices, or usage-based billing exist anywhere in the product |
| Per-tenant storage quota management | Not implemented — Settings shows global storage configuration read-only |
| Backups | Not implemented in the console — database backups are an infrastructure-level concern |
| Super Admin notifications center | Not implemented — the topbar bell icon is decorative (a tenant-side notification API exists, but no super-admin UI) |
| Platform-level user & role management UI | Not implemented — the console has no screen to create additional Super Admins or manage tenant users; university users are managed by each tenant's Admin in the tenant portal |
| Global search (topbar) | Decorative only |
| Two-Factor Authentication | Partially implemented — UI field on the login page only; not enforced |
| Forgot-password flow (admin login page) | Partially implemented — backend endpoints exist; the login-page button is not wired |
| Audit log export | Not implemented — on-screen viewing only |

---

*End of Super Admin User Manual.*
