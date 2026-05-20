## Summary

<!-- One or two sentences describing what this PR does and why. -->

## Type of change

- [ ] Bug fix
- [ ] New feature / module
- [ ] Refactor (no functional change)
- [ ] Infrastructure / config change
- [ ] Security hardening
- [ ] Documentation

## Pre-merge checklist

### Code quality
- [ ] `ruff check backend/` passes locally
- [ ] `cd frontend && npm run typecheck` passes locally
- [ ] No new `:latest` image tags in Helm values files

### Tests
- [ ] `pytest backend/tests/ -x -q` passes locally (xfail deferred tests are acceptable)
- [ ] New code paths have corresponding test coverage
- [ ] No tests removed without justification

### Migrations (if DB changes)
- [ ] `downgrade()` is implemented for every new migration
- [ ] Migration does not contain `op.drop_table` or `op.drop_column` in `upgrade()` without DBA sign-off
- [ ] `infra/scripts/migration-check.sh` passes locally (apply + rollback + re-upgrade)
- [ ] Tenant migration tested with at least one tenant schema
- [ ] Migration is backwards-compatible with the current deployed code (no breaking schema changes)

### Security
- [ ] No secrets or credentials committed
- [ ] No new `ENVIRONMENT` guards bypassed
- [ ] Audit log entries written for all consequential actions
- [ ] Tenant isolation verified — no cross-tenant query paths introduced

### Non-negotiable rules (Vidya)
- [ ] No autonomous grade, penalty, or rejection logic added
- [ ] Every consequential action has a human ratification step at the DB level
- [ ] Audit log remains append-only — no UPDATE/DELETE on `audit_logs`
- [ ] Every query includes `tenant_id` scoping

### Helm / infra (if changed)
- [ ] `bash infra/helm/lint.sh` passes (all three overlays: dev / staging / prod)
- [ ] `values.staging.yaml` and `values.prod.yaml` do not contain `:latest` tags
- [ ] No production credentials in committed files

## Deferred issues referenced (if any)

<!-- List any known deferred issues this PR touches or intentionally leaves open. -->
<!-- Example: H05-DEF-01 (error envelope format) — not addressed in this PR -->

## Reviewer notes

<!-- Anything that needs special attention during review. -->
