# TASK-003: Audit Log Module — Implementation Plan

## Status
PENDING APPROVAL

## Phase
0

## Objective
Build `backend/app/core/audit_log/` — an immutable, append-only audit logging system
that records every security-relevant and tenant-management event across the platform.
Exit criteria: every auth and tenant provisioning event writes a row to
`public.audit_logs`; SUPER_ADMIN can query all logs with filters; tenant ADMIN
can query only their own tenant logs; no update/delete APIs exist.

---

## Decision Log

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| D-01 | Storage location | **Single `public.audit_logs` table with `tenant_id` column** | PRD data model; SUPER_ADMIN cross-tenant investigation is natural; simpler than per-tenant schema fan-out |
| D-02 | Write mechanism | **Direct `await AuditService.log(...)` in service layer** | Reliable; audit logs must not be silently dropped; INSERT latency is acceptable |
| D-03 | Transaction coupling | **Separate DB session per audit write (own `AsyncSessionLocal()`)** | Business transaction rollback must not suppress audit entries; failure audit entries (wrong password, token reuse) have no business transaction to couple to |
| D-04 | Integration style | **Explicit `await AuditService.log(...)` calls inside existing service methods** | Predictable, traceable, no decorator magic; services have full business context |
| D-05 | Folder name | **`backend/app/core/audit_log/`** (underscore) | Python packages cannot contain hyphens; CLAUDE.md logical name `audit-log` maps to underscore on disk |
| D-06 | AI fields | **Store all extra context in `metadata` JSONB for Phase 0** | `ai_model`, `confidence_score`, `human_decision` are Phase 1/2 concerns; JSONB keeps the schema stable and extensible |
| OQ-01 | Audit write failure | **Swallow + structured error log** | Business operation must not fail because the audit DB write failed; write failure is logged to stderr with structlog/logging |
| OQ-02 | Failed auth events | **Yes, log them** — `actor_user_id=None` when user unknown; attempted email in `metadata` | Required for security investigation and brute-force detection |
| OQ-03 | IP / user-agent | **Explicitly passed from router → service → AuditService.log()** | Clean call chain; router owns `Request`, service owns business logic |

---

## Schema Architecture

### `public.audit_logs` — single shared table, all events

```
id              UUID PK, default uuid4
event_type      TEXT NOT NULL           -- AuditEventType string value
actor_user_id   UUID nullable           -- null for system events or unknown-user auth failures
actor_role      TEXT nullable           -- role string at time of event
tenant_id       UUID nullable FK → public.tenants.id ON DELETE SET NULL
schema_name     TEXT nullable           -- convenience copy, join-free queries
target_entity   TEXT nullable           -- "User", "Tenant", "RefreshToken"
target_id       TEXT nullable           -- UUID or slug as string
metadata        JSONB nullable          -- event-specific context; never PII passwords
ip_address      TEXT nullable
user_agent      TEXT nullable
created_at      TIMESTAMPTZ NOT NULL, server_default=now()
```

**Immutability rules:**
- No UPDATE or DELETE SQL may ever touch this table
- Repository exposes only `create()` and read methods
- No update/delete endpoints in the router
- `created_at` uses DB `now()` — not Python `datetime.now()` — so clock skew cannot forge timestamps

**Indexes:**
```sql
CREATE INDEX ix_audit_logs_tenant_created  ON public.audit_logs (tenant_id, created_at DESC);
CREATE INDEX ix_audit_logs_event_created   ON public.audit_logs (event_type, created_at DESC);
CREATE INDEX ix_audit_logs_actor_created   ON public.audit_logs (actor_user_id, created_at DESC);
CREATE INDEX ix_audit_logs_created         ON public.audit_logs (created_at DESC);
```

---

## AuditEventType Catalogue

```python
class AuditEventType(str, enum.Enum):
    # Tenant auth flows
    AUTH_LOGIN_SUCCESS               = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILURE               = "AUTH_LOGIN_FAILURE"
    AUTH_LOGOUT                      = "AUTH_LOGOUT"
    AUTH_LOGOUT_ALL                  = "AUTH_LOGOUT_ALL"
    AUTH_TOKEN_REFRESH               = "AUTH_TOKEN_REFRESH"
    AUTH_TOKEN_REUSE_DETECTED        = "AUTH_TOKEN_REUSE_DETECTED"
    AUTH_PASSWORD_RESET_REQUESTED    = "AUTH_PASSWORD_RESET_REQUESTED"
    AUTH_PASSWORD_RESET_OTP_FAILED   = "AUTH_PASSWORD_RESET_OTP_FAILED"
    AUTH_PASSWORD_RESET_VERIFIED     = "AUTH_PASSWORD_RESET_VERIFIED"
    AUTH_PASSWORD_RESET_COMPLETED    = "AUTH_PASSWORD_RESET_COMPLETED"

    # Platform auth flows (SUPER_ADMIN)
    PLATFORM_LOGIN_SUCCESS           = "PLATFORM_LOGIN_SUCCESS"
    PLATFORM_LOGIN_FAILURE           = "PLATFORM_LOGIN_FAILURE"
    PLATFORM_LOGOUT                  = "PLATFORM_LOGOUT"
    PLATFORM_LOGOUT_ALL              = "PLATFORM_LOGOUT_ALL"
    PLATFORM_TOKEN_REFRESH           = "PLATFORM_TOKEN_REFRESH"
    PLATFORM_TOKEN_REUSE_DETECTED    = "PLATFORM_TOKEN_REUSE_DETECTED"
    PLATFORM_PASSWORD_RESET_REQUESTED  = "PLATFORM_PASSWORD_RESET_REQUESTED"
    PLATFORM_PASSWORD_RESET_OTP_FAILED = "PLATFORM_PASSWORD_RESET_OTP_FAILED"
    PLATFORM_PASSWORD_RESET_VERIFIED   = "PLATFORM_PASSWORD_RESET_VERIFIED"
    PLATFORM_PASSWORD_RESET_COMPLETED  = "PLATFORM_PASSWORD_RESET_COMPLETED"

    # User management (tenant-scoped)
    USER_CREATED                     = "USER_CREATED"
    USER_UPDATED                     = "USER_UPDATED"
    USER_DEACTIVATED                 = "USER_DEACTIVATED"
    USER_ROLE_CHANGED                = "USER_ROLE_CHANGED"

    # Tenant management (platform-level)
    TENANT_PROVISIONED               = "TENANT_PROVISIONED"
    TENANT_UPDATED                   = "TENANT_UPDATED"
    TENANT_DEACTIVATED               = "TENANT_DEACTIVATED"
```

---

## Folder Structure to Create

```
backend/app/core/audit_log/
├── __init__.py
├── models.py        ← AuditLog ORM model + AuditEventType enum
├── schemas.py       ← AuditLogEntry (response), AuditLogListResponse
├── repository.py    ← AuditLogRepository: create + read only
├── service.py       ← AuditService.log() + AuditService.query()
└── router.py        ← GET /audit-logs (RBAC + pagination + filtering)

backend/alembic/public_versions/
└── 0003_public_create_audit_logs.py   ← new migration

backend/tests/core/audit_log/
├── __init__.py
└── test_audit_log.py
```

---

## Implementation Steps

Steps are ordered by dependency. Each step is one sub-agent task.
A step must be complete and reviewed before the next step begins.

---

### STEP-01 — AuditLog ORM model + Alembic migration
**Depends on:** TASK-001 STEP-04 (public migration infrastructure)
**Files:**
- `backend/app/core/audit_log/__init__.py`
- `backend/app/core/audit_log/models.py`
- `backend/alembic/public_versions/0003_public_create_audit_logs.py`

**What to build:**

**`audit_log/__init__.py`** — empty file.

**`audit_log/models.py`:**

```python
import enum
import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.database import Base

class AuditEventType(str, enum.Enum):
    # (all event types listed in the catalogue above)
    ...

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_created",  "tenant_id",     "created_at"),
        Index("ix_audit_logs_event_created",   "event_type",    "created_at"),
        Index("ix_audit_logs_actor_created",   "actor_user_id", "created_at"),
        Index("ix_audit_logs_created",         "created_at"),
        {"schema": "public"},
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type     = Column(String, nullable=False)
    actor_user_id  = Column(UUID(as_uuid=True), nullable=True)
    actor_role     = Column(String, nullable=True)
    tenant_id      = Column(UUID(as_uuid=True),
                        ForeignKey("public.tenants.id", ondelete="SET NULL"),
                        nullable=True)
    schema_name    = Column(String, nullable=True)
    target_entity  = Column(String, nullable=True)
    target_id      = Column(String, nullable=True)
    metadata_      = Column("metadata", JSONB, nullable=True)
    ip_address     = Column(String, nullable=True)
    user_agent     = Column(String, nullable=True)
    created_at     = Column(DateTime(timezone=True),
                        nullable=False, server_default=text("now()"))
```

Note on `metadata_`: SQLAlchemy reserves `metadata` as a class attribute name. Use
`metadata_` as the Python attribute but map it to the `"metadata"` column name via the
positional string argument to `Column`.

**`0003_public_create_audit_logs.py`:**

Explicit `op.create_table()` (no autogenerate). Use `schema="public"`. Include:
- All columns from the model above
- FK constraint on `tenant_id` → `public.tenants.id` with `ondelete="SET NULL"`
- All four indexes defined in the table args

The `down` migration must `op.drop_table("audit_logs", schema="public")` and drop the indexes.

**Acceptance check:**
```
python -m app.db.migrate public
```
`public.audit_logs` table exists with all columns and indexes.
`python -c "from app.core.audit_log.models import AuditLog, AuditEventType; print('ok')"` passes.

---

### STEP-02 — Repository
**Depends on:** STEP-01
**Files:** `backend/app/core/audit_log/repository.py`

**What to build:**

```python
class AuditLogRepository:

    @staticmethod
    async def create(
        event_type: str,
        *,
        actor_user_id: UUID | None,
        actor_role: str | None,
        tenant_id: UUID | None,
        schema_name: str | None,
        target_entity: str | None,
        target_id: str | None,
        metadata: dict | None,
        ip_address: str | None,
        user_agent: str | None,
        db: AsyncSession,
    ) -> AuditLog:
        entry = AuditLog(
            event_type=event_type,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity=target_entity,
            target_id=target_id,
            metadata_=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(entry)
        await db.flush()
        await db.refresh(entry)
        return entry

    @staticmethod
    async def list(
        *,
        tenant_id: UUID | None = None,
        restrict_to_tenant: bool = False,
        event_type: str | None = None,
        actor_user_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[AuditLog]:
        ...

    @staticmethod
    async def count(
        *,
        tenant_id: UUID | None = None,
        restrict_to_tenant: bool = False,
        event_type: str | None = None,
        actor_user_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        db: AsyncSession,
    ) -> int:
        ...
```

**`restrict_to_tenant` flag:**
- When `True` AND `tenant_id` is not None: `WHERE tenant_id = :tenant_id`
  This is the ADMIN path — forces scope to exactly one tenant.
- When `False` AND `tenant_id` is not None: `WHERE tenant_id = :tenant_id`
  This is SUPER_ADMIN filtering by a specific tenant.
- When `False` AND `tenant_id` is None: no tenant_id filter — all logs visible.
  This is SUPER_ADMIN querying everything.

The `list()` and `count()` methods share the same filter-building logic (extract to a
`_build_filters()` private function returning a list of SQLAlchemy clauses).

**Immutability contract:** This class has no `update()` or `delete()` method.
Any future attempt to add one must be blocked at code review.

**Acceptance check:** `python -c "from app.core.audit_log.repository import AuditLogRepository; print('ok')"` passes.

---

### STEP-03 — Pydantic schemas
**Depends on:** STEP-01
**Files:** `backend/app/core/audit_log/schemas.py`

**What to build:**

```python
class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:            UUID
    event_type:    str
    actor_user_id: UUID | None
    actor_role:    str | None
    tenant_id:     UUID | None
    schema_name:   str | None
    target_entity: str | None
    target_id:     str | None
    metadata:      dict | None   # maps from metadata_ via alias
    ip_address:    str | None
    user_agent:    str | None
    created_at:    datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def _alias_metadata(cls, v, info):
        # Pydantic sees "metadata_" from the ORM; expose as "metadata" in JSON
        return v
```

Implementation note: because the ORM attribute is `metadata_` but the column and JSON
key should be `metadata`, use `model_validator(mode="before")` or an alias to remap.
Simplest approach: declare `metadata: dict | None = Field(None, alias="metadata_")`
with `model_config = ConfigDict(from_attributes=True, populate_by_name=True)`.

```python
class AuditLogListResponse(BaseModel):
    total:     int
    page:      int
    page_size: int
    items:     list[AuditLogEntry]
```

**Acceptance check:** `python -c "from app.core.audit_log.schemas import AuditLogEntry, AuditLogListResponse; print('ok')"` passes.

---

### STEP-04 — AuditService
**Depends on:** STEP-02, STEP-03
**Files:** `backend/app/core/audit_log/service.py`

**What to build:**

```python
import logging
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.repository import AuditLogRepository
from app.core.audit_log.schemas import AuditLogEntry, AuditLogListResponse

logger = logging.getLogger("vidya.audit")


class AuditService:

    @staticmethod
    async def log(
        event_type: AuditEventType,
        *,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
        target_entity: str | None = None,
        target_id: str | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        # Opens its own session — completely independent of any business session.
        # Swallows all errors per D/OQ-01 so business operations are never blocked.
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    await AuditLogRepository.create(
                        event_type.value,
                        actor_user_id=actor_user_id,
                        actor_role=actor_role,
                        tenant_id=tenant_id,
                        schema_name=schema_name,
                        target_entity=target_entity,
                        target_id=target_id,
                        metadata=metadata,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        db=session,
                    )
        except Exception:
            logger.error(
                "audit_write_failed event_type=%s actor=%s tenant=%s",
                event_type.value,
                actor_user_id,
                tenant_id,
                exc_info=True,
            )

    @staticmethod
    async def query(
        *,
        current_role: str,
        current_tenant_id: UUID | None,
        filter_tenant_id: UUID | None = None,
        event_type: AuditEventType | None = None,
        actor_user_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> AuditLogListResponse:
        is_super_admin = (current_role == "SUPER_ADMIN")

        if is_super_admin:
            # SUPER_ADMIN: can filter by any tenant_id; if none given, sees everything
            restrict = False
            effective_tenant_id = filter_tenant_id
        else:
            # ADMIN: always restricted to their own tenant; filter_tenant_id ignored
            restrict = True
            effective_tenant_id = current_tenant_id

        offset = (page - 1) * page_size

        total = await AuditLogRepository.count(
            tenant_id=effective_tenant_id,
            restrict_to_tenant=restrict,
            event_type=event_type.value if event_type else None,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
            db=db,
        )
        rows = await AuditLogRepository.list(
            tenant_id=effective_tenant_id,
            restrict_to_tenant=restrict,
            event_type=event_type.value if event_type else None,
            actor_user_id=actor_user_id,
            date_from=date_from,
            date_to=date_to,
            offset=offset,
            limit=page_size,
            db=db,
        )
        items = [AuditLogEntry.model_validate(r) for r in rows]
        return AuditLogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )
```

**Acceptance check:**
`python -c "from app.core.audit_log.service import AuditService; print('ok')"` passes.

---

### STEP-05 — Router + main.py wiring
**Depends on:** STEP-04
**Files:**
- `backend/app/core/audit_log/router.py`
- `backend/app/main.py`

**`audit_log/router.py`:**

```python
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.auth.dependencies import require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.audit_log.models import AuditEventType
from app.core.audit_log.schemas import AuditLogListResponse
from app.core.audit_log.service import AuditService

router = APIRouter(tags=["audit-log"])


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    event_type:     AuditEventType | None = Query(None),
    actor_user_id:  UUID | None           = Query(None),
    tenant_id:      UUID | None           = Query(None),
    date_from:      datetime | None       = Query(None),
    date_to:        datetime | None       = Query(None),
    page:           int                   = Query(1,  ge=1),
    page_size:      int                   = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> AuditLogListResponse:
    return await AuditService.query(
        current_role=current_user.role,
        current_tenant_id=current_user.tenant_id,
        filter_tenant_id=tenant_id,
        event_type=event_type,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        db=db,
    )
```

**RBAC enforced by `require_roles(TenantRole.ADMIN)`:**
- SUPER_ADMIN: passes the bypass check; `current_role = "SUPER_ADMIN"` → sees all
- ADMIN: passes; restricted to `current_tenant_id`
- FACULTY / STUDENT / BOARD / GUIDE: 403

**`main.py` — add two lines:**
```python
from app.core.audit_log.router import router as audit_log_router
# in the routers section:
app.include_router(audit_log_router, prefix="/audit-logs")
```

**Acceptance check:**
`GET /audit-logs` with SUPER_ADMIN token → 200 (empty list or seeded entries).
`GET /audit-logs` with FACULTY token → 403.
`GET /audit-logs` with ADMIN token → 200 (tenant-scoped).

---

### STEP-06 — Auth integration
**Depends on:** STEP-04
**Files:**
- `backend/app/core/auth/service.py`
- `backend/app/core/auth/router.py`
- `backend/app/core/auth/platform_router.py`
- `backend/app/core/auth/admin_router.py`

This step adds `await AuditService.log(...)` calls throughout the auth module.
It also adjusts service method signatures to accept `ip_address` and `user_agent`
where they are not yet present, and updates routers to pass those values.

---

#### 6A — `TenantAuthService` changes in `service.py`

**`login()`** — signatures unchanged; ADD audit calls:
```
SUCCESS path (after last_login_at update):
    await AuditService.log(
        AuditEventType.AUTH_LOGIN_SUCCESS,
        actor_user_id=user.id,
        actor_role=user.role.value,
        tenant_id=tenant_id,
        schema_name=schema_name,
        target_entity="User", target_id=str(user.id),
        ip_address=ip, user_agent=user_agent,
    )

FAILURE path (user not found or inactive — BEFORE raise):
    await AuditService.log(
        AuditEventType.AUTH_LOGIN_FAILURE,
        actor_role=None, tenant_id=tenant_id, schema_name=schema_name,
        metadata={"attempted_email": email, "reason": "user_not_found_or_inactive"},
        ip_address=ip, user_agent=user_agent,
    )
    raise AuthError(...)

FAILURE path (wrong password — BEFORE raise):
    await AuditService.log(
        AuditEventType.AUTH_LOGIN_FAILURE,
        actor_user_id=user.id, actor_role=user.role.value,
        tenant_id=tenant_id, schema_name=schema_name,
        target_entity="User", target_id=str(user.id),
        metadata={"reason": "invalid_password"},
        ip_address=ip, user_agent=user_agent,
    )
    raise AuthError(...)
```

**`refresh_tokens()`** — signatures unchanged; ADD audit calls (inside nested session):
```
REUSE DETECTED (before raise, inside _open_tenant_session block):
    await AuditService.log(
        AuditEventType.AUTH_TOKEN_REUSE_DETECTED,
        actor_user_id=record.user_id, schema_name=schema_name,
        tenant_id=tenant.id, ip_address=ip, user_agent=user_agent,
    )

SUCCESS (after new token pair created, before return):
    await AuditService.log(
        AuditEventType.AUTH_TOKEN_REFRESH,
        actor_user_id=user.id, actor_role=user.role.value,
        tenant_id=tenant.id, schema_name=schema_name,
        ip_address=ip, user_agent=user_agent,
    )
```

**`logout()`** — NEW params: add `actor_user_id: UUID | None`, `actor_role: str | None`,
`tenant_id: UUID | None`, `schema_name: str | None`, `ip_address: str | None`,
`user_agent: str | None` before `db`:
```python
async def logout(
    raw_token: str,
    actor_user_id: UUID | None,
    actor_role: str | None,
    tenant_id: UUID | None,
    schema_name: str | None,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> None:
    # ... existing logic ...
    # After revocation (or if already revoked — logout is idempotent):
    await AuditService.log(
        AuditEventType.AUTH_LOGOUT,
        actor_user_id=actor_user_id, actor_role=actor_role,
        tenant_id=tenant_id, schema_name=schema_name,
        ip_address=ip_address, user_agent=user_agent,
    )
```

**`logout_all()`** — ADD params `actor_role: str | None`, `tenant_id: UUID | None`,
`ip_address: str | None`, `user_agent: str | None`:
```python
async def logout_all(
    user_id: UUID,
    actor_role: str | None,
    tenant_id: UUID | None,
    schema_name: str,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> None:
    # ... existing logic ...
    await AuditService.log(
        AuditEventType.AUTH_LOGOUT_ALL,
        actor_user_id=user_id, actor_role=actor_role,
        tenant_id=tenant_id, schema_name=schema_name,
        ip_address=ip_address, user_agent=user_agent,
    )
```

**`request_password_reset()`** — ADD params `tenant_id: UUID`, `schema_name: str`,
`ip_address: str | None`, `user_agent: str | None`:
```python
# Only log if user actually exists (preserves no-enumeration):
if user and user.is_active:
    await AuditService.log(
        AuditEventType.AUTH_PASSWORD_RESET_REQUESTED,
        actor_user_id=user.id, actor_role=user.role.value,
        tenant_id=tenant_id, schema_name=schema_name,
        target_entity="User", target_id=str(user.id),
        ip_address=ip_address, user_agent=user_agent,
    )
return  # always silent
```

**`verify_otp_and_issue_reset_token()`** — ADD params `tenant_id: UUID`,
`ip_address: str | None`, `user_agent: str | None`:
```
OTP_FAILED (before raise, inside max-attempts block):
    await AuditService.log(
        AuditEventType.AUTH_PASSWORD_RESET_OTP_FAILED,
        actor_user_id=user.id, actor_role=user.role.value,
        tenant_id=tenant_id, schema_name=schema_name,
        metadata={"attempts": otp_record.attempts + 1},
        ip_address=ip_address, user_agent=user_agent,
    )

SUCCESS (before return):
    await AuditService.log(
        AuditEventType.AUTH_PASSWORD_RESET_VERIFIED,
        actor_user_id=user.id, actor_role=user.role.value,
        tenant_id=tenant_id, schema_name=schema_name,
        ip_address=ip_address, user_agent=user_agent,
    )
```

**`confirm_password_reset()`** — ADD params `ip_address: str | None`,
`user_agent: str | None`. The schema_name comes from the JWT, tenant_id requires a
`get_tenant_by_schema_name` lookup (already in PublicRepository):
```
SUCCESS (inside _open_tenant_session, after password hash updated):
    tenant = await PublicRepository.get_tenant_by_schema_name(schema_name, public_db)
    await AuditService.log(
        AuditEventType.AUTH_PASSWORD_RESET_COMPLETED,
        actor_user_id=user_id, schema_name=schema_name,
        tenant_id=tenant.id if tenant else None,
        target_entity="User", target_id=str(user_id),
        ip_address=ip_address, user_agent=user_agent,
    )
```
Note: `confirm_password_reset` currently only uses `db` (public) at the start for token
decode, then opens `_open_tenant_session`. To get `tenant.id`, open a brief public
session or use the `db` param at the call site. Pass a `public_db: AsyncSession` as well,
or look up tenant inside `_open_tenant_session` since `public` is in the search_path.
Simplest: since `SET LOCAL search_path = schema_name, public`, a query for
`public.tenants` still resolves. Use the tenant_db session to call
`PublicRepository.get_tenant_by_schema_name(schema_name, tenant_db)`.

**`create_user()`** — ADD params `actor_user_id: UUID`, `actor_role: str`,
`tenant_id: UUID`, `schema_name: str`, `ip_address: str | None`, `user_agent: str | None`:
```python
async def create_user(
    payload: CreateUserRequest,
    actor_user_id: UUID,
    actor_role: str,
    tenant_id: UUID,
    schema_name: str,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> UserResponse:
    # ... existing logic ...
    # After user created:
    await AuditService.log(
        AuditEventType.USER_CREATED,
        actor_user_id=actor_user_id, actor_role=actor_role,
        tenant_id=tenant_id, schema_name=schema_name,
        target_entity="User", target_id=str(user.id),
        metadata={"email": payload.email, "role": payload.role.value},
        ip_address=ip_address, user_agent=user_agent,
    )
```

**Promote `update_user` to a service method** (currently a direct repo call in router):
Add `TenantAuthService.update_user()`:
```python
@staticmethod
async def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    actor_user_id: UUID,
    actor_role: str,
    tenant_id: UUID,
    schema_name: str,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> UserResponse:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise AuthError("NO_FIELDS", "No fields to update", 422)
    user = await TenantRepository.update_user(user_id, updates, db)
    if not user:
        raise AuthError("USER_NOT_FOUND", "User not found", 404)

    # Determine event type by what changed
    if "is_active" in updates and updates["is_active"] is False:
        event = AuditEventType.USER_DEACTIVATED
    elif "role" in updates:
        event = AuditEventType.USER_ROLE_CHANGED
    else:
        event = AuditEventType.USER_UPDATED

    await AuditService.log(
        event,
        actor_user_id=actor_user_id, actor_role=actor_role,
        tenant_id=tenant_id, schema_name=schema_name,
        target_entity="User", target_id=str(user_id),
        metadata={"changes": updates},
        ip_address=ip_address, user_agent=user_agent,
    )
    return UserResponse.model_validate(user)
```

---

#### 6B — `PlatformAuthService` changes in `service.py`

**`login()`** — signatures unchanged; ADD audit calls:
```
SUCCESS (before return):
    await AuditService.log(
        AuditEventType.PLATFORM_LOGIN_SUCCESS,
        actor_user_id=user.id, actor_role="SUPER_ADMIN",
        ip_address=ip, user_agent=user_agent,
    )

FAILURE (BEFORE each raise):
    await AuditService.log(
        AuditEventType.PLATFORM_LOGIN_FAILURE,
        metadata={"attempted_email": email},
        ip_address=ip, user_agent=user_agent,
    )
    raise AuthError(...)
```

**`refresh_tokens()`** — signatures unchanged; ADD audit calls:
```
REUSE DETECTED (before raise):
    await AuditService.log(
        AuditEventType.PLATFORM_TOKEN_REUSE_DETECTED,
        actor_user_id=record.user_id, actor_role="SUPER_ADMIN",
        ip_address=ip, user_agent=user_agent,
    )

SUCCESS (before return):
    await AuditService.log(
        AuditEventType.PLATFORM_TOKEN_REFRESH,
        actor_user_id=user.id, actor_role="SUPER_ADMIN",
        ip_address=ip, user_agent=user_agent,
    )
```

**`logout()`** — ADD params `actor_user_id: UUID | None`, `ip_address: str | None`,
`user_agent: str | None`:
```
After revocation:
    await AuditService.log(
        AuditEventType.PLATFORM_LOGOUT,
        actor_user_id=actor_user_id, actor_role="SUPER_ADMIN",
        ip_address=ip_address, user_agent=user_agent,
    )
```

**`logout_all()`** — ADD params `ip_address: str | None`, `user_agent: str | None`:
```
After all tokens revoked:
    await AuditService.log(
        AuditEventType.PLATFORM_LOGOUT_ALL,
        actor_user_id=user_id, actor_role="SUPER_ADMIN",
        ip_address=ip_address, user_agent=user_agent,
    )
```

**`request_password_reset()`** — ADD params `ip_address: str | None`, `user_agent: str | None`:
```
If user found and active:
    await AuditService.log(
        AuditEventType.PLATFORM_PASSWORD_RESET_REQUESTED,
        actor_user_id=user.id, actor_role="SUPER_ADMIN",
        ip_address=ip_address, user_agent=user_agent,
    )
```

**`verify_otp_and_issue_reset_token()`** — ADD params `ip_address: str | None`, `user_agent: str | None`:
```
OTP_FAILED (before raise):
    await AuditService.log(AuditEventType.PLATFORM_PASSWORD_RESET_OTP_FAILED, ...)

SUCCESS (before return):
    await AuditService.log(AuditEventType.PLATFORM_PASSWORD_RESET_VERIFIED, ...)
```

**`confirm_password_reset()`** — ADD params `ip_address: str | None`, `user_agent: str | None`:
```
SUCCESS (after password updated):
    await AuditService.log(
        AuditEventType.PLATFORM_PASSWORD_RESET_COMPLETED,
        actor_user_id=user_id, actor_role="SUPER_ADMIN",
        target_entity="PlatformUser", target_id=str(user_id),
        ip_address=ip_address, user_agent=user_agent,
    )
```

---

#### 6C — Router call site updates

**`router.py` (tenant auth):**

`logout` handler — add `request: Request`, pass new params:
```python
await TenantAuthService.logout(
    body.refresh_token,
    current_user.user_id,
    current_user.role,
    current_user.tenant_id,
    current_user.schema_name,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`logout_all` handler — add `request: Request`, pass new params:
```python
await TenantAuthService.logout_all(
    current_user.user_id,
    current_user.role,
    current_user.tenant_id,
    current_user.schema_name,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`request_reset` handler — already has `request: Request`; pass new params to service:
```python
await TenantAuthService.request_password_reset(
    body.email,
    tenant.id,
    tenant.schema_name,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`verify_otp` handler — add `request: Request`; pass new params:
```python
return await TenantAuthService.verify_otp_and_issue_reset_token(
    body.email, body.otp,
    tenant.schema_name,
    tenant.id,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`confirm_reset` handler — add `request: Request`; pass new params:
```python
await TenantAuthService.confirm_password_reset(
    body.reset_token, body.new_password,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

**`platform_router.py`:**

`platform_refresh` handler — currently passes `None, None` for ip/user_agent; add
`request: Request` and pass real values:
```python
return await PlatformAuthService.refresh_tokens(
    body.refresh_token,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`platform_logout` handler — add `request: Request`; pass new params:
```python
await PlatformAuthService.logout(
    body.refresh_token,
    current_user.user_id,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`platform_logout_all` handler — add `request: Request`; pass ip/ua:
```python
await PlatformAuthService.logout_all(
    current_user.user_id,
    request.client.host if request.client else None,
    request.headers.get("user-agent"),
    db,
)
```

`platform_request_reset`, `platform_verify_otp`, `platform_confirm_reset` — add
`request: Request` to each; extract and pass ip/ua.

**`admin_router.py`:**

`create_user` handler — add `current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN))`
and `request: Request` as explicit params (FastAPI caches the Depends result — no double evaluation):
```python
@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    request: Request,
    body: CreateUserRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_get_admin_db),
) -> UserResponse:
    return await TenantAuthService.create_user(
        body,
        current_user.user_id,
        current_user.role,
        current_user.tenant_id,
        current_user.schema_name,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
        db,
    )
```

`update_user` handler — route through new `TenantAuthService.update_user()`:
```python
@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: UUID,
    body: UpdateUserRequest,
    current_user: CurrentUser = Depends(require_roles(TenantRole.ADMIN)),
    db: AsyncSession = Depends(_get_admin_db),
) -> UserResponse:
    try:
        return await TenantAuthService.update_user(
            user_id, body,
            current_user.user_id,
            current_user.role,
            current_user.tenant_id,
            current_user.schema_name,
            request.client.host if request.client else None,
            request.headers.get("user-agent"),
            db,
        )
    except AuthError as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"error": e.code, "message": e.message})
```

**Acceptance check:** All existing auth integration tests still pass.
`POST /auth/login` with correct creds → 200 AND one `public.audit_logs` row with
`event_type = AUTH_LOGIN_SUCCESS`.
`POST /auth/login` with wrong password → 401 AND one row with `event_type = AUTH_LOGIN_FAILURE`.

---

### STEP-07 — Tenants integration + integration tests
**Depends on:** STEP-04, STEP-06
**Files:**
- `backend/app/core/tenants/service.py`
- `backend/tests/core/audit_log/__init__.py`
- `backend/tests/core/audit_log/test_audit_log.py`

---

#### 7A — `TenantService` changes

**`create_tenant()`** — the service needs `actor_user_id` and `ip_address` / `user_agent`
to audit the SUPER_ADMIN who provisioned the tenant. These come from the router.

Change `create_tenant()` signature to accept:
```python
async def create_tenant(
    body: CreateTenantRequest,
    actor_user_id: UUID,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> TenantResponse:
```

Add audit call after tenant becomes ACTIVE:
```python
await AuditService.log(
    AuditEventType.TENANT_PROVISIONED,
    actor_user_id=actor_user_id,
    actor_role="SUPER_ADMIN",
    tenant_id=tenant.id,
    schema_name=tenant.schema_name,
    target_entity="Tenant",
    target_id=str(tenant.id),
    metadata={"name": tenant.name, "slug": tenant.slug},
    ip_address=ip_address,
    user_agent=user_agent,
)
```

**`update_tenant()`** — add `actor_user_id`, `ip_address`, `user_agent`:
```python
# After successful update:
event = (
    AuditEventType.TENANT_DEACTIVATED
    if updates.get("is_active") is False
    else AuditEventType.TENANT_UPDATED
)
await AuditService.log(
    event,
    actor_user_id=actor_user_id, actor_role="SUPER_ADMIN",
    tenant_id=tenant.id, schema_name=tenant.schema_name,
    target_entity="Tenant", target_id=str(tenant_id),
    metadata={"changes": updates},
    ip_address=ip_address, user_agent=user_agent,
)
```

Update `tenants/router.py` to extract and pass `current_user.user_id`, `request.client.host`,
and `request.headers.get("user-agent")` to each service method.

---

#### 7B — Integration tests: `test_audit_log.py`

Uses the same `conftest.py` fixtures from TASK-001 (`test_tenant_a`, `admin_user_a`,
`test_platform_user`, `async_client`, `tenant_headers`, `platform_headers`).

Add helper fixture:
```python
async def get_audit_logs(client, headers, **query_params) -> dict:
    resp = await client.get("/audit-logs", headers=headers, params=query_params)
    return resp.json()
```

**Test cases:**

`test_login_success_writes_audit`:
- `POST /auth/login` with correct creds → 200
- SUPER_ADMIN `GET /audit-logs?event_type=AUTH_LOGIN_SUCCESS` → items list contains one entry
- Entry has correct `actor_user_id`, `tenant_id`, `schema_name`

`test_login_failure_writes_audit`:
- `POST /auth/login` with wrong password → 401
- SUPER_ADMIN `GET /audit-logs?event_type=AUTH_LOGIN_FAILURE` → at least one entry
- Entry has `actor_user_id` matching the user (found by email, wrong password branch)
- `metadata["reason"] == "invalid_password"`

`test_login_failure_unknown_email`:
- `POST /auth/login` with non-existent email → 401
- SUPER_ADMIN `GET /audit-logs?event_type=AUTH_LOGIN_FAILURE` → entry with `actor_user_id=null`
- `metadata["attempted_email"]` present

`test_platform_login_writes_audit`:
- `POST /platform/auth/login` SUPER_ADMIN login → 200
- `GET /audit-logs?event_type=PLATFORM_LOGIN_SUCCESS` → one entry, `tenant_id=null`

`test_token_reuse_writes_audit`:
- Login, capture refresh token, use it once (valid refresh), use OLD token again → 401
- SUPER_ADMIN `GET /audit-logs?event_type=AUTH_TOKEN_REUSE_DETECTED` → entry present

`test_password_reset_full_flow_writes_audit`:
- Request OTP → `AUTH_PASSWORD_RESET_REQUESTED`
- Verify OTP → `AUTH_PASSWORD_RESET_VERIFIED`
- Confirm reset → `AUTH_PASSWORD_RESET_COMPLETED`
- All three events present in audit log with same `actor_user_id`

`test_user_created_writes_audit`:
- ADMIN creates FACULTY → 201
- `GET /audit-logs?event_type=USER_CREATED` → entry with correct tenant scoping
- `metadata["role"] == "FACULTY"`

`test_user_role_changed_writes_audit`:
- ADMIN patches user with `{"role": "DEAN"}` → 200
- `GET /audit-logs?event_type=USER_ROLE_CHANGED` → entry
- `metadata["changes"]["role"] == "DEAN"`

`test_user_deactivated_writes_audit`:
- ADMIN patches user with `{"is_active": false}` → 200
- `GET /audit-logs?event_type=USER_DEACTIVATED` → entry

`test_tenant_admin_cannot_see_other_tenant_logs`:
- Login succeeds for `admin_user_a` (tenant A) and `admin_user_b` (tenant B)
- `admin_user_a` calls `GET /audit-logs` → sees only tenant A events
- Events from tenant B (seeded by performing login in tenant B) are NOT in response

`test_super_admin_sees_all_logs`:
- SUPER_ADMIN `GET /audit-logs` → items from BOTH tenant A and tenant B present
- SUPER_ADMIN `GET /audit-logs?tenant_id=<tenant_a_id>` → only tenant A events

`test_tenant_provisioned_writes_audit`:
- SUPER_ADMIN creates a new tenant → 201
- `GET /audit-logs?event_type=TENANT_PROVISIONED` → entry with `schema_name` set

`test_audit_logs_no_update_delete_api`:
- `PATCH /audit-logs/{id}` → 405 (Method Not Allowed — no route registered)
- `DELETE /audit-logs/{id}` → 405

`test_faculty_cannot_access_audit_logs`:
- `GET /audit-logs` with FACULTY token → 403

`test_pagination`:
- Seed multiple events (10 logins)
- `GET /audit-logs?page=1&page_size=3` → `items` length == 3, `total >= 10`
- `GET /audit-logs?page=2&page_size=3` → different items

**Acceptance check:**
```
pytest tests/core/audit_log/ -v
```
All tests pass.

```
pytest tests/ -v
```
Full suite still passes (STEP-06 changes did not break existing auth tests).

---

## Execution Order

```
STEP-01 (model + migration)
  └── STEP-02 (repository)
        └── STEP-03 (schemas)
              └── STEP-04 (service)
                    ├── STEP-05 (router + main.py wiring)
                    └── STEP-06 (auth integration)
                              └── STEP-07 (tenants integration + tests)
```

Steps 05 and 06 both depend on STEP-04 and can be done in parallel by different
sub-agents, but STEP-07 requires STEP-06 to be complete.

---

## Sub-agent Scope

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

| Concern | Phase 0 (dev) | Future |
|---------|--------------|--------|
| Audit write latency | ~1–2ms synchronous INSERT; acceptable | Celery background task if > 5ms p99 |
| Retention policy | None — all logs kept | Add `created_at < now() - interval '1 year'` archival job |
| Analytics | Raw SQL / pgAdmin queries only | Phase 3: materialized views or clickhouse export |
| Compliance export | None in Phase 0 | `GET /audit-logs/export?format=csv` added when required |
| Platform-only events | `tenant_id IS NULL` rows; SUPER_ADMIN visible | SUPER_ADMIN filter UI in admin panel |

---

## PDCA Log

### Cycle 1

Plan: Brainstorm complete 2026-05-06. All decisions locked (D-01 through D-06, OQ-01 through OQ-03).
Approved: PENDING — awaiting Srinivas approval.
Do:
Check:
Act:

---

## Checkpoints

Step: STEP-01 AuditLog model + migration
Status: PENDING
Git Commit:
Notes:

Step: STEP-02 Repository
Status: PENDING
Git Commit:
Notes:

Step: STEP-03 Pydantic schemas
Status: PENDING
Git Commit:
Notes:

Step: STEP-04 AuditService
Status: PENDING
Git Commit:
Notes:

Step: STEP-05 Router + main.py wiring
Status: PENDING
Git Commit:
Notes:

Step: STEP-06 Auth integration
Status: COMPLETE
Git Commit: TASK-003 STEP-06 auth integration
Notes: AuditService.log calls added to all TenantAuthService and PlatformAuthService methods. TenantAuthService.update_user() promoted to service layer. All four router files updated to pass ip_address and user_agent.

Step: STEP-07 Tenants integration + tests
Status: COMPLETE
Git Commit: a9e766c TASK-003 STEP-07 tenants integration and audit log tests
Notes: TenantService audit calls added. db.begin() replaced with explicit db.commit()/db.rollback(). models.py native_enum=False fix for TenantStatus. conftest.py: ON CONFLICT no longer updates tenant PK; unique ASGITransport IP per test to avoid rate-limit bleed. test_audit_log.py: .test TLD changed to .com. 15/15 tests pass.
