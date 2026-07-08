# VIDYA AI — Super Admin Module: Functional Report

**Product:** VIDYA AI Enterprise Academic Platform (University ERP SaaS)
**Module:** Super Admin Platform Console
**Vendor:** SherpaVector Pvt. Ltd.
**Audience:** Managers, Clients, Product Reviewers, Auditors
**Document Type:** Functional & Architectural Report
**Version:** 1.0 · July 2026

> This report describes functionality that exists in the current codebase. Items that are incomplete are explicitly marked **Partially Implemented**; items that do not exist are listed under Future Scope.

---

## 1. Module Overview

The Super Admin module is the platform-owner control plane of VIDYA AI, a multi-tenant SaaS ERP for universities. It is delivered as a dedicated web console (`/admin/*` routes) backed by platform-scoped REST APIs, entirely separate from the tenant-facing university application.

Its single organizing concept is the **tenant**: one university = one tenant = one isolated PostgreSQL schema. The Super Admin module owns the tenant registry and lifecycle, plus the platform-wide operational surfaces that no individual university should see: cross-tenant audit logs, infrastructure health, schema migration state, AI provider status, and platform branding.

[Screenshot – Platform Console Dashboard]

## 2. Objectives

1. **Tenant provisioning in minutes** — a single form creates an isolated schema, a tenant record with branding, and a seeded university admin with an enforced first-login password change.
2. **Safe lifecycle management** — reversible suspend/archive states, soft delete with restore, and a compliance-preserving permanent delete; destructive actions gated by type-to-confirm slug verification enforced server-side.
3. **Operational transparency** — real-time health, queue, and AI diagnostics; per-tenant migration status with one-click remediation.
4. **Compliance by construction** — an append-only audit log spanning all tenants, with every consequential Super Admin action recorded (actor, IP, user agent, metadata).
5. **Strict tenant isolation** — no data path crosses tenant schemas; the platform layer sees registry metadata, not tenant academic data.

## 3. Architecture

| Layer | Technology | Super Admin components |
|---|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind | `AdminShell` layout, 12 console pages under `frontend/src/pages/admin/`, dedicated `AdminAuthGuard` and admin API client |
| Backend | Python 3.12, FastAPI (async) | `tenants` router/service/repository, `platform/auth` router, `platform/audit-logs` router, `platform/health` router |
| Data | PostgreSQL 16 | Public schema: tenant registry, platform users, audit_logs, platform branding. One schema per tenant for university data |
| Async | Celery + Redis | Two queues: `celery` (light) and `celery-heavy` (AI); monitored from the console |
| Storage | MinIO / AWS S3 | Global object store; configuration surfaced read-only in Settings |
| Vector DB | Qdrant | Health-checked from the console |
| AI | Gemini / Groq / DeepSeek | Provider status and fallback order surfaced in Settings and Health |

**Separation of authentication domains.** The Super Admin portal has its own login endpoint (`/platform/auth/login`), its own token storage key in the browser, its own refresh/logout endpoints, and a distinct set of audit event types (`PLATFORM_*`). A tenant user token cannot access platform APIs; every platform endpoint requires the `require_super_admin` dependency.

## 4. Responsibilities

**In scope for Super Admin:** tenant registry and lifecycle; platform monitoring and diagnostics; cross-tenant audit review; tenant schema migration management; platform branding; own-account security.

**Explicitly out of scope:** university-internal administration (students, faculty, programs, exams, users, roles inside a tenant) — these belong to the tenant's own Admin role in the tenant portal. The Super Admin console never renders tenant academic data.

## 5. Complete Feature List

| # | Feature | Status |
|---|---|---|
| 1 | Email/password login with rate limiting (5/min) | Implemented |
| 2 | Google Sign-In (OAuth credential) login | Implemented (requires client-ID configuration) |
| 3 | Two-Factor Authentication | **Partially Implemented** — login-page UI field only; not enforced by backend |
| 4 | Password reset (request/verify/confirm APIs) | **Partially Implemented** — backend endpoints exist; not wired into the admin login page UI |
| 5 | Token refresh, logout, logout-all with reuse detection events | Implemented |
| 6 | Dashboard (KPIs, recent tenants, quick actions, health banner) | Implemented |
| 7 | Tenant list with search, filters, sort, stat cards | Implemented |
| 8 | Tenant creation (schema provisioning + admin seeding + branding) | Implemented |
| 9 | Provisioning failure recovery (retry on FAILED tenants) | Implemented |
| 10 | Tenant detail view with live polling during provisioning | Implemented |
| 11 | Tenant edit (name, contact email, logo URL, brand colors) | Implemented |
| 12 | Deactivate / Activate (suspend/resume) | Implemented |
| 13 | Archive / Reactivate | Implemented |
| 14 | Soft delete with slug confirmation | Implemented |
| 15 | Deleted-tenants view with Restore | Implemented |
| 16 | Permanent delete (flag-based, audit-preserving, slug-confirmed) | Implemented |
| 17 | Platform monitoring (services, tenant stats, jobs, AI, events; 30s auto-refresh) | Implemented |
| 18 | Platform health diagnostics (system, workers, queues, AI) | Implemented |
| 19 | Cross-tenant audit log browser (filters, pagination, KPIs, live recent feed) | Implemented |
| 20 | Tenant migration status board + per-tenant retry | Implemented |
| 21 | Platform branding editor with live preview | Implemented |
| 22 | Read-only platform settings (profile, AI, storage, security) | Implemented |
| 23 | Super Admin profile (name/avatar), email change, password change with session revocation, session count | Implemented |
| 24 | Subscription/billing management | Not implemented |
| 25 | Per-tenant storage quotas / backups UI / notifications center / platform user-role management UI / audit export | Not implemented |

## 6. Functional Workflow

### 6.1 University Onboarding Flow

[Screenshot – Provision University Form]

```
Super Admin fills form
        │
        ▼
Validate: name 3–100 chars · unique slug derived from name ·
password complexity (8+ chars, upper, lower, digit, special) ·
hex color formats
        │
        ▼
Create tenant record (status = PROVISIONING)
        │
        ▼
Create isolated PostgreSQL schema  ─── failure ──► status = FAILED
        │                                              │
        ▼                                              ▼
Seed university admin account              Super Admin clicks
(first-login password change enforced)     "Retry provisioning"
        │                                  (re-runs on same record)
        ▼
status = ACTIVE · audit event TENANT_PROVISIONED
        │
        ▼
Success screen: slug (Institution ID), admin email,
temporary password — copyable, shown once
```

### 6.2 Tenant Lifecycle State Model

```
PROVISIONING ──► ACTIVE ◄────────► INACTIVE (suspend/resume)
      │            │  ▲                │
      ▼            │  └── reactivate ──┤
    FAILED         ▼                   ▼
  (retry ►      ARCHIVED ◄─────────────┘
  ACTIVE)          │
                   ▼
   ACTIVE/INACTIVE/ARCHIVED ──soft delete──► DELETED
                                               │  ▲
                              restore (to INACTIVE)│
                                               ▼  │
                                    PERMANENTLY_DELETED (terminal)
```

Guard rails encoded in the API: `PROVISIONING`, `FAILED`, `DELETED`, and `PERMANENTLY_DELETED` cannot be set through the generic update endpoint — only through their dedicated flows. Restore is refused for permanently deleted tenants. Permanent delete is only possible from the `DELETED` state.

## 7. Business Logic

- **Slug and schema derivation.** The Institution ID (slug) and schema name are derived deterministically from the university name at creation; the slug is immutable thereafter and doubles as (a) the login institution identifier for tenant users and (b) the confirmation token for destructive actions.
- **Duplicate protection.** Creation is rejected if the derived slug already exists.
- **Password policy.** Seeded admin passwords must contain uppercase, lowercase, digit, and special characters (validated in both UI and API); the admin is forced to change it at first login.
- **Confirmation symmetry.** Soft delete and permanent delete both require the exact slug typed by the operator; the server re-validates independently of the UI.
- **Delta updates.** Edit dialogs send only changed fields; no-op saves are short-circuited client-side.
- **Restore is conservative.** A restored tenant returns as `INACTIVE`, requiring a deliberate reactivation before users regain access.

## 8. Security Model

| Control | Implementation |
|---|---|
| Authentication | JWT access + refresh tokens; platform tokens separate from tenant tokens; refresh-token reuse detection (audited as `PLATFORM_TOKEN_REUSE_DETECTED`) |
| Authorization | Every platform endpoint depends on `require_super_admin`; frontend routes wrapped in `AdminAuthGuard` |
| Rate limiting | 5/minute on login and Google login |
| Session hygiene | Password change terminates all other sessions; logout-all endpoint; active session count visible in profile |
| Secrets handling | Settings and Health APIs return only booleans/model names for AI keys — never key material; SMTP/S3 credentials never surfaced |
| Destructive-action friction | Type-to-confirm slug verification, enforced server-side; confirmation dialogs on all lifecycle changes |
| Forensics | Actor user ID, IP address, and user agent captured on every tenant lifecycle API call and written to the audit log |
| Token lifetimes | Access-token expiry (minutes) and refresh-token expiry (days) are configuration-driven and displayed in Settings |

## 9. Role Permissions

The platform layer has effectively two audiences:

| Capability | Super Admin | Tenant users (any role) |
|---|---|---|
| Platform console access (`/admin/*`) | ✔ | ✖ |
| Tenant CRUD & lifecycle | ✔ | ✖ |
| Cross-tenant audit logs | ✔ | ✖ (tenants see only their own audit scope via a separate tenant endpoint) |
| Platform health/monitoring/migrations | ✔ | ✖ |
| Platform branding | ✔ | ✖ |
| University-internal administration | ✖ (by design) | ✔ per tenant RBAC (ADMIN, DEAN, FACULTY, STUDENT, BOARD, etc.) |

There is currently **no UI to create additional Super Admin accounts or delegate sub-roles at the platform level**; the console assumes a small, trusted operator group.

## 10. Tenant Isolation

- **Schema-per-tenant**: every university's data lives in its own PostgreSQL schema; the public schema holds only the registry, platform users, branding, and audit log.
- The tenant creation screen states the guarantee shown to operators: *"Each university gets a fully isolated schema. No data is ever shared across tenants."*
- No Super Admin screen queries across tenant schemas; the console consumes registry metadata, aggregate counters, and the shared audit table only.
- Suspension (`INACTIVE`), archive, and delete flags gate login at the platform level without touching tenant data.
- Migration management operates per-schema: each tenant's Alembic revision is tracked and can be advanced individually.

## 11. SaaS Design

- **Single application, many isolated tenants** — horizontal onboarding without redeployment; provisioning is an online operation.
- **Central control plane** — the console is the one place where fleet-wide state (health, migrations, audit) is visible.
- **Environment-aware** — Settings surfaces an environment badge (Development/Staging/Production) and build version for deployment verification.
- **Async-first** — AI generation and heavy work run on Celery queues, never on the API thread; queue depth and worker liveness are first-class console metrics.
- **Provider-pluggable AI** — three LLM providers with a configured fallback order (Gemini → Groq → DeepSeek), toggled by environment variables.

## 12. Branding Flow

Two independent branding layers:

1. **Platform branding** (Super Admin → Branding page): platform name, company name, support email/phone, logo URL, favicon URL, primary and accent colors. Stored in the public schema, edited with a live preview, applied to the Super Admin login page, console header, tenant portal login pages, and email templates (where configured).

   [Screenshot – Platform Branding Editor with Live Preview]

2. **Tenant branding** (per university): logo URL, primary and secondary colors, captured at tenant creation or via tenant edit, validated as hex codes, and used to theme that university's portal. Universities can further manage their branding from their own Institution Settings.

## 13. Subscription Flow

**Not implemented.** The current system has no subscription plans, billing, invoicing, metering, or plan-based feature gating. Commercial arrangements are handled outside the product. The tenant lifecycle states (`ACTIVE`/`INACTIVE`/`ARCHIVED`) are the only levers available to operationally enforce a commercial decision (e.g., suspending a non-paying institution). See Future Scope.

## 14. Storage Management

- Object storage is a **global, platform-level service** (MinIO in development, AWS S3 in production), exposed read-only in Settings: provider, endpoint, bucket, region, TLS flag, and max upload size.
- Health checks verify storage connectivity on the Monitoring and Health pages.
- Tenant file assets are managed inside tenant portals via a storage API with presigned upload/download URLs; asset events (`STORAGE_ASSET_CREATED/DOWNLOADED/DELETED`) appear in the cross-tenant audit log.
- **Not implemented:** per-tenant storage quotas, usage dashboards, or storage administration actions in the Super Admin console.

## 15. Audit System

[Screenshot – Audit Logs Browser]

- **Append-only by policy and by code**: the application contains no UPDATE or DELETE path for `audit_logs`; records survive tenant permanent deletion ("preserved for compliance" is asserted in the deletion UX itself).
- **Coverage**: platform auth events (`PLATFORM_LOGIN_SUCCESS/FAILURE`, logout, token refresh, token-reuse detection, password reset), full tenant lifecycle (`TENANT_PROVISIONED/UPDATED/DEACTIVATED/ARCHIVED/REACTIVATED/DELETED/RESTORED/PERMANENTLY_DELETED`), and the entire catalog of tenant-side domain events (users, programs, syllabi, course kits, learning packages, labs, research, exams, scripts, bell curve, SIS, storage).
- **Record content**: event type, timestamp, actor user ID and role, tenant/schema, target entity and ID, IP, user agent, and structured metadata.
- **Console access**: KPI aggregates (total / tenant / login / AI / security events), filterable browser (tenant, event type, date range) paginated at 50/page with a server-side cap of 200, and a 20-event live recent feed.
- **Limitations**: read-only viewing; no export, alerting, or retention policy UI.

## 16. High-Level Process Flow

```
                    ┌────────────────────────────┐
                    │  Super Admin Console (SPA) │
                    │  /admin/* · AdminAuthGuard │
                    └──────────────┬─────────────┘
                                   │ JWT (platform token)
        ┌──────────────────────────┼───────────────────────────┐
        ▼                          ▼                           ▼
 /platform/auth/*            /tenants/*                /platform/audit-logs
 login · google · refresh    create · list · get       stats · list (filtered,
 logout(-all) · me ·         update · delete ·         paginated)
 email · password ·          retry · restore ·
 sessions · branding ·       permanent · migrations    /platform/health
 password-reset                    │                   system · workers ·
        │                          │                   queue · ai diagnostics
        │                          ▼
        │                Tenant Service ──► Schema provisioning (per-tenant
        │                          │        PostgreSQL schema + admin seed)
        │                          ▼
        └────────────────► AuditService ──► audit_logs (append-only)
                                   │
                                   ▼
                       PostgreSQL public schema
              (tenant registry · platform users · branding)
```

## 17. Benefits

- **Fast, repeatable onboarding** — a university goes from form to live, isolated environment in one operation, with credentials handed over on a copy-safe success screen.
- **Reversibility as default** — suspend, archive, and soft delete are all recoverable; the only irreversible action requires two prior states and a typed confirmation.
- **Audit-grade accountability** — every consequential platform action is attributable (who, when, from where) in an append-only store, supporting compliance reviews out of the box.
- **Operational self-sufficiency** — health, queue, worker, migration, and AI diagnostics mean most incidents can be triaged without database access.
- **Low blast radius** — strict isolation and the platform/tenant privilege split mean a tenant-side compromise cannot reach the control plane, and control-plane screens cannot leak academic data.

## 18. Future Scope

Reasonable next increments, none of which exist today:

1. **Subscription & billing** — plans, seat/usage metering, invoices, and plan-gated features tied to tenant lifecycle.
2. **Platform user management** — multiple Super Admin accounts, delegated operator roles, and enforced 2FA (completing the existing login-page placeholder).
3. **Notifications center** — activating the console bell with alerts for failed provisioning, failed migrations, and unhealthy services.
4. **Audit export & retention** — CSV/JSON export, retention policies, and anomaly alerting on security events.
5. **Storage governance** — per-tenant usage metrics and quotas.
6. **Backup & restore tooling** — surfacing infrastructure backup state per tenant schema.
7. **Wired forgot-password flow** on the admin login page (backend endpoints already exist).
8. **Global console search** — activating the decorative topbar search across tenants and events.

---

*End of Super Admin Functional Report.*
