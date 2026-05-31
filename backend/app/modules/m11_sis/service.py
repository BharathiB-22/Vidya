from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.modules.m11_sis.models import SisSchool
from app.modules.m11_sis.repository import SchoolRepository
from app.modules.m11_sis.schemas import SchoolCreate, SchoolUpdate


class SchoolServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SchoolService:

    @staticmethod
    async def list_schools(
        db: AsyncSession,
        include_inactive: bool = False,
    ) -> list[SisSchool]:
        return await SchoolRepository.list_all(db, include_inactive=include_inactive)

    @staticmethod
    async def get_school(school_id: UUID, db: AsyncSession) -> SisSchool:
        school = await SchoolRepository.get_by_id(school_id, db)
        if school is None:
            raise SchoolServiceError("NOT_FOUND", "School not found.", 404)
        return school

    @staticmethod
    async def create_school(
        body: SchoolCreate,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> SisSchool:
        if await SchoolRepository.get_by_code(body.code, db):
            raise SchoolServiceError("DUPLICATE_CODE", f"School code '{body.code}' already exists.")
        if await SchoolRepository.get_by_name(body.name, db):
            raise SchoolServiceError("DUPLICATE_NAME", f"School '{body.name}' already exists.")
        school = await SchoolRepository.create(body.code, body.name, body.description, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.SCHOOL_CREATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_school",
            target_id=str(school.id),
            metadata={"code": school.code, "name": school.name},
        )
        return school

    @staticmethod
    async def update_school(
        school_id: UUID,
        body: SchoolUpdate,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> SisSchool:
        school = await SchoolRepository.get_by_id(school_id, db)
        if school is None:
            raise SchoolServiceError("NOT_FOUND", "School not found.", 404)
        updates = body.model_dump(exclude_none=True)
        if "code" in updates and updates["code"] != school.code:
            if await SchoolRepository.get_by_code(updates["code"], db):
                raise SchoolServiceError("DUPLICATE_CODE", f"School code '{updates['code']}' already exists.")
        if "name" in updates and updates["name"] != school.name:
            if await SchoolRepository.get_by_name(updates["name"], db):
                raise SchoolServiceError("DUPLICATE_NAME", f"School '{updates['name']}' already exists.")
        school = await SchoolRepository.update(school, updates, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.SCHOOL_UPDATED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_school",
            target_id=str(school.id),
            metadata={"fields_updated": list(updates.keys())},
        )
        return school

    @staticmethod
    async def delete_school(
        school_id: UUID,
        actor_user_id: UUID,
        actor_role: str,
        tenant_id: UUID,
        schema_name: str,
        db: AsyncSession,
    ) -> None:
        school = await SchoolRepository.get_by_id(school_id, db)
        if school is None:
            raise SchoolServiceError("NOT_FOUND", "School not found.", 404)
        dept_count = await SchoolRepository.count_departments(school_id, db)
        if dept_count > 0:
            raise SchoolServiceError(
                "SCHOOL_HAS_DEPARTMENTS",
                f"Cannot delete school: {dept_count} department(s) are linked to it.",
                409,
            )
        school_name = school.name
        await SchoolRepository.delete(school, db)
        await db.commit()
        await AuditService.log(
            AuditEventType.SCHOOL_DELETED,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="sis_school",
            target_id=str(school_id),
            metadata={"name": school_name},
        )
