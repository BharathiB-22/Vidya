# Phase 1.2 — Task D: Primary Login Migration Plan (Institution Email)

**Status:** Architecture / planning only. **No login code is changed in Phase 1.2.**
**Question to answer:** *Should `institution_email` become the primary login identifier in Phase 2?*
**Author:** Engineering · **Date:** 2026-06-16 · **Branch:** `feature/erp-onboarding`

This document accompanies the Phase 1.2 / Task C work, which added (generation
only) `public.tenants.institution_domain`, `users.personal_email`, and
`users.institution_email`. It defines how — and whether — to make the generated
institution email the primary credential later.

---

## 1. Current login flow

### 1.1 Identity model (today)
- Each tenant is an isolated Postgres **schema**. Users live in `<schema>.users`.
- `users.email` is the **login identifier**. It is `UNIQUE` per tenant
  (`UniqueConstraint("email")`) and is whatever was supplied at onboarding —
  typically a personal address (e.g. `john.doe@gmail.com`).
- `users.password_hash` holds the bcrypt/argon hash. Roles: ADMIN/DEAN/FACULTY/STUDENT.

### 1.2 Request path
1. Client sends `POST /auth/login` with `{ email, password }` **plus the
   `X-Tenant-Slug` header**.
2. `get_tenant_context` resolves the slug → `public.tenants` row → `schema_name`
   (`app/core/auth/dependencies.py`). Without a valid slug there is no tenant
   context, so login cannot proceed.
3. `TenantAuthService.login(email, password, tenant_id, schema_name, …)`
   (`app/core/auth/service.py:399`) calls
   `TenantRepository.get_user_by_email(email)` →
   `select(User).where(User.email == email)` **scoped to the tenant schema**.
4. Password is verified against `user.password_hash`. On success a JWT access
   token is minted with claims `{ sub, tenant_id, schema_name, role, email }`,
   plus a refresh token (stored in `<schema>.refresh_tokens` and mirrored in
   `public.refresh_token_index`).
5. All subsequent requests carry the JWT; `schema_name` in the token is matched
   against the tenant resolved from `X-Tenant-Slug` on every call.

### 1.3 Key properties
- **Email is the only username.** There is no separate "username" field; USN /
  employee_id are identity attributes, not credentials.
- **Uniqueness is per tenant**, not global. The same email could exist in two
  different tenant schemas.
- Google SSO (`login_with_google`) also resolves the user by email within a tenant.

---

## 2. Future dual-login flow

The goal is to let users authenticate with **either** their existing personal
email **or** their new institution email during a transition window, then make
institution email primary. Personal email is never deleted.

### 2.1 Resolution change
Replace the single-column lookup with an identifier resolver:

```
get_user_by_login(identifier):
    # case-insensitive, tenant-scoped
    return SELECT * FROM users
           WHERE lower(institution_email) = lower(:id)
              OR lower(email)             = lower(:id)
           LIMIT 1
```

- Both columns are already `UNIQUE` per tenant, so at most one row matches.
- A guard is required so the two columns can never resolve to **different**
  users for the same string (see Risk R3).

### 2.2 Phased rollout (feature-flagged per tenant)
| Stage | Behaviour | Flag |
|-------|-----------|------|
| **S0 – today** | Login by `email` only. | — |
| **S1 – dual accept** | Login accepts `email` OR `institution_email`. JWT `email` claim unchanged. | `login.dual_identifier` |
| **S2 – institution preferred** | UI prefills/labels the institution email; both still accepted. Notifications/displays use institution email. | `login.institution_primary` |
| **S3 – institution primary** | `institution_email` is the canonical username; personal `email` retained for recovery only, still accepted as an alias unless a tenant opts out. | per-tenant setting |

Flags are **per tenant** because institution email coverage (backfill
completeness) differs by tenant. A tenant only advances when 100% of active
users have an `institution_email` (verifiable via the Task C preview:
`to_assign == 0 && no_identifier == 0`).

### 2.3 Token / session impact
- Access-token claims stay keyed on `sub` (user id), so existing sessions remain
  valid across stages. Only the *login resolver* changes, not the token shape.
  (Optionally add an `institution_email` claim in S2 for display.)

---

## 3. Migration plan

**Pre-req (done in Phase 1.2 / Task C):** columns + generation + ADMIN
preview/commit backfill; institution email shown in directories and profiles.

1. **Data readiness (per tenant).**
   - Set `institution_domain` (`PUT /admin/onboarding/institution-domain`).
   - Run `institution-email/preview` → resolve every `SKIP_NO_IDENTIFIER`
     (assign USN / employee_id) and every `CONFLICT`.
   - Run `institution-email/commit`. Target state: `to_assign == 0` and
     `no_identifier == 0` for active users.
2. **Resolver (S1).** Introduce `get_user_by_login` behind `login.dual_identifier`.
   Add a DB-level safety check that `email` and `institution_email` never point
   to two different users for one string. Default flag **off**.
3. **Observability.** Log which identifier was used per login
   (`login_identifier_kind = email | institution`) to measure adoption.
4. **Comms + UI (S2).** Notify users of their institution email (already
   surfaced in profile). Update login screen copy; prefill nothing, but label
   the field "Email or institution email".
5. **Cutover (S3).** When a tenant's institution-email adoption is high and
   stable, flip `login.institution_primary`. Personal email stays accepted as an
   alias (recovery) unless the tenant explicitly disables it.
6. **Backstops.** Password reset, Google SSO, and refresh-token paths must all
   route through the same resolver — audit each before S1.

No destructive migration is required: this is **additive**. The `email` column
is never dropped or overwritten.

---

## 4. Rollback plan

Because every stage is additive and flag-gated, rollback is a flag flip, not a
data restore.

| From | Rollback action | Data impact |
|------|-----------------|-------------|
| S1 → S0 | Turn off `login.dual_identifier`. | None — `email` login still works. |
| S2 → S1 | Turn off `login.institution_primary` (display only). | None. |
| S3 → S2 | Re-enable personal-email login for the tenant. | None — `email` + hash untouched. |

- **Invariant that makes rollback safe:** the personal `email` column and
  `password_hash` are *never* modified by the institution-email feature
  (Task C only writes `institution_email` and backfills `personal_email`). So at
  any stage the original credential still authenticates.
- **Refresh tokens** are keyed on user id, so a rollback does not invalidate
  active sessions.
- **Hard rollback** (remove the columns) = run the down-migrations
  (`0053ten` down, `0014pub` down). Only needed if the whole feature is
  abandoned; not part of normal operations.

---

## 5. Risks

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| R1 | **Incomplete backfill** — some active users have no institution email, locking them out if cutover is premature. | Med | Gate S3 on `to_assign == 0 && no_identifier == 0`; keep personal email as alias. |
| R2 | **Domain typo / change** — wrong `institution_domain` mints wrong addresses; school/program code is locked but domain is not. | Med | Preview-before-commit; domain is editable until cutover; institution emails are unique so a re-mint surfaces conflicts rather than silently overwriting. |
| R3 | **Cross-column collision** — string X is user A's personal email and user B's institution email in the same tenant. | Low | Resolver must reject ambiguous matches; add a one-off validation query before enabling S1. |
| R4 | **Case / whitespace mismatches** — login by `John@…` vs stored `john@…`. | Med | Generation lower-cases; resolver compares `lower()` both sides. |
| R5 | **External integrations** keyed on personal email (SSO, notifications, exports). | Med | Keep personal email retained and accepted; migrate integrations before disabling it. |
| R6 | **User confusion** during dual window. | High | Clear UI labelling (S2), profile shows both, comms campaign. |
| R7 | **Audit/event continuity** — historical `AuditLog` rows reference the personal email. | Low | Audit keys on user id; email is metadata only — no remap needed. |
| R8 | **Per-tenant drift** — some tenants never set a domain. | Med | Feature is opt-in per tenant; tenants without a domain simply stay at S0. |

---

## 6. Recommendation

**Yes — make `institution_email` the primary login in Phase 2, but only as the
final stage of a gated, additive, per-tenant rollout, and never by removing the
personal email.**

Rationale:
- It is the right long-term identity model for an institutional ERP: stable,
  institution-owned, derivable from USN / employee_id, and decoupled from
  personal accounts that change or get lost.
- The Phase 1.2 design already makes this **low-risk**: the change is purely
  additive, the personal credential is never touched, and every stage is a
  reversible feature flag rather than a data migration.

Conditions / guardrails for Phase 2:
1. **Do not cut over (S3) until a tenant's active-user institution-email
   coverage is 100%** (measured via the Task C preview). Until then, dual-accept
   only (S1/S2).
2. **Always keep personal email as a recovery alias** unless a tenant
   deliberately opts out; this preserves the rollback guarantee.
3. **Roll out per tenant**, not globally — coverage and readiness differ.
4. **One resolver** for login, password reset, and SSO — no parallel code paths.
5. Treat the domain as locked-once-issued in spirit (like school/program codes)
   to avoid invalidating minted addresses; allow edits only before first cutover.

**Phase 1.2 scope is correct as "generation only."** Login resolver work,
feature flags, and the S1→S3 rollout belong in Phase 2.
