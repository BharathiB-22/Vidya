# Student Login Phases — Future Roadmap

Foundation laid in Phase 1.4. No authentication behavior changes yet.

## Current State (Phase 1.4)

- Students log in with their **personal email** (the `email` column on `users`).
- Institution email (`institution_email`) is generated and stored but **not used for login**.
- `users.must_change_password` column exists (migration 0014ten), default `false`.
- `tenants.default_student_password_pattern` column exists (migration 0015pub), stores the
  tenant-configured pattern (e.g. `Dsu@2026`). Not yet consumed at login.

## Phase A — Personal Email Login (current)

Students authenticate with their personal email and the default password set during onboarding.
No changes from the current system.

## Phase B — Personal Email OR Institution Email

Allow login via either `users.email` or `users.institution_email`.
Auth flow must check both columns when resolving identity.
Requires: institution email to be unique across the tenant (already enforced by the
`uq_users_institution_email` unique constraint from migration 0053ten).

## Phase C — Institution Email as Primary Login

Institution email (`institution_email`) becomes the primary credential.
Personal email becomes a fallback or recovery path only.
Requires: all students to have an institution email assigned (use the backfill endpoint
`POST /admin/institution-email/commit` before enabling).

## Phase D — Force Password Reset on First Login

When `users.must_change_password = true`, redirect student to a password-change screen
before granting access to the application.
Tenant default password pattern (`tenants.default_student_password_pattern`) is used to
set the initial bulk password; students must change it on first login.
Requires: auth middleware to check `must_change_password` after token issuance and return
a 403 with code `MUST_CHANGE_PASSWORD` that the frontend intercepts.

## Implementation Notes

- Never change `must_change_password` from the UI autonomously — a human ratification step
  (ADMIN toggle or scheduled migration) is required per the Vidya non-negotiable rules.
- Audit every login-path change via the AuditLog (model, prompt_hash, output_summary,
  confidence_score as applicable).
- Multi-tenant isolation applies: password policy is per-tenant via
  `tenants.default_student_password_pattern`.
