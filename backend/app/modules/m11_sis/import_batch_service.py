"""SIS Import Batch Service — H64.1 / P1.4 (list/get/create/rollback).

Context columns (program_id/name, batch_id/name, semester_id/name,
section_id/name) are managed entirely via raw SQL so that this service
degrades gracefully when migration 0054ten has not yet been applied:

* Reads:  SELECT * via raw SQL — returns whatever columns exist in the DB.
* Writes: INSERT base fields via ORM, then UPDATE context via savepoint-wrapped
          raw SQL.  If the UPDATE fails (column missing), the savepoint rolls
          back the UPDATE only; the batch INSERT is preserved.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime as _datetime, timezone as _timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.models import SisImportBatch


class ImportBatchServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Internal: raw-SQL row → dict (schema-adaptive, handles pre-0054ten DBs)
# ---------------------------------------------------------------------------

def _row_to_dict(row_mapping: Any) -> dict:
    """Convert a raw SQL row mapping to a plain dict with context defaults."""
    d = dict(row_mapping)
    for key in (
        "program_id", "program_name",
        "batch_id", "batch_name",
        "semester_id", "semester_name",
        "section_id", "section_name",
    ):
        d.setdefault(key, None)
    return d


class ImportBatchService:

    @staticmethod
    async def list_batches(
        db: AsyncSession,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        total_q = await db.execute(select(func.count()).select_from(SisImportBatch))
        total   = total_q.scalar_one()

        rows_q = await db.execute(
            text(
                "SELECT * FROM sis_import_batches "
                "ORDER BY imported_at DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": limit, "offset": offset},
        )
        return [_row_to_dict(r) for r in rows_q.mappings()], total

    @staticmethod
    async def get_batch(batch_id: UUID, db: AsyncSession) -> dict:
        rows_q = await db.execute(
            text("SELECT * FROM sis_import_batches WHERE id = :id"),
            {"id": str(batch_id)},
        )
        row = rows_q.mappings().one_or_none()
        if row is None:
            raise ImportBatchServiceError("NOT_FOUND", "Import batch not found", 404)
        return _row_to_dict(row)

    @staticmethod
    async def create_batch(
        *,
        imported_by: UUID,
        record_type: str,
        total_records: int,
        success_count: int,
        failed_count: int,
        db: AsyncSession,
        source_filename: str | None = None,
        # P1.4 context — optional, silently skipped if migration 0054ten not applied
        program_id:    UUID | None = None,
        program_name:  str | None = None,
        batch_id:      UUID | None = None,
        batch_name:    str | None = None,
        semester_id:   UUID | None = None,
        semester_name: str | None = None,
        section_id:    UUID | None = None,
        section_name:  str | None = None,
    ) -> SisImportBatch:
        now       = _datetime.now(_timezone.utc)
        short     = str(_uuid.uuid4()).replace("-", "")[:6].upper()
        batch_ref = f"IMPORT-{now.strftime('%Y%m%d')}-{short}"

        batch = SisImportBatch(
            id             = _uuid.uuid4(),
            batch_ref      = batch_ref,
            imported_by    = imported_by,
            imported_at    = now,
            record_type    = record_type,
            source_filename= source_filename,
            total_records  = total_records,
            success_count  = success_count,
            failed_count   = failed_count,
            is_rolled_back = False,
        )
        db.add(batch)
        await db.flush()  # persists INSERT; batch.id is now available

        # Try to stamp academic context via savepoint-protected raw SQL.
        # If migration 0054ten has not been applied, the UPDATE fails and the
        # savepoint rolls back only the UPDATE — the batch INSERT is kept.
        if any([program_id, batch_id, semester_id, section_id]):
            try:
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "UPDATE sis_import_batches SET "
                            "program_id    = :pid, "
                            "program_name  = :pname, "
                            "batch_id      = :bid, "
                            "batch_name    = :bname, "
                            "semester_id   = :semid, "
                            "semester_name = :semname, "
                            "section_id    = :secid, "
                            "section_name  = :secname "
                            "WHERE id = :id"
                        ),
                        {
                            "pid":     str(program_id)  if program_id  else None,
                            "pname":   program_name,
                            "bid":     str(batch_id)    if batch_id    else None,
                            "bname":   batch_name,
                            "semid":   str(semester_id) if semester_id else None,
                            "semname": semester_name,
                            "secid":   str(section_id)  if section_id  else None,
                            "secname": section_name,
                            "id":      str(batch.id),
                        },
                    )
            except DatabaseError:
                # Context columns not yet migrated (0054ten pending) — batch is
                # still created without context; history shows "Unknown" values.
                pass

        return batch

    @staticmethod
    async def rollback_batch(
        batch_id: UUID,
        *,
        actor_user_id: UUID,
        db: AsyncSession,
    ) -> SisImportBatch:
        """
        Human-gate rollback: detaches import_batch_id from affected profiles
        and marks the batch as rolled back.
        """
        from sqlalchemy import update as sa_update
        from app.modules.m11_sis.models import SisStudentProfile

        batch = await db.get(SisImportBatch, batch_id)
        if batch is None:
            raise ImportBatchServiceError("NOT_FOUND", "Import batch not found", 404)
        if batch.is_rolled_back:
            raise ImportBatchServiceError(
                "ALREADY_ROLLED_BACK",
                "This batch has already been rolled back.",
                409,
            )

        await db.execute(
            sa_update(SisStudentProfile)
            .where(SisStudentProfile.import_batch_id == batch_id)
            .values(import_batch_id=None)
        )

        now = _datetime.now(_timezone.utc)
        batch.is_rolled_back = True
        batch.rolled_back_by = actor_user_id
        batch.rolled_back_at = now
        await db.flush()
        return batch
