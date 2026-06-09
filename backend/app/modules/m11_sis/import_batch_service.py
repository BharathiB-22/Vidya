"""SIS Import Batch Service — H64.1 (list/get/create).

Rollback and delete logic are added in H64.2.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.models import SisImportBatch


class ImportBatchServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code       = code
        self.message    = message
        self.status_code = status_code
        super().__init__(message)


class ImportBatchService:

    @staticmethod
    async def list_batches(
        db: AsyncSession,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SisImportBatch], int]:
        total_q = await db.execute(select(func.count()).select_from(SisImportBatch))
        total   = total_q.scalar_one()

        rows_q = await db.execute(
            select(SisImportBatch)
            .order_by(SisImportBatch.imported_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(rows_q.scalars().all())
        return rows, total

    @staticmethod
    async def get_batch(batch_id: UUID, db: AsyncSession) -> SisImportBatch:
        row = await db.get(SisImportBatch, batch_id)
        if row is None:
            raise ImportBatchServiceError("NOT_FOUND", "Import batch not found", 404)
        return row

    @staticmethod
    async def create_batch(
        *,
        imported_by: UUID,
        record_type: str,
        total_records: int,
        success_count: int,
        failed_count: int,
        db: AsyncSession,
    ) -> SisImportBatch:
        now = datetime.now(timezone.utc)
        # Generate a short human-readable ref: IMPORT-YYYYMMDD-XXXX
        short = str(_uuid.uuid4()).replace("-", "")[:6].upper()
        batch_ref = f"IMPORT-{now.strftime('%Y%m%d')}-{short}"

        batch = SisImportBatch(
            id            = _uuid.uuid4(),
            batch_ref     = batch_ref,
            imported_by   = imported_by,
            imported_at   = now,
            record_type   = record_type,
            total_records = total_records,
            success_count = success_count,
            failed_count  = failed_count,
            is_rolled_back= False,
        )
        db.add(batch)
        await db.flush()   # get the id before the caller stamps it on profiles
        return batch
