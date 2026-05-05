# TASK-001: Auth Module — Implementation Plan

## Status
PLAN_APPROVED

## Phase
0

## Objective
Build `backend/app/core/auth/` — JWT access tokens, refresh token rotation,
OTP-based password reset, RBAC dependencies, and schema-per-tenant isolation.
Exit criteria: a user can register (via admin), log in, refresh tokens, reset
their password, and every unauthenticated or wrong-role request is rejected.
Tenant data is isolated at the PostgreSQL schema level from day one.

---

## Decision Log

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| D-01 | Tenant isolation strategy | **Schema-per-tenant from day one** | PRD requirement; production-grade isolation; avoids migration debt later; sets the pattern for all future modules |
| D-02 | Tenant context on unauthenticated endpoints | `X-Tenant-Slug` header; dependency resolves slug → `schema_name` from `public.tenants` | Works for API clients and dev; subdomain resolution added in tenants session |
| D-03 | Active user check in `get_current_user` | One DB query per request inside the tenant schema | Safer default; no stale role/active-state window |
| D-04 | `password_changed_at` column | YES — on both `users` (tenant schema) and `platform_users` (public schema) | Prevents reset-token reuse without a Redis blocklist |
| D-05 | Rate limiting | `slowapi` middleware inside FastAPI | Self-contained; no gateway dependency for Phase 0 |

---

## Schema Architecture

### Two schema tiers

**`public` schema — platform-level, global**
Contains tables that exist once for the entire platform:
- `public.tenants` — registry of all institutions
- `public.platform_users` — SUPER_ADMIN accounts only
- `public.platform_refresh_tokens` — refresh tokens for platform users
- `public.platform_otp_codes` — OTP codes for platform users

**`tenant_{schema_name}` schema — one per institution**
Created when a tenant is provisioned. Contains:
- `users` — ADMIN, DEAN, FACULTY, STUDENT, BOARD, GUIDE accounts
- `refresh_tokens` — refresh tokens for tenant users
- `otp_codes` — OTP codes for tenant users

No `tenant_id` column on any table inside a tenant schema — the schema itself
provides the isolation. The JWT carries both `tenant_id` (UUID) and `schema_name`
(PostgreSQL schema string) so lookups are direct.

### `search_path` strategy
All DB access uses `SET LOCAL search_path = {schema_name}, public` scoped to the
active transaction. `SET LOCAL` reverts automatically when the transaction ends —
this is safe with PgBouncer in any pool mode. Phase 0 dev has no PgBouncer;
the note is here for when production infra is wired.

### SUPER_ADMIN code path
SUPER_ADMIN accounts live in `public.platform_users`. They use a separate login
endpoint (`POST /platform/auth/login`). Their JWT carries `schema_name = null`
and `role = SUPER_ADMIN`. All `get_current_user` calls branch on this flag.

---

## Folder Structure to Create

```
backend/
├── Dockerfile
├── pyproject.toml
├── alembic.ini                              ← branches on ALEMBIC_TARGET env var
├── alembic/
│   ├── env.py                               ← custom async env, schema-aware
│   ├── public_versions/
│   │   └── 0001_public_create_platform_tables.py
│   └── tenant_versions/
│       └── 0001_tenant_create_auth_tables.py
├── app/
│   ├── __init__.py
│   ├── main.py                              ← FastAPI app factory, routers, middleware
│   ├── config.py                            ← Settings (pydantic-settings, reads .env)
│   ├── database.py                          ← Engine, session factory, search_path helpers
│   ├── db/
│   │   └── migrate.py                       ← CLI helper: run migrations per-tenant or public
│   └── core/
│       └── auth/
│           ├── __init__.py
│           ├── models.py                    ← ORM models: public schema + tenant schema
│           ├── schemas.py                   ← Pydantic request/response schemas
│           ├── security.py                  ← bcrypt, JWT, OTP, token hash — pure Python
│           ├── repository.py                ← DB queries split: PublicRepo + TenantRepo
│           ├── service.py                   ← Business logic (login, refresh, OTP)
│           ├── dependencies.py              ← FastAPI Depends: get_current_user, require_roles
│           ├── router.py                    ← Tenant auth endpoints (/auth/*)
│           ├── platform_router.py           ← SUPER_ADMIN auth endpoints (/platform/auth/*)
│           └── admin_router.py              ← Tenant admin user-management (/admin/*)
└── tests/
    ├── conftest.py                          ← fixtures: test schemas, tenant, users, headers
    ├── core/
    │   └── auth/
    │       ├── test_security.py             ← Unit: bcrypt, JWT, OTP
    │       ├── test_login.py                ← Integration: tenant login flows
    │       ├── test_platform_login.py       ← Integration: SUPER_ADMIN login
    │       ├── test_refresh.py              ← Integration: token rotation + reuse detection
    │       ├── test_logout.py               ← Integration: revocation
    │       ├── test_password_reset.py       ← Integration: OTP flows
    │       ├── test_rbac.py                 ← Integration: role allow/deny
    │       └── test_tenant_isolation.py     ← Integration: cross-schema rejection
```

---

## Implementation Steps

Steps are ordered by dependency. Each step is one sub-agent task.
A step must be complete and reviewed before the next step begins.

---

### STEP-01 — Backend scaffold
**Depends on:** nothing
**Files:** `backend/Dockerfile`, `backend/pyproject.toml`,
`backend/app/__init__.py`, `backend/app/main.py` (skeleton), `backend/app/config.py`

**What to build:**

`pyproject.toml` dependencies:
- `fastapi`, `uvicorn[standard]`
- `sqlalchemy[asyncio]`, `asyncpg`
- `alembic`
- `passlib[bcrypt]`
- `python-jose[cryptography]`
- `pydantic-settings`
- `slowapi`
- `httpx`, `pytest`, `pytest-asyncio` (dev)

`config.py` — `Settings` class via `pydantic-settings`, reads `.env`:
- `DATABASE_URL`, `JWT_SECRET`, `ENVIRONMENT`
- `ACCESS_TOKEN_EXPIRE_MINUTES = 60`
- `REFRESH_TOKEN_EXPIRE_DAYS = 7`
- `OTP_EXPIRE_MINUTES = 10`
- `OTP_MAX_ATTEMPTS = 3`
- `BCRYPT_ROUNDS = 12`

`main.py` — bare FastAPI app, single `GET /healthz` → `{"status": "ok"}`.

`Dockerfile` — Python 3.12-slim, installs from `pyproject.toml`, runs uvicorn.

**Acceptance check:** `docker compose up vidya-api` starts without error.
`GET /healthz` returns 200.

---

### STEP-02 — Database connection
**Depends on:** STEP-01
**Files:** `backend/app/database.py`

**What to build:**

- Async SQLAlchemy engine created from `DATABASE_URL`.
- `AsyncSessionLocal` — base session factory (no search_path set).
- `Base` — declarative base; all models import from here.
- `get_db()` — async generator dependency; yields a plain session against the
  `public` schema. Used by public-schema operations only.
- `get_tenant_db(schema_name: str) -> AsyncGenerator` — async generator that:
  1. Opens a session
  2. Begins a transaction
  3. Executes `SET LOCAL search_path = {schema_name}, public`
  4. Yields the session
  5. Commits / rolls back on exit
  This is the session used by all tenant-scoped operations.

**Safety note on `schema_name` injection:**
The `schema_name` value comes from `public.tenants.schema_name` which was written
at tenant provisioning time by the platform. It is NOT taken from user input.
Before calling `SET LOCAL search_path`, validate that `schema_name` matches the
pattern `^tenant_[a-z0-9_]+$` and reject with 500 if it does not. This prevents
any accidental or injected schema string from reaching the query.

**PgBouncer note (production):**
`SET LOCAL` is transaction-scoped. When the transaction ends and the connection
returns to PgBouncer's pool, the `search_path` reverts to the connection default.
This is safe in both session mode and transaction mode. No PgBouncer reconfiguration
needed.

**Acceptance check:** Engine connects to the Postgres container.
`get_tenant_db("public")` executes `SELECT current_schema()` and returns `public`.

---

### STEP-03 — Auth ORM models
**Depends on:** STEP-02
**Files:** `backend/app/core/auth/models.py`

**What to build — five tables across two schema tiers:**

#### Public schema models (`__table_args__ = {"schema": "public"}`)

**`public.tenants`**
```
id            UUID PK, default uuid4
slug          Text, unique, not null          -- URL-safe identifier, e.g. "mit-csai"
name          Text, not null                  -- display name
schema_name   Text, unique, not null          -- PostgreSQL schema, e.g. "tenant_mit_csai"
is_active     Boolean, default True
created_at    TIMESTAMPTZ, server_default=now()
```
Index: unique on `slug`, unique on `schema_name`.

**`public.platform_users`**
```
id                  UUID PK, default uuid4
email               Text, unique, not null
password_hash       Text, not null
full_name           Text, not null
is_active           Boolean, default True
password_changed_at TIMESTAMPTZ, nullable
created_at          TIMESTAMPTZ, server_default=now()
last_login_at       TIMESTAMPTZ, nullable
```
Role is always SUPER_ADMIN — no role column needed on this table.

**`public.platform_refresh_tokens`**
```
id           UUID PK, default uuid4
user_id      UUID FK → public.platform_users.id, on_delete=CASCADE
token_hash   Text, unique, not null
expires_at   TIMESTAMPTZ, not null
is_revoked   Boolean, default False
replaced_by  UUID FK → public.platform_refresh_tokens.id, nullable
ip_address   Text, nullable
user_agent   Text, nullable
created_at   TIMESTAMPTZ, server_default=now()
```

**`public.platform_otp_codes`**
```
id          UUID PK, default uuid4
user_id     UUID FK → public.platform_users.id, on_delete=CASCADE
otp_hash    Text, not null
purpose     Enum(PASSWORD_RESET), not null
expires_at  TIMESTAMPTZ, not null
is_used     Boolean, default False
attempts    Integer, default 0
created_at  TIMESTAMPTZ, server_default=now()
```

---

#### Tenant schema models (no `schema` in `__table_args__` — resolved via search_path)

**`users`**
```
id                  UUID PK, default uuid4
email               Text, not null
password_hash       Text, not null
role                Enum(ADMIN, DEAN, FACULTY, STUDENT, BOARD, GUIDE), not null
full_name           Text, not null
identifier          Text, nullable          -- roll number or employee ID
is_active           Boolean, default True
password_changed_at TIMESTAMPTZ, nullable
created_at          TIMESTAMPTZ, server_default=now()
last_login_at       TIMESTAMPTZ, nullable
```
Unique constraint: `(email)` — unique within this schema, which is unique per tenant.
Note: NO `tenant_id` column. The schema IS the tenant.

**`refresh_tokens`**
```
id           UUID PK, default uuid4
user_id      UUID FK → users.id, on_delete=CASCADE
token_hash   Text, unique, not null
expires_at   TIMESTAMPTZ, not null
is_revoked   Boolean, default False
replaced_by  UUID FK → refresh_tokens.id, nullable
ip_address   Text, nullable
user_agent   Text, nullable
created_at   TIMESTAMPTZ, server_default=now()
```

**`otp_codes`**
```
id          UUID PK, default uuid4
user_id     UUID FK → users.id, on_delete=CASCADE
otp_hash    Text, not null
purpose     Enum(PASSWORD_RESET), not null
expires_at  TIMESTAMPTZ, not null
is_used     Boolean, default False
attempts    Integer, default 0
created_at  TIMESTAMPTZ, server_default=now()
```

**Acceptance check:** all models import cleanly; no circular imports.

---

### STEP-04 — Alembic setup + migrations
**Depends on:** STEP-03
**Files:** `backend/alembic.ini`, `backend/alembic/env.py`,
`backend/alembic/public_versions/0001_public_create_platform_tables.py`,
`backend/alembic/tenant_versions/0001_tenant_create_auth_tables.py`,
`backend/app/db/migrate.py`

**What to build:**

**`alembic.ini`**
Single ini file. Two `version_locations` configured:
```ini
version_locations = alembic/public_versions alembic/tenant_versions
```

**`alembic/env.py`**
Async-compatible env. Branches on `ALEMBIC_TARGET` environment variable:
- `ALEMBIC_TARGET=public` → sets `search_path = public`, runs migrations from
  `public_versions/` only. Imports all public schema models so autogenerate works.
- `ALEMBIC_TARGET=tenant` → reads `TENANT_SCHEMA` env var, executes
  `SET search_path = {TENANT_SCHEMA}, public`, runs migrations from
  `tenant_versions/` only. Imports all tenant schema models.
- If `ALEMBIC_TARGET` is missing → raise a clear error: do not silently run all.

**`0001_public_create_platform_tables.py`**
Explicit `op.create_table()` calls (not autogenerated) for:
`public.tenants`, `public.platform_users`, `public.platform_refresh_tokens`,
`public.platform_otp_codes`
Includes all constraints and indexes defined in STEP-03.

**`0001_tenant_create_auth_tables.py`**
Explicit `op.create_table()` calls for:
`users`, `refresh_tokens`, `otp_codes`
No schema prefix — applied to whichever schema is active via `search_path`.

**`app/db/migrate.py`** — CLI helper (invoked as `python -m app.db.migrate`):
```
Commands:
  public                  Run public migrations (alembic upgrade head, ALEMBIC_TARGET=public)
  tenant <schema_name>    Run tenant migrations for one schema
  tenant --all            Query public.tenants, run tenant migrations for every active schema
```
Used by the tenant provisioning flow later. For Phase 0, `tenant <schema_name>`
is called manually after a test tenant is inserted into `public.tenants`.

**Run order for initial setup:**
```bash
python -m app.db.migrate public          # create public schema tables once
python -m app.db.migrate tenant test_uni # create tenant schema tables for a test tenant
```

**Acceptance check:**
`python -m app.db.migrate public` runs without error; all four public tables exist.
`python -m app.db.migrate tenant test_uni` creates schema `test_uni` and all three
tenant tables inside it.

---

### STEP-05 — Pydantic schemas
**Depends on:** STEP-03 (uses Role enum)
**Files:** `backend/app/core/auth/schemas.py`

**Schemas to define:**

*Request schemas:*
- `LoginRequest`: `email: EmailStr`, `password: str`
- `PlatformLoginRequest`: same as `LoginRequest` (separate type for clarity)
- `RefreshRequest`: `refresh_token: str`
- `PasswordResetRequestIn`: `email: EmailStr`
- `PasswordResetVerifyIn`: `email: EmailStr`, `otp: str`
- `PasswordResetConfirmIn`: `reset_token: str`, `new_password: str` (min length 8)
- `CreateUserRequest`: `email: EmailStr`, `password: str`, `full_name: str`,
  `role: Role` (must be tenant role — ADMIN/DEAN/FACULTY/STUDENT/BOARD/GUIDE),
  `identifier: str | None`
- `UpdateUserRequest`: `full_name: str | None`, `role: Role | None`,
  `is_active: bool | None` (all optional)

*Response schemas:*
- `TokenResponse`: `access_token: str`, `refresh_token: str`,
  `token_type: str = "bearer"`, `expires_in: int`
- `PasswordResetTokenResponse`: `reset_token: str`
- `UserResponse`: `id: UUID`, `email: str`, `role: Role`, `full_name: str`,
  `identifier: str | None`, `is_active: bool`, `created_at: datetime`
- `MeResponse(UserResponse)`: adds `tenant_id: UUID | None`, `schema_name: str | None`

*Internal schema (not serialized to HTTP):*
- `CurrentUser`: `user_id: UUID`, `tenant_id: UUID | None`, `schema_name: str | None`,
  `role: Role`, `email: str`
  — returned by `get_current_user`; passed through the call stack explicitly.
  `schema_name = None` and `tenant_id = None` when role is SUPER_ADMIN.

*JWT payload structure (documented here, not a Pydantic model):*
```
{
  "sub":         "<user_uuid>",
  "tenant_id":   "<tenant_uuid> or null",
  "schema_name": "<tenant_schema> or null",
  "role":        "<role_string>",
  "email":       "<email>",
  "iat":         <unix_timestamp>,
  "exp":         <unix_timestamp>
}
```

**Acceptance check:** all schemas import cleanly; `LoginRequest` rejects missing fields;
`CreateUserRequest` rejects `role=SUPER_ADMIN` at the validator level.

---

### STEP-06 — Security utilities
**Depends on:** STEP-01 (config only)
**Files:** `backend/app/core/auth/security.py`

**Pure Python — zero FastAPI imports:**

- `hash_password(plain: str) -> str` — bcrypt, rounds from `settings.BCRYPT_ROUNDS`
- `verify_password(plain: str, hashed: str) -> bool`
- `create_access_token(data: dict, expires_delta: timedelta) -> str`
  — HS256 JWT signed with `settings.JWT_SECRET`; merges `data` with `iat`/`exp` claims
- `create_reset_token(user_id: UUID, iat_cutoff: datetime, expires_delta: timedelta) -> str`
  — JWT with `purpose=PASSWORD_RESET` claim; embeds `iat_cutoff` so confirm step
  can reject tokens issued before the last password change
- `decode_token(token: str) -> dict`
  — verifies signature and expiry; raises `jose.JWTError` on any failure
- `generate_refresh_token() -> str`
  — `secrets.token_urlsafe(32)`; opaque, not a JWT
- `hash_token(token: str) -> str`
  — `hashlib.sha256(token.encode()).hexdigest()`; deterministic
- `generate_otp() -> str`
  — `str(secrets.randbelow(1_000_000)).zfill(6)`
- `hash_otp(otp: str) -> str`
  — SHA-256 hex digest
- `verify_otp(plain: str, hashed: str) -> bool`
  — `hmac.compare_digest(hash_otp(plain), hashed)` — constant-time

**Acceptance check:** unit tests in STEP-13 all pass.

---

### STEP-07 — Auth repository
**Depends on:** STEP-03, STEP-06
**Files:** `backend/app/core/auth/repository.py`

**Two repository classes. All methods async.**

---

#### `PublicRepository`
Operates on the `public` schema. Session passed in has `search_path = public`
(default, or `get_db()` from STEP-02). No `tenant_id` filtering needed — these
are global tables.

Methods:
- `get_tenant_by_slug(slug: str, db) -> Tenant | None`
- `get_platform_user_by_email(email: str, db) -> PlatformUser | None`
- `get_platform_user_by_id(user_id: UUID, db) -> PlatformUser | None`
- `update_platform_user(user_id: UUID, updates: dict, db) -> PlatformUser`
- `create_platform_refresh_token(user_id, token_hash, expires_at, ip, user_agent, db) -> PlatformRefreshToken`
- `get_platform_refresh_token_by_hash(token_hash: str, db) -> PlatformRefreshToken | None`
- `revoke_platform_refresh_token(token_id: UUID, replaced_by_id: UUID | None, db) -> None`
- `revoke_all_platform_user_refresh_tokens(user_id: UUID, db) -> None`
- `create_platform_otp(user_id, otp_hash, purpose, expires_at, db) -> PlatformOTPCode`
- `get_active_platform_otp(user_id: UUID, purpose, db) -> PlatformOTPCode | None`
- `increment_platform_otp_attempts(otp_id: UUID, db) -> None`
- `consume_platform_otp(otp_id: UUID, db) -> None`
- `invalidate_prior_platform_otps(user_id: UUID, purpose, db) -> None`

---

#### `TenantRepository`
Operates on the active tenant schema. Session passed in has
`SET LOCAL search_path = {schema_name}, public` already applied.
No `tenant_id` parameter on any method — schema isolation handles it.

Methods:
- `get_user_by_email(email: str, db) -> User | None`
- `get_user_by_id(user_id: UUID, db) -> User | None`
- `create_user(email, password_hash, role, full_name, identifier, db) -> User`
- `update_user(user_id: UUID, updates: dict, db) -> User`
- `list_users(db) -> list[User]`
- `create_refresh_token(user_id, token_hash, expires_at, ip, user_agent, db) -> RefreshToken`
- `get_refresh_token_by_hash(token_hash: str, db) -> RefreshToken | None`
- `revoke_refresh_token(token_id: UUID, replaced_by_id: UUID | None, db) -> None`
- `revoke_all_user_refresh_tokens(user_id: UUID, db) -> None`
- `create_otp(user_id, otp_hash, purpose, expires_at, db) -> OTPCode`
- `get_active_otp(user_id: UUID, purpose, db) -> OTPCode | None`
- `increment_otp_attempts(otp_id: UUID, db) -> None`
- `consume_otp(otp_id: UUID, db) -> None`
- `invalidate_prior_otps(user_id: UUID, purpose, db) -> None`

**Acceptance check:** both repositories instantiate and execute basic queries
against the test DB schemas in conftest smoke tests.

---

### STEP-08 — Auth service
**Depends on:** STEP-05, STEP-06, STEP-07
**Files:** `backend/app/core/auth/service.py`

**Business logic only. No HTTP or FastAPI imports.**
Two service classes mirroring the repository split.

---

#### `PlatformAuthService` — SUPER_ADMIN flows

- `login(email, password, ip, user_agent, db) -> TokenResponse`
  1. `PublicRepository.get_platform_user_by_email` → 401 if not found or inactive
  2. `verify_password` → 401 on mismatch (same message — no enumeration)
  3. `create_access_token` with `{sub, tenant_id=null, schema_name=null, role=SUPER_ADMIN, email}`
  4. `generate_refresh_token` → `hash_token` → `create_platform_refresh_token`
  5. Update `last_login_at`
  6. Return `TokenResponse`

- `refresh_tokens(raw_token, ip, user_agent, db) -> TokenResponse`
  — Same rotation/reuse logic as tenant flow but uses platform tables.

- `logout(raw_token, db) -> None`
- `logout_all(user_id, db) -> None`
- `request_password_reset(email, db) -> None`
- `verify_otp_and_issue_reset_token(email, otp_plain, db) -> PasswordResetTokenResponse`
- `confirm_password_reset(reset_token_str, new_password, db) -> None`

---

#### `TenantAuthService` — tenant user flows

- `login(email, password, tenant_id, schema_name, ip, user_agent, db) -> TokenResponse`
  Note: `db` has `search_path = schema_name` already set by the dependency.
  `tenant_id` and `schema_name` are embedded in the JWT so downstream refresh
  calls can locate the right schema without a `public.tenants` lookup.
  1. `TenantRepository.get_user_by_email` → 401 if not found or inactive
  2. `verify_password` → 401 on mismatch
  3. `create_access_token` with `{sub, tenant_id, schema_name, role, email}`
  4. `generate_refresh_token` → `hash_token` → `create_refresh_token`
  5. Update `last_login_at`
  6. Return `TokenResponse`

- `refresh_tokens(raw_token, ip, user_agent, db) -> TokenResponse`
  Note: `db` is a plain session here (no search_path yet). Service must:
  1. `hash_token` → look up `public.platform_refresh_tokens` first (to detect
     SUPER_ADMIN tokens). Actually: the token carries no schema info itself.
     Service branches based on whether the JWT (access token not passed here)
     tells us the schema. Solution: the client passes ONLY the opaque refresh
     token; the service queries ALL `refresh_tokens` tables to find it.
  **Revised approach:** Store token hash in a unified lookup table.
  Add `public.refresh_token_index`: `(token_hash, schema_name | null, user_id)`.
  On token creation, write to both the tenant `refresh_tokens` table AND
  `public.refresh_token_index`. On refresh, query `public.refresh_token_index`
  first to resolve which schema to use, then load the full token record.
  This eliminates the cross-schema fan-out problem cleanly.

  Revised method:
  1. `hash_token` → query `public.refresh_token_index` → get `schema_name`
  2. If `schema_name` is null → use `PlatformAuthService.refresh_tokens`
  3. Else → open tenant session (`get_tenant_db(schema_name)`) →
     `TenantRepository.get_refresh_token_by_hash`
  4. Reuse detection, expiry check, rotation as before
  5. Return new `TokenResponse`

  **Note on `public.refresh_token_index`:** Add this table to STEP-03 models and
  STEP-04 public migrations. Schema:
  ```
  token_hash   Text PK
  schema_name  Text, nullable     -- null = SUPER_ADMIN (platform)
  user_id      UUID, not null
  created_at   TIMESTAMPTZ
  ```

- `logout(raw_token, db) -> None`
  Same index-lookup approach to find schema, then revoke in correct table.

- `logout_all(user_id, schema_name, db) -> None`
  Revoke all tokens in tenant schema; also delete from index for this user.

- `request_password_reset(email, tenant_id, schema_name, db) -> None`
  Note: `db` has search_path set. Proceeds as before.

- `verify_otp_and_issue_reset_token(email, otp_plain, db) -> PasswordResetTokenResponse`
  `iat_cutoff` embedded in reset token = `user.password_changed_at` or epoch.

- `confirm_password_reset(reset_token_str, new_password, db) -> None`
  `db` here has no search_path yet (reset token in body, no header needed).
  Decode reset token → get `schema_name` from `sub` lookup via index — no,
  the reset token JWT should carry `schema_name` as a claim (added in STEP-06).
  Service opens a tenant session with that schema_name, then proceeds.

- `create_user(payload, db) -> UserResponse`
  Note: `db` has search_path set to the caller's tenant schema.

**Acceptance check:** service methods covered by integration tests in STEP-14.

---

### STEP-09 — FastAPI dependencies
**Depends on:** STEP-06, STEP-07, STEP-08
**Files:** `backend/app/core/auth/dependencies.py`

**Exported callables (public API of the auth module):**

---

`resolve_tenant(x_tenant_slug: str = Header(...), db = Depends(get_db)) -> TenantInfo`
- Queries `public.tenants` for `slug`
- Returns `TenantInfo(id: UUID, schema_name: str, slug: str)`
- 404 if not found; 403 if `is_active = False`
- Validates that `schema_name` matches `^tenant_[a-z0-9_]+$` — safety guard

`get_tenant_db_dep(tenant: TenantInfo = Depends(resolve_tenant)) -> AsyncGenerator`
- Calls `get_tenant_db(tenant.schema_name)` from `database.py`
- Yields the session with `SET LOCAL search_path = {schema_name}, public` applied
- Used on all tenant-user-facing endpoints that are unauthenticated (login, OTP)

`get_current_user(authorization: str = Header(...)) -> CurrentUser`
- Extracts `Bearer` token → 401 if missing
- `decode_token` → 401 on `JWTError`
- Reads `schema_name` claim from JWT payload
- If `schema_name` is null (SUPER_ADMIN path):
  - Opens `get_db()` session (public schema)
  - Queries `public.platform_users` by `sub` claim → 401 if not found or inactive
  - Returns `CurrentUser(user_id, tenant_id=None, schema_name=None, role=SUPER_ADMIN, email)`
- Else (tenant user path):
  - Opens `get_tenant_db(schema_name)` session
  - Queries `users` by `sub` claim → 401 if not found or inactive
  - Returns `CurrentUser(user_id, tenant_id, schema_name, role, email)`

`require_roles(*allowed_roles: Role) -> Callable`
- Factory; returns a dependency that:
  1. Calls `get_current_user`
  2. SUPER_ADMIN bypasses all role checks
  3. Else: 403 if `current_user.role not in allowed_roles`
  4. Returns `current_user`

`require_super_admin`
- Calls `get_current_user`; 403 if not SUPER_ADMIN; returns `current_user`

**Acceptance check:** dependency injection resolves correctly in router-level tests.

---

### STEP-10 — Tenant auth router
**Depends on:** STEP-05, STEP-08, STEP-09
**Files:** `backend/app/core/auth/router.py`

**Routes — prefix `/auth` — all require `X-Tenant-Slug` header on public endpoints:**

| Method | Path | Handler | Auth |
|--------|------|---------|------|
| POST | `/login` | `tenant_login` | `resolve_tenant` + `get_tenant_db_dep`; rate 5/min/IP |
| POST | `/refresh` | `refresh_tokens` | none (token in body); rate 10/min/IP |
| POST | `/logout` | `logout` | `get_current_user` |
| POST | `/logout-all` | `logout_all` | `get_current_user` |
| GET | `/me` | `get_me` | `get_current_user` |
| POST | `/password-reset/request` | `request_reset` | `resolve_tenant` + `get_tenant_db_dep`; rate 3/15min/IP |
| POST | `/password-reset/verify` | `verify_otp` | `resolve_tenant` + `get_tenant_db_dep` |
| POST | `/password-reset/confirm` | `confirm_reset` | none (schema from reset token JWT claim) |

`/refresh`, `/logout`, `/logout-all`, `/password-reset/confirm` do NOT require
`X-Tenant-Slug` — the tenant schema is resolved from the JWT or refresh token index.

**Error envelope:** `{"error": "ERROR_CODE", "message": "..."}` for all errors.
Never distinguish "email not found" vs "wrong password" — both return `INVALID_CREDENTIALS`.

**Acceptance check:** `POST /auth/login` with wrong creds → 401 with correct envelope.

---

### STEP-11 — Platform auth router + Admin router
**Depends on:** STEP-09, STEP-10
**Files:** `backend/app/core/auth/platform_router.py`,
`backend/app/core/auth/admin_router.py`

**`platform_router.py` — prefix `/platform/auth`:**

| Method | Path | Handler | Auth |
|--------|------|---------|------|
| POST | `/login` | `platform_login` | none (public schema path); rate 5/min/IP |
| POST | `/refresh` | `platform_refresh` | none (token in body) |
| POST | `/logout` | `platform_logout` | `require_super_admin` |
| POST | `/logout-all` | `platform_logout_all` | `require_super_admin` |
| GET | `/me` | `platform_me` | `require_super_admin` |
| POST | `/password-reset/request` | `platform_request_reset` | none |
| POST | `/password-reset/verify` | `platform_verify_otp` | none |
| POST | `/password-reset/confirm` | `platform_confirm_reset` | none |

**`admin_router.py` — prefix `/admin`:**

| Method | Path | Handler | Auth |
|--------|------|---------|------|
| POST | `/users` | `create_user` | `require_roles(ADMIN)` + tenant db from JWT |
| GET | `/users` | `list_users` | `require_roles(ADMIN)` + tenant db from JWT |
| PATCH | `/users/{user_id}` | `update_user` | `require_roles(ADMIN)` + tenant db from JWT |

**Tenant scoping on admin routes:**
`current_user.schema_name` from the JWT drives `get_tenant_db()`. An ADMIN
cannot target a different schema — `schema_name` comes exclusively from the JWT,
not from the request body or URL. SUPER_ADMIN uses the `platform_router` for
cross-tenant user management (added in the tenants session).

**Acceptance check:** ADMIN token creates a FACULTY user in the correct schema;
FACULTY token on `POST /admin/users` → 403; cross-schema attempt → 403.

---

### STEP-12 — App wiring
**Depends on:** STEP-10, STEP-11
**Files:** `backend/app/main.py` (replace skeleton)

**What to add:**
- Include `auth_router` at prefix `/auth`, tag `auth`
- Include `platform_router` at prefix `/platform/auth`, tag `platform-auth`
- Include `admin_router` at prefix `/admin`, tag `admin`
- Global exception handlers:
  - `RequestValidationError` → 422 `{"error": "VALIDATION_ERROR", "detail": [...]}`
  - `HTTPException` passthrough (FastAPI default is fine; standardise the body here)
  - Bare `Exception` → 500 `{"error": "INTERNAL_ERROR", "message": "unexpected error"}`
  - Stack traces logged server-side; never sent to client outside `ENVIRONMENT=development`
- `slowapi` limiter on `app.state.limiter`; 429 handler returns `{"error": "RATE_LIMITED"}`
- CORS middleware: all origins in `development`; tightened in production
- Request logger middleware: method, path, status, duration in ms; never logs body

**Acceptance check:** `GET /healthz` → 200; `POST /auth/login` with wrong creds →
401 with `{"error": "INVALID_CREDENTIALS", "message": "..."}`.

---

### STEP-13 — Unit tests
**Depends on:** STEP-06
**Files:** `backend/tests/core/auth/test_security.py`

**Tests (pure Python, no DB, no HTTP):**

`hash_password` / `verify_password`:
- Correct round-trip passes
- Wrong password fails
- Two hashes of the same input are different (bcrypt salt)
- Hash length is consistent

`create_access_token` / `decode_token`:
- Payload round-trips; all claims present
- `exp` is approximately `now + ACCESS_TOKEN_EXPIRE_MINUTES`
- Expired token raises `JWTError`
- Tampered signature raises `JWTError`
- Wrong secret raises `JWTError`

`create_reset_token`:
- Contains `purpose=PASSWORD_RESET` claim
- Contains `iat_cutoff` claim

`generate_refresh_token`:
- Non-empty string; at least 32 chars
- Two calls produce different values

`hash_token`:
- Deterministic: `hash_token(x) == hash_token(x)`
- Different inputs produce different hashes

`generate_otp`:
- Exactly 6 characters; all digits
- Two calls differ (probabilistic; run 10 pairs)

`hash_otp` / `verify_otp`:
- Correct OTP verifies
- Wrong OTP fails
- Function uses `hmac.compare_digest` (assert it does not use `==` directly)

**Acceptance check:** `pytest tests/core/auth/test_security.py -v` — all pass.

---

### STEP-14 — Integration tests
**Depends on:** STEP-12, STEP-13
**Files:** `backend/tests/conftest.py`,
`backend/tests/core/auth/test_login.py`,
`backend/tests/core/auth/test_platform_login.py`,
`backend/tests/core/auth/test_refresh.py`,
`backend/tests/core/auth/test_logout.py`,
`backend/tests/core/auth/test_password_reset.py`,
`backend/tests/core/auth/test_rbac.py`,
`backend/tests/core/auth/test_tenant_isolation.py`

**`conftest.py` — schema-aware fixtures:**

- `event_loop` — single async event loop for all tests
- `db_engine` — async engine connected to the test Postgres instance
  (separate DB: `vidya_test`; or same DB, different schemas)
- `setup_public_schema` — session-scoped fixture that runs `public_versions`
  migrations once (creates `public.tenants`, `public.platform_users`, etc.)
- `setup_tenant_schema(schema_name)` — creates the PostgreSQL schema and runs
  `tenant_versions` migrations; tears down schema (`DROP SCHEMA ... CASCADE`) after
- `test_tenant_a` — inserts a row in `public.tenants` with `schema_name = "test_tenant_a"`;
  calls `setup_tenant_schema("test_tenant_a")`; cleans up after
- `test_tenant_b` — same for a second tenant `"test_tenant_b"`
- `test_platform_user` — inserts a `public.platform_users` row (SUPER_ADMIN)
- `admin_user_a`, `faculty_user_a`, `student_user_a` — users in `test_tenant_a` schema
- `admin_user_b`, `faculty_user_b` — users in `test_tenant_b` schema
- `tenant_headers(user, schema_slug)` — returns
  `{"Authorization": "Bearer <token>", "X-Tenant-Slug": "<slug>"}`
- `platform_headers(platform_user)` — returns `{"Authorization": "Bearer <token>"}`
- `async_client` — `httpx.AsyncClient` wrapping the FastAPI app

---

**`test_login.py`**
- Happy path: correct credentials → `TokenResponse`; `last_login_at` updated in `test_tenant_a` schema
- Wrong password → 401, `INVALID_CREDENTIALS`
- Inactive user → 401
- Unknown email → 401, same error code (no enumeration)
- Missing `X-Tenant-Slug` → 422
- Unknown slug → 404
- Inactive tenant → 403

**`test_platform_login.py`**
- Happy path SUPER_ADMIN login → `TokenResponse` with `schema_name=null` in decoded JWT
- Wrong password → 401
- Platform login does not touch any tenant schema

**`test_refresh.py`**
- Happy path → new token pair; old token revoked in `refresh_token_index` and tenant table
- Reuse detected: present old revoked token → all tokens for user revoked → 401
- Expired token → 401
- Bogus token → 401
- Inactive user → 401
- SUPER_ADMIN refresh → uses platform tables; tenant tables untouched

**`test_logout.py`**
- Logout: token revoked; subsequent refresh → 401
- Logout-all: all tokens for user revoked; tokens of another user in same tenant unaffected
- Logout with already-revoked token → 200 (idempotent)

**`test_password_reset.py`**
- Full happy path: request OTP → verify → confirm → login with new password
- All refresh tokens revoked after reset
- OTP wrong once: `attempts` incremented; OTP still active
- OTP wrong 3 times: OTP consumed; must request new one → 401
- OTP expired → 401
- OTP second use → 401
- Request for non-existent email → 200 (no enumeration; no OTP created)
- Reset token reuse: password changed; second confirm attempt → 401 (iat_cutoff check)

**`test_rbac.py`**
- FACULTY on `GET /auth/me` → 200
- FACULTY on `POST /admin/users` → 403
- ADMIN on `POST /admin/users` → 201
- SUPER_ADMIN on any tenant route (via JWT with null schema) → relevant response
- No token on any protected route → 401
- Expired token → 401
- ADMIN cannot create user with role SUPER_ADMIN → 422 (schema-level rejection)

**`test_tenant_isolation.py`**
- `faculty_user_a` (JWT scoped to `test_tenant_a`) calls `GET /auth/me` → returns tenant A data
- `faculty_user_b` JWT + `X-Tenant-Slug: test_tenant_a_slug` on unauthenticated endpoint →
  token is valid but slug resolves to wrong schema; after login, data is from tenant B
- `admin_user_a` calls `GET /admin/users` → returns only users in `test_tenant_a` schema
- `admin_user_a` calls `GET /admin/users` with a manually forged JWT containing
  `schema_name=test_tenant_b` → 401 (signature invalid; JWT cannot be forged)
- User created via `admin_user_a` exists only in `test_tenant_a` schema;
  querying `test_tenant_b` schema shows no such user

**Acceptance check:** `pytest tests/ -v --cov=app/core/auth` — all pass, coverage ≥ 90%.

---

## Execution Order

```
STEP-01 → STEP-02 → STEP-03 → STEP-04
                    STEP-03 → STEP-05
                    STEP-01 → STEP-06
STEP-03 + STEP-06 → STEP-07
STEP-05 + STEP-06 + STEP-07 → STEP-08
STEP-06 + STEP-07 + STEP-08 → STEP-09
STEP-05 + STEP-08 + STEP-09 → STEP-10
STEP-09 + STEP-10 → STEP-11
STEP-10 + STEP-11 → STEP-12
STEP-06 → STEP-13
STEP-12 + STEP-13 → STEP-14
```

---

## Sub-agent Scope (for superpowers execute)

Each STEP is one sub-agent. Sub-agent receives:
- This plan file
- The specific STEP number it must implement
- The exact files listed under that step
- Instruction: implement only what is listed; do not touch other files

Sub-agents report back:
- Files created/edited
- Any deviation from the plan with reason
- Output of the acceptance check command

---

## Infrastructure Notes

| Concern | Phase 0 (dev) | Production |
|---------|--------------|------------|
| PgBouncer | Not present in Docker Compose | Session mode OR `SET LOCAL` (already used — safe in any mode) |
| Schema creation | Manual: `CREATE SCHEMA {name}` + `migrate.py tenant` | Automated in tenants session (TASK-002) |
| SUPER_ADMIN seed | Manual: insert into `public.platform_users` | Provisioned via deploy script |
| `refresh_token_index` | In `public` schema — created by STEP-04 public migration | Same |

---

## PDCA Log

### Cycle 1

Plan: Complete — brainstorm done, D-01 confirmed schema-per-tenant, full 14-step plan updated.
Approved: YES — 2026-05-05. All 5 decisions locked (D-01 through D-05). Plan reviewed and signed off by Srinivas. Ready for superpowers execute plan.
Do:
Check:
Act:

---

## Checkpoints

Step: STEP-01 Backend scaffold
Status:
Git Commit:
Notes:

Step: STEP-02 Database connection
Status:
Git Commit:
Notes:

Step: STEP-03 Auth ORM models
Status:
Git Commit:
Notes:

Step: STEP-04 Alembic setup + migrations
Status:
Git Commit:
Notes:

Step: STEP-05 Pydantic schemas
Status:
Git Commit:
Notes:

Step: STEP-06 Security utilities
Status:
Git Commit:
Notes:

Step: STEP-07 Auth repository
Status:
Git Commit:
Notes:

Step: STEP-08 Auth service
Status:
Git Commit:
Notes:

Step: STEP-09 FastAPI dependencies
Status:
Git Commit:
Notes:

Step: STEP-10 Tenant auth router
Status:
Git Commit:
Notes:

Step: STEP-11 Platform auth router + Admin router
Status:
Git Commit:
Notes:

Step: STEP-12 App wiring
Status:
Git Commit:
Notes:

Step: STEP-13 Unit tests
Status:
Git Commit:
Notes:

Step: STEP-14 Integration tests
Status:
Git Commit:
Notes:
